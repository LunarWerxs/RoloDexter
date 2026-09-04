// Split out of the former monolithic mapper.test.ts (2572 lines, over the
// oversized-files gate of 2500). Same tests, grouped by topic. Shared
// CLI/version-probe helpers live in _mapper_test_helpers.ts.
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  ContactMapper,
} from "../src/index.js";

test("map_dataframe rejects row arrays like Python pandas entry point", () => {
  const rows = [
    {
      fname: "jane",
      mobile: "(202) 555-0143",
      phone: "+1 202 555 0143",
      Whatever: "kept",
    },
  ];

  assert.throws(
    () => new ContactMapper().map_dataframe(rows as never),
    { name: "AttributeError", message: "'list' object has no attribute 'columns'" },
  );
  assert.deepEqual(rows[0], {
    fname: "jane",
    mobile: "(202) 555-0143",
    phone: "+1 202 555 0143",
    Whatever: "kept",
  });
});

test("map_dataframe accepts DataFrame-like adapters with columns and rename", () => {
  class FakeFrame {
    [key: string]: unknown;

    columns: string[];
    data: Record<string, unknown[]>;

    constructor(data: Record<string, unknown[]>) {
      this.columns = Object.keys(data);
      this.data = Object.fromEntries(Object.entries(data).map(([key, values]) => [key, [...values]]));
    }

    rename(args: { columns: Record<string, string> } | Record<string, string>): FakeFrame {
      const columns = ((args as { columns?: Record<string, string> }).columns ?? args) as Record<string, string>;
      const renamed: Record<string, unknown[]> = {};
      for (const column of this.columns) {
        renamed[columns[column] ?? column] = [...(this.data[column] ?? [])];
      }
      return new FakeFrame(renamed);
    }

    get(column: string): unknown[] {
      return this.data[column] ?? [];
    }

    set(column: string, values: unknown): void {
      this.data[column] = Array.isArray(values) ? values : [values];
    }
  }

  const frame = new FakeFrame({
    fname: ["jane"],
    mobile: ["(202) 555-0143"],
    Whatever: ["kept"],
  });

  const mapped = new ContactMapper().map_dataframe(frame) as FakeFrame;

  assert.deepEqual(mapped.columns, ["first_name", "phone", "Whatever"]);
  assert.deepEqual(mapped.data, {
    first_name: ["Jane"],
    phone: ["+12025550143"],
    Whatever: ["kept"],
  });
  assert.deepEqual(frame.columns, ["fname", "mobile", "Whatever"]);
});

test("map_dataframe preserves unmatched suffix columns and rejects duplicate labels", () => {
  class FakeFrame {
    [key: string]: unknown;

    constructor(
      public columns: string[],
      public data: Record<string, unknown[]>,
    ) {}

    rename(args: { columns: Record<string, string> } | Record<string, string>): FakeFrame {
      const names = ((args as { columns?: Record<string, string> }).columns ?? args) as Record<string, string>;
      return new FakeFrame(
        this.columns.map((column) => names[column] ?? column),
        Object.fromEntries(
          this.columns.map((column) => [names[column] ?? column, [...(this.data[column] ?? [])]]),
        ),
      );
    }

    get(column: string): unknown[] {
      return this.data[column] ?? [];
    }

    set(column: string, values: unknown): void {
      this.data[column] = Array.isArray(values) ? values : [values];
    }
  }

  const mapper = new ContactMapper({
    patterns: { fields: { custom: ["source_a", "source_b"] } },
  });
  const mapped = mapper.map_dataframe(
    new FakeFrame(
      ["source_a", "source_b", "custom__2"],
      { source_a: ["one"], source_b: ["two"], custom__2: ["keep"] },
    ),
    { normalize: false },
  ) as FakeFrame;

  assert.deepEqual(mapped.columns, ["custom", "custom__3", "custom__2"]);
  assert.deepEqual(mapped.data, {
    custom: ["one"],
    custom__3: ["two"],
    custom__2: ["keep"],
  });
  assert.throws(
    () => new ContactMapper().map_dataframe(
      new FakeFrame(["fname", "fname"], { fname: ["Ada"] }),
    ),
    { name: "ValueError", message: /unique input column labels/ },
  );
});

test("map_dataframe honors normalize, strict, and threshold options", () => {
  const mapper = new ContactMapper();
  class TinyFrame {
    [key: string]: unknown;

    columns: string[];
    data: Record<string, unknown[]>;

    constructor(data: Record<string, unknown[]>) {
      this.columns = Object.keys(data);
      this.data = Object.fromEntries(Object.entries(data).map(([key, values]) => [key, [...values]]));
    }

    rename(args: { columns: Record<string, string> } | Record<string, string>): TinyFrame {
      const columns = ((args as { columns?: Record<string, string> }).columns ?? args) as Record<string, string>;
      return new TinyFrame(Object.fromEntries(this.columns.map((column) => [columns[column] ?? column, [...(this.data[column] ?? [])]])));
    }

    get(column: string): unknown[] {
      return this.data[column] ?? [];
    }

    set(column: string, values: unknown): void {
      this.data[column] = Array.isArray(values) ? values : [values];
    }
  }

  assert.deepEqual((mapper.map_dataframe(new TinyFrame({ fname: ["jane"] }), { normalize: false }) as TinyFrame).data, {
    first_name: ["jane"],
  });
  assert.deepEqual((mapper.map_dataframe(new TinyFrame({ Compny: ["Acme"] }), { confidence_threshold: 0.99 }) as TinyFrame).data, {
    Compny: ["Acme"],
  });
  assert.throws(
    () => mapper.map_dataframe(new TinyFrame({ phone: ["not a phone"] }), { strict: true }),
    /default_region\?/,
  );
});

test("get_all_phones mirrors Python MappingResult helper", () => {
  const result = new ContactMapper().map_payload({
    phone: "(202) 555-0143",
    whatsapp: "+1 202 555 0143",
  });

  assert.deepEqual(result.get_all_phones(), ["+12025550143"]);
  assert.deepEqual(new ContactMapper({ normalize: false }).map_payload({ phone: [null, true, 123] }).get_all_phones(), ["None", "True", "123"]);
});

