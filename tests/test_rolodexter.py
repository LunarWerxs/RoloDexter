"""Complete test suite for rolodexter v2.1 — tests in one file."""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib

from rolodexter import (
    ContactMapper,
    ExactMatchStrategy,
    HeuristicMatchStrategy,
    MappingResult,
    PatternRegistry,
)
from rolodexter.core import (
    PatternLoadError,
)


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
        "CountryNormalizer",
        "DateNormalizer",
        "EmailNormalizer",
        "ExactMatchStrategy",
        "FieldMatch",
        "FuzzyMatchStrategy",
        "HeuristicMatchStrategy",
        "ListNormalizer",
        "MappingProfile",
        "MappingResult",
        "MappingSchema",
        "MappingWarning",
        "MatchStrategy",
        "NameNormalizer",
        "NormalizationError",
        "NormalizedMatchStrategy",
        "PatternLoadError",
        "PatternRegistry",
        "PhoneNormalizer",
        "PostalCodeNormalizer",
        "RolodexterError",
        "StateNormalizer",
        "StringNormalizer",
        "WarningCategory",
        "normalize_value",
        "value_warnings",
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
        "normalize_language_code",
    ]


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
        assert registry.version == "2.10.0"

    def test_custom_patterns(self) -> None:
        custom = {
            "fields": {"first_name": ["fname", "given"]},
        }
        reg = PatternRegistry(patterns=custom)
        assert reg.exact_lookup("fname") == "first_name"
        assert reg.exact_lookup("given") == "first_name"

    @pytest.mark.parametrize(
        "patterns",
        [
            [],
            {"version": None},
            {"fields": None},
            {"fields": {"custom": "alias"}},
            {"fields": {"custom": [""]}},
            {"expansion": {"form_prefixes": "billing_"}},
            {"expansion": {"form_fields": {"email": ""}}},
        ],
    )
    def test_malformed_custom_patterns_raise_actionable_error(
        self, patterns: object
    ) -> None:
        with pytest.raises(PatternLoadError, match="Invalid custom patterns"):
            PatternRegistry(patterns=patterns)  # type: ignore[arg-type]

    def test_malformed_overrides_raise_actionable_error(self) -> None:
        with pytest.raises(PatternLoadError, match="Invalid overrides"):
            PatternRegistry(overrides={"": "email"})

    def test_bad_path_raises(self) -> None:
        with pytest.raises(PatternLoadError):
            PatternRegistry(patterns_path="/nonexistent/path.json")

    def test_repr(self, registry: PatternRegistry) -> None:
        r = repr(registry)
        assert "PatternRegistry" in r
        assert "aliases=" in r


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
#  I18N SYSTEM TESTS (on-demand generation model)
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
#  v2.2 — PHONE MODULE: EXTENSIONS, RFC3966, FORMATTING, ETC.
# ═══════════════════════════════════════════════════════════════


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


class TestPatternRegistryFromPath:
    """Test PatternRegistry loaded from a custom file path."""

    def test_load_from_valid_path(self, tmp_path: Path) -> None:
        import json

        data = {"version": "1.0.0", "fields": {"email": ["correo"]}}
        fp = tmp_path / "patterns.json"
        fp.write_text(json.dumps(data))
        reg = PatternRegistry(patterns_path=str(fp))
        assert reg.exact_lookup("correo") == "email"


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
            "language_code": "sw",
            "language_name": "Swahili",
            "generated_at": "2026-01-01",
            "source_version": "2.10.0",
            "fields": {"email": ["correo_cov_test"]},
        }
        _write_cache(lang_data)
        try:
            reg = PatternRegistry(languages=["test_cov"])
            assert reg.exact_lookup("correo_cov_test") is None
            assert reg.loaded_languages == []
            # A real, supported code loads the same cache file.
            reg = PatternRegistry(languages=["sw"])
            assert reg.exact_lookup("correo_cov_test") == "email"
            assert "sw" in reg.loaded_languages
        finally:
            # Clean up
            p = cache_dir / "sw.json"
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
