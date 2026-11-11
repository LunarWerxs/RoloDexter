// Regression tests for the 2026-11-11 audit, mapper group (W4). Each test names
// its finding id. The Python twin is tests/test_audit_mapper.py.
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  ContactMapper,
  FieldMatch,
  MappingResult,
  MappingSchema,
  NormalizationError,
  PatternLoadError,
} from "../src/index.js";
import { valueForMatching } from "../src/_models.js";

const SERVICE_TEXT = "the 'service' argument is ignored since rolodexter 2.0 and will be removed in a future release";

const result = (normalized: Record<string, unknown>): MappingResult => new MappingResult(normalized, {}, []);

/** Collect what the rolodexterWarning event carries while `run` executes. */
function captureEvents(run: () => void): Array<{ name: string; message: string }> {
  const seen: Array<{ name: string; message: string }> = [];
  const listener = (warning: Error): void => {
    seen.push(warning);
  };
  process.on("rolodexterWarning" as "warning", listener);
  try {
    run();
  } finally {
    process.off("rolodexterWarning" as "warning", listener);
  }
  return seen;
}

/** Collect DeprecationWarning texts synchronously (emitWarning itself delivers on a later tick). */
function captureDeprecations(run: () => void): string[] {
  const seen: string[] = [];
  const original = process.emitWarning;
  process.emitWarning = ((warning: string | Error, options?: { type?: string } | string) => {
    const type = typeof options === "string" ? options : options?.type;
    if (type === "DeprecationWarning") {
      seen.push(String(warning));
    }
  }) as typeof process.emitWarning;
  try {
    run();
  } finally {
    process.emitWarning = original;
  }
  return seen;
}

class Frame {
  [key: string]: unknown;

  columns: string[];
  data: Record<string, unknown[]>;

  constructor(data: Record<string, unknown[]>) {
    this.columns = Object.keys(data);
    this.data = data;
  }

  rename(args: { columns: Record<string, string> } | Record<string, string>): Frame {
    const columns = ((args as { columns?: Record<string, string> }).columns ?? args) as Record<string, string>;
    return new Frame(Object.fromEntries(this.columns.map((c) => [columns[c] ?? c, [...(this.data[c] ?? [])]])));
  }

  get(column: string): unknown[] {
    return this.data[column] ?? [];
  }

  set(column: string, values: unknown): void {
    this.data[column] = values as unknown[];
  }
}

// ── H3 (contract C2) ───────────────────────────────────────────────────────

test("H3: placeholders never become identity keys", () => {
  const keys = result({ email: ["n/a", "-", "ada@example.com"], phone: ["none", "555-1234"] }).get_identity_keys();
  assert.deepEqual(keys, ["email:ada@example.com"]);
});

test("H3: work_phone and fax are not identity keys", () => {
  assert.deepEqual(result({ work_phone: "+14155550100", fax: "+14155550199" }).get_identity_keys(), []);
});

test("H3: a phone key drops the extension", () => {
  const keys = result({ phone: "+14155550100;ext=123", home_phone: "+14155550100" }).get_identity_keys();
  assert.deepEqual(keys, ["phone:+14155550100"]);
});

// ── M8 (contract C3, mapper parts) ─────────────────────────────────────────

test("M8: a whole number is written without .0 for value-shape matching", () => {
  assert.equal(valueForMatching(4155550100), "4155550100");
  assert.equal(valueForMatching(1.5), "1.5");
});

test("M8: a phone value that is not text gets the phone warning", () => {
  const warnings = new ContactMapper().map_payload({ phone: true }).warnings;
  assert.deepEqual(warnings, [
    "'phone': phone value True could not be normalized to E.164 (set a matching default_region?)",
  ]);
});

// ── M10 ────────────────────────────────────────────────────────────────────

const PLAN = {
  schema_version: 1,
  default_region: "US",
  columns: { Contact: { canonical: "company", confidence: 1, strategy: "schema" } },
};

test("M10: a seeded plan survives cache size 0, clear_cache and eviction", () => {
  for (const size of [0, 1]) {
    const mapper = new ContactMapper({ header_cache_max_size: size });
    MappingSchema.from_dict(PLAN, mapper);
    mapper.clear_cache();
    for (const header of ["a", "b", "c"]) {
      mapper.map_payload({ [header]: "x" });
    }
    const match = mapper.map_payload({ Contact: "Acme" }).get_match("Contact");
    assert.equal(match?.canonical, "company", `size ${size}`);
    assert.equal(match?.strategy, "schema", `size ${size}`);
  }
});

// ── L14 (contract C6) ──────────────────────────────────────────────────────

test("L14: the event and the error name header and category, not the value", () => {
  const secret = "garbage value here";
  let warnings: readonly string[] = [];
  const seen = captureEvents(() => {
    warnings = new ContactMapper().map_payload({ phone: secret }).warnings;
  });
  assert.ok(warnings.some((warning) => warning.includes(secret)));
  assert.deepEqual(seen.map((event) => event.message), ["'phone': phone_normalization"]);
  assert.throws(
    () => new ContactMapper({ strict: true }).map_payload({ phone: secret }),
    (error: unknown) => error instanceof NormalizationError && error.message === "'phone': phone_normalization",
  );
});

// ── L15 ────────────────────────────────────────────────────────────────────

test("L15: map_dataframe surfaces ambiguous dates", () => {
  assert.throws(
    () => new ContactMapper({ strict: true }).map_dataframe(new Frame({ birthday: ["03/04/2020"] })),
    { name: "NormalizationError", message: /date_ambiguous/ },
  );
});

// ── L16 ────────────────────────────────────────────────────────────────────

test("L16: from_dict refuses a field that is not canonical", () => {
  assert.throws(
    () => MappingSchema.from_dict(
      { schema_version: 1, columns: { E: { canonical: "emial", confidence: 1 } } },
      new ContactMapper(),
    ),
    (error: unknown) => error instanceof PatternLoadError && /'emial', which is not a canonical field/.test(error.message),
  );
});

test("L16: from_dict accepts an override target", () => {
  const plan = new ContactMapper({ overrides: { "crm ref": "crm_ref" } }).compile_schema(["crm ref"]).to_dict();
  const restored = MappingSchema.from_dict(plan, new ContactMapper({ overrides: { x: "crm_ref" } }));
  assert.deepEqual(restored.column_map(), { "crm ref": "crm_ref" });
});

// ── L18 ────────────────────────────────────────────────────────────────────

test("L18: profile counts embedded phones apart from columns", () => {
  const profile = new ContactMapper().profile([{ notes: "call me at +1 415 555 0100" }], { extract_embedded_phones: true });
  assert.equal(profile.fields_seen, 1);
  assert.equal(profile.matched_count + profile.unmatched_count, 1);
  assert.equal(profile.embedded_phone_count, 1);
  assert.equal(profile.to_dict().embedded_phone_count, 1);
});

// ── L19 ────────────────────────────────────────────────────────────────────

test("L19: a flattening collision is warned", () => {
  const warnings = new ContactMapper().map_payload({ "a.b": 1, a: { b: 2 } }, { depth: 2 }).warnings;
  assert.ok(warnings.includes("'a.b': two payload keys flatten to this name; the later value replaced the earlier one"));
});

// ── L20 ────────────────────────────────────────────────────────────────────

test("L20: headers named get, set, entries and items survive the saved plan", () => {
  const headers = ["get", "set", "entries", "items", "fname"];
  const schema = new ContactMapper().compile_schema(headers);
  assert.deepEqual([...schema.matches.keys()], headers);
  assert.equal(schema.matches.get("fname")?.canonical, "first_name");
  assert.deepEqual(Object.keys(schema.to_dict().columns as Record<string, unknown>), headers);
  const restored = MappingSchema.from_dict(schema.to_dict(), new ContactMapper());
  assert.deepEqual([...restored.matches.keys()], headers);
});

// ── L26 ────────────────────────────────────────────────────────────────────

test("L26: frozen fields still raise FrozenInstanceError and warnings carry no stack frames", () => {
  const match = new FieldMatch("x", "email", 1, "exact");
  assert.throws(
    () => {
      (match as unknown as Record<string, unknown>).original = "y";
    },
    { name: "FrozenInstanceError" },
  );

  const events = captureEvents(() => {
    new ContactMapper().map_payload({ phone: "garbage value here" });
  });
  assert.equal(events.length, 1);
  assert.equal(events[0]?.name, "RolodexterWarning");
  assert.ok(events[0] instanceof Error);
  assert.ok(!String(events[0]?.stack ?? "").includes("\n    at "));
});

// ── L28 ────────────────────────────────────────────────────────────────────

test("L28: service and default_service emit one DeprecationWarning each", () => {
  assert.deepEqual(
    captureDeprecations(() => new ContactMapper({ default_service: "hubspot" })),
    [SERVICE_TEXT.replace("'service'", "'default_service'")],
  );
  const mapper = new ContactMapper();
  assert.deepEqual(captureDeprecations(() => mapper.map_payload({ email: "a@b.co" }, { service: "x" })), [SERVICE_TEXT]);
  assert.deepEqual(captureDeprecations(() => mapper.identify("email", { service: "x" })), [SERVICE_TEXT]);
  assert.deepEqual(
    captureDeprecations(() => mapper.map_batch([{ email: "a@b.co" }, { email: "c@d.co" }], { service: "x" })),
    [SERVICE_TEXT],
  );
  assert.deepEqual(captureDeprecations(() => mapper.map_payload({ email: "a@b.co" })), []);
});
