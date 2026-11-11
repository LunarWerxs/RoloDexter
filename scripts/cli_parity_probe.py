from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable, "-m", "rolodexter"]
PY_I18N = [sys.executable, "-m", "rolodexter.i18n"]
JS = ["node", str(ROOT / "packages/js/dist/src/cli.js")]
JS_I18N = ["node", str(ROOT / "packages/js/dist/src/i18n.js")]


def run(
    cmd: list[str], *, cwd: Path, env: dict[str, str], raw: bool = False
) -> dict[str, Any]:
    # encoding is explicit for the same reason as in parity_probe.py: the
    # platform default is cp1252 on Windows, which mangles any non-ASCII output
    # the CLI prints.
    if raw:
        # Exact bytes, no newline translation: CSV line ends are part of the
        # contract (M6, the old \r\r\n on a redirected Windows stdout).
        proc_bytes = subprocess.run(
            cmd, cwd=cwd, env=env, capture_output=True, check=False
        )
        return {
            "code": proc_bytes.returncode,
            "stdout": proc_bytes.stdout.decode("utf-8", "backslashreplace"),
            "stderr": proc_bytes.stderr.decode("utf-8", "backslashreplace"),
        }
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    return {"code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


_CHOOSE_RE = re.compile(r"choose from ([^)]*)")
_PROG_RE = re.compile(r"(?<![\w.-])i18n\.py(?=[ :])")
_SEP = r"(?:/|\\\\)"
_PACKAGE_I18N_RE = re.compile(
    rf"<ROOT>{_SEP}(?:packages{_SEP}js{_SEP}dist{_SEP}(?:src|cjs)|src{_SEP}rolodexter){_SEP}i18n"
)
_SHORT_METAVAR_RE = re.compile(r"(?<![\w-])(-\w) ([A-Z][A-Z_]*), (--[\w-]+) \2\b")


def _normalize_argparse(text: str) -> str:
    """Neutralize argparse output that varies across Python versions.

    argparse's help/error text is not stable across CPython releases: the
    ``-m`` program name, usage-line wrapping/indentation, and whether the
    ``choose from`` choices are quoted all differ between versions (and even
    patch releases). The JS CLI reimplements one particular rendering, so we
    compare argparse boilerplate on semantic content rather than exact bytes.
    Non-argparse output (mapped JSON/CSV/JSONL) is returned unchanged.
    """
    if "usage:" not in text:
        return text
    # Collapse version-dependent usage-line wrapping and indentation.
    text = re.sub(r"[ \t]*\n[ \t]*", " ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    # Normalize "choose from 'a', 'b'" (older) vs "choose from a, b" (newer).
    text = _CHOOSE_RE.sub(lambda m: "choose from " + m.group(1).replace("'", ""), text)
    # Python 3.14 names a ``-m`` program "python -m pkg.mod"; older releases use
    # the file name ("i18n.py"). The JS CLI renders the 3.14 form.
    text = _PROG_RE.sub("python -m rolodexter.i18n", text)
    # Python 3.13+ writes "-o, --output OUTPUT"; older releases repeat the
    # metavar ("-o OUTPUT, --output OUTPUT"). The JS CLI renders the new form.
    text = _SHORT_METAVAR_RE.sub(r"\1, \3 \2", text)
    return text.strip()


def scrub(result: dict[str, Any], tmp: Path) -> dict[str, Any]:
    text = json.dumps(result)
    text = text.replace(str(tmp), "<TMP>")
    text = text.replace(str(tmp).replace("\\", "\\\\"), "<TMP>")
    text = text.replace(str(ROOT), "<ROOT>")
    text = text.replace(str(ROOT).replace("\\", "\\\\"), "<ROOT>")
    # Each package lists its own bundled language folder; the location differs
    # by design (the JS package no longer borrows Python's through PYTHONPATH).
    text = _PACKAGE_I18N_RE.sub("<PACKAGE_I18N>", text)
    out: dict[str, Any] = json.loads(text)
    for key in ("stdout", "stderr"):
        value = out.get(key)
        if isinstance(value, str):
            out[key] = _normalize_argparse(value)
    return out


def main() -> int:
    tmp_root = ROOT / ".tmp"
    tmp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="rolodexter-cli-parity-",
        dir=tmp_root,
    ) as raw_tmp:
        tmp = Path(raw_tmp)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        env["ROLODEXTER_CACHE_DIR"] = str(tmp / "cache")

        contacts_json = tmp / "contacts.json"
        contacts_json.write_text(
            '[{"fname":"Ada","mobile":"(202) 555-0143"}]', encoding="utf-8"
        )
        empty_json = tmp / "empty.json"
        empty_json.write_text("[]", encoding="utf-8")
        bad_json = tmp / "bad.json"
        bad_json.write_text("{", encoding="utf-8")
        contacts_csv = tmp / "contacts.csv"
        contacts_csv.write_text("fname,mobile\nAda,(202) 555-0143\n", encoding="utf-8")
        extra_csv = tmp / "extra.csv"
        extra_csv.write_text("Name,Email\nAda,a@example.com,EXTRA\n", encoding="utf-8")
        bad_quote_csv = tmp / "badquote.csv"
        bad_quote_csv.write_text('Name,Email\n"Ada,a@example.com\n', encoding="utf-8")
        bad_jsonl = tmp / "bad.jsonl"
        bad_jsonl.write_text(
            '{"fname":"Ada"}\nnot json\n{"email":"A@EXAMPLE.COM"}\n', encoding="utf-8"
        )
        limit_jsonl = tmp / "limit.jsonl"
        limit_jsonl.write_text(
            '{"Name":"Ada"}\n{"Name":"Grace"}\nnot-json\n', encoding="utf-8"
        )
        colon_bad_json = tmp / "colon_bad.json"
        colon_bad_json.write_text('{"Name":}', encoding="utf-8")
        nan_json = tmp / "nan.json"
        nan_json.write_text(
            '[{"score":NaN},{"score":Infinity},{"score":-Infinity}]', encoding="utf-8"
        )

        cases: list[tuple[str, list[str], list[str]]] = [
            ("root_help", [*PY, "--help"], [*JS, "--help"]),
            ("root_no_args", PY, JS),
            ("root_unknown", [*PY, "wat"], [*JS, "wat"]),
            ("fields", [*PY, "fields"], [*JS, "fields"]),
            ("fields_help", [*PY, "fields", "--help"], [*JS, "fields", "--help"]),
            (
                "explain_basic",
                [*PY, "explain", "Job Titel", "--value", "CEO"],
                [*JS, "explain", "Job Titel", "--value", "CEO"],
            ),
            (
                "explain_apostrophe",
                [*PY, "explain", "O'Reilly", "--value", "CEO"],
                [*JS, "explain", "O'Reilly", "--value", "CEO"],
            ),
            ("explain_no_value", [*PY, "explain", "fname"], [*JS, "explain", "fname"]),
            (
                "map_json_stdout",
                [
                    *PY,
                    "map",
                    str(contacts_json),
                    "--in-format",
                    "json",
                    "--format",
                    "json",
                ],
                [
                    *JS,
                    "map",
                    str(contacts_json),
                    "--in-format",
                    "json",
                    "--format",
                    "json",
                ],
            ),
            (
                "map_json_nan",
                [*PY, "map", str(nan_json), "--in-format", "json", "--format", "json"],
                [*JS, "map", str(nan_json), "--in-format", "json", "--format", "json"],
            ),
            (
                "map_csv_jsonl",
                [*PY, "map", str(contacts_csv), "--format", "jsonl"],
                [*JS, "map", str(contacts_csv), "--format", "jsonl"],
            ),
            (
                "map_bad_json",
                [*PY, "map", str(bad_json), "--in-format", "json"],
                [*JS, "map", str(bad_json), "--in-format", "json"],
            ),
            (
                "map_bad_json_colon",
                [*PY, "map", str(colon_bad_json), "--format", "json"],
                [*JS, "map", str(colon_bad_json), "--format", "json"],
            ),
            (
                "map_missing_file",
                [*PY, "map", str(tmp / "missing.json")],
                [*JS, "map", str(tmp / "missing.json")],
            ),
            (
                "map_bad_on_error",
                [*PY, "map", str(empty_json), "--on-error", "bogus"],
                [*JS, "map", str(empty_json), "--on-error", "bogus"],
            ),
            (
                "map_missing_region_value",
                [
                    *PY,
                    "map",
                    str(contacts_csv),
                    "--region",
                    "--strict",
                    "--format",
                    "json",
                ],
                [
                    *JS,
                    "map",
                    str(contacts_csv),
                    "--region",
                    "--strict",
                    "--format",
                    "json",
                ],
            ),
            (
                "map_missing_format_before_help",
                [*PY, "map", str(contacts_csv), "--format", "--help"],
                [*JS, "map", str(contacts_csv), "--format", "--help"],
            ),
            (
                "map_skip_jsonl",
                [
                    *PY,
                    "map",
                    str(bad_jsonl),
                    "--in-format",
                    "jsonl",
                    "--format",
                    "jsonl",
                    "--on-error",
                    "skip",
                ],
                [
                    *JS,
                    "map",
                    str(bad_jsonl),
                    "--in-format",
                    "jsonl",
                    "--format",
                    "jsonl",
                    "--on-error",
                    "skip",
                ],
            ),
            (
                "map_quarantine_default",
                [
                    *PY,
                    "map",
                    str(bad_jsonl),
                    "--in-format",
                    "jsonl",
                    "--format",
                    "jsonl",
                    "--on-error",
                    "quarantine",
                ],
                [
                    *JS,
                    "map",
                    str(bad_jsonl),
                    "--in-format",
                    "jsonl",
                    "--format",
                    "jsonl",
                    "--on-error",
                    "quarantine",
                ],
            ),
            (
                "map_csv_extra_column",
                [*PY, "map", str(extra_csv), "--format", "json"],
                [*JS, "map", str(extra_csv), "--format", "json"],
            ),
            (
                "map_csv_unclosed_quote",
                [*PY, "map", str(bad_quote_csv), "--format", "json"],
                [*JS, "map", str(bad_quote_csv), "--format", "json"],
            ),
            (
                "map_materialization_before_later_bad_row",
                [
                    *PY,
                    "map",
                    str(limit_jsonl),
                    "--format",
                    "json",
                    "--max-materialized-rows",
                    "1",
                ],
                [
                    *JS,
                    "map",
                    str(limit_jsonl),
                    "--format",
                    "json",
                    "--max-materialized-rows",
                    "1",
                ],
            ),
            (
                "map_negative_dot_confidence",
                [
                    *PY,
                    "map",
                    str(empty_json),
                    "--format",
                    "json",
                    "--min-confidence",
                    "-.5",
                ],
                [
                    *JS,
                    "map",
                    str(empty_json),
                    "--format",
                    "json",
                    "--min-confidence",
                    "-.5",
                ],
            ),
            ("i18n_help", [*PY_I18N, "--help"], [*JS_I18N, "--help"]),
            ("i18n_list", [*PY_I18N, "--list"], [*JS_I18N, "--list"]),
            (
                "i18n_bad_language",
                [*PY_I18N, "--languages", "zz", "--dry-run"],
                [*JS_I18N, "--languages", "zz", "--dry-run"],
            ),
            (
                "i18n_missing_languages_value",
                [*PY_I18N, "--languages", "--dry-run"],
                [*JS_I18N, "--languages", "--dry-run"],
            ),
            (
                "i18n_missing_languages_before_help",
                [*PY_I18N, "--languages", "--help"],
                [*JS_I18N, "--languages", "--help"],
            ),
            (
                "i18n_trailing_empty_language",
                [*PY_I18N, "--dry-run", "--languages", "es,"],
                [*JS_I18N, "--dry-run", "--languages", "es,"],
            ),
            (
                "i18n_bad_workers",
                [*PY_I18N, "--workers", "-1", "--dry-run", "--languages", "es"],
                [*JS_I18N, "--workers", "-1", "--dry-run", "--languages", "es"],
            ),
            (
                "i18n_negative_dot_timeout",
                [*PY_I18N, "--timeout", "-.5", "--dry-run", "--languages", "es"],
                [*JS_I18N, "--timeout", "-.5", "--dry-run", "--languages", "es"],
            ),
        ]

        # Audit 2026-11 (M3): profile, dedupe, keep-unmapped, schema files,
        # embedded phones, CSV cell types, blank lines, BOM, non-ASCII,
        # delimiters, encodings and --csv-safe.
        dup_csv = tmp / "dup.csv"
        dup_csv.write_text(
            "Name,Email,Phone\nAda,ada@example.com,n/a\nGrace,grace@example.com,n/a\n"
            "Ada L,ada@example.com,\n",
            encoding="utf-8",
        )
        messy_csv = tmp / "messy.csv"
        messy_csv.write_text("fname,MMERGE9,Internal ID\nAda,x,42\n", encoding="utf-8")
        notes_csv = tmp / "notes.csv"
        notes_csv.write_text(
            "Name,Notes\nAda,call me on (202) 555-0143 after 5\n", encoding="utf-8"
        )
        cells_json = tmp / "cells.json"
        cells_json.write_text(
            json.dumps(
                [
                    {
                        "Email": "a@example.com",
                        "email_opt_out": "yes",
                        "Tags": ["vip", "lead"],
                        "Score": 5,
                        "Rating": 2.5,
                    },
                    {
                        "Email": "b@example.com",
                        "email_opt_out": "no",
                        "Tags": "x",
                        "Score": 0,
                        "Rating": -1.25,
                    },
                ]
            ),
            encoding="utf-8",
        )
        blank_csv = tmp / "blank.csv"
        blank_csv.write_bytes(b"Name,Email\r\n\r\nAda,a@example.com\r\n\r\n,\r\n")
        bom_csv = tmp / "bom.csv"
        bom_csv.write_bytes(b"\xef\xbb\xbfName,Email\nAda,a@example.com\n")
        bom_json = tmp / "bom.json"
        bom_json.write_bytes(b'\xef\xbb\xbf[{"Email": "a@example.com"}]')
        unicode_csv = tmp / "unicode.csv"
        unicode_csv.write_text(
            "Prénom,Nom,Société\nZoë,Ångström,Café Ünïcode 東京\n", encoding="utf-8"
        )
        semi_csv = tmp / "semi.csv"
        semi_csv.write_text(
            'Name;Email;"Note, with comma"\nAda;a@example.com;x\n', encoding="utf-8"
        )
        tab_tsv = tmp / "tab.tsv"
        tab_tsv.write_text(
            "Name\tEmail\tA,B,C\nAda\ta@example.com\tq\n", encoding="utf-8"
        )
        cp1252_csv = tmp / "cp1252.csv"
        cp1252_csv.write_bytes(
            "First Name,Email\nJosé,jose@example.com\n".encode("cp1252")
        )
        formula_json = tmp / "formula.json"
        formula_json.write_text(
            json.dumps(
                [
                    {
                        "Company": "=HYPERLINK(1)",
                        "Notes": "@cmd",
                        "Title": "-x",
                        "Phone": "+1 202 555 0143",
                    }
                ]
            ),
            encoding="utf-8",
        )
        extra_cells_csv = tmp / "extra_cells.csv"
        extra_cells_csv.write_text(
            "Name,Email\nAda,a@example.com,X,Y\n", encoding="utf-8"
        )

        cases += [
            (
                "profile_csv",
                [*PY, "profile", str(contacts_csv)],
                [*JS, "profile", str(contacts_csv)],
            ),
            (
                "profile_json_flag",
                [*PY, "profile", str(contacts_json), "--json"],
                [*JS, "profile", str(contacts_json), "--json"],
            ),
            (
                "profile_max_json_bytes",
                [*PY, "profile", str(contacts_json), "--max-json-input-bytes", "5"],
                [*JS, "profile", str(contacts_json), "--max-json-input-bytes", "5"],
            ),
            (
                "profile_semicolon",
                [*PY, "profile", str(semi_csv), "--json"],
                [*JS, "profile", str(semi_csv), "--json"],
            ),
            (
                "profile_max_rows",
                [*PY, "profile", str(dup_csv), "--max-rows", "1", "--json"],
                [*JS, "profile", str(dup_csv), "--max-rows", "1", "--json"],
            ),
            (
                "map_dedupe",
                [*PY, "map", str(dup_csv), "--dedupe", "--format", "json"],
                [*JS, "map", str(dup_csv), "--dedupe", "--format", "json"],
            ),
            (
                "map_duplicates_output_needs_dedupe",
                [*PY, "map", str(dup_csv), "--duplicates-output", str(tmp / "d.jsonl")],
                [*JS, "map", str(dup_csv), "--duplicates-output", str(tmp / "d.jsonl")],
            ),
            (
                "map_keep_unmapped",
                [*PY, "map", str(messy_csv), "--keep-unmapped", "--format", "json"],
                [*JS, "map", str(messy_csv), "--keep-unmapped", "--format", "json"],
            ),
            (
                "map_embedded_phones",
                [*PY, "map", str(notes_csv), "--embedded-phones", "--format", "json"],
                [*JS, "map", str(notes_csv), "--embedded-phones", "--format", "json"],
            ),
            (
                "map_blank_lines",
                [*PY, "map", str(blank_csv), "--format", "json"],
                [*JS, "map", str(blank_csv), "--format", "json"],
            ),
            (
                "map_bom_csv",
                [*PY, "map", str(bom_csv), "--format", "json"],
                [*JS, "map", str(bom_csv), "--format", "json"],
            ),
            (
                "map_bom_json",
                [*PY, "map", str(bom_json), "--format", "json"],
                [*JS, "map", str(bom_json), "--format", "json"],
            ),
            (
                "map_non_ascii",
                [*PY, "map", str(unicode_csv), "--keep-unmapped", "--format", "json"],
                [*JS, "map", str(unicode_csv), "--keep-unmapped", "--format", "json"],
            ),
            (
                "map_semicolon",
                [*PY, "map", str(semi_csv), "--format", "json"],
                [*JS, "map", str(semi_csv), "--format", "json"],
            ),
            (
                "map_tab_tsv",
                [*PY, "map", str(tab_tsv), "--format", "json"],
                [*JS, "map", str(tab_tsv), "--format", "json"],
            ),
            (
                "map_delimiter_flag",
                [*PY, "map", str(semi_csv), "--delimiter", ",", "--format", "json"],
                [*JS, "map", str(semi_csv), "--delimiter", ",", "--format", "json"],
            ),
            (
                "map_bad_delimiter",
                [*PY, "map", str(semi_csv), "--delimiter", "ab"],
                [*JS, "map", str(semi_csv), "--delimiter", "ab"],
            ),
            (
                "map_encoding_cp1252",
                [
                    *PY,
                    "map",
                    str(cp1252_csv),
                    "--encoding",
                    "cp1252",
                    "--format",
                    "json",
                ],
                [
                    *JS,
                    "map",
                    str(cp1252_csv),
                    "--encoding",
                    "cp1252",
                    "--format",
                    "json",
                ],
            ),
            (
                "map_encoding_wrong",
                [*PY, "map", str(cp1252_csv), "--format", "json"],
                [*JS, "map", str(cp1252_csv), "--format", "json"],
            ),
            (
                "map_encoding_unknown",
                [*PY, "map", str(cp1252_csv), "--encoding", "ebcdic"],
                [*JS, "map", str(cp1252_csv), "--encoding", "ebcdic"],
            ),
            (
                "profile_encoding_wrong",
                [*PY, "profile", str(cp1252_csv)],
                [*JS, "profile", str(cp1252_csv)],
            ),
            (
                "map_extra_cells_summary",
                [*PY, "map", str(extra_cells_csv), "--format", "jsonl"],
                [*JS, "map", str(extra_cells_csv), "--format", "jsonl"],
            ),
            ("map_help", [*PY, "map", "--help"], [*JS, "map", "--help"]),
            ("profile_help", [*PY, "profile", "--help"], [*JS, "profile", "--help"]),
        ]
        # CSV on stdout: compared as exact bytes.
        raw_cases: list[tuple[str, list[str], list[str]]] = [
            (
                "map_csv_cells_stdout",
                [*PY, "map", str(cells_json), "--format", "csv"],
                [*JS, "map", str(cells_json), "--format", "csv"],
            ),
            (
                "map_csv_safe_stdout",
                [*PY, "map", str(formula_json), "--format", "csv", "--csv-safe"],
                [*JS, "map", str(formula_json), "--format", "csv", "--csv-safe"],
            ),
            (
                "map_csv_unsafe_stdout",
                [*PY, "map", str(formula_json), "--format", "csv"],
                [*JS, "map", str(formula_json), "--format", "csv"],
            ),
            (
                "map_csv_unicode_stdout",
                [*PY, "map", str(unicode_csv), "--format", "csv", "--keep-unmapped"],
                [*JS, "map", str(unicode_csv), "--format", "csv", "--keep-unmapped"],
            ),
        ]

        mismatches: list[dict[str, Any]] = []
        for case_id, py_cmd, js_cmd in cases:
            py = scrub(run(py_cmd, cwd=ROOT, env=env), tmp)
            js = scrub(run(js_cmd, cwd=ROOT, env=env), tmp)
            if py != js:
                mismatches.append({"id": case_id, "python": py, "js": js})
        for case_id, py_cmd, js_cmd in raw_cases:
            py = scrub(run(py_cmd, cwd=ROOT, env=env, raw=True), tmp)
            js = scrub(run(js_cmd, cwd=ROOT, env=env, raw=True), tmp)
            if py != js:
                mismatches.append({"id": case_id, "python": py, "js": js})

        def run_with_file_bytes(
            case_id: str,
            py_cmd: list[str],
            js_cmd: list[str],
            paths: list[Path],
        ) -> None:
            for path in paths:
                path.unlink(missing_ok=True)
            py = scrub(run(py_cmd, cwd=ROOT, env=env), tmp)
            py_files = {
                path.name: list(path.read_bytes()) if path.exists() else None
                for path in paths
            }
            for path in paths:
                path.unlink(missing_ok=True)
            js = scrub(run(js_cmd, cwd=ROOT, env=env), tmp)
            js_files = {
                path.name: list(path.read_bytes()) if path.exists() else None
                for path in paths
            }
            if {"result": py, "files": py_files} != {"result": js, "files": js_files}:
                mismatches.append(
                    {
                        "id": case_id,
                        "python": {"result": py, "files": py_files},
                        "js": {"result": js, "files": js_files},
                    }
                )

        clean_json = tmp / "clean.json"
        clean_json.write_text("[]", encoding="utf-8")
        clean_quarantine = tmp / "clean.json.quarantine.jsonl"
        run_with_file_bytes(
            "map_clean_quarantine_side_effect",
            [
                *PY,
                "map",
                str(clean_json),
                "--format",
                "json",
                "--on-error",
                "quarantine",
            ],
            [
                *JS,
                "map",
                str(clean_json),
                "--format",
                "json",
                "--on-error",
                "quarantine",
            ],
            [clean_quarantine],
        )

        out_csv = tmp / "out.csv"
        run_with_file_bytes(
            "map_csv_file_bytes",
            [*PY, "map", str(contacts_csv), "--format", "csv", "-o", str(out_csv)],
            [*JS, "map", str(contacts_csv), "--format", "csv", "-o", str(out_csv)],
            [out_csv],
        )

        dups_out = tmp / "dups.jsonl"
        run_with_file_bytes(
            "map_duplicates_output_file",
            [
                *PY,
                "map",
                str(dup_csv),
                "--dedupe",
                "--duplicates-output",
                str(dups_out),
                "--format",
                "json",
            ],
            [
                *JS,
                "map",
                str(dup_csv),
                "--dedupe",
                "--duplicates-output",
                str(dups_out),
                "--format",
                "json",
            ],
            [dups_out],
        )
        plan = tmp / "plan.json"
        run_with_file_bytes(
            "map_schema_out",
            [
                *PY,
                "map",
                str(limit_jsonl),
                "--format",
                "jsonl",
                "--on-error",
                "skip",
                "--schema-out",
                str(plan),
            ],
            [
                *JS,
                "map",
                str(limit_jsonl),
                "--format",
                "jsonl",
                "--on-error",
                "skip",
                "--schema-out",
                str(plan),
            ],
            [plan],
        )
        # run_with_file_bytes leaves the JS run's plan in place: replay it.
        cases_schema_in = [
            (
                "map_schema_in",
                [
                    *PY,
                    "map",
                    str(contacts_csv),
                    "--schema-in",
                    str(plan),
                    "--format",
                    "json",
                ],
                [
                    *JS,
                    "map",
                    str(contacts_csv),
                    "--schema-in",
                    str(plan),
                    "--format",
                    "json",
                ],
            ),
        ]
        for case_id, py_cmd, js_cmd in cases_schema_in:
            py = scrub(run(py_cmd, cwd=ROOT, env=env), tmp)
            js = scrub(run(js_cmd, cwd=ROOT, env=env), tmp)
            if py != js:
                mismatches.append({"id": case_id, "python": py, "js": js})
        out_csv_cells = tmp / "cells.csv"
        run_with_file_bytes(
            "map_csv_cells_file_bytes",
            [*PY, "map", str(cells_json), "-o", str(out_csv_cells)],
            [*JS, "map", str(cells_json), "-o", str(out_csv_cells)],
            [out_csv_cells],
        )

        print(
            json.dumps(
                {"mismatch_count": len(mismatches), "mismatches": mismatches},
                indent=2,
                sort_keys=True,
            )
        )
        return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
