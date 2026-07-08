#!/usr/bin/env node
import { once } from "node:events";
import { createReadStream, createWriteStream, existsSync, readFileSync, renameSync, unlinkSync, writeFileSync, writeSync } from "node:fs";
import { basename, dirname, join } from "node:path";
import { createInterface } from "node:readline";
import type { WriteStream } from "node:fs";
import { fileURLToPath } from "node:url";
import { inspect } from "node:util";

import { stringify as stringifyCsv } from "csv-stringify/sync";

import {
  CanonicalField,
  ContactMapper,
  NormalizationError,
  RolodexterError,
} from "./index.js";

const DEFAULT_MAX_MATERIALIZED_ROWS = 100_000;
const DEFAULT_MAX_JSON_INPUT_BYTES = 50 * 1024 * 1024;
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
}

interface ExplainArgs {
  header: string;
  value?: string;
  region: string;
  languages?: string;
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
    "usage: rolodexter [-h] {map,explain,fields} ...",
    "",
    "Map messy contact data to a clean canonical schema.",
    "",
    "positional arguments:",
    "  {map,explain,fields}",
    "    map                 Map a CSV/JSON/JSONL file to canonical fields",
    "    explain             Show how a single header resolves",
    "    fields              List all canonical fields",
    "",
    "options:",
    "  -h, --help            show this help message and exit",
  ].join("\n");
}

function rootUsageLine(): string {
  return "usage: rolodexter [-h] {map,explain,fields} ...";
}

function mapUsage(): string {
  return [
    "usage: rolodexter map [-h] [-o OUTPUT] [--format {auto,csv,json,jsonl}]",
    "                      [--in-format {auto,csv,json,jsonl}] [--region REGION]",
    "                      [--languages LANGUAGES] [--strict]",
    "                      [--min-confidence MIN_CONFIDENCE] [--no-normalize]",
    "                      [--embedded-phones] [--on-error {fail,skip,quarantine}]",
    "                      [--quarantine-output QUARANTINE_OUTPUT]",
    "                      [--max-materialized-rows MAX_MATERIALIZED_ROWS]",
    "                      [--max-json-input-bytes MAX_JSON_INPUT_BYTES]",
    "                      input",
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
    "                      input",
  ].join("\n");
}

function explainUsage(): string {
  return [
    "usage: rolodexter explain [-h] [--value VALUE] [--region REGION]",
    "                          [--languages LANGUAGES]",
    "                          header",
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
  ].join("\n");
}

function explainUsageLine(): string {
  return [
    "usage: rolodexter explain [-h] [--value VALUE] [--region REGION]",
    "                          [--languages LANGUAGES]",
    "                          header",
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
  if (!"--help".startsWith(raw)) {
    return false;
  }
  if (equalsAt !== -1) {
    throw usageError(usageText, prog, `argument --help: ignored explicit argument ${pyRepr(arg.slice(equalsAt + 1))}`);
  }
  return true;
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

function takeValue(argv: string[], index: number, option: string): [string, number] {
  const current = argv[index] ?? "";
  const equalsAt = current.indexOf("=");
  if (equalsAt !== -1) {
    return [current.slice(equalsAt + 1), index];
  }
  const value = argv[index + 1];
  if (value === undefined) {
    throw usageError(mapUsageLine(), "rolodexter map", `argument ${option}: expected one argument`);
  }
  return [value, index + 1];
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

function validateFormat(value: string, option: string): Format {
  if (["auto", "csv", "json", "jsonl"].includes(value)) {
    return value as Format;
  }
  throw usageError(mapUsageLine(), "rolodexter map", `argument ${option}: invalid choice: ${pyRepr(value)} (choose from auto, csv, json, jsonl)`);
}

function validateOnError(value: string): OnError {
  if (["fail", "skip", "quarantine"].includes(value)) {
    return value as OnError;
  }
  throw usageError(mapUsageLine(), "rolodexter map", `argument --on-error: invalid choice: ${pyRepr(value)} (choose from fail, skip, quarantine)`);
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
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i] ?? "";
    if (arg === "--") {
      positional.push(...argv.slice(i + 1));
      break;
    }
    const resolved = optionToken(arg, knownOptions, mapUsageLine(), "rolodexter map");
    const option = resolved?.option ?? arg;
    const inlineValue = resolved?.value;
    if (arg === "-o" || option === "--output") {
      const [value, next] = arg === "-o"
        ? takeResolvedValue(argv, i, "-o", undefined, mapUsageLine(), "rolodexter map")
        : takeResolvedValue(argv, i, "--output", inlineValue, mapUsageLine(), "rolodexter map");
      args.output = value;
      i = next;
    } else if (arg.startsWith("-o") && arg.length > 2 && !arg.startsWith("--")) {
      args.output = arg.slice(2);
    } else if (option === "--format") {
      const [value, next] = takeResolvedValue(argv, i, "--format", inlineValue, mapUsageLine(), "rolodexter map");
      args.format = validateFormat(value, "--format");
      i = next;
    } else if (option === "--in-format") {
      const [value, next] = takeResolvedValue(argv, i, "--in-format", inlineValue, mapUsageLine(), "rolodexter map");
      args.inFormat = validateFormat(value, "--in-format");
      i = next;
    } else if (option === "--region") {
      const [value, next] = takeResolvedValue(argv, i, "--region", inlineValue, mapUsageLine(), "rolodexter map");
      args.region = value;
      i = next;
    } else if (option === "--languages") {
      const [value, next] = takeResolvedValue(argv, i, "--languages", inlineValue, mapUsageLine(), "rolodexter map");
      args.languages = value;
      i = next;
    } else if (option === "--strict") {
      rejectExplicitFlagValue("--strict", inlineValue, mapUsageLine(), "rolodexter map");
      args.strict = true;
    } else if (option === "--min-confidence") {
      const [value, next] = takeResolvedValue(argv, i, "--min-confidence", inlineValue, mapUsageLine(), "rolodexter map");
      args.minConfidence = asFloat(value, "--min-confidence", mapUsageLine(), "rolodexter map");
      i = next;
    } else if (option === "--no-normalize") {
      rejectExplicitFlagValue("--no-normalize", inlineValue, mapUsageLine(), "rolodexter map");
      args.normalize = false;
    } else if (option === "--embedded-phones") {
      rejectExplicitFlagValue("--embedded-phones", inlineValue, mapUsageLine(), "rolodexter map");
      args.embeddedPhones = true;
    } else if (option === "--on-error") {
      const [value, next] = takeResolvedValue(argv, i, "--on-error", inlineValue, mapUsageLine(), "rolodexter map");
      args.onError = validateOnError(value);
      i = next;
    } else if (option === "--quarantine-output") {
      const [value, next] = takeResolvedValue(argv, i, "--quarantine-output", inlineValue, mapUsageLine(), "rolodexter map");
      args.quarantineOutput = value;
      i = next;
    } else if (option === "--max-materialized-rows") {
      const [value, next] = takeResolvedValue(argv, i, "--max-materialized-rows", inlineValue, mapUsageLine(), "rolodexter map");
      args.maxMaterializedRows = optionalLimit(asNonNegativeInt(value, "--max-materialized-rows", mapUsageLine(), "rolodexter map"));
      i = next;
    } else if (option === "--max-json-input-bytes") {
      const [value, next] = takeResolvedValue(argv, i, "--max-json-input-bytes", inlineValue, mapUsageLine(), "rolodexter map");
      args.maxJsonInputBytes = optionalLimit(asNonNegativeInt(value, "--max-json-input-bytes", mapUsageLine(), "rolodexter map"));
      i = next;
    } else if (option === "--help" || arg === "-h") {
      rejectExplicitFlagValue("--help", inlineValue, mapUsageLine(), "rolodexter map");
      throw new CliHelpError(mapUsage());
    } else if (arg.startsWith("-")) {
      if (/^-[^-]/.test(arg) && positional.length === 0) {
        unknownShortOptions.push(arg);
        continue;
      }
      throw usageError(mapUsageLine(), "rolodexter map", `unrecognized arguments: ${arg}`);
    } else {
      positional.push(arg);
    }
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
  const knownOptions = ["--value", "--region", "--languages", "--help"];
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

async function* readRows(path: string, format: Exclude<Format, "auto">, maxJsonBytes: number | null): AsyncGenerator<InputRow | RowFailure> {
  if (format === "csv") {
    const records = parsePythonCsv(readFileSync(path, "utf8").replace(/^\uFEFF/, ""));
    const headers = (records.shift() ?? []).map(String);
    let lineNumber = 1;
    for (const record of records) {
      lineNumber += csvRecordLineSpan(record);
      if (record.length === 1 && record[0] === "") {
        continue;
      }
      const data: Record<string, unknown> = {};
      for (const [index, header] of headers.entries()) {
        data[header] = index < record.length ? record[index] : null;
      }
      yield { kind: "row", rowNumber: lineNumber, data };
    }
    return;
  }

  if (format === "jsonl") {
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
    return;
  }

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

function formatRows(
  results: ReturnType<ContactMapper["map_payload"]>[],
  format: Exclude<Format, "auto">,
  maxRows: number | null,
  outputPath: string | undefined,
): string {
  const rows = results.map((result) => result.normalized);
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
  const temp = join(dirname(path), `.${basename(path)}.${process.pid}.tmp`);
  try {
    writeFileSync(temp, text, "utf8");
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

  const temp = join(dirname(path), `.${basename(path)}.${process.pid}.tmp`);
  const stream = createWriteStream(temp, { encoding: "utf8" });
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

async function handleFailure(
  failure: RowFailure,
  args: MapArgs,
  quarantine: RowFailure[],
  quarantineWriter: TextWriter | undefined,
): Promise<number> {
  if (args.onError === "fail") {
    throw new Error(`row ${failure.rowNumber}: ${failure.error}`);
  }
  if (args.onError === "quarantine") {
    logStderr(`warning: quarantined row ${failure.rowNumber}: ${failure.error}`);
    if (quarantineWriter) {
      await quarantineWriter.write(`${pythonCompactJson({
        row: failure.rowNumber,
        error: failure.error,
        raw: failure.raw,
      })}\n`);
    } else {
      quarantine.push(failure);
    }
  } else {
    logStderr(`warning: skipped row ${failure.rowNumber}: ${failure.error}`);
  }
  return 1;
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
  const mapper = new ContactMapper({
    default_region: args.region,
    languages: parseLanguages(args.languages),
    normalize: args.normalize,
    strict: args.strict,
    confidence_threshold: args.minConfidence,
  });
  const inputFormat = detectFormat(args.input, args.inFormat);
  const outputFormat = args.output ? detectFormat(args.output, args.format) : args.format === "auto" ? "json" : args.format;
  if (!existsSync(args.input)) {
    throw new Error(fileNotFoundMessage(args.input));
  }
  const items = readRows(args.input, inputFormat, args.maxJsonInputBytes);
  const results: ReturnType<ContactMapper["map_payload"]>[] = [];
  const quarantine: RowFailure[] = [];
  let failed = 0;
  let count = 0;
  const streamJsonl = outputFormat === "jsonl";
  const outputWriter = streamJsonl ? createTextWriter(args.output) : undefined;
  const quarantinePath = args.onError === "quarantine" ? defaultQuarantinePath(args) : undefined;
  const quarantineWriter = streamJsonl && quarantinePath ? createTextWriter(quarantinePath) : undefined;

  try {
    for await (const item of items) {
      if (item.kind === "failure") {
        failed += await handleFailure(item, args, quarantine, quarantineWriter);
        continue;
      }
      if (!streamJsonl && args.maxMaterializedRows !== null && results.length >= args.maxMaterializedRows) {
        throw new Error(`${outputFormat.toUpperCase()} output requires materializing more than ${args.maxMaterializedRows} row(s); use --format jsonl for streaming output or raise --max-materialized-rows`);
      }
      try {
        const result = mapper.map_payload(item.data, { extract_embedded_phones: args.embeddedPhones });
        if (streamJsonl) {
          await outputWriter?.write(`${pythonCompactJson(result.normalized)}\n`);
          count += 1;
        } else {
          results.push(result);
        }
      } catch (error) {
        failed += await handleFailure({
          kind: "failure",
          rowNumber: item.rowNumber,
          error: (error as Error).message,
          raw: item.data,
        }, args, quarantine, quarantineWriter);
      }
    }

    if (streamJsonl) {
      await closeTextWriter(outputWriter);
      await closeTextWriter(quarantineWriter);
    } else {
      const output = formatRows(results, outputFormat, args.maxMaterializedRows, args.output);
      writeAtomic(args.output, output);
      if (args.onError === "quarantine" && quarantinePath) {
        const quarantineText = quarantine.map((failure) => pythonCompactJson({
          row: failure.rowNumber,
          error: failure.error,
          raw: failure.raw,
        })).join("\n");
        writeAtomic(quarantinePath, quarantineText ? `${quarantineText}\n` : "");
      }
      count = results.length;
    }
  } catch (error) {
    await abortTextWriter(outputWriter);
    await abortTextWriter(quarantineWriter);
    throw error;
  }

  let message = `Mapped ${count} row(s) -> ${args.output || "stdout"} (${outputFormat})`;
  if (failed) {
    if (args.onError === "quarantine") {
      message += `; quarantined ${failed} row(s) -> ${quarantinePath}`;
    } else {
      message += `; skipped ${failed} row(s)`;
    }
  }
  logStderr(message);
  return 0;
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
  const mapper = new ContactMapper({
    default_region: args.region,
    languages: parseLanguages(args.languages),
  });
  const match = mapper.identify(args.header, { value: args.value });
  logStdout(`${inspect(args.header)} -> ${match.canonical} [${match.strategy}, conf=${match.confidence.toFixed(2)}]`);
  if (args.value !== undefined) {
    logStdout();
    logStdout(mapper.map_payload({ [args.header]: args.value }).explain());
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
  if (!command) {
    throw usageError(rootUsageLine(), "rolodexter", "the following arguments are required: command");
  }
  if (command === "map") {
    return commandMap(rest);
  }
  if (command === "explain") {
    return commandExplain(rest);
  }
  if (command === "fields") {
    return commandFields(rest);
  }
  throw usageError(rootUsageLine(), "rolodexter", `argument command: invalid choice: ${inspect(command)} (choose from map, explain, fields)`);
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
