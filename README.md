<div align="center">

<img src="https://res.cloudinary.com/dicsgc72e/image/upload/v1772425436/ezgif-42b0a21d2af73c08_iwq3aa.gif" alt="RoloDexter" width="600" />

**The universal contact field mapper.**

Route messy, inconsistent contact data from *any* source to a clean, canonical schema.

[![CI](https://img.shields.io/github/actions/workflow/status/LunarWerxs/RoloDexter/ci.yml?label=CI)](https://github.com/LunarWerxs/RoloDexter/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/rolodexter)](https://pypi.org/project/rolodexter/)
[![npm](https://img.shields.io/npm/v/rolodexter)](https://www.npmjs.com/package/rolodexter)
[![Python](https://img.shields.io/pypi/pyversions/rolodexter)](https://pypi.org/project/rolodexter/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

</div>

---

RoloDexter is an open-source Python and TypeScript library that maps messy,
inconsistent contact field names, like HubSpot's `firstname` or a CSV's
`Column A`, onto one canonical schema of 62 fields. It resolves each header
through a four-layer pipeline, exact, normalized, fuzzy, heuristic, scores
every match's confidence, and normalizes the matched values so the output is
ready to store.

## Packages In This Repository

RoloDexter is maintained as a dual-package repository:

| Ecosystem | Package | Source | Package metadata | Publish target |
| --------- | ------- | ------ | ---------------- | -------------- |
| Python | `rolodexter` | [`src/rolodexter`](src/rolodexter) | [`pyproject.toml`](pyproject.toml) | [PyPI](https://pypi.org/project/rolodexter/) |
| JavaScript / TypeScript | `rolodexter` | [`packages/js/src`](packages/js/src) | [`packages/js/package.json`](packages/js/package.json) | [npm](https://www.npmjs.com/package/rolodexter) |

The Python package remains the canonical implementation and owns the shared
`patterns.json` alias table. The NPM package lives under `packages/js`, syncs
that alias table during build, and has its own README, TypeScript sources,
tests, package metadata, and publish workflow.

## The Problem

Every CRM, email platform, and CSV export uses different field names for the same data:

| Service    | First Name   | Phone             | Company                 |
| ---------- | ------------ | ----------------- | ----------------------- |
| HubSpot    | `firstname`  | `mobilephone`     | `company`               |
| Salesforce | `FirstName`  | `MobilePhone`     | `Company`               |
| Mailchimp  | `FNAME`      | `PHONE`           | `COMPANY`               |
| Google CSV | `Given Name` | `Phone 1 - Value` | `Organization 1 - Name` |
| Random CSV | `Column A`   | `Column B`        | `Column C`              |

## The Solution

```python
from rolodexter import ContactMapper

mapper = ContactMapper()

result = mapper.map_payload({
    "fname": "jane",
    "surname": "doe",
    "mobile": "+1-650-253-0000",
    "employer": "Tech Corp",
    "Column 1": "jane.doe@example.com",  # auto-detected by value shape
})

print(result.normalized)
# {
#     "first_name": "Jane",
#     "last_name": "Doe",
#     "phone": "+16502530000",
#     "company": "Tech Corp",
#     "email": "jane.doe@example.com"
# }
```

## Installation

### Python

```bash
# Core (phonenumbers + nameparser)
pip install rolodexter

# With fuzzy matching for typo recovery
pip install rolodexter[fuzzy]

# With on-demand i18n cache generation dependencies (40 languages)
pip install rolodexter[i18n-generate]

# Everything
pip install rolodexter[all]

# Development
pip install rolodexter[dev]
```

### JavaScript / TypeScript

```bash
npm install rolodexter
```

The NPM package source lives in `packages/js`. For local development:

```bash
cd packages/js
npm install
npm test
```

## Features

### 🔎 Pre-Flight Profiling: "What Will I Lose?"

```bash
# See what a file maps to before you write anything
rolodexter profile contacts.csv

# Same report as JSON, for scripting
rolodexter profile contacts.csv --json

# Skip value-level normalization for a faster pass on a big file
rolodexter profile huge.csv --no-normalize --max-rows 5000
```

`profile` never writes mapped output. It reports the match rate, which
canonical fields got populated, which headers went unmapped, and categorized
warning counts, so you can see what an import will drop or flag before
running `map` for real. It accepts the same `--region`, `--languages`,
`--min-confidence`, and `--override` flags as `map`.

### 🎯 Four-Layer Matching Pipeline

Every field runs through the strategy chain in priority order:

1. **Exact Match**: O(1) lookup against 600+ known aliases across 62 canonical fields
2. **Normalized Match**: handles `CamelCase`, `dot.path`, `space → underscore`, and similar variations
3. **Fuzzy Match**: `rapidfuzz` catches typos like `"phne_nmbr"` → `phone`
4. **Heuristic Match**: regex detects emails, phones, URLs, postal codes by *data shape*

### 📊 Confidence Scoring

Every match comes with a confidence score (0.0–1.0):

```python
match = mapper.identify("fname")
# FieldMatch(original='fname', canonical='first_name', confidence=1.0, strategy='exact')

match = mapper.identify("phne")
# FieldMatch(original='phne', canonical='phone', confidence=0.7, strategy='fuzzy')

match = mapper.identify("Column X", value="jane@test.com")
# FieldMatch(original='Column X', canonical='email', confidence=0.6, strategy='heuristic')
```

### Per-Caller Field Overrides

For vendor-specific or account-level field names that won't be in the standard alias table:

```python
mapper = ContactMapper(
    overrides={
        "MMERGE6": "company",   # Mailchimp custom merge field
        "cf_lead_score": "tags",
    }
)
```

### 📱 Phone Extraction

```python
# Extract phones embedded in arbitrary string values
result = mapper.map_payload(
    {"notes": "call me at +1-650-253-0000 or +44 20 7946 0958"},
    extract_embedded_phones=True,
)
print(result.get_all_phones())
# ['+16502530000', '+442079460958']
```

### 🗂️ Tags / List Fields

Fields like `tags` are automatically list-normalised: comma-separated strings, JSON arrays, and Python lists all collapse to a clean list:

```python
result = mapper.map_payload({"tags": "vip, newsletter, beta"})
print(result.normalized["tags"])
# ['vip', 'newsletter', 'beta']
```

### 🌍 On-Demand i18n (40 Languages)

English ships by default. Install `rolodexter[i18n-generate]` to generate any
of 40 supported language caches with the i18n CLI or API, then pass those
languages to `ContactMapper`; runtime loading is cache-only and never
translates during mapper construction:

```python
from rolodexter import ContactMapper

# Load Spanish aliases from a generated cache
mapper = ContactMapper(languages=["es"])
result = mapper.map_payload({"correo_electronico": "juan@example.com"})
print(result.normalized["email"])  # juan@example.com
```

```bash
# CLI: generate and cache all 40 languages
python -m rolodexter.i18n

# Or specific languages
python -m rolodexter.i18n --languages es,fr,de

# Bound network behavior during generation
python -m rolodexter.i18n --languages es,fr --timeout 10 --retries 1 --workers 4

# List supported languages
python -m rolodexter.i18n --list
```

Supported: Spanish, French, German, Portuguese, Italian, Dutch, Polish, Romanian, Turkish, Russian, Japanese, Chinese (Simplified), Korean, Arabic, Hindi, Swedish, Danish, Norwegian, Finnish, Czech, Ukrainian, Greek, Hungarian, Thai, Vietnamese, Indonesian, Malay, Hebrew, Bulgarian, Croatian, Slovak, Slovenian, Serbian, Lithuanian, Latvian, Estonian, Catalan, Filipino, Swahili, Afrikaans.

### 🧹 Value Normalization

Automatic cleanup on matched fields:

- **Phone** → E.164 format via libphonenumber (`+16502530000`)
- **Email** → lowercase, trimmed
- **Names** → title case with particle awareness (`"jane van der berg"` → `"Jane van der Berg"`)
- **Addresses** → excess whitespace collapsed, title-cased
- **Tags** → normalized to `list[str]`
- **Dates** → ISO-8601 for `birthday`, `created_at`, `updated_at`, `last_contacted`. Ambiguous values (`03/04/2024`, a two-digit year) are left unchanged and reported as a warning instead of guessed.
- **Country** → ISO 3166-1 alpha-2 (`"Deutschland"` → `"DE"`)
- **State / Province** → 2-letter US state or Canadian province code (`"california"` → `"CA"`)

### 📦 Batch & Streaming

```python
results = mapper.map_batch([contact1, contact2, contact3, ...])

# Constant-memory streaming for huge CSV/JSONL exports:
import csv
with open("contacts.csv") as fh:
    for result in mapper.map_stream(csv.DictReader(fh)):
        save(result.normalized)

# Preview import readiness without retaining mapped rows:
profile = mapper.profile(contacts, max_rows=1_000)
print(profile.explain())
```

### 🐼 DataFrames

```python
import pandas as pd
from rolodexter import ContactMapper

df = pd.read_csv("hubspot_export.csv")
clean = ContactMapper().map_dataframe(df)   # pip install rolodexter[pandas]
# Columns renamed to canonical fields, values normalized, unmatched columns kept.
```

### 🖥️ Command Line

```bash
# Map a CSV/JSON/JSONL export to the canonical schema
rolodexter map contacts.csv -o clean.csv --region US

# Stream JSON Lines, drop low-confidence guesses, fail loudly
rolodexter map export.jsonl --min-confidence 0.8 --strict -o out.jsonl

# JSON/CSV output paths are bounded; JSONL output remains streaming
rolodexter map huge.jsonl --format jsonl --max-materialized-rows 100000

# Keep processing after bad rows, preserving failures in a JSONL quarantine file
rolodexter map export.jsonl --strict --on-error quarantine -o clean.jsonl

# Carry unmapped columns through instead of dropping them, and drop rows
# that share an identity key (email/phone/source id) with an earlier row
rolodexter map contacts.csv --keep-unmapped --dedupe -o clean.csv

# Force a vendor-specific column to a canonical field
rolodexter map contacts.csv --override "MMERGE3=full_address" -o clean.csv

# Save the resolved header plan, then replay it on a later import so columns
# route identically even after a patterns.json change (a mapping lockfile)
rolodexter map jan.csv --schema-out plan.json -o jan-clean.csv
rolodexter map feb.csv --schema-in plan.json  -o feb-clean.csv

# See exactly how a header resolves
rolodexter explain "Job Titel" --value CEO
# 'Job Titel' -> job_title [fuzzy, conf=0.70]

rolodexter --version
rolodexter fields        # list every canonical field
```

### 🛡️ Strict Mode, Warnings & Confidence

```python
# Non-fatal issues are reported, never silent:
result = mapper.map_payload({"mobile": "not a phone"})
print(result.warnings)
# ("'mobile': phone value 'not a phone' could not be normalized to E.164 ...",)

# Each warning is a str subclass carrying its category, for grouping by code
# instead of matching substrings of the message text:
print(result.warnings[0].category)   # 'phone_normalization'

# Demand high-confidence mappings; fail loudly on any problem:
mapper = ContactMapper(strict=True, confidence_threshold=0.8)

print(result.explain())   # human-readable resolution + warnings
```

### 🗺️ Compile a Schema Once

```python
schema = mapper.compile_schema(["First Name", "Mobile Phone", "Org"])
schema.column_map()         # {'First Name': 'first_name', 'Mobile Phone': 'phone', 'Org': 'company'}
schema.apply(row)           # reuse the resolved plan per row

# Save the plan and replay it later so columns route identically, even after
# a patterns.json update (the "map --schema-out" / "--schema-in" CLI flags
# do this for you):
plan = schema.to_dict()
schema2 = MappingSchema.from_dict(plan, mapper)
```

### 📈 Rich Diagnostics

```python
result = mapper.map_payload(data)

print(result.match_rate)        # 0.857
print(result.matched_count)     # 6
print(result.unmatched_count)   # 1
print(result.get_all_phones())  # ['+16502530000']
print(result.get_all_emails())  # ['jane@example.com']
print(result.get_identity_keys())
# ['email:jane@example.com', 'phone:+16502530000', 'source:hubspot:123']
print(result.to_dict())         # Full JSON-serializable report
```

### 🔢 Nested Payload Support

```python
# Flatten one level of nesting with depth=2
result = mapper.map_payload(
    {"contact": {"fname": "Jane", "lname": "Doe"}},
    depth=2,
)
# Accesses "contact.fname" and "contact.lname"
```

## API Reference

### `ContactMapper`

```python
ContactMapper(
    *,
    patterns=None,             # Custom pattern dict (overrides built-in)
    patterns_path=None,        # Path to a custom patterns.json file
    normalize=True,            # Apply value normalization after mapping
    strategies=None,           # Override the default strategy pipeline
    languages=None,            # None=English only | "es" | ["es","fr"] | "all"
    overrides=None,            # Extra alias→canonical mappings {"MMERGE6": "company"}
    default_region="US",       # ISO-3166 region for phone parsing/E.164
    strict=False,              # Raise NormalizationError on any warning
    confidence_threshold=0.0,  # Drop matches below this confidence to unmapped
    header_cache_max_size=4096,# Bound header-resolution cache; None=unbounded
)
```

**Methods:**

| Method                                                    | Description                                       |
| --------------------------------------------------------- | ------------------------------------------------- |
| `identify(header, *, value)`                              | Resolve a single header to a `FieldMatch`         |
| `map_payload(payload, *, depth, ...)`                     | Normalize an entire dict → `MappingResult`        |
| `map_batch(payloads, *, ...)`                             | Process a list of payloads → `list[MappingResult]`|
| `map_stream(iterable, *, ...)`                            | Lazily yield results (constant memory)            |
| `profile(iterable, *, max_rows, ...)`                     | Aggregate import-readiness diagnostics            |
| `compile_schema(headers)`                                 | Resolve headers once → reusable `MappingSchema`   |
| `map_dataframe(df)`                                       | Rename/normalize a pandas DataFrame               |
| `clear_cache()`                                           | Clear cached header-resolution verdicts           |
| `cache_info()`                                            | Inspect header cache size/configuration           |
| `registry`                                                | Access the underlying `PatternRegistry`           |

`map_dataframe()` guarantees unique output labels. It skips reserved
`<canonical>__N` names when an unmatched source column already uses one, and
rejects duplicate input labels because they cannot be renamed without
ambiguity.

### `FieldMatch`

```python
FieldMatch(
    original='fname',
    canonical='first_name',
    confidence=1.0,
    strategy='exact',      # 'exact' | 'normalized' | 'fuzzy' | 'heuristic' | 'none'
    is_matched=True,
)
```

### `MappingResult`

| Attribute / Method  | Type                     | Description                                       |
| ------------------- | ------------------------ | ------------------------------------------------- |
| `normalized`        | `dict`                   | Canonical key → cleaned value                     |
| `unmapped`          | `dict`                   | Fields that couldn't be resolved                  |
| `field_matches`     | `tuple[FieldMatch, ...]` | Full match detail for every input field           |
| `match_rate`        | `float`                  | Fraction of fields successfully matched           |
| `matched_count`     | `int`                    | Count of matched fields                           |
| `unmatched_count`   | `int`                    | Count of unmatched fields                         |
| `warnings`          | `tuple[str, ...]`        | Non-fatal issues (failed E.164, dropped matches)  |
| `get_match(header)` | `FieldMatch \| None`     | O(1) lookup of the match for an input header       |
| `get_all_phones()`  | `list[str]`              | All phone values across all phone-adjacent fields |
| `get_all_emails()`  | `list[str]`              | All email values, flattened and deduplicated      |
| `get_identity_keys()` | `list[str]`            | Stable email/phone/source keys for deduplication  |
| `explain()`         | `str`                    | Human-readable resolution + warnings summary      |
| `to_dict()`         | `dict`                   | Full JSON-serializable report                     |

### `MappingProfile`

`ContactMapper.profile()` consumes any iterable in constant memory and reports
rows and fields seen, aggregate match rate, canonical-field counts, unmapped
header counts, strategy usage, and categorized warnings. Use `max_rows` for a
bounded preview; the next iterator item is left untouched.

```python
profile = mapper.profile(rows, max_rows=1_000, confidence_threshold=0.8)
profile.match_rate
profile.warning_counts
profile.to_dict()   # JSON-ready
profile.explain()   # compact report for logs or a CLI
```

### `CanonicalField`

Enum of all 62 canonical fields. Inherits from `str` for JSON compatibility:

```python
from rolodexter import CanonicalField

assert CanonicalField.EMAIL == "email"
assert CanonicalField.PHONE.value == "phone"
```

<details>
<summary>All 62 canonical fields (+ the <code>unknown</code> sentinel)</summary>

`first_name` · `last_name` · `full_name` · `middle_name` · `nickname` · `prefix` · `suffix` · `email` · `phone` · `home_phone` · `work_phone` · `fax` · `whatsapp` · `website` · `company` · `job_title` · `department` · `industry` · `address_line1` · `address_line2` · `city` · `state` · `postal_code` · `country` · `full_address` · `linkedin` · `twitter` · `facebook` · `instagram` · `github` · `youtube` · `tiktok` · `discord` · `telegram` · `lead_status` · `lifecycle_stage` · `email_opt_out` · `tags` · `source` · `utm_parameters` · `score` · `owner` · `birthday` · `age` · `created_at` · `updated_at` · `last_contacted` · `revenue` · `currency` · `message` · `subject` · `company_size` · `notes` · `metadata` · `gender` · `timezone` · `language_preference` · `referrer_url` · `source_id` · `source_service` · `subscribed` · `verified` · `unknown`

</details>

### Custom Patterns

```python
custom = {
    "fields": {
        "first_name": ["fname", "given", "nombre"],
        "loyalty_tier": ["tier", "vip_level", "membership"],
    }
}

mapper = ContactMapper(patterns=custom)
```

Custom pattern data is validated when the registry is constructed. `fields`
must be an object whose values are lists of non-empty aliases; malformed files
raise `PatternLoadError` with the failing section instead of partially building
an index.

## Repository Layout

```text
rolodexter/
├── pyproject.toml              # Python/PyPI package metadata
├── src/rolodexter/             # Python package source
├── tests/                      # Python tests
├── packages/js/package.json    # JavaScript/NPM package metadata
├── packages/js/src/            # TypeScript package source
├── packages/js/test/           # JavaScript package tests
└── scripts/                    # Cross-language release/parity probes
```

## Python Package Architecture

```
src/rolodexter/
├── __init__.py      # Public API
├── __main__.py      # CLI: rolodexter map / explain / fields
├── core.py          # ContactMapper, PatternRegistry, strategies, normalizers
├── _phone.py        # E.164 phone parser (wraps libphonenumber)
├── i18n.py          # On-demand i18n generator (40 languages, cached)
└── patterns.json    # Master alias table (600+ aliases, 62 canonical fields)
```

## Contributing

```bash
git clone https://github.com/LunarWerxs/RoloDexter.git
cd rolodexter
pip install -e ".[dev]"
pytest
```

## FAQ

**Is RoloDexter free?**
Yes. RoloDexter is MIT-licensed and free to use in commercial and open-source
projects, both the Python package on PyPI and the JavaScript/TypeScript
package on npm. There is no paid tier, account, or API key involved: it
installs as a normal dependency and runs entirely inside your own process.

**Does it work offline?**
Yes, for field mapping and value normalization, both run entirely locally
with no network calls. The one exception is the optional i18n alias
generator (`rolodexter[i18n-generate]`), which calls Google Translate to
build language caches; that step is explicit, one-time, and the caches it
produces are then loaded offline with no further network access.

**What are the system requirements?**
The Python package needs Python 3.10 or newer (tested through 3.14) plus
its two core dependencies, `phonenumbers` and `nameparser`; optional extras
add `rapidfuzz` for fuzzy matching, `pandas` for DataFrame support, or
translation libraries for i18n generation. The JavaScript/TypeScript package
needs Node.js 20 or newer. Neither requires a database or server.

**How is it different from Zapier's or Make's field mapping?**
Zapier and Make connect two apps by having you manually map each field
between them for every workflow you build, by hand, per pill. RoloDexter
instead resolves headers automatically against a built-in table of 600+
aliases across 62 canonical fields, so a HubSpot export and a random CSV
both land on the same schema without you wiring each column yourself.

**How is it different from an ETL platform like Talend or Alteryx?**
Talend and Alteryx are full ETL platforms with schema mapping as one feature
among many; Talend Data Fabric alone is priced for enterprise budgets,
commonly six figures a year. RoloDexter is a free, MIT-licensed library that
does one job, contact field mapping and value normalization, embedded
directly in your own Python or Node code with no platform to manage.

**How is it different from using `phonenumbers` or `nameparser` directly?**
`phonenumbers` and `nameparser`, two libraries RoloDexter depends on, each
solve one field type: phone parsing and name parsing. Neither tells you
which of fifty CSV columns is a phone number, or that `mobilephone` and
`mobile` both mean `phone`. RoloDexter runs header identification across all
62 canonical fields first, then hands the matched values to libraries like
these for normalization.

**What data formats does it support?**
CSV, JSON, and JSON Lines files through the CLI (`rolodexter map`), plus
plain Python dicts, lists, and streaming iterables through the library API,
and pandas DataFrames with the `pandas` extra installed. Output can be
written as CSV, JSON, or streamed JSONL, and a `--schema-out`/`--schema-in`
lockfile replays a resolved header plan on later imports.

**Is my data sent anywhere?**
No. Field mapping and value normalization run entirely inside your own
Python or Node process; RoloDexter makes no network calls and has no server
component. The only exception is the optional, explicitly-invoked i18n
alias generator, which sends field names, not your contact data, to Google
Translate to build a local language cache.

## License

MIT, see [LICENSE](LICENSE).

---

Made by [LunarWerx Studios](https://lunarwerx.com), the team also behind
[RepoYeti](https://repoyeti.com), [AgentHydra](https://agenthydra.lunarwerx.com),
and [SageThumbs](https://sagethumbs.lunarwerx.com).
