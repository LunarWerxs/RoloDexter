import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const packageRoot = resolve(here, "..");
const repoRoot = resolve(packageRoot, "..", "..");
const source = resolve(repoRoot, "src", "rolodexter", "patterns.json");
const target = resolve(packageRoot, "src", "patterns.json");

mkdirSync(dirname(target), { recursive: true });
copyFileSync(source, target);
