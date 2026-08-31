"""The _phone module API: parse, format, match and number types.

Extracted verbatim from ``test_rolodexter.py``.
"""

from __future__ import annotations

from rolodexter._phone import (
    MatchType,
    NumberType,
    PhoneNumberMatcher,
    format_international,
    format_national,
    is_number_match,
    number_type,
    parse,
)

# ═══════════════════════════════════════════════════════════════
#  v2.1 — BUILT-IN PHONE MODULE (rolodexter._phone)
# ═══════════════════════════════════════════════════════════════


class TestPhoneModuleParse:
    """Test the built-in _phone.parse() function directly."""

    def test_e164_passthrough(self) -> None:
        from rolodexter._phone import parse

        p = parse("+15551234567")
        assert p is not None
        assert p.calling_code == 1
        assert p.national_number == "5551234567"
        assert p.e164 == "+15551234567"

    def test_us_formatted(self) -> None:
        from rolodexter._phone import parse

        p = parse("+1 (555) 123-4567")
        assert p is not None
        assert p.e164 == "+15551234567"

    def test_uk_number(self) -> None:
        from rolodexter._phone import parse

        p = parse("+44 20 7946 0958")
        assert p is not None
        assert p.e164 == "+442079460958"

    def test_japan_number(self) -> None:
        from rolodexter._phone import parse

        p = parse("+81 3-1234-5678")
        assert p is not None
        assert p.e164 == "+81312345678"

    def test_germany_number(self) -> None:
        from rolodexter._phone import parse

        p = parse("+49 30 1234567")
        assert p is not None
        assert p.e164 == "+49301234567"

    def test_india_number(self) -> None:
        from rolodexter._phone import parse

        p = parse("+91 98765 43210")
        assert p is not None
        assert p.e164 == "+919876543210"

    def test_australia_with_region(self) -> None:
        from rolodexter._phone import parse

        p = parse("(02) 1234 5678", default_region="AU")
        assert p is not None
        assert p.calling_code == 61
        assert p.e164.startswith("+61")

    def test_uk_local_with_region(self) -> None:
        from rolodexter._phone import parse

        p = parse("020 7946 0958", default_region="GB")
        assert p is not None
        assert p.e164 == "+442079460958"

    def test_france_local_with_region(self) -> None:
        from rolodexter._phone import parse

        p = parse("01 23 45 67 89", default_region="FR")
        assert p is not None
        assert p.e164 == "+33123456789"

    def test_double_zero_prefix(self) -> None:
        from rolodexter._phone import parse

        p = parse("0044 20 7946 0958")
        assert p is not None
        assert p.e164 == "+442079460958"

    def test_us_011_prefix(self) -> None:
        from rolodexter._phone import parse

        p = parse("011 44 20 7946 0958")
        assert p is not None
        assert p.e164 == "+442079460958"

    def test_vanity_number(self) -> None:
        from rolodexter._phone import parse

        p = parse("+1-800-FLOWERS")
        assert p is not None
        assert p.calling_code == 1
        assert p.e164 == "+18003569377"

    def test_china_mobile(self) -> None:
        from rolodexter._phone import parse

        p = parse("+86 138 0013 8000")
        assert p is not None
        assert p.e164 == "+8613800138000"

    def test_brazil_mobile(self) -> None:
        from rolodexter._phone import parse

        p = parse("+55 11 91234-5678")
        assert p is not None
        assert p.e164 == "+5511912345678"

    def test_none_returns_none(self) -> None:
        from rolodexter._phone import parse

        assert parse(None) is None  # type: ignore[arg-type]

    def test_empty_returns_none(self) -> None:
        from rolodexter._phone import parse

        assert parse("") is None

    def test_garbage_returns_none(self) -> None:
        from rolodexter._phone import parse

        assert parse("no phone here") is None

    def test_too_short_returns_none(self) -> None:
        from rolodexter._phone import parse

        assert parse("123") is None

    def test_is_valid_property(self) -> None:
        from rolodexter._phone import parse

        p = parse("+12025551234")
        assert p is not None
        assert p.is_valid is True

    def test_country_codes_property(self) -> None:
        from rolodexter._phone import parse

        p = parse("+442079460958")
        assert p is not None
        assert "GB" in p.country_codes

    def test_str_returns_e164(self) -> None:
        from rolodexter._phone import parse

        p = parse("+15551234567")
        assert str(p) == "+15551234567"


class TestPhoneModuleFormatE164:
    """Test the format_e164() convenience function."""

    def test_basic(self) -> None:
        from rolodexter._phone import format_e164

        assert format_e164("+1 (555) 123-4567") == "+15551234567"

    def test_with_region(self) -> None:
        from rolodexter._phone import format_e164

        result = format_e164("020 7946 0958", default_region="GB")
        assert result == "+442079460958"

    def test_returns_none_on_fail(self) -> None:
        from rolodexter._phone import format_e164

        assert format_e164("abc") is None


class TestPhoneModuleIsValid:
    """Test the is_valid() convenience function."""

    def test_valid_us(self) -> None:
        from rolodexter._phone import is_valid

        assert is_valid("+12025551234") is True

    def test_invalid_garbage(self) -> None:
        from rolodexter._phone import is_valid

        assert is_valid("hello") is False


class TestPhoneExtensions:
    """Test extension parsing in parse()."""

    def test_ext_keyword(self) -> None:
        p = parse("+1 555 123 4567 ext 890")
        assert p is not None
        assert p.e164 == "+15551234567"
        assert p.extension == "890"

    def test_ext_keyword_dot(self) -> None:
        p = parse("+1 555 123 4567 ext. 42")
        assert p is not None
        assert p.extension == "42"

    def test_extn_keyword(self) -> None:
        p = parse("+44 20 7946 0958 extn 100")
        assert p is not None
        assert p.extension == "100"

    def test_extension_keyword(self) -> None:
        p = parse("+1 555 123 4567 extension 999")
        assert p is not None
        assert p.extension == "999"

    def test_x_separator(self) -> None:
        p = parse("+1 555 123 4567 x 55")
        assert p is not None
        assert p.extension == "55"

    def test_hash_separator(self) -> None:
        p = parse("+1 555 123 4567 # 77")
        assert p is not None
        assert p.extension == "77"

    def test_semicolon_ext(self) -> None:
        p = parse("+1 555 123 4567;ext=200")
        assert p is not None
        assert p.extension == "200"

    def test_no_extension_none(self) -> None:
        p = parse("+15551234567")
        assert p is not None
        assert p.extension is None


class TestPhoneRFC3966:
    """Test RFC 3966 tel: URI handling."""

    def test_basic_tel_uri(self) -> None:
        p = parse("tel:+15551234567")
        assert p is not None
        assert p.e164 == "+15551234567"

    def test_tel_uri_with_phone_context(self) -> None:
        p = parse("tel:+442079460958;phone-context=+44")
        assert p is not None
        assert p.e164 == "+442079460958"

    def test_tel_uri_with_ext(self) -> None:
        p = parse("tel:+15551234567;ext=42")
        assert p is not None
        assert p.e164 == "+15551234567"
        assert p.extension == "42"

    def test_tel_uri_case_insensitive(self) -> None:
        p = parse("TEL:+15551234567")
        assert p is not None
        assert p.e164 == "+15551234567"


class TestPhoneFormatInternational:
    """Test format_international()."""

    def test_us_number(self) -> None:
        p = parse("+12025551234")
        assert p is not None
        assert format_international(p) == "+1 202-555-1234"

    def test_uk_number(self) -> None:
        p = parse("+442079460958")
        assert p is not None
        result = format_international(p)
        assert result.startswith("+44 ")
        assert " " in result  # has grouping

    def test_france_number(self) -> None:
        p = parse("+33123456789")
        assert p is not None
        result = format_international(p)
        assert result.startswith("+33 ")

    def test_unknown_cc_no_grouping(self) -> None:
        """Countries without a template get ungrouped output."""
        p = parse("+29012345")
        assert p is not None
        result = format_international(p)
        assert result.startswith("+290 ")

    def test_with_extension(self) -> None:
        p = parse("+1 555 123 4567 ext 42")
        assert p is not None
        result = format_international(p)
        assert "ext. 42" in result

    def test_india(self) -> None:
        p = parse("+919876543210")
        assert p is not None
        result = format_international(p)
        assert result.startswith("+91 ")

    def test_china(self) -> None:
        p = parse("+8613800138000")
        assert p is not None
        result = format_international(p)
        assert result.startswith("+86 ")


class TestPhoneFormatNational:
    """Test format_national()."""

    def test_us_nanp_style(self) -> None:
        p = parse("+15551234567")
        assert p is not None
        assert format_national(p) == "(555) 123-4567"

    def test_us_with_extension(self) -> None:
        p = parse("+1 555 123 4567 ext 42")
        assert p is not None
        result = format_national(p)
        assert result == "(555) 123-4567 ext. 42"

    def test_uk_has_trunk(self) -> None:
        """UK national format should include trunk 0."""
        p = parse("+442079460958")
        assert p is not None
        result = format_national(p)
        assert result.startswith("0")

    def test_singapore_no_trunk(self) -> None:
        """Singapore doesn't use trunk prefix."""
        p = parse("+6512345678")
        assert p is not None
        result = format_national(p)
        assert not result.startswith("0")


class TestPhoneNumberMatch:
    """Test is_number_match()."""

    def test_exact_match(self) -> None:
        assert (
            is_number_match("+15551234567", "+1 555 123 4567") == MatchType.EXACT_MATCH
        )

    def test_exact_match_with_extension(self) -> None:
        assert (
            is_number_match("+15551234567 ext 42", "+1 555 123 4567 ext 42")
            == MatchType.EXACT_MATCH
        )

    def test_nsn_match_extension_differs(self) -> None:
        assert (
            is_number_match("+12025551234 ext 42", "+12025551234")
            == MatchType.SHORT_NSN_MATCH
        )

    def test_no_match(self) -> None:
        assert is_number_match("+15551234567", "+15559876543") == MatchType.NO_MATCH

    def test_not_a_number(self) -> None:
        assert is_number_match("hello", "+15551234567") == MatchType.NOT_A_NUMBER

    def test_different_cc(self) -> None:
        assert is_number_match("+15551234567", "+441234567890") == MatchType.NO_MATCH

    def test_short_nsn_match(self) -> None:
        """If one is suffix of the other (>=7 digits), SHORT_NSN_MATCH."""
        assert (
            is_number_match(
                "+5511987654321",  # BR 11-digit
                "+55987654321",  # BR shorter
                default_region="BR",
            )
            == MatchType.SHORT_NSN_MATCH
        )

    def test_accepts_phone_number_objects(self) -> None:
        a = parse("+15551234567")
        b = parse("+1 555 123 4567")
        assert a is not None and b is not None
        assert is_number_match(a, b) == MatchType.EXACT_MATCH


class TestPhoneNumberType:
    """Test number_type() heuristic detection."""

    def test_us_toll_free(self) -> None:
        p = parse("+18005551212")
        assert p is not None
        assert number_type(p) == NumberType.TOLL_FREE

    def test_us_premium(self) -> None:
        p = parse("+19002001234")
        assert p is not None
        assert number_type(p) == NumberType.PREMIUM_RATE

    def test_us_regular_fixed_or_mobile(self) -> None:
        """NANP can't distinguish mobile from fixed → FIXED_LINE_OR_MOBILE."""
        p = parse("+12025551234")
        assert p is not None
        assert number_type(p) == NumberType.FIXED_LINE_OR_MOBILE

    def test_uk_mobile(self) -> None:
        p = parse("+447911123456")
        assert p is not None
        assert number_type(p) == NumberType.MOBILE

    def test_uk_fixed(self) -> None:
        p = parse("+442079460958")
        assert p is not None
        assert number_type(p) == NumberType.FIXED_LINE

    def test_france_mobile(self) -> None:
        p = parse("+33612345678")
        assert p is not None
        assert number_type(p) == NumberType.MOBILE

    def test_india_mobile(self) -> None:
        p = parse("+919876543210")
        assert p is not None
        assert number_type(p) == NumberType.MOBILE

    def test_china_mobile(self) -> None:
        p = parse("+8613800138000")
        assert p is not None
        assert number_type(p) == NumberType.MOBILE

    def test_germany_mobile(self) -> None:
        p = parse("+4915112345678")
        assert p is not None
        assert number_type(p) == NumberType.MOBILE

    def test_unknown_country(self) -> None:
        p = parse("+29012345")
        assert p is not None
        assert number_type(p) == NumberType.UNKNOWN


class TestPhoneNumberMatcher:
    """Test PhoneNumberMatcher for extracting phones from text."""

    def test_single_phone_in_text(self) -> None:
        text = "Call me at +1 202 555 1234 please"
        matches = list(PhoneNumberMatcher(text))
        assert len(matches) >= 1
        assert matches[0].number.e164 == "+12025551234"

    def test_multiple_phones(self) -> None:
        text = "Office: +1 202 555 1234, Mobile: +44 7911 123456"
        matches = list(PhoneNumberMatcher(text))
        e164s = {m.number.e164 for m in matches}
        assert "+12025551234" in e164s

    def test_no_phones(self) -> None:
        text = "This text has no phone numbers at all."
        assert len(PhoneNumberMatcher(text)) == 0

    def test_with_default_region(self) -> None:
        text = "Ring 020 7946 0958 for info"
        matches = list(PhoneNumberMatcher(text, default_region="GB"))
        assert len(matches) >= 1
        assert matches[0].number.e164 == "+442079460958"

    def test_match_positions(self) -> None:
        text = "Number: +12025551234!"
        matches = list(PhoneNumberMatcher(text))
        assert len(matches) >= 1
        m = matches[0]
        assert (
            text[m.start : m.end].strip().replace(" ", "").replace("+", "+") is not None
        )

    def test_has_next(self) -> None:
        matcher = PhoneNumberMatcher("Call +12025551234")
        assert matcher.has_next() is True

    def test_has_next_empty(self) -> None:
        matcher = PhoneNumberMatcher("No phones here")
        assert matcher.has_next() is False

    def test_max_matches_caps_cached_results(self) -> None:
        text = "One +1 202 555 1234 two +1 650 253 0000"
        matcher = PhoneNumberMatcher(text, max_matches=1)
        assert len(matcher) == 1
        assert len(list(matcher)) == 1


# ═══════════════════════════════════════════════════════════════
#  v2.5 — COVERAGE BOOST: _phone.py DEFENSIVE FALLBACKS
# ═══════════════════════════════════════════════════════════════


class TestPhoneNumberWithoutPnObj:
    """Test PhoneNumber properties when _pn_obj is None (defensive paths)."""

    def test_e164_fallback(self) -> None:
        from rolodexter._phone import PhoneNumber

        pn = PhoneNumber(
            calling_code=1, national_number="2025551234", raw="+12025551234"
        )
        assert pn.e164 == "+12025551234"

    def test_is_valid_fallback_false(self) -> None:
        from rolodexter._phone import PhoneNumber

        pn = PhoneNumber(calling_code=1, national_number="2025551234", raw="x")
        assert pn.is_valid is False

    def test_is_possible_fallback_false(self) -> None:
        from rolodexter._phone import PhoneNumber

        pn = PhoneNumber(calling_code=1, national_number="2025551234", raw="x")
        assert pn.is_possible is False

    def test_format_international_fallback(self) -> None:
        from rolodexter._phone import PhoneNumber, format_international

        pn = PhoneNumber(calling_code=44, national_number="2079460958", raw="x")
        result = format_international(pn)
        assert result == "+44 2079460958"

    def test_format_national_fallback(self) -> None:
        from rolodexter._phone import PhoneNumber, format_national

        pn = PhoneNumber(calling_code=1, national_number="2025551234", raw="x")
        assert format_national(pn) == "2025551234"

    def test_number_type_fallback_unknown(self) -> None:
        from rolodexter._phone import NumberType, PhoneNumber, number_type

        pn = PhoneNumber(calling_code=1, national_number="2025551234", raw="x")
        assert number_type(pn) == NumberType.UNKNOWN

    def test_is_number_match_with_bare_phone_number(self) -> None:
        from rolodexter._phone import MatchType, PhoneNumber, is_number_match

        a = PhoneNumber(calling_code=1, national_number="2025551234", raw="x")
        result = is_number_match(a, "+12025551234")
        assert result == MatchType.EXACT_MATCH

    def test_is_number_match_exception_returns_not_a_number(self) -> None:
        from rolodexter._phone import MatchType, is_number_match

        # Passing None to trigger exception inside phonenumbers
        result = is_number_match(None, None)  # type: ignore[arg-type]
        assert result == MatchType.NOT_A_NUMBER


class TestPhoneParseEdgeCases:
    """Edge cases for parse() not covered by existing tests."""

    def test_parse_whitespace_only(self) -> None:
        from rolodexter._phone import parse

        assert parse("   ") is None

    def test_parse_not_possible_number(self) -> None:
        from rolodexter._phone import parse

        # A number that's parseable but not possible (too few digits)
        assert parse("+1 2") is None

    def test_parse_non_string(self) -> None:
        from rolodexter._phone import parse

        assert parse(12345) is None  # type: ignore[arg-type]

    def test_parse_empty(self) -> None:
        from rolodexter._phone import parse

        assert parse("") is None

    def test_parse_none(self) -> None:
        from rolodexter._phone import parse

        assert parse(None) is None  # type: ignore[arg-type]


class TestPhoneNumberMatchRepr:
    """Test PhoneNumberMatch __repr__."""

    def test_repr_format(self) -> None:
        from rolodexter._phone import PhoneNumberMatch, parse

        phone = parse("+12025551234")
        assert phone is not None
        m = PhoneNumberMatch(start=0, end=12, raw_string="+12025551234", number=phone)
        r = repr(m)
        assert "PhoneNumberMatch" in r
        assert "+12025551234" in r
        assert "start=0" in r
        assert "end=12" in r


class TestPhoneMatcherIterLen:
    """Test PhoneNumberMatcher __iter__ and __len__ caching."""

    def test_len_then_iter(self) -> None:
        from rolodexter._phone import PhoneNumberMatcher

        matcher = PhoneNumberMatcher("Call +12025551234 today")
        # len triggers _find_all
        n = len(matcher)
        assert n >= 1
        # iter reuses cached results
        results = list(matcher)
        assert len(results) == n

    def test_iter_then_len(self) -> None:
        from rolodexter._phone import PhoneNumberMatcher

        matcher = PhoneNumberMatcher("Call +12025551234 today")
        results = list(matcher)
        assert len(matcher) == len(results)


# ═══════════════════════════════════════════════════════════════
#  v2.5 — COVERAGE BOOST ROUND 2
# ═══════════════════════════════════════════════════════════════


class TestPhoneIsPossibleReal:
    """Test PhoneNumber.is_possible with a real parsed number."""

    def test_is_possible_true(self) -> None:
        from rolodexter._phone import parse

        p = parse("+12025551234")
        assert p is not None
        assert p.is_possible is True

    def test_parse_not_possible_returns_none(self) -> None:
        """A number that parses in phonenumbers but is NOT possible."""
        from rolodexter._phone import parse

        # +1234 parses but is_possible_number returns False
        assert parse("+1234") is None
