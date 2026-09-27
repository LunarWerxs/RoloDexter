# Running CI Locally

Before a release, the whole GitHub Actions workflow is run once in a Linux
container on the maintainer's machine, before it runs on GitHub. This page
says what that run covers and how to reproduce it without the maintainer's
private tooling.

## What it runs

The workflow is `.github/workflows/ci.yml`. Its jobs are:

- `test`: ruff, mypy and pytest with coverage on Python 3.10-3.14, plus the
  additional static analysis (deptry, vulture, pylint) that CI runs on one
  OS and Python version only.
- `secret-scan`: gitleaks over the history.
- `test-js`: the TypeScript package on Node 20 and 24 - typecheck, tests,
  coverage thresholds, the Python/NPM parity probes and `npm pack --dry-run`.
- `build`: sdist and wheel.

Run in a container, that is 35 steps for this repo and takes about six
minutes, which is faster than the Windows host and matches the Linux leg CI
actually runs.

## How the maintainer runs it

The maintainer uses `localci.py`, a small runner kept in the maintainer's
shared `claude-memory` repository (mirrored on the maintainer's machine under
the AI profile's `tools/` folder):

```powershell
python <claude-memory>/home/tools/localci.py --docker
```

It reads `.github/workflows/ci.yml` and executes its steps inside a Linux
container, so a failure shows up before the push instead of after it.

## Without that runner

Anyone else gets the same coverage by either of these:

1. Run the workflow with [`act`](https://github.com/nektos/act) from the
   repository root, which executes GitHub Actions workflows in Docker.
2. Run the steps by hand: the local quality gate listed under "Release Policy"
   in [release_and_distribution.md](release_and_distribution.md), then the
   JavaScript steps from `ci.yml`'s `test-js` job inside `packages/js`.

Either way, the push to GitHub remains the final gate; the local run only
moves the failure earlier.
