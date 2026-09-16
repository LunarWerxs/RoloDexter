# RoloDexter

> Maps messy CRM/CSV contact headers onto one canonical 62-field schema, offline, in Python and TypeScript.

<!-- odin:about HAND-OWNED above the GENERATED marker. Edit freely; `odin codex about --ingest` carries it back into Odin's Codex. -->

## What it is

RoloDexter is an open-source Python and TypeScript library that maps messy, inconsistent contact field names (HubSpot's 'firstname', a CSV's 'Column A', a Mailchimp merge field) onto one canonical schema of 62 fields. It resolves each header through a four-layer pipeline (exact, normalized, fuzzy, heuristic), scores every match's confidence, and normalizes the matched values (E.164 phones, ISO country/state, title-cased names, ISO-8601 dates) so the output is ready to store. It runs entirely inside the caller's own process with no network calls, no API key, and no server component; the one thing nothing else here does is resolve arbitrary CRM/CSV headers to a shared contact schema automatically instead of requiring per-integration field mapping by hand.

## Things not to forget

_The intricacies worth remembering: the gotchas, the half-built parts, the decisions whose
reason lives nowhere else. Odin never overwrites this section._

- Python and JS deliberately disagree on name-casing for names with an inner capital (DeAngelo, LaToya): Python flattens to 'Deangelo', JS preserves 'DeAngelo'. This is an open, undecided product question affecting 175 divergences, not a bug waiting on a fix - whoever decides must update both _normalizers.py and _names.ts, plus scripts/parity_probe.py, in the same commit. anchors: `docs/todo/TODO.md:15`
- A second TODO section filed under 'Close RoloDexter's coverage gap and turn CI green' tracks the exact same name-casing decision as its sole remaining item, so it is a duplicate that self-resolves (and the file gets deleted) once the casing question is decided - do not treat it as a separate outstanding gap. anchors: `docs/todo/TODO.md:110`
- Fuzzy matching (pipeline layer 3, typo recovery via rapidfuzz) is an optional extra (pip install rolodexter[fuzzy]); without it the import is skipped and matching silently falls back to exact/normalized/heuristic only, so a match rate can drop with no error raised. anchors: `src/rolodexter/_strategies.py:347`
- compile_schema lets a caller resolve a header set once and replay it via --schema-out/--schema-in so later imports route identically - but a saved schema is a frozen plan: if patterns.json changes afterward, replaying the old schema will not pick up the new aliases. anchors: `src/rolodexter/core.py:343`
- Google Translate is only ever called for the optional, explicit i18n-generate step that builds the 39 non-English alias caches; normal runtime mapping does zero network calls and loads a language from the local cache file only, which is the whole basis of the 'no network calls' claim. anchors: `src/rolodexter/i18n.py:629`
- The CLI's --dedupe only compares email/phone/source identity keys (MappingResult.get_identity_keys); a row with only a name and company populated produces zero identity keys and is therefore never deduplicated, always kept even if it is a clear duplicate. anchors: `src/rolodexter/_models.py:359`
- The Python package is canonical and packages/js is a hand-maintained line-for-line parity port (not a transpile): adding a canonical field, match strategy, or normalizer requires editing both _models.py/_strategies.py/_normalizers.py and their packages/js/src/*.ts counterparts, then running sync-patterns.mjs to copy the shared patterns.json - the JSON syncs automatically, the logic does not. anchors: `packages/js/scripts/sync-patterns.mjs:1`
- --on-error quarantine is a deliberate partial-success mode: it keeps a whole file processing while routing failing rows to a separate JSONL file, instead of the default behavior of aborting the run on the first bad row. anchors: `src/rolodexter/__main__.py:413`

<!-- odin:about GENERATED BEGIN - rewritten by `odin codex about --publish`; edit the Codex, not this -->

## What Odin knows about this project

Everything from here down is generated from this project's Codex dossier
(`codex/projects/rolodexter.md` in the Odin clone) and is **rewritten on every publish** -
edit the dossier, not this block. Everything ABOVE the marker is yours.

### At a glance

- **Ships as:** library/crate/package - pip install (PyPI, package `rolodexter`) and npm install (npm, package `rolodexter`); dual Python + TypeScript packages built from one repo, published via GitHub Actions (publish.yml for PyPI, npm-publish.yml for npm)
- **Live at:** https://rolodexter.lunarwerx.com/
- **Written in:** Python (39 files), TypeScript (37 files), JavaScript (6 files)
- **Built with:** NumPy, TypeScript, esbuild, pandas, pytest
- **Package:** `rolodexter` 2.12.0
- **Entry points:** `python_scripts`
- **Tests:** 43 test file(s)
- **CI:** `ci.yml`, `npm-publish.yml`, `publish.yml`
- **Domain:** contact-data, crm-integration, csv-import, field-mapping, phone-normalization, name-parsing, etl
- **Remote:** https://github.com/LunarWerxs/RoloDexter.git

### Architecture

- `src/rolodexter/` - Python package source: ContactMapper/MappingSchema (core.py), header resolution (_mapper.py), match strategies (_strategies.py), value normalizers (_normalizers.py), phone/geo helpers (_phone.py, _geo.py), pattern registry (_patterns.py), i18n generator (i18n.py), and the `rolodexter` CLI (__main__.py)
- `src/rolodexter/patterns.json` - Master alias table (600+ aliases across 62 canonical fields); the Python package owns it, the JS package syncs a copy at build time
- `packages/js/src/` - TypeScript package source: a line-for-line parity port of the Python pipeline (ContactMapper/MappingSchema in index.ts, _strategies.ts, _normalizers.ts, _phone.ts, _geo.ts, _registry.ts, _i18n_cache.ts/_i18n_generate.ts, cli.ts)
- `packages/js/scripts/` - Build/release tooling: build-cjs.mjs (esbuild dual ESM+CJS build), sync-patterns.mjs (copies Python's patterns.json into the JS package), run-tests.mjs, copy-assets.mjs
- `tests/` - Python test suite (pytest), 43 test files across both packages per derived counts
- `packages/js/test/` - JavaScript/TypeScript test suite, run across supported Node versions by run-tests.mjs
- `scripts/` - Cross-language release/parity probes and a sweep script that compares Python and JS output for the same inputs
- `docs/` - GitHub Pages marketing/docs site (index.html, CNAME, sitemap.xml, robots.txt) plus llms.txt/llms-full.txt for AI-crawler consumption and pricing.md
- `.github/` - CI workflows: ci.yml (test/lint), npm-publish.yml and publish.yml (dual PyPI + npm release)

### Features

19 recorded - 19 shipped, 0 partial, 0 planned. Each path is where the feature is DEFINED; the exact lines live in the Codex entry, which `odin codex check` re-verifies and repairs.

**Shipped**

- **Four-layer header matching pipeline** - Resolves each input header to a canonical field through exact, normalized, fuzzy, then heuristic (data-shape) matching, in priority order. - `src/rolodexter/_mapper.py`, `src/rolodexter/_strategies.py`
- **Confidence scoring** - Every header match returns a 0.0-1.0 confidence score and which strategy produced it (exact/normalized/fuzzy/heuristic). - `src/rolodexter/_models.py`
- **Value normalization** - Matched values are cleaned per field type: phone to E.164, email lowercased, names title-cased with particle awareness, addresses whitespace-collapsed, dates to ISO-8601, tags to a list. - `src/rolodexter/_normalizers.py`
- **Pre-flight profiling** - `rolodexter profile` reports match rate, populated/unmapped fields, and categorized warnings for a file before any mapped output is written. - `src/rolodexter/_mapper.py`, `src/rolodexter/__main__.py`
- **Batch and streaming processing** - map_batch processes a list of payloads; map_stream lazily yields results in constant memory for large CSV/JSONL exports. - `src/rolodexter/_mapper.py`
- **Pandas DataFrame support** - map_dataframe renames a DataFrame's columns to canonical fields and normalizes values in place, guaranteeing unique output labels. - `src/rolodexter/core.py`
- **Command-line interface** - `rolodexter map/profile/explain/fields` maps CSV/JSON/JSONL files from the shell with region, language, confidence, and override flags. - `src/rolodexter/__main__.py`
- **Strict mode and confidence-threshold gating** - Callers can demand high-confidence-only matches and raise on any normalization warning instead of silently degrading. - `src/rolodexter/_mapper.py`
- **Quarantine handling for bad rows** - `--on-error quarantine` keeps processing a file while writing failing rows to a separate JSONL file instead of aborting the run. - `src/rolodexter/__main__.py`
- **Schema compile-once / mapping lockfile** - compile_schema resolves a header set once into a reusable MappingSchema; `--schema-out`/`--schema-in` save and replay that plan so later imports route identically even after a patterns.json change. - `src/rolodexter/core.py`
- **Embedded phone number extraction** - Finds and extracts phone numbers embedded inside free-text field values (e.g. a notes field), bounded per field and per payload. - `src/rolodexter/_mapper.py`
- **Per-caller field overrides** - Callers can force specific vendor headers (e.g. a Mailchimp merge-field code) to a canonical field without editing the shared alias table. - `src/rolodexter/_patterns.py`
- **Custom pattern tables** - A ContactMapper can be constructed from a caller-supplied patterns dict or patterns.json file instead of the built-in 600+ alias table, with validation on load. - `src/rolodexter/_patterns.py`
- **Row deduplication via identity keys** - Each mapped result exposes stable email/phone/source identity keys, and the CLI's `--dedupe` flag drops later rows that share one with an earlier row. - `src/rolodexter/_models.py`
- **On-demand i18n alias generation** - Generates and caches header-alias tables for 40 languages via an explicit, one-time CLI/API call; runtime loading of a language is then cache-only with no further network access. - `src/rolodexter/i18n.py`
- **E.164 phone parsing and formatting** - Wraps libphonenumber to parse, validate, and format matched phone values to E.164/international/national forms and detect number type. - `src/rolodexter/_phone.py`
- **Country and state/province normalization** - Normalizes free-text country and state/province values to ISO 3166-1 alpha-2 and 2-letter US/Canadian codes. - `src/rolodexter/_geo.py`
- **Dual Python + TypeScript packages with parity** - The full pipeline is maintained as two packages, a canonical Python implementation and a parity-tested TypeScript port sharing the same alias table, published separately to PyPI and npm. - `packages/js/src/index.ts`
- **explain command** - `rolodexter explain "Header" --value X` prints exactly how one header resolved (strategy, confidence) without processing a file. - `src/rolodexter/__main__.py`

### Where to add a new one

- **a new canonical field** - add it to the CanonicalField enum in _models.py and the parity CanonicalFieldMember table in packages/js/src/_models.ts, add its aliases to patterns.json, then run sync-patterns.mjs so the JS package's copy matches anchors: `src/rolodexter/_models.py`, `packages/js/src/_models.ts`
- **a new match strategy (a fifth pipeline layer)** - subclass MatchStrategy in _strategies.py (Python) and the parallel MatchStrategy in packages/js/src/_strategies.ts, then register it in the default strategy list both packages build anchors: `src/rolodexter/_strategies.py`, `packages/js/src/_strategies.ts`
- **a new value normalizer for a field type** - add a normalizer class and register it in the _FIELD_NORMALIZERS dispatch table (_normalizers.py) and the parity normalizeValue dispatch in packages/js/src/_normalizers.ts anchors: `src/rolodexter/_normalizers.py`, `packages/js/src/_normalizers.ts`
- **a new CLI subcommand** - add a `_cmd_*` handler and wire it into the argparse subparsers built in _build_parser (__main__.py); mirror it in packages/js/src/cli.ts for parity anchors: `src/rolodexter/__main__.py`
- **a new supported i18n language** - add the language code/name to SUPPORTED_LANGUAGES in i18n.py and the parity table in packages/js/src/_i18n_cache.ts, so both the generator and the cache loader recognize it anchors: `src/rolodexter/i18n.py`, `packages/js/src/_i18n_cache.ts`
- **a new normalization warning category** - add a member to WarningCategory in _models.py and raise/emit it from the relevant normalizer anchors: `src/rolodexter/_models.py`

### Gaps and wants

_Withheld: this repository is public, and the gap list is not published outside the private index._
_Read it with `python odin.py codex brief rolodexter` in the Odin clone._

---

_Generated by `odin codex about --publish rolodexter` on 2026-09-16 from a Codex dossier stamped 2026-09-15. Regenerate after the product moves; `odin codex about` reports drift._
<!-- odin:about GENERATED END sha=c46a48af5c12 -->
