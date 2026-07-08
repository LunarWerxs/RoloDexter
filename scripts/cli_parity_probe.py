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


def run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    proc = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True, check=False)
    return {"code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


_CHOOSE_RE = re.compile(r"choose from ([^)]*)")


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
    return text.strip()


def scrub(result: dict[str, Any], tmp: Path) -> dict[str, Any]:
    text = json.dumps(result)
    text = text.replace(str(tmp), "<TMP>")
    text = text.replace(str(tmp).replace("\\", "\\\\"), "<TMP>")
    text = text.replace(str(ROOT), "<ROOT>")
    text = text.replace(str(ROOT).replace("\\", "\\\\"), "<ROOT>")
    out = json.loads(text)
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
        contacts_json.write_text('[{"fname":"Ada","mobile":"(202) 555-0143"}]', encoding="utf-8")
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
        bad_jsonl.write_text('{"fname":"Ada"}\nnot json\n{"email":"A@EXAMPLE.COM"}\n', encoding="utf-8")
        limit_jsonl = tmp / "limit.jsonl"
        limit_jsonl.write_text('{"Name":"Ada"}\n{"Name":"Grace"}\nnot-json\n', encoding="utf-8")
        colon_bad_json = tmp / "colon_bad.json"
        colon_bad_json.write_text('{"Name":}', encoding="utf-8")
        nan_json = tmp / "nan.json"
        nan_json.write_text('[{"score":NaN},{"score":Infinity},{"score":-Infinity}]', encoding="utf-8")

        cases: list[tuple[str, list[str], list[str]]] = [
            ("root_help", PY + ["--help"], JS + ["--help"]),
            ("root_no_args", PY, JS),
            ("root_unknown", PY + ["wat"], JS + ["wat"]),
            ("fields", PY + ["fields"], JS + ["fields"]),
            ("fields_help", PY + ["fields", "--help"], JS + ["fields", "--help"]),
            ("explain_basic", PY + ["explain", "Job Titel", "--value", "CEO"], JS + ["explain", "Job Titel", "--value", "CEO"]),
            ("explain_apostrophe", PY + ["explain", "O'Reilly", "--value", "CEO"], JS + ["explain", "O'Reilly", "--value", "CEO"]),
            ("explain_no_value", PY + ["explain", "fname"], JS + ["explain", "fname"]),
            ("map_json_stdout", PY + ["map", str(contacts_json), "--in-format", "json", "--format", "json"], JS + ["map", str(contacts_json), "--in-format", "json", "--format", "json"]),
            ("map_json_nan", PY + ["map", str(nan_json), "--in-format", "json", "--format", "json"], JS + ["map", str(nan_json), "--in-format", "json", "--format", "json"]),
            ("map_csv_jsonl", PY + ["map", str(contacts_csv), "--format", "jsonl"], JS + ["map", str(contacts_csv), "--format", "jsonl"]),
            ("map_bad_json", PY + ["map", str(bad_json), "--in-format", "json"], JS + ["map", str(bad_json), "--in-format", "json"]),
            ("map_bad_json_colon", PY + ["map", str(colon_bad_json), "--format", "json"], JS + ["map", str(colon_bad_json), "--format", "json"]),
            ("map_missing_file", PY + ["map", str(tmp / "missing.json")], JS + ["map", str(tmp / "missing.json")]),
            ("map_bad_on_error", PY + ["map", str(empty_json), "--on-error", "bogus"], JS + ["map", str(empty_json), "--on-error", "bogus"]),
            ("map_missing_region_value", PY + ["map", str(contacts_csv), "--region", "--strict", "--format", "json"], JS + ["map", str(contacts_csv), "--region", "--strict", "--format", "json"]),
            ("map_missing_format_before_help", PY + ["map", str(contacts_csv), "--format", "--help"], JS + ["map", str(contacts_csv), "--format", "--help"]),
            ("map_skip_jsonl", PY + ["map", str(bad_jsonl), "--in-format", "jsonl", "--format", "jsonl", "--on-error", "skip"], JS + ["map", str(bad_jsonl), "--in-format", "jsonl", "--format", "jsonl", "--on-error", "skip"]),
            ("map_quarantine_default", PY + ["map", str(bad_jsonl), "--in-format", "jsonl", "--format", "jsonl", "--on-error", "quarantine"], JS + ["map", str(bad_jsonl), "--in-format", "jsonl", "--format", "jsonl", "--on-error", "quarantine"]),
            ("map_csv_extra_column", PY + ["map", str(extra_csv), "--format", "json"], JS + ["map", str(extra_csv), "--format", "json"]),
            ("map_csv_unclosed_quote", PY + ["map", str(bad_quote_csv), "--format", "json"], JS + ["map", str(bad_quote_csv), "--format", "json"]),
            ("map_materialization_before_later_bad_row", PY + ["map", str(limit_jsonl), "--format", "json", "--max-materialized-rows", "1"], JS + ["map", str(limit_jsonl), "--format", "json", "--max-materialized-rows", "1"]),
            ("map_negative_dot_confidence", PY + ["map", str(empty_json), "--format", "json", "--min-confidence", "-.5"], JS + ["map", str(empty_json), "--format", "json", "--min-confidence", "-.5"]),
            ("i18n_help", PY_I18N + ["--help"], JS_I18N + ["--help"]),
            ("i18n_list", PY_I18N + ["--list"], JS_I18N + ["--list"]),
            ("i18n_bad_language", PY_I18N + ["--languages", "zz", "--dry-run"], JS_I18N + ["--languages", "zz", "--dry-run"]),
            ("i18n_missing_languages_value", PY_I18N + ["--languages", "--dry-run"], JS_I18N + ["--languages", "--dry-run"]),
            ("i18n_missing_languages_before_help", PY_I18N + ["--languages", "--help"], JS_I18N + ["--languages", "--help"]),
            ("i18n_trailing_empty_language", PY_I18N + ["--dry-run", "--languages", "es,"], JS_I18N + ["--dry-run", "--languages", "es,"]),
            ("i18n_bad_workers", PY_I18N + ["--workers", "-1", "--dry-run", "--languages", "es"], JS_I18N + ["--workers", "-1", "--dry-run", "--languages", "es"]),
            ("i18n_negative_dot_timeout", PY_I18N + ["--timeout", "-.5", "--dry-run", "--languages", "es"], JS_I18N + ["--timeout", "-.5", "--dry-run", "--languages", "es"]),
        ]

        mismatches: list[dict[str, Any]] = []
        for case_id, py_cmd, js_cmd in cases:
            py = scrub(run(py_cmd, cwd=ROOT, env=env), tmp)
            js = scrub(run(js_cmd, cwd=ROOT, env=env), tmp)
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
            py_files = {path.name: list(path.read_bytes()) if path.exists() else None for path in paths}
            for path in paths:
                path.unlink(missing_ok=True)
            js = scrub(run(js_cmd, cwd=ROOT, env=env), tmp)
            js_files = {path.name: list(path.read_bytes()) if path.exists() else None for path in paths}
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
            PY + ["map", str(clean_json), "--format", "json", "--on-error", "quarantine"],
            JS + ["map", str(clean_json), "--format", "json", "--on-error", "quarantine"],
            [clean_quarantine],
        )

        out_csv = tmp / "out.csv"
        run_with_file_bytes(
            "map_csv_file_bytes",
            PY + ["map", str(contacts_csv), "--format", "csv", "-o", str(out_csv)],
            JS + ["map", str(contacts_csv), "--format", "csv", "-o", str(out_csv)],
            [out_csv],
        )

        print(json.dumps({"mismatch_count": len(mismatches), "mismatches": mismatches}, indent=2, sort_keys=True))
        return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
