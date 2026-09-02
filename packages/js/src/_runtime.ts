// Module-relative runtime handles (the ESM url and a CommonJS require).
// Extracted verbatim from index.ts, which re-exports every public name here.

import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";

const moduleUrl = typeof __filename !== "undefined" ? pathToFileURL(__filename).href : import.meta.url;
const require = createRequire(moduleUrl);

// True when the calling module's file is the script Node was started with,
// i.e. the package is running as a CLI rather than being imported. Both CLIs
// used to test this inline as `fileURLToPath(import.meta.url) === process.argv[1]`,
// which is right under ESM and fatal under the esbuild CommonJS bundles: there
// `import.meta` is an empty object, so `.url` is undefined and fileURLToPath
// threw ERR_INVALID_ARG_TYPE at require-time. `require("rolodexter/i18n")`
// crashed every real, file-invoked Node process, and only `node -e`, which
// has no argv[1], survived - which is why no test saw it.
//
// The caller passes its own `import.meta.url`: `import.meta` is per module,
// so reading it here would name this file, never the CLI. Under the CommonJS
// bundles the whole package is one file and that file is __filename, exactly
// as moduleUrl above already knows; there the caller's argument is undefined
// (esbuild's shim) and is not consulted.
function runningAsMain(callerModuleUrl: string | undefined): boolean {
  const entry = process.argv[1];
  if (!entry) {
    return false;
  }
  if (typeof __filename !== "undefined") {
    return __filename === entry;
  }
  return callerModuleUrl !== undefined && fileURLToPath(callerModuleUrl) === entry;
}


// File-private in index.ts; exported here only because the split put
// their callers in another module. Not part of the package's public API -
// ./public.ts and ./core.ts still decide that.
export { moduleUrl, require, runningAsMain };
