// Country and state/province tables and their normalizers.
// Extracted verbatim from index.ts, which re-exports every public name here.

import { pyCollapseSpace, pyStrip } from "./_pycompat.js";
import { REGION_CODES, smartTitleCase } from "./_names.js";
import { TABLES } from "./_tables.js";

// The three tables below are prototype-free, and that is load-bearing rather
// than stylistic.  They are indexed with contact data, and a plain object
// answers for keys nobody put in it: COUNTRY_NAMES["constructor"] is the
// Object function and COUNTRY_NAMES["__proto__"] is Object.prototype, so a row
// whose country column read "constructor" normalized to a *function* here and
// to the string "constructor" in Python.  Python dicts have no such inherited
// members, so this was a type confusion in JavaScript and a cross-language
// divergence at the same time.
//
// Only member names that survive the lookup's own .toLowerCase() can collide,
// which is why "__proto__" and "constructor" leaked and "toString" did not -
// a distinction far too subtle to leave standing as the reason it is safe.
// Object.create(null) removes the inherited keys instead of enumerating which
// ones happen to be reachable today, so a lookup added later is safe by
// construction.  This is the read-side counterpart of setOwnProperty() in
// _pycompat.ts, which already does the same job for writes.
const COUNTRY_ALPHA3: Record<string, string> = Object.assign(Object.create(null) as Record<string, string>, TABLES.geo.alpha3);

const COUNTRY_NAMES: Record<string, string> = Object.assign(Object.create(null) as Record<string, string>, TABLES.geo.country_names);

// Every officially assigned ISO 3166-1 alpha-2 code (249). A two-letter value
// is read as a country code only when it is one of these, so "UK" (a name in
// COUNTRY_NAMES) and "ZZ" are not taken for codes. Same list as
// CountryNormalizer._ALPHA2 in src/rolodexter/_geo.py.
const COUNTRY_ALPHA2: ReadonlySet<string> = new Set(TABLES.geo.alpha2);

function normalizeCountry(value: string): string {
  const text = pyCollapseSpace(pyStrip(value));
  if (!text) {
    return value;
  }
  const lowered = text.toLowerCase();
  const stripped = lowered.replace(/\./g, "");
  // "U.K." reads as "UK" does: the dotless form is looked up too.
  const named = COUNTRY_NAMES[lowered] ?? COUNTRY_NAMES[stripped];
  if (named !== undefined) {
    return named;
  }
  if (COUNTRY_ALPHA2.has(stripped.toUpperCase())) {
    return stripped.toUpperCase();
  }
  const alpha3 = COUNTRY_ALPHA3[stripped];
  if (alpha3 !== undefined) {
    return alpha3;
  }
  return text;
}

const STATE_NAMES: Record<string, string> = Object.assign(Object.create(null) as Record<string, string>, TABLES.geo.state_names);

function normalizeState(value: string): string {
  const text = pyCollapseSpace(pyStrip(value));
  if (!text) {
    return value;
  }
  const named = STATE_NAMES[text.toLowerCase()];
  if (named !== undefined) {
    return named;
  }
  if (REGION_CODES.has(text.toUpperCase())) {
    return text.toUpperCase();
  }
  // A region code from elsewhere written in capitals ("NSW", "QLD", "NRW",
  // "SP") is already right; title-casing it would damage it.
  if (/^[A-Z]{2,3}$/.test(text)) {
    return text;
  }
  return smartTitleCase(text);
}


// File-private in index.ts; exported here only because the split put
// their callers in another module. Not part of the package's public API -
// ./public.ts and ./core.ts still decide that.
export { normalizeCountry, normalizeState };
