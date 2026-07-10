"""Tests for the 2.8.0 feature set.

Covers observability (warnings / strict / confidence threshold), the
MappingResult conveniences (explain, O(1) get_match), the scalability API
(map_stream / compile_schema), the pandas adapter, the heuristic input cap,
the enum-as-source-of-truth invariant, and the CLI.
"""

from __future__ import annotations

import json
import types
from importlib.resources import files
from pathlib import Path

import pytest

from rolodexter import (
    CanonicalField,
    ContactMapper,
    MappingSchema,
    NormalizationError,
)
from rolodexter.__main__ import main as cli_main
from rolodexter.core import HeuristicMatchStrategy, normalize_value

# ── Observability: warnings + strict ────────────────────────────────────


class TestWarnings:
    def test_phone_normalization_failure_warns(self) -> None:
        result = ContactMapper().map_payload({"Mobile Phone": "not a phone"})
        assert result.normalized.get("phone") == "not a phone"
        assert any("E.164" in w for w in result.warnings)

    def test_clean_payload_has_no_warnings(self) -> None:
        result = ContactMapper().map_payload(
            {"fname": "Jane", "Mobile Phone": "(202) 555-0143"}
        )
        assert result.warnings == ()
        assert result.normalized["phone"] == "+12025550143"

    def test_warnings_serialized_in_to_dict(self) -> None:
        result = ContactMapper().map_payload({"phone": "nope"})
        assert "warnings" in result.to_dict()
        assert result.to_dict()["warnings"] == list(result.warnings)


class TestStrictMode:
    def test_strict_constructor_raises(self) -> None:
        mapper = ContactMapper(strict=True)
        with pytest.raises(NormalizationError):
            mapper.map_payload({"phone": "garbage value here"})

    def test_strict_per_call_override_raises(self) -> None:
        mapper = ContactMapper()  # not strict by default
        with pytest.raises(NormalizationError):
            mapper.map_payload({"phone": "garbage value here"}, strict=True)

    def test_strict_passes_on_clean_payload(self) -> None:
        mapper = ContactMapper(strict=True)
        result = mapper.map_payload({"fname": "Jane", "phone": "(202) 555-0143"})
        assert result.normalized["phone"] == "+12025550143"

    def test_non_strict_collects_instead_of_raising(self) -> None:
        result = ContactMapper().map_payload({"phone": "garbage value here"})
        assert result.warnings  # recorded, not raised


class TestConfidenceThreshold:
    def test_constructor_threshold_rejects_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="confidence_threshold"):
            ContactMapper(confidence_threshold=1.1)

    def test_per_call_threshold_rejects_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="confidence_threshold"):
            ContactMapper().map_payload({"fname": "Jane"}, confidence_threshold=-0.1)

    def test_threshold_drops_heuristic_match(self) -> None:
        result = ContactMapper().map_payload(
            {"Mystery Column": "jane@example.com"}, confidence_threshold=0.8
        )
        assert "email" not in result.normalized
        assert "Mystery Column" in result.unmapped
        assert any("dropped low-confidence" in w for w in result.warnings)

    def test_threshold_keeps_exact_match(self) -> None:
        result = ContactMapper().map_payload(
            {"fname": "Jane"}, confidence_threshold=0.99
        )
        assert result.normalized["first_name"] == "Jane"

    def test_constructor_threshold_drops_fuzzy(self) -> None:
        mapper = ContactMapper(confidence_threshold=0.99)
        result = mapper.map_payload({"Compny": "Acme"})  # fuzzy < 0.99
        assert "company" not in result.normalized
        assert "Compny" in result.unmapped


# ── MappingResult conveniences ──────────────────────────────────────────


class TestMappingResultExtras:
    def test_explain_mentions_headers_and_canonicals(self) -> None:
        result = ContactMapper().map_payload({"fname": "Jane", "zzz_nope": "?"})
        text = result.explain()
        assert "fname" in text
        assert "first_name" in text
        assert "zzz_nope" in text

    def test_get_match_index_is_consistent(self) -> None:
        result = ContactMapper().map_payload({"fname": "Jane", "email": "a@b.com"})
        assert result.get_match("fname").canonical == "first_name"  # builds index
        assert result.get_match("email").canonical == "email"  # reuses index
        assert result.get_match("absent") is None

    def test_counts_consistent(self) -> None:
        result = ContactMapper().map_payload({"fname": "Jane", "zzz_nope": "?"})
        assert result.matched_count == 1
        assert result.unmatched_count == 1
        assert result.match_rate == 0.5


# ── Scalability API ─────────────────────────────────────────────────────


class TestMapStream:
    def test_returns_generator(self) -> None:
        gen = ContactMapper().map_stream([{"fname": "A"}])
        assert isinstance(gen, types.GeneratorType)

    def test_yields_one_result_per_payload(self) -> None:
        rows = [{"fname": "A"}, {"surname": "B"}, {"email": "c@d.com"}]
        results = list(ContactMapper().map_stream(rows))
        assert len(results) == 3
        assert results[0].normalized["first_name"] == "A"
        assert results[1].normalized["last_name"] == "B"

    def test_map_batch_matches_stream(self) -> None:
        mapper = ContactMapper()
        rows = [{"fname": "A"}, {"surname": "B"}]
        batch = mapper.map_batch(rows)
        stream = list(mapper.map_stream(rows))
        assert [r.normalized for r in batch] == [r.normalized for r in stream]

    def test_map_batch_forwards_embedded_phone_extraction(self) -> None:
        mapper = ContactMapper()
        rows = [{"notes": "call +1-650-253-0000"}]
        batch = mapper.map_batch(rows, extract_embedded_phones=True)
        stream = list(mapper.map_stream(rows, extract_embedded_phones=True))
        assert batch[0].normalized["phone"] == stream[0].normalized["phone"]


class TestCompileSchema:
    def test_column_map(self) -> None:
        schema = ContactMapper().compile_schema(
            ["First Name", "Mobile Phone", "Whatever"]
        )
        assert isinstance(schema, MappingSchema)
        cmap = schema.column_map()
        assert cmap["First Name"] == "first_name"
        assert cmap["Mobile Phone"] == "phone"
        assert "Whatever" not in cmap

    def test_unmatched_headers(self) -> None:
        schema = ContactMapper().compile_schema(["fname", "zzz_nonsense"])
        assert "zzz_nonsense" in schema.unmatched_headers()
        assert "fname" not in schema.unmatched_headers()

    def test_apply_maps_and_normalizes(self) -> None:
        schema = ContactMapper().compile_schema(["First Name", "Mobile Phone"])
        result = schema.apply({"First Name": "Jane", "Mobile Phone": "(202) 555-0143"})
        assert result.normalized["first_name"] == "Jane"
        assert result.normalized["phone"] == "+12025550143"

    def test_threshold_drops_low_confidence_schema_match(self) -> None:
        schema = ContactMapper(confidence_threshold=0.99).compile_schema(["Compny"])
        assert schema.column_map() == {}
        assert schema.unmatched_headers() == ["Compny"]

    def test_strict_threshold_raises_for_schema_match(self) -> None:
        with pytest.raises(NormalizationError):
            ContactMapper(strict=True, confidence_threshold=0.99).compile_schema(
                ["Compny"]
            )


# ── pandas adapter ──────────────────────────────────────────────────────


class TestMapDataframe:
    def test_renames_and_normalizes(self) -> None:
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame(
            {
                "First Name": ["Jane"],
                "Mobile Phone": ["(202) 555-0143"],
                "Junk Column": ["x"],
            }
        )
        out = ContactMapper().map_dataframe(df)
        assert "first_name" in out.columns
        assert "phone" in out.columns
        assert "Junk Column" in out.columns  # unmatched columns preserved
        assert out["phone"].iloc[0] == "+12025550143"

    def test_collision_gets_suffix(self) -> None:
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({"phone": ["(202) 555-0143"], "mobile": ["212-555-9999"]})
        out = ContactMapper().map_dataframe(df)
        cols = list(out.columns)
        assert "phone" in cols
        assert any(c.startswith("phone__") for c in cols)

    def test_confidence_threshold_preserves_low_confidence_columns(self) -> None:
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({"Compny": ["Acme"]})
        out = ContactMapper(confidence_threshold=0.99).map_dataframe(df)
        assert list(out.columns) == ["Compny"]

    def test_strict_phone_normalization_raises(self) -> None:
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({"phone": ["garbage value here"]})
        with pytest.raises(NormalizationError):
            ContactMapper(strict=True).map_dataframe(df)

    def test_strict_confidence_threshold_raises(self) -> None:
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({"Compny": ["Acme"]})
        with pytest.raises(NormalizationError):
            ContactMapper(strict=True, confidence_threshold=0.99).map_dataframe(df)


# ── Heuristic input cap (defensive) ─────────────────────────────────────


class TestHeuristicInputCap:
    def test_overlong_value_is_not_matched(self) -> None:
        strat = HeuristicMatchStrategy()
        long_email = "a" * 600 + "@example.com"
        assert strat.match("col", value=long_email) is None

    def test_normal_value_still_matched(self) -> None:
        strat = HeuristicMatchStrategy()
        match = strat.match("col", value="jane@example.com")
        assert match is not None
        assert match.canonical == "email"


# ── Enum as the single source of truth ──────────────────────────────────


class TestEnumIsSourceOfTruth:
    def test_patterns_fields_are_all_canonical(self) -> None:
        data = json.loads(
            files("rolodexter").joinpath("patterns.json").read_text("utf-8")
        )
        enum_values = {f.value for f in CanonicalField}
        for canonical in data.get("fields", {}):
            assert canonical in enum_values, (
                f"patterns.json field {canonical!r} is not in CanonicalField"
            )

    def test_normalize_value_passthrough_for_unknown_field(self) -> None:
        # Unknown canonical names fall back to a string strip, never crash.
        assert normalize_value("not_a_real_field", "  hi  ") == "hi"


# ── CLI ─────────────────────────────────────────────────────────────────


class TestCLI:
    """Exercise the CLI in-process (so coverage sees __main__.py)."""

    def test_fields(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = cli_main(["fields"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "first_name" in out
        assert "unknown" in out

    def test_explain(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = cli_main(["explain", "Job Titel"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "job_title" in out

    def test_explain_with_value(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = cli_main(["explain", "Mystery", "--value", "jane@example.com"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "email" in out

    def test_map_csv_to_json(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "in.csv"
        csv_path.write_text(
            "First Name,Mobile Phone,Compny\nJane,(202) 555-0143,Acme\n",
            encoding="utf-8",
        )
        out_path = tmp_path / "out.json"
        rc = cli_main(["map", str(csv_path), "-o", str(out_path), "--region", "US"])
        assert rc == 0
        data = json.loads(out_path.read_text("utf-8"))
        assert data[0]["first_name"] == "Jane"
        assert data[0]["phone"] == "+12025550143"
        assert data[0]["company"] == "Acme"

    def test_map_csv_ignores_surplus_cells(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "in.csv"
        csv_path.write_text(
            "Name,Email\nAda,a@example.com,EXTRA\n",
            encoding="utf-8",
        )
        out_path = tmp_path / "out.json"

        rc = cli_main(["map", str(csv_path), "-o", str(out_path), "--format", "json"])

        assert rc == 0
        data = json.loads(out_path.read_text("utf-8"))
        assert data == [{"full_name": "Ada", "email": "a@example.com"}]

    def test_map_to_stdout_jsonl(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        csv_path = tmp_path / "in.csv"
        csv_path.write_text("First Name\nJane\n", encoding="utf-8")
        rc = cli_main(["map", str(csv_path), "--format", "jsonl"])
        out = capsys.readouterr().out
        assert rc == 0
        assert '"first_name": "Jane"' in out

    def test_map_strict_fails_on_bad_phone(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        csv_path = tmp_path / "in.csv"
        csv_path.write_text("phone\ngarbage value here\n", encoding="utf-8")
        rc = cli_main(["map", str(csv_path), "--strict"])
        err = capsys.readouterr().err
        assert rc == 1
        assert "error" in err.lower()

    def test_map_file_failure_does_not_leave_partial_jsonl(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        csv_path = tmp_path / "in.csv"
        csv_path.write_text(
            "phone\n(202) 555-0143\ngarbage value here\n",
            encoding="utf-8",
        )
        out_path = tmp_path / "out.jsonl"

        rc = cli_main(["map", str(csv_path), "-o", str(out_path), "--strict"])
        err = capsys.readouterr().err

        assert rc == 1
        assert "error" in err.lower()
        assert not out_path.exists()

    def test_map_file_failure_preserves_existing_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        csv_path = tmp_path / "in.csv"
        csv_path.write_text("phone\ngarbage value here\n", encoding="utf-8")
        out_path = tmp_path / "out.json"
        original = '[{"first_name": "Existing"}]\n'
        out_path.write_text(original, encoding="utf-8")

        rc = cli_main(["map", str(csv_path), "-o", str(out_path), "--strict"])
        err = capsys.readouterr().err

        assert rc == 1
        assert "error" in err.lower()
        assert out_path.read_text("utf-8") == original

    def test_map_json_input_to_csv_scalarizes_lists(self, tmp_path: Path) -> None:
        # JSON array input -> CSV output; the tags list must collapse to one cell.
        in_path = tmp_path / "in.json"
        in_path.write_text(
            json.dumps([{"fname": "Jane", "tags": "vip, beta"}]),
            encoding="utf-8",
        )
        out_path = tmp_path / "out.csv"
        rc = cli_main(["map", str(in_path), "-o", str(out_path)])
        assert rc == 0
        text = out_path.read_text("utf-8")
        assert "first_name" in text
        assert "vip; beta" in text  # list scalarized for CSV

    def test_map_jsonl_input(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        in_path = tmp_path / "in.jsonl"
        in_path.write_text('{"fname": "A"}\n{"surname": "B"}\n', encoding="utf-8")
        rc = cli_main(["map", str(in_path), "--format", "json"])
        out = capsys.readouterr().out
        assert rc == 0
        data = json.loads(out)
        assert data[0]["first_name"] == "A"
        assert data[1]["last_name"] == "B"

    def test_map_jsonl_skip_bad_row(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        in_path = tmp_path / "in.jsonl"
        in_path.write_text(
            '{"fname": "A"}\n{"not json"\n{"surname": "B"}\n',
            encoding="utf-8",
        )
        rc = cli_main(["map", str(in_path), "--format", "json", "--on-error", "skip"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert rc == 0
        assert [row for row in data] == [{"first_name": "A"}, {"last_name": "B"}]
        assert "skipped row 2" in captured.err

    def test_map_strict_skip_bad_row(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        csv_path = tmp_path / "in.csv"
        csv_path.write_text(
            "phone\n(202) 555-0143\ngarbage value here\n",
            encoding="utf-8",
        )
        rc = cli_main(
            [
                "map",
                str(csv_path),
                "--strict",
                "--on-error",
                "skip",
                "--format",
                "jsonl",
            ]
        )
        captured = capsys.readouterr()
        lines = [json.loads(line) for line in captured.out.splitlines() if line]
        assert rc == 0
        assert lines == [{"phone": "+12025550143"}]
        assert "skipped row 3" in captured.err

    def test_map_jsonl_quarantines_bad_row(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        in_path = tmp_path / "in.jsonl"
        out_path = tmp_path / "out.jsonl"
        quarantine_path = tmp_path / "bad.jsonl"
        in_path.write_text(
            '{"fname": "A"}\n{"not json"\n{"surname": "B"}\n',
            encoding="utf-8",
        )
        rc = cli_main(
            [
                "map",
                str(in_path),
                "-o",
                str(out_path),
                "--format",
                "jsonl",
                "--on-error",
                "quarantine",
                "--quarantine-output",
                str(quarantine_path),
            ]
        )
        err = capsys.readouterr().err
        out_rows = [
            json.loads(line) for line in out_path.read_text("utf-8").splitlines()
        ]
        quarantined = [
            json.loads(line) for line in quarantine_path.read_text("utf-8").splitlines()
        ]
        assert rc == 0
        assert out_rows == [{"first_name": "A"}, {"last_name": "B"}]
        assert quarantined[0]["row"] == 2
        assert "invalid JSON" in quarantined[0]["error"]
        assert "quarantined 1 row" in err

    def test_quarantine_output_requires_quarantine_mode(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        in_path = tmp_path / "in.jsonl"
        in_path.write_text('{"fname": "A"}\n', encoding="utf-8")
        rc = cli_main(
            [
                "map",
                str(in_path),
                "--on-error",
                "skip",
                "--quarantine-output",
                str(tmp_path / "bad.jsonl"),
            ]
        )
        err = capsys.readouterr().err
        assert rc == 1
        assert "--quarantine-output requires --on-error quarantine" in err

    def test_json_output_materialization_limit(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        in_path = tmp_path / "in.jsonl"
        in_path.write_text('{"fname": "A"}\n{"surname": "B"}\n', encoding="utf-8")
        rc = cli_main(
            [
                "map",
                str(in_path),
                "--format",
                "json",
                "--max-materialized-rows",
                "1",
            ]
        )
        captured = capsys.readouterr()
        assert rc == 1
        assert "materializing more than 1 row" in captured.err

    def test_json_output_materialization_limit_precedes_later_row_errors(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        in_path = tmp_path / "in.jsonl"
        in_path.write_text(
            '{"fname": "A"}\n{"surname": "B"}\nnot-json\n', encoding="utf-8"
        )
        rc = cli_main(
            [
                "map",
                str(in_path),
                "--format",
                "json",
                "--max-materialized-rows",
                "1",
            ]
        )
        captured = capsys.readouterr()
        assert rc == 1
        assert "materializing more than 1 row" in captured.err
        assert "row 3" not in captured.err

    def test_jsonl_output_is_not_materialized(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        in_path = tmp_path / "in.jsonl"
        in_path.write_text('{"fname": "A"}\n{"surname": "B"}\n', encoding="utf-8")
        rc = cli_main(
            [
                "map",
                str(in_path),
                "--format",
                "jsonl",
                "--max-materialized-rows",
                "1",
            ]
        )
        captured = capsys.readouterr()
        rows = [json.loads(line) for line in captured.out.splitlines()]
        assert rc == 0
        assert rows == [{"first_name": "A"}, {"last_name": "B"}]

    def test_json_input_byte_limit(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        in_path = tmp_path / "in.json"
        in_path.write_text(json.dumps([{"fname": "A"}]), encoding="utf-8")
        rc = cli_main(["map", str(in_path), "--max-json-input-bytes", "1"])
        err = capsys.readouterr().err
        assert rc == 1
        assert "JSON input is" in err
        assert "--max-json-input-bytes" in err
