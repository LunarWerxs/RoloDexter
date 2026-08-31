"""The match strategies, from exact header equality up to heuristics.

Extracted verbatim from ``core.py``, which re-imports every name here so
``rolodexter.core`` keeps the whole surface its callers and tests import.
"""

from __future__ import annotations

import math
import re
import threading
from abc import ABC, abstractmethod
from bisect import bisect_left, bisect_right

from ._models import FieldMatch
from ._normalizers import (
    _HEADER_UNDERSCORE_RUN_RE,
    _PHONE_FIELDS,
    _SOCIAL_FIELDS,
    _is_reference_header,
    _normalize_header,
)
from ._patterns import PatternRegistry

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

# Fields that hold a contactable value rather than a reference to a record.
# A header like ``primary_phone_id`` names a foreign key, so the ``_id``-suffix
# stripping in NormalizedMatchStrategy must not route it here — see
# ``NormalizedMatchStrategy._is_value_bearing``.
_VALUE_BEARING_FIELDS: frozenset[str] = _PHONE_FIELDS | _SOCIAL_FIELDS | {"email"}


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

    def _candidates_camel_split(self, h: str, uscore: str) -> str | None:
        """Step 2: CamelCase / PascalCase split, if it differs from `uscore`."""
        if not any(c.isupper() for c in h[1:]):
            return None
        snake = _normalize_header(h)
        if snake and snake != uscore:
            return snake
        return None

    def _candidates_dot_path(self, h: str) -> tuple[list[str], bool]:
        """Step 3: dot-path resolution (e.g. Account.Name, fields.last_name).

        Returns the items to append, and whether "company" must be inserted
        at the very front of the caller's accumulated candidates (a
        company-like prefix + a 'name'/'nombre' suffix).
        """
        if "." not in h:
            return [], False
        parts = h.rsplit(".", 1)
        prefix_raw = parts[0].lower().strip()
        suffix_raw = parts[1].strip()
        suffix_lower = self._SEP_RE.sub("_", suffix_raw).lower()
        last_prefix = prefix_raw.rsplit(".", 1)[-1]
        company_first = last_prefix in self._COMPANY_PREFIXES and suffix_lower in (
            "name",
            "nombre",
        )
        items = [suffix_lower]
        if any(c.isupper() for c in suffix_raw[1:]):
            snake_sfx = _normalize_header(suffix_raw)
            if snake_sfx != suffix_lower:
                items.append(snake_sfx)
        return items, company_first

    def _candidates_indexed(self, h: str) -> list[str]:
        """Step 4: indexed pattern ("E-mail 1 - Value", "Organization 1 - Title")."""
        m = self._INDEXED_RE.match(h)
        if not m:
            return []
        grp = self._SEP_RE.sub("_", m.group(1).strip()).lower()
        prop = self._SEP_RE.sub("_", m.group(2).strip()).lower()
        return [f"{grp}_{prop}", prop, grp]  # organization_name, name, organization

    def _candidates_number_stripped(self, uscore: str) -> str | None:
        """Step 5: number stripping ("E-mail 2 Address" -> e_mail_address)."""
        num_stripped = self._NUM_SUFFIX_RE.sub("", uscore)
        num_stripped = _HEADER_UNDERSCORE_RUN_RE.sub("_", num_stripped).strip("_")
        if num_stripped and num_stripped != uscore:
            return num_stripped
        return None

    def _candidates_prefix_stripped(
        self, uscore: str, prefixes: tuple[str, ...]
    ) -> list[str]:
        """Steps 6 and 7: strip a known prefix (vendor or address) off `uscore`."""
        items = []
        for pfx in prefixes:
            if uscore.startswith(pfx):
                stripped = uscore[len(pfx) :]
                if stripped:
                    items.append(stripped)
        return items

    def _candidates_id_stripped(self, out: list[str]) -> list[str]:
        """Step 8: _id suffix stripping (owner_id -> owner), plus a vendor-prefix
        strip of that result. Skips anything already present in `out` (or
        already produced by this step), and anything value-bearing.
        """
        items: list[str] = []
        id_candidates = [c for c in out if c.endswith("_id")]
        for candidate in id_candidates:
            base = candidate[:-3]
            if not base or base in out or base in items or self._is_value_bearing(base):
                continue
            items.append(base)
            # Also strip vendor prefix off the base
            for pfx in self._VENDOR_PREFIXES:
                if base.startswith(pfx):
                    inner = base[len(pfx) :]
                    if (
                        inner
                        and inner not in out
                        and inner not in items
                        and not self._is_value_bearing(inner)
                    ):
                        items.append(inner)
        return items

    def _candidates(self, header: str) -> list[str]:
        out: list[str] = []
        h = header.strip()
        if not h:
            return out

        # 1. Space / hyphen → underscore  +  strip non-word chars
        uscore = _normalize_header(h, camel_split=False)
        if uscore:
            out.append(uscore)

        snake = self._candidates_camel_split(h, uscore)
        if snake:
            out.append(snake)

        dot_items, company_first = self._candidates_dot_path(h)
        if company_first:
            out.insert(0, "company")
        out.extend(dot_items)

        out.extend(self._candidates_indexed(h))

        num_stripped = self._candidates_number_stripped(uscore)
        if num_stripped:
            out.append(num_stripped)

        out.extend(self._candidates_prefix_stripped(uscore, self._VENDOR_PREFIXES))
        out.extend(self._candidates_prefix_stripped(uscore, self._address_prefixes))

        out.extend(self._candidates_id_stripped(out))

        return out

    def _is_value_bearing(self, candidate: str) -> bool:
        """True if *candidate* names a field that stores the value itself.

        Stripping ``_id`` is a useful convenience for *reference* columns —
        ``owner_id`` really does identify the owner, and ``account_id`` the
        account.  It is actively harmful for fields whose whole purpose is to
        hold the value: ``primary_phone_id`` is a foreign key, not a phone
        number, and routing it to ``phone`` stores an internal ID as the
        contact's number at near-exact confidence, where no confidence
        threshold will catch it.

        .. versionadded:: 2.11.0
        """
        canonical = self._registry.exact_lookup(candidate)
        return canonical is not None and canonical in _VALUE_BEARING_FIELDS

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

        # A header that structurally names a foreign key ("primary_phone_id",
        # "email_ref") must not be *guessed* into a field that holds the value
        # itself — that stores an internal ID as someone's phone number or
        # email address.  Exact aliases are exempt: the truth table is allowed
        # to assert that a given vendor's "<platform>_id" really is the handle.
        if canonical in _VALUE_BEARING_FIELDS and _is_reference_header(header):
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
    # A bare five-digit run is the one genuinely ambiguous postal shape: an
    # order total, an account balance, an employee number and a US ZIP are
    # indistinguishable as values, so filing "45000" as a postal code is a coin
    # flip.  Like the phone and birthday shapes above, require corroboration
    # from the header for that pattern alone.  The alphanumeric shapes
    # (K1A 0B1, SW1A 1AA) and ZIP+4 are distinctive enough to stand on their
    # own and keep working with no header hint.
    _AMBIGUOUS_POSTAL_RE = re.compile(r"^\d{5}$")
    _POSTAL_HEADER_HINTS = frozenset(
        {
            "cep",
            "cp",
            "eircode",
            "pincode",
            "plz",
            "postal",
            "postalcode",
            "postcode",
            "zip",
            "zipcode",
        }
    )
    _POSTAL_HEADER_PHRASES = frozenset(
        {
            "postal_code",
            "post_code",
            "zip_code",
            "codigo_postal",
            "code_postal",
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

    @classmethod
    def _has_postal_header_hint(cls, header: str) -> bool:
        normalized, terms = cls._header_terms(header)
        return bool(
            (terms & cls._POSTAL_HEADER_HINTS)
            or normalized in cls._POSTAL_HEADER_PHRASES
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
            if (
                canonical == "postal_code"
                and self._AMBIGUOUS_POSTAL_RE.match(cleaned)
                and not self._has_postal_header_hint(header)
            ):
                continue
            return FieldMatch(
                original=header,
                canonical=canonical,
                confidence=HEURISTIC_CONFIDENCE,
                strategy=self.name,
            )
        return None
