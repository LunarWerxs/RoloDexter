// The shared data tables, read once from tables.json. The file is synced from
// src/rolodexter/tables.json by scripts/sync-patterns.mjs, copied into dist by
// scripts/copy-assets.mjs, and read the same way patterns.json is (_registry.ts).
// Python reads the same file in src/rolodexter/_tables.py.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { moduleUrl } from "./_runtime.js";

export interface SocialUrlDef {
  readonly canonical: string;
  readonly domains: readonly string[];
  readonly path: string;
}

export interface Tables {
  readonly version: string;
  readonly confidence: {
    readonly exact: number;
    readonly normalized: number;
    readonly fuzzy_threshold: number;
    readonly fuzzy_high: number;
    readonly fuzzy_low: number;
    readonly fuzzy_length_ratio: number;
    readonly heuristic: number;
  };
  readonly field_sets: {
    readonly phone: readonly string[];
    readonly name: readonly string[];
    readonly address: readonly string[];
    readonly boolean: readonly string[];
    readonly list: readonly string[];
    readonly date: readonly string[];
    readonly timestamp: readonly string[];
    readonly social: readonly string[];
  };
  readonly prefixes: {
    readonly company: readonly string[];
    readonly vendor: readonly string[];
    readonly address_context: readonly string[];
  };
  readonly header_hints: {
    readonly phone: readonly string[];
    readonly postal: readonly string[];
    readonly postal_phrases: readonly string[];
    readonly birthday: readonly string[];
    readonly birthday_phrases: readonly string[];
    readonly reference_suffixes: readonly string[];
  };
  readonly value_properties: readonly string[];
  readonly qualifier_tails: readonly (readonly string[])[];
  readonly social_urls: readonly SocialUrlDef[];
  readonly geo: {
    readonly alpha2: readonly string[];
    readonly alpha3: Readonly<Record<string, string>>;
    readonly country_names: Readonly<Record<string, string>>;
    readonly state_names: Readonly<Record<string, string>>;
  };
  readonly text: {
    readonly region_codes: readonly string[];
    readonly always_upper: readonly string[];
  };
  readonly mac_exceptions: readonly string[];
  readonly languages: Readonly<Record<string, readonly [string, string]>>;
  readonly i18n_skip: {
    readonly timestamp: readonly string[];
    readonly crm: readonly string[];
    readonly platform: readonly string[];
  };
}

export const TABLES: Tables = JSON.parse(
  readFileSync(fileURLToPath(new URL("./tables.json", moduleUrl)), "utf8"),
) as Tables;
