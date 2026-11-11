"""Audit fixes for header matching: H2, M9, M11 and non-ASCII headers.

The JavaScript twin is ``packages/js/test/audit_matching.test.ts``; both assert
the same verdicts.
"""

from __future__ import annotations

import time

import pytest

from rolodexter import (
    ContactMapper,
    FuzzyMatchStrategy,
    HeuristicMatchStrategy,
    NormalizedMatchStrategy,
    PatternRegistry,
)
from rolodexter.core import FUZZY_LENGTH_RATIO

# ── H2: "Type" / "Label" / "Display Name" columns stay unmapped ─────────────

QUALIFIER_HEADERS = (
    "E-mail 1 - Type",
    "E-mail 1 - Label",
    "Phone 1 - Type",
    "Phone 1 - Label",
    "Address 1 - Type",
    "Organization 1 - Type",
    "Website 1 - Type",
    "E-mail Type",
    "E-mail 2 Type",
    "E-mail Display Name",
    "E-mail 2 Display Name",
    "Phone Type",
    "Contact Type",
)


@pytest.mark.parametrize("header", QUALIFIER_HEADERS)
def test_h2_qualifier_columns_are_unmapped(header: str) -> None:
    match = ContactMapper().identify(header)
    assert (match.canonical, match.strategy) == ("unknown", "none")


@pytest.mark.parametrize(
    "header, expected",
    [
        ("E-mail 1 - Value", "email"),
        ("E-mail 2 Address", "email"),
        ("Phone 1 - Value", "phone"),
        ("Website 1 - Value", "website"),
        ("Address 1 - Formatted", "address_line1"),
        ("Address 1 - Street", "address_line1"),
        ("Organization 1 - Name", "company"),
        ("Organization 1 - Title", "job_title"),
        ("Display Name", "full_name"),
        ("Business Type", "industry"),
        ("Inquiry Type", "subject"),
    ],
)
def test_h2_value_name_title_twins_keep_their_verdicts(
    header: str, expected: str
) -> None:
    assert ContactMapper().identify(header).canonical == expected


def test_h2_no_layer_maps_a_type_column(registry: PatternRegistry) -> None:
    assert NormalizedMatchStrategy(registry).match("E-mail 1 - Type") is None
    assert FuzzyMatchStrategy(registry).match("E-mail Type") is None
    heuristic = HeuristicMatchStrategy()
    assert heuristic.match("Phone 1 - Type", "+14155550100") is None
    # Control: the same value under a plain header is a phone.
    control = heuristic.match("Misc", "+14155550100")
    assert control is not None and control.canonical == "phone"


def test_h2_google_row_keeps_type_labels_out_of_email_and_phone() -> None:
    result = ContactMapper().map_payload(
        {
            "E-mail 1 - Type": "* Work",
            "E-mail 1 - Value": "ada@example.com",
            "Phone 1 - Type": "Mobile",
            "Phone 1 - Value": "+1 415 555 0100",
        }
    )
    assert result.normalized["email"] == "ada@example.com"
    assert result.normalized["phone"] == "+14155550100"
    assert result.unmapped == {"E-mail 1 - Type": "* Work", "Phone 1 - Type": "Mobile"}


# ── M9: no 0.85 containment score for "alias plus a qualifier" ──────────────


def test_m9_length_ratio_is_three_quarters() -> None:
    assert FUZZY_LENGTH_RATIO == 0.75


@pytest.mark.parametrize(
    "header", ["phone_type", "email_type", "phone_ext", "E-mail Type"]
)
def test_m9_alias_plus_qualifier_is_not_matched(header: str) -> None:
    assert ContactMapper().identify(header).canonical == "unknown"


@pytest.mark.parametrize(
    "header, expected",
    [
        ("tel_nationa", ("phone", 0.7, "fuzzy")),
        ("replyt", ("email", 0.7, "fuzzy")),
        ("repyto", ("email", 0.7, "fuzzy")),
        ("ownerid", ("unknown", 0.0, "none")),
        ("Phoneish", ("unknown", 0.0, "none")),
        ("moblie", ("phone", 0.7, "fuzzy")),
    ],
)
def test_m9_short_alias_slips_no_longer_score_high(
    header: str, expected: tuple[str, float, str]
) -> None:
    match = ContactMapper().identify(header)
    assert (match.canonical, match.confidence, match.strategy) == expected


@pytest.mark.parametrize(
    "header, expected",
    [
        ("Contact Province", ("state", 0.95, "normalized")),
        ("Contact Employer", ("company", 0.95, "normalized")),
        ("contact_comments", ("notes", 0.95, "normalized")),
        ("contact_currency", ("currency", 0.95, "normalized")),
        ("Your contact province", ("state", 0.95, "normalized")),
        ("contact_email_id", ("unknown", 0.0, "none")),
        ("contact_owner_id", ("owner", 0.95, "normalized")),
    ],
)
def test_m9_contact_prefix_is_stripped_not_guessed(
    header: str, expected: tuple[str, float, str]
) -> None:
    # Before the 0.75 ratio these reached their field by fuzzy containment;
    # after it, "Contact Province" was guessed as phone. The rewrite layer now
    # strips "contact_" as it does "billing_", and a reference stays unmatched.
    match = ContactMapper().identify(header)
    assert (match.canonical, match.confidence, match.strategy) == expected


# ── M11: long headers skip the rewrite and fuzzy layers ─────────────────────


@pytest.mark.parametrize("header", [" " * 50_000, "a" + " " * 50_000 + "b"])
def test_m11_huge_header_maps_quickly(header: str) -> None:
    start = time.perf_counter()
    match = ContactMapper().identify(header)
    elapsed = time.perf_counter() - start
    assert match.canonical == "unknown"
    assert elapsed < 1.0


def test_m11_rewrite_layers_skip_headers_over_200_chars(
    registry: PatternRegistry,
) -> None:
    header = "First" + " " * 200 + "Name"
    assert NormalizedMatchStrategy(registry).match(header) is None
    assert FuzzyMatchStrategy(registry).match(header) is None
    # Short enough, the same header still normalizes.
    short = NormalizedMatchStrategy(registry).match("First Name")
    assert short is not None and short.canonical == "first_name"


# ── Non-ASCII headers: same verdict as the JavaScript port ──────────────────


@pytest.mark.parametrize(
    "header, expected",
    [
        ("Teléfono", ("phone", 0.7, "fuzzy")),
        ("Straße 1", ("unknown", 0.0, "none")),
        ("Ciudad/Población", ("unknown", 0.0, "none")),
    ],
)
def test_non_ascii_header_verdicts(
    header: str, expected: tuple[str, float, str]
) -> None:
    match = ContactMapper().identify(header)
    assert (match.canonical, match.confidence, match.strategy) == expected


def test_non_ascii_letters_survive_header_rewriting() -> None:
    registry = PatternRegistry(patterns={"fields": {"phone": ["teléfono_móvil"]}})
    match = NormalizedMatchStrategy(registry).match("Teléfono Móvil")
    assert match is not None and match.canonical == "phone"
