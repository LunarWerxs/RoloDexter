// Split out of the former monolithic mapper.test.ts (2572 lines, over the
// oversized-files gate of 2500). Same tests, grouped by topic. Shared
// CLI/version-probe helpers live in _mapper_test_helpers.ts.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import {
  __version__,
  __all__,
  ContactMapper,
  discover_cached,
  generate_language,
  get_all_cache_dirs,
  get_cache_dir,
  get_writable_cache_dir,
  load_cached,
  PatternRegistry,
  SUPPORTED_LANGUAGES,
  normalizeLanguageCode,
} from "../src/index.js";
import { discoverCachedLanguages, loadCachedLanguage } from "../src/_i18n_cache.js";
import { generateLanguage, generateLanguageAsync } from "../src/_i18n_generate.js";
import { VERSION_FROM_PACKAGE_JSON, runI18nCli, packageRoot } from "./_mapper_test_helpers.js";

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

  // A trailing comma used to be a hard error reporting an unknown language ''.
  // Empty entries are now dropped, matching i18n.py.
  const trailingEmptyLanguage = runI18nCli(["--dry-run", "--languages", "es,"]);
  assert.equal(trailingEmptyLanguage.status, 0, trailingEmptyLanguage.stderr);
  assert.match(trailingEmptyLanguage.stdout, /Generating 1 language\(s\)/);

  // Case-folding: "ES" resolves to the supported code.
  const upperCaseLanguage = runI18nCli(["--dry-run", "--languages", "ES"]);
  assert.equal(upperCaseLanguage.status, 0, upperCaseLanguage.stderr);
  assert.match(upperCaseLanguage.stdout, /\[es\] Spanish/);

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
  assert.equal(result.stdout.trim(), `${VERSION_FROM_PACKAGE_JSON} Ada function false false function function false`);
});

test("i18n language codes are validated before they become a file path", () => {
  // A caller-supplied code reaches loadCachedLanguage from
  // `new ContactMapper({languages})` and the CLI's --languages flag. Without
  // validation a relative path escapes the cache directory and has its
  // contents merged into the alias index, which decides where every column of
  // a contact export is routed.
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-js-i18n-guard-"));
  const outside = join(dir, "outside.json");
  const inner = join(dir, "cache");
  mkdirSync(inner, { recursive: true });
  try {
    writeFileSync(
      outside,
      JSON.stringify({ language_code: "x", language_name: "x", fields: { email: ["pwned"] } }),
      "utf8",
    );
    assert.equal(loadCachedLanguage("../outside", { cache_dir: inner }), undefined);
    assert.equal(loadCachedLanguage("zz", { cache_dir: inner }), undefined);

    // Case-folding: "ES" is the supported "es".
    assert.equal(normalizeLanguageCode(" ES "), "es");
    assert.equal(normalizeLanguageCode("zz"), undefined);
    assert.equal(normalizeLanguageCode(42), undefined);

    // A real code still loads.
    writeFileSync(
      join(inner, "es.json"),
      JSON.stringify({ language_code: "es", language_name: "Spanish", fields: { email: ["correo"] } }),
      "utf8",
    );
    assert.deepEqual(loadCachedLanguage("ES", { cache_dir: inner })?.fields?.email, ["correo"]);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("a malformed i18n cache file is skipped rather than trusted", () => {
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-js-i18n-bad-"));
  try {
    const read = (): unknown =>
      loadCachedLanguage("es", { cache_dir: dir })?.fields?.email;
    const write = (body: unknown): void => {
      writeFileSync(join(dir, "es.json"), JSON.stringify(body), "utf8");
    };
    // A real user cache may also hold es.json, and falling through to it is
    // correct behavior. What must never happen is the malformed file being
    // trusted, so assert on the poisoned alias rather than on undefined.

    write(["not", "an", "object"]);
    assert.notDeepEqual(read(), ["poisoned"]);

    write({ language_code: "es", fields: { email: ["poisoned"] } }); // missing language_name
    assert.notDeepEqual(read(), ["poisoned"]);

    write({ language_code: "es", language_name: "Spanish", fields: "nope" });
    assert.notDeepEqual(read(), ["poisoned"]);

    // A non-string alias used to throw out of ContactMapper construction.
    write({ language_code: "es", language_name: "Spanish", fields: { email: [123] } });
    assert.notDeepEqual(read(), [123]);
    assert.doesNotThrow(() => new ContactMapper({ languages: ["es"] }));

    writeFileSync(join(dir, "es.json"), "NOT JSON{{{", "utf8");
    assert.notDeepEqual(read(), ["poisoned"]);

    // Only *.json named after a supported language counts as a pack.
    writeFileSync(join(dir, "notes.json"), JSON.stringify({}), "utf8");
    assert.equal("notes" in discoverCachedLanguages({ cache_dir: dir }), false);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
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

