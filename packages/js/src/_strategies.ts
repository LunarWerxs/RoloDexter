// Header match strategies: exact, normalized, fuzzy, heuristic.
// Extracted verbatim from index.ts, which re-exports every public name here.

import { extract as fuzzyExtract, partial_ratio as fuzzyPartialRatio, ratio as fuzzyRatio } from "fuzzball";
import { ADDRESS_PREFIXES, COMPANY_PREFIXES, EXACT_MATCH_CONFIDENCE, FUZZY_HIGH_CONFIDENCE, FUZZY_LENGTH_RATIO, FUZZY_LOW_CONFIDENCE, FUZZY_MATCH_THRESHOLD, FieldMatch, HEURISTIC_CONFIDENCE, NORMALIZED_MATCH_CONFIDENCE, PHONE_FIELDS, SOCIAL_FIELDS, VENDOR_PREFIXES, fieldMatch } from "./_models.js";
import type { PatternData } from "./_models.js";
import { isPossiblePhone } from "./_phone.js";
import { pyStrip } from "./_pycompat.js";
import { PatternRegistry } from "./_registry.js";
import { TABLES } from "./_tables.js";

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

// Python's `\w` on text is Unicode-aware (letters and digits of any script,
// plus "_"); JS's `\w` is ASCII-only and would turn "Teléfono" into "tel_fono".
const NON_WORD_RE = /[^\p{L}\p{N}_]/gu;
// Python's str.isupper(), which the camelCase checks use (the split itself
// stays ASCII, as Python's [a-z]/[A-Z] pattern does).
const UPPERCASE_RE = /\p{Lu}/u;

function underscore(value: string): string {
  return value
    .replace(/[\s-]+/g, "_")
    .toLowerCase()
    .replace(NON_WORD_RE, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
}

/**
 * Headers longer than this skip the rewrite (normalized) and fuzzy layers; the
 * exact lookup still runs. Header text is as attacker-controlled as a cell
 * value, and the indexed-header pattern backtracks quadratically on long runs
 * of spaces. Python: `_MAX_REWRITE_HEADER_LEN`.
 */
const MAX_REWRITE_HEADER_LEN = 200;

/**
 * The property of a "Group N - Property" header that names the group's value
 * itself, so the bare group ("e_mail") may stand in for it. Python:
 * `_VALUE_PROPERTIES`.
 */
const VALUE_PROPERTIES = new Set(TABLES.value_properties);

/**
 * Trailing words that describe another column instead of holding a value
 * ("E-mail 1 - Type", "E-mail Display Name", "Phone Ext"). Python:
 * `_QUALIFIER_TAILS`.
 */
const QUALIFIER_TAILS: readonly (readonly string[])[] = TABLES.qualifier_tails;

/**
 * The qualifier a header ends with ("type", "display_name") after at least one
 * other word, ignoring index numbers; else undefined. Python: `_qualifier_tail`.
 */
function qualifierTail(header: string): string | undefined {
  const words = underscore(splitCamel(pyStrip(header)))
    .split("_")
    .filter((word) => word && !/^\p{Nd}+$/u.test(word));
  for (const tail of QUALIFIER_TAILS) {
    if (words.length > tail.length && tail.every((word, i) => words[words.length - tail.length + i] === word)) {
      return tail.join("_");
    }
  }
  return undefined;
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
const REFERENCE_SUFFIX_RE = new RegExp("_(?:" + TABLES.header_hints.reference_suffixes.join("|") + ")$");

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
  const prefixRaw = pyStrip(h.slice(0, dot).toLowerCase());
  const suffixRaw = pyStrip(h.slice(dot + 1));
  const suffixLower = suffixRaw.replace(/[\s-]+/g, "_").toLowerCase();
  const lastPrefix = prefixRaw.slice(prefixRaw.lastIndexOf(".") + 1);
  if (COMPANY_PREFIXES.has(lastPrefix) && ["name", "nombre"].includes(suffixLower)) {
    out.unshift("company");
  }
  if (suffixLower) {
    out.push(suffixLower);
  }
  if (UPPERCASE_RE.test(suffixRaw.slice(1))) {
    // Python: _normalize_header(suffix_raw) (camel split, then non-word runs to "_").
    const snakeSuffix = underscore(splitCamel(suffixRaw));
    if (snakeSuffix && snakeSuffix !== suffixLower) {
      out.push(snakeSuffix);
    }
  }
}

/** Push the indexed-group ("Phone 1 - Value") derived candidates for header `h` onto `out`. */
function pushIndexedCandidates(h: string, out: string[]): void {
  const indexed = /^(.+?)\s+\p{Nd}+\s*(?:[-\u2013\u2014]\s*)?(.+)$/u.exec(h);
  if (!indexed) {
    return;
  }
  const group = pyStrip(indexed[1] ?? "").replace(/[\s-]+/g, "_").toLowerCase();
  const prop = pyStrip(indexed[2] ?? "").replace(/[\s-]+/g, "_").toLowerCase();
  if (group && prop) {
    // organization_name, name; the bare group ("e_mail") only when the property
    // names the group's value, never for "Type" or "Label".
    out.push(`${group}_${prop}`, prop);
    if (VALUE_PROPERTIES.has(prop)) {
      out.push(group);
    }
  }
}

/** A header addressed to the person filling a form ("Your company name"). */
const READER_PREFIX = "your_";

/**
 * Push vendor/address prefix-stripped variants of `uscore` onto `out`. What is
 * left after "contact_" is kept off a value field when it names a reference:
 * contact_email_id is the contact's email record, not an email address.
 * Python: `NormalizedMatchStrategy._candidates_context_stripped`.
 */
function pushPrefixCandidates(uscore: string, out: string[], registry: PatternRegistry): void {
  for (const prefix of VENDOR_PREFIXES) {
    if (uscore.startsWith(prefix)) {
      out.push(uscore.slice(prefix.length));
    }
  }
  for (const prefix of ADDRESS_PREFIXES) {
    if (uscore.startsWith(prefix)) {
      const rest = uscore.slice(prefix.length);
      if (prefix === "contact_" && isReferenceHeader(rest) && isValueBearing(registry, rest)) {
        continue;
      }
      out.push(rest);
    }
  }
}

/**
 * Push `uscore` without a leading "your_" ("Your work email" -> work_email), then
 * its vendor/address-stripped forms ("Your billing city" -> billing_city -> city).
 * Form exports title a column with the question the person answered. Python:
 * `NormalizedMatchStrategy._candidates_reader_prefix`. Added in 2.14.0.
 */
function pushReaderPrefixCandidates(uscore: string, out: string[], registry: PatternRegistry): void {
  if (!uscore.startsWith(READER_PREFIX)) {
    return;
  }
  const rest = uscore.slice(READER_PREFIX.length);
  if (!rest) {
    return;
  }
  out.push(rest);
  pushPrefixCandidates(rest, out, registry);
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
  const h = pyStrip(header);
  if (!h) {
    return out;
  }

  const uscore = underscore(h);
  if (uscore) {
    out.push(uscore);
  }

  if (UPPERCASE_RE.test(h.slice(1))) {
    // Python: _normalize_header(h) (camel split, then non-word runs to "_").
    const snake = underscore(splitCamel(h));
    if (snake && snake !== uscore) {
      out.push(snake);
    }
  }

  pushDotSuffixCandidates(h, out);
  pushIndexedCandidates(h, out);

  const numStripped = uscore.replace(/_\p{Nd}+/gu, "").replace(/_+/g, "_").replace(/^_+|_+$/g, "");
  if (numStripped && numStripped !== uscore) {
    out.push(numStripped);
  }

  pushPrefixCandidates(uscore, out, registry);
  pushReaderPrefixCandidates(uscore, out, registry);
  pushIdBaseCandidates(out, registry);

  return out;
}

function fuzzyClean(header: string): string {
  return pyStrip(header.toLowerCase()).replace(NON_WORD_RE, "_").replace(/_+/g, "_").replace(/^_+|_+$/g, "");
}

// Headers on which fuzzball's ratio/partial_ratio pair (scored by fuzzyScore
// below) and rapidfuzz's WRatio still pick a different field or confidence
// tier: the recorded Python verdict. Every other header is scored here and
// agrees with Python without an entry (e.g. phone_ext, ownerid and
// reply_to_email are unmatched in both).
const PYTHON_FUZZY_COMPAT = new Map<string, { canonical: string; confidence: number } | null>([
  ["replyt", { canonical: "email", confidence: FUZZY_LOW_CONFIDENCE }],
  ["repyto", { canonical: "email", confidence: FUZZY_LOW_CONFIDENCE }],
  ["rplyto", { canonical: "email", confidence: FUZZY_LOW_CONFIDENCE }],
  ["tel_nationa", { canonical: "phone", confidence: FUZZY_LOW_CONFIDENCE }],
  ["tl_national", { canonical: "phone", confidence: FUZZY_LOW_CONFIDENCE }],
  ["tel_naitonal", { canonical: "phone", confidence: FUZZY_LOW_CONFIDENCE }],
  ["tel_loca", { canonical: "phone", confidence: FUZZY_LOW_CONFIDENCE }],
  ["tl_local", { canonical: "phone", confidence: FUZZY_LOW_CONFIDENCE }],
  ["streetaddress2", { canonical: "address_line2", confidence: FUZZY_HIGH_CONFIDENCE }],
  ["address_level", { canonical: "city", confidence: FUZZY_LOW_CONFIDENCE }],
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
  // An alias far shorter than the header (or the reverse) gets no partial
  // credit: "phone" inside "phone_ext" is a qualifier on the phone, not the
  // phone. Python reaches the same verdict through FUZZY_LENGTH_RATIO.
  const shorter = Math.min(a.length, b.length);
  const longer = Math.max(a.length, b.length);
  if (!(longer > 0 && shorter / longer >= FUZZY_LENGTH_RATIO)) {
    return direct;
  }
  const partial = fuzzyPartialRatio(a, b);
  if (partial === 100) {
    return Math.max(direct, 90);
  }
  if (partial >= 85) {
    return Math.max(direct, Math.round(partial * 0.95));
  }
  return direct;
}

interface LengthIndex {
  aliases: string[];
  lengths: number[];
}

// A registry's aliases are fixed once it is built (languages and overrides are
// applied in its constructor), so each registry's length-sorted alias list is
// computed once instead of copied and filtered on every fuzzy miss.
const LENGTH_INDEXES = new WeakMap<PatternRegistry, LengthIndex>();

function lengthIndex(registry: PatternRegistry): LengthIndex {
  let index = LENGTH_INDEXES.get(registry);
  if (!index) {
    // Stable sort by length keeps registry order within a length, as Python's
    // FuzzyMatchStrategy._get_length_index does, so ties resolve the same way.
    const aliases = registry.all_aliases
      .filter((alias) => alias.length > 2)
      .sort((left, right) => left.length - right.length);
    index = { aliases, lengths: aliases.map((alias) => alias.length) };
    LENGTH_INDEXES.set(registry, index);
  }
  return index;
}

function lowerBound(values: number[], target: number, inclusive: boolean): number {
  let lo = 0;
  let hi = values.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (inclusive ? (values[mid] as number) <= target : (values[mid] as number) < target) {
      lo = mid + 1;
    } else {
      hi = mid;
    }
  }
  return lo;
}

/** Aliases whose length can pass FUZZY_LENGTH_RATIO against `cleanLength`. */
function aliasesInLengthBand(registry: PatternRegistry, cleanLength: number): string[] {
  const { aliases, lengths } = lengthIndex(registry);
  const lo = lowerBound(lengths, Math.ceil(cleanLength * FUZZY_LENGTH_RATIO), false);
  const hi = lowerBound(lengths, Math.floor(cleanLength / FUZZY_LENGTH_RATIO), true);
  return aliases.slice(lo, hi);
}

function fuzzyMatch(header: string, registry: PatternRegistry): FieldMatch | undefined {
  if (header.length > MAX_REWRITE_HEADER_LEN || qualifierTail(header)) {
    return undefined;
  }
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
  const aliases = aliasesInLengthBand(registry, clean.length);
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

const SOCIAL_URL_PATTERNS: Array<[string, RegExp]> = TABLES.social_urls.map(
  (def): [string, RegExp] => [
    def.canonical,
    new RegExp(
      "^https?://(www\\.)?(?:" +
        def.domains.map((domain) => domain.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") +
        ")/" +
        def.path,
      "i",
    ),
  ],
);

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

const PHONE_HEADER_HINTS = new Set(TABLES.header_hints.phone);
// A bare five-digit run is the one genuinely ambiguous postal shape: an order
// total, an account balance and a US ZIP are indistinguishable as values, so
// filing "45000" as a postal code is a coin flip. Like the phone and birthday
// shapes, require corroboration from the header for that pattern alone; the
// alphanumeric shapes (K1A 0B1, SW1A 1AA) and ZIP+4 stand on their own.
const AMBIGUOUS_POSTAL_RE = /^\d{5}$/;
const POSTAL_HEADER_HINTS = new Set(TABLES.header_hints.postal);
const POSTAL_HEADER_PHRASES = new Set(TABLES.header_hints.postal_phrases);
const BIRTHDAY_HEADER_HINTS = new Set(TABLES.header_hints.birthday);
const BIRTHDAY_HEADER_PHRASES = new Set(TABLES.header_hints.birthday_phrases);

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
  const cleaned = pyStrip(value);
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
    // "Phone 1 - Type" describes the phone column; a phone-shaped value in it
    // is still not this contact's phone.
    if (qualifierTail(header)) {
      return undefined;
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
    if (header.length > MAX_REWRITE_HEADER_LEN) {
      return undefined;
    }
    // A qualifier header ("E-mail 1 - Type") may only match an alias that keeps
    // the qualifier ("business_type"); dropping it ("e_mail", "label") would
    // file the type label as the value.
    const tail = qualifierTail(header);
    for (const candidate of normalizedCandidates(header, this.#registry)) {
      if (tail !== undefined && !candidate.endsWith(`_${tail}`)) {
        continue;
      }
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
