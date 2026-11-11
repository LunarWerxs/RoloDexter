// Generating a language pack: translation, budgets, cache writes.
// Extracted verbatim from index.ts, which re-exports every public name here.

import { spawnSync } from "node:child_process";
import { mkdirSync, renameSync, unlinkSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { pathToFileURL } from "node:url";
import { SUPPORTED_LANGUAGES, loadCachedLanguage, userI18nCacheDir } from "./_i18n_cache.js";
import type { AsyncTranslateFunction, GenerateLanguageAsyncOptions, GenerateLanguageOptions, InternalGenerateLanguageOptions, LanguageData, PatternData, TranslateFunction } from "./_models.js";
import { assertPythonOptionsKeys, isPlainObject, pyRepr, pythonMissingRequiredArg, pythonPositionalTypeError, pythonRangePositionalTypeError, valueError } from "./_pycompat.js";
import { loadDefaultPatterns } from "./_registry.js";
import { require } from "./_runtime.js";
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

/** @internal The canonical fields a language pack translates (all but I18N_SKIP_FIELDS). */
export function translatableFields(): Set<string> {
  return new Set(Object.keys(deriveFieldPhrases(loadDefaultPatterns())));
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
        throw new TypeError("generate_language translator must be synchronous; use generateLanguageAsync (exported from rolodexter/i18n) for Promise-returning translators");
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

/** A generated pack; `failed_fields` lists the fields whose translation failed (M12). */
type GeneratedLanguageData = LanguageData & { failed_fields?: string[] };

interface GenerationPlan {
  langCode: string;
  langName: string;
  translateCode: string;
  cacheDir: string | undefined;
  existing: GeneratedLanguageData | undefined;
  phrases: Record<string, string>;
  english: Set<string>;
  sourceVersion: string;
  toTranslate: string[];
}

function planGeneration(langCode: string, options: InternalGenerateLanguageOptions | GenerateLanguageAsyncOptions): GenerationPlan {
  const [translateCode, langName] = SUPPORTED_LANGUAGES[langCode] ?? [];
  if (!translateCode || !langName) {
    throw unsupportedLanguageError(langCode);
  }
  const cacheDir = options.cache_dir;
  const forceFields = normalizeForceFields(options);
  const existing: GeneratedLanguageData | undefined = options.force
    ? undefined
    : loadCachedLanguage(langCode, { cache_dir: cacheDir });
  const master = loadDefaultPatterns();
  const phrases = deriveFieldPhrases(master);
  const existingFields = existing?.fields ?? {};
  const previouslyFailed = new Set(existing?.failed_fields ?? []);
  const toTranslate = Object.keys(phrases).filter((canonical) => (
    options.force || !(canonical in existingFields) || forceFields.has(canonical) || previouslyFailed.has(canonical)
  )).sort();
  return {
    langCode,
    langName,
    translateCode,
    cacheDir,
    existing,
    phrases,
    english: englishAliases(master),
    sourceVersion: master.version ?? "unknown",
    toTranslate,
  };
}

function novelVariants(translated: string, english: Set<string>): string[] {
  return [...aliasVariants(translated)]
    .filter((variant) => !english.has(variant) && variant.length > 1)
    .sort();
}

function translationBudget(options: GenerateLanguageOptions): { timeout: number; retries: number; retry_backoff: number } {
  return {
    timeout: options.timeout ?? 10,
    retries: options.retries ?? 1,
    retry_backoff: options.retry_backoff ?? 0.5,
  };
}

/**
 * Merge new translations over the cached pack and write it. A field whose
 * translation failed is listed in `failed_fields`, so the pack is not taken
 * for complete: the next generate call retries exactly those fields (M12).
 */
function finishGeneration(plan: GenerationPlan, newTranslations: Record<string, string[]>, failed: string[]): GeneratedLanguageData {
  const merged: Record<string, string[]> = {};
  for (const [canonical, aliases] of Object.entries(plan.existing?.fields ?? {})) {
    if (Object.hasOwn(plan.phrases, canonical)) {
      merged[canonical] = aliases;
    }
  }
  Object.assign(merged, newTranslations);

  const langData: GeneratedLanguageData = {
    language_code: plan.langCode,
    language_name: plan.langName,
    generated_at: new Date().toISOString().replace("Z", "+00:00"),
    source_version: plan.sourceVersion,
    fields: merged,
  };
  if (failed.length > 0) {
    langData.failed_fields = [...failed].sort();
  }

  if (Object.keys(merged).length > 0 || plan.existing) {
    writeLanguageCache(langData, plan.cacheDir);
  } else {
    warnNoTranslations(plan.langCode);
  }
  return langData;
}

async function generateLanguageData(langCode: string, options: GenerateLanguageAsyncOptions): Promise<LanguageData> {
  const plan = planGeneration(langCode, options);
  const budget = translationBudget(options);
  const translator = options.translator ?? defaultTranslate;
  const newTranslations: Record<string, string[]> = {};
  const failed: string[] = [];

  for (const canonical of plan.toTranslate) {
    const translated = await translateWithBudget(plan.phrases[canonical] ?? canonical, plan.translateCode, translator, budget);
    if (!translated) {
      failed.push(canonical);
      continue;
    }
    const filtered = novelVariants(translated, plan.english);
    if (filtered.length > 0) {
      newTranslations[canonical] = filtered;
    }
  }
  return finishGeneration(plan, newTranslations, failed);
}

function generateLanguageDataSync(langCode: string, options: InternalGenerateLanguageOptions): LanguageData {
  const plan = planGeneration(langCode, options);
  if (!options.translator) {
    return generateLanguageDataInSubprocess(plan, options);
  }
  const budget = translationBudget(options);
  const newTranslations: Record<string, string[]> = {};
  const failed: string[] = [];

  for (const canonical of plan.toTranslate) {
    const translated = translateWithBudgetSync(plan.phrases[canonical] ?? canonical, plan.translateCode, options.translator, budget);
    if (!translated) {
      failed.push(canonical);
      continue;
    }
    const filtered = novelVariants(translated, plan.english);
    if (filtered.length > 0) {
      newTranslations[canonical] = filtered;
    }
  }
  return finishGeneration(plan, newTranslations, failed);
}

// The module the helper process imports must be the one that really exports
// generateLanguageAsync (H7): this file's own address under ESM. The esbuild
// CommonJS bundles are single files whose import.meta is empty, so
// build-cjs.mjs also builds this module as a bundle of its own and defines
// __ROLODEXTER_CJS_GENERATOR__ as that bundle's file name, a sibling of
// whichever bundle is running.
declare const __ROLODEXTER_CJS_GENERATOR__: string | undefined;
const generatorModuleUrl = typeof __filename !== "undefined" && typeof __ROLODEXTER_CJS_GENERATOR__ === "string"
  ? pathToFileURL(join(dirname(__filename), __ROLODEXTER_CJS_GENERATOR__)).href
  : import.meta.url;

const HELPER_STARTUP_SECONDS = 30;

/**
 * Seconds the helper process may run (M12): every phrase may use every
 * attempt's timeout and backoff, plus a fixed allowance for Node start-up.
 * Undefined (no limit) when the caller chose an infinite request timeout.
 */
function helperTimeoutSeconds(phraseCount: number, options: GenerateLanguageOptions): number | undefined {
  const { timeout, retries, retry_backoff: backoff } = translationBudget(options);
  const attempts = Math.max(0, retries) + 1;
  const perPhrase = attempts * Math.max(0, timeout) + (Math.max(0, backoff) * attempts * (attempts - 1)) / 2;
  const total = phraseCount * perPhrase + HELPER_STARTUP_SECONDS;
  return Number.isFinite(total) ? total : undefined;
}

function generateLanguageDataInSubprocess(plan: GenerationPlan, options: InternalGenerateLanguageOptions): LanguageData {
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
const generatorUrl = ${JSON.stringify(generatorModuleUrl)};
const langCode = ${JSON.stringify(plan.langCode)};
const options = JSON.parse(process.argv[1] ?? "{}");
if (Array.isArray(options.force_fields)) options.force_fields = new Set(options.force_fields);
const mod = await import(generatorUrl);
const api = typeof mod.generateLanguageAsync === "function" ? mod : mod.default;
const data = await api.generateLanguageAsync(langCode, options);
process.stdout.write(JSON.stringify(data));
`;
  const timeoutSeconds = helperTimeoutSeconds(plan.toTranslate.length, options);
  const result = spawnSync(process.execPath, ["--input-type=module", "-e", script, JSON.stringify(payload)], {
    encoding: "utf8",
    maxBuffer: 50 * 1024 * 1024,
    timeout: timeoutSeconds === undefined ? undefined : Math.ceil(timeoutSeconds * 1000),
  });
  if ((result.error as NodeJS.ErrnoException | undefined)?.code === "ETIMEDOUT") {
    throw new Error(
      `generate_language(${pyRepr(plan.langCode)}) timed out after ${Math.ceil(timeoutSeconds ?? 0)} seconds `
        + "and its helper process was stopped; the language pack was not updated.",
    );
  }
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
  // hasOwn rather than `in`, for the reason spelled out on
  // normalizeLanguageCode: `in` accepts inherited members, so
  // "constructor" reached the generator as a supported language.
  if (!Object.hasOwn(SUPPORTED_LANGUAGES, langCode)) {
    throw unsupportedLanguageError(langCode);
  }
  const forceFields = normalizeForceFields(options);
  const cacheDir = options.cache_dir;
  if (!options.force && forceFields.size === 0) {
    const cached: GeneratedLanguageData | undefined = loadCachedLanguage(langCode, { cache_dir: cacheDir });
    if (cached && !cached.failed_fields?.length) {
      return cached;
    }
  }
  return generateLanguageData(langCode, options);
}

/** @internal */
export function generateLanguage(langCode: string, options: InternalGenerateLanguageOptions = {}): LanguageData {
  // hasOwn rather than `in`, for the reason spelled out on
  // normalizeLanguageCode: `in` accepts inherited members, so
  // "constructor" reached the generator as a supported language.
  if (!Object.hasOwn(SUPPORTED_LANGUAGES, langCode)) {
    throw unsupportedLanguageError(langCode);
  }
  const forceFields = normalizeForceFields(options);
  const cacheDir = options.cache_dir;
  if (!options.force && forceFields.size === 0) {
    const cached: GeneratedLanguageData | undefined = loadCachedLanguage(langCode, { cache_dir: cacheDir });
    if (cached && !cached.failed_fields?.length) {
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
  if (arguments.length > 2) {
    throw pythonRangePositionalTypeError("generate_language", 1, 2, arguments.length);
  }
  if (arguments.length === 2 && !isPlainObject(options)) {
    throw pythonPositionalTypeError("generate_language", 1, arguments.length);
  }
  assertPythonOptionsKeys("generate_language", options as Record<string, unknown>, GENERATE_LANGUAGE_OPTION_KEYS);
  return generateLanguage(langCode, options);
}
