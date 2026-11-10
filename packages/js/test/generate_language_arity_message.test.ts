// generate_language takes one required and one optional positional argument,
// so Python's arity message for too many arguments is "takes from 1 to 2
// positional arguments". The published entry must say that, not "takes 1".
import assert from "node:assert/strict";
import { test } from "node:test";

import { generate_language } from "../src/public.js";

test("generate_language with three positional arguments reports the 1-to-2 arity range", () => {
  assert.throws(
    () => (generate_language as unknown as (lang: string, options: unknown, extra: unknown) => unknown)("es", {}, "extra"),
    {
      name: "TypeError",
      message: "generate_language() takes from 1 to 2 positional arguments but 3 were given",
    },
  );
});
