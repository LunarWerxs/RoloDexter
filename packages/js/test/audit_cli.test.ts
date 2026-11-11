// CLI fixes from the 2026-11 audit (H3, M4, M5, M6, L1-L3, L8-L11). Each
// test names its finding id. The Python twin lives in tests/test_audit_cli.py;
// scripts/cli_parity_probe.py checks both CLIs print the same bytes.
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { main } from "../src/cli.js";
import { ContactMapper } from "../src/index.js";
import { runCli } from "./_mapper_test_helpers.js";

function withDir(run: (dir: string) => void | Promise<void>): () => Promise<void> {
  return async () => {
    const dir = mkdtempSync(join(tmpdir(), "rolodexter-js-audit-cli-"));
    try {
      await run(dir);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  };
}

function readJsonl(path: string): Record<string, unknown>[] {
  return readFileSync(path, "utf8").split("\n").filter(Boolean).map((line) => JSON.parse(line) as Record<string, unknown>);
}

// ── H3: --duplicates-output ───────────────────────────────────────────

test("H3: --duplicates-output records each dropped row", withDir((dir) => {
  const input = join(dir, "in.csv");
  writeFileSync(input, "Name,Email\nAda,ada@example.com\nGrace,grace@example.com\nAda L,ada@example.com\n", "utf8");
  const output = join(dir, "out.json");
  const dups = join(dir, "dups.jsonl");

  const result = runCli(["map", input, "-o", output, "--dedupe", "--duplicates-output", dups]);

  assert.equal(result.status, 0, result.stderr);
  assert.equal((JSON.parse(readFileSync(output, "utf8")) as unknown[]).length, 2);
  const records = readJsonl(dups);
  assert.equal(records.length, 1);
  assert.deepEqual(Object.keys(records[0] ?? {}), ["row", "error", "raw", "key", "first_row"]);
  assert.deepEqual(records[0], {
    row: 4,
    error: "duplicate of row 2",
    raw: { Name: "Ada L", Email: "ada@example.com" },
    key: "email:ada@example.com",
    first_row: 2,
  });
  assert.ok(result.stderr.includes(`dropped 1 duplicate row(s) -> ${dups}`), result.stderr);
}));

test("H3: --duplicates-output is not created without duplicates and requires --dedupe", withDir((dir) => {
  const input = join(dir, "in.csv");
  writeFileSync(input, "Email\na@example.com\nb@example.com\n", "utf8");
  const dups = join(dir, "dups.jsonl");

  const clean = runCli(["map", input, "-o", join(dir, "out.json"), "--dedupe", "--duplicates-output", dups]);
  assert.equal(clean.status, 0, clean.stderr);
  assert.equal(existsSync(dups), false);

  const missing = runCli(["map", input, "--duplicates-output", dups]);
  assert.equal(missing.status, 1);
  assert.match(missing.stderr, /^error: --duplicates-output requires --dedupe/);
}));

// ── M4: booleans in CSV output ────────────────────────────────────────

test("M4: CSV output writes booleans as True/False like Python's csv module", withDir((dir) => {
  const input = join(dir, "in.json");
  writeFileSync(input, JSON.stringify([
    { Email: "a@example.com", email_opt_out: "no" },
    { Email: "b@example.com", email_opt_out: "yes" },
  ]), "utf8");
  const output = join(dir, "out.csv");

  const result = runCli(["map", input, "-o", output]);

  assert.equal(result.status, 0, result.stderr);
  assert.equal(readFileSync(output, "utf8"), "email,email_opt_out\r\na@example.com,False\r\nb@example.com,True\r\n");
}));

// ── M5: --encoding and --delimiter ────────────────────────────────────

test("M5: cp1252 input decodes with --encoding", withDir((dir) => {
  const input = join(dir, "in.csv");
  writeFileSync(input, Buffer.from("First Name,Email\nJos\xe9,jose@example.com\n", "latin1"));

  const result = runCli(["map", input, "--format", "json", "--encoding", "Windows-1252"]);

  assert.equal(result.status, 0, result.stderr);
  assert.equal((JSON.parse(result.stdout) as Record<string, unknown>[])[0]?.first_name, "José");
}));

test("M5: undecodable input fails naming --encoding, never with replacement characters", withDir((dir) => {
  const input = join(dir, "in.csv");
  writeFileSync(input, Buffer.from("First Name\nJos\xe9\n", "latin1"));

  const result = runCli(["map", input, "--format", "json"]);

  assert.equal(result.status, 1);
  assert.equal(result.stdout, "");
  assert.ok(!result.stdout.includes("�"));
  assert.equal(
    result.stderr.trimEnd(),
    `error: cannot decode ${input} as utf-8 text; pass --encoding with the file's real encoding (e.g. --encoding cp1252)`,
  );

  const undefinedByte = join(dir, "undefined.csv");
  writeFileSync(undefinedByte, Buffer.from([...Buffer.from("Name\nA"), 0x81, 0x0a]));
  const cp1252 = runCli(["map", undefinedByte, "--format", "json", "--encoding", "cp1252"]);
  assert.equal(cp1252.status, 1);
  assert.match(cp1252.stderr, /cannot decode/);
}));

test("M5: utf-16 and latin-1 inputs decode", withDir((dir) => {
  const utf16 = join(dir, "utf16.csv");
  writeFileSync(utf16, Buffer.concat([Buffer.from([0xff, 0xfe]), Buffer.from("Name,Email\nZoë,z@example.com\n", "utf16le")]));
  const latin1 = join(dir, "latin1.csv");
  writeFileSync(latin1, Buffer.from("Name,Email\nZoë,z@example.com\n", "latin1"));
  for (const [path, flag] of [[utf16, "utf-16"], [latin1, "ISO-8859-1"]] as const) {
    const result = runCli(["map", path, "--format", "json", "--encoding", flag]);
    assert.equal(result.status, 0, result.stderr);
    assert.equal((JSON.parse(result.stdout) as Record<string, unknown>[])[0]?.full_name, "Zoë");
  }
}));

test("M5: unknown --encoding is a usage error", () => {
  const result = runCli(["map", "x.csv", "--encoding", "ebcdic"]);
  assert.equal(result.status, 2);
  assert.ok(result.stderr.includes(
    "rolodexter map: error: argument --encoding: unsupported encoding 'ebcdic' (choose from utf-8, utf-8-sig, utf-16, latin-1, iso-8859-1, cp1252, windows-1252)",
  ), result.stderr);

  const delimiter = runCli(["profile", "x.csv", "--delimiter", "ab"]);
  assert.equal(delimiter.status, 2);
  assert.ok(delimiter.stderr.includes("argument --delimiter: expected one character or 'tab', got 'ab'"), delimiter.stderr);
});

test("M5: JSON input tolerates a UTF-8 byte-order mark", withDir((dir) => {
  const input = join(dir, "in.json");
  writeFileSync(input, Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), Buffer.from('[{"Email": "a@example.com"}]')]));
  const result = runCli(["map", input, "--format", "json"]);
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), [{ email: "a@example.com" }]);
}));

test("M5: the delimiter is sniffed from the header line, or given", withDir((dir) => {
  const cases: [string, string, string[]][] = [
    ["semi.csv", 'Name;Email;"a,b,c"\nAda;a@example.com;x\n', []],
    // two tabs and two commas tie (sniff says comma); .tsv means tab
    ["tabs.tsv", "Name\tEmail\tA,B,C\nAda\ta@example.com\tq\n", []],
    ["tabs.txt", "Name\tEmail\nAda\ta@example.com\n", ["--in-format", "csv"]],
    // two pipes and two semicolons tie; the flag decides
    ["pipe.csv", "Name;Email;a|b|c\nAda;a@example.com;q\n", ["--delimiter", ";"]],
    // a tie falls back to comma
    ["tie.csv", "Name;x,Email\nAda;y,a@example.com\n", []],
  ];
  for (const [name, text, extra] of cases) {
    const input = join(dir, name);
    writeFileSync(input, text, "utf8");
    const result = runCli(["map", input, "--format", "json", ...extra]);
    assert.equal(result.status, 0, `${name}: ${result.stderr}`);
    const row = (JSON.parse(result.stdout) as Record<string, unknown>[])[0];
    assert.equal(row?.email, "a@example.com", name);
  }
}));

// ── M6: CSV on stdout ─────────────────────────────────────────────────

test("M6: CSV to stdout ends records with a single \\r\\n on every platform", withDir((dir) => {
  const input = join(dir, "in.json");
  writeFileSync(input, '[{"Email": "a@example.com"}, {"Email": "b@example.com"}]', "utf8");
  const result = runCli(["map", input, "--format", "csv"]);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout, "email\r\na@example.com\r\nb@example.com\r\n");
}));

// ── L1 / L2 / L3 ──────────────────────────────────────────────────────

test("L1: profile honours --max-json-input-bytes", withDir((dir) => {
  const input = join(dir, "in.json");
  writeFileSync(input, '[{"Email": "a@example.com"}]', "utf8");
  const result = runCli(["profile", input, "--max-json-input-bytes", "5"]);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /above the 5 byte materialization limit/);
}));

test("L2: blank CSV lines are skipped, including a bare \\r\\n", withDir((dir) => {
  const input = join(dir, "in.csv");
  writeFileSync(input, "Name,Email\n\nAda,a@example.com\n\r\n", "utf8");
  const result = runCli(["map", input, "--format", "json"]);
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), [{ full_name: "Ada", email: "a@example.com" }]);
}));

test("L3: surplus CSV cells are counted in the summary", withDir((dir) => {
  const input = join(dir, "in.csv");
  writeFileSync(input, "Name,Email\nAda,a@example.com,X,Y\nGrace,g@example.com,Z\n", "utf8");
  const result = runCli(["map", input, "-o", join(dir, "out.json")]);
  assert.equal(result.status, 0, result.stderr);
  assert.ok(result.stderr.includes(`warning: 3 extra cell(s) in 2 row(s) of ${input} had no header column and were dropped`), result.stderr);
}));

// ── L8: --csv-safe ────────────────────────────────────────────────────

test("L8: --csv-safe quotes formula cells; without it CSV is unchanged", withDir((dir) => {
  const input = join(dir, "in.json");
  writeFileSync(input, JSON.stringify([{ Company: "=HYPERLINK(1)", Notes: "@cmd", Title: "ok" }]), "utf8");
  const safe = join(dir, "safe.csv");
  const plain = join(dir, "plain.csv");

  assert.equal(runCli(["map", input, "-o", safe, "--csv-safe"]).status, 0);
  assert.equal(readFileSync(safe, "utf8"), "company,notes,job_title\r\n'=HYPERLINK(1),'@cmd,ok\r\n");
  assert.equal(runCli(["map", input, "-o", plain]).status, 0);
  assert.equal(readFileSync(plain, "utf8"), "company,notes,job_title\r\n=HYPERLINK(1),@cmd,ok\r\n");
}));

// ── L9: unexpected errors stop the run ────────────────────────────────

test("L9: a non-mapping error is not swallowed by --on-error skip", withDir(async (dir) => {
  const input = join(dir, "in.csv");
  writeFileSync(input, "Email\na@example.com\n", "utf8");
  const original = ContactMapper.prototype.map_payload;
  ContactMapper.prototype.map_payload = function boom(): never {
    throw new TypeError("boom");
  };
  try {
    await assert.rejects(main(["map", input, "--on-error", "skip", "--format", "json"]), TypeError);
  } finally {
    ContactMapper.prototype.map_payload = original;
  }
}));

// ── L10 / L11 ─────────────────────────────────────────────────────────

test("L10: --keep-unmapped keeps a column named __proto__", withDir((dir) => {
  const input = join(dir, "in.json");
  writeFileSync(input, '[{"__proto__": "kept", "Email": "a@example.com"}]', "utf8");
  const result = runCli(["map", input, "--format", "jsonl", "--keep-unmapped"]);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /"__proto__": "kept"/);
}));

test("L11: --schema-out records every row's headers without re-reading the input", withDir((dir) => {
  const input = join(dir, "in.jsonl");
  writeFileSync(input, '{"fname": "A"}\n{"surname": "B"}\n', "utf8");
  const schema = join(dir, "plan.json");
  const result = runCli(["map", input, "--format", "jsonl", "--schema-out", schema]);
  assert.equal(result.status, 0, result.stderr);
  const plan = readFileSync(schema, "utf8");
  assert.match(plan, /"fname"/);
  assert.match(plan, /"surname"/);
}));
