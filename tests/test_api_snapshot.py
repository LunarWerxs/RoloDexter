"""The API snapshot's verdict logic, which CI gates releases on.

``scripts/api_snapshot.py`` turns the two packages' public surfaces into
per-export hashes and classifies every difference against the goldens.  The
goldens themselves are checked by ``npm run check:parity``; what is pinned
here is the part a wrong edit would silently weaken: which change counts as
breaking, that a change deep in a shared type reaches every export using it,
and that rendering does not depend on the process's hash seed.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "api_snapshot.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("api_snapshot", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


snap = _load()


def _surface(options_text: str) -> dict:
    return {
        "modules": {
            "rolodexter": {
                "Mapper": {
                    "text": "class Mapper\n  map(options: Options): Result",
                    "refs": [],
                    "members": {"map": "map(options: Options): Result"},
                },
                "normalize": {"text": "def normalize(value: str) -> str"},
            },
        },
        "types": {
            "Options": {"text": options_text},
            "Result": {"text": "interface Result { ok: boolean }"},
        },
    }


class TestVerdicts:
    def test_removed_changed_and_added_names_are_classified(self) -> None:
        golden = {"rolodexter": {"gone": "aaaa", "same": "bbbb", "moved": "cccc"}}
        live = {"rolodexter": {"same": "bbbb", "moved": "dddd", "new": "eeee"}}

        changes = snap.diff_manifests(golden, live)

        assert changes == [
            (snap.BREAKING, "rolodexter", "gone"),
            (snap.POTENTIALLY_BREAKING, "rolodexter", "moved"),
            (snap.POTENTIALLY_NON_BREAKING, "rolodexter", "new"),
        ]
        assert snap.suggested_bump(changes) == "major"

    def test_a_removed_module_breaks_every_name_in_it(self) -> None:
        changes = snap.diff_manifests({"rolodexter.i18n": {"load": "aaaa"}}, {})
        assert changes == [(snap.BREAKING, "rolodexter.i18n", "load")]

    def test_additions_alone_suggest_a_minor_bump(self) -> None:
        changes = snap.diff_manifests({}, {"rolodexter": {"new": "aaaa"}})
        assert snap.suggested_bump(changes) == "minor"
        assert snap.suggested_bump([]) == "none"


class TestTransitiveHashes:
    def test_a_dependency_change_rehashes_every_export_that_reaches_it(self) -> None:
        before, _ = snap.build_manifest(
            _surface("interface Options { depth: number }")
        )
        after, reached = snap.build_manifest(
            _surface("interface Options { depth: string }")
        )

        changes = snap.diff_manifests(before, after)

        # The export and the member whose signature names Options both move;
        # an export that never reaches Options does not.
        assert changes == [
            (snap.POTENTIALLY_BREAKING, "rolodexter", "Mapper"),
            (snap.POTENTIALLY_BREAKING, "rolodexter", "Mapper.map"),
        ]
        assert reached == {"Options", "Result"}

    def test_every_member_is_its_own_entry_so_removing_one_is_breaking(self) -> None:
        manifest, _ = snap.build_manifest(_surface("interface Options {}"))
        assert set(manifest["rolodexter"]) == {"Mapper", "Mapper.map", "normalize"}


class TestDeterminism:
    def test_set_values_render_in_sorted_order(self) -> None:
        # A frozenset's iteration order follows PYTHONHASHSEED; left unsorted,
        # a class constant would flip its hash between two identical runs.
        rendered = snap._stable_repr(frozenset({"b", "a", "c"}))
        assert rendered == "frozenset({'a', 'b', 'c'})"

    def test_memory_addresses_are_dropped_from_default_values(self) -> None:
        sentinel = object()
        assert " at 0x" not in snap._stable_repr(sentinel)
