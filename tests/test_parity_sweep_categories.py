"""The parity sweep's CATEGORIES list names every label classify() can return.

Before this, the two fallback labels ("other string normalizer" and "other")
were bare literals inside classify(), absent from the list of categories.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "parity_sweep.py"


def _load() -> ModuleType:
    # parity_sweep imports parity_sweep_values from its own folder, which is
    # sys.path[0] only when it runs as a script; add it for this import.
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("parity_sweep", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses looks the module up in sys.modules while it executes.
    sys.modules["parity_sweep"] = module
    spec.loader.exec_module(module)
    return module


class ClassifyCategoriesTest(unittest.TestCase):
    def test_fallback_labels_are_listed_as_categories(self) -> None:
        sweep = _load()
        cases = [
            ("normalize", {"field": "not_a_known_field", "value": "abc"}),
            ("unknown_section", {}),
        ]
        for section, item in cases:
            label = sweep.classify(section, item)
            self.assertIn(label, sweep.CATEGORIES, msg=f"{section}: {label!r}")


if __name__ == "__main__":
    unittest.main()
