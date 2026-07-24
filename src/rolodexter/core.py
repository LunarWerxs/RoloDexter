"""Rolodexter — The universal contact field mapper.

This single module contains the complete implementation:
exceptions, enums, models, normalizers, registry, strategies, and mapper.
"""
# pylint: disable=import-outside-toplevel  # optional-dep lazy imports are intentional
# pylint: disable=too-many-lines           # single-module library design

from __future__ import annotations

import json
import logging
import math
import re
import threading
from abc import ABC, abstractmethod
from bisect import bisect_left, bisect_right
from collections import Counter, OrderedDict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from enum import Enum, unique
from importlib import import_module, resources
from typing import Any, cast

# Library logger.  A NullHandler keeps rolodexter silent by default; callers
# opt into output by configuring logging on this logger (or the root).
logger = logging.getLogger("rolodexter")
logger.addHandler(logging.NullHandler())

# ═══════════════════════════════════════════════════════════════════════
#  EXCEPTIONS
# ═══════════════════════════════════════════════════════════════════════


class RolodexterError(Exception):
    """Base exception for all rolodexter errors."""


class PatternLoadError(RolodexterError):
    """Raised when pattern data cannot be loaded or parsed."""


class NormalizationError(RolodexterError):
    """Raised in ``strict`` mode when a matched field cannot be normalized.

    The most common trigger is a value that mapped to a phone field but could
    not be parsed into E.164 (e.g. a national-format number with no region).
    Outside ``strict`` mode the same condition surfaces as a non-fatal entry in
    :attr:`MappingResult.warnings`.

    .. versionadded:: 2.8.0
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
# Reject a fuzzy candidate that is far shorter than the header.  ``WRatio``'s
# partial-ratio component inflates the score of a short alias embedded in a
# longer header (e.g. ``"tel"`` inside ``"job_titel"``), which silently
# misroutes the column.  A genuine typo barely changes a header's length, so we
# require the shorter of (alias, header) to be at least this fraction of the
# longer before accepting the match.
FUZZY_LENGTH_RATIO: float = 0.5
HEURISTIC_CONFIDENCE: float = 0.60
EMBEDDED_PHONE_MAX_TEXT_CHARS: int = 8192
EMBEDDED_PHONE_MAX_MATCHES_PER_FIELD: int = 5
EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD: int = 20
DEFAULT_HEADER_CACHE_MAX_SIZE: int = 4096

__all__ = [
    "DEFAULT_HEADER_CACHE_MAX_SIZE",
    "EMBEDDED_PHONE_MAX_MATCHES_PER_FIELD",
    "EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD",
    "EMBEDDED_PHONE_MAX_TEXT_CHARS",
    "EXACT_MATCH_CONFIDENCE",
    "FUZZY_HIGH_CONFIDENCE",
    "FUZZY_LENGTH_RATIO",
    "FUZZY_LOW_CONFIDENCE",
    "FUZZY_MATCH_THRESHOLD",
    "HEURISTIC_CONFIDENCE",
    "NORMALIZED_MATCH_CONFIDENCE",
    "AddressNormalizer",
    "BooleanNormalizer",
    "CanonicalField",
    "ContactMapper",
    "EmailNormalizer",
    "ExactMatchStrategy",
    "FieldMatch",
    "FuzzyMatchStrategy",
    "HeuristicMatchStrategy",
    "ListNormalizer",
    "MappingProfile",
    "MappingResult",
    "MappingSchema",
    "MatchStrategy",
    "NameNormalizer",
    "NormalizationError",
    "NormalizedMatchStrategy",
    "PatternLoadError",
    "PatternRegistry",
    "PhoneNormalizer",
    "PostalCodeNormalizer",
    "RolodexterError",
    "StringNormalizer",
    "normalize_value",
]


def _validate_confidence_threshold(value: float) -> float:
    """Return *value* as a float if it is inside the public confidence range."""
    threshold = float(value)
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("confidence_threshold must be between 0.0 and 1.0")
    return threshold


def _value_for_matching(value: Any) -> str | None:
    """Convert only scalar values for value-shape matching."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bool | int | float):
        return str(value)
    return None


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
    """Result of normalizing an entire contact data payload.

    .. versionchanged:: 2.8.0
       Added :attr:`warnings` (non-fatal issues such as a phone value that
       could not be normalized to E.164, or a low-confidence match) and the
       :meth:`explain` helper.  ``get_match`` is now O(1) via a lazily-built
       index.
    """

    normalized: dict[str, Any]
    unmapped: dict[str, Any]
    field_matches: tuple[FieldMatch, ...]
    warnings: tuple[str, ...] = ()
    # Lazily-built {original_header: FieldMatch} index for O(1) get_match.
    # Not part of equality/repr; populated on first lookup.
    _index: dict[str, FieldMatch] | None = field(
        default=None, init=False, repr=False, compare=False
    )

    @property
    def match_rate(self) -> float:
        total = len(self.field_matches)
        return self.matched_count / total if total else 0.0

    @property
    def matched_count(self) -> int:
        return sum(1 for m in self.field_matches if m.is_matched)

    @property
    def unmatched_count(self) -> int:
        return len(self.field_matches) - self.matched_count

    def get_match(self, original_header: str) -> FieldMatch | None:
        """Return the :class:`FieldMatch` for *original_header*, or ``None``.

        The header→match index is built once on first call and reused, so
        repeated lookups (and large payloads) are O(1) per lookup.
        """
        idx = self._index
        if idx is None:
            idx = {m.original: m for m in self.field_matches}
            object.__setattr__(self, "_index", idx)
        return idx.get(original_header)

    def explain(self) -> str:
        """Return a human-readable, multi-line summary of the mapping.

        Useful from the REPL or the ``rolodexter explain`` CLI to see exactly
        how each header resolved, what was dropped, and any warnings.

        .. versionadded:: 2.8.0
        """
        lines = [
            f"Mapping: {self.matched_count} matched, "
            f"{self.unmatched_count} unmatched "
            f"(match rate {self.match_rate:.0%})",
        ]
        for m in self.field_matches:
            arrow = "->" if m.is_matched else " x"
            lines.append(
                f"  {m.original!r} {arrow} {m.canonical} "
                f"[{m.strategy}, conf={m.confidence:.2f}]"
            )
        if self.warnings:
            lines.append("Warnings:")
            lines.extend(f"  ! {w}" for w in self.warnings)
        return "\n".join(lines)

    def get_all_phones(self) -> list[str]:
        """Return all phone values from ``normalized``, deduplicated.

        Collects values from every phone-adjacent canonical field
        (``phone``, ``home_phone``, ``work_phone``, ``fax``, ``whatsapp``)
        and returns them in a single flat list with duplicates removed.

        .. versionadded:: 2.6.0
        """
        phones: list[str] = []
        for key in ("phone", "home_phone", "work_phone", "fax", "whatsapp"):
            val = self.normalized.get(key)
            if val is None:
                continue
            if isinstance(val, list):
                phones.extend(str(v) for v in val)
            else:
                phones.append(str(val))
        # Deduplicate preserving order
        seen: set[str] = set()
        result: list[str] = []
        for p in phones:
            if p not in seen:
                seen.add(p)
                result.append(p)
        return result

    def get_all_emails(self) -> list[str]:
        """Return every email value from ``normalized``, deduplicated.

        Email collisions are represented as a list by the mapper. This helper
        provides the same flat, order-preserving convenience as
        :meth:`get_all_phones`.
        """
        value = self.normalized.get("email")
        emails = value if isinstance(value, list) else [value]
        result: list[str] = []
        for email in emails:
            if email is None:
                continue
            text = str(email)
            if text not in result:
                result.append(text)
        return result

    def get_identity_keys(self) -> list[str]:
        """Return stable, prefixed identifiers suitable for deduplication.

        Keys are emitted in deterministic order from normalized emails,
        phones, and source IDs. Prefixes keep unlike identifiers in separate
        namespaces, while ``source_service`` scopes vendor IDs when available.
        Empty values are ignored and duplicates are removed.
        """
        keys: list[str] = []

        def add(key: str) -> None:
            if key and key not in keys:
                keys.append(key)

        for email in self.get_all_emails():
            text = email.strip().lower()
            if text:
                add(f"email:{text}")
        for phone in self.get_all_phones():
            text = phone.strip()
            if text:
                add(f"phone:{text}")

        raw_ids = self.normalized.get("source_id")
        source_ids = raw_ids if isinstance(raw_ids, list) else [raw_ids]
        raw_service = self.normalized.get("source_service")
        services = raw_service if isinstance(raw_service, list) else [raw_service]
        normalized_services = [
            str(value).strip().lower() if value is not None else ""
            for value in services
        ]
        for index, source_id in enumerate(source_ids):
            if source_id is None:
                continue
            text = str(source_id).strip()
            if text:
                if len(normalized_services) == 1:
                    service = normalized_services[0]
                elif index < len(normalized_services):
                    service = normalized_services[index]
                else:
                    service = ""
                prefix = f"source:{service}" if service else "source_id"
                add(f"{prefix}:{text}")
        return keys

    def to_dict(self) -> dict[str, Any]:
        # Single pass over field_matches: count and serialize together.
        matched = 0
        details: list[dict[str, Any]] = []
        for m in self.field_matches:
            if m.is_matched:
                matched += 1
            details.append(
                {
                    "original": m.original,
                    "canonical": m.canonical,
                    "confidence": m.confidence,
                    "strategy": m.strategy,
                    "service": m.service,
                }
            )
        total = len(self.field_matches)
        return {
            "normalized": dict(self.normalized),
            "unmapped": dict(self.unmapped),
            "match_rate": round(matched / total if total else 0.0, 4),
            "matched": matched,
            "unmatched": total - matched,
            "warnings": list(self.warnings),
            "details": details,
        }


@dataclass(frozen=True, slots=True)
class MappingProfile:
    """Aggregate mapping diagnostics for a batch or stream of contacts."""

    rows_seen: int
    fields_seen: int
    matched_count: int
    unmatched_count: int
    canonical_counts: dict[str, int]
    unmapped_counts: dict[str, int]
    strategy_counts: dict[str, int]
    warning_counts: dict[str, int]

    @property
    def match_rate(self) -> float:
        """Fraction of mapping decisions that resolved to a canonical field."""
        return self.matched_count / self.fields_seen if self.fields_seen else 0.0

    @property
    def warning_count(self) -> int:
        """Total warnings observed across the profiled rows."""
        return sum(self.warning_counts.values())

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable profile report."""
        return {
            "rows_seen": self.rows_seen,
            "fields_seen": self.fields_seen,
            "matched": self.matched_count,
            "unmatched": self.unmatched_count,
            "match_rate": round(self.match_rate, 4),
            "warning_count": self.warning_count,
            "canonical_counts": dict(self.canonical_counts),
            "unmapped_counts": dict(self.unmapped_counts),
            "strategy_counts": dict(self.strategy_counts),
            "warning_counts": dict(self.warning_counts),
        }

    def explain(self) -> str:
        """Return a compact human-readable import-readiness report."""
        lines = [
            f"Profile: {self.rows_seen} row(s), {self.fields_seen} field(s), "
            f"{self.matched_count} matched, {self.unmatched_count} unmatched "
            f"(match rate {self.match_rate:.0%}), {self.warning_count} warning(s)"
        ]

        def section(title: str, values: dict[str, int]) -> None:
            if not values:
                return
            lines.append(f"{title}:")
            for key, count in sorted(
                values.items(), key=lambda item: (-item[1], item[0])
            ):
                lines.append(f"  {key}: {count}")

        section("Canonical fields", self.canonical_counts)
        section("Unmapped headers", self.unmapped_counts)
        section("Warnings", self.warning_counts)
        return "\n".join(lines)


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
            return value

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
            return value
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
    _prefix_lock = threading.Lock()

    @classmethod
    def _ensure_prefixes(cls) -> None:
        """Add missing particles to nameparser on first use (once).

        Thread-safe — the i18n CLI uses a worker pool that may invoke
        ``NameNormalizer`` concurrently from multiple threads.
        """
        if cls._prefixes_patched:
            return
        with cls._prefix_lock:
            if cls._prefixes_patched:
                return
            from nameparser.config import CONSTANTS

            CONSTANTS.prefixes.add(*cls._EXTRA_PREFIXES)
            cls._prefixes_patched = True

    @classmethod
    def normalize(cls, value: str) -> str:
        """Capitalize a name string with culturally-aware rules."""
        if not value or not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return value

        cls._ensure_prefixes()
        from nameparser import HumanName

        hn = HumanName(text.lower())
        hn.capitalize()
        result = str(hn)
        # ``nameparser`` >= 1.2 leaves a *leading* recognized particle
        # lowercase (e.g. "ter braak" -> "ter Braak"), whereas older
        # releases capitalized it. A normalized display name should always
        # begin with an uppercase letter, so fix the first character here
        # without disturbing internal particle casing ("Jan van der Berg").
        if result[:1].islower():
            result = result[:1].upper() + result[1:]
        return result

    @classmethod
    def parse(cls, value: str) -> dict[str, str]:
        """Parse a name string into structured components.

        Returns a dict with keys: ``title``, ``first``, ``middle``,
        ``last``, ``suffix``, ``nickname``.

        .. versionadded:: 2.5.0
        """
        cls._ensure_prefixes()
        from nameparser import HumanName

        hn = HumanName(value.strip())
        return {
            "title": str(hn.title),
            "first": str(hn.first),
            "middle": str(hn.middle),
            "last": str(hn.last),
            "suffix": str(hn.suffix),
            "nickname": str(hn.nickname),
        }


# ── Address title-casing helpers ──
# ``str.title()`` mangles real-world address tokens (``MCDONALD`` → ``Mcdonald``,
# ``5TH`` → ``5Th``, possessives like ``Macy's`` → ``Macy'S``).  These helpers do
# a conservative title-case that preserves ordinals, Mc-names, already-mixed-case
# tokens, and apostrophe segments.
_ORDINAL_RE = re.compile(r"^\d+(?:st|nd|rd|th)$")


def _cap_part(part: str) -> str:
    """Capitalize a single apostrophe-free word with address-aware rules."""
    if not part:
        return part
    low = part.lower()
    if _ORDINAL_RE.match(low):  # 5th, 21st, 2nd — keep the ordinal suffix lower
        return low
    if low.startswith("mc") and len(low) > 2:  # mcdonald → McDonald
        return "Mc" + low[2].upper() + low[3:]
    return low[:1].upper() + low[1:]


def _smart_titlecase(text: str) -> str:
    """Title-case *text* (whitespace already collapsed) without mangling.

    Preserves tokens that already carry internal mixed case (``McDonald``,
    ``iPhone``), handles ordinals and Mc-names, and capitalizes apostrophe
    segments only when long enough (``O'Brien`` but not ``Macy'S``).
    """
    out: list[str] = []
    for word in text.split():
        # Preserve tokens that already mix upper and lower case.
        if (
            not word.isupper()
            and not word.islower()
            and any(c.isupper() for c in word[1:])
        ):
            out.append(word)
            continue
        if "'" in word:
            segs = word.split("'")
            rebuilt = _cap_part(segs[0])
            for seg in segs[1:]:
                rebuilt += "'" + (_cap_part(seg) if len(seg) > 1 else seg.lower())
            out.append(rebuilt)
        else:
            out.append(_cap_part(word))
    return " ".join(out)


class AddressNormalizer:
    @staticmethod
    def normalize(value: str) -> str:
        if not value or not isinstance(value, str):
            return value
        collapsed = " ".join(value.strip().split())
        if not collapsed:
            return value
        return _smart_titlecase(collapsed)


class StringNormalizer:
    @staticmethod
    def normalize(value: str) -> str:
        if not value or not isinstance(value, str):
            return value
        return value.strip()


class PostalCodeNormalizer:
    """Uppercase and format postal codes."""

    _CA_RE = re.compile(r"^([A-Z]\d[A-Z])(\d[A-Z]\d)$")

    @classmethod
    def normalize(cls, value: str) -> str:
        if not value or not isinstance(value, str):
            return value
        cleaned = value.strip().upper()
        m = cls._CA_RE.match(cleaned)
        if m:
            return f"{m.group(1)} {m.group(2)}"
        return cleaned


class BooleanNormalizer:
    """Normalize boolean-like strings to Python bools."""

    _TRUE = frozenset(
        {"true", "yes", "1", "on", "y", "opted_in", "subscribed", "opt_in"}
    )
    _FALSE = frozenset(
        {"false", "no", "0", "off", "n", "opted_out", "unsubscribed", "opt_out"}
    )

    @classmethod
    def normalize(cls, value: str) -> bool | str:
        if not isinstance(value, str):
            return value
        lower = value.strip().lower()
        if lower in cls._TRUE:
            return True
        if lower in cls._FALSE:
            return False
        return value.strip()


class ListNormalizer:
    """Normalize list-like values to Python lists.

    Handles JSON arrays (``'["a", "b"]'``), comma-separated strings
    (``'marketing, sales'``), semicolon-separated strings, and
    pre-existing Python lists.  Single bare strings become a
    one-element list.

    .. versionadded:: 2.6.0
    """

    @staticmethod
    def normalize(value: Any) -> list[str] | Any:  # pylint: disable=too-many-return-statements
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return value
        # Try JSON array first
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [str(v).strip() for v in parsed if str(v).strip()]
            except (json.JSONDecodeError, ValueError):
                pass
        # Semicolon-separated
        if ";" in text:
            items = [s.strip() for s in text.split(";") if s.strip()]
            if items:
                return items
        # Comma-separated
        if "," in text:
            items = [s.strip() for s in text.split(",") if s.strip()]
            if items:
                return items
        # Single value → single-element list
        return [text]


# Category sets — each canonical field belongs to exactly one normalizer group.
# Adding a new CanonicalField? Just add it to the right set below.
_PHONE_FIELDS: frozenset[str] = frozenset(
    {"phone", "home_phone", "work_phone", "fax", "whatsapp"}
)
_NAME_FIELDS: frozenset[str] = frozenset(
    {
        "first_name",
        "last_name",
        "full_name",
        "middle_name",
        "nickname",
        "prefix",
        "suffix",
    }
)
_ADDRESS_FIELDS: frozenset[str] = frozenset(
    {"address_line1", "address_line2", "city", "full_address"}
)
_BOOLEAN_FIELDS: frozenset[str] = frozenset({"email_opt_out", "subscribed", "verified"})
_LIST_FIELDS: frozenset[str] = frozenset({"tags"})
_SOCIAL_FIELDS: frozenset[str] = frozenset(
    {
        "website",
        "linkedin",
        "twitter",
        "facebook",
        "instagram",
        "github",
        "youtube",
        "tiktok",
        "discord",
        "telegram",
    }
)

# Build the lookup dict programmatically from the category sets.
_FIELD_NORMALIZERS: dict[str, Any] = {  # maps canonical field → normalizer class
    **{f: PhoneNormalizer for f in _PHONE_FIELDS},
    **{f: NameNormalizer for f in _NAME_FIELDS},
    **{f: AddressNormalizer for f in _ADDRESS_FIELDS},
    **{f: BooleanNormalizer for f in _BOOLEAN_FIELDS},
    **{f: ListNormalizer for f in _LIST_FIELDS},
    **{f: StringNormalizer for f in _SOCIAL_FIELDS},
    "email": EmailNormalizer,
    "postal_code": PostalCodeNormalizer,
    # Remaining fields default to StringNormalizer via normalize_value()
}


def normalize_value(
    canonical_field: str, value: Any, *, default_region: str | None = None
) -> Any:
    """Apply the correct normalizer for *canonical_field*.

    *default_region* (ISO 3166-1 alpha-2) is forwarded to phone
    normalization so national-format numbers without a ``+`` prefix
    (e.g. ``"(202) 555-0143"``) still format to E.164.  It is ignored by
    normalizers that don't take a region.

    .. versionchanged:: 2.7.0
       Honours *default_region* for phone fields.
    """
    cls = _FIELD_NORMALIZERS.get(canonical_field, StringNormalizer)
    if cls is PhoneNormalizer:
        return cls.normalize(value, default_region=default_region)
    return cls.normalize(value)


# ═══════════════════════════════════════════════════════════════════════
#  PATTERN REGISTRY
# ═══════════════════════════════════════════════════════════════════════


class PatternRegistry:
    """Immutable index over the master ``patterns.json`` truth table.

    The optional *languages* parameter controls which i18n language
    aliases are merged into the alias index:

    * ``None`` or ``[]`` (default) — **English only**, no i18n.
    * ``"all"`` — every supported language that has a **cached** alias file.
    * ``["es", "fr"]`` — only the listed language codes, loaded from cache.

    Construction **only loads pre-generated cache files** — it never calls
    out to a translation service.  This keeps object construction fast,
    offline, and free of unbounded network latency.  Languages that have no
    cached file are skipped (with a logged warning); generate them ahead of
    time with the explicit, offline step::

        python -m rolodexter.i18n --languages es,fr   # or i18n.generate_language(...)
    """

    __slots__ = (
        "_alias_set",
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
        overrides: dict[str, str] | None = None,
    ) -> None:
        if patterns is not None:
            self._data = self._validate_data(patterns, source="custom patterns")
        elif patterns_path is not None:
            self._data = self._load_from_path(patterns_path)
        else:
            self._data = self._load_default()

        self._languages = languages
        self._reverse_index: dict[str, str] = {}
        self._all_aliases: list[str] = []
        self._alias_set: set[str] = set()
        self._canonical_fields: list[str] = []
        self._loaded_languages: list[str] = []
        self._build_indexes()

        # ── Caller overrides (after base indexes) ─────────────────
        self._apply_overrides(overrides)

    @staticmethod
    def _load_from_path(path: str) -> dict[str, Any]:
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
            raise PatternLoadError(
                f"Failed to load patterns from {path}: {exc}"
            ) from exc
        return PatternRegistry._validate_data(data, source=f"patterns file {path!r}")

    @staticmethod
    def _load_default() -> dict[str, Any]:
        try:
            pkg = resources.files("rolodexter")
            text = pkg.joinpath("patterns.json").read_text(encoding="utf-8")
            data = json.loads(text)
        except Exception as exc:
            raise PatternLoadError(f"Failed to load bundled patterns: {exc}") from exc
        return PatternRegistry._validate_data(data, source="bundled patterns")

    @staticmethod
    def _validate_data(data: Any, *, source: str) -> dict[str, Any]:
        """Validate a pattern registry before building indexes from it.

        Custom registries are part of the public API, so malformed data should
        fail once with an actionable :class:`PatternLoadError` instead of
        leaking an ``AttributeError`` midway through index construction (or,
        worse, treating a string as a sequence of one-character aliases).
        """

        def fail(detail: str) -> None:
            raise PatternLoadError(f"Invalid {source}: {detail}")

        def string_list(value: Any, name: str) -> None:
            if not isinstance(value, list) or any(
                not isinstance(item, str) or not item.strip() for item in value
            ):
                fail(f"{name} must be a list of non-empty strings")

        if not isinstance(data, dict):
            fail("top level must be an object")

        if "version" in data and not isinstance(data["version"], str):
            fail("'version' must be a string")

        fields = data.get("fields", {})
        if not isinstance(fields, dict):
            fail("'fields' must be an object")
        for canonical, aliases in fields.items():
            if not isinstance(canonical, str) or not canonical.strip():
                fail("field names must be non-empty strings")
            string_list(aliases, f"aliases for field {canonical!r}")

        expansion = data.get("expansion")
        if expansion is not None:
            if not isinstance(expansion, dict):
                fail("'expansion' must be an object")
            for key in ("form_prefixes", "social_suffixes", "social_fields"):
                if key in expansion:
                    string_list(expansion[key], f"'expansion.{key}'")
            if "form_fields" in expansion:
                form_fields = expansion["form_fields"]
                if not isinstance(form_fields, dict) or any(
                    not isinstance(key, str)
                    or not key.strip()
                    or not isinstance(value, str)
                    or not value.strip()
                    for key, value in (
                        form_fields.items() if isinstance(form_fields, dict) else ()
                    )
                ):
                    fail(
                        "'expansion.form_fields' must be an object of "
                        "non-empty string keys and values"
                    )

        return cast(dict[str, Any], data)

    def _add_alias(self, key: str, canonical: str) -> None:
        """Register *key* → *canonical* (first-write-wins on reverse_index)
        and append to ``_all_aliases`` only on first sight."""
        if key not in self._reverse_index:
            self._reverse_index[key] = canonical
        if key not in self._alias_set:
            self._alias_set.add(key)
            self._all_aliases.append(key)

    def _build_indexes(self) -> None:  # pylint: disable=too-many-branches
        fields: dict[str, list[str]] = self._data.get("fields", {})
        for canonical, aliases in fields.items():
            self._canonical_fields.append(canonical)
            for alias in aliases:
                self._add_alias(alias.lower().strip(), canonical)

        # ── expansion rules (programmatic alias generation) ─────────
        self._apply_expansion_rules()

        # ── i18n layer (cached files only — never translates over the
        #    network from inside the constructor) ─────────────────────
        from .i18n import SUPPORTED_LANGUAGES, load_cached

        if self._languages == "all":
            lang_codes = sorted(SUPPORTED_LANGUAGES.keys())
        elif self._languages:
            lang_codes = (
                list(self._languages)
                if not isinstance(self._languages, str)
                else [self._languages]
            )
        else:
            lang_codes = []

        missing: list[str] = []
        for lang in lang_codes:
            lang_data = load_cached(lang)
            if lang_data is None:
                # Deliberately do NOT translate here: that would issue
                # blocking network calls (with unbounded latency and silent
                # rate-limit failures) from inside object construction.
                # Generation is an explicit, offline step — see the class
                # docstring.  Only flag genuinely-supported languages.
                if lang in SUPPORTED_LANGUAGES:
                    missing.append(lang)
                continue

            self._loaded_languages.append(lang)
            for canonical, aliases in lang_data.get("fields", {}).items():
                for alias in aliases:
                    self._add_alias(alias.lower().strip(), canonical)

        if missing:
            import logging

            logging.getLogger(__name__).warning(
                "No cached i18n aliases for %s — these languages were NOT "
                "loaded. Generate them first (offline) with: "
                "python -m rolodexter.i18n --languages %s",
                ", ".join(missing),
                ",".join(missing),
            )

    def _apply_overrides(self, overrides: dict[str, str] | None) -> None:
        """Apply caller-supplied alias overrides with highest priority.

        Use this for vendor-specific field names that rolodexter can't
        know generically (e.g. Mailchimp per-account MMERGE fields)::

            registry = PatternRegistry(overrides={
                "MMERGE3": "full_address",
                "MMERGE6": "company",
            })

        Override entries **replace** any existing mapping for the same
        alias, so callers can correct or extend the alias index at
        construction time.

        .. versionadded:: 2.6.0
        """
        if not overrides:
            return
        if not isinstance(overrides, dict):
            raise PatternLoadError("Invalid overrides: expected an object")
        for alias, canonical in overrides.items():
            if (
                not isinstance(alias, str)
                or not alias.strip()
                or not isinstance(canonical, str)
                or not canonical.strip()
            ):
                raise PatternLoadError(
                    "Invalid overrides: aliases and canonical fields must be "
                    "non-empty strings"
                )
            key = alias.lower().strip()
            self._reverse_index[key] = canonical  # highest priority
            if key not in self._alias_set:
                self._alias_set.add(key)
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
            self._add_alias(alias.lower().strip(), canonical)

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

    def _expansion_form_prefixes(self) -> tuple[str, ...]:
        """Return ``expansion.form_prefixes`` from the loaded patterns data.

        Internal accessor so strategies that need the raw prefix list (e.g.
        address-prefix stripping) read the same truth table the alias
        expansion engine already loads, instead of hand-duplicating it.
        """
        expansion = self._data.get("expansion") or {}
        return tuple(expansion.get("form_prefixes", []))

    @property
    def all_aliases(self) -> list[str]:
        return list(self._all_aliases)

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
        return str(self._data.get("version", "0.0.0"))

    def __repr__(self) -> str:
        return (
            f"PatternRegistry(aliases={len(self._reverse_index)}, "
            f"languages={self._loaded_languages}, "
            f"version={self.version!r})"
        )


# ═══════════════════════════════════════════════════════════════════════
#  MATCHING STRATEGIES
# ═══════════════════════════════════════════════════════════════════════

# Shared header-normalization regex trio.  Every strategy below needs the
# same three transforms — split CamelCase/PascalCase, collapse non-word
# runs, and collapse underscore runs — before it can compare a raw header
# against the alias index.  Kept as one compiled set so the three strategy
# classes can't drift on the underlying pattern.
_HEADER_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_HEADER_NONWORD_RE = re.compile(r"[^\w]+")
_HEADER_UNDERSCORE_RUN_RE = re.compile(r"_+")


def _normalize_header(header: str, *, camel_split: bool = True) -> str:
    """Lowercase-and-underscore a header via the shared regex trio.

    With *camel_split* (the default), CamelCase/PascalCase boundaries are
    split into underscores before non-word collapsing — used wherever a
    header may arrive in camelCase (e.g. ``leadStatus``).  Pass ``False`` to
    skip that step when the caller only wants separator/non-word collapsing
    (e.g. an already-delimited fragment).
    """
    text = header.strip()
    if camel_split:
        text = _HEADER_CAMEL_RE.sub("_", text)
    normalized = _HEADER_NONWORD_RE.sub("_", text.lower())
    return _HEADER_UNDERSCORE_RUN_RE.sub("_", normalized).strip("_")


class MatchStrategy(ABC):
    """Protocol every matching strategy must satisfy."""

    # True when ``match()`` depends only on the header (never the value).
    # Header-only strategies are deterministic per header, so a mapper can
    # resolve each unique header once and reuse the verdict across every row
    # of a batch.  Value-dependent strategies (e.g. data-shape heuristics)
    # must run per row.  Defaults to ``False`` (conservative) so a custom
    # strategy is never cached unless it explicitly opts in.
    header_only: bool = False

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def match(
        self, header: str, value: str | None = None, **kwargs: object
    ) -> FieldMatch | None: ...


class ExactMatchStrategy(MatchStrategy):
    __slots__ = ("_registry",)
    header_only = True

    def __init__(self, registry: PatternRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "exact"

    def match(
        self, header: str, value: str | None = None, **kwargs: object
    ) -> FieldMatch | None:
        canonical = self._registry.exact_lookup(header)
        if canonical is not None:
            return FieldMatch(
                original=header,
                canonical=canonical,
                confidence=EXACT_MATCH_CONFIDENCE,
                strategy=self.name,
            )
        return None


class NormalizedMatchStrategy(MatchStrategy):
    """Smart header normalisation → exact alias lookup (confidence 0.95).

    Handles CamelCase, dot-paths, space/hyphen→underscore, indexed
    patterns (``E-mail 1 - Value``), vendor prefix stripping, address
    prefix stripping, ``_id`` suffix stripping, and number stripping —
    all with **zero** hardcoded service profiles.
    """

    __slots__ = ("_address_prefixes", "_registry")
    header_only = True

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

    # Address/context prefixes (the suffix IS the field): the subset of
    # patterns.json's expansion.form_prefixes that denote an address/contact
    # context rather than generic form scaffolding (e.g. "your_", "name_").
    # Single-sourced from the registry in __init__ so the two lists can't
    # drift — see _ADDRESS_CONTEXT_TERMS.
    _ADDRESS_CONTEXT_TERMS = frozenset(
        {
            "business",
            "mailing",
            "home",
            "other",
            "personal",
            "shipping",
            "billing",
            "primary",
            "secondary",
        }
    )

    _INDEXED_RE = re.compile(r"^(.+?)\s+\d+\s*(?:[-\u2013\u2014]\s*)?(.+)$")
    _SEP_RE = re.compile(r"[\s\-]+")
    _NUM_SUFFIX_RE = re.compile(r"_\d+")

    def __init__(self, registry: PatternRegistry) -> None:
        self._registry = registry
        self._address_prefixes = tuple(
            prefix
            for prefix in registry._expansion_form_prefixes()
            if prefix.rstrip("_-") in self._ADDRESS_CONTEXT_TERMS
        )

    @property
    def name(self) -> str:
        return "normalized"

    # ------------------------------------------------------------------
    def _lookup(self, candidate: str) -> str | None:
        return self._registry.exact_lookup(candidate)

    def _candidates(self, header: str) -> list[str]:  # pylint: disable=too-many-branches,too-many-locals,too-many-statements
        out: list[str] = []
        h = header.strip()
        if not h:
            return out

        # 1. Space / hyphen → underscore  +  strip non-word chars
        uscore = _normalize_header(h, camel_split=False)
        if uscore:
            out.append(uscore)

        # 2. CamelCase / PascalCase split
        if any(c.isupper() for c in h[1:]):
            snake = _normalize_header(h)
            if snake and snake != uscore:
                out.append(snake)

        # 3. Dot-path resolution  (e.g. Account.Name, fields.last_name)
        if "." in h:
            parts = h.rsplit(".", 1)
            prefix_raw = parts[0].lower().strip()
            suffix_raw = parts[1].strip()
            suffix_lower = self._SEP_RE.sub("_", suffix_raw).lower()
            # Context-aware: company-like prefix + 'name' → company
            last_prefix = prefix_raw.rsplit(".", 1)[-1]
            if last_prefix in self._COMPANY_PREFIXES and suffix_lower in (
                "name",
                "nombre",
            ):
                out.insert(0, "company")
            # Last segment (underscore-normalised)
            out.append(suffix_lower)
            # CamelCase split of last segment
            if any(c.isupper() for c in suffix_raw[1:]):
                snake_sfx = _normalize_header(suffix_raw)
                if snake_sfx != suffix_lower:
                    out.append(snake_sfx)

        # 4. Indexed pattern:  "E-mail 1 - Value", "Organization 1 - Title"
        m = self._INDEXED_RE.match(h)
        if m:
            grp = self._SEP_RE.sub("_", m.group(1).strip()).lower()
            prop = self._SEP_RE.sub("_", m.group(2).strip()).lower()
            out.append(f"{grp}_{prop}")  # organization_name
            out.append(prop)  # name
            out.append(grp)  # organization

        # 5. Number stripping  ("E-mail 2 Address" → e_mail_address)
        num_stripped = self._NUM_SUFFIX_RE.sub("", uscore)
        num_stripped = _HEADER_UNDERSCORE_RUN_RE.sub("_", num_stripped).strip("_")
        if num_stripped and num_stripped != uscore:
            out.append(num_stripped)

        # 6. Vendor prefix stripping  (hs_lead_status → lead_status)
        for pfx in self._VENDOR_PREFIXES:
            if uscore.startswith(pfx):
                stripped = uscore[len(pfx) :]
                if stripped:
                    out.append(stripped)

        # 7. Address prefix stripping  (business_city → city)
        for pfx in self._address_prefixes:
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
    def match(
        self, header: str, value: str | None = None, **kwargs: object
    ) -> FieldMatch | None:
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
    __slots__ = (
        "_available",
        "_cache_lock",
        "_length_index",
        "_length_index_source_len",
        "_registry",
        "_sorted_lengths",
    )
    header_only = True

    def __init__(self, registry: PatternRegistry) -> None:
        self._registry = registry
        self._length_index: list[tuple[int, str]] | None = None
        self._sorted_lengths: list[int] | None = None
        self._length_index_source_len: int = -1
        self._cache_lock = threading.Lock()
        try:
            import rapidfuzz  # noqa: F401  # pylint: disable=unused-import

            self._available = True
        except ImportError:
            self._available = False

    @property
    def name(self) -> str:
        return "fuzzy"

    def _get_length_index(self) -> list[tuple[int, str]] | None:
        """Return ``(length, alias)`` pairs (length > 2), sorted by length.

        Precomputed once and cached across calls instead of rescanning the
        full alias list on every unrecognized header: ``match()`` binary-
        searches this index down to the length band ``FUZZY_LENGTH_RATIO``
        allows, so fuzzy scoring only runs against plausible-length
        candidates rather than every alias.  The cache invalidates if the
        registry grows (e.g. lazy i18n load), detected by comparing the
        source list length.  Guarded by a lock so a single strategy
        instance is safe to share across threads.
        """
        aliases = self._registry.all_aliases
        if not aliases:
            return None
        with self._cache_lock:
            if self._length_index is None or self._length_index_source_len != len(
                aliases
            ):
                index = sorted(
                    ((len(a), a) for a in aliases if len(a) > 2),
                    key=lambda pair: pair[0],
                )
                self._length_index = index
                self._sorted_lengths = [length for length, _ in index]
                self._length_index_source_len = len(aliases)
            return self._length_index or None

    def _candidates_in_length_band(self, clean_len: int) -> list[str]:
        """Aliases whose length can pass ``FUZZY_LENGTH_RATIO`` against *clean_len*."""
        index = self._get_length_index()
        if not index or self._sorted_lengths is None:
            return []
        min_len = math.ceil(clean_len * FUZZY_LENGTH_RATIO)
        max_len = math.floor(clean_len / FUZZY_LENGTH_RATIO)
        lo = bisect_left(self._sorted_lengths, min_len)
        hi = bisect_right(self._sorted_lengths, max_len)
        return [alias for _, alias in index[lo:hi]]

    def match(
        self, header: str, value: str | None = None, **kwargs: object
    ) -> FieldMatch | None:
        if not self._available:
            return None
        from rapidfuzz import fuzz, process

        clean = _normalize_header(header, camel_split=False)

        if not clean:
            return None

        filtered = self._candidates_in_length_band(len(clean))
        if not filtered:
            return None

        # Pull several top candidates rather than only the single best: WRatio's
        # partial-ratio component can rank a short alias embedded in a longer
        # header (e.g. "tel" inside "job_titel") above the genuinely-intended
        # one.  Skip candidates whose length is far from the header's and take
        # the best survivor; this keeps real typo recovery while dropping the
        # degenerate substring matches that misroute data.
        candidates = process.extract(
            clean,
            filtered,
            scorer=fuzz.WRatio,
            score_cutoff=FUZZY_MATCH_THRESHOLD,
            limit=5,
        )
        matched_alias: str | None = None
        score = 0.0
        for alias, alias_score, _ in candidates:
            shorter, longer = sorted((len(alias), len(clean)))
            if longer and shorter / longer >= FUZZY_LENGTH_RATIO:
                matched_alias, score = alias, alias_score
                break
        if matched_alias is None:
            return None

        canonical = self._registry.exact_lookup(matched_alias)
        if canonical is None:
            return None

        confidence = FUZZY_HIGH_CONFIDENCE if score >= 90 else FUZZY_LOW_CONFIDENCE
        return FieldMatch(
            original=header,
            canonical=canonical,
            confidence=confidence,
            strategy=self.name,
        )


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
    for canonical, domains, path in _SOCIAL_URL_DEFS:
        if isinstance(domains, tuple):
            domain_re = "|".join(re.escape(d) for d in domains)
        else:
            domain_re = re.escape(domains)
        result.append(
            (
                canonical,
                re.compile(rf"^https?://(www\.)?({domain_re})/{path}", re.IGNORECASE),
            )
        )
    return tuple(result)


class HeuristicMatchStrategy(MatchStrategy):
    """Regex data-shape detection for unrecognisable headers.

    Value-dependent (``header_only = False``): the verdict depends on the
    cell value, so it is recomputed per row rather than cached.

    The *default_region* (ISO 3166-1 alpha-2, default ``"US"``) is used when
    confirming bare-digit values look like real phone numbers; pass a region
    matching your data to avoid US-centric misparsing of international rows.
    """

    __slots__ = ("_default_region",)
    header_only = False

    def __init__(self, default_region: str | None = "US") -> None:
        self._default_region = default_region

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
        (
            "postal_code",
            re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}$", re.IGNORECASE),
        ),
        # Dates
        ("birthday", re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$")),
        ("birthday", re.compile(r"^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$")),
        ("birthday", re.compile(r"^\d{1,2}\.\d{1,2}\.\d{2,4}$")),
    )
    _PHONE_HEADER_HINTS = frozenset(
        {
            "cell",
            "fax",
            "mobile",
            "phone",
            "phones",
            "sms",
            "tel",
            "telephone",
            "whatsapp",
        }
    )
    _BIRTHDAY_HEADER_HINTS = frozenset(
        {
            "birth",
            "birthday",
            "birthdate",
            "bday",
            "dob",
        }
    )
    _BIRTHDAY_HEADER_PHRASES = frozenset(
        {
            "birth_date",
            "date_of_birth",
            "day_of_birth",
        }
    )

    @property
    def name(self) -> str:
        return "heuristic"

    @classmethod
    def _header_terms(cls, header: str) -> tuple[str, set[str]]:
        normalized = _normalize_header(header)
        return normalized, {part for part in normalized.split("_") if part}

    @classmethod
    def _has_phone_header_hint(cls, header: str) -> bool:
        _normalized, terms = cls._header_terms(header)
        return bool(terms & cls._PHONE_HEADER_HINTS)

    @classmethod
    def _has_birthday_header_hint(cls, header: str) -> bool:
        normalized, terms = cls._header_terms(header)
        return bool(
            (terms & cls._BIRTHDAY_HEADER_HINTS)
            or normalized in cls._BIRTHDAY_HEADER_PHRASES
        )

    # Cap the value length the data-shape regexes scan.  Cell values are
    # caller/attacker-controlled; nothing longer than this is a phone, email,
    # URL, or postal code, so skipping long values is both correct and a cheap
    # guard against pathological inputs.
    _MAX_VALUE_LEN: int = 512

    def match(
        self, header: str, value: str | None = None, **kwargs: object
    ) -> FieldMatch | None:
        if not value or not isinstance(value, str):
            return None
        cleaned = value.strip()
        if not cleaned or len(cleaned) > self._MAX_VALUE_LEN:
            return None
        region_kw = kwargs.get("default_region")
        region = region_kw if isinstance(region_kw, str) else self._default_region
        for canonical, pattern in self._PATTERNS:
            if not pattern.match(cleaned):
                continue
            # Secondary check: when the pattern is one of the loose phone
            # regexes, confirm via libphonenumber that the digits are a
            # *possible* phone number.  Filters out 10-digit numeric IDs
            # that happen to match the bare-digit phone pattern.
            if canonical == "phone":
                if cleaned.isdigit() and not self._has_phone_header_hint(header):
                    continue
                from . import _phone

                parsed = _phone.parse(cleaned, default_region=region)
                if parsed is None:
                    continue
            if canonical == "birthday" and not self._has_birthday_header_hint(header):
                continue
            return FieldMatch(
                original=header,
                canonical=canonical,
                confidence=HEURISTIC_CONFIDENCE,
                strategy=self.name,
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

    Steps 1-3 depend only on the header, so each unique header is resolved
    **once** and the verdict is cached for reuse across every row of a batch
    (see :meth:`map_batch`).  Step 4 depends on the cell value and runs per
    row.  This makes bulk ingestion of CSV/exports (where every row shares the
    same headers) scale with the number of *unique headers*, not rows.

    *default_region* (ISO 3166-1 alpha-2, e.g. ``"GB"``, ``"AU"``) sets the
    region used by value-shape phone detection and embedded-phone extraction.
    It defaults to ``"US"``; set it to match your data to avoid US-centric
    misparsing.  It can be overridden per call via ``map_payload`` /
    ``identify``.

    Thread-safety: a single ``ContactMapper`` may be shared across threads —
    ``map_payload``/``identify`` are read-only over the registry, and the
    internal header cache and fuzzy-alias cache are guarded for concurrent
    use.

    .. versionchanged:: 2.0.0
        Per-service profiles removed.  The ``default_service`` and
        ``service`` parameters are accepted but ignored.

    .. versionchanged:: 2.6.0
        Added *overrides* parameter for caller-supplied alias mappings
        (e.g. vendor-specific merge fields).

    .. versionchanged:: 2.7.0
        Header resolution is cached across rows; added *default_region*;
        construction loads i18n caches only (no network translation).

    .. versionchanged:: 2.8.0
        Added *strict* and *confidence_threshold*; non-fatal issues are
        reported on :attr:`MappingResult.warnings`.  Added :meth:`map_stream`
        (constant-memory iteration), :meth:`compile_schema` (reusable header
        plan), and :meth:`map_dataframe` (pandas).
    """

    __slots__ = (
        "_cacheable_pipeline",
        "_confidence_threshold",
        "_default_region",
        "_default_service",
        "_header_cache",
        "_header_cache_lock",
        "_header_cache_max_size",
        "_header_strategies",
        "_normalize",
        "_registry",
        "_strategies",
        "_strict",
        "_value_strategies",
    )

    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        patterns: dict[str, Any] | None = None,
        patterns_path: str | None = None,
        default_service: str | None = None,
        normalize: bool = True,
        strategies: Sequence[MatchStrategy] | None = None,
        languages: str | Sequence[str] | None = None,
        overrides: dict[str, str] | None = None,
        default_region: str | None = "US",
        strict: bool = False,
        confidence_threshold: float = 0.0,
        header_cache_max_size: int | None = DEFAULT_HEADER_CACHE_MAX_SIZE,
    ) -> None:
        self._registry = PatternRegistry(
            patterns=patterns,
            patterns_path=patterns_path,
            languages=languages,
            overrides=overrides,
        )
        self._normalize = normalize
        self._default_region = default_region
        self._strict = strict
        self._confidence_threshold = _validate_confidence_threshold(
            confidence_threshold
        )
        if header_cache_max_size is not None and header_cache_max_size < 0:
            raise ValueError("header_cache_max_size must be non-negative or None")
        self._header_cache_max_size = header_cache_max_size
        self._default_service = (
            default_service  # accepted for backward compat; not used since v2.0
        )

        if strategies is not None:
            self._strategies = list(strategies)
        else:
            self._strategies = [
                ExactMatchStrategy(self._registry),
                NormalizedMatchStrategy(self._registry),
                FuzzyMatchStrategy(self._registry),
                HeuristicMatchStrategy(default_region=default_region),
            ]

        # ── Header-resolution cache (per unique header) ──────────────
        # Steps 1-3 are header_only=True (deterministic per header).  We can
        # split the pipeline and cache the header-only verdict ONLY when every
        # header-only strategy precedes every value-dependent one; otherwise a
        # value-dependent strategy could pre-empt a header-only match on some
        # rows and caching would change results.  Fall back to per-call
        # resolution for such custom pipelines.
        seen_value = False
        cacheable = True
        for strat in self._strategies:
            if strat.header_only:
                if seen_value:
                    cacheable = False
                    break
            else:
                seen_value = True
        self._cacheable_pipeline = cacheable
        self._header_strategies = [s for s in self._strategies if s.header_only]
        self._value_strategies = [s for s in self._strategies if not s.header_only]
        # header -> cached header-only verdict (None = all header-only missed)
        self._header_cache: OrderedDict[str, FieldMatch | None] = OrderedDict()
        self._header_cache_lock = threading.Lock()

    @staticmethod
    def _unknown(header: str) -> FieldMatch:
        return FieldMatch(
            original=header,
            canonical=CanonicalField.UNKNOWN.value,
            confidence=0.0,
            strategy="none",
        )

    def identify(  # pylint: disable=unused-argument
        self,
        header: str,
        *,
        value: str | None = None,
        service: str | None = None,
        default_region: str | None = None,
    ) -> FieldMatch:
        """Resolve a single header to its canonical field.

        The *service* parameter is accepted for backward compatibility
        but is ignored since v2.0.  *default_region* overrides the mapper's
        region for value-shape phone detection on this call only.
        """
        region = default_region if default_region is not None else self._default_region
        for strategy in self._strategies:
            result = strategy.match(header, value=value, default_region=region)
            if result is not None:
                return result
        return self._unknown(header)

    def _resolve(self, header: str, value: Any, region: str | None) -> FieldMatch:
        """Resolve a header, caching the deterministic header-only verdict.

        For a cache-friendly pipeline, header-only strategies (exact /
        normalized / fuzzy) are run at most once per unique header; only the
        value-dependent strategies (heuristic) run per call.  This is what
        makes :meth:`map_batch` scale to large, repetitive exports.
        """
        if not self._cacheable_pipeline:
            return self.identify(
                header, value=_value_for_matching(value), default_region=region
            )

        with self._header_cache_lock:
            if header in self._header_cache:
                verdict = self._header_cache[header]
                self._header_cache.move_to_end(header)
            else:
                verdict = None
                for strategy in self._header_strategies:
                    result = strategy.match(header, value=None, default_region=region)
                    if result is not None:
                        verdict = result
                        break
                if self._header_cache_max_size != 0:
                    self._header_cache[header] = verdict
                    if self._header_cache_max_size is not None:
                        while len(self._header_cache) > self._header_cache_max_size:
                            self._header_cache.popitem(last=False)

        if verdict is not None:
            return verdict

        # Header-only strategies missed — the value-dependent ones may still
        # match, and their result can differ per row, so never cache them.
        match_value = _value_for_matching(value)
        for strategy in self._value_strategies:
            result = strategy.match(header, value=match_value, default_region=region)
            if result is not None:
                return result
        return self._unknown(header)

    def clear_cache(self) -> None:
        """Clear cached header-resolution verdicts.

        Long-lived mapper instances can call this after processing a tenant or
        import job to release header cache memory without rebuilding the mapper.
        """
        with self._header_cache_lock:
            self._header_cache.clear()

    def cache_info(self) -> dict[str, Any]:
        """Return lightweight header-cache diagnostics."""
        with self._header_cache_lock:
            return {
                "size": len(self._header_cache),
                "max_size": self._header_cache_max_size,
                "cacheable_pipeline": self._cacheable_pipeline,
            }

    def map_payload(  # pylint: disable=unused-argument,too-many-locals,too-many-branches
        self,
        payload: dict[str, Any],
        *,
        service: str | None = None,
        depth: int = 1,
        extract_embedded_phones: bool = False,
        default_region: str | None = None,
        strict: bool | None = None,
        confidence_threshold: float | None = None,
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
        extract_embedded_phones : bool, default False
            When ``True``, scan all non-phone string values for embedded
            phone numbers (e.g. ``"reach me at +1-555-123-4567"``) using
            :class:`PhoneNumberMatcher` and merge any found numbers into
            the ``phone`` field of the result.

            .. versionadded:: 2.6.0
        default_region : str, optional
            Overrides the mapper's region for value-shape phone detection and
            embedded-phone extraction on this call only.  Falls back to the
            region given at construction (``"US"`` by default).

            .. versionadded:: 2.7.0
        strict : bool, optional
            Overrides the mapper's ``strict`` setting for this call.  When
            truthy, any non-fatal issue (a phone that could not be normalized
            to E.164, or a match dropped by *confidence_threshold*) raises
            :class:`NormalizationError` instead of being recorded on
            :attr:`MappingResult.warnings`.

            .. versionadded:: 2.8.0
        confidence_threshold : float, optional
            Overrides the mapper's threshold for this call.  Matches whose
            confidence is below the threshold are dropped to ``unmapped`` and
            recorded as a warning.  Defaults to ``0.0`` (keep everything).

            .. versionadded:: 2.8.0

        Returns
        -------
        MappingResult
        """
        depth = max(1, min(depth, 5))
        flat = self._flatten(payload, depth) if depth > 1 else payload
        region = default_region if default_region is not None else self._default_region
        threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else self._confidence_threshold
        )
        threshold = _validate_confidence_threshold(threshold)
        is_strict = self._strict if strict is None else strict

        normalized: dict[str, Any] = {}
        unmapped: dict[str, Any] = {}
        matches: list[FieldMatch] = []
        warnings: list[str] = []

        for key, value in flat.items():
            match = self._resolve(key, value, region)

            # Drop matches below the confidence floor (recorded, not silent).
            if match.is_matched and match.confidence < threshold:
                warnings.append(
                    f"{key!r}: dropped low-confidence match to {match.canonical!r} "
                    f"(confidence {match.confidence:.2f} < threshold {threshold:.2f})"
                )
                match = self._unknown(key)

            matches.append(match)

            if match.is_matched:
                if self._normalize:
                    final = normalize_value(
                        match.canonical, value, default_region=region
                    )
                    # Surface the silent-degradation case: a phone field whose
                    # value didn't become E.164 (e.g. wrong/missing region).
                    if (
                        match.canonical in _PHONE_FIELDS
                        and isinstance(final, str)
                        and final.strip()
                        and not final.startswith("+")
                    ):
                        warnings.append(
                            f"{key!r}: phone value {final!r} could not be normalized "
                            f"to E.164 (set a matching default_region?)"
                        )
                else:
                    final = value
                _merge(normalized, match.canonical, final)
            else:
                unmapped[key] = value

        # ── Embedded phone extraction (opt-in) ─────────────────────
        if extract_embedded_phones:
            self._extract_embedded_phones(
                normalized, unmapped, matches, warnings, region
            )

        if warnings:
            for w in warnings:
                logger.warning("%s", w)
            if is_strict:
                raise NormalizationError("; ".join(warnings))

        return MappingResult(
            normalized=normalized,
            unmapped=unmapped,
            field_matches=tuple(matches),
            warnings=tuple(warnings),
        )

    @staticmethod
    def _extract_embedded_phones(
        normalized: dict[str, Any],
        unmapped: dict[str, Any],
        matches: list[FieldMatch],
        warnings: list[str],
        default_region: str | None = None,
    ) -> None:
        """Scan non-phone string values for embedded phone numbers.

        Found numbers are merged into ``normalized["phone"]`` and
        recorded in *matches* with ``strategy="embedded_phone"``.  Scans are
        bounded by text length and match-count caps so an overlong notes field
        cannot monopolize CPU/memory; any truncation is reported in *warnings*.

        .. versionadded:: 2.6.0
        .. versionchanged:: 2.7.0 Honours *default_region*.
        """
        from . import _phone

        def candidates() -> Iterator[tuple[str, str]]:
            for key, val in unmapped.items():
                if isinstance(val, str) and len(val) > 6:
                    yield key, val
            for key, val in tuple(normalized.items()):
                if key not in _PHONE_FIELDS and isinstance(val, str) and len(val) > 6:
                    yield key, val

        found_total = 0
        warned_payload_limit = False
        for key, text in candidates():
            if found_total >= EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD:
                if not warned_payload_limit:
                    warnings.append(
                        "embedded phone extraction stopped after "
                        f"{EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD} matches "
                        "for this payload"
                    )
                    warned_payload_limit = True
                break

            scan_text = text
            if len(scan_text) > EMBEDDED_PHONE_MAX_TEXT_CHARS:
                warnings.append(
                    f"{key!r}: embedded phone scan truncated at "
                    f"{EMBEDDED_PHONE_MAX_TEXT_CHARS} characters"
                )
                scan_text = scan_text[:EMBEDDED_PHONE_MAX_TEXT_CHARS]

            remaining_payload = EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD - found_total
            field_limit = min(
                EMBEDDED_PHONE_MAX_MATCHES_PER_FIELD,
                remaining_payload,
            )
            overflow_for_field = False
            for found_for_field, pm in enumerate(
                _phone.PhoneNumberMatcher(
                    scan_text,
                    default_region=default_region,
                    max_matches=field_limit + 1,
                )
            ):
                if found_for_field >= field_limit:
                    overflow_for_field = True
                    break
                e164 = pm.number.e164
                _merge(normalized, "phone", e164)
                matches.append(
                    FieldMatch(
                        original=key,
                        canonical="phone",
                        confidence=HEURISTIC_CONFIDENCE,
                        strategy="embedded_phone",
                    )
                )
                found_total += 1

            if overflow_for_field:
                if field_limit == EMBEDDED_PHONE_MAX_MATCHES_PER_FIELD:
                    warnings.append(
                        f"{key!r}: embedded phone extraction stopped after "
                        f"{EMBEDDED_PHONE_MAX_MATCHES_PER_FIELD} matches "
                        "for this field"
                    )
                if (
                    found_total >= EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD
                    and not warned_payload_limit
                ):
                    warnings.append(
                        "embedded phone extraction stopped after "
                        f"{EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD} matches "
                        "for this payload"
                    )
                    warned_payload_limit = True

    @staticmethod
    def _flatten(
        payload: dict[str, Any],
        depth: int,
        _prefix: str = "",
        _current: int = 1,
    ) -> dict[str, Any]:
        """Recursively flatten nested dicts up to *depth* levels.

        Nested keys are joined with ``.`` (dot).  Non-dict values and
        dicts beyond the depth limit are preserved as-is.  The dot
        separator is consumed by :class:`NormalizedMatchStrategy`'s
        dot-path resolution.
        """
        result: dict[str, Any] = {}
        for key, value in payload.items():
            full_key = f"{_prefix}{key}" if _prefix else key
            if isinstance(value, dict) and _current < depth:
                result.update(
                    ContactMapper._flatten(value, depth, f"{full_key}.", _current + 1)
                )
            else:
                result[full_key] = value
        return result

    def map_batch(  # pylint: disable=unused-argument
        self,
        payloads: Sequence[dict[str, Any]],
        *,
        service: str | None = None,
        depth: int = 1,
        default_region: str | None = None,
        extract_embedded_phones: bool = False,
        strict: bool | None = None,
        confidence_threshold: float | None = None,
    ) -> list[MappingResult]:
        """Process multiple payloads, materializing all results into a list.

        Header resolution is cached on the mapper, so payloads that share the
        same headers (the typical CSV/export case) resolve each unique header
        only once across the whole batch rather than once per row.

        For very large inputs prefer :meth:`map_stream`, which yields results
        lazily and keeps memory constant.
        """
        return list(
            self.map_stream(
                payloads,
                depth=depth,
                default_region=default_region,
                extract_embedded_phones=extract_embedded_phones,
                strict=strict,
                confidence_threshold=confidence_threshold,
            )
        )

    def map_stream(
        self,
        payloads: Iterable[dict[str, Any]],
        *,
        depth: int = 1,
        default_region: str | None = None,
        extract_embedded_phones: bool = False,
        strict: bool | None = None,
        confidence_threshold: float | None = None,
    ) -> Iterator[MappingResult]:
        """Lazily map an iterable of payloads, yielding one result at a time.

        Unlike :meth:`map_batch`, this never holds more than one result in
        memory, so it scales to million-row CSV/JSONL streams.  Header
        resolution is still cached across rows.

        Example::

            import csv
            with open("contacts.csv") as fh:
                for result in mapper.map_stream(csv.DictReader(fh)):
                    write(result.normalized)

        .. versionadded:: 2.8.0
        """
        for payload in payloads:
            yield self.map_payload(
                payload,
                depth=depth,
                default_region=default_region,
                extract_embedded_phones=extract_embedded_phones,
                strict=strict,
                confidence_threshold=confidence_threshold,
            )

    def profile(
        self,
        payloads: Iterable[dict[str, Any]],
        *,
        max_rows: int | None = None,
        depth: int = 1,
        default_region: str | None = None,
        extract_embedded_phones: bool = False,
        strict: bool | None = None,
        confidence_threshold: float | None = None,
    ) -> MappingProfile:
        """Summarize mapping quality across a batch or stream.

        The profiler keeps counters rather than materializing mapped rows, so
        memory use stays bounded for large imports. ``max_rows`` can limit a
        preview without consuming an additional item from an input iterator.
        Existing mapping semantics and options are reused unchanged.
        """
        if max_rows is not None:
            if not isinstance(max_rows, int) or isinstance(max_rows, bool):
                raise TypeError("max_rows must be an integer or None")
            if max_rows < 0:
                raise ValueError("max_rows must be non-negative or None")

        canonical_counts: Counter[str] = Counter()
        unmapped_counts: Counter[str] = Counter()
        strategy_counts: Counter[str] = Counter()
        warning_counts: Counter[str] = Counter()
        rows_seen = 0
        matched_count = 0
        unmatched_count = 0
        iterator = iter(payloads)

        while max_rows is None or rows_seen < max_rows:
            try:
                payload = next(iterator)
            except StopIteration:
                break
            result = self.map_payload(
                payload,
                depth=depth,
                default_region=default_region,
                extract_embedded_phones=extract_embedded_phones,
                strict=strict,
                confidence_threshold=confidence_threshold,
            )
            rows_seen += 1
            for match in result.field_matches:
                strategy_counts[match.strategy] += 1
                if match.is_matched:
                    matched_count += 1
                    canonical_counts[match.canonical] += 1
                else:
                    unmatched_count += 1
                    unmapped_counts[match.original] += 1
            for warning in result.warnings:
                if "dropped low-confidence match" in warning:
                    category = "low_confidence"
                elif "could not be normalized to E.164" in warning:
                    category = "phone_normalization"
                elif "embedded phone" in warning:
                    category = "embedded_phone_limit"
                else:
                    category = "other"
                warning_counts[category] += 1

        return MappingProfile(
            rows_seen=rows_seen,
            fields_seen=matched_count + unmatched_count,
            matched_count=matched_count,
            unmatched_count=unmatched_count,
            canonical_counts=dict(canonical_counts),
            unmapped_counts=dict(unmapped_counts),
            strategy_counts=dict(strategy_counts),
            warning_counts=dict(warning_counts),
        )

    def compile_schema(
        self,
        headers: Iterable[str],
        *,
        default_region: str | None = None,
        strict: bool | None = None,
        confidence_threshold: float | None = None,
    ) -> MappingSchema:
        """Resolve a fixed set of headers once into a reusable mapping plan.

        Returns a :class:`MappingSchema` capturing the header-only verdict for
        each header (exact / normalized / fuzzy).  This warms the mapper's
        per-header cache and exposes a ``column_map`` (header → canonical),
        which is exactly what column-oriented callers — DataFrame renames,
        SQL ``SELECT`` aliases — need.  Value-shape heuristics are inherently
        per-row and are *not* part of a static schema; use ``apply`` / the
        mapper for those.

        .. versionadded:: 2.8.0
        """
        region = default_region if default_region is not None else self._default_region
        threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else self._confidence_threshold
        )
        threshold = _validate_confidence_threshold(threshold)
        is_strict = self._strict if strict is None else strict
        matches: dict[str, FieldMatch] = {}
        warnings: list[str] = []
        for header in headers:
            key = str(header)
            if self._cacheable_pipeline:
                # value=None → only header-only strategies fire; also warms the
                # mapper's _header_cache for subsequent row mapping.
                match = self._resolve(key, None, region)
            else:
                match = self.identify(key, default_region=region)
            if match.is_matched and match.confidence < threshold:
                warnings.append(
                    f"{key!r}: dropped low-confidence match to {match.canonical!r} "
                    f"(confidence {match.confidence:.2f} < threshold {threshold:.2f})"
                )
                match = self._unknown(key)
            matches[key] = match
        if warnings:
            for warning in warnings:
                logger.warning("%s", warning)
            if is_strict:
                raise NormalizationError("; ".join(warnings))
        return MappingSchema(matches=matches, mapper=self, default_region=region)

    def map_dataframe(
        self,
        df: Any,
        *,
        default_region: str | None = None,
        normalize: bool | None = None,
        strict: bool | None = None,
        confidence_threshold: float | None = None,
    ) -> Any:
        """Return a copy of *df* with columns renamed to canonical fields.

        Column headers are resolved via :meth:`compile_schema`; matched columns
        are renamed to their canonical name and (when *normalize* is on) their
        values are normalized.  Unmatched columns are left untouched, so no
        data is dropped.  If two source columns map to the same canonical
        field, the first keeps the canonical name and later ones get a
        ``<canonical>__N`` suffix (with a logged warning).

        Requires pandas (``pip install rolodexter[pandas]``).

        .. versionadded:: 2.8.0
        """
        try:
            import_module("pandas")
        except ImportError:
            raise ImportError(
                "map_dataframe requires pandas. Install with: "
                "pip install 'rolodexter[pandas]'"
            ) from None

        region = default_region if default_region is not None else self._default_region
        do_norm = self._normalize if normalize is None else normalize
        is_strict = self._strict if strict is None else strict
        threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else self._confidence_threshold
        )
        threshold = _validate_confidence_threshold(threshold)
        schema = self.compile_schema(
            [str(c) for c in df.columns],
            default_region=region,
            strict=is_strict,
            confidence_threshold=threshold,
        )

        columns = list(df.columns)
        if len(columns) != len(set(columns)):
            raise ValueError(
                "map_dataframe requires unique input column labels; duplicate "
                "labels cannot be renamed without ambiguity"
            )

        rename: dict[Any, str] = {}
        # Unmatched labels remain in the output. Reserve them before assigning
        # canonical names so a generated ``<canonical>__N`` label cannot
        # collide with an untouched source column and silently hide data.
        used_names: set[Any] = {
            col
            for col in columns
            if (match := schema.matches.get(str(col))) is None or not match.is_matched
        }
        next_suffix: dict[str, int] = {}
        for col in columns:
            match = schema.matches.get(str(col))
            if match is None or not match.is_matched:
                continue
            canonical = match.canonical
            suffix = next_suffix.get(canonical, 1)
            new_name = canonical if suffix == 1 else f"{canonical}__{suffix}"
            while new_name in used_names:
                suffix += 1
                new_name = f"{canonical}__{suffix}"
            next_suffix[canonical] = suffix + 1
            used_names.add(new_name)
            if new_name != canonical:
                logger.warning(
                    "map_dataframe: column %r also maps to %r; renamed to %r "
                    "to avoid a collision",
                    col,
                    canonical,
                    new_name,
                )
            rename[col] = new_name

        out = df.rename(columns=rename)
        warnings: list[str] = []
        if do_norm:
            for old_name, new_name in rename.items():
                canonical = new_name.split("__", 1)[0]
                out[new_name] = out[new_name].map(
                    lambda v, c=canonical: normalize_value(c, v, default_region=region)
                )
                if canonical in _PHONE_FIELDS:
                    for final in out[new_name]:
                        if (
                            isinstance(final, str)
                            and final.strip()
                            and not final.startswith("+")
                        ):
                            warnings.append(
                                f"{old_name!r}: phone value {final!r} could not be "
                                "normalized to E.164 (set a matching default_region?)"
                            )
        if warnings:
            for warning in warnings:
                logger.warning("%s", warning)
            if is_strict:
                raise NormalizationError("; ".join(warnings))
        return out

    @property
    def registry(self) -> PatternRegistry:
        return self._registry

    def __repr__(self) -> str:
        return (
            f"ContactMapper(strategies={[s.name for s in self._strategies]}, "
            f"normalize={self._normalize})"
        )


@dataclass(frozen=True, slots=True)
class MappingSchema:
    """A reusable header→canonical plan produced by :meth:`ContactMapper.compile_schema`.

    Captures the header-only verdict for a fixed set of headers so column-
    oriented work (DataFrame renames, CSV header mapping) resolves each header
    exactly once.  Per-row value-shape heuristics are not part of the schema;
    :meth:`apply` delegates to the mapper for full per-row semantics.

    .. versionadded:: 2.8.0
    """

    matches: dict[str, FieldMatch]
    mapper: ContactMapper
    default_region: str | None = None

    def column_map(self) -> dict[str, str]:
        """Return ``{header: canonical}`` for the matched headers only."""
        return {h: m.canonical for h, m in self.matches.items() if m.is_matched}

    def unmatched_headers(self) -> list[str]:
        """Return the headers that did not resolve to a canonical field."""
        return [h for h, m in self.matches.items() if not m.is_matched]

    def apply(self, row: dict[str, Any], **kwargs: Any) -> MappingResult:
        """Map a single *row* using the mapper (header verdicts already cached).

        Extra keyword arguments are forwarded to
        :meth:`ContactMapper.map_payload`.
        """
        kwargs.setdefault("default_region", self.default_region)
        return self.mapper.map_payload(row, **kwargs)


def _merge(target: dict[str, Any], key: str, value: Any) -> None:
    """Merge *value* into *target[key]*, promoting to list on collision.

    Duplicate values are dropped so the same normalized phone/email
    from multiple aliases (e.g. ``phone`` + ``mobile`` carrying the
    same number) appears only once.
    """
    if key in _LIST_FIELDS:
        if key not in target:
            target[key] = list(value) if isinstance(value, list) else value
            return
        incoming = value if isinstance(value, list) else [value]
        existing = target[key] if isinstance(target[key], list) else [target[key]]
        merged = list(existing)
        for item in incoming:
            if item not in merged:
                merged.append(item)
        target[key] = merged
        return

    if key not in target:
        target[key] = value
        return
    existing = target[key]
    if isinstance(existing, list):
        if value not in existing:
            existing.append(value)
    elif existing != value:
        target[key] = [existing, value]
