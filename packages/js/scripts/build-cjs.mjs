import { build } from "esbuild";
import { rmSync } from "node:fs";

rmSync("dist/cjs", { recursive: true, force: true });

// generate_language() runs its network work in a helper Node process, which
// imports the module that exports generateLanguageAsync. Each bundle below is
// one file with an empty import.meta, so that module is built as a bundle of
// its own and every bundle is told its file name (see _i18n_generate.ts).
const GENERATOR_BUNDLE = "i18n_generate.cjs";

const shared = {
  bundle: true,
  define: {
    __ROLODEXTER_CJS_GENERATOR__: JSON.stringify(GENERATOR_BUNDLE),
  },
  format: "cjs",
  logOverride: {
    "empty-import-meta": "silent",
  },
  platform: "node",
  sourcemap: false,
  target: "node20",
};

await build({
  ...shared,
  entryPoints: ["src/public.ts"],
  outfile: "dist/cjs/index.cjs",
});

await build({
  ...shared,
  entryPoints: ["src/core.ts"],
  outfile: "dist/cjs/core.cjs",
});

await build({
  ...shared,
  entryPoints: ["src/i18n.ts"],
  outfile: "dist/cjs/i18n.cjs",
});

await build({
  ...shared,
  entryPoints: ["src/_i18n_generate.ts"],
  outfile: `dist/cjs/${GENERATOR_BUNDLE}`,
});
