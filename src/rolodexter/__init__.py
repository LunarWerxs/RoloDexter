"""RoloDexter — The universal contact field mapper.

Map messy, inconsistent contact data from any source to a clean,
canonical schema.  Supports fuzzy matching, smart normalisation,
regex heuristics, and value normalization out of the box.

Quick start::

    from rolodexter import ContactMapper

    mapper = ContactMapper()
    result = mapper.map_payload({
        "fname": "Jane",
        "surname": "Doe",
        "mobile": "(202) 555-0143",
        "employer": "Tech Corp",
    })
    print(result.normalized)
    # {'first_name': 'Jane', 'last_name': 'Doe', 'phone': '+12025550143', 'company': 'Tech Corp'}
"""

from __future__ import annotations

from ._phone import (
    MatchType,
    NumberType,
    PhoneNumber,
    PhoneNumberMatch,
    PhoneNumberMatcher,
    format_e164,
    format_international,
    format_national,
    is_number_match,
    is_valid,
    number_type,
    parse,
)
from .core import (
    AddressNormalizer,
    BooleanNormalizer,
    CanonicalField,
    ContactMapper,
    EmailNormalizer,
    ExactMatchStrategy,
    FieldMatch,
    FuzzyMatchStrategy,
    HeuristicMatchStrategy,
    ListNormalizer,
    MappingResult,
    MappingSchema,
    MatchStrategy,
    NameNormalizer,
    NormalizationError,
    NormalizedMatchStrategy,
    PatternLoadError,
    PatternRegistry,
    PhoneNormalizer,
    PostalCodeNormalizer,
    RolodexterError,
    StringNormalizer,
    normalize_value,
)

# Single source of truth: read the installed package version rather than
# duplicating a literal that can drift from pyproject.toml.
try:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("rolodexter")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "0.0.0+unknown"


def __getattr__(name: str) -> object:
    if name in {"SUPPORTED_LANGUAGES", "generate_language"}:
        from . import i18n

        return getattr(i18n, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "SUPPORTED_LANGUAGES",
    "AddressNormalizer",
    "BooleanNormalizer",
    "CanonicalField",
    # Core
    "ContactMapper",
    "EmailNormalizer",
    "ExactMatchStrategy",
    # Models
    "FieldMatch",
    "FuzzyMatchStrategy",
    "HeuristicMatchStrategy",
    "ListNormalizer",
    "MappingResult",
    "MappingSchema",
    # Strategies
    "MatchStrategy",
    "MatchType",
    "NameNormalizer",
    "NormalizationError",
    "NormalizedMatchStrategy",
    "NumberType",
    "PatternLoadError",
    "PatternRegistry",
    # Normalizers
    "PhoneNormalizer",
    # Phone module
    "PhoneNumber",
    "PhoneNumberMatch",
    "PhoneNumberMatcher",
    "PostalCodeNormalizer",
    # Exceptions
    "RolodexterError",
    "StringNormalizer",
    "format_e164",
    "format_international",
    "format_national",
    "generate_language",
    "is_number_match",
    "is_valid",
    "normalize_value",
    "number_type",
    "parse",
]
