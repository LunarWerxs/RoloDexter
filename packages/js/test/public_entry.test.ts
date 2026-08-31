// The published "rolodexter" entry point re-exports the root surface from
// index.ts, but wraps generate_language so that calling it the way Python
// callers do — positionally — fails with Python's own arity message instead
// of silently ignoring the extra argument. Nothing exercised that wrapper.
import assert from "node:assert/strict";
import { test } from "node:test";

import { generate_language } from "../src/public.js";
import { __all__ } from "../src/index.js";

test("the published generate_language enforces Python's positional arity", () => {
  assert.throws(
    () => (generate_language as unknown as () => unknown)(),
    {
      name: "TypeError",
      message: "generate_language() missing 1 required positional argument: 'lang_code'",
    },
  );
  assert.throws(
    () => (generate_language as unknown as (lang: string, options: unknown, extra: unknown) => unknown)("es", {}, "extra"),
    {
      name: "TypeError",
      message: "generate_language() takes 1 positional argument but 3 were given",
    },
  );
});

test("generate_language is part of the advertised root surface", () => {
  assert.equal(typeof generate_language, "function");
  assert.ok(__all__.includes("generate_language"));
});
