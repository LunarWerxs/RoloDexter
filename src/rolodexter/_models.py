"""Exceptions, the canonical field enum, and the mapping result models.

Extracted verbatim from ``core.py``, which re-imports every name here so
``rolodexter.core`` keeps the whole surface its callers and tests import.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, unique
from typing import Any

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
#  WARNINGS
# ═══════════════════════════════════════════════════════════════════════


@unique
class WarningCategory(str, Enum):
    """Machine-readable classification for a :class:`MappingWarning`.

    .. versionadded:: 2.11.0
    """

    LOW_CONFIDENCE = "low_confidence"
    PHONE_NORMALIZATION = "phone_normalization"
    EMAIL_VALIDATION = "email_validation"
    EMBEDDED_PHONE_LIMIT = "embedded_phone_limit"
    DATE_AMBIGUOUS = "date_ambiguous"
    OTHER = "other"


class MappingWarning(str):
    """A warning message that also carries its category.

    Subclasses :class:`str`, so it compares, formats, joins and JSON-serializes
    exactly like the plain strings :attr:`MappingResult.warnings` has always
    held — existing callers need no changes.  What it adds is
    :attr:`category`, so :meth:`ContactMapper.profile` can group warnings by
    what they *are* rather than by matching substrings of their English text.
    A reworded message used to silently reclassify every warning as
    ``"other"``, which quietly broke any pipeline gating on
    :attr:`MappingProfile.warning_counts`.

    .. versionadded:: 2.11.0
    """

    __slots__ = ("category",)

    category: str

    def __new__(
        cls, message: str, category: str | WarningCategory = WarningCategory.OTHER
    ) -> MappingWarning:
        obj = super().__new__(cls, message)
        obj.category = (
            category.value if isinstance(category, WarningCategory) else str(category)
        )
        return obj

    def __repr__(self) -> str:
        return f"MappingWarning({str(self)!r}, category={self.category!r})"


def _warning_category(warning: str) -> str:
    """Return the category of *warning*, tolerating a plain ``str``.

    :class:`MappingResult` is a public dataclass a caller may construct by
    hand with ordinary strings, so fall back to the pre-2.11 text matching
    rather than losing the classification entirely.
    """
    category = getattr(warning, "category", None)
    if isinstance(category, str):
        return category
    if "dropped low-confidence match" in warning:
        return WarningCategory.LOW_CONFIDENCE.value
    if "could not be normalized to E.164" in warning:
        return WarningCategory.PHONE_NORMALIZATION.value
    if "embedded phone" in warning:
        return WarningCategory.EMBEDDED_PHONE_LIMIT.value
    return WarningCategory.OTHER.value


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
        # Scope IDs by vendor ONLY when the payload names exactly one vendor.
        #
        # When several headers collide onto ``source_id`` and several onto
        # ``source_service``, the two lists are built independently by
        # ``_merge`` from raw dict key order — nothing links position *i* of
        # one to position *i* of the other.  Zipping them would emit a
        # confident, fabricated key such as ``source:hubspot:222`` for a
        # record that came from somewhere else, silently corrupting any
        # dedup built on this API.  Ambiguous means unqualified, which is
        # merely less specific rather than wrong.
        service = normalized_services[0] if len(normalized_services) == 1 else ""
        prefix = f"source:{service}" if service else "source_id"
        for source_id in source_ids:
            if source_id is None:
                continue
            text = str(source_id).strip()
            if text:
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
