// Reading and writing the dataframe-like objects map_dataframe accepts.
// Extracted verbatim from index.ts, which re-exports every public name here.

import type { DataFrameLike } from "./_models.js";

function flatten(payload: Record<string, unknown>, depth: number, prefix = "", current = 1): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(payload)) {
    const fullKey = prefix ? `${prefix}${key}` : key;
    if (value && typeof value === "object" && !Array.isArray(value) && current < depth) {
      Object.assign(result, flatten(value as Record<string, unknown>, depth, `${fullKey}.`, current + 1));
    } else {
      result[fullKey] = value;
    }
  }
  return result;
}

function isDataFrameLike(value: unknown): value is DataFrameLike {
  return !!value && typeof value === "object" && "columns" in value && typeof (value as DataFrameLike).rename === "function";
}

function dataframeColumns(value: DataFrameLike): string[] {
  const columns = value.columns;
  if (columns && typeof (columns as Iterable<unknown>)[Symbol.iterator] === "function") {
    return [...columns as Iterable<unknown>].map(String);
  }
  if (columns && typeof (columns as ArrayLike<unknown>).length === "number") {
    return Array.from(columns as ArrayLike<unknown>, String);
  }
  throw new TypeError("map_dataframe expects DataFrame-like columns to be iterable or array-like");
}

function dataframeColumnValues(frame: DataFrameLike, column: string): unknown {
  if (typeof frame.get === "function") {
    return frame.get(column);
  }
  return frame[column];
}

function mappedColumnValues(values: unknown, mapper: (value: unknown) => unknown): unknown {
  if (typeof values === "string") {
    return undefined;
  }
  if (Array.isArray(values)) {
    return values.map(mapper);
  }
  if (values && typeof values === "object" && typeof (values as { map?: unknown }).map === "function") {
    return (values as { map: (callback: (value: unknown) => unknown) => unknown }).map(mapper);
  }
  return undefined;
}

function setDataframeColumn(frame: DataFrameLike, column: string, values: unknown): void {
  if (typeof frame.set === "function") {
    frame.set(column, values);
    return;
  }
  frame[column] = values;
}

function iterableColumnValues(values: unknown): Iterable<unknown> {
  if (typeof values === "string") {
    return [];
  }
  if (values && typeof (values as Iterable<unknown>)[Symbol.iterator] === "function") {
    return values as Iterable<unknown>;
  }
  return [];
}


// File-private in index.ts; exported here only because the split put
// their callers in another module. Not part of the package's public API -
// ./public.ts and ./core.ts still decide that.
export { dataframeColumnValues, dataframeColumns, flatten, isDataFrameLike, iterableColumnValues, mappedColumnValues, setDataframeColumn };
