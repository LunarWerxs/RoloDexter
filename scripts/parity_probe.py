from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
JS_PROBE = Path(__file__).with_name("parity_js_probe.mjs")

sys.path.insert(0, str(ROOT / "src"))

import rolodexter as r  # noqa: E402
import rolodexter.i18n as i18n  # noqa: E402


CASES: dict[str, Any] = {
    "normalize": [
        {"id": "email_spaces", "field": "email", "value": " A@EXAMPLE.COM "},
        {"id": "email_none", "field": "email", "value": None},
        {"id": "phone_us", "field": "phone", "value": "(202) 555-0143", "default_region": "US"},
        {"id": "phone_blank", "field": "phone", "value": "   ", "default_region": "US"},
        {"id": "phone_bool", "field": "phone", "value": True, "default_region": "US"},
        {"id": "name_particle", "field": "full_name", "value": "DR. jane van doe jr."},
        {"id": "address_hyphen", "field": "address_line1", "value": " 123 main-st apt 4 "},
        {"id": "address_mac_word", "field": "address_line1", "value": "machine shop rd"},
        {"id": "postal_numeric", "field": "postal_code", "value": 1234},
        {"id": "bool_yes", "field": "email_opt_out", "value": " YES "},
        {"id": "bool_zero", "field": "email_opt_out", "value": "0"},
        {"id": "bool_unknown", "field": "email_opt_out", "value": "sometimes"},
        {"id": "tags_csv", "field": "tags", "value": "alpha, beta,,alpha"},
        {"id": "tags_list", "field": "tags", "value": [" alpha ", "", "beta", "alpha"]},
        {"id": "age_float", "field": "age", "value": 42.0},
        {"id": "score_string", "field": "score", "value": " 12.50 "},
        {"id": "revenue_bad", "field": "revenue", "value": "12 bucks"},
        {"id": "metadata_object", "field": "metadata", "value": {"a": 1}},
        {"id": "unknown_string", "field": "unknown", "value": " X "},
    ],
    "payloads": [
        {"id": "basic", "payload": {"fname": "Ada", "surname": "Lovelace", "mobile": "(202) 555-0143"}},
        {"id": "nested_depth1", "payload": {"person": {"fname": "Ada"}}, "options": {"depth": 1}},
        {"id": "nested_depth2", "payload": {"person": {"fname": "Ada"}}, "options": {"depth": 2}},
        {"id": "unknown_email_value", "payload": {"Mystery": "ada@example.com"}},
        {"id": "unknown_phone_value", "payload": {"Mystery": "202-555-0143"}},
        {"id": "low_threshold", "payload": {"Mystery": "202-555-0143"}, "mapper_options": {"confidence_threshold": 0.95}},
        {"id": "strict_bad_phone", "payload": {"phone": "not a phone"}, "mapper_options": {"strict": True}},
        {"id": "normalize_false", "payload": {"email": " A@EXAMPLE.COM "}, "mapper_options": {"normalize": False}},
        {
            "id": "embedded",
            "payload": {"notes": "Call Ada at (202) 555-0143 or +1 202 555 0199"},
            "options": {"extract_embedded_phones": True},
        },
        {"id": "duplicate_names", "payload": {"fname": "Ada", "first": "Augusta"}},
        {"id": "list_collision", "payload": {"tags": "alpha,beta", "labels": ["beta", "gamma"]}},
        {"id": "list_duplicate_incoming", "payload": {"tags": [], "tag": ["a", "a"]}, "mapper_options": {"overrides": {"tag": "tags"}}},
        {"id": "float_phone_heuristic", "payload": {"Mystery Phone": 2025550143.0}},
    ],
    "schemas": [
        {"id": "schema_basic", "headers": ["fname", "mobile", "Mystery"]},
        {"id": "schema_threshold", "headers": ["Compny"], "mapper_options": {"confidence_threshold": 0.99}},
        {"id": "schema_strict", "headers": ["Compny"], "mapper_options": {"confidence_threshold": 0.99, "strict": True}},
        {"id": "schema_nonstring_headers", "headers": [1, True, None, ["x"]]},
    ],
    "phones": [
        {"id": "parse_us", "fn": "parse", "value": "(202) 555-0143", "default_region": "US"},
        {"id": "parse_local", "fn": "parse", "value": "555-0143", "default_region": "US"},
        {"id": "parse_blank", "fn": "parse", "value": "", "default_region": "US"},
        {"id": "parse_none", "fn": "parse", "value": None, "default_region": "US"},
        {"id": "parse_number", "fn": "parse", "value": 123, "default_region": "US"},
        {"id": "parse_bool", "fn": "parse", "value": True, "default_region": "US"},
        {"id": "parse_object", "fn": "parse", "value": {"x": 1}, "default_region": "US"},
        {"id": "parse_list", "fn": "parse", "value": [], "default_region": "US"},
        {"id": "parse_extension", "fn": "parse", "value": "+1 202 555 0143 ext. 99", "default_region": "US"},
        {"id": "format_e164_bad", "fn": "format_e164", "value": "not a phone", "default_region": "US"},
        {"id": "format_e164_none", "fn": "format_e164", "value": None, "default_region": "US"},
        {"id": "format_e164_number", "fn": "format_e164", "value": 123, "default_region": "US"},
        {"id": "format_e164_bool", "fn": "format_e164", "value": True, "default_region": "US"},
        {"id": "format_e164_object", "fn": "format_e164", "value": {"x": 1}, "default_region": "US"},
        {"id": "format_e164_list", "fn": "format_e164", "value": [], "default_region": "US"},
        {"id": "format_e164_alpha_gb", "fn": "format_e164", "value": "not a phone", "default_region": "GB"},
        {"id": "is_valid_bad", "fn": "is_valid", "value": "not a phone", "default_region": "US"},
        {"id": "is_valid_none", "fn": "is_valid", "value": None, "default_region": "US"},
        {"id": "is_valid_number", "fn": "is_valid", "value": 123, "default_region": "US"},
        {"id": "is_valid_bool", "fn": "is_valid", "value": True, "default_region": "US"},
        {"id": "is_valid_object", "fn": "is_valid", "value": {"x": 1}, "default_region": "US"},
        {"id": "is_valid_list", "fn": "is_valid", "value": [], "default_region": "US"},
        {"id": "match_same", "fn": "is_number_match", "a": "+12025550143", "b": "(202) 555-0143", "default_region": "US"},
        {"id": "match_diff", "fn": "is_number_match", "a": "+12025550143", "b": "+442079460958", "default_region": "US"},
        {"id": "matcher_two", "fn": "matcher", "value": "A (202) 555-0143 and +1 202 555 0199", "default_region": "US"},
    ],
    "objects": [
        {
            "id": "mapping_result_helpers",
            "kind": "mapping_result_helpers",
            "payload": {"fname": "Ada", "mobile": "(202) 555-0143", "Mystery": "???"},
        },
        {
            "id": "schema_helpers",
            "kind": "schema_helpers",
            "headers": ["fname", "mobile", "Mystery"],
            "row": {"fname": "Ada", "mobile": "(202) 555-0143", "Mystery": "???"},
        },
        {
            "id": "registry_helpers",
            "kind": "registry_helpers",
            "header": "fname",
        },
        {
            "id": "constructors",
            "kind": "constructors",
        },
        {
            "id": "object_constructor_rejections",
            "kind": "object_constructor_rejections",
        },
        {
            "id": "constructor_arity_errors",
            "kind": "constructor_arity_errors",
        },
        {
            "id": "i18n_main_arity",
            "kind": "i18n_main_arity",
        },
        {
            "id": "i18n_public_helpers",
            "kind": "i18n_public_helpers",
        },
        {
            "id": "mapper_runtime_rejections",
            "kind": "mapper_runtime_rejections",
        },
        {
            "id": "phone_runtime_edges",
            "kind": "phone_runtime_edges",
        },
        {
            "id": "frozen_assignment",
            "kind": "frozen_assignment",
        },
        {
            "id": "normalizer_methods",
            "kind": "normalizer_methods",
        },
        {
            "id": "strategy_constructors",
            "kind": "strategy_constructors",
        },
    ],
}


def simplify(value: Any) -> Any:
    if isinstance(value, Exception):
        return {"kind": "error", "name": type(value).__name__, "message": str(value)}
    if isinstance(value, r.MappingResult):
        return {
            "normalized": simplify(value.normalized),
            "unmapped": simplify(value.unmapped),
            "field_matches": simplify(value.field_matches),
            "warnings": simplify(value.warnings),
        }
    if isinstance(value, r.FieldMatch):
        return {
            "original": value.original,
            "canonical": value.canonical,
            "confidence": value.confidence,
            "strategy": value.strategy,
            "service": value.service,
            "is_matched": value.is_matched,
        }
    if isinstance(value, r.MappingSchema):
        return {"matches": simplify(value.matches), "default_region": simplify(value.default_region)}
    if isinstance(value, r.PhoneNumber):
        return {
            "calling_code": value.calling_code,
            "national_number": str(value.national_number),
            "extension": value.extension,
            "raw": value.raw,
            "e164": value.e164,
            "is_possible": value.is_possible,
            "is_valid": value.is_valid,
            "country_codes": value.country_codes,
        }
    if hasattr(r, "PhoneNumberMatch") and isinstance(value, r.PhoneNumberMatch):
        return {
            "start": value.start,
            "end": value.end,
            "raw_string": value.raw_string,
            "number": simplify(value.number),
        }
    if isinstance(value, dict):
        return {str(key): simplify(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [simplify(item) for item in value]
    return value


def capture(fn: Any) -> dict[str, Any]:
    try:
        return {"ok": True, "value": simplify(fn())}
    except Exception as exc:  # noqa: BLE001 - parity probe needs exact exception shape
        return {"ok": False, "error": simplify(exc)}


def capture_value(fn: Any) -> Any:
    try:
        return simplify(fn())
    except Exception as exc:  # noqa: BLE001 - parity probe needs exact exception shape
        return simplify(exc)


def python_results() -> dict[str, Any]:
    output: dict[str, Any] = {"normalize": {}, "payloads": {}, "phones": {}, "schemas": {}, "objects": {}}
    for item in CASES["normalize"]:
        output["normalize"][item["id"]] = capture(
            lambda item=item: r.normalize_value(
                item["field"], item.get("value"), default_region=item.get("default_region")
            )
        )
    for item in CASES["payloads"]:
        output["payloads"][item["id"]] = capture(
            lambda item=item: r.ContactMapper(**item.get("mapper_options", {})).map_payload(
                item["payload"], **item.get("options", {})
            )
        )
    for item in CASES["schemas"]:
        output["schemas"][item["id"]] = capture(
            lambda item=item: r.ContactMapper(**item.get("mapper_options", {})).compile_schema(
                item["headers"], **item.get("options", {})
            )
        )
    for item in CASES["phones"]:
        if item["fn"] == "parse":
            fn = lambda item=item: r.parse(item["value"], item.get("default_region"))
        elif item["fn"] == "format_e164":
            fn = lambda item=item: r.format_e164(item["value"], item.get("default_region"))
        elif item["fn"] == "is_valid":
            fn = lambda item=item: r.is_valid(item["value"], item.get("default_region"))
        elif item["fn"] == "is_number_match":
            fn = lambda item=item: r.is_number_match(item["a"], item["b"], item.get("default_region"))
        elif item["fn"] == "matcher":
            fn = lambda item=item: list(
                r.PhoneNumberMatcher(
                    item["value"],
                    item.get("default_region"),
                    max_matches=item.get("max_matches"),
                )
            )
        else:
            raise AssertionError(item["fn"])
        output["phones"][item["id"]] = capture(fn)
    for item in CASES["objects"]:
        if item["kind"] == "mapping_result_helpers":
            def fn(item: dict[str, Any] = item) -> dict[str, Any]:
                result = r.ContactMapper(**item.get("mapper_options", {})).map_payload(
                    item["payload"], **item.get("options", {})
                )
                return {
                    "matched_count": result.matched_count,
                    "unmatched_count": result.unmatched_count,
                    "match_rate": result.match_rate,
                    "dict": result.to_dict(),
                    "explain": result.explain(),
                    "all_phones": result.get_all_phones(),
                    "match_fname": simplify(result.get_match("fname")),
                    "match_missing": simplify(result.get_match("missing")),
                }
        elif item["kind"] == "schema_helpers":
            def fn(item: dict[str, Any] = item) -> dict[str, Any]:
                schema = r.ContactMapper(**item.get("mapper_options", {})).compile_schema(
                    item["headers"], **item.get("options", {})
                )
                return {
                    "column_map": simplify(schema.column_map()),
                    "unmatched_headers": simplify(schema.unmatched_headers()),
                    "matches_get_missing": simplify(schema.matches.get("missing")),
                    "applied": simplify(schema.apply(item["row"])),
                    "apply_missing": capture_value(lambda: schema.apply()),  # type: ignore[call-arg]
                    "apply_positional_options": capture_value(lambda: schema.apply(item["row"], 2)),  # type: ignore[call-arg]
                    "apply_unknown_kw": capture_value(lambda: schema.apply(item["row"], bogus=True)),  # type: ignore[call-arg]
                    "apply_extra_positional": capture_value(lambda: schema.apply(item["row"], {}, "extra")),  # type: ignore[call-arg]
                }
        elif item["kind"] == "registry_helpers":
            def fn(item: dict[str, Any] = item) -> dict[str, Any]:
                registry = r.PatternRegistry(**item.get("options", {}))
                aliases = registry.all_aliases
                aliases.append("__mutated__")
                custom_patterns = {"version": "probe", "fields": {"custom": ["Alias One"]}}
                positional = r.PatternRegistry(custom_patterns)
                positional_override = r.PatternRegistry(
                    custom_patterns,
                    None,
                    None,
                    {"Override": "custom2"},
                )
                return {
                    "exact_lookup": registry.exact_lookup(item["header"]),
                    "exact_lookup_missing": registry.exact_lookup("not-a-known-alias"),
                    "canonical_fields_prefix": registry.canonical_fields[:5],
                    "all_aliases_mutation_leaked": "__mutated__" in registry.all_aliases,
                    "version": registry.version,
                    "available_languages_count": len(registry.available_languages),
                    "cached_languages_type": "array" if isinstance(registry.cached_languages, list) else type(registry.cached_languages).__name__,
                    "loaded_languages": registry.loaded_languages,
                    "repr": repr(positional),
                    "positional_patterns": {
                        "version": positional.version,
                        "lookup": positional.exact_lookup("Alias One"),
                        "fields": positional.canonical_fields,
                    },
                    "positional_override": positional_override.exact_lookup("Override"),
                    "too_many_args": capture_value(
                        lambda: r.PatternRegistry(None, None, None, None, "extra")  # type: ignore[call-arg]
                    ),
                    "patterns_list": capture_value(lambda: r.PatternRegistry(patterns=[])),  # type: ignore[arg-type]
                    "languages_int": capture_value(lambda: r.PatternRegistry(languages=123)),  # type: ignore[arg-type]
                }
        elif item["kind"] == "constructors":
            def fn() -> dict[str, Any]:
                phone = r.PhoneNumber(1, "2025550143", "raw", "99")
                local = r.PhoneNumber(1, "5551212", "raw")
                return {
                    "field_positional": simplify(r.FieldMatch("x", "unknown", 0, "none")),
                    "field_with_service": simplify(r.FieldMatch("x", "unknown", 0, "none", "legacy")),
                    "mapping_result_positional": simplify(r.MappingResult({}, {}, [r.FieldMatch("x", "unknown", 0, "none")])),
                    "phone_positional": simplify(phone),
                    "phone_positional_display": {
                        "str": str(phone),
                        "format_international": r.format_international(phone),
                        "format_national": r.format_national(phone),
                        "number_type": r.number_type(phone),
                        "local_format_national": r.format_national(local),
                    },
                    "match_positional": simplify(r.PhoneNumberMatch(1, 4, "raw", r.PhoneNumber(1, "2025550143", "raw"))),
                }
        elif item["kind"] == "object_constructor_rejections":
            def fn() -> dict[str, Any]:
                return {
                    "field": capture_value(lambda: r.FieldMatch({"original": "x", "canonical": "unknown", "confidence": 0, "strategy": "none"})),  # type: ignore[arg-type]
                    "mapping_result": capture_value(lambda: r.MappingResult({"normalized": {}, "unmapped": {}, "field_matches": []})),  # type: ignore[call-arg]
                    "mapping_schema": capture_value(lambda: r.MappingSchema({"matches": {}, "mapper": r.ContactMapper()})),  # type: ignore[call-arg]
                    "phone": capture_value(lambda: r.PhoneNumber({"calling_code": 1, "national_number": "2025550143", "raw": "x"})),  # type: ignore[arg-type]
                }
        elif item["kind"] == "constructor_arity_errors":
            def fn() -> dict[str, Any]:
                return {
                    "FieldMatch0": capture_value(lambda: r.FieldMatch()),  # type: ignore[call-arg]
                    "FieldMatch1": capture_value(lambda: r.FieldMatch("x")),  # type: ignore[call-arg]
                    "FieldMatch6": capture_value(lambda: r.FieldMatch("x", "unknown", 0, "none", None, "extra")),  # type: ignore[call-arg]
                    "MappingResult0": capture_value(lambda: r.MappingResult()),  # type: ignore[call-arg]
                    "MappingResult1": capture_value(lambda: r.MappingResult({})),  # type: ignore[call-arg]
                    "MappingResult2": capture_value(lambda: r.MappingResult({}, {})),  # type: ignore[call-arg]
                    "MappingResult5": capture_value(lambda: r.MappingResult({}, {}, [], (), "extra")),  # type: ignore[call-arg]
                    "MappingSchema0": capture_value(lambda: r.MappingSchema()),  # type: ignore[call-arg]
                    "MappingSchema1": capture_value(lambda: r.MappingSchema({})),  # type: ignore[call-arg]
                    "MappingSchema4": capture_value(lambda: r.MappingSchema({}, r.ContactMapper(), None, "extra")),  # type: ignore[call-arg]
                    "PhoneNumber0": capture_value(lambda: r.PhoneNumber()),  # type: ignore[call-arg]
                    "PhoneNumber1": capture_value(lambda: r.PhoneNumber(1)),  # type: ignore[call-arg]
                    "PhoneNumber2": capture_value(lambda: r.PhoneNumber(1, "202")),  # type: ignore[call-arg]
                    "PhoneNumber6": capture_value(lambda: r.PhoneNumber(1, "202", "raw", None, None, "extra")),  # type: ignore[call-arg]
                    "PhoneNumberMatch0": capture_value(lambda: r.PhoneNumberMatch()),  # type: ignore[call-arg]
                    "PhoneNumberMatch1": capture_value(lambda: r.PhoneNumberMatch(1)),  # type: ignore[call-arg]
                    "PhoneNumberMatch5": capture_value(lambda: r.PhoneNumberMatch(1, 2, "raw", r.PhoneNumber(1, "202", "raw"), "extra")),  # type: ignore[call-arg]
                }
        elif item["kind"] == "i18n_main_arity":
            def fn() -> dict[str, Any]:
                return {
                    "one_arg": capture_value(lambda: i18n.main(["--help"])),  # type: ignore[call-arg]
                }
        elif item["kind"] == "i18n_public_helpers":
            def fn() -> dict[str, Any]:
                return {
                    "load_missing": capture_value(lambda: i18n.load_cached("__missing__")),
                    "load_missing_arg": capture_value(lambda: i18n.load_cached()),  # type: ignore[call-arg]
                    "load_extra_arg": capture_value(lambda: i18n.load_cached("__missing__", "extra")),  # type: ignore[call-arg]
                    "get_writable_extra_arg": capture_value(lambda: i18n.get_writable_cache_dir("extra")),  # type: ignore[call-arg]
                    "get_cache_extra_arg": capture_value(lambda: i18n.get_cache_dir("extra")),  # type: ignore[call-arg]
                    "get_all_extra_arg": capture_value(lambda: i18n.get_all_cache_dirs("extra")),  # type: ignore[call-arg]
                    "discover_extra_arg": capture_value(lambda: i18n.discover_cached("extra")),  # type: ignore[call-arg]
                    "generate_missing_arg": capture_value(lambda: i18n.generate_language()),  # type: ignore[call-arg]
                    "generate_bad": capture_value(lambda: i18n.generate_language("__missing__")),
                    "generate_positional_bool": capture_value(
                        lambda: i18n.generate_language("__missing__", True)  # type: ignore[call-arg]
                    ),
                    "generate_keyword_options": capture_value(lambda: i18n.generate_language("__missing__", force=True)),
                    "generate_badkw": capture_value(lambda: i18n.generate_language("__missing__", cache_dir="x")),  # type: ignore[call-arg]
                }
        elif item["kind"] == "mapper_runtime_rejections":
            def fn() -> dict[str, Any]:
                mapper = r.ContactMapper()
                return {
                    "identify_missing_arg": capture_value(lambda: mapper.identify()),  # type: ignore[call-arg]
                    "identify_positional_value": capture_value(lambda: mapper.identify("Mystery", "ada@example.com")),  # type: ignore[call-arg]
                    "map_payload_missing_arg": capture_value(lambda: mapper.map_payload()),  # type: ignore[call-arg]
                    "map_payload_positional_options": capture_value(lambda: mapper.map_payload({"fname": "Ada"}, 2)),  # type: ignore[call-arg]
                    "map_payload_array": capture_value(lambda: mapper.map_payload([("fname", "Ada")])),  # type: ignore[arg-type]
                    "map_batch_missing_arg": capture_value(lambda: mapper.map_batch()),  # type: ignore[call-arg]
                    "map_batch_positional_options": capture_value(lambda: mapper.map_batch([{"fname": "Ada"}], 2)),  # type: ignore[call-arg]
                    "map_stream_missing_arg": capture_value(lambda: mapper.map_stream()),  # type: ignore[call-arg]
                    "map_stream_positional_options": capture_value(lambda: mapper.map_stream([{"fname": "Ada"}], 2)),  # type: ignore[call-arg]
                    "compile_schema_missing_arg": capture_value(lambda: mapper.compile_schema()),  # type: ignore[call-arg]
                    "compile_schema_positional_options": capture_value(lambda: mapper.compile_schema(["fname"], 2)),  # type: ignore[call-arg]
                    "map_dataframe_missing_arg": capture_value(lambda: mapper.map_dataframe()),  # type: ignore[call-arg]
                    "map_dataframe_positional_options": capture_value(lambda: mapper.map_dataframe([], 2)),  # type: ignore[call-arg]
                    "ctor_positional": capture_value(lambda: r.ContactMapper(2)),  # type: ignore[call-arg]
                    "ctor_bogus": capture_value(lambda: r.ContactMapper(bogus=True)),  # type: ignore[call-arg]
                    "ctor_patterns_list": capture_value(lambda: r.ContactMapper(patterns=[])),  # type: ignore[arg-type]
                    "ctor_header_cache_string": capture_value(lambda: r.ContactMapper(header_cache_max_size="2")),  # type: ignore[arg-type]
                    "cache_info_extra": capture_value(lambda: mapper.cache_info(1)),  # type: ignore[call-arg]
                    "clear_cache_extra": capture_value(lambda: mapper.clear_cache(1)),  # type: ignore[call-arg]
                }
        elif item["kind"] == "phone_runtime_edges":
            def fn() -> dict[str, Any]:
                match = r.PhoneNumberMatch(1, 4, "raw", r.PhoneNumber(1, "2025550143", "raw"))
                return {
                    "parse_missing": capture_value(lambda: r.parse()),  # type: ignore[call-arg]
                    "parse_extra": capture_value(lambda: r.parse("x", "US", "extra")),  # type: ignore[call-arg]
                    "format_e164_missing": capture_value(lambda: r.format_e164()),  # type: ignore[call-arg]
                    "format_e164_extra": capture_value(lambda: r.format_e164("x", "US", "extra")),  # type: ignore[call-arg]
                    "is_valid_missing": capture_value(lambda: r.is_valid()),  # type: ignore[call-arg]
                    "is_valid_extra": capture_value(lambda: r.is_valid("x", "US", "extra")),  # type: ignore[call-arg]
                    "format_international_missing": capture_value(lambda: r.format_international()),  # type: ignore[call-arg]
                    "format_international_extra": capture_value(lambda: r.format_international(r.PhoneNumber(1, "202", "raw"), "extra")),  # type: ignore[call-arg]
                    "format_international_wrong": capture_value(lambda: r.format_international({})),  # type: ignore[arg-type]
                    "format_national_missing": capture_value(lambda: r.format_national()),  # type: ignore[call-arg]
                    "format_national_extra": capture_value(lambda: r.format_national(r.PhoneNumber(1, "202", "raw"), "extra")),  # type: ignore[call-arg]
                    "format_national_wrong": capture_value(lambda: r.format_national("x")),  # type: ignore[arg-type]
                    "number_type_missing": capture_value(lambda: r.number_type()),  # type: ignore[call-arg]
                    "number_type_extra": capture_value(lambda: r.number_type(r.PhoneNumber(1, "202", "raw"), "extra")),  # type: ignore[call-arg]
                    "number_type_wrong": capture_value(lambda: r.number_type(None)),  # type: ignore[arg-type]
                    "is_number_match_missing0": capture_value(lambda: r.is_number_match()),  # type: ignore[call-arg]
                    "is_number_match_missing1": capture_value(lambda: r.is_number_match("x")),  # type: ignore[call-arg]
                    "is_number_match_extra": capture_value(lambda: r.is_number_match("x", "y", "US", "extra")),  # type: ignore[call-arg]
                    "match_repr": repr(match),
                    "match_str": str(match),
                    "matcher_null_len": len(r.PhoneNumberMatcher(None, "US")),  # type: ignore[arg-type]
                    "matcher_null_list": simplify(list(r.PhoneNumberMatcher(None, "US"))),  # type: ignore[arg-type]
                    "matcher_bad_max": capture_value(lambda: r.PhoneNumberMatcher("a +1 202 555 0143", "US", max_matches="1")),  # type: ignore[arg-type]
                }
        elif item["kind"] == "frozen_assignment":
            def fn() -> str:
                match = r.FieldMatch("x", "unknown", 0, "none")
                match.original = "y"  # type: ignore[misc]
                return match.original
        elif item["kind"] == "normalizer_methods":
            def fn() -> dict[str, Any]:
                return {
                    "normalize_value_missing0": capture_value(
                        lambda: r.normalize_value()  # type: ignore[call-arg]
                    ),
                    "normalize_value_missing1": capture_value(
                        lambda: r.normalize_value("email")  # type: ignore[call-arg]
                    ),
                    "normalize_value_positional_region": capture_value(
                        lambda: r.normalize_value("phone", "(202) 555-0143", "US")  # type: ignore[call-arg]
                    ),
                    "phone_static_keyword": capture_value(
                        lambda: r.PhoneNormalizer.normalize(
                            "(202) 555-0143",
                            default_region="US",
                        )
                    ),
                    "phone_static_positional_region": capture_value(
                        lambda: r.PhoneNormalizer.normalize("(202) 555-0143", "US")  # type: ignore[misc]
                    ),
                    "phone_static_missing": capture_value(
                        lambda: r.PhoneNormalizer.normalize()  # type: ignore[call-arg]
                    ),
                    "phone_instance_keyword": capture_value(
                        lambda: r.PhoneNormalizer().normalize(
                            "(202) 555-0143",
                            default_region="US",
                        )
                    ),
                    "phone_instance_positional_region": capture_value(
                        lambda: r.PhoneNormalizer().normalize("(202) 555-0143", "US")  # type: ignore[misc]
                    ),
                    "email_instance": capture_value(
                        lambda: r.EmailNormalizer().normalize(" A@EXAMPLE.COM ")
                    ),
                    "email_static_missing": capture_value(
                        lambda: r.EmailNormalizer.normalize()  # type: ignore[call-arg]
                    ),
                    "email_static_extra": capture_value(
                        lambda: r.EmailNormalizer.normalize("A@EXAMPLE.COM", "extra")  # type: ignore[call-arg]
                    ),
                    "email_instance_extra": capture_value(
                        lambda: r.EmailNormalizer().normalize("A@EXAMPLE.COM", "extra")  # type: ignore[call-arg]
                    ),
                    "string_static_extra": capture_value(
                        lambda: r.StringNormalizer.normalize(" x ", "extra")  # type: ignore[call-arg]
                    ),
                    "address_static_extra": capture_value(
                        lambda: r.AddressNormalizer.normalize(" x ", "extra")  # type: ignore[call-arg]
                    ),
                    "postal_static_extra": capture_value(
                        lambda: r.PostalCodeNormalizer.normalize("123", "extra")  # type: ignore[call-arg]
                    ),
                    "boolean_static_extra": capture_value(
                        lambda: r.BooleanNormalizer.normalize("yes", "extra")  # type: ignore[call-arg]
                    ),
                    "list_static_extra": capture_value(
                        lambda: r.ListNormalizer.normalize("a,b", "extra")  # type: ignore[call-arg]
                    ),
                    "name_normalize_missing": capture_value(
                        lambda: r.NameNormalizer.normalize()  # type: ignore[call-arg]
                    ),
                    "name_normalize_extra": capture_value(
                        lambda: r.NameNormalizer.normalize("Ada", "extra")  # type: ignore[call-arg]
                    ),
                    "name_parse_missing": capture_value(
                        lambda: r.NameNormalizer.parse()  # type: ignore[call-arg]
                    ),
                    "name_parse_extra": capture_value(
                        lambda: r.NameNormalizer.parse("Ada", "extra")  # type: ignore[call-arg]
                    ),
                    "name_parse_nonstring": capture_value(
                        lambda: r.NameNormalizer.parse(123)  # type: ignore[arg-type]
                    ),
                    "name_parse_none": capture_value(
                        lambda: r.NameNormalizer.parse(None)  # type: ignore[arg-type]
                    ),
                    "name_normalize_none": capture_value(
                        lambda: r.NameNormalizer.normalize(None)  # type: ignore[arg-type]
                    ),
                }
        elif item["kind"] == "strategy_constructors":
            def fn() -> dict[str, Any]:
                registry = r.PatternRegistry()

                def describe(strategy: Any) -> dict[str, Any]:
                    return {
                        "name": strategy.name,
                        "header_only": strategy.header_only,
                    }

                return {
                    "exact0": capture_value(lambda: r.ExactMatchStrategy()),  # type: ignore[call-arg]
                    "exact1": capture_value(lambda: describe(r.ExactMatchStrategy(registry))),
                    "exact2": capture_value(lambda: r.ExactMatchStrategy(registry, "extra")),  # type: ignore[call-arg]
                    "normalized0": capture_value(lambda: r.NormalizedMatchStrategy()),  # type: ignore[call-arg]
                    "normalized1": capture_value(lambda: describe(r.NormalizedMatchStrategy(registry))),
                    "normalized2": capture_value(lambda: r.NormalizedMatchStrategy(registry, "extra")),  # type: ignore[call-arg]
                    "fuzzy0": capture_value(lambda: r.FuzzyMatchStrategy()),  # type: ignore[call-arg]
                    "fuzzy1": capture_value(lambda: describe(r.FuzzyMatchStrategy(registry))),
                    "fuzzy2": capture_value(lambda: r.FuzzyMatchStrategy(registry, "extra")),  # type: ignore[call-arg]
                    "heuristic0": capture_value(lambda: describe(r.HeuristicMatchStrategy())),
                    "heuristic1": capture_value(lambda: describe(r.HeuristicMatchStrategy("US"))),
                    "heuristic2": capture_value(lambda: r.HeuristicMatchStrategy("US", "extra")),  # type: ignore[call-arg]
                }
        else:
            raise AssertionError(item["kind"])
        output["objects"][item["id"]] = capture(fn)
    return output


def js_results() -> dict[str, Any]:
    env = os.environ.copy()
    proc = subprocess.run(
        ["node", str(JS_PROBE)],
        cwd=ROOT,
        input=json.dumps(CASES),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    return json.loads(proc.stdout)


def main() -> int:
    py = python_results()
    js = js_results()
    mismatches: list[dict[str, Any]] = []
    for section in py:
        for case_id, py_value in py[section].items():
            js_value = js[section][case_id]
            if py_value != js_value:
                mismatches.append(
                    {
                        "section": section,
                        "id": case_id,
                        "python": py_value,
                        "js": js_value,
                    }
                )
    print(json.dumps({"mismatch_count": len(mismatches), "mismatches": mismatches}, indent=2, sort_keys=True))
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
