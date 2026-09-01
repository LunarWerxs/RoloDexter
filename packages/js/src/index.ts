// Everything below was extracted into the sibling modules named here.
// index.ts imports what it still uses and re-exports exactly what it used to
// export, so ./public.ts, ./core.ts, ./cli.ts and ./i18n.ts see no change.
import { dataframeColumnValues, dataframeColumns, flatten, isDataFrameLike, iterableColumnValues, mappedColumnValues, setDataframeColumn } from "./_dataframe.js";
import { CANONICAL_FIELD_MEMBERS, CanonicalField, EXACT_MATCH_CONFIDENCE, FieldMatch, NormalizationError, PHONE_FIELDS, PatternLoadError, fieldMatch, isMatched, mergeValue, unknown, valueForMatching } from "./_models.js";
import type { CanonicalFieldMember, CompileSchemaOptions, DataFrameLike, MapDataFrameOptions, MapPayloadOptions, ProfileOptions } from "./_models.js";
import { normalizeValue, valueWarnings } from "./_normalizers.js";
import { extractEmbeddedPhones } from "./_phone.js";
import { assertMappingPayload, assertPythonMethodOptions, assertPythonOptionsKeys, attributeError, emitRolodexterWarning, emitRolodexterWarnings, isPlainObject, lockPythonFrozenFields, pyRepr, pyString, pythonPositionalTypeError, pythonTypeName, pyStrip, setOwnProperty, validateConfidenceThreshold, valueError } from "./_pycompat.js";
import { PatternRegistry } from "./_registry.js";
import { MappingProfile, MappingResult, makeMappingMatches } from "./_results.js";
import type { MappingMatches } from "./_results.js";
import { ExactMatchStrategy, FuzzyMatchStrategy, HeuristicMatchStrategy, MatchStrategy, NormalizedMatchStrategy, isHeaderOnlyStrategy } from "./_strategies.js";
import type { ContactMapperOptions } from "./_strategies.js";

export { SUPPORTED_LANGUAGES, discoverCachedLanguages, discover_cached, getAllCacheDirs, getCacheDir, getWritableCacheDir, get_all_cache_dirs, get_cache_dir, get_writable_cache_dir, loadCachedLanguage, load_cached, normalizeLanguageCode } from "./_i18n_cache.js";
export { generateLanguage, generateLanguageAsync, generate_language } from "./_i18n_generate.js";
export { CanonicalField, EXACT_MATCH_CONFIDENCE, FUZZY_HIGH_CONFIDENCE, FUZZY_LENGTH_RATIO, FUZZY_LOW_CONFIDENCE, FUZZY_MATCH_THRESHOLD, FieldMatch, HEURISTIC_CONFIDENCE, NORMALIZED_MATCH_CONFIDENCE, NormalizationError, PatternLoadError, RolodexterError } from "./_models.js";
export type { AsyncTranslateFunction, CanonicalFieldValue, CompileSchemaOptions, DataFrameLike, GenerateLanguageOptions, LanguageData, MapDataFrameOptions, MapPayloadOptions, PatternData, ProfileOptions, TranslateFunction } from "./_models.js";
export { AddressNormalizer, BooleanNormalizer, EmailNormalizer, ListNormalizer, NameNormalizer, PhoneNormalizer, PostalCodeNormalizer, StringNormalizer, normalizeValue, normalize_value } from "./_normalizers.js";
export { EMBEDDED_PHONE_MAX_MATCHES_PER_FIELD, EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD, EMBEDDED_PHONE_MAX_TEXT_CHARS, MatchType, NumberType, PhoneNumber, PhoneNumberMatch, PhoneNumberMatcher, format_e164, format_international, format_national, is_number_match, is_valid, number_type, parse } from "./_phone.js";
export { PatternRegistry } from "./_registry.js";
export { MappingProfile, MappingResult } from "./_results.js";
export { ExactMatchStrategy, FuzzyMatchStrategy, HeuristicMatchStrategy, MatchStrategy, NormalizedMatchStrategy } from "./_strategies.js";
export type { ContactMapperOptions, MatchOptions } from "./_strategies.js";
export const DEFAULT_HEADER_CACHE_MAX_SIZE = 4096;

Object.defineProperty(CanonicalField, Symbol.iterator, {
  value: function* iterCanonicalFields(): IterableIterator<CanonicalFieldMember> {
    yield* Object.values(CANONICAL_FIELD_MEMBERS);
  },
});
Object.freeze(CanonicalField);

export class MappingSchema {
  readonly matches: MappingMatches;
  readonly default_region: string | null | undefined;
  readonly mapper: ContactMapper;

  constructor(matches: Record<string, FieldMatch>, mapper: ContactMapper, default_region?: string | null) {
    if (arguments.length === 0) {
      throw new TypeError("MappingSchema.__init__() missing 2 required positional arguments: 'matches' and 'mapper'");
    }
    if (arguments.length === 1) {
      throw new TypeError("MappingSchema.__init__() missing 1 required positional argument: 'mapper'");
    }
    if (arguments.length > 3) {
      throw new TypeError(`MappingSchema.__init__() takes from 3 to 4 positional arguments but ${arguments.length + 1} were given`);
    }
    this.matches = makeMappingMatches(matches);
    this.mapper = mapper;
    this.default_region = default_region;
    lockPythonFrozenFields(this, ["matches", "mapper", "default_region"]);
  }

  column_map(): Record<string, string> {
    const out: Record<string, string> = {};
    for (const [header, match] of this.matches.entries()) {
      if (isMatched(match)) {
        setOwnProperty(out, header, match.canonical);
      }
    }
    return out;
  }

  unmatched_headers(): string[] {
    return [...this.matches.entries()]
      .filter(([, match]) => !isMatched(match))
      .map(([header]) => header);
  }

  apply(row: Record<string, unknown>, options: MapPayloadOptions = {}): MappingResult {
    assertPythonMethodOptions("MappingSchema.apply", "row", arguments.length, options);
    assertPythonOptionsKeys("ContactMapper.map_payload", options, MAP_PAYLOAD_OPTION_KEYS);
    const default_region = options.default_region !== undefined
        ? options.default_region
        : this.default_region;
    return this.mapper.map_payload(row, {
      ...options,
      default_region,
    });
  }

  static readonly SCHEMA_VERSION = 1;

  /**
   * Return a JSON-serializable mapping plan (a "mapping lockfile").
   *
   * Load it back with from_dict to get byte-identical column routing on every
   * later run, including after a patterns.json update that would otherwise
   * resolve a header differently.
   */
  to_dict(): Record<string, unknown> {
    const columns: Record<string, unknown> = {};
    for (const [header, match] of this.matches.entries()) {
      setOwnProperty(columns, header, {
        canonical: match.canonical,
        confidence: match.confidence,
        strategy: match.strategy,
        service: match.service ?? null,
      });
    }
    return {
      schema_version: MappingSchema.SCHEMA_VERSION,
      default_region: this.default_region ?? null,
      columns,
    };
  }

  /**
   * Rebuild a plan saved by to_dict and bind it to `mapper`.
   *
   * The restored verdicts are seeded into the mapper's header cache, so later
   * map_payload calls route columns exactly as the saved plan says rather than
   * re-resolving them. Headers the plan records as `unknown` are skipped, so
   * per-row value heuristics can still match them.
   */
  static from_dict(
    data: Record<string, unknown>,
    mapper: ContactMapper,
    options: { default_region?: string | null } = {},
  ): MappingSchema {
    if (data === null || typeof data !== "object" || Array.isArray(data)) {
      throw new PatternLoadError("Invalid mapping schema: expected an object");
    }
    const version = (data as { schema_version?: unknown }).schema_version;
    if (version !== MappingSchema.SCHEMA_VERSION) {
      throw new PatternLoadError(
        `Unsupported mapping schema version ${pyRepr(version)}; this rolodexter reads version ${MappingSchema.SCHEMA_VERSION}`,
      );
    }
    const columns = (data as { columns?: unknown }).columns;
    if (columns === null || typeof columns !== "object" || Array.isArray(columns)) {
      throw new PatternLoadError("Invalid mapping schema: 'columns' must be an object");
    }

    const matches: Record<string, FieldMatch> = {};
    for (const [header, rawEntry] of Object.entries(columns as Record<string, unknown>)) {
      if (rawEntry === null || typeof rawEntry !== "object" || Array.isArray(rawEntry)) {
        throw new PatternLoadError(
          "Invalid mapping schema: each column must map a string header to an object",
        );
      }
      const entry = rawEntry as Record<string, unknown>;
      const canonical = entry.canonical;
      const strategy = entry.strategy ?? "schema";
      const confidence = entry.confidence ?? EXACT_MATCH_CONFIDENCE;
      const service = entry.service;
      if (typeof canonical !== "string" || !pyStrip(canonical)) {
        throw new PatternLoadError(
          `Invalid mapping schema: column ${pyRepr(header)} has no canonical field`,
        );
      }
      if (typeof strategy !== "string" || typeof confidence !== "number") {
        throw new PatternLoadError(
          `Invalid mapping schema: column ${pyRepr(header)} has a malformed strategy or confidence`,
        );
      }
      setOwnProperty(matches, header, fieldMatch(
        header,
        canonical,
        confidence,
        strategy,
        typeof service === "string" ? service : null,
      ));
    }

    let region = options.default_region;
    if (region === undefined) {
      const stored = (data as { default_region?: unknown }).default_region;
      region = typeof stored === "string" ? stored : null;
    }

    mapper.seed_header_cache(matches);
    return new MappingSchema(matches, mapper, region);
  }
}

const CONTACT_MAPPER_OPTION_KEYS = new Set([
  "patterns",
  "patterns_path",
  "default_service",
  "normalize",
  "strategies",
  "languages",
  "overrides",
  "default_region",
  "strict",
  "confidence_threshold",
  "header_cache_max_size",
]);

const IDENTIFY_OPTION_KEYS = new Set(["value", "service", "default_region"]);
const MAP_PAYLOAD_OPTION_KEYS = new Set(["depth", "service", "default_region", "extract_embedded_phones", "strict", "confidence_threshold"]);
const PROFILE_OPTION_KEYS = new Set(["max_rows", "depth", "default_region", "extract_embedded_phones", "strict", "confidence_threshold"]);
const COMPILE_SCHEMA_OPTION_KEYS = new Set(["default_region", "strict", "confidence_threshold"]);
const MAP_DATAFRAME_OPTION_KEYS = new Set(["default_region", "normalize", "strict", "confidence_threshold"]);

export class ContactMapper {
  #registry: PatternRegistry;
  #normalize: boolean;
  #defaultRegion: string | null;
  #strict: boolean;
  #confidenceThreshold: number;
  #headerCacheMaxSize: number | null;
  #strategies: MatchStrategy[];
  #headerStrategies: MatchStrategy[];
  #valueStrategies: MatchStrategy[];
  #cacheablePipeline: boolean;
  #headerCache = new Map<string, FieldMatch | undefined>();

  constructor(options: ContactMapperOptions = {}) {
    if (arguments.length > 1 || (arguments.length === 1 && options !== undefined && !isPlainObject(options))) {
      throw pythonPositionalTypeError("ContactMapper.__init__", 1, arguments.length + 1);
    }
    const opts = options ?? {};
    assertPythonOptionsKeys("ContactMapper.__init__", opts as Record<string, unknown>, CONTACT_MAPPER_OPTION_KEYS);
    this.#registry = new PatternRegistry({
      patterns: opts.patterns,
      patterns_path: opts.patterns_path,
      languages: opts.languages,
      overrides: opts.overrides,
    });
    this.#normalize = opts.normalize ?? true;
    const defaultRegion = opts.default_region;
    this.#defaultRegion = defaultRegion === undefined ? "US" : defaultRegion;
    this.#strict = opts.strict ?? false;
    this.#confidenceThreshold = validateConfidenceThreshold(opts.confidence_threshold ?? 0);
    const headerCacheMaxSize = opts.header_cache_max_size;
    if (headerCacheMaxSize != null && typeof headerCacheMaxSize !== "number") {
      throw new TypeError(`'<' not supported between instances of '${pythonTypeName(headerCacheMaxSize)}' and 'int'`);
    }
    this.#headerCacheMaxSize = headerCacheMaxSize === undefined ? DEFAULT_HEADER_CACHE_MAX_SIZE : headerCacheMaxSize;
    if (this.#headerCacheMaxSize !== null && this.#headerCacheMaxSize < 0) {
      throw valueError("header_cache_max_size must be non-negative or None");
    }
    this.#strategies = opts.strategies
      ? [...opts.strategies]
      : [
          new ExactMatchStrategy(this.#registry),
          new NormalizedMatchStrategy(this.#registry),
          new FuzzyMatchStrategy(this.#registry),
          new HeuristicMatchStrategy(this.#defaultRegion),
        ];

    let seenValueDependent = false;
    let cacheablePipeline = true;
    for (const strategy of this.#strategies) {
      if (isHeaderOnlyStrategy(strategy)) {
        if (seenValueDependent) {
          cacheablePipeline = false;
          break;
        }
      } else {
        seenValueDependent = true;
      }
    }
    this.#cacheablePipeline = cacheablePipeline;
    this.#headerStrategies = this.#strategies.filter(isHeaderOnlyStrategy);
    this.#valueStrategies = this.#strategies.filter((strategy) => !isHeaderOnlyStrategy(strategy));
  }

  get registry(): PatternRegistry {
    return this.#registry;
  }

  identify(header: string, options: { value?: string; service?: string | null; default_region?: string | null } = {}): FieldMatch {
    assertPythonMethodOptions("ContactMapper.identify", "header", arguments.length, options);
    assertPythonOptionsKeys("ContactMapper.identify", options, IDENTIFY_OPTION_KEYS);
    const opts = options ?? {};
    const region = opts.default_region ?? this.#defaultRegion;
    for (const strategy of this.#strategies) {
      const result = strategy.match(header, opts.value ?? null, {
        default_region: region,
      });
      if (result) {
        return result;
      }
    }
    return unknown(header);
  }

  /** Resolve, normalize, and record one `key`/`value` entry of a payload during `map_payload`, mutating the accumulators in place. */
  #mapField(
    key: string,
    value: unknown,
    region: string | null,
    threshold: number,
    normalizeValues: boolean,
    normalized: Record<string, unknown>,
    unmapped: Record<string, unknown>,
    fieldMatches: FieldMatch[],
    warnings: string[],
  ): void {
    let match = this.#resolve(key, value, region);

    if (isMatched(match) && match.confidence < threshold) {
      warnings.push(
        `${pyRepr(key)}: dropped low-confidence match to ${pyRepr(match.canonical)} (confidence ${match.confidence.toFixed(2)} < threshold ${threshold.toFixed(2)})`,
      );
      match = unknown(key);
    }

    fieldMatches.push(match);

    if (!isMatched(match)) {
      setOwnProperty(unmapped, key, value);
      return;
    }

    const finalValue = normalizeValues ? normalizeValue(match.canonical, value, region) : value;
    if (
      PHONE_FIELDS.has(match.canonical) &&
      typeof finalValue === "string" &&
      pyStrip(finalValue) &&
      !finalValue.startsWith("+")
    ) {
      warnings.push(
        `${pyRepr(key)}: phone value ${pyRepr(finalValue)} could not be normalized to E.164 (set a matching default_region?)`,
      );
    }
    // Surface silent degradation beyond phones too: an "email" that is not
    // shaped like one, or a date whose day/month order cannot be known.
    if (!PHONE_FIELDS.has(match.canonical)) {
      warnings.push(...valueWarnings(key, match.canonical, finalValue));
    }
    mergeValue(normalized, match.canonical, finalValue);
  }

  map_payload(payload: Record<string, unknown>, options: MapPayloadOptions = {}): MappingResult {
    assertPythonMethodOptions("ContactMapper.map_payload", "payload", arguments.length, options);
    assertPythonOptionsKeys("ContactMapper.map_payload", options, MAP_PAYLOAD_OPTION_KEYS);
    assertMappingPayload(payload);
    const opts = options ?? {};
    if (Object.prototype.hasOwnProperty.call(opts, "normalize")) {
      throw new TypeError("ContactMapper.map_payload() got an unexpected keyword argument 'normalize'");
    }
    const depth = Math.max(1, Math.min(opts.depth ?? 1, 5));
    const flat = depth > 1 ? flatten(payload, depth) : payload;
    const regionOption = opts.default_region;
    const region = regionOption === undefined || regionOption === null ? this.#defaultRegion : regionOption;
    const threshold = validateConfidenceThreshold(opts.confidence_threshold ?? this.#confidenceThreshold);
    const isStrict = opts.strict ?? this.#strict;
    const normalizeValues = this.#normalize;
    const shouldExtractEmbeddedPhones = opts.extract_embedded_phones ?? false;

    const normalized: Record<string, unknown> = {};
    const unmapped: Record<string, unknown> = {};
    const fieldMatches: FieldMatch[] = [];
    const warnings: string[] = [];

    for (const [key, value] of Object.entries(flat)) {
      this.#mapField(key, value, region, threshold, normalizeValues, normalized, unmapped, fieldMatches, warnings);
    }

    if (shouldExtractEmbeddedPhones) {
      extractEmbeddedPhones(normalized, unmapped, fieldMatches, warnings, region);
    }

    if (warnings.length > 0) {
      emitRolodexterWarnings(warnings);
      if (isStrict) {
        throw new NormalizationError(warnings.join("; "));
      }
    }

    return new MappingResult(normalized, unmapped, fieldMatches, warnings);
  }

  map_batch(payloads: Iterable<Record<string, unknown>>, options: MapPayloadOptions = {}): MappingResult[] {
    assertPythonMethodOptions("ContactMapper.map_batch", "payloads", arguments.length, options);
    assertPythonOptionsKeys("ContactMapper.map_batch", options, MAP_PAYLOAD_OPTION_KEYS);
    return [...this.map_stream(payloads, options)];
  }

  map_stream(payloads: Iterable<Record<string, unknown>>, options: MapPayloadOptions = {}): Generator<MappingResult> {
    assertPythonMethodOptions("ContactMapper.map_stream", "payloads", arguments.length, options);
    assertPythonOptionsKeys("ContactMapper.map_stream", options, MAP_PAYLOAD_OPTION_KEYS);
    return this.#mapStream(payloads, options);
  }

  *#mapStream(payloads: Iterable<Record<string, unknown>>, options: MapPayloadOptions = {}): Generator<MappingResult> {
    for (const payload of payloads) {
      yield this.map_payload(payload, options);
    }
  }

  profile(payloads: Iterable<Record<string, unknown>>, options: ProfileOptions = {}): MappingProfile {
    assertPythonMethodOptions("ContactMapper.profile", "payloads", arguments.length, options);
    assertPythonOptionsKeys("ContactMapper.profile", options, PROFILE_OPTION_KEYS);
    const opts = options ?? {};
    const maxRows = opts.max_rows;
    if (
      maxRows != null &&
      (typeof maxRows !== "number" || !Number.isInteger(maxRows))
    ) {
      throw new TypeError("max_rows must be an integer or None");
    }
    if (maxRows != null && maxRows < 0) {
      throw valueError("max_rows must be non-negative or None");
    }

    const canonicalCounts = new Map<string, number>();
    const unmappedCounts = new Map<string, number>();
    const strategyCounts = new Map<string, number>();
    const warningCounts = new Map<string, number>();
    const increment = (counts: Map<string, number>, key: string): void => {
      counts.set(key, (counts.get(key) ?? 0) + 1);
    };
    let rowsSeen = 0;
    let matchedCount = 0;
    let unmatchedCount = 0;
    const iterator = payloads[Symbol.iterator]();

    while (maxRows === null || maxRows === undefined || rowsSeen < maxRows) {
      const next = iterator.next();
      if (next.done) {
        break;
      }
      const result = this.map_payload(next.value, {
        depth: opts.depth,
        default_region: opts.default_region,
        extract_embedded_phones: opts.extract_embedded_phones,
        strict: opts.strict,
        confidence_threshold: opts.confidence_threshold,
      });
      rowsSeen += 1;
      for (const match of result.field_matches) {
        increment(strategyCounts, match.strategy);
        if (isMatched(match)) {
          matchedCount += 1;
          increment(canonicalCounts, match.canonical);
        } else {
          unmatchedCount += 1;
          increment(unmappedCounts, match.original);
        }
      }
      for (const warning of result.warnings) {
        let category = "other";
        if (warning.includes("dropped low-confidence match")) {
          category = "low_confidence";
        } else if (warning.includes("could not be normalized to E.164")) {
          category = "phone_normalization";
        } else if (warning.includes("embedded phone")) {
          category = "embedded_phone_limit";
        }
        increment(warningCounts, category);
      }
    }

    return new MappingProfile(
      rowsSeen,
      matchedCount + unmatchedCount,
      matchedCount,
      unmatchedCount,
      Object.fromEntries(canonicalCounts),
      Object.fromEntries(unmappedCounts),
      Object.fromEntries(strategyCounts),
      Object.fromEntries(warningCounts),
    );
  }

  compile_schema(headers: Iterable<unknown>, options: CompileSchemaOptions = {}): MappingSchema {
    assertPythonMethodOptions("ContactMapper.compile_schema", "headers", arguments.length, options);
    assertPythonOptionsKeys("ContactMapper.compile_schema", options, COMPILE_SCHEMA_OPTION_KEYS);
    const opts = options ?? {};
    const regionOption = opts.default_region;
    const region = regionOption === undefined || regionOption === null ? this.#defaultRegion : regionOption;
    const threshold = validateConfidenceThreshold(opts.confidence_threshold ?? this.#confidenceThreshold);
    const isStrict = opts.strict ?? this.#strict;
    const matches = new Map<string, FieldMatch>();
    const warnings: string[] = [];

    for (const header of headers) {
      const key = pyString(header);
      let match = this.#resolve(key, undefined, region);
      if (isMatched(match) && match.confidence < threshold) {
        warnings.push(
          `${pyRepr(key)}: dropped low-confidence match to ${pyRepr(match.canonical)} (confidence ${match.confidence.toFixed(2)} < threshold ${threshold.toFixed(2)})`,
        );
        match = unknown(key);
      }
      matches.set(key, match);
    }

    if (warnings.length > 0) {
      emitRolodexterWarnings(warnings);
      if (isStrict) {
        throw new NormalizationError(warnings.join("; "));
      }
    }

    return new MappingSchema(Object.fromEntries(matches), this, region);
  }

  /** Build the collision-free output-column rename plan for `map_dataframe`, warning on any collision. */
  #buildDataframeRenamePlan(columns: string[], schema: MappingSchema): Map<string, string> {
    const rename = new Map<string, string>();
    const usedNames = new Set(
      columns.filter((column) => {
        const match = schema.matches.get(column);
        return !match || !isMatched(match);
      }),
    );
    const nextSuffix = new Map<string, number>();
    for (const column of columns) {
      const match = schema.matches.get(column);
      if (!match || !isMatched(match)) {
        continue;
      }
      let suffix = nextSuffix.get(match.canonical) ?? 1;
      let newName = suffix === 1 ? match.canonical : `${match.canonical}__${suffix}`;
      while (usedNames.has(newName)) {
        suffix += 1;
        newName = `${match.canonical}__${suffix}`;
      }
      nextSuffix.set(match.canonical, suffix + 1);
      usedNames.add(newName);
      if (newName !== match.canonical) {
        emitRolodexterWarning(
          `map_dataframe: column ${pyRepr(column)} also maps to ${pyRepr(match.canonical)}; renamed to ${pyRepr(newName)} to avoid a collision`,
        );
      }
      rename.set(column, newName);
    }
    return rename;
  }

  /** Normalize the renamed output columns in place for `map_dataframe`, pushing any phone-normalization warnings. */
  #normalizeDataframeColumns(out: DataFrameLike, rename: Map<string, string>, region: string | null, warnings: string[]): void {
    for (const [oldName, newName] of rename) {
      const canonical = newName.split("__", 1)[0] ?? newName;
      const values = dataframeColumnValues(out, newName);
      const mapped = mappedColumnValues(values, (value) => normalizeValue(canonical, value, region));
      if (mapped === undefined) {
        continue;
      }
      setDataframeColumn(out, newName, mapped);
      if (PHONE_FIELDS.has(canonical)) {
        for (const finalValue of iterableColumnValues(mapped)) {
          if (
            typeof finalValue === "string" &&
            pyStrip(finalValue) &&
            !finalValue.startsWith("+")
          ) {
            warnings.push(
              `${pyRepr(oldName)}: phone value ${pyRepr(finalValue)} could not be normalized to E.164 (set a matching default_region?)`,
            );
          }
        }
      }
    }
  }

  map_dataframe(rows: DataFrameLike, options: MapDataFrameOptions = {}): unknown {
    assertPythonMethodOptions("ContactMapper.map_dataframe", "df", arguments.length, options);
    assertPythonOptionsKeys("ContactMapper.map_dataframe", options, MAP_DATAFRAME_OPTION_KEYS);
    const opts = options ?? {};
    const region = opts.default_region ?? this.#defaultRegion;
    const normalizeValues = opts.normalize === null || opts.normalize === undefined ? this.#normalize : opts.normalize;
    const isStrict = opts.strict === null || opts.strict === undefined ? this.#strict : opts.strict;
    const thresholdOption = opts.confidence_threshold;
    const threshold = validateConfidenceThreshold(thresholdOption === null || thresholdOption === undefined ? this.#confidenceThreshold : thresholdOption);
    const columns: string[] = [];
    if (Array.isArray(rows)) {
      throw attributeError("'list' object has no attribute 'columns'");
    } else if (isDataFrameLike(rows)) {
      columns.push(...dataframeColumns(rows));
    } else {
      throw new TypeError("map_dataframe expects an array of row objects or a DataFrame-like object with columns and rename()");
    }

    const schema = this.compile_schema(columns, {
      default_region: region,
      strict: isStrict,
      confidence_threshold: threshold,
    });
    if (new Set(columns).size !== columns.length) {
      throw valueError(
        "map_dataframe requires unique input column labels; duplicate labels cannot be renamed without ambiguity",
      );
    }
    const rename = this.#buildDataframeRenamePlan(columns, schema);

    const warnings: string[] = [];
    if (isDataFrameLike(rows)) {
      const renameRecord = Object.fromEntries(rename);
      const renamed = rows.rename({ columns: renameRecord }) ?? rows.rename(renameRecord);
      const out = (renamed ?? rows) as DataFrameLike;
      if (normalizeValues) {
        this.#normalizeDataframeColumns(out, rename, region, warnings);
      }
      if (warnings.length > 0) {
        emitRolodexterWarnings(warnings);
        if (isStrict) {
          throw new NormalizationError(warnings.join("; "));
        }
      }
      return out;
    }

    throw attributeError("'list' object has no attribute 'columns'");
  }

  /**
   * Pre-load header verdicts so a replayed plan wins over live resolution.
   *
   * Entries whose canonical field is `unknown` are skipped rather than cached
   * as a miss, so a column the plan could not resolve statically can still be
   * matched from its value by the per-row heuristics.
   */
  seed_header_cache(matches: Record<string, FieldMatch>): void {
    for (const [header, match] of Object.entries(matches)) {
      if (match.canonical === "unknown") {
        continue;
      }
      this.#headerCache.delete(header);
      this.#headerCache.set(header, match);
    }
    if (this.#headerCacheMaxSize !== null) {
      while (this.#headerCache.size > this.#headerCacheMaxSize) {
        const oldest = this.#headerCache.keys().next();
        if (oldest.done) {
          break;
        }
        this.#headerCache.delete(oldest.value);
      }
    }
  }

  clear_cache(): void {
    if (arguments.length > 0) {
      throw pythonPositionalTypeError("ContactMapper.clear_cache", 1, arguments.length + 1);
    }
    this.#headerCache.clear();
  }

  cache_info(): { size: number; max_size: number | null; cacheable_pipeline: boolean } {
    if (arguments.length > 0) {
      throw pythonPositionalTypeError("ContactMapper.cache_info", 1, arguments.length + 1);
    }
    return {
      size: this.#headerCache.size,
      max_size: this.#headerCacheMaxSize,
      cacheable_pipeline: this.#cacheablePipeline,
    };
  }

  #resolve(header: string, value: unknown, region: string | null | undefined): FieldMatch {
    if (!this.#cacheablePipeline) {
      return this.identify(header, {
        value: valueForMatching(value),
        default_region: region,
      });
    }

    if (this.#headerCache.has(header)) {
      const cached = this.#headerCache.get(header);
      this.#headerCache.delete(header);
      this.#headerCache.set(header, cached);
      if (cached) {
        return cached;
      }
    } else {
      let headerOnlyMatch: FieldMatch | undefined;
      for (const strategy of this.#headerStrategies) {
        const result = strategy.match(header, null, {
          default_region: region,
        });
        if (result) {
          headerOnlyMatch = result;
          break;
        }
      }
      if (this.#headerCacheMaxSize !== 0) {
        this.#headerCache.set(header, headerOnlyMatch);
        if (this.#headerCacheMaxSize !== null) {
          while (this.#headerCache.size > this.#headerCacheMaxSize) {
            const oldest = this.#headerCache.keys().next().value as string | undefined;
            if (oldest === undefined) {
              break;
            }
            this.#headerCache.delete(oldest);
          }
        }
      }
      if (headerOnlyMatch) {
        return headerOnlyMatch;
      }
    }

    const matchValue = valueForMatching(value);
    for (const strategy of this.#valueStrategies) {
      const result = strategy.match(header, matchValue, {
        default_region: region,
      });
      if (result) {
        return result;
      }
    }
    return unknown(header);
  }
}

export const __all__ = [
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
] as const;

// Kept in step with packages/js/package.json by
// scripts/check_release_versions.py, which the publish workflows run before
// building. This literal silently shipped 2.10.0 inside the 2.11.0 package
// because nothing compared the two.
export const version = "2.11.1";
export const __version__ = version;
