// Date and per-field value normalizers, and the dispatch over them.
// Extracted verbatim from index.ts, which re-exports every public name here.

import { normalizeCountry, normalizeState } from "./_geo.js";
import { ADDRESS_FIELDS, BOOLEAN_FIELDS, DATE_FIELDS, LIST_FIELDS, NAME_FIELDS, PHONE_FIELDS, SOCIAL_FIELDS, canonicalFieldValue } from "./_models.js";
import type { CanonicalFieldValue } from "./_models.js";
import { normalizeName, parseNameParts, smartTitleCase, splitNameNickname } from "./_names.js";
import { normalizePhone } from "./_phone.js";
import { assertValueNormalizerArity, attributeError, pyCollapseSpace, pyRepr, pyString, pyStrip, pythonMissingRequiredArg, pythonMissingRequiredArgs, pythonPositionalTypeError, pythonTypeName } from "./_pycompat.js";

/** @internal */

// ── Date / country / state normalization (mirrors core.py) ───────────────
// These tables are generated from the Python source of truth; keep them in
// step, and let scripts/parity_probe.py be the thing that proves it.

const ISO_DATE_RE = /^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ].*)?$/;
const YMD_DATE_RE = /^(\d{4})[/.](\d{1,2})[/.](\d{1,2})$/;
const DMY_DATE_RE = /^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})$/;
const SHORT_YEAR_DATE_RE = /^\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2}$/;
// The time part of an ISO value: 09:30, 09:30:00, 09:30:00.123, then an
// optional zone (Z, +05:30, +0530, +05). Same as DateNormalizer._TIME_RE.
const ISO_TIME_RE = /^[T ](\d{1,2}):(\d{2})(?::(\d{2})(\.\d+)?)?\s*(?:([Zz])|([+-])(\d{2}):?(\d{2})?)?$/;
const MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
// Date fields that record a moment, so their time and zone are kept.
const TIMESTAMP_FIELDS: ReadonlySet<string> = new Set(["created_at", "updated_at", "last_contacted"]);

const pad = (n: number, width: number): string => String(n).padStart(width, "0");

function isoDate(year: number, month: number, day: number): string | undefined {
  if (month < 1 || month > 12 || day < 1) {
    return undefined;
  }
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const last = month === 2 && leap ? 29 : (MONTH_DAYS[month - 1] ?? 31);
  if (day > last) {
    return undefined;
  }
  return `${pad(year, 4)}-${pad(month, 2)}-${pad(day, 2)}`;
}

/** The ISO time and zone of `tail` (" 9:30+0530" -> "T09:30+05:30"), or undefined. */
function isoTime(tail: string): string | undefined {
  const m = ISO_TIME_RE.exec(tail);
  if (!m) {
    return undefined;
  }
  const hour = Number(m[1]);
  const minute = Number(m[2]);
  const second = m[3];
  if (hour > 23 || minute > 59 || (second !== undefined && Number(second) > 59)) {
    return undefined;
  }
  let out = `T${pad(hour, 2)}:${pad(minute, 2)}`;
  if (second !== undefined) {
    out += `:${second}${m[4] ?? ""}`;
  }
  if (m[5]) {
    out += "Z";
  } else if (m[6]) {
    const zoneHour = Number(m[7]);
    const zoneMinute = Number(m[8] ?? 0);
    if (zoneHour > 14 || zoneMinute > 59) {
      return undefined;
    }
    out += `${m[6]}${pad(zoneHour, 2)}:${pad(zoneMinute, 2)}`;
  }
  return out;
}

/**
 * Normalize an UNAMBIGUOUS date to ISO-8601. Refuses to guess: "03/04/2024" is
 * 3 April in most of the world and 4 March in the US, so it is returned
 * unchanged (and reported as a warning) rather than silently reordered.
 */
function normalizeDate(value: string, keepTime = false): string {
  const text = pyStrip(value);
  if (!text) {
    return value;
  }
  const ymd = ISO_DATE_RE.exec(text) ?? YMD_DATE_RE.exec(text);
  if (ymd) {
    const iso = isoDate(Number(ymd[1]), Number(ymd[2]), Number(ymd[3]));
    if (iso === undefined) {
      return value;
    }
    // With keepTime (the timestamp fields) the time and zone are kept; a time
    // part that cannot be read leaves the value unchanged rather than lost.
    const tail = text.slice(`${ymd[1]}-${ymd[2]}-${ymd[3]}`.length);
    if (keepTime && tail) {
      const time = isoTime(tail);
      return time === undefined ? value : iso + time;
    }
    return iso;
  }
  const dmy = DMY_DATE_RE.exec(text);
  if (dmy) {
    const first = Number(dmy[1]);
    const second = Number(dmy[2]);
    const year = Number(dmy[3]);
    if (first > 12 && second <= 12) {
      return isoDate(year, second, first) ?? value;
    }
    if (second > 12 && first <= 12) {
      return isoDate(year, first, second) ?? value;
    }
  }
  return value;
}

function isAmbiguousDate(value: string): boolean {
  const text = pyStrip(value);
  if (!text || normalizeDate(text) !== text) {
    return false;
  }
  const dmy = DMY_DATE_RE.exec(text);
  if (dmy && Number(dmy[1]) <= 12 && Number(dmy[2]) <= 12) {
    return true;
  }
  return SHORT_YEAR_DATE_RE.test(text);
}

// Deliberately permissive: this drives a *warning*, not a rejection, so it
// flags obvious junk ("n/a", "see notes", a bare name) without second-guessing
// unusual-but-valid addresses. No network lookup is performed.
const EMAIL_SHAPE_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/**
 * Warnings about a normalized value that silently degraded. Shared by
 * map_payload and map_dataframe so the two cannot drift on what counts as
 * suspicious.
 */
function valueWarnings(key: string, canonicalField: string, value: unknown): string[] {
  if (typeof value !== "string") {
    return [];
  }
  const text = pyStrip(value);
  if (!text) {
    return [];
  }
  if (PHONE_FIELDS.has(canonicalField) && !text.startsWith("+")) {
    return [
      `${pyRepr(key)}: phone value ${pyRepr(value)} could not be normalized to E.164 (set a matching default_region?)`,
    ];
  }
  if (canonicalField === "email" && !EMAIL_SHAPE_RE.test(text)) {
    return [`${pyRepr(key)}: value ${pyRepr(value)} does not look like an email address`];
  }
  if (DATE_FIELDS.has(canonicalField) && isAmbiguousDate(text)) {
    return [
      `${pyRepr(key)}: date ${pyRepr(value)} is ambiguous (day/month order or a two-digit year) and was left unchanged`,
    ];
  }
  return [];
}

const SUBSCRIBED_WORDS = ["subscribed", "opted_in", "opt_in"];
const UNSUBSCRIBED_WORDS = ["unsubscribed", "opted_out", "opt_out"];

/**
 * Normalize a boolean-field string value as the yes/no answer of `field`,
 * mirroring Python's BooleanNormalizer. Plain answers (yes/no, true/false,
 * 1/0, on/off, y/n) mean the same on every field; the subscription status
 * words are True for "subscribed" and False for "email_opt_out" when they say
 * "subscribed", the reverse when they say "unsubscribed", and stay text on
 * "verified".
 */
function normalizeBooleanFieldValue(value: string, field: string): boolean | string {
  const lower = pyStrip(value).toLowerCase();
  if (["true", "yes", "1", "on", "y"].includes(lower)) {
    return true;
  }
  if (["false", "no", "0", "off", "n"].includes(lower)) {
    return false;
  }
  if (field === "subscribed" || field === "email_opt_out") {
    if (SUBSCRIBED_WORDS.includes(lower)) {
      return field === "subscribed";
    }
    if (UNSUBSCRIBED_WORDS.includes(lower)) {
      return field === "email_opt_out";
    }
  }
  return pyStrip(value);
}

/** Normalize a list-field value (array, JSON array text, or delimited text) into a string array. */
function normalizeListFieldValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(pyString).map(pyStrip).filter(Boolean);
  }
  if (typeof value !== "string") {
    return value;
  }
  const text = pyStrip(value);
  if (!text) {
    return value;
  }
  if (text.startsWith("[")) {
    try {
      const parsed = JSON.parse(text) as unknown;
      if (Array.isArray(parsed)) {
        return parsed.map(pyString).map(pyStrip).filter(Boolean);
      }
    } catch {
      // Fall through to separator-based parsing.
    }
  }
  const separator = text.includes(";") ? ";" : text.includes(",") ? "," : undefined;
  if (separator) {
    const items = text.split(separator).map(pyStrip).filter(Boolean);
    if (items.length > 0) {
      return items;
    }
  }
  return [text];
}

export function normalizeValue(canonicalField: CanonicalFieldValue, value: unknown, default_region: string | null = null): unknown {
  const field = canonicalFieldValue(canonicalField);
  if (PHONE_FIELDS.has(field)) {
    return normalizePhone(value, default_region);
  }
  if (field === "email" && typeof value === "string") {
    return pyStrip(value).toLowerCase();
  }
  if (NAME_FIELDS.has(field) && typeof value === "string") {
    const text = pyStrip(value);
    return text ? normalizeName(text) : value;
  }
  if (ADDRESS_FIELDS.has(field) && typeof value === "string") {
    const text = pyCollapseSpace(pyStrip(value));
    return text ? smartTitleCase(text) : value;
  }
  if (field === "postal_code") {
    // A postcode that arrived as a whole number (JSON, a spreadsheet column
    // of digits) is cleaned as its digit text, as in Python.
    const text = typeof value === "number" && Number.isInteger(value) ? String(value) : value;
    if (typeof text === "string" && text) {
      const cleaned = pyStrip(text).toUpperCase();
      return cleaned.replace(/^([A-Z]\d[A-Z])(\d[A-Z]\d)$/, "$1 $2");
    }
    return text;
  }
  if (DATE_FIELDS.has(field) && typeof value === "string") {
    return normalizeDate(value, TIMESTAMP_FIELDS.has(field));
  }
  if (field === "country" && typeof value === "string") {
    return normalizeCountry(value);
  }
  if (field === "state" && typeof value === "string") {
    return normalizeState(value);
  }
  if (BOOLEAN_FIELDS.has(field) && typeof value === "string") {
    return normalizeBooleanFieldValue(value, field);
  }
  if (LIST_FIELDS.has(field)) {
    return normalizeListFieldValue(value);
  }
  if (SOCIAL_FIELDS.has(field) && typeof value === "string") {
    return pyStrip(value);
  }
  if (typeof value === "string") {
    return pyStrip(value);
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
  if (arguments.length > 3 || (arguments.length === 3 && options != null && typeof options !== "object")) {
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
    if (rawOptions != null && typeof rawOptions !== "object") {
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
    return typeof value === "string" ? pyStrip(value).toLowerCase() : value;
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
    const text = pyStrip(value);
    return text ? normalizeName(text) : value;
  }

  static parse(value: string): Record<string, string> {
    assertValueNormalizerArity("NameNormalizer.parse", arguments.length, 2);
    if (typeof value !== "string") {
      throw attributeError(`'${pythonTypeName(value)}' object has no attribute 'strip'`);
    }
    const { text, nickname } = splitNameNickname(pyStrip(value));
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
    const text = pyCollapseSpace(pyStrip(value));
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
    return typeof value === "string" ? pyStrip(value) : value;
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
    // Read as the "subscribed" field reads it, as Python's classmethod does.
    return normalizeValue("subscribed", value);
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


// File-private in index.ts; exported here only because the split put
// their callers in another module. Not part of the package's public API -
// ./public.ts and ./core.ts still decide that.
export { EMAIL_SHAPE_RE, valueWarnings };
