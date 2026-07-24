"""Command-line interface for rolodexter.

Map a contact export to the canonical schema, explain how a header resolves,
or list the canonical fields — without writing any Python.

Examples
--------
::

    rolodexter map contacts.csv -o clean.csv
    rolodexter map export.json --format jsonl -o out.jsonl --region GB
    rolodexter map messy.csv --min-confidence 0.8 --strict
    rolodexter explain "Job Titel" --value CEO
    rolodexter fields

Run as ``rolodexter <command>`` (console script) or ``python -m rolodexter``.

.. versionadded:: 2.8.0
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import json
import os
import sys
import tempfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from .core import CanonicalField, ContactMapper, MappingResult, RolodexterError

DEFAULT_MAX_MATERIALIZED_ROWS = 100_000
DEFAULT_MAX_JSON_INPUT_BYTES = 50 * 1024 * 1024

# ── I/O helpers ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _InputRow:
    row_number: int
    data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _RowFailure:
    row_number: int
    error: str
    raw: Any


@dataclass(slots=True)
class _MapStats:
    failed: int = 0


def _detect_format(path: str | None, explicit: str) -> str:
    """Resolve the file format from an explicit flag or the file extension."""
    if explicit and explicit != "auto":
        return explicit
    low = (path or "").lower()
    if low.endswith((".jsonl", ".ndjson")):
        return "jsonl"
    if low.endswith(".json"):
        return "json"
    return "csv"


def _read_row_items(
    path: str,
    fmt: str,
    *,
    max_json_bytes: int | None = DEFAULT_MAX_JSON_INPUT_BYTES,
) -> Iterator[_InputRow | _RowFailure]:
    """Yield rows or row-level failures from *path* in the given *fmt*."""
    if fmt == "csv":
        with open(path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for row_number, row in enumerate(reader, start=2):
                # csv.DictReader stores surplus cells under a None key by default.
                # They have no header to map and previously leaked into the mapper.
                row.pop(None, None)
                yield _InputRow(reader.line_num or row_number, row)
    elif fmt == "jsonl":
        with open(path, encoding="utf-8") as fh:
            for line_number, line in enumerate(fh, start=1):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError as exc:
                    yield _RowFailure(line_number, f"invalid JSON: {exc.msg}", raw)
                    continue
                if isinstance(obj, dict):
                    yield _InputRow(line_number, obj)
                else:
                    yield _RowFailure(
                        line_number,
                        f"expected JSON object, got {type(obj).__name__}",
                        obj,
                    )
    else:  # json
        if max_json_bytes is not None:
            size = Path(path).stat().st_size
            if size > max_json_bytes:
                raise ValueError(
                    f"JSON input is {size} bytes, above the "
                    f"{max_json_bytes} byte materialization limit; use JSONL "
                    "for streaming input or raise --max-json-input-bytes"
                )
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            yield _InputRow(1, data)
        elif isinstance(data, list):
            for row_number, obj in enumerate(data, start=1):
                if isinstance(obj, dict):
                    yield _InputRow(row_number, obj)
                else:
                    yield _RowFailure(
                        row_number,
                        f"expected JSON object, got {type(obj).__name__}",
                        obj,
                    )


def _read_rows(path: str, fmt: str) -> Iterator[dict[str, Any]]:
    """Yield raw contact dicts from *path* in the given *fmt*."""
    for item in _read_row_items(path, fmt):
        if isinstance(item, _RowFailure):
            raise ValueError(f"row {item.row_number}: {item.error}")
        yield item.data


def _scalarize(value: Any) -> Any:
    """Flatten list/dict values so they fit in a single CSV cell."""
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return value


def _optional_limit(raw: int) -> int | None:
    """Treat 0 as unbounded for CLI numeric limits."""
    return None if raw == 0 else raw


def _collect_normalized_rows(
    results: Iterable[MappingResult],
    *,
    max_rows: int | None,
    materialized_for: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, result in enumerate(results, start=1):
        if max_rows is not None and index > max_rows:
            raise ValueError(
                f"{materialized_for} requires materializing more than "
                f"{max_rows} row(s); use --format jsonl for streaming output "
                "or raise --max-materialized-rows"
            )
        rows.append(result.normalized)
    return rows


def _write_csv(
    results: Iterable[MappingResult],
    out: IO[str],
    *,
    max_rows: int | None,
) -> int:
    rows = _collect_normalized_rows(
        results,
        max_rows=max_rows,
        materialized_for="CSV output",
    )
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: _scalarize(v) for k, v in row.items()})
    return len(rows)


def _write_jsonl(results: Iterable[MappingResult], out: IO[str]) -> int:
    count = 0
    for result in results:
        out.write(json.dumps(result.normalized, ensure_ascii=False) + "\n")
        count += 1
    return count


def _write_json(
    results: Iterable[MappingResult],
    out: IO[str],
    *,
    max_rows: int | None,
) -> int:
    rows = _collect_normalized_rows(
        results,
        max_rows=max_rows,
        materialized_for="JSON output",
    )
    json.dump(rows, out, ensure_ascii=False, indent=2)
    out.write("\n")
    return len(rows)


def _parse_languages(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [code.strip() for code in raw.split(",") if code.strip()]


def _non_negative_int(raw: str) -> int:
    value = int(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return value


def _default_quarantine_path(args: argparse.Namespace) -> str:
    if args.quarantine_output:
        return str(args.quarantine_output)
    base = args.output or args.input
    return f"{base}.quarantine.jsonl"


def _same_path(left: str, right: str) -> bool:
    """Return whether two path spellings resolve to the same filesystem path."""
    return os.path.normcase(str(Path(left).resolve())) == os.path.normcase(
        str(Path(right).resolve())
    )


def _write_quarantine_record(
    failure: _RowFailure,
    out: IO[str],
) -> None:
    out.write(
        json.dumps(
            {
                "row": failure.row_number,
                "error": failure.error,
                "raw": failure.raw,
            },
            ensure_ascii=False,
        )
        + "\n"
    )


def _handle_row_failure(
    failure: _RowFailure,
    *,
    on_error: str,
    stats: _MapStats,
    quarantine_out: IO[str] | None,
) -> None:
    if on_error == "fail":
        raise ValueError(f"row {failure.row_number}: {failure.error}")

    stats.failed += 1
    if on_error == "skip":
        print(
            f"warning: skipped row {failure.row_number}: {failure.error}",
            file=sys.stderr,
        )
        return

    if quarantine_out is None:
        raise ValueError("--on-error quarantine requires a quarantine output")
    _write_quarantine_record(failure, quarantine_out)
    print(
        f"warning: quarantined row {failure.row_number}: {failure.error}",
        file=sys.stderr,
    )


def _map_row_items(
    items: Iterable[_InputRow | _RowFailure],
    mapper: ContactMapper,
    *,
    extract_embedded_phones: bool,
    on_error: str,
    stats: _MapStats,
    quarantine_out: IO[str] | None = None,
) -> Iterator[MappingResult]:
    for item in items:
        if isinstance(item, _RowFailure):
            _handle_row_failure(
                item,
                on_error=on_error,
                stats=stats,
                quarantine_out=quarantine_out,
            )
            continue

        try:
            yield mapper.map_payload(
                item.data,
                extract_embedded_phones=extract_embedded_phones,
            )
        except RolodexterError as exc:
            _handle_row_failure(
                _RowFailure(item.row_number, str(exc), item.data),
                on_error=on_error,
                stats=stats,
                quarantine_out=quarantine_out,
            )


@contextlib.contextmanager
def _atomic_output(path: str) -> Iterator[IO[str]]:
    """Write to a same-directory temp file, then replace *path* on success."""
    target = Path(path)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            newline="",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as fh:
            temp_name = fh.name
            yield fh
        os.replace(temp_name, target)
        temp_name = None
    finally:
        if temp_name is not None:
            with contextlib.suppress(OSError):
                os.unlink(temp_name)


# ── Commands ───────────────────────────────────────────────────────────


def _cmd_map(args: argparse.Namespace) -> int:
    if args.quarantine_output and args.on_error != "quarantine":
        raise ValueError("--quarantine-output requires --on-error quarantine")

    mapper = ContactMapper(
        default_region=args.region,
        languages=_parse_languages(args.languages),
        normalize=not args.no_normalize,
        strict=args.strict,
        confidence_threshold=args.min_confidence,
    )
    in_fmt = _detect_format(args.input, args.in_format)
    if args.output:
        out_fmt = _detect_format(args.output, args.format)
    elif args.format != "auto":
        out_fmt = args.format
    else:
        out_fmt = "json"

    stats = _MapStats()
    max_materialized_rows = _optional_limit(args.max_materialized_rows)
    max_json_bytes = _optional_limit(args.max_json_input_bytes)
    quarantine_path = (
        _default_quarantine_path(args) if args.on_error == "quarantine" else None
    )
    if quarantine_path is not None:
        if _same_path(quarantine_path, args.input):
            raise ValueError("quarantine output must differ from the input path")
        if args.output and _same_path(quarantine_path, args.output):
            raise ValueError(
                "quarantine output must differ from the mapped output path"
            )

    with contextlib.ExitStack() as stack:
        out: IO[str] = (
            stack.enter_context(_atomic_output(args.output))
            if args.output
            else sys.stdout
        )
        quarantine_out: IO[str] | None = None
        if quarantine_path is not None:
            quarantine_out = stack.enter_context(_atomic_output(quarantine_path))

        results = _map_row_items(
            _read_row_items(args.input, in_fmt, max_json_bytes=max_json_bytes),
            mapper,
            extract_embedded_phones=args.embedded_phones,
            on_error=args.on_error,
            stats=stats,
            quarantine_out=quarantine_out,
        )

        if out_fmt == "csv":
            count = _write_csv(results, out, max_rows=max_materialized_rows)
        elif out_fmt == "jsonl":
            count = _write_jsonl(results, out)
        else:
            count = _write_json(results, out, max_rows=max_materialized_rows)

    where = args.output or "stdout"
    message = f"Mapped {count} row(s) -> {where} ({out_fmt})"
    if stats.failed:
        if args.on_error == "quarantine":
            message += f"; quarantined {stats.failed} row(s) -> {quarantine_path}"
        else:
            message += f"; skipped {stats.failed} row(s)"
    print(message, file=sys.stderr)
    return 0


def _cmd_explain(args: argparse.Namespace) -> int:
    mapper = ContactMapper(
        default_region=args.region,
        languages=_parse_languages(args.languages),
    )
    match = mapper.identify(args.header, value=args.value)
    print(
        f"{args.header!r} -> {match.canonical} "
        f"[{match.strategy}, conf={match.confidence:.2f}]"
    )
    if args.value is not None:
        print()
        print(mapper.map_payload({args.header: args.value}).explain())
    return 0


def _cmd_fields(args: argparse.Namespace) -> int:
    for canonical in CanonicalField:
        print(canonical.value)
    return 0


# ── Entry point ────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rolodexter",
        description="Map messy contact data to a clean canonical schema.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_map = sub.add_parser("map", help="Map a CSV/JSON/JSONL file to canonical fields")
    p_map.add_argument("input", help="Input file (.csv, .json, or .jsonl)")
    p_map.add_argument("-o", "--output", help="Output file (default: stdout)")
    p_map.add_argument(
        "--format",
        choices=["auto", "csv", "json", "jsonl"],
        default="auto",
        help="Output format (default: infer from -o extension, else json)",
    )
    p_map.add_argument(
        "--in-format",
        dest="in_format",
        choices=["auto", "csv", "json", "jsonl"],
        default="auto",
        help="Input format (default: infer from the input file extension)",
    )
    p_map.add_argument(
        "--region", default="US", help="Default phone region (ISO-3166 alpha-2)"
    )
    p_map.add_argument(
        "--languages", help="Comma-separated i18n language codes (cached)"
    )
    p_map.add_argument(
        "--strict", action="store_true", help="Fail on any mapping warning"
    )
    p_map.add_argument(
        "--min-confidence",
        type=float,
        default=0.0,
        dest="min_confidence",
        help="Drop matches below this confidence (0.0-1.0)",
    )
    p_map.add_argument(
        "--no-normalize", action="store_true", help="Skip value normalization"
    )
    p_map.add_argument(
        "--embedded-phones",
        action="store_true",
        help="Also extract phone numbers embedded in free-text values",
    )
    p_map.add_argument(
        "--on-error",
        choices=["fail", "skip", "quarantine"],
        default="fail",
        help=(
            "How to handle row-level failures such as malformed JSONL rows or "
            "strict normalization errors (default: fail)"
        ),
    )
    p_map.add_argument(
        "--quarantine-output",
        help=(
            "JSONL file for failed raw rows when --on-error quarantine is used "
            "(default: <output-or-input>.quarantine.jsonl)"
        ),
    )
    p_map.add_argument(
        "--max-materialized-rows",
        type=_non_negative_int,
        default=DEFAULT_MAX_MATERIALIZED_ROWS,
        help=(
            "Maximum rows to materialize for JSON/CSV output; use 0 to disable "
            f"(default: {DEFAULT_MAX_MATERIALIZED_ROWS})"
        ),
    )
    p_map.add_argument(
        "--max-json-input-bytes",
        type=_non_negative_int,
        default=DEFAULT_MAX_JSON_INPUT_BYTES,
        help=(
            "Maximum bytes to read with non-streaming JSON input; use 0 to "
            f"disable (default: {DEFAULT_MAX_JSON_INPUT_BYTES})"
        ),
    )
    p_map.set_defaults(func=_cmd_map)

    p_ex = sub.add_parser("explain", help="Show how a single header resolves")
    p_ex.add_argument("header", help="The column header to resolve")
    p_ex.add_argument(
        "--value", help="An example cell value (enables shape heuristics)"
    )
    p_ex.add_argument("--region", default="US", help="Default phone region")
    p_ex.add_argument(
        "--languages", help="Comma-separated i18n language codes (cached)"
    )
    p_ex.set_defaults(func=_cmd_explain)

    p_fields = sub.add_parser("fields", help="List all canonical fields")
    p_fields.set_defaults(func=_cmd_fields)

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.  Returns a process exit code."""
    # Force UTF-8 on stdout/stderr so non-ASCII names don't crash on consoles
    # using a legacy code page (e.g. Windows cp1252).
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8")

    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return cast_int(args.func(args))
    except (RolodexterError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def cast_int(value: object) -> int:
    """Coerce a command handler's return to an int exit code."""
    return int(value) if isinstance(value, int) else 0


if __name__ == "__main__":
    sys.exit(main())
