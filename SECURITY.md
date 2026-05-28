# Security Policy

## Reporting a Vulnerability

Please report security issues privately via
[GitHub Security Advisories](https://github.com/lunawerx/rolodexter/security/advisories/new)
rather than opening a public issue.

We aim to acknowledge reports within 3 business days and to ship a fix or
mitigation for confirmed issues as quickly as is practical.

## Supported Versions

Security fixes are applied to the latest released minor version. Please upgrade
to the most recent release before reporting.

## Supply-chain Hardening

- **Releases use PyPI [trusted publishing](https://docs.pypi.org/trusted-publishers/)
  (OIDC)** — no long-lived API tokens are stored anywhere. Published
  artifacts include [PEP 740](https://peps.python.org/pep-0740/) provenance
  attestations.
- **CI runs a [`gitleaks`](https://github.com/gitleaks/gitleaks) secret scan**
  on every push and pull request.
- **Dependencies are monitored by Dependabot** and pinned with an upper bound
  on `phonenumbers` (whose metadata changes frequently).

## Handling Contact Data

`rolodexter` performs all normalization locally and makes **no network calls**
during mapping. The optional i18n alias *generation* step (`rolodexter.i18n`)
calls a translation service; it is an explicit, offline build step and is never
invoked on a mapping/request path.
