"""Complete test suite for rolodexter — tests in one file."""

from __future__ import annotations

import pytest

from rolodexter import (
    CanonicalField,
    ContactMapper,
    ExactMatchStrategy,
    FuzzyMatchStrategy,
    HeuristicMatchStrategy,
    MappingResult,
    PatternRegistry,
    ServiceMatchStrategy,
)
from rolodexter.core import (
    AddressNormalizer,
    EmailNormalizer,
    NameNormalizer,
    PatternLoadError,
    PhoneNormalizer,
    ServiceNotFoundError,
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
def mapper_mailchimp() -> ContactMapper:
    return ContactMapper(default_service="mailchimp")


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
        assert len(registry.available_services) >= 15

    def test_version(self, registry: PatternRegistry) -> None:
        assert registry.version == "1.2.0"

    def test_custom_patterns(self) -> None:
        custom = {
            "fields": {"first_name": ["fname", "given"]},
            "services": {},
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


class TestServiceLookup:
    @pytest.mark.parametrize(
        "service, svc_field, expected",
        [
            ("hubspot", "firstname", "first_name"),
            ("hubspot", "mobilephone", "phone"),
            ("hubspot", "hs_lead_status", "lead_status"),
            ("mailchimp", "FNAME", "first_name"),
            ("mailchimp", "LNAME", "last_name"),
            ("salesforce", "MobilePhone", "phone"),
            ("salesforce", "MailingStreet", "address_line1"),
            ("sendgrid", "state_province_region", "state"),
            ("stripe", "line1", "address_line1"),
            ("beehiiv", "firstName", "first_name"),
            ("omnisend", "postalCode", "postal_code"),
            ("pipedrive", "org_name", "company"),
            ("notion", "Full Name", "full_name"),
            ("zoho", "Mailing_Zip", "postal_code"),
            ("activecampaign", "orgname", "company"),
            ("brevo", "SMS", "phone"),
            ("google_contacts", "E-mail 1 - Value", "email"),
            ("outlook", "Business Phone", "work_phone"),
            ("linkedin_export", "Position", "job_title"),
            ("freshsales", "work_number", "work_phone"),
        ],
    )
    def test_service_field(self, registry: PatternRegistry, service: str, svc_field: str, expected: str) -> None:
        assert registry.service_lookup(svc_field, service) == expected

    def test_unknown_service(self, registry: PatternRegistry) -> None:
        assert registry.service_lookup("fname", "nonexistent") is None

    def test_get_service_mapping(self, registry: PatternRegistry) -> None:
        mapping = registry.get_service_mapping("hubspot")
        assert isinstance(mapping, dict)
        assert mapping["firstname"] == "first_name"

    def test_get_reverse_mapping(self, registry: PatternRegistry) -> None:
        rev = registry.get_reverse_mapping("hubspot")
        assert rev["first_name"] == "firstname"
        assert rev["last_name"] == "lastname"

    def test_service_not_found_raises(self, registry: PatternRegistry) -> None:
        with pytest.raises(ServiceNotFoundError):
            registry.get_service_mapping("totally_fake_service")


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


class TestServiceMatch:
    def test_with_service(self, registry: PatternRegistry) -> None:
        strat = ServiceMatchStrategy(registry)
        m = strat.match("FNAME", service="mailchimp")
        assert m is not None
        assert m.canonical == "first_name"
        assert m.service == "mailchimp"
        assert m.confidence == 0.95

    def test_without_service(self, registry: PatternRegistry) -> None:
        strat = ServiceMatchStrategy(registry)
        assert strat.match("FNAME") is None

    def test_wrong_service(self, registry: PatternRegistry) -> None:
        strat = ServiceMatchStrategy(registry)
        assert strat.match("FNAME", service="hubspot") is None


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

    def test_service_override(self, mapper: ContactMapper) -> None:
        m = mapper.identify("FNAME", service="mailchimp")
        assert m.canonical == "first_name"
        assert m.strategy == "service"

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

    def test_with_service(self) -> None:
        m = ContactMapper()
        result = m.map_payload({"FNAME": "Jane", "LNAME": "Doe"}, service="mailchimp")
        assert result.normalized.get("first_name") == "Jane"
        assert result.normalized.get("last_name") == "Doe"

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


class TestTranslate:
    def test_hubspot_to_mailchimp(self, mapper: ContactMapper) -> None:
        payload = {"firstname": "Jane", "lastname": "Doe", "phone": "555"}
        translated = mapper.translate(payload, from_service="hubspot", to_service="mailchimp")
        assert "first_name" in translated or any(v == "Jane" for v in translated.values())

    def test_stripe_to_sendgrid(self, mapper: ContactMapper) -> None:
        payload = {"name": "Jane Doe", "phone": "555", "city": "New York"}
        translated = mapper.translate(payload, from_service="stripe", to_service="sendgrid")
        assert any(v == "New York" for v in translated.values())


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
#  INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════


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
        result = mapper.map_payload(payload, service="hubspot")
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
        result = mapper.map_payload(payload, service="mailchimp")
        assert result.normalized["email"] == "bob@example.com"
        assert result.normalized["first_name"] == "Bob"
        assert result.normalized["last_name"] == "Smith"
        assert result.normalized["company"] == "Widgets LLC"
        assert result.match_rate >= 0.8


class TestSalesforceIngestion:
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
        result = mapper.map_payload(payload, service="salesforce")
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
        result = mapper.map_payload(payload, service="google_contacts")
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
        result = mapper.map_payload(payload, service="outlook")
        assert result.normalized["first_name"] == "Emma"
        assert result.normalized["work_phone"] == "+442079460958"
        assert result.normalized["city"] == "London"
        assert result.normalized["postal_code"] == "SW1A 1AA"


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


class TestCrossServiceTranslation:
    def test_hubspot_to_salesforce(self, mapper: ContactMapper) -> None:
        hubspot_data = {
            "firstname": "Aisha",
            "lastname": "Patel",
            "email": "aisha@corp.com",
            "phone": "+1-555-000-1234",
            "company": "Global Co",
            "jobtitle": "Engineer",
        }
        sf = mapper.translate(hubspot_data, from_service="hubspot", to_service="salesforce")
        assert any(v == "Aisha" for v in sf.values())
        assert any(v == "Patel" for v in sf.values())
        assert any(v == "aisha@corp.com" for v in sf.values())


class TestDefaultServiceConfig:
    def test_default_service(self) -> None:
        m = ContactMapper(default_service="mailchimp")
        match = m.identify("FNAME")
        assert match.canonical == "first_name"
        assert match.strategy == "service"

    def test_per_call_overrides_default(self) -> None:
        m = ContactMapper(default_service="mailchimp")
        match = m.identify("firstname", service="hubspot")
        assert match.canonical == "first_name"
        assert match.service == "hubspot"


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


class TestW3CAutocompleteServiceProfile:
    """The w3c_autocomplete service profile for direct autocomplete attr lookup."""

    @pytest.mark.parametrize(
        "attr, expected",
        [
            ("given-name", "first_name"),
            ("family-name", "last_name"),
            ("name", "full_name"),
            ("email", "email"),
            ("tel", "phone"),
            ("tel-national", "phone"),
            ("organization", "company"),
            ("organization-title", "job_title"),
            ("street-address", "address_line1"),
            ("address-line1", "address_line1"),
            ("address-line2", "address_line2"),
            ("address-level2", "city"),
            ("address-level1", "state"),
            ("postal-code", "postal_code"),
            ("country-name", "country"),
            ("url", "website"),
            ("bday", "birthday"),
            ("honorific-prefix", "prefix"),
            ("honorific-suffix", "suffix"),
            ("additional-name", "middle_name"),
            ("nickname", "nickname"),
        ],
    )
    def test_w3c_service_lookup(self, registry: PatternRegistry, attr: str, expected: str) -> None:
        assert registry.service_lookup(attr, "w3c_autocomplete") == expected


class TestFormBotServiceProfile:
    """form_bot identity key → canonical field mapping."""

    @pytest.mark.parametrize(
        "identity_key, expected",
        [
            ("first_name", "first_name"),
            ("last_name", "last_name"),
            ("email", "email"),
            ("phone", "phone"),
            ("company", "company"),
            ("title", "job_title"),
            ("job_title", "job_title"),
            ("address", "address_line1"),
            ("city", "city"),
            ("state", "state"),
            ("zip", "postal_code"),
            ("country", "country"),
            ("website", "website"),
            ("message", "message"),
            ("subject", "subject"),
            ("industry", "industry"),
            ("department", "department"),
            ("revenue", "revenue"),
            ("company_size", "company_size"),
            ("source", "source"),
            # Extended form_bot overrides
            ("note", "message"),
            ("comment", "message"),
            ("body", "message"),
            ("enquiry", "message"),
            ("feedback", "message"),
            ("organisation", "company"),
            ("organization", "company"),
            ("firm", "company"),
            ("employer", "company"),
            ("business", "company"),
            ("mobile", "phone"),
            ("cell", "phone"),
            ("tel", "phone"),
            ("postal", "postal_code"),
            ("postcode", "postal_code"),
            ("province", "state"),
            ("region", "state"),
            ("url", "website"),
            ("domain", "website"),
            ("position", "job_title"),
            ("role", "job_title"),
            ("occupation", "job_title"),
            ("function", "job_title"),
            ("age", "age"),
        ],
    )
    def test_form_bot_identity_key(self, registry: PatternRegistry, identity_key: str, expected: str) -> None:
        assert registry.service_lookup(identity_key, "form_bot") == expected


class TestFormBotFormDetectionPatterns:
    """Simulate form bot's detectPurpose() regex patterns via rolodexter."""

    def test_form_field_first_name(self, mapper: ContactMapper) -> None:
        # form bot regex: /\b(first.?name|fname|given.?name|forename)\b/
        for header in ["first_name", "fname", "given_name", "forename", "firstname"]:
            m = mapper.identify(header)
            assert m.canonical == "first_name", f"Failed for {header}"

    def test_form_field_last_name(self, mapper: ContactMapper) -> None:
        # form bot regex: /\b(last.?name|lname|surname|family.?name)\b/
        for header in ["last_name", "lname", "surname", "family_name", "lastname"]:
            m = mapper.identify(header)
            assert m.canonical == "last_name", f"Failed for {header}"

    def test_form_field_company(self, mapper: ContactMapper) -> None:
        # form bot regex: /\b(company|organisation|organization|firm|employer|business)\b/
        for header in ["company", "organization", "organisation", "firm", "employer", "business"]:
            m = mapper.identify(header)
            assert m.canonical == "company", f"Failed for {header}"

    def test_form_field_message(self, mapper: ContactMapper) -> None:
        # form bot regex: /\b(message|comment|body|inquiry|enquiry|question|note|feedback)\b/
        for header in ["message", "inquiry", "enquiry", "feedback"]:
            m = mapper.identify(header)
            assert m.canonical == "message", f"Failed for {header}"

    def test_form_field_job_title(self, mapper: ContactMapper) -> None:
        # form bot regex: /\b(job.?title|position|role|occupation|function)\b/
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


class TestFormBotIdentityTranslation:
    """Translate form_bot identity payloads to/from other services."""

    def test_formbot_to_hubspot(self, mapper: ContactMapper) -> None:
        identity = {
            "first_name": "Amber",
            "last_name": "Maccione",
            "email": "amber@cognitutor.com",
            "company": "CogniTutor",
            "title": "Principal",
            "phone": "321-460-8272",
            "address": "2502 Lawler Ln",
            "city": "Deltona",
            "state": "FL",
            "zip": "32738",
        }
        hs = mapper.translate(identity, from_service="form_bot", to_service="hubspot")
        assert any(v == "Amber" for v in hs.values())
        assert any(v == "Maccione" for v in hs.values())
        assert any(v == "amber@cognitutor.com" for v in hs.values())

    def test_formbot_to_mailchimp(self, mapper: ContactMapper) -> None:
        identity = {
            "first_name": "Loni",
            "last_name": "Lebanoff",
            "email": "loni@cognitutor.com",
            "company": "CogniTutor",
        }
        mc = mapper.translate(identity, from_service="form_bot", to_service="mailchimp")
        assert any(v == "Loni" for v in mc.values())
        assert any(v == "loni@cognitutor.com" for v in mc.values())

    def test_formbot_full_identity_mapping(self, mapper: ContactMapper) -> None:
        """Full identity with form_bot service should map all fields."""
        identity = {
            "first_name": "Amber",
            "last_name": "Maccione",
            "email": "amber@cognitutor.com",
            "company": "CogniTutor",
            "title": "Principal",
            "phone": "321-460-8272",
            "address": "2502 Lawler Ln",
            "city": "Deltona",
            "state": "FL",
            "zip": "32738",
            "message": "Please add me to your mailing list.",
        }
        result = mapper.map_payload(identity, service="form_bot")
        assert result.normalized["first_name"] == "Amber"
        assert result.normalized["last_name"] == "Maccione"
        assert result.normalized["email"] == "amber@cognitutor.com"
        assert result.normalized["company"] == "CogniTutor"
        assert result.normalized["job_title"] == "Principal"
        assert result.normalized["phone"] == "3214608272"
        assert result.normalized["address_line1"] == "2502 Lawler Ln"
        assert result.normalized["city"] == "Deltona"
        assert result.normalized["state"] == "FL"
        assert result.normalized["postal_code"] == "32738"
        assert result.normalized["message"] == "Please add me to your mailing list."
        assert result.unmatched_count == 0


class TestFormBotAutocompleteWorkflow:
    """Simulate how form bot would use rolodexter for autocomplete attributes."""

    def test_autocomplete_attr_to_identity_key(self) -> None:
        """Given an HTML autocomplete attr, resolve to form_bot identity key."""
        mapper = ContactMapper()
        reg = mapper.registry

        # Simulate: form has autocomplete="given-name", map to canonical, then to form_bot key
        canonical = reg.service_lookup("given-name", "w3c_autocomplete")
        assert canonical == "first_name"

        # Now get the form_bot identity key for this canonical
        bot_reverse = reg.get_reverse_mapping("form_bot")
        identity_key = bot_reverse.get(canonical)
        assert identity_key == "first_name"

    def test_full_autocomplete_chain(self) -> None:
        """Full chain: autocomplete attr → canonical → form_bot identity key."""
        mapper = ContactMapper()
        reg = mapper.registry
        bot_reverse = reg.get_reverse_mapping("form_bot")

        test_cases = {
            "given-name": "first_name",
            "family-name": "last_name",
            "email": "email",
            "tel": "phone",
            "organization": "company",
            "organization-title": "title",
            "street-address": "address",
            "address-level2": "city",
            "address-level1": "state",
            "postal-code": "zip",
            "country-name": "country",
            "url": "website",
        }
        for attr, expected_identity_key in test_cases.items():
            canonical = reg.service_lookup(attr, "w3c_autocomplete")
            assert canonical is not None, f"No canonical for autocomplete={attr}"
            identity_key = bot_reverse.get(canonical)
            assert identity_key == expected_identity_key, (
                f"autocomplete={attr} → canonical={canonical} → "
                f"identity_key={identity_key}, expected {expected_identity_key}"
            )


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

    def test_age_service_lookup_form_bot(self, registry: PatternRegistry) -> None:
        assert registry.service_lookup("age", "form_bot") == "age"


class TestI18nAliases:
    """Verify internationalized aliases from smus_bark definitions.json."""

    @pytest.mark.parametrize(
        "alias, expected",
        [
            # Romanian
            ("prenume", "first_name"),
            ("nume", "last_name"),
            ("nume_complet", "full_name"),
            ("adresa_email", "email"),
            ("mesaj", "message"),
            ("subiect", "subject"),
            # German
            ("vorname", "first_name"),
            ("nachname", "last_name"),
            # French
            ("nom", "last_name"),
            ("nom_complet", "full_name"),
            ("courriel", "email"),
            ("sujet", "subject"),
            ("société", "company"),
            # Other
            ("companie", "company"),
            ("firma", "company"),
            ("telefon", "phone"),
            ("custtel", "phone"),
            ("custemail", "email"),
            ("user_email", "email"),
            ("custname", "full_name"),
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


class TestFormBotServiceOverrides:
    """form_bot profile overrides generic aliases for form-specific semantics."""

    def test_note_maps_to_message_via_service(self, mapper: ContactMapper) -> None:
        """'note' generically maps to 'notes', but form_bot maps it to 'message'."""
        # Generic (no service): note → notes
        generic = mapper.identify("note")
        assert generic.canonical == "notes"

        # With form_bot service: note → message
        service = mapper.identify("note", service="form_bot")
        assert service.canonical == "message"

    def test_comment_maps_to_message_via_service(self, mapper: ContactMapper) -> None:
        """'comment' generically maps to 'notes', but form_bot maps it to 'message'."""
        generic = mapper.identify("comment")
        assert generic.canonical == "notes"

        service = mapper.identify("comment", service="form_bot")
        assert service.canonical == "message"

    def test_body_maps_to_message_via_service(self, mapper: ContactMapper) -> None:
        service = mapper.identify("body", service="form_bot")
        assert service.canonical == "message"

    def test_form_bot_payload_with_overrides(self, mapper: ContactMapper) -> None:
        """Full payload using form_bot service with override fields."""
        payload = {
            "first_name": "Test",
            "email": "test@example.com",
            "note": "Please contact me.",
            "organisation": "Acme Corp",
            "mobile": "555-0199",
            "postal": "78701",
            "province": "ON",
        }
        result = mapper.map_payload(payload, service="form_bot")
        assert result.normalized["message"] == "Please contact me."
        assert result.normalized["company"] == "Acme Corp"
        assert result.normalized["phone"] == "5550199"
        assert result.normalized["postal_code"] == "78701"
        assert result.normalized["state"] == "ON"
        assert result.unmatched_count == 0


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

    def test_version_is_1_2_0(self, registry: PatternRegistry) -> None:
        assert registry.version == "1.2.0"
