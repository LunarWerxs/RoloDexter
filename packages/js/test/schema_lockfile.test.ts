// MappingSchema.to_dict / from_dict — the "mapping lockfile" added in 2.11.0.
// Python covers this in tests/test_v211_fixes.py::TestMappingSchemaRoundTrip;
// the TypeScript port shipped the feature with no test at all, so a plan that
// failed to round-trip would have reached npm unnoticed.
import assert from "node:assert/strict";
import { test } from "node:test";

import { ContactMapper, MappingSchema, PatternLoadError } from "../src/index.js";

const HEADERS = ["First Name", "Mobile Phone", "Whatever"];
const ROW = { "First Name": "Jane", "Mobile Phone": "(202) 555-0143", Whatever: "x" };

test("to_dict emits a reviewable JSON plan", () => {
  const plan = new ContactMapper().compile_schema(HEADERS).to_dict();

  assert.deepEqual(plan, {
    schema_version: MappingSchema.SCHEMA_VERSION,
    default_region: "US",
    columns: {
      "First Name": { canonical: "first_name", confidence: 0.95, strategy: "normalized", service: null },
      "Mobile Phone": { canonical: "phone", confidence: 0.95, strategy: "normalized", service: null },
      // Headers that did not resolve are still recorded, so a reviewer can
      // see what the plan decided *not* to route.
      Whatever: { canonical: "unknown", confidence: 0, strategy: "none", service: null },
    },
  });
  // The whole point is that it survives a file, so it has to be JSON-safe.
  assert.deepEqual(JSON.parse(JSON.stringify(plan)) as unknown, plan);
});

test("a saved plan round-trips through a fresh mapper", () => {
  const schema = new ContactMapper().compile_schema(HEADERS);
  const rebuilt = MappingSchema.from_dict(
    JSON.parse(JSON.stringify(schema.to_dict())) as Record<string, unknown>,
    new ContactMapper(),
  );

  assert.deepEqual(rebuilt.column_map(), schema.column_map());
  assert.deepEqual(rebuilt.unmatched_headers(), schema.unmatched_headers());
  assert.deepEqual(rebuilt.apply(ROW).normalized, schema.apply(ROW).normalized);
});

test("the saved plan wins over what the alias table would decide today", () => {
  // "Whatever" resolves to nothing on its own; a plan that pins it to
  // "company" must route it anyway. This is what makes an import
  // reproducible across a patterns.json update.
  const rebuilt = MappingSchema.from_dict(
    {
      schema_version: MappingSchema.SCHEMA_VERSION,
      default_region: null,
      columns: { Whatever: { canonical: "company", confidence: 1, strategy: "schema", service: null } },
    },
    new ContactMapper(),
  );

  assert.deepEqual(rebuilt.column_map(), { Whatever: "company" });
  assert.deepEqual(rebuilt.apply({ Whatever: "Acme" }).normalized, { company: "Acme" });
});

test("the region travels with the plan and can be overridden on load", () => {
  const plan = new ContactMapper({ default_region: "US" }).compile_schema(["Mobile Phone"]).to_dict();
  assert.equal(plan.default_region, "US");

  const restored = MappingSchema.from_dict(plan, new ContactMapper());
  assert.equal(restored.default_region, "US");
  assert.deepEqual(restored.apply({ "Mobile Phone": "(202) 555-0143" }).normalized, { phone: "+12025550143" });

  const relocated = MappingSchema.from_dict(plan, new ContactMapper(), { default_region: "GB" });
  assert.deepEqual(relocated.apply({ "Mobile Phone": "020 7946 0958" }).normalized, { phone: "+442079460958" });
});

test("omitted column fields fall back to an exact-match verdict", () => {
  const rebuilt = MappingSchema.from_dict(
    { schema_version: MappingSchema.SCHEMA_VERSION, columns: { Col: { canonical: "email" } } },
    new ContactMapper(),
  );

  assert.deepEqual(
    [...rebuilt.matches.entries()].map(([header, match]) => [
      header,
      match.canonical,
      match.confidence,
      match.strategy,
      match.service,
    ]),
    [["Col", "email", 1, "schema", null]],
  );
});

test("from_dict refuses a plan it cannot honor", () => {
  const cases: Array<[unknown, RegExp]> = [
    [null, /expected an object/],
    ["nope", /expected an object/],
    [[], /expected an object/],
    [{ schema_version: 999, columns: {} }, /Unsupported mapping schema version 999/],
    [{ schema_version: MappingSchema.SCHEMA_VERSION, columns: "nope" }, /'columns' must be an object/],
    [{ schema_version: MappingSchema.SCHEMA_VERSION, columns: [] }, /'columns' must be an object/],
    [{ schema_version: MappingSchema.SCHEMA_VERSION, columns: { a: "nope" } }, /must map a string header to an object/],
    [{ schema_version: MappingSchema.SCHEMA_VERSION, columns: { a: [] } }, /must map a string header to an object/],
    [{ schema_version: MappingSchema.SCHEMA_VERSION, columns: { a: { canonical: "  " } } }, /has no canonical field/],
    [{ schema_version: MappingSchema.SCHEMA_VERSION, columns: { a: { canonical: 7 } } }, /has no canonical field/],
    [
      { schema_version: MappingSchema.SCHEMA_VERSION, columns: { a: { canonical: "email", strategy: 7 } } },
      /malformed strategy or confidence/,
    ],
    [
      { schema_version: MappingSchema.SCHEMA_VERSION, columns: { a: { canonical: "email", confidence: "high" } } },
      /malformed strategy or confidence/,
    ],
  ];

  for (const [data, message] of cases) {
    assert.throws(
      () => MappingSchema.from_dict(data as Record<string, unknown>, new ContactMapper()),
      { name: "PatternLoadError", message },
      `expected ${JSON.stringify(data)} to be rejected`,
    );
  }

  // Rejection is by type, not just by message, so callers can catch it.
  assert.throws(
    () => MappingSchema.from_dict(null as unknown as Record<string, unknown>, new ContactMapper()),
    PatternLoadError,
  );
});
