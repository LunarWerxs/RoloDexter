# Release And Distribution Notes

Last checked: 2026-07-08.

## Current Package Status

RoloDexter ships a Python package on PyPI and a JavaScript/TypeScript package on
npm, both at `2.9.0` (released 2026-07-08):

- PyPI project: <https://pypi.org/project/rolodexter/> — latest published `2.9.0`.
- NPM package: <https://www.npmjs.com/package/rolodexter> — latest published
  `2.9.0`, published from `packages/js` with Sigstore provenance.
- Local versions in `pyproject.toml` and `packages/js/package.json`: `2.9.0`.
- Python requirement: `>=3.10`; Node requirement: `>=20`.

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
- Current release parity note: package root, `rolodexter/core`, and `rolodexter/i18n` exports are Python-shaped; packed declarations no longer advertise the previously audited camelCase helper/option aliases; installed public class instances no longer expose the previously audited JS-only camelCase prototype methods; mapper/schema/DataFrame warning messages are silent by default and observable through a package-specific Node process event when hosts opt in; importing `rolodexter/i18n` has no global stdout listener side effect; closed-stdout CLI behavior now matches the audited Python broken-pipe diagnostic/exit shape; manually constructed phone formatting, phone helper edge cases, normalizer runtime edge cases, `FieldMatch.service`, registry/schema/i18n missing-value semantics, mapper argument/shape errors, `MappingSchema.apply()` errors, public i18n helper arity/keyword-equivalent options, Python JSON constants, CSV file bytes, clean quarantine side effects, `-.5` CLI value validation, and model/strategy constructor arity errors are covered by the tracked parity probes; and tracked mapper/API plus CLI parity probes report zero mismatches. Ongoing parity probe expansion is tracked in `docs/todo/next_gpt.md`.

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

The `.github/workflows/npm-publish.yml` workflow is manual and defaults to a
dry run. Set `dry_run=false` only after the NPM package has token-based
credentials (`NPM_TOKEN`) or trusted publishing configured for the repository.

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
