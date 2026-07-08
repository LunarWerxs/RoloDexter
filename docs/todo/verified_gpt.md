# Verified GPT Todo

Consolidated from `dry_gpt.md`, `slow_gpt.md`, `despoke_gpt.md`, `delete_gpt.md`, and `deviant_gpt.md`.

Kept items were rechecked against the current code before action. Items marked done were implemented in this pass and verified with the test suite.

Last rechecked: 2026-06-30.

## Done In This Pass

- [x] Severity: 1/5 - Fix list-field normalization and list collision merging.
  - Verified: `normalize_value("tags", [" vip ", "", "beta"])` bypassed `ListNormalizer`, and duplicate `tags` aliases could produce nested lists.
  - Done: field normalizers now receive non-string values when they support them, and `_merge()` flattens/dedupes list-valued fields.
  - Verification: regression tests in `tests/test_rolodexter.py`; full suite passed.

- [x] Severity: 1/5 - Keep `map_batch()`, `map_stream()`, and `map_payload()` option surfaces in sync for embedded phone extraction.
  - Verified: `map_batch(..., extract_embedded_phones=True)` raised `TypeError`.
  - Done: `map_batch()` now accepts and forwards `extract_embedded_phones`.
  - Verification: regression test in `tests/test_v28_features.py`; full suite passed.

- [x] Severity: 1/5 - Make `compile_schema()` and `map_dataframe()` honor confidence thresholds and strict mode.
  - Verified: `ContactMapper(confidence_threshold=0.99).map_payload({"Compny": "Acme"})` dropped the fuzzy match, while `compile_schema()` and `map_dataframe()` still mapped it.
  - Done: schema/DataFrame paths apply validated thresholds; strict mode raises on dropped low-confidence matches and phone normalization failures.
  - Verification: regression tests in `tests/test_v28_features.py`; full suite passed.

- [x] Severity: 2/5 - Validate confidence thresholds as 0.0 to 1.0.
  - Verified: out-of-range thresholds like `1.1` silently made even exact matches disappear.
  - Done: constructor and per-call thresholds now raise `ValueError` outside `[0.0, 1.0]`.
  - Verification: regression tests in `tests/test_v28_features.py`; full suite passed.

- [x] Severity: 2/5 - Defer value stringification in the mapper hot path.
  - Verified: `map_payload()` stringified every value before knowing whether value-shape heuristics were needed.
  - Done: header-only matches no longer stringify values, and value-shape matching only stringifies scalar values.
  - Verification: full suite passed.

- [x] Severity: 2/5 - Add atomic CLI output semantics for file targets.
  - Verified: CLI `-o/--output` opened the final path before mapping, so strict failures could leave partial files or truncate existing output.
  - Done: file outputs now write to a same-directory temp file and replace the target only after successful completion.
  - Verification: regression tests in `tests/test_v28_features.py`; full suite passed.

- [x] Severity: 2/5 - Keep i18n cache reads read-only and make writes atomic.
  - Verified: cache discovery/read paths created directories and `.probe` files.
  - Done: read/discovery paths only inspect existing dirs; writes select an explicit writable dir and use temp-file replace. i18n dry-run no longer creates cache dirs.
  - Verification: `tests/test_i18n_cache_behavior.py`, i18n-focused tests, and full suite passed.

- [x] Severity: 2/5 - Bound embedded phone extraction CPU and memory.
  - Verified: extraction scanned full candidate strings and could materialize every `PhoneNumberMatcher` match.
  - Done: opt-in embedded extraction now caps scanned text length, matches per field, and matches per payload, and emits `MappingResult.warnings` when limits stop scanning.
  - Verification: regression tests in `tests/test_rolodexter.py`; full suite passed.

- [x] Severity: 1/5 - Add row-level CLI fault isolation.
  - Verified: one malformed JSONL row or strict normalization failure aborted the whole import.
  - Done: `rolodexter map --on-error fail|skip|quarantine` now handles row-level failures with row-numbered warnings, optional JSONL quarantine output, and fail-fast behavior preserved as the default.
  - Verification: regression tests in `tests/test_v28_features.py`; full suite passed.

- [x] Severity: 3/5 - Add a bounded header-resolution cache.
  - Verified: `_header_cache` was unbounded on long-lived mapper instances.
  - Done: `ContactMapper` now uses a bounded LRU header cache by default, accepts `header_cache_max_size`, and exposes `clear_cache()` / `cache_info()`.
  - Verification: regression tests in `tests/test_rolodexter.py`; full suite passed.

- [x] Severity: 1/5 - Make CLI CSV/JSON processing truly streaming or explicitly bounded.
  - Verified: JSON input and JSON/CSV output paths materialized full jobs in memory.
  - Done: JSONL output remains streaming; JSON input now has an explicit byte cap, and JSON/CSV output collection has an explicit row cap with CLI overrides.
  - Verification: regression tests in `tests/test_v28_features.py`.

- [x] Severity: 2/5 - Harden i18n generation against network stalls and worker failure propagation.
  - Verified: translation calls had no explicit timeout/retry budget and one failed worker could abort unrelated languages.
  - Done: translation calls now accept timeout/retry/backoff budgets, CLI worker counts are clamped, and per-language worker failures are reported while other completed languages still print results.
  - Verification: regression tests in `tests/test_rolodexter.py`.

- [x] Severity: 2/5 - Stop treating generated i18n cache files as package-local source data.
  - Verified: writable cache selection could choose the package `i18n/` directory for generation.
  - Done: generated i18n cache writes now prefer the platform user cache, package-data wildcarding was removed, and docs/tests no longer describe generated package-local data.
  - Verification: regression tests in `tests/test_i18n_cache_behavior.py` and `tests/test_rolodexter.py`.

- [x] Severity: 4/5 - Split i18n generation dependencies from runtime cache loading.
  - Verified: runtime mapper construction does not translate, but the `i18n` extra still bundled generation dependencies.
  - Done: `i18n` is dependency-light for cache loading, and the new `i18n-generate` extra installs `deep-translator` and `unidecode` for generation.
  - Verification: packaging metadata/docs updated.

- [x] Severity: 3/5 - Update README i18n wording to match cache-only runtime loading.
  - Verified: README still said mapper construction generated translations on demand.
  - Done: README now says caches must be generated first and mapper construction only loads cached aliases.
  - Verification: documentation-only change plus full suite passed.

- [x] Severity: 5/5 - Do not expose the mutable internal alias list.
  - Verified: `PatternRegistry.all_aliases` returned the backing list, so callers could mutate registry internals.
  - Done: `all_aliases` now returns a shallow copy while preserving the public `list[str]` shape.
  - Verification: regression test in `tests/test_rolodexter.py`; full suite passed.

- [x] Severity: 2/5 - Reduce value-only heuristic overclaiming for ambiguous dates and numeric IDs.
  - Verified: generic unknown date values map to `birthday`, and bare numeric strings can map to `phone`.
  - Done: date-shaped birthday matches now require a birth/DOB header hint, and digit-only phone-shaped values require a phone/tel/mobile-style header hint while formatted/E.164 phone values still match.
  - Verification: regression tests in `tests/test_rolodexter.py` and `packages/js/test/mapper.test.ts`.

- [x] Severity: 3/5 - Decide the fate of stale tracked `rolodexter.md`.
  - Verified: it appears to be an old prototype document and is not referenced by README, package metadata, or tests.
  - Done: removed the stale tracked prototype document.

- [x] Severity: 1/5 - Bring the NPM package from installable subset to practical Python parity.
  - Verified: the initial JS package exported only a mapper subset and lacked fuzzy matching, public phone helpers, public strategy classes, Python-shaped aliases, cached-i18n registry behavior, and a CLI.
  - Done: added fuzzy matching, public phone/normalizer/strategy APIs, instance normalizer calls, snake_case aliases, bounded header cache controls, i18n generation plus cached loading/introspection, an i18n CLI, streaming JSONL/CSV input paths, a `rolodexter` NPM CLI, CSV dependencies, ESM and CommonJS exports, Python-shaped root/core/i18n package exports, publish-safe package metadata, and bumped the JS package to `2.8.1`.
  - Done: matched audited Python parity cases for fuzzy confidence, reply-to/owner fuzzy drift, generated fuzzy edge cases, nickname parsing, Python `nameparser` title/suffix cases, list/object stringification, duplicate collision equality, 7-digit US local phone normalization and national formatting, cross-country phone match behavior, `MappingSchema.default_region`, JSONL CLI formatting and quarantine diagnostics, argparse-style abbreviations, explicit boolean flag values, `--` handling, leading-plus numeric args, invalid-choice/type exits, sampled argparse-style CLI usage failures, ragged CSV rows, JSON parser diagnostics, class/instance normalizer calls, and DataFrame-like adapter column renaming/normalization.
  - Done: tightened the emitted TypeScript declarations so packed declarations no longer advertise camelCase phone/i18n/helper exports, camelCase option aliases, object-shape constructors, array `map_dataframe`, or `cli.d.ts`.
  - Done: added opt-in JS warning observability for mapper/schema/DataFrame warnings while preserving Python-like default silence.
  - Done: matched Python-style closed-stdout behavior for the NPM CLIs by reporting the same broken stdout flush diagnostic shape and exit `120` when downstream readers close early.
  - Done: matched the final readiness-pass parity cases for Python dataclass-like frozen errors, `MappingResult.get_match()`, name/address casing drift, incoming-list dedupe, numeric value-shape matching, option-looking CLI value handling, JSONL/full-JSON diagnostics, CSV surplus/unclosed-row behavior, i18n language parsing, and materialization-limit ordering.
  - Done: isolated the cached-language test from the real user cache directory so the Python suite no longer hangs on restricted Windows cache paths.
  - Done: matched stricter API-surface parity for Python/JS submodule `__all__`, alphabetic non-phone parsing, 7-digit US local phone possibility, object-shaped constructor rejection messages, and `rolodexter.i18n.main()` arity.
  - Done: broadened runtime API parity again for normalizer edge cases, manually constructed `PhoneNumber` display helpers, `FieldMatch.service`, and public model constructor arity TypeErrors for too-few and too-many positional arguments.
  - Done: broadened public registry/strategy parity by matching `PatternRegistry` positional arguments, missing lookup return values, verified `PatternRegistry` string representation, `MappingSchema.matches.get()` missing values, and match-strategy constructor arity TypeErrors.
  - Done: tightened public i18n helper parity by returning `null` for missing `load_cached()` values and rejecting extra positional `generate_language()` arguments before any generation path runs.
  - Done: tightened mapper runtime shape parity for non-string schema headers, missing required mapper method args, primitive option bags, and array payload rejection.
  - Done: tightened CLI parity for Python JSON constants (`NaN`/`Infinity`), CSV file line endings, clean quarantine file side effects, and Python-style string repr quote selection in explanations.
  - Done: closed final subagent-audited NPM parity gaps for public phone helper arity/non-string/wrong-object edges, `PhoneNumberMatcher` null/bad-limit behavior, `PhoneNumberMatch` string form, `MappingSchema.apply()` errors, mapper constructor/option/cache-helper errors, `PatternRegistry` invalid shapes, non-extensible public model objects, fixed-field `to_dict()` serialization, i18n import side effects, JS keyword-equivalent `generate_language()` options, empty i18n generation warnings, i18n worker parallelism, `-.5` CLI value parsing, and optional generation-only NPM dependencies.
  - Done: promoted parity evidence from scratch files into tracked `scripts/` probes, wired `npm run test:parity` into CI/NPM publish checks, added a Python/NPM version parity check, and removed the unused `csv-parse` production dependency.
  - Verification: `npm run typecheck`, parity probe syntax checks, `npm test` with 56 tests, and `npm run test:parity` passed with matching `2.8.1` versions and zero mapper/API and CLI mismatches; `npm publish --dry-run` passed for `rolodexter@2.8.1`; full `npm audit --json` reported 0 vulnerabilities; `npm pack --dry-run --json` produced a 407.1 kB packed / 1.9 MB unpacked tarball with 24 files; fresh throwaway installs from the packed tarball worked for ESM import, CommonJS require, Python-shaped root/core/i18n exports, i18n `load_cached()`/`generate_language()` parity edges, `npx rolodexter fields`, and `npx rolodexter-i18n --list`, including a cache-only install with `--omit=optional`; `prepack` now runs parity so local pack/publish cannot skip it accidentally; CI now tests Node 20 and Node 24; Python gates passed (`ruff`, `mypy`, 905 pytest cases, 93.93% coverage); and Python build/twine checks passed for the `2.8.1` sdist and wheel.

## Verified Next Work

No verified follow-up fixes remain from the consolidated GPT audit.

## Intentionally Not Kept

- Replace email/date/URL parsing with new dependencies: useful to evaluate later, but not necessary for the verified bug fixes above and would expand the dependency surface.
- Rebuild field metadata/social-platform registries: valid design cleanup, but too broad for this autonomous pass.
- Delete pre-existing untracked `cb_better_01.md` and `cb_issues_01.md`: verified as untracked scratch files, but they predated this turn and were left untouched.
