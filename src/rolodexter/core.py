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
    """Raised when a requested service profile does not exist in the registry."""


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
    UNKNOWN = "unknown"


# Confidence thresholds
EXACT_MATCH_CONFIDENCE: float = 1.0
SERVICE_MATCH_CONFIDENCE: float = 0.95
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


class PhoneNormalizer:
    _STRIP = _PHONE_STRIP

    @classmethod
    def normalize(cls, value: str) -> str:
        if not value or not isinstance(value, str):
            return value  # type: ignore[return-value]
        digits = cls._STRIP.sub("", value.strip())
        if not digits:
            return value
        if len(digits) > 10 and not digits.startswith("+"):
            digits = "+" + digits
        return digits


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
    """Immutable index over the master ``patterns.json`` truth table."""

    __slots__ = ("_all_aliases", "_canonical_fields", "_data", "_reverse_index", "_service_indexes")

    def __init__(
        self,
        patterns: dict[str, Any] | None = None,
        patterns_path: str | None = None,
    ) -> None:
        if patterns is not None:
            self._data = patterns
        elif patterns_path is not None:
            self._data = self._load_from_path(patterns_path)
        else:
            self._data = self._load_default()

        self._reverse_index: dict[str, str] = {}
        self._service_indexes: dict[str, dict[str, str]] = {}
        self._all_aliases: list[str] = []
        self._canonical_fields: list[str] = []
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

        services: dict[str, dict[str, str]] = self._data.get("services", {})
        for svc_name, mapping in services.items():
            idx: dict[str, str] = {}
            for svc_field, canonical in mapping.items():
                idx[svc_field.lower().strip()] = canonical
            self._service_indexes[svc_name.lower()] = idx

    def exact_lookup(self, header: str) -> str | None:
        return self._reverse_index.get(header.lower().strip())

    def service_lookup(self, header: str, service: str) -> str | None:
        svc_idx = self._service_indexes.get(service.lower())
        if svc_idx is None:
            return None
        return svc_idx.get(header.lower().strip())

    @property
    def all_aliases(self) -> list[str]:
        return self._all_aliases

    @property
    def canonical_fields(self) -> list[str]:
        return list(self._canonical_fields)

    @property
    def available_services(self) -> list[str]:
        return list(self._service_indexes)

    def get_service_mapping(self, service: str) -> dict[str, str]:
        key = service.lower()
        if key not in self._service_indexes:
            raise ServiceNotFoundError(f"Service '{service}' not found. Available: {self.available_services}")
        return dict(self._service_indexes[key])

    def get_reverse_mapping(self, service: str) -> dict[str, str]:
        forward = self.get_service_mapping(service)
        reverse: dict[str, str] = {}
        for svc_field, canonical in forward.items():
            reverse.setdefault(canonical, svc_field)
        return reverse

    @property
    def version(self) -> str:
        return self._data.get("version", "0.0.0")

    def __repr__(self) -> str:
        return (
            f"PatternRegistry(aliases={len(self._reverse_index)}, "
            f"services={len(self._service_indexes)}, "
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
    __slots__ = ("_registry",)

    def __init__(self, registry: PatternRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "service"

    def match(self, header: str, value: str | None = None, **kwargs: object) -> FieldMatch | None:
        service = kwargs.get("service")
        if not service:
            return None
        canonical = self._registry.service_lookup(header, str(service))
        if canonical is not None:
            return FieldMatch(
                original=header,
                canonical=canonical,
                confidence=SERVICE_MATCH_CONFIDENCE,
                strategy=self.name,
                service=str(service),
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

    1. Service-specific exact match (highest priority)
    2. Generic exact match against the alias index
    3. Fuzzy match for typos and variations (rapidfuzz)
    4. Heuristic match using data-shape regex patterns
    """

    __slots__ = ("_default_service", "_normalize", "_registry", "_strategies")

    def __init__(
        self,
        *,
        patterns: dict[str, Any] | None = None,
        patterns_path: str | None = None,
        default_service: str | None = None,
        normalize: bool = True,
        strategies: Sequence[MatchStrategy] | None = None,
    ) -> None:
        self._registry = PatternRegistry(patterns=patterns, patterns_path=patterns_path)
        self._normalize = normalize
        self._default_service = default_service

        if strategies is not None:
            self._strategies = list(strategies)
        else:
            self._strategies: list[MatchStrategy] = [
                ServiceMatchStrategy(self._registry),
                ExactMatchStrategy(self._registry),
                FuzzyMatchStrategy(self._registry),
                HeuristicMatchStrategy(),
            ]

    def identify(self, header: str, *, value: str | None = None, service: str | None = None) -> FieldMatch:
        """Resolve a single header to its canonical field."""
        svc = service or self._default_service
        for strategy in self._strategies:
            result = strategy.match(header, value=value, service=svc)
            if result is not None:
                return result
        return FieldMatch(original=header, canonical=CanonicalField.UNKNOWN.value, confidence=0.0, strategy="none")

    def map_payload(self, payload: dict[str, Any], *, service: str | None = None) -> MappingResult:
        """Normalize an entire contact data dictionary."""
        normalized: dict[str, Any] = {}
        unmapped: dict[str, Any] = {}
        matches: list[FieldMatch] = []

        for key, value in payload.items():
            str_val = str(value) if value is not None else None
            match = self.identify(key, value=str_val, service=service)
            matches.append(match)

            if match.is_matched:
                final = normalize_value(match.canonical, value) if self._normalize else value
                _merge(normalized, match.canonical, final)
            else:
                unmapped[key] = value

        return MappingResult(normalized=normalized, unmapped=unmapped, field_matches=tuple(matches))

    def map_batch(self, payloads: Sequence[dict[str, Any]], *, service: str | None = None) -> list[MappingResult]:
        """Process multiple payloads."""
        return [self.map_payload(p, service=service) for p in payloads]

    def translate(self, payload: dict[str, Any], *, from_service: str, to_service: str) -> dict[str, Any]:
        """Translate a payload from one service schema to another."""
        result = self.map_payload(payload, service=from_service)
        reverse = self._registry.get_reverse_mapping(to_service)
        translated: dict[str, Any] = {}
        for canonical_key, value in result.normalized.items():
            target_key = reverse.get(canonical_key, canonical_key)
            translated[target_key] = value
        return translated

    @property
    def registry(self) -> PatternRegistry:
        return self._registry

    def __repr__(self) -> str:
        return (
            f"ContactMapper(strategies={[s.name for s in self._strategies]}, "
            f"normalize={self._normalize}, "
            f"default_service={self._default_service!r})"
        )


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
