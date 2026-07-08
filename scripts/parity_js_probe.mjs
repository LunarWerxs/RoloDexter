import fs from "node:fs";
import * as r from "../packages/js/dist/src/index.js";
import * as i18n from "../packages/js/dist/src/i18n.js";

const input = JSON.parse(fs.readFileSync(0, "utf8"));

function simplify(value) {
  if (value === undefined) {
    return { kind: "undefined" };
  }
  if (value instanceof Error) {
    return { kind: "error", name: value.name, message: value.message };
  }
  if (value && typeof value === "object") {
    if (value.constructor?.name === "MappingResult") {
      return {
        normalized: simplify(value.normalized),
        unmapped: simplify(value.unmapped),
        field_matches: simplify(value.field_matches),
        warnings: simplify(value.warnings),
      };
    }
    if (value.constructor?.name === "FieldMatch") {
      return {
        original: value.original,
        canonical: value.canonical,
        confidence: value.confidence,
        strategy: value.strategy,
        service: value.service,
        is_matched: value.is_matched,
      };
    }
    if (value.constructor?.name === "MappingSchema") {
      return {
        matches: simplify(value.matches),
        default_region: simplify(value.default_region),
      };
    }
    if (value.constructor?.name === "PhoneNumber") {
      return {
        calling_code: value.calling_code,
        national_number: value.national_number,
        extension: value.extension,
        raw: value.raw,
        e164: value.e164,
        is_possible: value.is_possible,
        is_valid: value.is_valid,
        country_codes: value.country_codes,
      };
    }
    if (Array.isArray(value)) {
      return value.map(simplify);
    }
    return Object.fromEntries(Object.entries(value).map(([key, val]) => [key, simplify(val)]));
  }
  return value;
}

function capture(fn) {
  try {
    return { ok: true, value: simplify(fn()) };
  } catch (error) {
    return { ok: false, error: simplify(error) };
  }
}

function captureValue(fn) {
  try {
    return simplify(fn());
  } catch (error) {
    return simplify(error);
  }
}

const output = {
  normalize: {},
  payloads: {},
  phones: {},
  schemas: {},
  objects: {},
};

for (const item of input.normalize ?? []) {
  output.normalize[item.id] = capture(() => r.normalize_value(item.field, item.value, { default_region: item.default_region ?? null }));
}

for (const item of input.payloads ?? []) {
  output.payloads[item.id] = capture(() => {
    const mapper = new r.ContactMapper(item.mapper_options ?? {});
    return mapper.map_payload(item.payload, item.options ?? {});
  });
}

for (const item of input.schemas ?? []) {
  output.schemas[item.id] = capture(() => {
    const mapper = new r.ContactMapper(item.mapper_options ?? {});
    return mapper.compile_schema(item.headers, item.options ?? {});
  });
}

for (const item of input.phones ?? []) {
  output.phones[item.id] = capture(() => {
    if (item.fn === "parse") {
      return r.parse(item.value, item.default_region ?? null);
    }
    if (item.fn === "format_e164") {
      return r.format_e164(item.value, item.default_region ?? null);
    }
    if (item.fn === "is_valid") {
      return r.is_valid(item.value, item.default_region ?? null);
    }
    if (item.fn === "is_number_match") {
      return r.is_number_match(item.a, item.b, item.default_region ?? null);
    }
    if (item.fn === "matcher") {
      return [...new r.PhoneNumberMatcher(item.value, item.default_region ?? null, { max_matches: item.max_matches ?? null })].map((match) => ({
        start: match.start,
        end: match.end,
        raw_string: match.raw_string,
        number: simplify(match.number),
      }));
    }
    throw new Error(`unknown phone fn: ${item.fn}`);
  });
}

for (const item of input.objects ?? []) {
  output.objects[item.id] = capture(() => {
    if (item.kind === "mapping_result_helpers") {
      const result = new r.ContactMapper(item.mapper_options ?? {}).map_payload(item.payload, item.options ?? {});
      return {
        matched_count: result.matched_count,
        unmatched_count: result.unmatched_count,
        match_rate: result.match_rate,
        dict: result.to_dict(),
        explain: result.explain(),
        all_phones: result.get_all_phones(),
        match_fname: simplify(result.get_match("fname")),
        match_missing: simplify(result.get_match("missing")),
      };
    }
    if (item.kind === "schema_helpers") {
      const schema = new r.ContactMapper(item.mapper_options ?? {}).compile_schema(item.headers, item.options ?? {});
      return {
        column_map: simplify(schema.column_map()),
        unmatched_headers: simplify(schema.unmatched_headers()),
        matches_get_missing: simplify(schema.matches.get("missing")),
        applied: simplify(schema.apply(item.row)),
        apply_missing: captureValue(() => schema.apply()),
        apply_positional_options: captureValue(() => schema.apply(item.row, 2)),
        apply_unknown_kw: captureValue(() => schema.apply(item.row, { bogus: true })),
        apply_extra_positional: captureValue(() => schema.apply(item.row, {}, "extra")),
      };
    }
    if (item.kind === "registry_helpers") {
      const registry = item.options === undefined ? new r.PatternRegistry() : new r.PatternRegistry(item.options ?? {});
      const aliases = registry.all_aliases;
      aliases.push("__mutated__");
      const customPatterns = { version: "probe", fields: { custom: ["Alias One"] } };
      const positional = new r.PatternRegistry(customPatterns);
      const positionalOverride = new r.PatternRegistry(
        customPatterns,
        null,
        null,
        { Override: "custom2" },
      );
      return {
        exact_lookup: registry.exact_lookup(item.header),
        exact_lookup_missing: registry.exact_lookup("not-a-known-alias"),
        canonical_fields_prefix: registry.canonical_fields.slice(0, 5),
        all_aliases_mutation_leaked: registry.all_aliases.includes("__mutated__"),
        version: registry.version,
        available_languages_count: registry.available_languages.length,
        cached_languages_type: Array.isArray(registry.cached_languages) ? "array" : typeof registry.cached_languages,
        loaded_languages: registry.loaded_languages,
        repr: String(positional),
        positional_patterns: {
          version: positional.version,
          lookup: positional.exact_lookup("Alias One"),
          fields: positional.canonical_fields,
        },
        positional_override: positionalOverride.exact_lookup("Override"),
        too_many_args: captureValue(() => new r.PatternRegistry(null, null, null, null, "extra")),
        patterns_list: captureValue(() => new r.PatternRegistry({ patterns: [] })),
        languages_int: captureValue(() => new r.PatternRegistry({ languages: 123 })),
      };
    }
    if (item.kind === "constructors") {
      const phone = new r.PhoneNumber(1, "2025550143", "raw", "99");
      const local = new r.PhoneNumber(1, "5551212", "raw");
      return {
        field_positional: simplify(new r.FieldMatch("x", "unknown", 0, "none")),
        field_with_service: simplify(new r.FieldMatch("x", "unknown", 0, "none", "legacy")),
        mapping_result_positional: simplify(new r.MappingResult({}, {}, [new r.FieldMatch("x", "unknown", 0, "none")])),
        phone_positional: simplify(phone),
        phone_positional_display: {
          str: String(phone),
          format_international: r.format_international(phone),
          format_national: r.format_national(phone),
          number_type: r.number_type(phone),
          local_format_national: r.format_national(local),
        },
        match_positional: simplify(new r.PhoneNumberMatch(1, 4, "raw", new r.PhoneNumber(1, "2025550143", "raw"))),
      };
    }
    if (item.kind === "object_constructor_rejections") {
      return {
        field: captureValue(() => new r.FieldMatch({ original: "x", canonical: "unknown", confidence: 0, strategy: "none" })),
        mapping_result: captureValue(() => new r.MappingResult({ normalized: {}, unmapped: {}, field_matches: [] })),
        mapping_schema: captureValue(() => new r.MappingSchema({ matches: {}, mapper: new r.ContactMapper() })),
        phone: captureValue(() => new r.PhoneNumber({ calling_code: 1, national_number: "2025550143", raw: "x" })),
      };
    }
    if (item.kind === "constructor_arity_errors") {
      return {
        FieldMatch0: captureValue(() => new r.FieldMatch()),
        FieldMatch1: captureValue(() => new r.FieldMatch("x")),
        FieldMatch6: captureValue(() => new r.FieldMatch("x", "unknown", 0, "none", null, "extra")),
        MappingResult0: captureValue(() => new r.MappingResult()),
        MappingResult1: captureValue(() => new r.MappingResult({})),
        MappingResult2: captureValue(() => new r.MappingResult({}, {})),
        MappingResult5: captureValue(() => new r.MappingResult({}, {}, [], [], "extra")),
        MappingSchema0: captureValue(() => new r.MappingSchema()),
        MappingSchema1: captureValue(() => new r.MappingSchema({})),
        MappingSchema4: captureValue(() => new r.MappingSchema({}, new r.ContactMapper(), null, "extra")),
        PhoneNumber0: captureValue(() => new r.PhoneNumber()),
        PhoneNumber1: captureValue(() => new r.PhoneNumber(1)),
        PhoneNumber2: captureValue(() => new r.PhoneNumber(1, "202")),
        PhoneNumber6: captureValue(() => new r.PhoneNumber(1, "202", "raw", null, null, "extra")),
        PhoneNumberMatch0: captureValue(() => new r.PhoneNumberMatch()),
        PhoneNumberMatch1: captureValue(() => new r.PhoneNumberMatch(1)),
        PhoneNumberMatch5: captureValue(() => new r.PhoneNumberMatch(1, 2, "raw", new r.PhoneNumber(1, "202", "raw"), "extra")),
      };
    }
    if (item.kind === "i18n_main_arity") {
      return {
        one_arg: captureValue(() => i18n.main(["--help"])),
      };
    }
    if (item.kind === "i18n_public_helpers") {
      return {
        load_missing: captureValue(() => i18n.load_cached("__missing__")),
        load_missing_arg: captureValue(() => i18n.load_cached()),
        load_extra_arg: captureValue(() => i18n.load_cached("__missing__", "extra")),
        get_writable_extra_arg: captureValue(() => i18n.get_writable_cache_dir("extra")),
        get_cache_extra_arg: captureValue(() => i18n.get_cache_dir("extra")),
        get_all_extra_arg: captureValue(() => i18n.get_all_cache_dirs("extra")),
        discover_extra_arg: captureValue(() => i18n.discover_cached("extra")),
        generate_missing_arg: captureValue(() => i18n.generate_language()),
        generate_bad: captureValue(() => i18n.generate_language("__missing__")),
        generate_positional_bool: captureValue(() => i18n.generate_language("__missing__", true)),
        generate_keyword_options: captureValue(() => i18n.generate_language("__missing__", { force: true })),
        generate_badkw: captureValue(() => i18n.generate_language("__missing__", { cache_dir: "x" })),
      };
    }
    if (item.kind === "mapper_runtime_rejections") {
      const mapper = new r.ContactMapper();
      return {
        identify_missing_arg: captureValue(() => mapper.identify()),
        identify_positional_value: captureValue(() => mapper.identify("Mystery", "ada@example.com")),
        map_payload_missing_arg: captureValue(() => mapper.map_payload()),
        map_payload_positional_options: captureValue(() => mapper.map_payload({ fname: "Ada" }, 2)),
        map_payload_array: captureValue(() => mapper.map_payload([["fname", "Ada"]])),
        map_batch_missing_arg: captureValue(() => mapper.map_batch()),
        map_batch_positional_options: captureValue(() => mapper.map_batch([{ fname: "Ada" }], 2)),
        map_stream_missing_arg: captureValue(() => mapper.map_stream()),
        map_stream_positional_options: captureValue(() => mapper.map_stream([{ fname: "Ada" }], 2)),
        compile_schema_missing_arg: captureValue(() => mapper.compile_schema()),
        compile_schema_positional_options: captureValue(() => mapper.compile_schema(["fname"], 2)),
        map_dataframe_missing_arg: captureValue(() => mapper.map_dataframe()),
        map_dataframe_positional_options: captureValue(() => mapper.map_dataframe([], 2)),
        ctor_positional: captureValue(() => new r.ContactMapper(2)),
        ctor_bogus: captureValue(() => new r.ContactMapper({ bogus: true })),
        ctor_patterns_list: captureValue(() => new r.ContactMapper({ patterns: [] })),
        ctor_header_cache_string: captureValue(() => new r.ContactMapper({ header_cache_max_size: "2" })),
        cache_info_extra: captureValue(() => mapper.cache_info(1)),
        clear_cache_extra: captureValue(() => mapper.clear_cache(1)),
      };
    }
    if (item.kind === "phone_runtime_edges") {
      const match = new r.PhoneNumberMatch(1, 4, "raw", new r.PhoneNumber(1, "2025550143", "raw"));
      return {
        parse_missing: captureValue(() => r.parse()),
        parse_extra: captureValue(() => r.parse("x", "US", "extra")),
        format_e164_missing: captureValue(() => r.format_e164()),
        format_e164_extra: captureValue(() => r.format_e164("x", "US", "extra")),
        is_valid_missing: captureValue(() => r.is_valid()),
        is_valid_extra: captureValue(() => r.is_valid("x", "US", "extra")),
        format_international_missing: captureValue(() => r.format_international()),
        format_international_extra: captureValue(() => r.format_international(new r.PhoneNumber(1, "202", "raw"), "extra")),
        format_international_wrong: captureValue(() => r.format_international({})),
        format_national_missing: captureValue(() => r.format_national()),
        format_national_extra: captureValue(() => r.format_national(new r.PhoneNumber(1, "202", "raw"), "extra")),
        format_national_wrong: captureValue(() => r.format_national("x")),
        number_type_missing: captureValue(() => r.number_type()),
        number_type_extra: captureValue(() => r.number_type(new r.PhoneNumber(1, "202", "raw"), "extra")),
        number_type_wrong: captureValue(() => r.number_type(null)),
        is_number_match_missing0: captureValue(() => r.is_number_match()),
        is_number_match_missing1: captureValue(() => r.is_number_match("x")),
        is_number_match_extra: captureValue(() => r.is_number_match("x", "y", "US", "extra")),
        match_repr: String(match),
        match_str: String(match),
        matcher_null_len: new r.PhoneNumberMatcher(null, "US").length,
        matcher_null_list: simplify([...new r.PhoneNumberMatcher(null, "US")]),
        matcher_bad_max: captureValue(() => new r.PhoneNumberMatcher("a +1 202 555 0143", "US", { max_matches: "1" })),
      };
    }
    if (item.kind === "frozen_assignment") {
      const match = new r.FieldMatch("x", "unknown", 0, "none");
      match.original = "y";
      return match.original;
    }
    if (item.kind === "normalizer_methods") {
      return {
        normalize_value_missing0: captureValue(() => r.normalize_value()),
        normalize_value_missing1: captureValue(() => r.normalize_value("email")),
        normalize_value_positional_region: captureValue(() => r.normalize_value("phone", "(202) 555-0143", "US")),
        phone_static_keyword: captureValue(() => r.PhoneNormalizer.normalize("(202) 555-0143", { default_region: "US" })),
        phone_static_positional_region: captureValue(() => r.PhoneNormalizer.normalize("(202) 555-0143", "US")),
        phone_static_missing: captureValue(() => r.PhoneNormalizer.normalize()),
        phone_instance_keyword: captureValue(() => new r.PhoneNormalizer().normalize("(202) 555-0143", { default_region: "US" })),
        phone_instance_positional_region: captureValue(() => new r.PhoneNormalizer().normalize("(202) 555-0143", "US")),
        email_instance: captureValue(() => new r.EmailNormalizer().normalize(" A@EXAMPLE.COM ")),
        email_static_missing: captureValue(() => r.EmailNormalizer.normalize()),
        email_static_extra: captureValue(() => r.EmailNormalizer.normalize("A@EXAMPLE.COM", "extra")),
        email_instance_extra: captureValue(() => new r.EmailNormalizer().normalize("A@EXAMPLE.COM", "extra")),
        string_static_extra: captureValue(() => r.StringNormalizer.normalize(" x ", "extra")),
        address_static_extra: captureValue(() => r.AddressNormalizer.normalize(" x ", "extra")),
        postal_static_extra: captureValue(() => r.PostalCodeNormalizer.normalize("123", "extra")),
        boolean_static_extra: captureValue(() => r.BooleanNormalizer.normalize("yes", "extra")),
        list_static_extra: captureValue(() => r.ListNormalizer.normalize("a,b", "extra")),
        name_normalize_missing: captureValue(() => r.NameNormalizer.normalize()),
        name_normalize_extra: captureValue(() => r.NameNormalizer.normalize("Ada", "extra")),
        name_parse_missing: captureValue(() => r.NameNormalizer.parse()),
        name_parse_extra: captureValue(() => r.NameNormalizer.parse("Ada", "extra")),
        name_parse_nonstring: captureValue(() => r.NameNormalizer.parse(123)),
        name_parse_none: captureValue(() => r.NameNormalizer.parse(null)),
        name_normalize_none: captureValue(() => r.NameNormalizer.normalize(null)),
      };
    }
    if (item.kind === "strategy_constructors") {
      const registry = new r.PatternRegistry();
      const describe = (strategy) => ({
        name: strategy.name,
        header_only: strategy.header_only,
      });
      return {
        exact0: captureValue(() => new r.ExactMatchStrategy()),
        exact1: captureValue(() => describe(new r.ExactMatchStrategy(registry))),
        exact2: captureValue(() => new r.ExactMatchStrategy(registry, "extra")),
        normalized0: captureValue(() => new r.NormalizedMatchStrategy()),
        normalized1: captureValue(() => describe(new r.NormalizedMatchStrategy(registry))),
        normalized2: captureValue(() => new r.NormalizedMatchStrategy(registry, "extra")),
        fuzzy0: captureValue(() => new r.FuzzyMatchStrategy()),
        fuzzy1: captureValue(() => describe(new r.FuzzyMatchStrategy(registry))),
        fuzzy2: captureValue(() => new r.FuzzyMatchStrategy(registry, "extra")),
        heuristic0: captureValue(() => describe(new r.HeuristicMatchStrategy())),
        heuristic1: captureValue(() => describe(new r.HeuristicMatchStrategy("US"))),
        heuristic2: captureValue(() => new r.HeuristicMatchStrategy("US", "extra")),
      };
    }
    throw new Error(`unknown object kind: ${item.kind}`);
  });
}

console.log(JSON.stringify(output, null, 2));
