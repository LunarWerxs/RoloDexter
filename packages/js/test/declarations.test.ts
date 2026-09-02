import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

// The shipped .d.ts files must type-check on their own, with skipLibCheck at
// TypeScript's default of false.
//
// `tsc -p tsconfig.json` type-checks the SOURCES, and this package's own
// tsconfig sets skipLibCheck: true, so neither ever looked at the emitted
// declarations. `stripInternal` removes every internally-tagged declaration from
// them - and a re-export line, or an interface member, that still names a
// stripped declaration is left behind as a dangling reference. That is what
// the 2.12.0 module split produced: index.d.ts re-exported internal i18n
// helpers and translator types from the modules that had just stripped them,
// _models.d.ts kept two interfaces whose members named the stripped types,
// and `import { ContactMapper } from "rolodexter"` failed every consumer's
// build with eleven errors inside node_modules. 2.11.1 type-checked clean.
//
// This runs tsc over the four entry-point declarations as a consumer would
// see them. The tsconfig is written into dist/ so `types: ["node"]` resolves
// against this package's node_modules.
const packageDir = fileURLToPath(new URL("../../", import.meta.url));
const distDir = join(packageDir, "dist");
const entryPoints = ["public", "core", "i18n", "index"].map((name) => `./src/${name}.d.ts`);

test("the emitted declarations type-check with skipLibCheck off", () => {
  const checkDir = join(distDir, ".declcheck");
  mkdirSync(checkDir, { recursive: true });
  const tsconfig = join(checkDir, "tsconfig.json");
  writeFileSync(
    tsconfig,
    JSON.stringify(
      {
        compilerOptions: {
          module: "NodeNext",
          moduleResolution: "NodeNext",
          target: "ES2022",
          strict: true,
          noEmit: true,
          skipLibCheck: false,
          types: ["node"],
        },
        files: entryPoints.map((entry) => join("..", entry)),
      },
      null,
      2,
    ),
  );
  const tsc = join(packageDir, "node_modules", "typescript", "bin", "tsc");
  const result = spawnSync(process.execPath, [tsc, "-p", tsconfig], { cwd: packageDir, encoding: "utf8" });
  assert.equal(result.status, 0, `${result.stdout}${result.stderr}`);
});

test("no shipped declaration names a stripped @internal declaration", () => {
  // The camelCase i18n helpers and the translator function types are
  // tagged internal in their own modules, so they must not appear in any
  // entry-point declaration, where they would be a dangling re-export.
  const stripped = [
    "discoverCachedLanguages",
    "loadCachedLanguage",
    "getAllCacheDirs",
    "getWritableCacheDir",
    "generateLanguageAsync",
    "TranslateFunction",
    "InternalGenerateLanguageOptions",
    "GenerateLanguageAsyncOptions",
  ];
  for (const entry of entryPoints) {
    const text = readFileSync(join(distDir, entry), "utf8");
    for (const name of stripped) {
      assert.doesNotMatch(text, new RegExp(`\\b${name}\\b`), `${entry} still names ${name}`);
    }
  }
});
