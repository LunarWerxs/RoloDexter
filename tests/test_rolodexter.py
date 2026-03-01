"""Complete test suite for rolodexter v2.1 — tests in one file."""

from __future__ import annotations

import pytest

from rolodexter import (
    CanonicalField,
    ContactMapper,
    ExactMatchStrategy,
    FuzzyMatchStrategy,
    HeuristicMatchStrategy,
    MappingResult,
    NormalizedMatchStrategy,
    PatternRegistry,
)
from rolodexter.core import (
    AddressNormalizer,
    EmailNormalizer,
    NameNormalizer,
    PatternLoadError,
    PhoneNormalizer,
    StringNormalizer,
    normalize_value,
)

# ═══════════════════════════════════════════════════════════════
#  FIXTURES
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def registry() -> PatternRegistry:
    return PatternRegistry()


@pytest.fixture
def mapper() -> ContactMapper:
    return ContactMapper()


@pytest.fixture
def mapper_no_norm() -> ContactMapper:
    return ContactMapper(normalize=False)


@pytest.fixture
def sample_payload() -> dict:
    return {
        "fname": "jane",
        "surname": "doe",
        "mobile": "+1-555-019-9876",
        "employer": "Tech Corp",
        "designation": "Senior Engineer",
        "Column 1": "jane.doe@example.com",
        "favorite_color": "Blue",
    }


# ═══════════════════════════════════════════════════════════════
#  REGISTRY TESTS
# ═══════════════════════════════════════════════════════════════


class TestLoading:
    def test_default_load(self, registry: PatternRegistry) -> None:
        assert len(registry.all_aliases) > 200
        assert len(registry.canonical_fields) >= 30

    def test_version(self, registry: PatternRegistry) -> None:
        assert registry.version == "2.1.0"

    def test_custom_patterns(self) -> None:
        custom = {
            "fields": {"first_name": ["fname", "given"]},
        }
        reg = PatternRegistry(patterns=custom)
        assert reg.exact_lookup("fname") == "first_name"
        assert reg.exact_lookup("given") == "first_name"

    def test_bad_path_raises(self) -> None:
        with pytest.raises(PatternLoadError):
            PatternRegistry(patterns_path="/nonexistent/path.json")

    def test_repr(self, registry: PatternRegistry) -> None:
        r = repr(registry)
        assert "PatternRegistry" in r
        assert "aliases=" in r


class TestExactLookup:
    @pytest.mark.parametrize(
        "alias, expected",
        [
            ("fname", "first_name"),
            ("given_name", "first_name"),
            ("surname", "last_name"),
            ("lname", "last_name"),
            ("display_name", "full_name"),
            ("email_address", "email"),
            ("telephone", "phone"),
            ("cell", "phone"),
            ("mobile_phone", "phone"),
            ("fax_number", "fax"),
            ("home_tel", "home_phone"),
            ("office_phone", "work_phone"),
            ("whatsapp", "whatsapp"),
            ("organization", "company"),
            ("employer", "company"),
            ("jobtitle", "job_title"),
            ("designation", "job_title"),
            ("dept", "department"),
            ("sector", "industry"),
            ("street", "address_line1"),
            ("apt", "address_line2"),
            ("locality", "city"),
            ("province", "state"),
            ("zipcode", "postal_code"),
            ("countrycode", "country"),
            ("linkedin_url", "linkedin"),
            ("twitter_handle", "twitter"),
            ("ig", "instagram"),
            ("github", "github"),
            ("yt", "youtube"),
            ("tiktok", "tiktok"),
            ("lead_status", "lead_status"),
            ("lifecyclestage", "lifecycle_stage"),
            ("unsubscribed", "email_opt_out"),
            ("tags", "tags"),
            ("lead_source", "source"),
            ("utm", "utm_parameters"),
            ("dob", "birthday"),
            ("signup_date", "created_at"),
            ("last_modified", "updated_at"),
            ("last_activity", "last_contacted"),
            ("memo", "notes"),
            ("annual_revenue", "revenue"),
            ("currency_code", "currency"),
            ("lead_score", "score"),
            ("assigned_to", "owner"),
            ("custom_fields", "metadata"),
        ],
    )
    def test_alias_resolves(self, registry: PatternRegistry, alias: str, expected: str) -> None:
        assert registry.exact_lookup(alias) == expected

    def test_case_insensitive(self, registry: PatternRegistry) -> None:
        assert registry.exact_lookup("FNAME") == "first_name"
        assert registry.exact_lookup("Email_Address") == "email"

    def test_leading_trailing_spaces(self, registry: PatternRegistry) -> None:
        assert registry.exact_lookup("  fname  ") == "first_name"

    def test_unknown_returns_none(self, registry: PatternRegistry) -> None:
        assert registry.exact_lookup("xyzzy_garbage") is None


# ═══════════════════════════════════════════════════════════════
#  STRATEGY TESTS
# ═══════════════════════════════════════════════════════════════


class TestExactMatch:
    def test_known_alias(self, registry: PatternRegistry) -> None:
        strat = ExactMatchStrategy(registry)
        m = strat.match("fname")
        assert m is not None
        assert m.canonical == "first_name"
        assert m.confidence == 1.0
        assert m.strategy == "exact"

    def test_unknown(self, registry: PatternRegistry) -> None:
        strat = ExactMatchStrategy(registry)
        assert strat.match("zzz_garbage") is None


class TestNormalizedMatchStrategy:
    """NormalizedMatchStrategy: smart header normalization → exact lookup."""

    # CamelCase tests
    def test_camel_first_name(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("FirstName")
        assert m is not None and m.canonical == "first_name" and m.confidence == 0.95 and m.strategy == "normalized"

    def test_camel_last_name(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("LastName")
        assert m is not None and m.canonical == "last_name"

    def test_camel_mobile_phone(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("MobilePhone")
        assert m is not None and m.canonical == "phone"

    def test_camel_mailing_street(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("MailingStreet")
        assert m is not None and m.canonical == "address_line1"

    def test_camel_mailing_postal_code(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("MailingPostalCode")
        assert m is not None and m.canonical == "postal_code"

    def test_camel_annual_revenue(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("AnnualRevenue")
        assert m is not None and m.canonical == "revenue"

    def test_camel_created_date(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("CreatedDate")
        assert m is not None and m.canonical == "created_at"

    def test_camel_last_modified_date(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("LastModifiedDate")
        assert m is not None and m.canonical == "updated_at"

    def test_camel_lead_source(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("LeadSource")
        assert m is not None and m.canonical == "source"

    def test_camel_home_phone(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("HomePhone")
        assert m is not None and m.canonical == "home_phone"

    def test_camel_country_code(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("countryCode")
        assert m is not None and m.canonical == "country"

    def test_camel_postal_code(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("postalCode")
        assert m is not None and m.canonical == "postal_code"

    def test_camel_created_at(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("createdAt")
        assert m is not None and m.canonical == "created_at"

    def test_camel_modified_at(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("modifiedAt")
        assert m is not None and m.canonical == "updated_at"

    # Space → underscore tests
    def test_space_first_name(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("First Name")
        assert m is not None and m.canonical == "first_name"

    def test_space_last_name(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("Last Name")
        assert m is not None and m.canonical == "last_name"

    def test_space_middle_name(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("Middle Name")
        assert m is not None and m.canonical == "middle_name"

    def test_space_full_name(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("Full Name")
        assert m is not None and m.canonical == "full_name"

    def test_space_job_title(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("Job Title")
        assert m is not None and m.canonical == "job_title"

    def test_space_email_address(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("Email Address")
        assert m is not None and m.canonical == "email"

    def test_space_last_modified(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("Last Modified")
        assert m is not None and m.canonical == "updated_at"

    # Dot-path tests
    def test_dot_fields_last_name(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("fields.last_name")
        assert m is not None and m.canonical == "last_name"

    def test_dot_fields_company(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("fields.company")
        assert m is not None and m.canonical == "company"

    def test_dot_fields_phone(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("fields.phone")
        assert m is not None and m.canonical == "phone"

    def test_dot_account_name(self, registry: PatternRegistry) -> None:
        """Account.Name → company (context-aware dot-path)."""
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("Account.Name")
        assert m is not None and m.canonical == "company"

    def test_dot_companies_name(self, registry: PatternRegistry) -> None:
        """companies.name → company (context-aware dot-path)."""
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("companies.name")
        assert m is not None and m.canonical == "company"

    def test_dot_company_name(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("company.name")
        assert m is not None and m.canonical == "company"

    # Indexed pattern tests (Google Contacts style)
    def test_indexed_email(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("E-mail 1 - Value")
        assert m is not None and m.canonical == "email"

    def test_indexed_phone(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("Phone 1 - Value")
        assert m is not None and m.canonical == "phone"

    def test_indexed_organization_name(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("Organization 1 - Name")
        assert m is not None and m.canonical == "company"

    def test_indexed_organization_title(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("Organization 1 - Title")
        assert m is not None and m.canonical == "job_title"

    def test_indexed_organization_department(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("Organization 1 - Department")
        assert m is not None and m.canonical == "department"

    def test_indexed_address_street(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("Address 1 - Street")
        assert m is not None and m.canonical == "address_line1"

    def test_indexed_address_city(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("Address 1 - City")
        assert m is not None and m.canonical == "city"

    def test_indexed_address_region(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("Address 1 - Region")
        assert m is not None and m.canonical == "state"

    def test_indexed_address_postal_code(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("Address 1 - Postal Code")
        assert m is not None and m.canonical == "postal_code"

    def test_indexed_address_country(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("Address 1 - Country")
        assert m is not None and m.canonical == "country"

    def test_indexed_website(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("Website 1 - Value")
        assert m is not None and m.canonical == "website"

    # Vendor prefix stripping
    def test_vendor_hs_lead_status(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("hs_lead_status")
        assert m is not None and m.canonical == "lead_status"

    def test_vendor_hubspot_owner_id(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("hubspot_owner_id")
        assert m is not None and m.canonical == "owner"

    # Address prefix stripping
    def test_address_prefix_business_city(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("Business City")
        assert m is not None and m.canonical == "city"

    def test_address_prefix_business_state(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("Business State")
        assert m is not None and m.canonical == "state"

    def test_address_prefix_business_postal_code(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("Business Postal Code")
        assert m is not None and m.canonical == "postal_code"

    def test_address_prefix_business_street(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("Business Street")
        assert m is not None and m.canonical == "address_line1"

    def test_address_prefix_business_country_region(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("Business Country/Region")
        assert m is not None and m.canonical == "country"

    # _id suffix stripping
    def test_owner_id(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("OwnerId")
        assert m is not None and m.canonical == "owner"

    def test_owner_id_lowercase(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("owner_id")
        assert m is not None and m.canonical == "owner"

    # Number stripping
    def test_number_strip_email_2_address(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("E-mail 2 Address")
        assert m is not None and m.canonical == "email"

    def test_number_strip_email_3_address(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("E-mail 3 Address")
        assert m is not None and m.canonical == "email"

    # Hyphen → underscore (W3C tokens)
    def test_hyphen_given_name(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("given-name")
        assert m is not None and m.canonical == "first_name"

    def test_hyphen_family_name(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("family-name")
        assert m is not None and m.canonical == "last_name"

    def test_hyphen_additional_name(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("additional-name")
        assert m is not None and m.canonical == "middle_name"

    def test_hyphen_honorific_prefix(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("honorific-prefix")
        assert m is not None and m.canonical == "prefix"

    def test_hyphen_honorific_suffix(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("honorific-suffix")
        assert m is not None and m.canonical == "suffix"

    def test_hyphen_postal_code(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("postal-code")
        assert m is not None and m.canonical == "postal_code"

    def test_hyphen_country_name(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("country-name")
        assert m is not None and m.canonical == "country"

    def test_no_match_garbage(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        assert strat.match("xyzzy_garbage_nonsense") is None

    # DOUBLE_OPT-IN (Brevo) — hyphen mid-word
    def test_double_opt_in(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("DOUBLE_OPT-IN")
        assert m is not None and m.canonical == "email_opt_out"


class TestFuzzyMatch:
    def test_typo_recovery(self, registry: PatternRegistry) -> None:
        strat = FuzzyMatchStrategy(registry)
        m = strat.match("phne_nmbr")
        if m is not None:
            assert m.canonical == "phone"
            assert m.strategy == "fuzzy"

    def test_close_misspelling(self, registry: PatternRegistry) -> None:
        strat = FuzzyMatchStrategy(registry)
        m = strat.match("first_nam")
        if m is not None:
            assert m.canonical == "first_name"

    def test_garbage_no_match(self, registry: PatternRegistry) -> None:
        strat = FuzzyMatchStrategy(registry)
        m = strat.match("supercalifragilistic")
        assert m is None


class TestHeuristicMatch:
    @pytest.mark.parametrize(
        "value, expected",
        [
            ("jane@example.com", "email"),
            ("JOHN.DOE@CORP.CO.UK", "email"),
            ("+15551234567", "phone"),
            ("555-123-4567", "phone"),
            ("(555) 123-4567", "phone"),
            ("https://example.com", "website"),
            ("www.example.com", "website"),
            ("https://linkedin.com/in/janedoe", "linkedin"),
            ("@janedoe", "twitter"),
            ("90210", "postal_code"),
            ("90210-1234", "postal_code"),
            ("K1A 0B1", "postal_code"),
            ("SW1A 1AA", "postal_code"),
            ("1990-05-15", "birthday"),
            ("05/15/1990", "birthday"),
        ],
    )
    def test_value_shape_detection(self, value: str, expected: str) -> None:
        strat = HeuristicMatchStrategy()
        m = strat.match("Unknown Column", value=value)
        assert m is not None
        assert m.canonical == expected
        assert m.strategy == "heuristic"
        assert m.confidence == 0.60

    def test_none_value(self) -> None:
        strat = HeuristicMatchStrategy()
        assert strat.match("col", value=None) is None

    def test_empty_string(self) -> None:
        strat = HeuristicMatchStrategy()
        assert strat.match("col", value="") is None

    def test_plain_text_no_match(self) -> None:
        strat = HeuristicMatchStrategy()
        assert strat.match("col", value="Just some text") is None


# ═══════════════════════════════════════════════════════════════
#  MAPPER TESTS
# ═══════════════════════════════════════════════════════════════


class TestIdentify:
    def test_exact(self, mapper: ContactMapper) -> None:
        m = mapper.identify("fname")
        assert m.canonical == "first_name"
        assert m.confidence == 1.0
        assert m.strategy == "exact"

    def test_heuristic_fallback(self, mapper: ContactMapper) -> None:
        m = mapper.identify("Column X", value="jane@test.com")
        assert m.canonical == "email"
        assert m.strategy == "heuristic"

    def test_unknown(self, mapper: ContactMapper) -> None:
        m = mapper.identify("zzzz_nonsense_field")
        assert not m.is_matched
        assert m.canonical == "unknown"
        assert m.confidence == 0.0


class TestMapPayload:
    def test_basic(self, mapper: ContactMapper) -> None:
        result = mapper.map_payload({"fname": "Jane", "surname": "Doe", "mobile": "555-0199"})
        assert isinstance(result, MappingResult)
        assert result.normalized["first_name"] == "Jane"
        assert result.normalized["last_name"] == "Doe"
        assert "phone" in result.normalized

    def test_unmapped_fields(self, mapper: ContactMapper) -> None:
        result = mapper.map_payload({"zzz_nonsense": "hello"})
        assert "zzz_nonsense" in result.unmapped
        assert result.unmatched_count == 1

    def test_empty_payload(self, mapper: ContactMapper) -> None:
        result = mapper.map_payload({})
        assert result.normalized == {}
        assert result.unmapped == {}
        assert result.match_rate == 0.0

    def test_none_values(self, mapper: ContactMapper) -> None:
        result = mapper.map_payload({"fname": None})
        assert result.normalized["first_name"] is None

    def test_empty_string_values(self, mapper: ContactMapper) -> None:
        result = mapper.map_payload({"email": ""})
        assert result.normalized["email"] == ""

    def test_collision_creates_list(self, mapper: ContactMapper) -> None:
        result = mapper.map_payload({"mobile": "555-1111", "cell": "555-2222"})
        val = result.normalized.get("phone")
        assert isinstance(val, list)
        assert len(val) == 2

    def test_match_rate(self, mapper: ContactMapper) -> None:
        result = mapper.map_payload({"fname": "Jane", "zzz_qqqq_xxxx_jjj": "???"})
        assert result.match_rate == pytest.approx(0.5)
        assert result.matched_count == 1
        assert result.unmatched_count == 1

    def test_normalization_applied(self, mapper: ContactMapper) -> None:
        result = mapper.map_payload({"email": "  HELLO@Example.COM  "})
        assert result.normalized["email"] == "hello@example.com"

    def test_normalization_disabled(self, mapper_no_norm: ContactMapper) -> None:
        result = mapper_no_norm.map_payload({"email": "  HELLO@Example.COM  "})
        assert result.normalized["email"] == "  HELLO@Example.COM  "


class TestBatch:
    def test_batch_basic(self, mapper: ContactMapper) -> None:
        payloads = [{"fname": "Jane"}, {"fname": "John"}]
        results = mapper.map_batch(payloads)
        assert len(results) == 2
        assert results[0].normalized["first_name"] == "Jane"
        assert results[1].normalized["first_name"] == "John"

    def test_batch_empty(self, mapper: ContactMapper) -> None:
        assert mapper.map_batch([]) == []


class TestMappingResultSerialization:
    def test_to_dict(self, mapper: ContactMapper) -> None:
        result = mapper.map_payload({"fname": "Jane", "xyz": "???"})
        d = result.to_dict()
        assert "normalized" in d
        assert "unmapped" in d
        assert "match_rate" in d
        assert "details" in d
        assert d["matched"] == 1
        assert d["unmatched"] == 1

    def test_get_match(self, mapper: ContactMapper) -> None:
        result = mapper.map_payload({"fname": "Jane"})
        fm = result.get_match("fname")
        assert fm is not None
        assert fm.canonical == "first_name"

    def test_get_match_missing(self, mapper: ContactMapper) -> None:
        result = mapper.map_payload({"fname": "Jane"})
        assert result.get_match("nonexistent") is None


# ═══════════════════════════════════════════════════════════════
#  NORMALIZER TESTS
# ═══════════════════════════════════════════════════════════════


class TestPhoneNormalizer:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("+1-555-123-4567", "+15551234567"),
            ("(555) 123-4567", "5551234567"),
            ("555.123.4567", "5551234567"),
            ("+44 20 7946 0958", "+442079460958"),
            ("15551234567890", "+15551234567890"),
            ("", ""),
            ("   ", "   "),
        ],
    )
    def test_normalize(self, raw: str, expected: str) -> None:
        assert PhoneNormalizer.normalize(raw) == expected

    def test_none_passthrough(self) -> None:
        assert PhoneNormalizer.normalize(None) is None  # type: ignore[arg-type]

    def test_non_string(self) -> None:
        assert PhoneNormalizer.normalize(12345) == 12345  # type: ignore[arg-type]


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
        assert normalize_value("tags", "  vip  ") == "vip"

    def test_non_string_passthrough(self) -> None:
        assert normalize_value("phone", 12345) == 12345
        assert normalize_value("email", None) is None


# ═══════════════════════════════════════════════════════════════
#  NEW ALIASES (v2.0 — promoted from service profiles to fields)
# ═══════════════════════════════════════════════════════════════


class TestNewAliases:
    """Verify aliases that were previously only in service profiles are now in fields."""

    @pytest.mark.parametrize(
        "alias, expected",
        [
            ("custemail", "email"),
            ("user_email", "email"),
            ("e_mail_address", "email"),
            ("mobilephone", "phone"),
            ("custtel", "phone"),
            ("custname", "full_name"),
            ("additional_name", "middle_name"),
            ("honorific_prefix", "prefix"),
            ("honorific_suffix", "suffix"),
            ("orgname", "company"),
            ("organization_name", "company"),
            ("organization_title", "job_title"),
            ("organization_department", "department"),
            ("web_page", "website"),
            ("other_street", "address_line2"),
            ("street_2", "address_line2"),
            ("status", "lead_status"),
            ("createdate", "created_at"),
            ("add_time", "created_at"),
            ("connected_on", "created_at"),
            ("cdate", "created_at"),
            ("lastmodifieddate", "updated_at"),
            ("last_modified_date", "updated_at"),
            ("update_time", "updated_at"),
            ("modified_at", "updated_at"),
            ("udate", "updated_at"),
            ("notes_last_contacted", "last_contacted"),
            ("unsubscribed_from_emails", "email_opt_out"),
            ("double_opt_in", "email_opt_out"),
            ("work_number", "work_phone"),
            ("annualrevenue", "revenue"),
        ],
    )
    def test_new_alias(self, registry: PatternRegistry, alias: str, expected: str) -> None:
        assert registry.exact_lookup(alias) == expected


# ═══════════════════════════════════════════════════════════════
#  INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════


class TestSalesforceIngestion:
    """Salesforce CamelCase headers resolve via normalizer (no service param)."""

    def test_lead(self, mapper: ContactMapper) -> None:
        payload = {
            "FirstName": "Akiko",
            "LastName": "Tanaka",
            "Email": "AKIKO@example.jp",
            "Phone": "+81-3-1234-5678",
            "Company": "Tokyo Tech",
            "Title": "CTO",
            "MailingCity": "tokyo",
            "MailingCountry": "JP",
            "LeadSource": "Website",
            "Industry": "Technology",
        }
        result = mapper.map_payload(payload)
        assert result.normalized["first_name"] == "Akiko"
        assert result.normalized["last_name"] == "Tanaka"
        assert result.normalized["email"] == "akiko@example.jp"
        assert result.normalized["company"] == "Tokyo Tech"
        assert result.normalized["job_title"] == "CTO"
        assert result.normalized["source"] == "Website"


class TestGoogleContactsCSV:
    def test_csv_row(self, mapper: ContactMapper) -> None:
        payload = {
            "Given Name": "Carlos",
            "Family Name": "Rivera",
            "E-mail 1 - Value": "CARLOS@MAIL.COM",
            "Phone 1 - Value": "+52-55-1234-5678",
            "Organization 1 - Name": "Rivera & Sons",
            "Organization 1 - Title": "Partner",
            "Address 1 - City": "mexico city",
            "Birthday": "1985-03-22",
        }
        result = mapper.map_payload(payload)
        assert result.normalized["first_name"] == "Carlos"
        assert result.normalized["last_name"] == "Rivera"
        assert result.normalized["email"] == "carlos@mail.com"
        assert result.normalized["company"] == "Rivera & Sons"
        assert result.normalized["birthday"] == "1985-03-22"


class TestOutlookCSV:
    def test_contact(self, mapper: ContactMapper) -> None:
        payload = {
            "First Name": "Emma",
            "Last Name": "Wilson",
            "E-mail Address": "emma@work.com",
            "Business Phone": "+44 20 7946 0958",
            "Mobile Phone": "+44 7700 900000",
            "Company": "London Ltd",
            "Job Title": "Director",
            "Business City": "london",
            "Business Postal Code": "SW1A 1AA",
            "Birthday": "12/25/1990",
        }
        result = mapper.map_payload(payload)
        assert result.normalized["first_name"] == "Emma"
        assert result.normalized["work_phone"] == "+442079460958"
        assert result.normalized["city"] == "London"
        assert result.normalized["postal_code"] == "SW1A 1AA"


class TestHubSpotIngestion:
    def test_full_contact(self, mapper: ContactMapper) -> None:
        payload = {
            "firstname": "Maria",
            "lastname": "Garcia",
            "email": "  Maria.GARCIA@corp.com  ",
            "phone": "+1-555-234-5678",
            "mobilephone": "+1-555-999-0000",
            "company": "Acme Inc",
            "jobtitle": "VP of Sales",
            "address": "123 Main St",
            "city": "Austin",
            "state": "TX",
            "zip": "78701",
            "country": "US",
            "website": "https://acme.com",
            "lifecyclestage": "customer",
            "hs_lead_status": "Open",
        }
        result = mapper.map_payload(payload)
        assert result.normalized["first_name"] == "Maria"
        assert result.normalized["last_name"] == "Garcia"
        assert result.normalized["email"] == "maria.garcia@corp.com"
        assert result.normalized["company"] == "Acme Inc"
        assert result.normalized["job_title"] == "VP of Sales"
        assert result.normalized["city"] == "Austin"
        assert result.normalized["postal_code"] == "78701"
        assert result.normalized["lifecycle_stage"] == "customer"
        assert result.unmatched_count == 0


class TestMailchimpIngestion:
    def test_subscriber(self, mapper: ContactMapper) -> None:
        payload = {
            "EMAIL": "bob@example.com",
            "FNAME": "bob",
            "LNAME": "smith",
            "PHONE": "(555) 321-0000",
            "COMPANY": "Widgets LLC",
            "BIRTHDAY": "05/15",
        }
        result = mapper.map_payload(payload)
        assert result.normalized["email"] == "bob@example.com"
        assert result.normalized["first_name"] == "Bob"
        assert result.normalized["last_name"] == "Smith"
        assert result.normalized["company"] == "Widgets LLC"
        assert result.match_rate >= 0.8


class TestMessyCSVWithHeuristics:
    def test_heuristic_recovery(self, mapper: ContactMapper) -> None:
        payload = {
            "Column A": "jane.doe@example.com",
            "Column B": "+15551234567",
            "Column C": "Jane",
            "Column D": "Doe",
            "Column E": "Blue",
        }
        result = mapper.map_payload(payload)
        assert result.normalized.get("email") == "jane.doe@example.com"
        assert "phone" in result.normalized
        assert result.unmatched_count >= 2


class TestServiceParamBackwardCompat:
    """service= parameter is accepted but silently ignored."""

    def test_service_param_accepted(self, mapper: ContactMapper) -> None:
        result = mapper.map_payload({"email": "a@b.com"}, service="mailchimp")
        assert result.normalized["email"] == "a@b.com"

    def test_identify_service_param_accepted(self, mapper: ContactMapper) -> None:
        m = mapper.identify("fname", service="mailchimp")
        assert m.canonical == "first_name"

    def test_default_service_accepted(self) -> None:
        m = ContactMapper(default_service="mailchimp")
        match = m.identify("fname")
        assert match.canonical == "first_name"


class TestEdgeCases:
    def test_numeric_values(self, mapper: ContactMapper) -> None:
        result = mapper.map_payload({"phone": 5551234567})
        assert "phone" in result.normalized

    def test_bool_values(self, mapper: ContactMapper) -> None:
        result = mapper.map_payload({"unsubscribed": True})
        assert result.normalized.get("email_opt_out") is True

    def test_large_payload(self, mapper: ContactMapper) -> None:
        payload = {f"field_{i}": f"value_{i}" for i in range(100)}
        payload["email"] = "test@test.com"
        result = mapper.map_payload(payload)
        assert result.normalized.get("email") == "test@test.com"
        assert len(result.field_matches) == 101

    def test_unicode_values(self, mapper: ContactMapper) -> None:
        result = mapper.map_payload({"fname": "José", "surname": "García", "company": "Café Corp"})
        assert result.normalized["first_name"] == "José"
        assert result.normalized["last_name"] == "García"


# ═══════════════════════════════════════════════════════════════
#  FORM BOT INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════


class TestNewCanonicalFields:
    """Verify the 3 new fields added for form bot compatibility."""

    def test_message_alias(self, registry: PatternRegistry) -> None:
        assert registry.exact_lookup("message") == "message"
        assert registry.exact_lookup("inquiry") == "message"
        assert registry.exact_lookup("feedback") == "message"
        assert registry.exact_lookup("your_message") == "message"

    def test_subject_alias(self, registry: PatternRegistry) -> None:
        assert registry.exact_lookup("subject") == "subject"
        assert registry.exact_lookup("subject_line") == "subject"
        assert registry.exact_lookup("reason_for_contact") == "subject"

    def test_company_size_alias(self, registry: PatternRegistry) -> None:
        assert registry.exact_lookup("company_size") == "company_size"
        assert registry.exact_lookup("team_size") == "company_size"
        assert registry.exact_lookup("employees") == "company_size"
        assert registry.exact_lookup("headcount") == "company_size"


class TestW3CAutocompleteAliases:
    """W3C autocomplete tokens must resolve as first-class aliases."""

    @pytest.mark.parametrize(
        "token, expected",
        [
            ("given-name", "first_name"),
            ("family-name", "last_name"),
            ("address-level1", "state"),
            ("address-level2", "city"),
            ("country-name", "country"),
            ("street-address", "address_line1"),
            ("address-line1", "address_line1"),
            ("tel-national", "phone"),
        ],
    )
    def test_w3c_token_exact_lookup(self, registry: PatternRegistry, token: str, expected: str) -> None:
        assert registry.exact_lookup(token) == expected


class TestFormBotFormDetectionPatterns:
    """Simulate form bot's detectPurpose() regex patterns via rolodexter."""

    def test_form_field_first_name(self, mapper: ContactMapper) -> None:
        for header in ["first_name", "fname", "given_name", "forename", "firstname"]:
            m = mapper.identify(header)
            assert m.canonical == "first_name", f"Failed for {header}"

    def test_form_field_last_name(self, mapper: ContactMapper) -> None:
        for header in ["last_name", "lname", "surname", "family_name", "lastname"]:
            m = mapper.identify(header)
            assert m.canonical == "last_name", f"Failed for {header}"

    def test_form_field_company(self, mapper: ContactMapper) -> None:
        for header in ["company", "organization", "organisation", "firm", "employer", "business"]:
            m = mapper.identify(header)
            assert m.canonical == "company", f"Failed for {header}"

    def test_form_field_message(self, mapper: ContactMapper) -> None:
        for header in ["message", "inquiry", "enquiry", "feedback"]:
            m = mapper.identify(header)
            assert m.canonical == "message", f"Failed for {header}"

    def test_form_field_job_title(self, mapper: ContactMapper) -> None:
        for header in ["job_title", "position", "designation"]:
            m = mapper.identify(header)
            assert m.canonical == "job_title", f"Failed for {header}"

    def test_form_field_address(self, mapper: ContactMapper) -> None:
        assert mapper.identify("address").canonical == "address_line1"

    def test_form_field_website(self, mapper: ContactMapper) -> None:
        assert mapper.identify("website").canonical == "website"

    def test_form_field_subject(self, mapper: ContactMapper) -> None:
        assert mapper.identify("subject").canonical == "subject"

    def test_form_field_industry(self, mapper: ContactMapper) -> None:
        assert mapper.identify("industry").canonical == "industry"

    def test_form_field_department(self, mapper: ContactMapper) -> None:
        assert mapper.identify("department").canonical == "department"

    def test_form_field_revenue(self, mapper: ContactMapper) -> None:
        assert mapper.identify("revenue").canonical == "revenue"

    def test_form_field_company_size(self, mapper: ContactMapper) -> None:
        for header in ["company_size", "team_size", "employees", "headcount"]:
            m = mapper.identify(header)
            assert m.canonical == "company_size", f"Failed for {header}"


# ═══════════════════════════════════════════════════════════════
#  V1.2 — EXHAUSTIVE AUDIT TESTS
# ═══════════════════════════════════════════════════════════════


class TestAgeField:
    """Verify the new AGE canonical field."""

    def test_age_enum_exists(self) -> None:
        assert CanonicalField.AGE == "age"

    def test_age_alias_lookup(self, registry: PatternRegistry) -> None:
        assert registry.exact_lookup("age") == "age"
        assert registry.exact_lookup("years_old") == "age"
        assert registry.exact_lookup("your_age") == "age"

    def test_age_in_canonical_fields(self, registry: PatternRegistry) -> None:
        assert "age" in registry.canonical_fields


class TestI18nAliases:
    """Verify i18n aliases resolve from the i18n language blocks."""

    @pytest.mark.parametrize(
        "alias, expected",
        [
            # Romanian
            ("prenume", "first_name"),
            ("nume", "last_name"),
            ("numele_complet", "full_name"),
            ("e-mail", "email"),
            ("mesaj", "message"),
            ("subiect", "subject"),
            # German
            ("vorname", "first_name"),
            ("nachname", "last_name"),
            ("firma", "company"),
            ("nachricht", "message"),
            ("thema", "subject"),
            # French
            ("nom_de_famille", "last_name"),
            ("nom_et_prenom", "full_name"),
            ("prenom", "first_name"),
            ("sujet", "subject"),
            ("entreprise", "company"),
            # Spanish
            ("nombre_de_pila", "first_name"),
            ("apellido", "last_name"),
            ("correo_electronico", "email"),
            ("empresa", "company"),
            ("ciudad", "city"),
            # Portuguese
            ("sobrenome", "last_name"),
            ("codigo_postal", "postal_code"),
            # Italian
            ("cognome", "last_name"),
            ("azienda", "company"),
            ("messaggio", "message"),
            # Dutch
            ("voornaam", "first_name"),
            ("achternaam", "last_name"),
            ("bedrijf", "company"),
            ("bericht", "message"),
            # Romanian extras
            ("companie", "company"),
            # Polish
            ("imie", "first_name"),
            ("nazwisko", "last_name"),
            ("wiadomosc", "message"),
            # Turkish
            ("ilk_adi", "first_name"),
            ("soyisim", "last_name"),
            ("eposta", "email"),
        ],
    )
    def test_i18n_alias_resolves(self, registry: PatternRegistry, alias: str, expected: str) -> None:
        assert registry.exact_lookup(alias) == expected


class TestExtendedSourceAliases:
    """Verify extended source/referral aliases."""

    @pytest.mark.parametrize(
        "alias, expected",
        [
            ("referral", "source"),
            ("how_heard", "source"),
            ("referrer", "source"),
            ("traffic_source", "source"),
            ("campaign_source", "source"),
            ("how_did_you_hear", "source"),
        ],
    )
    def test_source_alias(self, registry: PatternRegistry, alias: str, expected: str) -> None:
        assert registry.exact_lookup(alias) == expected


class TestExtendedOptOutAliases:
    """Verify extended email opt-out / consent aliases."""

    @pytest.mark.parametrize(
        "alias, expected",
        [
            ("optin", "email_opt_out"),
            ("opt_in", "email_opt_out"),
            ("consent", "email_opt_out"),
            ("terms_accepted", "email_opt_out"),
            ("privacy_consent", "email_opt_out"),
            ("subscribe_consent", "email_opt_out"),
            ("gdpr_consent", "email_opt_out"),
            ("marketing_consent", "email_opt_out"),
        ],
    )
    def test_optout_alias(self, registry: PatternRegistry, alias: str, expected: str) -> None:
        assert registry.exact_lookup(alias) == expected


class TestIndustryExtendedAliases:
    """Verify extended industry aliases from audit."""

    @pytest.mark.parametrize(
        "alias",
        ["industry", "sector", "vertical", "market", "business_type", "business_industry"],
    )
    def test_industry_alias(self, registry: PatternRegistry, alias: str) -> None:
        assert registry.exact_lookup(alias) == "industry"


class TestFormBotDetectPurposeCompleteness:
    """Verify ALL 21 purpose strings from detectPurpose() resolve correctly."""

    @pytest.mark.parametrize(
        "field_name, expected_canonical",
        [
            ("email", "email"),
            ("phone", "phone"),
            ("first_name", "first_name"),
            ("last_name", "last_name"),
            ("full_name", "full_name"),
            ("company", "company"),
            ("message", "message"),
            ("job_title", "job_title"),
            ("zip", "postal_code"),
            ("city", "city"),
            ("state", "state"),
            ("country", "country"),
            ("address", "address_line1"),
            ("website", "website"),
            ("subject", "subject"),
            ("industry", "industry"),
            ("department", "department"),
            ("revenue", "revenue"),
            ("company_size", "company_size"),
        ],
    )
    def test_all_detect_purposes(self, mapper: ContactMapper, field_name: str, expected_canonical: str) -> None:
        m = mapper.identify(field_name)
        assert m.canonical == expected_canonical, f"{field_name} → {m.canonical}, expected {expected_canonical}"


class TestFormBotGuessRequiredValueKeywords:
    """Verify all keywords from guessRequiredValue() resolve to correct canonicals."""

    @pytest.mark.parametrize(
        "keyword, expected",
        [
            ("name", "full_name"),
            ("company", "company"),
            ("organisation", "company"),
            ("organization", "company"),
            ("city", "city"),
            ("state", "state"),
            ("province", "state"),
            ("country", "country"),
            ("zip", "postal_code"),
            ("postal", "postal_code"),
            ("url", "website"),
            ("website", "website"),
            ("domain", "website"),
            ("linkedin", "linkedin"),
            ("twitter", "twitter"),
            ("instagram", "instagram"),
            ("phone", "phone"),
            ("mobile", "phone"),
            ("tel", "phone"),
            ("age", "age"),
        ],
    )
    def test_guess_keyword_resolves(self, mapper: ContactMapper, keyword: str, expected: str) -> None:
        m = mapper.identify(keyword)
        assert m.canonical == expected, f"{keyword} → {m.canonical}, expected {expected}"


class TestPatternVersionBump:
    """Verify patterns.json version was bumped for this release."""

    def test_version_is_2_1_0(self, registry: PatternRegistry) -> None:
        assert registry.version == "2.1.0"


# ═══════════════════════════════════════════════════════════════
#  I18N SYSTEM TESTS
# ═══════════════════════════════════════════════════════════════


class TestI18nLanguageSelection:
    """Test the languages parameter for selective i18n loading."""

    def test_all_languages_loaded_by_default(self) -> None:
        reg = PatternRegistry()
        assert len(reg.loaded_languages) >= 20
        assert "es" in reg.loaded_languages
        assert "fr" in reg.loaded_languages
        assert "de" in reg.loaded_languages
        assert "ru" in reg.loaded_languages
        assert "ja" in reg.loaded_languages

    def test_english_only_with_none(self) -> None:
        reg = PatternRegistry(languages=None)
        assert reg.loaded_languages == []
        # English still works
        assert reg.exact_lookup("email") == "email"
        assert reg.exact_lookup("first_name") == "first_name"
        # i18n alias does NOT resolve
        assert reg.exact_lookup("correo") is None
        assert reg.exact_lookup("vorname") is None
        assert reg.exact_lookup("prenume") is None

    def test_english_only_with_empty_list(self) -> None:
        reg = PatternRegistry(languages=[])
        assert reg.loaded_languages == []
        assert reg.exact_lookup("correo") is None

    def test_single_language_string(self) -> None:
        reg = PatternRegistry(languages="es")
        assert reg.loaded_languages == ["es"]
        # Spanish works
        assert reg.exact_lookup("correo_electronico") == "email"
        assert reg.exact_lookup("empresa") == "company"
        # German does not
        assert reg.exact_lookup("vorname") is None
        assert reg.exact_lookup("nachname") is None

    def test_selective_language_list(self) -> None:
        reg = PatternRegistry(languages=["fr", "de"])
        assert sorted(reg.loaded_languages) == ["de", "fr"]
        # French works
        assert reg.exact_lookup("prenom") == "first_name"
        # German works
        assert reg.exact_lookup("vorname") == "first_name"
        # Spanish does not
        assert reg.exact_lookup("correo_electronico") is None
        # Romanian does not
        assert reg.exact_lookup("prenume") is None

    def test_nonexistent_language_ignored(self) -> None:
        reg = PatternRegistry(languages=["xx_fake", "es"])
        assert reg.loaded_languages == ["es"]
        assert reg.exact_lookup("correo_electronico") == "email"


class TestI18nAvailableLanguages:
    """Test the available_languages property."""

    def test_available_languages_lists_all(self) -> None:
        reg = PatternRegistry(languages=None)
        langs = reg.available_languages
        # All 20 language files are discoverable
        assert len(langs) >= 20
        for code in [
            "es",
            "fr",
            "de",
            "ro",
            "pt",
            "it",
            "nl",
            "ja",
            "pl",
            "tr",
            "ru",
            "zh",
            "ko",
            "ar",
            "hi",
            "sv",
            "da",
            "nb",
            "fi",
            "cs",
        ]:
            assert code in langs, f"{code} not in available_languages"

    def test_available_vs_loaded(self) -> None:
        reg = PatternRegistry(languages=["es"])
        assert len(reg.available_languages) >= 20
        assert len(reg.loaded_languages) == 1


class TestI18nContactMapper:
    """Test that ContactMapper passes languages through."""

    def test_mapper_default_loads_all(self) -> None:
        mapper = ContactMapper()
        assert len(mapper.registry.loaded_languages) >= 20
        m = mapper.identify("correo_electronico")
        assert m.canonical == "email"

    def test_mapper_english_only(self) -> None:
        mapper = ContactMapper(languages=None)
        assert mapper.registry.loaded_languages == []
        # Spanish i18n alias does NOT resolve via exact lookup
        assert mapper.registry.exact_lookup("correo") is None
        assert mapper.registry.exact_lookup("vorname") is None
        # English still works
        m = mapper.identify("email")
        assert m.canonical == "email"

    def test_mapper_selective_languages(self) -> None:
        mapper = ContactMapper(languages=["de"])
        m = mapper.identify("vorname")
        assert m.canonical == "first_name"
        # Spanish not loaded — verify via exact lookup
        assert mapper.registry.exact_lookup("correo") is None

    def test_mapper_payload_with_i18n(self) -> None:
        mapper = ContactMapper(languages=["es", "fr"])
        result = mapper.map_payload(
            {
                "correo_electronico": "juan@example.com",
                "nombre_de_pila": "Juan",
                "apellido": "García",
                "empresa": "Acme",
                "e-mail": "duplicate@example.com",
            }
        )
        assert result.normalized["email"] == ["juan@example.com", "duplicate@example.com"]
        assert result.normalized["first_name"] == "Juan"
        assert result.normalized["last_name"] == "García"
        assert result.normalized["company"] == "Acme"


# ═══════════════════════════════════════════════════════════════
#  v2.1 — PHONE NORMALIZER E.164 UPGRADE
# ═══════════════════════════════════════════════════════════════


class TestPhoneNormalizerE164:
    """Test the upgraded PhoneNormalizer with optional phonenumbers lib."""

    def test_regex_fallback_basic(self) -> None:
        """Regex fallback still works for US-like numbers."""
        result = PhoneNormalizer.normalize("555-123-4567")
        assert result == "5551234567"

    def test_regex_fallback_international(self) -> None:
        result = PhoneNormalizer.normalize("+44 20 7946 0958")
        assert "44" in result and "7946" in result

    def test_regex_fallback_long_number_prepends_plus(self) -> None:
        result = PhoneNormalizer.normalize("44207946095812")
        assert result.startswith("+")

    def test_empty_returns_as_is(self) -> None:
        assert PhoneNormalizer.normalize("") == ""

    def test_none_returns_none(self) -> None:
        assert PhoneNormalizer.normalize(None) is None  # type: ignore[arg-type]

    def test_non_string_returns_as_is(self) -> None:
        assert PhoneNormalizer.normalize(12345) == 12345  # type: ignore[arg-type]

    def test_garbage_returns_original(self) -> None:
        # No digits at all → returns original
        assert PhoneNormalizer.normalize("no phone here") == "no phone here"

    def test_too_short_returns_original(self) -> None:
        assert PhoneNormalizer.normalize("123") == "123"

    def test_whitespace_only_returns_original(self) -> None:
        assert PhoneNormalizer.normalize("   ") == "   "

    def test_e164_output_when_phonenumbers_available(self) -> None:
        """If phonenumbers is installed, E.164 formatting should be used."""
        try:
            import phonenumbers  # noqa: F401

            result = PhoneNormalizer.normalize("+1 (555) 123-4567")
            assert result == "+15551234567"
        except ImportError:
            pytest.skip("phonenumbers not installed")

    def test_e164_international_uk(self) -> None:
        try:
            import phonenumbers  # noqa: F401

            result = PhoneNormalizer.normalize("+44 20 7946 0958")
            assert result == "+442079460958"
        except ImportError:
            pytest.skip("phonenumbers not installed")

    def test_e164_international_japan(self) -> None:
        try:
            import phonenumbers  # noqa: F401

            result = PhoneNormalizer.normalize("+81 3-1234-5678")
            assert result == "+81312345678"
        except ImportError:
            pytest.skip("phonenumbers not installed")

    def test_e164_invalid_number_falls_back(self) -> None:
        """Invalid phone numbers fall back to regex strip."""
        result = PhoneNormalizer.normalize("+99 000 000 0000")
        # Should return something (regex fallback), not crash
        assert isinstance(result, str)

    def test_default_region_parameter(self) -> None:
        """The default_region kwarg is accepted for phonenumbers parsing."""
        try:
            import phonenumbers  # noqa: F401

            result = PhoneNormalizer.normalize("(02) 1234 5678", default_region="AU")
            assert result.startswith("+61")
        except ImportError:
            pytest.skip("phonenumbers not installed")


# ═══════════════════════════════════════════════════════════════
#  v2.1 — RECURSIVE / NESTED PAYLOAD SUPPORT
# ═══════════════════════════════════════════════════════════════


class TestNestedPayloadDepth:
    """Test map_payload() with depth parameter for nested dicts."""

    def test_depth_1_flat_only(self) -> None:
        """depth=1 (default) only processes top-level keys."""
        mapper = ContactMapper()
        payload = {
            "email": "test@example.com",
            "address": {"line1": "123 Main St", "city": "Springfield"},
        }
        result = mapper.map_payload(payload, depth=1)
        assert result.normalized["email"] == "test@example.com"
        # nested dict preserved in unmapped or normalized as-is
        assert "address" not in result.unmapped or isinstance(result.unmapped.get("address"), dict)

    def test_depth_2_flattens_one_level(self) -> None:
        """depth=2 flattens nested dicts one level."""
        mapper = ContactMapper()
        payload = {
            "email": "test@example.com",
            "address": {"line1": "123 Main St", "city": "Springfield"},
        }
        result = mapper.map_payload(payload, depth=2)
        assert result.normalized["email"] == "test@example.com"
        # address_city should resolve to city via normalizer
        assert "city" in result.normalized

    def test_stripe_style_nested(self) -> None:
        """Stripe-style nested address payload."""
        mapper = ContactMapper()
        payload = {
            "email": "jane@stripe.com",
            "name": "Jane Doe",
            "address": {
                "line1": "123 Main St",
                "city": "San Francisco",
                "state": "CA",
                "postal_code": "94105",
                "country": "US",
            },
        }
        result = mapper.map_payload(payload, depth=2)
        assert result.normalized["email"] == "jane@stripe.com"
        assert result.normalized["full_name"] == "Jane Doe"
        # Flattened address fields should resolve
        assert "city" in result.normalized
        assert "state" in result.normalized
        assert "postal_code" in result.normalized
        assert "country" in result.normalized

    def test_hubspot_style_properties_wrapper(self) -> None:
        """HubSpot-style properties wrapper."""
        mapper = ContactMapper()
        payload = {
            "properties": {
                "email": "lead@company.com",
                "firstname": "Alice",
                "lastname": "Smith",
                "company": "Acme Corp",
            }
        }
        result = mapper.map_payload(payload, depth=2)
        assert result.normalized["email"] == "lead@company.com"
        assert result.normalized["first_name"] == "Alice"
        assert result.normalized["last_name"] == "Smith"
        assert result.normalized["company"] == "Acme Corp"

    def test_mailchimp_merge_fields(self) -> None:
        """Mailchimp merge_fields wrapper."""
        mapper = ContactMapper()
        payload = {
            "email_address": "bob@mc.com",
            "merge_fields": {
                "FNAME": "Bob",
                "LNAME": "Jones",
                "PHONE": "555-0100",
            },
        }
        result = mapper.map_payload(payload, depth=2)
        assert result.normalized["email"] == "bob@mc.com"
        assert result.normalized["first_name"] == "Bob"

    def test_depth_clamped_maximum_5(self) -> None:
        """depth > 5 is clamped to 5."""
        mapper = ContactMapper()
        payload = {"email": "a@b.com"}
        result = mapper.map_payload(payload, depth=100)
        assert result.normalized["email"] == "a@b.com"

    def test_depth_clamped_minimum_1(self) -> None:
        """depth < 1 is clamped to 1."""
        mapper = ContactMapper()
        payload = {"email": "a@b.com"}
        result = mapper.map_payload(payload, depth=0)
        assert result.normalized["email"] == "a@b.com"

    def test_deeply_nested_depth_3(self) -> None:
        """depth=3 flattens two levels of nesting."""
        mapper = ContactMapper()
        payload = {
            "contact": {
                "info": {
                    "email": "deep@test.com",
                    "first_name": "Deep",
                }
            }
        }
        result = mapper.map_payload(payload, depth=3)
        assert result.normalized["email"] == "deep@test.com"
        assert result.normalized["first_name"] == "Deep"

    def test_non_dict_values_preserved(self) -> None:
        """Non-dict values are not recursed into."""
        mapper = ContactMapper()
        payload = {
            "email": "test@test.com",
            "tags": ["a", "b", "c"],
            "score": 42,
        }
        result = mapper.map_payload(payload, depth=2)
        assert result.normalized["email"] == "test@test.com"
        assert result.normalized["tags"] == ["a", "b", "c"]
        assert result.normalized["score"] == 42

    def test_map_batch_with_depth(self) -> None:
        """map_batch passes depth through."""
        mapper = ContactMapper()
        payloads = [
            {"properties": {"email": "a@a.com", "firstname": "A"}},
            {"properties": {"email": "b@b.com", "firstname": "B"}},
        ]
        results = mapper.map_batch(payloads, depth=2)
        assert len(results) == 2
        assert results[0].normalized["email"] == "a@a.com"
        assert results[1].normalized["first_name"] == "B"

    def test_flatten_static_method(self) -> None:
        """Test _flatten directly."""
        flat = ContactMapper._flatten(
            {"a": {"b": "val", "c": "val2"}, "d": "top"},
            depth=2,
        )
        assert flat == {"a.b": "val", "a.c": "val2", "d": "top"}


# ═══════════════════════════════════════════════════════════════
#  v2.1 — NEW CANONICAL FIELDS
# ═══════════════════════════════════════════════════════════════


class TestNewCanonicalFields:
    """Test the 4 new fields added in v2.1."""

    def test_source_id_in_enum(self) -> None:
        assert CanonicalField.SOURCE_ID == "source_id"

    def test_source_service_in_enum(self) -> None:
        assert CanonicalField.SOURCE_SERVICE == "source_service"

    def test_subscribed_in_enum(self) -> None:
        assert CanonicalField.SUBSCRIBED == "subscribed"

    def test_verified_in_enum(self) -> None:
        assert CanonicalField.VERIFIED == "verified"

    @pytest.mark.parametrize(
        "header,expected",
        [
            ("source_id", "source_id"),
            ("external_id", "source_id"),
            ("remote_id", "source_id"),
            ("customer_id", "source_id"),
            ("stripe_id", "source_id"),
            ("crm_id", "source_id"),
            ("source_service", "source_service"),
            ("source_system", "source_service"),
            ("provider", "source_service"),
            ("data_source", "source_service"),
            ("imported_from", "source_service"),
            ("integration", "source_service"),
            ("platform", "source_service"),
            ("subscribed", "subscribed"),
            ("is_subscribed", "subscribed"),
            ("subscription_status", "subscribed"),
            ("opted_in", "subscribed"),
            ("newsletter", "subscribed"),
            ("verified", "verified"),
            ("is_verified", "verified"),
            ("email_verified", "verified"),
            ("confirmed", "verified"),
            ("email_confirmed", "verified"),
            ("validated", "verified"),
        ],
    )
    def test_new_field_aliases(self, header: str, expected: str) -> None:
        mapper = ContactMapper()
        m = mapper.identify(header)
        assert m.canonical == expected, f"{header!r} → {m.canonical!r}, expected {expected!r}"

    def test_payload_with_new_fields(self) -> None:
        mapper = ContactMapper()
        result = mapper.map_payload(
            {
                "email": "test@example.com",
                "source_id": "cus_abc123",
                "source_service": "stripe",
                "subscribed": True,
                "verified": True,
            }
        )
        assert result.normalized["email"] == "test@example.com"
        assert result.normalized["source_id"] == "cus_abc123"
        assert result.normalized["source_service"] == "stripe"
        assert result.normalized["subscribed"] is True
        assert result.normalized["verified"] is True


# ═══════════════════════════════════════════════════════════════
#  v2.1 — DYNAMIC SERVICE RESOLUTION (verifying #3 deprecated)
# ═══════════════════════════════════════════════════════════════


class TestWishlistServicesDynamic:
    """Verify the 8 'missing' services from the wishlist resolve
    dynamically without any service profiles.
    """

    @pytest.mark.parametrize(
        "header,expected",
        [
            # mailgun
            ("address", "address_line1"),
            ("name", "full_name"),
            ("subscribed", "subscribed"),
            ("created_at", "created_at"),
            # mailersend
            ("email", "email"),
            ("first_name", "first_name"),
            ("last_name", "last_name"),
            # postmark
            ("Email", "email"),
            ("Name", "full_name"),
            ("Description", "notes"),
            # moosend
            ("FirstName", "first_name"),
            ("LastName", "last_name"),
            ("Phone", "phone"),
            ("MobilePhone", "phone"),
            ("Company", "company"),
            ("Country", "country"),
            ("City", "city"),
            ("Zip", "postal_code"),
            ("CreatedOn", "created_at"),
            # getresponse
            ("dayOfBirth", "birthday"),
            ("tags", "tags"),
            ("ipAddress", "metadata"),
            # campaignmonitor
            ("EmailAddress", "email"),
            ("State", "state"),
            ("CustomFields", "metadata"),
            # elasticemail
            ("firstName", "first_name"),
            ("lastName", "last_name"),
            ("phone", "phone"),
            ("status", "lead_status"),
            ("dateAdded", "created_at"),
            # smtp2go
            ("subject", "subject"),
        ],
    )
    def test_service_field_resolves(self, header: str, expected: str) -> None:
        mapper = ContactMapper()
        m = mapper.identify(header)
        assert m.is_matched, f"{header!r} → {m.canonical!r} (unmatched, strategy={m.strategy})"
        assert m.canonical == expected, f"{header!r} → {m.canonical!r}, expected {expected!r}"


# ═══════════════════════════════════════════════════════════════
#  v2.1 — ALIAS GAP FIXES
# ═══════════════════════════════════════════════════════════════


class TestAliasGapFixes:
    """Aliases added to close gaps found during service verification."""

    @pytest.mark.parametrize(
        "header,expected",
        [
            ("created_on", "created_at"),
            ("day_of_birth", "birthday"),
            ("ip_address", "metadata"),
        ],
    )
    def test_gap_alias(self, header: str, expected: str) -> None:
        mapper = ContactMapper()
        m = mapper.identify(header)
        assert m.canonical == expected
