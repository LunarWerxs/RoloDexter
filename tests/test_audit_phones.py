"""Audit group W2 (phones): H6 region-first dial-out, M8 7-digit numbers, L25 extensions."""

from __future__ import annotations

import pytest

from rolodexter._phone import format_e164, parse

_CASES = [
    ("011 234 5678", "ZA", "+27112345678"),
    ("011 2345 6789", "IN", "+911123456789"),
    ("0011 61 2 9999 0000", "AU", "+61299990000"),
    ("011 44 20 7946 0958", "US", "+442079460958"),
    ("011 44 20 7946 0958", None, "+442079460958"),
    ("00 44 20 7946 0958", None, "+442079460958"),
]


@pytest.mark.parametrize(("raw", "region", "expected"), _CASES)
def test_h6_region_parsed_before_dialout_rewrite(
    raw: str, region: str | None, expected: str
) -> None:
    assert format_e164(raw, region) == expected


def test_m8_seven_digit_local_number_is_not_e164() -> None:
    assert format_e164("555-1234", "US") is None
    assert parse("555-1234", "US") is None


def test_m8_full_us_number_still_normalizes() -> None:
    assert format_e164("415-555-0100", "US") == "+14155550100"


@pytest.mark.parametrize(
    ("raw", "region"),
    [("+1 415 555 0100 x123", None), ("415 555 0100 ext 123", "US")],
)
def test_l25_extension_kept_as_ext_suffix(raw: str, region: str | None) -> None:
    assert format_e164(raw, region) == "+14155550100;ext=123"
