// Co-located contract test for _phone.ts: parsing and formatting, number
// matching, the text matcher, and the embedded-phone extraction limits that
// map_payload relies on. The wider public-API cases live in
// test/mapper.phone.test.ts.
import assert from "node:assert/strict";
import { test } from "node:test";

import type { FieldMatch } from "./_models.js";
import {
  EMBEDDED_PHONE_MAX_MATCHES_PER_FIELD,
  EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD,
  MatchType,
  NumberType,
  PhoneNumber,
  PhoneNumberMatcher,
  extractEmbeddedPhones,
  format_e164,
  format_international,
  format_national,
  isPossiblePhone,
  is_number_match,
  is_valid,
  normalizePhone,
  number_type,
  parse,
} from "./_phone.js";

// Five distinct numbers libphonenumber accepts as valid.
const FIVE_NUMBERS = "+1 650-253-0000, +44 20 7946 0958, +33 6 12 34 56 78, +91 98765 43210, +49 151 12345678";

test("parse and the formatters agree on a valid international number", () => {
  const phone = parse("+1 650 253 0000");
  assert.ok(phone);
  assert.equal(phone.e164, "+16502530000");
  assert.equal(phone.is_valid, true);
  assert.equal(format_e164("+1 650 253 0000"), "+16502530000");
  assert.equal(format_international(phone), "+1 650-253-0000");
  assert.equal(format_national(phone), "(650) 253-0000");
  assert.equal(number_type(phone), NumberType.FIXED_LINE_OR_MOBILE);
  assert.equal(is_valid("+1 650 253 0000"), true);
});

test("parse reads dial-out prefixes, tel: URIs, vanity letters and extensions", () => {
  assert.equal(format_e164("011 44 20 7946 0958"), "+442079460958");
  assert.equal(format_e164("+1-800-FLOWERS"), "+18003569377");
  assert.equal(parse("tel:+1-650-253-0000;ext=123")?.extension, "123");
  assert.equal(parse("+1 555 123 4567 x 55")?.extension, "55");
});

test("parse returns null for text and non-strings, and falls back to a US local number", () => {
  assert.equal(parse("not a phone"), null);
  assert.equal(format_e164("not a phone", "GB"), null);
  assert.equal(is_valid("not a phone"), false);
  assert.equal(parse(42 as never, "US"), null);

  const local = parse("555-1212", "US");
  assert.ok(local);
  assert.equal(local.is_possible, true);
  assert.equal(local.is_valid, false);
  assert.equal(format_national(local), "555-1212");
  // The seven-digit fallback is US-only.
  assert.equal(parse("555-1212", "GB"), null);
});

test("is_number_match grades exact, extension-only, national and non matches", () => {
  assert.equal(is_number_match("+1 650 253 0000", "6502530000", "US"), MatchType.EXACT_MATCH);
  assert.equal(is_number_match("+12025551234 ext 42", "+12025551234"), MatchType.SHORT_NSN_MATCH);
  assert.equal(is_number_match("+12025551234 ext 42", "+12025551234 ext 43"), MatchType.NO_MATCH);
  assert.equal(is_number_match("2025551234", "5551234", "US"), MatchType.SHORT_NSN_MATCH);
  assert.equal(is_number_match(new PhoneNumber(1, "2025551234", "x"), "+12025551234"), MatchType.EXACT_MATCH);
  assert.equal(is_number_match("hello", "+15551234567"), MatchType.NOT_A_NUMBER);
});

test("the formatters reject anything that is not a PhoneNumber", () => {
  for (const format of [format_international, format_national, number_type]) {
    assert.throws(() => (format as unknown as (phone: unknown) => unknown)("+16502530000"), {
      name: "AttributeError",
      message: "'str' object has no attribute '_pn_obj'",
    });
  }
});

test("PhoneNumberMatcher finds numbers in text and honours max_matches", () => {
  const text = "Call +1 650-253-0000 or +44 20 7946 0958 today";
  const matcher = new PhoneNumberMatcher(text);
  assert.equal(matcher.length, 2);
  assert.equal(matcher.has_next(), true);
  const matches = [...matcher];
  assert.deepEqual(
    matches.map((match) => match.number.e164),
    ["+16502530000", "+442079460958"],
  );
  for (const match of matches) {
    assert.equal(text.slice(match.start, match.end), match.raw_string);
  }

  assert.equal(new PhoneNumberMatcher(text, null, { max_matches: 1 }).length, 1);
  assert.equal(new PhoneNumberMatcher(text, null, { max_matches: -3 }).length, 0);
  assert.equal(new PhoneNumberMatcher(42 as never).has_next(), false);
  assert.throws(() => new PhoneNumberMatcher(text, null, { max_matches: "2" as never }), TypeError);
});

test("normalizePhone and isPossiblePhone leave anything unparseable untouched", () => {
  assert.equal(normalizePhone("  +1 650 253 0000  ", null), "+16502530000");
  assert.equal(normalizePhone("555-1212", "US"), "+15551212");
  assert.equal(normalizePhone("hello", null), "hello");
  assert.equal(normalizePhone("   ", null), "   ");
  assert.equal(normalizePhone(42, null), 42);

  assert.equal(isPossiblePhone("+1 650 253 0000", undefined), true);
  assert.equal(isPossiblePhone("555-1212", "US"), true);
  assert.equal(isPossiblePhone("hello", null), false);
});

function extract(
  normalized: Record<string, unknown>,
  unmapped: Record<string, unknown>,
): { matches: FieldMatch[]; warnings: string[] } {
  const matches: FieldMatch[] = [];
  const warnings: string[] = [];
  extractEmbeddedPhones(normalized, unmapped, matches, warnings, "US");
  return { matches, warnings };
}

test("extractEmbeddedPhones scans unmapped text and non-phone fields only", () => {
  const normalized: Record<string, unknown> = {
    notes: "Office line +1 650-253-0000",
    fax: "+44 20 7946 0958",
  };
  const { matches, warnings } = extract(normalized, { memo: "short", about: "Reach me at +33 6 12 34 56 78" });
  assert.deepEqual(
    matches.map((match) => [match.original, match.canonical, match.strategy]),
    [
      ["about", "phone", "embedded_phone"],
      ["notes", "phone", "embedded_phone"],
    ],
  );
  assert.deepEqual(warnings, []);
  assert.ok(normalized.phone);
});

test("extractEmbeddedPhones caps matches per field and per payload, warning once each", () => {
  const perField = extract({}, { notes: `${FIVE_NUMBERS}, +44 7911 123456` });
  assert.equal(perField.matches.length, EMBEDDED_PHONE_MAX_MATCHES_PER_FIELD);
  assert.deepEqual(perField.warnings, [
    `'notes': embedded phone extraction stopped after ${EMBEDDED_PHONE_MAX_MATCHES_PER_FIELD} matches for this field`,
  ]);

  const unmapped: Record<string, unknown> = {};
  for (let index = 0; index < 5; index += 1) {
    unmapped[`note_${index}`] = FIVE_NUMBERS;
  }
  const perPayload = extract({}, unmapped);
  assert.equal(perPayload.matches.length, EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD);
  assert.deepEqual(perPayload.warnings, [
    `embedded phone extraction stopped after ${EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD} matches for this payload`,
  ]);
});
