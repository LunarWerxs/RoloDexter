import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

// The CommonJS bundles have to load from a REAL, file-invoked Node process.
//
// Until 2.12.0 both CLIs guarded their "am I the entrypoint?" check with
// `fileURLToPath(import.meta.url) === process.argv[1]`. Under ESM that is
// right. In the esbuild CJS bundles `import.meta` is an empty object, so the
// guard called fileURLToPath(undefined) and threw ERR_INVALID_ARG_TYPE at
// require-time: `require("rolodexter/i18n")` crashed every consumer whose
// process had a script path in argv[1], i.e. every consumer. The one shape
// that survived was `node -e`, which has no argv[1] and short-circuits the
// guard before the throw - and `node -e` was exactly how the existing test
// exercised the bundles. So these run a script FILE, the way an application
// does, and nothing here may switch to `node -e`.
const cjsDir = fileURLToPath(new URL("../cjs/", import.meta.url));
const bundle = (name: string): string => JSON.stringify(join(cjsDir, name));

function runScript(source: string): { status: number | null; stdout: string; stderr: string } {
  const dir = mkdtempSync(join(tmpdir(), "rolodexter-cjs-entry-"));
  try {
    const script = join(dir, "main.cjs");
    writeFileSync(script, source);
    const result = spawnSync(process.execPath, [script], { encoding: "utf8" });
    return { status: result.status, stdout: result.stdout, stderr: result.stderr };
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

test("every CJS bundle can be required from a file-invoked Node process", () => {
  const result = runScript(`
    const i18n = require(${bundle("i18n.cjs")});
    const core = require(${bundle("core.cjs")});
    const pkg = require(${bundle("index.cjs")});
    process.stdout.write(JSON.stringify({
      generate_language: typeof i18n.generate_language,
      load_cached: typeof i18n.load_cached,
      coreMapper: typeof core.ContactMapper,
      pkgMapper: typeof pkg.ContactMapper,
      name: pkg.NameNormalizer.normalize("DeAngelo"),
      first: new pkg.ContactMapper().map_payload({ fname: "Ada" }).normalized.first_name,
    }));
  `);
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), {
    generate_language: "function",
    load_cached: "function",
    coreMapper: "function",
    pkgMapper: "function",
    name: "DeAngelo",
    first: "Ada",
  });
});

test("requiring a CJS bundle does not run its CLI", () => {
  // If the entrypoint guard misfired under CommonJS, requiring i18n.cjs would
  // start the language CLI: it would parse the host script's argv, print
  // usage or a language list, and set the host's exit code.
  const result = runScript(`
    require(${bundle("i18n.cjs")});
    process.stdout.write("host-still-in-control");
  `);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout, "host-still-in-control");
});

test("the i18n CJS bundle still runs as a CLI when it IS the script", () => {
  // The same guard must fire when the bundle is the entrypoint. --list is an
  // offline command: it reads the cache directories and touches no network.
  const result = spawnSync(process.execPath, [join(cjsDir, "i18n.cjs"), "--list"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /\bes\b/);
});
