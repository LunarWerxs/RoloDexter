// Audit fixes for the npm commands and language packs: H5, H7, M12, L22
// (contract C5), L23, L24. Python's side is tests/test_audit_i18n.py.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import * as nodeModule from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import { PatternRegistry, generate_language, get_cache_dir, load_cached } from "../src/index.js";
import { generateLanguageAsync } from "../src/i18n.js";
import { translatableFields } from "../src/_i18n_generate.js";
import { cliPath, i18nCliPath, runI18nCli } from "./_mapper_test_helpers.js";

type Pack = { fields?: Record<string, string[]>; failed_fields?: string[]; language_name?: string };

function withEnv<T>(vars: Record<string, string | undefined>, fn: () => T): T {
  const saved = Object.fromEntries(Object.keys(vars).map((key) => [key, process.env[key]]));
  const restore = (): void => {
    for (const [key, value] of Object.entries(saved)) {
      if (value === undefined) {
        delete process.env[key];
      } else {
        process.env[key] = value;
      }
    }
  };
  for (const [key, value] of Object.entries(vars)) {
    if (value === undefined) {
      delete process.env[key];
    } else {
      process.env[key] = value;
    }
  }
  try {
    const result = fn();
    if (result instanceof Promise) {
      return result.finally(restore) as T;
    }
    restore();
    return result;
  } catch (error) {
    restore();
    throw error;
  }
}

function captureWarnings(fn: () => void): string[] {
  const seen: string[] = [];
  const listener = (warning: Error): void => {
    if (warning.name === "RolodexterWarning") {
      seen.push(warning.message);
    }
  };
  process.on("rolodexterWarning" as "warning", listener);
  try {
    fn();
  } finally {
    process.off("rolodexterWarning" as "warning", listener);
  }
  return seen;
}

/**
 * A stand-in for @vitalets/google-translate-api, installed in every Node
 * process started with the returned NODE_OPTIONS through Node's own module
 * hooks: the real helper process imports the real generator, which imports
 * this stub instead of the network library. `STUB_FAIL` names phrases that
 * fail; every phrase asked for is appended to `STUB_LOG`.
 */
function translatorStub(dir: string): string {
  const stub = join(dir, "stub-translate.mjs");
  writeFileSync(stub, [
    'import { appendFileSync } from "node:fs";',
    "export async function translate(text) {",
    '  if (process.env.STUB_LOG) appendFileSync(process.env.STUB_LOG, `${text}\\n`);',
    '  if ((process.env.STUB_FAIL ?? "").split(",").includes(text)) throw new Error("stub failure");',
    "  return { text: `zz ${text}` };",
    "}",
    "",
  ].join("\n"));
  const hooks = join(dir, "hooks.mjs");
  writeFileSync(hooks, [
    `const STUB = ${JSON.stringify(pathToFileURL(stub).href)};`,
    "export async function resolve(specifier, context, next) {",
    '  if (specifier === "@vitalets/google-translate-api") return { url: STUB, shortCircuit: true };',
    "  return next(specifier, context);",
    "}",
    "",
  ].join("\n"));
  const register = join(dir, "register.mjs");
  writeFileSync(register, [
    'import { register } from "node:module";',
    `register(${JSON.stringify(pathToFileURL(hooks).href)});`,
    "",
  ].join("\n"));
  return `--import "${pathToFileURL(register).href}"`;
}

const hasModuleHooks = typeof (nodeModule as { register?: unknown }).register === "function";

test("H5: both commands run when started through a symlink, as npm installs them", (t) => {
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-h5-"));
  try {
    const cliLink = join(dir, "rolodexter");
    const i18nLink = join(dir, "rolodexter-i18n");
    try {
      symlinkSync(cliPath(), cliLink);
      symlinkSync(i18nCliPath(), i18nLink);
    } catch (error) {
      if (process.platform === "win32" && (error as NodeJS.ErrnoException).code === "EPERM") {
        t.skip("creating symlinks is not permitted for this Windows account");
        return;
      }
      throw error;
    }
    const fields = spawnSync(process.execPath, [cliLink, "fields"], { encoding: "utf8" });
    assert.equal(fields.status, 0, fields.stderr);
    assert.match(fields.stdout, /\bfirst_name\b/);
    assert.match(fields.stdout, /\bemail\b/);

    const list = spawnSync(process.execPath, [i18nLink, "--list"], { encoding: "utf8" });
    assert.equal(list.status, 0, list.stderr);
    assert.match(list.stdout, /Supported languages \(40\):/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("H7 + M12: generate_language runs the real helper process, records failed fields and retries only them", { skip: !hasModuleHooks && "needs node:module register()" }, () => {
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-h7-"));
  try {
    const cacheDir = join(dir, "packs");
    const log = join(dir, "calls.log");
    const nodeOptions = translatorStub(dir);
    const env = { NODE_OPTIONS: nodeOptions, ROLODEXTER_CACHE_DIR: cacheDir, STUB_LOG: log };

    const first = withEnv({ ...env, STUB_FAIL: "email" }, () => generate_language("es", { retries: 0 })) as Pack;
    assert.deepEqual(first.failed_fields, ["email"]);
    assert.ok(first.fields?.first_name?.includes("zz first name"), JSON.stringify(first.fields?.first_name));
    assert.equal(first.fields?.email, undefined);
    const onDisk = JSON.parse(readFileSync(join(cacheDir, "es.json"), "utf8")) as Pack;
    assert.deepEqual(onDisk.failed_fields, ["email"]);
    assert.equal(readFileSync(log, "utf8").trim().split("\n").length, translatableFields().size);

    rmSync(log);
    const second = withEnv({ ...env, STUB_FAIL: "" }, () => generate_language("es", { retries: 0 })) as Pack;
    assert.deepEqual(readFileSync(log, "utf8").trim().split("\n"), ["email"]);
    assert.equal(second.failed_fields, undefined);
    assert.ok(second.fields?.email?.includes("zz email"));

    // Complete now: served from the cache, nothing translated.
    rmSync(log);
    withEnv(env, () => generate_language("es"));
    assert.equal(existsSync(log), false);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("H7: generateLanguageAsync is public on rolodexter/i18n and shares the cache", async () => {
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-h7-async-"));
  try {
    writeFileSync(join(dir, "fr.json"), JSON.stringify({ language_code: "fr", language_name: "French", fields: { email: ["courriel"] } }));
    const data = await withEnv({ ROLODEXTER_CACHE_DIR: dir }, () => generateLanguageAsync("fr"));
    assert.deepEqual(data.fields, { email: ["courriel"] });
    assert.throws(() => generateLanguageAsync("fr", { translator: () => "x" } as never), /translator/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("H7: the CommonJS bundles reach the generator from the helper process", () => {
  // A zero-second request budget makes every phrase fail at once with no
  // network answer needed. Before the fix the helper imported a module with
  // no generateLanguageAsync and generate_language threw instead.
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-h7-cjs-"));
  try {
    const bundle = fileURLToPath(new URL("../cjs/index.cjs", import.meta.url));
    const script = join(dir, "main.cjs");
    writeFileSync(script, [
      `const { generate_language } = require(${JSON.stringify(bundle)});`,
      'const data = generate_language("de", { timeout: 0, retries: 0 });',
      "console.log(JSON.stringify({ fields: Object.keys(data.fields).length, failed: data.failed_fields.length }));",
      "",
    ].join("\n"));
    const result = spawnSync(process.execPath, [script], {
      encoding: "utf8",
      env: { ...process.env, ROLODEXTER_CACHE_DIR: join(dir, "packs") },
    });
    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(JSON.parse(result.stdout.trim()), { fields: 0, failed: translatableFields().size });
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("M12: rolodexter-i18n prints N of M fields and exits 2 when some fields failed", { skip: !hasModuleHooks && "needs node:module register()" }, () => {
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-m12-cli-"));
  try {
    const result = spawnSync(process.execPath, [i18nCliPath(), "--languages", "es", "--retries", "0"], {
      encoding: "utf8",
      env: { ...process.env, NODE_OPTIONS: translatorStub(dir), ROLODEXTER_CACHE_DIR: join(dir, "packs"), STUB_FAIL: "email" },
    });
    assert.equal(result.status, 2, result.stderr);
    const total = translatableFields().size;
    assert.match(result.stdout, new RegExp(`\\[es\\] Spanish: ${total - 1} of ${total} fields, \\d+ aliases; 1 failed \\(email\\)`));
    assert.match(result.stdout, /Incomplete 1 language\(s\): es; run again to retry the failed fields\./);
    assert.doesNotMatch(result.stdout, /Done\./);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("L22 / C5: ROLODEXTER_CACHE_DIR is the pack folder and PYTHONPATH is not read", () => {
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-c5-"));
  try {
    const packs = join(dir, "packs");
    const pythonSrc = join(dir, "pysrc");
    mkdirSync(join(pythonSrc, "rolodexter", "i18n"), { recursive: true });
    writeFileSync(join(pythonSrc, "rolodexter", "i18n", "fr.json"), JSON.stringify({ language_code: "fr", language_name: "French", fields: { email: ["courriel"] } }));
    withEnv({ ROLODEXTER_CACHE_DIR: packs, PYTHONPATH: pythonSrc }, () => {
      assert.equal(get_cache_dir(), packs);
      writeFileSync(join(packs, "es.json"), JSON.stringify({ language_code: "es", language_name: "Spanish", fields: { email: ["correo"] } }));
      assert.deepEqual(load_cached("es")?.fields, { email: ["correo"] });
      assert.equal(load_cached("fr"), null);
    });
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("L23: missing, unknown and corrupt language packs warn with Python's text", () => {
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-l23-"));
  try {
    const missing = withEnv({ ROLODEXTER_CACHE_DIR: dir }, () => captureWarnings(() => {
      new PatternRegistry({ languages: ["es", "xx"] });
    }));
    assert.deepEqual(missing, [
      "No cached i18n aliases for es — these languages were NOT loaded. Generate them first (offline) with: python -m rolodexter.i18n --languages es",
      "Unsupported i18n language code(s) 'xx' — ignored. Supported codes: af, ar, bg, ca, cs, da, de, el, es, et, fi, fr, he, hi, hr, hu, id, it, ja, ko, lt, lv, ms, nb, nl, pl, pt, ro, ru, sk, sl, sr, sv, sw, th, tl, tr, uk, vi, zh",
    ]);

    const pack = join(dir, "es.json");
    writeFileSync(pack, "[]");
    const corrupt = withEnv({ ROLODEXTER_CACHE_DIR: dir }, () => captureWarnings(() => {
      assert.equal(load_cached("es"), null);
    }));
    assert.deepEqual(corrupt, [`Ignoring corrupt i18n cache file ${pack}: expected a JSON object, got list.`]);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("L24: --retranslate-fields rejects unknown field names as a usage error", () => {
  const result = runI18nCli(["--languages", "es", "--retranslate-fields", "email,emial,score"]);
  assert.equal(result.status, 2);
  assert.match(result.stderr, /error: argument --retranslate-fields: unknown or untranslated field\(s\): 'emial', 'score'/);
  assert.equal(result.stdout, "");
});
