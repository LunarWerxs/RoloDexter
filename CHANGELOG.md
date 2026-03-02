# Changelog

All notable changes to **rolodexter** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

## [1.0.0] — 2026-03-01

### Added

- **ContactMapper** — multi-layer strategy pipeline (exact → service → fuzzy → heuristic).
- **PatternRegistry** — O(1) indexed lookup over 300+ field aliases across 40+ canonical fields.
- **20 service profiles** — Mailchimp, HubSpot, Salesforce, SendGrid, Stripe, Beehiiv, Resend, Omnisend, Pipedrive, Notion, Zoho, ActiveCampaign, Intercom, Brevo, ConvertKit, Airtable, Google Contacts, Apple Contacts, Outlook, LinkedIn export, Close CRM, Freshsales.
- **4 matching strategies** — `ExactMatchStrategy`, `ServiceMatchStrategy`, `FuzzyMatchStrategy`, `HeuristicMatchStrategy`.
- **5 value normalizers** — Phone, Email, Name (with surname particle awareness), Address, String.
- **Cross-service translation** via `mapper.translate()`.
- **Batch processing** via `mapper.map_batch()`.
- **Confidence scoring** on every match (0.0–1.0).
- **MappingResult diagnostics** — match rate, per-field details, JSON serialisation.
- **CanonicalField enum** — 50+ standardised fields with `str` mixin for easy JSON compat.
- Full type annotations + PEP 561 `py.typed` marker.
- Comprehensive test suite (90+ test cases).
- GitHub Actions CI + PyPI publish workflows.
