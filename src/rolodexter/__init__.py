"""Rolodexter — The universal contact field mapper.

Map messy, inconsistent contact data from any source to a clean,
canonical schema.  Supports fuzzy matching, smart normalisation,
regex heuristics, and value normalization out of the box.

Quick start::

    from rolodexter import ContactMapper

    mapper = ContactMapper()
    result = mapper.map_payload({
        "fname": "Jane",
        "surname": "Doe",
        "mobile": "555-0199",
        "employer": "Tech Corp",
    })
    print(result.normalized)
    # {'first_name': 'Jane', 'last_name': 'Doe', 'phone': '5550199', 'company': 'Tech Corp'}
"""

from __future__ import annotations

from .core import (
    AddressNormalizer,
    CanonicalField,
    ContactMapper,
    EmailNormalizer,
    ExactMatchStrategy,
    FieldMatch,
    FuzzyMatchStrategy,
    HeuristicMatchStrategy,
    MappingResult,
    MatchStrategy,
    NameNormalizer,
    NormalizationError,
    NormalizedMatchStrategy,
    PatternLoadError,
    PatternRegistry,
    PhoneNormalizer,
    RolodexterError,
    ServiceMatchStrategy,
    ServiceNotFoundError,
    StrategyError,
    StringNormalizer,
    normalize_value,
)

__version__ = "2.1.0"

__all__ = [
    "AddressNormalizer",
    "CanonicalField",
    # Core
    "ContactMapper",
    "EmailNormalizer",
    "ExactMatchStrategy",
    # Models
    "FieldMatch",
    "FuzzyMatchStrategy",
    "HeuristicMatchStrategy",
    "MappingResult",
    # Strategies
    "MatchStrategy",
    "NameNormalizer",
    "NormalizationError",
    "NormalizedMatchStrategy",
    "PatternLoadError",
    "PatternRegistry",
    # Normalizers
    "PhoneNormalizer",
    # Exceptions
    "RolodexterError",
    "ServiceMatchStrategy",
    "ServiceNotFoundError",
    "StrategyError",
    "StringNormalizer",
    "normalize_value",
]
