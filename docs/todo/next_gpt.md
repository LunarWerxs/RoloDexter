# Next Work Todo

Created: 2026-06-28.
Last checked: 2026-06-30.

This is the restart list for the next RoloDexter maintenance stint.

## Completed In This Stint

- [x] Fixed the failing Python CI / Dependabot path and preserved local work while syncing with remote `main`.
- [x] Completed the verified Python maintenance fixes:
  - CLI atomic output and row-level `--on-error fail|skip|quarantine`.
  - Bounded JSON/CSV materialization.
  - Bounded embedded phone extraction.
  - i18n cache read/write hardening.
  - Bounded header-resolution cache.
  - Heuristic guardrails for ambiguous dates and numeric IDs.
- [x] Prepared Python package release metadata for local `2.8.1`.
- [x] Created and expanded the parallel TypeScript/NPM package under `packages/js`.
- [x] Synced JS patterns from Python `patterns.json`.
- [x] Added cross-language golden fixture coverage in `tests/fixtures/golden_corpora.json`.
- [x] Added NPM CI and manual publish workflow.
- [x] Expanded the NPM package to practical Python parity:
  - exact, normalized, fuzzy, and heuristic matching;
  - public normalizers, match strategies, phone helpers, and Python-shaped aliases;
  - i18n generation plus cached loading/introspection;
  - bounded header cache controls;
  - `rolodexter` CLI with `map`, `explain`, `fields`, CSV handling, and JSONL quarantine.
- [x] Bumped the local NPM package version to `2.8.1`.
- [x] Fixed NPM publish metadata polish:
  - normalized the CLI `bin` path so `npm publish --dry-run` no longer auto-corrects it;
  - included a package-local `LICENSE` file in the JS tarball;
  - added CommonJS output alongside ESM exports;
  - added the `rolodexter-i18n` CLI and exact Python-shaped root/i18n package exports;
  - matched audited Python parity cases for fuzzy confidence, reply-to/owner fuzzy drift, nickname parsing, `nameparser` title/suffix handling, short phone-number matching, 7-digit US local phone normalization and national formatting, cross-country phone match behavior, `MappingSchema.default_region`, DataFrame-like adapters, and normalizer instance calls.
  - matched sampled Python CLI stdout/stderr/exit behavior for missing and invalid subcommands, option abbreviations, `--`, leading-plus numeric args, invalid choices, invalid numeric types, and JSONL quarantine diagnostics.
  - streamed CSV/JSONL input and JSONL output paths instead of materializing all mapped rows.
- [x] Tightened the shipped NPM API/declaration surface toward Python parity:
  - removed camelCase helper names and option aliases from emitted TypeScript declarations;
  - stopped packing `dist/src/cli.d.ts`;
  - kept root/package exports Python-shaped while preserving internal implementation hooks for the CLIs;
  - matched an additional 18/18 targeted Python-vs-JS CLI edge cases byte-for-byte, including abbreviated `--help`, explicit values on boolean flags, unknown short options, ragged CSV, JSON diagnostics, and i18n `--` handling.
- [x] Added JS warning observability for mapper/schema/DataFrame warning paths:
  - default JS behavior remains silent like Python's default logging setup;
  - hosts can subscribe to the package-specific `rolodexterWarning` process event to observe the same warning messages Python emits through configured logging.
- [x] Matched Python-style closed-stdout handling in the NPM CLIs:
  - `rolodexter` and `rolodexter-i18n` now report the same broken stdout flush diagnostic shape and exit `120` when a downstream pipe closes early.
  - Added a regression test that closes stdout after the first byte of a large JSONL CLI stream.
- [x] Rechecked and patched the final Python/NPM parity drift found during readiness verification:
  - matched additional mapper and CLI edge cases for Python dataclass-like frozen errors, `MappingResult.get_match()`, name/address casing, list collision dedupe, CSV surplus/unclosed-row behavior, option value parsing, JSON diagnostics, i18n language parsing, and materialization-limit ordering;
  - expanded the local Python-vs-JS mapper and CLI parity probes, both of which now report zero mismatches;
  - isolated a Python i18n cache test from the real user cache directory so the full suite no longer hangs on restricted Windows cache paths.
- [x] Promoted stricter parity evidence from scratch probes into tracked release gates:
  - added explicit Python `core.__all__` and `i18n.__all__` lists and matching JS subpath `__all__` exports;
  - matched JS phone helper edge cases for alphabetic non-phone text and 7-digit US local fallback possibility;
  - removed JS-only object-shaped public constructors and matched Python constructor TypeError messages;
  - matched `rolodexter.i18n.main()` arity behavior;
  - moved mapper/API and CLI parity probes into `scripts/`, added `scripts/check_release_versions.py`, wired `npm run test:parity` into CI and NPM publish checks, and removed unused `csv-parse`.
- [x] Broadened the tracked Python/NPM API parity probe again:
  - matched normalizer runtime edge cases for keyword-equivalent phone regions, rejected positional phone regions, and `NameNormalizer.parse()` non-string AttributeErrors;
  - matched manually constructed `PhoneNumber` display helpers, including metadata-free NANP formatting and `country_codes`;
  - matched public model constructor arity errors for too-few and too-many positional arguments;
  - included `FieldMatch.service` in the mapper/API parity probe.
- [x] Broadened public registry/strategy runtime parity:
  - `PatternRegistry` now accepts Python-style positional `patterns`, `patterns_path`, `languages`, and `overrides` while preserving the JS keyword-equivalent options object;
  - `PatternRegistry.exact_lookup()` and `MappingSchema.matches.get()` now return `null` for missing values, matching Python `None`;
  - `PatternRegistry.toString()` mirrors Python `repr()` for the verified custom-pattern case;
  - public match strategy constructors now match Python arity errors for missing or extra arguments.
- [x] Tightened public i18n helper runtime parity:
  - `load_cached()` now returns `null` for missing caches, matching Python `None`;
  - Python-shaped `generate_language()` now rejects extra positional arguments before any translation/generation path can run;
  - tracked parity probes cover these cache-only i18n public-helper cases.
- [x] Tightened mapper runtime shape parity:
  - `compile_schema()` now stringifies non-string headers like Python;
  - mapper methods reject missing required arguments, primitive option bags, and array payloads with Python-shaped errors;
  - tracked parity probes cover these runtime rejection cases.
- [x] Tightened CLI byte and side-effect parity:
  - JSON/JSONL parsing and output now preserve Python's `NaN`/`Infinity` behavior;
  - CSV file output uses Python `csv` CRLF bytes;
  - clean `--on-error quarantine` runs create the same empty quarantine file side effect;
  - `explain`/`MappingResult.explain()` string repr quote selection is closer to Python.
- [x] Closed the final subagent-audited NPM parity gaps:
  - public phone helpers now match Python for non-string raw values, arity errors, wrong-object `AttributeError`s, matcher `null` text, bad `max_matches`, and `PhoneNumberMatch` string form;
  - importing `rolodexter/i18n` no longer registers a global stdout error listener; broken-pipe handling is installed only for CLI execution / `main()`;
  - `generate_language()` accepts the JS keyword-equivalent options object for Python's keyword-only generation args while still rejecting true extra positional args and unknown keywords;
  - `MappingSchema.apply()`, mapper constructors/options, cache helpers, and `PatternRegistry` invalid shapes now follow Python rejection paths;
  - public model objects are non-extensible like frozen slotted dataclasses, and `MappingResult.to_dict()` serializes fixed `FieldMatch` fields only;
  - `rolodexter-i18n --workers` now actually runs bounded parallel language generation, generation-only dependencies are optional on NPM, empty i18n generation warns and skips empty cache writes, and `-.5` option values flow to validation like Python `argparse`.
- [x] Added the missing combined audit source of truth at `docs/todo/combined_gpt.md`.

## Verified Gates

- [x] `ruff check src/ tests/`
- [x] `ruff format --check src/ tests/`
- [x] `mypy src/`
- [x] `$env:PYTHONPATH='src'; pytest --cov=rolodexter --cov-report=xml --cov-report=term-missing`
  - Result: 905 passed, total coverage 93.93%.
- [x] `py -3 -m build --outdir .tmp\dist-check`
  - Result: built `rolodexter-2.8.1.tar.gz` and `rolodexter-2.8.1-py3-none-any.whl`.
- [x] `py -3 -m twine check .tmp\dist-check\*`
  - Result: passed for both Python artifacts.
- [x] `npm test`
  - Result: 56 passed.
- [x] `npm run test:parity`
  - Result: release versions match `2.8.1`; expanded mapper/API and CLI parity probes both reported zero mismatches.
- [x] Targeted Python-vs-JS mapper parity probe
  - Result: zero mismatches.
- [x] Targeted Python-vs-JS CLI parity probe
  - Result: zero mismatches.
- [x] `npm pack --dry-run --json`
  - Result: passed for `rolodexter@2.8.1`; tarball is 407.1 kB packed / 1.9 MB unpacked, includes 24 files, and includes compiled ESM/CJS library files, CLI files, type declarations, `patterns.json`, README, LICENSE, and package metadata. `cli.d.ts` is no longer packed.
- [x] Fresh throwaway install from packed NPM tarball
  - Result: ESM import, CommonJS require, `ContactMapper.map_payload()`, Python-shaped root/core/i18n exports, i18n missing-cache/missing-language edges, `npx rolodexter fields`, and `npx rolodexter-i18n --list` worked. A separate install with `--omit=optional` also worked for cache-only mapper/runtime use and both CLIs.
- [x] `npm publish --dry-run`
  - Result: passed for `rolodexter@2.8.1`; tarball includes `LICENSE` and no CLI `bin` auto-correction warning.
- [x] `npm audit --json`
  - Result: 0 vulnerabilities; audit metadata reports 7 production deps and 39 optional deps after moving generation-only translation/transliteration packages to optional dependencies.

## Still Open

- [ ] Keep broadening Python/NPM parity probes as the API grows.
  - No known NPM implementation blocker remains from the current audit.
  - JS warning observability intentionally uses a Node process event rather than Python's logging module while preserving Python-like default silence.
  - Exact CLI byte parity should continue to be sampled on every release, not only when behavior changes.
- [ ] Publish to PyPI only after CI passes and release approval is explicit.
  - Latest registry check on 2026-06-30: PyPI latest is `2.8.0`; local release candidate is `2.8.1`.
- [ ] Publish to NPM only after CI passes and NPM credentials or trusted publishing are configured.
  - Latest registry check on 2026-06-30: `npm view rolodexter version --json` returns `E404`; local `2.8.1` pack and publish dry-runs pass.
- [ ] Leave pre-existing untracked scratch files alone unless explicitly asked:
  - `cb_better_01.md`
  - `cb_issues_01.md`
