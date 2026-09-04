// Split out of the former monolithic mapper.test.ts (2572 lines, over the
// oversized-files gate of 2500). Same tests, grouped by topic. Shared
// CLI/version-probe helpers live in _mapper_test_helpers.ts.
import assert from "node:assert/strict";
import {} from "node:path";
import { test } from "node:test";
import {
  ContactMapper,
  ExactMatchStrategy,
  FuzzyMatchStrategy,
  HeuristicMatchStrategy,
  MappingProfile,
  MappingResult,
  MappingSchema,
  MatchStrategy,
  NormalizedMatchStrategy,
  PatternRegistry,
} from "../src/index.js";

test("maps and normalizes a basic contact payload", () => {
  const result = new ContactMapper().map_payload({
    fname: "jane",
    surname: "doe",
    mobile: "(202) 555-0143",
    employer: "Tech Corp",
    "Column 1": "jane.doe@example.com",
  });

  assert.equal(result.normalized.first_name, "Jane");
  assert.equal(result.normalized.last_name, "Doe");
  assert.equal(result.normalized.phone, "+12025550143");
  assert.equal(result.normalized.company, "Tech Corp");
  assert.equal(result.normalized.email, "jane.doe@example.com");
  assert.equal(result.unmatched_count, 0);
});

test("handles normalized headers and dot paths", () => {
  const mapper = new ContactMapper();

  assert.equal(mapper.identify("FirstName").canonical, "first_name");
  assert.equal(mapper.identify("Account.Name").canonical, "company");
  assert.equal(mapper.identify("Phone 1 - Value").canonical, "phone");
  assert.equal(mapper.identify("hs_lead_status").canonical, "lead_status");
});

test("mapper runtime argument and shape errors mirror Python", () => {
  const mapper = new ContactMapper();

  assert.throws(
    () => (mapper.identify as unknown as () => unknown)(),
    { name: "TypeError", message: "ContactMapper.identify() missing 1 required positional argument: 'header'" },
  );
  assert.throws(
    () => (mapper.identify as unknown as (header: string, value: string) => unknown)("Mystery", "ada@example.com"),
    { name: "TypeError", message: "ContactMapper.identify() takes 2 positional arguments but 3 were given" },
  );
  assert.throws(
    () => (mapper.map_payload as unknown as (payload: Record<string, unknown>, options: unknown) => unknown)({ fname: "Ada" }, 2),
    { name: "TypeError", message: "ContactMapper.map_payload() takes 2 positional arguments but 3 were given" },
  );
  assert.throws(
    () => mapper.map_payload([["fname", "Ada"]] as never),
    { name: "AttributeError", message: "'list' object has no attribute 'items'" },
  );
  assert.throws(
    () => (mapper.map_batch as unknown as (payloads: Iterable<Record<string, unknown>>, options: unknown) => unknown)([{ fname: "Ada" }], 2),
    { name: "TypeError", message: "ContactMapper.map_batch() takes 2 positional arguments but 3 were given" },
  );
  assert.throws(
    () => (mapper.map_stream as unknown as (payloads: Iterable<Record<string, unknown>>, options: unknown) => unknown)([{ fname: "Ada" }], 2),
    { name: "TypeError", message: "ContactMapper.map_stream() takes 2 positional arguments but 3 were given" },
  );
  assert.throws(
    () => (mapper.compile_schema as unknown as (headers: Iterable<string>, options: unknown) => unknown)(["fname"], 2),
    { name: "TypeError", message: "ContactMapper.compile_schema() takes 2 positional arguments but 3 were given" },
  );
  assert.throws(
    () => (mapper.map_dataframe as unknown as (df: unknown, options: unknown) => unknown)({ columns: [], rename: () => ({}) }, 2),
    { name: "TypeError", message: "ContactMapper.map_dataframe() takes 2 positional arguments but 3 were given" },
  );
  assert.throws(
    () => new (ContactMapper as unknown as new (...args: unknown[]) => ContactMapper)(2),
    { name: "TypeError", message: "ContactMapper.__init__() takes 1 positional argument but 2 were given" },
  );
  assert.throws(
    () => new ContactMapper({ bogus: true } as never),
    { name: "TypeError", message: "ContactMapper.__init__() got an unexpected keyword argument 'bogus'" },
  );
  assert.throws(
    () => new ContactMapper({ patterns: [] as never }),
    { name: "PatternLoadError", message: "Invalid custom patterns: top level must be an object" },
  );

  const schema = mapper.compile_schema([1, true, null, ["x"]]);
  assert.deepEqual(schema.column_map(), {});
  assert.deepEqual(schema.unmatched_headers(), ["1", "True", "None", "['x']"]);

  const applySchema = mapper.compile_schema(["fname"]);
  assert.throws(
    () => (applySchema.apply as unknown as () => unknown)(),
    { name: "TypeError", message: "MappingSchema.apply() missing 1 required positional argument: 'row'" },
  );
  assert.throws(
    () => (applySchema.apply as unknown as (row: Record<string, unknown>, options: unknown) => unknown)({ fname: "Ada" }, 2),
    { name: "TypeError", message: "MappingSchema.apply() takes 2 positional arguments but 3 were given" },
  );
  assert.throws(
    () => applySchema.apply({ fname: "Ada" }, { bogus: true } as never),
    { name: "TypeError", message: "ContactMapper.map_payload() got an unexpected keyword argument 'bogus'" },
  );
  assert.throws(
    () => (applySchema.apply as unknown as (...args: unknown[]) => unknown)({ fname: "Ada" }, {}, "extra"),
    { name: "TypeError", message: "MappingSchema.apply() takes 2 positional arguments but 4 were given" },
  );
});

test("fuzzy matching follows Python typo recovery guards", () => {
  const mapper = new ContactMapper();

  assert.deepEqual(
    ["phne_nmbr", "Compny", "Job Titel"].map((header) => mapper.identify(header).canonical),
    ["phone", "company", "job_title"],
  );
  assert.deepEqual(
    ["repyto", "reply_to_email", "ownerid"].map((header) => {
      const match = mapper.identify(header);
      return [match.canonical, match.confidence, match.strategy];
    }),
    [
      ["owner", 0.85, "fuzzy"],
      ["unknown", 0, "none"],
      ["owner", 0.7, "fuzzy"],
    ],
  );
  assert.equal(mapper.identify("Job Titel").strategy, "fuzzy");
  assert.equal(mapper.identify("Job Titel").confidence, 0.7);
  assert.equal(mapper.identify("phne_nmbr").confidence, 0.7);
  assert.equal(mapper.identify("Compny").confidence, 0.85);
  assert.equal(mapper.identify("First Nmae").confidence, 0.85);
  assert.deepEqual(
    ["emial", "frist name", "linked in", "source idd", "adress line"].map((header) => {
      const match = mapper.identify(header);
      return [match.canonical, match.confidence, match.strategy];
    }),
    [
      ["email", 0.7, "fuzzy"],
      ["first_name", 0.85, "fuzzy"],
      ["linkedin", 0.85, "fuzzy"],
      ["source_id", 0.85, "fuzzy"],
      ["address_line1", 0.7, "fuzzy"],
    ],
  );
  const placeholder = mapper.identify("field_1");
  assert.equal(placeholder.canonical, "industry");
  assert.equal(placeholder.strategy, "fuzzy");
  assert.equal(mapper.identify("Phoneish").canonical, "phone");
  assert.equal(mapper.identify("Phoneish").confidence, 0.85);
  assert.equal(mapper.identify("Emailish").canonical, "email");
  assert.equal(mapper.identify("Emailish").confidence, 0.85);
  assert.equal(mapper.identify("moblie").canonical, "phone");
  assert.equal(mapper.identify("moblie").confidence, 0.85);
  assert.equal(mapper.identify("addressline").canonical, "address_line1");
  assert.equal(mapper.identify("addressline").confidence, 0.85);
  assert.equal(mapper.identify("Column 1").canonical, "unknown");
  assert.deepEqual(
    [
      "_replyt",
      "tel-nationa",
      "tl-national",
      "streetaddress2",
      "address-level",
      "_rplyto",
      "tel-naitonal",
      "tel-loca",
      "tl-local",
      "street_line",
      "ddress-line3",
      "ddress-level2",
      "ddress-level1",
      "howdidyouhear",
    ].map((header) => {
      const match = mapper.identify(header);
      return [match.canonical, match.confidence, match.strategy];
    }),
    [
      ["owner", 0.85, "fuzzy"],
      ["country", 0.85, "fuzzy"],
      ["country", 0.85, "fuzzy"],
      ["address_line2", 0.85, "fuzzy"],
      ["address_line1", 0.85, "fuzzy"],
      ["email", 0.7, "fuzzy"],
      ["phone", 0.7, "fuzzy"],
      ["phone", 0.7, "fuzzy"],
      ["phone", 0.7, "fuzzy"],
      ["address_line1", 0.85, "fuzzy"],
      ["address_line2", 0.7, "fuzzy"],
      ["city", 0.7, "fuzzy"],
      ["state", 0.7, "fuzzy"],
      ["source", 0.7, "fuzzy"],
    ],
  );
  assert.equal(mapper.identify("tel-olcal").canonical, "unknown");
  assert.deepEqual(
    [mapper.identify("tel-olcal", { value: "202-555-0143" }).canonical, mapper.identify("tel-olcal", { value: "202-555-0143" }).confidence, mapper.identify("tel-olcal", { value: "202-555-0143" }).strategy],
    ["phone", 0.6, "heuristic"],
  );

  const result = mapper.map_payload({ "Column 1": "jane.doe@example.com" });
  assert.equal(result.normalized.email, "jane.doe@example.com");
  assert.equal(result.get_match("Column 1")?.strategy, "heuristic");
});

test("heuristics detect already-normalized E.164 phone values", () => {
  const match = new ContactMapper().identify("Mystery Column", {
    value: "+12025550143",
  });

  assert.equal(match.canonical, "phone");
  assert.equal(match.strategy, "heuristic");
});

test("heuristics avoid ambiguous dates and bare numeric phone IDs", () => {
  const heuristic = new HeuristicMatchStrategy("US");

  assert.equal(heuristic.match("Mystery Column", "1990-05-15"), undefined);
  assert.equal(heuristic.match("raw_numeric_token", "2025550143"), undefined);
  assert.deepEqual(new ContactMapper().map_payload({ "Mystery Phone": 2025550143 }).normalized, {});

  const birthday = heuristic.match("custom_birth_marker", "1990-05-15");
  assert.ok(birthday);
  assert.equal(birthday.canonical, "birthday");
  assert.equal(birthday.strategy, "heuristic");

  const phone = heuristic.match("contact phone", "2025550143");
  assert.ok(phone);
  assert.equal(phone.canonical, "phone");
  assert.equal(phone.strategy, "heuristic");

  assert.equal(heuristic.match("Mystery Column", "202-555-0143")?.canonical, "phone");
});

test("drops low-confidence heuristic matches at threshold", () => {
  const result = new ContactMapper({ confidence_threshold: 0.8 }).map_payload({
    Mystery: "jane@example.com",
  });

  assert.equal(result.normalized.email, undefined);
  assert.equal(result.unmapped.Mystery, "jane@example.com");
  assert.match(result.warnings[0] ?? "", /dropped low-confidence/);

  const phone = new ContactMapper().map_payload(
    { Mystery: "202-555-0143" },
    { confidence_threshold: 0.95 },
  );
  assert.equal(
    phone.warnings[0],
    "'Mystery': dropped low-confidence match to 'phone' (confidence 0.60 < threshold 0.95)",
  );
});

test("header cache can be bounded, cleared, and disabled", () => {
  const mapper = new ContactMapper({ header_cache_max_size: 2 });
  mapper.map_payload({ fname: "A" });
  mapper.map_payload({ surname: "B" });
  mapper.map_payload({ employer: "C" });

  assert.deepEqual(mapper.cache_info(), {
    size: 2,
    max_size: 2,
    cacheable_pipeline: true,
  });

  mapper.clear_cache();
  assert.equal(mapper.cache_info().size, 0);
  assert.throws(
    () => (mapper.cache_info as unknown as (extra: unknown) => unknown)(1),
    { name: "TypeError", message: "ContactMapper.cache_info() takes 1 positional argument but 2 were given" },
  );
  assert.throws(
    () => (mapper.clear_cache as unknown as (extra: unknown) => unknown)(1),
    { name: "TypeError", message: "ContactMapper.clear_cache() takes 1 positional argument but 2 were given" },
  );

  const disabled = new ContactMapper({ header_cache_max_size: 0 });
  disabled.map_payload({ fname: "A" });
  assert.equal(disabled.cache_info().size, 0);

  assert.throws(
    () => new ContactMapper({ header_cache_max_size: -1 }),
    { name: "ValueError", message: "header_cache_max_size must be non-negative or None" },
  );
  assert.throws(
    () => new ContactMapper({ header_cache_max_size: "2" as never }),
    { name: "TypeError", message: "'<' not supported between instances of 'str' and 'int'" },
  );
});

test("public strategy classes and custom strategy pipeline work", () => {
  const registry = new PatternRegistry();

  assert.equal(new ExactMatchStrategy(registry).match("fname")?.canonical, "first_name");
  const normalized = new NormalizedMatchStrategy(registry);
  const fuzzy = new FuzzyMatchStrategy(registry);
  const heuristic = new HeuristicMatchStrategy("US");
  assert.equal(normalized.match("FirstName")?.canonical, "first_name");
  assert.equal(fuzzy.match("Compny")?.canonical, "company");
  assert.equal(heuristic.match("Mystery", "jane@example.com")?.canonical, "email");
  for (const strategy of [normalized, fuzzy, heuristic]) {
    assert.equal("headerOnly" in strategy, false);
    assert.equal("registry" in strategy, false);
    assert.equal("defaultRegion" in strategy, false);
  }

  const AnyExact = ExactMatchStrategy as unknown as new (...args: unknown[]) => ExactMatchStrategy;
  const AnyNormalized = NormalizedMatchStrategy as unknown as new (...args: unknown[]) => NormalizedMatchStrategy;
  const AnyFuzzy = FuzzyMatchStrategy as unknown as new (...args: unknown[]) => FuzzyMatchStrategy;
  const AnyHeuristic = HeuristicMatchStrategy as unknown as new (...args: unknown[]) => HeuristicMatchStrategy;
  assert.throws(() => new AnyExact(), {
    name: "TypeError",
    message: "ExactMatchStrategy.__init__() missing 1 required positional argument: 'registry'",
  });
  assert.throws(() => new AnyExact(registry, "extra"), {
    name: "TypeError",
    message: "ExactMatchStrategy.__init__() takes 2 positional arguments but 3 were given",
  });
  assert.throws(() => new AnyNormalized(), {
    name: "TypeError",
    message: "NormalizedMatchStrategy.__init__() missing 1 required positional argument: 'registry'",
  });
  assert.throws(() => new AnyNormalized(registry, "extra"), {
    name: "TypeError",
    message: "NormalizedMatchStrategy.__init__() takes 2 positional arguments but 3 were given",
  });
  assert.throws(() => new AnyFuzzy(), {
    name: "TypeError",
    message: "FuzzyMatchStrategy.__init__() missing 1 required positional argument: 'registry'",
  });
  assert.throws(() => new AnyFuzzy(registry, "extra"), {
    name: "TypeError",
    message: "FuzzyMatchStrategy.__init__() takes 2 positional arguments but 3 were given",
  });
  assert.throws(() => new AnyHeuristic("US", "extra"), {
    name: "TypeError",
    message: "HeuristicMatchStrategy.__init__() takes from 1 to 2 positional arguments but 3 were given",
  });

  class SourceStrategy extends MatchStrategy {
    get header_only(): boolean {
      return true;
    }

    get name(): string {
      return "custom";
    }

    match(header: string) {
      return header === "special"
        ? {
            original: header,
            canonical: "source",
            confidence: 0.99,
            strategy: this.name,
            service: null,
            is_matched: true,
          }
        : undefined;
    }
  }

  const result = new ContactMapper({ strategies: [new SourceStrategy()] }).map_payload({
    special: "partner",
    fname: "Jane",
  });
  assert.equal(result.normalized.source, "partner");
  assert.equal(result.unmapped.fname, "Jane");
  assert.equal(result.get_match("special")?.strategy, "custom");
});

test("strict mode raises on warnings", () => {
  assert.throws(
    () => new ContactMapper({ strict: true }).map_payload({ phone: "not a phone" }),
    /default_region\?/,
  );
});

test("mapper warnings are observable when Node warning listeners opt in", () => {
  const seen: string[] = [];
  const listener = (warning: Error) => {
    if (warning.name === "RolodexterWarning") {
      seen.push(warning.message);
    }
  };
  process.on("rolodexterWarning" as "warning", listener);
  try {
    new ContactMapper({ confidence_threshold: 0.95 }).map_payload({ Mystery: "202-555-0143" });
    new ContactMapper({ confidence_threshold: 0.99 }).compile_schema(["Compny"]);

    class CollisionFrame {
      [key: string]: unknown;

      columns = ["fname", "first_name"];
      data: Record<string, unknown[]> = { fname: ["Ada"], first_name: ["Lovelace"] };

      rename(args: { columns: Record<string, string> } | Record<string, string>): CollisionFrame {
        const columns = ((args as { columns?: Record<string, string> }).columns ?? args) as Record<string, string>;
        const out = new CollisionFrame();
        out.columns = this.columns.map((column) => columns[column] ?? column);
        out.data = Object.fromEntries(this.columns.map((column) => [columns[column] ?? column, [...(this.data[column] ?? [])]]));
        return out;
      }

      get(column: string): unknown[] {
        return this.data[column] ?? [];
      }

      set(column: string, values: unknown): void {
        this.data[column] = Array.isArray(values) ? values : [values];
      }
    }

    new ContactMapper().map_dataframe(new CollisionFrame());
  } finally {
    process.off("rolodexterWarning" as "warning", listener);
  }

  assert.ok(seen.some((warning) => warning.includes("dropped low-confidence match to 'phone'")));
  assert.ok(seen.some((warning) => warning.includes("dropped low-confidence match to 'company'")));
  assert.ok(seen.some((warning) => warning.includes("map_dataframe: column 'first_name' also maps to 'first_name'")));
});

test("normalizes list fields and dedupes collisions", () => {
  const result = new ContactMapper().map_payload({
    tags: "vip, newsletter",
    labels: '["vip", "beta"]',
  });

  assert.deepEqual(result.normalized.tags, ["vip", "newsletter", "beta"]);
  assert.deepEqual(
    new ContactMapper({ overrides: { tag: "tags" } }).map_payload({ tags: [], tag: ["a", "a"] }).normalized.tags,
    ["a"],
  );
  assert.deepEqual(new ContactMapper({ normalize: false }).map_payload({ phone: true, mobile: 1 }).normalized, {
    phone: true,
  });
  assert.deepEqual(new ContactMapper({ normalize: false }).map_payload({ email: true, "e-mail": 1 }).normalized, {
    email: true,
  });
});

test("extracts embedded phone numbers when opted in", () => {
  const result = new ContactMapper().map_payload(
    { notes: "Call +1-650-253-0000 before lunch" },
    { extract_embedded_phones: true },
  );

  assert.deepEqual(result.get_all_phones(), ["+16502530000"]);
});

test("embedded phone extraction is bounded and warns", () => {
  const manyNumbers = Array.from({ length: 7 }, () => "+1 202 555 1234").join(" ");
  const result = new ContactMapper().map_payload(
    { notes: manyNumbers },
    { extract_embedded_phones: true },
  );

  assert.equal(
    result.field_matches.filter((match) => match.strategy === "embedded_phone").length,
    5,
  );
  assert.match(result.warnings[0] ?? "", /for this field/);
});

// The 20-per-payload cap is reached from two directions and reported from two
// different places in the scan loop, so each route needs its own case. Python
// covered only the first of them, which is what made the second look dead.
const CAP_NUMBERS = [
  "+12132530000", "+12133334444", "+12135550000", "+12137363100", "+12132002000",
  "+16502530000", "+16503334444", "+16505550000", "+16507363100", "+16502002000",
  "+12122530000", "+12123334444", "+12125550000", "+12127363100", "+12122002000",
  "+13232530000", "+13233334444", "+13235550000", "+13237363100", "+13232002000",
  "+14082530000", "+14083334444",
];

function capPayload(counts: number[]): Record<string, string> {
  let cursor = 0;
  const payload: Record<string, string> = {};
  counts.forEach((count, index) => {
    const numbers = CAP_NUMBERS.slice(cursor, cursor + count);
    cursor += count;
    payload[`blob_${index}`] = `reach ${numbers.join(" or ")} anytime`;
  });
  return payload;
}

function capResult(counts: number[]) {
  const result = new ContactMapper().map_payload(capPayload(counts), {
    extract_embedded_phones: true,
  });
  return {
    embedded: result.field_matches.filter((match) => match.strategy === "embedded_phone").length,
    payloadWarnings: result.warnings.filter((warning) => /for this payload/.test(warning)),
    fieldWarnings: result.warnings.filter((warning) => /for this field/.test(warning)),
  };
}

test("embedded phone payload cap warns when a later field finds it spent", () => {
  // Four fields land exactly on 20 without any of them overflowing, so nothing
  // has warned yet when the fifth candidate is reached.
  const result = capResult([5, 5, 5, 5, 1]);

  assert.equal(result.embedded, 20);
  assert.equal(result.payloadWarnings.length, 1);
  assert.deepEqual(result.fieldWarnings, []);
});

test("embedded phone payload cap warns when an overflowing field trips it", () => {
  // A sixth number in the fourth field trips the per-field cap and the payload
  // cap in the same iteration.
  const result = capResult([5, 5, 5, 6]);

  assert.equal(result.embedded, 20);
  assert.equal(result.payloadWarnings.length, 1);
  assert.equal(result.fieldWarnings.length, 1);
});

test("embedded phone payload cap warns without a field warning on a partial field", () => {
  // The last field is allowed only four of its six numbers, so it overflows the
  // payload cap without ever reaching the per-field cap.
  const result = capResult([5, 5, 5, 1, 6]);

  assert.equal(result.embedded, 20);
  assert.equal(result.payloadWarnings.length, 1);
  assert.deepEqual(result.fieldWarnings, []);
});

test("embedded phone payload cap is reported only once", () => {
  // An overflowing field warns, and then two further candidates each find the
  // cap already spent. One warning, not three.
  const result = capResult([5, 5, 5, 6, 1, 1]);

  assert.equal(result.payloadWarnings.length, 1);
});

test("compile_schema returns a reusable header plan", () => {
  const schema = new ContactMapper().compile_schema(["First Name", "Mobile Phone", "Whatever"]);

  assert.ok(schema instanceof MappingSchema);
  assert.deepEqual(schema.column_map(), {
    "First Name": "first_name",
    "Mobile Phone": "phone",
  });
  assert.deepEqual(schema.unmatched_headers(), ["Whatever"]);
  assert.equal("columnMap" in schema, false);

  const result = schema.apply({ "First Name": "jane", "Mobile Phone": "(202) 555-0143" });
  assert.equal(result.normalized.first_name, "Jane");
  assert.equal(result.normalized.phone, "+12025550143");

  const gbResult = new ContactMapper({ default_region: "US" })
    .compile_schema(["mobile"])
    .apply({ mobile: "020 7946 0958" }, { default_region: "GB" });
  assert.equal(gbResult.normalized.phone, "+442079460958");
});

test("map_batch and map_stream agree", () => {
  const mapper = new ContactMapper();
  const rows = [{ fname: "A" }, { surname: "B" }, { email: "C@Example.COM" }];
  function* generatedRows() {
    yield { fname: "A" };
    yield { surname: "B" };
  }

  assert.deepEqual(
    mapper.map_batch(rows).map((result) => result.normalized),
    [...mapper.map_stream(rows)].map((result) => result.normalized),
  );
  assert.equal("mapPayload" in mapper, false);
  assert.equal("mapBatch" in mapper, false);
  assert.equal("mapStream" in mapper, false);
  assert.deepEqual(mapper.map_batch(generatedRows()).map((result) => result.normalized), [
    { first_name: "A" },
    { last_name: "B" },
  ]);
});

test("profile summarizes mapping readiness without materializing or overconsuming", () => {
  function* rows(): Generator<Record<string, unknown>> {
    yield { fname: "Ada", email: "ADA@EXAMPLE.COM" };
    yield { "First Name": "Grace", Mystery: "???" };
    yield { phone: "not a phone" };
  }
  const iterator = rows();

  const profile = new ContactMapper().profile(iterator, { max_rows: 2 });

  assert.ok(profile instanceof MappingProfile);
  assert.equal(profile.rows_seen, 2);
  assert.equal(profile.fields_seen, 4);
  assert.equal(profile.matched_count, 3);
  assert.equal(profile.unmatched_count, 1);
  assert.equal(profile.match_rate, 0.75);
  assert.deepEqual(profile.canonical_counts, { first_name: 2, email: 1 });
  assert.deepEqual(profile.unmapped_counts, { Mystery: 1 });
  assert.deepEqual(profile.strategy_counts, { exact: 2, normalized: 1, none: 1 });
  assert.deepEqual(iterator.next().value, { phone: "not a phone" });

  const warningProfile = new ContactMapper().profile([{ phone: "not a phone" }]);
  assert.equal(warningProfile.warning_count, 1);
  assert.deepEqual(warningProfile.warning_counts, { phone_normalization: 1 });
  assert.equal(warningProfile.to_dict().match_rate, 1);
  assert.match(warningProfile.explain(), /phone_normalization: 1/);

  assert.throws(
    () => new ContactMapper().profile([], { max_rows: -1 }),
    { name: "ValueError", message: /non-negative/ },
  );
  assert.throws(
    () => new ContactMapper().profile([], { max_rows: 1.5 }),
    { name: "TypeError", message: /integer or None/ },
  );
});

test("mapping results expose email and identity helpers for deduplication", () => {
  const result = new MappingResult(
    {
      email: [" A@EXAMPLE.COM ", "a@example.com"],
      phone: ["+12025550143", "+12025550143"],
      source_service: "HubSpot",
      source_id: [" 42 ", "42"],
    },
    {},
    [],
  );

  assert.deepEqual(result.get_all_emails(), [" A@EXAMPLE.COM ", "a@example.com"]);
  assert.deepEqual(result.get_identity_keys(), [
    "email:a@example.com",
    "phone:+12025550143",
    "source:hubspot:42",
  ]);

  // Two vendors means the id -> vendor correspondence is unknowable: the two
  // lists are built independently from raw key order, so pairing them by index
  // emitted a confident but fabricated key. Ambiguous now means unqualified.
  const multipleServices = new MappingResult(
    {
      source_service: ["HubSpot", "Salesforce"],
      source_id: ["42", "99", "orphan"],
    },
    {},
    [],
  );
  assert.deepEqual(multipleServices.get_identity_keys(), [
    "source_id:42",
    "source_id:99",
    "source_id:orphan",
  ]);
});

