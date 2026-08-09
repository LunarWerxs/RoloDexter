import { copyFileSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import process from "node:process";

const here = dirname(fileURLToPath(import.meta.url));
const packageRoot = resolve(here, "..");
const repoRoot = resolve(packageRoot, "..", "..");
const source = resolve(repoRoot, "src", "rolodexter", "patterns.json");
const target = resolve(packageRoot, "src", "patterns.json");

const checkOnly = process.argv.includes("--check");

if (checkOnly) {
  const sourceContents = readFileSync(source);
  let targetContents;
  try {
    targetContents = readFileSync(target);
  } catch {
    targetContents = null;
  }

  if (targetContents === null || !sourceContents.equals(targetContents)) {
    console.error(
      `patterns.json is out of sync:\n` +
        `  source: ${relative(repoRoot, source)}\n` +
        `  target: ${relative(repoRoot, target)}\n` +
        `Run "npm run sync:patterns" to update it.`,
    );
    process.exit(1);
  }

  console.log("patterns.json is in sync.");
  process.exit(0);
}

mkdirSync(dirname(target), { recursive: true });
copyFileSync(source, target);
