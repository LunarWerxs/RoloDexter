# Release And Distribution Notes

Last checked: 2026-07-18.

## Current Package Status

- PyPI project: <https://pypi.org/project/rolodexter/> — latest published `2.9.1`.
- NPM package: <https://www.npmjs.com/package/rolodexter> — latest published
  `2.9.1`, published from `packages/js` with Sigstore provenance.
- Local versions in `pyproject.toml` and `packages/js/package.json`: `2.9.1`.
- Python requirement: `>=3.10`; Node requirement: `>=20`.

Both registries are back in step at `2.9.1`. They were not between 2026-07-10
and 2026-07-18; see "The 2.9.1 npm gap" below for the cause and the fix.

npm `2.9.1` was published from `main` rather than from the `v2.9.1` tag,
because the tag predates the owner move and still carries the old
`Lunarwerx` URLs that `--provenance` would reject. Its provenance therefore
records the `main` commit, not the tag. The tag is left where it is: it is the
commit PyPI `2.9.1` was built from, and moving it would misstate that.

### Repository owner moved (2026-07-18)

The repository moved from the `Lunarwerx` **organization** to the `LunarWerxs`
**user** account, which is where every other public LunarWerx product repo
lives. Consequences:

- `NPM_TOKEN` is an **environment** secret on the `npm` environment, so it is
  repo-scoped and survived the move.
- `--provenance` validates the `repository.url` in `packages/js/package.json`
  against the repo it is built from. That URL, and the URLs in `pyproject.toml`,
  `README.md`, `packages/js/README.md`, and `SECURITY.md`, were rewritten to
  `LunarWerxs/RoloDexter`. **Do not publish with a stale owner in that field.**
- PyPI uses **trusted publishing**, which is pinned on PyPI's side to a specific
  `owner/repo`. The move invalidates it, so the PyPI publisher must be
  re-pointed at `LunarWerxs/RoloDexter` before the next Python release.

### 2.9.0 release (2026-07-08)

2.9.0 (minor) shipped the first-class TypeScript/NPM package plus Python fixes.
PyPI published automatically from the `v2.9.0` GitHub Release (trusted
publishing); NPM published via the manual `Publish to NPM` workflow
(`dry_run=false`) using an `NPM_TOKEN` in the `npm` environment. CI installing
fresh dependencies caught four cross-environment issues that a stale local
environment had hidden, now fixed: `nameparser` 1.3.0 leading-particle
capitalization, `tomllib` on Python 3.10 (`tomli` fallback), `node --test` glob
support on Node 20 (`packages/js/scripts/run-tests.mjs`), and CPython
version-dependent `argparse` text in the CLI parity probe. The first NPM publish
also required correcting the stale `lunawerx` GitHub org name to `Lunarwerx` so
`--provenance` validation passed.

## Release Policy

After a meaningful maintenance stint or behavior change, do not leave the repository in a "changed but unreleased" state indefinitely.

Before publishing a new version:

1. Run the full local quality gate:

   ```powershell
   $env:PYTHONPATH='src'; python -m ruff check src tests
   $env:PYTHONPATH='src'; python -m pytest -q
   ```

2. Confirm package metadata and docs are current:

   - `pyproject.toml` version
   - `CHANGELOG.md`
   - README examples and feature wording
   - Any generated/cache behavior notes

3. Bump the version using semver intent:

   - Patch: bug fixes and internal maintenance with compatible behavior
   - Minor: new public features or meaningful API additions
   - Major: breaking API or behavior changes

4. Build and inspect the package before publishing:

   ```powershell
   python -m build
   python -m twine check dist/*
   ```

5. Publish only after lint, tests, build, and metadata checks pass.

For the JavaScript/TypeScript package:

```powershell
cd packages/js
npm ci
npm run typecheck
npm test
npm run test:parity
npm pack --dry-run
npm publish --dry-run
npm audit --omit=dev
```

Latest local release verification on 2026-06-30:

- Python gates: `ruff check src tests`, `ruff format --check src tests`, `mypy src`, and `$env:PYTHONPATH='src'; pytest --cov=rolodexter --cov-report=xml --cov-report=term-missing` passed. Pytest result: 905 passed, 93.93% total coverage.
- Python artifacts: `py -3 -m build --outdir .tmp\dist-check` built the `2.8.1`
  sdist and wheel, and `py -3 -m twine check .tmp\dist-check\*` passed for both.
- `npm run typecheck`: passed.
- `npm test`: 56 passed.
- `npm run test:parity`: release versions match `2.8.1`; expanded mapper/API and CLI parity probes reported zero mismatches.
- `npm pack --dry-run --json`: passed for `rolodexter@2.8.1`; packed size 407.1 kB, unpacked size 1.9 MB, 24 files. Tarball includes ESM/CJS library files, both CLIs, `patterns.json`, README, LICENSE, declaration files, and package metadata; `cli.d.ts` is not packed. The package `prepack` lifecycle runs both `npm test` and `npm run test:parity`, so local pack/publish commands cannot skip parity accidentally.
- Fresh throwaway install from the packed tarball: ESM import, CommonJS require, `ContactMapper.map_payload()`, Python-shaped root/core/i18n exports, i18n `load_cached()`/`generate_language()` parity edges, `npx rolodexter fields`, and `npx rolodexter-i18n --list` worked. A cache-only install with `--omit=optional` also worked, proving mapper construction and both CLIs do not require generation-only translation/transliteration packages.
- `npm publish --dry-run`: passed for `rolodexter@2.8.1` with the CLI `bin` metadata accepted as-is.
- `npm audit --json`: 0 vulnerabilities; audit metadata reports 7 production dependencies and 39 optional dependencies after generation-only translation/transliteration packages moved to `optionalDependencies`.
- Current release parity note: package root, `rolodexter/core`, and `rolodexter/i18n` exports are Python-shaped; packed declarations no longer advertise the previously audited camelCase helper/option aliases; installed public class instances no longer expose the previously audited JS-only camelCase prototype methods; mapper/schema/DataFrame warning messages are silent by default and observable through a package-specific Node process event when hosts opt in; importing `rolodexter/i18n` has no global stdout listener side effect; closed-stdout CLI behavior now matches the audited Python broken-pipe diagnostic/exit shape; manually constructed phone formatting, phone helper edge cases, normalizer runtime edge cases, `FieldMatch.service`, registry/schema/i18n missing-value semantics, mapper argument/shape errors, `MappingSchema.apply()` errors, public i18n helper arity/keyword-equivalent options, Python JSON constants, CSV file bytes, clean quarantine side effects, `-.5` CLI value validation, and model/strategy constructor arity errors are covered by the tracked parity probes; and tracked mapper/API plus CLI parity probes report zero mismatches. Ongoing parity probe expansion is tracked internally.

## NPM Package Possibility

Yes, RoloDexter can also become an NPM package, but the best path depends on the intended JavaScript audience.

Recommended approach:

- Create a real TypeScript package that mirrors the Python core behavior and ships types.
- Keep the canonical alias/pattern data in a shared JSON source so Python and NPM packages do not drift.
- Keep cross-language golden tests pointed at `tests/fixtures/golden_corpora.json`
  so Python and TypeScript exercise the same fixture corpus.
- Publish Python to PyPI and JavaScript/TypeScript to NPM with matching version numbers when behavior is equivalent.

Other options:

- A thin NPM CLI wrapper around Python is faster to create, but it is less useful for browser/serverless users and requires Python at runtime.
- A generated/WASM approach is possible, but probably too heavy for this package right now.

The NPM package lives under `packages/js`. It syncs
`src/rolodexter/patterns.json` before build so Python remains the canonical
alias source in this repository. The local package now uses the same `2.9.0`
version as the Python release candidate, but publishing should still wait for
CI, credentials/trusted publishing, and explicit release approval.

The CI workflow tests the JavaScript package on Node 20 and Node 24 so the
declared `>=20` engine floor is covered before release.

### The 2.9.1 npm gap

`2.9.1` shipped to PyPI and GitHub on 2026-07-10 but sat unpublished on npm
until 2026-07-18. The cause was structural, not a decision:

- `publish.yml` (PyPI) triggers on `release: [published]`, so cutting the
  GitHub Release published Python automatically.
- `npm-publish.yml` triggered on `workflow_dispatch` **only**, and defaulted to
  `dry_run: true`. Nothing dispatched it, so npm silently stayed at `2.9.0`.

Because the two halves were triggered differently, npm was guaranteed to fall
behind on every release where someone forgot the manual dispatch. `2.9.0` only
made it because it was dispatched by hand the day it was cut.

`npm-publish.yml` now also triggers on `release: [published]`, matching
`publish.yml`, so both registries publish from the same event. The publish step
is gated on `github.event_name == 'release' || !inputs.dry_run`, which keeps the
manual dry run as the default for hand-dispatched runs while letting a real
release publish for real. `workflow_dispatch` is retained for re-runs and
dry-run pack checks.

## JS Runtime Dependency Weight

Measured 2026-07-18 against the published `rolodexter@2.9.0` with a clean
`npm i rolodexter --omit=optional`: **19 MB across 7 packages**.

| Package | On disk | Direct? |
| --- | --- | --- |
| `libphonenumber-js` | 12 MB | yes |
| `lodash` | 3.3 MB | no, transitive via `fuzzball` |
| `rolodexter` | 1.9 MB | n/a |
| `csv-stringify` | 970 KB | yes |
| `fuzzball` | 492 KB | yes |
| `heap`, `setimmediate` | 64 KB | no, transitive via `fuzzball` |

Two things are worth knowing before anyone touches this list.

**`fuzzball` really costs about 3.85 MB, not 492 KB.** It depends on
`lodash`, `heap`, and `setimmediate`. Worse, the CJS builds already inline it:
`dist/cjs/index.cjs` contains no `require("fuzzball")` at all, since esbuild
bundles fuzzball and its lodash tree straight into the output. Its only
external requires are node builtins, `libphonenumber-js/metadata.max.json`,
and `unidecode`. So a `require("rolodexter")` consumer receives fuzzball
inlined in the tarball AND installs 3.85 MB of `node_modules` that is never
loaded. Only the ESM path (`dist/src/index.js`) imports it from disk.

The Python package already treats this layer as optional: `rapidfuzz` lives in
the `fuzzy` extra, and `FuzzyMatchStrategy.__init__` in `src/rolodexter/core.py`
catches the `ImportError`, sets `_available = False`, and `match()` returns
`None`, leaving the other three strategies running. The JS package makes the
same layer a hard `dependencies` entry, so every consumer pays for typo
recovery whether or not they want it.

Moving `fuzzball` to `optionalDependencies` and mirroring the Python guard in
the JS `FuzzyMatchStrategy` would cut a default install from roughly 19 MB to
15 MB and make the two packages behave identically. It is not done: it changes
published behavior, needs test coverage, and interacts with the CJS bundling
described above.

**`csv-stringify` is used at exactly one call site**, `packages/js/src/cli.ts`
(the CSV output path), with only `header: true` and `columns`. It has no
dependencies of its own and is not imported by the library or the CJS bundles,
so it is only needed when someone runs the CLI. A small internal RFC-4180
writer would replace it and save 970 KB, at the cost of hand-maintaining quote
and newline escaping.

`libphonenumber-js` is 12 MB on disk, but its metadata files are only 83 to
155 KB each; the bulk is shipped source variants, not runtime cost. Leave it
alone.

## Dependabot

Dependabot is configured in `.github/dependabot.yml` for:

- Python dependencies in `pyproject.toml`
- GitHub Actions in workflow files

It is useful here because it keeps CI and publishing actions current and opens small reviewable dependency PRs. Keep it unless the noise becomes more expensive than the maintenance value.

Current Dependabot handling on 2026-06-28:

- Merged PR #5: `actions/setup-python` from 5 to 6. Checks were green.
- Merged PR #7: `actions/upload-artifact` from 4 to 7. Checks were green.
- Merged PR #8: `codecov/codecov-action` from 4 to 7. Checks were green.
- Merged PR #9: `actions/checkout` from 4 to 7. The initial failures were from
  mypy/dependency typing drift, not checkout itself; CI was fixed and rerun
  green before merge.

Dependabot rule of thumb:

- Merge small dependency PRs when they are mergeable, scoped, and green across the full required CI matrix.
- Do not merge dependency PRs with red CI just because they are dependency updates.
- For GitHub Actions bumps, inspect workflow diffs and CI logs before merging.
