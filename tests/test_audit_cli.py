"""CLI fixes from the 2026-11 audit (H3, M5, M6, L1-L3, L8, L9).

Each test names its finding id. The JS twin lives in
``packages/js/test/audit_cli.test.ts``; ``scripts/cli_parity_probe.py``
checks that both CLIs print the same bytes for the same cases.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from rolodexter import ContactMapper
from rolodexter.__main__ import main as cli_main

SRC = Path(__file__).resolve().parents[1] / "src"


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()]


# ── H3: --duplicates-output ────────────────────────────────────────────


def test_h3_duplicates_output_records_each_dropped_row(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = tmp_path / "in.csv"
    src.write_text(
        "Name,Email\nAda,ada@example.com\nGrace,grace@example.com\n"
        "Ada L,ada@example.com\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.json"
    dups = tmp_path / "dups.jsonl"

    rc = cli_main(
        ["map", str(src), "-o", str(out), "--dedupe", "--duplicates-output", str(dups)]
    )

    assert rc == 0
    assert len(json.loads(out.read_text("utf-8"))) == 2
    records = _read_jsonl(dups)
    assert len(records) == 1
    record = records[0]
    assert list(record) == ["row", "error", "raw", "key", "first_row"]
    assert record["row"] == 4
    assert record["first_row"] == 2
    assert record["error"] == "duplicate of row 2"
    assert record["key"] == "email:ada@example.com"
    assert record["raw"] == {"Name": "Ada L", "Email": "ada@example.com"}
    err = capsys.readouterr().err
    assert f"dropped 1 duplicate row(s) -> {dups}" in err


def test_h3_duplicates_output_is_not_created_without_duplicates(
    tmp_path: Path,
) -> None:
    src = tmp_path / "in.csv"
    src.write_text("Email\na@example.com\nb@example.com\n", encoding="utf-8")
    dups = tmp_path / "dups.jsonl"

    rc = cli_main(
        [
            "map",
            str(src),
            "-o",
            str(tmp_path / "out.json"),
            "--dedupe",
            "--duplicates-output",
            str(dups),
        ]
    )

    assert rc == 0
    assert not dups.exists()


def test_h3_duplicates_output_requires_dedupe(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = tmp_path / "in.csv"
    src.write_text("Email\na@example.com\n", encoding="utf-8")

    rc = cli_main(["map", str(src), "--duplicates-output", str(tmp_path / "d.jsonl")])

    assert rc == 1
    assert "error: --duplicates-output requires --dedupe" in capsys.readouterr().err


# ── M5: --encoding and --delimiter ─────────────────────────────────────


def test_m5_cp1252_input_decodes_with_encoding_flag(tmp_path: Path) -> None:
    src = tmp_path / "in.csv"
    src.write_bytes("First Name,Email\nJosé,jose@example.com\n".encode("cp1252"))
    out = tmp_path / "out.json"

    rc = cli_main(["map", str(src), "-o", str(out), "--encoding", "Windows-1252"])

    assert rc == 0
    assert json.loads(out.read_text("utf-8"))[0]["first_name"] == "José"


def test_m5_undecodable_input_fails_naming_encoding_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = tmp_path / "in.csv"
    src.write_bytes("First Name\nJosé\n".encode("cp1252"))

    rc = cli_main(["map", str(src), "--format", "json"])

    assert rc == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        f"error: cannot decode {src} as utf-8 text; pass --encoding with the "
        "file's real encoding (e.g. --encoding cp1252)\n"
    )


def test_m5_undefined_cp1252_byte_is_a_decode_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = tmp_path / "in.csv"
    src.write_bytes(b"Name\nA\x81\n")

    rc = cli_main(["map", str(src), "--format", "json", "--encoding", "cp1252"])

    assert rc == 1
    assert "cannot decode" in capsys.readouterr().err


def test_m5_utf16_and_latin1_inputs(tmp_path: Path) -> None:
    for encoding, flag in (("utf-16", "utf-16"), ("latin-1", "ISO-8859-1")):
        src = tmp_path / f"{encoding}.csv"
        src.write_bytes("Name,Email\nZoë,z@example.com\n".encode(encoding))
        out = tmp_path / f"{encoding}.json"
        rc = cli_main(["map", str(src), "-o", str(out), "--encoding", flag])
        assert rc == 0
        assert json.loads(out.read_text("utf-8"))[0]["full_name"] == "Zoë"


def test_m5_unknown_encoding_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        cli_main(["map", str(tmp_path / "x.csv"), "--encoding", "ebcdic"])

    assert exc.value.code == 2
    assert (
        "rolodexter map: error: argument --encoding: unsupported encoding "
        "'ebcdic' (choose from utf-8, utf-8-sig, utf-16, latin-1, iso-8859-1, "
        "cp1252, windows-1252)"
    ) in capsys.readouterr().err


def test_m5_json_input_tolerates_utf8_bom(tmp_path: Path) -> None:
    src = tmp_path / "in.json"
    src.write_bytes(b"\xef\xbb\xbf" + b'[{"Email": "a@example.com"}]')
    out = tmp_path / "out.json"

    rc = cli_main(["map", str(src), "-o", str(out)])

    assert rc == 0
    assert json.loads(out.read_text("utf-8")) == [{"email": "a@example.com"}]


@pytest.mark.parametrize(
    ("name", "text", "extra"),
    [
        ("semi.csv", 'Name;Email;"a,b,c"\nAda;a@example.com;x\n', []),
        # two tabs and two commas tie (sniff says comma); .tsv means tab
        ("tabs.tsv", "Name\tEmail\tA,B,C\nAda\ta@example.com\tq\n", []),
        ("tabs.txt", "Name\tEmail\nAda\ta@example.com\n", ["--in-format", "csv"]),
        # two pipes and two semicolons tie; the flag decides
        ("pipe.csv", "Name;Email;a|b|c\nAda;a@example.com;q\n", ["--delimiter", ";"]),
    ],
)
def test_m5_delimiter_is_sniffed_or_given(
    tmp_path: Path, name: str, text: str, extra: list[str]
) -> None:
    src = tmp_path / name
    src.write_text(text, encoding="utf-8")
    out = tmp_path / "out.json"

    rc = cli_main(["map", str(src), "-o", str(out), *extra])

    assert rc == 0
    row = json.loads(out.read_text("utf-8"))[0]
    assert row["full_name"] == "Ada"
    assert row["email"] == "a@example.com"


def test_m5_delimiter_tie_falls_back_to_comma(tmp_path: Path) -> None:
    src = tmp_path / "tie.csv"
    src.write_text("Name;x,Email\nAda;y,a@example.com\n", encoding="utf-8")
    out = tmp_path / "out.json"

    rc = cli_main(["map", str(src), "-o", str(out), "--keep-unmapped"])

    assert rc == 0
    assert json.loads(out.read_text("utf-8"))[0]["email"] == "a@example.com"


def test_m5_bad_delimiter_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        cli_main(["profile", str(tmp_path / "x.csv"), "--delimiter", "ab"])

    assert exc.value.code == 2
    assert (
        "argument --delimiter: expected one character or 'tab', got 'ab'"
        in capsys.readouterr().err
    )


# ── M6: CSV on stdout keeps \r\n line ends ─────────────────────────────


def test_m6_csv_to_stdout_has_single_crlf_line_ends(tmp_path: Path) -> None:
    src = tmp_path / "in.json"
    src.write_text('[{"Email": "a@example.com"}, {"Email": "b@example.com"}]')
    env = {**os.environ, "PYTHONPATH": str(SRC)}

    proc = subprocess.run(
        [sys.executable, "-m", "rolodexter", "map", str(src), "--format", "csv"],
        capture_output=True,
        env=env,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == b"email\r\na@example.com\r\nb@example.com\r\n"


# ── L1: profile honours --max-json-input-bytes ─────────────────────────


def test_l1_profile_honours_max_json_input_bytes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = tmp_path / "in.json"
    src.write_text('[{"Email": "a@example.com"}]', encoding="utf-8")

    rc = cli_main(["profile", str(src), "--max-json-input-bytes", "5"])

    assert rc == 1
    assert "above the 5 byte materialization limit" in capsys.readouterr().err


# ── L2 / L3: blank lines and surplus cells ─────────────────────────────


def test_l2_blank_csv_lines_are_skipped(tmp_path: Path) -> None:
    src = tmp_path / "in.csv"
    src.write_text("Name,Email\n\nAda,a@example.com\n\r\n", encoding="utf-8")
    out = tmp_path / "out.json"

    rc = cli_main(["map", str(src), "-o", str(out)])

    assert rc == 0
    assert json.loads(out.read_text("utf-8")) == [
        {"full_name": "Ada", "email": "a@example.com"}
    ]


def test_l3_surplus_cells_are_counted_in_the_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = tmp_path / "in.csv"
    src.write_text(
        "Name,Email\nAda,a@example.com,X,Y\nGrace,g@example.com,Z\n",
        encoding="utf-8",
    )

    rc = cli_main(["map", str(src), "-o", str(tmp_path / "out.json")])

    assert rc == 0
    assert (
        f"warning: 3 extra cell(s) in 2 row(s) of {src} had no header column "
        "and were dropped"
    ) in capsys.readouterr().err


# ── L8: --csv-safe ─────────────────────────────────────────────────────


def test_l8_csv_safe_quotes_formula_cells(tmp_path: Path) -> None:
    src = tmp_path / "in.json"
    src.write_text(
        json.dumps([{"Company": "=HYPERLINK(1)", "Notes": "@cmd", "Title": "ok"}]),
        encoding="utf-8",
    )
    out = tmp_path / "out.csv"

    rc = cli_main(["map", str(src), "-o", str(out), "--csv-safe", "--keep-unmapped"])

    assert rc == 0
    assert out.read_bytes() == (
        b"company,notes,job_title\r\n'=HYPERLINK(1),'@cmd,ok\r\n"
    )


def test_l8_csv_without_flag_is_unchanged(tmp_path: Path) -> None:
    src = tmp_path / "in.json"
    src.write_text(json.dumps([{"Company": "=1+1"}]), encoding="utf-8")
    out = tmp_path / "out.csv"

    rc = cli_main(["map", str(src), "-o", str(out)])

    assert rc == 0
    assert out.read_bytes() == b"company\r\n=1+1\r\n"


# ── L9: unexpected errors ──────────────────────────────────────────────


def test_l9_unexpected_error_prints_one_line(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    src = tmp_path / "in.csv"
    src.write_text("Email\na@example.com\n", encoding="utf-8")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise KeyError("boom")

    monkeypatch.setattr(ContactMapper, "map_payload", boom)

    rc = cli_main(["map", str(src), "--on-error", "skip", "--format", "json"])

    assert rc == 1
    err = capsys.readouterr().err
    assert err == "error: internal error: KeyError: 'boom'\n"
