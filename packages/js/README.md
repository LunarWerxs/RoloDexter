# RoloDexter for JavaScript and TypeScript

This is the NPM package for RoloDexter, the universal contact field mapper.
In the GitHub repository it lives under `packages/js`; the Python/PyPI package
lives separately at the repository root under `src/rolodexter`.

The NPM package shares the Python package's `patterns.json` truth table and
targets the same high-value mapper surface:

- exact alias matching
- normalized header matching
- fuzzy typo recovery
- value-shape heuristics for email, phone, URL, postal code, social URL, and birth-hinted date fields
- value normalization for phones, emails, names, addresses, postal codes, booleans, and tags
- public phone helpers, normalizers, match strategies, and Python-shaped names
- `ContactMapper`, `map_payload`, `map_batch`, `map_stream`, `compile_schema`, and the `rolodexter` CLI

## Installation

After publication:

```bash
npm install rolodexter
```

For local development from the monorepo:

```bash
cd packages/js
npm install
npm test
```

Cached i18n alias packs can be loaded with `languages`; generation of new i18n
packs is available through `generate_language()`. Mapper
construction only loads cache files and never translates on the request path.
Generation uses optional translation/transliteration dependencies, so installs
with `--omit=optional` still support cache-only mapper/runtime use.

```ts
import { ContactMapper } from "rolodexter";

const result = new ContactMapper().map_payload({
  fname: "jane",
  surname: "doe",
  mobile: "(202) 555-0143",
  employer: "Tech Corp",
  Mystery: "jane@example.com",
});

console.log(result.normalized);
// {
//   first_name: "Jane",
//   last_name: "Doe",
//   phone: "+12025550143",
//   company: "Tech Corp",
//   email: "jane@example.com"
// }
```

## CLI

```bash
rolodexter map contacts.csv --format jsonl
rolodexter explain "Job Titel" --value CEO
rolodexter fields
```

## i18n

```ts
import { ContactMapper, generate_language } from "rolodexter";

generate_language("es");
const mapper = new ContactMapper({ languages: ["es"] });
```

## Package Boundary

`package.json` publishes only the JS package files listed in `files`, including
compiled ESM/CJS output, type declarations, CLI entry points, README, LICENSE,
and the synced `patterns.json`. It does not publish the Python source tree.

`npm run sync:patterns` copies `../../src/rolodexter/patterns.json` into this
package before every build so the NPM package does not maintain a drifting alias
table.
