# Changelog

All notable changes to **rolodexter** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.6.6] — 2026-05-23

### Fixed

- **`_merge()` deduplication** — when multiple aliases on a payload (e.g. `phone` and `mobile`) carry the same normalized value, the result no longer contains duplicate list entries.
- **`PatternRegistry._all_aliases` deduplication** — aliases that appeared in both the `fields` table and expansion rules (e.g. `"first"`), or across English + i18n layers, are no longer counted multiple times.  Cuts the fuzzy-match scan list to unique entries.
- **`HeuristicMatchStrategy` phone false-positives** — bare-digit strings that match the loose phone regex are now confirmed against libphonenumber's `is_possible_number`, so 10-digit numeric IDs are no longer misclassified as phones.
- **`NameNormalizer._ensure_prefixes` thread-safety** — the one-time `nameparser` prefix patch is now guarded by a double-checked lock.  The i18n CLI's worker pool could previously race on first use.
- **`_phone._wrap()` italian leading zero** — reads `national_number` directly while preserving `italian_leading_zero` (e.g. Italian numbers).
- **i18n `_translate_batch`** logs warnings on batch + per-phrase failures instead of swallowing them silently.
- **i18n `generate_language`** no longer writes an empty cache file when zero translations succeed and no prior cache exists — the next invocation can retry instead of short-circuiting.
- **i18n `_package_i18n_dir`** probe uses `unlink(missing_ok=True)` to survive transient races (AV scanners, parallel probes).

### Performance

- **`FuzzyMatchStrategy`** caches the length-filtered alias list across calls instead of rebuilding it per header.  Invalidates only when the alias set grows.
- **`NormalizedMatchStrategy` / `FuzzyMatchStrategy`** use module-level compiled regexes instead of recompiling per call.

### Removed

- 11 redundant aliases from `patterns.json` that the expansion engine already generates (`primary_email`, `personal_email`, `primary_phone`, `secondary_phone`, `personal_phone`, `business_fax`, `mailing_city`, `mailing_state`, `mailing_zip`, `mailing_country`, `personal_website`).  Total aliases: 615 → 604; no behavior change.

## [2.6.5] — 2026-03-01

### Added

- **`ListNormalizer`** — tags and other list-adjacent fields now auto-normalise comma/semicolon-separated strings, JSON arrays, and Python lists to `list[str]`.
- **`MappingResult.get_all_phones()`** — returns all phone values from `normalized` (across `phone`, `home_phone`, `work_phone`, `fax`, `whatsapp`), deduplicated and in order.
- **`extract_embedded_phones` parameter on `map_payload()`** — when `True`, scans all non-phone string values with `PhoneNumberMatcher` and merges discovered numbers into the result.
- **`overrides` parameter on `ContactMapper()` and `PatternRegistry()`** — caller-supplied `{alias: canonical}` dict applied before any strategy runs.  Intended for vendor-specific merge fields (e.g. Mailchimp `MMERGE*`).
- **`depth` parameter on `map_payload()` and `map_batch()`** — flatten nested payloads up to `depth` levels (default `1`; max `5`).
- Exported `ListNormalizer` from `rolodexter.__init__`.

### Fixed

- `_flatten()` docstring incorrectly stated the depth=2 joiner was `_`; it is `.`  (functionality was always correct).
- `# type: ignore[import-untyped]` was attached to the wrong line of the multi-line `deep_translator` import in `i18n.py`.
- All ruff lint (`RUF012`, `E402`, `F401`, `F811`) and format violations resolved.

### Removed

- **Service-specific override system** — `service_overrides` section removed from `patterns.json`.  `service` / `available_services` properties and `_apply_service_overrides()` removed from `PatternRegistry`.  The generic `overrides` dict supersedes this.

## [2.5.0] — 2025-07-10

### Changed

- **`_phone.py` — complete rewrite** using `phonenumbers` (Google's libphonenumber).
  Deleted ~510 lines of manual ITU metadata (`_CC`, `_REGION`, `_NO_TRUNK`,
  `_MOBILE_PREFIXES`, `_TOLL_FREE_PREFIXES`, `_PREMIUM_PREFIXES`), 19 grouping
  pattern constants, `_FORMAT_TEMPLATES` dict (45 countries), compiled regexes
  (`_E164_RE`, `_STRIP_RE`, `_VANITY_MAP`, `_EXT_RE`, `_TEL_URI_RE`), and all
  manual parsing / formatting logic.  Replaced with a thin wrapper (~280 lines)
  delegating to `phonenumbers` for parsing, validation, E.164 / international /
  national formatting, number-type detection, number matching, and text extraction.
- **`NameNormalizer`** — replaced 24-entry `_PARTICLES` frozenset and manual
  capitalize logic with `nameparser.HumanName`.  Added 9 extra prefixes
  (`ten`, `ter`, `zur`, `zum`, `das`, `des`, `op`, `el`, `af`) via
  `CONSTANTS.prefixes.add()`.  New `parse()` class method returns structured
  `{"title", "first", "middle", "last", "suffix", "nickname"}` dict.
- **`PhoneNormalizer`** — removed regex fallback branch (`_PHONE_STRIP`).
  Now delegates solely to `_phone.format_e164()`.

### Added

- **Hard dependencies**: `phonenumbers>=8.0`, `nameparser>=1.1`.
- `PhoneNumber.is_possible` property (delegates to `is_possible_number()`).
- `NameNormalizer.parse()` — structured name decomposition via `nameparser`.
- Tel: URI pre-processing (RFC 3966) — strips `tel:` scheme, extracts `;ext=`
  extensions, removes `;phone-context=` and other params before delegating to
  `phonenumbers`.
- `00` / `011` international dial-out prefix pre-processing.

### Removed

- All manual phone metadata (~230 calling codes, ~80 country regions, mobile /
  toll-free / premium prefix tables, 45-country format templates).
- Manual `_PARTICLES` frozenset in `NameNormalizer`.
- `_PHONE_STRIP` regex fallback in `PhoneNormalizer`.

## [1.0.0] — 2026-01-01

### Added

- **ContactMapper** — multi-layer strategy pipeline (exact → normalized → fuzzy → heuristic).
- **PatternRegistry** — O(1) indexed lookup over 400+ field aliases across 50+ canonical fields.
- **4 matching strategies** — `ExactMatchStrategy`, `NormalizedMatchStrategy`, `FuzzyMatchStrategy`, `HeuristicMatchStrategy`.
- **5 value normalizers** — Phone, Email, Name (with surname particle awareness), Address, String.
- **Batch processing** via `mapper.map_batch()`.
- **Confidence scoring** on every match (0.0–1.0).
- **MappingResult diagnostics** — match rate, per-field details, JSON serialisation.
- **CanonicalField enum** — standardised fields with `str` mixin for easy JSON compat.
- Full type annotations + PEP 561 `py.typed` marker.
- Comprehensive test suite.
- GitHub Actions CI + PyPI publish workflows.
