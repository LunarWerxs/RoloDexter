"""Accuracy benchmark + property-based tests.

The golden corpora below are labeled header→canonical maps for real CRM/export
formats.  They turn "looks right" into a measured precision/recall floor that
catches regressions (e.g. a fuzzy change that starts misrouting a column).

The Hypothesis tests assert invariants that should hold for *any* input:
mapping never crashes, header resolution is deterministic, and value
normalization is idempotent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from rolodexter import ContactMapper
from rolodexter.core import normalize_value

# ── Shared golden corpora: header → expected canonical field ─────────────

CORPORA: dict[str, dict[str, str]] = json.loads(
    (Path(__file__).parent / "fixtures" / "golden_corpora.json").read_text(
        encoding="utf-8"
    )
)


@pytest.fixture(scope="module")
def mapper() -> ContactMapper:
    return ContactMapper()


def _score(mapper: ContactMapper, expected: dict[str, str]) -> tuple[int, int, int]:
    """Return (correct, predicted, misrouted) for a corpus."""
    correct = predicted = misrouted = 0
    for header, want in expected.items():
        got = mapper.identify(header).canonical
        if got != "unknown":
            predicted += 1
        if got == want:
            correct += 1
        elif got != "unknown":
            misrouted += 1
    return correct, predicted, misrouted


class TestCorpusAccuracy:
    @pytest.mark.parametrize("corpus", sorted(CORPORA))
    def test_recall_floor(self, mapper: ContactMapper, corpus: str) -> None:
        """At least 90% of known headers in each corpus map correctly."""
        expected = CORPORA[corpus]
        correct, _, _ = _score(mapper, expected)
        recall = correct / len(expected)
        assert recall >= 0.9, f"{corpus}: recall {recall:.2%} below floor"

    @pytest.mark.parametrize("corpus", sorted(CORPORA))
    def test_no_misroutes(self, mapper: ContactMapper, corpus: str) -> None:
        """No header maps to the *wrong* canonical field (it may be unknown).

        This is the precision guard against fuzzy/heuristic mis-mapping —
        the failure mode behind the "Job Titel -> phone" class of bugs.
        """
        _, _, misrouted = _score(mapper, CORPORA[corpus])
        assert misrouted == 0, f"{corpus}: {misrouted} header(s) misrouted"

    def test_overall_recall(self, mapper: ContactMapper) -> None:
        total = sum(len(v) for v in CORPORA.values())
        correct = sum(_score(mapper, v)[0] for v in CORPORA.values())
        assert correct / total >= 0.95


# ── Property-based invariants ───────────────────────────────────────────

_TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cs", "Cc")),
    max_size=40,
)


class TestProperties:
    @settings(max_examples=200, deadline=None)
    @given(header=_TEXT)
    def test_identify_is_deterministic(self, header: str) -> None:
        a = ContactMapper().identify(header).canonical
        b = ContactMapper().identify(header).canonical
        assert a == b

    @settings(max_examples=200, deadline=None)
    @given(
        payload=st.dictionaries(_TEXT, _TEXT, max_size=8),
    )
    def test_map_payload_never_crashes(self, payload: dict[str, str]) -> None:
        result = ContactMapper().map_payload(payload)
        # Every input key is accounted for exactly once across the outputs.
        assert len(result.field_matches) == len(payload)

    @settings(max_examples=200, deadline=None)
    @given(value=_TEXT)
    def test_email_normalization_is_idempotent(self, value: str) -> None:
        once = normalize_value("email", value)
        twice = normalize_value("email", once)
        assert once == twice

    @settings(max_examples=200, deadline=None)
    @given(value=_TEXT)
    def test_string_normalization_is_idempotent(self, value: str) -> None:
        once = normalize_value("notes", value)
        twice = normalize_value("notes", once)
        assert once == twice
