"""The per-field value normalizers.

Extracted verbatim from ``test_rolodexter.py``.
"""

from __future__ import annotations

import pytest

from rolodexter import (
    ContactMapper,
)
from rolodexter.core import (
    AddressNormalizer,
    EmailNormalizer,
    NameNormalizer,
    StringNormalizer,
    normalize_value,
)


class TestEmailNormalizer:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("HELLO@Example.COM", "hello@example.com"),
            ("  user@test.org  ", "user@test.org"),
            ("", ""),
        ],
    )
    def test_normalize(self, raw: str, expected: str) -> None:
        assert EmailNormalizer.normalize(raw) == expected


class TestNameNormalizer:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("jane doe", "Jane Doe"),
            ("JANE DOE", "Jane Doe"),
            ("jane van der berg", "Jane van der Berg"),
            ("jean-pierre", "Jean-Pierre"),
            ("  john  ", "John"),
            ("maria del carmen", "Maria del Carmen"),
        ],
    )
    def test_normalize(self, raw: str, expected: str) -> None:
        assert NameNormalizer.normalize(raw) == expected

    def test_empty(self) -> None:
        assert NameNormalizer.normalize("") == ""

    def test_none(self) -> None:
        assert NameNormalizer.normalize(None) is None  # type: ignore[arg-type]


class TestAddressNormalizer:
    def test_normalize(self) -> None:
        assert AddressNormalizer.normalize("  123  main   st  ") == "123 Main St"

    def test_empty(self) -> None:
        assert AddressNormalizer.normalize("") == ""


class TestStringNormalizer:
    def test_strips_whitespace(self) -> None:
        assert StringNormalizer.normalize("  hello  ") == "hello"

    def test_passthrough_non_string(self) -> None:
        assert StringNormalizer.normalize(42) == 42  # type: ignore[arg-type]


class TestNormalizeValue:
    def test_phone(self) -> None:
        assert normalize_value("phone", "+1-555-000-1234") == "+15550001234"

    def test_email(self) -> None:
        assert normalize_value("email", "  A@B.COM  ") == "a@b.com"

    def test_name(self) -> None:
        assert normalize_value("first_name", "jane") == "Jane"

    def test_address(self) -> None:
        assert normalize_value("city", "  new york  ") == "New York"

    def test_fallback_string(self) -> None:
        # tags now uses ListNormalizer (v2.6.0) — single values become a list
        assert normalize_value("tags", "  vip  ") == ["vip"]
        # Fields without a category normalizer still use StringNormalizer
        assert normalize_value("notes", "  hello  ") == "hello"

    def test_non_string_passthrough(self) -> None:
        assert normalize_value("phone", 12345) == 12345
        assert normalize_value("email", None) is None
        assert normalize_value("tags", [" vip ", "", "  ", "beta"]) == [
            "vip",
            "beta",
        ]


class TestV23PostalCodeNormalizer:
    """PostalCodeNormalizer: uppercase + Canadian spacing."""

    def test_canadian_postal_code_spacing(self) -> None:
        from rolodexter.core import PostalCodeNormalizer

        n = PostalCodeNormalizer()
        assert n.normalize("k1a0b1") == "K1A 0B1"
        assert n.normalize("K1A 0B1") == "K1A 0B1"
        assert n.normalize("  m5v 2t6  ") == "M5V 2T6"

    def test_us_zip_passthrough(self) -> None:
        from rolodexter.core import PostalCodeNormalizer

        n = PostalCodeNormalizer()
        assert n.normalize("90210") == "90210"
        assert n.normalize("90210-1234") == "90210-1234"

    def test_uppercase(self) -> None:
        from rolodexter.core import PostalCodeNormalizer

        n = PostalCodeNormalizer()
        assert n.normalize("sw1a 1aa") == "SW1A 1AA"


class TestV23BooleanNormalizer:
    """BooleanNormalizer: yes/no/true/false/1/0 → Python bool."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("yes", True),
            ("YES", True),
            ("true", True),
            ("True", True),
            ("1", True),
            ("on", True),
            ("no", False),
            ("NO", False),
            ("false", False),
            ("False", False),
            ("0", False),
            ("off", False),
        ],
    )
    def test_boolean_values(self, raw: str, expected: bool) -> None:
        from rolodexter.core import BooleanNormalizer

        n = BooleanNormalizer()
        assert n.normalize(raw) is expected

    def test_unrecognized_passthrough(self) -> None:
        from rolodexter.core import BooleanNormalizer

        n = BooleanNormalizer()
        assert n.normalize("maybe") == "maybe"
        assert n.normalize("") == ""


# ═══════════════════════════════════════════════════════════════
#  v2.5 — COVERAGE BOOST: core.py GAPS
# ═══════════════════════════════════════════════════════════════


class TestNameNormalizerParse:
    """Test NameNormalizer.parse() structured output."""

    def test_simple_name(self) -> None:
        result = NameNormalizer.parse("John Smith")
        assert result["first"] == "John"
        assert result["last"] == "Smith"

    def test_with_title_and_suffix(self) -> None:
        result = NameNormalizer.parse("Dr. Jane Doe Jr.")
        assert result["title"] == "Dr."
        assert result["first"] == "Jane"
        assert result["last"] == "Doe"
        assert result["suffix"] == "Jr."

    def test_with_middle_name(self) -> None:
        result = NameNormalizer.parse("John Fitzgerald Kennedy")
        assert result["first"] == "John"
        assert result["middle"] == "Fitzgerald"
        assert result["last"] == "Kennedy"

    def test_returns_all_keys(self) -> None:
        result = NameNormalizer.parse("Alice")
        expected_keys = {"title", "first", "middle", "last", "suffix", "nickname"}
        assert set(result.keys()) == expected_keys


class TestNameNormalizerEdge:
    """Edge cases for NameNormalizer.normalize()."""

    def test_none_returns_none(self) -> None:
        assert NameNormalizer.normalize(None) is None  # type: ignore[arg-type]

    def test_empty_returns_empty(self) -> None:
        assert NameNormalizer.normalize("") == ""

    def test_non_string_passthrough(self) -> None:
        assert NameNormalizer.normalize(42) == 42  # type: ignore[arg-type]

    def test_whitespace_only(self) -> None:
        assert NameNormalizer.normalize("   ") == "   "


class TestPostalCodeNormalizerEdge:
    """Edge cases for PostalCodeNormalizer."""

    def test_none_returns_none(self) -> None:
        from rolodexter.core import PostalCodeNormalizer

        assert PostalCodeNormalizer.normalize(None) is None  # type: ignore[arg-type]

    def test_empty_returns_empty(self) -> None:
        from rolodexter.core import PostalCodeNormalizer

        assert PostalCodeNormalizer.normalize("") == ""

    def test_non_string_passthrough(self) -> None:
        from rolodexter.core import PostalCodeNormalizer

        assert PostalCodeNormalizer.normalize(123) == 123  # type: ignore[arg-type]


class TestBooleanNormalizerEdge:
    """Edge cases for BooleanNormalizer."""

    def test_non_string_passthrough(self) -> None:
        from rolodexter.core import BooleanNormalizer

        assert BooleanNormalizer.normalize(42) == 42  # type: ignore[arg-type]

    def test_unknown_string_passthrough(self) -> None:
        from rolodexter.core import BooleanNormalizer

        assert BooleanNormalizer.normalize(" maybe ") == "maybe"


# ═══════════════════════════════════════════════════════════════
#  v2.6.0 — LIST-AWARE TAGS NORMALIZER
# ═══════════════════════════════════════════════════════════════


class TestListNormalizer:
    """Test ListNormalizer for tags and list-like values."""

    def test_comma_separated(self) -> None:
        from rolodexter.core import ListNormalizer

        assert ListNormalizer.normalize("marketing, sales, vip") == [
            "marketing",
            "sales",
            "vip",
        ]

    def test_semicolon_separated(self) -> None:
        from rolodexter.core import ListNormalizer

        assert ListNormalizer.normalize("a; b; c") == ["a", "b", "c"]

    def test_json_array(self) -> None:
        from rolodexter.core import ListNormalizer

        assert ListNormalizer.normalize('["hot", "lead"]') == ["hot", "lead"]

    def test_single_value(self) -> None:
        from rolodexter.core import ListNormalizer

        assert ListNormalizer.normalize("vip") == ["vip"]

    def test_python_list_passthrough(self) -> None:
        from rolodexter.core import ListNormalizer

        assert ListNormalizer.normalize(["a", "b"]) == ["a", "b"]

    def test_empty_string_passthrough(self) -> None:
        from rolodexter.core import ListNormalizer

        assert ListNormalizer.normalize("") == ""

    def test_non_string_passthrough(self) -> None:
        from rolodexter.core import ListNormalizer

        assert ListNormalizer.normalize(42) == 42

    def test_whitespace_trimmed(self) -> None:
        from rolodexter.core import ListNormalizer

        assert ListNormalizer.normalize("  a ,  b  , c  ") == ["a", "b", "c"]

    def test_empty_items_filtered(self) -> None:
        from rolodexter.core import ListNormalizer

        assert ListNormalizer.normalize("a,,b,  ,c") == ["a", "b", "c"]

    def test_json_array_with_numbers(self) -> None:
        from rolodexter.core import ListNormalizer

        assert ListNormalizer.normalize("[1, 2, 3]") == ["1", "2", "3"]

    def test_list_with_empty_strings_filtered(self) -> None:
        from rolodexter.core import ListNormalizer

        assert ListNormalizer.normalize(["a", "", "  ", "b"]) == ["a", "b"]

    def test_tags_in_map_payload(self) -> None:
        """Tags come through as a list in map_payload result."""
        mapper = ContactMapper()
        result = mapper.map_payload({"tags": "marketing, sales"})
        assert result.normalized["tags"] == ["marketing", "sales"]

    def test_tags_json_array_in_payload(self) -> None:
        mapper = ContactMapper()
        result = mapper.map_payload({"tags": '["hot", "lead"]'})
        assert result.normalized["tags"] == ["hot", "lead"]

    def test_tags_already_list(self) -> None:
        mapper = ContactMapper()
        result = mapper.map_payload({"tags": ["a", "b", "c"]})
        assert result.normalized["tags"] == ["a", "b", "c"]

    def test_tags_list_items_cleaned_in_map_payload(self) -> None:
        mapper = ContactMapper()
        result = mapper.map_payload({"tags": [" vip ", "", "  ", "beta"]})
        assert result.normalized["tags"] == ["vip", "beta"]

    def test_duplicate_tag_aliases_merge_flat_and_dedupe(self) -> None:
        mapper = ContactMapper()
        result = mapper.map_payload(
            {"tags": "vip,beta", "contact": {"tag": "vip,gamma"}},
            depth=2,
        )
        assert result.normalized["tags"] == ["vip", "beta", "gamma"]


# ═══════════════════════════════════════════════════════════════
#  v2.7.0 — AUDIT FIXES
# ═══════════════════════════════════════════════════════════════


class TestAddressSmartCasing:
    """AddressNormalizer no longer mangles real-world tokens (was str.title())."""

    def test_existing_behaviour_preserved(self) -> None:
        assert AddressNormalizer.normalize("  123  main   st  ") == "123 Main St"
        assert normalize_value("city", "  new york  ") == "New York"

    def test_mc_names(self) -> None:
        assert AddressNormalizer.normalize("123 MCDONALD ST") == "123 McDonald St"
        assert AddressNormalizer.normalize("mcdonald") == "McDonald"

    def test_ordinals_preserved(self) -> None:
        assert AddressNormalizer.normalize("5TH AVENUE") == "5th Avenue"
        assert AddressNormalizer.normalize("21st street") == "21st Street"
        assert AddressNormalizer.normalize("2ND FLOOR") == "2nd Floor"

    def test_internal_mixed_case_preserved(self) -> None:
        # Already-correct tokens must not be flattened.
        assert AddressNormalizer.normalize("123 iPhone Way") == "123 iPhone Way"

    def test_apostrophes(self) -> None:
        # Proper noun: capitalize the long trailing segment.
        assert AddressNormalizer.normalize("O'BRIEN ROAD") == "O'Brien Road"
        # Possessive: do NOT capitalize a single trailing letter (no "Macy'S").
        assert AddressNormalizer.normalize("macy's plaza") == "Macy's Plaza"

    def test_empty_passthrough(self) -> None:
        assert AddressNormalizer.normalize("") == ""
        assert AddressNormalizer.normalize("   ") == "   "


# ═══════════════════════════════════════════════════════════════
#  v2.7.0 — REGION-AWARE VALUE NORMALIZATION (E.164 through map_payload)
# ═══════════════════════════════════════════════════════════════


class TestRegionAwareNormalization:
    """``default_region`` must reach the value-normalization layer, not just
    header matching — otherwise national-format phones silently stay raw."""

    def test_national_number_normalizes_to_e164_via_map_payload(self) -> None:
        mapper = ContactMapper()  # default_region="US"
        result = mapper.map_payload({"Mobile Phone": "(202) 555-0143"})
        assert result.normalized["phone"] == "+12025550143"

    def test_normalize_value_honours_region(self) -> None:
        assert normalize_value("phone", "(202) 555-0143", default_region="US") == (
            "+12025550143"
        )

    def test_normalize_value_without_region_is_passthrough(self) -> None:
        # No region and no '+' prefix → libphonenumber can't resolve it, so the
        # original value is preserved (non-destructive).
        assert normalize_value("phone", "(202) 555-0143") == "(202) 555-0143"

    def test_per_call_region_override(self) -> None:
        mapper = ContactMapper(default_region=None)
        result = mapper.map_payload({"mobile": "020 7946 0958"}, default_region="GB")
        assert result.normalized["phone"] == "+442079460958"

    def test_batch_region_normalizes_values(self) -> None:
        mapper = ContactMapper(default_region="US")
        rows = [{"Mobile Phone": "(202) 555-0143"} for _ in range(5)]
        results = mapper.map_batch(rows)
        assert all(r.normalized["phone"] == "+12025550143" for r in results)
