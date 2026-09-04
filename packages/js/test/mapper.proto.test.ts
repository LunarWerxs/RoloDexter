// Split out of the former monolithic mapper.test.ts (2572 lines, over the
// oversized-files gate of 2500). Same tests, grouped by topic. Shared
// CLI/version-probe helpers live in _mapper_test_helpers.ts.
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  ContactMapper,
  MappingSchema,
} from "../src/index.js";

const PROTO_KEY = "__proto__";
const protoRow = () => JSON.parse('{"__proto__": "kept", "fname": "Ada"}') as Record<string, unknown>;

test("a __proto__ column survives map_payload as data", () => {
  const result = new ContactMapper().map_payload(protoRow());

  assert.deepEqual(Object.keys(result.unmapped), [PROTO_KEY]);
  assert.equal(result.unmapped[PROTO_KEY], "kept");
  assert.equal((result.to_dict().unmapped as Record<string, unknown>)[PROTO_KEY], "kept");
});

test("a __proto__ column survives map_batch and map_stream", () => {
  assert.deepEqual(Object.keys(new ContactMapper().map_batch([protoRow()])[0]!.unmapped), [PROTO_KEY]);
  for (const result of new ContactMapper().map_stream([protoRow()])) {
    assert.deepEqual(Object.keys(result.unmapped), [PROTO_KEY]);
  }
});

test("__proto__ survives as a canonical field name too", () => {
  const mapper = new ContactMapper({ overrides: JSON.parse('{"weird": "__proto__"}') as Record<string, string> });
  const normalized = mapper.map_payload({ weird: "v" }).normalized;

  assert.deepEqual(Object.keys(normalized), [PROTO_KEY]);
  assert.equal(normalized[PROTO_KEY], "v");
});

test("compile_schema keeps a __proto__ header", () => {
  const schema = new ContactMapper().compile_schema([PROTO_KEY, "fname"]);

  assert.deepEqual(Object.keys(schema.matches).sort(), [PROTO_KEY, "fname"]);
  assert.deepEqual(schema.unmatched_headers(), [PROTO_KEY]);
  assert.equal(Object.getPrototypeOf(schema.matches), Object.prototype);
});

test("a matched __proto__ header reaches column_map", () => {
  const mapper = new ContactMapper({ overrides: JSON.parse('{"__proto__": "email"}') as Record<string, string> });
  const schema = mapper.compile_schema([PROTO_KEY, "fname"]);

  assert.deepEqual(schema.column_map(), JSON.parse('{"__proto__": "email", "fname": "first_name"}'));
});

test("the mapping lockfile records and restores a __proto__ column", () => {
  // to_dict is the lockfile: a column missing from it is a column that routes
  // differently on the next run.
  const schema = new ContactMapper().compile_schema([PROTO_KEY, "fname"]);
  const lockfile = schema.to_dict();

  assert.deepEqual(Object.keys(lockfile.columns as Record<string, unknown>).sort(), [PROTO_KEY, "fname"]);

  const restored = MappingSchema.from_dict(lockfile, new ContactMapper());
  assert.deepEqual(Object.keys(restored.matches).sort(), [PROTO_KEY, "fname"]);
});

test("schema.apply and a seeded header cache keep a __proto__ column", () => {
  const mapper = new ContactMapper();
  const schema = mapper.compile_schema([PROTO_KEY, "fname"]);

  assert.deepEqual(Object.keys(schema.apply(protoRow()).unmapped), [PROTO_KEY]);

  mapper.seed_header_cache(Object.fromEntries([...schema.matches.entries()]));
  assert.deepEqual(Object.keys(mapper.map_payload(protoRow()).unmapped), [PROTO_KEY]);
});

test("a nested __proto__ key survives payload flattening", () => {
  const nested = JSON.parse('{"person": {"__proto__": "kept", "fname": "Ada"}}') as Record<string, unknown>;
  const result = new ContactMapper().map_payload(nested, { depth: 2 });

  assert.equal(result.unmapped["person.__proto__"], "kept");
});
