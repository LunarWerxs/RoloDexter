"""Shared Python/TypeScript conformance fixture suite.

``tests/fixtures/conformance_cases.json`` holds a small set of
input/expected-output cases for behaviors that have historically diverged
between the Python package and the ``packages/js`` TypeScript port (see
CHANGELOG.md for the concrete parity bugs these cover: 7-digit US local
phone normalization, cross-country number matching, list-value merge/dedupe
semantics, fuzzy confidence bands, and schema confidence-threshold
filtering). This file exercises the Python side; ``packages/js/test/
mapper.test.ts`` exercises the same fixture against the TypeScript port, so
a regression on either side that drifts from the fixture fails in CI
independent of the other language being present.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from rolodexter import ContactMapper, is_number_match, normalize_value

CASES: dict[str, Any] = json.loads(
    (Path(__file__).parent / "fixtures" / "conformance_cases.json").read_text(
        encoding="utf-8"
    )
)


@pytest.fixture(scope="module")
def mapper() -> ContactMapper:
    return ContactMapper()


@pytest.mark.parametrize(
    "case", CASES["normalize"], ids=[c["id"] for c in CASES["normalize"]]
)
def test_normalize(case: dict[str, Any]) -> None:
    got = normalize_value(
        case["field"], case["value"], default_region=case.get("default_region")
    )
    assert got == case["expected"]


@pytest.mark.parametrize(
    "case", CASES["payloads"], ids=[c["id"] for c in CASES["payloads"]]
)
def test_map_payload(mapper: ContactMapper, case: dict[str, Any]) -> None:
    result = mapper.map_payload(case["payload"])
    for key, expected in case["expected_normalized"].items():
        assert result.normalized.get(key) == expected


@pytest.mark.parametrize(
    "case", CASES["phones"], ids=[c["id"] for c in CASES["phones"]]
)
def test_phone_match(case: dict[str, Any]) -> None:
    assert case["fn"] == "is_number_match"
    got = int(
        is_number_match(case["a"], case["b"], default_region=case.get("default_region"))
    )
    assert got == case["expected"]


@pytest.mark.parametrize(
    "case", CASES["identify"], ids=[c["id"] for c in CASES["identify"]]
)
def test_identify(mapper: ContactMapper, case: dict[str, Any]) -> None:
    field_match = mapper.identify(case["header"])
    assert field_match.canonical == case["expected_canonical"]
    assert field_match.strategy == case["expected_strategy"]
    assert field_match.confidence == case["expected_confidence"]


@pytest.mark.parametrize(
    "case", CASES["schemas"], ids=[c["id"] for c in CASES["schemas"]]
)
def test_compile_schema(mapper: ContactMapper, case: dict[str, Any]) -> None:
    schema = mapper.compile_schema(case["headers"], **case.get("mapper_options", {}))
    for header, expected in case["expected_matches"].items():
        field_match = schema.matches[header]
        assert field_match.canonical == expected["canonical"]
        assert field_match.confidence == expected["confidence"]
        assert field_match.strategy == expected["strategy"]
