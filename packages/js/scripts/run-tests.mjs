// Run the compiled Node test suite across all supported Node versions.
//
// `node --test "dist/test/**/*.js"` only works on Node >= 21 (glob-pattern
// arguments landed in v21), and bare `node --test` auto-discovery also picks up
// the TypeScript *sources* on Node >= 22.6 (which can execute .ts directly),
// running them against paths that only exist after compilation. To stay
// compatible with the declared `engines.node` floor of 20, enumerate the
// compiled `dist/test/**/*.test.js` files ourselves and pass them explicitly.
import { spawnSync } from "node:child_process";
import { readdirSync } from "node:fs";
import { join } from "node:path";
import process from "node:process";

const TEST_DIR = "dist/test";

const files = readdirSync(TEST_DIR, { recursive: true })
  .map(String)
  .filter((entry) => entry.endsWith(".test.js"))
  .map((entry) => join(TEST_DIR, entry));

if (files.length === 0) {
  console.error(`No compiled test files found in ${TEST_DIR}. Run the build first.`);
  process.exit(1);
}

const result = spawnSync(process.execPath, ["--test", ...files], { stdio: "inherit" });
process.exit(result.status ?? 1);
