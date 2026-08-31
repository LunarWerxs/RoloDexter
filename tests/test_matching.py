"""Exact, fuzzy and heuristic header matching, and the resolution cache.

Extracted verbatim from ``test_rolodexter.py``.
"""

from __future__ import annotations

import pytest

from rolodexter import (
    ContactMapper,
    ExactMatchStrategy,
    FuzzyMatchStrategy,
    HeuristicMatchStrategy,
    PatternRegistry,
)


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

    @pytest.mark.parametrize(
        "header",
        ["zip", "Postal Code", "cust_plz", "shipping zipcode"],
    )
    def test_bare_five_digits_needs_a_postal_header_hint(self, header: str) -> None:
        """A bare 5-digit run is only a postal code if the header says so."""
        strat = HeuristicMatchStrategy()
        m = strat.match(header, value="90210")
        assert m is not None
        assert m.canonical == "postal_code"

    @pytest.mark.parametrize(
        "header",
        ["Unknown Column", "order_total", "account_balance", "employee_number"],
    )
    def test_bare_five_digits_is_not_guessed_as_postal(self, header: str) -> None:
        r"""Money, IDs and quantities must not be filed as someone's postal code.

        ``^\d{5}$`` cannot distinguish a ZIP from an order total, so without
        corroboration from the header the shape is not trusted -- mirroring the
        guards the phone and birthday shapes already have.
        """
        strat = HeuristicMatchStrategy()
        assert strat.match(header, value="45000") is None
        assert strat.match(header, value="90210") is None

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
