# Release And Distribution Notes

Last checked: 2026-09-02.

## Current Package Status

- PyPI project: <https://pypi.org/project/rolodexter/>, latest published `2.12.0`
  (2026-09-02).
- NPM package: <https://www.npmjs.com/package/rolodexter>, latest published
  `2.12.0`, published from `packages/js` with Sigstore provenance.
- Local release-candidate versions in `pyproject.toml`,
  `packages/js/package.json`, `packages/js/package-lock.json` and the
  `version` literal in `packages/js/src/index.ts`: `2.12.0`. All four are
  bumped together (the lockfile sat at `2.10.0` through two releases because
  nothing checked it; `npm version X --no-git-tag-version` bumps it with
  `package.json`).
- Python requirement: `>=3.10`; Node requirement: `>=20`.

Both registries are in step at `2.12.0`, and have been at every release since
`2.9.1`, because one GitHub Release now publishes both. They were not between
2026-07-10 and 2026-07-18; see "The 2.9.1 npm gap" below for the cause and the
fix.

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
- PyPI uses **trusted publishing**, which is pinned on PyPI's side. The move
  initially invalidated it: a manual dispatch of `publish.yml` on 2026-07-18
  failed the OIDC exchange with `invalid-publisher`. The publisher was
  reconfigured for the new owner and verified on 2026-07-23: a safe
  existing-version dispatch completed the OIDC exchange and reached PyPI,
  where it stopped only because the `2.9.1` wheel already exists. The active
  publisher matches these claims:

  | Field | Value |
  | --- | --- |
  | Owner | `LunarWerxs` |
  | Repository name | `RoloDexter` |
  | Workflow name | `publish.yml` |
  | Environment name | `pypi` |

  The verification run is
  <https://github.com/LunarWerxs/RoloDexter/actions/runs/30067677802>.

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

1. Run the full local quality gate, which is exactly what CI runs plus the
   step CI runs on one OS only:

   ```powershell
   ruff check src tests; ruff format --check src tests; mypy src
   pytest -q
   deptry .; vulture src scripts --min-confidence 80; pylint --errors-only src/rolodexter
   ```

   Then the whole workflow in a Linux container, which is faster than the
   host and is the leg CI actually runs: `python ~/.claude/tools/localci.py
   --docker` (35 steps for this repo, about six minutes).

2. If the release touches module layout, packaging, or a normalizer, run the
   adversarial pre-release review described under "Release verification for
   2.12.0" below. It is the only gate that looks at the shipped artifacts the
   way a consumer does, and it found a release-blocker that every other gate
   passed.

3. Confirm package metadata and docs are current:

   - `CHANGELOG.md`: `[Unreleased]` becomes `[X.Y.Z] - date`, with an empty
     `[Unreleased]` left above it. Walk `git log <last tag>..HEAD` and check
     every user-observable change has an entry; two were missing at 2.12.0.
   - README examples and feature wording
   - `docs/pricing.md`, which names the shipped version

4. Bump the version using semver intent, in all five sites named under
   "Current Package Status", and run `python scripts/check_release_versions.py`:

   - Patch: bug fixes and internal maintenance with compatible behavior
   - Minor: new public features or meaningful API additions, or a behavior
     change on a common field (2.12.0's name casing)
   - Major: breaking API or behavior changes

5. Build and inspect the Python package before publishing, outside the
   repository so the checkout cannot leak into the artifact:

   ```powershell
   python -m build --outdir <scratch>/dist .
   python -m twine check <scratch>/dist/*
   python -m venv <scratch>/venv; <scratch>/venv/Scripts/pip install <scratch>/dist/*.whl
   cd <scratch>; <scratch>/venv/Scripts/python -W error -c "import rolodexter; print(rolodexter.__version__)"
   ```

6. Publish only after every gate above passes: commit, push, then
   `gh release create vX.Y.Z --title "RoloDexter X.Y.Z" --notes-file <notes>`.
   The Release event publishes to PyPI and npm at once. Watch both runs, then
   verify from the registries, not the logs: `pip install rolodexter==X.Y.Z`
   into a fresh venv and `npm install rolodexter@X.Y.Z` into a fresh consumer,
   with a file-invoked `require("rolodexter/i18n")` and a `tsc` run at
   `skipLibCheck: false`. PyPI's JSON index lags pip by a few minutes.

For the JavaScript/TypeScript package:

```powershell
cd packages/js
npm ci
npm run typecheck
npm test
npm run check:parity
npm pack --dry-run
npm publish --dry-run
npm audit --omit=dev
```

Release verification for 2.12.0 on 2026-09-02, which added one gate to the
list above and is the one to copy next time:

- Everything under "Before publishing" passed: ruff, mypy, 1,098 pytest cases
  on 3.10-3.14, deptry/vulture/pylint by hand (CI runs them on one OS only),
  `python -m build` + `twine check` for both artifacts, and a fresh-venv
  install of the built wheel from outside the repo. JS: typecheck, 130 tests
  on Node 20 and 24, both parity probes at zero mismatches, `npm pack
  --dry-run`. The whole workflow ran in a Linux container first via
  `localci --docker` (35 steps), then on GitHub.
- **The new gate: an adversarial pre-release review of everything since the
  last tag**, run as seven independent finders (Python API surface, JS API
  surface, Python packaging, JS packaging, a 37,705-case behavior diff against
  the published 2.11.1, a 300-name attack on the changed normalizer, and
  changelog-vs-code) with every finding attacked by two refuters and a
  completeness critic at the end. It found one release-blocker that no test
  or CI step could see: the shipped `.d.ts` files did not type-check for a
  consumer with `skipLibCheck` at its default, because the `index.ts` split
  re-exported names `stripInternal` had removed. It also found the CJS
  `require("rolodexter/i18n")` crash that had shipped in every release since
  the bundles existed, an unbounded `nameparser` pin over a deprecated code
  path, and two changelog omissions. Each is fixed and has a test that was
  shown to fail on the previous sources. `test/declarations.test.ts` is the
  permanent form of the blocker's check; the review itself is worth
  re-running before any release that touches module layout or packaging.

Latest local release verification on 2026-06-30:

- Python gates: `ruff check src tests`, `ruff format --check src tests`, `mypy src`, and `$env:PYTHONPATH='src'; pytest --cov=rolodexter --cov-report=xml --cov-report=term-missing` passed. Pytest result: 905 passed, 93.93% total coverage.
- Python artifacts: `py -3 -m build --outdir .tmp\dist-check` built the `2.8.1`
  sdist and wheel, and `py -3 -m twine check .tmp\dist-check\*` passed for both.
- `npm run typecheck`: passed.
- `npm test`: 56 passed.
- `npm run check:parity`: release versions match `2.8.1`; expanded mapper/API and CLI parity probes reported zero mismatches.
- `npm pack --dry-run --json`: passed for `rolodexter@2.8.1`; packed size 407.1 kB, unpacked size 1.9 MB, 24 files. Tarball includes ESM/CJS library files, both CLIs, `patterns.json`, README, LICENSE, declaration files, and package metadata; `cli.d.ts` is not packed. The package `prepack` lifecycle runs both `npm test` and `npm run check:parity`, so local pack/publish commands cannot skip parity accidentally.
- Fresh throwaway install from the packed tarball: ESM import, CommonJS require, `ContactMapper.map_payload()`, Python-shaped root/core/i18n exports, i18n `load_cached()`/`generate_language()` parity edges, `npx rolodexter fields`, and `npx rolodexter-i18n --list` worked. A cache-only install with `--omit=optional` also worked, proving mapper construction and both CLIs do not require generation-only translation/transliteration packages.
- `npm publish --dry-run`: passed for `rolodexter@2.8.1` with the CLI `bin` metadata accepted as-is.
- `npm audit --json`: 0 vulnerabilities; audit metadata reports 7 production dependencies and 39 optional dependencies after generation-only translation/transliteration packages moved to `optionalDependencies`.
- Current release parity note: package root, `rolodexter/core`, and `rolodexter/i18n` exports are Python-shaped; packed declarations no longer advertise the previously audited camelCase helper/option aliases; installed public class instances no longer expose the previously audited JS-only camelCase prototype methods; mapper/schema/DataFrame warning messages are silent by default and observable through a package-specific Node process event when hosts opt in; importing `rolodexter/i18n` has no global stdout listener side effect; closed-stdout CLI behavior now matches the audited Python broken-pipe diagnostic/exit shape; manually constructed phone formatting, phone helper edge cases, normalizer runtime edge cases, `FieldMatch.service`, registry/schema/i18n missing-value semantics, mapper argument/shape errors, `MappingSchema.apply()` errors, public i18n helper arity/keyword-equivalent options, Python JSON constants, CSV file bytes, clean quarantine side effects, `-.5` CLI value validation, and model/strategy constructor arity errors are covered by the tracked parity probes; and tracked mapper/API plus CLI parity probes report zero mismatches. Ongoing parity probe expansion is tracked internally.

## The NPM Package

`rolodexter` on npm is a real TypeScript package under `packages/js`, shipped
since 2.9.0 (2026-07-08), not a wrapper around Python. It mirrors the Python
package's behavior and ships its own types. What keeps the two from drifting:

- `src/rolodexter/patterns.json` is the canonical alias source; the JS build
  syncs it before compiling, so the two packages read one file.
- Both packages exercise the same fixture corpus in
  `tests/fixtures/golden_corpora.json`.
- `scripts/parity_probe.py` and `scripts/cli_parity_probe.py` run the same
  curated cases through both packages in CI and fail on any mismatch;
  `scripts/parity_sweep.py` runs a generated 37,705-case corpus on demand (see
  `docs/maintenance/parity_sweep.md`).
- The two packages are published with matching version numbers from one
  GitHub Release, and `scripts/check_release_versions.py` refuses a mismatch.

The CI workflow tests the JavaScript package on Node 20 and Node 24 so the
declared `>=20` engine floor is covered before release.

### Moving npm to trusted publishing (open)

PyPI publishes through OIDC trusted publishing and holds no token. npm still
publishes with `NPM_TOKEN`, an environment secret on the `npm` environment,
and that token was pasted into a chat when it was created on 2026-07-08, so it
should be treated as exposed. The right fix is not a fresh token but the same
model PyPI uses: npm's trusted publishing, which the workflow is already
shaped for (`permissions: id-token: write`, `npm publish --provenance`). It
needs one action on npmjs.com that only a package owner can take, then one
workflow edit:

1. On npmjs.com, signed in as an owner of `rolodexter`: package settings,
   "Trusted publishing", add a GitHub Actions publisher with organization or
   user `LunarWerxs`, repository `RoloDexter`, workflow filename
   `npm-publish.yml`, environment `npm`. These must match the workflow file's
   name and the environment it declares exactly, the way the PyPI publisher
   table above does.
2. In `.github/workflows/npm-publish.yml`, delete the `env: NODE_AUTH_TOKEN`
   line from the publish step, and add `npm install -g npm@latest` before it:
   trusted publishing needs npm CLI 11.5.1 or newer, and the npm bundled with
   the runner's Node 24 is not guaranteed to be that new. With no token in the
   environment, `npm publish --provenance` exchanges the runner's OIDC token
   for a short-lived publish credential on its own.
3. Verify with a `workflow_dispatch` of `npm-publish.yml` at the default
   `dry_run: true` (which exercises everything but the upload), then trust
   the next real release, and only then delete the `NPM_TOKEN` secret and
   revoke the token on npmjs.com.

Do step 1 before step 2: with the token removed and no publisher configured,
the next release's npm half fails and the registries fall out of step again.

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
