// A plain JavaScript object used as a lookup table answers for keys nobody put
// in it. COUNTRY_NAMES["constructor"] is the Object function and
// COUNTRY_NAMES["__proto__"] is Object.prototype, so before 2.11.2 a contact
// whose country column read "constructor" normalized to a *function*, and one
// reading "__proto__" to an object - from an API typed to return a string.
// Python dicts carry no inherited members, so the same rows stayed strings
// there: a type confusion here and a cross-language divergence at once.
//
// Only member names that survive the lookup's own .toLowerCase() can collide,
// which is why "__proto__" and "constructor" leaked while "toString" did not.
// That is far too fine a distinction to rest on, so the tables are built with
// Object.create(null) and the membership tests use Object.hasOwn - the reads
// are safe by construction rather than by luck. These cases are mirrored
// one-for-one in tests/test_prototype_keys_contract.py.
import assert from "node:assert/strict";
import { test } from "node:test";

import { ContactMapper, normalize_value } from "../src/index.js";
import { generate_language, load_cached } from "../src/i18n.js";

// Every name Object.prototype contributes. Spelled out rather than derived, so
// that a future engine adding a member does not silently shrink this test.
const PROTOTYPE_KEYS = [
  "__proto__",
  "constructor",
  "toString",
  "toLocaleString",
  "valueOf",
  "hasOwnProperty",
  "isPrototypeOf",
  "propertyIsEnumerable",
  "__defineGetter__",
  "__defineSetter__",
  "__lookupGetter__",
  "__lookupSetter__",
];

test("a country column holding a prototype member name stays a string", () => {
  for (const key of PROTOTYPE_KEYS) {
    const out = normalize_value("country", key);
    assert.equal(typeof out, "string", `country=${key} returned ${typeof out}`);
  }
  // The two that actually reached the tables, pinned by value.
  assert.equal(normalize_value("country", "__proto__"), "__proto__");
  assert.equal(normalize_value("country", "constructor"), "constructor");
});

test("a state column holding a prototype member name stays a string", () => {
  for (const key of PROTOTYPE_KEYS) {
    const out = normalize_value("state", key);
    assert.equal(typeof out, "string", `state=${key} returned ${typeof out}`);
  }
  assert.equal(normalize_value("state", "__proto__"), "__proto__");
  // Unmatched states are title-cased, exactly as any other unknown value is.
  assert.equal(normalize_value("state", "constructor"), "Constructor");
});

test("a real country still resolves, so the tables were not emptied", () => {
  assert.equal(normalize_value("country", "United States"), "US");
  assert.equal(normalize_value("country", "deutschland"), "DE");
  assert.equal(normalize_value("country", "usa"), "US");
  assert.equal(normalize_value("country", "gb"), "GB");
  assert.equal(normalize_value("state", "california"), "CA");
  assert.equal(normalize_value("state", "Ontario"), "ON");
});

test("a prototype member name is not a supported language code", () => {
  for (const key of PROTOTYPE_KEYS) {
    // `in` accepted every one of these, and the generator then destructured
    // Object.prototype as a [code, name] pair: "object is not iterable".
    assert.throws(
      () => generate_language(key),
      (error: Error) => /Unsupported language/.test(error.message),
      `generate_language(${key}) did not report an unsupported language`,
    );
    assert.equal(load_cached(key), null, `load_cached(${key}) found something`);
  }
});

test("a payload carrying prototype member names maps without type confusion", () => {
  const mapper = new ContactMapper();
  const result = mapper.map_payload({ country: "constructor", state: "__proto__" });
  for (const value of Object.values(result.normalized)) {
    assert.ok(
      typeof value === "string" || Array.isArray(value) || value === null,
      `normalized value was ${typeof value}`,
    );
  }
  // JSON is the round trip that a function silently fails: it serializes to
  // undefined and the key vanishes from the output entirely.
  const encoded = JSON.stringify(result.to_dict());
  assert.ok(encoded.includes("constructor"), "the country value did not survive JSON");
});
