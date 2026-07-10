import { build } from "esbuild";
import { rmSync } from "node:fs";

rmSync("dist/cjs", { recursive: true, force: true });

const shared = {
  bundle: true,
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
