// The mapping result, profile and match-collection types.
// Extracted verbatim from index.ts, which re-exports every public name here.

import { FieldMatch, PHONE_FIELDS, isMatched } from "./_models.js";
import { EMAIL_SHAPE_RE } from "./_normalizers.js";
import { lockPythonFrozenFields, pyRepr, pyString, pyStrip, pythonLiteral } from "./_pycompat.js";

// Phone fields whose number belongs to one person. work_phone (often a
// switchboard) and fax are shared, so they never become identity keys.
const IDENTITY_PHONE_FIELDS = ["phone", "home_phone", "whatsapp"] as const;

export class MappingProfile {
  readonly rows_seen: number;
  readonly fields_seen: number;
  readonly matched_count: number;
  readonly unmatched_count: number;
  readonly canonical_counts: Record<string, number>;
  readonly unmapped_counts: Record<string, number>;
  readonly strategy_counts: Record<string, number>;
  readonly warning_counts: Record<string, number>;
  /**
   * Phones found in free text (extract_embedded_phones). Counted here, not in
   * fields_seen / matched_count, because they are not columns.
   */
  readonly embedded_phone_count: number;

  constructor(
    rows_seen: number,
    fields_seen: number,
    matched_count: number,
    unmatched_count: number,
    canonical_counts: Record<string, number>,
    unmapped_counts: Record<string, number>,
    strategy_counts: Record<string, number>,
    warning_counts: Record<string, number>,
    embedded_phone_count = 0,
  ) {
    this.rows_seen = rows_seen;
    this.fields_seen = fields_seen;
    this.matched_count = matched_count;
    this.unmatched_count = unmatched_count;
    this.canonical_counts = canonical_counts;
    this.unmapped_counts = unmapped_counts;
    this.strategy_counts = strategy_counts;
    this.warning_counts = warning_counts;
    this.embedded_phone_count = embedded_phone_count;
    lockPythonFrozenFields(this, [
      "rows_seen",
      "fields_seen",
      "matched_count",
      "unmatched_count",
      "canonical_counts",
      "unmapped_counts",
      "strategy_counts",
      "warning_counts",
      "embedded_phone_count",
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
      embedded_phone_count: this.embedded_phone_count,
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

  /**
   * Stable, prefixed identifiers for deduplication. Only values that identify
   * one person become keys: an `email:` key only from a value shaped like an
   * email address (the check behind the email warning), and a `phone:` key
   * only from a phone that normalized to E.164 (starts with `+`; an `;ext=`
   * suffix is dropped from the key). work_phone and fax are left out, because
   * a switchboard or office fax is shared. Placeholders such as `n/a` or `-`
   * never become keys.
   */
  get_identity_keys(): string[] {
    const keys: string[] = [];
    const add = (key: string): void => {
      if (key && !keys.includes(key)) {
        keys.push(key);
      }
    };

    for (const email of this.get_all_emails()) {
      const text = pyStrip(email).toLowerCase();
      if (text && EMAIL_SHAPE_RE.test(text)) {
        add(`email:${text}`);
      }
    }
    for (const field of IDENTITY_PHONE_FIELDS) {
      const raw = this.normalized[field];
      for (const phone of Array.isArray(raw) ? raw : [raw]) {
        if (typeof phone !== "string") {
          continue;
        }
        const text = pyStrip(phone).split(";ext=", 1)[0] ?? "";
        if (text.startsWith("+") && text.length > 1) {
          add(`phone:${text}`);
        }
      }
    }

    const rawIds = this.normalized.source_id;
    const sourceIds = Array.isArray(rawIds) ? rawIds : [rawIds];
    const rawService = this.normalized.source_service;
    const services = Array.isArray(rawService) ? rawService : [rawService];
    const normalizedServices = services.map((value) =>
      value == null ? "" : pyStrip(pyString(value)).toLowerCase()
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
      const text = pyStrip(pyString(sourceId));
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

/**
 * A saved plan's header -> FieldMatch table, the JS twin of Python's
 * `MappingSchema.matches` dict. Headers live in a Map, never as properties of
 * this object, so a header named `get`, `set`, `entries` or `items` is stored
 * like any other instead of being shadowed by (or shadowing) a method.
 * `get` returns null for a missing header, as Python's dict.get returns None.
 */
class MappingMatches implements Iterable<[string, FieldMatch]> {
  readonly #map: Map<string, FieldMatch>;

  constructor(entries: Iterable<[string, FieldMatch]> = []) {
    this.#map = new Map(entries);
  }

  get size(): number {
    return this.#map.size;
  }

  get(header: string): FieldMatch | null {
    return this.#map.get(header) ?? null;
  }

  set(header: string, match: FieldMatch): this {
    this.#map.set(header, match);
    return this;
  }

  has(header: string): boolean {
    return this.#map.has(header);
  }

  keys(): IterableIterator<string> {
    return this.#map.keys();
  }

  values(): IterableIterator<FieldMatch> {
    return this.#map.values();
  }

  entries(): IterableIterator<[string, FieldMatch]> {
    return this.#map.entries();
  }

  items(): IterableIterator<[string, FieldMatch]> {
    return this.#map.entries();
  }

  [Symbol.iterator](): IterableIterator<[string, FieldMatch]> {
    return this.#map.entries();
  }

  /** A plain object with the headers as own keys (safe for "__proto__"). */
  toJSON(): Record<string, FieldMatch> {
    const out: Record<string, FieldMatch> = {};
    for (const [header, match] of this.#map) {
      Object.defineProperty(out, header, { value: match, enumerable: true, writable: true, configurable: true });
    }
    return out;
  }
}

function makeMappingMatches(
  source: Map<string, FieldMatch> | Record<string, FieldMatch> | Iterable<[string, FieldMatch]> = {},
): MappingMatches {
  if (source instanceof Map || typeof (source as Iterable<[string, FieldMatch]>)[Symbol.iterator] === "function") {
    return new MappingMatches(source as Iterable<[string, FieldMatch]>);
  }
  return new MappingMatches(Object.entries(source as Record<string, FieldMatch>));
}


// File-private in index.ts; exported here only because the split put
// their callers in another module. Not part of the package's public API -
// ./public.ts and ./core.ts still decide that.
export { MappingMatches, makeMappingMatches };
