"""Regression tests for the 2026-11-11 audit, mapper group (W4).

Each test names its finding id.  The JavaScript twin is
``packages/js/test/audit_mapper.test.ts``.
"""

from __future__ import annotations

import csv
import io
import logging
from unittest import mock

import pytest

from rolodexter import ContactMapper, MappingSchema
from rolodexter._models import _value_for_matching
from rolodexter.core import MappingResult, NormalizationError, PatternLoadError

SERVICE_TEXT = (
    "the 'service' argument is ignored since rolodexter 2.0 and will be "
    "removed in a future release"
)


def _result(normalized: dict) -> MappingResult:
    return MappingResult(normalized=normalized, unmapped={}, field_matches=())


# ── H3 (contract C2): identity keys ────────────────────────────────────────


def test_h3_placeholders_never_become_identity_keys() -> None:
    keys = _result(
        {"email": ["n/a", "-", "ada@example.com"], "phone": ["none", "555-1234"]}
    ).get_identity_keys()
    assert keys == ["email:ada@example.com"]


def test_h3_work_phone_and_fax_are_not_identity_keys() -> None:
    keys = _result(
        {"work_phone": "+14155550100", "fax": "+14155550199"}
    ).get_identity_keys()
    assert keys == []


def test_h3_phone_key_drops_the_extension() -> None:
    keys = _result(
        {"phone": "+14155550100;ext=123", "home_phone": "+14155550100"}
    ).get_identity_keys()
    assert keys == ["phone:+14155550100"]


# ── M7: non-text payload keys ──────────────────────────────────────────────


def test_m7_none_key_goes_to_unmapped_and_never_crashes() -> None:
    result = ContactMapper().map_payload({"email": "a@b.co", None: ["x", "y"]})
    assert result.normalized == {"email": "a@b.co"}
    assert result.unmapped == {None: ["x", "y"]}
    assert all(m.original is not None for m in result.field_matches)


def test_m7_other_non_text_key_is_matched_on_its_text() -> None:
    class Header:
        def __str__(self) -> str:
            return "email"

    result = ContactMapper().map_payload({Header(): "a@b.co"})
    assert result.normalized == {"email": "a@b.co"}


def test_m7_map_stream_survives_an_overlong_dictreader_row() -> None:
    text = "email,first_name\na@b.co,Ada,extra,cells\n"
    results = list(ContactMapper().map_stream(csv.DictReader(io.StringIO(text))))
    assert results[0].normalized["email"] == "a@b.co"
    assert results[0].unmapped == {None: ["extra", "cells"]}


# ── M8 (contract C3, mapper part): value-shape text of whole floats ───────


def test_m8_whole_number_float_is_written_without_point_zero() -> None:
    assert _value_for_matching(4155550100.0) == "4155550100"
    assert _value_for_matching(4155550100) == "4155550100"
    assert _value_for_matching(1.5) == "1.5"


# ── M10: seeded plan verdicts survive the header cache ─────────────────────

_PLAN = {
    "schema_version": 1,
    "default_region": "US",
    "columns": {
        "Contact": {"canonical": "company", "confidence": 1.0, "strategy": "schema"}
    },
}


@pytest.mark.parametrize("max_size", [0, 1])
def test_m10_seeded_plan_survives_cache_size_and_clear(max_size: int) -> None:
    mapper = ContactMapper(header_cache_max_size=max_size)
    MappingSchema.from_dict(_PLAN, mapper)
    mapper.clear_cache()
    for header in ("a", "b", "c"):  # evicts anything held in the LRU cache
        mapper.map_payload({header: "x"})
    match = mapper.map_payload({"Contact": "Acme"}).get_match("Contact")
    assert match is not None
    assert match.canonical == "company"
    assert match.strategy == "schema"


# ── L14 (contract C6): logs and errors carry header + category only ────────


def test_l14_log_and_error_name_header_and_category_not_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "garbage value here"
    with caplog.at_level(logging.WARNING, logger="rolodexter"):
        result = ContactMapper().map_payload({"phone": secret})
    assert any(secret in w for w in result.warnings)
    assert caplog.messages == ["'phone': phone_normalization"]
    with pytest.raises(NormalizationError) as info:
        ContactMapper(strict=True).map_payload({"phone": secret})
    assert str(info.value) == "'phone': phone_normalization"


# ── L15 / L27: map_dataframe ───────────────────────────────────────────────


def test_l15_map_dataframe_surfaces_ambiguous_dates() -> None:
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame({"birthday": ["03/04/2020"]})
    with pytest.raises(NormalizationError, match="date_ambiguous"):
        ContactMapper(strict=True).map_dataframe(df)


def test_l27_map_dataframe_cleans_each_repeated_value_once() -> None:
    pd = pytest.importorskip("pandas")
    import rolodexter.core as core

    df = pd.DataFrame({"city": ["paris"] * 50 + ["rome"] * 50})
    with mock.patch.object(core, "normalize_value", wraps=core.normalize_value) as spy:
        out = ContactMapper().map_dataframe(df)
    assert spy.call_count == 2
    assert list(out["city"].unique()) == ["Paris", "Rome"]


# ── L16: from_dict refuses unknown field names ─────────────────────────────


def test_l16_from_dict_refuses_a_field_that_is_not_canonical() -> None:
    plan = {
        "schema_version": 1,
        "columns": {"E": {"canonical": "emial", "confidence": 1.0}},
    }
    with pytest.raises(PatternLoadError, match="'emial', which is not a canonical"):
        MappingSchema.from_dict(plan, ContactMapper())


def test_l16_from_dict_accepts_an_override_target() -> None:
    mapper = ContactMapper(overrides={"crm ref": "crm_ref"})
    plan = mapper.compile_schema(["crm ref"]).to_dict()
    restored = MappingSchema.from_dict(plan, ContactMapper(overrides={"x": "crm_ref"}))
    assert restored.column_map() == {"crm ref": "crm_ref"}


# ── L18: embedded phones are not columns ───────────────────────────────────


def test_l18_profile_counts_embedded_phones_apart_from_columns() -> None:
    profile = ContactMapper().profile(
        [{"notes": "call me at +1 415 555 0100"}], extract_embedded_phones=True
    )
    assert profile.fields_seen == 1
    assert profile.matched_count + profile.unmatched_count == 1
    assert profile.embedded_phone_count == 1
    assert profile.to_dict()["embedded_phone_count"] == 1


# ── L19: flattening collisions warn ────────────────────────────────────────


def test_l19_flatten_collision_is_warned() -> None:
    result = ContactMapper().map_payload({"a.b": 1, "a": {"b": 2}}, depth=2)
    assert (
        "'a.b': two payload keys flatten to this name; the later value "
        "replaced the earlier one"
    ) in result.warnings


# ── L28: service / default_service are deprecated ──────────────────────────


def test_l28_service_arguments_emit_deprecation_warnings() -> None:
    with pytest.warns(DeprecationWarning) as record:
        ContactMapper(default_service="hubspot")
    assert str(record[0].message) == SERVICE_TEXT.replace(
        "'service'", "'default_service'"
    )
    assert record[0].filename == __file__
    mapper = ContactMapper()
    for call in (
        lambda: mapper.map_payload({"email": "a@b.co"}, service="x"),
        lambda: mapper.identify("email", service="x"),
        lambda: mapper.map_batch([{"email": "a@b.co"}], service="x"),
    ):
        with pytest.warns(DeprecationWarning, match="'service' argument is ignored"):
            call()


# ── L29: no subclass __slots__ that cannot work ────────────────────────────


def test_l29_contact_mapper_declares_no_ineffective_slots() -> None:
    assert "__slots__" not in vars(ContactMapper)
