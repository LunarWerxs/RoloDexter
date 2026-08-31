// Pattern loading, validation, and the alias registry.
// Extracted verbatim from index.ts, which re-exports every public name here.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { SUPPORTED_LANGUAGES, discoverCachedLanguages, loadCachedLanguage } from "./_i18n_cache.js";
import { PatternLoadError, normalizeAlias } from "./_models.js";
import type { PatternData, PatternRegistryOptions } from "./_models.js";
import { assertPythonOptionsKeys, isPlainObject, pyRepr, pythonLiteral, pythonTypeName } from "./_pycompat.js";
import { moduleUrl } from "./_runtime.js";

function isPatternRegistryOptions(value: unknown): value is PatternRegistryOptions {
  return isPlainObject(value) &&
    ("patterns" in value || "patterns_path" in value || "languages" in value || "overrides" in value) &&
    !("fields" in value);
}

function validatePatternData(data: unknown, source: string): PatternData {
  const fail = (detail: string): never => {
    throw new PatternLoadError(`Invalid ${source}: ${detail}`);
  };
  const validateStringArray = (value: unknown, name: string): void => {
    if (
      !Array.isArray(value) ||
      value.some((item) => typeof item !== "string" || item.trim().length === 0)
    ) {
      fail(`${name} must be a list of non-empty strings`);
    }
  };

  if (!isPlainObject(data)) {
    fail("top level must be an object");
  }
  const root = data as Record<string, unknown>;
  if (root.version !== undefined && typeof root.version !== "string") {
    fail("'version' must be a string");
  }

  const fields = root.fields === undefined ? {} : root.fields;
  if (!isPlainObject(fields)) {
    fail("'fields' must be an object");
  }
  const fieldRecord = fields as Record<string, unknown>;
  for (const [canonical, aliases] of Object.entries(fieldRecord)) {
    if (!canonical.trim()) {
      fail("field names must be non-empty strings");
    }
    validateStringArray(aliases, `aliases for field ${pyRepr(canonical)}`);
  }

  const expansion = root.expansion;
  if (expansion != null) {
    if (!isPlainObject(expansion)) {
      fail("'expansion' must be an object");
    }
    const expansionRecord = expansion as Record<string, unknown>;
    for (const key of ["form_prefixes", "social_suffixes", "social_fields"]) {
      if (expansionRecord[key] !== undefined) {
        validateStringArray(expansionRecord[key], `'expansion.${key}'`);
      }
    }
    const formFields = expansionRecord.form_fields;
    if (formFields !== undefined) {
      if (
        !isPlainObject(formFields) ||
        Object.entries(formFields).some(
          ([key, value]) =>
            !key.trim() || typeof value !== "string" || !value.trim(),
        )
      ) {
        fail(
          "'expansion.form_fields' must be an object of non-empty string keys and values",
        );
      }
    }
  }

  return root as PatternData;
}

function loadDefaultPatterns(): PatternData {
  let data: unknown;
  try {
    const path = fileURLToPath(new URL("./patterns.json", moduleUrl));
    data = JSON.parse(readFileSync(path, "utf8")) as unknown;
  } catch (error) {
    throw new PatternLoadError(`Failed to load bundled patterns: ${String(error)}`);
  }
  return validatePatternData(data, "bundled patterns");
}

function loadPatternFile(path: string): PatternData {
  let data: unknown;
  try {
    data = JSON.parse(readFileSync(path, "utf8")) as unknown;
  } catch (error) {
    throw new PatternLoadError(`Failed to load patterns from ${path}: ${String(error)}`);
  }
  return validatePatternData(data, `patterns file ${pyRepr(path)}`);
}

const PATTERN_REGISTRY_OPTION_KEYS = new Set(["patterns", "patterns_path", "languages", "overrides"]);

export class PatternRegistry {
  #data: PatternData;
  #reverseIndex = new Map<string, string>();
  #aliasSet = new Set<string>();
  #aliases: string[] = [];
  #fields: string[] = [];
  #loadedLanguageCodes: string[] = [];
  #languages: string | string[] | null | undefined;

  constructor();
  constructor(options: PatternRegistryOptions);
  constructor(
    patterns: PatternData | null,
    patterns_path?: string | null,
    languages?: string | string[] | null,
    overrides?: Record<string, string> | null,
  );
  constructor(
    patternsOrOptions: PatternData | PatternRegistryOptions | null = null,
    patternsPathArg?: string | null,
    languagesArg?: string | string[] | null,
    overridesArg?: Record<string, string> | null,
  ) {
    if (arguments.length > 4) {
      throw new TypeError(`PatternRegistry.__init__() takes from 1 to 5 positional arguments but ${arguments.length + 1} were given`);
    }
    const options = arguments.length === 1 && isPatternRegistryOptions(patternsOrOptions)
      ? patternsOrOptions
      : {
          patterns: patternsOrOptions as PatternData | null,
          patterns_path: patternsPathArg,
          languages: languagesArg,
          overrides: overridesArg,
        };
    if (arguments.length === 1 && isPatternRegistryOptions(patternsOrOptions)) {
      assertPythonOptionsKeys("PatternRegistry.__init__", options as Record<string, unknown>, PATTERN_REGISTRY_OPTION_KEYS);
    }
    const patternsPath = options.patterns_path;
    const patterns = options.patterns;
    this.#data = patterns != null
      ? validatePatternData(patterns, "custom patterns")
      : patternsPath
        ? loadPatternFile(patternsPath)
        : loadDefaultPatterns();
    this.#languages = options.languages;
    this.#buildIndexes();
    this.#applyOverrides(options.overrides ?? undefined);
  }

  exact_lookup(header: string): string | null {
    return this.#reverseIndex.get(normalizeAlias(header)) ?? null;
  }

  get all_aliases(): string[] {
    return [...this.#aliases];
  }

  get canonical_fields(): string[] {
    return [...this.#fields];
  }

  get loaded_languages(): string[] {
    return [...this.#loadedLanguageCodes];
  }

  get available_languages(): string[] {
    return Object.keys(SUPPORTED_LANGUAGES).sort();
  }

  get cached_languages(): string[] {
    return Object.keys(discoverCachedLanguages()).sort();
  }

  get version(): string {
    return this.#data.version ?? "0.0.0";
  }

  toString(): string {
    return `PatternRegistry(aliases=${this.#reverseIndex.size}, languages=${pythonLiteral(this.#loadedLanguageCodes)}, version=${pyRepr(this.version)})`;
  }

  #addAlias(alias: string, canonical: string): void {
    const key = normalizeAlias(alias);
    if (!this.#reverseIndex.has(key)) {
      this.#reverseIndex.set(key, canonical);
    }
    if (!this.#aliasSet.has(key)) {
      this.#aliasSet.add(key);
      this.#aliases.push(key);
    }
  }

  #buildIndexes(): void {
    for (const [canonical, aliases] of Object.entries(this.#data.fields ?? {})) {
      this.#fields.push(canonical);
      for (const alias of aliases) {
        this.#addAlias(alias, canonical);
      }
    }
    this.#applyExpansionRules();
    this.#applyLanguageAliases();
  }

  #applyExpansionRules(): void {
    const expansion = this.#data.expansion;
    if (!expansion) {
      return;
    }

    for (const prefix of expansion.form_prefixes ?? []) {
      for (const [suffix, canonical] of Object.entries(expansion.form_fields ?? {})) {
        this.#addAlias(`${prefix}${suffix}`, canonical);
      }
    }

    for (const platform of expansion.social_fields ?? []) {
      for (const suffix of expansion.social_suffixes ?? []) {
        this.#addAlias(`${platform}${suffix}`, platform);
      }
    }
  }

  #applyLanguageAliases(): void {
    let langCodes: string[] = [];
    if (this.#languages === "all") {
      langCodes = Object.keys(SUPPORTED_LANGUAGES).sort();
    } else if (Array.isArray(this.#languages)) {
      langCodes = this.#languages;
    } else if (typeof this.#languages === "string") {
      langCodes = [this.#languages];
    } else if (this.#languages) {
      const iterable = this.#languages as Iterable<string>;
      if (typeof iterable[Symbol.iterator] !== "function") {
        throw new TypeError(`'${pythonTypeName(this.#languages)}' object is not iterable`);
      }
      langCodes = [...iterable];
    }

    for (const langCode of langCodes) {
      const langData = loadCachedLanguage(langCode);
      if (!langData) {
        continue;
      }
      this.#loadedLanguageCodes.push(langCode);
      for (const [canonical, aliases] of Object.entries(langData.fields ?? {})) {
        for (const alias of aliases) {
          this.#addAlias(alias, canonical);
        }
      }
    }
  }

  #applyOverrides(overrides?: Record<string, string>): void {
    if (!overrides) {
      return;
    }
    if (!isPlainObject(overrides)) {
      throw new PatternLoadError("Invalid overrides: expected an object");
    }
    for (const [alias, canonical] of Object.entries(overrides)) {
      if (!alias.trim() || typeof canonical !== "string" || !canonical.trim()) {
        throw new PatternLoadError(
          "Invalid overrides: aliases and canonical fields must be non-empty strings",
        );
      }
      const key = normalizeAlias(alias);
      this.#reverseIndex.set(key, canonical);
      if (!this.#aliasSet.has(key)) {
        this.#aliasSet.add(key);
        this.#aliases.push(key);
      }
    }
  }
}


// File-private in index.ts; exported here only because the split put
// their callers in another module. Not part of the package's public API -
// ./public.ts and ./core.ts still decide that.
export { loadDefaultPatterns };
