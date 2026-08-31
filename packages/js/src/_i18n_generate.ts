// Generating a language pack: translation, budgets, cache writes.
// Extracted verbatim from index.ts, which re-exports every public name here.

import { spawnSync } from "node:child_process";
import { mkdirSync, renameSync, unlinkSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { SUPPORTED_LANGUAGES, loadCachedLanguage, userI18nCacheDir } from "./_i18n_cache.js";
import type { AsyncTranslateFunction, GenerateLanguageAsyncOptions, GenerateLanguageOptions, InternalGenerateLanguageOptions, LanguageData, PatternData, TranslateFunction } from "./_models.js";
import { assertPythonOptionsKeys, isPlainObject, pyRepr, pythonMissingRequiredArg, pythonPositionalTypeError, valueError } from "./_pycompat.js";
import { loadDefaultPatterns } from "./_registry.js";
import { moduleUrl, require } from "./_runtime.js";
let unidecode: ((value: string) => string) | undefined;

const I18N_SKIP_FIELDS = new Set([
  "created_at",
  "updated_at",
  "last_contacted",
  "utm_parameters",
  "metadata",
  "score",
  "owner",
  "tags",
  "lead_status",
  "lifecycle_stage",
  "email_opt_out",
  "currency",
  "source",
  "referrer_url",
  "timezone",
  "discord",
  "telegram",
]);

function asciiFold(text: string): string | undefined {
  const stripped = text.normalize("NFKD").replace(/\p{Diacritic}/gu, "").trim();
  if (stripped && stripped !== text) {
    return stripped;
  }
  try {
    unidecode ??= require("unidecode") as (value: string) => string;
  } catch {
    return undefined;
  }
  const folded = unidecode(text).trim();
  return folded && folded !== text ? folded : undefined;
}

function aliasVariants(text: string): Set<string> {
  const variants = new Set<string>();
  const low = text.toLowerCase().trim();
  if (low.length < 2) {
    return variants;
  }
  variants.add(low);
  variants.add(low.replace(/\s+/g, "_"));
  const concat = low.replace(/[\s_-]+/g, "");
  if (concat.length > 1) {
    variants.add(concat);
  }
  const hyphenated = low.replace(/\s+/g, "-");
  if (hyphenated !== low) {
    variants.add(hyphenated);
  }
  const folded = asciiFold(low);
  if (folded) {
    variants.add(folded);
    variants.add(folded.replace(/\s+/g, "_"));
    const foldedConcat = folded.replace(/[\s_-]+/g, "");
    if (foldedConcat.length > 1) {
      variants.add(foldedConcat);
    }
  }
  return new Set([...variants].filter((variant) => variant.length > 1));
}

function deriveFieldPhrases(master: PatternData): Record<string, string> {
  const phrases: Record<string, string> = {};
  for (const canonical of Object.keys(master.fields ?? {})) {
    if (!I18N_SKIP_FIELDS.has(canonical)) {
      phrases[canonical] = canonical.replace(/_/g, " ");
    }
  }
  return phrases;
}

function englishAliases(master: PatternData): Set<string> {
  const aliases = new Set<string>();
  for (const values of Object.values(master.fields ?? {})) {
    for (const alias of values) {
      aliases.add(alias.toLowerCase().trim());
    }
  }
  return aliases;
}

function normalizeForceFields(options: Pick<GenerateLanguageOptions, "force_fields">): Set<string> {
  const raw = options.force_fields ?? [];
  return raw instanceof Set ? new Set(raw) : new Set(raw);
}

async function defaultTranslate(
  phrase: string,
  languageCode: string,
  options: { timeout: number; signal?: AbortSignal },
): Promise<string> {
  const { translate } = await import("@vitalets/google-translate-api");
  const result = await translate(phrase, {
    from: "en",
    to: languageCode,
    fetchOptions: options.signal ? { signal: options.signal } : undefined,
  });
  return result.text;
}

async function translateWithBudget(
  phrase: string,
  languageCode: string,
  translator: AsyncTranslateFunction,
  options: { timeout: number; retries: number; retry_backoff: number },
): Promise<string | undefined> {
  const attempts = Math.max(0, options.retries) + 1;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), Math.max(0, options.timeout) * 1000);
    try {
      const translated = await translator(phrase, languageCode, {
        timeout: options.timeout,
        signal: controller.signal,
      });
      const text = typeof translated === "string" ? translated : translated.text;
      return text?.trim() || undefined;
    } catch (error) {
      if (attempt >= attempts) {
        return undefined;
      }
      const backoffMs = Math.max(0, options.retry_backoff) * attempt * 1000;
      if (backoffMs > 0) {
        await new Promise((resolve) => setTimeout(resolve, backoffMs));
      }
    } finally {
      clearTimeout(timer);
    }
  }
  return undefined;
}

function sleepSync(ms: number): void {
  if (ms <= 0) {
    return;
  }
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function isPromiseLike(value: unknown): value is Promise<unknown> {
  return !!value && (typeof value === "object" || typeof value === "function") && typeof (value as { then?: unknown }).then === "function";
}

function translationText(value: string | { text?: string } | undefined): string | undefined {
  const text = typeof value === "string" ? value : value?.text;
  return text?.trim() || undefined;
}

function translateWithBudgetSync(
  phrase: string,
  languageCode: string,
  translator: TranslateFunction,
  options: { timeout: number; retries: number; retry_backoff: number },
): string | undefined {
  const attempts = Math.max(0, options.retries) + 1;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      const translated = translator(phrase, languageCode, { timeout: options.timeout });
      if (isPromiseLike(translated)) {
        throw new TypeError("generate_language translator must be synchronous; use generateLanguageAsync for Promise-returning translators");
      }
      return translationText(translated);
    } catch (error) {
      if (attempt >= attempts) {
        if (error instanceof TypeError && /must be synchronous/.test(error.message)) {
          throw error;
        }
        return undefined;
      }
      sleepSync(Math.max(0, options.retry_backoff) * attempt * 1000);
    }
  }
  return undefined;
}

function writeLanguageCache(langData: LanguageData, cacheDir?: string): string {
  const targetDir = cacheDir ?? userI18nCacheDir();
  mkdirSync(targetDir, { recursive: true });
  const langCode = langData.language_code;
  if (!langCode) {
    throw new Error("language cache data must include language_code");
  }
  const path = join(targetDir, `${langCode}.json`);
  const temp = join(targetDir, `.${langCode}.${process.pid}.${Date.now()}.tmp`);
  try {
    writeFileSync(temp, `${JSON.stringify(langData, null, 2)}\n`, "utf8");
    renameSync(temp, path);
  } catch (error) {
    try {
      unlinkSync(temp);
    } catch {
      // Best effort cleanup.
    }
    throw error;
  }
  return path;
}

function warnNoTranslations(langCode: string): void {
  console.warn(`No translations produced for ${langCode}; skipping cache write so a future run can retry.`);
}

function unsupportedLanguageError(langCode: string): Error {
  const supported = `[${Object.keys(SUPPORTED_LANGUAGES).sort().map(pyRepr).join(", ")}]`;
  return valueError(`Unsupported language: ${pyRepr(langCode)}. Supported: ${supported}`);
}

async function generateLanguageData(langCode: string, options: GenerateLanguageAsyncOptions): Promise<LanguageData> {
  const [translateCode, langName] = SUPPORTED_LANGUAGES[langCode] ?? [];
  if (!translateCode || !langName) {
    throw unsupportedLanguageError(langCode);
  }
  const cacheDir = options.cache_dir;
  const forceFields = normalizeForceFields(options);
  const existing = options.force ? undefined : loadCachedLanguage(langCode, { cache_dir: cacheDir });
  const master = loadDefaultPatterns();
  const phrases = deriveFieldPhrases(master);
  const english = englishAliases(master);
  const existingFields = existing?.fields ?? {};
  const allCanonicals = new Set(Object.keys(phrases));
  const toTranslate = Object.keys(phrases).filter((canonical) => (
    options.force || !(canonical in existingFields) || forceFields.has(canonical)
  ));
  const timeout = options.timeout ?? 10;
  const retries = options.retries ?? 1;
  const retryBackoff = options.retry_backoff ?? 0.5;
  const translator = options.translator ?? defaultTranslate;
  const newTranslations: Record<string, string[]> = {};

  for (const canonical of toTranslate.sort()) {
    const translated = await translateWithBudget(phrases[canonical] ?? canonical, translateCode, translator, {
      timeout,
      retries,
      retry_backoff: retryBackoff,
    });
    if (!translated) {
      continue;
    }
    const filtered = [...aliasVariants(translated)]
      .filter((variant) => !english.has(variant) && variant.length > 1)
      .sort();
    if (filtered.length > 0) {
      newTranslations[canonical] = filtered;
    }
  }

  const merged: Record<string, string[]> = {};
  for (const [canonical, aliases] of Object.entries(existingFields)) {
    if (allCanonicals.has(canonical)) {
      merged[canonical] = aliases;
    }
  }
  Object.assign(merged, newTranslations);

  const langData: LanguageData = {
    language_code: langCode,
    language_name: langName,
    generated_at: new Date().toISOString().replace("Z", "+00:00"),
    source_version: master.version ?? "unknown",
    fields: merged,
  };

  if (Object.keys(merged).length > 0 || existing) {
    writeLanguageCache(langData, cacheDir);
  } else {
    warnNoTranslations(langCode);
  }
  return langData;
}

function generateLanguageDataSync(langCode: string, options: InternalGenerateLanguageOptions): LanguageData {
  const [translateCode, langName] = SUPPORTED_LANGUAGES[langCode] ?? [];
  if (!translateCode || !langName) {
    throw unsupportedLanguageError(langCode);
  }
  if (!options.translator) {
    return generateLanguageDataInSubprocess(langCode, options);
  }

  const cacheDir = options.cache_dir;
  const forceFields = normalizeForceFields(options);
  const existing = options.force ? undefined : loadCachedLanguage(langCode, { cache_dir: cacheDir });
  const master = loadDefaultPatterns();
  const phrases = deriveFieldPhrases(master);
  const english = englishAliases(master);
  const existingFields = existing?.fields ?? {};
  const allCanonicals = new Set(Object.keys(phrases));
  const toTranslate = Object.keys(phrases).filter((canonical) => (
    options.force || !(canonical in existingFields) || forceFields.has(canonical)
  ));
  const timeout = options.timeout ?? 10;
  const retries = options.retries ?? 1;
  const retryBackoff = options.retry_backoff ?? 0.5;
  const newTranslations: Record<string, string[]> = {};

  for (const canonical of toTranslate.sort()) {
    const translated = translateWithBudgetSync(phrases[canonical] ?? canonical, translateCode, options.translator, {
      timeout,
      retries,
      retry_backoff: retryBackoff,
    });
    if (!translated) {
      continue;
    }
    const filtered = [...aliasVariants(translated)]
      .filter((variant) => !english.has(variant) && variant.length > 1)
      .sort();
    if (filtered.length > 0) {
      newTranslations[canonical] = filtered;
    }
  }

  const merged: Record<string, string[]> = {};
  for (const [canonical, aliases] of Object.entries(existingFields)) {
    if (allCanonicals.has(canonical)) {
      merged[canonical] = aliases;
    }
  }
  Object.assign(merged, newTranslations);

  const langData: LanguageData = {
    language_code: langCode,
    language_name: langName,
    generated_at: new Date().toISOString().replace("Z", "+00:00"),
    source_version: master.version ?? "unknown",
    fields: merged,
  };

  if (Object.keys(merged).length > 0 || existing) {
    writeLanguageCache(langData, cacheDir);
  } else {
    warnNoTranslations(langCode);
  }
  return langData;
}

function generateLanguageDataInSubprocess(langCode: string, options: InternalGenerateLanguageOptions): LanguageData {
  const forceFields = [...normalizeForceFields(options)];
  const payload = {
    force: options.force ?? false,
    force_fields: forceFields,
    timeout: options.timeout,
    retries: options.retries,
    retry_backoff: options.retry_backoff,
    cache_dir: options.cache_dir,
  };
  const script = `
const moduleUrl = ${JSON.stringify(moduleUrl)};
const langCode = ${JSON.stringify(langCode)};
const options = JSON.parse(process.argv[1] ?? "{}");
if (Array.isArray(options.force_fields)) options.force_fields = new Set(options.force_fields);
const mod = await import(moduleUrl);
const api = mod.generateLanguageAsync ? mod : mod.default;
const data = await api.generateLanguageAsync(langCode, options);
process.stdout.write(JSON.stringify(data));
`;
  const result = spawnSync(process.execPath, ["--input-type=module", "-e", script, JSON.stringify(payload)], {
    encoding: "utf8",
    maxBuffer: 50 * 1024 * 1024,
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error((result.stderr || result.stdout || `i18n generation failed with exit ${result.status}`).trim());
  }
  try {
    return JSON.parse(result.stdout) as LanguageData;
  } catch (error) {
    throw new Error(`i18n generation returned invalid JSON: ${(error as Error).message}`);
  }
}

/** @internal */
export async function generateLanguageAsync(langCode: string, options: GenerateLanguageAsyncOptions = {}): Promise<LanguageData> {
  if (!(langCode in SUPPORTED_LANGUAGES)) {
    throw unsupportedLanguageError(langCode);
  }
  const forceFields = normalizeForceFields(options);
  const cacheDir = options.cache_dir;
  if (!options.force && forceFields.size === 0) {
    const cached = loadCachedLanguage(langCode, { cache_dir: cacheDir });
    if (cached) {
      return cached;
    }
  }
  return generateLanguageData(langCode, options);
}

/** @internal */
export function generateLanguage(langCode: string, options: InternalGenerateLanguageOptions = {}): LanguageData {
  if (!(langCode in SUPPORTED_LANGUAGES)) {
    throw unsupportedLanguageError(langCode);
  }
  const forceFields = normalizeForceFields(options);
  const cacheDir = options.cache_dir;
  if (!options.force && forceFields.size === 0) {
    const cached = loadCachedLanguage(langCode, { cache_dir: cacheDir });
    if (cached) {
      return cached;
    }
  }
  return generateLanguageDataSync(langCode, options);
}

const GENERATE_LANGUAGE_OPTION_KEYS = new Set(["force", "force_fields", "timeout", "retries", "retry_backoff"]);

export function generate_language(langCode: string, options: GenerateLanguageOptions = {}): LanguageData {
  if (arguments.length < 1) {
    throw pythonMissingRequiredArg("generate_language", "lang_code");
  }
  if (arguments.length > 2 || (arguments.length === 2 && !isPlainObject(options))) {
    throw pythonPositionalTypeError("generate_language", 1, arguments.length);
  }
  assertPythonOptionsKeys("generate_language", options as Record<string, unknown>, GENERATE_LANGUAGE_OPTION_KEYS);
  return generateLanguage(langCode, options);
}
