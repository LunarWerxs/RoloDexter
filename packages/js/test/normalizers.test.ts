// Value normalization that map_payload reaches through normalize_value:
// dates, countries, states, lists, booleans, and the "this value silently
// degraded" warnings. The Python suite covers these in
// tests/test_v211_fixes.py (TestDateNormalizer / TestCountryNormalizer /
// TestStateNormalizer); the TypeScript port had no equivalent, so a
// divergence here could only be caught by the parity probes at release time.
import assert from "node:assert/strict";
import { test } from "node:test";

import { ContactMapper, normalize_value } from "../src/index.js";

test("dates reach ISO-8601 only when the day/month order is unambiguous", () => {
  // A component over 12 can only be a day, so the order is knowable.
  assert.equal(normalize_value("birthday", "25/03/2024"), "2024-03-25");
  assert.equal(normalize_value("birthday", "13.05.2024"), "2024-05-13");
  // The mirror image: the *second* component is the one over 12.
  assert.equal(normalize_value("birthday", "05.13.2024"), "2024-05-13");

  // A leading four-digit year is unambiguous by construction, and is padded.
  assert.equal(normalize_value("birthday", "2024/3/5"), "2024-03-05");
  assert.equal(normalize_value("birthday", "2024-3-5"), "2024-03-05");
  assert.equal(normalize_value("birthday", "2024-01-15T09:30:00Z"), "2024-01-15");

  // Every date field shares the normalizer, not just birthday.
  assert.equal(normalize_value("created_at", "25/03/2024"), "2024-03-25");
  assert.equal(normalize_value("last_contacted", "25/03/2024"), "2024-03-25");
});

test("dates that would have to be guessed are returned untouched", () => {
  // 3 April in most of the world, 4 March in the US. Refuses to pick.
  assert.equal(normalize_value("birthday", "03/04/2024"), "03/04/2024");
  // "68" is 1968 or 2068; both are guesses.
  assert.equal(normalize_value("birthday", "12/11/68"), "12/11/68");
  // Out-of-range components fail the ISO build and fall back to the input
  // rather than emitting a nonsense "2024-13-01".
  assert.equal(normalize_value("birthday", "2024-13-01"), "2024-13-01");
  assert.equal(normalize_value("birthday", "2024-01-32"), "2024-01-32");
  assert.equal(normalize_value("birthday", "   "), "   ");
  assert.equal(normalize_value("birthday", "not a date"), "not a date");
});

test("date normalization is a reordering, not a calendar check", () => {
  // 31 February is not a real date, but rejecting it is the caller's job:
  // this normalizer only decides which component is the day. Pinned so a
  // future "helpful" validation cannot land here unnoticed.
  assert.equal(normalize_value("birthday", "31/02/2024"), "2024-02-31");
});

test("countries collapse to ISO alpha-2", () => {
  assert.equal(normalize_value("country", "United States"), "US");
  assert.equal(normalize_value("country", "deutschland"), "DE");
  // Already alpha-2, and alpha-2 written with dots.
  assert.equal(normalize_value("country", "de"), "DE");
  assert.equal(normalize_value("country", "u.s."), "US");
  // Alpha-3 is recognized too.
  assert.equal(normalize_value("country", "DEU"), "DE");
  assert.equal(normalize_value("country", "GBR"), "GB");
  // Unknown values survive rather than being blanked or guessed at.
  assert.equal(normalize_value("country", "Narnia"), "Narnia");
  assert.equal(normalize_value("country", "  "), "  ");
});

test("states collapse to US/Canadian codes", () => {
  assert.equal(normalize_value("state", "california"), "CA");
  assert.equal(normalize_value("state", "Ontario"), "ON");
  // Already a code, in either case.
  assert.equal(normalize_value("state", "ca"), "CA");
  assert.equal(normalize_value("state", "QC"), "QC");
  // Internal whitespace is collapsed before the lookup.
  assert.equal(normalize_value("state", "new  york"), "NY");
  // Anything outside those two countries is title-cased, not discarded.
  assert.equal(normalize_value("state", "Bavaria"), "Bavaria");
  assert.equal(normalize_value("state", "  "), "  ");
});

test("boolean fields coerce the usual opt-in/opt-out vocabulary", () => {
  assert.equal(normalize_value("email_opt_out", "yes"), true);
  assert.equal(normalize_value("email_opt_out", "NO "), false);
  assert.equal(normalize_value("email_opt_out", "opted_out"), false);
  assert.equal(normalize_value("subscribed", "1"), true);
  assert.equal(normalize_value("verified", "off"), false);
  // Anything else keeps its text rather than becoming a misleading false.
  assert.equal(normalize_value("email_opt_out", " maybe "), "maybe");
});

test("list fields accept arrays, JSON arrays, and delimited text", () => {
  assert.deepEqual(normalize_value("tags", ["x ", "", "y"]), ["x", "y"]);
  assert.deepEqual(normalize_value("tags", '["a", "b"]'), ["a", "b"]);
  // ";" wins over "," when both are present, so "b,c" stays one tag.
  assert.deepEqual(normalize_value("tags", "a;b,c"), ["a", "b,c"]);
  // Text that only looks like JSON falls back to separator parsing rather
  // than throwing.
  assert.deepEqual(normalize_value("tags", "[not json"), ["[not json"]);
  // A separator that yields nothing but empties keeps the original text.
  assert.deepEqual(normalize_value("tags", ",,,"), [",,,"]);
  // No separator at all is still a one-item list.
  assert.deepEqual(normalize_value("tags", "solo"), ["solo"]);
  // Empty and non-string values pass through untouched.
  assert.equal(normalize_value("tags", ""), "");
  assert.equal(normalize_value("tags", "   "), "   ");
  assert.equal(normalize_value("tags", 42), 42);
});

test("social and unclassified fields are trimmed, and non-strings pass through", () => {
  assert.equal(normalize_value("website", "  https://x.io  "), "https://x.io");
  assert.equal(normalize_value("linkedin", " in/ada "), "in/ada");
  // Nothing here is string-shaped, so every normalizer must hand it back
  // rather than calling .trim() on it.
  assert.equal(normalize_value("first_name", 42), 42);
  assert.equal(normalize_value("company", 42), 42);
  assert.equal(normalize_value("street", 42), 42);
  assert.equal(normalize_value("birthday", 42), 42);
  assert.equal(normalize_value("country", 42), 42);
  assert.equal(normalize_value("state", 42), 42);
  assert.equal(normalize_value("email_opt_out", 42), 42);
  assert.equal(normalize_value("first_name", null), null);
});

test("silently degraded values are reported as warnings", () => {
  const ambiguous = new ContactMapper().map_payload({ birthday: "03/04/2024" });
  assert.deepEqual(ambiguous.warnings, [
    "'birthday': date '03/04/2024' is ambiguous (day/month order or a two-digit year) and was left unchanged",
  ]);
  // The value itself is still passed through unchanged, not dropped.
  assert.equal(ambiguous.normalized.birthday, "03/04/2024");

  const twoDigitYear = new ContactMapper().map_payload({ birthday: "12/11/68" });
  assert.deepEqual(twoDigitYear.warnings, [
    "'birthday': date '12/11/68' is ambiguous (day/month order or a two-digit year) and was left unchanged",
  ]);

  const badEmail = new ContactMapper().map_payload({ email: "not-an-email" });
  assert.deepEqual(badEmail.warnings, [
    "'email': value 'not-an-email' does not look like an email address",
  ]);

  // A date that *could* be resolved is not warned about.
  const clean = new ContactMapper().map_payload({ birthday: "25/03/2024" });
  assert.deepEqual(clean.warnings, []);
  assert.equal(clean.normalized.birthday, "2024-03-25");

  // Neither is a blank or non-string value, which has nothing to degrade.
  assert.deepEqual(new ContactMapper().map_payload({ email: "   " }).warnings, []);
  assert.deepEqual(new ContactMapper().map_payload({ email: 42 }).warnings, []);
});
