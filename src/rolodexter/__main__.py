"""Command-line interface for rolodexter.

Map a contact export to the canonical schema, explain how a header resolves,
or list the canonical fields — without writing any Python.

Examples
--------
::

    rolodexter profile contacts.csv            # what will I lose?
    rolodexter map contacts.csv -o clean.csv
    rolodexter map export.json --format jsonl -o out.jsonl --region GB
    rolodexter map messy.csv --min-confidence 0.8 --strict
    rolodexter map messy.csv --keep-unmapped --dedupe -o clean.csv
    rolodexter map messy.csv --override "MMERGE3=full_address" -o clean.csv
    rolodexter map jan.csv --schema-out plan.json -o jan-clean.csv
    rolodexter map feb.csv --schema-in plan.json  -o feb-clean.csv
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
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

from . import __version__
from ._ping import maybe_ping
from .core import (
    CanonicalField,
    ContactMapper,
    MappingResult,
    MappingSchema,
    RolodexterError,
)

DEFAULT_MAX_MATERIALIZED_ROWS = 100_000
DEFAULT_MAX_JSON_INPUT_BYTES = 50 * 1024 * 1024
# Matches below this are reported for review.  Exact (1.0) and normalized
# (0.95) matches are header-derived and reliable; fuzzy (0.85/0.70) and
# value-shape heuristics (0.60) are guesses worth a human glance.
REVIEW_CONFIDENCE = 0.95
MAX_SUMMARY_COLUMNS = 20
# Exit code when rows failed but the run was allowed to continue.  Distinct
# from 1 (the run itself failed) so a caller can tell "nothing was produced"
# from "output written, but some rows did not make it".
EXIT_PARTIAL = 2

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
    duplicates: int = 0
    dropped_headers: dict[str, int] = field(default_factory=dict)
    low_confidence: dict[str, int] = field(default_factory=dict)
    # Insertion-ordered set of every header seen, so --schema-out does not
    # have to re-read the input file (which would re-emit its warnings).
    headers_seen: dict[str, None] = field(default_factory=dict)

    def note_result(self, result: MappingResult) -> None:
        """Record which columns were dropped or matched only weakly."""
        for match in result.field_matches:
            self.headers_seen.setdefault(match.original, None)
            if not match.is_matched:
                self.dropped_headers[match.original] = (
                    self.dropped_headers.get(match.original, 0) + 1
                )
            elif match.confidence < REVIEW_CONFIDENCE:
                key = f"{match.original} -> {match.canonical}"
                self.low_confidence[key] = self.low_confidence.get(key, 0) + 1


def _summarize_columns(label: str, counts: dict[str, int], hint: str) -> None:
    """Print a one-line-per-column stderr summary, capped so it stays readable."""
    if not counts:
        return
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    shown = ordered[:MAX_SUMMARY_COLUMNS]
    print(f"warning: {label} ({len(ordered)} column(s)); {hint}", file=sys.stderr)
    for name, count in shown:
        print(f"  {name}  [{count} row(s)]", file=sys.stderr)
    if len(ordered) > len(shown):
        print(f"  ... and {len(ordered) - len(shown)} more", file=sys.stderr)


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


def _dedupe_headers(raw_headers: list[str]) -> tuple[list[str], int]:
    """Return unique header names, suffixing repeats, plus how many were renamed.

    ``csv.DictReader`` keeps only the *last* value for a repeated column name,
    so an export with two ``Email`` columns silently lost the first one before
    the mapper ever saw it.  Renaming the repeats to ``Email__2`` keeps both
    values and lets the mapper's own collision handling merge them into a list,
    which is the documented behavior for two headers that mean the same field.
    """
    seen: dict[str, int] = {}
    out: list[str] = []
    renamed = 0
    for index, header in enumerate(raw_headers):
        name = (header or "").strip() or f"column_{index + 1}"
        count = seen.get(name, 0) + 1
        seen[name] = count
        if count > 1:
            name = f"{name}__{count}"
            renamed += 1
        out.append(name)
    return out, renamed


def _looks_like_data_not_headers(headers: list[str], mapper: ContactMapper) -> bool:
    """True if the first CSV row looks like a contact rather than column names.

    Exporting without a header row is a routine mistake whose failure mode
    otherwise looks like success: ``csv.DictReader`` consumes row 1 as the
    schema, so a value becomes a column name and that entire record is lost.
    Row 1 is treated as data when at least one cell parses as an email, a phone
    number or a URL — things that are values, never column names.
    """
    if not headers:
        return False
    for header in headers:
        cell = (header or "").strip()
        if not cell:
            continue
        match = mapper.identify("__header_probe__", value=cell)
        if match.strategy == "heuristic" and match.canonical in {
            "email",
            "phone",
            "website",
        }:
            return True
    return False


def _read_csv_rows(
    path: str, *, mapper: ContactMapper | None = None
) -> Iterator[_InputRow | _RowFailure]:
    """Yield rows from a CSV, preserving duplicate columns and flagging no-header files."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        try:
            raw_headers = next(reader)
        except StopIteration:
            return
        headers, renamed = _dedupe_headers(raw_headers)
        if renamed:
            print(
                f"warning: {renamed} duplicate column name(s) in {path} were "
                "renamed with a __N suffix so no column is lost",
                file=sys.stderr,
            )
        if mapper is not None and _looks_like_data_not_headers(raw_headers, mapper):
            print(
                f"warning: the first row of {path} looks like DATA, not column "
                "names - it has been consumed as the header row and that record "
                "will not appear in the output. Add a header row, or re-export "
                "with one.",
                file=sys.stderr,
            )
        for row_number, values in enumerate(reader, start=2):
            row: dict[str, Any] = {}
            for index, value in enumerate(values):
                if index < len(headers):
                    row[headers[index]] = value
                # Surplus cells have no header to map; csv.DictReader used to
                # bucket them under a None key. Dropping them is unchanged
                # behavior, but now it is explicit.
            for name in headers[len(values) :]:
                row[name] = ""
            yield _InputRow(reader.line_num or row_number, row)


def _read_row_items(
    path: str,
    fmt: str,
    *,
    max_json_bytes: int | None = DEFAULT_MAX_JSON_INPUT_BYTES,
    mapper: ContactMapper | None = None,
) -> Iterator[_InputRow | _RowFailure]:
    """Yield rows or row-level failures from *path* in the given *fmt*."""
    if fmt == "csv":
        yield from _read_csv_rows(path, mapper=mapper)
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


def _read_rows(
    path: str, fmt: str, *, mapper: ContactMapper | None = None
) -> Iterator[dict[str, Any]]:
    """Yield raw contact dicts from *path* in the given *fmt*."""
    for item in _read_row_items(path, fmt, mapper=mapper):
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


def _row_payload(result: MappingResult, *, keep_unmapped: bool) -> dict[str, Any]:
    """Return the dict written for one mapped row.

    ``MappingResult.unmapped`` holds every column the mapper could not place.
    The CLI used to write only ``normalized``, so those columns - CRM custom
    fields, internal IDs, free-text notes - vanished from the output with no
    warning and no way to keep them.  ``--keep-unmapped`` passes them through
    untouched under their original header.
    """
    if not keep_unmapped or not result.unmapped:
        return result.normalized
    merged = dict(result.normalized)
    for key, value in result.unmapped.items():
        # A canonical field always wins its own name; an unmapped column that
        # happens to collide keeps its data under a suffixed key.
        target = key if key not in merged else f"{key}__unmapped"
        while target in merged:
            target += "_"
        merged[target] = value
    return merged


def _collect_normalized_rows(
    results: Iterable[MappingResult],
    *,
    max_rows: int | None,
    materialized_for: str,
    keep_unmapped: bool = False,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, result in enumerate(results, start=1):
        if max_rows is not None and index > max_rows:
            raise ValueError(
                f"{materialized_for} requires materializing more than "
                f"{max_rows} row(s); use --format jsonl for streaming output "
                "or raise --max-materialized-rows"
            )
        rows.append(_row_payload(result, keep_unmapped=keep_unmapped))
    return rows


def _write_csv(
    results: Iterable[MappingResult],
    out: IO[str],
    *,
    max_rows: int | None,
    keep_unmapped: bool = False,
) -> int:
    rows = _collect_normalized_rows(
        results,
        max_rows=max_rows,
        materialized_for="CSV output",
        keep_unmapped=keep_unmapped,
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


def _write_jsonl(
    results: Iterable[MappingResult], out: IO[str], *, keep_unmapped: bool = False
) -> int:
    count = 0
    for result in results:
        payload = _row_payload(result, keep_unmapped=keep_unmapped)
        out.write(json.dumps(payload, ensure_ascii=False) + "\n")
        count += 1
    return count


def _write_json(
    results: Iterable[MappingResult],
    out: IO[str],
    *,
    max_rows: int | None,
    keep_unmapped: bool = False,
) -> int:
    rows = _collect_normalized_rows(
        results,
        max_rows=max_rows,
        materialized_for="JSON output",
        keep_unmapped=keep_unmapped,
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


class _QuarantineWriter:
    """Opens the quarantine file on the FIRST failure, not before.

    The stream used to be opened up front, so a run with zero failures still
    created - and, via the atomic replace, truncated - whatever was at that
    path.  Since the default path is derived from the input or output name,
    a clean re-run silently destroyed the previous run's rejects.
    """

    def __init__(self, path: str, stack: contextlib.ExitStack) -> None:
        self.path = path
        self._stack = stack
        self._out: IO[str] | None = None
        self.used = False

    def write(self, failure: _RowFailure) -> None:
        if self._out is None:
            self._out = self._stack.enter_context(_atomic_output(self.path))
            self.used = True
        _write_quarantine_record(failure, self._out)


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
    quarantine_out: _QuarantineWriter | None,
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
    quarantine_out.write(failure)
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
    quarantine_out: _QuarantineWriter | None = None,
    dedupe: bool = False,
) -> Iterator[MappingResult]:
    seen_keys: set[str] = set()
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
            result = mapper.map_payload(
                item.data,
                extract_embedded_phones=extract_embedded_phones,
            )
            stats.note_result(result)
            if dedupe:
                keys = result.get_identity_keys()
                if keys and any(key in seen_keys for key in keys):
                    stats.duplicates += 1
                    continue
                seen_keys.update(keys)
            yield result
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


def _parse_overrides(raw: list[str] | None) -> dict[str, str] | None:
    """Parse repeated ``--override HEADER=canonical_field`` flags."""
    if not raw:
        return None
    overrides: dict[str, str] = {}
    valid = {f.value for f in CanonicalField}
    for entry in raw:
        header, sep, canonical = entry.partition("=")
        header, canonical = header.strip(), canonical.strip()
        if not sep or not header or not canonical:
            raise ValueError(
                f"--override expects HEADER=canonical_field, got {entry!r}"
            )
        if canonical not in valid:
            raise ValueError(
                f"--override {entry!r}: {canonical!r} is not a canonical field "
                "(run 'rolodexter fields' to list them)"
            )
        overrides[header] = canonical
    return overrides


def _build_mapper(args: argparse.Namespace) -> ContactMapper:
    """Construct the mapper shared by the map and profile commands."""
    return ContactMapper(
        default_region=args.region,
        languages=_parse_languages(args.languages),
        normalize=not getattr(args, "no_normalize", False),
        strict=getattr(args, "strict", False),
        confidence_threshold=getattr(args, "min_confidence", 0.0),
        overrides=_parse_overrides(getattr(args, "override", None)),
    )


def _load_schema(mapper: ContactMapper, path: str) -> MappingSchema:
    """Replay a saved mapping plan so this run routes columns identically."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return MappingSchema.from_dict(data, mapper)


def _write_schema(mapper: ContactMapper, path: str, headers: Iterable[str]) -> None:
    """Save the resolved header plan so a later run can reproduce it exactly."""
    schema = mapper.compile_schema(list(headers))
    with _atomic_output(path) as fh:
        json.dump(schema.to_dict(), fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def _cmd_map(args: argparse.Namespace) -> int:  # pylint: disable=too-many-branches
    if args.quarantine_output and args.on_error != "quarantine":
        raise ValueError("--quarantine-output requires --on-error quarantine")
    if args.output and _same_path(args.output, args.input):
        # Guarded because the transform is lossy in both directions: original
        # formatting is rewritten, and any column the mapper cannot place is
        # dropped unless --keep-unmapped is set.  Overwriting the source export
        # in place destroys the only copy, with no undo.
        raise ValueError(
            "output must differ from the input path; mapping a file onto itself "
            "would destroy the original export"
        )

    mapper = _build_mapper(args)
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

    if args.schema_in:
        _load_schema(mapper, args.schema_in)

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
        quarantine_out: _QuarantineWriter | None = None
        if quarantine_path is not None:
            quarantine_out = _QuarantineWriter(quarantine_path, stack)

        results = _map_row_items(
            _read_row_items(
                args.input, in_fmt, max_json_bytes=max_json_bytes, mapper=mapper
            ),
            mapper,
            extract_embedded_phones=args.embedded_phones,
            on_error=args.on_error,
            stats=stats,
            quarantine_out=quarantine_out,
            dedupe=args.dedupe,
        )

        if out_fmt == "csv":
            count = _write_csv(
                results,
                out,
                max_rows=max_materialized_rows,
                keep_unmapped=args.keep_unmapped,
            )
        elif out_fmt == "jsonl":
            count = _write_jsonl(results, out, keep_unmapped=args.keep_unmapped)
        else:
            count = _write_json(
                results,
                out,
                max_rows=max_materialized_rows,
                keep_unmapped=args.keep_unmapped,
            )

    if args.schema_out:
        _write_schema(mapper, args.schema_out, stats.headers_seen)

    if not args.keep_unmapped:
        _summarize_columns(
            "dropped unmapped column(s) from the output",
            stats.dropped_headers,
            "pass --keep-unmapped to carry them through",
        )
    _summarize_columns(
        "low-confidence column mapping(s)",
        stats.low_confidence,
        "review these, then pin them with --override HEADER=field or raise "
        "--min-confidence",
    )

    where = args.output or "stdout"
    message = f"Mapped {count} row(s) -> {where} ({out_fmt})"
    if stats.duplicates:
        message += f"; dropped {stats.duplicates} duplicate row(s)"
    if stats.failed:
        if args.on_error == "quarantine":
            message += f"; quarantined {stats.failed} row(s) -> {quarantine_path}"
        else:
            message += f"; skipped {stats.failed} row(s)"
    print(message, file=sys.stderr)
    # A non-zero code so a pipeline can tell that rows did not make it. Without
    # it a nightly import that silently dropped half its rows reported success.
    return EXIT_PARTIAL if stats.failed else 0


def _cmd_profile(args: argparse.Namespace) -> int:
    """Report import readiness without writing any mapped output."""
    mapper = _build_mapper(args)
    in_fmt = _detect_format(args.input, args.in_format)
    max_json_bytes = _optional_limit(args.max_json_input_bytes)
    rows = _read_rows(args.input, in_fmt, mapper=mapper)
    profile = mapper.profile(
        rows,
        max_rows=_optional_limit(args.max_rows),
        extract_embedded_phones=args.embedded_phones,
        normalize=not args.no_normalize,
    )
    del max_json_bytes
    if args.json:
        json.dump(profile.to_dict(), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print(profile.explain())
    return 0


def _cmd_explain(args: argparse.Namespace) -> int:
    mapper = _build_mapper(args)
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
    parser.add_argument(
        "--version",
        action="version",
        version=f"rolodexter {__version__}",
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
    p_map.add_argument(
        "--keep-unmapped",
        action="store_true",
        dest="keep_unmapped",
        help=(
            "Carry columns that could not be mapped through to the output "
            "under their original header (default: drop them)"
        ),
    )
    p_map.add_argument(
        "--dedupe",
        action="store_true",
        help=(
            "Drop later rows that share an identity key (email, phone or "
            "source id) with an earlier row"
        ),
    )
    p_map.add_argument(
        "--override",
        action="append",
        metavar="HEADER=FIELD",
        help=(
            "Force a column to a canonical field, e.g. "
            "--override MMERGE3=full_address (repeatable)"
        ),
    )
    p_map.add_argument(
        "--schema-out",
        dest="schema_out",
        metavar="PATH",
        help="Write the resolved header plan to a JSON file for reuse",
    )
    p_map.add_argument(
        "--schema-in",
        dest="schema_in",
        metavar="PATH",
        help=(
            "Replay a plan saved by --schema-out so columns route "
            "identically to that run"
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
    p_ex.add_argument(
        "--override",
        action="append",
        metavar="HEADER=FIELD",
        help="Force a column to a canonical field (repeatable)",
    )
    p_ex.set_defaults(func=_cmd_explain)

    p_profile = sub.add_parser(
        "profile",
        help="Report how well a file maps, without writing any output",
    )
    p_profile.add_argument("input", help="Input file (.csv, .json, or .jsonl)")
    p_profile.add_argument(
        "--in-format",
        dest="in_format",
        choices=["auto", "csv", "json", "jsonl"],
        default="auto",
        help="Input format (default: infer from the input file extension)",
    )
    p_profile.add_argument(
        "--region", default="US", help="Default phone region (ISO-3166 alpha-2)"
    )
    p_profile.add_argument(
        "--languages", help="Comma-separated i18n language codes (cached)"
    )
    p_profile.add_argument(
        "--override",
        action="append",
        metavar="HEADER=FIELD",
        help="Force a column to a canonical field (repeatable)",
    )
    p_profile.add_argument(
        "--max-rows",
        type=_non_negative_int,
        default=0,
        dest="max_rows",
        help="Profile at most this many rows; 0 means all (default: 0)",
    )
    p_profile.add_argument(
        "--min-confidence",
        type=float,
        default=0.0,
        dest="min_confidence",
        help="Treat matches below this confidence as unmapped (0.0-1.0)",
    )
    p_profile.add_argument(
        "--embedded-phones",
        action="store_true",
        help="Also count phone numbers embedded in free-text values",
    )
    p_profile.add_argument(
        "--no-normalize",
        action="store_true",
        help=(
            "Skip value normalization: much faster on a large export, but "
            "drops the phone/email/date warning counts"
        ),
    )
    p_profile.add_argument(
        "--json", action="store_true", help="Emit the profile as JSON"
    )
    p_profile.add_argument(
        "--max-json-input-bytes",
        type=_non_negative_int,
        default=DEFAULT_MAX_JSON_INPUT_BYTES,
        help="Maximum bytes to read with non-streaming JSON input; 0 disables",
    )
    p_profile.set_defaults(func=_cmd_profile)

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
    # Anonymous, opt-out, throttled to <=1/24h; see _ping.py and SECURITY.md.
    # --version/--help exit inside parse_args above and never reach this line.
    maybe_ping(__version__)
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
