"""Per-field value normalizers and the dispatch that picks one.

Extracted verbatim from ``core.py``, which re-imports every name here so
``rolodexter.core`` keeps the whole surface its callers and tests import.
"""

from __future__ import annotations

import json
import re
import threading
from typing import Any

from ._geo import CountryNormalizer, StateNormalizer
from ._models import MappingWarning, WarningCategory
from ._text import _smart_titlecase

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


# The JavaScript package splits a name word on "@" and "-" before deciding
# how to case each piece, so "Smith-DeAngelo" keeps its second half and
# re-cases its first, and "ada@EXAMPLE.com" (an email that landed in a name
# field) keeps only the part that was cased on purpose.  Kept identical so
# both packages restore the same pieces.  The comma is here because
# nameparser consumes it: "DiCaprio, LaToya" reaches the result as
# "LaToya Dicaprio", and the piece to restore is "dicaprio", not "dicaprio,".
_NAME_SEGMENT_RE = re.compile(r"([@,-])")


def _has_deliberate_capital(segment: str) -> bool:
    """True when *segment* mixes case with a capital after its first letter.

    That is the signal both packages read as "cased on purpose": ``DeAngelo``,
    ``LaToya``, ``eBay``.  All-upper (``DEANGELO``), all-lower and
    conventionally-cased (``Jane``) words return False and are re-cased from
    rules.  Same test :func:`_smart_titlecase` applies to address tokens.
    """
    return (
        not segment.isupper()
        and not segment.islower()
        and any(c.isupper() for c in segment[1:])
    )


def _restore_deliberate_capitals(source: str, result: str) -> str:
    """Put back the inner capitals that lowercasing *source* discarded.

    **The decision.**  A source system that wrote ``DeAngelo`` is a better
    authority on that name than a casing rule is, and flattening it to
    ``Deangelo`` is a visible error in anything user-facing.  The cost is
    that ``DeAngelo`` and ``deangelo`` no longer normalize to one string, so
    a caller who compares names for equality must compare them
    case-insensitively - which is how names should be compared anyway, and
    is how this package's own identity keys already compare emails.  It was
    an open question between the two packages until 2.12.0; JavaScript and
    :class:`AddressNormalizer` had both answered it this way already, and
    ``nameparser``'s own default is to leave a mixed-case name alone.

    ``nameparser`` may reorder words (``"Smith, DeAngelo"`` becomes
    ``"DeAngelo Smith"``) and drop punctuation, so restoration matches by
    lowercase form rather than by position.  A piece is restored wherever
    nameparser *capitalized* it, whichever rule it used - the generic one
    (``Deangelo``), the per-run one around an apostrophe (``O'Deangelo``) or
    the Mac/Mc one (``McDeangelo``) - because in each case the source's own
    casing is the better authority.  A piece nameparser deliberately
    lowercased (a particle inside the name: ``"jane VanDer berg"`` stays
    ``"Jane vander Berg"``) is left alone, and a suffix it expanded (``PhD``
    to ``Ph.D.``) no longer matches by lowercase form and is left expanded.
    Both are what the JavaScript package does with the same input.
    """
    preserved: dict[str, str] = {}
    for word in source.split():
        for segment in _NAME_SEGMENT_RE.split(word):
            if _has_deliberate_capital(segment):
                preserved.setdefault(segment.lower(), segment)
    if not preserved:
        return result
    # Split keeping the whitespace nameparser emitted, so nothing but the
    # cased pieces changes.
    out: list[str] = []
    for chunk in re.split(r"(\s+)", result):
        if not chunk or chunk.isspace():
            out.append(chunk)
            continue
        pieces = _NAME_SEGMENT_RE.split(chunk)
        for i, piece in enumerate(pieces):
            original = preserved.get(piece.lower())
            # nameparser lowercased this piece on purpose (a particle or a
            # conjunction inside the name) when it is all-lower yet has a
            # letter it could have capitalized.  Everything else it either
            # cased or could not case ("0x1f" has no first letter to raise),
            # and there the source's own casing wins.
            lowered_on_purpose = piece == piece.lower() and piece != piece.capitalize()
            if original is not None and not lowered_on_purpose:
                pieces[i] = original
        out.append("".join(pieces))
    return "".join(out)


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
    _constants: Any = None
    _constants_lock = threading.Lock()

    @classmethod
    def _nameparser_constants(cls) -> Any:
        """A private ``nameparser`` ``Constants`` carrying our extra particles.

        Built once, under a lock - the i18n CLI calls this from a worker pool.
        A private instance rather than the shared ``CONSTANTS`` singleton:
        mutating the singleton is deprecated in nameparser 2.2 for removal in
        3.0 (it raised under ``-W error`` on every first ``map_payload``), and
        it leaked this package's particle set into every other ``HumanName``
        in the process.

        .. versionchanged:: 2.12.0
           Was ``_ensure_prefixes()``, which mutated the shared singleton.
        """
        if cls._constants is None:
            with cls._constants_lock:
                if cls._constants is None:
                    from nameparser.config import Constants

                    constants = Constants()
                    constants.prefixes.add(*cls._EXTRA_PREFIXES)
                    cls._constants = constants
        return cls._constants

    @classmethod
    def normalize(cls, value: str) -> str:
        """Capitalize a name string with culturally-aware rules.

        .. versionchanged:: 2.12.0
           A word that arrives with a deliberate inner capital keeps the
           casing it arrived with: ``DeAngelo``, ``LaToya`` and ``DiCaprio``
           no longer flatten to ``Deangelo``, ``Latoya`` and ``Dicaprio``.
           All-lower and all-upper input is still re-cased from rules, so
           ``deangelo`` and ``DEANGELO`` both normalize to ``Deangelo``.
           This is the rule the JavaScript package and this package's own
           :class:`AddressNormalizer` already applied.
        """
        if not value or not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return value

        from nameparser import HumanName

        # nameparser re-derives casing from an all-lowercase copy.  That is
        # what turns "JANE DOE" and "jane doe" into "Jane Doe" and what gives
        # us its particle, Mc/Mac, title and suffix handling.  Lowercasing
        # first also discards a capital the source system placed on purpose
        # ("DeAngelo"), and a source that took the trouble to case a name is
        # a better authority on it than a rule is.  Those capitals are put
        # back afterwards by _restore_deliberate_capitals(); the decision and
        # its trade-off are written on that function.
        hn = HumanName(text.lower(), constants=cls._nameparser_constants())
        hn.capitalize()
        result = str(hn)
        # ``nameparser`` >= 1.2 leaves a *leading* recognized particle
        # lowercase (e.g. "ter braak" -> "ter Braak"), whereas older
        # releases capitalized it. A normalized display name should always
        # begin with an uppercase letter, so fix the first character here
        # without disturbing internal particle casing ("Jan van der Berg").
        if result[:1].islower():
            result = result[:1].upper() + result[1:]
        return _restore_deliberate_capitals(text, result)

    @classmethod
    def parse(cls, value: str) -> dict[str, str]:
        """Parse a name string into structured components.

        Returns a dict with keys: ``title``, ``first``, ``middle``,
        ``last``, ``suffix``, ``nickname``.

        .. versionadded:: 2.5.0
        """
        from nameparser import HumanName

        hn = HumanName(value.strip(), constants=cls._nameparser_constants())
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


class DateNormalizer:
    """Normalize unambiguous date strings to ISO-8601 (``YYYY-MM-DD``).

    **Refuses to guess.**  ``03/04/2024`` is 3 April in most of the world and
    4 March in the United States, and there is nothing in the value to say
    which.  Silently picking one would corrupt a birthday in half the data
    it touches, so ambiguous values are returned unchanged and reported via
    :func:`value_warnings`.  What is normalized:

    * already-ISO values, with or without a time part (``2024-03-15``,
      ``2024-03-15T09:30:00Z``) — the time is dropped;
    * slash- or dot-separated values where one component is unambiguous
      because it exceeds 12 (``25/03/2024``, ``2024/03/15``, ``15.03.2024``);
    * ``YYYY/MM/DD``, where a four-digit leading year fixes the order.

    Two-digit years are treated as ambiguous and left alone: mapping ``68`` to
    1968 or 2068 is a guess of exactly the kind this class exists to avoid.

    .. versionadded:: 2.11.0
    """

    _ISO_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ].*)?$")
    _YMD_RE = re.compile(r"^(\d{4})[/.](\d{1,2})[/.](\d{1,2})$")
    _DMY_RE = re.compile(r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})$")

    @classmethod
    def _iso(cls, year: int, month: int, day: int) -> str | None:
        if not 1 <= month <= 12 or not 1 <= day <= 31:
            return None
        return f"{year:04d}-{month:02d}-{day:02d}"

    @classmethod
    def normalize(cls, value: str) -> str:
        if not value or not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return value

        m = cls._ISO_RE.match(text) or cls._YMD_RE.match(text)
        if m:
            iso = cls._iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return iso if iso is not None else value

        m = cls._DMY_RE.match(text)
        if m:
            first, second, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            # Only one ordering can be valid when a component exceeds 12.
            if first > 12 and second <= 12:
                iso = cls._iso(year, second, first)  # DD/MM/YYYY
                return iso if iso is not None else value
            if second > 12 and first <= 12:
                iso = cls._iso(year, first, second)  # MM/DD/YYYY
                return iso if iso is not None else value
        return value

    @classmethod
    def is_ambiguous(cls, value: str) -> bool:
        """True if *value* looks like a date this class deliberately won't reorder."""
        if not isinstance(value, str):
            return False
        text = value.strip()
        if not text or cls.normalize(text) != text:
            return False
        m = cls._DMY_RE.match(text)
        if m and int(m.group(1)) <= 12 and int(m.group(2)) <= 12:
            return True
        return bool(re.match(r"^\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2}$", text))


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
_DATE_FIELDS: frozenset[str] = frozenset(
    {"birthday", "created_at", "updated_at", "last_contacted"}
)
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

# Suffixes that mark a header as naming a *reference* to a record rather than
# holding the record's value.  Used to veto a derived (normalized/fuzzy) match
# onto a value-bearing field; an explicit alias in patterns.json still wins,
# since the truth table is allowed to say that e.g. ``twitter_id`` really is
# the handle for a given export format.
_REFERENCE_SUFFIX_RE = re.compile(r"_(?:id|ids|uuid|guid|key|ref|fk)$")


def _is_reference_header(header: str) -> bool:
    """True if *header* names a foreign key (``primary_phone_id``, ``email_ref``)."""
    return bool(_REFERENCE_SUFFIX_RE.search(_normalize_header(header)))


# Build the lookup dict programmatically from the category sets.
_FIELD_NORMALIZERS: dict[str, Any] = {  # maps canonical field → normalizer class
    **{f: PhoneNormalizer for f in _PHONE_FIELDS},
    **{f: NameNormalizer for f in _NAME_FIELDS},
    **{f: AddressNormalizer for f in _ADDRESS_FIELDS},
    **{f: BooleanNormalizer for f in _BOOLEAN_FIELDS},
    **{f: ListNormalizer for f in _LIST_FIELDS},
    **{f: DateNormalizer for f in _DATE_FIELDS},
    **{f: StringNormalizer for f in _SOCIAL_FIELDS},
    "email": EmailNormalizer,
    "postal_code": PostalCodeNormalizer,
    "country": CountryNormalizer,
    "state": StateNormalizer,
    # Remaining fields default to StringNormalizer via normalize_value()
}


# Deliberately permissive: this drives a *warning*, not a rejection, so it
# should flag obvious junk ("n/a", "see notes", a bare name) without
# second-guessing unusual-but-valid addresses.  No network lookup is performed.
_EMAIL_SHAPE_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def value_warnings(key: str, canonical_field: str, value: Any) -> list[MappingWarning]:
    """Return warnings about a *normalized* value that silently degraded.

    Shared by :meth:`ContactMapper.map_payload` and
    :meth:`ContactMapper.map_dataframe` so the two cannot drift on what counts
    as a suspicious value.

    .. versionadded:: 2.11.0
       Extracted from ``map_payload``; adds the email shape check, which
       previously had no equivalent to the phone E.164 check even though
       ``email`` is the primary key :meth:`MappingResult.get_identity_keys`
       builds on.
    """
    if not isinstance(value, str):
        return []
    text = value.strip()
    if not text:
        return []
    if canonical_field in _PHONE_FIELDS and not text.startswith("+"):
        return [
            MappingWarning(
                f"{key!r}: phone value {value!r} could not be normalized to "
                "E.164 (set a matching default_region?)",
                WarningCategory.PHONE_NORMALIZATION,
            )
        ]
    if canonical_field == "email" and not _EMAIL_SHAPE_RE.match(text):
        return [
            MappingWarning(
                f"{key!r}: value {value!r} does not look like an email address",
                WarningCategory.EMAIL_VALIDATION,
            )
        ]
    if canonical_field in _DATE_FIELDS and DateNormalizer.is_ambiguous(text):
        return [
            MappingWarning(
                f"{key!r}: date {value!r} is ambiguous (day/month order or a "
                "two-digit year) and was left unchanged",
                WarningCategory.DATE_AMBIGUOUS,
            )
        ]
    return []


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
