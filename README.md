<div align="center">

<img src="https://res.cloudinary.com/dicsgc72e/image/upload/v1772425436/ezgif-42b0a21d2af73c08_iwq3aa.gif" alt="RoloDexter" width="600" />

**The universal contact field mapper.**

Route messy, inconsistent contact data from *any* source to a clean, canonical schema.

[![CI](https://img.shields.io/github/actions/workflow/status/Lunarwerx/rolodexter/ci.yml?label=CI)](https://github.com/Lunarwerx/rolodexter/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/rolodexter)](https://pypi.org/project/rolodexter/)
[![Python](https://img.shields.io/pypi/pyversions/rolodexter)](https://pypi.org/project/rolodexter/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

</div>

---

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

### 🎯 Four-Layer Matching Pipeline

Every field runs through the strategy chain in priority order:

1. **Exact Match** — O(1) lookup against 600+ known aliases across 62 canonical fields
2. **Normalized Match** — handles `CamelCase`, `dot.path`, `space → underscore`, and similar variations
3. **Fuzzy Match** — `rapidfuzz` catches typos like `"phne_nmbr"` → `phone`
4. **Heuristic Match** — regex detects emails, phones, URLs, postal codes by *data shape*

### 📊 Confidence Scoring

Every match comes with a confidence score (0.0–1.0):

```python
match = mapper.identify("fname")
# FieldMatch(original='fname', canonical='first_name', confidence=1.0, strategy='exact')

match = mapper.identify("phne")
# FieldMatch(original='phne', canonical='phone', confidence=0.85, strategy='fuzzy')

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

Fields like `tags` are automatically list-normalised — comma-separated strings, JSON arrays, and Python lists all collapse to a clean list:

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

### 📦 Batch & Streaming

```python
results = mapper.map_batch([contact1, contact2, contact3, ...])

# Constant-memory streaming for huge CSV/JSONL exports:
import csv
with open("contacts.csv") as fh:
    for result in mapper.map_stream(csv.DictReader(fh)):
        save(result.normalized)
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

# See exactly how a header resolves
rolodexter explain "Job Titel" --value CEO
# 'Job Titel' -> job_title [fuzzy, conf=0.70]

rolodexter fields        # list every canonical field
```

### 🛡️ Strict Mode, Warnings & Confidence

```python
# Non-fatal issues are reported, never silent:
result = mapper.map_payload({"mobile": "not a phone"})
print(result.warnings)
# ("'mobile': phone value 'not a phone' could not be normalized to E.164 ...",)

# Demand high-confidence mappings; fail loudly on any problem:
mapper = ContactMapper(strict=True, confidence_threshold=0.8)

print(result.explain())   # human-readable resolution + warnings
```

### 🗺️ Compile a Schema Once

```python
schema = mapper.compile_schema(["First Name", "Mobile Phone", "Org"])
schema.column_map()         # {'First Name': 'first_name', 'Mobile Phone': 'phone', 'Org': 'company'}
schema.apply(row)           # reuse the resolved plan per row
```

### 📈 Rich Diagnostics

```python
result = mapper.map_payload(data)

print(result.match_rate)        # 0.857
print(result.matched_count)     # 6
print(result.unmatched_count)   # 1
print(result.get_all_phones())  # ['+16502530000']
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
| `compile_schema(headers)`                                 | Resolve headers once → reusable `MappingSchema`   |
| `map_dataframe(df)`                                       | Rename/normalize a pandas DataFrame               |
| `clear_cache()`                                           | Clear cached header-resolution verdicts           |
| `cache_info()`                                            | Inspect header cache size/configuration           |
| `registry`                                                | Access the underlying `PatternRegistry`           |

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
| `explain()`         | `str`                    | Human-readable resolution + warnings summary      |
| `to_dict()`         | `dict`                   | Full JSON-serializable report                     |

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
git clone https://github.com/Lunarwerx/rolodexter.git
cd rolodexter
pip install -e ".[dev]"
pytest
```

## License

MIT — see [LICENSE](LICENSE).
