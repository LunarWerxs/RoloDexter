// The shared data tables (tables.json) load in both builds. The ESM build reads
// the copy beside its own module (dist/src/tables.json); the CommonJS bundles
// read the copy in dist/cjs, so one of each is loaded from a real Node process.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { TABLES } from "../src/_tables.js";
import { VERSION_FROM_PACKAGE_JSON } from "./_mapper_test_helpers.js";

const srcDir = fileURLToPath(new URL("../src/", import.meta.url));
const cjsDir = fileURLToPath(new URL("../cjs/", import.meta.url));

test("ESM build loads tables.json and its version matches the package", () => {
  assert.ok(existsSync(join(srcDir, "tables.json")), "dist/src/tables.json is missing");
  const onDisk = JSON.parse(readFileSync(join(srcDir, "tables.json"), "utf8")) as { version: string };
  assert.equal(onDisk.version, VERSION_FROM_PACKAGE_JSON);
  assert.equal(TABLES.version, VERSION_FROM_PACKAGE_JSON);
  assert.deepEqual(TABLES.languages.es, ["es", "Spanish"]);
});

test("CommonJS bundles load tables.json from dist/cjs in a real Node process", () => {
  assert.ok(existsSync(join(cjsDir, "tables.json")), "dist/cjs/tables.json is missing");
  const script = `const pkg = require(${JSON.stringify(join(cjsDir, "index.cjs"))});
process.stdout.write(String(pkg.__version__));`;
  const result = spawnSync(process.execPath, ["-e", script], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout, VERSION_FROM_PACKAGE_JSON);
});
