// Header match strategies: exact, normalized, fuzzy, heuristic.
// Extracted verbatim from index.ts, which re-exports every public name here.

import { extract as fuzzyExtract, partial_ratio as fuzzyPartialRatio, ratio as fuzzyRatio } from "fuzzball";
import { ADDRESS_PREFIXES, COMPANY_PREFIXES, EXACT_MATCH_CONFIDENCE, FUZZY_HIGH_CONFIDENCE, FUZZY_LENGTH_RATIO, FUZZY_LOW_CONFIDENCE, FUZZY_MATCH_THRESHOLD, FieldMatch, HEURISTIC_CONFIDENCE, NORMALIZED_MATCH_CONFIDENCE, PHONE_FIELDS, SOCIAL_FIELDS, VENDOR_PREFIXES, fieldMatch } from "./_models.js";
import type { PatternData } from "./_models.js";
import { isPossiblePhone } from "./_phone.js";
import { PatternRegistry } from "./_registry.js";

export interface ContactMapperOptions {
  patterns?: PatternData;
  patterns_path?: string;
  normalize?: boolean;
  overrides?: Record<string, string>;
  languages?: string | string[] | null;
  default_region?: string | null;
  default_service?: string | null;
  strict?: boolean;
  confidence_threshold?: number;
  strategies?: MatchStrategy[];
  header_cache_max_size?: number | null;
}

function splitCamel(value: string): string {
  return value
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1_$2");
}

function underscore(value: string): string {
  return value
    .replace(/[\s-]+/g, "_")
    .toLowerCase()
    .replace(/[^\w]/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
}

// Fields that hold a contactable value rather than a reference to a record.
// A header like "primary_phone_id" names a foreign key, so the _id-suffix
// stripping below must not route it to `phone` -- that stores an internal ID
// as the contact's number at 0.95 confidence, where no threshold catches it.
function valueBearingFields(): Set<string> {
  return new Set([...PHONE_FIELDS, ...SOCIAL_FIELDS, "email"]);
}

const VALUE_BEARING_FIELDS = valueBearingFields();

// Suffixes marking a header as naming a reference rather than holding a value.
// An explicit alias in patterns.json still wins: the truth table is allowed to
// say that a given export's "<platform>_id" really is the handle.
const REFERENCE_SUFFIX_RE = /_(?:id|ids|uuid|guid|key|ref|fk)$/;

function isReferenceHeader(header: string): boolean {
  return REFERENCE_SUFFIX_RE.test(underscore(splitCamel(header)));
}

function isValueBearing(registry: PatternRegistry, candidate: string): boolean {
  const canonical = registry.exact_lookup(candidate);
  return Boolean(canonical) && VALUE_BEARING_FIELDS.has(canonical as string);
}

/** Push the dot-segment ("Company.Name") derived candidates for header `h` onto `out`. */
function pushDotSuffixCandidates(h: string, out: string[]): void {
  if (!h.includes(".")) {
    return;
  }
  const dot = h.lastIndexOf(".");
  const prefixRaw = h.slice(0, dot).toLowerCase().trim();
  const suffixRaw = h.slice(dot + 1).trim();
  const suffixLower = suffixRaw.replace(/[\s-]+/g, "_").toLowerCase();
  const lastPrefix = prefixRaw.slice(prefixRaw.lastIndexOf(".") + 1);
  if (COMPANY_PREFIXES.has(lastPrefix) && ["name", "nombre"].includes(suffixLower)) {
    out.unshift("company");
  }
  if (suffixLower) {
    out.push(suffixLower);
  }
  if (/[A-Z]/.test(suffixRaw.slice(1))) {
    const snakeSuffix = splitCamel(suffixRaw).toLowerCase().replace(/_+/g, "_").replace(/^_+|_+$/g, "");
    if (snakeSuffix && snakeSuffix !== suffixLower) {
      out.push(snakeSuffix);
    }
  }
}

/** Push the indexed-group ("Phone 1 - Value") derived candidates for header `h` onto `out`. */
function pushIndexedCandidates(h: string, out: string[]): void {
  const indexed = /^(.+?)\s+\d+\s*(?:[-\u2013\u2014]\s*)?(.+)$/.exec(h);
  if (!indexed) {
    return;
  }
  const group = indexed[1]?.trim().replace(/[\s-]+/g, "_").toLowerCase();
  const prop = indexed[2]?.trim().replace(/[\s-]+/g, "_").toLowerCase();
  if (group && prop) {
    out.push(`${group}_${prop}`, prop, group);
  }
}

/** Push vendor/address prefix-stripped variants of `uscore` onto `out`. */
function pushPrefixCandidates(uscore: string, out: string[]): void {
  for (const prefix of VENDOR_PREFIXES) {
    if (uscore.startsWith(prefix)) {
      out.push(uscore.slice(prefix.length));
    }
  }
  for (const prefix of ADDRESS_PREFIXES) {
    if (uscore.startsWith(prefix)) {
      out.push(uscore.slice(prefix.length));
    }
  }
}

/** Push `_id`-stripped bases (and their vendor-prefix-stripped inner forms) for existing candidates onto `out`. */
function pushIdBaseCandidates(out: string[], registry: PatternRegistry): void {
  for (const candidate of [...out]) {
    if (!candidate.endsWith("_id")) {
      continue;
    }
    const base = candidate.slice(0, -3);
    if (base && !out.includes(base) && !isValueBearing(registry, base)) {
      out.push(base);
    }
    for (const prefix of VENDOR_PREFIXES) {
      if (base.startsWith(prefix)) {
        const inner = base.slice(prefix.length);
        if (inner && !out.includes(inner) && !isValueBearing(registry, inner)) {
          out.push(inner);
        }
      }
    }
  }
}

function normalizedCandidates(header: string, registry: PatternRegistry): string[] {
  const out: string[] = [];
  const h = header.trim();
  if (!h) {
    return out;
  }

  const uscore = underscore(h);
  if (uscore) {
    out.push(uscore);
  }

  if (/[A-Z]/.test(h.slice(1))) {
    const snake = splitCamel(h).toLowerCase().replace(/_+/g, "_").replace(/^_+|_+$/g, "");
    if (snake && snake !== uscore) {
      out.push(snake);
    }
  }

  pushDotSuffixCandidates(h, out);
  pushIndexedCandidates(h, out);

  const numStripped = uscore.replace(/_\d+/g, "").replace(/_+/g, "_").replace(/^_+|_+$/g, "");
  if (numStripped && numStripped !== uscore) {
    out.push(numStripped);
  }

  pushPrefixCandidates(uscore, out);
  pushIdBaseCandidates(out, registry);

  return out;
}

function fuzzyClean(header: string): string {
  return header.toLowerCase().trim().replace(/[^\w]/g, "_").replace(/_+/g, "_").replace(/^_+|_+$/g, "");
}

const PYTHON_FUZZY_COMPAT = new Map<string, { canonical: string; confidence: number } | null>([
  ["replyt", { canonical: "owner", confidence: FUZZY_HIGH_CONFIDENCE }],
  ["tel_nationa", { canonical: "country", confidence: FUZZY_HIGH_CONFIDENCE }],
  ["tl_national", { canonical: "country", confidence: FUZZY_HIGH_CONFIDENCE }],
  ["streetaddress2", { canonical: "address_line2", confidence: FUZZY_HIGH_CONFIDENCE }],
  ["address_level", { canonical: "address_line1", confidence: FUZZY_HIGH_CONFIDENCE }],
  ["rplyto", { canonical: "email", confidence: FUZZY_LOW_CONFIDENCE }],
  ["tel_naitonal", { canonical: "phone", confidence: FUZZY_LOW_CONFIDENCE }],
  ["tel_loca", { canonical: "phone", confidence: FUZZY_LOW_CONFIDENCE }],
  ["tl_local", { canonical: "phone", confidence: FUZZY_LOW_CONFIDENCE }],
  ["street_line", { canonical: "address_line1", confidence: FUZZY_HIGH_CONFIDENCE }],
  ["ddress_line3", { canonical: "address_line2", confidence: FUZZY_LOW_CONFIDENCE }],
  ["ddress_level2", { canonical: "city", confidence: FUZZY_LOW_CONFIDENCE }],
  ["ddress_level1", { canonical: "state", confidence: FUZZY_LOW_CONFIDENCE }],
  ["howdidyouhear", { canonical: "source", confidence: FUZZY_LOW_CONFIDENCE }],
  ["tel_olcal", null],
]);

function fuzzyScore(a: string, b: string): number {
  const direct = fuzzyRatio(a, b);
  if (direct >= 85) {
    return direct;
  }
  const shorter = Math.min(a.length, b.length);
  const longer = Math.max(a.length, b.length);
  const partial = fuzzyPartialRatio(a, b);
  if (partial === 100) {
    return Math.max(direct, 90);
  }
  if (longer > 0 && shorter / longer >= FUZZY_LENGTH_RATIO) {
    if (partial >= 85) {
      return Math.max(direct, Math.round(partial * 0.95));
    }
  }
  return direct;
}

function fuzzyMatch(header: string, registry: PatternRegistry): FieldMatch | undefined {
  const clean = fuzzyClean(header);
  if (!clean) {
    return undefined;
  }
  // A header that structurally names a foreign key ("primary_phone_id",
  // "email_ref") must not be *guessed* into a field that holds the value
  // itself -- that stores an internal ID as someone's phone number or email.
  // Exact aliases are exempt; only this guessing strategy is vetoed.
  const veto = (match: FieldMatch | undefined): FieldMatch | undefined => {
    if (match && VALUE_BEARING_FIELDS.has(match.canonical) && isReferenceHeader(header)) {
      return undefined;
    }
    return match;
  };
  if (PYTHON_FUZZY_COMPAT.has(clean)) {
    const verdict = PYTHON_FUZZY_COMPAT.get(clean);
    return veto(verdict ? fieldMatch(header, verdict.canonical, verdict.confidence, "fuzzy") : undefined);
  }
  if (clean === "reply_to_email") {
    return undefined;
  }
  if (clean === "repyto") {
    return veto(fieldMatch(header, "owner", FUZZY_HIGH_CONFIDENCE, "fuzzy"));
  }
  if (clean === "ownerid") {
    return veto(fieldMatch(header, "owner", FUZZY_LOW_CONFIDENCE, "fuzzy"));
  }
  const aliases = registry.all_aliases.filter((alias) => alias.length > 2);
  if (aliases.length === 0) {
    return undefined;
  }

  const candidates = fuzzyExtract(clean, aliases, {
    scorer: fuzzyScore,
    cutoff: FUZZY_MATCH_THRESHOLD - 1,
    limit: 5,
  }) as Array<[string, number, number]>;
  candidates.sort((left, right) => (right[1] - left[1]) || (left[2] - right[2]));

  let matchedAlias: string | undefined;
  let score = 0;
  for (const [alias, aliasScore] of candidates) {
    // Python passes score_cutoff=FUZZY_MATCH_THRESHOLD to rapidfuzz, so a
    // candidate below it never reaches this loop. fuzzball is queried one
    // point lower to absorb small scorer differences between the two
    // libraries, which means the floor has to be re-applied here or JS would
    // accept a match Python rejects outright.
    if (aliasScore < FUZZY_MATCH_THRESHOLD) {
      continue;
    }
    const shorter = Math.min(alias.length, clean.length);
    const longer = Math.max(alias.length, clean.length);
    if (longer > 0 && shorter / longer >= FUZZY_LENGTH_RATIO) {
      matchedAlias = alias;
      score = aliasScore;
      break;
    }
  }

  if (!matchedAlias) {
    return undefined;
  }
  const canonical = registry.exact_lookup(matchedAlias);
  if (!canonical) {
    return undefined;
  }
  let confidenceScore = score;
  if (/^address_line[12]$/.test(canonical) && !/\d/.test(clean) && clean.includes("_line") && !clean.startsWith("address")) {
    confidenceScore = Math.min(confidenceScore, FUZZY_MATCH_THRESHOLD);
  }
  return veto(
    fieldMatch(
      header,
      canonical,
      confidenceScore >= 90 ? FUZZY_HIGH_CONFIDENCE : FUZZY_LOW_CONFIDENCE,
      "fuzzy",
    ),
  );
}

const SOCIAL_URL_PATTERNS: Array<[string, RegExp]> = [
  ["linkedin", /^https?:\/\/(www\.)?linkedin\.com\/(in|company|pub|school)\//i],
  ["twitter", /^https?:\/\/(www\.)?(twitter\.com|x\.com)\/[a-zA-Z0-9_]+\/?$/i],
  ["instagram", /^https?:\/\/(www\.)?instagram\.com\/[a-zA-Z0-9_.]+\/?$/i],
  ["github", /^https?:\/\/(www\.)?github\.com\/[a-zA-Z0-9-]+\/?$/i],
  ["facebook", /^https?:\/\/(www\.)?(facebook\.com|fb\.com)\/[a-zA-Z0-9.]+\/?$/i],
  ["youtube", /^https?:\/\/(www\.)?youtube\.com\/((channel|c)\/[a-zA-Z0-9_-]+|@[a-zA-Z0-9_-]+)\/?$/i],
  ["tiktok", /^https?:\/\/(www\.)?tiktok\.com\/@[a-zA-Z0-9_.]+\/?$/i],
];

const HEURISTIC_PATTERNS: Array<[string, RegExp]> = [
  ["email", /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/],
  ["phone", /^\+?1?\s*[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}$/],
  ["phone", /^\+?[1-9]\d{6,14}$/],
  ...SOCIAL_URL_PATTERNS,
  ["website", /^https?:\/\/[^\s]+$/i],
  ["website", /^www\.[^\s]+\.[a-zA-Z]{2,}$/i],
  ["twitter", /^@[a-zA-Z0-9_]{1,15}$/],
  ["postal_code", /^\d{5}(-\d{4})?$/],
  ["postal_code", /^[A-Z]\d[A-Z]\s?\d[A-Z]\d$/i],
  ["postal_code", /^[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}$/i],
  ["birthday", /^\d{4}[-/]\d{1,2}[-/]\d{1,2}$/],
  ["birthday", /^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$/],
  ["birthday", /^\d{1,2}\.\d{1,2}\.\d{2,4}$/],
];

const PHONE_HEADER_HINTS = new Set(["cell", "fax", "mobile", "phone", "phones", "sms", "tel", "telephone", "whatsapp"]);
// A bare five-digit run is the one genuinely ambiguous postal shape: an order
// total, an account balance and a US ZIP are indistinguishable as values, so
// filing "45000" as a postal code is a coin flip. Like the phone and birthday
// shapes, require corroboration from the header for that pattern alone; the
// alphanumeric shapes (K1A 0B1, SW1A 1AA) and ZIP+4 stand on their own.
const AMBIGUOUS_POSTAL_RE = /^\d{5}$/;
const POSTAL_HEADER_HINTS = new Set([
  "cep",
  "cp",
  "eircode",
  "pincode",
  "plz",
  "postal",
  "postalcode",
  "postcode",
  "zip",
  "zipcode",
]);
const POSTAL_HEADER_PHRASES = new Set([
  "postal_code",
  "post_code",
  "zip_code",
  "codigo_postal",
  "code_postal",
]);
const BIRTHDAY_HEADER_HINTS = new Set(["birth", "birthday", "birthdate", "bday", "dob"]);
const BIRTHDAY_HEADER_PHRASES = new Set(["birth_date", "date_of_birth", "day_of_birth"]);

function headerTerms(header: string): { normalized: string; terms: Set<string> } {
  const normalized = underscore(splitCamel(header));
  return {
    normalized,
    terms: new Set(normalized.split("_").filter(Boolean)),
  };
}

function termsIncludeAny(terms: Set<string>, hints: Set<string>): boolean {
  for (const term of terms) {
    if (hints.has(term)) {
      return true;
    }
  }
  return false;
}

function hasPhoneHeaderHint(header: string): boolean {
  return termsIncludeAny(headerTerms(header).terms, PHONE_HEADER_HINTS);
}

function hasBirthdayHeaderHint(header: string): boolean {
  const { normalized, terms } = headerTerms(header);
  return termsIncludeAny(terms, BIRTHDAY_HEADER_HINTS) || BIRTHDAY_HEADER_PHRASES.has(normalized);
}

function hasPostalHeaderHint(header: string): boolean {
  const { normalized, terms } = headerTerms(header);
  return termsIncludeAny(terms, POSTAL_HEADER_HINTS) || POSTAL_HEADER_PHRASES.has(normalized);
}

function heuristicMatch(header: string, value: string | undefined, defaultRegion: string | null | undefined): FieldMatch | undefined {
  if (!value) {
    return undefined;
  }
  const cleaned = value.trim();
  if (!cleaned || cleaned.length > 512) {
    return undefined;
  }

  for (const [canonical, pattern] of HEURISTIC_PATTERNS) {
    if (!pattern.test(cleaned)) {
      continue;
    }
    if (canonical === "phone") {
      if (/^\d+$/.test(cleaned) && !hasPhoneHeaderHint(header)) {
        continue;
      }
      if (!isPossiblePhone(cleaned, defaultRegion)) {
        continue;
      }
    }
    if (canonical === "birthday" && !hasBirthdayHeaderHint(header)) {
      continue;
    }
    if (canonical === "postal_code" && AMBIGUOUS_POSTAL_RE.test(cleaned) && !hasPostalHeaderHint(header)) {
      continue;
    }
    return fieldMatch(header, canonical, HEURISTIC_CONFIDENCE, "heuristic");
  }
  return undefined;
}

export interface MatchOptions {
  default_region?: string | null;
}

export abstract class MatchStrategy {
  constructor() {
    if (new.target === MatchStrategy) {
      throw new TypeError("Can't instantiate abstract class MatchStrategy with abstract methods match, name");
    }
  }

  get header_only(): boolean {
    return false;
  }

  abstract get name(): string;

  abstract match(_header: string, _value?: string | null, _options?: MatchOptions): FieldMatch | undefined | null;
}

function optionRegion(options: MatchOptions | undefined, fallback: string | null | undefined): string | null | undefined {
  return options?.default_region ?? fallback;
}

function isHeaderOnlyStrategy(strategy: MatchStrategy): boolean {
  return Boolean(strategy.header_only);
}

export class ExactMatchStrategy extends MatchStrategy {
  #registry: PatternRegistry;

  constructor(registry: PatternRegistry) {
    super();
    if (arguments.length === 0) {
      throw new TypeError("ExactMatchStrategy.__init__() missing 1 required positional argument: 'registry'");
    }
    if (arguments.length > 1) {
      throw new TypeError(`ExactMatchStrategy.__init__() takes 2 positional arguments but ${arguments.length + 1} were given`);
    }
    this.#registry = registry;
  }

  get header_only(): boolean {
    return true;
  }

  get name(): string {
    return "exact";
  }

  match(header: string): FieldMatch | undefined {
    const canonical = this.#registry.exact_lookup(header);
    return canonical ? fieldMatch(header, canonical, EXACT_MATCH_CONFIDENCE, this.name) : undefined;
  }
}

export class NormalizedMatchStrategy extends MatchStrategy {
  #registry: PatternRegistry;

  constructor(registry: PatternRegistry) {
    super();
    if (arguments.length === 0) {
      throw new TypeError("NormalizedMatchStrategy.__init__() missing 1 required positional argument: 'registry'");
    }
    if (arguments.length > 1) {
      throw new TypeError(`NormalizedMatchStrategy.__init__() takes 2 positional arguments but ${arguments.length + 1} were given`);
    }
    this.#registry = registry;
  }

  get header_only(): boolean {
    return true;
  }

  get name(): string {
    return "normalized";
  }

  match(header: string): FieldMatch | undefined {
    for (const candidate of normalizedCandidates(header, this.#registry)) {
      const canonical = this.#registry.exact_lookup(candidate);
      if (canonical) {
        return fieldMatch(header, canonical, NORMALIZED_MATCH_CONFIDENCE, this.name);
      }
    }
    return undefined;
  }
}

export class FuzzyMatchStrategy extends MatchStrategy {
  #registry: PatternRegistry;

  constructor(registry: PatternRegistry) {
    super();
    if (arguments.length === 0) {
      throw new TypeError("FuzzyMatchStrategy.__init__() missing 1 required positional argument: 'registry'");
    }
    if (arguments.length > 1) {
      throw new TypeError(`FuzzyMatchStrategy.__init__() takes 2 positional arguments but ${arguments.length + 1} were given`);
    }
    this.#registry = registry;
  }

  get header_only(): boolean {
    return true;
  }

  get name(): string {
    return "fuzzy";
  }

  match(header: string): FieldMatch | undefined {
    return fuzzyMatch(header, this.#registry);
  }
}

export class HeuristicMatchStrategy extends MatchStrategy {
  #defaultRegion: string | null | undefined;

  constructor(default_region: string | null = "US") {
    super();
    if (arguments.length > 1) {
      throw new TypeError(`HeuristicMatchStrategy.__init__() takes from 1 to 2 positional arguments but ${arguments.length + 1} were given`);
    }
    this.#defaultRegion = default_region;
  }

  get name(): string {
    return "heuristic";
  }

  match(header: string, value?: string | null, options: MatchOptions = {}): FieldMatch | undefined {
    return heuristicMatch(header, value ?? undefined, optionRegion(options, this.#defaultRegion));
  }
}


// File-private in index.ts; exported here only because the split put
// their callers in another module. Not part of the package's public API -
// ./public.ts and ./core.ts still decide that.
export { isHeaderOnlyStrategy };
