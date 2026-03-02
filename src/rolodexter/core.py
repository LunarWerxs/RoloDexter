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
    DISCORD = "discord"
    TELEGRAM = "telegram"
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
    # Demographics
    GENDER = "gender"
    TIMEZONE = "timezone"
    LANGUAGE_PREFERENCE = "language_preference"
    REFERRER_URL = "referrer_url"
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


class PhoneNormalizer:
    """Normalize phone values to E.164 via ``phonenumbers``.

    Delegates to Google's libphonenumber (via the ``phonenumbers`` hard
    dependency) for parsing and E.164 formatting.  Returns the original
    value unchanged if the input cannot be interpreted as a phone number.

    .. versionchanged:: 2.5.0
       Manual regex fallback removed; ``phonenumbers`` handles all cases.
    """

    @classmethod
    def normalize(cls, value: str, *, default_region: str | None = None) -> str:
        if not value or not isinstance(value, str):
            return value  # type: ignore[return-value]

        raw = value.strip()
        if not raw:
            return value

        from . import _phone

        result = _phone.format_e164(raw, default_region)
        if result is not None:
            return result

        return value


class EmailNormalizer:
    @staticmethod
    def normalize(value: str) -> str:
        if not value or not isinstance(value, str):
            return value  # type: ignore[return-value]
        return value.strip().lower()


class NameNormalizer:
    """Normalize and parse names via ``nameparser``.

    Delegates to the ``nameparser`` library for culturally-aware
    capitalisation, particle handling ("van der", "de la", etc.),
    title recognition, and suffix detection.

    .. versionchanged:: 2.5.0
       Replaced manual particle set with ``nameparser.HumanName``.
    """

    # Particles missing from nameparser's built-in prefix set.
    _EXTRA_PREFIXES: tuple[str, ...] = (
        "ten",
        "ter",
        "zur",
        "zum",
        "das",
        "des",
        "op",
        "el",
        "af",
    )
    _prefixes_patched: bool = False

    @classmethod
    def _ensure_prefixes(cls) -> None:
        """Add missing particles to nameparser on first use (once)."""
        if cls._prefixes_patched:
            return
        from nameparser.config import CONSTANTS  # type: ignore[import-untyped]

        CONSTANTS.prefixes.add(*cls._EXTRA_PREFIXES)
        cls._prefixes_patched = True

    @classmethod
    def normalize(cls, value: str) -> str:
        """Capitalize a name string with culturally-aware rules."""
        if not value or not isinstance(value, str):
            return value  # type: ignore[return-value]
        text = value.strip()
        if not text:
            return value

        cls._ensure_prefixes()
        from nameparser import HumanName  # type: ignore[import-untyped]

        hn = HumanName(text.lower())
        hn.capitalize()
        return str(hn)

    @classmethod
    def parse(cls, value: str) -> dict[str, str]:
        """Parse a name string into structured components.

        Returns a dict with keys: ``title``, ``first``, ``middle``,
        ``last``, ``suffix``, ``nickname``.

        .. versionadded:: 2.5.0
        """
        cls._ensure_prefixes()
        from nameparser import HumanName  # type: ignore[import-untyped]

        hn = HumanName(value.strip())
        return {
            "title": str(hn.title),
            "first": str(hn.first),
            "middle": str(hn.middle),
            "last": str(hn.last),
            "suffix": str(hn.suffix),
            "nickname": str(hn.nickname),
        }


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


class PostalCodeNormalizer:
    """Uppercase and format postal codes."""

    _CA_RE = re.compile(r"^([A-Z]\d[A-Z])(\d[A-Z]\d)$")

    @classmethod
    def normalize(cls, value: str) -> str:
        if not value or not isinstance(value, str):
            return value  # type: ignore[return-value]
        cleaned = value.strip().upper()
        m = cls._CA_RE.match(cleaned)
        if m:
            return f"{m.group(1)} {m.group(2)}"
        return cleaned


class BooleanNormalizer:
    """Normalize boolean-like strings to Python bools."""

    _TRUE = frozenset({"true", "yes", "1", "on", "y", "opted_in", "subscribed", "opt_in"})
    _FALSE = frozenset({"false", "no", "0", "off", "n", "opted_out", "unsubscribed", "opt_out"})

    @classmethod
    def normalize(cls, value: str) -> bool | str:
        if not isinstance(value, str):
            return value  # type: ignore[return-value]
        lower = value.strip().lower()
        if lower in cls._TRUE:
            return True
        if lower in cls._FALSE:
            return False
        return value.strip()


# Category sets — each canonical field belongs to exactly one normalizer group.
# Adding a new CanonicalField? Just add it to the right set below.
_PHONE_FIELDS: frozenset[str] = frozenset({"phone", "home_phone", "work_phone", "fax", "whatsapp"})
_NAME_FIELDS: frozenset[str] = frozenset(
    {"first_name", "last_name", "full_name", "middle_name", "nickname", "prefix", "suffix"}
)
_ADDRESS_FIELDS: frozenset[str] = frozenset({"address_line1", "address_line2", "city", "full_address"})
_BOOLEAN_FIELDS: frozenset[str] = frozenset({"email_opt_out", "subscribed", "verified"})
_SOCIAL_FIELDS: frozenset[str] = frozenset(
    {"website", "linkedin", "twitter", "facebook", "instagram", "github", "youtube", "tiktok", "discord", "telegram"}
)

# Build the lookup dict programmatically from the category sets.
_FIELD_NORMALIZERS: dict[str, type] = {
    **{f: PhoneNormalizer for f in _PHONE_FIELDS},
    **{f: NameNormalizer for f in _NAME_FIELDS},
    **{f: AddressNormalizer for f in _ADDRESS_FIELDS},
    **{f: BooleanNormalizer for f in _BOOLEAN_FIELDS},
    **{f: StringNormalizer for f in _SOCIAL_FIELDS},
    "email": EmailNormalizer,
    "postal_code": PostalCodeNormalizer,
    # Remaining fields default to StringNormalizer via normalize_value()
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
    aliases are merged into the alias index:

    * ``None`` or ``[]`` (default) — **English only**, no i18n.
    * ``"all"`` — every supported language (generates on first use).
    * ``["es", "fr"]`` — only the listed language codes are loaded
      (generated on first use if not already cached).

    Generated i18n files are cached so translation only happens once.
    Requires ``deep-translator`` to be installed for generation.
    """

    __slots__ = (
        "_all_aliases",
        "_canonical_fields",
        "_data",
        "_languages",
        "_loaded_languages",
        "_reverse_index",
    )

    def __init__(
        self,
        patterns: dict[str, Any] | None = None,
        patterns_path: str | None = None,
        languages: str | Sequence[str] | None = None,
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

    def _build_indexes(self) -> None:
        fields: dict[str, list[str]] = self._data.get("fields", {})
        for canonical, aliases in fields.items():
            self._canonical_fields.append(canonical)
            for alias in aliases:
                key = alias.lower().strip()
                if key not in self._reverse_index:
                    self._reverse_index[key] = canonical
                self._all_aliases.append(key)

        # ── expansion rules (programmatic alias generation) ─────────
        self._apply_expansion_rules()

        # ── i18n layer (on-demand) ──────────────────────────────────
        from .i18n import SUPPORTED_LANGUAGES, discover_cached, load_cached

        if self._languages == "all":
            lang_codes = sorted(SUPPORTED_LANGUAGES.keys())
        elif self._languages:
            lang_codes = list(self._languages) if not isinstance(self._languages, str) else [self._languages]
        else:
            lang_codes = []

        for lang in lang_codes:
            # Try loading from cache first (no translation needed)
            lang_data = load_cached(lang)
            if lang_data is None:
                # Try to generate on the fly
                try:
                    from .i18n import generate_language

                    lang_data = generate_language(lang)
                except (ImportError, ValueError):
                    # deep-translator not installed or unsupported lang
                    continue

            if lang_data is None:
                continue

            self._loaded_languages.append(lang)
            for canonical, aliases in lang_data.get("fields", {}).items():
                for alias in aliases:
                    key = alias.lower().strip()
                    if key not in self._reverse_index:
                        self._reverse_index[key] = canonical
                    self._all_aliases.append(key)

    def _apply_expansion_rules(self) -> None:
        """Expand compact ``expansion`` rules in patterns.json into aliases.

        This eliminates hundreds of hand-written prefix/suffix permutations
        (``billing_email``, ``shipping_city``, ``twitter_url``, …) by
        generating them from concise rule tables at load time.
        """
        expansion = self._data.get("expansion")
        if not expansion:
            return

        def _register(alias: str, canonical: str) -> None:
            key = alias.lower().strip()
            if key not in self._reverse_index:
                self._reverse_index[key] = canonical
                self._all_aliases.append(key)

        # ── form prefixes (billing_, shipping_, your_, …) ──────────
        form_prefixes: list[str] = expansion.get("form_prefixes", [])
        form_fields: dict[str, str] = expansion.get("form_fields", {})
        for prefix in form_prefixes:
            for suffix, canonical in form_fields.items():
                _register(f"{prefix}{suffix}", canonical)

        # ── social suffixes (_url, _handle, _profile, …) ───────────
        social_suffixes: list[str] = expansion.get("social_suffixes", [])
        social_fields: list[str] = expansion.get("social_fields", [])
        for platform in social_fields:
            for suffix in social_suffixes:
                _register(f"{platform}{suffix}", platform)

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
        """All supported language codes (whether cached or not)."""
        from .i18n import SUPPORTED_LANGUAGES

        return sorted(SUPPORTED_LANGUAGES.keys())

    @property
    def cached_languages(self) -> list[str]:
        """Language codes that have cached i18n files ready to use."""
        from .i18n import discover_cached

        return sorted(discover_cached().keys())

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

    # ── Strippable prefixes (module-level constants) ──
    # These are intentionally NOT duplicated; NormalizedMatchStrategy reads
    # the same objects that the expansion engine could reference if needed.

    # Vendor-specific prefixes to strip
    _VENDOR_PREFIXES = (
        "hs_",
        "hubspot_",
        "sf_",
        "salesforce_",
        "sl_",
        "smartlead_",
    )

    # Address/context prefixes (the suffix IS the field).
    # Superset of expansion form_prefixes that overlap with address contexts.
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

        # Exclude very short aliases (≤2 chars) — they cause false positives
        # with WRatio partial matching (e.g. "co" matching "column").
        # Short aliases still work via exact/normalized strategies.
        filtered = [a for a in aliases if len(a) > 2]
        if not filtered:
            return None

        result = process.extractOne(clean, filtered, scorer=fuzz.WRatio, score_cutoff=FUZZY_MATCH_THRESHOLD)
        if result is None:
            return None

        matched_alias, score, _ = result
        canonical = self._registry.exact_lookup(matched_alias)
        if canonical is None:
            return None

        confidence = FUZZY_HIGH_CONFIDENCE if score >= 90 else FUZZY_LOW_CONFIDENCE
        return FieldMatch(original=header, canonical=canonical, confidence=confidence, strategy=self.name)


# ── Social URL data table ──
# (canonical, domain(s), path_regex_suffix)
# Adding a new platform = 1 row here.
_SOCIAL_URL_DEFS: tuple[tuple[str, str | tuple[str, ...], str], ...] = (
    ("linkedin", "linkedin.com", r"(in|company|pub|school)/"),
    ("twitter", ("twitter.com", "x.com"), r"[a-zA-Z0-9_]+/?$"),
    ("instagram", "instagram.com", r"[a-zA-Z0-9_.]+/?$"),
    ("github", "github.com", r"[a-zA-Z0-9\-]+/?$"),
    ("facebook", ("facebook.com", "fb.com"), r"[a-zA-Z0-9.]+/?$"),
    ("youtube", "youtube.com", r"((channel|c)/[a-zA-Z0-9\-_]+|@[a-zA-Z0-9\-_]+)/?$"),
    ("tiktok", "tiktok.com", r"@[a-zA-Z0-9_.]+/?$"),
)


def _build_social_url_patterns() -> tuple[tuple[str, re.Pattern[str]], ...]:
    """Generate compiled social URL regexes from *_SOCIAL_URL_DEFS*."""
    result: list[tuple[str, re.Pattern[str]]] = []
    for field, domains, path in _SOCIAL_URL_DEFS:
        if isinstance(domains, tuple):
            domain_re = "|".join(re.escape(d) for d in domains)
        else:
            domain_re = re.escape(domains)
        result.append((field, re.compile(rf"^https?://(www\.)?({domain_re})/{path}", re.IGNORECASE)))
    return tuple(result)


class HeuristicMatchStrategy(MatchStrategy):
    """Regex data-shape detection for unrecognisable headers."""

    _PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
        # Email
        ("email", re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")),
        # Phone
        ("phone", re.compile(r"^\+?1?\s*[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}$")),
        ("phone", re.compile(r"^\+?[1-9]\d{6,14}$")),
        # Social media URLs — generated from _SOCIAL_URL_DEFS at import time
        *_build_social_url_patterns(),
        # Generic URLs
        ("website", re.compile(r"^https?://[^\s]+$", re.IGNORECASE)),
        ("website", re.compile(r"^www\.[^\s]+\.[a-zA-Z]{2,}$", re.IGNORECASE)),
        # Social handle (ambiguous — low confidence inherent in heuristic)
        ("twitter", re.compile(r"^@[a-zA-Z0-9_]{1,15}$")),
        # Postal codes
        ("postal_code", re.compile(r"^\d{5}(-\d{4})?$")),
        ("postal_code", re.compile(r"^[A-Z]\d[A-Z]\s?\d[A-Z]\d$", re.IGNORECASE)),
        ("postal_code", re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}$", re.IGNORECASE)),
        # Dates
        ("birthday", re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$")),
        ("birthday", re.compile(r"^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$")),
        ("birthday", re.compile(r"^\d{1,2}\.\d{1,2}\.\d{2,4}$")),
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
        languages: str | Sequence[str] | None = None,
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
