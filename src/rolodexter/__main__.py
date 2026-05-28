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
import sys
from collections.abc import Iterable, Iterator
from typing import IO, Any

from .core import CanonicalField, ContactMapper, MappingResult, RolodexterError

# ── I/O helpers ────────────────────────────────────────────────────────


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


def _read_rows(path: str, fmt: str) -> Iterator[dict[str, Any]]:
    """Yield raw contact dicts from *path* in the given *fmt*."""
    if fmt == "csv":
        with open(path, newline="", encoding="utf-8-sig") as fh:
            yield from csv.DictReader(fh)
    elif fmt == "jsonl":
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        yield obj
    else:  # json
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            yield data
        elif isinstance(data, list):
            for obj in data:
                if isinstance(obj, dict):
                    yield obj


def _scalarize(value: Any) -> Any:
    """Flatten list/dict values so they fit in a single CSV cell."""
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return value


def _write_csv(results: Iterable[MappingResult], out: IO[str]) -> int:
    rows = [r.normalized for r in results]
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


def _write_json(results: Iterable[MappingResult], out: IO[str]) -> int:
    rows = [r.normalized for r in results]
    json.dump(rows, out, ensure_ascii=False, indent=2)
    out.write("\n")
    return len(rows)


def _parse_languages(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [code.strip() for code in raw.split(",") if code.strip()]


# ── Commands ───────────────────────────────────────────────────────────


def _cmd_map(args: argparse.Namespace) -> int:
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

    rows = _read_rows(args.input, in_fmt)
    results = mapper.map_stream(rows, extract_embedded_phones=args.embedded_phones)

    with contextlib.ExitStack() as stack:
        out: IO[str] = (
            stack.enter_context(open(args.output, "w", newline="", encoding="utf-8"))
            if args.output
            else sys.stdout
        )
        if out_fmt == "csv":
            count = _write_csv(results, out)
        elif out_fmt == "jsonl":
            count = _write_jsonl(results, out)
        else:
            count = _write_json(results, out)

    where = args.output or "stdout"
    print(f"Mapped {count} row(s) -> {where} ({out_fmt})", file=sys.stderr)
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
