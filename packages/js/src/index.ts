import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, readdirSync, renameSync, unlinkSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { homedir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import {
  findPhoneNumbersInText,
  getCountries,
  getCountryCallingCode,
  parsePhoneNumberFromString,
} from "libphonenumber-js/max";
import type { CountryCode, PhoneNumber as LibPhoneNumber } from "libphonenumber-js/max";
import { extract as fuzzyExtract, partial_ratio as fuzzyPartialRatio, ratio as fuzzyRatio } from "fuzzball";

const moduleUrl = typeof __filename !== "undefined" ? pathToFileURL(__filename).href : import.meta.url;
const require = createRequire(moduleUrl);
const phoneMetadata = require("libphonenumber-js/metadata.max.json") as {
  country_calling_codes?: Record<string, string[]>;
};
let unidecode: ((value: string) => string) | undefined;

export const EXACT_MATCH_CONFIDENCE = 1.0;
export const NORMALIZED_MATCH_CONFIDENCE = 0.95;
export const FUZZY_MATCH_THRESHOLD = 80;
export const FUZZY_HIGH_CONFIDENCE = 0.85;
export const FUZZY_LOW_CONFIDENCE = 0.7;
export const FUZZY_LENGTH_RATIO = 0.5;
export const HEURISTIC_CONFIDENCE = 0.6;
export const EMBEDDED_PHONE_MAX_TEXT_CHARS = 8192;
export const EMBEDDED_PHONE_MAX_MATCHES_PER_FIELD = 5;
export const EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD = 20;
export const DEFAULT_HEADER_CACHE_MAX_SIZE = 4096;

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

export class MatchType {
  static readonly NOT_A_NUMBER = 0;
  static readonly NO_MATCH = 1;
  static readonly SHORT_NSN_MATCH = 2;
  static readonly NSN_MATCH = 3;
  static readonly EXACT_MATCH = 4;

  readonly NOT_A_NUMBER = MatchType.NOT_A_NUMBER;
  readonly NO_MATCH = MatchType.NO_MATCH;
  readonly SHORT_NSN_MATCH = MatchType.SHORT_NSN_MATCH;
  readonly NSN_MATCH = MatchType.NSN_MATCH;
  readonly EXACT_MATCH = MatchType.EXACT_MATCH;
}

export class NumberType {
  static readonly FIXED_LINE = 0;
  static readonly MOBILE = 1;
  static readonly FIXED_LINE_OR_MOBILE = 2;
  static readonly TOLL_FREE = 3;
  static readonly PREMIUM_RATE = 4;
  static readonly SHARED_COST = 5;
  static readonly VOIP = 6;
  static readonly PERSONAL_NUMBER = 7;
  static readonly PAGER = 8;
  static readonly UAN = 9;
  static readonly VOICEMAIL = 10;
  static readonly UNKNOWN = 99;

  readonly FIXED_LINE = NumberType.FIXED_LINE;
  readonly MOBILE = NumberType.MOBILE;
  readonly FIXED_LINE_OR_MOBILE = NumberType.FIXED_LINE_OR_MOBILE;
  readonly TOLL_FREE = NumberType.TOLL_FREE;
  readonly PREMIUM_RATE = NumberType.PREMIUM_RATE;
  readonly SHARED_COST = NumberType.SHARED_COST;
  readonly VOIP = NumberType.VOIP;
  readonly PERSONAL_NUMBER = NumberType.PERSONAL_NUMBER;
  readonly PAGER = NumberType.PAGER;
  readonly UAN = NumberType.UAN;
  readonly VOICEMAIL = NumberType.VOICEMAIL;
  readonly UNKNOWN = NumberType.UNKNOWN;
}

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

export interface MapPayloadOptions {
  depth?: number;
  service?: string | null;
  default_region?: string | null;
  extract_embedded_phones?: boolean;
  strict?: boolean;
  confidence_threshold?: number;
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

Object.defineProperty(CanonicalField, Symbol.iterator, {
  value: function* iterCanonicalFields(): IterableIterator<CanonicalFieldMember> {
    yield* Object.values(CANONICAL_FIELD_MEMBERS);
  },
});
Object.freeze(CanonicalField);

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

const DIALOUT_RE = /^(?:011|00)\s*/;
const TEL_URI_RE = /^tel:/i;
const TEL_EXT_RE = /;ext=(\d+)/i;
const TEL_PARAMS_RE = /;[a-z-]+=.*$/i;
const EXTENSION_RE = /(?:;ext=|\bext\.?|\bextn\.?|\bextension\b|\bx|(?<=\d)x|#)\s*(\d+)$/i;
const PHONE_ALPHA_MAP: Record<string, string> = {
  A: "2",
  B: "2",
  C: "2",
  D: "3",
  E: "3",
  F: "3",
  G: "4",
  H: "4",
  I: "4",
  J: "5",
  K: "5",
  L: "5",
  M: "6",
  N: "6",
  O: "6",
  P: "7",
  Q: "7",
  R: "7",
  S: "7",
  T: "8",
  U: "8",
  V: "8",
  W: "9",
  X: "9",
  Y: "9",
  Z: "9",
};
const NUMBER_TYPE_MAP: Record<string, number> = {
  FIXED_LINE: NumberType.FIXED_LINE,
  MOBILE: NumberType.MOBILE,
  FIXED_LINE_OR_MOBILE: NumberType.FIXED_LINE_OR_MOBILE,
  TOLL_FREE: NumberType.TOLL_FREE,
  PREMIUM_RATE: NumberType.PREMIUM_RATE,
  SHARED_COST: NumberType.SHARED_COST,
  VOIP: NumberType.VOIP,
  PERSONAL_NUMBER: NumberType.PERSONAL_NUMBER,
  PAGER: NumberType.PAGER,
  UAN: NumberType.UAN,
  VOICEMAIL: NumberType.VOICEMAIL,
};

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

function pyRepr(value: unknown): string {
  if (typeof value === "string") {
    return pythonStringLiteral(value);
  }
  return pythonLiteral(value);
}

function pyString(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  return pythonLiteral(value);
}

function pythonPositionalTypeError(callable: string, expected: number, given: number): TypeError {
  const expectedWord = expected === 1 ? "argument" : "arguments";
  const givenVerb = given === 1 ? "was" : "were";
  return new TypeError(`${callable}() takes ${expected} positional ${expectedWord} but ${given} ${givenVerb} given`);
}

function pythonRangePositionalTypeError(callable: string, minExpected: number, maxExpected: number, given: number): TypeError {
  return new TypeError(`${callable}() takes from ${minExpected} to ${maxExpected} positional arguments but ${given} were given`);
}

function pythonMissingRequiredArg(callable: string, argName: string): TypeError {
  return new TypeError(`${callable}() missing 1 required positional argument: '${argName}'`);
}

function pythonMissingRequiredArgs(callable: string, argNames: string[]): TypeError {
  const quoted = argNames.map((argName) => `'${argName}'`);
  const joined = quoted.length === 2
    ? `${quoted[0]} and ${quoted[1]}`
    : `${quoted.slice(0, -1).join(", ")}, and ${quoted.at(-1)}`;
  return new TypeError(`${callable}() missing ${argNames.length} required positional arguments: ${joined}`);
}

function pythonLiteral(value: unknown): string {
  if (value === null) {
    return "None";
  }
  if (value === undefined) {
    return "None";
  }
  if (value === true) {
    return "True";
  }
  if (value === false) {
    return "False";
  }
  if (typeof value === "string") {
    return pythonStringLiteral(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => pythonLiteral(item)).join(", ")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>).map(([key, item]) => `${pythonLiteral(key)}: ${pythonLiteral(item)}`).join(", ")}}`;
  }
  return String(value);
}

function pythonStringLiteral(value: string): string {
  const quote = value.includes("'") && !value.includes("\"") ? "\"" : "'";
  const escaped = value
    .replace(/\\/g, "\\\\")
    .replace(/\n/g, "\\n")
    .replace(/\r/g, "\\r")
    .replace(/\t/g, "\\t")
    .replace(new RegExp(quote, "g"), `\\${quote}`);
  return `${quote}${escaped}${quote}`;
}

function pythonTypeName(value: unknown): string {
  if (value === null || value === undefined) {
    return "NoneType";
  }
  if (Array.isArray(value)) {
    return "list";
  }
  if (typeof value === "boolean") {
    return "bool";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? "int" : "float";
  }
  if (typeof value === "string") {
    return "str";
  }
  if (typeof value === "object") {
    return "dict";
  }
  return typeof value;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function assertPythonMethodOptions(
  callable: string,
  requiredArgName: string,
  argLength: number,
  options: unknown,
): asserts options is Record<string, unknown> | undefined {
  if (argLength < 1) {
    throw pythonMissingRequiredArg(callable, requiredArgName);
  }
  if (argLength > 2 || (argLength === 2 && options !== undefined && !isPlainObject(options))) {
    throw pythonPositionalTypeError(callable, 2, argLength + 1);
  }
}

function assertPythonOptionsKeys(callable: string, options: Record<string, unknown> | undefined, allowed: Set<string>): void {
  if (!options) {
    return;
  }
  for (const key of Object.keys(options)) {
    if (!allowed.has(key)) {
      throw new TypeError(`${callable}() got an unexpected keyword argument '${key}'`);
    }
  }
}

function assertMappingPayload(payload: unknown): asserts payload is Record<string, unknown> {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw attributeError(`'${pythonTypeName(payload)}' object has no attribute 'items'`);
  }
}

function assertPhoneNumber(value: unknown): asserts value is PhoneNumber {
  if (!(value instanceof PhoneNumber)) {
    throw attributeError(`'${pythonTypeName(value)}' object has no attribute '_pn_obj'`);
  }
}

function assertValueNormalizerArity(
  callable: string,
  argLength: number,
  expected: number,
  valueArgName = "value",
): void {
  if (argLength < 1) {
    throw pythonMissingRequiredArg(callable, valueArgName);
  }
  if (argLength > 1) {
    throw pythonPositionalTypeError(callable, expected, argLength + (expected - 1));
  }
}

function isPatternRegistryOptions(value: unknown): value is PatternRegistryOptions {
  return isPlainObject(value) &&
    ("patterns" in value || "patterns_path" in value || "languages" in value || "overrides" in value) &&
    !("fields" in value);
}

function lockPythonFrozenFields(target: object, fields: string[]): void {
  for (const field of fields) {
    const value = (target as Record<string, unknown>)[field];
    Object.defineProperty(target, field, {
      configurable: false,
      enumerable: true,
      get() {
        return value;
      },
      set() {
        const error = new TypeError(`cannot assign to field '${field}'`);
        error.name = "FrozenInstanceError";
        throw error;
      },
    });
  }
  Object.preventExtensions(target);
}

const phoneNumberObjects = new WeakMap<object, LibPhoneNumber>();
const possiblePhoneNumbers = new WeakSet<object>();

export class PhoneNumber {
  readonly calling_code: number;
  readonly national_number: string;
  readonly raw: string;
  readonly extension: string | null;

  constructor(calling_code: number, national_number: string, raw: string, extension?: string | null);
  /** @internal */
  constructor(
    calling_code: number,
    national_number: string,
    raw: string,
    extension: string | null | undefined,
    parsed: LibPhoneNumber | undefined,
  );
  constructor(
    calling_code: number,
    nationalNumberArg?: string,
    rawArg?: string,
    extensionArg?: string | null,
    parsedArg?: LibPhoneNumber,
  ) {
    if (arguments.length === 0) {
      throw new TypeError("PhoneNumber.__init__() missing 3 required positional arguments: 'calling_code', 'national_number', and 'raw'");
    }
    if (arguments.length === 1) {
      throw new TypeError("PhoneNumber.__init__() missing 2 required positional arguments: 'national_number' and 'raw'");
    }
    if (arguments.length === 2) {
      throw new TypeError("PhoneNumber.__init__() missing 1 required positional argument: 'raw'");
    }
    if (arguments.length > 5) {
      throw new TypeError(`PhoneNumber.__init__() takes from 4 to 6 positional arguments but ${arguments.length + 1} were given`);
    }
    this.calling_code = calling_code;
    this.national_number = nationalNumberArg as string;
    this.raw = rawArg as string;
    this.extension = extensionArg ?? null;
    if (parsedArg) {
      phoneNumberObjects.set(this, parsedArg);
    }
    lockPythonFrozenFields(this, [
      "calling_code",
      "national_number",
      "raw",
      "extension",
    ]);
  }

  get e164(): string {
    return phoneNumberObjects.get(this)?.number ?? `+${this.calling_code}${this.national_number}`;
  }

  get is_valid(): boolean {
    return phoneNumberObjects.get(this)?.isValid() ?? false;
  }

  get is_possible(): boolean {
    return phoneNumberObjects.get(this)?.isPossible() ?? possiblePhoneNumbers.has(this);
  }

  get country_codes(): string[] {
    return phoneMetadata.country_calling_codes?.[String(this.calling_code)] ??
      getCountries().filter((country) => getCountryCallingCode(country) === String(this.calling_code));
  }

  toString(): string {
    return this.e164;
  }
}

export class PhoneNumberMatch {
  readonly start: number;
  readonly end: number;
  readonly raw_string: string;
  readonly number: PhoneNumber;

  constructor(start: number, end: number, raw_string: string, number: PhoneNumber) {
    if (arguments.length === 0) {
      throw new TypeError("PhoneNumberMatch.__init__() missing 4 required positional arguments: 'start', 'end', 'raw_string', and 'number'");
    }
    if (arguments.length === 1) {
      throw new TypeError("PhoneNumberMatch.__init__() missing 3 required positional arguments: 'end', 'raw_string', and 'number'");
    }
    if (arguments.length === 2) {
      throw new TypeError("PhoneNumberMatch.__init__() missing 2 required positional arguments: 'raw_string' and 'number'");
    }
    if (arguments.length === 3) {
      throw new TypeError("PhoneNumberMatch.__init__() missing 1 required positional argument: 'number'");
    }
    if (arguments.length > 4) {
      throw new TypeError(`PhoneNumberMatch.__init__() takes 5 positional arguments but ${arguments.length + 1} were given`);
    }
    this.start = start;
    this.end = end;
    this.raw_string = raw_string;
    this.number = number;
  }

  toString(): string {
    return `PhoneNumberMatch(start=${this.start}, end=${this.end}, number=${this.number.e164})`;
  }
}

export class PhoneNumberMatcher implements Iterable<PhoneNumberMatch> {
  #text: unknown;
  #defaultRegion: string | null | undefined;
  #maxMatches: number | null;
  #matches?: PhoneNumberMatch[];

  constructor(
    text: string,
    default_region: string | null = null,
    options: { max_matches?: number | null } = {},
  ) {
    this.#text = text;
    this.#defaultRegion = default_region;
    const requestedMax = options.max_matches;
    if (requestedMax !== undefined && requestedMax !== null && typeof requestedMax !== "number") {
      throw new TypeError("'>' not supported between instances of 'str' and 'int'");
    }
    this.#maxMatches = requestedMax === undefined || requestedMax === null ? null : Math.max(0, requestedMax);
  }

  #findAll(): PhoneNumberMatch[] {
    if (typeof this.#text !== "string") {
      return [];
    }
    const results: PhoneNumberMatch[] = [];
    const region = this.#defaultRegion ?? "US";
    for (const found of findPhoneNumbersInText(this.#text, asCountryCode(region))) {
      if (this.#maxMatches !== null && results.length >= this.#maxMatches) {
        break;
      }
      const raw_string = this.#text.slice(found.startsAt, found.endsAt);
      results.push(new PhoneNumberMatch(found.startsAt, found.endsAt, raw_string, wrapPhoneNumber(found.number, raw_string)));
    }
    return results;
  }

  get #allMatches(): PhoneNumberMatch[] {
    this.#matches ??= this.#findAll();
    return this.#matches;
  }

  get length(): number {
    return this.#allMatches.length;
  }

  has_next(): boolean {
    return this.length > 0;
  }

  [Symbol.iterator](): Iterator<PhoneNumberMatch> {
    return this.#allMatches[Symbol.iterator]();
  }
}

export function parse(raw: string, default_region: string | null = null): PhoneNumber | null {
  if (arguments.length < 1) {
    throw pythonMissingRequiredArg("parse", "raw");
  }
  if (arguments.length > 2) {
    throw pythonRangePositionalTypeError("parse", 1, 2, arguments.length);
  }
  if (typeof raw !== "string") {
    return null;
  }
  const parsed = parsePhoneObject(raw, default_region);
  return parsed ? wrapPhoneNumber(parsed, raw) : parseNanpLocalFallback(raw, default_region);
}

function parsePhoneForMatch(raw: string, default_region: string | null = null): PhoneNumber | null {
  if (typeof raw !== "string") {
    return null;
  }
  const text = preprocessPhoneRaw(raw);
  if (!text) {
    return null;
  }
  try {
    const parsed = parsePhoneNumberFromString(text, asCountryCode(default_region));
    return parsed ? wrapPhoneNumber(parsed, raw) : parseNanpLocalFallback(raw, default_region);
  } catch {
    return parseNanpLocalFallback(raw, default_region);
  }
}

function formatE164(raw: string, default_region: string | null = null): string | null {
  return parse(raw, default_region)?.e164 ?? null;
}

export function format_e164(raw: string, default_region: string | null = null): string | null {
  if (arguments.length < 1) {
    throw pythonMissingRequiredArg("format_e164", "raw");
  }
  if (arguments.length > 2) {
    throw pythonRangePositionalTypeError("format_e164", 1, 2, arguments.length);
  }
  return formatE164(raw, default_region);
}

function isValid(raw: string, default_region: string | null = null): boolean {
  return parse(raw, default_region)?.is_valid ?? false;
}

export function is_valid(raw: string, default_region: string | null = null): boolean {
  if (arguments.length < 1) {
    throw pythonMissingRequiredArg("is_valid", "raw");
  }
  if (arguments.length > 2) {
    throw pythonRangePositionalTypeError("is_valid", 1, 2, arguments.length);
  }
  return isValid(raw, default_region);
}

function formatInternational(phone: PhoneNumber): string {
  const parsed = phoneNumberObjects.get(phone);
  if (parsed && phone.calling_code === 1 && /^\d{10}$/.test(phone.national_number)) {
    const national = phone.national_number;
    const formatted = `+1 ${national.slice(0, 3)}-${national.slice(3, 6)}-${national.slice(6)}`;
    return phone.extension ? `${formatted} ext. ${phone.extension}` : formatted;
  }
  return parsed?.formatInternational() ?? `+${phone.calling_code} ${phone.national_number}`;
}

export function format_international(phone: PhoneNumber): string {
  if (arguments.length < 1) {
    throw pythonMissingRequiredArg("format_international", "phone");
  }
  if (arguments.length > 1) {
    throw pythonPositionalTypeError("format_international", 1, arguments.length);
  }
  assertPhoneNumber(phone);
  return formatInternational(phone);
}

function formatNational(phone: PhoneNumber): string {
  const parsed = phoneNumberObjects.get(phone);
  if (parsed) {
    return parsed.formatNational();
  }
  if (possiblePhoneNumbers.has(phone) && phone.calling_code === 1 && /^\d{7}$/.test(phone.national_number)) {
    return `${phone.national_number.slice(0, 3)}-${phone.national_number.slice(3)}`;
  }
  return phone.national_number;
}

export function format_national(phone: PhoneNumber): string {
  if (arguments.length < 1) {
    throw pythonMissingRequiredArg("format_national", "phone");
  }
  if (arguments.length > 1) {
    throw pythonPositionalTypeError("format_national", 1, arguments.length);
  }
  assertPhoneNumber(phone);
  return formatNational(phone);
}

function numberType(phone: PhoneNumber): number {
  const type = phoneNumberObjects.get(phone)?.getType();
  return type ? NUMBER_TYPE_MAP[type] ?? NumberType.UNKNOWN : NumberType.UNKNOWN;
}

export function number_type(phone: PhoneNumber): number {
  if (arguments.length < 1) {
    throw pythonMissingRequiredArg("number_type", "phone");
  }
  if (arguments.length > 1) {
    throw pythonPositionalTypeError("number_type", 1, arguments.length);
  }
  assertPhoneNumber(phone);
  return numberType(phone);
}

function isNumberMatch(
  a: string | PhoneNumber,
  b: string | PhoneNumber,
  default_region: string | null = null,
): number {
  const first = a instanceof PhoneNumber ? a : parsePhoneForMatch(a, default_region);
  const second = b instanceof PhoneNumber ? b : parsePhoneForMatch(b, default_region);
  if (!first || !second) {
    return MatchType.NOT_A_NUMBER;
  }
  if (first.e164 === second.e164) {
    if (first.extension === second.extension) {
      return MatchType.EXACT_MATCH;
    }
    if (first.extension && second.extension) {
      return MatchType.NO_MATCH;
    }
    return MatchType.SHORT_NSN_MATCH;
  }
  if (first.calling_code === second.calling_code && first.national_number === second.national_number) {
    return MatchType.NSN_MATCH;
  }
  if (
    first.calling_code === second.calling_code &&
    (first.national_number.endsWith(second.national_number) ||
      second.national_number.endsWith(first.national_number))
  ) {
    return MatchType.SHORT_NSN_MATCH;
  }
  return MatchType.NO_MATCH;
}

export function is_number_match(
  a: string | PhoneNumber,
  b: string | PhoneNumber,
  default_region: string | null = null,
): number {
  if (arguments.length === 0) {
    throw pythonMissingRequiredArgs("is_number_match", ["a", "b"]);
  }
  if (arguments.length === 1) {
    throw pythonMissingRequiredArg("is_number_match", "b");
  }
  if (arguments.length > 3) {
    throw pythonRangePositionalTypeError("is_number_match", 2, 3, arguments.length);
  }
  return isNumberMatch(a, b, default_region);
}

function validateConfidenceThreshold(value: number): number {
  const threshold = Number(value);
  if (!Number.isFinite(threshold) || threshold < 0 || threshold > 1) {
    throw valueError("confidence_threshold must be between 0.0 and 1.0");
  }
  return threshold;
}

function emitRolodexterWarning(message: string): void {
  if (typeof process === "undefined" || typeof process.emit !== "function") {
    return;
  }
  const warning = new Error(message);
  warning.name = "RolodexterWarning";
  process.emit("rolodexterWarning" as "warning", warning);
}

function emitRolodexterWarnings(warnings: readonly string[]): void {
  for (const warning of warnings) {
    emitRolodexterWarning(warning);
  }
}

function asCountryCode(region: string | null | undefined): CountryCode | undefined {
  return region ? (region.toUpperCase() as CountryCode) : undefined;
}

function preprocessPhoneRaw(raw: string): string {
  let text = raw.trim();
  if (TEL_URI_RE.test(text)) {
    text = text.replace(TEL_URI_RE, "");
    const extMatch = TEL_EXT_RE.exec(text);
    const extSuffix = extMatch ? ` ext ${extMatch[1]}` : "";
    text = text.replace(TEL_PARAMS_RE, "") + extSuffix;
  }
  text = text.replace(EXTENSION_RE, " ext $1");

  const dialout = DIALOUT_RE.exec(text);
  if (dialout && text.length > dialout[0].length + 5) {
    text = `+${text.slice(dialout[0].length)}`;
  }
  const extensionMatch = /\s+ext\s+\d+$/i.exec(text);
  const extensionText = extensionMatch?.[0] ?? "";
  const numberText = extensionText ? text.slice(0, -extensionText.length) : text;
  if (/\d/.test(numberText)) {
    text = numberText.replace(/[A-Za-z]/g, (letter) => PHONE_ALPHA_MAP[letter.toUpperCase()] ?? letter) + extensionText;
  }
  return text;
}

function parsePhoneObject(raw: string, defaultRegion: string | null | undefined): LibPhoneNumber | undefined {
  if (typeof raw !== "string") {
    return undefined;
  }
  const text = preprocessPhoneRaw(raw);
  if (!text) {
    return undefined;
  }
  try {
    const parsed = parsePhoneNumberFromString(text, asCountryCode(defaultRegion));
    return parsed?.isPossible() ? parsed : undefined;
  } catch {
    return undefined;
  }
}

function wrapPhoneNumber(parsed: LibPhoneNumber, raw: string): PhoneNumber {
  return new PhoneNumber(
    Number.parseInt(parsed.countryCallingCode, 10),
    String(parsed.nationalNumber),
    raw,
    parsed.ext ?? null,
    parsed,
  );
}

function parseNanpLocalFallback(raw: string, defaultRegion: string | null | undefined): PhoneNumber | null {
  if ((defaultRegion ?? "").toUpperCase() !== "US") {
    return null;
  }
  if (typeof raw !== "string") {
    return null;
  }
  const digits = preprocessPhoneRaw(raw).replace(/\D/g, "");
  if (digits.length !== 7) {
    return null;
  }
  const phone = new PhoneNumber(1, digits, raw, null);
  possiblePhoneNumbers.add(phone);
  return phone;
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

function loadDefaultPatterns(): PatternData {
  try {
    const path = fileURLToPath(new URL("./patterns.json", moduleUrl));
    return JSON.parse(readFileSync(path, "utf8")) as PatternData;
  } catch (error) {
    throw new PatternLoadError(`Failed to load bundled patterns: ${String(error)}`);
  }
}

function loadPatternFile(path: string): PatternData {
  try {
    return JSON.parse(readFileSync(path, "utf8")) as PatternData;
  } catch (error) {
    throw new PatternLoadError(`Failed to load patterns from ${path}: ${String(error)}`);
  }
}

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

/** @internal */
export function loadCachedLanguage(langCode: string, options: { cache_dir?: string } = {}): LanguageData | undefined {
  for (const dir of getAllCacheDirs(options)) {
    const path = join(dir, `${langCode}.json`);
    if (!existsSync(path)) {
      continue;
    }
    try {
      return JSON.parse(readFileSync(path, "utf8")) as LanguageData;
    } catch {
      continue;
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
      const langCode = item.slice(0, -5);
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

function valueError(message: string): Error {
  const error = new Error(message);
  error.name = "ValueError";
  return error;
}

function attributeError(message: string): Error {
  const error = new Error(message);
  error.name = "AttributeError";
  return error;
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
    if (patterns !== null && patterns !== undefined && !isPlainObject(patterns)) {
      throw attributeError(`'${pythonTypeName(patterns)}' object has no attribute 'get'`);
    }
    this.#data = patterns ?? (patternsPath ? loadPatternFile(patternsPath) : loadDefaultPatterns());
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
    for (const [alias, canonical] of Object.entries(overrides)) {
      const key = normalizeAlias(alias);
      this.#reverseIndex.set(key, canonical);
      if (!this.#aliasSet.has(key)) {
        this.#aliasSet.add(key);
        this.#aliases.push(key);
      }
    }
  }
}

export class MappingResult {
  readonly normalized: Record<string, unknown>;
  readonly unmapped: Record<string, unknown>;
  readonly field_matches: readonly FieldMatch[];
  readonly warnings: readonly string[];
  #index?: Map<string, FieldMatch>;

  constructor(
    normalized: Record<string, unknown>,
    unmapped: Record<string, unknown>,
    field_matches: Iterable<FieldMatch>,
    warnings?: Iterable<string>,
  ) {
    if (arguments.length === 0) {
      throw new TypeError("MappingResult.__init__() missing 3 required positional arguments: 'normalized', 'unmapped', and 'field_matches'");
    }
    if (arguments.length === 1) {
      throw new TypeError("MappingResult.__init__() missing 2 required positional arguments: 'unmapped' and 'field_matches'");
    }
    if (arguments.length === 2) {
      throw new TypeError("MappingResult.__init__() missing 1 required positional argument: 'field_matches'");
    }
    if (arguments.length > 4) {
      throw new TypeError(`MappingResult.__init__() takes from 4 to 5 positional arguments but ${arguments.length + 1} were given`);
    }
    this.normalized = normalized;
    this.unmapped = unmapped;
    this.field_matches = Object.freeze([...field_matches]);
    this.warnings = Object.freeze([...(warnings ?? [])]);
    lockPythonFrozenFields(this, ["normalized", "unmapped", "field_matches", "warnings"]);
  }

  get matched_count(): number {
    return this.field_matches.filter(isMatched).length;
  }

  get unmatched_count(): number {
    return this.field_matches.length - this.matched_count;
  }

  get match_rate(): number {
    return this.field_matches.length === 0 ? 0 : this.matched_count / this.field_matches.length;
  }

  get_match(originalHeader: string): FieldMatch | null {
    if (!this.#index) {
      this.#index = new Map(this.field_matches.map((match) => [match.original, match]));
    }
    return this.#index.get(originalHeader) ?? null;
  }

  explain(): string {
    const lines = [
      `Mapping: ${this.matched_count} matched, ${this.unmatched_count} unmatched (match rate ${Math.round(this.match_rate * 100)}%)`,
    ];
    for (const match of this.field_matches) {
      const arrow = isMatched(match) ? "->" : " x";
      lines.push(
        `  ${pyRepr(match.original)} ${arrow} ${match.canonical} [${match.strategy}, conf=${match.confidence.toFixed(2)}]`,
      );
    }
    if (this.warnings.length > 0) {
      lines.push("Warnings:");
      for (const warning of this.warnings) {
        lines.push(`  ! ${warning}`);
      }
    }
    return lines.join("\n");
  }

  get_all_phones(): string[] {
    const phones: string[] = [];
    for (const key of PHONE_FIELDS) {
      const value = this.normalized[key];
      if (Array.isArray(value)) {
        phones.push(...value.map(pyString));
      } else if (value != null) {
        phones.push(pyString(value));
      }
    }
    return [...new Set(phones)];
  }

  to_dict(): Record<string, unknown> {
    const matched = this.matched_count;
    const total = this.field_matches.length;
    return {
      normalized: { ...this.normalized },
      unmapped: { ...this.unmapped },
      match_rate: Number((total === 0 ? 0 : matched / total).toFixed(4)),
      matched,
      unmatched: total - matched,
      warnings: [...this.warnings],
      details: this.field_matches.map((match) => ({
        original: match.original,
        canonical: match.canonical,
        confidence: match.confidence,
        strategy: match.strategy,
        service: match.service,
      })),
    };
  }

  toString(): string {
    const matches = `[${this.field_matches.map((match) => match.toString()).join(", ")}]`;
    return `MappingResult(normalized=${pythonLiteral(this.normalized)}, unmapped=${pythonLiteral(this.unmapped)}, field_matches=${matches}, warnings=${pythonLiteral(this.warnings)})`;
  }
}

type MappingMatches = Record<string, FieldMatch> & {
  get(header: string): FieldMatch | null;
  set(header: string, match: FieldMatch): MappingMatches;
  entries(): IterableIterator<[string, FieldMatch]>;
  items(): IterableIterator<[string, FieldMatch]>;
  [Symbol.iterator](): IterableIterator<[string, FieldMatch]>;
};

function makeMappingMatches(
  source: Map<string, FieldMatch> | Record<string, FieldMatch> | Iterable<[string, FieldMatch]> = {},
): MappingMatches {
  const out = {} as MappingMatches;
  const entries: Iterable<[string, FieldMatch]> = source instanceof Map
    ? source
    : typeof (source as Iterable<[string, FieldMatch]>)[Symbol.iterator] === "function"
      ? source as Iterable<[string, FieldMatch]>
      : Object.entries(source as Record<string, FieldMatch>);

  for (const [header, match] of entries) {
    out[header] = match;
  }

  Object.defineProperties(out, {
    get: {
      value(header: string): FieldMatch | null {
        return out[header] ?? null;
      },
    },
    set: {
      value(header: string, match: FieldMatch): MappingMatches {
        out[header] = match;
        return out;
      },
    },
    entries: {
      value: function* entriesIterator(): IterableIterator<[string, FieldMatch]> {
        yield* Object.entries(out) as Array<[string, FieldMatch]>;
      },
    },
    items: {
      value: function* itemsIterator(): IterableIterator<[string, FieldMatch]> {
        yield* Object.entries(out) as Array<[string, FieldMatch]>;
      },
    },
    [Symbol.iterator]: {
      value: function* matchesIterator(): IterableIterator<[string, FieldMatch]> {
        yield* Object.entries(out) as Array<[string, FieldMatch]>;
      },
    },
  });

  return out;
}

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
        out[header] = match.canonical;
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
const COMPILE_SCHEMA_OPTION_KEYS = new Set(["default_region", "strict", "confidence_threshold"]);
const MAP_DATAFRAME_OPTION_KEYS = new Set(["default_region", "normalize", "strict", "confidence_threshold"]);

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

function normalizedCandidates(header: string): string[] {
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

  if (h.includes(".")) {
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

  const indexed = /^(.+?)\s+\d+\s*(?:[-\u2013\u2014]\s*)?(.+)$/.exec(h);
  if (indexed) {
    const group = indexed[1]?.trim().replace(/[\s-]+/g, "_").toLowerCase();
    const prop = indexed[2]?.trim().replace(/[\s-]+/g, "_").toLowerCase();
    if (group && prop) {
      out.push(`${group}_${prop}`, prop, group);
    }
  }

  const numStripped = uscore.replace(/_\d+/g, "").replace(/_+/g, "_").replace(/^_+|_+$/g, "");
  if (numStripped && numStripped !== uscore) {
    out.push(numStripped);
  }

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

  for (const candidate of [...out]) {
    if (candidate.endsWith("_id")) {
      const base = candidate.slice(0, -3);
      if (base && !out.includes(base)) {
        out.push(base);
      }
      for (const prefix of VENDOR_PREFIXES) {
        if (base.startsWith(prefix)) {
          const inner = base.slice(prefix.length);
          if (inner && !out.includes(inner)) {
            out.push(inner);
          }
        }
      }
    }
  }

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
  if (PYTHON_FUZZY_COMPAT.has(clean)) {
    const verdict = PYTHON_FUZZY_COMPAT.get(clean);
    return verdict ? fieldMatch(header, verdict.canonical, verdict.confidence, "fuzzy") : undefined;
  }
  if (clean === "reply_to_email") {
    return undefined;
  }
  if (clean === "repyto") {
    return fieldMatch(header, "owner", FUZZY_HIGH_CONFIDENCE, "fuzzy");
  }
  if (clean === "ownerid") {
    return fieldMatch(header, "owner", FUZZY_LOW_CONFIDENCE, "fuzzy");
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
  return fieldMatch(
    header,
    canonical,
    confidenceScore >= 90 ? FUZZY_HIGH_CONFIDENCE : FUZZY_LOW_CONFIDENCE,
    "fuzzy",
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
    for (const candidate of normalizedCandidates(header)) {
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

function normalizePhone(value: unknown, defaultRegion: string | null | undefined): unknown {
  if (typeof value !== "string") {
    return value;
  }
  const raw = value.trim();
  if (!raw) {
    return value;
  }
  const parsed = parse(raw, defaultRegion ?? null);
  if (parsed) {
    return parsed.e164;
  }
  return value;
}

function isPossiblePhone(value: string, defaultRegion: string | null | undefined): boolean {
  return parse(value, defaultRegion ?? null) !== null;
}

function titleWord(word: string): string {
  if (!word) {
    return word;
  }
  const lower = word.toLowerCase();
  if (/^\d+(st|nd|rd|th)$/.test(lower)) {
    return lower;
  }
  if (lower.startsWith("mc") && lower.length > 2) {
    return `Mc${lower[2]?.toUpperCase() ?? ""}${lower.slice(3)}`;
  }
  return `${lower.slice(0, 1).toUpperCase()}${lower.slice(1)}`;
}

function smartTitleCase(value: string): string {
  return value
    .split(/\s+/)
    .map((word) => {
      if (word !== word.toUpperCase() && word !== word.toLowerCase() && /[A-Z]/.test(word.slice(1))) {
        return word;
      }
      if (word.includes("'")) {
        const [first = "", ...rest] = word.split("'");
        return [titleWord(first), ...rest.map((part) => (part.length > 1 ? titleWord(part) : part.toLowerCase()))].join("'");
      }
      return titleWord(word);
    })
    .join(" ");
}

const NAME_PARTICLES = new Set([
  "af",
  "das",
  "da",
  "de",
  "del",
  "der",
  "des",
  "di",
  "du",
  "el",
  "la",
  "op",
  "ten",
  "ter",
  "van",
  "von",
  "y",
  "zum",
  "zur",
]);

const NAME_TITLES = new Map([
  ["capt", "Capt"],
  ["capt.", "Capt."],
  ["dr", "Dr"],
  ["dr.", "Dr."],
  ["hon", "Hon"],
  ["hon.", "Hon."],
  ["mr", "Mr"],
  ["mr.", "Mr."],
  ["mrs", "Mrs"],
  ["mrs.", "Mrs."],
  ["ms", "Ms"],
  ["ms.", "Ms."],
  ["miss", "Miss"],
  ["dame", "Dame"],
  ["prof", "Prof"],
  ["prof.", "Prof."],
  ["rev", "Rev"],
  ["rev.", "Rev."],
  ["sir", "Sir"],
  ["mx", "Mx"],
  ["st", "St"],
  ["st.", "St."],
]);

const NAME_SUFFIXES = new Map([
  ["jr", "Jr"],
  ["jr.", "Jr."],
  ["md", "M.D."],
  ["m.d.", "M.d."],
  ["cpa", "Cpa"],
  ["sr", "Sr"],
  ["sr.", "Sr."],
  ["ii", "II"],
  ["iii", "III"],
  ["iv", "IV"],
  ["v", "V"],
  ["phd", "Ph.D."],
  ["ph.d.", "Ph.d."],
]);

function nameWord(word: string, index = 0): string {
  const lower = word.toLowerCase();
  if (index > 0 && lower === "and") {
    return "and";
  }
  if (NAME_TITLES.has(lower)) {
    return NAME_TITLES.get(lower) ?? word;
  }
  if (NAME_SUFFIXES.has(lower)) {
    return NAME_SUFFIXES.get(lower) ?? word;
  }
  if (index > 0 && NAME_PARTICLES.has(lower)) {
    return lower;
  }
  if (word.includes("@")) {
    return word.split("@").map((part) => nameWord(part, index)).join("@");
  }
  if (lower.startsWith("mac") && lower.length > 3) {
    return `Mac${lower[3]?.toUpperCase() ?? ""}${lower.slice(4)}`;
  }
  if (word.includes("-")) {
    return word.split("-").map((part) => nameWord(part, index)).join("-");
  }
  return smartTitleCase(word);
}

function smartNameCase(value: string): string {
  return value.split(/\s+/).map((word, index) => nameWord(word, index)).join(" ");
}

function splitNameNickname(value: string): { text: string; nickname: string } {
  let nickname = "";
  const text = value
    .replace(/(?:"([^"]+)"|\(([^)]+)\))/g, (_match, quoted: string | undefined, parenthesized: string | undefined) => {
      if (!nickname) {
        nickname = (quoted ?? parenthesized ?? "").trim();
      }
      return " ";
    })
    .replace(/\s+/g, " ")
    .trim();
  return { text, nickname };
}

function normalizeName(value: string): string {
  const { text, nickname } = splitNameNickname(value.trim());
  let normalized = text ? smartNameCase(text) : "";
  if (/^the\s+hon\.\s+/i.test(text)) {
    normalized = normalized.replace(/^The\s+Hon\.\s+/, "the Hon. ");
  } else if (/^the\s+hon\s+/i.test(text)) {
    normalized = normalized.replace(/^The\s+Hon\s+/, "the Hon ");
  } else if (/^the\s+honorable\s+/i.test(text)) {
    normalized = normalized.replace(/^The\s+Honorable\s+/, "the Honorable ");
  } else if (text.includes(",")) {
    const parsed = parseNameParts(text, "");
    const components = [parsed.title, parsed.first, parsed.middle, parsed.last, parsed.suffix]
      .filter(Boolean)
      .map((part, index) => part.split(/\s+/).map((word, wordIndex) => nameWord(word, index + wordIndex)).join(" "));
    normalized = components.join(" ");
  }
  if (!nickname) {
    return normalized || value;
  }
  const normalizedNickname = nickname.toLowerCase();
  return normalized ? `${normalized} (${normalizedNickname})` : `(${normalizedNickname})`;
}

function consumeNameTitles(parts: string[]): string {
  const titles: string[] = [];
  if (
    parts.length >= 2 &&
    parts[0]?.toLowerCase() === "the" &&
    ["hon", "hon.", "honorable"].includes(parts[1]?.toLowerCase() ?? "")
  ) {
    titles.push(parts.shift() ?? "");
    titles.push(parts.shift() ?? "");
    return titles.join(" ");
  }
  if (
    parts.length >= 2 &&
    parts[0]?.toLowerCase() === "his" &&
    parts[1]?.toLowerCase() === "excellency"
  ) {
    titles.push(parts.shift() ?? "");
    titles.push(parts.shift() ?? "");
    return titles.join(" ");
  }
  if (
    parts.length >= 3 &&
    ["mr", "mr."].includes(parts[0]?.toLowerCase() ?? "") &&
    parts[1]?.toLowerCase() === "and" &&
    ["mrs", "mrs."].includes(parts[2]?.toLowerCase() ?? "")
  ) {
    titles.push(parts.shift() ?? "");
    titles.push(parts.shift() ?? "");
    titles.push(parts.shift() ?? "");
    return titles.join(" ");
  }
  while (parts.length > 0 && NAME_TITLES.has((parts[0] ?? "").toLowerCase())) {
    titles.push(parts.shift() ?? "");
  }
  return titles.join(" ");
}

function consumeNameSuffix(parts: string[]): string {
  if (parts.length === 0) {
    return "";
  }
  const lastLower = (parts.at(-1) ?? "").toLowerCase();
  if (!NAME_SUFFIXES.has(lastLower)) {
    return "";
  }
  return parts.pop() ?? "";
}

function parseNameParts(text: string, nickname: string): Record<string, string> {
  const commaIndex = text.indexOf(",");
  if (commaIndex !== -1) {
    let last = text.slice(0, commaIndex).trim();
    const parts = text.slice(commaIndex + 1).trim().split(/\s+/).filter(Boolean).map((part) => part.replace(/,$/, ""));

    if (parts.length > 0 && parts.every((part) => NAME_SUFFIXES.has(part.toLowerCase()))) {
      const parsed = parseNameParts(last, nickname);
      parsed.suffix = parts.join(" ");
      return parsed;
    }

    const lastParts = last.split(/\s+/).filter(Boolean);
    const lastSuffix = consumeNameSuffix(lastParts);
    last = lastParts.join(" ");
    const title = consumeNameTitles(parts);
    const suffix = consumeNameSuffix(parts) || lastSuffix;
    return {
      title,
      first: parts[0] ?? "",
      middle: parts.slice(1).join(" "),
      last,
      suffix,
      nickname,
    };
  }

  const parts = text.split(/\s+/).filter(Boolean);
  const title = consumeNameTitles(parts);
  const suffix = consumeNameSuffix(parts);
  let first = parts[0] ?? "";
  let middle = "";
  let last = "";
  if (parts.length > 1) {
    const particleStart = parts.findIndex((part, index) => index > 0 && NAME_PARTICLES.has(part.toLowerCase()));
    if (particleStart > 0) {
      first = parts[0] ?? "";
      middle = parts.slice(1, particleStart).join(" ");
      last = parts.slice(particleStart).join(" ");
    } else {
      middle = parts.length > 2 ? parts.slice(1, -1).join(" ") : "";
      last = parts.at(-1) ?? "";
    }
  }
  if (parts.length === 1 && ["st", "st."].includes(title.toLowerCase())) {
    first = "";
    last = parts[0] ?? "";
  }

  return {
    title,
    first,
    middle,
    last,
    suffix,
    nickname,
  };
}

/** @internal */
export function normalizeValue(canonicalField: CanonicalFieldValue, value: unknown, default_region: string | null = null): unknown {
  const field = canonicalFieldValue(canonicalField);
  if (PHONE_FIELDS.has(field)) {
    return normalizePhone(value, default_region);
  }
  if (field === "email" && typeof value === "string") {
    return value.trim().toLowerCase();
  }
  if (NAME_FIELDS.has(field) && typeof value === "string") {
    const text = value.trim();
    return text ? normalizeName(text) : value;
  }
  if (ADDRESS_FIELDS.has(field) && typeof value === "string") {
    const text = value.trim().replace(/\s+/g, " ");
    return text ? smartTitleCase(text) : value;
  }
  if (field === "postal_code" && typeof value === "string") {
    const cleaned = value.trim().toUpperCase();
    return cleaned.replace(/^([A-Z]\d[A-Z])(\d[A-Z]\d)$/, "$1 $2");
  }
  if (BOOLEAN_FIELDS.has(field) && typeof value === "string") {
    const lower = value.trim().toLowerCase();
    if (["true", "yes", "1", "on", "y", "opted_in", "subscribed", "opt_in"].includes(lower)) {
      return true;
    }
    if (["false", "no", "0", "off", "n", "opted_out", "unsubscribed", "opt_out"].includes(lower)) {
      return false;
    }
    return value.trim();
  }
  if (LIST_FIELDS.has(field)) {
    if (Array.isArray(value)) {
      return value.map(pyString).map((item) => item.trim()).filter(Boolean);
    }
    if (typeof value !== "string") {
      return value;
    }
    const text = value.trim();
    if (!text) {
      return value;
    }
    if (text.startsWith("[")) {
      try {
        const parsed = JSON.parse(text) as unknown;
        if (Array.isArray(parsed)) {
          return parsed.map(pyString).map((item) => item.trim()).filter(Boolean);
        }
      } catch {
        // Fall through to separator-based parsing.
      }
    }
    const separator = text.includes(";") ? ";" : text.includes(",") ? "," : undefined;
    if (separator) {
      const items = text.split(separator).map((item) => item.trim()).filter(Boolean);
      if (items.length > 0) {
        return items;
      }
    }
    return [text];
  }
  if (SOCIAL_FIELDS.has(field) && typeof value === "string") {
    return value.trim();
  }
  if (typeof value === "string") {
    return value.trim();
  }
  return value;
}

export function normalize_value(
  canonicalField: CanonicalFieldValue,
  value: unknown,
  options: { default_region?: string | null } | null = {},
): unknown {
  if (arguments.length < 2) {
    throw arguments.length === 0
      ? pythonMissingRequiredArgs("normalize_value", ["canonical_field", "value"])
      : pythonMissingRequiredArg("normalize_value", "value");
  }
  if (arguments.length > 3 || (arguments.length === 3 && options !== null && options !== undefined && typeof options !== "object")) {
    throw pythonPositionalTypeError("normalize_value", 2, arguments.length);
  }
  return normalizeValue(canonicalField, value, options?.default_region ?? null);
}

export class PhoneNormalizer {
  normalize(
    value: unknown,
    options: { default_region?: string | null } | null = {},
  ): unknown {
    if (arguments.length < 1) {
      throw pythonMissingRequiredArg("PhoneNormalizer.normalize", "value");
    }
    return PhoneNormalizer.normalize(value, options);
  }

  static normalize(
    value: unknown,
    options: { default_region?: string | null } | null = {},
  ): unknown {
    if (arguments.length < 1) {
      throw pythonMissingRequiredArg("PhoneNormalizer.normalize", "value");
    }
    const rawOptions = options as unknown;
    if (rawOptions !== null && rawOptions !== undefined && typeof rawOptions !== "object") {
      throw pythonPositionalTypeError("PhoneNormalizer.normalize", 2, arguments.length + 1);
    }
    const region = (rawOptions as { default_region?: string | null } | null | undefined)?.default_region ?? null;
    return normalizePhone(value, region);
  }
}

export class EmailNormalizer {
  normalize(value: unknown): unknown {
    assertValueNormalizerArity("EmailNormalizer.normalize", arguments.length, 1);
    return EmailNormalizer.normalize(value);
  }

  static normalize(value: unknown): unknown {
    assertValueNormalizerArity("EmailNormalizer.normalize", arguments.length, 1);
    return typeof value === "string" ? value.trim().toLowerCase() : value;
  }
}

export class NameNormalizer {
  normalize(value: unknown): unknown {
    assertValueNormalizerArity("NameNormalizer.normalize", arguments.length, 2);
    return NameNormalizer.normalize(value);
  }

  parse(value: string): Record<string, string> {
    assertValueNormalizerArity("NameNormalizer.parse", arguments.length, 2);
    return NameNormalizer.parse(value);
  }

  static normalize(value: unknown): unknown {
    assertValueNormalizerArity("NameNormalizer.normalize", arguments.length, 2);
    if (typeof value !== "string") {
      return value;
    }
    const text = value.trim();
    return text ? normalizeName(text) : value;
  }

  static parse(value: string): Record<string, string> {
    assertValueNormalizerArity("NameNormalizer.parse", arguments.length, 2);
    if (typeof value !== "string") {
      throw attributeError(`'${pythonTypeName(value)}' object has no attribute 'strip'`);
    }
    const { text, nickname } = splitNameNickname(value.trim());
    return parseNameParts(text, nickname);
  }
}

export class AddressNormalizer {
  normalize(value: unknown): unknown {
    assertValueNormalizerArity("AddressNormalizer.normalize", arguments.length, 1);
    return AddressNormalizer.normalize(value);
  }

  static normalize(value: unknown): unknown {
    assertValueNormalizerArity("AddressNormalizer.normalize", arguments.length, 1);
    if (typeof value !== "string") {
      return value;
    }
    const text = value.trim().replace(/\s+/g, " ");
    return text ? smartTitleCase(text) : value;
  }
}

export class StringNormalizer {
  normalize(value: unknown): unknown {
    assertValueNormalizerArity("StringNormalizer.normalize", arguments.length, 1);
    return StringNormalizer.normalize(value);
  }

  static normalize(value: unknown): unknown {
    assertValueNormalizerArity("StringNormalizer.normalize", arguments.length, 1);
    return typeof value === "string" ? value.trim() : value;
  }
}

export class PostalCodeNormalizer {
  normalize(value: unknown): unknown {
    assertValueNormalizerArity("PostalCodeNormalizer.normalize", arguments.length, 2);
    return PostalCodeNormalizer.normalize(value);
  }

  static normalize(value: unknown): unknown {
    assertValueNormalizerArity("PostalCodeNormalizer.normalize", arguments.length, 2);
    return normalizeValue("postal_code", value);
  }
}

export class BooleanNormalizer {
  normalize(value: unknown): unknown {
    assertValueNormalizerArity("BooleanNormalizer.normalize", arguments.length, 2);
    return BooleanNormalizer.normalize(value);
  }

  static normalize(value: unknown): unknown {
    assertValueNormalizerArity("BooleanNormalizer.normalize", arguments.length, 2);
    return normalizeValue("email_opt_out", value);
  }
}

export class ListNormalizer {
  normalize(value: unknown): unknown {
    assertValueNormalizerArity("ListNormalizer.normalize", arguments.length, 1);
    return ListNormalizer.normalize(value);
  }

  static normalize(value: unknown): unknown {
    assertValueNormalizerArity("ListNormalizer.normalize", arguments.length, 1);
    return normalizeValue("tags", value);
  }
}

function mergeValue(target: Record<string, unknown>, key: string, value: unknown): void {
  if (LIST_FIELDS.has(key)) {
    if (!(key in target)) {
      target[key] = Array.isArray(value) ? [...value] : value;
      return;
    }
    const incoming = Array.isArray(value) ? value : [value];
    const existing = Array.isArray(target[key]) ? target[key] : [target[key]];
    const merged = [...existing];
    for (const item of incoming) {
      if (!pythonIncludes(merged, item)) {
        merged.push(item);
      }
    }
    target[key] = merged;
    return;
  }

  if (!(key in target)) {
    target[key] = value;
    return;
  }
  const existing = target[key];
  if (Array.isArray(existing)) {
    if (!pythonIncludes(existing, value)) {
      existing.push(value);
    }
  } else if (!pythonEquals(existing, value)) {
    target[key] = [existing, value];
  }
}

function pythonIncludes(values: unknown[], item: unknown): boolean {
  return values.some((value) => pythonEquals(value, item));
}

function pythonEquals(left: unknown, right: unknown): boolean {
  if (left === right) {
    return true;
  }
  if (left === null || left === undefined || right === null || right === undefined) {
    return left == null && right == null;
  }
  if (
    (typeof left === "boolean" && typeof right === "number") ||
    (typeof left === "number" && typeof right === "boolean")
  ) {
    return Number(left) === Number(right);
  }
  if (Array.isArray(left) && Array.isArray(right)) {
    return left.length === right.length && left.every((item, index) => pythonEquals(item, right[index]));
  }
  if (typeof left === "object" && typeof right === "object") {
    const leftEntries = Object.entries(left as Record<string, unknown>);
    const rightRecord = right as Record<string, unknown>;
    return leftEntries.length === Object.keys(rightRecord).length &&
      leftEntries.every(([key, value]) => Object.prototype.hasOwnProperty.call(rightRecord, key) && pythonEquals(value, rightRecord[key]));
  }
  return false;
}

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
    if (headerCacheMaxSize !== undefined && headerCacheMaxSize !== null && typeof headerCacheMaxSize !== "number") {
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
      let match = this.#resolve(key, value, region);

      if (isMatched(match) && match.confidence < threshold) {
        warnings.push(
          `${pyRepr(key)}: dropped low-confidence match to ${pyRepr(match.canonical)} (confidence ${match.confidence.toFixed(2)} < threshold ${threshold.toFixed(2)})`,
        );
        match = unknown(key);
      }

      fieldMatches.push(match);

      if (isMatched(match)) {
        const finalValue = normalizeValues ? normalizeValue(match.canonical, value, region) : value;
        if (
          PHONE_FIELDS.has(match.canonical) &&
          typeof finalValue === "string" &&
          finalValue.trim() &&
          !finalValue.startsWith("+")
        ) {
          warnings.push(
            `${pyRepr(key)}: phone value ${pyRepr(finalValue)} could not be normalized to E.164 (set a matching default_region?)`,
          );
        }
        mergeValue(normalized, match.canonical, finalValue);
      } else {
        unmapped[key] = value;
      }
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
    const rename = new Map<string, string>();
    const seenCanonical = new Map<string, number>();
    for (const column of columns) {
      const match = schema.matches.get(column);
      if (!match || !isMatched(match)) {
        continue;
      }
      const current = seenCanonical.get(match.canonical) ?? 0;
      seenCanonical.set(match.canonical, current + 1);
      const newName = current === 0 ? match.canonical : `${match.canonical}__${current + 1}`;
      if (current > 0) {
        emitRolodexterWarning(
          `map_dataframe: column ${pyRepr(column)} also maps to ${pyRepr(match.canonical)}; renamed to ${pyRepr(newName)} to avoid a collision`,
        );
      }
      rename.set(column, newName);
    }

    const warnings: string[] = [];
    if (isDataFrameLike(rows)) {
      const renameRecord = Object.fromEntries(rename);
      const renamed = rows.rename({ columns: renameRecord }) ?? rows.rename(renameRecord);
      const out = (renamed ?? rows) as DataFrameLike;
      if (normalizeValues) {
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
                finalValue.trim() &&
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

function flatten(payload: Record<string, unknown>, depth: number, prefix = "", current = 1): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(payload)) {
    const fullKey = prefix ? `${prefix}${key}` : key;
    if (value && typeof value === "object" && !Array.isArray(value) && current < depth) {
      Object.assign(result, flatten(value as Record<string, unknown>, depth, `${fullKey}.`, current + 1));
    } else {
      result[fullKey] = value;
    }
  }
  return result;
}

function extractEmbeddedPhones(
  normalized: Record<string, unknown>,
  unmapped: Record<string, unknown>,
  fieldMatches: FieldMatch[],
  warnings: string[],
  defaultRegion: string | null | undefined,
): void {
  const candidates: Array<[string, string]> = [];
  for (const [key, value] of Object.entries(unmapped)) {
    if (typeof value === "string" && value.length > 6) {
      candidates.push([key, value]);
    }
  }
  for (const [key, value] of Object.entries(normalized)) {
    if (!PHONE_FIELDS.has(key) && typeof value === "string" && value.length > 6) {
      candidates.push([key, value]);
    }
  }

  let foundTotal = 0;
  let warnedPayloadLimit = false;

  for (const [key, text] of candidates) {
    if (foundTotal >= EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD) {
      if (!warnedPayloadLimit) {
        warnings.push(
          `embedded phone extraction stopped after ${EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD} matches for this payload`,
        );
      }
      break;
    }

    let scanText = text;
    if (scanText.length > EMBEDDED_PHONE_MAX_TEXT_CHARS) {
      warnings.push(
        `${pyRepr(key)}: embedded phone scan truncated at ${EMBEDDED_PHONE_MAX_TEXT_CHARS} characters`,
      );
      scanText = scanText.slice(0, EMBEDDED_PHONE_MAX_TEXT_CHARS);
    }

    const remainingPayload = EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD - foundTotal;
    const fieldLimit = Math.min(EMBEDDED_PHONE_MAX_MATCHES_PER_FIELD, remainingPayload);
    const foundNumbers = findPhoneNumbersInText(scanText, asCountryCode(defaultRegion));

    for (const found of foundNumbers.slice(0, fieldLimit)) {
      mergeValue(normalized, "phone", found.number.number);
      fieldMatches.push(fieldMatch(key, "phone", HEURISTIC_CONFIDENCE, "embedded_phone"));
      foundTotal += 1;
    }

    if (foundNumbers.length > fieldLimit) {
      if (fieldLimit === EMBEDDED_PHONE_MAX_MATCHES_PER_FIELD) {
        warnings.push(
          `${pyRepr(key)}: embedded phone extraction stopped after ${EMBEDDED_PHONE_MAX_MATCHES_PER_FIELD} matches for this field`,
        );
      }
      if (foundTotal >= EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD && !warnedPayloadLimit) {
        warnings.push(
          `embedded phone extraction stopped after ${EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD} matches for this payload`,
        );
        warnedPayloadLimit = true;
      }
    }
  }
}

function isDataFrameLike(value: unknown): value is DataFrameLike {
  return !!value && typeof value === "object" && "columns" in value && typeof (value as DataFrameLike).rename === "function";
}

function dataframeColumns(value: DataFrameLike): string[] {
  const columns = value.columns;
  if (columns && typeof (columns as Iterable<unknown>)[Symbol.iterator] === "function") {
    return [...columns as Iterable<unknown>].map(String);
  }
  if (columns && typeof (columns as ArrayLike<unknown>).length === "number") {
    return Array.from(columns as ArrayLike<unknown>, String);
  }
  throw new TypeError("map_dataframe expects DataFrame-like columns to be iterable or array-like");
}

function dataframeColumnValues(frame: DataFrameLike, column: string): unknown {
  if (typeof frame.get === "function") {
    return frame.get(column);
  }
  return frame[column];
}

function mappedColumnValues(values: unknown, mapper: (value: unknown) => unknown): unknown {
  if (typeof values === "string") {
    return undefined;
  }
  if (Array.isArray(values)) {
    return values.map(mapper);
  }
  if (values && typeof values === "object" && typeof (values as { map?: unknown }).map === "function") {
    return (values as { map: (callback: (value: unknown) => unknown) => unknown }).map(mapper);
  }
  return undefined;
}

function setDataframeColumn(frame: DataFrameLike, column: string, values: unknown): void {
  if (typeof frame.set === "function") {
    frame.set(column, values);
    return;
  }
  frame[column] = values;
}

function iterableColumnValues(values: unknown): Iterable<unknown> {
  if (typeof values === "string") {
    return [];
  }
  if (values && typeof (values as Iterable<unknown>)[Symbol.iterator] === "function") {
    return values as Iterable<unknown>;
  }
  return [];
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

export const version = "2.9.1";
export const __version__ = version;
