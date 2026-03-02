"""E.164 phone normalizer — powered by Google's libphonenumber.

Built into rolodexter.  Provides parsing, validation, E.164
formatting, number-type detection, and text extraction for
international phone numbers using Google's comprehensive
libphonenumber metadata (via the ``phonenumbers`` package).

Design goals
────────────
* **Accurate** — delegates to Google's continuously-maintained
  metadata covering every ITU-assigned calling code.
* **Full-featured** — validation, formatting, number-type detection,
  and text extraction.
* **Compatible** — same public API as the previous zero-dep built-in
  module; a drop-in upgrade.

.. versionchanged:: 2.5.0
   Replaced manual ITU metadata with ``phonenumbers`` hard dependency.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import phonenumbers as _pn
from phonenumbers import PhoneNumberFormat as _Fmt


# ═══════════════════════════════════════════════════════════════════════
#  DATA CLASS
# ═══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class PhoneNumber:
    """Parsed phone number components."""

    calling_code: int
    national_number: str
    raw: str
    extension: str | None = None
    _pn_obj: _pn.PhoneNumber | None = field(  # type: ignore[name-defined]
        default=None, repr=False, compare=False,
    )

    @property
    def e164(self) -> str:
        """E.164 formatted string, e.g. ``+15551234567``."""
        if self._pn_obj is not None:
            return _pn.format_number(self._pn_obj, _Fmt.E164)
        return f"+{self.calling_code}{self.national_number}"

    @property
    def is_valid(self) -> bool:
        """True if the number is a valid assignment per libphonenumber."""
        if self._pn_obj is not None:
            return _pn.is_valid_number(self._pn_obj)
        return False

    @property
    def is_possible(self) -> bool:
        """True if the number has a plausible length (less strict than is_valid).

        .. versionadded:: 2.5.0
        """
        if self._pn_obj is not None:
            return _pn.is_possible_number(self._pn_obj)
        return False

    @property
    def country_codes(self) -> list[str]:
        """ISO country codes that share this calling code."""
        return list(_pn.region_codes_for_country_code(self.calling_code))

    def __str__(self) -> str:
        return self.e164


# ═══════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════════


class MatchType:
    """Result constants for :func:`is_number_match`."""

    NOT_A_NUMBER = _pn.MatchType.NOT_A_NUMBER        # 0
    NO_MATCH = _pn.MatchType.NO_MATCH                # 1
    SHORT_NSN_MATCH = _pn.MatchType.SHORT_NSN_MATCH  # 2
    NSN_MATCH = _pn.MatchType.NSN_MATCH              # 3
    EXACT_MATCH = _pn.MatchType.EXACT_MATCH          # 4


class NumberType:
    """Phone number type constants."""

    FIXED_LINE = _pn.PhoneNumberType.FIXED_LINE                      # 0
    MOBILE = _pn.PhoneNumberType.MOBILE                              # 1
    FIXED_LINE_OR_MOBILE = _pn.PhoneNumberType.FIXED_LINE_OR_MOBILE  # 2
    TOLL_FREE = _pn.PhoneNumberType.TOLL_FREE                        # 3
    PREMIUM_RATE = _pn.PhoneNumberType.PREMIUM_RATE                  # 4
    SHARED_COST = _pn.PhoneNumberType.SHARED_COST                    # 5
    VOIP = _pn.PhoneNumberType.VOIP                                  # 6
    PERSONAL_NUMBER = _pn.PhoneNumberType.PERSONAL_NUMBER            # 7
    PAGER = _pn.PhoneNumberType.PAGER                                # 8
    UAN = _pn.PhoneNumberType.UAN                                    # 9
    VOICEMAIL = _pn.PhoneNumberType.VOICEMAIL                        # 10
    UNKNOWN = _pn.PhoneNumberType.UNKNOWN                            # 99


# ═══════════════════════════════════════════════════════════════════════
#  INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════════════

# Regex for 00 / 011 international dial-out prefixes that phonenumbers
# does not resolve without an explicit default_region.
_DIALOUT_RE = re.compile(r"^(?:011|00)\s*")

# tel: URI scheme (RFC 3966) — phonenumbers chokes on ;params
_TEL_URI_RE = re.compile(r"^tel:", re.IGNORECASE)
_TEL_EXT_RE = re.compile(r";ext=(\d+)", re.IGNORECASE)
_TEL_PARAMS_RE = re.compile(r";[a-z\-]+=.*$", re.IGNORECASE)


def _wrap(pn_obj: _pn.PhoneNumber, raw: str) -> PhoneNumber:  # type: ignore[name-defined]
    """Wrap a ``phonenumbers.PhoneNumber`` into our ``PhoneNumber``."""
    e164 = _pn.format_number(pn_obj, _Fmt.E164)
    cc = pn_obj.country_code
    national = e164[1 + len(str(cc)) :]
    ext: str | None = pn_obj.extension if pn_obj.extension else None
    return PhoneNumber(
        calling_code=cc,
        national_number=national,
        raw=raw,
        extension=ext,
        _pn_obj=pn_obj,
    )


# ═══════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════════════════════════════════


def parse(raw: str, default_region: str | None = None) -> PhoneNumber | None:
    """Parse a phone string into a :class:`PhoneNumber`.

    Parameters
    ----------
    raw : str
        Any common phone format: ``+1 (555) 123-4567``, ``00 44 20 7946 0958``,
        ``(02) 1234 5678``, ``1-800-FLOWERS``, plain digits, etc.
    default_region : str, optional
        ISO 3166-1 alpha-2 code (e.g. ``"US"``, ``"AU"``) used when *raw*
        has no international prefix.

    Returns
    -------
    PhoneNumber or None
        ``None`` if the input cannot be interpreted as a phone number.
    """
    if not raw or not isinstance(raw, str):
        return None

    text = raw.strip()
    if not text:
        return None

    # ── Pre-process: tel: URI (RFC 3966) ────────────────────────
    # phonenumbers cannot parse ;phone-context= and similar params,
    # so we strip the scheme and any trailing params before handing off.
    # ;ext= is a real extension — convert it to a format phonenumbers
    # understands before stripping other params.
    if _TEL_URI_RE.match(text):
        text = _TEL_URI_RE.sub("", text)
        ext_m = _TEL_EXT_RE.search(text)
        ext_suffix = f" ext {ext_m.group(1)}" if ext_m else ""
        text = _TEL_PARAMS_RE.sub("", text) + ext_suffix

    # ── Pre-process: 00 / 011 dial-out → + prefix ──────────────
    # phonenumbers cannot resolve these without default_region, so
    # we normalise them into a + prefix first.
    m = _DIALOUT_RE.match(text)
    if m and len(text) > m.end() + 5:
        text = "+" + text[m.end() :]

    # ── Primary: delegate to phonenumbers ───────────────────────
    try:
        pn_obj = _pn.parse(text, default_region)
    except _pn.NumberParseException:
        return None

    if not _pn.is_possible_number(pn_obj):
        return None

    return _wrap(pn_obj, raw)


def format_e164(raw: str, default_region: str | None = None) -> str | None:
    """Parse *raw* and return the E.164 string, or ``None`` on failure.

    This is the main entry point for normalisation::

        >>> format_e164("+1 (555) 123-4567")
        '+15551234567'

        >>> format_e164("020 7946 0958", default_region="GB")
        '+442079460958'
    """
    phone = parse(raw, default_region)
    if phone is None:
        return None
    return phone.e164


def is_valid(raw: str, default_region: str | None = None) -> bool:
    """Return ``True`` if *raw* parses and is a valid assigned number."""
    phone = parse(raw, default_region)
    return phone is not None and phone.is_valid


# ═══════════════════════════════════════════════════════════════════════
#  DISPLAY FORMATTING
# ═══════════════════════════════════════════════════════════════════════


def format_international(phone: PhoneNumber) -> str:
    """Format as international display: ``+1 202-555-1234``.

    Uses libphonenumber's locale-correct grouping and separators.
    """
    if phone._pn_obj is not None:
        return _pn.format_number(phone._pn_obj, _Fmt.INTERNATIONAL)
    return f"+{phone.calling_code} {phone.national_number}"


def format_national(phone: PhoneNumber) -> str:
    """Format as national display: ``(202) 555-1234`` for NANP, etc.

    Uses libphonenumber's locale-correct grouping with trunk prefix.
    """
    if phone._pn_obj is not None:
        return _pn.format_number(phone._pn_obj, _Fmt.NATIONAL)
    return phone.national_number


# ═══════════════════════════════════════════════════════════════════════
#  NUMBER COMPARISON — is_number_match()
# ═══════════════════════════════════════════════════════════════════════


def is_number_match(
    a: str | PhoneNumber,
    b: str | PhoneNumber,
    default_region: str | None = None,
) -> int:
    """Compare two phone numbers and return a :class:`MatchType` constant.

    - ``EXACT_MATCH``: same CC + national + extension
    - ``NSN_MATCH``: same CC + national, extensions differ or missing
    - ``SHORT_NSN_MATCH``: one national number is a suffix of the other
    - ``NO_MATCH``: different numbers
    - ``NOT_A_NUMBER``: one or both couldn't be parsed
    """
    def _resolve(x: str | PhoneNumber) -> _pn.PhoneNumber | str:  # type: ignore[name-defined]
        if isinstance(x, PhoneNumber):
            if x._pn_obj is not None:
                return x._pn_obj
            return x.e164
        return x

    try:
        return _pn.is_number_match(_resolve(a), _resolve(b))  # type: ignore[arg-type]
    except Exception:
        return MatchType.NOT_A_NUMBER


# ═══════════════════════════════════════════════════════════════════════
#  NUMBER TYPE DETECTION
# ═══════════════════════════════════════════════════════════════════════


def number_type(phone: PhoneNumber) -> int:
    """Return a :class:`NumberType` constant for the given parsed number.

    Delegates to libphonenumber's comprehensive metadata for accurate
    detection across all countries.
    """
    if phone._pn_obj is not None:
        return _pn.number_type(phone._pn_obj)
    return NumberType.UNKNOWN


# ═══════════════════════════════════════════════════════════════════════
#  PHONE NUMBER MATCHER — extract phones from free text
# ═══════════════════════════════════════════════════════════════════════


class PhoneNumberMatch:
    """A phone number found in free text."""

    __slots__ = ("end", "number", "raw_string", "start")

    def __init__(self, start: int, end: int, raw_string: str, number: PhoneNumber):
        self.start = start
        self.end = end
        self.raw_string = raw_string
        self.number = number

    def __repr__(self) -> str:
        return f"PhoneNumberMatch(start={self.start}, end={self.end}, number={self.number.e164})"


class PhoneNumberMatcher:
    """Iterator that finds phone numbers in a block of text.

    Uses libphonenumber's ``PhoneNumberMatcher`` for accurate extraction.

    Usage::

        text = "Call me at +1 202 555 1234 or 020 7946 0958"
        for match in PhoneNumberMatcher(text, default_region="GB"):
            print(match.number.e164, match.start, match.end)
    """

    def __init__(self, text: str, default_region: str | None = None):
        self._text = text
        self._region = default_region
        self._matches: list[PhoneNumberMatch] | None = None

    def _find_all(self) -> list[PhoneNumberMatch]:
        results: list[PhoneNumberMatch] = []
        # phonenumbers matcher requires a region; default to "US".
        region = self._region or "US"
        for m in _pn.PhoneNumberMatcher(self._text, region):
            wrapped = _wrap(m.number, m.raw_string)
            results.append(
                PhoneNumberMatch(
                    start=m.start,
                    end=m.end,
                    raw_string=m.raw_string,
                    number=wrapped,
                )
            )
        return results

    def __iter__(self):
        if self._matches is None:
            self._matches = self._find_all()
        return iter(self._matches)

    def __len__(self):
        if self._matches is None:
            self._matches = self._find_all()
        return len(self._matches)

    def has_next(self) -> bool:
        """Return True if there is at least one phone number in the text."""
        return len(self) > 0
