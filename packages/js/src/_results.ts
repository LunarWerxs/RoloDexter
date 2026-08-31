// The mapping result, profile and match-collection types.
// Extracted verbatim from index.ts, which re-exports every public name here.

import { FieldMatch, PHONE_FIELDS, isMatched } from "./_models.js";
import { lockPythonFrozenFields, pyRepr, pyString, pythonLiteral } from "./_pycompat.js";

export class MappingProfile {
  readonly rows_seen: number;
  readonly fields_seen: number;
  readonly matched_count: number;
  readonly unmatched_count: number;
  readonly canonical_counts: Record<string, number>;
  readonly unmapped_counts: Record<string, number>;
  readonly strategy_counts: Record<string, number>;
  readonly warning_counts: Record<string, number>;

  constructor(
    rows_seen: number,
    fields_seen: number,
    matched_count: number,
    unmatched_count: number,
    canonical_counts: Record<string, number>,
    unmapped_counts: Record<string, number>,
    strategy_counts: Record<string, number>,
    warning_counts: Record<string, number>,
  ) {
    this.rows_seen = rows_seen;
    this.fields_seen = fields_seen;
    this.matched_count = matched_count;
    this.unmatched_count = unmatched_count;
    this.canonical_counts = canonical_counts;
    this.unmapped_counts = unmapped_counts;
    this.strategy_counts = strategy_counts;
    this.warning_counts = warning_counts;
    lockPythonFrozenFields(this, [
      "rows_seen",
      "fields_seen",
      "matched_count",
      "unmatched_count",
      "canonical_counts",
      "unmapped_counts",
      "strategy_counts",
      "warning_counts",
    ]);
  }

  get match_rate(): number {
    return this.fields_seen === 0 ? 0 : this.matched_count / this.fields_seen;
  }

  get warning_count(): number {
    return Object.values(this.warning_counts).reduce((total, count) => total + count, 0);
  }

  to_dict(): Record<string, unknown> {
    return {
      rows_seen: this.rows_seen,
      fields_seen: this.fields_seen,
      matched: this.matched_count,
      unmatched: this.unmatched_count,
      match_rate: Number(this.match_rate.toFixed(4)),
      warning_count: this.warning_count,
      canonical_counts: { ...this.canonical_counts },
      unmapped_counts: { ...this.unmapped_counts },
      strategy_counts: { ...this.strategy_counts },
      warning_counts: { ...this.warning_counts },
    };
  }

  explain(): string {
    const lines = [
      `Profile: ${this.rows_seen} row(s), ${this.fields_seen} field(s), ${this.matched_count} matched, ${this.unmatched_count} unmatched (match rate ${Math.round(this.match_rate * 100)}%), ${this.warning_count} warning(s)`,
    ];
    const section = (title: string, values: Record<string, number>): void => {
      const entries = Object.entries(values).sort(
        ([leftKey, leftCount], [rightKey, rightCount]) =>
          (rightCount - leftCount) || leftKey.localeCompare(rightKey),
      );
      if (entries.length === 0) {
        return;
      }
      lines.push(`${title}:`);
      for (const [key, count] of entries) {
        lines.push(`  ${key}: ${count}`);
      }
    };
    section("Canonical fields", this.canonical_counts);
    section("Unmapped headers", this.unmapped_counts);
    section("Warnings", this.warning_counts);
    return lines.join("\n");
  }
}

export class MappingResult {
  readonly normalized: Record<string, unknown>;
  readonly unmapped: Record<string, unknown>;
  readonly field_matches: readonly FieldMatch[];
  readonly warnings: readonly string[];
  #index?: Map<string, FieldMatch>;

  constructor(
    normalized: Record<string, unknown>,
    unmapped: Record<string, unknown>,
    field_matches: Iterable<FieldMatch>,
    warnings?: Iterable<string>,
  ) {
    if (arguments.length === 0) {
      throw new TypeError("MappingResult.__init__() missing 3 required positional arguments: 'normalized', 'unmapped', and 'field_matches'");
    }
    if (arguments.length === 1) {
      throw new TypeError("MappingResult.__init__() missing 2 required positional arguments: 'unmapped' and 'field_matches'");
    }
    if (arguments.length === 2) {
      throw new TypeError("MappingResult.__init__() missing 1 required positional argument: 'field_matches'");
    }
    if (arguments.length > 4) {
      throw new TypeError(`MappingResult.__init__() takes from 4 to 5 positional arguments but ${arguments.length + 1} were given`);
    }
    this.normalized = normalized;
    this.unmapped = unmapped;
    this.field_matches = Object.freeze([...field_matches]);
    this.warnings = Object.freeze([...(warnings ?? [])]);
    lockPythonFrozenFields(this, ["normalized", "unmapped", "field_matches", "warnings"]);
  }

  get matched_count(): number {
    return this.field_matches.filter(isMatched).length;
  }

  get unmatched_count(): number {
    return this.field_matches.length - this.matched_count;
  }

  get match_rate(): number {
    return this.field_matches.length === 0 ? 0 : this.matched_count / this.field_matches.length;
  }

  get_match(originalHeader: string): FieldMatch | null {
    if (!this.#index) {
      this.#index = new Map(this.field_matches.map((match) => [match.original, match]));
    }
    return this.#index.get(originalHeader) ?? null;
  }

  explain(): string {
    const lines = [
      `Mapping: ${this.matched_count} matched, ${this.unmatched_count} unmatched (match rate ${Math.round(this.match_rate * 100)}%)`,
    ];
    for (const match of this.field_matches) {
      const arrow = isMatched(match) ? "->" : " x";
      lines.push(
        `  ${pyRepr(match.original)} ${arrow} ${match.canonical} [${match.strategy}, conf=${match.confidence.toFixed(2)}]`,
      );
    }
    if (this.warnings.length > 0) {
      lines.push("Warnings:");
      for (const warning of this.warnings) {
        lines.push(`  ! ${warning}`);
      }
    }
    return lines.join("\n");
  }

  get_all_phones(): string[] {
    const phones: string[] = [];
    for (const key of PHONE_FIELDS) {
      const value = this.normalized[key];
      if (Array.isArray(value)) {
        phones.push(...value.map(pyString));
      } else if (value != null) {
        phones.push(pyString(value));
      }
    }
    return [...new Set(phones)];
  }

  get_all_emails(): string[] {
    const value = this.normalized.email;
    const emails = Array.isArray(value) ? value : [value];
    const result: string[] = [];
    for (const email of emails) {
      if (email == null) {
        continue;
      }
      const text = pyString(email);
      if (!result.includes(text)) {
        result.push(text);
      }
    }
    return result;
  }

  get_identity_keys(): string[] {
    const keys: string[] = [];
    const add = (key: string): void => {
      if (key && !keys.includes(key)) {
        keys.push(key);
      }
    };

    for (const email of this.get_all_emails()) {
      const text = email.trim().toLowerCase();
      if (text) {
        add(`email:${text}`);
      }
    }
    for (const phone of this.get_all_phones()) {
      const text = phone.trim();
      if (text) {
        add(`phone:${text}`);
      }
    }

    const rawIds = this.normalized.source_id;
    const sourceIds = Array.isArray(rawIds) ? rawIds : [rawIds];
    const rawService = this.normalized.source_service;
    const services = Array.isArray(rawService) ? rawService : [rawService];
    const normalizedServices = services.map((value) =>
      value == null ? "" : pyString(value).trim().toLowerCase()
    );
    // Scope IDs by vendor ONLY when the payload names exactly one vendor.
    // source_id and source_service are two independent lists built by the
    // collision merge from raw key order; nothing links position i of one to
    // position i of the other, so zipping them emitted a confident but
    // fabricated key. Ambiguous means unqualified, which is less specific
    // rather than wrong.
    const service = normalizedServices.length === 1 ? normalizedServices[0] : "";
    const prefix = service ? `source:${service}` : "source_id";
    for (const sourceId of sourceIds) {
      if (sourceId == null) {
        continue;
      }
      const text = pyString(sourceId).trim();
      if (text) {
        add(`${prefix}:${text}`);
      }
    }
    return keys;
  }

  to_dict(): Record<string, unknown> {
    const matched = this.matched_count;
    const total = this.field_matches.length;
    return {
      normalized: { ...this.normalized },
      unmapped: { ...this.unmapped },
      match_rate: Number((total === 0 ? 0 : matched / total).toFixed(4)),
      matched,
      unmatched: total - matched,
      warnings: [...this.warnings],
      details: this.field_matches.map((match) => ({
        original: match.original,
        canonical: match.canonical,
        confidence: match.confidence,
        strategy: match.strategy,
        service: match.service,
      })),
    };
  }

  toString(): string {
    const matches = `[${this.field_matches.map((match) => match.toString()).join(", ")}]`;
    return `MappingResult(normalized=${pythonLiteral(this.normalized)}, unmapped=${pythonLiteral(this.unmapped)}, field_matches=${matches}, warnings=${pythonLiteral(this.warnings)})`;
  }
}

type MappingMatches = Record<string, FieldMatch> & {
  get(header: string): FieldMatch | null;
  set(header: string, match: FieldMatch): MappingMatches;
  entries(): IterableIterator<[string, FieldMatch]>;
  items(): IterableIterator<[string, FieldMatch]>;
  [Symbol.iterator](): IterableIterator<[string, FieldMatch]>;
};

function makeMappingMatches(
  source: Map<string, FieldMatch> | Record<string, FieldMatch> | Iterable<[string, FieldMatch]> = {},
): MappingMatches {
  const out = {} as MappingMatches;
  const entries: Iterable<[string, FieldMatch]> = source instanceof Map
    ? source
    : typeof (source as Iterable<[string, FieldMatch]>)[Symbol.iterator] === "function"
      ? source as Iterable<[string, FieldMatch]>
      : Object.entries(source as Record<string, FieldMatch>);

  for (const [header, match] of entries) {
    out[header] = match;
  }

  Object.defineProperties(out, {
    get: {
      value(header: string): FieldMatch | null {
        return out[header] ?? null;
      },
    },
    set: {
      value(header: string, match: FieldMatch): MappingMatches {
        out[header] = match;
        return out;
      },
    },
    entries: {
      value: function* entriesIterator(): IterableIterator<[string, FieldMatch]> {
        yield* Object.entries(out) as Array<[string, FieldMatch]>;
      },
    },
    items: {
      value: function* itemsIterator(): IterableIterator<[string, FieldMatch]> {
        yield* Object.entries(out) as Array<[string, FieldMatch]>;
      },
    },
    [Symbol.iterator]: {
      value: function* matchesIterator(): IterableIterator<[string, FieldMatch]> {
        yield* Object.entries(out) as Array<[string, FieldMatch]>;
      },
    },
  });

  return out;
}


// File-private in index.ts; exported here only because the split put
// their callers in another module. Not part of the package's public API -
// ./public.ts and ./core.ts still decide that.
export { makeMappingMatches };
export type { MappingMatches };
