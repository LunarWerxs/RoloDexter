"""Alias coverage and the canonical fields each release added.

Extracted verbatim from ``test_rolodexter.py``.
"""

from __future__ import annotations

import pytest

from rolodexter import (
    CanonicalField,
    ContactMapper,
    PatternRegistry,
)

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

    def test_version_matches_pattern_table(self, registry: PatternRegistry) -> None:
        assert registry.version == "2.10.0"


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
