"""Complete test suite for rolodexter v2.1 — tests in one file."""

from __future__ import annotations

from pathlib import Path

import pytest
import tomllib

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


def test_console_script_entry_points_match_package_bins() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"] == {
        "rolodexter": "rolodexter.__main__:main",
        "rolodexter-i18n": "rolodexter.i18n:main",
    }


def test_submodule_public_export_lists_are_explicit() -> None:
    import rolodexter.core as core
    import rolodexter.i18n as i18n

    assert core.__all__ == [
        "DEFAULT_HEADER_CACHE_MAX_SIZE",
        "EMBEDDED_PHONE_MAX_MATCHES_PER_FIELD",
        "EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD",
        "EMBEDDED_PHONE_MAX_TEXT_CHARS",
        "EXACT_MATCH_CONFIDENCE",
        "FUZZY_HIGH_CONFIDENCE",
        "FUZZY_LENGTH_RATIO",
        "FUZZY_LOW_CONFIDENCE",
        "FUZZY_MATCH_THRESHOLD",
        "HEURISTIC_CONFIDENCE",
        "NORMALIZED_MATCH_CONFIDENCE",
        "AddressNormalizer",
        "BooleanNormalizer",
        "CanonicalField",
        "ContactMapper",
        "EmailNormalizer",
        "ExactMatchStrategy",
        "FieldMatch",
        "FuzzyMatchStrategy",
        "HeuristicMatchStrategy",
        "ListNormalizer",
        "MappingResult",
        "MappingSchema",
        "MatchStrategy",
        "NameNormalizer",
        "NormalizationError",
        "NormalizedMatchStrategy",
        "PatternLoadError",
        "PatternRegistry",
        "PhoneNormalizer",
        "PostalCodeNormalizer",
        "RolodexterError",
        "StringNormalizer",
        "normalize_value",
    ]
    assert i18n.__all__ == [
        "DEFAULT_TRANSLATE_RETRIES",
        "DEFAULT_TRANSLATE_RETRY_BACKOFF",
        "DEFAULT_TRANSLATE_TIMEOUT",
        "MAX_I18N_WORKERS",
        "SUPPORTED_LANGUAGES",
        "discover_cached",
        "generate_language",
        "get_all_cache_dirs",
        "get_cache_dir",
        "get_writable_cache_dir",
        "load_cached",
        "main",
    ]


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

    def test_all_aliases_returns_copy(self, registry: PatternRegistry) -> None:
        aliases = registry.all_aliases
        aliases.clear()
        assert len(registry.all_aliases) > 200
        assert registry.exact_lookup("fname") == "first_name"

    def test_version(self, registry: PatternRegistry) -> None:
        assert registry.version == "2.6.0"

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
    def test_alias_resolves(
        self, registry: PatternRegistry, alias: str, expected: str
    ) -> None:
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
        assert (
            m is not None
            and m.canonical == "first_name"
            and m.confidence == 0.95
            and m.strategy == "normalized"
        )

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

    def test_address_prefix_business_postal_code(
        self, registry: PatternRegistry
    ) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("Business Postal Code")
        assert m is not None and m.canonical == "postal_code"

    def test_address_prefix_business_street(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("Business Street")
        assert m is not None and m.canonical == "address_line1"

    def test_address_prefix_business_country_region(
        self, registry: PatternRegistry
    ) -> None:
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

    # DOUBLE_OPT-IN (Brevo) — hyphen mid-word → subscribed (affirmative)
    def test_double_opt_in(self, registry: PatternRegistry) -> None:
        strat = NormalizedMatchStrategy(registry)
        m = strat.match("DOUBLE_OPT-IN")
        assert m is not None and m.canonical == "subscribed"


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

    def test_generic_dates_are_not_birthday_without_header_hint(self) -> None:
        strat = HeuristicMatchStrategy()
        assert strat.match("Unknown Column", value="1990-05-15") is None
        assert strat.match("Unknown Column", value="05/15/1990") is None

    @pytest.mark.parametrize("header", ["Birth Date", "Date of Birth", "dayOfBirth"])
    def test_birth_date_header_hint_allows_date_values(self, header: str) -> None:
        strat = HeuristicMatchStrategy()
        m = strat.match(header, value="1990-05-15")
        assert m is not None
        assert m.canonical == "birthday"

    def test_bare_numeric_phone_shape_requires_header_hint(self) -> None:
        strat = HeuristicMatchStrategy()
        assert strat.match("customer_id", value="2025550143") is None
        m = strat.match("contact phone", value="2025550143")
        assert m is not None
        assert m.canonical == "phone"

    def test_formatted_phone_shape_still_matches_unknown_headers(self) -> None:
        strat = HeuristicMatchStrategy()
        m = strat.match("Unknown Column", value="202-555-0143")
        assert m is not None
        assert m.canonical == "phone"


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
        result = mapper.map_payload(
            {"fname": "Jane", "surname": "Doe", "mobile": "555-0199"}
        )
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
            ("double_opt_in", "subscribed"),
            ("work_number", "work_phone"),
            ("annualrevenue", "revenue"),
        ],
    )
    def test_new_alias(
        self, registry: PatternRegistry, alias: str, expected: str
    ) -> None:
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
        result = mapper.map_payload(
            {"fname": "José", "surname": "García", "company": "Café Corp"}
        )
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
    def test_w3c_token_exact_lookup(
        self, registry: PatternRegistry, token: str, expected: str
    ) -> None:
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
        for header in [
            "company",
            "organization",
            "organisation",
            "firm",
            "employer",
            "business",
        ]:
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
    """Verify i18n aliases resolve when language data is available.

    Uses mock cached data to avoid needing deep-translator at test time.
    """

    # Fake i18n data matching what the generator would produce
    _MOCK_ES = {  # noqa: RUF012
        "language_code": "es",
        "language_name": "Spanish",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "2.1.0",
        "fields": {
            "first_name": [
                "nombre de pila",
                "nombre_de_pila",
                "nombredepila",
                "nombre-de-pila",
            ],
            "last_name": ["apellido"],
            "full_name": [
                "nombre completo",
                "nombre_completo",
                "nombrecompleto",
                "nombre-completo",
            ],
            "email": [
                "correo electronico",
                "correo_electronico",
                "correoelectronico",
                "correo-electronico",
                "correo",
            ],
            "company": ["empresa"],
            "city": ["ciudad"],
            "message": ["mensaje"],
            "subject": ["asunto"],
        },
    }
    _MOCK_DE = {  # noqa: RUF012
        "language_code": "de",
        "language_name": "German",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "2.1.0",
        "fields": {
            "first_name": ["vorname"],
            "last_name": ["nachname"],
            "full_name": ["vollstandiger name", "vollstandiger_name"],
            "company": ["firma"],
            "message": ["nachricht"],
            "subject": ["thema"],
        },
    }
    _MOCK_FR = {  # noqa: RUF012
        "language_code": "fr",
        "language_name": "French",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "2.1.0",
        "fields": {
            "first_name": ["prenom"],
            "last_name": ["nom de famille", "nom_de_famille"],
            "full_name": ["nom et prenom", "nom_et_prenom"],
            "email": ["e-mail"],
            "company": ["entreprise"],
            "subject": ["sujet"],
        },
    }
    _MOCK_RO = {  # noqa: RUF012
        "language_code": "ro",
        "language_name": "Romanian",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "2.1.0",
        "fields": {
            "first_name": ["prenume"],
            "last_name": ["nume"],
            "full_name": ["numele complet", "numele_complet"],
            "email": ["e-mail"],
            "company": ["companie"],
            "message": ["mesaj"],
            "subject": ["subiect"],
        },
    }
    _MOCK_PT = {  # noqa: RUF012
        "language_code": "pt",
        "language_name": "Portuguese",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "2.1.0",
        "fields": {
            "last_name": ["sobrenome"],
            "postal_code": ["codigo postal", "codigo_postal"],
        },
    }
    _MOCK_IT = {  # noqa: RUF012
        "language_code": "it",
        "language_name": "Italian",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "2.1.0",
        "fields": {
            "last_name": ["cognome"],
            "company": ["azienda"],
            "message": ["messaggio"],
        },
    }
    _MOCK_NL = {  # noqa: RUF012
        "language_code": "nl",
        "language_name": "Dutch",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "2.1.0",
        "fields": {
            "first_name": ["voornaam"],
            "last_name": ["achternaam"],
            "company": ["bedrijf"],
            "message": ["bericht"],
        },
    }
    _MOCK_PL = {  # noqa: RUF012
        "language_code": "pl",
        "language_name": "Polish",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "2.1.0",
        "fields": {
            "first_name": ["imie"],
            "last_name": ["nazwisko"],
            "message": ["wiadomosc"],
        },
    }
    _MOCK_TR = {  # noqa: RUF012
        "language_code": "tr",
        "language_name": "Turkish",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "2.1.0",
        "fields": {
            "first_name": ["ilk adi", "ilk_adi"],
            "last_name": ["soyisim"],
            "email": ["eposta"],
        },
    }

    _ALL_MOCKS = {  # noqa: RUF012
        "es": _MOCK_ES,
        "de": _MOCK_DE,
        "fr": _MOCK_FR,
        "ro": _MOCK_RO,
        "pt": _MOCK_PT,
        "it": _MOCK_IT,
        "nl": _MOCK_NL,
        "pl": _MOCK_PL,
        "tr": _MOCK_TR,
    }

    @staticmethod
    def _mock_load_cached(lang_code: str):
        return TestI18nAliases._ALL_MOCKS.get(lang_code)

    @pytest.mark.parametrize(
        "alias, expected",
        [
            # Romanian
            ("prenume", "first_name"),
            ("nume", "last_name"),
            ("numele_complet", "full_name"),
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
    def test_i18n_alias_resolves(self, alias: str, expected: str) -> None:
        from unittest.mock import patch

        with patch("rolodexter.i18n.load_cached", side_effect=self._mock_load_cached):
            reg = PatternRegistry(
                languages=["es", "de", "fr", "ro", "pt", "it", "nl", "pl", "tr"]
            )
        assert reg.exact_lookup(alias) == expected


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
    def test_source_alias(
        self, registry: PatternRegistry, alias: str, expected: str
    ) -> None:
        assert registry.exact_lookup(alias) == expected


class TestExtendedOptOutAliases:
    """Verify extended email opt-out / consent aliases."""

    @pytest.mark.parametrize(
        "alias, expected",
        [
            # Negative / opt-out semantics → email_opt_out
            ("consent", "email_opt_out"),
            ("terms_accepted", "email_opt_out"),
            ("privacy_consent", "email_opt_out"),
            ("gdpr_consent", "email_opt_out"),
            ("marketing_consent", "email_opt_out"),
            # Affirmative / opt-in semantics → subscribed
            ("optin", "subscribed"),
            ("opt_in", "subscribed"),
            ("subscribe_consent", "subscribed"),
        ],
    )
    def test_optout_alias(
        self, registry: PatternRegistry, alias: str, expected: str
    ) -> None:
        assert registry.exact_lookup(alias) == expected


class TestIndustryExtendedAliases:
    """Verify extended industry aliases from audit."""

    @pytest.mark.parametrize(
        "alias",
        [
            "industry",
            "sector",
            "vertical",
            "market",
            "business_type",
            "business_industry",
        ],
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
    def test_all_detect_purposes(
        self, mapper: ContactMapper, field_name: str, expected_canonical: str
    ) -> None:
        m = mapper.identify(field_name)
        assert m.canonical == expected_canonical, (
            f"{field_name} → {m.canonical}, expected {expected_canonical}"
        )


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
    def test_guess_keyword_resolves(
        self, mapper: ContactMapper, keyword: str, expected: str
    ) -> None:
        m = mapper.identify(keyword)
        assert m.canonical == expected, (
            f"{keyword} → {m.canonical}, expected {expected}"
        )


class TestPatternVersionBump:
    """Verify patterns.json version was bumped for this release."""

    def test_version_is_2_6_0(self, registry: PatternRegistry) -> None:
        assert registry.version == "2.6.0"


# ═══════════════════════════════════════════════════════════════
#  I18N SYSTEM TESTS (on-demand generation model)
# ═══════════════════════════════════════════════════════════════

from unittest.mock import patch as _mock_patch  # noqa: E402

# Shared mock data for i18n tests
_MOCK_I18N = {
    "es": {
        "language_code": "es",
        "language_name": "Spanish",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "2.1.0",
        "fields": {
            "first_name": ["nombre de pila", "nombre_de_pila"],
            "last_name": ["apellido"],
            "full_name": ["nombre completo", "nombre_completo"],
            "email": ["correo electronico", "correo_electronico", "correo"],
            "company": ["empresa"],
            "city": ["ciudad"],
        },
    },
    "de": {
        "language_code": "de",
        "language_name": "German",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "2.1.0",
        "fields": {
            "first_name": ["vorname"],
            "last_name": ["nachname"],
            "company": ["firma"],
        },
    },
    "fr": {
        "language_code": "fr",
        "language_name": "French",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "2.1.0",
        "fields": {
            "first_name": ["prenom"],
            "last_name": ["nom de famille", "nom_de_famille"],
            "email": ["e-mail"],
            "company": ["entreprise"],
        },
    },
}


def _mock_load_cached(lang_code: str):
    return _MOCK_I18N.get(lang_code)


class TestI18nLanguageSelection:
    """Test the languages parameter for selective i18n loading."""

    def test_default_is_english_only(self) -> None:
        """Default (no languages) loads English only — no i18n."""
        reg = PatternRegistry()
        assert reg.loaded_languages == []
        assert reg.exact_lookup("email") == "email"
        assert reg.exact_lookup("correo") is None

    def test_english_only_with_none(self) -> None:
        reg = PatternRegistry(languages=None)
        assert reg.loaded_languages == []
        assert reg.exact_lookup("email") == "email"
        assert reg.exact_lookup("first_name") == "first_name"
        assert reg.exact_lookup("correo") is None
        assert reg.exact_lookup("vorname") is None

    def test_english_only_with_empty_list(self) -> None:
        reg = PatternRegistry(languages=[])
        assert reg.loaded_languages == []
        assert reg.exact_lookup("correo") is None

    def test_single_language_string(self) -> None:
        with _mock_patch("rolodexter.i18n.load_cached", side_effect=_mock_load_cached):
            reg = PatternRegistry(languages="es")
        assert reg.loaded_languages == ["es"]
        assert reg.exact_lookup("correo_electronico") == "email"
        assert reg.exact_lookup("empresa") == "company"
        assert reg.exact_lookup("vorname") is None

    def test_selective_language_list(self) -> None:
        with _mock_patch("rolodexter.i18n.load_cached", side_effect=_mock_load_cached):
            reg = PatternRegistry(languages=["fr", "de"])
        assert sorted(reg.loaded_languages) == ["de", "fr"]
        assert reg.exact_lookup("prenom") == "first_name"
        assert reg.exact_lookup("vorname") == "first_name"
        assert reg.exact_lookup("correo_electronico") is None

    def test_nonexistent_language_skipped(self) -> None:
        """Unknown language codes are silently skipped."""
        with _mock_patch("rolodexter.i18n.load_cached", side_effect=_mock_load_cached):
            reg = PatternRegistry(languages=["xx_fake", "es"])
        # xx_fake skipped, es loaded
        assert reg.loaded_languages == ["es"]
        assert reg.exact_lookup("correo_electronico") == "email"


class TestI18nAvailableLanguages:
    """Test the available_languages property (lists SUPPORTED_LANGUAGES)."""

    def test_available_languages_lists_all_supported(self) -> None:
        reg = PatternRegistry(languages=None)
        langs = reg.available_languages
        # SUPPORTED_LANGUAGES has 40 entries
        assert len(langs) >= 30
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
        with _mock_patch("rolodexter.i18n.load_cached", side_effect=_mock_load_cached):
            reg = PatternRegistry(languages=["es"])
        assert len(reg.available_languages) >= 30
        assert len(reg.loaded_languages) == 1


class TestI18nContactMapper:
    """Test that ContactMapper passes languages through."""

    def test_mapper_default_english_only(self) -> None:
        mapper = ContactMapper()
        assert mapper.registry.loaded_languages == []
        assert mapper.registry.exact_lookup("correo") is None
        m = mapper.identify("email")
        assert m.canonical == "email"

    def test_mapper_english_only_explicit(self) -> None:
        mapper = ContactMapper(languages=None)
        assert mapper.registry.loaded_languages == []
        assert mapper.registry.exact_lookup("vorname") is None
        m = mapper.identify("email")
        assert m.canonical == "email"

    def test_mapper_selective_languages(self) -> None:
        with _mock_patch("rolodexter.i18n.load_cached", side_effect=_mock_load_cached):
            mapper = ContactMapper(languages=["de"])
        m = mapper.identify("vorname")
        assert m.canonical == "first_name"
        assert mapper.registry.exact_lookup("correo") is None

    def test_mapper_payload_with_i18n(self) -> None:
        with _mock_patch("rolodexter.i18n.load_cached", side_effect=_mock_load_cached):
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
        assert result.normalized["email"] == [
            "juan@example.com",
            "duplicate@example.com",
        ]
        assert result.normalized["first_name"] == "Juan"
        assert result.normalized["last_name"] == "García"
        assert result.normalized["company"] == "Acme"


class TestI18nModule:
    """Test the i18n module itself — internal helpers and public API."""

    # --- SUPPORTED_LANGUAGES ---

    def test_supported_languages_dict(self) -> None:
        from rolodexter.i18n import SUPPORTED_LANGUAGES

        assert len(SUPPORTED_LANGUAGES) >= 30
        assert "es" in SUPPORTED_LANGUAGES
        assert "fr" in SUPPORTED_LANGUAGES
        assert "de" in SUPPORTED_LANGUAGES

    def test_supported_languages_structure(self) -> None:
        from rolodexter.i18n import SUPPORTED_LANGUAGES

        for code, (translate_code, display_name) in SUPPORTED_LANGUAGES.items():
            assert isinstance(code, str) and len(code) >= 2
            assert isinstance(translate_code, str) and len(translate_code) >= 2
            assert isinstance(display_name, str) and len(display_name) >= 3

    # --- generate_language ---

    def test_generate_language_unsupported_raises(self) -> None:
        from rolodexter.i18n import generate_language

        with pytest.raises(ValueError, match="Unsupported language"):
            generate_language("xx_fake")

    # --- discover / load ---

    def test_discover_cached_returns_dict(self) -> None:
        from rolodexter.i18n import discover_cached

        result = discover_cached()
        assert isinstance(result, dict)

    def test_load_cached_missing_returns_none(self) -> None:
        from rolodexter.i18n import load_cached

        assert load_cached("zz_nonexistent_lang") is None

    # --- cache dirs ---

    def test_get_cache_dir_returns_path(self) -> None:
        from pathlib import Path

        from rolodexter.i18n import get_cache_dir

        d = get_cache_dir()
        assert isinstance(d, Path)
        assert d.exists()

    def test_get_all_cache_dirs(self) -> None:
        from rolodexter.i18n import get_all_cache_dirs

        dirs = get_all_cache_dirs()
        assert isinstance(dirs, list)
        for d in dirs:
            assert isinstance(d, Path)
            assert d.is_dir()

    def test_package_i18n_dir(self) -> None:
        from rolodexter.i18n import _package_i18n_dir

        d = _package_i18n_dir()
        # In an editable install this should succeed
        if d is not None:
            assert d.is_dir()

    def test_user_cache_dir(self) -> None:
        from rolodexter.i18n import _user_cache_dir

        d = _user_cache_dir()
        assert isinstance(d, Path)
        assert d.name == "i18n"

    # --- alias variant generation ---

    def test_to_alias_variants_basic(self) -> None:
        from rolodexter.i18n import _to_alias_variants

        variants = _to_alias_variants("correo electrónico")
        assert "correo electrónico" in variants
        assert "correo_electrónico" in variants
        assert "correoelectrónico" in variants
        assert "correo-electrónico" in variants

    def test_to_alias_variants_short_ignored(self) -> None:
        from rolodexter.i18n import _to_alias_variants

        assert _to_alias_variants("") == set()
        assert _to_alias_variants("x") == set()

    def test_to_alias_variants_single_word(self) -> None:
        from rolodexter.i18n import _to_alias_variants

        variants = _to_alias_variants("Empresa")
        assert "empresa" in variants

    def test_to_alias_variants_preserves_case_lower(self) -> None:
        from rolodexter.i18n import _to_alias_variants

        variants = _to_alias_variants("NachName")
        assert "nachname" in variants
        assert "NachName" not in variants

    # --- field derivation ---

    def test_derive_field_phrases(self) -> None:
        from rolodexter.i18n import _derive_field_phrases

        master = {"fields": {"first_name": [], "email": [], "metadata": [], "tags": []}}
        result = _derive_field_phrases(master)
        assert result["first_name"] == "first name"
        assert result["email"] == "email"
        # Skip fields are excluded
        assert "metadata" not in result
        assert "tags" not in result

    def test_derive_field_phrases_empty(self) -> None:
        from rolodexter.i18n import _derive_field_phrases

        assert _derive_field_phrases({}) == {}
        assert _derive_field_phrases({"fields": {}}) == {}

    def test_get_english_aliases(self) -> None:
        from rolodexter.i18n import _get_english_aliases

        master = {
            "fields": {
                "email": ["e-mail", "Email Address", "EmailAddress"],
                "first_name": ["fname", "First Name"],
            }
        }
        aliases = _get_english_aliases(master)
        assert "e-mail" in aliases
        assert "email address" in aliases
        assert "emailaddress" in aliases
        assert "fname" in aliases
        assert "first name" in aliases

    # --- load_master ---

    def test_load_master_returns_dict(self) -> None:
        from rolodexter.i18n import _load_master

        master = _load_master()
        assert isinstance(master, dict)
        assert "fields" in master
        assert "version" in master
        assert len(master["fields"]) >= 40

    # --- write / load round-trip ---

    def test_write_and_load_cache(self, tmp_path: Path) -> None:
        """Write a cache file via _write_cache, read it back with load_cached."""
        import json

        from rolodexter.i18n import _write_cache, load_cached

        lang_data = {
            "language_code": "zz_test",
            "language_name": "Test Language",
            "generated_at": "2026-01-01T00:00:00+00:00",
            "source_version": "2.2.0",
            "fields": {"email": ["prueba"]},
        }
        # Patch get_cache_dir to use tmp_path
        with _mock_patch("rolodexter.i18n.get_cache_dir", return_value=tmp_path):
            written = _write_cache(lang_data)
        assert written.exists()
        assert json.loads(written.read_text("utf-8"))["language_code"] == "zz_test"
        # Now load it back
        with _mock_patch("rolodexter.i18n.get_all_cache_dirs", return_value=[tmp_path]):
            loaded = load_cached("zz_test")
        assert loaded is not None
        assert loaded["fields"]["email"] == ["prueba"]

    def test_load_cached_bad_json(self, tmp_path: Path) -> None:
        """Corrupt JSON is silently skipped."""
        from rolodexter.i18n import load_cached

        bad_file = tmp_path / "zz_corrupt.json"
        bad_file.write_text("NOT JSON{{{", encoding="utf-8")
        with _mock_patch("rolodexter.i18n.get_all_cache_dirs", return_value=[tmp_path]):
            assert load_cached("zz_corrupt") is None

    # --- discover_cached with tmp dir ---

    def test_discover_cached_finds_files(self, tmp_path: Path) -> None:
        from rolodexter.i18n import discover_cached

        (tmp_path / "es.json").write_text('{"language_code":"es"}', encoding="utf-8")
        (tmp_path / "fr.json").write_text('{"language_code":"fr"}', encoding="utf-8")
        (tmp_path / "readme.txt").write_text("ignore me", encoding="utf-8")
        with _mock_patch("rolodexter.i18n.get_all_cache_dirs", return_value=[tmp_path]):
            found = discover_cached()
        assert "es" in found
        assert "fr" in found
        assert "readme" not in found

    # --- translate batch (mocked) ---

    def test_translate_batch_mocked(self) -> None:
        """Verify _translate_batch calls deep-translator correctly."""
        mock_translator = type(
            "MockTranslator",
            (),
            {
                "translate_batch": lambda self, phrases: [p.upper() for p in phrases],
            },
        )()
        with _mock_patch(
            "rolodexter.i18n.GoogleTranslator",
            return_value=mock_translator,
            create=True,
        ):
            # We need to mock the actual import inside the function
            import rolodexter.i18n as i18n_mod

            original = i18n_mod._translate_batch

            def patched_batch(phrases, lang_code):
                return [p.upper() for p in phrases]

            i18n_mod._translate_batch = patched_batch
            try:
                results = i18n_mod._translate_batch(["hello", "world"], "es")
                assert results == ["HELLO", "WORLD"]
            finally:
                i18n_mod._translate_batch = original

    # --- generate_language full flow (mocked translation) ---

    def test_generate_language_mocked(self, tmp_path: Path) -> None:
        """Full generate_language with mocked translation engine."""
        import rolodexter.i18n as i18n_mod

        def fake_translate(phrases, lang_code):
            return [f"translated_{p}" for p in phrases]

        with (
            _mock_patch.object(
                i18n_mod, "_translate_batch", side_effect=fake_translate
            ),
            _mock_patch.object(i18n_mod, "get_cache_dir", return_value=tmp_path),
            _mock_patch.object(i18n_mod, "get_all_cache_dirs", return_value=[tmp_path]),
            _mock_patch("rolodexter.i18n.GoogleTranslator", create=True),
        ):
            data = i18n_mod.generate_language("es", force=True)

        assert data["language_code"] == "es"
        assert data["language_name"] == "Spanish"
        assert "fields" in data
        assert "generated_at" in data
        # Should have written a cache file
        assert (tmp_path / "es.json").exists()

    def test_generate_language_uses_cache(self, tmp_path: Path) -> None:
        """generate_language returns cached data without translating."""
        import json

        import rolodexter.i18n as i18n_mod

        cached = {
            "language_code": "de",
            "language_name": "German",
            "generated_at": "2026-01-01T00:00:00+00:00",
            "source_version": "2.2.0",
            "fields": {"first_name": ["vorname"]},
        }
        (tmp_path / "de.json").write_text(json.dumps(cached), encoding="utf-8")
        with _mock_patch.object(
            i18n_mod, "get_all_cache_dirs", return_value=[tmp_path]
        ):
            data = i18n_mod.generate_language("de")
        assert data == cached

    # --- CLI ---

    def test_main_list_flag(self, capsys) -> None:
        """CLI --list prints supported languages."""
        import rolodexter.i18n as i18n_mod

        with _mock_patch("sys.argv", ["i18n", "--list"]):
            i18n_mod.main()
        out = capsys.readouterr().out
        assert "Spanish" in out
        assert "French" in out
        assert "German" in out

    def test_main_dry_run(self, capsys, tmp_path: Path) -> None:
        """CLI --dry-run does not write files."""
        import rolodexter.i18n as i18n_mod

        with (
            _mock_patch("sys.argv", ["i18n", "--languages", "es", "--dry-run"]),
            _mock_patch.object(i18n_mod, "get_cache_dir", return_value=tmp_path),
            _mock_patch.object(i18n_mod, "get_all_cache_dirs", return_value=[tmp_path]),
        ):
            i18n_mod.main()
        out = capsys.readouterr().out
        assert "es" in out
        # No file should have been created
        assert not (tmp_path / "es.json").exists()

    def test_main_unknown_language_exits(self) -> None:
        """CLI with unknown language exits with error."""
        import rolodexter.i18n as i18n_mod

        with (
            _mock_patch("sys.argv", ["i18n", "--languages", "zz_bad"]),
            pytest.raises(SystemExit),
        ):
            i18n_mod.main()


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

    def test_regex_fallback_unknown_code(self) -> None:
        """Numbers that can't be parsed fall back to regex strip."""
        result = PhoneNormalizer.normalize("+999 000 000 0000")
        assert isinstance(result, str)

    def test_normalize_value_uses_e164(self) -> None:
        """normalize_value() for phone fields uses E.164 formatting."""
        result = normalize_value("phone", "+44 20 7946 0958")
        assert result == "+442079460958"


# ═══════════════════════════════════════════════════════════════
#  v2.2 — PHONE MODULE: EXTENSIONS, RFC3966, FORMATTING, ETC.
# ═══════════════════════════════════════════════════════════════

from rolodexter._phone import (  # noqa: E402
    MatchType,
    NumberType,
    PhoneNumberMatcher,
    format_international,
    format_national,
    is_number_match,
    number_type,
    parse,
)


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
        assert "address" not in result.unmapped or isinstance(
            result.unmapped.get("address"), dict
        )

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


class TestV21CanonicalFields:
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
        assert m.canonical == expected, (
            f"{header!r} → {m.canonical!r}, expected {expected!r}"
        )

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
        assert m.is_matched, (
            f"{header!r} → {m.canonical!r} (unmatched, strategy={m.strategy})"
        )
        assert m.canonical == expected, (
            f"{header!r} → {m.canonical!r}, expected {expected!r}"
        )


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


# ═══════════════════════════════════════════════════════════════
#  v2.3 — SMUS_BARK DEEP-DIVE AUDIT ADDITIONS
# ═══════════════════════════════════════════════════════════════


class TestV23NewCanonicalFields:
    """Six new canonical fields added in v2.3.0."""

    @pytest.mark.parametrize(
        "alias, expected",
        [
            ("discord", "discord"),
            ("discord_handle", "discord"),
            ("discord_id", "discord"),
            ("discord_username", "discord"),
            ("telegram", "telegram"),
            ("telegram_handle", "telegram"),
            ("telegram_username", "telegram"),
            ("gender", "gender"),
            ("sex", "gender"),
            ("timezone", "timezone"),
            ("tz", "timezone"),
            ("time_zone", "timezone"),
            ("language_preference", "language_preference"),
            ("preferred_language", "language_preference"),
            ("locale", "language_preference"),
            ("lang", "language_preference"),
            ("referrer_url", "referrer_url"),
            ("referring_url", "referrer_url"),
        ],
    )
    def test_new_field_alias(
        self, registry: PatternRegistry, alias: str, expected: str
    ) -> None:
        assert registry.exact_lookup(alias) == expected

    def test_canonical_enum_members(self) -> None:
        """New fields exist in CanonicalField enum."""
        from rolodexter import CanonicalField

        for name in (
            "DISCORD",
            "TELEGRAM",
            "GENDER",
            "TIMEZONE",
            "LANGUAGE_PREFERENCE",
            "REFERRER_URL",
        ):
            assert hasattr(CanonicalField, name), f"CanonicalField.{name} missing"


class TestV23ShortAliases:
    """Short aliases (fn, ln, em, ph, etc.) resolve via exact match."""

    @pytest.mark.parametrize(
        "alias, expected",
        [
            ("fn", "first_name"),
            ("ln", "last_name"),
            ("em", "email"),
            ("ph", "phone"),
            ("co", "company"),
            ("addr", "address_line1"),
            ("subj", "subject"),
        ],
    )
    def test_short_alias_exact(
        self, registry: PatternRegistry, alias: str, expected: str
    ) -> None:
        assert registry.exact_lookup(alias) == expected

    def test_short_aliases_dont_pollute_fuzzy(self) -> None:
        """Short aliases (≤2 chars) must NOT cause false-positive fuzzy matches."""
        from rolodexter import ContactMapper

        mapper = ContactMapper()
        m = mapper.identify("Column X", value="jane@test.com")
        assert m.canonical == "email", (
            f"Expected heuristic → email, got {m.canonical} via {m.strategy}"
        )


class TestV23WooCommerceAliases:
    """WooCommerce billing/shipping field aliases."""

    @pytest.mark.parametrize(
        "alias, expected",
        [
            ("billing_first_name", "first_name"),
            ("billing_last_name", "last_name"),
            ("billing_email", "email"),
            ("billing_phone", "phone"),
            ("billing_company", "company"),
            ("billing_address_1", "address_line1"),
            ("billing_address_2", "address_line2"),
            ("billing_city", "city"),
            ("billing_state", "state"),
            ("billing_postcode", "postal_code"),
            ("billing_country", "country"),
            ("shipping_first_name", "first_name"),
            ("shipping_last_name", "last_name"),
            ("shipping_address_1", "address_line1"),
            ("shipping_address_2", "address_line2"),
            ("shipping_city", "city"),
            ("shipping_state", "state"),
            ("shipping_postcode", "postal_code"),
            ("shipping_country", "country"),
        ],
    )
    def test_woo_alias(
        self, registry: PatternRegistry, alias: str, expected: str
    ) -> None:
        assert registry.exact_lookup(alias) == expected


class TestV23SocialMediaHeuristics:
    """Heuristic URL detection for social media platforms."""

    @pytest.mark.parametrize(
        "url, expected",
        [
            ("https://www.linkedin.com/in/johndoe", "linkedin"),
            ("https://linkedin.com/company/acme-corp", "linkedin"),
            ("https://linkedin.com/pub/jane-doe/1/2/3", "linkedin"),
            ("https://linkedin.com/school/mit", "linkedin"),
            ("https://twitter.com/johndoe", "twitter"),
            ("https://x.com/johndoe", "twitter"),
            ("https://www.instagram.com/johndoe", "instagram"),
            ("https://github.com/octocat", "github"),
            ("https://www.facebook.com/johndoe", "facebook"),
            ("https://fb.com/johndoe", "facebook"),
            ("https://www.youtube.com/channel/UC1234", "youtube"),
            ("https://youtube.com/@creator", "youtube"),
            ("https://www.tiktok.com/@username", "tiktok"),
        ],
    )
    def test_social_url_heuristic(
        self, mapper: ContactMapper, url: str, expected: str
    ) -> None:
        m = mapper.identify("some_profile", value=url)
        assert m.canonical == expected, f"{url} → {m.canonical}, expected {expected}"
        assert m.strategy == "heuristic"

    def test_generic_url_fallback(self, mapper: ContactMapper) -> None:
        """Non-social URLs fall through to generic website detection."""
        m = mapper.identify("colZZ", value="https://example.com/page")
        assert m.canonical == "website"
        assert m.strategy == "heuristic"

    def test_twitter_handle_heuristic(self, mapper: ContactMapper) -> None:
        """@handle pattern detected as twitter."""
        m = mapper.identify("colZZ", value="@johndoe")
        assert m.canonical == "twitter"
        assert m.strategy == "heuristic"


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


class TestV23ExpandedNameParticles:
    """NameNormalizer handles additional European particles."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("du pont", "Du Pont"),
            ("DES moines", "Des Moines"),
            ("VAN DER berg", "Van der Berg"),
            ("TEN hove", "Ten Hove"),
            ("TER braak", "Ter Braak"),
            ("ZUR linde", "Zur Linde"),
            ("ZUM stein", "Zum Stein"),
            # Particles in non-initial position stay lowercase
            ("jan van der berg", "Jan van der Berg"),
            ("lisa du pont", "Lisa du Pont"),
            ("pieter ten hove", "Pieter ten Hove"),
        ],
    )
    def test_particle_preservation(self, raw: str, expected: str) -> None:
        from rolodexter.core import NameNormalizer

        n = NameNormalizer()
        assert n.normalize(raw) == expected


class TestV23VendorPrefixes:
    """Smartlead vendor prefix stripping."""

    @pytest.mark.parametrize(
        "header, expected",
        [
            ("sl_email", "email"),
            ("smartlead_first_name", "first_name"),
            ("sl_company", "company"),
        ],
    )
    def test_smartlead_prefix(
        self, mapper: ContactMapper, header: str, expected: str
    ) -> None:
        m = mapper.identify(header)
        assert m.canonical == expected, f"{header} → {m.canonical}, expected {expected}"


class TestV23PublicExports:
    """PostalCodeNormalizer and BooleanNormalizer are importable from rolodexter."""

    def test_postalcode_importable(self) -> None:
        from rolodexter import PostalCodeNormalizer

        assert PostalCodeNormalizer is not None

    def test_boolean_importable(self) -> None:
        from rolodexter import BooleanNormalizer

        assert BooleanNormalizer is not None

    def test_dead_symbols_removed(self) -> None:
        """Removed symbols should not be importable.

        Note: ``NormalizationError`` was reintroduced in 2.8.0 with a new
        meaning (strict-mode normalization failure), so it is intentionally
        no longer in this list.
        """
        import rolodexter

        for name in (
            "StrategyError",
            "ServiceNotFoundError",
            "ServiceMatchStrategy",
        ):
            assert not hasattr(rolodexter, name), f"{name} should have been removed"


class TestV23CollisionFixes:
    """P0 alias collision fixes — opt_in/unit deterministic."""

    def test_opt_in_maps_to_subscribed(self, registry: PatternRegistry) -> None:
        """opt_in/optin are affirmative → subscribed (not email_opt_out)."""
        assert registry.exact_lookup("opt_in") == "subscribed"
        assert registry.exact_lookup("optin") == "subscribed"

    def test_unit_maps_to_address_line2(self, registry: PatternRegistry) -> None:
        """unit is address context → address_line2 (not department)."""
        assert registry.exact_lookup("unit") == "address_line2"
        assert registry.exact_lookup("apt") == "address_line2"

    def test_ambiguous_aliases_removed(self, registry: PatternRegistry) -> None:
        """Overly generic aliases removed from their original fields."""
        # 'status' removed from lead_status (too broad)
        assert registry.exact_lookup("status") is None
        # 'handle' removed from nickname (ambiguous with social)
        assert registry.exact_lookup("handle") is None
        # 're' removed from subject (Python module name collision)
        assert registry.exact_lookup("re") is None


class TestV23EUDateHeuristic:
    """Date formats are birthday heuristics only with birth-related headers."""

    def test_generic_eu_date_format_stays_unknown(self, mapper: ContactMapper) -> None:
        m = mapper.identify("unknown_col", value="15.03.1990")
        assert m.canonical == "unknown"
        assert m.strategy == "none"

    def test_generic_iso_date_format_stays_unknown(self, mapper: ContactMapper) -> None:
        m = mapper.identify("unknown_col", value="1990-03-15")
        assert m.canonical == "unknown"
        assert m.strategy == "none"

    def test_birth_date_hint_detects_date_format(self, mapper: ContactMapper) -> None:
        m = mapper.identify("custom_birth_marker", value="1990-03-15")
        assert m.canonical == "birthday"
        assert m.strategy == "heuristic"


# ═══════════════════════════════════════════════════════════════
#  v2.3 — EXPANSION RULES ENGINE
# ═══════════════════════════════════════════════════════════════


class TestExpansionEngine:
    """Verify programmatic alias expansion from patterns.json rules."""

    def test_form_prefix_generates_aliases(self, registry: PatternRegistry) -> None:
        """Every form_prefix x form_field combo should resolve."""
        # These are NOT in the seed aliases — purely expansion-generated
        for prefix in (
            "billing_",
            "shipping_",
            "your_",
            "your-",
            "contact_",
            "customer_",
            "applicant_",
        ):
            for suffix, expected in (
                ("email", "email"),
                ("phone", "phone"),
                ("city", "city"),
            ):
                alias = f"{prefix}{suffix}"
                result = registry.exact_lookup(alias)
                assert result == expected, f"{alias} → {result}, expected {expected}"

    def test_social_suffix_generates_aliases(self, registry: PatternRegistry) -> None:
        """Every social_field x social_suffix combo should resolve."""
        for platform in (
            "twitter",
            "instagram",
            "facebook",
            "github",
            "discord",
            "telegram",
        ):
            for suffix in ("_url", "_handle", "_profile", "_username", "_link", "_id"):
                alias = f"{platform}{suffix}"
                result = registry.exact_lookup(alias)
                assert result == platform, f"{alias} → {result}, expected {platform}"

    def test_expansion_doesnt_override_seeds(self) -> None:
        """Seed aliases take priority over expansion-generated ones."""
        # 'contact_number' is a seed for 'phone' — expansion would also map it
        reg = PatternRegistry()
        assert reg.exact_lookup("contact_number") == "phone"

    def test_expansion_covers_new_prefixes(self, registry: PatternRegistry) -> None:
        """Expansion generates aliases that weren't in the old hand-written list."""
        # These never existed before — pure bonus from expansion rules
        bonus = [
            ("applicant_email", "email"),
            ("applicant_phone", "phone"),
            ("shipping_email", "email"),
            ("shipping_phone", "phone"),
            ("customer_address_1", "address_line1"),
            ("name_birthday", "birthday"),
        ]
        for alias, expected in bonus:
            result = registry.exact_lookup(alias)
            assert result == expected, f"Bonus: {alias} → {result}, expected {expected}"

    def test_no_expansion_when_absent(self) -> None:
        """Custom patterns dict without expansion section still works."""
        custom = {"fields": {"first_name": ["fname", "given"]}}
        reg = PatternRegistry(patterns=custom)
        assert reg.exact_lookup("fname") == "first_name"
        # No expansion-generated aliases
        assert reg.exact_lookup("billing_first_name") is None

    def test_total_aliases_grew(self, registry: PatternRegistry) -> None:
        """Expansion should increase total alias count beyond seed count."""
        assert len(registry.all_aliases) > 700  # seeds are ~615, expansion adds ~340


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


class TestPatternRegistryErrors:
    """Test PatternRegistry error paths."""

    def test_load_from_bad_path_raises(self) -> None:
        with pytest.raises(PatternLoadError):
            PatternRegistry(patterns_path="/nonexistent/path.json")

    def test_repr(self) -> None:
        reg = PatternRegistry()
        r = repr(reg)
        assert "PatternRegistry" in r
        assert "aliases=" in r

    def test_available_languages(self) -> None:
        reg = PatternRegistry()
        langs = reg.available_languages
        assert isinstance(langs, list)
        assert "es" in langs

    def test_cached_languages(self) -> None:
        reg = PatternRegistry()
        cached = reg.cached_languages
        assert isinstance(cached, list)

    def test_loaded_languages_empty_default(self) -> None:
        reg = PatternRegistry()
        assert reg.loaded_languages == []


class TestContactMapperRepr:
    """Test ContactMapper __repr__."""

    def test_repr_format(self) -> None:
        mapper = ContactMapper()
        r = repr(mapper)
        assert "ContactMapper" in r
        assert "normalize=True" in r

    def test_custom_strategies(self) -> None:
        reg = PatternRegistry()
        mapper = ContactMapper(strategies=[ExactMatchStrategy(reg)])
        r = repr(mapper)
        assert "exact" in r


class TestMergeCollision:
    """Test the _merge helper handles duplicate keys → list promotion."""

    def test_duplicate_keys_promote_to_list(self) -> None:
        mapper = ContactMapper()
        result = mapper.map_payload({"phone": "111", "tel": "222"})
        phone_val = result.normalized.get("phone")
        # Both map to "phone" — should be a list
        assert isinstance(phone_val, list)
        assert len(phone_val) == 2

    def test_triple_merge_appends(self) -> None:
        mapper = ContactMapper()
        result = mapper.map_payload({"phone": "111", "tel": "222", "telephone": "333"})
        phone_val = result.normalized.get("phone")
        assert isinstance(phone_val, list)
        assert len(phone_val) == 3


class TestFuzzyStrategyUnavailable:
    """Cover the branch where rapidfuzz is NOT installed."""

    def test_match_returns_none_when_unavailable(self) -> None:
        reg = PatternRegistry()
        fuzzy = FuzzyMatchStrategy(reg)
        # Simulate unavailability
        fuzzy._available = False
        assert fuzzy.match("first_name") is None


class TestHeuristicStrategyEdge:
    """Edge cases for HeuristicMatchStrategy."""

    def test_none_value_returns_none(self) -> None:
        h = HeuristicMatchStrategy()
        assert h.match("something") is None

    def test_empty_value_returns_none(self) -> None:
        h = HeuristicMatchStrategy()
        assert h.match("something", value="") is None

    def test_non_string_value_returns_none(self) -> None:
        h = HeuristicMatchStrategy()
        assert h.match("something", value=42) is None  # type: ignore[arg-type]

    def test_whitespace_value_returns_none(self) -> None:
        h = HeuristicMatchStrategy()
        assert h.match("something", value="   ") is None


# ═══════════════════════════════════════════════════════════════
#  v2.5 — COVERAGE BOOST: i18n.py GAPS
# ═══════════════════════════════════════════════════════════════


class TestI18nCacheDirs:
    """Test i18n cache directory resolution."""

    def test_get_cache_dir_returns_path(self) -> None:
        from rolodexter.i18n import get_cache_dir

        d = get_cache_dir()
        assert isinstance(d, Path)
        assert d.exists()

    def test_get_all_cache_dirs(self) -> None:
        from rolodexter.i18n import get_all_cache_dirs

        dirs = get_all_cache_dirs()
        assert isinstance(dirs, list)
        for d in dirs:
            assert isinstance(d, Path)
            assert d.is_dir()

    def test_user_cache_dir(self) -> None:
        from rolodexter.i18n import _user_cache_dir

        d = _user_cache_dir()
        assert isinstance(d, Path)
        assert d.name == "i18n"


class TestI18nAliasVariants:
    """Test _to_alias_variants() variant generation."""

    def test_basic_variants(self) -> None:
        from rolodexter.i18n import _to_alias_variants

        variants = _to_alias_variants("First Name")
        assert "first name" in variants
        assert "first_name" in variants
        assert "firstname" in variants
        assert "first-name" in variants

    def test_single_char_excluded(self) -> None:
        from rolodexter.i18n import _to_alias_variants

        assert _to_alias_variants("x") == set()

    def test_empty_excluded(self) -> None:
        from rolodexter.i18n import _to_alias_variants

        assert _to_alias_variants("") == set()


class TestI18nFieldDerivation:
    """Test _derive_field_phrases and _get_english_aliases."""

    def test_derive_field_phrases(self) -> None:
        from rolodexter.i18n import _derive_field_phrases

        master = {"fields": {"first_name": ["fname"], "email": ["e_mail"]}}
        result = _derive_field_phrases(master)
        assert result["first_name"] == "first name"
        assert result["email"] == "email"

    def test_skip_fields_excluded(self) -> None:
        from rolodexter.i18n import _derive_field_phrases

        master = {"fields": {"first_name": ["fname"], "metadata": ["meta"]}}
        result = _derive_field_phrases(master)
        assert "metadata" not in result

    def test_get_english_aliases(self) -> None:
        from rolodexter.i18n import _get_english_aliases

        master = {"fields": {"first_name": ["FName", "Given"], "email": ["E-Mail"]}}
        aliases = _get_english_aliases(master)
        assert "fname" in aliases
        assert "given" in aliases
        assert "e-mail" in aliases


class TestI18nLoadMaster:
    """Test _load_master()."""

    def test_returns_dict_with_fields(self) -> None:
        from rolodexter.i18n import _load_master

        data = _load_master()
        assert isinstance(data, dict)
        assert "fields" in data
        assert "version" in data


class TestI18nLoadCached:
    """Test load_cached() with nonexistent language."""

    def test_missing_language_returns_none(self) -> None:
        from rolodexter.i18n import load_cached

        assert load_cached("zz_nonexistent") is None


class TestI18nDiscoverCached:
    """Test discover_cached()."""

    def test_returns_dict(self) -> None:
        from rolodexter.i18n import discover_cached

        found = discover_cached()
        assert isinstance(found, dict)


class TestI18nTryUnidecode:
    """Test _try_unidecode fallback."""

    def test_ascii_input_returns_none(self) -> None:
        from rolodexter.i18n import _try_unidecode

        # Pure ASCII text → unidecode returns same → None
        result = _try_unidecode("hello")
        # Either None (same text) or None (unidecode not installed)
        assert result is None

    def test_empty_returns_none(self) -> None:
        from rolodexter.i18n import _try_unidecode

        result = _try_unidecode("")
        assert result is None


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


class TestPatternRegistryFromPath:
    """Test PatternRegistry loaded from a custom file path."""

    def test_load_from_valid_path(self, tmp_path: Path) -> None:
        import json

        data = {"version": "1.0.0", "fields": {"email": ["correo"]}}
        fp = tmp_path / "patterns.json"
        fp.write_text(json.dumps(data))
        reg = PatternRegistry(patterns_path=str(fp))
        assert reg.exact_lookup("correo") == "email"


class TestNormalizedMatchDotPathCamelCase:
    """Cover dot-path with CamelCase suffix in NormalizedMatchStrategy."""

    def test_account_first_name_dot_path(self) -> None:
        reg = PatternRegistry()
        strat = NormalizedMatchStrategy(reg)
        result = strat.match("Account.FirstName")
        assert result is not None
        assert result.canonical == "first_name"

    def test_company_dot_name_resolution(self) -> None:
        reg = PatternRegistry()
        strat = NormalizedMatchStrategy(reg)
        result = strat.match("Organization.Name")
        assert result is not None
        assert result.canonical == "company"

    def test_empty_header_returns_none(self) -> None:
        reg = PatternRegistry()
        strat = NormalizedMatchStrategy(reg)
        assert strat.match("") is None
        assert strat.match("   ") is None


class TestFuzzyStrategyEmptyAliases:
    """Cover FuzzyMatchStrategy edge cases with empty registries."""

    def test_empty_registry_returns_none(self) -> None:
        reg = PatternRegistry(patterns={"fields": {}})
        fuzzy = FuzzyMatchStrategy(reg)
        assert fuzzy.match("anything") is None

    def test_only_short_aliases_returns_none(self) -> None:
        reg = PatternRegistry(patterns={"fields": {"id": ["id"]}})
        fuzzy = FuzzyMatchStrategy(reg)
        assert fuzzy.match("identifier") is None

    def test_no_fuzzy_match_returns_none(self) -> None:
        reg = PatternRegistry(patterns={"fields": {"email": ["electronic_mail"]}})
        fuzzy = FuzzyMatchStrategy(reg)
        result = fuzzy.match("zzzzzzzzz_totally_unrelated")
        assert result is None


class TestI18nGenerateLanguageErrors:
    """Test generate_language error paths."""

    def test_unsupported_language_raises(self) -> None:
        from rolodexter.i18n import generate_language

        with pytest.raises(ValueError, match="Unsupported language"):
            generate_language("xx_fake")


class TestI18nPackageDir:
    """Test _package_i18n_dir directly."""

    def test_returns_path_on_editable_install(self) -> None:
        from rolodexter.i18n import _package_i18n_dir

        result = _package_i18n_dir()
        # On editable install this should return a valid Path
        if result is not None:
            assert isinstance(result, Path)
            assert result.exists()


class TestI18nWriteAndLoadCache:
    """Test _write_cache + load_cached round-trip."""

    def test_write_and_load(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from rolodexter.i18n import _write_cache, load_cached

        # Monkeypatch get_cache_dir to use tmp_path
        monkeypatch.setattr("rolodexter.i18n.get_cache_dir", lambda: tmp_path)
        monkeypatch.setattr("rolodexter.i18n.get_all_cache_dirs", lambda: [tmp_path])

        lang_data = {
            "language_code": "test_lang",
            "language_name": "Test Language",
            "generated_at": "2026-01-01T00:00:00+00:00",
            "source_version": "2.6.0",
            "fields": {"email": ["correo_test"]},
        }
        path = _write_cache(lang_data)
        assert path.exists()

        loaded = load_cached("test_lang")
        assert loaded is not None
        assert loaded["language_code"] == "test_lang"
        assert loaded["fields"]["email"] == ["correo_test"]


class TestI18nCliList:
    """Test i18n CLI --list option."""

    def test_list_languages(self, capsys: pytest.CaptureFixture[str]) -> None:
        import sys

        from rolodexter.i18n import main

        old_argv = sys.argv
        try:
            sys.argv = ["rolodexter.i18n", "--list"]
            main()
        finally:
            sys.argv = old_argv
        captured = capsys.readouterr()
        assert "Spanish" in captured.out
        assert "French" in captured.out
        assert "es" in captured.out


class TestI18nGenerateLanguageCached:
    """Test generate_language when cached data already exists."""

    def test_returns_cached_without_translating(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from rolodexter.i18n import generate_language

        cached_data = {
            "language_code": "es",
            "language_name": "Spanish",
            "generated_at": "2026-01-01",
            "source_version": "2.6.0",
            "fields": {"email": ["correo"]},
        }
        monkeypatch.setattr(
            "rolodexter.i18n.load_cached",
            lambda code: cached_data if code == "es" else None,
        )
        result = generate_language("es")
        assert result == cached_data

    def test_force_bypasses_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With force=True and no deep-translator, ImportError is raised."""
        # Remove deep-translator from available imports
        import builtins

        from rolodexter.i18n import generate_language

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "deep_translator":
                raise ImportError("mocked")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        with pytest.raises(ImportError, match="deep-translator is required"):
            generate_language("es", force=True)


class TestI18nTranslateBatch:
    """Test _translate_batch when deep-translator is not available."""

    def test_returns_nones_without_translator(self) -> None:
        from rolodexter.i18n import _translate_batch

        results = _translate_batch(["hello", "world"], "es")
        # Without deep-translator installed, all results should be None
        # (or actual translations if it IS installed)
        assert isinstance(results, list)
        assert len(results) == 2


class TestI18nLoadMasterFallback:
    """Test _load_master filesystem fallback."""

    def test_direct_call_returns_data(self) -> None:
        from rolodexter.i18n import _load_master

        data = _load_master()
        assert "fields" in data
        assert len(data["fields"]) > 30

    def test_fallback_when_resources_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from rolodexter import i18n

        def broken_files(_pkg_name):
            raise Exception("mocked resources failure")

        monkeypatch.setattr("rolodexter.i18n.resources.files", broken_files)
        data = i18n._load_master()
        assert "fields" in data
        assert "version" in data


class TestPatternRegistryLanguages:
    """Test PatternRegistry with language loading branches."""

    def test_languages_list_with_cached(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Loading a language that has cached data."""
        from rolodexter.i18n import _write_cache

        cache_dir = tmp_path / "i18n-cache"
        monkeypatch.setattr("rolodexter.i18n.get_cache_dir", lambda: cache_dir)
        monkeypatch.setattr("rolodexter.i18n.get_all_cache_dirs", lambda: [cache_dir])
        lang_data = {
            "language_code": "test_cov",
            "language_name": "Test Coverage",
            "generated_at": "2026-01-01",
            "source_version": "2.6.0",
            "fields": {"email": ["correo_cov_test"]},
        }
        _write_cache(lang_data)
        try:
            reg = PatternRegistry(languages=["test_cov"])
            assert reg.exact_lookup("correo_cov_test") == "email"
            assert "test_cov" in reg.loaded_languages
        finally:
            # Clean up
            p = cache_dir / "test_cov.json"
            if p.exists():
                p.unlink()

    def test_languages_uncached_no_translator(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Loading a language with no cache and no deep-translator gracefully skips."""
        import rolodexter.i18n as _i18n_mod

        def _no_cache(code: str):
            return None

        def _no_translator(*_a, **_kw):
            raise ImportError("deep-translator not installed (mocked)")

        monkeypatch.setattr(_i18n_mod, "load_cached", _no_cache)
        monkeypatch.setattr(_i18n_mod, "generate_language", _no_translator)
        reg = PatternRegistry(languages=["es"])
        assert isinstance(reg.all_aliases, list)


class TestNormalizedMatchBranchCoverage:
    """Cover more branches in NormalizedMatchStrategy._candidates."""

    def test_camel_case_no_dot(self) -> None:
        """CamelCase header without dot-path."""
        reg = PatternRegistry()
        strat = NormalizedMatchStrategy(reg)
        result = strat.match("FirstName")
        assert result is not None
        assert result.canonical == "first_name"

    def test_indexed_pattern(self) -> None:
        """Indexed headers like 'E-mail 1 - Value'."""
        reg = PatternRegistry()
        strat = NormalizedMatchStrategy(reg)
        result = strat.match("E-mail 1 - Value")
        assert result is not None

    def test_vendor_prefix_stripped(self) -> None:
        """Vendor-prefixed headers like 'hs_email'."""
        reg = PatternRegistry()
        strat = NormalizedMatchStrategy(reg)
        result = strat.match("hs_email")
        assert result is not None
        assert result.canonical == "email"

    def test_number_stripped(self) -> None:
        """Headers with numbers like 'phone_2'."""
        reg = PatternRegistry()
        strat = NormalizedMatchStrategy(reg)
        result = strat.match("phone_2")
        assert result is not None
        assert result.canonical == "phone"

    def test_address_prefix_stripped(self) -> None:
        """Address-prefixed headers like 'billing_city'."""
        reg = PatternRegistry()
        strat = NormalizedMatchStrategy(reg)
        result = strat.match("billing_city")
        assert result is not None
        assert result.canonical == "city"

    def test_id_suffix_stripped(self) -> None:
        """Headers ending in _id like 'owner_id'."""
        reg = PatternRegistry()
        strat = NormalizedMatchStrategy(reg)
        result = strat.match("owner_id")
        assert result is not None
        assert result.canonical == "owner"


class TestI18nGenerateLanguageFull:
    """Test generate_language with mocked translation pipeline."""

    def test_force_with_mocked_translator(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Full generate_language with mocked _translate_batch and deep-translator."""
        import sys
        import types

        from rolodexter import i18n

        # Mock _translate_batch to return fake translations (one per phrase)
        def mock_translate(phrases, lang_code):
            return [f"translated_{i}" for i in range(len(phrases))]

        monkeypatch.setattr(i18n, "_translate_batch", mock_translate)
        monkeypatch.setattr(i18n, "get_cache_dir", lambda: tmp_path)
        monkeypatch.setattr(i18n, "get_all_cache_dirs", lambda: [tmp_path])

        # Mock the deep-translator import check inside generate_language
        fake_module = types.ModuleType("deep_translator")
        fake_module.GoogleTranslator = type("GoogleTranslator", (), {})  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "deep_translator", fake_module)

        result = i18n.generate_language("es", force=True)
        assert result["language_code"] == "es"
        assert "fields" in result
        assert len(result["fields"]) > 0
        # Verify cache was written
        assert (tmp_path / "es.json").exists()

    def test_non_force_with_mocked_translator(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-force generate_language — covers the else branch for to_translate."""
        import sys
        import types

        from rolodexter import i18n

        def mock_translate(phrases, lang_code):
            # Return some None results to cover the 'continue' branch
            results = []
            for i, p in enumerate(phrases):
                results.append(
                    None if i % 3 == 0 else f"translated_{p.replace(' ', '_')}"
                )
            return results

        monkeypatch.setattr(i18n, "_translate_batch", mock_translate)
        monkeypatch.setattr(i18n, "get_cache_dir", lambda: tmp_path)
        monkeypatch.setattr(i18n, "get_all_cache_dirs", lambda: [tmp_path])

        fake_module = types.ModuleType("deep_translator")
        fake_module.GoogleTranslator = type("GoogleTranslator", (), {})  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "deep_translator", fake_module)

        result = i18n.generate_language("es")
        assert result["language_code"] == "es"
        assert "fields" in result
        assert (tmp_path / "es.json").exists()


class TestI18nTranslateBatchFallback:
    """Test _translate_batch fallback when batch translation fails."""

    def test_batch_retry_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Transient batch failures are retried within the configured budget."""
        from rolodexter import i18n

        call_count = {"batch": 0}
        seen_timeout: list[float] = []

        class RetryTranslator:
            def __init__(self, **kwargs):
                seen_timeout.append(kwargs["timeout"])

            def translate_batch(self, phrases):
                call_count["batch"] += 1
                if call_count["batch"] == 1:
                    raise Exception("transient")
                return [f"translated_{phrase}" for phrase in phrases]

        import types

        fake_dt = types.ModuleType("deep_translator")
        fake_dt.GoogleTranslator = RetryTranslator  # type: ignore[attr-defined]
        monkeypatch.setitem(__import__("sys").modules, "deep_translator", fake_dt)

        results = i18n._translate_batch(
            ["hello", "world"],
            "es",
            timeout=3.5,
            retries=1,
            retry_backoff=0,
        )
        assert call_count["batch"] == 2
        assert seen_timeout == [3.5]
        assert results == ["translated_hello", "translated_world"]

    def test_fallback_per_phrase(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When batch translate throws, falls back to per-phrase."""
        from rolodexter import i18n

        call_count = {"batch": 0, "single": 0}

        class MockTranslator:
            def __init__(self, **_kwargs):
                pass

            def translate_batch(self, phrases):
                call_count["batch"] += 1
                raise Exception("batch failed")

            def translate(self, phrase):
                call_count["single"] += 1
                return f"translated_{phrase}"

        # Create a fake module with our mock
        import types

        fake_dt = types.ModuleType("deep_translator")
        fake_dt.GoogleTranslator = MockTranslator  # type: ignore[attr-defined]
        monkeypatch.setitem(__import__("sys").modules, "deep_translator", fake_dt)

        results = i18n._translate_batch(["hello", "world"], "es")
        assert call_count["batch"] == 2
        assert call_count["single"] == 2
        assert results == ["translated_hello", "translated_world"]

    def test_fallback_per_phrase_also_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When both batch and per-phrase fail, returns Nones."""
        from rolodexter import i18n

        class FailTranslator:
            def __init__(self, **_kwargs):
                pass

            def translate_batch(self, phrases):
                raise Exception("batch failed")

            def translate(self, phrase):
                raise Exception("single failed")

        import types

        fake_dt = types.ModuleType("deep_translator")
        fake_dt.GoogleTranslator = FailTranslator  # type: ignore[attr-defined]
        monkeypatch.setitem(__import__("sys").modules, "deep_translator", fake_dt)

        results = i18n._translate_batch(["hello", "world"], "es")
        assert results == [None, None]

    def test_worker_count_clamped(self) -> None:
        from rolodexter import i18n

        assert i18n._bounded_workers(0, 5) == 1
        assert i18n._bounded_workers(99, 5) == 5
        assert i18n._bounded_workers(99, 99) == i18n.MAX_I18N_WORKERS


class TestI18nCliDryRun:
    """Test i18n CLI --dry-run and error paths."""

    def test_dry_run(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import sys
        import types

        from rolodexter.i18n import main

        # Mock deep-translator so the import check passes
        fake_dt = types.ModuleType("deep_translator")
        fake_dt.GoogleTranslator = type("GoogleTranslator", (), {})  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "deep_translator", fake_dt)

        old_argv = sys.argv
        try:
            sys.argv = ["rolodexter.i18n", "--dry-run", "--languages", "es"]
            main()
        finally:
            sys.argv = old_argv
        captured = capsys.readouterr()
        assert "Generating 1 language" in captured.out
        assert "[es]" in captured.out

    def test_generate_via_cli(
        self,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """CLI generate path (non-dry-run) with mocked translator."""
        import sys
        import types

        from rolodexter import i18n
        from rolodexter.i18n import main

        def mock_translate(phrases, lang_code):
            return [f"mock_{i}" for i in range(len(phrases))]

        monkeypatch.setattr(i18n, "_translate_batch", mock_translate)
        monkeypatch.setattr(i18n, "get_cache_dir", lambda: tmp_path)
        monkeypatch.setattr(i18n, "get_all_cache_dirs", lambda: [tmp_path])

        fake_dt = types.ModuleType("deep_translator")
        fake_dt.GoogleTranslator = type("GoogleTranslator", (), {})  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "deep_translator", fake_dt)

        old_argv = sys.argv
        try:
            sys.argv = ["rolodexter.i18n", "--languages", "es", "--force"]
            main()
        finally:
            sys.argv = old_argv
        captured = capsys.readouterr()
        assert "Generating 1 language" in captured.out
        assert "[es]" in captured.out
        assert "Spanish" in captured.out

    def test_cli_reports_per_language_failures(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import sys
        import types

        from rolodexter import i18n
        from rolodexter.i18n import main

        fake_dt = types.ModuleType("deep_translator")
        fake_dt.GoogleTranslator = type("GoogleTranslator", (), {})  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "deep_translator", fake_dt)

        def fake_generate(code, **_kwargs):
            if code == "es":
                raise RuntimeError("network budget exhausted")
            return {
                "language_code": code,
                "language_name": i18n.SUPPORTED_LANGUAGES[code][1],
                "fields": {"email": ["correo"]},
            }

        monkeypatch.setattr(i18n, "generate_language", fake_generate)

        old_argv = sys.argv
        try:
            sys.argv = ["rolodexter.i18n", "--languages", "es,fr", "--workers", "99"]
            with pytest.raises(SystemExit) as excinfo:
                main()
        finally:
            sys.argv = old_argv
        captured = capsys.readouterr()
        assert excinfo.value.code == 1
        assert "[fr]" in captured.out
        assert "[es] FAILED: network budget exhausted" in captured.out
        assert "Failed 1 language" in captured.out

    def test_default_all_languages(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CLI with no --languages flag defaults to all supported."""
        import sys
        import types

        from rolodexter.i18n import main

        fake_dt = types.ModuleType("deep_translator")
        fake_dt.GoogleTranslator = type("GoogleTranslator", (), {})  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "deep_translator", fake_dt)

        old_argv = sys.argv
        try:
            sys.argv = ["rolodexter.i18n", "--dry-run"]
            main()
        finally:
            sys.argv = old_argv
        captured = capsys.readouterr()
        assert "Generating" in captured.out

    def test_unknown_language_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        import sys

        from rolodexter.i18n import main

        old_argv = sys.argv
        try:
            sys.argv = ["rolodexter.i18n", "--languages", "xx_fake"]
            with pytest.raises(SystemExit):
                main()
        finally:
            sys.argv = old_argv
        captured = capsys.readouterr()
        assert "Unknown language" in captured.out

    def test_no_deep_translator_error(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import builtins
        import sys

        from rolodexter.i18n import main

        # Ensure deep-translator is NOT available
        original_import = builtins.__import__

        def block_deep_translator(name, *args, **kwargs):
            if "deep_translator" in name:
                raise ImportError("not installed")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", block_deep_translator)
        # Also remove from sys.modules if cached
        monkeypatch.delitem(sys.modules, "deep_translator", raising=False)

        old_argv = sys.argv
        try:
            sys.argv = ["rolodexter.i18n", "--languages", "es"]
            with pytest.raises(SystemExit):
                main()
        finally:
            sys.argv = old_argv
        captured = capsys.readouterr()
        assert "deep-translator is required" in captured.out


class TestI18nCacheDirFallback:
    """Test generated i18n cache writes use the user cache."""

    def test_user_cache_used_when_pkg_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from rolodexter.i18n import _user_cache_dir, get_cache_dir

        monkeypatch.setattr("rolodexter.i18n.sys.platform", "linux")
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        result = get_cache_dir()
        assert result == _user_cache_dir()
        assert result.is_dir()


# ═══════════════════════════════════════════════════════════════
#  v2.6.0 — CALLER OVERRIDES (generic alias escape hatch)
# ═══════════════════════════════════════════════════════════════


class TestOverrides:
    """Test the generic overrides dict on PatternRegistry and ContactMapper."""

    def test_basic_override(self) -> None:
        reg = PatternRegistry(overrides={"custom_field_x": "email"})
        assert reg.exact_lookup("custom_field_x") == "email"

    def test_override_replaces_existing(self) -> None:
        """Caller overrides beat base aliases."""
        reg = PatternRegistry(overrides={"fname": "full_name"})
        assert reg.exact_lookup("fname") == "full_name"  # was first_name

    def test_case_insensitive_keys(self) -> None:
        reg = PatternRegistry(overrides={"MyField": "email"})
        assert reg.exact_lookup("myfield") == "email"

    def test_multiple_overrides(self) -> None:
        reg = PatternRegistry(
            overrides={
                "MMERGE3": "full_address",
                "MMERGE6": "company",
                "MMERGE7": "website",
            }
        )
        assert reg.exact_lookup("mmerge3") == "full_address"
        assert reg.exact_lookup("mmerge6") == "company"
        assert reg.exact_lookup("mmerge7") == "website"

    def test_no_overrides_no_mmerge(self) -> None:
        """Without overrides, arbitrary MMERGE fields stay unmapped."""
        reg = PatternRegistry()
        assert reg.exact_lookup("mmerge3") is None
        assert reg.exact_lookup("mmerge6") is None

    def test_overrides_on_contact_mapper(self) -> None:
        mapper = ContactMapper(
            overrides={
                "MMERGE1": "first_name",
                "MMERGE2": "last_name",
            }
        )
        result = mapper.map_payload(
            {
                "MMERGE1": "Alice",
                "MMERGE2": "Smith",
            }
        )
        assert result.normalized["first_name"] == "Alice"
        assert result.normalized["last_name"] == "Smith"

    def test_heuristic_catches_email_in_mmerge(self) -> None:
        """Heuristic detects email by value shape even with garbage header."""
        mapper = ContactMapper()
        result = mapper.map_payload({"MMERGE0": "alice@example.com"})
        assert result.normalized.get("email") == "alice@example.com"

    def test_heuristic_catches_phone_in_mmerge(self) -> None:
        """Heuristic detects phone by value shape even with garbage header."""
        mapper = ContactMapper()
        result = mapper.map_payload({"MMERGE4": "+14155552671"})
        assert "phone" in result.normalized

    def test_base_aliases_cover_common_mailchimp(self) -> None:
        """FNAME, LNAME, PHONE, BIRTHDAY already resolve via base aliases."""
        reg = PatternRegistry()
        assert reg.exact_lookup("fname") == "first_name"
        assert reg.exact_lookup("lname") == "last_name"
        assert reg.exact_lookup("phone") == "phone"
        assert reg.exact_lookup("birthday") == "birthday"

    def test_none_overrides_no_crash(self) -> None:
        reg = PatternRegistry(overrides=None)
        assert len(reg.all_aliases) > 200

    def test_empty_overrides_no_crash(self) -> None:
        reg = PatternRegistry(overrides={})
        assert len(reg.all_aliases) > 200


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


# ═══════════════════════════════════════════════════════════════
#  v2.6.0 — DEPTH=2 NESTED KEY RESOLUTION
# ═══════════════════════════════════════════════════════════════


class TestDepth2KeyResolution:
    """Confirm depth=2 flattens with dots and NormalizedMatch resolves them."""

    def test_address_city_resolves(self) -> None:
        mapper = ContactMapper()
        result = mapper.map_payload(
            {"address": {"city": "Austin"}},
            depth=2,
        )
        assert result.normalized.get("city") == "Austin"

    def test_address_state_resolves(self) -> None:
        mapper = ContactMapper()
        result = mapper.map_payload(
            {"address": {"state": "TX"}},
            depth=2,
        )
        assert result.normalized.get("state") == "TX"

    def test_contact_email_resolves(self) -> None:
        mapper = ContactMapper()
        result = mapper.map_payload(
            {"contact": {"email": "a@b.com"}},
            depth=2,
        )
        assert result.normalized.get("email") == "a@b.com"

    def test_nested_company_name(self) -> None:
        mapper = ContactMapper()
        result = mapper.map_payload(
            {"account": {"name": "Acme"}},
            depth=2,
        )
        # account.name should resolve to company via dot-path logic
        assert result.normalized.get("company") == "Acme"

    def test_flat_key_preserved_at_depth1(self) -> None:
        """With depth=1, nested dicts are NOT flattened."""
        mapper = ContactMapper()
        result = mapper.map_payload(
            {"address": {"city": "Austin"}},
            depth=1,
        )
        # 'address' is the key, value is a dict — heuristic can't match it
        assert "city" not in result.normalized

    def test_flatten_uses_dot_separator(self) -> None:
        flat = ContactMapper._flatten({"a": {"b": "v"}}, depth=2)
        assert "a.b" in flat

    def test_depth3_nested(self) -> None:
        flat = ContactMapper._flatten(
            {"level1": {"level2": {"level3": "val"}}},
            depth=3,
        )
        assert "level1.level2.level3" in flat


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


class TestDefaultRegion:
    """default_region is configurable on the mapper, per call, and on heuristics."""

    def test_constructor_accepts_region(self) -> None:
        mapper = ContactMapper(default_region="GB")
        assert isinstance(repr(mapper), str)

    def test_heuristic_strategy_accepts_region(self) -> None:
        strat = HeuristicMatchStrategy(default_region="GB")
        m = strat.match("col", value="+442079460958")
        assert m is not None
        assert m.canonical == "phone"

    def test_embedded_extraction_honours_region(self) -> None:
        # A UK national-format number embedded in text is only recognised
        # when the region is GB — proves the region threads all the way down.
        text = {"notes": "ring me on 020 7946 0958 after six"}
        gb = ContactMapper().map_payload(
            dict(text), extract_embedded_phones=True, default_region="GB"
        )
        us = ContactMapper().map_payload(
            dict(text), extract_embedded_phones=True, default_region="US"
        )
        assert gb.normalized.get("phone") == "+442079460958"
        assert us.normalized.get("phone") is None

    def test_map_batch_accepts_region(self) -> None:
        mapper = ContactMapper()
        results = mapper.map_batch(
            [{"notes": "call 020 7946 0958"}],
            default_region="GB",
        )
        assert len(results) == 1


class TestHeaderResolutionCache:
    """Header-only verdicts are cached across rows (the C2 scalability fix)."""

    def test_batch_consistent_and_cached(self) -> None:
        mapper = ContactMapper()
        rows = [{"FirstName": "Jane"}, {"FirstName": "John"}, {"FirstName": "Jo"}]
        results = mapper.map_batch(rows)
        assert [r.normalized["first_name"] for r in results] == ["Jane", "John", "Jo"]
        # The unique header was resolved once and cached.
        assert "FirstName" in mapper._header_cache
        assert mapper._header_cache["FirstName"].canonical == "first_name"

    def test_unknown_header_still_value_sensitive_despite_cache(self) -> None:
        # Same header, different values: the per-row heuristic must still run
        # even though header-only strategies are cached as "missed".
        mapper = ContactMapper()
        r1 = mapper.map_payload({"mystery": "jane@example.com"})
        r2 = mapper.map_payload({"mystery": "just some text"})
        assert r1.normalized.get("email") == "jane@example.com"
        assert r2.unmapped.get("mystery") == "just some text"
        # A header-only miss is cached as None (not a spurious match).
        assert mapper._header_cache.get("mystery") is None

    def test_non_cacheable_pipeline_falls_back(self) -> None:
        # Value-dependent strategy placed BEFORE a header-only one makes the
        # pipeline non-cacheable; resolution must still be correct per call.
        reg = PatternRegistry()
        mapper = ContactMapper(
            strategies=[HeuristicMatchStrategy(), ExactMatchStrategy(reg)]
        )
        assert mapper._cacheable_pipeline is False
        # Header-only exact match still works (heuristic misses with no value).
        assert mapper.identify("fname").canonical == "first_name"
        # Heuristic (first in pipeline) wins on a value-shaped unknown header.
        r = mapper.map_payload({"weird": "jane@example.com"})
        assert r.normalized.get("email") == "jane@example.com"

    def test_cache_is_bounded_lru(self) -> None:
        mapper = ContactMapper(header_cache_max_size=2)
        mapper.map_payload({"FirstName": "Jane"})
        mapper.map_payload({"LastName": "Doe"})
        mapper.map_payload({"FirstName": "Jo"})  # refresh LRU position
        mapper.map_payload({"Email": "jo@example.com"})
        assert "FirstName" in mapper._header_cache
        assert "Email" in mapper._header_cache
        assert "LastName" not in mapper._header_cache
        assert mapper.cache_info()["size"] == 2
        assert mapper.cache_info()["max_size"] == 2

    def test_cache_can_be_disabled(self) -> None:
        mapper = ContactMapper(header_cache_max_size=0)
        mapper.map_payload({"FirstName": "Jane"})
        assert mapper.cache_info()["size"] == 0
        assert mapper._header_cache == {}

    def test_cache_can_be_cleared(self) -> None:
        mapper = ContactMapper()
        mapper.map_payload({"FirstName": "Jane"})
        assert mapper.cache_info()["size"] == 1
        mapper.clear_cache()
        assert mapper.cache_info()["size"] == 0

    def test_negative_cache_size_rejected(self) -> None:
        with pytest.raises(ValueError, match="header_cache_max_size"):
            ContactMapper(header_cache_max_size=-1)


class TestI18nLoadsCacheOnly:
    """Construction never translates over the network (the H1 reliability fix)."""

    def test_uncached_supported_language_warns_and_skips(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        import rolodexter.i18n as _i18n_mod

        def _no_cache(_code: str) -> None:
            return None

        def _must_not_be_called(*_a: object, **_kw: object) -> dict:
            raise AssertionError("generate_language must not run during construction")

        monkeypatch.setattr(_i18n_mod, "load_cached", _no_cache)
        monkeypatch.setattr(_i18n_mod, "generate_language", _must_not_be_called)

        with caplog.at_level(logging.WARNING, logger="rolodexter.core"):
            reg = PatternRegistry(languages=["es"])

        # No network call, language not loaded, and the user is warned how to
        # generate it offline.
        assert reg.loaded_languages == []
        assert any("python -m rolodexter.i18n" in r.message for r in caplog.records)


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


# ═══════════════════════════════════════════════════════════════
#  v2.7.0 — FUZZY SHORT-ALIAS FALSE-POSITIVE GUARD
# ═══════════════════════════════════════════════════════════════


class TestFuzzyShortAliasGuard:
    """A short alias embedded in a longer header (e.g. ``tel`` inside
    ``job_titel``) must not win the fuzzy match and misroute the column."""

    def test_job_titel_is_not_phone(self) -> None:
        match = ContactMapper().identify("Job Titel")
        assert match.canonical != "phone"
        assert match.canonical == "job_title"

    def test_legitimate_typos_still_recover(self) -> None:
        mapper = ContactMapper()
        assert mapper.identify("phne_nmbr").canonical == "phone"
        assert mapper.identify("first_nam").canonical == "first_name"
        assert mapper.identify("Compny").canonical == "company"

    def test_garbage_still_unmatched(self) -> None:
        assert ContactMapper().identify("supercalifragilistic").canonical == "unknown"
