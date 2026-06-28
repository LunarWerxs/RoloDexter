# Next Work Todo

Created: 2026-06-28.

This is the restart list for the next RoloDexter maintenance stint.

## Immediate

- [x] Diagnose the failing Python CI jobs on Dependabot PR #9.
  - PR: <https://github.com/Lunarwerx/rolodexter/pull/9>
  - Change: `actions/checkout` from 4 to 7.
  - Finding: checkout itself works. The first failure was stricter mypy handling
    of `nameparser` ignores; the later failure is NumPy 2.5 stubs being parsed
    while mypy is intentionally configured for the Python 3.10 type target.
  - Local fixes: remove the line-level ignores, add a config-level
    `nameparser.*` mypy override, avoid static pandas stub imports, and pin
    `numpy<2.5` in the dev extra for CI stability.
  - Remaining: push the latest CI fix, update/rerun PR #9, and merge only after
    the full CI matrix is green.

- [x] Sync local branch with the remote main branch after the merged Dependabot PRs.
  - Merged already: PR #5 `actions/setup-python`, PR #7 `actions/upload-artifact`, PR #8 `codecov/codecov-action`.
  - Do this carefully because there are substantial local uncommitted changes from the previous fix pass.
  - Preserve local work; do not reset it away.

- [x] Review, commit, and push the completed Python maintenance fixes.
  - Includes mapper correctness fixes, CLI atomic output, i18n cache behavior, README wording, regression tests, and todo/maintenance docs.
  - Leave or explicitly handle pre-existing untracked scratch files: `cb_better_01.md` and `cb_issues_01.md`.

- [x] Run the full local quality gate before any release decision.
  - Commands:

    ```powershell
    $env:PYTHONPATH='src'; python -m ruff check src/ tests/
    $env:PYTHONPATH='src'; python -m ruff format --check src/ tests/
    $env:PYTHONPATH='src'; python -m mypy src/
    $env:PYTHONPATH='src'; python -m pytest --cov=rolodexter --cov-report=xml --cov-report=term-missing
    ```

## Python Release

- [x] Decide the next Python package version.
  - Current PyPI version when noted: `2.8.0`.
  - Local release-candidate version: `2.8.1`.

- [x] Update release metadata before publishing.
  - `pyproject.toml`
  - `CHANGELOG.md`
  - README, if any final wording changes are needed
  - Any docs under `docs/maintenance` or `docs/todo`

- [x] Build and validate the Python package.

  ```powershell
  python -m build
  python -m twine check dist/*
  ```

  - Local validation used a temp output directory and passed for
    `rolodexter-2.8.1`.

- [ ] Publish to PyPI only after lint, tests, build validation, and CI pass.

## NPM Package Track

- [ ] Create a parallel JavaScript/TypeScript package plan.
  - Preferred shape: a TypeScript package, likely under `packages/js` or `npm/`.
  - Publish target: NPM.
  - Keep it parallel to the Python package, not tangled into `src/rolodexter`.

- [ ] Extract or formalize shared canonical data.
  - The NPM package should use the same alias/pattern truth table as Python.
  - Avoid Python and JS maintaining separate drifting copies.
  - Candidate shared source: `src/rolodexter/patterns.json`, possibly moved or mirrored into a package-neutral location.

- [ ] Define the initial NPM API.
  - Likely equivalents:
    - `ContactMapper`
    - `identify(header, value?)`
    - `mapPayload(payload, options?)`
    - `mapBatch(payloads, options?)`
    - `compileSchema(headers, options?)`
  - Ship TypeScript types from day one.

- [ ] Decide how much behavior parity v1 needs.
  - Easy first parity:
    - exact alias matching
    - normalized header matching
    - heuristic email/URL/postal/date matching
    - list/tag normalization
    - confidence reporting
  - Harder parity:
    - phone parsing equivalent to Python `phonenumbers`
    - fuzzy matching equivalent to `rapidfuzz`
    - i18n cache generation/loading

- [ ] Choose high-ROI JS dependencies.
  - Evaluate phone parsing options such as `libphonenumber-js`.
  - Evaluate fuzzy matching options such as `rapidfuzz` equivalents or a small maintained scorer.
  - Keep the dependency surface modest.

- [ ] Add cross-language golden tests.
  - Shared fixtures should assert Python and TypeScript produce the same canonical mappings where both claim support.
  - Start with CRM/contact examples already covered by Python tests.

- [ ] Add NPM build/test/release automation.
  - `package.json`
  - `tsconfig.json`
  - test runner
  - lint/format choice
  - GitHub Actions jobs for JS tests
  - NPM publish workflow, ideally versioned alongside PyPI when behavior is equivalent.

## Still Worth Doing From Verified Audit

- [ ] Make CLI CSV/JSON processing truly streaming or explicitly bounded.
- [ ] Add row-level CLI fault isolation, such as `--on-error fail|skip|quarantine`.
- [ ] Bound embedded phone extraction CPU and memory.
- [ ] Harden i18n generation against network stalls and worker failure propagation.
- [ ] Revisit generic date and numeric-ID heuristics before changing behavior.
- [ ] Prefer user cache for generated i18n files instead of package-local generated data.
- [ ] Add a bounded header-resolution cache for long-lived mapper instances.
