"""Small text helpers shared by the name and place normalizers.

Extracted verbatim from ``core.py``, which re-imports every name here so
``rolodexter.core`` keeps the whole surface its callers and tests import.
"""

from __future__ import annotations

import re

from ._tables import TABLES

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


# US states, DC and territories, then Canadian provinces and territories.
# Owned here, not in ``_geo``, because the place casing below needs it and
# ``_geo`` imports this module; ``StateNormalizer._CODES`` is this set.
_REGION_CODES: frozenset[str] = frozenset(TABLES["text"]["region_codes"])

# Words written in capitals wherever they stand in an all-caps place value:
# compass points, post-office and military mail words, and country
# abbreviations.  Region codes are kept upper too, but only where a region
# code stands (see _region_position), so "LA JOLLA" still reads "La Jolla".
_ALWAYS_UPPER: frozenset[str] = frozenset(TABLES["text"]["always_upper"])

_DIGIT_RE = re.compile(r"[0-9]")
_NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9]")


def _is_all_caps(text: str) -> bool:
    """``str.isupper()``: has a cased letter and no lowercase one."""
    return text.isupper()


def _region_position(words: list[str], index: int) -> bool:
    """True where a region code stands: after a comma or before a postcode.

    ``SPRINGFIELD, IL`` and ``IL 62704`` hold a region code; ``1 OAK CT``
    (a court) and ``LA JOLLA`` do not.
    """
    if index > 0 and words[index - 1].endswith(","):
        return True
    return index + 1 < len(words) and bool(_DIGIT_RE.search(words[index + 1]))


def _keep_upper_in_caps(words: list[str], index: int) -> bool:
    """True when an all-caps place value should keep *words[index]* as written."""
    word = words[index]
    key = _NON_ALNUM_RE.sub("", word).upper()
    if _ORDINAL_RE.match(key.lower()):  # 5TH → 5th, through the usual rule
        return False
    if _DIGIT_RE.search(word):  # 4B, 62704, #12A
        return True
    if key in _ALWAYS_UPPER:
        return True
    return key in _REGION_CODES and _region_position(words, index)


def _smart_titlecase(text: str) -> str:
    """Title-case a place value (whitespace already collapsed) without mangling.

    A value that mixes case was typed by someone who meant it, so only its
    all-lower words are re-cased: words written in capitals (``IL``, ``NW``,
    ``PO``, ``USA``) and words holding a digit (``4B``) stay as written.  A
    value written entirely in capitals is re-cased word by word, except
    compass points, ``PO``/``APO``/``FPO``, ``USA``/``US``/``UK``/``DC``,
    words holding a digit, and a US state or Canadian province code where a
    region code stands.  Every value keeps words that carry a deliberate
    inner capital (``McDonald``, ``iPhone``), lower-cases ordinal suffixes,
    handles Mc-names and capitalizes apostrophe segments only when long
    enough (``O'Brien`` but not ``Macy'S``).

    """
    shouting = _is_all_caps(text)
    words = text.split()
    out: list[str] = []
    for index, word in enumerate(words):
        # Preserve tokens that already mix upper and lower case.
        if (
            not word.isupper()
            and not word.islower()
            and any(c.isupper() for c in word[1:])
        ):
            out.append(word)
            continue
        if shouting:
            if _keep_upper_in_caps(words, index):
                out.append(word)
                continue
        elif _is_all_caps(word) or _DIGIT_RE.search(word):
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
