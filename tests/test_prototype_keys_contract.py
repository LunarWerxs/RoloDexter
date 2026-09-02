"""Prototype member names are ordinary data, in both languages.

A plain JavaScript object used as a lookup table answers for keys nobody put in
it: ``COUNTRY_NAMES["constructor"]`` is the ``Object`` function and
``COUNTRY_NAMES["__proto__"]`` is ``Object.prototype``.  Before 2.11.2 a contact
whose country column read ``constructor`` therefore normalized to a *function*
in the JavaScript package, and one reading ``__proto__`` to an object, from an
API typed to return a string.  A Python ``dict`` has no inherited members, so
the same rows stayed strings here - which made it a type confusion there and a
cross-language divergence at the same time.

Every assertion below already passed before the fix.  They exist because
``packages/js/test/prototype_keys.test.ts`` mirrors them one-for-one, and that
is where they failed - the same shape as the whitespace contract, and the same
reason the pair is kept in step.

This is the read-side sibling of the ``__proto__``-as-a-column work in 2.11.0:
that fixed writing a user-controlled key into a plain object, this fixes reading
one back out of a lookup table.
"""

from __future__ import annotations

import json

import pytest

from rolodexter import ContactMapper, normalize_value
from rolodexter.i18n import generate_language, load_cached

# Every name Object.prototype contributes on the JavaScript side.  Listed rather
# than derived so that a future engine adding a member cannot silently shrink
# the mirrored test.
PROTOTYPE_KEYS = [
    "__proto__",
    "constructor",
    "toString",
    "toLocaleString",
    "valueOf",
    "hasOwnProperty",
    "isPrototypeOf",
    "propertyIsEnumerable",
    "__defineGetter__",
    "__defineSetter__",
    "__lookupGetter__",
    "__lookupSetter__",
]


class TestGeoLookups:
    @pytest.mark.parametrize("key", PROTOTYPE_KEYS)
    def test_a_country_column_holding_a_prototype_name_stays_a_string(
        self, key: str
    ) -> None:
        assert isinstance(normalize_value("country", key), str)

    @pytest.mark.parametrize("key", PROTOTYPE_KEYS)
    def test_a_state_column_holding_a_prototype_name_stays_a_string(
        self, key: str
    ) -> None:
        assert isinstance(normalize_value("state", key), str)

    def test_the_two_that_actually_collided_are_pinned_by_value(self) -> None:
        # Only names that survive the lookup's own lowercasing could collide,
        # which is why these two leaked in JavaScript and "toString" did not.
        assert normalize_value("country", "__proto__") == "__proto__"
        assert normalize_value("country", "constructor") == "constructor"
        assert normalize_value("state", "__proto__") == "__proto__"
        # An unmatched state is title-cased like any other unknown value.
        assert normalize_value("state", "constructor") == "Constructor"

    def test_a_real_country_still_resolves(self) -> None:
        # The fix rebuilt the lookup tables, so prove they still hold data.
        assert normalize_value("country", "United States") == "US"
        assert normalize_value("country", "deutschland") == "DE"
        assert normalize_value("country", "usa") == "US"
        assert normalize_value("country", "gb") == "GB"
        assert normalize_value("state", "california") == "CA"
        assert normalize_value("state", "Ontario") == "ON"


class TestLanguageCodes:
    @pytest.mark.parametrize("key", PROTOTYPE_KEYS)
    def test_a_prototype_name_is_not_a_supported_language(self, key: str) -> None:
        # JavaScript's `in` accepted all of these, and the generator then tried
        # to destructure Object.prototype as a (code, name) pair.
        with pytest.raises(ValueError, match="Unsupported language"):
            generate_language(key)

    @pytest.mark.parametrize("key", PROTOTYPE_KEYS)
    def test_a_prototype_name_loads_no_cached_language(self, key: str) -> None:
        assert load_cached(key) is None


class TestPayloadRoundTrip:
    def test_a_payload_of_prototype_names_maps_without_type_confusion(self) -> None:
        result = ContactMapper().map_payload(
            {"country": "constructor", "state": "__proto__"}
        )
        for value in result.normalized.values():
            assert isinstance(value, (str, list)) or value is None

    def test_the_values_survive_a_json_round_trip(self) -> None:
        # JSON is the round trip a function silently fails: it encodes to
        # nothing and the key disappears from the output entirely.
        result = ContactMapper().map_payload(
            {"country": "constructor", "state": "__proto__"}
        )
        assert "constructor" in json.dumps(result.to_dict())
