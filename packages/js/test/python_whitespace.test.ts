// Python's str.strip() and JavaScript's String.prototype.trim() do not agree on
// what whitespace is: trim() strips U+FEFF and Python does not, Python strips
// U+001C-001F and U+0085 and trim() does not. A UTF-8 CSV puts a byte-order
// mark on its first field, so the disagreement reached ordinary data - the same
// column normalized to "" in one package and kept its mark in the other, and a
// BOM-prefixed header resolved at a different confidence.
//
// Python's repr() escapes those characters too, which is why the warning text
// is pinned here alongside the values.
//
// Every invisible character below is built with String.fromCharCode rather
// than pasted: a file that carries a real NUL or BOM is one no reviewer can see.
import assert from "node:assert/strict";
import { test } from "node:test";

import { ContactMapper, normalize_value } from "../src/index.js";

const BOM = String.fromCharCode(0xfeff);
const FILE_SEPARATOR = String.fromCharCode(0x1c);
const NEL = String.fromCharCode(0x85);
const NBSP = String.fromCharCode(0xa0);

test("a byte-order mark is not whitespace, as in Python", () => {
  // JavaScript's trim() disagrees with Python here, so `.trim()` would return "".
  assert.equal(normalize_value("unknown", BOM), BOM);
  assert.equal(normalize_value("company", BOM), BOM);
  assert.equal(normalize_value("email", BOM), BOM);
  assert.equal(normalize_value("notes", `${BOM}hello${BOM}`), `${BOM}hello${BOM}`);
});

test("the C1 and ASCII separator whitespace Python strips is stripped here too", () => {
  // The other direction: trim() leaves these, Python removes them.
  assert.equal(normalize_value("unknown", FILE_SEPARATOR), "");
  assert.equal(normalize_value("unknown", NEL), "");
  assert.equal(normalize_value("unknown", `${FILE_SEPARATOR}hello${NEL}`), "hello");
  assert.equal(normalize_value("unknown", `${NBSP}hello${NBSP}`), "hello");
});

test("a name splits on Python's whitespace set, not JavaScript's", () => {
  assert.equal(normalize_value("first_name", `ada${NEL}lovelace`), "Ada Lovelace");
  assert.equal(normalize_value("first_name", `ada${FILE_SEPARATOR}lovelace`), "Ada Lovelace");
  // A byte-order mark is NOT a split point, so the name stays one word. Whether
  // the half after it gets capitalized is a separate question - Python's
  // str.title() treats any non-letter as a word boundary and JavaScript's does
  // not - tracked as the name casing class in docs/maintenance/parity_sweep.md.
  assert.ok(String(normalize_value("first_name", `ada${BOM}lovelace`)).includes(BOM));
});

test("a BOM-prefixed header resolves at Python's confidence and strategy", () => {
  // What Excel writes on the first column of a UTF-8 CSV. Resolving it as an
  // exact match here and a normalized one in Python meant a confidence
  // threshold above 0.95 kept the column in one package and dropped it in the
  // other.
  const match = new ContactMapper().identify(`${BOM}fname`);

  assert.equal(match.canonical, "first_name");
  assert.equal(match.confidence, 0.95);
  assert.equal(match.strategy, "normalized");
});

test("a warning quotes a non-printable value the way Python's repr does", () => {
  const result = new ContactMapper().map_payload({ email: BOM });

  assert.deepEqual(result.warnings, [
    "'email': value '\\ufeff' does not look like an email address",
  ]);
});

test("repr escapes control characters, and leaves printable text alone", () => {
  const result = new ContactMapper().map_payload({ email: `a${FILE_SEPARATOR}b@x` });

  assert.deepEqual(result.warnings, [
    "'email': value 'a\\x1cb@x' does not look like an email address",
  ]);
});
