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

// `--coverage` turns on Node's built-in coverage. The per-metric thresholds
// only exist from Node 22, and the declared `engines.node` floor is 20, so
// they are added conditionally: on an older runtime coverage is still reported,
// just not enforced. CI runs the enforcing job on a current Node.
const wantCoverage = process.argv.includes("--coverage");
const nodeMajor = Number(process.versions.node.split(".")[0]);

const flags = ["--test"];
if (wantCoverage) {
  flags.unshift("--experimental-test-coverage");
  // dist/cjs is a bundled *duplicate* of the same sources, emitted for the
  // `require` entry point. Only a smoke test loads it, so counting it halves
  // the reported number while saying nothing about how well the code is
  // tested. dist/test is the test code itself.
  flags.unshift(
    "--test-coverage-exclude=dist/cjs/**",
    "--test-coverage-exclude=dist/test/**",
  );
  if (nodeMajor >= 22) {
    // A ratchet, not an aspiration: set just under today's real numbers so a
    // regression fails the build while an honest floor stays green. Raise it
    // as coverage improves.
    //
    // The number understates how well cli.ts is actually tested: both the CLI
    // tests and scripts/cli_parity_probe.py exercise it by spawning it as a
    // subprocess, which this instrumentation cannot see. Treat those probes,
    // not this percentage, as the real guarantee for CLI behavior.
    flags.unshift(
      "--test-coverage-lines=78",
      "--test-coverage-branches=76",
      "--test-coverage-functions=84",
    );
  } else {
    console.warn(
      `Node ${process.versions.node} cannot enforce coverage thresholds ` +
        "(needs >= 22); reporting only.",
    );
  }
}

const result = spawnSync(process.execPath, [...flags, ...files], { stdio: "inherit" });
process.exit(result.status ?? 1);
