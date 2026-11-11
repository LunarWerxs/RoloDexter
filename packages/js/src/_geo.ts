// Country and state/province tables and their normalizers.
// Extracted verbatim from index.ts, which re-exports every public name here.

import { pyCollapseSpace, pyStrip } from "./_pycompat.js";
import { REGION_CODES, smartTitleCase } from "./_names.js";

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
const COUNTRY_ALPHA3: Record<string, string> = Object.assign(Object.create(null) as Record<string, string>, {
  "arg": "AR",
  "aus": "AU",
  "aut": "AT",
  "bel": "BE",
  "bgr": "BG",
  "bra": "BR",
  "can": "CA",
  "che": "CH",
  "chl": "CL",
  "chn": "CN",
  "col": "CO",
  "cze": "CZ",
  "deu": "DE",
  "dnk": "DK",
  "esp": "ES",
  "est": "EE",
  "fin": "FI",
  "fra": "FR",
  "gbr": "GB",
  "grc": "GR",
  "hkg": "HK",
  "hrv": "HR",
  "hun": "HU",
  "idn": "ID",
  "ind": "IN",
  "irl": "IE",
  "isr": "IL",
  "ita": "IT",
  "jpn": "JP",
  "kor": "KR",
  "ltu": "LT",
  "lux": "LU",
  "lva": "LV",
  "mex": "MX",
  "mys": "MY",
  "nld": "NL",
  "nor": "NO",
  "nzl": "NZ",
  "per": "PE",
  "phl": "PH",
  "pol": "PL",
  "prt": "PT",
  "rou": "RO",
  "rus": "RU",
  "sau": "SA",
  "sgp": "SG",
  "svk": "SK",
  "svn": "SI",
  "swe": "SE",
  "tha": "TH",
  "tur": "TR",
  "twn": "TW",
  "ukr": "UA",
  "usa": "US",
  "vnm": "VN",
  "zaf": "ZA",
});

const COUNTRY_NAMES: Record<string, string> = Object.assign(Object.create(null) as Record<string, string>, {
  "america": "US",
  "argentina": "AR",
  "australia": "AU",
  "austria": "AT",
  "belgium": "BE",
  "brasil": "BR",
  "brazil": "BR",
  "bulgaria": "BG",
  "canada": "CA",
  "chile": "CL",
  "china": "CN",
  "colombia": "CO",
  "croatia": "HR",
  "czech republic": "CZ",
  "czechia": "CZ",
  "denmark": "DK",
  "deutschland": "DE",
  "england": "GB",
  "espa\u00f1a": "ES",
  "estonia": "EE",
  "finland": "FI",
  "france": "FR",
  "germany": "DE",
  "great britain": "GB",
  "greece": "GR",
  "holland": "NL",
  "hong kong": "HK",
  "hungary": "HU",
  "india": "IN",
  "indonesia": "ID",
  "ireland": "IE",
  "israel": "IL",
  "italia": "IT",
  "italy": "IT",
  "japan": "JP",
  "korea": "KR",
  "latvia": "LV",
  "lithuania": "LT",
  "luxembourg": "LU",
  "malaysia": "MY",
  "mexico": "MX",
  "m\u00e9xico": "MX",
  "netherlands": "NL",
  "new zealand": "NZ",
  "norway": "NO",
  "peru": "PE",
  "philippines": "PH",
  "poland": "PL",
  "polska": "PL",
  "portugal": "PT",
  "republic of korea": "KR",
  "romania": "RO",
  "russia": "RU",
  "russian federation": "RU",
  "saudi arabia": "SA",
  "scotland": "GB",
  "singapore": "SG",
  "slovakia": "SK",
  "slovenia": "SI",
  "south africa": "ZA",
  "south korea": "KR",
  "spain": "ES",
  "sverige": "SE",
  "sweden": "SE",
  "switzerland": "CH",
  "taiwan": "TW",
  "thailand": "TH",
  "the netherlands": "NL",
  "turkey": "TR",
  "t\u00fcrkiye": "TR",
  "u.s.": "US",
  "u.s.a.": "US",
  "uk": "GB",
  "ukraine": "UA",
  "united kingdom": "GB",
  "united states": "US",
  "united states of america": "US",
  "usa": "US",
  "viet nam": "VN",
  "vietnam": "VN",
  "wales": "GB",
});

// Every officially assigned ISO 3166-1 alpha-2 code (249). A two-letter value
// is read as a country code only when it is one of these, so "UK" (a name in
// COUNTRY_NAMES) and "ZZ" are not taken for codes. Same list as
// CountryNormalizer._ALPHA2 in src/rolodexter/_geo.py.
const COUNTRY_ALPHA2: ReadonlySet<string> = new Set([
  "AD", "AE", "AF", "AG", "AI", "AL", "AM", "AO", "AQ", "AR", "AS", "AT",
  "AU", "AW", "AX", "AZ", "BA", "BB", "BD", "BE", "BF", "BG", "BH", "BI",
  "BJ", "BL", "BM", "BN", "BO", "BQ", "BR", "BS", "BT", "BV", "BW", "BY",
  "BZ", "CA", "CC", "CD", "CF", "CG", "CH", "CI", "CK", "CL", "CM", "CN",
  "CO", "CR", "CU", "CV", "CW", "CX", "CY", "CZ", "DE", "DJ", "DK", "DM",
  "DO", "DZ", "EC", "EE", "EG", "EH", "ER", "ES", "ET", "FI", "FJ", "FK",
  "FM", "FO", "FR", "GA", "GB", "GD", "GE", "GF", "GG", "GH", "GI", "GL",
  "GM", "GN", "GP", "GQ", "GR", "GS", "GT", "GU", "GW", "GY", "HK", "HM",
  "HN", "HR", "HT", "HU", "ID", "IE", "IL", "IM", "IN", "IO", "IQ", "IR",
  "IS", "IT", "JE", "JM", "JO", "JP", "KE", "KG", "KH", "KI", "KM", "KN",
  "KP", "KR", "KW", "KY", "KZ", "LA", "LB", "LC", "LI", "LK", "LR", "LS",
  "LT", "LU", "LV", "LY", "MA", "MC", "MD", "ME", "MF", "MG", "MH", "MK",
  "ML", "MM", "MN", "MO", "MP", "MQ", "MR", "MS", "MT", "MU", "MV", "MW",
  "MX", "MY", "MZ", "NA", "NC", "NE", "NF", "NG", "NI", "NL", "NO", "NP",
  "NR", "NU", "NZ", "OM", "PA", "PE", "PF", "PG", "PH", "PK", "PL", "PM",
  "PN", "PR", "PS", "PT", "PW", "PY", "QA", "RE", "RO", "RS", "RU", "RW",
  "SA", "SB", "SC", "SD", "SE", "SG", "SH", "SI", "SJ", "SK", "SL", "SM",
  "SN", "SO", "SR", "SS", "ST", "SV", "SX", "SY", "SZ", "TC", "TD", "TF",
  "TG", "TH", "TJ", "TK", "TL", "TM", "TN", "TO", "TR", "TT", "TV", "TW",
  "TZ", "UA", "UG", "UM", "US", "UY", "UZ", "VA", "VC", "VE", "VG", "VI",
  "VN", "VU", "WF", "WS", "YE", "YT", "ZA", "ZM", "ZW",
]);

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

const STATE_NAMES: Record<string, string> = Object.assign(Object.create(null) as Record<string, string>, {
  "alabama": "AL",
  "alaska": "AK",
  "alberta": "AB",
  "arizona": "AZ",
  "arkansas": "AR",
  "british columbia": "BC",
  "california": "CA",
  "colorado": "CO",
  "connecticut": "CT",
  "delaware": "DE",
  "district of columbia": "DC",
  "florida": "FL",
  "georgia": "GA",
  "hawaii": "HI",
  "idaho": "ID",
  "illinois": "IL",
  "indiana": "IN",
  "iowa": "IA",
  "kansas": "KS",
  "kentucky": "KY",
  "louisiana": "LA",
  "maine": "ME",
  "manitoba": "MB",
  "maryland": "MD",
  "massachusetts": "MA",
  "michigan": "MI",
  "minnesota": "MN",
  "mississippi": "MS",
  "missouri": "MO",
  "montana": "MT",
  "nebraska": "NE",
  "nevada": "NV",
  "new brunswick": "NB",
  "new hampshire": "NH",
  "new jersey": "NJ",
  "new mexico": "NM",
  "new york": "NY",
  "newfoundland and labrador": "NL",
  "north carolina": "NC",
  "north dakota": "ND",
  "northwest territories": "NT",
  "nova scotia": "NS",
  "nunavut": "NU",
  "ohio": "OH",
  "oklahoma": "OK",
  "ontario": "ON",
  "oregon": "OR",
  "pennsylvania": "PA",
  "prince edward island": "PE",
  "puerto rico": "PR",
  "quebec": "QC",
  "qu\u00e9bec": "QC",
  "rhode island": "RI",
  "saskatchewan": "SK",
  "south carolina": "SC",
  "south dakota": "SD",
  "tennessee": "TN",
  "texas": "TX",
  "utah": "UT",
  "vermont": "VT",
  "virginia": "VA",
  "washington": "WA",
  "west virginia": "WV",
  "wisconsin": "WI",
  "wyoming": "WY",
  "yukon": "YT",
});

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
