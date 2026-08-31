"""The normalized match strategy: CamelCase, dot paths, separators.

Extracted verbatim from ``test_rolodexter.py``.
"""

from __future__ import annotations

from rolodexter import (
    NormalizedMatchStrategy,
    PatternRegistry,
)


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
