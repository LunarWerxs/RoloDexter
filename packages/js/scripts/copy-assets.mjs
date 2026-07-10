import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const packageRoot = resolve(here, "..");

const assets = [
  ["src/patterns.json", "dist/src/patterns.json"],
  ["src/patterns.json", "dist/cjs/patterns.json"],
  ["src/i18n/.gitkeep", "dist/src/i18n/.gitkeep"],
  ["src/i18n/.gitkeep", "dist/cjs/i18n/.gitkeep"],
];

for (const [from, to] of assets) {
  const target = resolve(packageRoot, to);
  mkdirSync(dirname(target), { recursive: true });
  copyFileSync(resolve(packageRoot, from), target);
}
