#!/usr/bin/env node
import { writeSync } from "node:fs";
import { fileURLToPath } from "node:url";

import {
  SUPPORTED_LANGUAGES,
  discover_cached as coreDiscoverCached,
  generateLanguageAsync,
  generate_language as generateLanguageSync,
  get_all_cache_dirs as coreGetAllCacheDirs,
  get_cache_dir as coreGetCacheDir,
  get_writable_cache_dir as coreGetWritableCacheDir,
  load_cached as coreLoadCached,
} from "./index.js";
import type { LanguageData } from "./index.js";

export { SUPPORTED_LANGUAGES } from "./index.js";

export const __all__ = [
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
] as const;

function positionalTypeError(callable: string, expected: number, given: number): TypeError {
  const expectedWord = expected === 1 ? "argument" : "arguments";
  const givenVerb = given === 1 ? "was" : "were";
  return new TypeError(`${callable}() takes ${expected} positional ${expectedWord} but ${given} ${givenVerb} given`);
}

function missingRequiredArg(callable: string, argName: string): TypeError {
  return new TypeError(`${callable}() missing 1 required positional argument: '${argName}'`);
}

export function get_writable_cache_dir(): string {
  if (arguments.length > 0) {
    throw positionalTypeError("get_writable_cache_dir", 0, arguments.length);
  }
  return coreGetWritableCacheDir();
}

export function get_cache_dir(): string {
  if (arguments.length > 0) {
    throw positionalTypeError("get_cache_dir", 0, arguments.length);
  }
  return coreGetCacheDir();
}

export function get_all_cache_dirs(): string[] {
  if (arguments.length > 0) {
    throw positionalTypeError("get_all_cache_dirs", 0, arguments.length);
  }
  return coreGetAllCacheDirs();
}

export function load_cached(lang_code: string): LanguageData | null {
  if (arguments.length < 1) {
    throw missingRequiredArg("load_cached", "lang_code");
  }
  if (arguments.length > 1) {
    throw positionalTypeError("load_cached", 1, arguments.length);
  }
  return coreLoadCached(lang_code);
}

export interface GenerateLanguageOptions {
  force?: boolean;
  force_fields?: Set<string> | string[];
  timeout?: number;
  retries?: number;
  retry_backoff?: number;
}

export function generate_language(langCode: string, options: GenerateLanguageOptions = {}): LanguageData {
  if (arguments.length < 1) {
    throw missingRequiredArg("generate_language", "lang_code");
  }
  if (arguments.length > 2) {
    throw positionalTypeError("generate_language", 1, arguments.length);
  }
  return generateLanguageSync(langCode, options);
}

export function discover_cached(): Record<string, string> {
  if (arguments.length > 0) {
    throw positionalTypeError("discover_cached", 0, arguments.length);
  }
  return coreDiscoverCached();
}

export const DEFAULT_TRANSLATE_TIMEOUT = 10;
export const DEFAULT_TRANSLATE_RETRIES = 1;
export const DEFAULT_TRANSLATE_RETRY_BACKOFF = 0.5;
export const MAX_I18N_WORKERS = 8;

const I18N_PROG = process.platform === "win32" ? "python.exe -m rolodexter.i18n" : "python -m rolodexter.i18n";
const CLI_EOL = process.platform === "win32" ? "\r\n" : "\n";

let brokenPipeExiting = false;

function brokenPipeText(): string {
  if (process.platform === "win32") {
    return "error: [Errno 22] Invalid argument\nException ignored while flushing sys.stdout:\nOSError: [Errno 22] Invalid argument\n";
  }
  return "error: [Errno 32] Broken pipe\nException ignored while flushing sys.stdout:\nBrokenPipeError: [Errno 32] Broken pipe\n";
}

function exitBrokenPipe(): never {
  if (!brokenPipeExiting) {
    brokenPipeExiting = true;
    try {
      writeSync(2, cliText(brokenPipeText()));
    } catch {
      // Match Python's best-effort broken-pipe reporting without masking exit.
    }
  }
  process.exit(120);
}

let brokenPipeHandlerInstalled = false;

function installBrokenPipeHandler(): void {
  if (brokenPipeHandlerInstalled) {
    return;
  }
  brokenPipeHandlerInstalled = true;
  process.stdout.on("error", (error: NodeJS.ErrnoException) => {
    if (error.code === "EPIPE" || error.code === "EINVAL") {
      exitBrokenPipe();
    }
    throw error;
  });
}

function cliText(text: string): string {
  return text.replace(/(?<!\r)\n/g, CLI_EOL);
}

function writeCliStdout(text: string): void {
  process.stdout.write(cliText(`${text}\n`));
}

function writeCliStderr(text: string): void {
  process.stderr.write(cliText(`${text}\n`));
}

interface I18nArgs {
  languages?: string;
  list: boolean;
  retranslateFields?: string;
  force: boolean;
  dryRun: boolean;
  workers: number;
  timeout: number;
  retries: number;
  retry_backoff: number;
}

function usage(): string {
  return [
    `usage: ${I18N_PROG} [-h] [--languages LANGUAGES] [--list]`,
    "                                     [--retranslate-fields RETRANSLATE_FIELDS]",
    "                                     [--force] [--dry-run] [--workers WORKERS]",
    "                                     [--timeout TIMEOUT] [--retries RETRIES]",
    "                                     [--retry-backoff RETRY_BACKOFF]",
    "                                     [--verbose]",
    "",
    "Generate i18n language files for rolodexter (on-demand, cached).",
    "",
    "options:",
  "  -h, --help            show this help message and exit",
  "  --languages LANGUAGES",
    "                        Comma-separated language codes (default: all",
    "                        supported)",
    "  --list                List supported languages and exit",
    "  --retranslate-fields RETRANSLATE_FIELDS",
    "                        Comma-separated canonical fields to force re-translate",
    "  --force               Re-translate ALL fields, ignoring cache",
    "  --dry-run             Preview without writing files",
    "  --workers WORKERS     Parallel workers, clamped to 8 max (default: 6)",
  "  --timeout TIMEOUT     Translation request timeout in seconds, when supported",
    "                        by the translator (default: 10)",
  "  --retries RETRIES     Retries after a failed translation attempt (default:",
    "                        1)",
  "  --retry-backoff RETRY_BACKOFF",
    "                        Base seconds between retries, multiplied by attempt",
    "                        number (default: 0.5)",
  "  --verbose, -v",
  ].join("\n");
}

function usageLine(): string {
  return [
    `usage: ${I18N_PROG} [-h] [--languages LANGUAGES] [--list]`,
    "                                     [--retranslate-fields RETRANSLATE_FIELDS]",
    "                                     [--force] [--dry-run] [--workers WORKERS]",
    "                                     [--timeout TIMEOUT] [--retries RETRIES]",
    "                                     [--retry-backoff RETRY_BACKOFF]",
    "                                     [--verbose]",
  ].join("\n");
}

function takeValue(argv: string[], index: number, option: string): [string, number] {
  const current = argv[index] ?? "";
  const equalsAt = current.indexOf("=");
  if (equalsAt !== -1) {
    return [current.slice(equalsAt + 1), index];
  }
  const value = argv[index + 1];
  if (value === undefined) {
    throw new I18nUsageError(`argument ${option}: expected one argument`);
  }
  return [value, index + 1];
}

class I18nUsageError extends Error {
  readonly exitCode = 2;
}

class I18nHelpError extends Error {
  constructor(readonly text: string) {
    super(text);
  }
}

function pyRepr(value: string): string {
  return `'${value.replace(/\\/g, "\\\\").replace(/'/g, "\\'")}'`;
}

function rejectExplicitFlagValue(option: string, value: string | undefined): void {
  if (value !== undefined) {
    throw new I18nUsageError(`argument ${option}: ignored explicit argument ${pyRepr(value)}`);
  }
}

function resolvedHelpOption(arg: string): boolean {
  if (arg === "-h") {
    return true;
  }
  if (!arg.startsWith("--") || arg === "--") {
    return false;
  }
  const equalsAt = arg.indexOf("=");
  const raw = equalsAt === -1 ? arg : arg.slice(0, equalsAt);
  if (!"--help".startsWith(raw)) {
    return false;
  }
  if (equalsAt !== -1) {
    throw new I18nUsageError(`argument --help: ignored explicit argument ${pyRepr(arg.slice(equalsAt + 1))}`);
  }
  return true;
}

function optionToken(arg: string, known: string[]): { option: string; value?: string } | undefined {
  if (!arg.startsWith("--") || arg === "--") {
    return undefined;
  }
  const equalsAt = arg.indexOf("=");
  const raw = equalsAt === -1 ? arg : arg.slice(0, equalsAt);
  const matches = known.filter((option) => option.startsWith(raw));
  if (matches.length === 1) {
    return { option: matches[0] ?? raw, value: equalsAt === -1 ? undefined : arg.slice(equalsAt + 1) };
  }
  if (matches.length > 1) {
    throw new I18nUsageError(`ambiguous option: ${raw} could match ${matches.join(", ")}`);
  }
  throw new I18nUsageError(`unrecognized arguments: ${arg}`);
}

function takeResolvedValue(argv: string[], index: number, option: string, value: string | undefined): [string, number] {
  if (value !== undefined) {
    return [value, index];
  }
  const next = argv[index + 1];
  if (next === undefined || (next.startsWith("-") && !/^-?(?:\d|\.\d)/.test(next))) {
    throw new I18nUsageError(`argument ${option}: expected one argument`);
  }
  return [next, index + 1];
}

function nonNegativeInt(raw: string, option: string): number {
  if (!/^[+-]?\d+$/.test(raw)) {
    throw new I18nUsageError(`argument ${option}: invalid _non_negative_int value: ${pyRepr(raw)}`);
  }
  const value = Number(raw);
  if (value < 0) {
    throw new I18nUsageError(`argument ${option}: must be non-negative`);
  }
  return value;
}

function nonNegativeFloat(raw: string, option: string): number {
  if (/^[+-]?(?:nan|inf(?:inity)?)$/i.test(raw)) {
    return raw.startsWith("-") ? Number.NEGATIVE_INFINITY : raw.toLowerCase().includes("nan") ? Number.NaN : Number.POSITIVE_INFINITY;
  }
  if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(raw)) {
    throw new I18nUsageError(`argument ${option}: invalid _non_negative_float value: ${pyRepr(raw)}`);
  }
  const value = Number(raw);
  if (value < 0) {
    throw new I18nUsageError(`argument ${option}: must be non-negative`);
  }
  return value;
}

function boundedWorkers(requested: number, targetCount: number): number {
  if (targetCount <= 0) {
    return 1;
  }
  return Math.min(Math.max(1, requested), targetCount, MAX_I18N_WORKERS);
}

function parseArgs(argv: string[]): I18nArgs {
  const knownOptions = [
    "--languages",
    "--list",
    "--retranslate-fields",
    "--force",
    "--dry-run",
    "--workers",
    "--timeout",
    "--retries",
    "--retry-backoff",
    "--verbose",
    "--help",
  ];
  const args: I18nArgs = {
    list: false,
    force: false,
    dryRun: false,
    workers: 6,
    timeout: 10,
    retries: 1,
    retry_backoff: 0.5,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i] ?? "";
    if (arg === "--") {
      const rest = argv.slice(i + 1);
      if (rest.length > 0) {
        throw new I18nUsageError(`unrecognized arguments: -- ${rest.join(" ")}`);
      }
      break;
    }
    const resolved = optionToken(arg, knownOptions);
    const option = resolved?.option ?? arg;
    const inlineValue = resolved?.value;
    if (option === "--help" || arg === "-h") {
      rejectExplicitFlagValue("--help", inlineValue);
      throw new I18nHelpError(usage());
    }
    if (option === "--languages") {
      const [value, next] = takeResolvedValue(argv, i, "--languages", inlineValue);
      args.languages = value;
      i = next;
    } else if (option === "--list") {
      rejectExplicitFlagValue("--list", inlineValue);
      args.list = true;
    } else if (option === "--retranslate-fields") {
      const [value, next] = takeResolvedValue(argv, i, "--retranslate-fields", inlineValue);
      args.retranslateFields = value;
      i = next;
    } else if (option === "--force") {
      rejectExplicitFlagValue("--force", inlineValue);
      args.force = true;
    } else if (option === "--dry-run") {
      rejectExplicitFlagValue("--dry-run", inlineValue);
      args.dryRun = true;
    } else if (option === "--workers") {
      const [value, next] = takeResolvedValue(argv, i, "--workers", inlineValue);
      args.workers = nonNegativeInt(value, "--workers");
      i = next;
    } else if (option === "--timeout") {
      const [value, next] = takeResolvedValue(argv, i, "--timeout", inlineValue);
      args.timeout = nonNegativeFloat(value, "--timeout");
      i = next;
    } else if (option === "--retries") {
      const [value, next] = takeResolvedValue(argv, i, "--retries", inlineValue);
      args.retries = nonNegativeInt(value, "--retries");
      i = next;
    } else if (option === "--retry-backoff") {
      const [value, next] = takeResolvedValue(argv, i, "--retry-backoff", inlineValue);
      args.retry_backoff = nonNegativeFloat(value, "--retry-backoff");
      i = next;
    } else if (option === "--verbose" || arg === "-v") {
      rejectExplicitFlagValue(option === "--verbose" ? "--verbose" : "-v", inlineValue);
      // Kept for Python CLI argument parity.
    } else {
      throw new I18nUsageError(`unrecognized arguments: ${arg}`);
    }
  }
  return args;
}

function targetLanguages(raw: string | undefined): string[] {
  if (!raw) {
    return Object.keys(SUPPORTED_LANGUAGES).sort();
  }
  const requested = raw.split(",").map((code) => code.trim());
  const unknown = requested.filter((code) => !(code in SUPPORTED_LANGUAGES));
  if (unknown.length > 0) {
    throw new Error(`Unknown language code(s): [${unknown.map(pyRepr).join(", ")}]\nRun with --list to see supported languages.`);
  }
  return requested;
}

async function mainWithArgs(argv = process.argv.slice(2)): Promise<number> {
  let args: I18nArgs;
  try {
    args = parseArgs(argv);
  } catch (error) {
    if (error instanceof I18nHelpError) {
      writeCliStdout(error.text);
      return 0;
    }
    throw error;
  }

  if (args.list) {
    writeCliStdout(`Supported languages (${Object.keys(SUPPORTED_LANGUAGES).length}):\n`);
    for (const [code, [, name]] of Object.entries(SUPPORTED_LANGUAGES).sort()) {
      const status = load_cached(code) ? "cached" : "not generated";
      writeCliStdout(`  ${code.padEnd(5)}  ${name.padEnd(25)}  [${status}]`);
    }
    return 0;
  }

  const languages = targetLanguages(args.languages);
  const force_fields = args.retranslateFields
    ? new Set(args.retranslateFields.split(",").map((field) => field.trim()).filter(Boolean))
    : undefined;

  writeCliStdout(`\nGenerating ${languages.length} language(s)...`);
  if (args.dryRun) {
    const cacheDirs = get_all_cache_dirs();
    writeCliStdout(`  Existing cache dirs: ${cacheDirs.length ? cacheDirs.join(", ") : "none"}\n`);
    for (const code of languages) {
      const [, name] = SUPPORTED_LANGUAGES[code] ?? [code, code];
      const cached = load_cached(code);
      const status = cached ? "cached" : "would generate";
      const fieldCount = Object.keys(cached?.fields ?? {}).length;
      writeCliStdout(`  [${code}] ${name}: ${status} (${fieldCount} fields)`);
    }
    writeCliStdout("\nDone.");
    return 0;
  }

  writeCliStdout(`  Cache dir: ${get_cache_dir()}\n`);
  const failures: Array<[string, string]> = [];
  let nextLanguage = 0;
  const workerCount = boundedWorkers(args.workers, languages.length);
  async function runWorker(): Promise<void> {
    while (nextLanguage < languages.length) {
      const code = languages[nextLanguage] as string;
      nextLanguage += 1;
    try {
      const data = await generateLanguageAsync(code, {
        force: args.force,
        force_fields,
        timeout: args.timeout,
        retries: args.retries,
        retry_backoff: args.retry_backoff,
      });
      const fieldCount = Object.keys(data.fields ?? {}).length;
      const aliasCount = Object.values(data.fields ?? {}).reduce((total, aliases) => total + aliases.length, 0);
      writeCliStdout(`  [${code}] ${data.language_name}: ${fieldCount} fields, ${aliasCount} aliases`);
    } catch (error) {
      failures.push([code, (error as Error).message]);
      writeCliStdout(`  [${code}] FAILED: ${(error as Error).message}`);
    }
  }
  }
  await Promise.all(Array.from({ length: workerCount }, () => runWorker()));
  if (failures.length > 0) {
    writeCliStdout(`\nFailed ${failures.length} language(s):`);
    for (const [code, error] of failures) {
      writeCliStdout(`  [${code}] ${error}`);
    }
    return 1;
  }
  writeCliStdout("\nDone.");
  return 0;
}

export function main(): Promise<number> {
  if (arguments.length > 0) {
    throw new TypeError(`main() takes 0 positional arguments but ${arguments.length} ${arguments.length === 1 ? "was" : "were"} given`);
  }
  installBrokenPipeHandler();
  return mainWithArgs();
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  installBrokenPipeHandler();
  mainWithArgs()
    .then((code) => {
      process.exitCode = code;
    })
    .catch((error: unknown) => {
      const message = (error as Error).message;
      if (message.startsWith("usage:")) {
        writeCliStdout(message);
        process.exitCode = 0;
      } else if (error instanceof I18nUsageError) {
        writeCliStderr(`${usageLine()}\n${I18N_PROG}: error: ${message}`);
        process.exitCode = error.exitCode;
      } else {
        writeCliStdout(`ERROR: ${message}`);
        process.exitCode = 1;
      }
    });
}
