<div align="center">

<a href="https://github.com/LunarWerxs/rolodexter">
  <img src="https://res.cloudinary.com/dicsgc72e/image/upload/v1772425436/ezgif-42b0a21d2af73c08_iwq3aa.gif" alt="RoloDexter, the universal contact field mapper" width="600">
</a>

<br/>
<br/>

[![npm version](https://img.shields.io/npm/v/rolodexter?style=flat-square&logo=npm&logoColor=white&label=npm&color=8a4a8a&labelColor=140e17)](https://www.npmjs.com/package/rolodexter)
[![npm downloads](https://img.shields.io/npm/dm/rolodexter?style=flat-square&label=downloads&color=6d2f6d&labelColor=140e17)](https://www.npmjs.com/package/rolodexter)
[![node](https://img.shields.io/node/v/rolodexter?style=flat-square&label=node&color=4a1f4a&labelColor=140e17)](https://nodejs.org)
[![PyPI](https://img.shields.io/pypi/v/rolodexter?style=flat-square&logo=python&logoColor=white&label=PyPI&color=8a4a8a&labelColor=140e17)](https://pypi.org/project/rolodexter/)
[![license MIT](https://img.shields.io/badge/license-MIT-8a4a8a?style=flat-square&labelColor=140e17)](https://opensource.org/licenses/MIT)

<strong>The universal contact field mapper.</strong><br/>
Route messy, inconsistent contact data from <em>any</em> source into one clean, canonical schema.

</div>

---

Every CRM, email platform, and CSV export invents its own name for the same field. `FNAME`. `firstname`. `Given Name`. `Column A`. Multiply that by phone formats, address splits, and a decade of ad-hoc exports, and every integration turns into the same hand-written mapping table you already wrote three times this year.

**RoloDexter** deletes that table. Hand it a payload from anywhere and it gives back your canonical field names, with the values already normalized.

```bash
npx rolodexter map contacts.csv --format json
```

## ✨ At a glance

Four vendors, one schema. Every row below is real matcher output, not an aspiration:

| Your source calls it | RoloDexter gives you | How it knew |
| --- | --- | --- |
| `FNAME`, `fname`, `first` | `first_name` | exact alias |
| `Given Name` | `first_name` | normalized |
| `Phone 1 - Value` | `phone` | normalized |
| `Organization 1 - Name` | `company` | normalized |
| `Job Titel` (typo) | `job_title` | fuzzy |
| `adress` (typo) | `address_line1` | fuzzy |
| `Column D` holding `jane@example.com` | `email` | value shape |
| `Column B` holding `+1 202-555-0143` | `phone` | value shape |

Those last two are the point: when the header tells you nothing at all, RoloDexter reads the *value* and routes it anyway.

## 🤔 Why you'd want it

Reach for RoloDexter when you want:

- 🎯 **One canonical schema** across HubSpot, Salesforce, Mailchimp, Google CSV, and whatever your customer emailed you
- 🧹 **Values normalized on the way in**: phones to E.164, names to title case, booleans and tags coerced
- 🕵️ **Unlabeled columns rescued** by value-shape detection instead of silently dropped
- 📊 **A confidence score per field**, so you can gate, audit, or quarantine instead of guessing
- 🌍 **40 languages** of alias coverage, pre-generated and cached, never translated mid-request
- 🧊 **Zero config**: no schema file, no rules to register, no service to call
- 🐍 **A Python twin** sharing the same alias table, for teams straddling both runtimes

## 📦 Install

```bash
npm i rolodexter
```

…or don't install it at all:

```bash
npx rolodexter map contacts.csv
```

Node `>=20`. Ships ESM and CommonJS builds plus TypeScript declarations for every entry point.

## 🚀 Quick start

```ts
import { ContactMapper } from "rolodexter";

const result = new ContactMapper().map_payload({
  fname: "jane",
  surname: "doe",
  mobile: "(202) 555-0143",
  employer: "Tech Corp",
  "Column 7": "jane@example.com",   // no usable header, matched by value shape
});

result.normalized;
// {
//   first_name: "Jane",
//   last_name:  "Doe",
//   phone:      "+12025550143",
//   company:    "Tech Corp",
//   email:      "jane@example.com"
// }

result.match_rate;      // 1
result.matched_count;   // 5
result.unmapped;        // {}
```

The API is deliberately snake_case in both runtimes, so a mapping written against the Python package reads identically here.

<details>
<summary><strong>⚙️ Constructor options, <code>new ContactMapper(options)</code></strong></summary>

<br/>

| Option | Default | What it does |
| --- | --- | --- |
| `default_region` | `"US"` | Region used to parse phone numbers with no country code |
| `normalize` | `true` | Normalize matched values. Set `false` to keep raw strings |
| `overrides` | none | Pin a header to a field, e.g. `{ MMERGE6: "company" }` |
| `languages` | none | Language codes whose cached alias packs get merged in |
| `strict` | `false` | Throw `NormalizationError` on a mapping warning instead of recording it |
| `confidence_threshold` | `0` | Matches scoring below this are demoted to unmapped |
| `header_cache_max_size` | `4096` | LRU cap on cached header matches |
| `strategies` | all four | Replace the matching pipeline outright |

```ts
const mapper = new ContactMapper({
  default_region: "GB",
  overrides: { MMERGE6: "company" },
  confidence_threshold: 0.8,
});

mapper.map_payload({ mobile: "020 7946 0958" }).normalized;
// { phone: "+442079460958" }
```

</details>

## 🧠 How matching works

Every header runs through four strategies in order and stops at the first hit:

| Strategy | Confidence | How it decides |
| --- | --- | --- |
| `exact` | `1.0` | The header is a known alias, verbatim |
| `normalized` | `0.95` | It matches after case and format folding (snake, camel, dotted, indexed, vendor-prefixed) |
| `fuzzy` | `0.85` / `0.7` | It scores at least `80` against a known alias. `0.85` above a score of 90, `0.7` below |
| `heuristic` | `0.6` | The header is useless, but the **value** looks like an email, phone, URL, postal code, or birthday |

```ts
mapper.identify("FirstName");                            // first_name     exact      1
mapper.identify("adress");                               // address_line1  fuzzy      0.85
mapper.identify("phne");                                 // phone          fuzzy      0.7
mapper.identify("Column X", { value: "jane@test.com" }); // email          heuristic  0.6
```

### What comes back

`map_payload` returns a `MappingResult`:

| Member | Type | What it is |
| --- | --- | --- |
| `.normalized` | `object` | Matched fields, keyed by canonical name |
| `.unmapped` | `object` | Everything it declined to place |
| `.field_matches` | `FieldMatch[]` | One per input header: `original`, `canonical`, `confidence`, `strategy` |
| `.warnings` | `string[]` | Non-fatal issues, thrown instead under `strict: true` |
| `.matched_count` / `.unmatched_count` / `.match_rate` | `number` | Derived from `field_matches` |
| `.get_match(header)` | `FieldMatch \| null` | How one specific header resolved |
| `.get_all_phones()` | `string[]` | Every phone-shaped value found, deduped and E.164 |
| `.explain()` | `string` | Human-readable audit of the whole mapping |
| `.to_dict()` | `object` | JSON-friendly snapshot |

`.explain()` is the one to reach for when a mapping surprises you:

```text
Mapping: 2 matched, 1 unmatched (match rate 67%)
  'MMERGE6' -> company [exact, conf=1.00]
  'phne'  x unknown [none, conf=0.00]
  'FNAME' -> first_name [exact, conf=1.00]
Warnings:
  ! 'phne': dropped low-confidence match to 'phone' (confidence 0.70 < threshold 0.80)
```

### Beyond a single payload

| Method | What it does |
| --- | --- |
| `map_payload(obj)` | Map one record |
| `map_batch(rows)` | Map an array of records |
| `map_stream(iterable)` | Map lazily, for files that will not fit in memory |
| `compile_schema(headers)` | Resolve a header list **once**, then reuse it across every row |
| `map_dataframe(df)` | Map a DataFrame-like column store |
| `identify(header, opts?)` | Resolve a single header without mapping anything |
| `clear_cache()` / `cache_info()` | Inspect and reset the header cache |

## 🎛️ CLI reference

```
rolodexter map <input>       Map a CSV/JSON/JSONL file to canonical fields
rolodexter explain <header>  Show how a single header resolves
rolodexter fields            List all canonical fields
```

`map` accepts:

| Flag | Default | What it does |
| --- | --- | --- |
| `-o, --output <path>` | stdout | Where to write results |
| `--format {auto,csv,json,jsonl}` | from `-o`, else `json` | Output format |
| `--in-format {auto,csv,json,jsonl}` | from input extension | Input format |
| `--region <code>` | `US` | Default phone region, ISO-3166 alpha-2 |
| `--languages <codes>` | none | Comma-separated cached language codes |
| `--strict` | off | Fail on any mapping warning |
| `--min-confidence <0.0-1.0>` | `0` | Drop matches below this confidence |
| `--no-normalize` | off | Skip value normalization |
| `--embedded-phones` | off | Also pull phone numbers out of free-text values |
| `--on-error {fail,skip,quarantine}` | `fail` | How to handle a row that will not parse |
| `--quarantine-output <path>` | `<input>.quarantine.jsonl` | Where quarantined rows land |
| `--max-materialized-rows <n>` | `100000` | Row cap for JSON/CSV output, `0` disables |
| `--max-json-input-bytes <n>` | `52428800` | Read cap for non-streaming JSON input, `0` disables |

```bash
# Mailchimp, Salesforce, Google CSV, and an unnamed column, all in one file
rolodexter map contacts.csv --format json

# Audit as you go, and keep the bad rows instead of dying on them
rolodexter map leads.csv --min-confidence 0.75 --on-error quarantine \
  --quarantine-output leads.bad.jsonl -o leads.clean.json

# Ask how a single header would resolve, before committing to a pipeline
rolodexter explain "Job Titel"
rolodexter explain "Column B" --value "+1 202-555-0143"

# Print every canonical field name
rolodexter fields
```

### 🧾 Output

```console
$ rolodexter map contacts.csv --format json
[
  {
    "first_name": "Jane",
    "phone": "+12025550143",
    "company": "Tech Corp",
    "email": "jane@example.com"
  },
  {
    "first_name": "Bob",
    "phone": "+16502530000",
    "company": "Acme",
    "email": "bob@acme.io"
  }
]
Mapped 2 row(s) -> stdout (json)
```

That input file's headers were `FNAME`, `MobilePhone`, `Organization 1 - Name`, and `Column D`. No configuration was supplied.

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success, or `-h`/`--help` |
| `1` | Runtime error: unreadable file, malformed JSON, `--min-confidence` out of range |
| `2` | Usage error: bad, missing, or unrecognized arguments |
| `120` | Broken pipe, e.g. piping into `head` |

## 🗂️ The canonical schema

62 canonical fields plus an `UNKNOWN` sentinel, spanning identity, contact, company, address, social, lifecycle, and metadata. `rolodexter fields` prints the live list; `CanonicalField` exposes it in code.

<details>
<summary><strong>Show all 62 fields</strong></summary>

<br/>

| Group | Fields |
| --- | --- |
| **Name** | `first_name` `last_name` `full_name` `middle_name` `nickname` `prefix` `suffix` |
| **Contact** | `email` `phone` `home_phone` `work_phone` `fax` `whatsapp` `website` |
| **Company** | `company` `job_title` `department` `industry` `company_size` |
| **Address** | `address_line1` `address_line2` `city` `state` `postal_code` `country` `full_address` |
| **Social** | `linkedin` `twitter` `facebook` `instagram` `github` `youtube` `tiktok` `discord` `telegram` |
| **Lifecycle** | `lead_status` `lifecycle_stage` `email_opt_out` `subscribed` `verified` `tags` `score` `owner` |
| **Attribution** | `source` `source_id` `source_service` `referrer_url` `utm_parameters` |
| **Dates** | `birthday` `age` `created_at` `updated_at` `last_contacted` |
| **Commerce** | `revenue` `currency` |
| **Freeform** | `message` `subject` `notes` `metadata` |
| **Profile** | `gender` `timezone` `language_preference` |

</details>

## 🌍 Language packs

English ships by default with no extra dependency. The other 40 languages are generated ahead of time into a cache and simply loaded at construction. RoloDexter never calls a translation service on the request path.

```bash
rolodexter-i18n --list                # supported languages and cache status
rolodexter-i18n --languages es,fr,de  # generate and cache three packs
```

```ts
const mapper = new ContactMapper({ languages: ["es", "fr"] });
```

Generating packs needs the optional `@vitalets/google-translate-api` and `unidecode` dependencies. Loading cached packs does not, so `npm i --omit=optional` is still a fully working install for mapping.

## 🧰 What's in the box

Three entry points, each with its own types:

| Import from | What you get |
| --- | --- |
| `rolodexter` | Everything: matcher, normalizers, phone helpers, `SUPPORTED_LANGUAGES`, `generate_language` |
| `rolodexter/core` | The matching engine and its tuning constants (`EXACT_MATCH_CONFIDENCE`, `FUZZY_MATCH_THRESHOLD`, …), without phone or i18n code |
| `rolodexter/i18n` | Cache and generation helpers behind the `rolodexter-i18n` CLI |

Runtime dependencies are deliberately few: `fuzzball` for fuzzy header scoring, `libphonenumber-js` for phone parsing, `csv-stringify` for CSV output.

> **The alias table is not maintained twice.** `patterns.json` lives in the Python package and is synced into this one on every build, so the JavaScript and Python packages cannot drift apart. Both are held to the same golden-corpus conformance fixtures.

## 🐍 The Python twin

The same engine, alias table, and canonical schema ship as [`rolodexter` on PyPI](https://pypi.org/project/rolodexter/), with a matching snake_case API:

```python
from rolodexter import ContactMapper

ContactMapper().map_payload({"fname": "jane", "mobile": "(202) 555-0143"}).normalized
# {'first_name': 'Jane', 'phone': '+12025550143'}
```

## 📜 Changelog

<details>
<summary><strong>v2.9.1</strong> · 2026-07-09 · internal hardening, no public API change</summary>

<br/>

- **Shared header normalizer**: the exact, normalized, and fuzzy strategies now fold headers through one helper instead of three copies.
- **Single-source address aliases**: the address-prefix list is derived from `patterns.json` rather than maintained beside it.
- **Validated i18n caches**: an invalid cache file now warns and regenerates instead of failing silently.
- **Precomputed fuzzy index**: built once per mapper instead of rescanned per header.
- **Shared Py/JS conformance corpus**: `conformance_cases.json` now drives both test suites.

</details>

<details>
<summary><strong>v2.9.0</strong> · 2026-07-08 · the first-class TypeScript package</summary>

<br/>

The release that created this package: the full four-strategy pipeline, public normalizers, phone helpers, match strategies, Python-shaped snake_case API, cached i18n loading and generation, batch / stream / schema / DataFrame helpers, ESM and CJS builds, and the `rolodexter` and `rolodexter-i18n` CLIs. Shared golden corpora keep it conformant with the Python package.

</details>

Full history: [CHANGELOG.md](https://github.com/LunarWerxs/rolodexter/blob/main/CHANGELOG.md)

## 📄 License

[MIT](https://github.com/LunarWerxs/rolodexter/blob/main/LICENSE) © [LunarWerx](https://lunarwerx.com)

<div align="center">
<br/>
<img src="https://res.cloudinary.com/dicsgc72e/image/upload/v1772425436/ezgif-42b0a21d2af73c08_iwq3aa.gif" alt="" width="52">
<br/>
<sub><strong>RoloDexter</strong> · same fields, every source.</sub>
</div>
