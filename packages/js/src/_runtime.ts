// Module-relative runtime handles (the ESM url and a CommonJS require).
// Extracted verbatim from index.ts, which re-exports every public name here.

import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const moduleUrl = typeof __filename !== "undefined" ? pathToFileURL(__filename).href : import.meta.url;
const require = createRequire(moduleUrl);


// File-private in index.ts; exported here only because the split put
// their callers in another module. Not part of the package's public API -
// ./public.ts and ./core.ts still decide that.
export { moduleUrl, require };
