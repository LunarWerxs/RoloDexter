"""Country and state/province normalization.

Extracted verbatim from ``core.py``, which re-imports every name here so
``rolodexter.core`` keeps the whole surface its callers and tests import.
"""

from __future__ import annotations

from typing import ClassVar

from ._text import _smart_titlecase


class CountryNormalizer:
    """Normalize common country spellings to ISO 3166-1 alpha-2.

    Recognizes alpha-2 codes, alpha-3 codes, and the English names and common
    informal spellings of the countries that dominate contact data.  Anything
    unrecognized is returned trimmed and otherwise untouched, so no data is
    lost or mangled by an incomplete table.

    .. versionadded:: 2.11.0
    """

    # alpha-3 → alpha-2 for the same set of countries covered by _NAMES.
    _ALPHA3: ClassVar[dict[str, str]] = {
        "arg": "AR",
        "aus": "AU",
        "aut": "AT",
        "bel": "BE",
        "bgr": "BG",
        "bra": "BR",
        "can": "CA",
        "che": "CH",
        "chl": "CL",
        "chn": "CN",
        "col": "CO",
        "cze": "CZ",
        "deu": "DE",
        "dnk": "DK",
        "esp": "ES",
        "est": "EE",
        "fin": "FI",
        "fra": "FR",
        "gbr": "GB",
        "grc": "GR",
        "hkg": "HK",
        "hrv": "HR",
        "hun": "HU",
        "idn": "ID",
        "ind": "IN",
        "irl": "IE",
        "isr": "IL",
        "ita": "IT",
        "jpn": "JP",
        "kor": "KR",
        "ltu": "LT",
        "lux": "LU",
        "lva": "LV",
        "mex": "MX",
        "mys": "MY",
        "nld": "NL",
        "nor": "NO",
        "nzl": "NZ",
        "per": "PE",
        "phl": "PH",
        "pol": "PL",
        "prt": "PT",
        "rou": "RO",
        "rus": "RU",
        "sau": "SA",
        "sgp": "SG",
        "svk": "SK",
        "svn": "SI",
        "swe": "SE",
        "tha": "TH",
        "tur": "TR",
        "twn": "TW",
        "ukr": "UA",
        "usa": "US",
        "vnm": "VN",
        "zaf": "ZA",
    }
    _NAMES: ClassVar[dict[str, str]] = {
        "argentina": "AR",
        "australia": "AU",
        "austria": "AT",
        "belgium": "BE",
        "brazil": "BR",
        "brasil": "BR",
        "bulgaria": "BG",
        "canada": "CA",
        "chile": "CL",
        "china": "CN",
        "colombia": "CO",
        "croatia": "HR",
        "czechia": "CZ",
        "czech republic": "CZ",
        "denmark": "DK",
        "estonia": "EE",
        "finland": "FI",
        "france": "FR",
        "germany": "DE",
        "deutschland": "DE",
        "greece": "GR",
        "hong kong": "HK",
        "hungary": "HU",
        "india": "IN",
        "indonesia": "ID",
        "ireland": "IE",
        "israel": "IL",
        "italy": "IT",
        "italia": "IT",
        "japan": "JP",
        "latvia": "LV",
        "lithuania": "LT",
        "luxembourg": "LU",
        "malaysia": "MY",
        "mexico": "MX",
        "méxico": "MX",
        "netherlands": "NL",
        "the netherlands": "NL",
        "holland": "NL",
        "new zealand": "NZ",
        "norway": "NO",
        "peru": "PE",
        "philippines": "PH",
        "poland": "PL",
        "polska": "PL",
        "portugal": "PT",
        "romania": "RO",
        "russia": "RU",
        "russian federation": "RU",
        "saudi arabia": "SA",
        "singapore": "SG",
        "slovakia": "SK",
        "slovenia": "SI",
        "south africa": "ZA",
        "south korea": "KR",
        "korea": "KR",
        "republic of korea": "KR",
        "spain": "ES",
        "españa": "ES",
        "sweden": "SE",
        "sverige": "SE",
        "switzerland": "CH",
        "taiwan": "TW",
        "thailand": "TH",
        "turkey": "TR",
        "türkiye": "TR",
        "ukraine": "UA",
        "united kingdom": "GB",
        "great britain": "GB",
        "england": "GB",
        "scotland": "GB",
        "wales": "GB",
        "uk": "GB",
        "united states": "US",
        "united states of america": "US",
        "usa": "US",
        "u.s.": "US",
        "u.s.a.": "US",
        "america": "US",
        "vietnam": "VN",
        "viet nam": "VN",
    }

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
        stripped = lowered.replace(".", "")
        if len(stripped) == 2 and stripped.isalpha():
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
    _CODES: ClassVar[frozenset[str]] = frozenset(
        (
            *[
                "AL",
                "AK",
                "AZ",
                "AR",
                "CA",
                "CO",
                "CT",
                "DE",
                "FL",
                "GA",
                "HI",
                "ID",
                "IL",
                "IN",
                "IA",
                "KS",
                "KY",
                "LA",
                "ME",
                "MD",
            ],
            *[
                "MA",
                "MI",
                "MN",
                "MS",
                "MO",
                "MT",
                "NE",
                "NV",
                "NH",
                "NJ",
                "NM",
                "NY",
                "NC",
                "ND",
                "OH",
                "OK",
                "OR",
                "PA",
                "RI",
            ],
            *[
                "SC",
                "SD",
                "TN",
                "TX",
                "UT",
                "VT",
                "VA",
                "WA",
                "WV",
                "WI",
                "WY",
                "DC",
                "PR",
                "VI",
                "GU",
                "AS",
                "MP",
            ],
            *[
                "AB",
                "BC",
                "MB",
                "NB",
                "NL",
                "NS",
                "NT",
                "NU",
                "ON",
                "PE",
                "QC",
                "SK",
                "YT",
            ],
        )
    )
    _NAMES: ClassVar[dict[str, str]] = {
        "alabama": "AL",
        "alaska": "AK",
        "arizona": "AZ",
        "arkansas": "AR",
        "california": "CA",
        "colorado": "CO",
        "connecticut": "CT",
        "delaware": "DE",
        "district of columbia": "DC",
        "florida": "FL",
        "georgia": "GA",
        "hawaii": "HI",
        "idaho": "ID",
        "illinois": "IL",
        "indiana": "IN",
        "iowa": "IA",
        "kansas": "KS",
        "kentucky": "KY",
        "louisiana": "LA",
        "maine": "ME",
        "maryland": "MD",
        "massachusetts": "MA",
        "michigan": "MI",
        "minnesota": "MN",
        "mississippi": "MS",
        "missouri": "MO",
        "montana": "MT",
        "nebraska": "NE",
        "nevada": "NV",
        "new hampshire": "NH",
        "new jersey": "NJ",
        "new mexico": "NM",
        "new york": "NY",
        "north carolina": "NC",
        "north dakota": "ND",
        "ohio": "OH",
        "oklahoma": "OK",
        "oregon": "OR",
        "pennsylvania": "PA",
        "puerto rico": "PR",
        "rhode island": "RI",
        "south carolina": "SC",
        "south dakota": "SD",
        "tennessee": "TN",
        "texas": "TX",
        "utah": "UT",
        "vermont": "VT",
        "virginia": "VA",
        "washington": "WA",
        "west virginia": "WV",
        "wisconsin": "WI",
        "wyoming": "WY",
        "alberta": "AB",
        "british columbia": "BC",
        "manitoba": "MB",
        "new brunswick": "NB",
        "newfoundland and labrador": "NL",
        "nova scotia": "NS",
        "northwest territories": "NT",
        "nunavut": "NU",
        "ontario": "ON",
        "prince edward island": "PE",
        "quebec": "QC",
        "québec": "QC",
        "saskatchewan": "SK",
        "yukon": "YT",
    }

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
        return _smart_titlecase(text)
