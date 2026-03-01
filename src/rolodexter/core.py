"""Rolodexter — The universal contact field mapper.

This single module contains the complete implementation:
exceptions, enums, models, normalizers, registry, strategies, and mapper.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, unique
from importlib import resources
from typing import Any

# ═══════════════════════════════════════════════════════════════════════
#  EXCEPTIONS
# ═══════════════════════════════════════════════════════════════════════


class RolodexterError(Exception):
    """Base exception for all rolodexter errors."""


class PatternLoadError(RolodexterError):
    """Raised when pattern data cannot be loaded or parsed."""


class StrategyError(RolodexterError):
    """Raised when a matching strategy encounters an unrecoverable error."""


class NormalizationError(RolodexterError):
    """Raised when value normalization fails."""


class ServiceNotFoundError(RolodexterError):
    """Raised when a requested service profile does not exist in the registry.

    .. deprecated:: 2.0.0
        Service profiles have been removed.  This exception is kept only
        for backward compatibility and is never raised by the library.
    """


# ═══════════════════════════════════════════════════════════════════════
#  CANONICAL FIELDS & THRESHOLDS
# ═══════════════════════════════════════════════════════════════════════


@unique
class CanonicalField(str, Enum):
    """Universal canonical contact fields.

    Inherits from ``str`` so values serialize to JSON and compare with
    plain strings: ``CanonicalField.EMAIL == "email"``.
    """

    # Identity
    FIRST_NAME = "first_name"
    LAST_NAME = "last_name"
    FULL_NAME = "full_name"
    MIDDLE_NAME = "middle_name"
    NICKNAME = "nickname"
    PREFIX = "prefix"
    SUFFIX = "suffix"
    # Communication
    EMAIL = "email"
    PHONE = "phone"
    HOME_PHONE = "home_phone"
    WORK_PHONE = "work_phone"
    FAX = "fax"
    WHATSAPP = "whatsapp"
    WEBSITE = "website"
    # Professional
    COMPANY = "company"
    JOB_TITLE = "job_title"
    DEPARTMENT = "department"
    INDUSTRY = "industry"
    # Address
    ADDRESS_LINE1 = "address_line1"
    ADDRESS_LINE2 = "address_line2"
    CITY = "city"
    STATE = "state"
    POSTAL_CODE = "postal_code"
    COUNTRY = "country"
    FULL_ADDRESS = "full_address"
    # Social
    LINKEDIN = "linkedin"
    TWITTER = "twitter"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    GITHUB = "github"
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    # CRM / Marketing
    LEAD_STATUS = "lead_status"
    LIFECYCLE_STAGE = "lifecycle_stage"
    EMAIL_OPT_OUT = "email_opt_out"
    TAGS = "tags"
    SOURCE = "source"
    UTM_PARAMETERS = "utm_parameters"
    SCORE = "score"
    OWNER = "owner"
    # Dates
    BIRTHDAY = "birthday"
    AGE = "age"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    LAST_CONTACTED = "last_contacted"
    # Financial
    REVENUE = "revenue"
    CURRENCY = "currency"
    # Form / Communication
    MESSAGE = "message"
    SUBJECT = "subject"
    COMPANY_SIZE = "company_size"
    # Meta
    NOTES = "notes"
    METADATA = "metadata"
    # Provenance / Integration
    SOURCE_ID = "source_id"
    SOURCE_SERVICE = "source_service"
    SUBSCRIBED = "subscribed"
    VERIFIED = "verified"
    UNKNOWN = "unknown"


# Confidence thresholds
EXACT_MATCH_CONFIDENCE: float = 1.0
NORMALIZED_MATCH_CONFIDENCE: float = 0.95
FUZZY_MATCH_THRESHOLD: int = 80
FUZZY_HIGH_CONFIDENCE: float = 0.85
FUZZY_LOW_CONFIDENCE: float = 0.70
HEURISTIC_CONFIDENCE: float = 0.60


# ═══════════════════════════════════════════════════════════════════════
#  MODELS
# ═══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class FieldMatch:
    """Result of mapping a single field header to its canonical form."""

    original: str
    canonical: str
    confidence: float
    strategy: str
    service: str | None = None

    @property
    def is_matched(self) -> bool:
        return self.canonical != "unknown"


@dataclass(frozen=True, slots=True)
class MappingResult:
    """Result of normalizing an entire contact data payload."""

    normalized: dict[str, Any]
    unmapped: dict[str, Any]
    field_matches: tuple[FieldMatch, ...]

    @property
    def match_rate(self) -> float:
        total = len(self.field_matches)
        return sum(1 for m in self.field_matches if m.is_matched) / total if total else 0.0

    @property
    def matched_count(self) -> int:
        return sum(1 for m in self.field_matches if m.is_matched)

    @property
    def unmatched_count(self) -> int:
        return sum(1 for m in self.field_matches if not m.is_matched)

    def get_match(self, original_header: str) -> FieldMatch | None:
        for m in self.field_matches:
            if m.original == original_header:
                return m
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "normalized": dict(self.normalized),
            "unmapped": dict(self.unmapped),
            "match_rate": round(self.match_rate, 4),
            "matched": self.matched_count,
            "unmatched": self.unmatched_count,
            "details": [
                {
                    "original": m.original,
                    "canonical": m.canonical,
                    "confidence": m.confidence,
                    "strategy": m.strategy,
                    "service": m.service,
                }
                for m in self.field_matches
            ],
        }


# ═══════════════════════════════════════════════════════════════════════
#  NORMALIZERS
# ═══════════════════════════════════════════════════════════════════════

_PHONE_STRIP = re.compile(r"[^\d+]")


def _phonenumbers_available() -> bool:
    """Return True if the ``phonenumbers`` package is importable."""
    try:
        import phonenumbers as _pn  # noqa: F401

        return True
    except ImportError:
        return False


class PhoneNormalizer:
    """Normalize phone values to E.164 when possible.

    If the optional ``phonenumbers`` package is installed
    (``pip install rolodexter[phone]``), numbers are parsed via
    Google's libphonenumber and formatted as E.164.  When the
    library is unavailable or parsing fails, a lightweight regex
    fallback strips non-digit characters.
    """

    _STRIP = _PHONE_STRIP

    @classmethod
    def normalize(cls, value: str, *, default_region: str | None = None) -> str:
        if not value or not isinstance(value, str):
            return value  # type: ignore[return-value]

        raw = value.strip()
        if not raw:
            return value

        # ── E.164 via phonenumbers (optional) ───────────────────────
        if _phonenumbers_available():
            import phonenumbers
            from phonenumbers import NumberParseException

            try:
                parsed = phonenumbers.parse(raw, default_region)
                if phonenumbers.is_valid_number(parsed):
                    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            except NumberParseException:
                pass

        # ── Regex fallback ──────────────────────────────────────────
        cleaned = cls._STRIP.sub("", raw)
        if not cleaned:
            return value
        if len(cleaned) > 10 and not cleaned.startswith("+"):
            cleaned = "+" + cleaned
        # Reject implausible lengths
        digit_count = sum(c.isdigit() for c in cleaned)
        if digit_count < 7 or digit_count > 15:
            return value
        return cleaned


class EmailNormalizer:
    @staticmethod
    def normalize(value: str) -> str:
        if not value or not isinstance(value, str):
            return value  # type: ignore[return-value]
        return value.strip().lower()


class NameNormalizer:
    _PARTICLES = frozenset(
        {
            "de",
            "del",
            "der",
            "van",
            "von",
            "la",
            "le",
            "di",
            "da",
            "dos",
            "das",
            "el",
            "al",
            "bin",
            "ibn",
            "mac",
            "mc",
        }
    )

    @classmethod
    def normalize(cls, value: str) -> str:
        if not value or not isinstance(value, str):
            return value  # type: ignore[return-value]
        parts = value.strip().split()
        result: list[str] = []
        for idx, part in enumerate(parts):
            lower = part.lower()
            if lower in cls._PARTICLES and idx > 0:
                result.append(lower)
            elif "-" in part:
                result.append("-".join(seg.capitalize() for seg in part.split("-")))
            else:
                result.append(part.capitalize())
        return " ".join(result)


class AddressNormalizer:
    @staticmethod
    def normalize(value: str) -> str:
        if not value or not isinstance(value, str):
            return value  # type: ignore[return-value]
        return " ".join(value.strip().split()).title()


class StringNormalizer:
    @staticmethod
    def normalize(value: str) -> str:
        if not value or not isinstance(value, str):
            return value  # type: ignore[return-value]
        return value.strip()


_FIELD_NORMALIZERS: dict[str, type] = {
    "phone": PhoneNormalizer,
    "home_phone": PhoneNormalizer,
    "work_phone": PhoneNormalizer,
    "fax": PhoneNormalizer,
    "whatsapp": PhoneNormalizer,
    "email": EmailNormalizer,
    "first_name": NameNormalizer,
    "last_name": NameNormalizer,
    "full_name": NameNormalizer,
    "middle_name": NameNormalizer,
    "nickname": NameNormalizer,
    "address_line1": AddressNormalizer,
    "address_line2": AddressNormalizer,
    "city": AddressNormalizer,
    "full_address": AddressNormalizer,
    "state": StringNormalizer,
    "country": StringNormalizer,
    "message": StringNormalizer,
    "subject": StringNormalizer,
    "company_size": StringNormalizer,
}


def normalize_value(canonical_field: str, value: Any) -> Any:
    """Apply the correct normalizer for *canonical_field*."""
    if not isinstance(value, str):
        return value
    cls = _FIELD_NORMALIZERS.get(canonical_field, StringNormalizer)
    return cls.normalize(value)


# ═══════════════════════════════════════════════════════════════════════
#  PATTERN REGISTRY
# ═══════════════════════════════════════════════════════════════════════


class PatternRegistry:
    """Immutable index over the master ``patterns.json`` truth table.

    The optional *languages* parameter controls which i18n language
    files (from ``_data/i18n/``) are merged into the alias index:

    * ``"all"`` (default) — every available language file is loaded.
    * ``None`` or ``[]`` — **no** i18n aliases are loaded (English only).
    * ``["es", "fr"]`` — only the listed language codes are loaded.
    """

    __slots__ = (
        "_all_aliases",
        "_canonical_fields",
        "_data",
        "_i18n_files",
        "_languages",
        "_loaded_languages",
        "_reverse_index",
    )

    def __init__(
        self,
        patterns: dict[str, Any] | None = None,
        patterns_path: str | None = None,
        languages: str | Sequence[str] | None = "all",
    ) -> None:
        if patterns is not None:
            self._data = patterns
        elif patterns_path is not None:
            self._data = self._load_from_path(patterns_path)
        else:
            self._data = self._load_default()

        self._languages = languages
        self._reverse_index: dict[str, str] = {}
        self._all_aliases: list[str] = []
        self._canonical_fields: list[str] = []
        self._loaded_languages: list[str] = []
        self._i18n_files: dict[str, Any] = self._discover_i18n_files()
        self._build_indexes()

    @staticmethod
    def _load_from_path(path: str) -> dict[str, Any]:
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
            raise PatternLoadError(f"Failed to load patterns from {path}: {exc}") from exc

    @staticmethod
    def _load_default() -> dict[str, Any]:
        try:
            pkg = resources.files("rolodexter._data")
            text = pkg.joinpath("patterns.json").read_text(encoding="utf-8")
            return json.loads(text)
        except Exception as exc:
            raise PatternLoadError(f"Failed to load bundled patterns: {exc}") from exc

    @staticmethod
    def _discover_i18n_files() -> dict[str, Any]:
        """Discover available ``i18n/*.json`` language files."""
        files: dict[str, Any] = {}
        try:
            pkg = resources.files("rolodexter._data")
            i18n_dir = pkg / "i18n"
            for item in i18n_dir.iterdir():
                if hasattr(item, "name") and item.name.endswith(".json"):
                    lang_code = item.name[:-5]  # strip .json
                    files[lang_code] = item
        except Exception:
            pass
        return files

    @staticmethod
    def _load_i18n_file(resource: Any) -> dict[str, Any] | None:
        """Load a single i18n language file."""
        try:
            text = resource.read_text(encoding="utf-8")
            return json.loads(text)
        except Exception:
            return None

    def _build_indexes(self) -> None:
        fields: dict[str, list[str]] = self._data.get("fields", {})
        for canonical, aliases in fields.items():
            self._canonical_fields.append(canonical)
            for alias in aliases:
                key = alias.lower().strip()
                if key not in self._reverse_index:
                    self._reverse_index[key] = canonical
                self._all_aliases.append(key)

        # ── i18n layer (file-based) ─────────────────────────────────
        if self._languages == "all":
            lang_codes = list(self._i18n_files.keys())
        elif self._languages:
            lang_codes = list(self._languages) if not isinstance(self._languages, str) else [self._languages]
        else:
            lang_codes = []

        for lang in lang_codes:
            resource = self._i18n_files.get(lang)
            if resource is None:
                continue
            lang_data = self._load_i18n_file(resource)
            if lang_data is None:
                continue
            self._loaded_languages.append(lang)
            for canonical, aliases in lang_data.get("fields", {}).items():
                for alias in aliases:
                    key = alias.lower().strip()
                    if key not in self._reverse_index:
                        self._reverse_index[key] = canonical
                    self._all_aliases.append(key)

    def exact_lookup(self, header: str) -> str | None:
        return self._reverse_index.get(header.lower().strip())

    @property
    def all_aliases(self) -> list[str]:
        return self._all_aliases

    @property
    def canonical_fields(self) -> list[str]:
        return list(self._canonical_fields)

    @property
    def loaded_languages(self) -> list[str]:
        """Language codes whose i18n aliases were loaded."""
        return list(self._loaded_languages)

    @property
    def available_languages(self) -> list[str]:
        """All language codes with i18n files available (loaded or not)."""
        return sorted(self._i18n_files.keys())

    @property
    def version(self) -> str:
        return self._data.get("version", "0.0.0")

    def __repr__(self) -> str:
        return (
            f"PatternRegistry(aliases={len(self._reverse_index)}, "
            f"languages={self._loaded_languages}, "
            f"version={self.version!r})"
        )


# ═══════════════════════════════════════════════════════════════════════
#  MATCHING STRATEGIES
# ═══════════════════════════════════════════════════════════════════════


class MatchStrategy(ABC):
    """Protocol every matching strategy must satisfy."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def match(self, header: str, value: str | None = None, **kwargs: object) -> FieldMatch | None: ...


class ExactMatchStrategy(MatchStrategy):
    __slots__ = ("_registry",)

    def __init__(self, registry: PatternRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "exact"

    def match(self, header: str, value: str | None = None, **kwargs: object) -> FieldMatch | None:
        canonical = self._registry.exact_lookup(header)
        if canonical is not None:
            return FieldMatch(
                original=header, canonical=canonical, confidence=EXACT_MATCH_CONFIDENCE, strategy=self.name
            )
        return None


class ServiceMatchStrategy(MatchStrategy):
    """Deprecated stub — service profiles were removed in v2.0.

    Kept so that code referencing the class does not crash on import.
    ``match()`` always returns ``None``.
    """

    __slots__ = ("_registry",)

    def __init__(self, registry: PatternRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "service"

    def match(self, header: str, value: str | None = None, **kwargs: object) -> FieldMatch | None:
        return None


class NormalizedMatchStrategy(MatchStrategy):
    """Smart header normalisation → exact alias lookup (confidence 0.95).

    Handles CamelCase, dot-paths, space/hyphen→underscore, indexed
    patterns (``E-mail 1 - Value``), vendor prefix stripping, address
    prefix stripping, ``_id`` suffix stripping, and number stripping —
    all with **zero** hardcoded service profiles.
    """

    __slots__ = ("_registry",)

    # Prefixes whose dotted object.name → company
    _COMPANY_PREFIXES = frozenset(
        {
            "account",
            "accounts",
            "org",
            "organization",
            "organisations",
            "organizations",
            "organisation",
            "company",
            "companies",
            "firm",
            "business",
            "enterprise",
        }
    )

    # Vendor-specific prefixes to strip
    _VENDOR_PREFIXES = ("hs_", "hubspot_", "sf_", "salesforce_")

    # Address-context prefixes (the suffix IS the field)
    _ADDRESS_PREFIXES = (
        "business_",
        "mailing_",
        "home_",
        "other_",
        "personal_",
        "shipping_",
        "billing_",
        "primary_",
        "secondary_",
    )

    _CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
    _INDEXED_RE = re.compile(r"^(.+?)\s+\d+\s*(?:[-–—]\s*)?(.+)$")

    def __init__(self, registry: PatternRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "normalized"

    # ------------------------------------------------------------------
    def _lookup(self, candidate: str) -> str | None:
        return self._registry.exact_lookup(candidate)

    def _candidates(self, header: str) -> list[str]:
        out: list[str] = []
        h = header.strip()
        if not h:
            return out

        # 1. Space / hyphen → underscore  +  strip non-word chars
        uscore = re.sub(r"[\s\-]+", "_", h).lower()
        uscore = re.sub(r"[^\w]", "_", uscore)
        uscore = re.sub(r"_+", "_", uscore).strip("_")
        if uscore:
            out.append(uscore)

        # 2. CamelCase / PascalCase split
        if any(c.isupper() for c in h[1:]):
            snake = self._CAMEL_RE.sub("_", h).lower()
            snake = re.sub(r"_+", "_", snake).strip("_")
            if snake and snake != uscore:
                out.append(snake)

        # 3. Dot-path resolution  (e.g. Account.Name, fields.last_name)
        if "." in h:
            parts = h.rsplit(".", 1)
            prefix_raw = parts[0].lower().strip()
            suffix_raw = parts[1].strip()
            suffix_lower = re.sub(r"[\s\-]+", "_", suffix_raw).lower()
            # Context-aware: company-like prefix + 'name' → company
            last_prefix = prefix_raw.rsplit(".", 1)[-1]
            if last_prefix in self._COMPANY_PREFIXES and suffix_lower in ("name", "nombre"):
                out.insert(0, "company")
            # Last segment (underscore-normalised)
            out.append(suffix_lower)
            # CamelCase split of last segment
            if any(c.isupper() for c in suffix_raw[1:]):
                snake_sfx = self._CAMEL_RE.sub("_", suffix_raw).lower()
                snake_sfx = re.sub(r"_+", "_", snake_sfx).strip("_")
                if snake_sfx != suffix_lower:
                    out.append(snake_sfx)

        # 4. Indexed pattern:  "E-mail 1 - Value", "Organization 1 - Title"
        m = self._INDEXED_RE.match(h)
        if m:
            grp = re.sub(r"[\s\-]+", "_", m.group(1).strip()).lower()
            prop = re.sub(r"[\s\-]+", "_", m.group(2).strip()).lower()
            out.append(f"{grp}_{prop}")  # organization_name
            out.append(prop)  # name
            out.append(grp)  # organization

        # 5. Number stripping  ("E-mail 2 Address" → e_mail_address)
        num_stripped = re.sub(r"_\d+", "", uscore)
        num_stripped = re.sub(r"_+", "_", num_stripped).strip("_")
        if num_stripped and num_stripped != uscore:
            out.append(num_stripped)

        # 6. Vendor prefix stripping  (hs_lead_status → lead_status)
        for pfx in self._VENDOR_PREFIXES:
            if uscore.startswith(pfx):
                stripped = uscore[len(pfx) :]
                if stripped:
                    out.append(stripped)

        # 7. Address prefix stripping  (business_city → city)
        for pfx in self._ADDRESS_PREFIXES:
            if uscore.startswith(pfx):
                stripped = uscore[len(pfx) :]
                if stripped:
                    out.append(stripped)

        # 8.  _id suffix stripping  (owner_id → owner)
        id_candidates = [c for c in out if c.endswith("_id")]
        for candidate in id_candidates:
            base = candidate[:-3]
            if base and base not in out:
                out.append(base)
                # Also strip vendor prefix off the base
                for pfx in self._VENDOR_PREFIXES:
                    if base.startswith(pfx):
                        inner = base[len(pfx) :]
                        if inner and inner not in out:
                            out.append(inner)

        return out

    # ------------------------------------------------------------------
    def match(self, header: str, value: str | None = None, **kwargs: object) -> FieldMatch | None:
        for candidate in self._candidates(header):
            canonical = self._lookup(candidate)
            if canonical is not None:
                return FieldMatch(
                    original=header,
                    canonical=canonical,
                    confidence=NORMALIZED_MATCH_CONFIDENCE,
                    strategy=self.name,
                )
        return None


class FuzzyMatchStrategy(MatchStrategy):
    __slots__ = ("_available", "_registry")

    def __init__(self, registry: PatternRegistry) -> None:
        self._registry = registry
        try:
            import rapidfuzz  # noqa: F401

            self._available = True
        except ImportError:
            self._available = False

    @property
    def name(self) -> str:
        return "fuzzy"

    def match(self, header: str, value: str | None = None, **kwargs: object) -> FieldMatch | None:
        if not self._available:
            return None
        from rapidfuzz import fuzz, process

        clean = re.sub(r"[^\w]", "_", header.lower().strip())
        clean = re.sub(r"_+", "_", clean).strip("_")

        aliases = self._registry.all_aliases
        if not aliases:
            return None

        result = process.extractOne(clean, aliases, scorer=fuzz.WRatio, score_cutoff=FUZZY_MATCH_THRESHOLD)
        if result is None:
            return None

        matched_alias, score, _ = result
        canonical = self._registry.exact_lookup(matched_alias)
        if canonical is None:
            return None

        confidence = FUZZY_HIGH_CONFIDENCE if score >= 90 else FUZZY_LOW_CONFIDENCE
        return FieldMatch(original=header, canonical=canonical, confidence=confidence, strategy=self.name)


class HeuristicMatchStrategy(MatchStrategy):
    """Regex data-shape detection for unrecognisable headers."""

    _PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("email", re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")),
        ("phone", re.compile(r"^\+?1?\s*[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}$")),
        ("phone", re.compile(r"^\+?[1-9]\d{6,14}$")),
        ("linkedin", re.compile(r"^https?://(www\.)?linkedin\.com/in/", re.IGNORECASE)),
        ("website", re.compile(r"^https?://[^\s]+$", re.IGNORECASE)),
        ("website", re.compile(r"^www\.[^\s]+\.[a-zA-Z]{2,}$", re.IGNORECASE)),
        ("twitter", re.compile(r"^@[a-zA-Z0-9_]{1,15}$")),
        ("postal_code", re.compile(r"^\d{5}(-\d{4})?$")),
        ("postal_code", re.compile(r"^[A-Z]\d[A-Z]\s?\d[A-Z]\d$", re.IGNORECASE)),
        ("postal_code", re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}$", re.IGNORECASE)),
        ("birthday", re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$")),
        ("birthday", re.compile(r"^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$")),
    )

    @property
    def name(self) -> str:
        return "heuristic"

    def match(self, header: str, value: str | None = None, **kwargs: object) -> FieldMatch | None:
        if not value or not isinstance(value, str):
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        for canonical, pattern in self._PATTERNS:
            if pattern.match(cleaned):
                return FieldMatch(
                    original=header, canonical=canonical, confidence=HEURISTIC_CONFIDENCE, strategy=self.name
                )
        return None


# ═══════════════════════════════════════════════════════════════════════
#  CONTACT MAPPER (ORCHESTRATOR)
# ═══════════════════════════════════════════════════════════════════════


class ContactMapper:
    """The universal contact field mapper.

    Routes messy, inconsistent contact data to canonical field names
    using a multi-layer strategy pipeline:

    1. Generic exact match against the alias index
    2. Normalised match (CamelCase / dot-path / space → underscore / …)
    3. Fuzzy match for typos and variations (rapidfuzz)
    4. Heuristic match using data-shape regex patterns

    .. versionchanged:: 2.0.0
        Per-service profiles removed.  The ``default_service`` and
        ``service`` parameters are accepted but ignored.
    """

    __slots__ = ("_normalize", "_registry", "_strategies")

    def __init__(
        self,
        *,
        patterns: dict[str, Any] | None = None,
        patterns_path: str | None = None,
        default_service: str | None = None,
        normalize: bool = True,
        strategies: Sequence[MatchStrategy] | None = None,
        languages: str | Sequence[str] | None = "all",
    ) -> None:
        self._registry = PatternRegistry(patterns=patterns, patterns_path=patterns_path, languages=languages)
        self._normalize = normalize

        if strategies is not None:
            self._strategies = list(strategies)
        else:
            self._strategies: list[MatchStrategy] = [
                ExactMatchStrategy(self._registry),
                NormalizedMatchStrategy(self._registry),
                FuzzyMatchStrategy(self._registry),
                HeuristicMatchStrategy(),
            ]

    def identify(self, header: str, *, value: str | None = None, service: str | None = None) -> FieldMatch:
        """Resolve a single header to its canonical field.

        The *service* parameter is accepted for backward compatibility
        but is ignored since v2.0.
        """
        for strategy in self._strategies:
            result = strategy.match(header, value=value)
            if result is not None:
                return result
        return FieldMatch(original=header, canonical=CanonicalField.UNKNOWN.value, confidence=0.0, strategy="none")

    def map_payload(
        self,
        payload: dict[str, Any],
        *,
        service: str | None = None,
        depth: int = 1,
    ) -> MappingResult:
        """Normalize an entire contact data dictionary.

        Parameters
        ----------
        payload : dict
            Raw contact data to normalize.
        service : str, optional
            Accepted for backward compatibility; ignored since v2.0.
        depth : int, default 1
            Recursion depth for nested payloads.  ``1`` (default) processes
            only the top-level keys.  ``2`` also recurses one level into
            nested dicts.  Maximum supported value is ``5``.

        Returns
        -------
        MappingResult
        """
        depth = max(1, min(depth, 5))
        flat = self._flatten(payload, depth) if depth > 1 else payload

        normalized: dict[str, Any] = {}
        unmapped: dict[str, Any] = {}
        matches: list[FieldMatch] = []

        for key, value in flat.items():
            str_val = str(value) if value is not None else None
            match = self.identify(key, value=str_val)
            matches.append(match)

            if match.is_matched:
                final = normalize_value(match.canonical, value) if self._normalize else value
                _merge(normalized, match.canonical, final)
            else:
                unmapped[key] = value

        return MappingResult(normalized=normalized, unmapped=unmapped, field_matches=tuple(matches))

    @staticmethod
    def _flatten(
        payload: dict[str, Any],
        depth: int,
        _prefix: str = "",
        _current: int = 1,
    ) -> dict[str, Any]:
        """Recursively flatten nested dicts up to *depth* levels.

        Nested keys are joined with ``_``.  Non-dict values and dicts
        beyond the depth limit are preserved as-is.
        """
        result: dict[str, Any] = {}
        for key, value in payload.items():
            full_key = f"{_prefix}{key}" if _prefix else key
            if isinstance(value, dict) and _current < depth:
                result.update(ContactMapper._flatten(value, depth, f"{full_key}.", _current + 1))
            else:
                result[full_key] = value
        return result

    def map_batch(
        self, payloads: Sequence[dict[str, Any]], *, service: str | None = None, depth: int = 1
    ) -> list[MappingResult]:
        """Process multiple payloads."""
        return [self.map_payload(p, depth=depth) for p in payloads]

    @property
    def registry(self) -> PatternRegistry:
        return self._registry

    def __repr__(self) -> str:
        return f"ContactMapper(strategies={[s.name for s in self._strategies]}, " f"normalize={self._normalize})"


def _merge(target: dict[str, Any], key: str, value: Any) -> None:
    """Merge *value* into *target[key]*, promoting to list on collision."""
    if key not in target:
        target[key] = value
        return
    existing = target[key]
    if isinstance(existing, list):
        existing.append(value)
    else:
        target[key] = [existing, value]
