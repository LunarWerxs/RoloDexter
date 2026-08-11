# Security Policy

## Reporting a Vulnerability

Please report security issues privately via
[GitHub Security Advisories](https://github.com/LunarWerxs/RoloDexter/security/advisories/new)
rather than opening a public issue.

We aim to acknowledge reports within 3 business days and to ship a fix or
mitigation for confirmed issues as quickly as is practical.

## Supported Versions

Security fixes are applied to the latest released minor version. Please upgrade
to the most recent release before reporting.

## Supply-chain Hardening

- **Releases use PyPI [trusted publishing](https://docs.pypi.org/trusted-publishers/)
  (OIDC)**, no long-lived API tokens are stored anywhere. Published
  artifacts include [PEP 740](https://peps.python.org/pep-0740/) provenance
  attestations.
- **NPM releases are published from GitHub Actions with
  [provenance](https://docs.npmjs.com/generating-provenance-statements)**
  (Sigstore), linking each published tarball to its source commit and build.
- **CI runs a [`gitleaks`](https://github.com/gitleaks/gitleaks) secret scan**
  on every push and pull request.
- **Dependencies are monitored by Dependabot** and pinned with an upper bound
  on `phonenumbers` (whose metadata changes frequently).

## Handling Contact Data

`rolodexter` performs all normalization locally and makes **no network calls**
during mapping. The optional i18n alias *generation* step (`rolodexter.i18n`)
calls a translation service; it is an explicit, offline build step and is never
invoked on a mapping/request path. `import rolodexter` on its own, and every
`ContactMapper` call, is likewise fully network-silent.

## Anonymous Install Ping

The `rolodexter` **CLI** (not the library) sends one small, anonymous ping at
most once every 24 hours: a random per-install id (`X-Install-Id`), the
running version, and a coarse OS tag such as `win11-26100`, `macos`, or
`linux`. It never carries a hostname, username, file path, email address, or
any contact data. The endpoint (`https://studio.connections.icu/v1/app/rolodexter/latest`)
relays GitHub's `releases/latest` JSON verbatim, so the ping doubles as the
CLI's update check and adds no separate network call. A country is derived
server-side from the connection for aggregate stats only; no IP address is
stored. On the first ping a fresh install makes, it also reports `new=1`,
recorded locally only after that ping succeeds so a later, offline run cannot
double-count.

The request is fire-and-forget: it runs on a background thread with a 5
second timeout, every failure is silently swallowed, and there is no retry
loop, so it can never delay, block, or crash a command. Set
`ROLODEXTER_NO_PING=1` to disable it; it is also skipped automatically under
`pytest` and common CI environments (`CI`, `GITHUB_ACTIONS`).
