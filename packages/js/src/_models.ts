// Errors, the canonical field enum, field sets, and the match record.
// Extracted verbatim from index.ts, which re-exports every public name here.

import { lockPythonFrozenFields, pyRepr, pythonEquals, pythonIncludes, pythonLiteral, setOwnProperty } from "./_pycompat.js";

export const EXACT_MATCH_CONFIDENCE = 1.0;
export const NORMALIZED_MATCH_CONFIDENCE = 0.95;
export const FUZZY_MATCH_THRESHOLD = 80;
export const FUZZY_HIGH_CONFIDENCE = 0.85;
export const FUZZY_LOW_CONFIDENCE = 0.7;
export const FUZZY_LENGTH_RATIO = 0.5;
export const HEURISTIC_CONFIDENCE = 0.6;

export class RolodexterError extends Error {
  constructor(message?: string) {
    super(message);
    this.name = "RolodexterError";
  }
}

export class PatternLoadError extends RolodexterError {
  constructor(message?: string) {
    super(message);
    this.name = "PatternLoadError";
  }
}

export class NormalizationError extends RolodexterError {
  constructor(message?: string) {
    super(message);
    this.name = "NormalizationError";
  }
}

export class FieldMatch {
  readonly original: string;
  readonly canonical: string;
  readonly confidence: number;
  readonly strategy: string;
  readonly service: string | null;

  constructor(
    original: string,
    canonical?: string,
    confidence?: number,
    strategy?: string,
    service: string | null = null,
  ) {
    if (arguments.length === 0) {
      throw new TypeError("FieldMatch.__init__() missing 4 required positional arguments: 'original', 'canonical', 'confidence', and 'strategy'");
    }
    if (arguments.length === 1) {
      throw new TypeError("FieldMatch.__init__() missing 3 required positional arguments: 'canonical', 'confidence', and 'strategy'");
    }
    if (arguments.length === 2) {
      throw new TypeError("FieldMatch.__init__() missing 2 required positional arguments: 'confidence' and 'strategy'");
    }
    if (arguments.length === 3) {
      throw new TypeError("FieldMatch.__init__() missing 1 required positional argument: 'strategy'");
    }
    if (arguments.length > 5) {
      throw new TypeError(`FieldMatch.__init__() takes from 5 to 6 positional arguments but ${arguments.length + 1} were given`);
    }
    this.original = original;
    this.canonical = canonical as string;
    this.confidence = confidence as number;
    this.strategy = strategy as string;
    this.service = service;
    lockPythonFrozenFields(this, ["original", "canonical", "confidence", "strategy", "service"]);
  }

  get is_matched(): boolean {
    return this.canonical !== UNKNOWN_MATCH;
  }

  toString(): string {
    return `FieldMatch(original=${pyRepr(this.original)}, canonical=${pyRepr(this.canonical)}, confidence=${this.confidence}, strategy=${pyRepr(this.strategy)}, service=${pythonLiteral(this.service)})`;
  }
}

export interface PatternData {
  version?: string;
  fields?: Record<string, string[]>;
  expansion?: {
    form_prefixes?: string[];
    form_fields?: Record<string, string>;
    social_suffixes?: string[];
    social_fields?: string[];
  };
}

export interface LanguageData {
  language_code?: string;
  language_name?: string;
  generated_at?: string;
  source_version?: string;
  fields?: Record<string, string[]>;
}

/** @internal */
export type TranslateFunction = (
  phrase: string,
  languageCode: string,
  options: { timeout: number; signal?: AbortSignal },
) => string | { text?: string };

/** @internal */
export type AsyncTranslateFunction = (
  phrase: string,
  languageCode: string,
  options: { timeout: number; signal?: AbortSignal },
) => string | { text?: string } | Promise<string | { text?: string }>;

export interface GenerateLanguageOptions {
  force?: boolean;
  force_fields?: Set<string> | string[];
  timeout?: number;
  retries?: number;
  retry_backoff?: number;
}

interface InternalGenerateLanguageOptions extends GenerateLanguageOptions {
  cache_dir?: string;
  translator?: TranslateFunction;
}

interface GenerateLanguageAsyncOptions extends Omit<InternalGenerateLanguageOptions, "translator"> {
  translator?: AsyncTranslateFunction;
}

export interface MapPayloadOptions {
  depth?: number;
  service?: string | null;
  default_region?: string | null;
  extract_embedded_phones?: boolean;
  strict?: boolean;
  confidence_threshold?: number;
}

export interface ProfileOptions extends Omit<MapPayloadOptions, "service"> {
  max_rows?: number | null;
}

export interface CompileSchemaOptions {
  default_region?: string | null;
  strict?: boolean;
  confidence_threshold?: number;
}

export interface MapDataFrameOptions {
  default_region?: string | null;
  normalize?: boolean | null;
  strict?: boolean | null;
  confidence_threshold?: number | null;
}

export interface DataFrameLike {
  columns: Iterable<unknown> | ArrayLike<unknown>;
  rename: (args: { columns: Record<string, string> } | Record<string, string>) => unknown;
  get?: (column: string) => unknown;
  set?: (column: string, values: unknown) => unknown;
  [key: string]: unknown;
}

interface PatternRegistryOptions {
  patterns?: PatternData | null;
  patterns_path?: string | null;
  languages?: string | string[] | null;
  overrides?: Record<string, string> | null;
}

const UNKNOWN_MATCH = "unknown";
type CanonicalFieldName =
  | "ADDRESS_LINE1"
  | "ADDRESS_LINE2"
  | "AGE"
  | "BIRTHDAY"
  | "CITY"
  | "COMPANY"
  | "COMPANY_SIZE"
  | "COUNTRY"
  | "CREATED_AT"
  | "CURRENCY"
  | "DEPARTMENT"
  | "DISCORD"
  | "EMAIL"
  | "EMAIL_OPT_OUT"
  | "FACEBOOK"
  | "FAX"
  | "FIRST_NAME"
  | "FULL_ADDRESS"
  | "FULL_NAME"
  | "GENDER"
  | "GITHUB"
  | "HOME_PHONE"
  | "INDUSTRY"
  | "INSTAGRAM"
  | "JOB_TITLE"
  | "LANGUAGE_PREFERENCE"
  | "LAST_CONTACTED"
  | "LAST_NAME"
  | "LEAD_STATUS"
  | "LIFECYCLE_STAGE"
  | "LINKEDIN"
  | "MESSAGE"
  | "METADATA"
  | "MIDDLE_NAME"
  | "NICKNAME"
  | "NOTES"
  | "OWNER"
  | "PHONE"
  | "POSTAL_CODE"
  | "PREFIX"
  | "REFERRER_URL"
  | "REVENUE"
  | "SCORE"
  | "SOURCE"
  | "SOURCE_ID"
  | "SOURCE_SERVICE"
  | "STATE"
  | "SUBJECT"
  | "SUBSCRIBED"
  | "SUFFIX"
  | "TAGS"
  | "TELEGRAM"
  | "TIKTOK"
  | "TIMEZONE"
  | "TWITTER"
  | "UNKNOWN"
  | "UPDATED_AT"
  | "UTM_PARAMETERS"
  | "VERIFIED"
  | "WEBSITE"
  | "WHATSAPP"
  | "WORK_PHONE"
  | "YOUTUBE";

interface CanonicalFieldMember {
  readonly name: CanonicalFieldName;
  readonly value: string;
  toString(): string;
  valueOf(): string;
  toJSON(): string;
  [Symbol.toPrimitive](hint: string): string;
}

function canonicalField(name: CanonicalFieldName, value: string): CanonicalFieldMember {
  return Object.freeze({
    name,
    value,
    toString: () => `CanonicalField.${name}`,
    valueOf: () => value,
    toJSON: () => value,
    [Symbol.toPrimitive]: (hint: string) => (hint === "string" ? `CanonicalField.${name}` : value),
  });
}

const CANONICAL_FIELD_MEMBERS = Object.freeze({
  FIRST_NAME: canonicalField("FIRST_NAME", "first_name"),
  LAST_NAME: canonicalField("LAST_NAME", "last_name"),
  FULL_NAME: canonicalField("FULL_NAME", "full_name"),
  MIDDLE_NAME: canonicalField("MIDDLE_NAME", "middle_name"),
  NICKNAME: canonicalField("NICKNAME", "nickname"),
  PREFIX: canonicalField("PREFIX", "prefix"),
  SUFFIX: canonicalField("SUFFIX", "suffix"),
  EMAIL: canonicalField("EMAIL", "email"),
  PHONE: canonicalField("PHONE", "phone"),
  HOME_PHONE: canonicalField("HOME_PHONE", "home_phone"),
  WORK_PHONE: canonicalField("WORK_PHONE", "work_phone"),
  FAX: canonicalField("FAX", "fax"),
  WHATSAPP: canonicalField("WHATSAPP", "whatsapp"),
  WEBSITE: canonicalField("WEBSITE", "website"),
  COMPANY: canonicalField("COMPANY", "company"),
  JOB_TITLE: canonicalField("JOB_TITLE", "job_title"),
  DEPARTMENT: canonicalField("DEPARTMENT", "department"),
  INDUSTRY: canonicalField("INDUSTRY", "industry"),
  ADDRESS_LINE1: canonicalField("ADDRESS_LINE1", "address_line1"),
  ADDRESS_LINE2: canonicalField("ADDRESS_LINE2", "address_line2"),
  CITY: canonicalField("CITY", "city"),
  STATE: canonicalField("STATE", "state"),
  POSTAL_CODE: canonicalField("POSTAL_CODE", "postal_code"),
  COUNTRY: canonicalField("COUNTRY", "country"),
  FULL_ADDRESS: canonicalField("FULL_ADDRESS", "full_address"),
  LINKEDIN: canonicalField("LINKEDIN", "linkedin"),
  TWITTER: canonicalField("TWITTER", "twitter"),
  FACEBOOK: canonicalField("FACEBOOK", "facebook"),
  INSTAGRAM: canonicalField("INSTAGRAM", "instagram"),
  GITHUB: canonicalField("GITHUB", "github"),
  YOUTUBE: canonicalField("YOUTUBE", "youtube"),
  TIKTOK: canonicalField("TIKTOK", "tiktok"),
  DISCORD: canonicalField("DISCORD", "discord"),
  TELEGRAM: canonicalField("TELEGRAM", "telegram"),
  LEAD_STATUS: canonicalField("LEAD_STATUS", "lead_status"),
  LIFECYCLE_STAGE: canonicalField("LIFECYCLE_STAGE", "lifecycle_stage"),
  EMAIL_OPT_OUT: canonicalField("EMAIL_OPT_OUT", "email_opt_out"),
  TAGS: canonicalField("TAGS", "tags"),
  SOURCE: canonicalField("SOURCE", "source"),
  UTM_PARAMETERS: canonicalField("UTM_PARAMETERS", "utm_parameters"),
  SCORE: canonicalField("SCORE", "score"),
  OWNER: canonicalField("OWNER", "owner"),
  BIRTHDAY: canonicalField("BIRTHDAY", "birthday"),
  AGE: canonicalField("AGE", "age"),
  CREATED_AT: canonicalField("CREATED_AT", "created_at"),
  UPDATED_AT: canonicalField("UPDATED_AT", "updated_at"),
  LAST_CONTACTED: canonicalField("LAST_CONTACTED", "last_contacted"),
  REVENUE: canonicalField("REVENUE", "revenue"),
  CURRENCY: canonicalField("CURRENCY", "currency"),
  MESSAGE: canonicalField("MESSAGE", "message"),
  SUBJECT: canonicalField("SUBJECT", "subject"),
  COMPANY_SIZE: canonicalField("COMPANY_SIZE", "company_size"),
  NOTES: canonicalField("NOTES", "notes"),
  METADATA: canonicalField("METADATA", "metadata"),
  GENDER: canonicalField("GENDER", "gender"),
  TIMEZONE: canonicalField("TIMEZONE", "timezone"),
  LANGUAGE_PREFERENCE: canonicalField("LANGUAGE_PREFERENCE", "language_preference"),
  REFERRER_URL: canonicalField("REFERRER_URL", "referrer_url"),
  SOURCE_ID: canonicalField("SOURCE_ID", "source_id"),
  SOURCE_SERVICE: canonicalField("SOURCE_SERVICE", "source_service"),
  SUBSCRIBED: canonicalField("SUBSCRIBED", "subscribed"),
  VERIFIED: canonicalField("VERIFIED", "verified"),
  UNKNOWN: canonicalField("UNKNOWN", "unknown"),
});

type CanonicalFieldEnum = {
  (value: string): CanonicalFieldMember;
  readonly [Symbol.iterator]: () => IterableIterator<CanonicalFieldMember>;
} & Record<CanonicalFieldName, CanonicalFieldMember>;

export const CanonicalField = Object.assign(
  function CanonicalField(value: string): CanonicalFieldMember {
    const member = Object.values(CANONICAL_FIELD_MEMBERS).find((field) => field.value === value);
    if (!member) {
      throw new RangeError(`${JSON.stringify(value)} is not a valid CanonicalField`);
    }
    return member;
  },
  CANONICAL_FIELD_MEMBERS,
) as CanonicalFieldEnum;

export type CanonicalFieldValue = string | CanonicalFieldMember;

function canonicalFieldValue(canonicalField: CanonicalFieldValue): string {
  return typeof canonicalField === "string" ? canonicalField : canonicalField.value;
}

const PHONE_FIELDS = new Set(["phone", "home_phone", "work_phone", "fax", "whatsapp"]);
const NAME_FIELDS = new Set([
  "first_name",
  "last_name",
  "full_name",
  "middle_name",
  "nickname",
  "prefix",
  "suffix",
]);
const ADDRESS_FIELDS = new Set(["address_line1", "address_line2", "city", "full_address"]);
const BOOLEAN_FIELDS = new Set(["email_opt_out", "subscribed", "verified"]);
const LIST_FIELDS = new Set(["tags"]);
const DATE_FIELDS = new Set(["birthday", "created_at", "updated_at", "last_contacted"]);
const SOCIAL_FIELDS = new Set([
  "website",
  "linkedin",
  "twitter",
  "facebook",
  "instagram",
  "github",
  "youtube",
  "tiktok",
  "discord",
  "telegram",
]);

const COMPANY_PREFIXES = new Set([
  "account",
  "accounts",
  "org",
  "organization",
  "organisations",
  "organizations",
  "organisation",
  "company",
  "companies",
  "firm",
  "business",
  "enterprise",
]);

const VENDOR_PREFIXES = [
  "hs_",
  "hubspot_",
  "sf_",
  "salesforce_",
  "sl_",
  "smartlead_",
];

const ADDRESS_PREFIXES = [
  "business_",
  "mailing_",
  "home_",
  "other_",
  "personal_",
  "shipping_",
  "billing_",
  "primary_",
  "secondary_",
];

function isMatched(match: FieldMatch): boolean {
  return match.canonical !== UNKNOWN_MATCH;
}

function fieldMatch(
  original: string,
  canonical: string,
  confidence: number,
  strategy: string,
  service: string | null = null,
): FieldMatch {
  return new FieldMatch(original, canonical, confidence, strategy, service);
}

function unknown(header: string): FieldMatch {
  return fieldMatch(header, UNKNOWN_MATCH, 0, "none");
}

function valueForMatching(value: unknown): string | undefined {
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "boolean") {
    return String(value);
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? `${value}.0` : String(value);
  }
  return undefined;
}

function normalizeAlias(alias: string): string {
  return alias.toLowerCase().trim();
}

function mergeValue(target: Record<string, unknown>, key: string, value: unknown): void {
  // Own-property semantics throughout: `"__proto__" in target` is true for
  // every plain object, so a plain `in` test would take the merge branch and
  // read Object.prototype as the existing value. Python's dict has no such key.
  const present = Object.prototype.hasOwnProperty.call(target, key);
  const current = present ? target[key] : undefined;

  if (LIST_FIELDS.has(key)) {
    if (!present) {
      setOwnProperty(target, key, Array.isArray(value) ? [...value] : value);
      return;
    }
    const incoming = Array.isArray(value) ? value : [value];
    const existing = Array.isArray(current) ? current : [current];
    const merged = [...existing];
    for (const item of incoming) {
      if (!pythonIncludes(merged, item)) {
        merged.push(item);
      }
    }
    setOwnProperty(target, key, merged);
    return;
  }

  if (!present) {
    setOwnProperty(target, key, value);
    return;
  }
  // An empty cell carries no information, so it must not turn a good value
  // into a two-element list. This shows up whenever an export has two columns
  // meaning the same field and only one is filled in.
  const isBlank = (candidate: unknown): boolean =>
    candidate === null || candidate === undefined ||
    (typeof candidate === "string" && candidate.trim() === "");
  if (isBlank(value)) {
    return;
  }
  const existing = current;
  if (isBlank(existing)) {
    setOwnProperty(target, key, value);
    return;
  }
  if (Array.isArray(existing)) {
    if (!pythonIncludes(existing, value)) {
      existing.push(value);
    }
  } else if (!pythonEquals(existing, value)) {
    setOwnProperty(target, key, [existing, value]);
  }
}


// File-private in index.ts; exported here only because the split put
// their callers in another module. Not part of the package's public API -
// ./public.ts and ./core.ts still decide that.
export { ADDRESS_FIELDS, ADDRESS_PREFIXES, BOOLEAN_FIELDS, CANONICAL_FIELD_MEMBERS, COMPANY_PREFIXES, DATE_FIELDS, LIST_FIELDS, NAME_FIELDS, PHONE_FIELDS, SOCIAL_FIELDS, VENDOR_PREFIXES, canonicalField, canonicalFieldValue, fieldMatch, isMatched, mergeValue, normalizeAlias, unknown, valueForMatching };
export type { CanonicalFieldMember, GenerateLanguageAsyncOptions, InternalGenerateLanguageOptions, PatternRegistryOptions };
