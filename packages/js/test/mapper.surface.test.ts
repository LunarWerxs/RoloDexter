// Split out of the former monolithic mapper.test.ts (2572 lines, over the
// oversized-files gate of 2500). Same tests, grouped by topic. Shared
// CLI/version-probe helpers live in _mapper_test_helpers.ts.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  __version__,
  __all__,
  AddressNormalizer,
  BooleanNormalizer,
  CanonicalField,
  ContactMapper,
  EmailNormalizer,
  FieldMatch,
  is_number_match,
  ListNormalizer,
  NameNormalizer,
  NormalizationError,
  PhoneNormalizer,
  PatternRegistry,
  PatternLoadError,
  PostalCodeNormalizer,
  RolodexterError,
  StringNormalizer,
  normalize_value,
  version,
} from "../src/index.js";
import { VERSION_FROM_PACKAGE_JSON, packageRoot } from "./_mapper_test_helpers.js";

test("pattern registry loads the synced Python truth table", () => {
  const pythonPatterns = JSON.parse(
    readFileSync(new URL("../../../../src/rolodexter/patterns.json", import.meta.url), "utf8"),
  ) as { fields: Record<string, string[]> };
  const registry = new PatternRegistry();

  assert.deepEqual(registry.canonical_fields.sort(), Object.keys(pythonPatterns.fields).sort());
  assert.equal(registry.exact_lookup("fname"), "first_name");
  assert.equal(registry.exact_lookup("MobilePhone"), "phone");
  assert.equal(registry.exact_lookup("not-a-known-alias"), null);
  assert.ok(registry.all_aliases.includes("fname"));
  assert.ok(registry.canonical_fields.includes("phone"));
  assert.equal("exactLookup" in registry, false);
  for (const name of ["data", "reverseIndex", "aliasSet", "aliases", "fields", "loadedLanguageCodes", "languages", "buildIndexes", "addAlias"]) {
    assert.equal(name in registry, false, `${name} should stay private`);
  }

  const customPatterns = { version: "probe", fields: { custom: ["Alias One"] } };
  const positional = new PatternRegistry(customPatterns);
  assert.equal(positional.version, "probe");
  assert.equal(positional.exact_lookup("Alias One"), "custom");
  assert.deepEqual(positional.canonical_fields, ["custom"]);
  assert.equal(String(positional), "PatternRegistry(aliases=1, languages=[], version='probe')");

  const positionalOverride = new PatternRegistry(customPatterns, null, null, { Override: "custom2" });
  assert.equal(positionalOverride.exact_lookup("Override"), "custom2");
  assert.throws(
    () => new (PatternRegistry as unknown as new (...args: unknown[]) => PatternRegistry)(null, null, null, null, "extra"),
    {
      name: "TypeError",
      message: "PatternRegistry.__init__() takes from 1 to 5 positional arguments but 6 were given",
    },
  );
  assert.throws(
    () => new PatternRegistry({ patterns: [] as never }),
    { name: "PatternLoadError", message: "Invalid custom patterns: top level must be an object" },
  );
  for (const patterns of [
    { version: null },
    { fields: null },
    { fields: { custom: "alias" } },
    { fields: { custom: [""] } },
    { expansion: { form_prefixes: "billing_" } },
    { expansion: { form_fields: { email: "" } } },
  ]) {
    assert.throws(
      () => new PatternRegistry({ patterns: patterns as never }),
      { name: "PatternLoadError", message: /Invalid custom patterns/ },
    );
  }
  assert.throws(
    () => new PatternRegistry({ overrides: { "": "email" } }),
    { name: "PatternLoadError", message: /Invalid overrides/ },
  );
  assert.throws(
    () => new PatternRegistry({ languages: 123 as never }),
    { name: "TypeError", message: "'int' object is not iterable" },
  );
});

test("FieldMatch is a runtime export like Python", () => {
  const match = new FieldMatch("fname", "first_name", 1, "exact");

  assert.equal(match.original, "fname");
  assert.equal(match.canonical, "first_name");
  assert.equal(match.is_matched, true);
  assert.equal(new FieldMatch("x", "unknown", 0, "none").is_matched, false);
  assert.equal("isMatched" in match, false);
});

test("CanonicalField members expose Python enum-like values", () => {
  assert.equal(CanonicalField.PHONE.name, "PHONE");
  assert.equal(CanonicalField.PHONE.value, "phone");
  assert.equal(String(CanonicalField.PHONE), "CanonicalField.PHONE");
  assert.equal(CanonicalField.PHONE.valueOf(), "phone");
  assert.equal(JSON.stringify(CanonicalField.PHONE), '"phone"');
  assert.equal(CanonicalField("phone"), CanonicalField.PHONE);
  assert.ok([...CanonicalField].includes(CanonicalField.UNKNOWN));
  assert.equal(normalize_value(CanonicalField.EMAIL, " A@EXAMPLE.COM "), "a@example.com");
  assert.equal(normalize_value(CanonicalField.PHONE, "(202) 555-0143", { default_region: "US" }), "+12025550143");
});

test("root version exports mirror Python package shape", () => {
  assert.equal(__version__, version);
  assert.equal(__version__, VERSION_FROM_PACKAGE_JSON);
  assert.deepEqual(__all__, [
    "SUPPORTED_LANGUAGES",
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
    "MappingProfile",
    "MappingResult",
    "MappingSchema",
    "MatchStrategy",
    "MatchType",
    "NameNormalizer",
    "NormalizationError",
    "NormalizedMatchStrategy",
    "NumberType",
    "PatternLoadError",
    "PatternRegistry",
    "PhoneNormalizer",
    "PhoneNumber",
    "PhoneNumberMatch",
    "PhoneNumberMatcher",
    "PostalCodeNormalizer",
    "RolodexterError",
    "StringNormalizer",
    "format_e164",
    "format_international",
    "format_national",
    "generate_language",
    "is_number_match",
    "is_valid",
    "normalize_value",
    "number_type",
    "parse",
  ]);
});

test("published package root exports only the Python root surface", () => {
  const result = spawnSync(
    process.execPath,
    [
      "--input-type=module",
      "-e",
      "import * as r from 'rolodexter'; console.log(JSON.stringify(Object.keys(r).sort()))",
    ],
    { cwd: packageRoot(), encoding: "utf8" },
  );

  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout) as string[], [...__all__, "__all__", "__version__"].sort());
});

test("core subpath exposes the explicit Python core surface", async () => {
  const core = await import("../src/core.js");

  assert.deepEqual(core.__all__, [
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
    "MappingProfile",
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
  ]);
  assert.deepEqual(Object.keys(core).sort(), [...core.__all__, "__all__"].sort());
});

test("error classes expose Python-like class names", () => {
  assert.equal(new RolodexterError("x").name, "RolodexterError");
  assert.equal(new PatternLoadError("x").name, "PatternLoadError");
  assert.equal(new NormalizationError("x").name, "NormalizationError");
});

test("normalizer instances expose Python-style normalize methods", () => {
  assert.equal(new PhoneNormalizer().normalize("(202) 555-0143", { default_region: "US" }), "+12025550143");
  assert.throws(
    () => new PhoneNormalizer().normalize("(202) 555-0143", "US" as never),
    /PhoneNormalizer\.normalize\(\) takes 2 positional arguments but 3 were given/,
  );
  assert.equal(new EmailNormalizer().normalize(" ADA@EXAMPLE.COM "), "ada@example.com");
  assert.equal(new NameNormalizer().normalize("ada lovelace"), "Ada Lovelace");
  assert.equal(new NameNormalizer().parse("Dr. Ada Lovelace Jr.").suffix, "Jr.");
  assert.throws(
    () => new NameNormalizer().parse(123 as never),
    (error: unknown) => error instanceof Error &&
      error.name === "AttributeError" &&
      error.message === "'int' object has no attribute 'strip'",
  );
  assert.equal(new AddressNormalizer().normalize("  5th   mcdonald ave  "), "5th McDonald Ave");
  assert.equal(new StringNormalizer().normalize("  hello  "), "hello");
  assert.equal(new PostalCodeNormalizer().normalize("k1a0b1"), "K1A 0B1");
  assert.equal(new BooleanNormalizer().normalize("yes"), true);
  assert.deepEqual(new ListNormalizer().normalize("a, b"), ["a", "b"]);
});

test("shared golden corpora match TypeScript mapper parity", () => {
  const corpora = JSON.parse(
    readFileSync(new URL("../../../../tests/fixtures/golden_corpora.json", import.meta.url), "utf8"),
  ) as Record<string, Record<string, string>>;
  const mapper = new ContactMapper();

  for (const [corpus, expected] of Object.entries(corpora)) {
    for (const [header, canonical] of Object.entries(expected)) {
      assert.equal(mapper.identify(header).canonical, canonical, `${corpus}: ${header}`);
    }
  }
});

test("shared conformance fixtures match Python-diverged behaviors", () => {
  const cases = JSON.parse(
    readFileSync(new URL("../../../../tests/fixtures/conformance_cases.json", import.meta.url), "utf8"),
  ) as {
    normalize: { id: string; field: string; value: unknown; default_region?: string | null; expected: unknown }[];
    payloads: { id: string; payload: Record<string, unknown>; expected_normalized: Record<string, unknown> }[];
    phones: { id: string; fn: string; a: string; b: string; default_region?: string | null; expected: number }[];
    identify: { id: string; header: string; expected_canonical: string; expected_strategy: string; expected_confidence: number }[];
    schemas: {
      id: string;
      headers: string[];
      mapper_options?: { confidence_threshold?: number };
      expected_matches: Record<string, { canonical: string; confidence: number; strategy: string }>;
    }[];
  };
  const mapper = new ContactMapper();

  for (const c of cases.normalize) {
    const got = normalize_value(c.field, c.value, { default_region: c.default_region ?? null });
    assert.deepEqual(got, c.expected, c.id);
  }

  for (const c of cases.payloads) {
    const result = mapper.map_payload(c.payload);
    for (const [key, expected] of Object.entries(c.expected_normalized)) {
      assert.deepEqual(result.normalized[key], expected, `${c.id}: ${key}`);
    }
  }

  for (const c of cases.phones) {
    assert.equal(c.fn, "is_number_match");
    assert.equal(is_number_match(c.a, c.b, c.default_region ?? null), c.expected, c.id);
  }

  for (const c of cases.identify) {
    const fieldMatch = mapper.identify(c.header);
    assert.equal(fieldMatch.canonical, c.expected_canonical, c.id);
    assert.equal(fieldMatch.strategy, c.expected_strategy, c.id);
    assert.equal(fieldMatch.confidence, c.expected_confidence, c.id);
  }

  for (const c of cases.schemas) {
    const schema = mapper.compile_schema(c.headers, c.mapper_options ?? {});
    for (const [header, expected] of Object.entries(c.expected_matches)) {
      const fieldMatch = schema.matches[header];
      assert.equal(fieldMatch.canonical, expected.canonical, `${c.id}: ${header}`);
      assert.equal(fieldMatch.confidence, expected.confidence, `${c.id}: ${header}`);
      assert.equal(fieldMatch.strategy, expected.strategy, `${c.id}: ${header}`);
    }
  }
});

