"""Audit fixes for value cleaning: H1, H4, M1, M8, L12, L13 and L27.

JavaScript twin: packages/js/test/audit_values.test.ts; both assert the same
outputs.
"""

from __future__ import annotations

import pytest

from rolodexter import ContactMapper
from rolodexter.core import (
    AddressNormalizer,
    NameNormalizer,
    PhoneNormalizer,
    normalize_value,
    value_warnings,
)

# ── H1: consent columns and the field-aware yes/no cleaner ──────────────────


def test_h1_marketing_consent_yes_maps_to_subscribed_true() -> None:
    result = ContactMapper().map_payload({"marketing_consent": "yes"})
    assert result.normalized == {"subscribed": True}


def test_h1_email_opt_out_unsubscribed_is_true() -> None:
    assert normalize_value("email_opt_out", "unsubscribed") is True
    assert normalize_value("email_opt_out", "Opted_Out ") is True
    assert normalize_value("email_opt_out", "opt_in") is False


def test_h1_subscribed_unsubscribed_is_false() -> None:
    assert normalize_value("subscribed", "unsubscribed") is False
    assert normalize_value("subscribed", "subscribed") is True


def test_h1_verified_keeps_status_words_as_text() -> None:
    assert normalize_value("verified", "subscribed") == "subscribed"
    assert normalize_value("verified", " opted_out ") == "opted_out"
    assert normalize_value("verified", "yes") is True


@pytest.mark.parametrize("header", ["sms_consent", "gdpr_consent"])
def test_h1_non_email_consent_never_lands_on_an_email_or_phone_field(
    header: str,
) -> None:
    canonical = ContactMapper().identify(header).canonical
    assert canonical not in {"email_opt_out", "email", "phone"}


# ── H4: address and state casing ────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            "123 Main St, Springfield, IL 62704",
            "123 Main St, Springfield, IL 62704",
        ),
        ("Apt 4B", "Apt 4B"),
        ("100 NW 5th Ave", "100 NW 5th Ave"),
        ("PO Box 12", "PO Box 12"),
        ("1 Main St, USA", "1 Main St, USA"),
        ("123 MAIN ST", "123 Main St"),
        (
            "123 MAIN ST, SPRINGFIELD, IL 62704",
            "123 Main St, Springfield, IL 62704",
        ),
        ("100 NW 5TH AVE APT 4B", "100 NW 5th Ave Apt 4B"),
        (
            "PO BOX 12, WASHINGTON, DC 20001, USA",
            "PO Box 12, Washington, DC 20001, USA",
        ),
        ("1 OAK CT, HARTFORD, CT 06101", "1 Oak Ct, Hartford, CT 06101"),
        ("LA JOLLA", "La Jolla"),
    ],
)
def test_h4_address_keeps_codes_and_unit_letters(raw: str, expected: str) -> None:
    assert AddressNormalizer.normalize(raw) == expected
    assert normalize_value("full_address", raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("NSW", "NSW"),
        ("QLD", "QLD"),
        ("VIC", "VIC"),
        ("NRW", "NRW"),
        ("SP", "SP"),
        ("D.C.", "D.C."),
        ("il", "IL"),
        ("bavaria", "Bavaria"),
    ],
)
def test_h4_state_keeps_capitalised_codes(raw: str, expected: str) -> None:
    assert normalize_value("state", raw) == expected


# ── M1: Mac/Mc only for uncased words that are Mac-names ────────────────────


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Machado", "Machado"),
        ("Macias", "Macias"),
        ("MACHADO", "Machado"),
        ("mackenzie", "Mackenzie"),
        ("Mcdonald", "Mcdonald"),
        ("mcdonald", "McDonald"),
        ("MACARTHUR", "MacArthur"),
        ("macaulay", "MacAulay"),
        ("Macy", "Macy"),
        ("Mack", "Mack"),
        ("Jennifer Le", "Jennifer Le"),
        ("Jane Q. Doe, CPA", "Jane Q. Doe CPA"),
        ("jane doe m.d.", "Jane Doe M.D."),
    ],
)
def test_m1_name_casing(raw: str, expected: str) -> None:
    assert NameNormalizer.normalize(raw) == expected


# ── M8: numeric phone and postal values (contract C3) ───────────────────────


def test_m8_whole_number_phone_is_cleaned_as_digits() -> None:
    assert PhoneNormalizer.normalize(4155550100, default_region="US") == "+14155550100"  # type: ignore[arg-type]
    assert normalize_value("phone", 4155550100.0, default_region="US") == "+14155550100"
    result = ContactMapper(default_region="US").map_payload({"phone": 4155550100})
    assert result.normalized == {"phone": "+14155550100"}
    assert result.warnings == ()


def test_m8_postal_whole_number_is_text() -> None:
    assert normalize_value("postal_code", 94107) == "94107"


@pytest.mark.parametrize("value", [1.5, True, {"n": 1}, [1, 2]])
def test_m8_non_text_phone_gets_the_phone_warning(value: object) -> None:
    warnings = value_warnings("p", "phone", value)
    assert [w.category for w in warnings] == ["phone_normalization"]
    assert str(warnings[0]) == (
        f"'p': phone value {value!r} could not be normalized to E.164 "
        "(set a matching default_region?)"
    )


@pytest.mark.parametrize("value", [None, float("nan")])
def test_m8_empty_phone_cell_is_not_warned(value: object) -> None:
    assert value_warnings("p", "phone", value) == []


# ── L12: country codes ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("U.K.", "GB"),
        ("UK", "GB"),
        ("u.s.", "US"),
        ("de", "DE"),
        ("ZZ", "ZZ"),
        ("xx", "xx"),
    ],
)
def test_l12_country(raw: str, expected: str) -> None:
    assert normalize_value("country", raw) == expected


# ── L13: timestamps keep their time; impossible days are not dates ──────────


@pytest.mark.parametrize(
    "field, raw, expected",
    [
        ("created_at", "2024-03-15T09:30:00Z", "2024-03-15T09:30:00Z"),
        ("updated_at", "2024-3-5 9:30+0530", "2024-03-05T09:30+05:30"),
        (
            "last_contacted",
            "2024-03-15T09:30:00.123-08:00",
            "2024-03-15T09:30:00.123-08:00",
        ),
        ("created_at", "2024-03-15", "2024-03-15"),
        ("created_at", "2024-03-15 9am", "2024-03-15 9am"),
        ("birthday", "2024-03-15T09:30:00Z", "2024-03-15"),
        ("birthday", "2024-02-31", "2024-02-31"),
        ("birthday", "31/02/2024", "31/02/2024"),
        ("birthday", "2023-02-29", "2023-02-29"),
        ("birthday", "2024-2-29", "2024-02-29"),
    ],
)
def test_l13_dates(field: str, raw: str, expected: str) -> None:
    assert normalize_value(field, raw) == expected


# ── L27: name casing is cached per distinct value ───────────────────────────


def test_l27_name_casing_is_cached() -> None:
    from rolodexter._normalizers import _cased_name

    _cased_name.cache_clear()
    NameNormalizer.normalize("jane doe")
    NameNormalizer.normalize("  jane doe ")
    info = _cased_name.cache_info()
    assert (info.hits, info.misses) == (1, 1)


# ── Sweep 2026-11-11: a name value is never emptied ─────────────────────────


@pytest.mark.parametrize("raw", ["\\", '"', "'", "​", "﻿", "\x00"])
def test_name_without_a_name_is_kept_as_written(raw: str) -> None:
    # nameparser 2.x returns "" for these; the value is kept, as in JS.
    assert NameNormalizer.normalize(raw) == raw
    assert normalize_value("last_name", f"  {raw} ") == raw


def test_infinite_phone_warning_writes_inf() -> None:
    warnings = ContactMapper().map_payload({"Phone": float("inf")}).warnings
    assert any("phone value inf could not" in str(w) for w in warnings)
