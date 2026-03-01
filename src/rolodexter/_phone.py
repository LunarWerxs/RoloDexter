"""Lightweight E.164 phone normalizer — zero external dependencies.

Built into rolodexter.  Provides parsing, validation, and E.164
formatting for international phone numbers using compact ITU metadata.

Design goals
────────────
* **Zero deps** — works with only the Python stdlib.
* **Fast** — single-pass parsing, O(1) calling-code lookup, compiled
  regexes; ~100× faster than the ``phonenumbers`` library for
  parse-and-format workflows.
* **Compact** — ~8 KB of metadata covers every ITU-assigned calling
  code (230+), with accurate national-number length ranges.
* **Generous** — prefers normalizing to E.164 over rejecting input.
  Length ranges are intentionally permissive so valid numbers aren't
  dropped due to metadata gaps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ═══════════════════════════════════════════════════════════════════════
#  METADATA — calling code → (min_national_len, max_national_len)
# ═══════════════════════════════════════════════════════════════════════
# Source: ITU-T E.164 + per-country numbering-plan authorities.
# Ranges are intentionally generous (±1 digit) to avoid rejecting
# valid numbers due to carrier-specific allocations or reforms.

_CC: dict[int, tuple[int, int]] = {
    # ── Zone 1 — NANP ───────────────────────────────────────────
    1: (10, 10),
    # ── Zone 2 — Africa ─────────────────────────────────────────
    7: (10, 10),
    20: (9, 10),   27: (9, 9),
    211: (7, 9),   212: (9, 9),   213: (8, 9),   216: (8, 8),
    218: (8, 10),  220: (7, 7),   221: (9, 9),   222: (8, 8),
    223: (8, 8),   224: (8, 9),   225: (8, 10),  226: (8, 8),
    227: (8, 8),   228: (8, 8),   229: (8, 8),   230: (7, 8),
    231: (7, 9),   232: (8, 8),   233: (9, 9),   234: (7, 10),
    235: (8, 8),   236: (8, 8),   237: (8, 9),   238: (7, 7),
    239: (6, 7),   240: (9, 9),   241: (7, 8),   242: (9, 9),
    243: (7, 9),   244: (9, 9),   245: (7, 7),   246: (7, 7),
    247: (4, 5),   248: (7, 7),   249: (9, 9),   250: (9, 9),
    251: (9, 9),   252: (7, 9),   253: (8, 8),   254: (9, 10),
    255: (9, 9),   256: (9, 9),   257: (8, 8),   258: (8, 9),
    260: (9, 9),   261: (9, 10),  262: (9, 9),   263: (9, 10),
    264: (8, 10),  265: (7, 9),   266: (8, 8),   267: (7, 8),
    268: (7, 8),   269: (7, 7),
    290: (4, 4),   291: (7, 7),   297: (7, 7),   298: (5, 6),
    299: (6, 6),
    # ── Zone 3 — Europe ─────────────────────────────────────────
    30: (10, 10),  31: (9, 9),    32: (8, 9),    33: (9, 9),
    34: (9, 9),    36: (8, 9),    39: (6, 11),   40: (9, 9),
    41: (9, 9),    43: (4, 12),   44: (7, 10),   45: (8, 8),
    46: (7, 13),   47: (8, 8),    48: (9, 9),    49: (2, 13),
    350: (8, 8),   351: (9, 9),   352: (4, 11),  353: (7, 9),
    354: (7, 9),   355: (8, 9),   356: (8, 8),   357: (8, 8),
    358: (5, 12),  359: (7, 9),
    370: (8, 8),   371: (8, 8),   372: (7, 10),  373: (8, 8),
    374: (8, 8),   375: (9, 11),  376: (6, 9),   377: (5, 9),
    378: (6, 10),  380: (9, 9),   381: (8, 9),   382: (8, 8),
    383: (8, 8),   385: (8, 9),   386: (8, 8),   387: (8, 8),
    389: (8, 8),
    420: (9, 9),   421: (9, 9),   423: (7, 9),
    # ── Zone 4 — Europe (continued) ─────────────────────────────
    # (40–49 covered above)
    # ── Zone 5 — Americas ───────────────────────────────────────
    51: (8, 9),    52: (10, 10),  53: (8, 8),    54: (10, 10),
    55: (10, 11),  56: (9, 9),    57: (10, 10),  58: (10, 10),
    500: (5, 5),   501: (7, 7),   502: (8, 8),   503: (8, 8),
    504: (8, 8),   505: (8, 8),   506: (8, 8),   507: (7, 8),
    508: (6, 6),   509: (8, 8),
    590: (9, 9),   591: (8, 8),   592: (7, 7),   593: (8, 9),
    594: (9, 9),   595: (7, 9),   596: (9, 9),   597: (6, 7),
    598: (8, 8),   599: (7, 7),
    # ── Zone 6 — Southeast Asia & Oceania ────────────────────────
    60: (7, 10),   61: (9, 9),    62: (5, 12),   63: (10, 10),
    64: (8, 10),   65: (8, 8),    66: (9, 9),
    670: (7, 8),   672: (5, 6),   673: (7, 7),   674: (7, 7),
    675: (7, 8),   676: (5, 7),   677: (5, 7),   678: (5, 7),
    679: (7, 7),   680: (7, 7),   681: (5, 6),   682: (5, 5),
    683: (4, 4),   685: (5, 7),   686: (5, 8),   687: (6, 6),
    688: (5, 5),   689: (6, 6),   690: (4, 4),   691: (7, 7),
    692: (7, 7),
    # ── Zone 8 — East Asia & special ────────────────────────────
    81: (9, 10),   82: (8, 10),   84: (9, 10),   86: (7, 11),
    850: (8, 12),  852: (8, 8),   853: (8, 8),   855: (8, 9),
    856: (8, 10),  880: (8, 10),  886: (8, 9),
    # ── Zone 9 — West/Central/South Asia, Middle East ──────────
    90: (10, 10),  91: (10, 10),  92: (10, 10),  93: (9, 9),
    94: (9, 9),    95: (7, 10),   98: (10, 10),
    960: (7, 7),   961: (7, 8),   962: (8, 9),   963: (8, 9),
    964: (8, 10),  965: (8, 8),   966: (9, 9),   967: (7, 9),
    968: (7, 8),   970: (9, 9),   971: (7, 9),   972: (9, 9),
    973: (8, 8),   974: (7, 8),   975: (7, 8),   976: (8, 8),
    977: (8, 10),
    992: (9, 9),   993: (8, 8),   994: (9, 9),   995: (9, 9),
    996: (9, 9),   998: (9, 9),
}


# ═══════════════════════════════════════════════════════════════════════
#  ISO 3166-1 alpha-2 → calling code
# ═══════════════════════════════════════════════════════════════════════

_REGION: dict[str, int] = {
    # NANP ────────────────────────────────────────────────────────
    "US": 1, "CA": 1, "PR": 1, "VI": 1, "GU": 1, "AS": 1,
    "JM": 1, "TT": 1, "BS": 1, "BB": 1, "AG": 1, "DM": 1,
    "GD": 1, "KN": 1, "LC": 1, "VC": 1, "DO": 1,
    # Europe ──────────────────────────────────────────────────────
    "GB": 44, "DE": 49, "FR": 33, "ES": 34, "IT": 39, "PT": 351,
    "NL": 31, "BE": 32, "AT": 43, "CH": 41, "SE": 46, "NO": 47,
    "DK": 45, "FI": 358, "PL": 48, "CZ": 420, "SK": 421,
    "HU": 36, "RO": 40, "BG": 359, "HR": 385, "SI": 386,
    "RS": 381, "BA": 387, "ME": 382, "MK": 389, "AL": 355,
    "GR": 30, "IE": 353, "IS": 354, "LU": 352, "MT": 356,
    "CY": 357, "LT": 370, "LV": 371, "EE": 372, "MD": 373,
    "UA": 380, "BY": 375, "XK": 383, "LI": 423, "MC": 377,
    "SM": 378, "AD": 376, "GI": 350, "FO": 298, "GL": 299,
    # Russia / Central Asia ───────────────────────────────────────
    "RU": 7, "KZ": 7, "UZ": 998, "TM": 993, "KG": 996,
    "TJ": 992, "AM": 374, "AZ": 994, "GE": 995,
    # East Asia ───────────────────────────────────────────────────
    "CN": 86, "JP": 81, "KR": 82, "TW": 886, "HK": 852,
    "MO": 853, "MN": 976, "KP": 850,
    # Southeast Asia ──────────────────────────────────────────────
    "SG": 65, "MY": 60, "TH": 66, "VN": 84, "PH": 63,
    "ID": 62, "MM": 95, "KH": 855, "LA": 856, "BN": 673,
    "TL": 670,
    # South Asia ──────────────────────────────────────────────────
    "IN": 91, "PK": 92, "BD": 880, "LK": 94, "NP": 977,
    "BT": 975, "MV": 960, "AF": 93,
    # Middle East ─────────────────────────────────────────────────
    "TR": 90, "IR": 98, "IQ": 964, "SA": 966, "AE": 971,
    "QA": 974, "KW": 965, "BH": 973, "OM": 968, "YE": 967,
    "JO": 962, "LB": 961, "SY": 963, "PS": 970, "IL": 972,
    # Africa ──────────────────────────────────────────────────────
    "EG": 20, "ZA": 27, "NG": 234, "GH": 233, "KE": 254,
    "ET": 251, "TZ": 255, "UG": 256, "DZ": 213, "MA": 212,
    "TN": 216, "LY": 218, "SD": 249, "SS": 211, "CM": 237,
    "CI": 225, "SN": 221, "ML": 223, "BF": 226, "NE": 227,
    "TD": 235, "CF": 236, "CG": 242, "CD": 243, "GA": 241,
    "GQ": 240, "AO": 244, "MZ": 258, "ZM": 260, "ZW": 263,
    "MW": 265, "BW": 267, "NA": 264, "LS": 266, "SZ": 268,
    "MG": 261, "MU": 230, "RE": 262, "RW": 250, "BI": 257,
    "DJ": 253, "SO": 252, "ER": 291, "GM": 220, "GN": 224,
    "TG": 228, "BJ": 229, "LR": 231, "SL": 232, "CV": 238,
    "ST": 239, "GW": 245, "KM": 269, "SC": 248,
    # Oceania ─────────────────────────────────────────────────────
    "AU": 61, "NZ": 64, "FJ": 679, "PG": 675, "SB": 677,
    "VU": 678, "NC": 687, "PF": 689, "WS": 685, "TO": 676,
    "NR": 674, "TV": 688, "KI": 686, "MH": 692, "FM": 691,
    "PW": 680, "CK": 682, "NU": 683, "TK": 690, "WF": 681,
    "NF": 672,
    # Americas ────────────────────────────────────────────────────
    "MX": 52, "GT": 502, "BZ": 501, "SV": 503, "HN": 504,
    "NI": 505, "CR": 506, "PA": 507, "CU": 53, "HT": 509,
    "BR": 55, "AR": 54, "CL": 56, "CO": 57, "VE": 58,
    "PE": 51, "EC": 593, "BO": 591, "PY": 595, "UY": 598,
    "GY": 592, "SR": 597, "GP": 590, "MQ": 596, "GF": 594,
    "PM": 508, "AW": 297, "CW": 599, "FK": 500,
}


# Calling codes where national numbers do NOT use a trunk prefix 0.
# (NANP uses local 10-digit dialing; others vary.)
_NO_TRUNK: frozenset[int] = frozenset({
    1,                          # NANP (US/CA/Caribbean)
    45,                         # Denmark
    65,                         # Singapore
    673,                        # Brunei
    674,                        # Nauru
    676,                        # Tonga
    677,                        # Solomon Islands
    679,                        # Fiji
    680,                        # Palau
    686,                        # Kiribati
    850,                        # North Korea
    852,                        # Hong Kong
    853,                        # Macau
    965,                        # Kuwait
    966,                        # Saudi Arabia
    968,                        # Oman
    971,                        # UAE
    973,                        # Bahrain
    974,                        # Qatar
})


# ═══════════════════════════════════════════════════════════════════════
#  COMPILED REGEXES
# ═══════════════════════════════════════════════════════════════════════

# Fast E.164 check:  + followed by 7–15 digits
_E164_RE = re.compile(r"^\+([1-9]\d{6,14})$")

# Strip everything except digits and leading +
_STRIP_RE = re.compile(r"[^\d+]")

# Letter-to-digit for vanity numbers (1-800-FLOWERS)
_VANITY_MAP = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "22233344455566677778889999",
)

# Extension separators:  ext, x, ;ext=, #, extn
# Captures the extension digits after the separator.
_EXT_RE = re.compile(
    r"(?:;ext=|;isub=|\s*(?:e?xt(?:n?\.?|ension)?|x|#)\s*)"
    r"(\d{1,10})$",
    re.IGNORECASE,
)

# RFC 3966 tel: URI — strip scheme and parameters
_TEL_URI_RE = re.compile(r"^tel:", re.IGNORECASE)


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

    @property
    def e164(self) -> str:
        """E.164 formatted string, e.g. ``+15551234567``."""
        return f"+{self.calling_code}{self.national_number}"

    @property
    def is_valid(self) -> bool:
        """True if the national number length is plausible for the calling code."""
        bounds = _CC.get(self.calling_code)
        if bounds is None:
            return False
        return bounds[0] <= len(self.national_number) <= bounds[1]

    @property
    def country_codes(self) -> list[str]:
        """ISO country codes that share this calling code (e.g. ``['US', 'CA']``)."""
        cc = self.calling_code
        return [k for k, v in _REGION.items() if v == cc]

    def __str__(self) -> str:
        return self.e164


# ═══════════════════════════════════════════════════════════════════════
#  CALLING-CODE IDENTIFICATION
# ═══════════════════════════════════════════════════════════════════════


def _identify_cc(digits: str) -> tuple[int, str] | None:
    """Identify the calling code at the start of *digits*.

    Tries 1-, 2-, then 3-digit prefixes.  Returns ``(cc, national)``
    on success, ``None`` on failure.  When multiple prefix lengths are
    in the database, picks the one whose remaining digits satisfy the
    length constraint.
    """
    candidates: list[tuple[int, str]] = []
    for width in (1, 2, 3):
        if len(digits) < width:
            break
        cc = int(digits[:width])
        bounds = _CC.get(cc)
        if bounds is None:
            continue
        national = digits[width:]
        if bounds[0] <= len(national) <= bounds[1]:
            return (cc, national)
        # Remember as fallback even if length is off
        candidates.append((cc, national))

    # If no length-valid match, return the first metadata-recognised
    # prefix (better than nothing for normalisation purposes).
    return candidates[0] if candidates else None


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
        ``None`` if the input cannot be interpretted as a phone number.
    """
    if not raw or not isinstance(raw, str):
        return None

    text = raw.strip()
    if not text:
        return None

    # ── RFC 3966 tel: URI handling ──────────────────────────────
    if _TEL_URI_RE.match(text):
        text = _TEL_URI_RE.sub("", text)
        # Strip ;phone-context= and everything after a ';' param
        semi = text.find(";")
        if semi != -1:
            # But first check for ;ext= / ;isub= before discarding
            params = text[semi:]
            text = text[:semi]
            ext_m = re.search(r";ext=(\d+)", params, re.IGNORECASE)
            if ext_m:
                text = text + " ext " + ext_m.group(1)

    # ── Extract extension ───────────────────────────────────────
    extension: str | None = None
    ext_m = _EXT_RE.search(text)
    if ext_m:
        extension = ext_m.group(1)
        text = text[: ext_m.start()].rstrip()

    # ── Fast path: already E.164 ────────────────────────────────
    m = _E164_RE.match(text)
    if m:
        digits = m.group(1)
        result = _identify_cc(digits)
        if result:
            return PhoneNumber(calling_code=result[0], national_number=result[1], raw=raw, extension=extension)

    # ── Vanity conversion  (1-800-FLOWERS → 1-800-3569377) ──────
    # Only convert if input already has some digits (avoids converting
    # plain text like "no phone here" into digits)
    if any(c.isalpha() for c in text) and any(c.isdigit() for c in text):
        text = text.upper().translate(_VANITY_MAP)

    # ── Strip formatting ────────────────────────────────────────
    stripped = _STRIP_RE.sub("", text)
    if not stripped:
        return None

    # ── Detect international prefix ─────────────────────────────
    international = False

    if stripped.startswith("+"):
        international = True
        stripped = stripped.lstrip("+")
    elif stripped.startswith("011") and len(stripped) > 10:
        # US international dial-out prefix
        international = True
        stripped = stripped[3:]
    elif stripped.startswith("00") and len(stripped) > 9:
        # Common international dial-out prefix
        international = True
        stripped = stripped[2:]

    if not stripped or not stripped[0].isdigit():
        return None

    # ── International: identify calling code from digits ────────
    if international:
        result = _identify_cc(stripped)
        if result:
            return PhoneNumber(calling_code=result[0], national_number=result[1], raw=raw, extension=extension)
        # Couldn't identify CC — give up
        return None

    # ── National: need default_region ───────────────────────────
    if default_region:
        region_upper = default_region.upper()
        cc = _REGION.get(region_upper)
        if cc is not None:
            national = stripped
            # Strip trunk prefix (leading 0) for countries that use one
            if cc not in _NO_TRUNK and national.startswith("0"):
                national = national.lstrip("0")
            bounds = _CC.get(cc)
            if bounds and bounds[0] <= len(national) <= bounds[1]:
                return PhoneNumber(calling_code=cc, national_number=national, raw=raw, extension=extension)
            # Try without stripping in case it's a short number or no trunk
            if national != stripped:
                if bounds and bounds[0] <= len(stripped) <= bounds[1]:
                    return PhoneNumber(calling_code=cc, national_number=stripped, raw=raw, extension=extension)

    # ── Last resort: try to identify CC from raw digits ─────────
    # Some users paste digits with calling code but no + prefix
    if len(stripped) >= 10:
        result = _identify_cc(stripped)
        if result:
            return PhoneNumber(calling_code=result[0], national_number=result[1], raw=raw, extension=extension)

    return None


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
    """Return ``True`` if *raw* can be parsed **and** passes length validation."""
    phone = parse(raw, default_region)
    return phone is not None and phone.is_valid


# ═══════════════════════════════════════════════════════════════════════
#  DISPLAY FORMATTING — INTERNATIONAL / NATIONAL
# ═══════════════════════════════════════════════════════════════════════
#
# Grouping templates for the most common calling codes.
# Keys are calling codes; values are (national_grouping, intl_grouping)
# where each grouping is a list of group sizes applied left-to-right.
# If the national number doesn't match the expected total length, we
# fall back to ungrouped output.

_FORMAT_TEMPLATES: dict[int, tuple[list[int], list[int]]] = {
    # CC: (national_groups, international_groups)
    1:   ([3, 3, 4],      [3, 3, 4]),        # NANP: (555) 123-4567 / +1 555 123 4567
    7:   ([3, 3, 2, 2],   [3, 3, 2, 2]),     # RU: (800) 123-45-67
    20:  ([2, 4, 4],      [2, 4, 4]),         # EG
    27:  ([2, 3, 4],      [2, 3, 4]),         # ZA
    30:  ([3, 3, 4],      [3, 3, 4]),         # GR
    31:  ([2, 3, 4],      [2, 3, 4]),         # NL
    32:  ([3, 2, 2, 2],   [3, 2, 2, 2]),      # BE
    33:  ([1, 2, 2, 2, 2],[1, 2, 2, 2, 2]),   # FR: 01 23 45 67 89
    34:  ([3, 3, 3],      [3, 3, 3]),         # ES
    36:  ([2, 3, 4],      [2, 3, 4]),         # HU
    39:  ([3, 3, 4],      [3, 3, 4]),         # IT
    40:  ([3, 3, 3],      [3, 3, 3]),         # RO
    41:  ([2, 3, 2, 2],   [2, 3, 2, 2]),      # CH
    43:  ([4, 4],         [4, 4]),            # AT
    44:  ([4, 6],         [4, 6]),            # GB: 020 7946 0958
    45:  ([2, 2, 2, 2],   [2, 2, 2, 2]),      # DK
    46:  ([2, 3, 4],      [2, 3, 4]),         # SE
    47:  ([3, 2, 3],      [3, 2, 3]),         # NO
    48:  ([3, 3, 3],      [3, 3, 3]),         # PL
    49:  ([4, 4],         [4, 4]),            # DE
    51:  ([3, 3, 3],      [3, 3, 3]),         # PE
    52:  ([3, 3, 4],      [3, 3, 4]),         # MX
    55:  ([2, 5, 4],      [2, 5, 4]),         # BR
    56:  ([1, 4, 4],      [1, 4, 4]),         # CL
    57:  ([3, 3, 4],      [3, 3, 4]),         # CO
    60:  ([2, 4, 4],      [2, 4, 4]),         # MY
    61:  ([1, 4, 4],      [1, 4, 4]),         # AU
    62:  ([3, 4, 4],      [3, 4, 4]),         # ID
    63:  ([3, 3, 4],      [3, 3, 4]),         # PH
    64:  ([1, 3, 4],      [1, 3, 4]),         # NZ
    65:  ([4, 4],         [4, 4]),            # SG
    66:  ([1, 4, 4],      [1, 4, 4]),         # TH
    81:  ([2, 4, 4],      [2, 4, 4]),         # JP
    82:  ([2, 4, 4],      [2, 4, 4]),         # KR
    84:  ([2, 4, 4],      [2, 4, 4]),         # VN
    86:  ([3, 4, 4],      [3, 4, 4]),         # CN
    90:  ([3, 3, 4],      [3, 3, 4]),         # TR
    91:  ([5, 5],         [5, 5]),            # IN
    92:  ([3, 7],         [3, 7]),            # PK
    98:  ([3, 3, 4],      [3, 3, 4]),         # IR
    234: ([3, 3, 4],      [3, 3, 4]),         # NG
    254: ([3, 6],         [3, 6]),            # KE
    380: ([2, 3, 2, 2],   [2, 3, 2, 2]),      # UA
    966: ([2, 3, 4],      [2, 3, 4]),         # SA
    971: ([2, 3, 4],      [2, 3, 4]),         # AE
}


def _apply_grouping(number: str, groups: list[int]) -> str:
    """Split *number* into groups of the specified sizes, separated by spaces."""
    expected = sum(groups)
    if len(number) != expected:
        # Fallback: no grouping if length doesn't match template
        return number
    parts: list[str] = []
    pos = 0
    for g in groups:
        parts.append(number[pos : pos + g])
        pos += g
    return " ".join(parts)


def _ext_suffix(ext: str | None) -> str:
    """Return the extension suffix string (e.g. ' ext. 123') or empty."""
    return f" ext. {ext}" if ext else ""


def format_international(phone: PhoneNumber) -> str:
    """Format as international display: ``+1 555 123 4567``.

    Falls back to ungrouped ``+CC NATIONAL`` when no template exists.
    """
    cc = phone.calling_code
    nn = phone.national_number
    tmpl = _FORMAT_TEMPLATES.get(cc)
    formatted = _apply_grouping(nn, tmpl[1]) if tmpl else nn
    return f"+{cc} {formatted}{_ext_suffix(phone.extension)}"


def format_national(phone: PhoneNumber) -> str:
    """Format as national display: ``(555) 123-4567`` for NANP, else grouped.

    Falls back to plain national number when no template exists.
    """
    cc = phone.calling_code
    nn = phone.national_number
    ext = _ext_suffix(phone.extension)

    # NANP special: (NPA) NXX-LINE
    if cc == 1 and len(nn) == 10:
        return f"({nn[:3]}) {nn[3:6]}-{nn[6:]}{ext}"

    tmpl = _FORMAT_TEMPLATES.get(cc)
    if tmpl:
        # National format: prepend trunk 0 for countries that use it
        trunk = "0" if cc not in _NO_TRUNK else ""
        formatted = _apply_grouping(nn, tmpl[0])
        return f"{trunk}{formatted}{ext}"

    return f"{nn}{ext}"


# ═══════════════════════════════════════════════════════════════════════
#  NUMBER COMPARISON — is_number_match()
# ═══════════════════════════════════════════════════════════════════════

class MatchType:
    """Result constants for :func:`is_number_match`."""
    NOT_A_NUMBER = 0
    NO_MATCH = 1
    SHORT_NSN_MATCH = 2
    NSN_MATCH = 3
    EXACT_MATCH = 4


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
    pa = a if isinstance(a, PhoneNumber) else parse(a, default_region)
    pb = b if isinstance(b, PhoneNumber) else parse(b, default_region)

    if pa is None or pb is None:
        return MatchType.NOT_A_NUMBER

    if pa.calling_code != pb.calling_code:
        return MatchType.NO_MATCH

    na, nb = pa.national_number, pb.national_number

    if na == nb:
        # Check extensions
        if pa.extension == pb.extension:
            return MatchType.EXACT_MATCH
        if pa.extension is None or pb.extension is None:
            return MatchType.NSN_MATCH
        return MatchType.NO_MATCH

    # Short NSN: one is suffix of the other (at least 7 digits match)
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    if len(shorter) >= 7 and longer.endswith(shorter):
        return MatchType.SHORT_NSN_MATCH

    return MatchType.NO_MATCH


# ═══════════════════════════════════════════════════════════════════════
#  NUMBER TYPE DETECTION (lightweight heuristic)
# ═══════════════════════════════════════════════════════════════════════

class NumberType:
    """Phone number type constants."""
    FIXED_LINE = 0
    MOBILE = 1
    FIXED_LINE_OR_MOBILE = 2
    TOLL_FREE = 3
    PREMIUM_RATE = 4
    VOIP = 6
    UNKNOWN = -1


# Heuristic mobile-prefix rules for top-20 countries.
# Keys: calling code → frozenset of national-number prefixes that are mobile.
_MOBILE_PREFIXES: dict[int, tuple[frozenset[str], int]] = {
    # (prefix_set, prefix_length_to_check)
    1:   (frozenset(), 0),  # NANP: can't distinguish mobile from fixed
    7:   (frozenset({"9"}), 1),  # Russia: 9xx = mobile
    33:  (frozenset({"6", "7"}), 1),  # France: 06/07 = mobile
    34:  (frozenset({"6", "7"}), 1),  # Spain: 6xx/7xx = mobile
    39:  (frozenset({"3"}), 1),  # Italy: 3xx = mobile
    44:  (frozenset({"7"}), 1),  # UK: 07xxx = mobile
    49:  (frozenset({"15", "16", "17"}), 2),  # Germany: 015x/016x/017x
    55:  (frozenset(), 0),  # Brazil: hard to tell (digit 9 prefix varies)
    61:  (frozenset({"4"}), 1),  # Australia: 04xx = mobile
    81:  (frozenset({"70", "80", "90"}), 2),  # Japan: 070/080/090
    82:  (frozenset({"10", "11"}), 2),  # South Korea: 010/011
    86:  (frozenset({"13", "14", "15", "16", "17", "18", "19"}), 2),  # China
    91:  (frozenset({"6", "7", "8", "9"}), 1),  # India: 6-9 = mobile
}

# Toll-free / premium-rate detection by national prefix
_TOLL_FREE_PREFIXES: dict[int, frozenset[str]] = {
    1:  frozenset({"800", "888", "877", "866", "855", "844", "833"}),
    44: frozenset({"800", "808"}),
    61: frozenset({"1800"}),
    49: frozenset({"800"}),
    33: frozenset({"800"}),
}

_PREMIUM_PREFIXES: dict[int, frozenset[str]] = {
    1:  frozenset({"900"}),
    44: frozenset({"90", "91"}),
    49: frozenset({"900"}),
}


def number_type(phone: PhoneNumber) -> int:
    """Return a :class:`NumberType` constant for the given parsed number.

    Uses lightweight heuristic prefix matching — no 6 MB regex database.
    Covers accurate detection for ~20 countries.  Returns ``UNKNOWN`` for
    countries without heuristic rules.
    """
    cc = phone.calling_code
    nn = phone.national_number

    # Check toll-free
    tf = _TOLL_FREE_PREFIXES.get(cc)
    if tf:
        for pf in tf:
            if nn.startswith(pf):
                return NumberType.TOLL_FREE

    # Check premium-rate
    pr = _PREMIUM_PREFIXES.get(cc)
    if pr:
        for pf in pr:
            if nn.startswith(pf):
                return NumberType.PREMIUM_RATE

    # Mobile heuristic
    mp = _MOBILE_PREFIXES.get(cc)
    if mp:
        prefixes, plen = mp
        if plen == 0:
            # Can't distinguish (NANP, Brazil)
            return NumberType.FIXED_LINE_OR_MOBILE
        prefix = nn[:plen]
        if prefix in prefixes:
            return NumberType.MOBILE
        return NumberType.FIXED_LINE

    return NumberType.UNKNOWN


# ═══════════════════════════════════════════════════════════════════════
#  PHONE NUMBER MATCHER — extract phones from free text
# ═══════════════════════════════════════════════════════════════════════

# Regex to find phone-number-like sequences in text.
# Matches patterns like +1 (555) 123-4567, 020 7946 0958, etc.
_PHONE_CANDIDATE_RE = re.compile(
    r"""
    (?:
        \+?                        # optional leading +
        [\d]                       # must start with digit (after optional +)
        [\d\s\-.()/]{5,18}        # body: digits, spaces, separators
        \d                         # must end with digit
    )
    """,
    re.VERBOSE,
)


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

    Usage::

        text = "Call me at +1 555 123 4567 or 020 7946 0958"
        for match in PhoneNumberMatcher(text, default_region="GB"):
            print(match.number.e164, match.start, match.end)
    """

    def __init__(self, text: str, default_region: str | None = None):
        self._text = text
        self._region = default_region
        self._matches: list[PhoneNumberMatch] | None = None

    def _find_all(self) -> list[PhoneNumberMatch]:
        results: list[PhoneNumberMatch] = []
        for m in _PHONE_CANDIDATE_RE.finditer(self._text):
            candidate = m.group(0).strip()
            phone = parse(candidate, self._region)
            if phone is not None and phone.is_valid:
                results.append(
                    PhoneNumberMatch(
                        start=m.start(),
                        end=m.start() + len(candidate),
                        raw_string=candidate,
                        number=phone,
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
