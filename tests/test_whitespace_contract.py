"""What counts as whitespace, and how a value is quoted back in a warning.

Python's ``str.strip()`` and JavaScript's ``String.prototype.trim()`` do not
agree: ``trim()`` strips U+FEFF and Python does not, Python strips U+001C-001F
and U+0085 and ``trim()`` does not.  A UTF-8 CSV puts a byte-order mark on its
first field, so the disagreement reached ordinary data - the same column
normalized to ``""`` in one package and kept its mark in the other, and a
BOM-prefixed header resolved at a different confidence in each.

Python's ``repr()`` escapes those characters too, which is why the warning text
is pinned here beside the values.  All of these passed here before the fix;
they exist because ``packages/js/test/python_whitespace.test.ts`` mirrors them
one-for-one, and that is where they failed.

Every invisible character is built with ``chr()`` rather than pasted: a source
file that carries a real NUL or BOM is one no reviewer can see.
"""

from __future__ import annotations

from rolodexter import ContactMapper, normalize_value

BOM = chr(0xFEFF)
FILE_SEPARATOR = chr(0x1C)
NEL = chr(0x85)
NBSP = chr(0xA0)


class TestWhitespaceSet:
    def test_a_byte_order_mark_is_not_whitespace(self) -> None:
        assert normalize_value("unknown", BOM) == BOM
        assert normalize_value("company", BOM) == BOM
        assert normalize_value("email", BOM) == BOM
        assert normalize_value("notes", f"{BOM}hello{BOM}") == f"{BOM}hello{BOM}"

    def test_separator_and_c1_whitespace_is_stripped(self) -> None:
        assert normalize_value("unknown", FILE_SEPARATOR) == ""
        assert normalize_value("unknown", NEL) == ""
        assert normalize_value("unknown", f"{FILE_SEPARATOR}hello{NEL}") == "hello"
        assert normalize_value("unknown", f"{NBSP}hello{NBSP}") == "hello"

    def test_a_name_splits_on_the_same_whitespace_set(self) -> None:
        assert normalize_value("first_name", f"ada{NEL}lovelace") == "Ada Lovelace"
        assert (
            normalize_value("first_name", f"ada{FILE_SEPARATOR}lovelace")
            == "Ada Lovelace"
        )
        # A byte-order mark is NOT a split point, so the name stays one word.
        # Whether the half after it gets capitalized is a separate question -
        # Python's str.title() treats any non-letter as a word boundary and
        # JavaScript's does not - and that difference is tracked as the name
        # casing class in docs/maintenance/parity_sweep.md, not pinned here.
        assert BOM in str(normalize_value("first_name", f"ada{BOM}lovelace"))


class TestBomPrefixedHeader:
    def test_it_resolves_as_a_normalized_match(self) -> None:
        # What Excel writes on the first column of a UTF-8 CSV. Resolving it as
        # an exact match in one package and a normalized one in the other meant
        # a confidence threshold above 0.95 kept the column in one and dropped
        # it in the other.
        match = ContactMapper().identify(f"{BOM}fname")

        assert match.canonical == "first_name"
        assert match.confidence == 0.95
        assert match.strategy == "normalized"


class TestWarningQuoting:
    def test_a_non_printable_value_is_escaped_in_the_warning(self) -> None:
        result = ContactMapper().map_payload({"email": BOM})

        assert [str(w) for w in result.warnings] == [
            "'email': value '\\ufeff' does not look like an email address"
        ]

    def test_a_control_character_is_escaped_in_the_warning(self) -> None:
        result = ContactMapper().map_payload({"email": f"a{FILE_SEPARATOR}b@x"})

        assert [str(w) for w in result.warnings] == [
            "'email': value 'a\\x1cb@x' does not look like an email address"
        ]
