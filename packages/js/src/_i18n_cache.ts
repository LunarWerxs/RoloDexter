// Language cache locations, loading and schema validation.
// Extracted verbatim from index.ts, which re-exports every public name here.

import { existsSync, mkdirSync, readFileSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import type { LanguageData } from "./_models.js";
import { pythonMissingRequiredArg, pythonPositionalTypeError } from "./_pycompat.js";
import { moduleUrl } from "./_runtime.js";

export const SUPPORTED_LANGUAGES: Record<string, readonly [string, string]> = Object.freeze({
  es: ["es", "Spanish"],
  fr: ["fr", "French"],
  de: ["de", "German"],
  pt: ["pt", "Portuguese"],
  it: ["it", "Italian"],
  nl: ["nl", "Dutch"],
  pl: ["pl", "Polish"],
  ro: ["ro", "Romanian"],
  tr: ["tr", "Turkish"],
  ru: ["ru", "Russian"],
  ja: ["ja", "Japanese"],
  zh: ["zh-CN", "Chinese (Simplified)"],
  ko: ["ko", "Korean"],
  ar: ["ar", "Arabic"],
  hi: ["hi", "Hindi"],
  sv: ["sv", "Swedish"],
  da: ["da", "Danish"],
  nb: ["no", "Norwegian"],
  fi: ["fi", "Finnish"],
  cs: ["cs", "Czech"],
  uk: ["uk", "Ukrainian"],
  el: ["el", "Greek"],
  hu: ["hu", "Hungarian"],
  th: ["th", "Thai"],
  vi: ["vi", "Vietnamese"],
  id: ["id", "Indonesian"],
  ms: ["ms", "Malay"],
  he: ["iw", "Hebrew"],
  bg: ["bg", "Bulgarian"],
  hr: ["hr", "Croatian"],
  sk: ["sk", "Slovak"],
  sl: ["sl", "Slovenian"],
  sr: ["sr", "Serbian"],
  lt: ["lt", "Lithuanian"],
  lv: ["lv", "Latvian"],
  et: ["et", "Estonian"],
  ca: ["ca", "Catalan"],
  tl: ["tl", "Filipino"],
  sw: ["sw", "Swahili"],
  af: ["af", "Afrikaans"],
});

function packageI18nDir(): string | undefined {
  const pythonPathSep = process.platform === "win32" ? ";" : ":";
  for (const entry of (process.env.PYTHONPATH ?? "").split(pythonPathSep)) {
    if (!entry) {
      continue;
    }
    const pythonSourceCache = join(entry, "rolodexter", "i18n");
    if (existsSync(pythonSourceCache)) {
      return pythonSourceCache;
    }
  }
  const path = fileURLToPath(new URL("./i18n", moduleUrl));
  return existsSync(path) ? path : undefined;
}

function userI18nCacheDir(): string {
  let base: string;
  if (process.platform === "win32") {
    base = process.env.LOCALAPPDATA ?? join(homedir(), "AppData", "Local");
  } else if (process.platform === "darwin") {
    base = join(homedir(), "Library", "Caches");
  } else {
    base = process.env.XDG_CACHE_HOME ?? join(homedir(), ".cache");
  }
  return join(base, "rolodexter", "i18n");
}

/** @internal */
export function getWritableCacheDir(): string {
  const dir = userI18nCacheDir();
  mkdirSync(dir, { recursive: true });
  return dir;
}

export function get_writable_cache_dir(): string {
  if (arguments.length > 0) {
    throw pythonPositionalTypeError("get_writable_cache_dir", 0, arguments.length);
  }
  return getWritableCacheDir();
}

/** @internal */
export function getCacheDir(): string {
  return getWritableCacheDir();
}

export function get_cache_dir(): string {
  if (arguments.length > 0) {
    throw pythonPositionalTypeError("get_cache_dir", 0, arguments.length);
  }
  return getCacheDir();
}

/** @internal */
export function getAllCacheDirs(options: { cache_dir?: string } = {}): string[] {
  const dirs: string[] = [];
  const pkgDir = packageI18nDir();
  if (pkgDir) {
    dirs.push(pkgDir);
  }
  const extraDir = options.cache_dir;
  if (extraDir && existsSync(extraDir) && !dirs.includes(extraDir)) {
    dirs.push(extraDir);
  }
  const userDir = userI18nCacheDir();
  if (existsSync(userDir) && !dirs.includes(userDir)) {
    dirs.push(userDir);
  }
  return dirs;
}

export function get_all_cache_dirs(): string[] {
  if (arguments.length > 0) {
    throw pythonPositionalTypeError("get_all_cache_dirs", 0, arguments.length);
  }
  return getAllCacheDirs();
}

/**
 * Canonical SUPPORTED_LANGUAGES key for `langCode`, or undefined.
 *
 * Accepts any case ("ES" -> "es") and surrounding whitespace. Every path that
 * turns a caller-supplied string into a cache *filename* must go through here
 * first: `langCode` arrives from `new ContactMapper({languages})` and the CLI's
 * --languages flag, so an unvalidated value would let a relative path
 * ("../../secrets") escape the cache directory and have its contents merged
 * into the alias index, which decides where every column is routed.
 */
export function normalizeLanguageCode(langCode: unknown): string | undefined {
  if (typeof langCode !== "string") {
    return undefined;
  }
  const candidate = langCode.trim().toLowerCase();
  return candidate in SUPPORTED_LANGUAGES ? candidate : undefined;
}

/**
 * Shape check for a generated i18n cache file.
 *
 * The cache directory is user-writable and its contents decide routing, so a
 * truncated, hand-edited or foreign file must be skipped rather than trusted.
 * Validating alias types here also stops a non-string entry throwing out of
 * ContactMapper construction.
 */
function validateCacheSchema(data: unknown): LanguageData | undefined {
  if (data === null || typeof data !== "object" || Array.isArray(data)) {
    return undefined;
  }
  const record = data as Record<string, unknown>;
  for (const key of ["language_code", "language_name", "fields"]) {
    if (!(key in record)) {
      return undefined;
    }
  }
  const fields = record.fields;
  if (fields === null || typeof fields !== "object" || Array.isArray(fields)) {
    return undefined;
  }
  for (const [canonical, aliases] of Object.entries(fields as Record<string, unknown>)) {
    if (!canonical.trim()) {
      return undefined;
    }
    if (!Array.isArray(aliases) || aliases.some((alias) => typeof alias !== "string" || !alias.trim())) {
      return undefined;
    }
  }
  return data as LanguageData;
}

/** @internal */
export function loadCachedLanguage(langCode: string, options: { cache_dir?: string } = {}): LanguageData | undefined {
  const code = normalizeLanguageCode(langCode);
  if (code === undefined) {
    return undefined;
  }
  for (const dir of getAllCacheDirs(options)) {
    const path = join(dir, `${code}.json`);
    if (!existsSync(path)) {
      continue;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(readFileSync(path, "utf8"));
    } catch {
      continue;
    }
    const validated = validateCacheSchema(parsed);
    if (validated !== undefined) {
      return validated;
    }
  }
  return undefined;
}

/** @internal */
export function discoverCachedLanguages(options: { cache_dir?: string } = {}): Record<string, string> {
  const found: Record<string, string> = {};
  for (const dir of getAllCacheDirs(options)) {
    if (!existsSync(dir)) {
      continue;
    }
    for (const item of readdirSync(dir)) {
      if (!item.endsWith(".json")) {
        continue;
      }
      const langCode = normalizeLanguageCode(item.slice(0, -5));
      if (langCode === undefined) {
        continue;
      }
      found[langCode] ??= join(dir, item);
    }
  }
  return found;
}

export function load_cached(lang_code: string): LanguageData | null {
  if (arguments.length < 1) {
    throw pythonMissingRequiredArg("load_cached", "lang_code");
  }
  if (arguments.length > 1) {
    throw pythonPositionalTypeError("load_cached", 1, arguments.length);
  }
  return loadCachedLanguage(lang_code) ?? null;
}

export function discover_cached(): Record<string, string> {
  if (arguments.length > 0) {
    throw pythonPositionalTypeError("discover_cached", 0, arguments.length);
  }
  return discoverCachedLanguages();
}


// File-private in index.ts; exported here only because the split put
// their callers in another module. Not part of the package's public API -
// ./public.ts and ./core.ts still decide that.
export { userI18nCacheDir };
