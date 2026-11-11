// Audit fixes for header matching: H2, M9, M11 and non-ASCII headers.
// Python twin: tests/test_audit_matching.py; both assert the same verdicts.
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  ContactMapper,
  FUZZY_LENGTH_RATIO,
  FuzzyMatchStrategy,
  HeuristicMatchStrategy,
  NormalizedMatchStrategy,
  PatternRegistry,
} from "../src/index.js";

function verdict(header: string): [string, number, string] {
  const match = new ContactMapper().identify(header);
  return [match.canonical, match.confidence, match.strategy];
}

// ── H2: "Type" / "Label" / "Display Name" columns stay unmapped ─────────────

const QUALIFIER_HEADERS = [
  "E-mail 1 - Type",
  "E-mail 1 - Label",
  "Phone 1 - Type",
  "Phone 1 - Label",
  "Address 1 - Type",
  "Organization 1 - Type",
  "Website 1 - Type",
  "E-mail Type",
  "E-mail 2 Type",
  "E-mail Display Name",
  "E-mail 2 Display Name",
  "Phone Type",
  "Contact Type",
];

test("H2: qualifier columns are unmapped", () => {
  for (const header of QUALIFIER_HEADERS) {
    assert.deepEqual(verdict(header), ["unknown", 0, "none"], header);
  }
});

test("H2: Value, Name and Title twins keep their verdicts", () => {
  const mapper = new ContactMapper();
  const expected: Array<[string, string]> = [
    ["E-mail 1 - Value", "email"],
    ["E-mail 2 Address", "email"],
    ["Phone 1 - Value", "phone"],
    ["Website 1 - Value", "website"],
    ["Address 1 - Formatted", "address_line1"],
    ["Address 1 - Street", "address_line1"],
    ["Organization 1 - Name", "company"],
    ["Organization 1 - Title", "job_title"],
    ["Display Name", "full_name"],
    ["Business Type", "industry"],
    ["Inquiry Type", "subject"],
  ];
  for (const [header, canonical] of expected) {
    assert.equal(mapper.identify(header).canonical, canonical, header);
  }
});

test("H2: no layer maps a Type column", () => {
  const registry = new PatternRegistry();
  assert.equal(new NormalizedMatchStrategy(registry).match("E-mail 1 - Type"), undefined);
  assert.equal(new FuzzyMatchStrategy(registry).match("E-mail Type"), undefined);
  const heuristic = new HeuristicMatchStrategy();
  assert.equal(heuristic.match("Phone 1 - Type", "+14155550100"), undefined);
  // Control: the same value under a plain header is a phone.
  assert.equal(heuristic.match("Misc", "+14155550100")?.canonical, "phone");
});

test("H2: a Google row keeps type labels out of email and phone", () => {
  const result = new ContactMapper().map_payload({
    "E-mail 1 - Type": "* Work",
    "E-mail 1 - Value": "ada@example.com",
    "Phone 1 - Type": "Mobile",
    "Phone 1 - Value": "+1 415 555 0100",
  });
  assert.equal(result.normalized.email, "ada@example.com");
  assert.equal(result.normalized.phone, "+14155550100");
  assert.deepEqual({ ...result.unmapped }, { "E-mail 1 - Type": "* Work", "Phone 1 - Type": "Mobile" });
});

// ── M9: no 0.85 containment score for "alias plus a qualifier" ──────────────

test("M9: the length ratio is three quarters, as in Python", () => {
  assert.equal(FUZZY_LENGTH_RATIO, 0.75);
});

test("M9: alias plus a qualifier is not matched", () => {
  for (const header of ["phone_type", "email_type", "phone_ext", "E-mail Type"]) {
    assert.equal(new ContactMapper().identify(header).canonical, "unknown", header);
  }
});

test("M9: short-alias slips no longer score high (Python verdicts)", () => {
  const expected: Array<[string, [string, number, string]]> = [
    ["tel_nationa", ["phone", 0.7, "fuzzy"]],
    ["replyt", ["email", 0.7, "fuzzy"]],
    ["repyto", ["email", 0.7, "fuzzy"]],
    ["ownerid", ["unknown", 0, "none"]],
    ["reply_to_email", ["unknown", 0, "none"]],
    ["Phoneish", ["unknown", 0, "none"]],
    ["moblie", ["phone", 0.7, "fuzzy"]],
  ];
  for (const [header, want] of expected) {
    assert.deepEqual(verdict(header), want, header);
  }
});

test("M9: a contact_ prefix is stripped, not guessed (Python verdicts)", () => {
  const expected: Array<[string, [string, number, string]]> = [
    ["Contact Province", ["state", 0.95, "normalized"]],
    ["Contact Employer", ["company", 0.95, "normalized"]],
    ["contact_comments", ["notes", 0.95, "normalized"]],
    ["contact_currency", ["currency", 0.95, "normalized"]],
    ["Your contact province", ["state", 0.95, "normalized"]],
    ["contact_email_id", ["unknown", 0, "none"]],
    ["contact_owner_id", ["owner", 0.95, "normalized"]],
  ];
  for (const [header, want] of expected) {
    assert.deepEqual(verdict(header), want, header);
  }
});

// ── M11: long headers skip the rewrite and fuzzy layers ─────────────────────

test("M11: a 50,000-character header maps quickly to no match", () => {
  for (const header of [" ".repeat(50_000), `a${" ".repeat(50_000)}b`]) {
    const start = performance.now();
    const match = new ContactMapper().identify(header);
    const elapsed = performance.now() - start;
    assert.equal(match.canonical, "unknown");
    assert.ok(elapsed < 1000, `took ${elapsed} ms`);
  }
});

test("M11: rewrite layers skip headers over 200 characters", () => {
  const registry = new PatternRegistry();
  const header = `First${" ".repeat(200)}Name`;
  assert.equal(new NormalizedMatchStrategy(registry).match(header), undefined);
  assert.equal(new FuzzyMatchStrategy(registry).match(header), undefined);
  // Short enough, the same header still normalizes.
  assert.equal(new NormalizedMatchStrategy(registry).match("First Name")?.canonical, "first_name");
});

// ── Non-ASCII headers: same verdict as Python ───────────────────────────────

test("non-ASCII header verdicts match Python", () => {
  assert.deepEqual(verdict("Teléfono"), ["phone", 0.7, "fuzzy"]);
  assert.deepEqual(verdict("Straße 1"), ["unknown", 0, "none"]);
  assert.deepEqual(verdict("Ciudad/Población"), ["unknown", 0, "none"]);
});

test("non-ASCII letters survive header rewriting", () => {
  const registry = new PatternRegistry({ patterns: { fields: { phone: ["teléfono_móvil"] } } });
  assert.equal(new NormalizedMatchStrategy(registry).match("Teléfono Móvil")?.canonical, "phone");
});
