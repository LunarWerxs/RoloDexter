"""The value corpus for the cross-language sweep.

It lives in its own module because it is the only part that needs invisible and
control characters.  Those are built with ``chr()`` rather than typed, so the
source file itself holds no NUL, no ESC and no BOM: a file that smuggles those
is one no reviewer can see, and mangling them in transit is exactly the kind of
bug this sweep exists to find.
"""

from __future__ import annotations

from typing import Any

NUL = chr(0x00)
ESC = chr(0x1B)
TAB = chr(0x09)
NEWLINE = chr(0x0A)
NBSP = chr(0xA0)
ZERO_WIDTH_SPACE = chr(0x200B)
BOM = chr(0xFEFF)
EMOJI = chr(0x1F600)
E_ACUTE = chr(0xE9)
E_PLUS_COMBINING_ACUTE = "e" + chr(0x301)
FULLWIDTH_AB = chr(0xFF21) + chr(0xFF22)
DOTTED_CAPITAL_I = chr(0x130)
TITLECASE_DZ = chr(0x1C5)
SHARP_S = chr(0xDF)

# Every value is fed to every canonical field, so a normalizer that mishandles
# a shape meant for a different field still shows up.
VALUES: list[Any] = [
    # empties, whitespace, invisibles, control characters
    None, "", " ", "   ", TAB, NEWLINE, f" {NBSP} ", ZERO_WIDTH_SPACE, BOM,
    NUL, f"{ESC}[31mred{ESC}[0m",
    # scalars that are not strings
    True, False, 0, 1, -1, 123, {"$": "float", "v": 1.5}, {"$": "float", "v": 0.0},
    {"$": "nan"}, {"$": "inf"}, {"$": "ninf"}, {"$": "float", "v": 2025550143.0},
    [], {}, ["a", "b"], ["a", "a"], [""], [None], {"x": 1},
    # names, including the mixed-case ones the two implementations disagree on
    "ada lovelace", "  Ada   Lovelace  ", "ADA LOVELACE", "mcdonald", "MacDonald",
    "o'brien", "d'angelo", "jean-luc picard", "van der berg", "maria dos santos",
    "anna van den heuvel", "giovanni della casa", "sven op den kamp", "de la cruz",
    f"{E_ACUTE}lodie durand", "ada", "dr. ada lovelace jr.",
    "LOVELACE, ADA", "ada  lovelace", "a", "ADA", "de", "van",
    "DeAngelo", "LaToya", "DiCaprio", "JoAnne",
    # emails
    "ADA@EXAMPLE.COM", " ada@example.com ", "ada+tag@example.co.uk", "ada@",
    "@example.com", "not an email", "ada@example", "ada @ example.com",
    f"{E_ACUTE}@example.com", "ada@EXAMPLE.com", "a@b.co", "ada@exam ple.com",
    # phones
    "+1 202 555 0143", "(202) 555-0143", "202.555.0143", "2025550143",
    "+44 20 7946 0958", "020 7946 0958", "0044 20 7946 0958", "+1-800-FLOWERS",
    "+81 3-1234-5678", "123", "+999 000 000 0000", "+1 202 555 0143 ext. 99",
    "call me at +1 202 555 0143", "555-0143", "+1 (202) 555-0143 x99",
    # urls and socials
    "https://example.com", "example.com", "www.example.com", "HTTP://EXAMPLE.COM/",
    "@handle", "https://twitter.com/handle", "linkedin.com/in/ada", "not a url",
    "ftp://example.com", "//example.com", "https://example.com/path?q=1#f",
    # dates
    "2024-03-15", "25/03/2024", "03/04/2024", "12/11/68", "2024/3/5",
    "March 15, 2024", "15 March 2024", "2024-13-45", "not a date", "0000-00-00",
    "2024-02-29", "2023-02-29", "20240315", "1710460800",
    # countries, states, postal codes
    "United States", "united states", "deutschland", "gb", "GB", "Freedonia",
    "california", "Ontario", "Bavaria", "CA", "90210", "K1A 0B1", "SW1A 1AA",
    "10115", "45000", "99999", "1234", "123456789",
    # booleans and numbers
    "yes", "no", "true", "FALSE", "y", "n", "1", "0", "on", "off", "maybe",
    "$1,234.56", "1.234,56", "1e5", "-42", "0x1F", "  42  ", "42%",
    # lists
    "alpha,beta", "alpha, beta", "alpha;beta", "alpha|beta", "a,,b", ",",
    "alpha,alpha", " alpha , beta ",
    # addresses and free text
    "123 Main St, Springfield, IL 62704", "Apt 4B", "  123  Main   St  ",
    "reach me at +1 202 555 0143 or ada@example.com",
    # adversarial: prototype keys, quoting, and Unicode case mapping
    "__proto__", "constructor", "prototype", "toString", "\\", '"', "'",
    "a" * 300, EMOJI, E_PLUS_COMBINING_ACUTE, FULLWIDTH_AB,
    f"{DOTTED_CAPITAL_I}stanbul", TITLECASE_DZ, SHARP_S,
]
