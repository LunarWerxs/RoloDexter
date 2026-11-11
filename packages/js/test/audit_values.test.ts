// Audit fixes for value cleaning: H1, H4, M1, M8 (postal), L12 and L13.
// Python twin: tests/test_audit_values.py; both assert the same outputs.
// (The JS phone half of M8 belongs to _phone.ts and index.ts; L27 is Python only.)
import assert from "node:assert/strict";
import { test } from "node:test";
import { AddressNormalizer, ContactMapper, NameNormalizer, normalize_value } from "../src/index.js";

// ── H1: consent columns and the field-aware yes/no cleaner ──────────────────

test("H1: marketing_consent=yes maps to subscribed true", () => {
  const result = new ContactMapper().map_payload({ marketing_consent: "yes" });
  assert.equal(result.normalized.subscribed, true);
  assert.deepEqual(Object.keys(result.normalized), ["subscribed"]);
});

test("H1: email_opt_out reads 'unsubscribed' as true", () => {
  assert.equal(normalize_value("email_opt_out", "unsubscribed"), true);
  assert.equal(normalize_value("email_opt_out", "Opted_Out "), true);
  assert.equal(normalize_value("email_opt_out", "opt_in"), false);
});

test("H1: subscribed reads 'unsubscribed' as false", () => {
  assert.equal(normalize_value("subscribed", "unsubscribed"), false);
  assert.equal(normalize_value("subscribed", "subscribed"), true);
});

test("H1: verified keeps the status words as text", () => {
  assert.equal(normalize_value("verified", "subscribed"), "subscribed");
  assert.equal(normalize_value("verified", " opted_out "), "opted_out");
  assert.equal(normalize_value("verified", "yes"), true);
});

test("H1: sms and gdpr consent never land on an email or phone field", () => {
  for (const header of ["sms_consent", "gdpr_consent"]) {
    const canonical = new ContactMapper().identify(header).canonical;
    assert.ok(!["email_opt_out", "email", "phone"].includes(canonical), `${header} -> ${canonical}`);
  }
});

// ── H4: address and state casing ────────────────────────────────────────────

test("H4: addresses keep codes, compass points and unit letters", () => {
  const cases: [string, string][] = [
    ["123 Main St, Springfield, IL 62704", "123 Main St, Springfield, IL 62704"],
    ["Apt 4B", "Apt 4B"],
    ["100 NW 5th Ave", "100 NW 5th Ave"],
    ["PO Box 12", "PO Box 12"],
    ["1 Main St, USA", "1 Main St, USA"],
    ["123 MAIN ST", "123 Main St"],
    ["123 MAIN ST, SPRINGFIELD, IL 62704", "123 Main St, Springfield, IL 62704"],
    ["100 NW 5TH AVE APT 4B", "100 NW 5th Ave Apt 4B"],
    ["PO BOX 12, WASHINGTON, DC 20001, USA", "PO Box 12, Washington, DC 20001, USA"],
    ["1 OAK CT, HARTFORD, CT 06101", "1 Oak Ct, Hartford, CT 06101"],
    ["LA JOLLA", "La Jolla"],
  ];
  for (const [raw, expected] of cases) {
    assert.equal(AddressNormalizer.normalize(raw), expected, raw);
    assert.equal(normalize_value("full_address", raw), expected, raw);
  }
});

test("H4: state keeps capitalised codes from outside North America", () => {
  const cases: [string, string][] = [
    ["NSW", "NSW"],
    ["QLD", "QLD"],
    ["VIC", "VIC"],
    ["NRW", "NRW"],
    ["SP", "SP"],
    ["D.C.", "D.C."],
    ["il", "IL"],
    ["bavaria", "Bavaria"],
  ];
  for (const [raw, expected] of cases) {
    assert.equal(normalize_value("state", raw), expected, raw);
  }
});

// ── M1: trailing particles, the Mac/Mc rule and the suffix table ────────────

test("M1: name casing matches Python", () => {
  const cases: [string, string][] = [
    ["Jennifer Le", "Jennifer Le"],
    ["Michael Do", "Michael Do"],
    ["David Du", "David Du"],
    ["Noa Bar", "Noa Bar"],
    ["jean le pen", "Jean le Pen"],
    ["Machado", "Machado"],
    ["Macias", "Macias"],
    ["MACHADO", "Machado"],
    ["mackenzie", "Mackenzie"],
    ["Mcdonald", "Mcdonald"],
    ["mcdonald", "McDonald"],
    ["MACARTHUR", "MacArthur"],
    ["MacArthur", "MacArthur"],
    ["macaulay", "MacAulay"],
    ["Macy", "Macy"],
    ["Mack", "Mack"],
    ["Jane Q. Doe, CPA", "Jane Q. Doe CPA"],
    ["jane doe m.d.", "Jane Doe M.D."],
    ["john doe ph.d.", "John Doe Ph.D."],
  ];
  for (const [raw, expected] of cases) {
    assert.equal(NameNormalizer.normalize(raw), expected, raw);
  }
});

// ── M8: numeric postal values (contract C3) ─────────────────────────────────

test("M8: a whole-number postcode is cleaned as its digit text", () => {
  assert.equal(normalize_value("postal_code", 94107), "94107");
  assert.equal(normalize_value("postal_code", 1.5), 1.5);
});

// ── L12: country codes ──────────────────────────────────────────────────────

test("L12: U.K. reads as UK; only real ISO codes are taken as codes", () => {
  const cases: [string, string][] = [
    ["U.K.", "GB"],
    ["UK", "GB"],
    ["u.s.", "US"],
    ["de", "DE"],
    ["ZZ", "ZZ"],
    ["xx", "xx"],
  ];
  for (const [raw, expected] of cases) {
    assert.equal(normalize_value("country", raw), expected, raw);
  }
});

// ── L13: timestamps keep their time; impossible days are not dates ──────────

test("L13: timestamp fields keep time and zone; impossible days stay unchanged", () => {
  const cases: [string, string, string][] = [
    ["created_at", "2024-03-15T09:30:00Z", "2024-03-15T09:30:00Z"],
    ["updated_at", "2024-3-5 9:30+0530", "2024-03-05T09:30+05:30"],
    ["last_contacted", "2024-03-15T09:30:00.123-08:00", "2024-03-15T09:30:00.123-08:00"],
    ["created_at", "2024-03-15", "2024-03-15"],
    ["created_at", "2024-03-15 9am", "2024-03-15 9am"],
    ["birthday", "2024-03-15T09:30:00Z", "2024-03-15"],
    ["birthday", "2024-02-31", "2024-02-31"],
    ["birthday", "31/02/2024", "31/02/2024"],
    ["birthday", "2023-02-29", "2023-02-29"],
    ["birthday", "2024-2-29", "2024-02-29"],
  ];
  for (const [field, raw, expected] of cases) {
    assert.equal(normalize_value(field, raw), expected, `${field} ${raw}`);
  }
});

// ── Sweep 2026-11-11: a name value is never emptied ─────────────────────────

test("a name value without a name is kept as written", () => {
  for (const raw of ["\\", "\"", "'", "​", "﻿", "\x00"]) {
    assert.equal(NameNormalizer.normalize(raw), raw, JSON.stringify(raw));
    assert.equal(normalize_value("last_name", `  ${raw} `), raw, JSON.stringify(raw));
  }
});

test("an infinite phone value's warning writes inf, as Python's repr does", () => {
  const { warnings } = new ContactMapper().map_payload({ Phone: Number.POSITIVE_INFINITY });
  assert.ok(warnings.some((w) => String(w).includes("phone value inf could not")), String(warnings));
});
