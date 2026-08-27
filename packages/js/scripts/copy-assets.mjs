import { copyFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

function findPackageRoot(from) {
  let current = from;
  while (current !== dirname(current)) {
    if (existsSync(resolve(current, "package.json"))) {
      return current;
    }
    current = dirname(current);
  }
  throw new Error("Could not find package.json");
}

const packageRoot = findPackageRoot(here);

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
