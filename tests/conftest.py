"""Fixtures shared by the rolodexter test modules.

Extracted verbatim from ``test_rolodexter.py`` when that file was split. A
conftest is the right home now that more than one module requests them; the
two suites that define their own ``mapper`` keep it, since a module-level
fixture shadows a conftest one.
"""

from __future__ import annotations

import pytest

from rolodexter import ContactMapper, PatternRegistry

# ═══════════════════════════════════════════════════════════════
#  FIXTURES
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def registry() -> PatternRegistry:
    return PatternRegistry()


@pytest.fixture
def mapper() -> ContactMapper:
    return ContactMapper()


@pytest.fixture
def mapper_no_norm() -> ContactMapper:
    return ContactMapper(normalize=False)


@pytest.fixture
def sample_payload() -> dict:
    return {
        "fname": "jane",
        "surname": "doe",
        "mobile": "+1-555-019-9876",
        "employer": "Tech Corp",
        "designation": "Senior Engineer",
        "Column 1": "jane.doe@example.com",
        "favorite_color": "Blue",
    }
