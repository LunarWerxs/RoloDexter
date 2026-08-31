// map_dataframe reads and writes its input through a small adapter layer so
// it can drive a pandas DataFrame, a Series-backed shim, or a plain object
// with equal footing. mapper.test.ts covers the well-behaved array-backed
// case; these are the shapes that exercise the *other* side of each adapter
// branch, including the defensive ones that keep a surprising adapter from
// corrupting the output.
import assert from "node:assert/strict";
import { test } from "node:test";

import { ContactMapper } from "../src/index.js";
import type { DataFrameLike } from "../src/index.js";

/** Columns exposed array-like (length + indices) instead of iterable, and no get/set. */
class ArrayLikeFrame {
  [key: string]: unknown;

  columns: ArrayLike<unknown>;

  constructor(data: Record<string, unknown>) {
    const keys = Object.keys(data);
    const columns: Record<number | string, unknown> = { length: keys.length };
    keys.forEach((key, index) => {
      columns[index] = key;
    });
    this.columns = columns as unknown as ArrayLike<unknown>;
    for (const [key, values] of Object.entries(data)) {
      this[key] = values;
    }
  }

  rename(args: { columns: Record<string, string> } | Record<string, string>): ArrayLikeFrame {
    const columns = ((args as { columns?: Record<string, string> }).columns ?? args) as Record<string, string>;
    const data: Record<string, unknown> = {};
    for (let index = 0; index < this.columns.length; index += 1) {
      const old = String(this.columns[index]);
      data[columns[old] ?? old] = this[old];
    }
    return new ArrayLikeFrame(data);
  }
}

/** A pandas-Series-shaped column: not an array, but it has map() and iterates. */
class Series {
  constructor(readonly values: unknown[]) {}

  map(fn: (value: unknown) => unknown): Series {
    return new Series(this.values.map(fn));
  }

  [Symbol.iterator](): Iterator<unknown> {
    return this.values[Symbol.iterator]();
  }
}

/** A frame that stores columns off to the side and routes through get()/set(). */
class SeriesFrame {
  [key: string]: unknown;

  columns: string[];
  data: Record<string, unknown>;

  constructor(data: Record<string, unknown>) {
    this.columns = Object.keys(data);
    this.data = { ...data };
  }

  rename(args: { columns: Record<string, string> } | Record<string, string>): SeriesFrame {
    const columns = ((args as { columns?: Record<string, string> }).columns ?? args) as Record<string, string>;
    const renamed: Record<string, unknown> = {};
    for (const column of this.columns) {
      renamed[columns[column] ?? column] = this.data[column];
    }
    return new SeriesFrame(renamed);
  }

  get(column: string): unknown {
    return this.data[column];
  }

  set(column: string, values: unknown): void {
    this.data[column] = values;
  }
}

const asFrame = (value: unknown): DataFrameLike => value as DataFrameLike;

test("array-like columns work, and a frame without get/set is read and written directly", () => {
  const mapped = new ContactMapper().map_dataframe(
    asFrame(new ArrayLikeFrame({ fname: ["jane"], mobile: ["(202) 555-0143"] })),
  ) as ArrayLikeFrame;

  assert.deepEqual(Array.from({ length: mapped.columns.length }, (_, i) => mapped.columns[i]), [
    "first_name",
    "phone",
  ]);
  // Written back onto the frame itself, since there is no set() to call.
  assert.deepEqual(mapped.first_name, ["Jane"]);
  assert.deepEqual(mapped.phone, ["+12025550143"]);
});

test("columns that are neither iterable nor array-like are rejected by name", () => {
  assert.throws(
    () => new ContactMapper().map_dataframe(asFrame({ columns: 42, rename: () => ({}) })),
    { name: "TypeError", message: "map_dataframe expects DataFrame-like columns to be iterable or array-like" },
  );
  assert.throws(
    () => new ContactMapper().map_dataframe(asFrame({ nope: 1 })),
    {
      name: "TypeError",
      message:
        "map_dataframe expects an array of row objects or a DataFrame-like object with columns and rename()",
    },
  );
});

test("a Series-shaped column is normalized through its own map()", () => {
  const mapped = new ContactMapper().map_dataframe(
    asFrame(new SeriesFrame({ fname: new Series(["jane"]), mobile: new Series(["(202) 555-0143"]) })),
  ) as SeriesFrame;

  assert.deepEqual(mapped.columns, ["first_name", "phone"]);
  assert.deepEqual((mapped.data.first_name as Series).values, ["Jane"]);
  assert.deepEqual((mapped.data.phone as Series).values, ["+12025550143"]);
});

test("a column that is not a sequence is renamed but left unnormalized", () => {
  // A string is iterable, so normalizing it "per value" would rewrite it one
  // character at a time. It is skipped instead, and so is anything else with
  // no map() to drive.
  const strings = new ContactMapper().map_dataframe(
    asFrame(new SeriesFrame({ fname: "jane", mobile: "(202) 555-0143" })),
  ) as SeriesFrame;
  assert.deepEqual(strings.columns, ["first_name", "phone"]);
  assert.equal(strings.data.first_name, "jane");
  assert.equal(strings.data.phone, "(202) 555-0143");

  const number = new ContactMapper().map_dataframe(asFrame(new SeriesFrame({ fname: 42 }))) as SeriesFrame;
  assert.equal(number.data.first_name, 42);
});

test("an adapter whose map() returns a scalar cannot flood the warning stream", () => {
  // The phone path walks the normalized column looking for values that never
  // reached E.164. If map() hands back a bare string, walking it would yield
  // one bogus warning per character; if it hands back a number, walking it
  // would throw. Both are treated as "nothing to inspect".
  class ScalarMapSeries {
    constructor(readonly result: unknown) {}

    map(): unknown {
      return this.result;
    }
  }

  const seen: string[] = [];
  const listener = (warning: Error): void => {
    if (warning.name === "RolodexterWarning") {
      seen.push(warning.message);
    }
  };
  process.on("rolodexterWarning" as "warning", listener);
  let text: SeriesFrame;
  let numeric: SeriesFrame;
  try {
    text = new ContactMapper().map_dataframe(
      asFrame(new SeriesFrame({ mobile: new ScalarMapSeries("nope") })),
    ) as SeriesFrame;
    numeric = new ContactMapper().map_dataframe(
      asFrame(new SeriesFrame({ mobile: new ScalarMapSeries(7) })),
    ) as SeriesFrame;
  } finally {
    process.off("rolodexterWarning" as "warning", listener);
  }

  assert.equal(text.data.phone, "nope");
  assert.equal(numeric.data.phone, 7);
  assert.deepEqual(seen, []);
});

test("an adapter whose rename() returns nothing falls back to the frame it was given", () => {
  const frame = new SeriesFrame({ fname: ["jane"] });
  // An adapter that renames in place and returns nothing at all.
  (frame as unknown as { rename: () => undefined }).rename = () => undefined;
  const mapped = new ContactMapper().map_dataframe(asFrame(frame));

  assert.equal(mapped, frame);
});
