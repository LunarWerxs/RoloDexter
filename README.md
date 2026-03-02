<div align="center">

<img src="https://res.cloudinary.com/dicsgc72e/image/upload/v1772425436/ezgif-42b0a21d2af73c08_iwq3aa.gif" alt="RoloDexter" width="600" />

**The universal contact field mapper.**

Route messy, inconsistent contact data from *any* source to a clean, canonical schema.

[![CI](https://img.shields.io/github/actions/workflow/status/L0garithmic/rolodexter/ci.yml?label=CI)](https://github.com/L0garithmic/rolodexter/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/rolodexter)](https://pypi.org/project/rolodexter/)
[![Python](https://img.shields.io/pypi/pyversions/rolodexter)](https://pypi.org/project/rolodexter/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

</div>

---

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

```bash
# Core (phonenumbers + nameparser)
pip install rolodexter

# With fuzzy matching for typo recovery
pip install rolodexter[fuzzy]

# With on-demand i18n translation (40 languages)
pip install rolodexter[i18n]

# Everything
pip install rolodexter[all]

# Development
pip install rolodexter[dev]
```

## Features

### 🎯 Four-Layer Matching Pipeline

Every field runs through the strategy chain in priority order:

1. **Exact Match** — O(1) lookup against 615+ known aliases across 62 canonical fields
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

### � Per-Caller Field Overrides

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

English ships by default. Request any of 40 supported languages and aliases are generated on the fly via Google Translate, then cached so translation only happens once:

```python
from rolodexter import ContactMapper

# Load Spanish aliases on demand
mapper = ContactMapper(languages=["es"])
result = mapper.map_payload({"correo_electronico": "juan@example.com"})
print(result.normalized["email"])  # juan@example.com
```

```bash
# CLI: generate and cache all 40 languages
python -m rolodexter.i18n

# Or specific languages
python -m rolodexter.i18n --languages es,fr,de

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

### 📦 Batch Processing

```python
results = mapper.map_batch([contact1, contact2, contact3, ...])
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
    patterns=None,        # Custom pattern dict (overrides built-in)
    patterns_path=None,   # Path to a custom patterns.json file
    normalize=True,       # Apply value normalization after mapping
    strategies=None,      # Override the default strategy pipeline
    languages=None,       # None=English only | "es" | ["es","fr"] | "all"
    overrides=None,       # Extra alias→canonical mappings {"MMERGE6": "company"}
)
```

**Methods:**

| Method                                                    | Description                               |
| --------------------------------------------------------- | ----------------------------------------- |
| `identify(header, *, value)`                              | Resolve a single header to a `FieldMatch` |
| `map_payload(payload, *, depth, extract_embedded_phones)` | Normalize an entire dict                  |
| `map_batch(payloads, *, depth)`                           | Process a list of payloads                |
| `registry`                                                | Access the underlying `PatternRegistry`   |

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
| `get_match(header)` | `FieldMatch \| None`     | Look up the match for a specific input header     |
| `get_all_phones()`  | `list[str]`              | All phone values across all phone-adjacent fields |
| `to_dict()`         | `dict`                   | Full JSON-serializable report                     |

### `CanonicalField`

Enum of all 62 canonical fields. Inherits from `str` for JSON compatibility:

```python
from rolodexter import CanonicalField

assert CanonicalField.EMAIL == "email"
assert CanonicalField.PHONE.value == "phone"
```

<details>
<summary>All 62 canonical fields</summary>

`first_name` · `last_name` · `full_name` · `email` · `phone` · `home_phone` · `work_phone` · `fax` · `whatsapp` · `address` · `address_line_2` · `city` · `state` · `postal_code` · `country` · `company` · `job_title` · `department` · `website` · `linkedin` · `twitter` · `instagram` · `facebook` · `birthday` · `gender` · `language` · `timezone` · `currency` · `tags` · `notes` · `source` · `source_id` · `source_service` · `subscribed` · `verified` · `created_at` · `updated_at` · `ip_address` · `user_agent` · `referrer` · `utm_source` · `utm_medium` · `utm_campaign` · `utm_term` · `utm_content` · `revenue` · `lifetime_value` · `company_size` · `industry` · `message` · `subject` · `salutation` · `suffix` · `nickname` · `middle_name` · `maiden_name` · `preferred_name` · `pronouns` · `age` · `annual_income` · `score` · `unknown`

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

## Architecture

```
rolodexter/
├── __init__.py      # Public API
├── core.py          # ContactMapper, PatternRegistry, strategies, normalizers
├── _phone.py        # E.164 phone parser (wraps libphonenumber)
├── i18n.py          # On-demand i18n generator (40 languages, cached)
├── patterns.json    # Master alias table (615+ aliases, 62 canonical fields)
└── i18n/            # Cached language files (generated on demand)
```

## Contributing

```bash
git clone https://github.com/L0garithmic/rolodexter.git
cd rolodexter
pip install -e ".[dev]"
pytest
```

## License

MIT — see [LICENSE](LICENSE).
