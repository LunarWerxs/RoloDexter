"""Small text helpers shared by the name and place normalizers.

Extracted verbatim from ``core.py``, which re-imports every name here so
``rolodexter.core`` keeps the whole surface its callers and tests import.
"""

from __future__ import annotations

import re

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
