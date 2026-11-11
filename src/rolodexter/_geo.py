"""Country and state/province normalization.

Extracted verbatim from ``core.py``, which re-imports every name here so
``rolodexter.core`` keeps the whole surface its callers and tests import.
"""

from __future__ import annotations

import re
from typing import ClassVar

from ._tables import TABLES
from ._text import _REGION_CODES, _smart_titlecase


class CountryNormalizer:
    """Normalize common country spellings to ISO 3166-1 alpha-2.

    Recognizes alpha-2 codes, alpha-3 codes, and the English names and common
    informal spellings of the countries that dominate contact data.  Anything
    unrecognized is returned trimmed and otherwise untouched, so no data is
    lost or mangled by an incomplete table.

    .. versionadded:: 2.11.0
    """

    # alpha-3 → alpha-2 for the same set of countries covered by _NAMES.
    # Every officially assigned ISO 3166-1 alpha-2 code (249).  A two-letter
    # value is read as a country code only when it is one of these, so "UK"
    # (a name, below) and "ZZ" are not taken for codes.  The JavaScript
    # package carries the same list in _geo.ts.
    _ALPHA2: ClassVar[frozenset[str]] = frozenset(TABLES["geo"]["alpha2"])
    _ALPHA3: ClassVar[dict[str, str]] = dict(TABLES["geo"]["alpha3"])
    _NAMES: ClassVar[dict[str, str]] = dict(TABLES["geo"]["country_names"])

    @classmethod
    def normalize(cls, value: str) -> str:
        if not value or not isinstance(value, str):
            return value
        text = " ".join(value.strip().split())
        if not text:
            return value
        lowered = text.lower()
        stripped = lowered.replace(".", "")
        # "U.K." reads as "UK" does: the dotless form is looked up too.
        named = cls._NAMES.get(lowered) or cls._NAMES.get(stripped)
        if named is not None:
            return named
        if stripped.upper() in cls._ALPHA2:
            return stripped.upper()
        alpha3 = cls._ALPHA3.get(stripped)
        if alpha3 is not None:
            return alpha3
        return text


class StateNormalizer:
    """Normalize US state and Canadian province names to their 2-letter code.

    Values that are already a valid code are uppercased; anything outside the
    table is returned trimmed and title-cased so non-US/CA regions keep their
    spelling.

    .. versionadded:: 2.11.0
    """

    # US states + DC + territories, then Canadian provinces/territories.
    _CODES: ClassVar[frozenset[str]] = _REGION_CODES
    _NAMES: ClassVar[dict[str, str]] = dict(TABLES["geo"]["state_names"])

    @classmethod
    def normalize(cls, value: str) -> str:
        if not value or not isinstance(value, str):
            return value
        text = " ".join(value.strip().split())
        if not text:
            return value
        lowered = text.lower()
        named = cls._NAMES.get(lowered)
        if named is not None:
            return named
        if text.upper() in cls._CODES:
            return text.upper()
        # A region code from elsewhere written in capitals ("NSW", "QLD",
        # "NRW", "SP") is already right; title-casing it would damage it.
        if re.fullmatch(r"[A-Z]{2,3}", text):
            return text
        return _smart_titlecase(text)
