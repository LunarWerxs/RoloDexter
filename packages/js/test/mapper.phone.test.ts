// Split out of the former monolithic mapper.test.ts (2572 lines, over the
// oversized-files gate of 2500). Same tests, grouped by topic. Shared
// CLI/version-probe helpers live in _mapper_test_helpers.ts.
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  format_e164,
  format_international,
  format_national,
  is_number_match,
  is_valid,
  MatchType,
  NumberType,
  PhoneNumber,
  PhoneNumberMatch,
  PhoneNumberMatcher,
  number_type,
  parse,
} from "../src/index.js";

test("public phone helpers mirror Python phone module basics", () => {
  const phone = parse("+1 650 253 0000");
  assert.ok(phone);

  assert.equal(phone.calling_code, 1);
  assert.equal(phone.national_number, "6502530000");
  assert.equal(phone.e164, "+16502530000");
  assert.equal(phone.is_valid, true);
  assert.equal(phone.is_possible, true);
  assert.equal(phone.toString(), "+16502530000");
  assert.equal(phone.country_codes[0], "US");
  assert.ok(phone.country_codes.includes("CA"));
  assert.equal("_phoneNumber" in phone, false);
  assert.equal("callingCode" in phone, false);
  assert.equal("nationalNumber" in phone, false);

  assert.equal(format_international(phone), "+1 650-253-0000");
  assert.equal(format_national(phone), "(650) 253-0000");
  assert.equal(number_type(phone), NumberType.FIXED_LINE_OR_MOBILE);
  assert.equal(is_valid("+1 650 253 0000"), true);
  assert.equal(is_number_match("+1 650 253 0000", "6502530000", "US"), MatchType.EXACT_MATCH);

  const tel = parse("tel:+1-650-253-0000;ext=123");
  assert.equal(tel?.extension, "123");
  assert.equal(format_e164("tel:+1-650-253-0000;ext=123"), "+16502530000");
  assert.equal(format_e164("011 44 20 7946 0958"), "+442079460958");
  assert.equal(format_e164("+1-800-FLOWERS"), "+18003569377");
  assert.equal(format_e164("not a phone", "GB"), null);
  assert.equal(parse("not a phone"), null);
  assert.equal(parse("not a phone", "GB"), null);
  for (const value of [null, 123, true, {}, []]) {
    assert.equal(parse(value as never, "US"), null);
    assert.equal(format_e164(value as never, "US"), null);
    assert.equal(is_valid(value as never, "US"), false);
  }
});

test("phone helpers mirror Python extension and match semantics", () => {
  const local = parse("555-1212", "US")!;
  assert.equal(local.e164, "+15551212");
  assert.equal(local.is_possible, true);
  assert.equal(local.is_valid, false);
  assert.equal(format_national(local), "555-1212");
  assert.equal(parse("+1 555 123 4567 ext 890")?.extension, "890");
  assert.equal(parse("+1 555 123 4567 ext. 42")?.extension, "42");
  assert.equal(parse("+44 20 7946 0958 extn 100")?.extension, "100");
  assert.equal(parse("+1 555 123 4567 extension 999")?.extension, "999");
  assert.equal(parse("+1 555 123 4567 x 55")?.extension, "55");
  assert.equal(parse("202-555-1234x9", "US")?.extension, "9");
  assert.equal(format_e164("202-555-1234 x9", "US"), "+12025551234");
  assert.equal(parse("+1 555 123 4567 # 77")?.extension, "77");
  assert.equal(parse("+1 555 123 4567;ext=200")?.extension, "200");

  assert.equal(is_number_match("+15551234567 ext 42", "+1 555 123 4567 ext 42"), MatchType.EXACT_MATCH);
  assert.equal(is_number_match("+1 202 555 1234 ext 9", "202-555-1234 x9", "US"), MatchType.EXACT_MATCH);
  assert.equal(is_number_match("+12025551234 ext 42", "+12025551234"), MatchType.SHORT_NSN_MATCH);
  assert.equal(is_number_match("+12025551234 ext 42", "+12025551234 ext 43"), MatchType.NO_MATCH);
  assert.equal(is_number_match("2025551234", "5551234", "US"), MatchType.SHORT_NSN_MATCH);
  assert.equal(is_number_match("+1 202-555-0123", "+44 20 2555 0123", "US"), MatchType.NO_MATCH);
  assert.equal(is_number_match("hello", "+15551234567"), MatchType.NOT_A_NUMBER);
});

test("phone number_type mirrors Python libphonenumber metadata", () => {
  assert.equal(number_type(parse("+18005551212")!), NumberType.TOLL_FREE);
  assert.equal(number_type(parse("+19002001234")!), NumberType.PREMIUM_RATE);
  assert.equal(number_type(parse("+12025551234")!), NumberType.FIXED_LINE_OR_MOBILE);
  assert.equal(number_type(parse("+447911123456")!), NumberType.MOBILE);
  assert.equal(number_type(parse("+442079460958")!), NumberType.FIXED_LINE);
  assert.equal(number_type(parse("+33612345678")!), NumberType.MOBILE);
  assert.equal(number_type(parse("+919876543210")!), NumberType.MOBILE);
  assert.equal(number_type(parse("+8613800138000")!), NumberType.MOBILE);
  assert.equal(number_type(parse("+4915112345678")!), NumberType.MOBILE);
  assert.equal(number_type(parse("+29012345")!), NumberType.UNKNOWN);
});

test("PhoneNumber fallback construction mirrors Python defensive paths", () => {
  const phone = new PhoneNumber(44, "2079460958", "x");
  const positional = new PhoneNumber(44, "2079460958", "x");
  const manualNanp = new PhoneNumber(1, "2025550143", "raw", "99");
  const manualLocal = new PhoneNumber(1, "5551212", "raw");

  assert.equal(phone.e164, "+442079460958");
  assert.equal(positional.e164, "+442079460958");
  assert.equal(phone.is_valid, false);
  assert.equal(phone.is_possible, false);
  assert.equal(format_international(phone), "+44 2079460958");
  assert.equal(format_national(phone), "2079460958");
  assert.equal(format_international(manualNanp), "+1 2025550143");
  assert.equal(format_national(manualNanp), "2025550143");
  assert.equal(format_national(manualLocal), "5551212");
  assert.equal(number_type(phone), NumberType.UNKNOWN);
  assert.equal(is_number_match(new PhoneNumber(1, "2025551234", "x"), "+12025551234"), MatchType.EXACT_MATCH);
  assert.equal(is_number_match(null as unknown as string, null as unknown as string), MatchType.NOT_A_NUMBER);
  assert.throws(() => (parse as unknown as () => unknown)(), {
    name: "TypeError",
    message: "parse() missing 1 required positional argument: 'raw'",
  });
  assert.throws(() => (parse as unknown as (raw: string, region: string, extra: string) => unknown)("x", "US", "extra"), {
    name: "TypeError",
    message: "parse() takes from 1 to 2 positional arguments but 3 were given",
  });
  assert.throws(() => (format_e164 as unknown as () => unknown)(), {
    name: "TypeError",
    message: "format_e164() missing 1 required positional argument: 'raw'",
  });
  assert.throws(() => (is_valid as unknown as (raw: string, region: string, extra: string) => unknown)("x", "US", "extra"), {
    name: "TypeError",
    message: "is_valid() takes from 1 to 2 positional arguments but 3 were given",
  });
  assert.throws(() => (is_number_match as unknown as () => unknown)(), {
    name: "TypeError",
    message: "is_number_match() missing 2 required positional arguments: 'a' and 'b'",
  });
  assert.throws(() => (is_number_match as unknown as (a: string) => unknown)("x"), {
    name: "TypeError",
    message: "is_number_match() missing 1 required positional argument: 'b'",
  });
  assert.throws(() => (is_number_match as unknown as (a: string, b: string, region: string, extra: string) => unknown)("x", "y", "US", "extra"), {
    name: "TypeError",
    message: "is_number_match() takes from 2 to 3 positional arguments but 4 were given",
  });
  assert.throws(() => format_international({} as never), {
    name: "AttributeError",
    message: "'dict' object has no attribute '_pn_obj'",
  });
  assert.throws(() => format_national("x" as never), {
    name: "AttributeError",
    message: "'str' object has no attribute '_pn_obj'",
  });
  assert.throws(() => number_type(null as never), {
    name: "AttributeError",
    message: "'NoneType' object has no attribute '_pn_obj'",
  });
});

test("PhoneNumberMatcher extracts bounded free-text matches", () => {
  const matcher = new PhoneNumberMatcher(
    "Call +1 650 253 0000 or +44 20 7946 0958",
    "US",
    { max_matches: 1 },
  );
  const matches = [...matcher];

  assert.equal(matcher.length, 1);
  assert.equal(matcher.has_next(), true);
  for (const name of ["text", "defaultRegion", "maxMatches", "matches", "findAll", "allMatches", "hasNext"]) {
    assert.equal(name in matcher, false, `${name} should stay private`);
  }
  assert.equal(matches[0]?.raw_string, "+1 650 253 0000");
  assert.equal(matches[0]?.number.e164, "+16502530000");

  const match = new PhoneNumberMatch(1, 4, "raw", new PhoneNumber(1, "2025550143", "raw"));
  assert.equal(String(match), "PhoneNumberMatch(start=1, end=4, number=+12025550143)");
  assert.equal(new PhoneNumberMatcher(null as never, "US").length, 0);
  assert.deepEqual([...new PhoneNumberMatcher(null as never, "US")], []);
  assert.throws(
    () => new PhoneNumberMatcher("a +1 202 555 0143", "US", { max_matches: "1" as never }),
    { name: "TypeError", message: "'>' not supported between instances of 'str' and 'int'" },
  );
});

