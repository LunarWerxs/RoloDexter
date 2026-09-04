// Shared by the mapper.*.test.ts siblings split out of the former
// monolithic mapper.test.ts. Not itself a *.test.ts file, so the test
// runner (which globs dist/test/**/*.test.js) does not pick it up.
import { spawn, spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// Read from package.json rather than pinned, so a version bump cannot leave
// the assertion agreeing with a stale literal in the source (which is exactly
// how 2.10.0 shipped inside the 2.11.0 package). Tests execute compiled from
// dist/test/, so the package root is two levels up, not one.
export const VERSION_FROM_PACKAGE_JSON = (
  JSON.parse(
    readFileSync(new URL("../../package.json", import.meta.url), "utf8"),
  ) as { version: string }
).version;
export const CLI_EOL = process.platform === "win32" ? "\r\n" : "\n";

export function cliPath(): string {
  return fileURLToPath(new URL("../src/cli.js", import.meta.url));
}

export function i18nCliPath(): string {
  return fileURLToPath(new URL("../src/i18n.js", import.meta.url));
}

export function runCli(args: string[], cwd?: string) {
  return spawnSync(process.execPath, [cliPath(), ...args], {
    cwd,
    encoding: "utf8",
  });
}

export function runI18nCli(args: string[], cwd?: string) {
  return spawnSync(process.execPath, [i18nCliPath(), ...args], {
    cwd,
    encoding: "utf8",
  });
}

export async function runCliWithClosedStdout(args: string[], cwd?: string) {
  const child = spawn(process.execPath, [cliPath(), ...args], {
    cwd,
    stdio: ["ignore", "pipe", "pipe"],
  });
  const stdoutChunks: Buffer[] = [];
  const stderrChunks: Buffer[] = [];
  let closedStdout = false;

  child.stdout.on("data", (chunk: Buffer) => {
    if (!closedStdout) {
      closedStdout = true;
      stdoutChunks.push(Buffer.from(chunk.subarray(0, 1)));
      child.stdout.destroy();
    }
  });
  child.stderr.on("data", (chunk: Buffer) => {
    stderrChunks.push(Buffer.from(chunk));
  });

  const status = await new Promise<number | null>((resolve, reject) => {
    const timer = setTimeout(() => {
      child.kill();
      reject(new Error("timed out waiting for CLI closed-stdout probe"));
    }, 15_000);
    child.once("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.once("close", (code) => {
      clearTimeout(timer);
      resolve(code);
    });
  });

  return {
    status,
    stdout: Buffer.concat(stdoutChunks).toString("utf8"),
    stderr: Buffer.concat(stderrChunks).toString("utf8"),
  };
}

export function packageRoot(): string {
  return fileURLToPath(new URL("../..", import.meta.url));
}
