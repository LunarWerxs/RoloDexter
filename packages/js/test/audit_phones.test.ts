// Audit group W2 (phones): H6 region-first dial-out, M8 7-digit and numeric values, L25 extensions.
import assert from "node:assert/strict";
import { test } from "node:test";

import { format_e164, normalizePhone, parse } from "../src/_phone.js";

const CASES: Array<[string, string | null, string]> = [
  ["011 234 5678", "ZA", "+27112345678"],
  ["011 2345 6789", "IN", "+911123456789"],
  ["0011 61 2 9999 0000", "AU", "+61299990000"],
  ["011 44 20 7946 0958", "US", "+442079460958"],
  ["011 44 20 7946 0958", null, "+442079460958"],
  ["00 44 20 7946 0958", null, "+442079460958"],
];

for (const [raw, region, expected] of CASES) {
  test(`H6 region ${region} parses ${raw} before the dial-out rewrite`, () => {
    assert.equal(format_e164(raw, region), expected);
  });
}

test("M8 seven-digit local number is not emitted as E.164", () => {
  assert.equal(format_e164("555-1234", "US"), null);
  assert.equal(parse("555-1234", "US"), null);
  assert.equal(normalizePhone("555-1234", "US"), "555-1234");
  assert.equal(format_e164("415-555-0100", "US"), "+14155550100");
});

test("M8 whole-number phone value is cleaned as its digit text", () => {
  assert.equal(normalizePhone(4155550100, "US"), "+14155550100");
});

test("L25 extension is kept as ;ext=", () => {
  assert.equal(format_e164("+1 415 555 0100 x123", null), "+14155550100;ext=123");
  assert.equal(format_e164("415 555 0100 ext 123", "US"), "+14155550100;ext=123");
  assert.equal(normalizePhone("+1 415 555 0100 x123", null), "+14155550100;ext=123");
});
