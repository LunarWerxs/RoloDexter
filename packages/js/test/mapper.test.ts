import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import {
  __version__,
  __all__,
  AddressNormalizer,
  BooleanNormalizer,
  CanonicalField,
  ContactMapper,
  discover_cached,
  EmailNormalizer,
  ExactMatchStrategy,
  FieldMatch,
  format_e164,
  format_international,
  format_national,
  FuzzyMatchStrategy,
  generateLanguage,
  generateLanguageAsync,
  generate_language,
  get_all_cache_dirs,
  get_cache_dir,
  get_writable_cache_dir,
  HeuristicMatchStrategy,
  is_number_match,
  is_valid,
  ListNormalizer,
  load_cached,
  MappingProfile,
  MappingResult,
  MappingSchema,
  MatchStrategy,
  MatchType,
  NameNormalizer,
  NormalizedMatchStrategy,
  NormalizationError,
  NumberType,
  PhoneNumber,
  PhoneNumberMatch,
  PhoneNumberMatcher,
  PhoneNormalizer,
  PatternRegistry,
  PatternLoadError,
  PostalCodeNormalizer,
  RolodexterError,
  StringNormalizer,
  SUPPORTED_LANGUAGES,
  number_type,
  normalize_value,
  parse,
  version,
} from "../src/index.js";

const CLI_EOL = process.platform === "win32" ? "\r\n" : "\n";

function cliPath(): string {
  return fileURLToPath(new URL("../src/cli.js", import.meta.url));
}

function i18nCliPath(): string {
  return fileURLToPath(new URL("../src/i18n.js", import.meta.url));
}

function runCli(args: string[], cwd?: string) {
  return spawnSync(process.execPath, [cliPath(), ...args], {
    cwd,
    encoding: "utf8",
  });
}

function runI18nCli(args: string[], cwd?: string) {
  return spawnSync(process.execPath, [i18nCliPath(), ...args], {
    cwd,
    encoding: "utf8",
  });
}

async function runCliWithClosedStdout(args: string[], cwd?: string) {
  const child = spawn(process.execPath, [cliPath(), ...args], {
    cwd,
    stdio: ["ignore", "pipe", "pipe"],
  });
  const stdoutChunks: Buffer[] = [];
  const stderrChunks: Buffer[] = [];
  let closedStdout = false;

  child.stdout.on("data", (chunk: Buffer) => {
    if (!closedStdout) {
      closedStdout = true;
      stdoutChunks.push(Buffer.from(chunk.subarray(0, 1)));
      child.stdout.destroy();
    }
  });
  child.stderr.on("data", (chunk: Buffer) => {
    stderrChunks.push(Buffer.from(chunk));
  });

  const status = await new Promise<number | null>((resolve, reject) => {
    const timer = setTimeout(() => {
      child.kill();
      reject(new Error("timed out waiting for CLI closed-stdout probe"));
    }, 15_000);
    child.once("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.once("close", (code) => {
      clearTimeout(timer);
      resolve(code);
    });
  });

  return {
    status,
    stdout: Buffer.concat(stdoutChunks).toString("utf8"),
    stderr: Buffer.concat(stderrChunks).toString("utf8"),
  };
}

function packageRoot(): string {
  return fileURLToPath(new URL("../..", import.meta.url));
}

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
  assert.equal(__version__, "2.10.0");
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

test("i18n registry introspection mirrors Python cache-loading contract", () => {
  const registry = new PatternRegistry({ languages: ["es"] });

  assert.equal(SUPPORTED_LANGUAGES.es[1], "Spanish");
  assert.ok(registry.available_languages.includes("es"));
  assert.equal("availableLanguages" in registry, false);
  assert.equal("loadedLanguages" in registry, false);
  assert.equal("cachedLanguages" in registry, false);
  assert.deepEqual(registry.cached_languages, Object.keys(discover_cached()).sort());
  assert.equal(load_cached("__missing__"), null);
  assert.equal(typeof get_cache_dir(), "string");
  assert.ok(Array.isArray(get_all_cache_dirs()));
  assert.throws(
    () => (get_writable_cache_dir as unknown as (extra: unknown) => unknown)("x"),
    { name: "TypeError", message: "get_writable_cache_dir() takes 0 positional arguments but 1 was given" },
  );
  assert.throws(
    () => (get_cache_dir as unknown as (extra: unknown) => unknown)("x"),
    { name: "TypeError", message: "get_cache_dir() takes 0 positional arguments but 1 was given" },
  );
  assert.throws(
    () => (get_all_cache_dirs as unknown as (extra: unknown) => unknown)("x"),
    { name: "TypeError", message: "get_all_cache_dirs() takes 0 positional arguments but 1 was given" },
  );
  assert.throws(
    () => (discover_cached as unknown as (extra: unknown) => unknown)("x"),
    { name: "TypeError", message: "discover_cached() takes 0 positional arguments but 1 was given" },
  );
  assert.throws(
    () => (load_cached as unknown as () => unknown)(),
    { name: "TypeError", message: "load_cached() missing 1 required positional argument: 'lang_code'" },
  );
  assert.throws(
    () => (load_cached as unknown as (langCode: string, extra: unknown) => unknown)("__missing__", "x"),
    { name: "TypeError", message: "load_cached() takes 1 positional argument but 2 were given" },
  );
  assert.throws(() => generate_language("__missing__"), { name: "ValueError" });
  assert.throws(
    () => (generate_language as unknown as () => unknown)(),
    { name: "TypeError", message: "generate_language() missing 1 required positional argument: 'lang_code'" },
  );
  assert.throws(
    () => (generate_language as unknown as (langCode: string, options: unknown) => unknown)("__missing__", true),
    { name: "TypeError", message: "generate_language() takes 1 positional argument but 2 were given" },
  );
  assert.throws(
    () => (generate_language as unknown as (langCode: string, options: unknown) => unknown)("__missing__", { force: true }),
    { name: "ValueError" },
  );
  assert.throws(
    () => (generate_language as unknown as (langCode: string, options: unknown) => unknown)("__missing__", { cache_dir: "x" }),
    { name: "TypeError", message: "generate_language() got an unexpected keyword argument 'cache_dir'" },
  );
});

test("i18n subpath exposes Python-shaped helper names", async () => {
  const stdoutErrorsBefore = process.stdout.listenerCount("error");
  const i18n = await import("../src/i18n.js");

  assert.equal(process.stdout.listenerCount("error"), stdoutErrorsBefore);
  assert.deepEqual(i18n.__all__, [
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
  ]);
  assert.deepEqual(Object.keys(i18n).sort(), [
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
    "__all__",
  ].sort());
  assert.equal(typeof i18n.get_writable_cache_dir, "function");
  assert.equal(typeof i18n.get_cache_dir, "function");
  assert.equal(typeof i18n.get_all_cache_dirs, "function");
  assert.equal(typeof i18n.load_cached, "function");
  assert.equal(typeof i18n.discover_cached, "function");
  assert.equal(i18n.DEFAULT_TRANSLATE_TIMEOUT, 10);
  assert.equal(i18n.DEFAULT_TRANSLATE_RETRIES, 1);
  assert.equal(i18n.DEFAULT_TRANSLATE_RETRY_BACKOFF, 0.5);
  assert.equal(i18n.MAX_I18N_WORKERS, 8);
  assert.equal("generateLanguageAsync" in i18n, false);
  assert.throws(
    () => (i18n.main as unknown as (argv: string[]) => Promise<number>)(["--help"]),
    { name: "TypeError", message: "main() takes 0 positional arguments but 1 was given" },
  );
});

test("i18n CLI mirrors Python list and dry-run workflows", () => {
  const listed = runI18nCli(["--list"]);

  assert.equal(listed.status, 0, listed.stderr);
  assert.match(listed.stdout, /Supported languages \(40\):/);
  assert.match(listed.stdout, /es\s+Spanish\s+\[(cached|not generated)\]/);

  const dryRun = runI18nCli(["--dry-run", "--languages", "es"]);
  assert.equal(dryRun.status, 0, dryRun.stderr);
  assert.match(dryRun.stdout, /Generating 1 language\(s\)/);
  assert.match(dryRun.stdout, /\[es\] Spanish: (cached|would generate)/);

  const abbreviated = runI18nCli(["--lang", "es", "--dry-run"]);
  assert.equal(abbreviated.status, 0, abbreviated.stderr);
  assert.match(abbreviated.stdout, /Generating 1 language\(s\)/);

  const missingLanguageValue = runI18nCli(["--languages"]);
  assert.equal(missingLanguageValue.status, 2);
  assert.match(missingLanguageValue.stderr, /^usage: (python\.exe|python) -m rolodexter\.i18n/);
  assert.match(missingLanguageValue.stderr, /argument --languages: expected one argument/);

  const missingLanguageBeforeFlag = runI18nCli(["--languages", "--dry-run"]);
  assert.equal(missingLanguageBeforeFlag.status, 2);
  assert.match(missingLanguageBeforeFlag.stderr, /argument --languages: expected one argument/);

  const missingLanguageBeforeHelp = runI18nCli(["--languages", "--help"]);
  assert.equal(missingLanguageBeforeHelp.status, 2);
  assert.equal(missingLanguageBeforeHelp.stdout, "");
  assert.match(missingLanguageBeforeHelp.stderr, /argument --languages: expected one argument/);

  const trailingEmptyLanguage = runI18nCli(["--dry-run", "--languages", "es,"]);
  assert.equal(trailingEmptyLanguage.status, 1);
  assert.match(trailingEmptyLanguage.stdout, /Unknown language code\(s\): \[''\]/);

  const invalidWorkers = runI18nCli(["--dry-run", "--languages", "es", "--workers=abc"]);
  assert.equal(invalidWorkers.status, 2);
  assert.match(invalidWorkers.stderr, /argument --workers: invalid _non_negative_int value/);

  const invalidTimeout = runI18nCli(["--dry-run", "--languages", "es", "--timeout=1abc"]);
  assert.equal(invalidTimeout.status, 2);
  assert.match(invalidTimeout.stderr, /argument --timeout: invalid _non_negative_float value/);

  const negativeDotTimeout = runI18nCli(["--dry-run", "--languages", "es", "--timeout", "-.5"]);
  assert.equal(negativeDotTimeout.status, 2);
  assert.match(negativeDotTimeout.stderr, /argument --timeout: must be non-negative/);

  const signedWorkers = runI18nCli(["--dry-run", "--languages", "es", "--workers", "+1"]);
  assert.equal(signedWorkers.status, 0, signedWorkers.stderr);
  assert.match(signedWorkers.stdout, /Generating 1 language\(s\)/);
});

test("CommonJS consumers can require root and i18n subpath", () => {
  const result = spawnSync(
    process.execPath,
    [
      "-e",
      "const r=require('rolodexter'); const core=require('rolodexter/core'); const i=require('rolodexter/i18n'); console.log(r.__version__, new r.ContactMapper().map_payload({fname:'Ada'}).normalized.first_name, typeof core.ContactMapper, 'generateLanguageAsync' in core, 'parse' in core, typeof i.generate_language, typeof i.load_cached, 'generateLanguageAsync' in i)",
    ],
    { cwd: packageRoot(), encoding: "utf8" },
  );

  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout.trim(), "2.10.0 Ada function false false function function false");
});

test("generate_language can build and cache an i18n pack", async () => {
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-js-i18n-"));
  try {
    const generated = generateLanguage("es", {
      force: true,
      cache_dir: dir,
      retries: 0,
      translator: (phrase) => (phrase === "first name" ? "名字 中文" : `ES ${phrase}`),
    });

    assert.equal(generated.language_code, "es");
    assert.equal(generated.language_name, "Spanish");
    assert.ok(generated.fields?.first_name?.includes("名字 中文"));
    assert.ok(generated.fields?.first_name?.includes("Ming Zi  Zhong Wen"));
    assert.ok(generated.fields?.first_name?.includes("Ming_Zi_Zhong_Wen"));
    assert.ok(generated.fields?.first_name?.includes("MingZiZhongWen"));
    assert.ok(generated.generated_at);

    const cached = JSON.parse(readFileSync(join(dir, "es.json"), "utf8")) as { fields?: Record<string, string[]> };
    assert.deepEqual(cached?.fields?.first_name, generated.fields?.first_name);

    const syncCached = generateLanguage("es", { cache_dir: dir });
    assert.equal((syncCached as { language_code?: string }).language_code, "es");
    assert.equal("then" in generated, false);

    const asyncGenerated = await generateLanguageAsync("es", {
      force: true,
      cache_dir: dir,
      retries: 0,
      translator: async (phrase) => (phrase === "last name" ? "Apellido" : `ASYNC ${phrase}`),
    });
    assert.ok(asyncGenerated.fields?.last_name?.includes("apellido"));

    const warnings: string[] = [];
    const originalWarn = console.warn;
    console.warn = (message?: unknown) => {
      warnings.push(String(message));
    };
    try {
      const emptyGenerated = generateLanguage("fr", {
        force: true,
        cache_dir: dir,
        retries: 0,
        translator: () => "",
      });
      assert.deepEqual(emptyGenerated.fields, {});
      assert.equal(existsSync(join(dir, "fr.json")), false);
      assert.match(warnings[0] ?? "", /No translations produced for fr; skipping cache write/);
    } finally {
      console.warn = originalWarn;
    }

  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("maps and normalizes a basic contact payload", () => {
  const result = new ContactMapper().map_payload({
    fname: "jane",
    surname: "doe",
    mobile: "(202) 555-0143",
    employer: "Tech Corp",
    "Column 1": "jane.doe@example.com",
  });

  assert.equal(result.normalized.first_name, "Jane");
  assert.equal(result.normalized.last_name, "Doe");
  assert.equal(result.normalized.phone, "+12025550143");
  assert.equal(result.normalized.company, "Tech Corp");
  assert.equal(result.normalized.email, "jane.doe@example.com");
  assert.equal(result.unmatched_count, 0);
});

test("handles normalized headers and dot paths", () => {
  const mapper = new ContactMapper();

  assert.equal(mapper.identify("FirstName").canonical, "first_name");
  assert.equal(mapper.identify("Account.Name").canonical, "company");
  assert.equal(mapper.identify("Phone 1 - Value").canonical, "phone");
  assert.equal(mapper.identify("hs_lead_status").canonical, "lead_status");
});

test("mapper runtime argument and shape errors mirror Python", () => {
  const mapper = new ContactMapper();

  assert.throws(
    () => (mapper.identify as unknown as () => unknown)(),
    { name: "TypeError", message: "ContactMapper.identify() missing 1 required positional argument: 'header'" },
  );
  assert.throws(
    () => (mapper.identify as unknown as (header: string, value: string) => unknown)("Mystery", "ada@example.com"),
    { name: "TypeError", message: "ContactMapper.identify() takes 2 positional arguments but 3 were given" },
  );
  assert.throws(
    () => (mapper.map_payload as unknown as (payload: Record<string, unknown>, options: unknown) => unknown)({ fname: "Ada" }, 2),
    { name: "TypeError", message: "ContactMapper.map_payload() takes 2 positional arguments but 3 were given" },
  );
  assert.throws(
    () => mapper.map_payload([["fname", "Ada"]] as never),
    { name: "AttributeError", message: "'list' object has no attribute 'items'" },
  );
  assert.throws(
    () => (mapper.map_batch as unknown as (payloads: Iterable<Record<string, unknown>>, options: unknown) => unknown)([{ fname: "Ada" }], 2),
    { name: "TypeError", message: "ContactMapper.map_batch() takes 2 positional arguments but 3 were given" },
  );
  assert.throws(
    () => (mapper.map_stream as unknown as (payloads: Iterable<Record<string, unknown>>, options: unknown) => unknown)([{ fname: "Ada" }], 2),
    { name: "TypeError", message: "ContactMapper.map_stream() takes 2 positional arguments but 3 were given" },
  );
  assert.throws(
    () => (mapper.compile_schema as unknown as (headers: Iterable<string>, options: unknown) => unknown)(["fname"], 2),
    { name: "TypeError", message: "ContactMapper.compile_schema() takes 2 positional arguments but 3 were given" },
  );
  assert.throws(
    () => (mapper.map_dataframe as unknown as (df: unknown, options: unknown) => unknown)({ columns: [], rename: () => ({}) }, 2),
    { name: "TypeError", message: "ContactMapper.map_dataframe() takes 2 positional arguments but 3 were given" },
  );
  assert.throws(
    () => new (ContactMapper as unknown as new (...args: unknown[]) => ContactMapper)(2),
    { name: "TypeError", message: "ContactMapper.__init__() takes 1 positional argument but 2 were given" },
  );
  assert.throws(
    () => new ContactMapper({ bogus: true } as never),
    { name: "TypeError", message: "ContactMapper.__init__() got an unexpected keyword argument 'bogus'" },
  );
  assert.throws(
    () => new ContactMapper({ patterns: [] as never }),
    { name: "PatternLoadError", message: "Invalid custom patterns: top level must be an object" },
  );

  const schema = mapper.compile_schema([1, true, null, ["x"]]);
  assert.deepEqual(schema.column_map(), {});
  assert.deepEqual(schema.unmatched_headers(), ["1", "True", "None", "['x']"]);

  const applySchema = mapper.compile_schema(["fname"]);
  assert.throws(
    () => (applySchema.apply as unknown as () => unknown)(),
    { name: "TypeError", message: "MappingSchema.apply() missing 1 required positional argument: 'row'" },
  );
  assert.throws(
    () => (applySchema.apply as unknown as (row: Record<string, unknown>, options: unknown) => unknown)({ fname: "Ada" }, 2),
    { name: "TypeError", message: "MappingSchema.apply() takes 2 positional arguments but 3 were given" },
  );
  assert.throws(
    () => applySchema.apply({ fname: "Ada" }, { bogus: true } as never),
    { name: "TypeError", message: "ContactMapper.map_payload() got an unexpected keyword argument 'bogus'" },
  );
  assert.throws(
    () => (applySchema.apply as unknown as (...args: unknown[]) => unknown)({ fname: "Ada" }, {}, "extra"),
    { name: "TypeError", message: "MappingSchema.apply() takes 2 positional arguments but 4 were given" },
  );
});

test("fuzzy matching follows Python typo recovery guards", () => {
  const mapper = new ContactMapper();

  assert.deepEqual(
    ["phne_nmbr", "Compny", "Job Titel"].map((header) => mapper.identify(header).canonical),
    ["phone", "company", "job_title"],
  );
  assert.deepEqual(
    ["repyto", "reply_to_email", "ownerid"].map((header) => {
      const match = mapper.identify(header);
      return [match.canonical, match.confidence, match.strategy];
    }),
    [
      ["owner", 0.85, "fuzzy"],
      ["unknown", 0, "none"],
      ["owner", 0.7, "fuzzy"],
    ],
  );
  assert.equal(mapper.identify("Job Titel").strategy, "fuzzy");
  assert.equal(mapper.identify("Job Titel").confidence, 0.7);
  assert.equal(mapper.identify("phne_nmbr").confidence, 0.7);
  assert.equal(mapper.identify("Compny").confidence, 0.85);
  assert.equal(mapper.identify("First Nmae").confidence, 0.85);
  assert.deepEqual(
    ["emial", "frist name", "linked in", "source idd", "adress line"].map((header) => {
      const match = mapper.identify(header);
      return [match.canonical, match.confidence, match.strategy];
    }),
    [
      ["email", 0.7, "fuzzy"],
      ["first_name", 0.85, "fuzzy"],
      ["linkedin", 0.85, "fuzzy"],
      ["source_id", 0.85, "fuzzy"],
      ["address_line1", 0.7, "fuzzy"],
    ],
  );
  const placeholder = mapper.identify("field_1");
  assert.equal(placeholder.canonical, "industry");
  assert.equal(placeholder.strategy, "fuzzy");
  assert.equal(mapper.identify("Phoneish").canonical, "phone");
  assert.equal(mapper.identify("Phoneish").confidence, 0.85);
  assert.equal(mapper.identify("Emailish").canonical, "email");
  assert.equal(mapper.identify("Emailish").confidence, 0.85);
  assert.equal(mapper.identify("moblie").canonical, "phone");
  assert.equal(mapper.identify("moblie").confidence, 0.85);
  assert.equal(mapper.identify("addressline").canonical, "address_line1");
  assert.equal(mapper.identify("addressline").confidence, 0.85);
  assert.equal(mapper.identify("Column 1").canonical, "unknown");
  assert.deepEqual(
    [
      "_replyt",
      "tel-nationa",
      "tl-national",
      "streetaddress2",
      "address-level",
      "_rplyto",
      "tel-naitonal",
      "tel-loca",
      "tl-local",
      "street_line",
      "ddress-line3",
      "ddress-level2",
      "ddress-level1",
      "howdidyouhear",
    ].map((header) => {
      const match = mapper.identify(header);
      return [match.canonical, match.confidence, match.strategy];
    }),
    [
      ["owner", 0.85, "fuzzy"],
      ["country", 0.85, "fuzzy"],
      ["country", 0.85, "fuzzy"],
      ["address_line2", 0.85, "fuzzy"],
      ["address_line1", 0.85, "fuzzy"],
      ["email", 0.7, "fuzzy"],
      ["phone", 0.7, "fuzzy"],
      ["phone", 0.7, "fuzzy"],
      ["phone", 0.7, "fuzzy"],
      ["address_line1", 0.85, "fuzzy"],
      ["address_line2", 0.7, "fuzzy"],
      ["city", 0.7, "fuzzy"],
      ["state", 0.7, "fuzzy"],
      ["source", 0.7, "fuzzy"],
    ],
  );
  assert.equal(mapper.identify("tel-olcal").canonical, "unknown");
  assert.deepEqual(
    [mapper.identify("tel-olcal", { value: "202-555-0143" }).canonical, mapper.identify("tel-olcal", { value: "202-555-0143" }).confidence, mapper.identify("tel-olcal", { value: "202-555-0143" }).strategy],
    ["phone", 0.6, "heuristic"],
  );

  const result = mapper.map_payload({ "Column 1": "jane.doe@example.com" });
  assert.equal(result.normalized.email, "jane.doe@example.com");
  assert.equal(result.get_match("Column 1")?.strategy, "heuristic");
});

test("heuristics detect already-normalized E.164 phone values", () => {
  const match = new ContactMapper().identify("Mystery Column", {
    value: "+12025550143",
  });

  assert.equal(match.canonical, "phone");
  assert.equal(match.strategy, "heuristic");
});

test("heuristics avoid ambiguous dates and bare numeric phone IDs", () => {
  const heuristic = new HeuristicMatchStrategy("US");

  assert.equal(heuristic.match("Mystery Column", "1990-05-15"), undefined);
  assert.equal(heuristic.match("raw_numeric_token", "2025550143"), undefined);
  assert.deepEqual(new ContactMapper().map_payload({ "Mystery Phone": 2025550143 }).normalized, {});

  const birthday = heuristic.match("custom_birth_marker", "1990-05-15");
  assert.ok(birthday);
  assert.equal(birthday.canonical, "birthday");
  assert.equal(birthday.strategy, "heuristic");

  const phone = heuristic.match("contact phone", "2025550143");
  assert.ok(phone);
  assert.equal(phone.canonical, "phone");
  assert.equal(phone.strategy, "heuristic");

  assert.equal(heuristic.match("Mystery Column", "202-555-0143")?.canonical, "phone");
});

test("drops low-confidence heuristic matches at threshold", () => {
  const result = new ContactMapper({ confidence_threshold: 0.8 }).map_payload({
    Mystery: "jane@example.com",
  });

  assert.equal(result.normalized.email, undefined);
  assert.equal(result.unmapped.Mystery, "jane@example.com");
  assert.match(result.warnings[0] ?? "", /dropped low-confidence/);

  const phone = new ContactMapper().map_payload(
    { Mystery: "202-555-0143" },
    { confidence_threshold: 0.95 },
  );
  assert.equal(
    phone.warnings[0],
    "'Mystery': dropped low-confidence match to 'phone' (confidence 0.60 < threshold 0.95)",
  );
});

test("header cache can be bounded, cleared, and disabled", () => {
  const mapper = new ContactMapper({ header_cache_max_size: 2 });
  mapper.map_payload({ fname: "A" });
  mapper.map_payload({ surname: "B" });
  mapper.map_payload({ employer: "C" });

  assert.deepEqual(mapper.cache_info(), {
    size: 2,
    max_size: 2,
    cacheable_pipeline: true,
  });

  mapper.clear_cache();
  assert.equal(mapper.cache_info().size, 0);
  assert.throws(
    () => (mapper.cache_info as unknown as (extra: unknown) => unknown)(1),
    { name: "TypeError", message: "ContactMapper.cache_info() takes 1 positional argument but 2 were given" },
  );
  assert.throws(
    () => (mapper.clear_cache as unknown as (extra: unknown) => unknown)(1),
    { name: "TypeError", message: "ContactMapper.clear_cache() takes 1 positional argument but 2 were given" },
  );

  const disabled = new ContactMapper({ header_cache_max_size: 0 });
  disabled.map_payload({ fname: "A" });
  assert.equal(disabled.cache_info().size, 0);

  assert.throws(
    () => new ContactMapper({ header_cache_max_size: -1 }),
    { name: "ValueError", message: "header_cache_max_size must be non-negative or None" },
  );
  assert.throws(
    () => new ContactMapper({ header_cache_max_size: "2" as never }),
    { name: "TypeError", message: "'<' not supported between instances of 'str' and 'int'" },
  );
});

test("public strategy classes and custom strategy pipeline work", () => {
  const registry = new PatternRegistry();

  assert.equal(new ExactMatchStrategy(registry).match("fname")?.canonical, "first_name");
  const normalized = new NormalizedMatchStrategy(registry);
  const fuzzy = new FuzzyMatchStrategy(registry);
  const heuristic = new HeuristicMatchStrategy("US");
  assert.equal(normalized.match("FirstName")?.canonical, "first_name");
  assert.equal(fuzzy.match("Compny")?.canonical, "company");
  assert.equal(heuristic.match("Mystery", "jane@example.com")?.canonical, "email");
  for (const strategy of [normalized, fuzzy, heuristic]) {
    assert.equal("headerOnly" in strategy, false);
    assert.equal("registry" in strategy, false);
    assert.equal("defaultRegion" in strategy, false);
  }

  const AnyExact = ExactMatchStrategy as unknown as new (...args: unknown[]) => ExactMatchStrategy;
  const AnyNormalized = NormalizedMatchStrategy as unknown as new (...args: unknown[]) => NormalizedMatchStrategy;
  const AnyFuzzy = FuzzyMatchStrategy as unknown as new (...args: unknown[]) => FuzzyMatchStrategy;
  const AnyHeuristic = HeuristicMatchStrategy as unknown as new (...args: unknown[]) => HeuristicMatchStrategy;
  assert.throws(() => new AnyExact(), {
    name: "TypeError",
    message: "ExactMatchStrategy.__init__() missing 1 required positional argument: 'registry'",
  });
  assert.throws(() => new AnyExact(registry, "extra"), {
    name: "TypeError",
    message: "ExactMatchStrategy.__init__() takes 2 positional arguments but 3 were given",
  });
  assert.throws(() => new AnyNormalized(), {
    name: "TypeError",
    message: "NormalizedMatchStrategy.__init__() missing 1 required positional argument: 'registry'",
  });
  assert.throws(() => new AnyNormalized(registry, "extra"), {
    name: "TypeError",
    message: "NormalizedMatchStrategy.__init__() takes 2 positional arguments but 3 were given",
  });
  assert.throws(() => new AnyFuzzy(), {
    name: "TypeError",
    message: "FuzzyMatchStrategy.__init__() missing 1 required positional argument: 'registry'",
  });
  assert.throws(() => new AnyFuzzy(registry, "extra"), {
    name: "TypeError",
    message: "FuzzyMatchStrategy.__init__() takes 2 positional arguments but 3 were given",
  });
  assert.throws(() => new AnyHeuristic("US", "extra"), {
    name: "TypeError",
    message: "HeuristicMatchStrategy.__init__() takes from 1 to 2 positional arguments but 3 were given",
  });

  class SourceStrategy extends MatchStrategy {
    get header_only(): boolean {
      return true;
    }

    get name(): string {
      return "custom";
    }

    match(header: string) {
      return header === "special"
        ? {
            original: header,
            canonical: "source",
            confidence: 0.99,
            strategy: this.name,
            service: null,
            is_matched: true,
          }
        : undefined;
    }
  }

  const result = new ContactMapper({ strategies: [new SourceStrategy()] }).map_payload({
    special: "partner",
    fname: "Jane",
  });
  assert.equal(result.normalized.source, "partner");
  assert.equal(result.unmapped.fname, "Jane");
  assert.equal(result.get_match("special")?.strategy, "custom");
});

test("strict mode raises on warnings", () => {
  assert.throws(
    () => new ContactMapper({ strict: true }).map_payload({ phone: "not a phone" }),
    /default_region\?/,
  );
});

test("mapper warnings are observable when Node warning listeners opt in", () => {
  const seen: string[] = [];
  const listener = (warning: Error) => {
    if (warning.name === "RolodexterWarning") {
      seen.push(warning.message);
    }
  };
  process.on("rolodexterWarning" as "warning", listener);
  try {
    new ContactMapper({ confidence_threshold: 0.95 }).map_payload({ Mystery: "202-555-0143" });
    new ContactMapper({ confidence_threshold: 0.99 }).compile_schema(["Compny"]);

    class CollisionFrame {
      [key: string]: unknown;

      columns = ["fname", "first_name"];
      data: Record<string, unknown[]> = { fname: ["Ada"], first_name: ["Lovelace"] };

      rename(args: { columns: Record<string, string> } | Record<string, string>): CollisionFrame {
        const columns = ((args as { columns?: Record<string, string> }).columns ?? args) as Record<string, string>;
        const out = new CollisionFrame();
        out.columns = this.columns.map((column) => columns[column] ?? column);
        out.data = Object.fromEntries(this.columns.map((column) => [columns[column] ?? column, [...(this.data[column] ?? [])]]));
        return out;
      }

      get(column: string): unknown[] {
        return this.data[column] ?? [];
      }

      set(column: string, values: unknown): void {
        this.data[column] = Array.isArray(values) ? values : [values];
      }
    }

    new ContactMapper().map_dataframe(new CollisionFrame());
  } finally {
    process.off("rolodexterWarning" as "warning", listener);
  }

  assert.ok(seen.some((warning) => warning.includes("dropped low-confidence match to 'phone'")));
  assert.ok(seen.some((warning) => warning.includes("dropped low-confidence match to 'company'")));
  assert.ok(seen.some((warning) => warning.includes("map_dataframe: column 'first_name' also maps to 'first_name'")));
});

test("normalizes list fields and dedupes collisions", () => {
  const result = new ContactMapper().map_payload({
    tags: "vip, newsletter",
    labels: '["vip", "beta"]',
  });

  assert.deepEqual(result.normalized.tags, ["vip", "newsletter", "beta"]);
  assert.deepEqual(
    new ContactMapper({ overrides: { tag: "tags" } }).map_payload({ tags: [], tag: ["a", "a"] }).normalized.tags,
    ["a"],
  );
  assert.deepEqual(new ContactMapper({ normalize: false }).map_payload({ phone: true, mobile: 1 }).normalized, {
    phone: true,
  });
  assert.deepEqual(new ContactMapper({ normalize: false }).map_payload({ email: true, "e-mail": 1 }).normalized, {
    email: true,
  });
});

test("extracts embedded phone numbers when opted in", () => {
  const result = new ContactMapper().map_payload(
    { notes: "Call +1-650-253-0000 before lunch" },
    { extract_embedded_phones: true },
  );

  assert.deepEqual(result.get_all_phones(), ["+16502530000"]);
});

test("embedded phone extraction is bounded and warns", () => {
  const manyNumbers = Array.from({ length: 7 }, () => "+1 202 555 1234").join(" ");
  const result = new ContactMapper().map_payload(
    { notes: manyNumbers },
    { extract_embedded_phones: true },
  );

  assert.equal(
    result.field_matches.filter((match) => match.strategy === "embedded_phone").length,
    5,
  );
  assert.match(result.warnings[0] ?? "", /for this field/);
});

test("compile_schema returns a reusable header plan", () => {
  const schema = new ContactMapper().compile_schema(["First Name", "Mobile Phone", "Whatever"]);

  assert.ok(schema instanceof MappingSchema);
  assert.deepEqual(schema.column_map(), {
    "First Name": "first_name",
    "Mobile Phone": "phone",
  });
  assert.deepEqual(schema.unmatched_headers(), ["Whatever"]);
  assert.equal("columnMap" in schema, false);

  const result = schema.apply({ "First Name": "jane", "Mobile Phone": "(202) 555-0143" });
  assert.equal(result.normalized.first_name, "Jane");
  assert.equal(result.normalized.phone, "+12025550143");

  const gbResult = new ContactMapper({ default_region: "US" })
    .compile_schema(["mobile"])
    .apply({ mobile: "020 7946 0958" }, { default_region: "GB" });
  assert.equal(gbResult.normalized.phone, "+442079460958");
});

test("map_batch and map_stream agree", () => {
  const mapper = new ContactMapper();
  const rows = [{ fname: "A" }, { surname: "B" }, { email: "C@Example.COM" }];
  function* generatedRows() {
    yield { fname: "A" };
    yield { surname: "B" };
  }

  assert.deepEqual(
    mapper.map_batch(rows).map((result) => result.normalized),
    [...mapper.map_stream(rows)].map((result) => result.normalized),
  );
  assert.equal("mapPayload" in mapper, false);
  assert.equal("mapBatch" in mapper, false);
  assert.equal("mapStream" in mapper, false);
  assert.deepEqual(mapper.map_batch(generatedRows()).map((result) => result.normalized), [
    { first_name: "A" },
    { last_name: "B" },
  ]);
});

test("profile summarizes mapping readiness without materializing or overconsuming", () => {
  function* rows(): Generator<Record<string, unknown>> {
    yield { fname: "Ada", email: "ADA@EXAMPLE.COM" };
    yield { "First Name": "Grace", Mystery: "???" };
    yield { phone: "not a phone" };
  }
  const iterator = rows();

  const profile = new ContactMapper().profile(iterator, { max_rows: 2 });

  assert.ok(profile instanceof MappingProfile);
  assert.equal(profile.rows_seen, 2);
  assert.equal(profile.fields_seen, 4);
  assert.equal(profile.matched_count, 3);
  assert.equal(profile.unmatched_count, 1);
  assert.equal(profile.match_rate, 0.75);
  assert.deepEqual(profile.canonical_counts, { first_name: 2, email: 1 });
  assert.deepEqual(profile.unmapped_counts, { Mystery: 1 });
  assert.deepEqual(profile.strategy_counts, { exact: 2, normalized: 1, none: 1 });
  assert.deepEqual(iterator.next().value, { phone: "not a phone" });

  const warningProfile = new ContactMapper().profile([{ phone: "not a phone" }]);
  assert.equal(warningProfile.warning_count, 1);
  assert.deepEqual(warningProfile.warning_counts, { phone_normalization: 1 });
  assert.equal(warningProfile.to_dict().match_rate, 1);
  assert.match(warningProfile.explain(), /phone_normalization: 1/);

  assert.throws(
    () => new ContactMapper().profile([], { max_rows: -1 }),
    { name: "ValueError", message: /non-negative/ },
  );
  assert.throws(
    () => new ContactMapper().profile([], { max_rows: 1.5 }),
    { name: "TypeError", message: /integer or None/ },
  );
});

test("mapping results expose email and identity helpers for deduplication", () => {
  const result = new MappingResult(
    {
      email: [" A@EXAMPLE.COM ", "a@example.com"],
      phone: ["+12025550143", "+12025550143"],
      source_service: "HubSpot",
      source_id: [" 42 ", "42"],
    },
    {},
    [],
  );

  assert.deepEqual(result.get_all_emails(), [" A@EXAMPLE.COM ", "a@example.com"]);
  assert.deepEqual(result.get_identity_keys(), [
    "email:a@example.com",
    "phone:+12025550143",
    "source:hubspot:42",
  ]);

  const multipleServices = new MappingResult(
    {
      source_service: ["HubSpot", "Salesforce"],
      source_id: ["42", "99", "orphan"],
    },
    {},
    [],
  );
  assert.deepEqual(multipleServices.get_identity_keys(), [
    "source:hubspot:42",
    "source:salesforce:99",
    "source_id:orphan",
  ]);
});

test("standalone normalize_value covers public normalizers", () => {
  assert.equal(normalize_value("email", " A@EXAMPLE.COM "), "a@example.com");
  assert.equal(normalize_value("email", " A@EXAMPLE.COM "), "a@example.com");
  assert.deepEqual(normalize_value("tags", "a;b"), ["a", "b"]);
  assert.equal(normalize_value("postal_code", "k1a0b1"), "K1A 0B1");
  assert.equal(normalize_value("phone", "(202) 555-0143"), "(202) 555-0143");
  assert.equal(normalize_value("phone", "(202) 555-0143", { default_region: "US" }), "+12025550143");
  assert.equal(normalize_value("phone", "555-1212", { default_region: "US" }), "+15551212");
  assert.throws(
    () => (normalize_value as unknown as () => unknown)(),
    { name: "TypeError", message: "normalize_value() missing 2 required positional arguments: 'canonical_field' and 'value'" },
  );
  assert.throws(
    () => (normalize_value as unknown as (field: string) => unknown)("email"),
    { name: "TypeError", message: "normalize_value() missing 1 required positional argument: 'value'" },
  );
  assert.throws(
    () => (normalize_value as unknown as (field: string, value: unknown, defaultRegion: string) => unknown)("phone", "(202) 555-0143", "US"),
    { name: "TypeError", message: "normalize_value() takes 2 positional arguments but 3 were given" },
  );
  assert.equal(PhoneNormalizer.normalize("(202) 555-0143"), "(202) 555-0143");
  assert.equal(PhoneNormalizer.normalize("2025550143", { default_region: "US" }), "+12025550143");
  assert.throws(
    () => (PhoneNormalizer.normalize as unknown as () => unknown)(),
    { name: "TypeError", message: "PhoneNormalizer.normalize() missing 1 required positional argument: 'value'" },
  );
  assert.throws(
    () => PhoneNormalizer.normalize("2025550143", "US" as never),
    { name: "TypeError", message: "PhoneNormalizer.normalize() takes 2 positional arguments but 3 were given" },
  );
  assert.throws(
    () => (EmailNormalizer.normalize as unknown as (value: unknown, extra: unknown) => unknown)("a@example.com", "extra"),
    { name: "TypeError", message: "EmailNormalizer.normalize() takes 1 positional argument but 2 were given" },
  );
  assert.throws(
    () => (StringNormalizer.normalize as unknown as (value: unknown, extra: unknown) => unknown)("x", "extra"),
    { name: "TypeError", message: "StringNormalizer.normalize() takes 1 positional argument but 2 were given" },
  );
  assert.throws(
    () => (AddressNormalizer.normalize as unknown as (value: unknown, extra: unknown) => unknown)("x", "extra"),
    { name: "TypeError", message: "AddressNormalizer.normalize() takes 1 positional argument but 2 were given" },
  );
  assert.throws(
    () => (PostalCodeNormalizer.normalize as unknown as (value: unknown, extra: unknown) => unknown)("123", "extra"),
    { name: "TypeError", message: "PostalCodeNormalizer.normalize() takes 2 positional arguments but 3 were given" },
  );
  assert.throws(
    () => (BooleanNormalizer.normalize as unknown as (value: unknown, extra: unknown) => unknown)("yes", "extra"),
    { name: "TypeError", message: "BooleanNormalizer.normalize() takes 2 positional arguments but 3 were given" },
  );
  assert.throws(
    () => (ListNormalizer.normalize as unknown as (value: unknown, extra: unknown) => unknown)("a,b", "extra"),
    { name: "TypeError", message: "ListNormalizer.normalize() takes 1 positional argument but 2 were given" },
  );
  assert.throws(
    () => (NameNormalizer.normalize as unknown as (value: unknown, extra: unknown) => unknown)("Ada", "extra"),
    { name: "TypeError", message: "NameNormalizer.normalize() takes 2 positional arguments but 3 were given" },
  );
  assert.throws(
    () => (NameNormalizer.parse as unknown as (value: string, extra: unknown) => unknown)("Ada", "extra"),
    { name: "TypeError", message: "NameNormalizer.parse() takes 2 positional arguments but 3 were given" },
  );
  assert.deepEqual(normalize_value("tags", "[true,false,null,7]"), ["True", "False", "None", "7"]);
  assert.deepEqual(ListNormalizer.normalize([{ a: 1 }, ["x"], true, null]), ["{'a': 1}", "['x']", "True", "None"]);
  assert.deepEqual(normalize_value("tags", '[{"a":1},["x"],true,null]'), ["{'a': 1}", "['x']", "True", "None"]);
});

test("NameNormalizer mirrors Python title, suffix, particle, and hyphen handling", () => {
  assert.equal(NameNormalizer.normalize("jane van der berg"), "Jane van der Berg");
  assert.equal(NameNormalizer.normalize("jean-pierre"), "Jean-Pierre");
  assert.equal(NameNormalizer.normalize("maria del carmen"), "Maria del Carmen");
  assert.equal(NameNormalizer.normalize("Dr. Jane Doe Jr."), "Dr. Jane Doe Jr.");
  assert.equal(NameNormalizer.normalize("john doe jr"), "John Doe Jr");
  assert.equal(NameNormalizer.normalize("john doe sr"), "John Doe Sr");
  assert.equal(NameNormalizer.normalize("dr jane doe"), "Dr Jane Doe");
  assert.equal(NameNormalizer.normalize("mr john q public phd"), "Mr John Q Public Ph.D.");
  assert.equal(NameNormalizer.normalize("john doe ph.d."), "John Doe Ph.d.");
  assert.equal(NameNormalizer.normalize("Dr Jane A. Doe PhD"), "Dr Jane A. Doe Ph.D.");
  assert.equal(NameNormalizer.normalize("Ms Ana Maria del Carmen"), "Ms Ana Maria del Carmen");
  assert.equal(NameNormalizer.normalize('john "jack" smith'), "John Smith (jack)");
  assert.equal(NameNormalizer.normalize('John "Johnny" Doe'), "John Doe (johnny)");
  assert.equal(NameNormalizer.normalize("public, john q"), "John Q Public");
  assert.equal(NameNormalizer.normalize("The Hon. Jane Doe"), "the Hon. Jane Doe");
  assert.equal(NameNormalizer.normalize("mr. and mrs. john smith"), "Mr. and Mrs. John Smith");
  assert.equal(NameNormalizer.normalize("Capt. Jane Smith"), "Capt. Jane Smith");
  assert.equal(NameNormalizer.normalize("Jane Smith MD"), "Jane Smith M.D.");
  assert.equal(NameNormalizer.normalize("Jane Smith V"), "Jane Smith V");
  assert.equal(NameNormalizer.normalize("JOHN MACDONALD"), "John MacDonald");
  assert.equal(NameNormalizer.normalize("smith, john phd"), "John Smith Ph.D.");
  assert.equal(NameNormalizer.normalize("smith, john ph.d."), "John Smith Ph.d.");
  assert.equal(NameNormalizer.normalize("jane doe m.d."), "Jane Doe M.d.");
  assert.equal(NameNormalizer.normalize("the hon jane doe"), "the Hon Jane Doe");
  assert.equal(NameNormalizer.normalize("the honorable jane doe"), "the Honorable Jane Doe");
  assert.equal(NameNormalizer.normalize("King Jr., Martin Luther"), "Martin Luther King Jr.");
  assert.equal(NameNormalizer.normalize("Leonardo da Vinci"), "Leonardo da Vinci");
  assert.equal(NameNormalizer.normalize("Jane Q. Doe, CPA"), "Jane Q. Doe Cpa");
  assert.equal(NameNormalizer.normalize("Doe, Jane Q., CPA"), "Jane Q. Doe Cpa");
  assert.equal(NameNormalizer.normalize("His Excellency John Doe"), "His Excellency John Doe");
  assert.equal(NameNormalizer.normalize("Dame Judi Dench"), "Dame Judi Dench");
  assert.equal(NameNormalizer.normalize("Mx Alex Doe"), "Mx Alex Doe");
  assert.equal(NameNormalizer.normalize("St. John-Smith"), "St. John-Smith");

  assert.deepEqual(NameNormalizer.parse("Dr. Jane Doe Jr."), {
    title: "Dr.",
    first: "Jane",
    middle: "",
    last: "Doe",
    suffix: "Jr.",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("John Fitzgerald Kennedy"), {
    title: "",
    first: "John",
    middle: "Fitzgerald",
    last: "Kennedy",
    suffix: "",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse('John "Johnny" Doe'), {
    title: "",
    first: "John",
    middle: "",
    last: "Doe",
    suffix: "",
    nickname: "Johnny",
  });
  assert.deepEqual(NameNormalizer.parse("mr john q public phd"), {
    title: "mr",
    first: "john",
    middle: "q",
    last: "public",
    suffix: "phd",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("sir isaac newton"), {
    title: "sir",
    first: "isaac",
    middle: "",
    last: "newton",
    suffix: "",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("rev dr martin luther king jr"), {
    title: "rev dr",
    first: "martin",
    middle: "luther",
    last: "king",
    suffix: "jr",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("public, john q"), {
    title: "",
    first: "john",
    middle: "q",
    last: "public",
    suffix: "",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("The Hon. Jane Doe"), {
    title: "The Hon.",
    first: "Jane",
    middle: "",
    last: "Doe",
    suffix: "",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("mr. and mrs. john smith"), {
    title: "mr. and mrs.",
    first: "john",
    middle: "",
    last: "smith",
    suffix: "",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("Capt. Jane Smith"), {
    title: "Capt.",
    first: "Jane",
    middle: "",
    last: "Smith",
    suffix: "",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("Jane Smith MD"), {
    title: "",
    first: "Jane",
    middle: "",
    last: "Smith",
    suffix: "MD",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("Jane Smith V"), {
    title: "",
    first: "Jane",
    middle: "",
    last: "Smith",
    suffix: "V",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("ST. JOHN SMITH"), {
    title: "ST.",
    first: "JOHN",
    middle: "",
    last: "SMITH",
    suffix: "",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("the honorable jane doe"), {
    title: "the honorable",
    first: "jane",
    middle: "",
    last: "doe",
    suffix: "",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("King Jr., Martin Luther"), {
    title: "",
    first: "Martin",
    middle: "Luther",
    last: "King",
    suffix: "Jr.",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("Doe, Jane Q., CPA"), {
    title: "",
    first: "Jane",
    middle: "Q.",
    last: "Doe",
    suffix: "CPA",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("His Excellency John Doe"), {
    title: "His Excellency",
    first: "John",
    middle: "",
    last: "Doe",
    suffix: "",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("St. John-Smith"), {
    title: "St.",
    first: "",
    middle: "",
    last: "John-Smith",
    suffix: "",
    nickname: "",
  });
});

test("address casing keeps Python hyphen behavior separate from names", () => {
  assert.equal(AddressNormalizer.normalize("winston-salem"), "Winston-salem");
  assert.equal(AddressNormalizer.normalize("machine shop rd"), "Machine Shop Rd");
  assert.equal(NameNormalizer.normalize("jean-pierre"), "Jean-Pierre");
  assert.equal(NameNormalizer.normalize("Ada,a@example.com"), "A@Example.com Ada");
});

test("Python-shaped mapping result surface is available", () => {
  const result = new ContactMapper().map_payload({ fname: "jane", Whatever: "x" });

  assert.equal(result.matched_count, 1);
  assert.equal(result.unmatched_count, 1);
  assert.equal(result.match_rate, 0.5);
  assert.equal(result.field_matches.length, 2);
  assert.equal(result.get_match("fname")?.is_matched, true);
  assert.equal(result.get_match("missing"), null);
  assert.deepEqual(result.to_dict().normalized, { first_name: "Jane" });
  assert.equal("getMatch" in result, false);
  assert.equal("getAllPhones" in result, false);
  assert.equal("toJSON" in result, false);

  const schema = new ContactMapper().compile_schema(["fname"]);
  assert.deepEqual(schema.column_map(), { fname: "first_name" });
  assert.deepEqual(Object.keys(schema.matches), ["fname"]);
  assert.equal(schema.matches.fname.canonical, "first_name");
  assert.equal(schema.matches.get("fname")?.canonical, "first_name");
  assert.equal(schema.matches.get("missing"), null);
  const gbSchema = new ContactMapper().compile_schema(["Mobile Phone"], { default_region: "GB" });
  assert.equal(gbSchema.default_region, "GB");
  assert.equal("defaultRegion" in gbSchema, false);

  const positional = new MappingResult({}, {}, [new FieldMatch("x", "unknown", 0, "none")]);
  assert.equal(positional.unmatched_count, 1);
  assert.throws(
    () => (positional.field_matches as FieldMatch[]).push(new FieldMatch("y", "unknown", 0, "none")),
    TypeError,
  );

  const match = new FieldMatch("x", "unknown", 0, "none");
  assert.equal(Object.isExtensible(match), false);
  assert.throws(() => {
    (match as unknown as Record<string, unknown>).extra = 1;
  }, TypeError);
  const details = new MappingResult({}, {}, [match]).to_dict().details as Array<Record<string, unknown>>;
  assert.deepEqual(details[0], {
    original: "x",
    canonical: "unknown",
    confidence: 0,
    strategy: "none",
    service: null,
  });
  assert.match(String(match), /^FieldMatch\(/);
  assert.match(String(new MappingResult({}, {}, [match])), /^MappingResult\(/);
});

test("public model constructors reject JS-only object-shaped calls", () => {
  const FieldMatchObjectCtor = FieldMatch as unknown as new (arg: unknown) => FieldMatch;
  assert.throws(
    () => new FieldMatchObjectCtor({ original: "x", canonical: "unknown", confidence: 0, strategy: "none" }),
    {
      name: "TypeError",
      message: "FieldMatch.__init__() missing 3 required positional arguments: 'canonical', 'confidence', and 'strategy'",
    },
  );

  const MappingResultObjectCtor = MappingResult as unknown as new (arg: unknown) => MappingResult;
  assert.throws(
    () => new MappingResultObjectCtor({ normalized: {}, unmapped: {}, field_matches: [] }),
    {
      name: "TypeError",
      message: "MappingResult.__init__() missing 2 required positional arguments: 'unmapped' and 'field_matches'",
    },
  );

  const MappingSchemaObjectCtor = MappingSchema as unknown as new (arg: unknown) => MappingSchema;
  assert.throws(
    () => new MappingSchemaObjectCtor({ matches: {}, mapper: new ContactMapper() }),
    {
      name: "TypeError",
      message: "MappingSchema.__init__() missing 1 required positional argument: 'mapper'",
    },
  );

  const PhoneNumberObjectCtor = PhoneNumber as unknown as new (arg: unknown) => PhoneNumber;
  assert.throws(
    () => new PhoneNumberObjectCtor({ calling_code: 1, national_number: "2025550143", raw: "x" }),
    {
      name: "TypeError",
      message: "PhoneNumber.__init__() missing 2 required positional arguments: 'national_number' and 'raw'",
    },
  );

  const AnyFieldMatch = FieldMatch as unknown as new (...args: unknown[]) => FieldMatch;
  assert.throws(() => new AnyFieldMatch(), {
    name: "TypeError",
    message: "FieldMatch.__init__() missing 4 required positional arguments: 'original', 'canonical', 'confidence', and 'strategy'",
  });
  assert.throws(() => new AnyFieldMatch("x", "unknown", 0, "none", null, "extra"), {
    name: "TypeError",
    message: "FieldMatch.__init__() takes from 5 to 6 positional arguments but 7 were given",
  });

  const AnyMappingResult = MappingResult as unknown as new (...args: unknown[]) => MappingResult;
  assert.throws(() => new AnyMappingResult(), {
    name: "TypeError",
    message: "MappingResult.__init__() missing 3 required positional arguments: 'normalized', 'unmapped', and 'field_matches'",
  });
  assert.throws(() => new AnyMappingResult({}, {}), {
    name: "TypeError",
    message: "MappingResult.__init__() missing 1 required positional argument: 'field_matches'",
  });
  assert.throws(() => new AnyMappingResult({}, {}, [], [], "extra"), {
    name: "TypeError",
    message: "MappingResult.__init__() takes from 4 to 5 positional arguments but 6 were given",
  });

  const AnyMappingSchema = MappingSchema as unknown as new (...args: unknown[]) => MappingSchema;
  assert.throws(() => new AnyMappingSchema(), {
    name: "TypeError",
    message: "MappingSchema.__init__() missing 2 required positional arguments: 'matches' and 'mapper'",
  });
  assert.throws(() => new AnyMappingSchema({}, new ContactMapper(), null, "extra"), {
    name: "TypeError",
    message: "MappingSchema.__init__() takes from 3 to 4 positional arguments but 5 were given",
  });

  const AnyPhoneNumber = PhoneNumber as unknown as new (...args: unknown[]) => PhoneNumber;
  assert.throws(() => new AnyPhoneNumber(), {
    name: "TypeError",
    message: "PhoneNumber.__init__() missing 3 required positional arguments: 'calling_code', 'national_number', and 'raw'",
  });
  assert.throws(() => new AnyPhoneNumber(1, "202"), {
    name: "TypeError",
    message: "PhoneNumber.__init__() missing 1 required positional argument: 'raw'",
  });
  assert.throws(() => new AnyPhoneNumber(1, "202", "raw", null, null, "extra"), {
    name: "TypeError",
    message: "PhoneNumber.__init__() takes from 4 to 6 positional arguments but 7 were given",
  });

  const AnyPhoneNumberMatch = PhoneNumberMatch as unknown as new (...args: unknown[]) => PhoneNumberMatch;
  assert.throws(() => new AnyPhoneNumberMatch(), {
    name: "TypeError",
    message: "PhoneNumberMatch.__init__() missing 4 required positional arguments: 'start', 'end', 'raw_string', and 'number'",
  });
  assert.throws(() => new AnyPhoneNumberMatch(1), {
    name: "TypeError",
    message: "PhoneNumberMatch.__init__() missing 3 required positional arguments: 'end', 'raw_string', and 'number'",
  });
  assert.throws(() => new AnyPhoneNumberMatch(1, 2, "raw", new PhoneNumber(1, "202", "raw"), "extra"), {
    name: "TypeError",
    message: "PhoneNumberMatch.__init__() takes 5 positional arguments but 6 were given",
  });
});

test("Python dataclass-like models reject public field reassignment", () => {
  const match = new FieldMatch("x", "unknown", 0, "none");
  assert.throws(() => {
    (match as unknown as Record<string, unknown>).original = "changed";
  }, { name: "FrozenInstanceError", message: "cannot assign to field 'original'" });

  const result = new MappingResult({ first_name: "Ada" }, {}, [match]);
  assert.throws(() => {
    (result as unknown as Record<string, unknown>).normalized = {};
  }, { name: "FrozenInstanceError", message: "cannot assign to field 'normalized'" });
  result.normalized.extra = "allowed like Python's mutable dict payloads";
  assert.equal(result.normalized.extra, "allowed like Python's mutable dict payloads");

  const schema = new ContactMapper().compile_schema(["fname"]);
  assert.throws(() => {
    (schema as unknown as Record<string, unknown>).matches = {};
  }, { name: "FrozenInstanceError", message: "cannot assign to field 'matches'" });
  schema.matches.set("extra", match);
  assert.equal(schema.matches.get("extra"), match);

  const phone = parse("+1 650 253 0000")!;
  assert.throws(() => {
    (phone as unknown as Record<string, unknown>).calling_code = 44;
  }, { name: "FrozenInstanceError", message: "cannot assign to field 'calling_code'" });
});

test("JS-only mapper aliases are not public", () => {
  const mapper = new ContactMapper();

  assert.deepEqual(mapper.map_payload({ Email: "ADA@EXAMPLE.COM" }).normalized, {
    email: "ada@example.com",
  });
  assert.equal("mapContact" in mapper, false);
  assert.equal("map_contact" in mapper, false);
  assert.equal("compileSchema" in mapper, false);
  assert.equal("mapDataFrame" in mapper, false);
  assert.equal("clearCache" in mapper, false);
  assert.equal("cacheInfo" in mapper, false);
  for (const name of ["normalize", "defaultRegion", "strict", "confidenceThreshold", "headerCacheMaxSize", "strategies", "headerCache", "resolve"]) {
    assert.equal(name in mapper, false, `${name} should stay private`);
  }
  assert.equal("registry" in mapper, true);
});

test("Python-shaped mapper option names are accepted", () => {
  const mapper = new ContactMapper({
    default_region: "GB",
    confidence_threshold: 0.8,
    header_cache_max_size: 1,
    default_service: "ignored",
  });

  assert.equal(mapper.map_payload({ phone: "020 7946 0958" }).normalized.phone, "+442079460958");
  assert.equal(mapper.cache_info().max_size, 1);

  const embedded = new ContactMapper().map_payload(
    { notes: "Call +1 650 253 0000" },
    { extract_embedded_phones: true },
  );
  assert.deepEqual(embedded.get_all_phones(), ["+16502530000"]);

  const schema = new ContactMapper().compile_schema(["Compny"], { confidence_threshold: 0.99 });
  assert.deepEqual(schema.column_map(), {});
  assert.throws(
    () => mapper.map_payload({ fname: " jane " }, { normalize: false } as never),
    { name: "TypeError", message: "ContactMapper.map_payload() got an unexpected keyword argument 'normalize'" },
  );
  assert.throws(
    () => new ContactMapper({ confidence_threshold: 2 }),
    { name: "ValueError", message: "confidence_threshold must be between 0.0 and 1.0" },
  );
});

test("public phone helpers mirror Python phone module basics", () => {
  const phone = parse("+1 650 253 0000");
  assert.ok(phone);

  assert.equal(phone.calling_code, 1);
  assert.equal(phone.national_number, "6502530000");
  assert.equal(phone.e164, "+16502530000");
  assert.equal(phone.is_valid, true);
  assert.equal(phone.is_possible, true);
  assert.equal(phone.toString(), "+16502530000");
  assert.equal(phone.country_codes[0], "US");
  assert.ok(phone.country_codes.includes("CA"));
  assert.equal("_phoneNumber" in phone, false);
  assert.equal("callingCode" in phone, false);
  assert.equal("nationalNumber" in phone, false);

  assert.equal(format_international(phone), "+1 650-253-0000");
  assert.equal(format_national(phone), "(650) 253-0000");
  assert.equal(number_type(phone), NumberType.FIXED_LINE_OR_MOBILE);
  assert.equal(is_valid("+1 650 253 0000"), true);
  assert.equal(is_number_match("+1 650 253 0000", "6502530000", "US"), MatchType.EXACT_MATCH);

  const tel = parse("tel:+1-650-253-0000;ext=123");
  assert.equal(tel?.extension, "123");
  assert.equal(format_e164("tel:+1-650-253-0000;ext=123"), "+16502530000");
  assert.equal(format_e164("011 44 20 7946 0958"), "+442079460958");
  assert.equal(format_e164("+1-800-FLOWERS"), "+18003569377");
  assert.equal(format_e164("not a phone", "GB"), null);
  assert.equal(parse("not a phone"), null);
  assert.equal(parse("not a phone", "GB"), null);
  for (const value of [null, 123, true, {}, []]) {
    assert.equal(parse(value as never, "US"), null);
    assert.equal(format_e164(value as never, "US"), null);
    assert.equal(is_valid(value as never, "US"), false);
  }
});

test("phone helpers mirror Python extension and match semantics", () => {
  const local = parse("555-1212", "US")!;
  assert.equal(local.e164, "+15551212");
  assert.equal(local.is_possible, true);
  assert.equal(local.is_valid, false);
  assert.equal(format_national(local), "555-1212");
  assert.equal(parse("+1 555 123 4567 ext 890")?.extension, "890");
  assert.equal(parse("+1 555 123 4567 ext. 42")?.extension, "42");
  assert.equal(parse("+44 20 7946 0958 extn 100")?.extension, "100");
  assert.equal(parse("+1 555 123 4567 extension 999")?.extension, "999");
  assert.equal(parse("+1 555 123 4567 x 55")?.extension, "55");
  assert.equal(parse("202-555-1234x9", "US")?.extension, "9");
  assert.equal(format_e164("202-555-1234 x9", "US"), "+12025551234");
  assert.equal(parse("+1 555 123 4567 # 77")?.extension, "77");
  assert.equal(parse("+1 555 123 4567;ext=200")?.extension, "200");

  assert.equal(is_number_match("+15551234567 ext 42", "+1 555 123 4567 ext 42"), MatchType.EXACT_MATCH);
  assert.equal(is_number_match("+1 202 555 1234 ext 9", "202-555-1234 x9", "US"), MatchType.EXACT_MATCH);
  assert.equal(is_number_match("+12025551234 ext 42", "+12025551234"), MatchType.SHORT_NSN_MATCH);
  assert.equal(is_number_match("+12025551234 ext 42", "+12025551234 ext 43"), MatchType.NO_MATCH);
  assert.equal(is_number_match("2025551234", "5551234", "US"), MatchType.SHORT_NSN_MATCH);
  assert.equal(is_number_match("+1 202-555-0123", "+44 20 2555 0123", "US"), MatchType.NO_MATCH);
  assert.equal(is_number_match("hello", "+15551234567"), MatchType.NOT_A_NUMBER);
});

test("phone number_type mirrors Python libphonenumber metadata", () => {
  assert.equal(number_type(parse("+18005551212")!), NumberType.TOLL_FREE);
  assert.equal(number_type(parse("+19002001234")!), NumberType.PREMIUM_RATE);
  assert.equal(number_type(parse("+12025551234")!), NumberType.FIXED_LINE_OR_MOBILE);
  assert.equal(number_type(parse("+447911123456")!), NumberType.MOBILE);
  assert.equal(number_type(parse("+442079460958")!), NumberType.FIXED_LINE);
  assert.equal(number_type(parse("+33612345678")!), NumberType.MOBILE);
  assert.equal(number_type(parse("+919876543210")!), NumberType.MOBILE);
  assert.equal(number_type(parse("+8613800138000")!), NumberType.MOBILE);
  assert.equal(number_type(parse("+4915112345678")!), NumberType.MOBILE);
  assert.equal(number_type(parse("+29012345")!), NumberType.UNKNOWN);
});

test("PhoneNumber fallback construction mirrors Python defensive paths", () => {
  const phone = new PhoneNumber(44, "2079460958", "x");
  const positional = new PhoneNumber(44, "2079460958", "x");
  const manualNanp = new PhoneNumber(1, "2025550143", "raw", "99");
  const manualLocal = new PhoneNumber(1, "5551212", "raw");

  assert.equal(phone.e164, "+442079460958");
  assert.equal(positional.e164, "+442079460958");
  assert.equal(phone.is_valid, false);
  assert.equal(phone.is_possible, false);
  assert.equal(format_international(phone), "+44 2079460958");
  assert.equal(format_national(phone), "2079460958");
  assert.equal(format_international(manualNanp), "+1 2025550143");
  assert.equal(format_national(manualNanp), "2025550143");
  assert.equal(format_national(manualLocal), "5551212");
  assert.equal(number_type(phone), NumberType.UNKNOWN);
  assert.equal(is_number_match(new PhoneNumber(1, "2025551234", "x"), "+12025551234"), MatchType.EXACT_MATCH);
  assert.equal(is_number_match(null as unknown as string, null as unknown as string), MatchType.NOT_A_NUMBER);
  assert.throws(() => (parse as unknown as () => unknown)(), {
    name: "TypeError",
    message: "parse() missing 1 required positional argument: 'raw'",
  });
  assert.throws(() => (parse as unknown as (raw: string, region: string, extra: string) => unknown)("x", "US", "extra"), {
    name: "TypeError",
    message: "parse() takes from 1 to 2 positional arguments but 3 were given",
  });
  assert.throws(() => (format_e164 as unknown as () => unknown)(), {
    name: "TypeError",
    message: "format_e164() missing 1 required positional argument: 'raw'",
  });
  assert.throws(() => (is_valid as unknown as (raw: string, region: string, extra: string) => unknown)("x", "US", "extra"), {
    name: "TypeError",
    message: "is_valid() takes from 1 to 2 positional arguments but 3 were given",
  });
  assert.throws(() => (is_number_match as unknown as () => unknown)(), {
    name: "TypeError",
    message: "is_number_match() missing 2 required positional arguments: 'a' and 'b'",
  });
  assert.throws(() => (is_number_match as unknown as (a: string) => unknown)("x"), {
    name: "TypeError",
    message: "is_number_match() missing 1 required positional argument: 'b'",
  });
  assert.throws(() => (is_number_match as unknown as (a: string, b: string, region: string, extra: string) => unknown)("x", "y", "US", "extra"), {
    name: "TypeError",
    message: "is_number_match() takes from 2 to 3 positional arguments but 4 were given",
  });
  assert.throws(() => format_international({} as never), {
    name: "AttributeError",
    message: "'dict' object has no attribute '_pn_obj'",
  });
  assert.throws(() => format_national("x" as never), {
    name: "AttributeError",
    message: "'str' object has no attribute '_pn_obj'",
  });
  assert.throws(() => number_type(null as never), {
    name: "AttributeError",
    message: "'NoneType' object has no attribute '_pn_obj'",
  });
});

test("PhoneNumberMatcher extracts bounded free-text matches", () => {
  const matcher = new PhoneNumberMatcher(
    "Call +1 650 253 0000 or +44 20 7946 0958",
    "US",
    { max_matches: 1 },
  );
  const matches = [...matcher];

  assert.equal(matcher.length, 1);
  assert.equal(matcher.has_next(), true);
  for (const name of ["text", "defaultRegion", "maxMatches", "matches", "findAll", "allMatches", "hasNext"]) {
    assert.equal(name in matcher, false, `${name} should stay private`);
  }
  assert.equal(matches[0]?.raw_string, "+1 650 253 0000");
  assert.equal(matches[0]?.number.e164, "+16502530000");

  const match = new PhoneNumberMatch(1, 4, "raw", new PhoneNumber(1, "2025550143", "raw"));
  assert.equal(String(match), "PhoneNumberMatch(start=1, end=4, number=+12025550143)");
  assert.equal(new PhoneNumberMatcher(null as never, "US").length, 0);
  assert.deepEqual([...new PhoneNumberMatcher(null as never, "US")], []);
  assert.throws(
    () => new PhoneNumberMatcher("a +1 202 555 0143", "US", { max_matches: "1" as never }),
    { name: "TypeError", message: "'>' not supported between instances of 'str' and 'int'" },
  );
});

test("map_dataframe rejects row arrays like Python pandas entry point", () => {
  const rows = [
    {
      fname: "jane",
      mobile: "(202) 555-0143",
      phone: "+1 202 555 0143",
      Whatever: "kept",
    },
  ];

  assert.throws(
    () => new ContactMapper().map_dataframe(rows as never),
    { name: "AttributeError", message: "'list' object has no attribute 'columns'" },
  );
  assert.deepEqual(rows[0], {
    fname: "jane",
    mobile: "(202) 555-0143",
    phone: "+1 202 555 0143",
    Whatever: "kept",
  });
});

test("map_dataframe accepts DataFrame-like adapters with columns and rename", () => {
  class FakeFrame {
    [key: string]: unknown;

    columns: string[];
    data: Record<string, unknown[]>;

    constructor(data: Record<string, unknown[]>) {
      this.columns = Object.keys(data);
      this.data = Object.fromEntries(Object.entries(data).map(([key, values]) => [key, [...values]]));
    }

    rename(args: { columns: Record<string, string> } | Record<string, string>): FakeFrame {
      const columns = ((args as { columns?: Record<string, string> }).columns ?? args) as Record<string, string>;
      const renamed: Record<string, unknown[]> = {};
      for (const column of this.columns) {
        renamed[columns[column] ?? column] = [...(this.data[column] ?? [])];
      }
      return new FakeFrame(renamed);
    }

    get(column: string): unknown[] {
      return this.data[column] ?? [];
    }

    set(column: string, values: unknown): void {
      this.data[column] = Array.isArray(values) ? values : [values];
    }
  }

  const frame = new FakeFrame({
    fname: ["jane"],
    mobile: ["(202) 555-0143"],
    Whatever: ["kept"],
  });

  const mapped = new ContactMapper().map_dataframe(frame) as FakeFrame;

  assert.deepEqual(mapped.columns, ["first_name", "phone", "Whatever"]);
  assert.deepEqual(mapped.data, {
    first_name: ["Jane"],
    phone: ["+12025550143"],
    Whatever: ["kept"],
  });
  assert.deepEqual(frame.columns, ["fname", "mobile", "Whatever"]);
});

test("map_dataframe preserves unmatched suffix columns and rejects duplicate labels", () => {
  class FakeFrame {
    [key: string]: unknown;

    constructor(
      public columns: string[],
      public data: Record<string, unknown[]>,
    ) {}

    rename(args: { columns: Record<string, string> } | Record<string, string>): FakeFrame {
      const names = ((args as { columns?: Record<string, string> }).columns ?? args) as Record<string, string>;
      return new FakeFrame(
        this.columns.map((column) => names[column] ?? column),
        Object.fromEntries(
          this.columns.map((column) => [names[column] ?? column, [...(this.data[column] ?? [])]]),
        ),
      );
    }

    get(column: string): unknown[] {
      return this.data[column] ?? [];
    }

    set(column: string, values: unknown): void {
      this.data[column] = Array.isArray(values) ? values : [values];
    }
  }

  const mapper = new ContactMapper({
    patterns: { fields: { custom: ["source_a", "source_b"] } },
  });
  const mapped = mapper.map_dataframe(
    new FakeFrame(
      ["source_a", "source_b", "custom__2"],
      { source_a: ["one"], source_b: ["two"], custom__2: ["keep"] },
    ),
    { normalize: false },
  ) as FakeFrame;

  assert.deepEqual(mapped.columns, ["custom", "custom__3", "custom__2"]);
  assert.deepEqual(mapped.data, {
    custom: ["one"],
    custom__3: ["two"],
    custom__2: ["keep"],
  });
  assert.throws(
    () => new ContactMapper().map_dataframe(
      new FakeFrame(["fname", "fname"], { fname: ["Ada"] }),
    ),
    { name: "ValueError", message: /unique input column labels/ },
  );
});

test("map_dataframe honors normalize, strict, and threshold options", () => {
  const mapper = new ContactMapper();
  class TinyFrame {
    [key: string]: unknown;

    columns: string[];
    data: Record<string, unknown[]>;

    constructor(data: Record<string, unknown[]>) {
      this.columns = Object.keys(data);
      this.data = Object.fromEntries(Object.entries(data).map(([key, values]) => [key, [...values]]));
    }

    rename(args: { columns: Record<string, string> } | Record<string, string>): TinyFrame {
      const columns = ((args as { columns?: Record<string, string> }).columns ?? args) as Record<string, string>;
      return new TinyFrame(Object.fromEntries(this.columns.map((column) => [columns[column] ?? column, [...(this.data[column] ?? [])]])));
    }

    get(column: string): unknown[] {
      return this.data[column] ?? [];
    }

    set(column: string, values: unknown): void {
      this.data[column] = Array.isArray(values) ? values : [values];
    }
  }

  assert.deepEqual((mapper.map_dataframe(new TinyFrame({ fname: ["jane"] }), { normalize: false }) as TinyFrame).data, {
    first_name: ["jane"],
  });
  assert.deepEqual((mapper.map_dataframe(new TinyFrame({ Compny: ["Acme"] }), { confidence_threshold: 0.99 }) as TinyFrame).data, {
    Compny: ["Acme"],
  });
  assert.throws(
    () => mapper.map_dataframe(new TinyFrame({ phone: ["not a phone"] }), { strict: true }),
    /default_region\?/,
  );
});

test("get_all_phones mirrors Python MappingResult helper", () => {
  const result = new ContactMapper().map_payload({
    phone: "(202) 555-0143",
    whatsapp: "+1 202 555 0143",
  });

  assert.deepEqual(result.get_all_phones(), ["+12025550143"]);
  assert.deepEqual(new ContactMapper({ normalize: false }).map_payload({ phone: [null, true, 123] }).get_all_phones(), ["None", "True", "123"]);
});

test("CLI fields and explain commands work", () => {
  const mapHelp = runCli(["map", "--help"]);
  assert.equal(mapHelp.status, 0, mapHelp.stderr);
  assert.match(mapHelp.stdout, /usage: rolodexter map/);
  assert.match(mapHelp.stdout, /--on-error \{fail,skip,quarantine\}/);

  const explainHelp = runCli(["explain", "--help"]);
  assert.equal(explainHelp.status, 0, explainHelp.stderr);
  assert.match(explainHelp.stdout, /usage: rolodexter explain/);

  const fieldsHelp = runCli(["fields", "--help"]);
  assert.equal(fieldsHelp.status, 0, fieldsHelp.stderr);
  assert.match(fieldsHelp.stdout, /usage: rolodexter fields/);

  const fields = runCli(["fields"]);
  assert.equal(fields.status, 0, fields.stderr);
  assert.match(fields.stdout, /first_name/);
  assert.match(fields.stdout, /phone/);

  const explain = runCli(["explain", "Job Titel", "--value", "CEO"]);
  assert.equal(explain.status, 0, explain.stderr);
  assert.match(explain.stdout, /job_title/);
  assert.match(explain.stdout, /fuzzy/);
});

test("CLI usage errors mirror Python argparse exits", () => {
  const root = runCli([]);
  assert.equal(root.status, 2);
  assert.equal(root.stdout, "");
  assert.equal(
    root.stderr,
    `usage: rolodexter [-h] {map,explain,fields} ...${CLI_EOL}rolodexter: error: the following arguments are required: command${CLI_EOL}`,
  );

  const map = runCli(["map"]);
  assert.equal(map.status, 2);
  assert.equal(map.stdout, "");
  assert.match(map.stderr, /^usage: rolodexter map/);
  assert.match(map.stderr, /rolodexter map: error: the following arguments are required: input/);

  const dir = mkdtempSync(join(tmpdir(), "rolodexter-js-cli-"));
  try {
    const input = join(dir, "contacts.json");
    writeFileSync(input, "[]", "utf8");

    const abbreviated = runCli(["map", input, "--format", "json", "--min-conf", "0.5"]);
    assert.equal(abbreviated.status, 0, abbreviated.stderr);
    assert.equal(abbreviated.stdout, `[]${CLI_EOL}`);

    const signedLimit = runCli(["map", input, "--format", "json", "--max-materialized-rows", "+1", "--min-confidence", "+.5"]);
    assert.equal(signedLimit.status, 0, signedLimit.stderr);
    assert.equal(signedLimit.stdout, `[]${CLI_EOL}`);

    const negativeDotConfidence = runCli(["map", input, "--format", "json", "--min-confidence", "-.5"]);
    assert.equal(negativeDotConfidence.status, 1);
    assert.match(negativeDotConfidence.stderr, /confidence_threshold must be between 0\.0 and 1\.0/);

    const separator = runCli(["map", "--", input]);
    assert.equal(separator.status, 0, separator.stderr);
    assert.equal(separator.stdout, `[]${CLI_EOL}`);

    const badConfidence = runCli(["map", input, "--format", "json", "--min-confidence", "0.5abc"]);
    assert.equal(badConfidence.status, 2);
    assert.match(badConfidence.stderr, /argument --min-confidence: invalid float value/);

    const badRows = runCli(["map", input, "--format", "json", "--max-materialized-rows", "1.5"]);
    assert.equal(badRows.status, 2);
    assert.match(badRows.stderr, /argument --max-materialized-rows: invalid _non_negative_int value/);

    const negativeRows = runCli(["map", input, "--format", "json", "--max-materialized-rows", "-1"]);
    assert.equal(negativeRows.status, 2);
    assert.match(negativeRows.stderr, /argument --max-materialized-rows: must be non-negative/);

    const badFormat = runCli(["map", input, "--format", "xml"]);
    assert.equal(badFormat.status, 2);
    assert.match(badFormat.stderr, /argument --format: invalid choice/);

    const missingRegion = runCli(["map", input, "--region", "--strict", "--format", "json"]);
    assert.equal(missingRegion.status, 2);
    assert.match(missingRegion.stderr, /argument --region: expected one argument/);

    const missingFormatBeforeHelp = runCli(["map", input, "--format", "--help"]);
    assert.equal(missingFormatBeforeHelp.status, 2);
    assert.equal(missingFormatBeforeHelp.stdout, "");
    assert.match(missingFormatBeforeHelp.stderr, /argument --format: expected one argument/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("CLI maps CSV to JSONL", () => {
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-js-cli-"));
  try {
    const input = join(dir, "contacts.csv");
    writeFileSync(input, "fname,email,mobile\nJane,JANE@EXAMPLE.COM,(202) 555-0143\n", "utf8");

    const result = runCli(["map", input, "--format", "jsonl"]);
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stderr, /Mapped 1 row/);
    assert.equal(
      result.stdout,
      `{"first_name": "Jane", "email": "jane@example.com", "phone": "+12025550143"}${CLI_EOL}`,
    );
    assert.deepEqual(JSON.parse(result.stdout.trim()), {
      first_name: "Jane",
      email: "jane@example.com",
      phone: "+12025550143",
    });
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("CLI CSV parsing follows Python DictReader edge behavior", () => {
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-js-cli-"));
  try {
    const extra = join(dir, "extra.csv");
    writeFileSync(extra, "Name,Email\nAda,a@example.com,EXTRA\n", "utf8");
    const extraResult = runCli(["map", extra, "--format", "json"]);
    assert.equal(extraResult.status, 0, extraResult.stderr);
    assert.deepEqual(JSON.parse(extraResult.stdout), [
      { full_name: "Ada", email: "a@example.com" },
    ]);

    const badQuote = join(dir, "badquote.csv");
    writeFileSync(badQuote, 'Name,Email\n"Ada,a@example.com\n', "utf8");
    const badQuoteResult = runCli(["map", badQuote, "--format", "json"]);
    assert.equal(badQuoteResult.status, 0, badQuoteResult.stderr);
    assert.deepEqual(JSON.parse(badQuoteResult.stdout), [
      { full_name: "A@Example.com Ada", email: null },
    ]);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("CLI JSONL output ignores materialization row limit", () => {
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-js-cli-"));
  try {
    const input = join(dir, "contacts.jsonl");
    writeFileSync(input, '{"fname":"A"}\n{"surname":"B"}', "utf8");

    const result = runCli(["map", input, "--format", "jsonl", "--max-materialized-rows", "1"]);
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.stdout, `{"first_name": "A"}${CLI_EOL}{"last_name": "B"}${CLI_EOL}`);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("CLI materialization limit is raised before later row failures", () => {
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-js-cli-"));
  try {
    const input = join(dir, "limit.jsonl");
    writeFileSync(input, '{"Name":"Ada"}\n{"Name":"Grace"}\nnot-json\n', "utf8");

    const result = runCli(["map", input, "--format", "json", "--max-materialized-rows", "1"]);
    assert.equal(result.status, 1);
    assert.match(result.stderr, /JSON output requires materializing more than 1 row\(s\)/);
    assert.doesNotMatch(result.stderr, /row 3: invalid JSON/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("CLI broken stdout mirrors Python broken pipe exit", { timeout: 20_000 }, async () => {
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-js-cli-"));
  try {
    const input = join(dir, "many.jsonl");
    const rows = Array.from({ length: 100_000 }, (_, index) => `{"fname":"Ada${index}"}`);
    writeFileSync(input, `${rows.join("\n")}\n`, "utf8");

    const result = await runCliWithClosedStdout(["map", input, "--in-format", "jsonl", "--format", "jsonl"]);

    assert.equal(result.status, 120);
    assert.equal(result.stdout, "{");
    if (process.platform === "win32") {
      assert.equal(
        result.stderr,
        `error: [Errno 22] Invalid argument${CLI_EOL}Exception ignored while flushing sys.stdout:${CLI_EOL}OSError: [Errno 22] Invalid argument${CLI_EOL}`,
      );
    } else {
      assert.equal(
        result.stderr,
        `error: [Errno 32] Broken pipe${CLI_EOL}Exception ignored while flushing sys.stdout:${CLI_EOL}BrokenPipeError: [Errno 32] Broken pipe${CLI_EOL}`,
      );
    }
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("CLI scalar JSON input maps as zero rows like Python", () => {
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-js-cli-"));
  try {
    const input = join(dir, "scalar.json");
    writeFileSync(input, "42", "utf8");

    const result = runCli(["map", input, "--in-format", "json", "--format", "json"]);
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.stdout, `[]${CLI_EOL}`);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("CLI can quarantine bad JSONL rows", () => {
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-js-cli-"));
  try {
    const input = join(dir, "contacts.jsonl");
    const output = join(dir, "out.jsonl");
    const quarantine = join(dir, "bad.jsonl");
    writeFileSync(input, '{"fname":"Jane"}\nnot json\n{"email":"A@EXAMPLE.COM"}\n', "utf8");

    const result = runCli([
      "map",
      input,
      "--in-format",
      "jsonl",
      "--format",
      "jsonl",
      "-o",
      output,
      "--on-error",
      "quarantine",
      "--quarantine-output",
      quarantine,
    ]);
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stderr, /warning: quarantined row 2: invalid JSON: Expecting value/);
    assert.match(result.stderr, /quarantined 1 row/);
    assert.equal(readFileSync(output, "utf8").trim().split(/\r?\n/).length, 2);
    const bad = JSON.parse(readFileSync(quarantine, "utf8").trim()) as { row: number; error: string };
    assert.equal(bad.row, 2);
    assert.equal(bad.error, "invalid JSON: Expecting value");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("CLI quarantine paths cannot overwrite input or mapped output", () => {
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-js-cli-"));
  try {
    const input = join(dir, "contacts.jsonl");
    const output = join(dir, "out.jsonl");
    const originalInput = '{"fname":"Jane"}\nnot json\n';
    writeFileSync(input, originalInput, "utf8");
    writeFileSync(output, "existing\n", "utf8");

    const inputCollision = runCli([
      "map",
      input,
      "--format",
      "jsonl",
      "--on-error",
      "quarantine",
      "--quarantine-output",
      input,
    ]);
    assert.equal(inputCollision.status, 1);
    assert.match(inputCollision.stderr, /quarantine output must differ from the input path/);
    assert.equal(readFileSync(input, "utf8"), originalInput);

    const outputCollision = runCli([
      "map",
      input,
      "-o",
      output,
      "--format",
      "jsonl",
      "--on-error",
      "quarantine",
      "--quarantine-output",
      output,
    ]);
    assert.equal(outputCollision.status, 1);
    assert.match(outputCollision.stderr, /quarantine output must differ from the mapped output path/);
    assert.equal(readFileSync(output, "utf8"), "existing\n");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
