// Split out of the former monolithic mapper.test.ts (2572 lines, over the
// oversized-files gate of 2500). Same tests, grouped by topic. Shared
// CLI/version-probe helpers live in _mapper_test_helpers.ts.
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  AddressNormalizer,
  BooleanNormalizer,
  ContactMapper,
  EmailNormalizer,
  FieldMatch,
  ListNormalizer,
  MappingResult,
  MappingSchema,
  NameNormalizer,
  PhoneNumber,
  PhoneNumberMatch,
  PhoneNormalizer,
  PostalCodeNormalizer,
  StringNormalizer,
  normalize_value,
  parse,
} from "../src/index.js";

test("standalone normalize_value covers public normalizers", () => {
  assert.equal(normalize_value("email", " A@EXAMPLE.COM "), "a@example.com");
  assert.equal(normalize_value("email", " A@EXAMPLE.COM "), "a@example.com");
  assert.deepEqual(normalize_value("tags", "a;b"), ["a", "b"]);
  assert.equal(normalize_value("postal_code", "k1a0b1"), "K1A 0B1");
  assert.equal(normalize_value("phone", "(202) 555-0143"), "(202) 555-0143");
  assert.equal(normalize_value("phone", "(202) 555-0143", { default_region: "US" }), "+12025550143");
  assert.equal(normalize_value("phone", "555-1212", { default_region: "US" }), "+15551212");
  assert.throws(
    () => (normalize_value as unknown as () => unknown)(),
    { name: "TypeError", message: "normalize_value() missing 2 required positional arguments: 'canonical_field' and 'value'" },
  );
  assert.throws(
    () => (normalize_value as unknown as (field: string) => unknown)("email"),
    { name: "TypeError", message: "normalize_value() missing 1 required positional argument: 'value'" },
  );
  assert.throws(
    () => (normalize_value as unknown as (field: string, value: unknown, defaultRegion: string) => unknown)("phone", "(202) 555-0143", "US"),
    { name: "TypeError", message: "normalize_value() takes 2 positional arguments but 3 were given" },
  );
  assert.equal(PhoneNormalizer.normalize("(202) 555-0143"), "(202) 555-0143");
  assert.equal(PhoneNormalizer.normalize("2025550143", { default_region: "US" }), "+12025550143");
  assert.throws(
    () => (PhoneNormalizer.normalize as unknown as () => unknown)(),
    { name: "TypeError", message: "PhoneNormalizer.normalize() missing 1 required positional argument: 'value'" },
  );
  assert.throws(
    () => PhoneNormalizer.normalize("2025550143", "US" as never),
    { name: "TypeError", message: "PhoneNormalizer.normalize() takes 2 positional arguments but 3 were given" },
  );
  assert.throws(
    () => (EmailNormalizer.normalize as unknown as (value: unknown, extra: unknown) => unknown)("a@example.com", "extra"),
    { name: "TypeError", message: "EmailNormalizer.normalize() takes 1 positional argument but 2 were given" },
  );
  assert.throws(
    () => (StringNormalizer.normalize as unknown as (value: unknown, extra: unknown) => unknown)("x", "extra"),
    { name: "TypeError", message: "StringNormalizer.normalize() takes 1 positional argument but 2 were given" },
  );
  assert.throws(
    () => (AddressNormalizer.normalize as unknown as (value: unknown, extra: unknown) => unknown)("x", "extra"),
    { name: "TypeError", message: "AddressNormalizer.normalize() takes 1 positional argument but 2 were given" },
  );
  assert.throws(
    () => (PostalCodeNormalizer.normalize as unknown as (value: unknown, extra: unknown) => unknown)("123", "extra"),
    { name: "TypeError", message: "PostalCodeNormalizer.normalize() takes 2 positional arguments but 3 were given" },
  );
  assert.throws(
    () => (BooleanNormalizer.normalize as unknown as (value: unknown, extra: unknown) => unknown)("yes", "extra"),
    { name: "TypeError", message: "BooleanNormalizer.normalize() takes 2 positional arguments but 3 were given" },
  );
  assert.throws(
    () => (ListNormalizer.normalize as unknown as (value: unknown, extra: unknown) => unknown)("a,b", "extra"),
    { name: "TypeError", message: "ListNormalizer.normalize() takes 1 positional argument but 2 were given" },
  );
  assert.throws(
    () => (NameNormalizer.normalize as unknown as (value: unknown, extra: unknown) => unknown)("Ada", "extra"),
    { name: "TypeError", message: "NameNormalizer.normalize() takes 2 positional arguments but 3 were given" },
  );
  assert.throws(
    () => (NameNormalizer.parse as unknown as (value: string, extra: unknown) => unknown)("Ada", "extra"),
    { name: "TypeError", message: "NameNormalizer.parse() takes 2 positional arguments but 3 were given" },
  );
  assert.deepEqual(normalize_value("tags", "[true,false,null,7]"), ["True", "False", "None", "7"]);
  assert.deepEqual(ListNormalizer.normalize([{ a: 1 }, ["x"], true, null]), ["{'a': 1}", "['x']", "True", "None"]);
  assert.deepEqual(normalize_value("tags", '[{"a":1},["x"],true,null]'), ["{'a': 1}", "['x']", "True", "None"]);
});

test("NameNormalizer keeps a deliberate inner capital and re-cases words without one", () => {
  // Mirrors tests/test_normalizers.py::TestNameDeliberateCapitals. Since
  // 2.12.0 both packages apply this rule; every expectation here is also
  // what the Python package returns for the same input.
  assert.equal(NameNormalizer.normalize("DeAngelo"), "DeAngelo");
  assert.equal(NameNormalizer.normalize("LaToya Jackson"), "LaToya Jackson");
  assert.equal(NameNormalizer.normalize("leonardo DiCaprio"), "Leonardo DiCaprio");
  assert.equal(NameNormalizer.normalize("JoAnne Smith-DeAngelo"), "JoAnne Smith-DeAngelo");
  assert.equal(NameNormalizer.normalize("smith, DeAngelo"), "DeAngelo Smith");
  assert.equal(NameNormalizer.normalize("DiCaprio, LaToya"), "LaToya DiCaprio");
  // Unicode-aware: an inner capital outside ASCII is still one.
  assert.equal(NameNormalizer.normalize("DeÁngelo"), "DeÁngelo");
  // The source's casing wins over the apostrophe and Mc/Mac rules too, and a
  // hyphenated Mac surname keeps its second half cased: the Mac rule used to
  // run before the hyphen split and returned "MacIntyre-smith".
  assert.equal(NameNormalizer.normalize("O'DeAngelo"), "O'DeAngelo");
  assert.equal(NameNormalizer.normalize("Smith, O'DeAngelo"), "O'DeAngelo Smith");
  assert.equal(NameNormalizer.normalize("McDeAngelo"), "McDeAngelo");
  assert.equal(NameNormalizer.normalize("Anne-Marie McDeAngelo"), "Anne-Marie McDeAngelo");
  assert.equal(NameNormalizer.normalize("MacARTHUR"), "MacARTHUR");
  assert.equal(NameNormalizer.normalize("MacIntyre-Smith"), "MacIntyre-Smith");
  assert.equal(NameNormalizer.normalize("MACINTYRE-SMITH"), "MacIntyre-Smith");
  assert.equal(NameNormalizer.normalize("macarthur"), "MacArthur");
  // All-upper and all-lower carry no signal and are re-cased from rules.
  assert.equal(NameNormalizer.normalize("DEANGELO"), "Deangelo");
  assert.equal(NameNormalizer.normalize("deangelo"), "Deangelo");
  assert.equal(NameNormalizer.normalize("LATOYA JACKSON"), "Latoya Jackson");
  assert.equal(NameNormalizer.normalize("MCDONALD"), "McDonald");
  assert.equal(NameNormalizer.normalize("MacArthur PhD"), "MacArthur Ph.D.");
  assert.equal(NameNormalizer.normalize("jane DeAngelo phd"), "Jane DeAngelo Ph.D.");
  assert.equal(NameNormalizer.normalize("DR. jane van doe jr."), "Dr. Jane van Doe Jr.");
});

test("NameNormalizer mirrors Python title, suffix, particle, and hyphen handling", () => {
  assert.equal(NameNormalizer.normalize("jane van der berg"), "Jane van der Berg");
  assert.equal(NameNormalizer.normalize("jean-pierre"), "Jean-Pierre");
  assert.equal(NameNormalizer.normalize("maria del carmen"), "Maria del Carmen");
  assert.equal(NameNormalizer.normalize("Dr. Jane Doe Jr."), "Dr. Jane Doe Jr.");
  assert.equal(NameNormalizer.normalize("john doe jr"), "John Doe Jr");
  assert.equal(NameNormalizer.normalize("john doe sr"), "John Doe Sr");
  assert.equal(NameNormalizer.normalize("dr jane doe"), "Dr Jane Doe");
  assert.equal(NameNormalizer.normalize("mr john q public phd"), "Mr John Q Public Ph.D.");
  assert.equal(NameNormalizer.normalize("john doe ph.d."), "John Doe Ph.d.");
  assert.equal(NameNormalizer.normalize("Dr Jane A. Doe PhD"), "Dr Jane A. Doe Ph.D.");
  assert.equal(NameNormalizer.normalize("Ms Ana Maria del Carmen"), "Ms Ana Maria del Carmen");
  assert.equal(NameNormalizer.normalize('john "jack" smith'), "John Smith (jack)");
  assert.equal(NameNormalizer.normalize('John "Johnny" Doe'), "John Doe (johnny)");
  assert.equal(NameNormalizer.normalize("public, john q"), "John Q Public");
  assert.equal(NameNormalizer.normalize("The Hon. Jane Doe"), "the Hon. Jane Doe");
  assert.equal(NameNormalizer.normalize("mr. and mrs. john smith"), "Mr. and Mrs. John Smith");
  assert.equal(NameNormalizer.normalize("Capt. Jane Smith"), "Capt. Jane Smith");
  assert.equal(NameNormalizer.normalize("Jane Smith MD"), "Jane Smith M.D.");
  assert.equal(NameNormalizer.normalize("Jane Smith V"), "Jane Smith V");
  assert.equal(NameNormalizer.normalize("JOHN MACDONALD"), "John MacDonald");
  assert.equal(NameNormalizer.normalize("smith, john phd"), "John Smith Ph.D.");
  assert.equal(NameNormalizer.normalize("smith, john ph.d."), "John Smith Ph.d.");
  assert.equal(NameNormalizer.normalize("jane doe m.d."), "Jane Doe M.d.");
  assert.equal(NameNormalizer.normalize("the hon jane doe"), "the Hon Jane Doe");
  assert.equal(NameNormalizer.normalize("the honorable jane doe"), "the Honorable Jane Doe");
  assert.equal(NameNormalizer.normalize("King Jr., Martin Luther"), "Martin Luther King Jr.");
  assert.equal(NameNormalizer.normalize("Leonardo da Vinci"), "Leonardo da Vinci");
  assert.equal(NameNormalizer.normalize("Jane Q. Doe, CPA"), "Jane Q. Doe Cpa");
  assert.equal(NameNormalizer.normalize("Doe, Jane Q., CPA"), "Jane Q. Doe Cpa");
  assert.equal(NameNormalizer.normalize("His Excellency John Doe"), "His Excellency John Doe");
  assert.equal(NameNormalizer.normalize("Dame Judi Dench"), "Dame Judi Dench");
  assert.equal(NameNormalizer.normalize("Mx Alex Doe"), "Mx Alex Doe");
  assert.equal(NameNormalizer.normalize("St. John-Smith"), "St. John-Smith");

  assert.deepEqual(NameNormalizer.parse("Dr. Jane Doe Jr."), {
    title: "Dr.",
    first: "Jane",
    middle: "",
    last: "Doe",
    suffix: "Jr.",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("John Fitzgerald Kennedy"), {
    title: "",
    first: "John",
    middle: "Fitzgerald",
    last: "Kennedy",
    suffix: "",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse('John "Johnny" Doe'), {
    title: "",
    first: "John",
    middle: "",
    last: "Doe",
    suffix: "",
    nickname: "Johnny",
  });
  assert.deepEqual(NameNormalizer.parse("mr john q public phd"), {
    title: "mr",
    first: "john",
    middle: "q",
    last: "public",
    suffix: "phd",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("sir isaac newton"), {
    title: "sir",
    first: "isaac",
    middle: "",
    last: "newton",
    suffix: "",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("rev dr martin luther king jr"), {
    title: "rev dr",
    first: "martin",
    middle: "luther",
    last: "king",
    suffix: "jr",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("public, john q"), {
    title: "",
    first: "john",
    middle: "q",
    last: "public",
    suffix: "",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("The Hon. Jane Doe"), {
    title: "The Hon.",
    first: "Jane",
    middle: "",
    last: "Doe",
    suffix: "",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("mr. and mrs. john smith"), {
    title: "mr. and mrs.",
    first: "john",
    middle: "",
    last: "smith",
    suffix: "",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("Capt. Jane Smith"), {
    title: "Capt.",
    first: "Jane",
    middle: "",
    last: "Smith",
    suffix: "",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("Jane Smith MD"), {
    title: "",
    first: "Jane",
    middle: "",
    last: "Smith",
    suffix: "MD",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("Jane Smith V"), {
    title: "",
    first: "Jane",
    middle: "",
    last: "Smith",
    suffix: "V",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("ST. JOHN SMITH"), {
    title: "ST.",
    first: "JOHN",
    middle: "",
    last: "SMITH",
    suffix: "",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("the honorable jane doe"), {
    title: "the honorable",
    first: "jane",
    middle: "",
    last: "doe",
    suffix: "",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("King Jr., Martin Luther"), {
    title: "",
    first: "Martin",
    middle: "Luther",
    last: "King",
    suffix: "Jr.",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("Doe, Jane Q., CPA"), {
    title: "",
    first: "Jane",
    middle: "Q.",
    last: "Doe",
    suffix: "CPA",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("His Excellency John Doe"), {
    title: "His Excellency",
    first: "John",
    middle: "",
    last: "Doe",
    suffix: "",
    nickname: "",
  });
  assert.deepEqual(NameNormalizer.parse("St. John-Smith"), {
    title: "St.",
    first: "",
    middle: "",
    last: "John-Smith",
    suffix: "",
    nickname: "",
  });
});

test("address casing keeps Python hyphen behavior separate from names", () => {
  assert.equal(AddressNormalizer.normalize("winston-salem"), "Winston-salem");
  assert.equal(AddressNormalizer.normalize("machine shop rd"), "Machine Shop Rd");
  assert.equal(NameNormalizer.normalize("jean-pierre"), "Jean-Pierre");
  assert.equal(NameNormalizer.normalize("Ada,a@example.com"), "A@Example.com Ada");
});

test("Python-shaped mapping result surface is available", () => {
  const result = new ContactMapper().map_payload({ fname: "jane", Whatever: "x" });

  assert.equal(result.matched_count, 1);
  assert.equal(result.unmatched_count, 1);
  assert.equal(result.match_rate, 0.5);
  assert.equal(result.field_matches.length, 2);
  assert.equal(result.get_match("fname")?.is_matched, true);
  assert.equal(result.get_match("missing"), null);
  assert.deepEqual(result.to_dict().normalized, { first_name: "Jane" });
  assert.equal("getMatch" in result, false);
  assert.equal("getAllPhones" in result, false);
  assert.equal("toJSON" in result, false);

  const schema = new ContactMapper().compile_schema(["fname"]);
  assert.deepEqual(schema.column_map(), { fname: "first_name" });
  assert.deepEqual(Object.keys(schema.matches), ["fname"]);
  assert.equal(schema.matches.fname.canonical, "first_name");
  assert.equal(schema.matches.get("fname")?.canonical, "first_name");
  assert.equal(schema.matches.get("missing"), null);
  const gbSchema = new ContactMapper().compile_schema(["Mobile Phone"], { default_region: "GB" });
  assert.equal(gbSchema.default_region, "GB");
  assert.equal("defaultRegion" in gbSchema, false);

  const positional = new MappingResult({}, {}, [new FieldMatch("x", "unknown", 0, "none")]);
  assert.equal(positional.unmatched_count, 1);
  assert.throws(
    () => (positional.field_matches as FieldMatch[]).push(new FieldMatch("y", "unknown", 0, "none")),
    TypeError,
  );

  const match = new FieldMatch("x", "unknown", 0, "none");
  assert.equal(Object.isExtensible(match), false);
  assert.throws(() => {
    (match as unknown as Record<string, unknown>).extra = 1;
  }, TypeError);
  const details = new MappingResult({}, {}, [match]).to_dict().details as Array<Record<string, unknown>>;
  assert.deepEqual(details[0], {
    original: "x",
    canonical: "unknown",
    confidence: 0,
    strategy: "none",
    service: null,
  });
  assert.match(String(match), /^FieldMatch\(/);
  assert.match(String(new MappingResult({}, {}, [match])), /^MappingResult\(/);
});

test("public model constructors reject JS-only object-shaped calls", () => {
  const FieldMatchObjectCtor = FieldMatch as unknown as new (arg: unknown) => FieldMatch;
  assert.throws(
    () => new FieldMatchObjectCtor({ original: "x", canonical: "unknown", confidence: 0, strategy: "none" }),
    {
      name: "TypeError",
      message: "FieldMatch.__init__() missing 3 required positional arguments: 'canonical', 'confidence', and 'strategy'",
    },
  );

  const MappingResultObjectCtor = MappingResult as unknown as new (arg: unknown) => MappingResult;
  assert.throws(
    () => new MappingResultObjectCtor({ normalized: {}, unmapped: {}, field_matches: [] }),
    {
      name: "TypeError",
      message: "MappingResult.__init__() missing 2 required positional arguments: 'unmapped' and 'field_matches'",
    },
  );

  const MappingSchemaObjectCtor = MappingSchema as unknown as new (arg: unknown) => MappingSchema;
  assert.throws(
    () => new MappingSchemaObjectCtor({ matches: {}, mapper: new ContactMapper() }),
    {
      name: "TypeError",
      message: "MappingSchema.__init__() missing 1 required positional argument: 'mapper'",
    },
  );

  const PhoneNumberObjectCtor = PhoneNumber as unknown as new (arg: unknown) => PhoneNumber;
  assert.throws(
    () => new PhoneNumberObjectCtor({ calling_code: 1, national_number: "2025550143", raw: "x" }),
    {
      name: "TypeError",
      message: "PhoneNumber.__init__() missing 2 required positional arguments: 'national_number' and 'raw'",
    },
  );

  const AnyFieldMatch = FieldMatch as unknown as new (...args: unknown[]) => FieldMatch;
  assert.throws(() => new AnyFieldMatch(), {
    name: "TypeError",
    message: "FieldMatch.__init__() missing 4 required positional arguments: 'original', 'canonical', 'confidence', and 'strategy'",
  });
  assert.throws(() => new AnyFieldMatch("x", "unknown", 0, "none", null, "extra"), {
    name: "TypeError",
    message: "FieldMatch.__init__() takes from 5 to 6 positional arguments but 7 were given",
  });

  const AnyMappingResult = MappingResult as unknown as new (...args: unknown[]) => MappingResult;
  assert.throws(() => new AnyMappingResult(), {
    name: "TypeError",
    message: "MappingResult.__init__() missing 3 required positional arguments: 'normalized', 'unmapped', and 'field_matches'",
  });
  assert.throws(() => new AnyMappingResult({}, {}), {
    name: "TypeError",
    message: "MappingResult.__init__() missing 1 required positional argument: 'field_matches'",
  });
  assert.throws(() => new AnyMappingResult({}, {}, [], [], "extra"), {
    name: "TypeError",
    message: "MappingResult.__init__() takes from 4 to 5 positional arguments but 6 were given",
  });

  const AnyMappingSchema = MappingSchema as unknown as new (...args: unknown[]) => MappingSchema;
  assert.throws(() => new AnyMappingSchema(), {
    name: "TypeError",
    message: "MappingSchema.__init__() missing 2 required positional arguments: 'matches' and 'mapper'",
  });
  assert.throws(() => new AnyMappingSchema({}, new ContactMapper(), null, "extra"), {
    name: "TypeError",
    message: "MappingSchema.__init__() takes from 3 to 4 positional arguments but 5 were given",
  });

  const AnyPhoneNumber = PhoneNumber as unknown as new (...args: unknown[]) => PhoneNumber;
  assert.throws(() => new AnyPhoneNumber(), {
    name: "TypeError",
    message: "PhoneNumber.__init__() missing 3 required positional arguments: 'calling_code', 'national_number', and 'raw'",
  });
  assert.throws(() => new AnyPhoneNumber(1, "202"), {
    name: "TypeError",
    message: "PhoneNumber.__init__() missing 1 required positional argument: 'raw'",
  });
  assert.throws(() => new AnyPhoneNumber(1, "202", "raw", null, null, "extra"), {
    name: "TypeError",
    message: "PhoneNumber.__init__() takes from 4 to 6 positional arguments but 7 were given",
  });

  const AnyPhoneNumberMatch = PhoneNumberMatch as unknown as new (...args: unknown[]) => PhoneNumberMatch;
  assert.throws(() => new AnyPhoneNumberMatch(), {
    name: "TypeError",
    message: "PhoneNumberMatch.__init__() missing 4 required positional arguments: 'start', 'end', 'raw_string', and 'number'",
  });
  assert.throws(() => new AnyPhoneNumberMatch(1), {
    name: "TypeError",
    message: "PhoneNumberMatch.__init__() missing 3 required positional arguments: 'end', 'raw_string', and 'number'",
  });
  assert.throws(() => new AnyPhoneNumberMatch(1, 2, "raw", new PhoneNumber(1, "202", "raw"), "extra"), {
    name: "TypeError",
    message: "PhoneNumberMatch.__init__() takes 5 positional arguments but 6 were given",
  });
});

test("Python dataclass-like models reject public field reassignment", () => {
  const match = new FieldMatch("x", "unknown", 0, "none");
  assert.throws(() => {
    (match as unknown as Record<string, unknown>).original = "changed";
  }, { name: "FrozenInstanceError", message: "cannot assign to field 'original'" });

  const result = new MappingResult({ first_name: "Ada" }, {}, [match]);
  assert.throws(() => {
    (result as unknown as Record<string, unknown>).normalized = {};
  }, { name: "FrozenInstanceError", message: "cannot assign to field 'normalized'" });
  result.normalized.extra = "allowed like Python's mutable dict payloads";
  assert.equal(result.normalized.extra, "allowed like Python's mutable dict payloads");

  const schema = new ContactMapper().compile_schema(["fname"]);
  assert.throws(() => {
    (schema as unknown as Record<string, unknown>).matches = {};
  }, { name: "FrozenInstanceError", message: "cannot assign to field 'matches'" });
  schema.matches.set("extra", match);
  assert.equal(schema.matches.get("extra"), match);

  const phone = parse("+1 650 253 0000")!;
  assert.throws(() => {
    (phone as unknown as Record<string, unknown>).calling_code = 44;
  }, { name: "FrozenInstanceError", message: "cannot assign to field 'calling_code'" });
});

test("JS-only mapper aliases are not public", () => {
  const mapper = new ContactMapper();

  assert.deepEqual(mapper.map_payload({ Email: "ADA@EXAMPLE.COM" }).normalized, {
    email: "ada@example.com",
  });
  assert.equal("mapContact" in mapper, false);
  assert.equal("map_contact" in mapper, false);
  assert.equal("compileSchema" in mapper, false);
  assert.equal("mapDataFrame" in mapper, false);
  assert.equal("clearCache" in mapper, false);
  assert.equal("cacheInfo" in mapper, false);
  for (const name of ["normalize", "defaultRegion", "strict", "confidenceThreshold", "headerCacheMaxSize", "strategies", "headerCache", "resolve"]) {
    assert.equal(name in mapper, false, `${name} should stay private`);
  }
  assert.equal("registry" in mapper, true);
});

test("Python-shaped mapper option names are accepted", () => {
  const mapper = new ContactMapper({
    default_region: "GB",
    confidence_threshold: 0.8,
    header_cache_max_size: 1,
    default_service: "ignored",
  });

  assert.equal(mapper.map_payload({ phone: "020 7946 0958" }).normalized.phone, "+442079460958");
  assert.equal(mapper.cache_info().max_size, 1);

  const embedded = new ContactMapper().map_payload(
    { notes: "Call +1 650 253 0000" },
    { extract_embedded_phones: true },
  );
  assert.deepEqual(embedded.get_all_phones(), ["+16502530000"]);

  const schema = new ContactMapper().compile_schema(["Compny"], { confidence_threshold: 0.99 });
  assert.deepEqual(schema.column_map(), {});
  assert.throws(
    () => mapper.map_payload({ fname: " jane " }, { normalize: false } as never),
    { name: "TypeError", message: "ContactMapper.map_payload() got an unexpected keyword argument 'normalize'" },
  );
  assert.throws(
    () => new ContactMapper({ confidence_threshold: 2 }),
    { name: "ValueError", message: "confidence_threshold must be between 0.0 and 1.0" },
  );
});

