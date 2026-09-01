// Phone parsing, formatting, matching and extraction.
// Extracted verbatim from index.ts, which re-exports every public name here.

import { findPhoneNumbersInText, getCountries, getCountryCallingCode, parsePhoneNumberFromString } from "libphonenumber-js/max";
import type { CountryCode, PhoneNumber as LibPhoneNumber } from "libphonenumber-js/max";
import { FieldMatch, HEURISTIC_CONFIDENCE, PHONE_FIELDS, fieldMatch, mergeValue } from "./_models.js";
import { attributeError, lockPythonFrozenFields, pyRepr, pyStrip, pythonMissingRequiredArg, pythonMissingRequiredArgs, pythonPositionalTypeError, pythonRangePositionalTypeError, pythonTypeName } from "./_pycompat.js";
import { require } from "./_runtime.js";
const phoneMetadata = require("libphonenumber-js/metadata.max.json") as {
  country_calling_codes?: Record<string, string[]>;
};
export const EMBEDDED_PHONE_MAX_TEXT_CHARS = 8192;
export const EMBEDDED_PHONE_MAX_MATCHES_PER_FIELD = 5;
export const EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD = 20;

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

function assertPhoneNumber(value: unknown): asserts value is PhoneNumber {
  if (!(value instanceof PhoneNumber)) {
    throw attributeError(`'${pythonTypeName(value)}' object has no attribute '_pn_obj'`);
  }
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
    if (requestedMax != null && typeof requestedMax !== "number") {
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

function asCountryCode(region: string | null | undefined): CountryCode | undefined {
  return region ? (region.toUpperCase() as CountryCode) : undefined;
}

function preprocessPhoneRaw(raw: string): string {
  let text = pyStrip(raw);
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

function normalizePhone(value: unknown, defaultRegion: string | null | undefined): unknown {
  if (typeof value !== "string") {
    return value;
  }
  const raw = pyStrip(value);
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

  // The payload cap is reached from two directions - a field that overflows it,
  // or a later candidate that finds it already spent - so both sites go through
  // one emitter that reports it exactly once.
  const warnPayloadLimit = (): void => {
    if (warnedPayloadLimit) {
      return;
    }
    warnings.push(
      `embedded phone extraction stopped after ${EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD} matches for this payload`,
    );
    warnedPayloadLimit = true;
  };

  for (const [key, text] of candidates) {
    if (foundTotal >= EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD) {
      warnPayloadLimit();
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
      if (foundTotal >= EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD) {
        warnPayloadLimit();
      }
    }
  }
}


// File-private in index.ts; exported here only because the split put
// their callers in another module. Not part of the package's public API -
// ./public.ts and ./core.ts still decide that.
export { extractEmbeddedPhones, isPossiblePhone, normalizePhone };
