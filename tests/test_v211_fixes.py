"""Regression tests for the 2.11.0 fix batch.

Covers the i18n cache-directory escape guard and corrupt-cache-file
tolerance, the reference-header ("*_id") veto on value-bearing fields, the
postal-code heuristic's header-hint guard, warning categorization, the new
Date/Country/State normalizers, the ``MappingSchema`` JSON round-trip,
``ContactMapper.profile(normalize=False)``, and a set of CLI safety nets
(overwrite guard, --keep-unmapped, duplicate columns, headerless CSV
detection, --on-error skip, quarantine no-op, --dedupe, --override,
--schema-out/--schema-in, --version and profile output).

Each test is written to fail if the underlying fix were reverted, not
merely to exercise the happy path.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from rolodexter import ContactMapper, MappingSchema, PatternLoadError, i18n
from rolodexter.__main__ import EXIT_PARTIAL, _atomic_output
from rolodexter.__main__ import main as cli_main
from rolodexter.core import (
    CountryNormalizer,
    DateNormalizer,
    HeuristicMatchStrategy,
    StateNormalizer,
    WarningCategory,
)

# ── 1. i18n cache-dir escape + language-code normalization ─────────────


class TestI18nCacheEscape:
    def test_load_cached_cannot_escape_the_cache_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A traversal code must not resolve to a file outside the cache dir.

        Plants a valid-looking cache file two directories *above* the
        (monkeypatched) cache dir, at exactly the path a naive
        ``cache_dir / f"{lang_code}.json"`` join would resolve to for
        ``"../../anything"``.  A pre-fix implementation that skips
        :func:`~rolodexter.i18n.normalize_language_code` would find and
        return that file; the fix rejects the code before any path is
        built, so it must stay ``None`` even though the escape target
        exists and parses fine.
        """
        cache_dir = tmp_path / "a" / "b"
        cache_dir.mkdir(parents=True)
        escape_target = tmp_path / "anything.json"
        escape_target.write_text(
            json.dumps(
                {
                    "language_code": "anything",
                    "language_name": "X",
                    "fields": {"email": ["x"]},
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(i18n, "get_all_cache_dirs", lambda: [cache_dir])

        assert i18n.load_cached("../../anything") is None

    def test_normalize_language_code_trims_and_lowercases(self) -> None:
        assert i18n.normalize_language_code(" ES ") == "es"

    def test_normalize_language_code_rejects_unsupported(self) -> None:
        assert i18n.normalize_language_code("zz") is None


# ── 2. Corrupt i18n cache file is skipped, not raised ───────────────────


class TestCorruptCacheFileIsSkipped:
    def test_non_string_alias_is_treated_as_corrupt(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A hand-edited/truncated cache file must not crash construction.

        Before the fix, a ``fields`` value holding a non-string alias (here
        ``123`` instead of a string) raised ``AttributeError`` deep inside
        ``PatternRegistry`` construction the first time code tried to
        ``.lower()`` it.  The fix validates the schema up front and skips
        the file as corrupt, so the language is simply not loaded.
        """
        cache_dir = tmp_path / "i18n_cache"
        cache_dir.mkdir()
        (cache_dir / "es.json").write_text(
            json.dumps(
                {
                    "language_code": "es",
                    "language_name": "Spanish",
                    "fields": {"email": [123]},
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(i18n, "get_all_cache_dirs", lambda: [cache_dir])

        mapper = ContactMapper(languages=["es"])  # must not raise

        assert mapper.registry.loaded_languages == []


# ── 3. Unsupported language code warns, naming the code ────────────────


class TestUnsupportedLanguageWarns:
    def test_warns_with_the_offending_code_and_still_constructs(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="rolodexter"):
            mapper = ContactMapper(languages=["nope"])  # must not raise

        assert mapper is not None
        messages = [r.message for r in caplog.records if r.name == "rolodexter"]
        assert any("'nope'" in m for m in messages)


# ── 4. Heuristic postal-code guard ──────────────────────────────────────


class TestPostalCodeGuard:
    def test_ambiguous_five_digit_value_needs_a_header_hint(self) -> None:
        strat = HeuristicMatchStrategy()
        match = strat.match("order_total", value="45000")
        assert match is None

    def test_zip_header_hint_confirms_the_ambiguous_shape(self) -> None:
        strat = HeuristicMatchStrategy()
        match = strat.match("zip", value="90210")
        assert match is not None
        assert match.canonical == "postal_code"

    def test_distinctive_postal_shape_needs_no_hint(self) -> None:
        strat = HeuristicMatchStrategy()
        match = strat.match("Unknown Column", value="K1A 0B1")
        assert match is not None
        assert match.canonical == "postal_code"


# ── 5. Reference-header ("*_id") veto ───────────────────────────────────


class TestReferenceHeaderGuard:
    @pytest.mark.parametrize(
        "header",
        ["primary_phone_id", "contact_email_id", "website_id", "email_ref"],
    )
    def test_foreign_key_header_is_not_guessed_into_a_value_field(
        self, header: str
    ) -> None:
        assert ContactMapper().identify(header).canonical == "unknown"

    def test_owner_id_still_strips_to_owner(self) -> None:
        assert ContactMapper().identify("owner_id").canonical == "owner"

    def test_shipping_company_id_still_strips_to_company(self) -> None:
        assert ContactMapper().identify("shipping_company_id").canonical == "company"


# ── 6. get_identity_keys() vendor-pairing ambiguity ─────────────────────
#
# Already covered by TestIdentityHelpers in test_v28_features.py
# (test_ambiguous_source_services_are_not_paired_by_position and
# test_single_source_service_still_scopes_every_id) — intentionally not
# duplicated here.


# ── 7. Warning categories ───────────────────────────────────────────────


class TestWarningCategories:
    def test_low_confidence_category(self) -> None:
        result = ContactMapper().map_payload(
            {"Mystery Column": "jane@example.com"}, confidence_threshold=0.8
        )
        assert result.warnings[0].category == WarningCategory.LOW_CONFIDENCE.value

    def test_phone_normalization_category(self) -> None:
        result = ContactMapper().map_payload({"phone": "not a phone"})
        assert result.warnings[0].category == WarningCategory.PHONE_NORMALIZATION.value

    def test_email_validation_category(self) -> None:
        result = ContactMapper().map_payload({"email": "not-an-email"})
        assert result.warnings[0].category == WarningCategory.EMAIL_VALIDATION.value

    def test_date_ambiguous_category(self) -> None:
        result = ContactMapper().map_payload({"birthday": "03/04/2024"})
        assert result.warnings[0].category == WarningCategory.DATE_AMBIGUOUS.value

    def test_warning_is_still_a_plain_string(self) -> None:
        """MappingWarning subclasses str so the public API stays unbroken."""
        result = ContactMapper().map_payload({"phone": "not a phone"})
        warning = result.warnings[0]
        assert isinstance(warning, str)
        assert warning == (
            "'phone': phone value 'not a phone' could not be normalized to "
            "E.164 (set a matching default_region?)"
        )


# ── 8. New normalizers ──────────────────────────────────────────────────


class TestDateNormalizer:
    def test_unambiguous_day_first_is_reordered_to_iso(self) -> None:
        assert DateNormalizer.normalize("25/03/2024") == "2024-03-25"

    def test_leading_four_digit_year_is_reordered_to_iso(self) -> None:
        assert DateNormalizer.normalize("2024/3/5") == "2024-03-05"

    def test_ambiguous_day_month_order_is_left_unchanged(self) -> None:
        """03/04/2024 could be 3 April or 4 March — refuses to guess."""
        assert DateNormalizer.normalize("03/04/2024") == "03/04/2024"

    def test_two_digit_year_is_left_unchanged(self) -> None:
        """Mapping "68" to 1968 or 2068 is a guess this class won't make."""
        assert DateNormalizer.normalize("12/11/68") == "12/11/68"


class TestCountryNormalizer:
    def test_english_name_to_alpha2(self) -> None:
        assert CountryNormalizer.normalize("United States") == "US"

    def test_native_spelling_to_alpha2(self) -> None:
        assert CountryNormalizer.normalize("deutschland") == "DE"

    def test_unknown_country_round_trips_unchanged(self) -> None:
        assert CountryNormalizer.normalize("Narnia") == "Narnia"


class TestStateNormalizer:
    def test_us_state_name_to_code(self) -> None:
        assert StateNormalizer.normalize("california") == "CA"

    def test_canadian_province_name_to_code(self) -> None:
        assert StateNormalizer.normalize("Ontario") == "ON"

    def test_unrecognized_region_is_left_alone(self) -> None:
        assert StateNormalizer.normalize("Bavaria") == "Bavaria"


# ── 9. MappingSchema JSON round-trip ─────────────────────────────────────


class TestMappingSchemaRoundTrip:
    def test_to_dict_from_dict_round_trip_matches_a_fresh_mapper(self) -> None:
        headers = ["First Name", "Mobile Phone", "Whatever"]
        original_mapper = ContactMapper()
        schema = original_mapper.compile_schema(headers)

        serialized = json.dumps(schema.to_dict())

        fresh_mapper = ContactMapper()
        rebuilt = MappingSchema.from_dict(json.loads(serialized), fresh_mapper)

        assert rebuilt.column_map() == schema.column_map()

        row = {
            "First Name": "Jane",
            "Mobile Phone": "(202) 555-0143",
            "Whatever": "x",
        }
        assert rebuilt.apply(row).normalized == schema.apply(row).normalized

    def test_from_dict_rejects_wrong_schema_version(self) -> None:
        with pytest.raises(PatternLoadError, match="version"):
            MappingSchema.from_dict(
                {"schema_version": 999, "columns": {}}, ContactMapper()
            )

    def test_from_dict_rejects_malformed_columns(self) -> None:
        with pytest.raises(PatternLoadError, match="columns"):
            MappingSchema.from_dict(
                {"schema_version": MappingSchema.SCHEMA_VERSION, "columns": "nope"},
                ContactMapper(),
            )


# ── 10. profile(normalize=False) trade-off ───────────────────────────────


class TestProfileNormalizeFalse:
    def test_same_match_counts_but_no_phone_normalization_warnings(self) -> None:
        rows = [
            {"fname": "Jane", "phone": "not a phone"},
            {"phone": "(202) 555-0143"},
        ]
        mapper = ContactMapper()

        default_profile = mapper.profile(rows)
        unnormalized_profile = mapper.profile(rows, normalize=False)

        assert unnormalized_profile.matched_count == default_profile.matched_count
        assert unnormalized_profile.canonical_counts == default_profile.canonical_counts
        assert default_profile.warning_counts == {"phone_normalization": 1}
        assert unnormalized_profile.warning_counts == {}


# ── 11. CLI: input/output overwrite guard ────────────────────────────────


class TestCLIOverwriteGuard:
    def test_mapping_a_file_onto_itself_is_rejected_and_leaves_it_untouched(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        csv_path = tmp_path / "input.csv"
        csv_path.write_text("First Name\nJane\n", encoding="utf-8")
        original_bytes = csv_path.read_bytes()

        rc = cli_main(["map", str(csv_path), "-o", str(csv_path)])
        err = capsys.readouterr().err

        assert rc != 0
        assert "output must differ from the input path" in err
        assert csv_path.read_bytes() == original_bytes


# ── 12. CLI: --keep-unmapped ──────────────────────────────────────────────


class TestCLIKeepUnmapped:
    def test_keep_unmapped_carries_the_column_through(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "in.csv"
        csv_path.write_text("First Name,Weird Col\nJane,zzz\n", encoding="utf-8")
        out_path = tmp_path / "out.json"

        rc = cli_main(["map", str(csv_path), "-o", str(out_path), "--keep-unmapped"])

        assert rc == 0
        data = json.loads(out_path.read_text("utf-8"))
        assert data == [{"first_name": "Jane", "Weird Col": "zzz"}]

    def test_without_the_flag_the_column_is_dropped_and_warned_about(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        csv_path = tmp_path / "in.csv"
        csv_path.write_text("First Name,Weird Col\nJane,zzz\n", encoding="utf-8")
        out_path = tmp_path / "out.json"

        rc = cli_main(["map", str(csv_path), "-o", str(out_path)])
        err = capsys.readouterr().err

        assert rc == 0
        data = json.loads(out_path.read_text("utf-8"))
        assert data == [{"first_name": "Jane"}]
        assert "dropped unmapped column" in err


# ── 13. CLI: duplicate-named columns merge into a list ───────────────────


class TestCLIDuplicateColumns:
    def test_two_identically_named_columns_keep_both_values(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        csv_path = tmp_path / "in.csv"
        csv_path.write_text(
            "Email,Email\na@example.com,b@example.com\n", encoding="utf-8"
        )
        out_path = tmp_path / "out.json"

        rc = cli_main(["map", str(csv_path), "-o", str(out_path), "--keep-unmapped"])
        err = capsys.readouterr().err

        assert rc == 0
        data = json.loads(out_path.read_text("utf-8"))
        assert data == [{"email": ["a@example.com", "b@example.com"]}]
        assert "duplicate column name" in err


# ── 14. CLI: headerless CSV detection ────────────────────────────────────


class TestCLIHeaderlessDetection:
    def test_warns_when_the_first_row_looks_like_data(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        csv_path = tmp_path / "in.csv"
        csv_path.write_text(
            "jane@example.com,555-1234,x\n"
            "john@example.com,555-5678,y\n"
            "sam@example.com,555-9999,z\n",
            encoding="utf-8",
        )
        out_path = tmp_path / "out.json"

        rc = cli_main(["map", str(csv_path), "-o", str(out_path)])
        err = capsys.readouterr().err

        assert rc == 0
        assert "looks like DATA, not column names" in err


# ── 15. CLI: --on-error skip ──────────────────────────────────────────────


class TestCLIOnErrorSkip:
    def test_malformed_row_returns_exit_partial(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        in_path = tmp_path / "in.jsonl"
        in_path.write_text('{"fname": "A"}\nnot-json\n', encoding="utf-8")
        out_path = tmp_path / "out.json"

        rc = cli_main(
            [
                "map",
                str(in_path),
                "-o",
                str(out_path),
                "--format",
                "json",
                "--on-error",
                "skip",
            ]
        )

        assert rc == EXIT_PARTIAL

    def test_a_fully_clean_run_returns_zero(self, tmp_path: Path) -> None:
        in_path = tmp_path / "in.jsonl"
        in_path.write_text('{"fname": "A"}\n', encoding="utf-8")
        out_path = tmp_path / "out.json"

        rc = cli_main(
            [
                "map",
                str(in_path),
                "-o",
                str(out_path),
                "--format",
                "json",
                "--on-error",
                "skip",
            ]
        )

        assert rc == 0


# ── 16. CLI: quarantine file is a no-op on zero failures ────────────────


class TestCLIQuarantineNoOp:
    def test_zero_failures_does_not_create_or_truncate_the_quarantine_file(
        self, tmp_path: Path
    ) -> None:
        in_path = tmp_path / "in.jsonl"
        in_path.write_text('{"fname": "A"}\n', encoding="utf-8")
        out_path = tmp_path / "out.json"
        quarantine_path = tmp_path / "bad.jsonl"
        quarantine_path.write_text("PRESERVE ME", encoding="utf-8")

        rc = cli_main(
            [
                "map",
                str(in_path),
                "-o",
                str(out_path),
                "--format",
                "json",
                "--on-error",
                "quarantine",
                "--quarantine-output",
                str(quarantine_path),
            ]
        )

        assert rc == 0
        assert quarantine_path.read_text("utf-8") == "PRESERVE ME"


# ── 17. CLI: --dedupe ──────────────────────────────────────────────────


class TestCLIDedupe:
    def test_second_row_sharing_an_email_case_insensitively_is_dropped(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        csv_path = tmp_path / "in.csv"
        csv_path.write_text(
            "First Name,Email\nJane,A@Example.com\nJohn,a@example.com\n",
            encoding="utf-8",
        )
        out_path = tmp_path / "out.json"

        rc = cli_main(["map", str(csv_path), "-o", str(out_path), "--dedupe"])
        err = capsys.readouterr().err

        assert rc == 0
        data = json.loads(out_path.read_text("utf-8"))
        assert data == [{"first_name": "Jane", "email": "a@example.com"}]
        assert "dropped 1 duplicate row" in err


# ── 18. CLI: --override ──────────────────────────────────────────────────


class TestCLIOverride:
    def test_override_routes_an_unrecognized_column(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "in.csv"
        csv_path.write_text("MMERGE3\n123 Main St\n", encoding="utf-8")
        out_path = tmp_path / "out.json"

        rc = cli_main(
            [
                "map",
                str(csv_path),
                "-o",
                str(out_path),
                "--override",
                "MMERGE3=full_address",
            ]
        )

        assert rc == 0
        data = json.loads(out_path.read_text("utf-8"))
        assert data == [{"full_address": "123 Main St"}]

    def test_override_to_an_unknown_field_errors_naming_rolodexter_fields(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        csv_path = tmp_path / "in.csv"
        csv_path.write_text("MMERGE3\n123 Main St\n", encoding="utf-8")
        out_path = tmp_path / "out.json"

        rc = cli_main(
            [
                "map",
                str(csv_path),
                "-o",
                str(out_path),
                "--override",
                "MMERGE3=not_a_field",
            ]
        )
        err = capsys.readouterr().err

        assert rc != 0
        assert "rolodexter fields" in err


# ── 19. CLI: --schema-out / --schema-in round-trip ───────────────────────


class TestCLISchemaRoundTrip:
    def test_replaying_a_saved_plan_reproduces_byte_identical_output(
        self, tmp_path: Path
    ) -> None:
        csv_path = tmp_path / "in.csv"
        csv_path.write_text(
            "First Name,Mobile Phone\nJane,(202) 555-0143\n", encoding="utf-8"
        )
        schema_path = tmp_path / "plan.json"
        out1_path = tmp_path / "out1.json"
        out2_path = tmp_path / "out2.json"

        rc1 = cli_main(
            [
                "map",
                str(csv_path),
                "-o",
                str(out1_path),
                "--schema-out",
                str(schema_path),
            ]
        )
        rc2 = cli_main(
            [
                "map",
                str(csv_path),
                "-o",
                str(out2_path),
                "--schema-in",
                str(schema_path),
            ]
        )

        assert rc1 == 0
        assert rc2 == 0
        assert out1_path.read_bytes() == out2_path.read_bytes()


# ── 20. CLI: --version and profile output ────────────────────────────────


class TestCLIVersionAndProfile:
    def test_version_flag_prints_the_version_and_exits_zero(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from rolodexter import __version__

        with pytest.raises(SystemExit) as exc_info:
            cli_main(["--version"])
        out = capsys.readouterr().out

        assert exc_info.value.code == 0
        assert __version__ in out

    def test_profile_command_reports_unmapped_headers(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        csv_path = tmp_path / "in.csv"
        csv_path.write_text("First Name,Weird\nJane,zzz\n", encoding="utf-8")

        rc = cli_main(["profile", str(csv_path)])
        out = capsys.readouterr().out

        assert rc == 0
        assert "Unmapped headers" in out


class TestAtomicOutputFailurePath:
    """The branch that decides whether a crashed run corrupts the user's file.

    ``_atomic_output`` writes to a same-directory temp file and only then
    replaces the target.  The cleanup path after a failed ``os.replace`` was
    never exercised, so nothing pinned that a failure leaves the original
    intact and no stray ``.tmp`` file behind.
    """

    def test_replace_failure_preserves_target_and_removes_temp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "out.json"
        target.write_text("ORIGINAL", encoding="utf-8")

        def boom(src: object, dst: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr("rolodexter.__main__.os.replace", boom)

        with (
            pytest.raises(OSError, match="disk full"),
            _atomic_output(str(target)) as fh,
        ):
            fh.write("REPLACEMENT")

        assert target.read_text(encoding="utf-8") == "ORIGINAL"
        leftovers = [p.name for p in tmp_path.iterdir() if p.name != "out.json"]
        assert leftovers == [], f"temp file(s) left behind: {leftovers}"

    def test_success_replaces_target(self, tmp_path: Path) -> None:
        target = tmp_path / "out.json"
        target.write_text("ORIGINAL", encoding="utf-8")
        with _atomic_output(str(target)) as fh:
            fh.write("REPLACEMENT")
        assert target.read_text(encoding="utf-8") == "REPLACEMENT"
        assert [p.name for p in tmp_path.iterdir()] == ["out.json"]


class TestMergeIgnoresBlanks:
    """Two columns meaning one field, only one filled in.

    Before, the blank one was merged in and the caller got
    ``["bob@y.co.uk", ""]`` where a single address was meant. Surfaced by the
    CLI's duplicate-header fix, which stopped discarding the first column.
    """

    def test_blank_second_column_does_not_create_a_list(self) -> None:
        result = ContactMapper().map_payload({"E-Mail": "bob@y.co.uk", "E-Mail__2": ""})
        assert result.normalized["email"] == "bob@y.co.uk"

    def test_blank_first_column_is_replaced(self) -> None:
        result = ContactMapper().map_payload({"E-Mail": "", "E-Mail__2": "bob@y.co.uk"})
        assert result.normalized["email"] == "bob@y.co.uk"

    def test_two_real_values_still_collide_into_a_list(self) -> None:
        result = ContactMapper().map_payload(
            {"E-Mail": "a@x.com", "E-Mail__2": "b@x.com"}
        )
        assert result.normalized["email"] == ["a@x.com", "b@x.com"]
