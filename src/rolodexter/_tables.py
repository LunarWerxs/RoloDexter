"""The shared data tables, read once from ``tables.json``.

``tables.json`` sits beside ``patterns.json``: the TypeScript package syncs and
copies the same file and reads it the same way, so both languages load one set
of lists, maps and confidence values. Nothing here imports another rolodexter
module, so every module that needs a table can import it without a cycle.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any


def _load_tables() -> dict[str, Any]:
    text = (
        resources.files("rolodexter")
        .joinpath("tables.json")
        .read_text(encoding="utf-8")
    )
    data: dict[str, Any] = json.loads(text)
    return data


TABLES: dict[str, Any] = _load_tables()
