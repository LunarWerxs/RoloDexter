// Co-located contract test for _i18n_cache.ts: where language packs are
// looked for, which language codes may become a cache filename, and which
// cache files are trusted. The ContactMapper-level behaviour built on top of
// this lives in test/mapper.i18n.test.ts.
import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import {
  SUPPORTED_LANGUAGES,
  discover_cached,
  discoverCachedLanguages,
  get_all_cache_dirs,
  get_cache_dir,
  get_writable_cache_dir,
  getAllCacheDirs,
  getCacheDir,
  getWritableCacheDir,
  load_cached,
  loadCachedLanguage,
  normalizeLanguageCode,
  userI18nCacheDir,
} from "./_i18n_cache.js";

function withTempDir(prefix: string, body: (dir: string) => void): void {
  const dir = mkdtempSync(join(tmpdir(), prefix));
  try {
    body(dir);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

function writeJson(path: string, body: unknown): void {
  writeFileSync(path, JSON.stringify(body), "utf8");
}

test("SUPPORTED_LANGUAGES maps each code to its translator code and name, and is frozen", () => {
  assert.deepEqual(SUPPORTED_LANGUAGES.es, ["es", "Spanish"]);
  // Three codes differ from the translator's own spelling.
  assert.equal(SUPPORTED_LANGUAGES.zh[0], "zh-CN");
  assert.equal(SUPPORTED_LANGUAGES.nb[0], "no");
  assert.equal(SUPPORTED_LANGUAGES.he[0], "iw");
  assert.equal(Object.isFrozen(SUPPORTED_LANGUAGES), true);
});

test("normalizeLanguageCode folds case and whitespace and rejects anything else", () => {
  assert.equal(normalizeLanguageCode("es"), "es");
  assert.equal(normalizeLanguageCode(" ES "), "es");
  assert.equal(normalizeLanguageCode("zz"), undefined);
  assert.equal(normalizeLanguageCode(""), undefined);
  assert.equal(normalizeLanguageCode(42), undefined);
  assert.equal(normalizeLanguageCode(null), undefined);
  // A path must never pass as a language code.
  assert.equal(normalizeLanguageCode("../es"), undefined);
  // Inherited Object members are not supported languages.
  assert.equal(normalizeLanguageCode("constructor"), undefined);
  assert.equal(normalizeLanguageCode("__proto__"), undefined);
});

test(
  "the user cache directory follows the platform cache variable and is created on request",
  { skip: process.platform === "darwin" ? "macOS always uses ~/Library/Caches" : false },
  () => {
    const variable = process.platform === "win32" ? "LOCALAPPDATA" : "XDG_CACHE_HOME";
    const saved = process.env[variable];
    withTempDir("rolodexter-js-i18n-home-", (dir) => {
      process.env[variable] = dir;
      try {
        const expected = join(dir, "rolodexter", "i18n");
        assert.equal(userI18nCacheDir(), expected);
        assert.equal(existsSync(expected), false);
        assert.equal(getWritableCacheDir(), expected);
        assert.equal(existsSync(expected), true);
        assert.equal(getCacheDir(), expected);
        assert.equal(get_writable_cache_dir(), expected);
        assert.equal(get_cache_dir(), expected);
        // Once it exists it is searched, exactly once.
        const dirs = getAllCacheDirs({ cache_dir: expected });
        assert.equal(dirs.filter((entry) => entry === expected).length, 1);
      } finally {
        if (saved === undefined) {
          delete process.env[variable];
        } else {
          process.env[variable] = saved;
        }
      }
    });
  },
);

test("getAllCacheDirs adds an existing extra cache_dir and skips a missing one", () => {
  withTempDir("rolodexter-js-i18n-dirs-", (dir) => {
    assert.ok(getAllCacheDirs({ cache_dir: dir }).includes(dir));
    const missing = join(dir, "missing");
    assert.equal(getAllCacheDirs({ cache_dir: missing }).includes(missing), false);
    assert.deepEqual(get_all_cache_dirs(), getAllCacheDirs());
  });
});

test("loadCachedLanguage returns a well-formed pack from cache_dir", () => {
  withTempDir("rolodexter-js-i18n-load-", (dir) => {
    writeJson(join(dir, "af.json"), {
      language_code: "af",
      language_name: "Afrikaans",
      fields: { email: ["e-pos"] },
    });
    assert.deepEqual(loadCachedLanguage("AF", { cache_dir: dir })?.fields?.email, ["e-pos"]);
    // An unsupported code never reaches the filesystem.
    writeJson(join(dir, "zz.json"), { language_code: "zz", language_name: "zz", fields: {} });
    assert.equal(loadCachedLanguage("zz", { cache_dir: dir }), undefined);
  });
});

test("loadCachedLanguage skips a cache file that fails the schema check", () => {
  withTempDir("rolodexter-js-i18n-schema-", (dir) => {
    const path = join(dir, "af.json");
    // Another cache directory may legitimately hold af.json too, so assert
    // that the poisoned alias is never trusted rather than on undefined.
    const read = (): unknown => loadCachedLanguage("af", { cache_dir: dir })?.fields?.email;
    const rejected: unknown[] = [
      null,
      ["not", "an", "object"],
      { language_code: "af", fields: { email: ["poisoned"] } },
      { language_code: "af", language_name: "Afrikaans", fields: ["poisoned"] },
      { language_code: "af", language_name: "Afrikaans", fields: { "  ": ["poisoned"], email: ["poisoned"] } },
      { language_code: "af", language_name: "Afrikaans", fields: { email: "poisoned" } },
      { language_code: "af", language_name: "Afrikaans", fields: { email: ["poisoned", "  "] } },
      { language_code: "af", language_name: "Afrikaans", fields: { email: ["poisoned", 7] } },
    ];
    for (const body of rejected) {
      writeJson(path, body);
      assert.notDeepEqual(read(), ["poisoned"]);
      assert.notDeepEqual(read(), ["poisoned", "  "]);
      assert.notDeepEqual(read(), ["poisoned", 7]);
    }
    writeFileSync(path, "NOT JSON{{{", "utf8");
    assert.doesNotThrow(read);
  });
});

test("discoverCachedLanguages lists only *.json files named after a supported language", () => {
  withTempDir("rolodexter-js-i18n-discover-", (dir) => {
    writeJson(join(dir, "sw.json"), {});
    writeJson(join(dir, "notes.json"), {});
    writeFileSync(join(dir, "af.txt"), "", "utf8");
    mkdirSync(join(dir, "nested"));
    const found = discoverCachedLanguages({ cache_dir: dir });
    assert.ok("sw" in found);
    assert.equal("notes" in found, false);
    assert.equal(Object.values(found).includes(join(dir, "af.txt")), false);
    assert.deepEqual(discover_cached(), discoverCachedLanguages());
  });
});

test("the Python-named wrappers keep Python's call signatures", () => {
  assert.equal(load_cached("zz"), null);
  assert.throws(() => (load_cached as unknown as () => unknown)(), {
    name: "TypeError",
    message: "load_cached() missing 1 required positional argument: 'lang_code'",
  });
  assert.throws(() => (load_cached as unknown as (a: string, b: string) => unknown)("es", "x"), {
    name: "TypeError",
    message: "load_cached() takes 1 positional argument but 2 were given",
  });
  for (const [name, fn] of [
    ["get_writable_cache_dir", get_writable_cache_dir],
    ["get_cache_dir", get_cache_dir],
    ["get_all_cache_dirs", get_all_cache_dirs],
    ["discover_cached", discover_cached],
  ] as const) {
    assert.throws(() => (fn as unknown as (extra: unknown) => unknown)("x"), {
      name: "TypeError",
      message: `${name}() takes 0 positional arguments but 1 was given`,
    });
  }
});
