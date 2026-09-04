// Split out of the former monolithic mapper.test.ts (2572 lines, over the
// oversized-files gate of 2500). Same tests, grouped by topic. Shared
// CLI/version-probe helpers live in _mapper_test_helpers.ts.
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { CLI_EOL, runCli, runCliWithClosedStdout } from "./_mapper_test_helpers.js";

test("CLI fields and explain commands work", () => {
  const mapHelp = runCli(["map", "--help"]);
  assert.equal(mapHelp.status, 0, mapHelp.stderr);
  assert.match(mapHelp.stdout, /usage: rolodexter map/);
  assert.match(mapHelp.stdout, /--on-error \{fail,skip,quarantine\}/);

  const explainHelp = runCli(["explain", "--help"]);
  assert.equal(explainHelp.status, 0, explainHelp.stderr);
  assert.match(explainHelp.stdout, /usage: rolodexter explain/);

  const fieldsHelp = runCli(["fields", "--help"]);
  assert.equal(fieldsHelp.status, 0, fieldsHelp.stderr);
  assert.match(fieldsHelp.stdout, /usage: rolodexter fields/);

  const fields = runCli(["fields"]);
  assert.equal(fields.status, 0, fields.stderr);
  assert.match(fields.stdout, /first_name/);
  assert.match(fields.stdout, /phone/);

  const explain = runCli(["explain", "Job Titel", "--value", "CEO"]);
  assert.equal(explain.status, 0, explain.stderr);
  assert.match(explain.stdout, /job_title/);
  assert.match(explain.stdout, /fuzzy/);
});

test("CLI usage errors mirror Python argparse exits", () => {
  const root = runCli([]);
  assert.equal(root.status, 2);
  assert.equal(root.stdout, "");
  assert.equal(
    root.stderr,
    `usage: rolodexter [-h] [--version] {map,explain,profile,fields} ...${CLI_EOL}rolodexter: error: the following arguments are required: command${CLI_EOL}`,
  );

  const map = runCli(["map"]);
  assert.equal(map.status, 2);
  assert.equal(map.stdout, "");
  assert.match(map.stderr, /^usage: rolodexter map/);
  assert.match(map.stderr, /rolodexter map: error: the following arguments are required: input/);

  const dir = mkdtempSync(join(tmpdir(), "rolodexter-js-cli-"));
  try {
    const input = join(dir, "contacts.json");
    writeFileSync(input, "[]", "utf8");

    const abbreviated = runCli(["map", input, "--format", "json", "--min-conf", "0.5"]);
    assert.equal(abbreviated.status, 0, abbreviated.stderr);
    assert.equal(abbreviated.stdout, `[]${CLI_EOL}`);

    const signedLimit = runCli(["map", input, "--format", "json", "--max-materialized-rows", "+1", "--min-confidence", "+.5"]);
    assert.equal(signedLimit.status, 0, signedLimit.stderr);
    assert.equal(signedLimit.stdout, `[]${CLI_EOL}`);

    const negativeDotConfidence = runCli(["map", input, "--format", "json", "--min-confidence", "-.5"]);
    assert.equal(negativeDotConfidence.status, 1);
    assert.match(negativeDotConfidence.stderr, /confidence_threshold must be between 0\.0 and 1\.0/);

    const separator = runCli(["map", "--", input]);
    assert.equal(separator.status, 0, separator.stderr);
    assert.equal(separator.stdout, `[]${CLI_EOL}`);

    const badConfidence = runCli(["map", input, "--format", "json", "--min-confidence", "0.5abc"]);
    assert.equal(badConfidence.status, 2);
    assert.match(badConfidence.stderr, /argument --min-confidence: invalid float value/);

    const badRows = runCli(["map", input, "--format", "json", "--max-materialized-rows", "1.5"]);
    assert.equal(badRows.status, 2);
    assert.match(badRows.stderr, /argument --max-materialized-rows: invalid _non_negative_int value/);

    const negativeRows = runCli(["map", input, "--format", "json", "--max-materialized-rows", "-1"]);
    assert.equal(negativeRows.status, 2);
    assert.match(negativeRows.stderr, /argument --max-materialized-rows: must be non-negative/);

    const badFormat = runCli(["map", input, "--format", "xml"]);
    assert.equal(badFormat.status, 2);
    assert.match(badFormat.stderr, /argument --format: invalid choice/);

    const missingRegion = runCli(["map", input, "--region", "--strict", "--format", "json"]);
    assert.equal(missingRegion.status, 2);
    assert.match(missingRegion.stderr, /argument --region: expected one argument/);

    const missingFormatBeforeHelp = runCli(["map", input, "--format", "--help"]);
    assert.equal(missingFormatBeforeHelp.status, 2);
    assert.equal(missingFormatBeforeHelp.stdout, "");
    assert.match(missingFormatBeforeHelp.stderr, /argument --format: expected one argument/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("CLI maps CSV to JSONL", () => {
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-js-cli-"));
  try {
    const input = join(dir, "contacts.csv");
    writeFileSync(input, "fname,email,mobile\nJane,JANE@EXAMPLE.COM,(202) 555-0143\n", "utf8");

    const result = runCli(["map", input, "--format", "jsonl"]);
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stderr, /Mapped 1 row/);
    assert.equal(
      result.stdout,
      `{"first_name": "Jane", "email": "jane@example.com", "phone": "+12025550143"}${CLI_EOL}`,
    );
    assert.deepEqual(JSON.parse(result.stdout.trim()), {
      first_name: "Jane",
      email: "jane@example.com",
      phone: "+12025550143",
    });
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("CLI CSV parsing follows Python DictReader edge behavior", () => {
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-js-cli-"));
  try {
    const extra = join(dir, "extra.csv");
    writeFileSync(extra, "Name,Email\nAda,a@example.com,EXTRA\n", "utf8");
    const extraResult = runCli(["map", extra, "--format", "json"]);
    assert.equal(extraResult.status, 0, extraResult.stderr);
    assert.deepEqual(JSON.parse(extraResult.stdout), [
      { full_name: "Ada", email: "a@example.com" },
    ]);

    const badQuote = join(dir, "badquote.csv");
    writeFileSync(badQuote, 'Name,Email\n"Ada,a@example.com\n', "utf8");
    const badQuoteResult = runCli(["map", badQuote, "--format", "json"]);
    assert.equal(badQuoteResult.status, 0, badQuoteResult.stderr);
    assert.deepEqual(JSON.parse(badQuoteResult.stdout), [
      { full_name: "A@Example.com Ada", email: "" },
    ]);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("CLI JSONL output ignores materialization row limit", () => {
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-js-cli-"));
  try {
    const input = join(dir, "contacts.jsonl");
    writeFileSync(input, '{"fname":"A"}\n{"surname":"B"}', "utf8");

    const result = runCli(["map", input, "--format", "jsonl", "--max-materialized-rows", "1"]);
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.stdout, `{"first_name": "A"}${CLI_EOL}{"last_name": "B"}${CLI_EOL}`);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("CLI materialization limit is raised before later row failures", () => {
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-js-cli-"));
  try {
    const input = join(dir, "limit.jsonl");
    writeFileSync(input, '{"Name":"Ada"}\n{"Name":"Grace"}\nnot-json\n', "utf8");

    const result = runCli(["map", input, "--format", "json", "--max-materialized-rows", "1"]);
    assert.equal(result.status, 1);
    assert.match(result.stderr, /JSON output requires materializing more than 1 row\(s\)/);
    assert.doesNotMatch(result.stderr, /row 3: invalid JSON/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("CLI broken stdout mirrors Python broken pipe exit", { timeout: 20_000 }, async () => {
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-js-cli-"));
  try {
    const input = join(dir, "many.jsonl");
    const rows = Array.from({ length: 100_000 }, (_, index) => `{"fname":"Ada${index}"}`);
    writeFileSync(input, `${rows.join("\n")}\n`, "utf8");

    const result = await runCliWithClosedStdout(["map", input, "--in-format", "jsonl", "--format", "jsonl"]);

    assert.equal(result.status, 120);
    assert.equal(result.stdout, "{");
    if (process.platform === "win32") {
      assert.equal(
        result.stderr,
        `error: [Errno 22] Invalid argument${CLI_EOL}Exception ignored while flushing sys.stdout:${CLI_EOL}OSError: [Errno 22] Invalid argument${CLI_EOL}`,
      );
    } else {
      assert.equal(
        result.stderr,
        `error: [Errno 32] Broken pipe${CLI_EOL}Exception ignored while flushing sys.stdout:${CLI_EOL}BrokenPipeError: [Errno 32] Broken pipe${CLI_EOL}`,
      );
    }
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("CLI scalar JSON input maps as zero rows like Python", () => {
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-js-cli-"));
  try {
    const input = join(dir, "scalar.json");
    writeFileSync(input, "42", "utf8");

    const result = runCli(["map", input, "--in-format", "json", "--format", "json"]);
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.stdout, `[]${CLI_EOL}`);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("CLI can quarantine bad JSONL rows", () => {
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-js-cli-"));
  try {
    const input = join(dir, "contacts.jsonl");
    const output = join(dir, "out.jsonl");
    const quarantine = join(dir, "bad.jsonl");
    writeFileSync(input, '{"fname":"Jane"}\nnot json\n{"email":"A@EXAMPLE.COM"}\n', "utf8");

    const result = runCli([
      "map",
      input,
      "--in-format",
      "jsonl",
      "--format",
      "jsonl",
      "-o",
      output,
      "--on-error",
      "quarantine",
      "--quarantine-output",
      quarantine,
    ]);
    assert.equal(result.status, 2, result.stderr);
    assert.match(result.stderr, /warning: quarantined row 2: invalid JSON: Expecting value/);
    assert.match(result.stderr, /quarantined 1 row/);
    assert.equal(readFileSync(output, "utf8").trim().split(/\r?\n/).length, 2);
    const bad = JSON.parse(readFileSync(quarantine, "utf8").trim()) as { row: number; error: string };
    assert.equal(bad.row, 2);
    assert.equal(bad.error, "invalid JSON: Expecting value");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("CLI quarantine paths cannot overwrite input or mapped output", () => {
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-js-cli-"));
  try {
    const input = join(dir, "contacts.jsonl");
    const output = join(dir, "out.jsonl");
    const originalInput = '{"fname":"Jane"}\nnot json\n';
    writeFileSync(input, originalInput, "utf8");
    writeFileSync(output, "existing\n", "utf8");

    const inputCollision = runCli([
      "map",
      input,
      "--format",
      "jsonl",
      "--on-error",
      "quarantine",
      "--quarantine-output",
      input,
    ]);
    assert.equal(inputCollision.status, 1);
    assert.match(inputCollision.stderr, /quarantine output must differ from the input path/);
    assert.equal(readFileSync(input, "utf8"), originalInput);

    const outputCollision = runCli([
      "map",
      input,
      "-o",
      output,
      "--format",
      "jsonl",
      "--on-error",
      "quarantine",
      "--quarantine-output",
      output,
    ]);
    assert.equal(outputCollision.status, 1);
    assert.match(outputCollision.stderr, /quarantine output must differ from the mapped output path/);
    assert.equal(readFileSync(output, "utf8"), "existing\n");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

// A column literally named "__proto__" is data, not a prototype instruction.
// `obj[key] = value` treats it as the prototype setter: the value is dropped
// and the object's prototype is replaced with caller-supplied data. map_payload
// was hardened against that; compile_schema and everything built from it were
// not, so eight entry points silently lost the column here while Python kept
// it. Mirrors tests/test_proto_key_columns.py one-for-one.
//
// Every object below is built with JSON.parse or Object.fromEntries: an object
// literal `{ __proto__: "kept" }` sets the prototype instead of creating the
// key, so a literal would make the TEST the thing that loses the column.
