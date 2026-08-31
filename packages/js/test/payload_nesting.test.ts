// map_payload({ depth }) flattens nested payloads into dotted headers before
// matching, so a contact arriving as nested JSON maps as well as a flat CSV
// row does. Nothing exercised the flattening itself.
import assert from "node:assert/strict";
import { test } from "node:test";

import { ContactMapper } from "../src/index.js";

test("nested payloads are only flattened when depth asks for it", () => {
  const payload = { contact: { fname: "jane" } };

  // depth defaults to 1: the nested object is matched as a single value.
  assert.deepEqual(new ContactMapper().map_payload(payload).normalized, {
    full_name: { fname: "jane" },
  });

  // depth 2 turns it into "contact.fname", which resolves like any header.
  assert.deepEqual(new ContactMapper().map_payload(payload, { depth: 2 }).normalized, {
    first_name: "Jane",
  });
});

test("flattening stops at the requested depth and keeps the remainder intact", () => {
  const payload = { a: { b: { fname: "jane", email: "A@B.CO" } } };

  const shallow = new ContactMapper().map_payload(payload, { depth: 2 });
  assert.deepEqual(shallow.normalized, {});
  assert.deepEqual(shallow.unmapped, { "a.b": { fname: "jane", email: "A@B.CO" } });

  const deep = new ContactMapper().map_payload(payload, { depth: 3 });
  assert.deepEqual(deep.normalized, { first_name: "Jane", email: "a@b.co" });
});

test("arrays are values, not levels to descend into", () => {
  // Flattening an array would produce "contact.tags.0", which is not a
  // header anyone means. It stays a list and normalizes as one.
  assert.deepEqual(
    new ContactMapper().map_payload({ contact: { tags: ["a", "b"] } }, { depth: 2 }).normalized,
    { tags: ["a", "b"] },
  );
});

test("depth is clamped rather than trusted", () => {
  const payload = { a: { b: { c: { d: { e: { fname: "jane" } } } } } };

  // Below 1 is meaningless; it behaves as "do not flatten".
  assert.deepEqual(new ContactMapper().map_payload(payload, { depth: 0 }).unmapped, payload);
  // Above 5 cannot be used to walk an arbitrarily deep payload: it stops at
  // five levels and leaves whatever is below as a value.
  assert.deepEqual(
    new ContactMapper().map_payload(payload, { depth: 99 }).unmapped,
    { "a.b.c.d.e": { fname: "jane" } },
  );
});
