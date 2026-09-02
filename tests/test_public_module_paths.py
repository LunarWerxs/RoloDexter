"""The 2.12.0 module split must be invisible from the outside.

``core.py`` was split into private ``_*`` modules, with ``rolodexter.core``
re-exporting the same names.  Attribute access survived that by construction;
three things did not, and each is pinned here because it reached a user:

* ``__module__``.  A class defined in ``rolodexter._models`` says so in its
  repr, in every traceback that names it, and in every pickle.  2.11.1 said
  ``rolodexter.core``, so a pickle written after the split failed to load on
  a 2.11.1 rollback with ``ModuleNotFoundError: rolodexter._models``.
* ``nameparser``'s shared ``CONSTANTS`` singleton was mutated on first use.
  nameparser 2.2 deprecates that for removal in 3.0, so every first
  ``map_payload`` raised under ``-W error`` (``filterwarnings = error`` in a
  user's pytest config), and the particle set leaked into every other
  ``HumanName`` in the process.
* A ``unittest.mock.patch`` target on ``rolodexter.core`` no longer reaches
  the code that runs, because the code now looks its collaborators up in the
  owning module.  That one is documented rather than fixed (redirecting it
  would mean the private modules importing from the facade), and the test
  below pins the owning-module target the changelog tells users to use.
"""

from __future__ import annotations

import pickle
import warnings
from unittest import mock

import pytest

import rolodexter
import rolodexter.core as core
from rolodexter import ContactMapper, MappingResult, NameNormalizer, NormalizationError


class TestModulePaths:
    def test_every_public_name_reports_rolodexter_core(self) -> None:
        # Exactly what 2.11.1 reported, for every class and function.
        private = [
            name
            for name in core.__all__
            if callable(getattr(core, name))
            and getattr(core, name).__module__.startswith("rolodexter._")
        ]
        assert private == []
        assert MappingResult.__module__ == "rolodexter.core"
        assert NormalizationError.__module__ == "rolodexter.core"
        assert core.normalize_value.__module__ == "rolodexter.core"
        # The package root re-exports the same objects, so it agrees.
        assert rolodexter.MappingResult is MappingResult

    def test_pickle_names_the_public_module_and_round_trips(self) -> None:
        result = ContactMapper().map_payload(
            {"fname": "Ada", "mobile": "(202) 555-0143"}
        )
        data = pickle.dumps(result)
        # The pickle stream carries the module path as bytes, so a 2.11.1
        # process, which has no rolodexter._results, can still load it.
        assert b"rolodexter.core" in data
        assert b"rolodexter._" not in data
        loaded = pickle.loads(data)
        assert loaded.normalized == result.normalized

    def test_traceback_names_the_public_module(self) -> None:
        with pytest.raises(NormalizationError) as info:
            raise NormalizationError("x")
        assert info.type.__module__ == "rolodexter.core"

    def test_patch_target_is_the_owning_module(self) -> None:
        # What the changelog tells a user whose stub of rolodexter.core.X
        # silently stopped applying: patch the module that owns X.
        with mock.patch(
            "rolodexter._mapper.normalize_value", return_value="stubbed"
        ) as stub:
            result = ContactMapper().map_payload({"fname": "ada"})
        assert stub.called
        assert result.normalized["first_name"] == "stubbed"


class TestNameparserIsolation:
    def test_normalizing_a_name_raises_no_warning(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert NameNormalizer.normalize("jane ten boom") == "Jane ten Boom"
            assert NameNormalizer.parse("jane ten boom")["last"] == "ten boom"

    def test_particles_live_in_a_private_constants_not_the_singleton(self) -> None:
        from nameparser.config import CONSTANTS

        private = NameNormalizer._nameparser_constants()
        assert private is not CONSTANTS
        assert NameNormalizer._nameparser_constants() is private
        for particle in NameNormalizer._EXTRA_PREFIXES:
            assert particle in private.prefixes
