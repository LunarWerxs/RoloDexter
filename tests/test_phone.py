"""Phone normalization and phone extraction from payloads.

Extracted verbatim from ``test_rolodexter.py``.
"""

from __future__ import annotations

import pytest

from rolodexter import (
    ContactMapper,
    MappingResult,
)
from rolodexter.core import (
    PhoneNormalizer,
    normalize_value,
)

# ═══════════════════════════════════════════════════════════════
#  NORMALIZER TESTS
# ═══════════════════════════════════════════════════════════════


class TestPhoneNormalizer:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("+1-555-123-4567", "+15551234567"),
            ("+44 20 7946 0958", "+442079460958"),
            ("", ""),
            ("   ", "   "),
        ],
    )
    def test_normalize(self, raw: str, expected: str) -> None:
        assert PhoneNormalizer.normalize(raw) == expected

    def test_us_local_with_region(self) -> None:
        """US local numbers need default_region='US' for correct E.164."""
        result = PhoneNormalizer.normalize("(555) 123-4567", default_region="US")
        assert result == "+15551234567"

    def test_us_dots_with_region(self) -> None:
        result = PhoneNormalizer.normalize("555.123.4567", default_region="US")
        assert result == "+15551234567"

    def test_none_passthrough(self) -> None:
        assert PhoneNormalizer.normalize(None) is None  # type: ignore[arg-type]

    def test_non_string(self) -> None:
        assert PhoneNormalizer.normalize(12345) == 12345  # type: ignore[arg-type]


class TestPhoneNormalizerE164:
    """Test PhoneNormalizer.normalize() uses built-in E.164 module."""

    def test_us_number(self) -> None:
        result = PhoneNormalizer.normalize("+1 (555) 123-4567")
        assert result == "+15551234567"

    def test_uk_number(self) -> None:
        result = PhoneNormalizer.normalize("+44 20 7946 0958")
        assert result == "+442079460958"

    def test_japan_number(self) -> None:
        result = PhoneNormalizer.normalize("+81 3-1234-5678")
        assert result == "+81312345678"

    def test_default_region_au(self) -> None:
        result = PhoneNormalizer.normalize("(02) 1234 5678", default_region="AU")
        assert result.startswith("+61")

    def test_default_region_gb(self) -> None:
        result = PhoneNormalizer.normalize("020 7946 0958", default_region="GB")
        assert result == "+442079460958"

    def test_empty_returns_as_is(self) -> None:
        assert PhoneNormalizer.normalize("") == ""

    def test_none_returns_none(self) -> None:
        assert PhoneNormalizer.normalize(None) is None  # type: ignore[arg-type]

    def test_non_string_returns_as_is(self) -> None:
        assert PhoneNormalizer.normalize(12345) == 12345  # type: ignore[arg-type]

    def test_garbage_returns_original(self) -> None:
        assert PhoneNormalizer.normalize("no phone here") == "no phone here"

    def test_too_short_returns_original(self) -> None:
        assert PhoneNormalizer.normalize("123") == "123"

    def test_whitespace_only_returns_original(self) -> None:
        assert PhoneNormalizer.normalize("   ") == "   "

    def test_double_zero_international(self) -> None:
        result = PhoneNormalizer.normalize("0044 20 7946 0958")
        assert result == "+442079460958"

    def test_vanity_number(self) -> None:
        result = PhoneNormalizer.normalize("+1-800-FLOWERS")
        assert result == "+18003569377"

    def test_india_number(self) -> None:
        result = PhoneNormalizer.normalize("+91 98765 43210")
        assert result == "+919876543210"

    def test_china_number(self) -> None:
        result = PhoneNormalizer.normalize("+86 138 0013 8000")
        assert result == "+8613800138000"

    def test_unparseable_number_is_returned_unchanged(self) -> None:
        """An unparseable number is passed through, never silently mangled.

        The manual regex fallback this used to describe was removed in 2.5.0;
        ``isinstance(result, str)`` was vacuous, since the input is a str and
        every branch returns one.  Pin the behavior that actually matters.
        """
        raw = "+999 000 000 0000"
        assert PhoneNormalizer.normalize(raw) == raw

    def test_normalize_value_uses_e164(self) -> None:
        """normalize_value() for phone fields uses E.164 formatting."""
        result = normalize_value("phone", "+44 20 7946 0958")
        assert result == "+442079460958"


# ═══════════════════════════════════════════════════════════════
#  v2.6.0 — EMBEDDED PHONE EXTRACTION
# ═══════════════════════════════════════════════════════════════


class TestEmbeddedPhoneExtraction:
    """Test extract_embedded_phones flag on map_payload."""

    def test_phone_in_notes_extracted(self) -> None:
        mapper = ContactMapper()
        result = mapper.map_payload(
            {"notes": "reach me at +1-650-253-0000"},
            extract_embedded_phones=True,
        )
        assert "phone" in result.normalized
        phones = result.normalized["phone"]
        if isinstance(phones, list):
            assert any("+16502530000" in p for p in phones)
        else:
            assert "+16502530000" in phones

    def test_phone_in_unmapped_field(self) -> None:
        mapper = ContactMapper()
        result = mapper.map_payload(
            {"favorite_color": "blue", "random_field": "call +44 20 7946 0958 anytime"},
            extract_embedded_phones=True,
        )
        assert "phone" in result.normalized

    def test_disabled_by_default(self) -> None:
        mapper = ContactMapper()
        result = mapper.map_payload({"weird_field": "reach me at +1-650-253-0000"})
        # Without extract_embedded_phones, phone should NOT appear
        assert "phone" not in result.normalized

    def test_no_false_positives_short_strings(self) -> None:
        mapper = ContactMapper()
        result = mapper.map_payload(
            {"code": "ABC"},
            extract_embedded_phones=True,
        )
        # Short strings should not trigger extraction
        assert "phone" not in result.normalized

    def test_existing_phone_field_plus_embedded(self) -> None:
        mapper = ContactMapper()
        result = mapper.map_payload(
            {"phone": "+1-212-456-7890", "notes": "also try +1-650-253-0000"},
            extract_embedded_phones=True,
        )
        phones = result.normalized.get("phone")
        # Should have both numbers
        if isinstance(phones, list):
            assert len(phones) >= 2
        else:
            # At minimum the mapped phone is there
            assert phones is not None

    def test_embedded_match_has_strategy_name(self) -> None:
        mapper = ContactMapper()
        result = mapper.map_payload(
            {"notes": "reach me at +1-650-253-0000"},
            extract_embedded_phones=True,
        )
        strategies = [m.strategy for m in result.field_matches]
        assert "embedded_phone" in strategies

    def test_long_embedded_phone_text_is_truncated_with_warning(self) -> None:
        mapper = ContactMapper()
        long_notes = "x" * 9000 + " call +1-650-253-0000"
        result = mapper.map_payload(
            {"notes": long_notes},
            extract_embedded_phones=True,
        )
        assert "phone" not in result.normalized
        assert any("truncated" in warning for warning in result.warnings)

    def test_embedded_phone_field_match_limit_warns(self) -> None:
        mapper = ContactMapper()
        many_numbers = " ".join("+1 202 555 1234" for _ in range(7))
        result = mapper.map_payload(
            {"notes": many_numbers},
            extract_embedded_phones=True,
        )
        embedded_matches = [
            match
            for match in result.field_matches
            if match.strategy == "embedded_phone"
        ]
        assert len(embedded_matches) == 5
        assert any("for this field" in warning for warning in result.warnings)

    def test_embedded_phone_payload_match_limit_warns(self) -> None:
        mapper = ContactMapper()
        many_numbers = " ".join("+1 202 555 1234" for _ in range(5))
        payload = {f"blob_{idx}": many_numbers for idx in range(5)}
        result = mapper.map_payload(payload, extract_embedded_phones=True)
        embedded_matches = [
            match
            for match in result.field_matches
            if match.strategy == "embedded_phone"
        ]
        assert len(embedded_matches) == 20
        assert any("for this payload" in warning for warning in result.warnings)


# ═══════════════════════════════════════════════════════════════
#  v2.6.0 — get_all_phones() HELPER
# ═══════════════════════════════════════════════════════════════


class TestGetAllPhones:
    """Test MappingResult.get_all_phones() aggregation."""

    def test_basic_single_phone(self) -> None:
        mapper = ContactMapper()
        result = mapper.map_payload({"phone": "+1-555-000-1234"})
        phones = result.get_all_phones()
        assert len(phones) >= 1
        assert "+15550001234" in phones

    def test_multiple_phone_fields(self) -> None:
        mapper = ContactMapper()
        result = mapper.map_payload(
            {
                "phone": "+1-555-000-1111",
                "home_phone": "+1-555-000-2222",
                "work_phone": "+1-555-000-3333",
                "fax": "+1-555-000-4444",
            }
        )
        phones = result.get_all_phones()
        assert len(phones) == 4
        assert "+15550001111" in phones
        assert "+15550002222" in phones
        assert "+15550003333" in phones
        assert "+15550004444" in phones

    def test_deduplication(self) -> None:
        """Same number in multiple fields appears once."""
        result = MappingResult(
            normalized={"phone": "+15550001234", "home_phone": "+15550001234"},
            unmapped={},
            field_matches=(),
        )
        phones = result.get_all_phones()
        assert phones == ["+15550001234"]

    def test_empty_normalized(self) -> None:
        result = MappingResult(normalized={}, unmapped={}, field_matches=())
        assert result.get_all_phones() == []

    def test_list_values_flattened(self) -> None:
        """Phone collision (list) is properly flattened."""
        result = MappingResult(
            normalized={"phone": ["+15550001111", "+15550002222"]},
            unmapped={},
            field_matches=(),
        )
        phones = result.get_all_phones()
        assert "+15550001111" in phones
        assert "+15550002222" in phones

    def test_whatsapp_included(self) -> None:
        result = MappingResult(
            normalized={"whatsapp": "+15550009999"},
            unmapped={},
            field_matches=(),
        )
        assert "+15550009999" in result.get_all_phones()
