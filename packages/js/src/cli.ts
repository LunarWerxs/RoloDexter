#!/usr/bin/env node
import { randomUUID } from "node:crypto";
import { once } from "node:events";
import { createReadStream, createWriteStream, existsSync, readFileSync, realpathSync, renameSync, unlinkSync, writeFileSync, writeSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { createInterface } from "node:readline";
import type { WriteStream } from "node:fs";
import { fileURLToPath } from "node:url";
import { inspect } from "node:util";

import { stringify as stringifyCsv } from "csv-stringify/sync";

import { setOwnProperty } from "./_pycompat.js";
import {
  CanonicalField,
  ContactMapper,
  MappingResult,
  MappingSchema,
  NormalizationError,
  RolodexterError,
  __version__,
} from "./index.js";

const DEFAULT_MAX_MATERIALIZED_ROWS = 100_000;
const DEFAULT_MAX_JSON_INPUT_BYTES = 50 * 1024 * 1024;
// Matches below this are reported for review. Exact (1.0) and normalized
// (0.95) matches are header-derived and reliable; fuzzy (0.85/0.70) and
// value-shape heuristics (0.60) are guesses worth a human glance.
const REVIEW_CONFIDENCE = 0.95;
const MAX_SUMMARY_COLUMNS = 20;
// Exit code when rows failed but the run was allowed to continue. Distinct
// from 1 (the run itself failed) so a caller can tell "nothing was produced"
// from "output written, but some rows did not make it".
const EXIT_PARTIAL = 2;
const CLI_EOL = process.platform === "win32" ? "\r\n" : "\n";

let brokenPipeExiting = false;

function brokenPipeText(): string {
  if (process.platform === "win32") {
    return "error: [Errno 22] Invalid argument\nException ignored while flushing sys.stdout:\nOSError: [Errno 22] Invalid argument\n";
  }
  return "error: [Errno 32] Broken pipe\nException ignored while flushing sys.stdout:\nBrokenPipeError: [Errno 32] Broken pipe\n";
}

function exitBrokenPipe(): never {
  if (!brokenPipeExiting) {
    brokenPipeExiting = true;
    try {
      writeSync(2, cliText(brokenPipeText()));
    } catch {
      // Match Python's best-effort broken-pipe reporting without masking exit.
    }
  }
  process.exit(120);
}

process.stdout.on("error", (error: NodeJS.ErrnoException) => {
  if (error.code === "EPIPE" || error.code === "EINVAL") {
    exitBrokenPipe();
  }
  throw error;
});

type Format = "auto" | "csv" | "json" | "jsonl";
type OnError = "fail" | "skip" | "quarantine";

interface InputRow {
  kind: "row";
  rowNumber: number;
  data: Record<string, unknown>;
}

interface RowFailure {
  kind: "failure";
  rowNumber: number;
  error: string;
  raw: unknown;
}

interface MapArgs {
  input: string;
  output?: string;
  format: Format;
  inFormat: Format;
  region: string;
  languages?: string;
  strict: boolean;
  minConfidence: number;
  normalize: boolean;
  embeddedPhones: boolean;
  onError: OnError;
  quarantineOutput?: string;
  maxMaterializedRows: number | null;
  maxJsonInputBytes: number | null;
  keepUnmapped: boolean;
  dedupe: boolean;
  override?: string[];
  schemaOut?: string;
  schemaIn?: string;
}

interface ExplainArgs {
  header: string;
  value?: string;
  region: string;
  languages?: string;
  override?: string[];
}

interface ProfileArgs {
  input: string;
  inFormat: Format;
  region: string;
  languages?: string;
  override?: string[];
  maxRows: number;
  minConfidence: number;
  embeddedPhones: boolean;
  noNormalize: boolean;
  json: boolean;
  maxJsonInputBytes: number | null;
}

class CliUsageError extends Error {
  readonly exitCode = 2;
}

class CliHelpError extends Error {
  constructor(readonly text: string) {
    super(text);
  }
}

function cliText(text: string): string {
  return text.replace(/(?<!\r)\n/g, CLI_EOL);
}

function writeStdout(text: string): void {
  process.stdout.write(cliText(text));
}

function writeStderr(text: string): void {
  process.stderr.write(cliText(text));
}

function logStdout(text = ""): void {
  writeStdout(`${text}\n`);
}

function logStderr(text = ""): void {
  writeStderr(`${text}\n`);
}

function usage(): string {
  return [
    "usage: rolodexter [-h] [--version] {map,explain,profile,fields} ...",
    "",
    "Map messy contact data to a clean canonical schema.",
    "",
    "positional arguments:",
    "  {map,explain,profile,fields}",
    "    map                 Map a CSV/JSON/JSONL file to canonical fields",
    "    explain             Show how a single header resolves",
    "    profile             Report how well a file maps, without writing any",
    "                        output",
    "    fields              List all canonical fields",
    "",
    "options:",
    "  -h, --help            show this help message and exit",
    "  --version             show program's version number and exit",
  ].join("\n");
}

function rootUsageLine(): string {
  return "usage: rolodexter [-h] [--version] {map,explain,profile,fields} ...";
}

function mapUsage(): string {
  return [
    mapUsageLine(),
    "",
    "positional arguments:",
    "  input                 Input file (.csv, .json, or .jsonl)",
    "",
    "options:",
    "  -h, --help            show this help message and exit",
  "  -o, --output OUTPUT   Output file (default: stdout)",
  "  --format {auto,csv,json,jsonl}",
    "                        Output format (default: infer from -o extension, else",
    "                        json)",
  "  --in-format {auto,csv,json,jsonl}",
    "                        Input format (default: infer from the input file",
    "                        extension)",
    "  --region REGION       Default phone region (ISO-3166 alpha-2)",
    "  --languages LANGUAGES",
    "                        Comma-separated i18n language codes (cached)",
    "  --strict              Fail on any mapping warning",
    "  --min-confidence MIN_CONFIDENCE",
    "                        Drop matches below this confidence (0.0-1.0)",
    "  --no-normalize        Skip value normalization",
    "  --embedded-phones     Also extract phone numbers embedded in free-text",
    "                        values",
  "  --on-error {fail,skip,quarantine}",
    "                        How to handle row-level failures such as malformed",
    "                        JSONL rows or strict normalization errors (default:",
    "                        fail)",
  "  --quarantine-output QUARANTINE_OUTPUT",
    "                        JSONL file for failed raw rows when --on-error",
    "                        quarantine is used (default: <output-or-",
    "                        input>.quarantine.jsonl)",
  "  --max-materialized-rows MAX_MATERIALIZED_ROWS",
    "                        Maximum rows to materialize for JSON/CSV output; use 0",
    "                        to disable (default: 100000)",
  "  --max-json-input-bytes MAX_JSON_INPUT_BYTES",
    "                        Maximum bytes to read with non-streaming JSON input;",
    "                        use 0 to disable (default: 52428800)",
    "  --keep-unmapped       Carry columns that could not be mapped through to the",
    "                        output under their original header (default: drop",
    "                        them)",
    "  --dedupe              Drop later rows that share an identity key (email,",
    "                        phone or source id) with an earlier row",
    "  --override HEADER=FIELD",
    "                        Force a column to a canonical field, e.g. --override",
    "                        MMERGE3=full_address (repeatable)",
    "  --schema-out PATH     Write the resolved header plan to a JSON file for",
    "                        reuse",
    "  --schema-in PATH      Replay a plan saved by --schema-out so columns route",
    "                        identically to that run",
  ].join("\n");
}

function mapUsageLine(): string {
  return [
    "usage: rolodexter map [-h] [-o OUTPUT] [--format {auto,csv,json,jsonl}]",
    "                      [--in-format {auto,csv,json,jsonl}] [--region REGION]",
    "                      [--languages LANGUAGES] [--strict]",
    "                      [--min-confidence MIN_CONFIDENCE] [--no-normalize]",
    "                      [--embedded-phones] [--on-error {fail,skip,quarantine}]",
    "                      [--quarantine-output QUARANTINE_OUTPUT]",
    "                      [--max-materialized-rows MAX_MATERIALIZED_ROWS]",
    "                      [--max-json-input-bytes MAX_JSON_INPUT_BYTES]",
    "                      [--keep-unmapped] [--dedupe] [--override HEADER=FIELD]",
    "                      [--schema-out PATH] [--schema-in PATH]",
    "                      input",
  ].join("\n");
}

function explainUsage(): string {
  return [
    explainUsageLine(),
    "",
    "positional arguments:",
    "  header                The column header to resolve",
    "",
    "options:",
    "  -h, --help            show this help message and exit",
    "  --value VALUE         An example cell value (enables shape heuristics)",
    "  --region REGION       Default phone region",
    "  --languages LANGUAGES",
    "                        Comma-separated i18n language codes (cached)",
    "  --override HEADER=FIELD",
    "                        Force a column to a canonical field (repeatable)",
  ].join("\n");
}

function explainUsageLine(): string {
  return [
    "usage: rolodexter explain [-h] [--value VALUE] [--region REGION]",
    "                          [--languages LANGUAGES] [--override HEADER=FIELD]",
    "                          header",
  ].join("\n");
}

function profileUsage(): string {
  return [
    profileUsageLine(),
    "",
    "positional arguments:",
    "  input                 Input file (.csv, .json, or .jsonl)",
    "",
    "options:",
    "  -h, --help            show this help message and exit",
    "  --in-format {auto,csv,json,jsonl}",
    "                        Input format (default: infer from the input file",
    "                        extension)",
    "  --region REGION       Default phone region (ISO-3166 alpha-2)",
    "  --languages LANGUAGES",
    "                        Comma-separated i18n language codes (cached)",
    "  --override HEADER=FIELD",
    "                        Force a column to a canonical field (repeatable)",
    "  --max-rows MAX_ROWS   Profile at most this many rows; 0 means all (default:",
    "                        0)",
    "  --min-confidence MIN_CONFIDENCE",
    "                        Treat matches below this confidence as unmapped",
    "                        (0.0-1.0)",
    "  --embedded-phones     Also count phone numbers embedded in free-text values",
    "  --no-normalize        Skip value normalization: much faster on a large",
    "                        export, but drops the phone/email/date warning counts",
    "  --json                Emit the profile as JSON",
    "  --max-json-input-bytes MAX_JSON_INPUT_BYTES",
    "                        Maximum bytes to read with non-streaming JSON input; 0",
    "                        disables",
  ].join("\n");
}

function profileUsageLine(): string {
  return [
    "usage: rolodexter profile [-h] [--in-format {auto,csv,json,jsonl}]",
    "                          [--region REGION] [--languages LANGUAGES]",
    "                          [--override HEADER=FIELD] [--max-rows MAX_ROWS]",
    "                          [--min-confidence MIN_CONFIDENCE]",
    "                          [--embedded-phones] [--no-normalize] [--json]",
    "                          [--max-json-input-bytes MAX_JSON_INPUT_BYTES]",
    "                          input",
  ].join("\n");
}

function fieldsUsage(): string {
  return [
    "usage: rolodexter fields [-h]",
    "",
    "options:",
    "  -h, --help  show this help message and exit",
  ].join("\n");
}

function usageError(usageText: string, prog: string, message: string): CliUsageError {
  return new CliUsageError(`${usageText}\n${prog}: error: ${message}`);
}

function parseLanguages(raw: string | undefined): string[] | undefined {
  if (!raw) {
    return undefined;
  }
  const languages = raw.split(",").map((item) => item.trim()).filter(Boolean);
  return languages.length > 0 ? languages : undefined;
}

function detectFormat(path: string | undefined, explicit: Format): Exclude<Format, "auto"> {
  if (explicit !== "auto") {
    return explicit;
  }
  const low = (path ?? "").toLowerCase();
  if (low.endsWith(".jsonl") || low.endsWith(".ndjson")) {
    return "jsonl";
  }
  if (low.endsWith(".json")) {
    return "json";
  }
  return "csv";
}

function optionalLimit(value: number): number | null {
  return value === 0 ? null : value;
}

function asNonNegativeInt(raw: string, option: string, usageText: string, prog: string): number {
  if (!/^[+-]?\d+$/.test(raw)) {
    throw usageError(usageText, prog, `argument ${option}: invalid _non_negative_int value: ${pyRepr(raw)}`);
  }
  if (raw.startsWith("-")) {
    throw usageError(usageText, prog, `argument ${option}: must be non-negative`);
  }
  return Number(raw);
}

function asFloat(raw: string, option: string, usageText: string, prog: string): number {
  if (/^[+-]?(?:nan|inf(?:inity)?)$/i.test(raw)) {
    return raw.startsWith("-") ? Number.NEGATIVE_INFINITY : raw.toLowerCase().includes("nan") ? Number.NaN : Number.POSITIVE_INFINITY;
  }
  if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(raw)) {
    throw usageError(usageText, prog, `argument ${option}: invalid float value: ${pyRepr(raw)}`);
  }
  return Number(raw);
}

function pyRepr(value: string): string {
  const quote = value.includes("'") && !value.includes("\"") ? "\"" : "'";
  const escaped = value
    .replace(/\\/g, "\\\\")
    .replace(/\n/g, "\\n")
    .replace(/\r/g, "\\r")
    .replace(/\t/g, "\\t")
    .replace(new RegExp(quote, "g"), `\\${quote}`);
  return `${quote}${escaped}${quote}`;
}

function resolvedHelpOption(arg: string, usageText: string, prog: string): boolean {
  if (arg === "-h") {
    return true;
  }
  if (!arg.startsWith("--") || arg === "--") {
    return false;
  }
  const equalsAt = arg.indexOf("=");
  const raw = equalsAt === -1 ? arg : arg.slice(0, equalsAt);
  if (!"--help".startsWith(raw) || raw === "--") {
    return false;
  }
  if (equalsAt !== -1) {
    throw usageError(usageText, prog, `argument --help: ignored explicit argument ${pyRepr(arg.slice(equalsAt + 1))}`);
  }
  return true;
}

function resolvedVersionOption(arg: string, usageText: string, prog: string): boolean {
  if (!arg.startsWith("--") || arg === "--") {
    return false;
  }
  const equalsAt = arg.indexOf("=");
  const raw = equalsAt === -1 ? arg : arg.slice(0, equalsAt);
  if (!"--version".startsWith(raw) || raw === "--") {
    return false;
  }
  if (equalsAt !== -1) {
    throw usageError(usageText, prog, `argument --version: ignored explicit argument ${pyRepr(arg.slice(equalsAt + 1))}`);
  }
  return true;
}

function parseOverrides(raw: string[] | undefined): Record<string, string> | undefined {
  if (!raw || raw.length === 0) {
    return undefined;
  }
  const overrides: Record<string, string> = {};
  const valid = new Set(Object.values(CanonicalField).map((field) => field.value));
  for (const entry of raw) {
    const equalsAt = entry.indexOf("=");
    const hasSeparator = equalsAt !== -1;
    const header = (hasSeparator ? entry.slice(0, equalsAt) : entry).trim();
    const canonical = (hasSeparator ? entry.slice(equalsAt + 1) : "").trim();
    if (!hasSeparator || !header || !canonical) {
      throw new Error(`--override expects HEADER=canonical_field, got ${pyRepr(entry)}`);
    }
    if (!valid.has(canonical)) {
      throw new Error(`--override ${pyRepr(entry)}: ${pyRepr(canonical)} is not a canonical field (run 'rolodexter fields' to list them)`);
    }
    setOwnProperty(overrides, header, canonical);
  }
  return overrides;
}

interface BuildMapperArgs {
  region: string;
  languages?: string;
  normalize?: boolean;
  strict?: boolean;
  minConfidence?: number;
  override?: string[];
}

function buildMapper(args: BuildMapperArgs): ContactMapper {
  return new ContactMapper({
    default_region: args.region,
    languages: parseLanguages(args.languages),
    normalize: args.normalize ?? true,
    strict: args.strict ?? false,
    confidence_threshold: args.minConfidence ?? 0,
    overrides: parseOverrides(args.override),
  });
}

function rejectExplicitFlagValue(option: string, value: string | undefined, usageText: string, prog: string): void {
  if (value !== undefined) {
    throw usageError(usageText, prog, `argument ${option}: ignored explicit argument ${pyRepr(value)}`);
  }
}

function fileNotFoundMessage(path: string): string {
  if (process.platform === "win32") {
    return `[WinError 2] The system cannot find the file specified: ${pyRepr(path)}`;
  }
  return `[Errno 2] No such file or directory: ${pyRepr(path)}`;
}

function optionToken(
  arg: string,
  known: string[],
  usageText: string,
  prog: string,
): { option: string; value?: string } | undefined {
  if (!arg.startsWith("--") || arg === "--") {
    return undefined;
  }
  const equalsAt = arg.indexOf("=");
  const raw = equalsAt === -1 ? arg : arg.slice(0, equalsAt);
  const matches = known.filter((option) => option.startsWith(raw));
  if (matches.length === 1) {
    return { option: matches[0] ?? raw, value: equalsAt === -1 ? undefined : arg.slice(equalsAt + 1) };
  }
  if (matches.length > 1) {
    throw usageError(usageText, prog, `ambiguous option: ${raw} could match ${matches.join(", ")}`);
  }
  if ((prog === "rolodexter map" || prog === "rolodexter explain") && raw.startsWith("--")) {
    throw usageError(rootUsageLine(), "rolodexter", `unrecognized arguments: ${arg}`);
  }
  throw usageError(usageText, prog, `unrecognized arguments: ${arg}`);
}

function takeResolvedValue(argv: string[], index: number, option: string, value: string | undefined, usageText: string, prog: string): [string, number] {
  if (value !== undefined) {
    return [value, index];
  }
  const next = argv[index + 1];
  if (next === undefined || (next.startsWith("-") && !/^-?(?:\d|\.\d)/.test(next))) {
    throw usageError(usageText, prog, `argument ${option}: expected one argument`);
  }
  return [next, index + 1];
}

function validateFormat(value: string, option: string, usageText: string, prog: string): Format {
  if (["auto", "csv", "json", "jsonl"].includes(value)) {
    return value as Format;
  }
  throw usageError(usageText, prog, `argument ${option}: invalid choice: ${pyRepr(value)} (choose from auto, csv, json, jsonl)`);
}

function validateOnError(value: string): OnError {
  if (["fail", "skip", "quarantine"].includes(value)) {
    return value as OnError;
  }
  throw usageError(mapUsageLine(), "rolodexter map", `argument --on-error: invalid choice: ${pyRepr(value)} (choose from fail, skip, quarantine)`);
}

/** Handle one `rolodexter map` CLI token, mutating `args`/`positional`/`unknownShortOptions` in place. Returns the loop index to resume from. */
function applyMapOption(
  argv: string[],
  i: number,
  arg: string,
  knownOptions: string[],
  args: MapArgs,
  positional: string[],
  unknownShortOptions: string[],
): number {
  const resolved = optionToken(arg, knownOptions, mapUsageLine(), "rolodexter map");
  const option = resolved?.option ?? arg;
  const inlineValue = resolved?.value;
  if (arg === "-o" || option === "--output") {
    const [value, next] = arg === "-o"
      ? takeResolvedValue(argv, i, "-o", undefined, mapUsageLine(), "rolodexter map")
      : takeResolvedValue(argv, i, "--output", inlineValue, mapUsageLine(), "rolodexter map");
    args.output = value;
    return next;
  } else if (arg.startsWith("-o") && arg.length > 2 && !arg.startsWith("--")) {
    args.output = arg.slice(2);
  } else if (option === "--format") {
    const [value, next] = takeResolvedValue(argv, i, "--format", inlineValue, mapUsageLine(), "rolodexter map");
    args.format = validateFormat(value, "--format", mapUsageLine(), "rolodexter map");
    return next;
  } else if (option === "--in-format") {
    const [value, next] = takeResolvedValue(argv, i, "--in-format", inlineValue, mapUsageLine(), "rolodexter map");
    args.inFormat = validateFormat(value, "--in-format", mapUsageLine(), "rolodexter map");
    return next;
  } else if (option === "--region") {
    const [value, next] = takeResolvedValue(argv, i, "--region", inlineValue, mapUsageLine(), "rolodexter map");
    args.region = value;
    return next;
  } else if (option === "--languages") {
    const [value, next] = takeResolvedValue(argv, i, "--languages", inlineValue, mapUsageLine(), "rolodexter map");
    args.languages = value;
    return next;
  } else if (option === "--strict") {
    rejectExplicitFlagValue("--strict", inlineValue, mapUsageLine(), "rolodexter map");
    args.strict = true;
  } else if (option === "--min-confidence") {
    const [value, next] = takeResolvedValue(argv, i, "--min-confidence", inlineValue, mapUsageLine(), "rolodexter map");
    args.minConfidence = asFloat(value, "--min-confidence", mapUsageLine(), "rolodexter map");
    return next;
  } else if (option === "--no-normalize") {
    rejectExplicitFlagValue("--no-normalize", inlineValue, mapUsageLine(), "rolodexter map");
    args.normalize = false;
  } else if (option === "--embedded-phones") {
    rejectExplicitFlagValue("--embedded-phones", inlineValue, mapUsageLine(), "rolodexter map");
    args.embeddedPhones = true;
  } else {
    return applyMapOptionTail(argv, i, arg, option, inlineValue, args, positional, unknownShortOptions);
  }
  return i;
}

/** The remainder of `applyMapOption`'s option table, split out so neither half carries the whole
 * option count in its own complexity score. Takes `option`/`inlineValue` already resolved by the
 * caller so `optionToken` runs exactly once per argument, same as before the split. */
function applyMapOptionTail(
  argv: string[],
  i: number,
  arg: string,
  option: string,
  inlineValue: string | undefined,
  args: MapArgs,
  positional: string[],
  unknownShortOptions: string[],
): number {
  if (option === "--on-error") {
    const [value, next] = takeResolvedValue(argv, i, "--on-error", inlineValue, mapUsageLine(), "rolodexter map");
    args.onError = validateOnError(value);
    return next;
  } else if (option === "--quarantine-output") {
    const [value, next] = takeResolvedValue(argv, i, "--quarantine-output", inlineValue, mapUsageLine(), "rolodexter map");
    args.quarantineOutput = value;
    return next;
  } else if (option === "--max-materialized-rows") {
    const [value, next] = takeResolvedValue(argv, i, "--max-materialized-rows", inlineValue, mapUsageLine(), "rolodexter map");
    args.maxMaterializedRows = optionalLimit(asNonNegativeInt(value, "--max-materialized-rows", mapUsageLine(), "rolodexter map"));
    return next;
  } else if (option === "--max-json-input-bytes") {
    const [value, next] = takeResolvedValue(argv, i, "--max-json-input-bytes", inlineValue, mapUsageLine(), "rolodexter map");
    args.maxJsonInputBytes = optionalLimit(asNonNegativeInt(value, "--max-json-input-bytes", mapUsageLine(), "rolodexter map"));
    return next;
  } else if (option === "--keep-unmapped") {
    rejectExplicitFlagValue("--keep-unmapped", inlineValue, mapUsageLine(), "rolodexter map");
    args.keepUnmapped = true;
  } else if (option === "--dedupe") {
    rejectExplicitFlagValue("--dedupe", inlineValue, mapUsageLine(), "rolodexter map");
    args.dedupe = true;
  } else if (option === "--override") {
    const [value, next] = takeResolvedValue(argv, i, "--override", inlineValue, mapUsageLine(), "rolodexter map");
    (args.override ??= []).push(value);
    return next;
  } else if (option === "--schema-out") {
    const [value, next] = takeResolvedValue(argv, i, "--schema-out", inlineValue, mapUsageLine(), "rolodexter map");
    args.schemaOut = value;
    return next;
  } else if (option === "--schema-in") {
    const [value, next] = takeResolvedValue(argv, i, "--schema-in", inlineValue, mapUsageLine(), "rolodexter map");
    args.schemaIn = value;
    return next;
  } else if (option === "--help" || arg === "-h") {
    rejectExplicitFlagValue("--help", inlineValue, mapUsageLine(), "rolodexter map");
    throw new CliHelpError(mapUsage());
  } else if (arg.startsWith("-")) {
    if (/^-[^-]/.test(arg) && positional.length === 0) {
      unknownShortOptions.push(arg);
      return i;
    }
    throw usageError(mapUsageLine(), "rolodexter map", `unrecognized arguments: ${arg}`);
  } else {
    positional.push(arg);
  }
  return i;
}

function parseMapArgs(argv: string[]): MapArgs {
  const positional: string[] = [];
  const unknownShortOptions: string[] = [];
  const knownOptions = [
    "--output",
    "--format",
    "--in-format",
    "--region",
    "--languages",
    "--strict",
    "--min-confidence",
    "--no-normalize",
    "--embedded-phones",
    "--on-error",
    "--quarantine-output",
    "--max-materialized-rows",
    "--max-json-input-bytes",
    "--keep-unmapped",
    "--dedupe",
    "--override",
    "--schema-out",
    "--schema-in",
    "--help",
  ];
  const args: MapArgs = {
    input: "",
    format: "auto",
    inFormat: "auto",
    region: "US",
    strict: false,
    minConfidence: 0,
    normalize: true,
    embeddedPhones: false,
    onError: "fail",
    maxMaterializedRows: DEFAULT_MAX_MATERIALIZED_ROWS,
    maxJsonInputBytes: DEFAULT_MAX_JSON_INPUT_BYTES,
    keepUnmapped: false,
    dedupe: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i] ?? "";
    if (arg === "--") {
      positional.push(...argv.slice(i + 1));
      break;
    }
    i = applyMapOption(argv, i, arg, knownOptions, args, positional, unknownShortOptions);
  }

  if (positional.length === 0) {
    throw usageError(mapUsageLine(), "rolodexter map", "the following arguments are required: input");
  }
  if (unknownShortOptions.length > 0) {
    throw usageError(rootUsageLine(), "rolodexter", `unrecognized arguments: ${unknownShortOptions.join(" ")}`);
  }
  if (positional.length > 1) {
    throw usageError(mapUsageLine(), "rolodexter map", `unrecognized arguments: ${positional.slice(1).join(" ")}`);
  }
  if (args.quarantineOutput && args.onError !== "quarantine") {
    throw new Error("--quarantine-output requires --on-error quarantine");
  }
  if (!Number.isFinite(args.minConfidence) || args.minConfidence < 0 || args.minConfidence > 1) {
    throw new Error("confidence_threshold must be between 0.0 and 1.0");
  }
  args.input = positional[0] ?? "";
  if (args.output === "") {
    args.output = undefined;
  }
  if (args.quarantineOutput === "") {
    args.quarantineOutput = undefined;
  }
  return args;
}

function parseExplainArgs(argv: string[]): ExplainArgs {
  const positional: string[] = [];
  const unknownShortOptions: string[] = [];
  const knownOptions = ["--value", "--region", "--languages", "--override", "--help"];
  const args: ExplainArgs = { header: "", region: "US" };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i] ?? "";
    if (arg === "--") {
      positional.push(...argv.slice(i + 1));
      break;
    }
    const resolved = optionToken(arg, knownOptions, explainUsageLine(), "rolodexter explain");
    const option = resolved?.option ?? arg;
    const inlineValue = resolved?.value;
    if (option === "--value") {
      const [value, next] = takeResolvedValue(argv, i, "--value", inlineValue, explainUsageLine(), "rolodexter explain");
      args.value = value;
      i = next;
    } else if (option === "--region") {
      const [value, next] = takeResolvedValue(argv, i, "--region", inlineValue, explainUsageLine(), "rolodexter explain");
      args.region = value;
      i = next;
    } else if (option === "--languages") {
      const [value, next] = takeResolvedValue(argv, i, "--languages", inlineValue, explainUsageLine(), "rolodexter explain");
      args.languages = value;
      i = next;
    } else if (option === "--override") {
      const [value, next] = takeResolvedValue(argv, i, "--override", inlineValue, explainUsageLine(), "rolodexter explain");
      (args.override ??= []).push(value);
      i = next;
    } else if (option === "--help" || arg === "-h") {
      rejectExplicitFlagValue("--help", inlineValue, explainUsageLine(), "rolodexter explain");
      throw new CliHelpError(explainUsage());
    } else if (arg.startsWith("-")) {
      if (/^-[^-]/.test(arg) && positional.length === 0) {
        unknownShortOptions.push(arg);
        continue;
      }
      throw usageError(explainUsageLine(), "rolodexter explain", `unrecognized arguments: ${arg}`);
    } else {
      positional.push(arg);
    }
  }
  if (positional.length === 0) {
    throw usageError(explainUsageLine(), "rolodexter explain", "the following arguments are required: header");
  }
  if (unknownShortOptions.length > 0) {
    throw usageError(rootUsageLine(), "rolodexter", `unrecognized arguments: ${unknownShortOptions.join(" ")}`);
  }
  if (positional.length > 1) {
    throw usageError(explainUsageLine(), "rolodexter explain", `unrecognized arguments: ${positional.slice(1).join(" ")}`);
  }
  args.header = positional[0] ?? "";
  return args;
}

/** Handle one `rolodexter profile` CLI token, mutating `args`/`positional`/`unknownShortOptions` in place. Returns the loop index to resume from. */
function applyProfileOption(
  argv: string[],
  i: number,
  arg: string,
  knownOptions: string[],
  args: ProfileArgs,
  positional: string[],
  unknownShortOptions: string[],
): number {
  const resolved = optionToken(arg, knownOptions, profileUsageLine(), "rolodexter profile");
  const option = resolved?.option ?? arg;
  const inlineValue = resolved?.value;
  if (option === "--in-format") {
    const [value, next] = takeResolvedValue(argv, i, "--in-format", inlineValue, profileUsageLine(), "rolodexter profile");
    args.inFormat = validateFormat(value, "--in-format", profileUsageLine(), "rolodexter profile");
    return next;
  } else if (option === "--region") {
    const [value, next] = takeResolvedValue(argv, i, "--region", inlineValue, profileUsageLine(), "rolodexter profile");
    args.region = value;
    return next;
  } else if (option === "--languages") {
    const [value, next] = takeResolvedValue(argv, i, "--languages", inlineValue, profileUsageLine(), "rolodexter profile");
    args.languages = value;
    return next;
  } else if (option === "--override") {
    const [value, next] = takeResolvedValue(argv, i, "--override", inlineValue, profileUsageLine(), "rolodexter profile");
    (args.override ??= []).push(value);
    return next;
  } else if (option === "--max-rows") {
    const [value, next] = takeResolvedValue(argv, i, "--max-rows", inlineValue, profileUsageLine(), "rolodexter profile");
    args.maxRows = asNonNegativeInt(value, "--max-rows", profileUsageLine(), "rolodexter profile");
    return next;
  } else if (option === "--min-confidence") {
    const [value, next] = takeResolvedValue(argv, i, "--min-confidence", inlineValue, profileUsageLine(), "rolodexter profile");
    args.minConfidence = asFloat(value, "--min-confidence", profileUsageLine(), "rolodexter profile");
    return next;
  } else if (option === "--embedded-phones") {
    rejectExplicitFlagValue("--embedded-phones", inlineValue, profileUsageLine(), "rolodexter profile");
    args.embeddedPhones = true;
  } else if (option === "--no-normalize") {
    rejectExplicitFlagValue("--no-normalize", inlineValue, profileUsageLine(), "rolodexter profile");
    args.noNormalize = true;
  } else if (option === "--json") {
    rejectExplicitFlagValue("--json", inlineValue, profileUsageLine(), "rolodexter profile");
    args.json = true;
  } else if (option === "--max-json-input-bytes") {
    const [value, next] = takeResolvedValue(argv, i, "--max-json-input-bytes", inlineValue, profileUsageLine(), "rolodexter profile");
    args.maxJsonInputBytes = optionalLimit(asNonNegativeInt(value, "--max-json-input-bytes", profileUsageLine(), "rolodexter profile"));
    return next;
  } else if (option === "--help" || arg === "-h") {
    rejectExplicitFlagValue("--help", inlineValue, profileUsageLine(), "rolodexter profile");
    throw new CliHelpError(profileUsage());
  } else if (arg.startsWith("-")) {
    if (/^-[^-]/.test(arg) && positional.length === 0) {
      unknownShortOptions.push(arg);
      return i;
    }
    throw usageError(profileUsageLine(), "rolodexter profile", `unrecognized arguments: ${arg}`);
  } else {
    positional.push(arg);
  }
  return i;
}

function parseProfileArgs(argv: string[]): ProfileArgs {
  const positional: string[] = [];
  const unknownShortOptions: string[] = [];
  const knownOptions = [
    "--in-format",
    "--region",
    "--languages",
    "--override",
    "--max-rows",
    "--min-confidence",
    "--embedded-phones",
    "--no-normalize",
    "--json",
    "--max-json-input-bytes",
    "--help",
  ];
  const args: ProfileArgs = {
    input: "",
    inFormat: "auto",
    region: "US",
    maxRows: 0,
    minConfidence: 0,
    embeddedPhones: false,
    noNormalize: false,
    json: false,
    maxJsonInputBytes: DEFAULT_MAX_JSON_INPUT_BYTES,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i] ?? "";
    if (arg === "--") {
      positional.push(...argv.slice(i + 1));
      break;
    }
    i = applyProfileOption(argv, i, arg, knownOptions, args, positional, unknownShortOptions);
  }
  if (positional.length === 0) {
    throw usageError(profileUsageLine(), "rolodexter profile", "the following arguments are required: input");
  }
  if (unknownShortOptions.length > 0) {
    throw usageError(rootUsageLine(), "rolodexter", `unrecognized arguments: ${unknownShortOptions.join(" ")}`);
  }
  if (positional.length > 1) {
    throw usageError(profileUsageLine(), "rolodexter profile", `unrecognized arguments: ${positional.slice(1).join(" ")}`);
  }
  args.input = positional[0] ?? "";
  return args;
}

function parsePythonCsv(text: string): string[][] {
  const records: string[][] = [];
  let record: string[] = [];
  let field = "";
  let inQuotes = false;
  let atFieldStart = true;
  let recordStarted = false;

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i] ?? "";
    if (inQuotes) {
      if (char === "\"") {
        if (text[i + 1] === "\"") {
          field += "\"";
          i += 1;
        } else {
          inQuotes = false;
        }
      } else {
        field += char;
      }
      recordStarted = true;
      continue;
    }

    if (char === "\"" && atFieldStart) {
      inQuotes = true;
      atFieldStart = false;
      recordStarted = true;
    } else if (char === ",") {
      record.push(field);
      field = "";
      atFieldStart = true;
      recordStarted = true;
    } else if (char === "\r" || char === "\n") {
      if (char === "\r" && text[i + 1] === "\n") {
        i += 1;
      }
      record.push(field);
      records.push(record);
      record = [];
      field = "";
      atFieldStart = true;
      recordStarted = false;
    } else {
      field += char;
      atFieldStart = false;
      recordStarted = true;
    }
  }

  if (recordStarted || field || record.length > 0 || inQuotes) {
    record.push(field);
    records.push(record);
  }
  return records;
}

function csvRecordLineSpan(record: string[]): number {
  return Math.max(1, record.reduce((total, field) => total + (field.match(/\n/g)?.length ?? 0), 0));
}

/**
 * Return unique header names, suffixing repeats, plus how many were renamed.
 *
 * A CSV reader that keeps only the last value for a repeated column name
 * silently loses the first one before the mapper ever sees it. Renaming the
 * repeats to `Email__2` keeps both values and lets the mapper's own
 * collision handling merge them into a list, which is the documented
 * behavior for two headers that mean the same field.
 */
function dedupeHeaders(rawHeaders: string[]): [string[], number] {
  const seen = new Map<string, number>();
  const out: string[] = [];
  let renamed = 0;
  rawHeaders.forEach((header, index) => {
    let name = (header ?? "").trim() || `column_${index + 1}`;
    const count = (seen.get(name) ?? 0) + 1;
    seen.set(name, count);
    if (count > 1) {
      name = `${name}__${count}`;
      renamed += 1;
    }
    out.push(name);
  });
  return [out, renamed];
}

/**
 * True if the first CSV row looks like a contact rather than column names.
 *
 * Row 1 is treated as data when at least one cell parses as an email, a
 * phone number or a URL - things that are values, never column names.
 */
function looksLikeDataNotHeaders(headers: string[], mapper: ContactMapper): boolean {
  if (headers.length === 0) {
    return false;
  }
  for (const header of headers) {
    const cell = (header ?? "").trim();
    if (!cell) {
      continue;
    }
    const match = mapper.identify("__header_probe__", { value: cell });
    if (match.strategy === "heuristic" && ["email", "phone", "website"].includes(match.canonical)) {
      return true;
    }
  }
  return false;
}

const JSON_NAN_SENTINEL = "\u0000rolodexter.nan\u0000";
const JSON_INF_SENTINEL = "\u0000rolodexter.inf\u0000";
const JSON_NEG_INF_SENTINEL = "\u0000rolodexter.neg_inf\u0000";

function isJsonConstantBoundary(char: string | undefined): boolean {
  return char === undefined || !/[A-Za-z0-9_$]/.test(char);
}

function replacePythonJsonConstants(raw: string): string {
  let out = "";
  let inString = false;
  let escaped = false;
  for (let i = 0; i < raw.length; i += 1) {
    const char = raw[i] ?? "";
    if (inString) {
      out += char;
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === "\"") {
        inString = false;
      }
      continue;
    }
    if (char === "\"") {
      inString = true;
      out += char;
      continue;
    }
    const prev = i > 0 ? raw[i - 1] : undefined;
    if (raw.startsWith("-Infinity", i) && isJsonConstantBoundary(prev) && isJsonConstantBoundary(raw[i + 9])) {
      out += JSON.stringify(JSON_NEG_INF_SENTINEL);
      i += 8;
    } else if (raw.startsWith("Infinity", i) && isJsonConstantBoundary(prev) && isJsonConstantBoundary(raw[i + 8])) {
      out += JSON.stringify(JSON_INF_SENTINEL);
      i += 7;
    } else if (raw.startsWith("NaN", i) && isJsonConstantBoundary(prev) && isJsonConstantBoundary(raw[i + 3])) {
      out += JSON.stringify(JSON_NAN_SENTINEL);
      i += 2;
    } else {
      out += char;
    }
  }
  return out;
}

function revivePythonJsonConstants(value: unknown): unknown {
  if (value === JSON_NAN_SENTINEL) {
    return Number.NaN;
  }
  if (value === JSON_INF_SENTINEL) {
    return Number.POSITIVE_INFINITY;
  }
  if (value === JSON_NEG_INF_SENTINEL) {
    return Number.NEGATIVE_INFINITY;
  }
  if (Array.isArray(value)) {
    return value.map(revivePythonJsonConstants);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, item]) => [key, revivePythonJsonConstants(item)]),
    );
  }
  return value;
}

function parsePythonJson(raw: string): unknown {
  return revivePythonJsonConstants(JSON.parse(replacePythonJsonConstants(raw)) as unknown);
}

async function* readCsvRows(path: string, mapper?: ContactMapper): AsyncGenerator<InputRow | RowFailure> {
  const records = parsePythonCsv(readFileSync(path, "utf8").replace(/^\uFEFF/, ""));
  const rawHeaders = (records.shift() ?? []).map(String);
  const [headers, renamed] = dedupeHeaders(rawHeaders);
  if (renamed > 0) {
    logStderr(`warning: ${renamed} duplicate column name(s) in ${path} were renamed with a __N suffix so no column is lost`);
  }
  if (mapper && looksLikeDataNotHeaders(rawHeaders, mapper)) {
    logStderr(
      `warning: the first row of ${path} looks like DATA, not column names - it has been consumed as the header row and that record will not appear in the output. Add a header row, or re-export with one.`,
    );
  }
  let lineNumber = 1;
  for (const record of records) {
    lineNumber += csvRecordLineSpan(record);
    if (record.length === 1 && record[0] === "") {
      continue;
    }
    const data: Record<string, unknown> = {};
    for (const [index, header] of headers.entries()) {
      setOwnProperty(data, header, index < record.length ? record[index] : "");
    }
    yield { kind: "row", rowNumber: lineNumber, data };
  }
}

async function* readJsonlRows(path: string): AsyncGenerator<InputRow | RowFailure> {
  const lines = createInterface({
    crlfDelay: Infinity,
    input: createReadStream(path, { encoding: "utf8" }),
  });
  let lineNumber = 0;
  for await (const line of lines) {
    lineNumber += 1;
    const raw = line.trim();
    if (!raw) {
      continue;
    }
    try {
      const parsed = parsePythonJson(raw);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        yield { kind: "row", rowNumber: lineNumber, data: parsed as Record<string, unknown> };
      } else {
        yield { kind: "failure", rowNumber: lineNumber, error: `expected JSON object, got ${pythonTypeName(parsed)}`, raw: parsed };
      }
    } catch (error) {
      yield { kind: "failure", rowNumber: lineNumber, error: `invalid JSON: ${pythonJsonDecodeShortMessage(raw, error as Error)}`, raw };
    }
  }
}

async function* readJsonRows(path: string, maxJsonBytes: number | null): AsyncGenerator<InputRow | RowFailure> {
  if (maxJsonBytes !== null) {
    const bytes = Buffer.byteLength(readFileSync(path));
    if (bytes > maxJsonBytes) {
      throw new Error(
        `JSON input is ${bytes} bytes, above the ${maxJsonBytes} byte materialization limit; use JSONL for streaming input or raise --max-json-input-bytes`,
      );
    }
  }
  const jsonText = readFileSync(path, "utf8");
  let parsed: unknown;
  try {
    parsed = parsePythonJson(jsonText);
  } catch (error) {
    throw new Error(pythonJsonDecodeMessage(jsonText, error as Error));
  }
  if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
    yield { kind: "row", rowNumber: 1, data: parsed as Record<string, unknown> };
    return;
  }
  if (Array.isArray(parsed)) {
    for (const [index, item] of parsed.entries()) {
      yield item && typeof item === "object" && !Array.isArray(item)
        ? { kind: "row", rowNumber: index + 1, data: item as Record<string, unknown> }
        : { kind: "failure", rowNumber: index + 1, error: `expected JSON object, got ${pythonTypeName(item)}`, raw: item };
    }
  }
}

async function* readRows(path: string, format: Exclude<Format, "auto">, maxJsonBytes: number | null, mapper?: ContactMapper): AsyncGenerator<InputRow | RowFailure> {
  if (format === "csv") {
    yield* readCsvRows(path, mapper);
    return;
  }
  if (format === "jsonl") {
    yield* readJsonlRows(path);
    return;
  }
  yield* readJsonRows(path, maxJsonBytes);
}

function pythonTypeName(value: unknown): string {
  if (value === null) {
    return "NoneType";
  }
  if (Array.isArray(value)) {
    return "list";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? "int" : "float";
  }
  if (typeof value === "string") {
    return "str";
  }
  if (typeof value === "boolean") {
    return "bool";
  }
  if (typeof value === "object") {
    return "dict";
  }
  return typeof value;
}

function scalarize(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(String).join("; ");
  }
  if (value && typeof value === "object") {
    return pythonCompactJson(value);
  }
  return value;
}

function pythonCompactJson(value: unknown): string {
  return pythonJson(value);
}

function pythonPrettyJson(value: unknown): string {
  return pythonJson(value, 2);
}

function pythonJson(value: unknown, indent?: number, level = 0): string {
  if (typeof value === "number") {
    if (Number.isNaN(value)) {
      return "NaN";
    }
    if (value === Number.POSITIVE_INFINITY) {
      return "Infinity";
    }
    if (value === Number.NEGATIVE_INFINITY) {
      return "-Infinity";
    }
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    if (indent === undefined) {
      return `[${value.map((item) => pythonJson(item)).join(", ")}]`;
    }
    if (value.length === 0) {
      return "[]";
    }
    const pad = " ".repeat(indent * level);
    const childPad = " ".repeat(indent * (level + 1));
    return `[\n${value.map((item) => `${childPad}${pythonJson(item, indent, level + 1)}`).join(",\n")}\n${pad}]`;
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (indent === undefined) {
      return `{${entries.map(([key, item]) => `${JSON.stringify(key)}: ${pythonJson(item)}`).join(", ")}}`;
    }
    if (entries.length === 0) {
      return "{}";
    }
    const pad = " ".repeat(indent * level);
    const childPad = " ".repeat(indent * (level + 1));
    return `{\n${entries.map(([key, item]) => `${childPad}${JSON.stringify(key)}: ${pythonJson(item, indent, level + 1)}`).join(",\n")}\n${pad}}`;
  }
  return JSON.stringify(value);
}

function pythonJsonDecodeMessage(raw: string, error: Error): string {
  const trimmed = raw.trimStart();
  if (!trimmed || !/^[{["\-0-9tfn]/.test(trimmed)) {
    const offset = trimmed ? raw.length - trimmed.length : 0;
    return `Expecting value${jsonLocation(raw, offset)}`;
  }
  if (/^[A-Za-z]/.test(trimmed) && !/^(?:true|false|null)\b/.test(trimmed)) {
    return `Expecting value${jsonLocation(raw, raw.length - trimmed.length)}`;
  }
  if (trimmed.startsWith("{") && !/^\{\s*(?:}|")/.test(trimmed)) {
    const base = raw.length - trimmed.length;
    const afterBrace = trimmed.slice(1);
    const gap = afterBrace.search(/\S/);
    const offset = base + 1 + (gap === -1 ? 0 : gap);
    return `Expecting property name enclosed in double quotes${jsonLocation(raw, offset)}`;
  }
  const missingValueAfterColon = /:\s*(?=[}\]])/.exec(raw);
  if (missingValueAfterColon?.index !== undefined) {
    const offset = missingValueAfterColon.index + missingValueAfterColon[0].length;
    return `Expecting value${jsonLocation(raw, offset)}`;
  }
  if (error.message === "Unexpected end of JSON input") {
    return `Expecting value${jsonLocation(raw, raw.length)}`;
  }
  return error.message;
}

function pythonJsonDecodeShortMessage(raw: string, error: Error): string {
  return pythonJsonDecodeMessage(raw, error).replace(/: line \d+ column \d+ \(char \d+\)$/, "");
}

function jsonLocation(raw: string, offset: number): string {
  const bounded = Math.max(0, Math.min(offset, raw.length));
  const before = raw.slice(0, bounded);
  const line = before.split("\n").length;
  const lineStart = before.lastIndexOf("\n") + 1;
  const column = bounded - lineStart + 1;
  return `: line ${line} column ${column} (char ${bounded})`;
}

/**
 * Return the dict written for one mapped row.
 *
 * `MappingResult.unmapped` holds every column the mapper could not place.
 * `--keep-unmapped` passes those columns through untouched under their
 * original header. A canonical field always wins its own name; an unmapped
 * column that happens to collide keeps its data under a suffixed key.
 */
function rowPayload(result: MappingResult, keepUnmapped: boolean): Record<string, unknown> {
  if (!keepUnmapped || Object.keys(result.unmapped).length === 0) {
    return result.normalized;
  }
  const merged: Record<string, unknown> = { ...result.normalized };
  for (const [key, value] of Object.entries(result.unmapped)) {
    let target = Object.prototype.hasOwnProperty.call(merged, key) ? `${key}__unmapped` : key;
    while (Object.prototype.hasOwnProperty.call(merged, target)) {
      target += "_";
    }
    merged[target] = value;
  }
  return merged;
}

function formatRows(
  results: MappingResult[],
  format: Exclude<Format, "auto">,
  maxRows: number | null,
  outputPath: string | undefined,
  keepUnmapped: boolean,
): string {
  const rows = results.map((result) => rowPayload(result, keepUnmapped));
  if (format === "jsonl") {
    return rows.map((row) => pythonCompactJson(row)).join("\n") + (rows.length ? "\n" : "");
  }
  if (maxRows !== null && rows.length > maxRows) {
    throw new Error(`${format.toUpperCase()} output requires materializing more than ${maxRows} row(s); use --format jsonl for streaming output or raise --max-materialized-rows`);
  }
  if (format === "json") {
    return `${pythonPrettyJson(rows)}\n`;
  }

  const fieldnames: string[] = [];
  const seen = new Set<string>();
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (!seen.has(key)) {
        seen.add(key);
        fieldnames.push(key);
      }
    }
  }
  const text = stringifyCsv(rows.map((row) => Object.fromEntries(Object.entries(row).map(([key, value]) => [key, scalarize(value)]))), {
    header: true,
    columns: fieldnames,
  });
  if (!outputPath) {
    return text.replace(/\n/g, process.platform === "win32" ? "\r\r\n" : "\r\n");
  }
  return text.replace(/\n/g, "\r\n");
}

function writeAtomic(path: string | undefined, text: string): void {
  if (!path) {
    writeStdout(text);
    return;
  }
  const temp = join(dirname(path), `.${basename(path)}.${process.pid}.${randomUUID()}.tmp`);
  try {
    writeFileSync(temp, text, { encoding: "utf8", flag: "wx" });
    renameSync(temp, path);
  } catch (error) {
    try {
      unlinkSync(temp);
    } catch {
      // Best effort cleanup.
    }
    throw error;
  }
}

interface TextWriter {
  write(text: string): Promise<void>;
  close(): Promise<void>;
  abort(): Promise<void>;
}

function waitForDrain(stream: WriteStream): Promise<void> {
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      stream.off("drain", onDrain);
      stream.off("error", onError);
    };
    const onDrain = () => {
      cleanup();
      resolve();
    };
    const onError = (error: Error) => {
      cleanup();
      reject(error);
    };
    stream.once("drain", onDrain);
    stream.once("error", onError);
  });
}

function createTextWriter(path: string | undefined): TextWriter {
  if (!path) {
    return {
      async write(text: string): Promise<void> {
        if (!process.stdout.write(cliText(text))) {
          await once(process.stdout, "drain");
        }
      },
      async close(): Promise<void> {
        // stdout is process-owned.
      },
      async abort(): Promise<void> {
        // stdout is process-owned.
      },
    };
  }

  const temp = join(dirname(path), `.${basename(path)}.${process.pid}.${randomUUID()}.tmp`);
  const stream = createWriteStream(temp, { encoding: "utf8", flags: "wx" });
  stream.on("error", () => {
    // Python's atomic context cleanup reports the original row error only.
  });
  let closed = false;
  return {
    async write(text: string): Promise<void> {
      if (!stream.write(text)) {
        await waitForDrain(stream);
      }
    },
    async close(): Promise<void> {
      if (closed) {
        return;
      }
      closed = true;
      await new Promise<void>((resolve, reject) => {
        stream.once("error", reject);
        stream.end(resolve);
      });
      renameSync(temp, path);
    },
    async abort(): Promise<void> {
      if (closed) {
        return;
      }
      closed = true;
      stream.destroy();
      try {
        unlinkSync(temp);
      } catch {
        // Best effort cleanup.
      }
    },
  };
}

async function closeTextWriter(writer: TextWriter | undefined): Promise<void> {
  if (writer) {
    await writer.close();
  }
}

async function abortTextWriter(writer: TextWriter | undefined): Promise<void> {
  if (writer) {
    await writer.abort();
  }
}

function defaultQuarantinePath(args: MapArgs): string {
  return args.quarantineOutput || `${args.output || args.input}.quarantine.jsonl`;
}

function comparablePath(path: string): string {
  let absolute = resolve(path);
  try {
    absolute = realpathSync.native(absolute);
  } catch {
    try {
      absolute = join(realpathSync.native(dirname(absolute)), basename(absolute));
    } catch {
      // A missing parent will be reported when the writer is opened.
    }
  }
  return process.platform === "win32" ? absolute.toLowerCase() : absolute;
}

/**
 * Opens the quarantine file on the FIRST failure, not before.
 *
 * A stream opened up front would still create - and, via the atomic
 * rename, truncate - whatever was at that path even on a run with zero
 * failures. Since the default path is derived from the input or output
 * name, a clean re-run would silently destroy the previous run's rejects.
 */
class LazyQuarantineWriter {
  readonly #path: string;
  #writer: TextWriter | undefined;

  constructor(path: string) {
    this.#path = path;
  }

  async write(failure: RowFailure): Promise<void> {
    if (!this.#writer) {
      this.#writer = createTextWriter(this.#path);
    }
    await this.#writer.write(`${pythonCompactJson({
      row: failure.rowNumber,
      error: failure.error,
      raw: failure.raw,
    })}\n`);
  }

  async close(): Promise<void> {
    await closeTextWriter(this.#writer);
  }

  async abort(): Promise<void> {
    await abortTextWriter(this.#writer);
  }
}

async function handleFailure(
  failure: RowFailure,
  args: MapArgs,
  quarantineWriter: LazyQuarantineWriter | undefined,
): Promise<number> {
  if (args.onError === "fail") {
    throw new Error(`row ${failure.rowNumber}: ${failure.error}`);
  }
  if (args.onError === "skip") {
    logStderr(`warning: skipped row ${failure.rowNumber}: ${failure.error}`);
    return 1;
  }
  if (!quarantineWriter) {
    throw new Error("--on-error quarantine requires a quarantine output");
  }
  await quarantineWriter.write(failure);
  logStderr(`warning: quarantined row ${failure.rowNumber}: ${failure.error}`);
  return 1;
}

interface MapStats {
  failed: number;
  duplicates: number;
  droppedHeaders: Map<string, number>;
  lowConfidence: Map<string, number>;
}

/** Record which columns were dropped or matched only weakly. */
function noteResult(stats: MapStats, result: MappingResult): void {
  for (const match of result.field_matches) {
    if (!match.is_matched) {
      stats.droppedHeaders.set(match.original, (stats.droppedHeaders.get(match.original) ?? 0) + 1);
    } else if (match.confidence < REVIEW_CONFIDENCE) {
      const key = `${match.original} -> ${match.canonical}`;
      stats.lowConfidence.set(key, (stats.lowConfidence.get(key) ?? 0) + 1);
    }
  }
}

/** Print a one-line-per-column stderr summary, capped so it stays readable. */
function summarizeColumns(label: string, counts: Map<string, number>, hint: string): void {
  if (counts.size === 0) {
    return;
  }
  const ordered = [...counts.entries()].sort((left, right) => (right[1] - left[1]) || left[0].localeCompare(right[0]));
  const shown = ordered.slice(0, MAX_SUMMARY_COLUMNS);
  logStderr(`warning: ${label} (${ordered.length} column(s)); ${hint}`);
  for (const [name, count] of shown) {
    logStderr(`  ${name}  [${count} row(s)]`);
  }
  if (ordered.length > shown.length) {
    logStderr(`  ... and ${ordered.length - shown.length} more`);
  }
}

/** Return the first row's header names without consuming the whole file. */
async function peekHeaders(path: string, format: Exclude<Format, "auto">, maxJsonBytes: number | null): Promise<string[]> {
  for await (const item of readRows(path, format, maxJsonBytes)) {
    if (item.kind === "row") {
      return Object.keys(item.data);
    }
  }
  return [];
}

/** Map one input row/failure into `results` or `outputWriter`, mutating `stats`/`seenKeys` in place. Returns the amount to add to the streamed row count. */
async function processMapRow(
  item: InputRow | RowFailure,
  args: MapArgs,
  mapper: ContactMapper,
  stats: MapStats,
  seenKeys: Set<string>,
  quarantineWriter: LazyQuarantineWriter | undefined,
  streamJsonl: boolean,
  outputWriter: TextWriter | undefined,
  results: MappingResult[],
  outputFormat: Format,
): Promise<number> {
  if (item.kind === "failure") {
    stats.failed += await handleFailure(item, args, quarantineWriter);
    return 0;
  }
  let result: MappingResult;
  try {
    result = mapper.map_payload(item.data, { extract_embedded_phones: args.embeddedPhones });
  } catch (error) {
    stats.failed += await handleFailure({
      kind: "failure",
      rowNumber: item.rowNumber,
      error: (error as Error).message,
      raw: item.data,
    }, args, quarantineWriter);
    return 0;
  }

  noteResult(stats, result);
  if (args.dedupe) {
    const keys = result.get_identity_keys();
    if (keys.length > 0 && keys.some((key) => seenKeys.has(key))) {
      stats.duplicates += 1;
      return 0;
    }
    for (const key of keys) {
      seenKeys.add(key);
    }
  }

  if (streamJsonl) {
    await outputWriter?.write(`${pythonCompactJson(rowPayload(result, args.keepUnmapped))}\n`);
    return 1;
  }
  if (args.maxMaterializedRows !== null && results.length >= args.maxMaterializedRows) {
    throw new Error(`${outputFormat.toUpperCase()} output requires materializing more than ${args.maxMaterializedRows} row(s); use --format jsonl for streaming output or raise --max-materialized-rows`);
  }
  results.push(result);
  return 0;
}

/** Resolves and validates the quarantine output path for `commandMap`, kept separate so its two
 * collision checks don't add to the branch count of the pipeline that calls it. */
function resolveQuarantinePath(args: MapArgs): string | undefined {
  const quarantinePath = args.onError === "quarantine" ? defaultQuarantinePath(args) : undefined;
  if (quarantinePath && comparablePath(quarantinePath) === comparablePath(args.input)) {
    throw new Error("quarantine output must differ from the input path");
  }
  if (
    quarantinePath &&
    args.output &&
    comparablePath(quarantinePath) === comparablePath(args.output)
  ) {
    throw new Error("quarantine output must differ from the mapped output path");
  }
  return quarantinePath;
}

/** Builds the final "Mapped N row(s) -> ..." status line, split out of `commandMap` so its own
 * small decision tree doesn't compound with the ingestion/write pipeline above it. */
function buildMapSummaryMessage(
  count: number,
  args: MapArgs,
  stats: MapStats,
  outputFormat: Format,
  quarantinePath: string | undefined,
): string {
  let message = `Mapped ${count} row(s) -> ${args.output || "stdout"} (${outputFormat})`;
  if (stats.duplicates) {
    message += `; dropped ${stats.duplicates} duplicate row(s)`;
  }
  if (stats.failed) {
    if (args.onError === "quarantine") {
      message += `; quarantined ${stats.failed} row(s) -> ${quarantinePath}`;
    } else {
      message += `; skipped ${stats.failed} row(s)`;
    }
  }
  return message;
}

async function commandMap(argv: string[]): Promise<number> {
  let args: MapArgs;
  try {
    args = parseMapArgs(argv);
  } catch (error) {
    if (error instanceof CliHelpError) {
      logStdout(error.text);
      return 0;
    }
    throw error;
  }

  if (args.output && comparablePath(args.output) === comparablePath(args.input)) {
    // The transform is lossy in both directions: original formatting is
    // rewritten, and any column the mapper cannot place is dropped unless
    // --keep-unmapped is set. Overwriting the source export in place would
    // destroy the only copy, with no undo.
    throw new Error(
      "output must differ from the input path; mapping a file onto itself would destroy the original export",
    );
  }

  const mapper = buildMapper({
    region: args.region,
    languages: args.languages,
    normalize: args.normalize,
    strict: args.strict,
    minConfidence: args.minConfidence,
    override: args.override,
  });
  const inputFormat = detectFormat(args.input, args.inFormat);
  const outputFormat = args.output ? detectFormat(args.output, args.format) : args.format === "auto" ? "json" : args.format;
  if (!existsSync(args.input)) {
    throw new Error(fileNotFoundMessage(args.input));
  }

  if (args.schemaIn) {
    if (!existsSync(args.schemaIn)) {
      throw new Error(fileNotFoundMessage(args.schemaIn));
    }
    const data = parsePythonJson(readFileSync(args.schemaIn, "utf8"));
    MappingSchema.from_dict(data as Record<string, unknown>, mapper);
  }

  const quarantinePath = resolveQuarantinePath(args);

  const stats: MapStats = { failed: 0, duplicates: 0, droppedHeaders: new Map(), lowConfidence: new Map() };
  const seenKeys = new Set<string>();
  const items = readRows(args.input, inputFormat, args.maxJsonInputBytes, mapper);
  const results: MappingResult[] = [];
  let count = 0;
  const streamJsonl = outputFormat === "jsonl";
  const outputWriter = streamJsonl ? createTextWriter(args.output) : undefined;
  const quarantineWriter = quarantinePath ? new LazyQuarantineWriter(quarantinePath) : undefined;

  try {
    for await (const item of items) {
      count += await processMapRow(item, args, mapper, stats, seenKeys, quarantineWriter, streamJsonl, outputWriter, results, outputFormat);
    }

    if (streamJsonl) {
      await closeTextWriter(outputWriter);
      await quarantineWriter?.close();
    } else {
      const output = formatRows(results, outputFormat, args.maxMaterializedRows, args.output, args.keepUnmapped);
      writeAtomic(args.output, output);
      await quarantineWriter?.close();
      count = results.length;
    }
  } catch (error) {
    await abortTextWriter(outputWriter);
    await quarantineWriter?.abort();
    throw error;
  }

  if (args.schemaOut) {
    const headers = await peekHeaders(args.input, inputFormat, args.maxJsonInputBytes);
    const schema = mapper.compile_schema(headers);
    writeAtomic(args.schemaOut, `${pythonPrettyJson(schema.to_dict())}\n`);
  }

  if (!args.keepUnmapped) {
    summarizeColumns(
      "dropped unmapped column(s) from the output",
      stats.droppedHeaders,
      "pass --keep-unmapped to carry them through",
    );
  }
  summarizeColumns(
    "low-confidence column mapping(s)",
    stats.lowConfidence,
    "review these, then pin them with --override HEADER=field or raise --min-confidence",
  );

  logStderr(buildMapSummaryMessage(count, args, stats, outputFormat, quarantinePath));
  return stats.failed ? EXIT_PARTIAL : 0;
}

function commandExplain(argv: string[]): number {
  let args: ExplainArgs;
  try {
    args = parseExplainArgs(argv);
  } catch (error) {
    if (error instanceof CliHelpError) {
      logStdout(error.text);
      return 0;
    }
    throw error;
  }
  const mapper = buildMapper({ region: args.region, languages: args.languages, override: args.override });
  const match = mapper.identify(args.header, { value: args.value });
  logStdout(`${inspect(args.header)} -> ${match.canonical} [${match.strategy}, conf=${match.confidence.toFixed(2)}]`);
  if (args.value !== undefined) {
    logStdout();
    logStdout(mapper.map_payload({ [args.header]: args.value }).explain());
  }
  return 0;
}

async function commandProfile(argv: string[]): Promise<number> {
  let args: ProfileArgs;
  try {
    args = parseProfileArgs(argv);
  } catch (error) {
    if (error instanceof CliHelpError) {
      logStdout(error.text);
      return 0;
    }
    throw error;
  }
  const mapper = buildMapper({
    region: args.region,
    languages: args.languages,
    normalize: !args.noNormalize,
    minConfidence: args.minConfidence,
    override: args.override,
  });
  const inputFormat = detectFormat(args.input, args.inFormat);
  if (!existsSync(args.input)) {
    throw new Error(fileNotFoundMessage(args.input));
  }

  // Note: unlike `map`, --max-json-input-bytes is intentionally not applied
  // here - it mirrors the Python CLI, whose profile command parses the flag
  // but never wires it into the read.
  const maxRows = optionalLimit(args.maxRows);
  const rows: Record<string, unknown>[] = [];
  for await (const item of readRows(args.input, inputFormat, DEFAULT_MAX_JSON_INPUT_BYTES, mapper)) {
    if (item.kind === "failure") {
      throw new Error(`row ${item.rowNumber}: ${item.error}`);
    }
    rows.push(item.data);
    if (maxRows !== null && rows.length >= maxRows) {
      break;
    }
  }

  const profile = mapper.profile(rows, {
    max_rows: maxRows,
    extract_embedded_phones: args.embeddedPhones,
  });
  if (args.json) {
    writeStdout(`${pythonPrettyJson(profile.to_dict())}\n`);
  } else {
    logStdout(profile.explain());
  }
  return 0;
}

function commandFields(argv: string[] = []): number {
  for (const arg of argv) {
    if (resolvedHelpOption(arg, fieldsUsage(), "rolodexter fields")) {
      logStdout(fieldsUsage());
      return 0;
    }
  }
  if (argv.includes("--help") || argv.includes("-h")) {
    logStdout(fieldsUsage());
    return 0;
  }
  if (argv.length > 0) {
    throw usageError(rootUsageLine(), "rolodexter", `unrecognized arguments: ${argv.join(" ")}`);
  }
  for (const field of Object.values(CanonicalField)) {
    logStdout(field.value);
  }
  return 0;
}

export async function main(argv = process.argv.slice(2)): Promise<number> {
  const [command, ...rest] = argv;
  if (command && resolvedHelpOption(command, rootUsageLine(), "rolodexter")) {
    logStdout(usage());
    return 0;
  }
  if (command && resolvedVersionOption(command, rootUsageLine(), "rolodexter")) {
    logStdout(`rolodexter ${__version__}`);
    return 0;
  }
  if (!command) {
    throw usageError(rootUsageLine(), "rolodexter", "the following arguments are required: command");
  }
  if (command === "map") {
    return commandMap(rest);
  }
  if (command === "explain") {
    return commandExplain(rest);
  }
  if (command === "profile") {
    return commandProfile(rest);
  }
  if (command === "fields") {
    return commandFields(rest);
  }
  throw usageError(rootUsageLine(), "rolodexter", `argument command: invalid choice: ${inspect(command)} (choose from map, explain, profile, fields)`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  main()
    .then((code) => {
      process.exitCode = code;
    })
    .catch((error: unknown) => {
      if (error instanceof CliUsageError) {
        logStderr(error.message);
        process.exitCode = error.exitCode;
      } else {
        const message = (error instanceof RolodexterError || error instanceof NormalizationError || error instanceof Error)
          ? error.message
          : String(error);
        logStderr(`error: ${message}`);
        process.exitCode = 1;
      }
    });
}
