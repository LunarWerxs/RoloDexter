// JavaScript half of the cross-language differential sweep.
//
// Reads a generated corpus on stdin, runs every case through the JS package,
// and writes a canonical JSON result to the path given as the first argument.
// The simplify/num contract below must match scripts/parity_sweep.py exactly,
// or the diff reports formatting differences instead of behavior.
import fs from "node:fs";

import * as r from "../packages/js/dist/src/index.js";

function decode(value) {
  if (value !== null && typeof value === "object" && !Array.isArray(value) && "$" in value) {
    const tag = value.$;
    if (tag === "float") return value.v;
    if (tag === "nan") return Number.NaN;
    if (tag === "inf") return Number.POSITIVE_INFINITY;
    if (tag === "ninf") return Number.NEGATIVE_INFINITY;
    throw new Error(`unknown marker ${tag}`);
  }
  if (Array.isArray(value)) return value.map(decode);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, decode(item)]));
  }
  return value;
}

// Numbers become text so 1 and 1.0 cannot look different across the two
// languages' JSON writers.
function num(value) {
  if (typeof value === "boolean") return value ? "true" : "false";
  if (Number.isNaN(value)) return "<nan>";
  if (value === Number.POSITIVE_INFINITY) return "<inf>";
  if (value === Number.NEGATIVE_INFINITY) return "<-inf>";
  return String(value);
}

// Object.fromEntries, never assignment: `out["__proto__"] = v` sets the
// prototype and drops the key, which would make this harness lose exactly the
// data it exists to compare.
function sortedObject(entries) {
  return Object.fromEntries(
    [...entries]
      .sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0))
      .map(([key, value]) => [key, simplify(value)]),
  );
}

function simplify(value) {
  if (value === null || value === undefined) return null;
  if (typeof value === "string") return value;
  if (typeof value === "boolean" || typeof value === "number") return { n: num(value) };
  if (Array.isArray(value)) return value.map(simplify);
  const name = value.constructor?.name;
  if (name === "MappingResult") {
    return {
      normalized: simplify(value.normalized),
      unmapped: simplify(value.unmapped),
      field_matches: simplify(value.field_matches),
      warnings: value.warnings.map(String),
    };
  }
  if (name === "FieldMatch") {
    return {
      original: value.original,
      canonical: simplify(value.canonical),
      confidence: simplify(value.confidence),
      strategy: value.strategy,
      service: simplify(value.service),
      is_matched: simplify(value.is_matched),
    };
  }
  if (name === "MappingSchema") {
    return {
      matches: simplify(value.matches),
      default_region: simplify(value.default_region),
      column_map: simplify(value.column_map()),
      to_dict: simplify(value.to_dict()),
    };
  }
  if (name === "PhoneNumber") {
    return {
      calling_code: simplify(value.calling_code),
      national_number: simplify(value.national_number),
      extension: simplify(value.extension),
      raw: simplify(value.raw),
      e164: simplify(value.e164),
      is_possible: simplify(value.is_possible),
      is_valid: simplify(value.is_valid),
      country_codes: simplify(value.country_codes),
    };
  }
  if (name === "PhoneNumberMatch") {
    return {
      start: simplify(value.start),
      end: simplify(value.end),
      raw_string: value.raw_string,
      number: simplify(value.number),
    };
  }
  if (typeof value === "object") return sortedObject(Object.entries(value));
  return { repr: String(value) };
}

function capture(fn) {
  try {
    return { ok: simplify(fn()) };
  } catch (error) {
    return { err: error?.name ?? "Error", msg: error?.message ?? String(error) };
  }
}

function phoneCase(item) {
  const value = decode(item.value);
  const region = item.default_region ?? null;
  switch (item.fn) {
    case "parse": return r.parse(value, region);
    case "format_e164": return r.format_e164(value, region);
    // These three take a parsed PhoneNumber, not a raw string.
    case "format_international": return r.format_international(r.parse(value, region));
    case "format_national": return r.format_national(r.parse(value, region));
    case "number_type": return r.number_type(r.parse(value, region));
    case "is_valid": return r.is_valid(value, region);
    case "is_number_match": return r.is_number_match(item.a, item.b, region);
    case "matcher":
      return [...new r.PhoneNumberMatcher(value, region, { max_matches: item.max_matches ?? null })];
    default: throw new Error(`unknown phone fn ${item.fn}`);
  }
}

function resultHelpers(item) {
  const result = new r.ContactMapper().map_payload(decode(item.payload), item.options ?? {});
  return {
    matched_count: result.matched_count,
    unmatched_count: result.unmatched_count,
    match_rate: result.match_rate,
    dict: result.to_dict(),
    explain: result.explain(),
    all_emails: result.get_all_emails(),
    all_phones: result.get_all_phones(),
    identity_keys: result.get_identity_keys(),
    get_match_fname: result.get_match("fname"),
    get_match_missing: result.get_match("nope"),
  };
}

function language(item) {
  const data = { ...r.generate_language(item.lang_code) };
  // Stamped per run, so it is noise here rather than behavior.
  delete data.generated_at;
  return data;
}

const corpus = JSON.parse(fs.readFileSync(0, "utf8"));
const out = {};

out.normalize = {};
for (const item of corpus.normalize) {
  out.normalize[item.id] = capture(() =>
    r.normalize_value(item.field, decode(item.value), { default_region: item.default_region ?? null }),
  );
}

out.schemas = {};
for (const item of corpus.schemas) {
  out.schemas[item.id] = capture(() =>
    new r.ContactMapper(item.mapper_options ?? {}).compile_schema(item.headers),
  );
}

out.payloads = {};
for (const item of corpus.payloads) {
  out.payloads[item.id] = capture(() =>
    new r.ContactMapper(item.mapper_options ?? {}).map_payload(decode(item.payload), item.options ?? {}),
  );
}

out.phones = {};
for (const item of corpus.phones) {
  out.phones[item.id] = capture(() => phoneCase(item));
}

out.objects = {};
for (const item of corpus.objects) {
  out.objects[item.id] = capture(() => resultHelpers(item));
}

out.languages = {};
for (const item of corpus.languages) {
  out.languages[item.id] = capture(() => language(item));
}

fs.writeFileSync(process.argv[2], JSON.stringify(out));
