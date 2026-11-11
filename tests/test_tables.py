"""Guards for the shared data file ``tables.json``.

The file has to load, carry the same version as ``patterns.json``, and hold no
key that the Python package never reads. The name-particle list the TypeScript
package keeps in ``_names.ts`` must stay a subset of what nameparser knows, so
that copy cannot drift from the library unnoticed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from rolodexter._normalizers import NameNormalizer
from rolodexter._tables import TABLES

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "rolodexter"
JS_NAMES = ROOT / "packages" / "js" / "src" / "_names.ts"


def _unused_keys(
    source: str, node: dict[str, Any], prefix: tuple[str, ...] = ()
) -> list[str]:
    """Return the table keys whose ``TABLES[...]`` accessor the source never uses."""
    unused: list[str] = []
    for key, value in node.items():
        path = (*prefix, key)
        if path == ("version",):
            # Read by scripts/check_release_versions.py, not by the package.
            continue
        accessor = "TABLES" + "".join(f'["{part}"]' for part in path)
        whole = re.escape(accessor) + r"(?!\[)"
        if isinstance(value, dict) and any(isinstance(v, dict) for v in value.values()):
            unused.extend(_unused_keys(source, value, path))
        elif isinstance(value, dict):
            # A flat map: used whole, or every key of it is indexed.
            if re.search(whole, source):
                continue
            unused.extend(
                ".".join((*path, child))
                for child in value
                if accessor + f'["{child}"]' not in source
            )
        elif not re.search(whole, source):
            unused.append(".".join(path))
    return unused


def test_tables_json_loads_and_matches_patterns_version() -> None:
    tables = json.loads((PACKAGE / "tables.json").read_text(encoding="utf-8"))
    patterns = json.loads((PACKAGE / "patterns.json").read_text(encoding="utf-8"))
    assert tables == TABLES
    assert tables["version"] == patterns["version"]


def test_every_tables_key_is_read_by_the_python_package() -> None:
    source = "\n".join(
        p.read_text(encoding="utf-8") for p in sorted(PACKAGE.glob("*.py"))
    )
    assert _unused_keys(source, TABLES) == []


def test_nameparser_mirror_js_particles_are_known_to_nameparser() -> None:
    # The JS copy of the particle list must not name a particle that nameparser
    # (plus this package's own extras) does not know. Skips where nameparser is
    # not installed.
    config = pytest.importorskip("nameparser.config")
    known = {p.lower() for p in config.Constants().prefixes}
    known |= {p.lower() for p in NameNormalizer._EXTRA_PREFIXES}

    text = JS_NAMES.read_text(encoding="utf-8")
    start = text.index("const NAME_PARTICLES")
    body = text[start : text.index("]);", start)]
    js_particles = set(re.findall(r'"([^"]+)"', body))

    assert js_particles, "NAME_PARTICLES literal not found in _names.ts"
    assert sorted(js_particles - known) == []
