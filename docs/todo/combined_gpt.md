# Combined GPT Todo

Created: 2026-06-30.

Sources: `docs/todo/verified_gpt.md`, `docs/todo/next_gpt.md`, and
`docs/maintenance/release_and_distribution.md`.

This file replaces the missing `combined_gpt.md` requested in the maintenance
thread. It keeps only the items that still look worth doing after verification.

## Current Verdict

All verified code-level GPT audit items are complete in the current checkout.
The remaining items are release/process items or intentionally deferred
maintenance guardrails. No further autonomous code fixes remain from the
consolidated DRY, bottleneck, dependency, deletion, or deviance audits.

## Completed And Reverified Locally

- [x] Severity: 1/5 - Python mapper, normalization, CLI, i18n cache, bounded
  processing, and row-level fault-isolation fixes are implemented.
  - Verification: `py -3 -m ruff check src tests`, `py -3 -m ruff format --check src tests`,
    `py -3 -m mypy src`, and `$env:PYTHONPATH='src'; py -3 -m pytest --cov=rolodexter --cov-report=xml --cov-report=term-missing`
    passed on 2026-06-30. Pytest result: 905 passed, 93.93% coverage.
- [x] Severity: 1/5 - Python release candidate `2.8.1` builds cleanly.
  - Verification: `py -3 -m build --outdir .tmp\dist-check` built both sdist
    and wheel, and `py -3 -m twine check .tmp\dist-check\*` passed.
- [x] Severity: 1/5 - The parallel TypeScript/NPM package is segregated under
  `packages/js` and is a practical parity package rather than a thin Python wrapper.
  - Verification: `npm run typecheck`, `npm test`, and `npm run test:parity`
    passed on 2026-06-30. Unit result: 56 passed. Parity result: Python/NPM
    release versions match `2.8.1`; mapper/API and CLI probes both reported
    zero mismatches.
- [x] Severity: 1/5 - The NPM package payload and dry-run publish path are ready
  for a real release once credentials and approval exist.
  - Verification: `npm audit --json` reported 0 vulnerabilities;
    `npm pack --dry-run --json` produced the expected 24-file package
    at 407.1 kB packed / 1.9 MB unpacked; `npm publish --dry-run` passed
    for `rolodexter@2.8.1`.
- [x] Severity: 2/5 - The Python and NPM package boundaries are documented.
  - Verification: root README and `packages/js/README.md` identify the PyPI
    package source (`src/rolodexter`, `pyproject.toml`) and NPM package source
    (`packages/js`, `packages/js/package.json`) separately.

## Remaining Todo, Ordered By Importance

- [ ] Severity: 1/5 - Commit/push the current release-candidate work only after
  reviewing the dirty worktree and confirming CI goes green on GitHub.
  - Verified need: local gates are green, but remote CI cannot be proven until
    the branch is pushed or the workflows are run in GitHub.
- [ ] Severity: 1/5 - Publish `rolodexter` `2.8.1` to PyPI after explicit release
  approval and green CI.
  - Verified need: PyPI latest is still `2.8.0` as of 2026-06-30; local
    `pyproject.toml` is `2.8.1`; build and twine checks pass.
- [ ] Severity: 1/5 - Publish `rolodexter` `2.8.1` to NPM after explicit release
  approval and NPM credentials or trusted publishing are configured.
  - Verified need: `npm view rolodexter version --json` returns registry `E404`
    as of 2026-06-30, so the package is not publicly visible under that name;
    local pack and publish dry-runs pass.
- [ ] Severity: 2/5 - Keep broadening Python/NPM parity probes whenever the
  public API grows.
  - Verified need: current probes report zero mismatches, but this is an ongoing
    release guardrail rather than a one-time code bug.
- [ ] Severity: 5/5 - Decide separately whether to keep or delete pre-existing
  untracked scratch files `cb_better_01.md` and `cb_issues_01.md`.
  - Verified need: they are untracked scratch files that predate this pass, so
    they were intentionally left untouched.

## Not Done Autonomously

- No real PyPI or NPM publish was attempted.
- No remote push, merge, or release tag was attempted.
- No pre-existing untracked scratch file was deleted.
