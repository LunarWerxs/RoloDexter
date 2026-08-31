// The i18n entry point is a hand-written mirror of Python's argparse: prefix
// matching, "=" inline values, ambiguity detection, and Python's exact error
// wording. mapper.test.ts drives it by spawning it as a subprocess, which
// proves it works but leaves the parser itself unmeasured and lets a message
// drift from i18n.py unnoticed. main() is part of __all__, and Python's own
// tests/test_i18n_cli.py calls it directly with a patched argv, so this does
// the same thing in-process.
//
// Every case below stays on a path that touches no network: --help, --list,
// --dry-run, a parse error, or an empty language selection. Anything else
// reaches the real translator.
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  discover_cached,
  generate_language,
  get_all_cache_dirs,
  get_cache_dir,
  get_writable_cache_dir,
  load_cached,
  main,
} from "../src/i18n.js";

const realWrite = process.stdout.write.bind(process.stdout);

/** Run the CLI in-process the way Python's tests do, capturing what it printed. */
async function runI18n(argv: string[]): Promise<{ code: number; stdout: string }> {
  const savedArgv = process.argv;
  let captured = "";
  process.argv = ["node", "i18n", ...argv];
  process.stdout.write = ((chunk: string | Uint8Array): boolean => {
    captured += typeof chunk === "string" ? chunk : Buffer.from(chunk).toString("utf8");
    return true;
  }) as typeof process.stdout.write;
  try {
    const code = await main();
    // The CLI emits CRLF on Windows; assertions are about the text, not the
    // line endings, which mapper.test.ts already pins.
    return { code, stdout: captured.replace(/\r\n/g, "\n") };
  } finally {
    process.stdout.write = realWrite;
    process.argv = savedArgv;
  }
}

/** Run the CLI expecting it to reject, and hand back the error it rejected with. */
async function runI18nExpectingError(argv: string[]): Promise<Error & { exitCode?: number }> {
  try {
    const { code, stdout } = await runI18n(argv);
    assert.fail(`expected ${JSON.stringify(argv)} to fail, but it exited ${code}: ${stdout}`);
  } catch (error) {
    if (error instanceof assert.AssertionError) {
      throw error;
    }
    return error as Error & { exitCode?: number };
  }
}

test("--help prints the argparse-shaped usage, including by prefix", async () => {
  const { code, stdout } = await runI18n(["--help"]);

  assert.equal(code, 0);
  assert.match(stdout, /^usage: python(?:\.exe)? -m rolodexter\.i18n \[-h\]/);
  assert.match(stdout, /Generate i18n language files for rolodexter \(on-demand, cached\)\./);
  // Every option is documented; a flag added to the parser without a help
  // line would drift from `python -m rolodexter.i18n --help`.
  for (const option of [
    "-h, --help",
    "--languages LANGUAGES",
    "--list",
    "--retranslate-fields RETRANSLATE_FIELDS",
    "--force",
    "--dry-run",
    "--workers WORKERS",
    "--timeout TIMEOUT",
    "--retries RETRIES",
    "--retry-backoff RETRY_BACKOFF",
    "--verbose, -v",
  ]) {
    assert.ok(stdout.includes(option), `usage text is missing ${option}`);
  }

  // -h and any unambiguous prefix of --help produce the same text.
  assert.equal((await runI18n(["-h"])).stdout, stdout);
  assert.equal((await runI18n(["--hel"])).stdout, stdout);
});

test("--list reports every supported language and whether it is cached", async () => {
  const { code, stdout } = await runI18n(["--list"]);

  assert.equal(code, 0);
  assert.match(stdout, /^Supported languages \(40\):$/m);
  assert.match(stdout, /^ {2}es\s+Spanish\s+\[(?:cached|not generated)\]$/m);
  assert.match(stdout, /^ {2}zh\s+Chinese[^[]*\[(?:cached|not generated)\]$/m);
  // One status line per supported language, whatever the cache state is.
  assert.equal(stdout.match(/\[(?:cached|not generated)\]/g)?.length, 40);
});

test("--dry-run previews without generating anything", async () => {
  const { code, stdout } = await runI18n(["--dry-run", "--languages", "es"]);

  assert.equal(code, 0);
  assert.match(stdout, /Generating 1 language\(s\)\.\.\./);
  assert.match(stdout, /Existing cache dirs: /);
  assert.match(stdout, /\[es\] Spanish: (?:cached|would generate) \(\d+ fields\)/);
  assert.match(stdout, /Done\.$/m);

  // With no --languages it defaults to every supported language.
  assert.match((await runI18n(["--dry-run"])).stdout, /Generating 40 language\(s\)\.\.\./);
});

test("language selection folds case, drops blanks, and accepts both value forms", async () => {
  const separate = await runI18n(["--dry-run", "--languages", "es"]);
  // "--languages=es" is the same argument written the other way.
  assert.equal((await runI18n(["--dry-run", "--languages=es"])).stdout, separate.stdout);
  // An unambiguous prefix resolves to the full option, as argparse does.
  assert.equal((await runI18n(["--dry-run", "--lang", "es"])).stdout, separate.stdout);
  // "ES," is upper-case and has a trailing comma; neither is an error.
  assert.equal((await runI18n(["--dry-run", "--languages", "ES,"])).stdout, separate.stdout);

  assert.match((await runI18n(["--dry-run", "--languages", "es,fr"])).stdout, /Generating 2 language\(s\)/);
});

test("an unknown language is named, and only the unknown one", async () => {
  const error = await runI18nExpectingError(["--languages", "xx_fake"]);
  assert.match(error.message, /^Unknown language code\(s\): \['xx_fake'\]/);
  assert.match(error.message, /Run with --list to see supported languages\./);

  const mixed = await runI18nExpectingError(["--languages", "es,xx_fake"]);
  assert.match(mixed.message, /^Unknown language code\(s\): \['xx_fake'\]/);
});

test("selecting no languages at all is a no-op, not a crash", async () => {
  // "," is all separators and no codes. Nothing is generated, so this is the
  // one non-dry-run path that reaches the generate branch without contacting
  // a translator.
  const { code, stdout } = await runI18n(["--languages", ","]);

  assert.equal(code, 0);
  assert.match(stdout, /Generating 0 language\(s\)\.\.\./);
  assert.match(stdout, /Cache dir: /);
  assert.match(stdout, /Done\.$/m);
  assert.doesNotMatch(stdout, /FAILED/);
});

test("every option parses and is accepted", async () => {
  const optionSets: string[][] = [
    ["--force"],
    ["--retranslate-fields", "first_name,email"],
    ["--retranslate-fields=first_name"],
    ["--workers", "3"],
    ["--workers", "0"],
    ["--timeout", "2.5"],
    ["--timeout", ".5"],
    ["--timeout", "1e2"],
    ["--retries", "0"],
    ["--retry-backoff", "1.5"],
    ["--verbose"],
    ["-v"],
    // Non-finite floats are accepted the way Python's float() accepts them.
    ["--timeout", "inf"],
    ["--timeout", "nan"],
    ["--timeout", "Infinity"],
  ];

  for (const options of optionSets) {
    const { code } = await runI18n(["--dry-run", "--languages", "es", ...options]);
    assert.equal(code, 0, `expected ${JSON.stringify(options)} to be accepted`);
  }

  // A bare "--" ends option parsing; with nothing after it that is legal.
  assert.equal((await runI18n(["--dry-run", "--"])).code, 0);
});

test("numeric options reject what Python's converters reject", async () => {
  const cases: Array<[string[], RegExp]> = [
    [["--workers", "abc"], /^argument --workers: invalid _non_negative_int value: 'abc'$/],
    [["--workers", "1.5"], /^argument --workers: invalid _non_negative_int value: '1\.5'$/],
    [["--workers", "-1"], /^argument --workers: must be non-negative$/],
    [["--retries", "1.5"], /^argument --retries: invalid _non_negative_int value: '1\.5'$/],
    [["--retries", "-2"], /^argument --retries: must be non-negative$/],
    [["--timeout", "abc"], /^argument --timeout: invalid _non_negative_float value: 'abc'$/],
    [["--timeout", "-1"], /^argument --timeout: must be non-negative$/],
    [["--retry-backoff", "abc"], /^argument --retry-backoff: invalid _non_negative_float value: 'abc'$/],
    [["--retry-backoff", "-0.5"], /^argument --retry-backoff: must be non-negative$/],
  ];

  for (const [argv, message] of cases) {
    const error = await runI18nExpectingError(argv);
    assert.match(error.message, message);
    // Exit code 2 is what argparse uses for a usage error.
    assert.equal(error.exitCode, 2, `expected ${JSON.stringify(argv)} to be a usage error`);
  }
});

test("malformed argument structure fails the way argparse does", async () => {
  const cases: Array<[string[], RegExp]> = [
    // A prefix that matches more than one option is ambiguous, not a guess.
    [["--re"], /^ambiguous option: --re could match --retranslate-fields, --retries, --retry-backoff$/],
    [["--nope"], /^unrecognized arguments: --nope$/],
    [["extra"], /^unrecognized arguments: extra$/],
    [["-x"], /^unrecognized arguments: -x$/],
    // An option that takes a value, given none.
    [["--languages"], /^argument --languages: expected one argument$/],
    // The next token looks like another option, so it is not swallowed as a value.
    [["--languages", "--force"], /^argument --languages: expected one argument$/],
    [["--timeout", "-inf"], /^argument --timeout: expected one argument$/],
    // Flags take no value, so "=x" is an error rather than being ignored.
    [["--list=x"], /^argument --list: ignored explicit argument 'x'$/],
    [["--force=x"], /^argument --force: ignored explicit argument 'x'$/],
    [["--dry-run=x"], /^argument --dry-run: ignored explicit argument 'x'$/],
    [["--verbose=x"], /^argument --verbose: ignored explicit argument 'x'$/],
    [["--help=x"], /^argument --help: ignored explicit argument 'x'$/],
    // Anything after "--" is a positional, and this CLI takes none.
    [["--", "leftover"], /^unrecognized arguments: -- leftover$/],
  ];

  for (const [argv, message] of cases) {
    const error = await runI18nExpectingError(argv);
    assert.match(error.message, message);
    assert.equal(error.exitCode, 2, `expected ${JSON.stringify(argv)} to be a usage error`);
  }
});

test("the i18n subpath's own helpers enforce Python's positional arity", async () => {
  // These are separate wrappers from the same-named exports on the package
  // root, and only the root's were being exercised.
  assert.equal(typeof get_cache_dir(), "string");
  assert.ok(Array.isArray(get_all_cache_dirs()));
  assert.equal(typeof get_writable_cache_dir(), "string");
  assert.equal(typeof discover_cached(), "object");
  assert.equal(load_cached("__missing__"), null);

  assert.throws(
    () => (get_cache_dir as unknown as (extra: unknown) => unknown)("x"),
    { name: "TypeError", message: "get_cache_dir() takes 0 positional arguments but 1 was given" },
  );
  assert.throws(
    () => (get_all_cache_dirs as unknown as (extra: unknown) => unknown)("x"),
    { name: "TypeError", message: "get_all_cache_dirs() takes 0 positional arguments but 1 was given" },
  );
  assert.throws(
    () => (get_writable_cache_dir as unknown as (extra: unknown) => unknown)("x"),
    { name: "TypeError", message: "get_writable_cache_dir() takes 0 positional arguments but 1 was given" },
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
    () => (load_cached as unknown as (code: string, extra: unknown) => unknown)("es", "x"),
    { name: "TypeError", message: "load_cached() takes 1 positional argument but 2 were given" },
  );
  assert.throws(
    () => (generate_language as unknown as () => unknown)(),
    { name: "TypeError", message: "generate_language() missing 1 required positional argument: 'lang_code'" },
  );
  assert.throws(
    () => (generate_language as unknown as (code: string, options: unknown, extra: unknown) => unknown)("es", {}, "x"),
    { name: "TypeError", message: "generate_language() takes 1 positional argument but 3 were given" },
  );
  // An unsupported code is rejected before any translation is attempted.
  assert.throws(() => generate_language("__missing__"), {
    name: "ValueError",
    message: /^Unsupported language: '__missing__'\./,
  });
});

test("the broken-pipe handler is installed once, however often main runs", async () => {
  // Importing the module must not install it (mapper.test.ts pins that), and
  // running main() any number of times must not stack duplicates — a second
  // handler would report the same broken pipe twice. The absolute count is
  // not ours (the test runner attaches its own), so this measures the delta
  // after the handler is known to be installed.
  await runI18n(["--help"]);
  const afterFirstRun = process.stdout.listenerCount("error");
  assert.ok(afterFirstRun >= 1);

  await runI18n(["--help"]);
  await runI18n(["--list"]);

  assert.equal(process.stdout.listenerCount("error"), afterFirstRun);
});
