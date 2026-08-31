"""Rolodexter — The universal contact field mapper.

This module is the public face of the implementation and re-exports the whole
surface, so ``from rolodexter.core import ...`` still reaches everything. The
parts live beside it: exceptions and models in ``_models``, value normalizers in
``_normalizers`` and ``_geo``, the pattern registry in ``_patterns``, the match
strategies in ``_strategies``, and the mapper's resolution half in ``_mapper``.
``ContactMapper`` and ``MappingSchema`` reference each other and so stay here
together.
"""
# pylint: disable=import-outside-toplevel  # optional-dep lazy imports are intentional

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from importlib import import_module
from typing import Any, ClassVar

from ._geo import (
    CountryNormalizer as CountryNormalizer,
)
from ._geo import (
    StateNormalizer as StateNormalizer,
)
from ._mapper import (
    _CACHE_MISS as _CACHE_MISS,
)
from ._mapper import (
    DEFAULT_HEADER_CACHE_MAX_SIZE as DEFAULT_HEADER_CACHE_MAX_SIZE,
)
from ._mapper import (
    EMBEDDED_PHONE_MAX_MATCHES_PER_FIELD as EMBEDDED_PHONE_MAX_MATCHES_PER_FIELD,
)
from ._mapper import (
    EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD as EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD,
)
from ._mapper import (
    EMBEDDED_PHONE_MAX_TEXT_CHARS as EMBEDDED_PHONE_MAX_TEXT_CHARS,
)
from ._mapper import (
    ContactMapper as ContactMapperBase,
)
from ._mapper import (
    _merge as _merge,
)

# Re-exported so ``rolodexter.core`` keeps the surface its callers and tests
# import. The redundant ``X as X`` form is the explicit re-export idiom: it
# marks these as deliberate rather than unused, so no linter can quietly
# delete one. A block-level ``noqa`` cannot do that - F401 is attributed to
# the NAME's own line - which is how _FIELD_NORMALIZERS briefly vanished
# from this module's surface and broke an import in the test suite.
from ._models import (
    CanonicalField as CanonicalField,
)
from ._models import (
    FieldMatch as FieldMatch,
)
from ._models import (
    MappingProfile as MappingProfile,
)
from ._models import (
    MappingResult as MappingResult,
)
from ._models import (
    MappingWarning as MappingWarning,
)
from ._models import (
    NormalizationError as NormalizationError,
)
from ._models import (
    PatternLoadError as PatternLoadError,
)
from ._models import (
    RolodexterError as RolodexterError,
)
from ._models import (
    WarningCategory as WarningCategory,
)
from ._models import (
    _validate_confidence_threshold as _validate_confidence_threshold,
)
from ._models import (
    _value_for_matching as _value_for_matching,
)
from ._models import (
    _warning_category as _warning_category,
)
from ._models import (
    logger as logger,
)
from ._normalizers import (
    _ADDRESS_FIELDS as _ADDRESS_FIELDS,
)
from ._normalizers import (
    _BOOLEAN_FIELDS as _BOOLEAN_FIELDS,
)
from ._normalizers import (
    _DATE_FIELDS as _DATE_FIELDS,
)
from ._normalizers import (
    _EMAIL_SHAPE_RE as _EMAIL_SHAPE_RE,
)
from ._normalizers import (
    _FIELD_NORMALIZERS as _FIELD_NORMALIZERS,
)
from ._normalizers import (
    _HEADER_CAMEL_RE as _HEADER_CAMEL_RE,
)
from ._normalizers import (
    _HEADER_NONWORD_RE as _HEADER_NONWORD_RE,
)
from ._normalizers import (
    _HEADER_UNDERSCORE_RUN_RE as _HEADER_UNDERSCORE_RUN_RE,
)
from ._normalizers import (
    _LIST_FIELDS as _LIST_FIELDS,
)
from ._normalizers import (
    _NAME_FIELDS as _NAME_FIELDS,
)
from ._normalizers import (
    _PHONE_FIELDS as _PHONE_FIELDS,
)
from ._normalizers import (
    _REFERENCE_SUFFIX_RE as _REFERENCE_SUFFIX_RE,
)
from ._normalizers import (
    _SOCIAL_FIELDS as _SOCIAL_FIELDS,
)
from ._normalizers import (
    AddressNormalizer as AddressNormalizer,
)
from ._normalizers import (
    BooleanNormalizer as BooleanNormalizer,
)
from ._normalizers import (
    DateNormalizer as DateNormalizer,
)
from ._normalizers import (
    EmailNormalizer as EmailNormalizer,
)
from ._normalizers import (
    ListNormalizer as ListNormalizer,
)
from ._normalizers import (
    NameNormalizer as NameNormalizer,
)
from ._normalizers import (
    PhoneNormalizer as PhoneNormalizer,
)
from ._normalizers import (
    PostalCodeNormalizer as PostalCodeNormalizer,
)
from ._normalizers import (
    StringNormalizer as StringNormalizer,
)
from ._normalizers import (
    _is_reference_header as _is_reference_header,
)
from ._normalizers import (
    _normalize_header as _normalize_header,
)
from ._normalizers import (
    normalize_value as normalize_value,
)
from ._normalizers import (
    value_warnings as value_warnings,
)
from ._patterns import (
    PatternRegistry as PatternRegistry,
)
from ._strategies import (
    _SOCIAL_URL_DEFS as _SOCIAL_URL_DEFS,
)
from ._strategies import (
    _VALUE_BEARING_FIELDS as _VALUE_BEARING_FIELDS,
)
from ._strategies import (
    EXACT_MATCH_CONFIDENCE as EXACT_MATCH_CONFIDENCE,
)
from ._strategies import (
    FUZZY_HIGH_CONFIDENCE as FUZZY_HIGH_CONFIDENCE,
)
from ._strategies import (
    FUZZY_LENGTH_RATIO as FUZZY_LENGTH_RATIO,
)
from ._strategies import (
    FUZZY_LOW_CONFIDENCE as FUZZY_LOW_CONFIDENCE,
)
from ._strategies import (
    FUZZY_MATCH_THRESHOLD as FUZZY_MATCH_THRESHOLD,
)
from ._strategies import (
    HEURISTIC_CONFIDENCE as HEURISTIC_CONFIDENCE,
)
from ._strategies import (
    NORMALIZED_MATCH_CONFIDENCE as NORMALIZED_MATCH_CONFIDENCE,
)
from ._strategies import (
    ExactMatchStrategy as ExactMatchStrategy,
)
from ._strategies import (
    FuzzyMatchStrategy as FuzzyMatchStrategy,
)
from ._strategies import (
    HeuristicMatchStrategy as HeuristicMatchStrategy,
)
from ._strategies import (
    MatchStrategy as MatchStrategy,
)
from ._strategies import (
    NormalizedMatchStrategy as NormalizedMatchStrategy,
)
from ._strategies import (
    _build_social_url_patterns as _build_social_url_patterns,
)
from ._text import (
    _ORDINAL_RE as _ORDINAL_RE,
)
from ._text import (
    _cap_part as _cap_part,
)
from ._text import (
    _smart_titlecase as _smart_titlecase,
)

__all__ = [
    "DEFAULT_HEADER_CACHE_MAX_SIZE",
    "EMBEDDED_PHONE_MAX_MATCHES_PER_FIELD",
    "EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD",
    "EMBEDDED_PHONE_MAX_TEXT_CHARS",
    "EXACT_MATCH_CONFIDENCE",
    "FUZZY_HIGH_CONFIDENCE",
    "FUZZY_LENGTH_RATIO",
    "FUZZY_LOW_CONFIDENCE",
    "FUZZY_MATCH_THRESHOLD",
    "HEURISTIC_CONFIDENCE",
    "NORMALIZED_MATCH_CONFIDENCE",
    "AddressNormalizer",
    "BooleanNormalizer",
    "CanonicalField",
    "ContactMapper",
    "CountryNormalizer",
    "DateNormalizer",
    "EmailNormalizer",
    "ExactMatchStrategy",
    "FieldMatch",
    "FuzzyMatchStrategy",
    "HeuristicMatchStrategy",
    "ListNormalizer",
    "MappingProfile",
    "MappingResult",
    "MappingSchema",
    "MappingWarning",
    "MatchStrategy",
    "NameNormalizer",
    "NormalizationError",
    "NormalizedMatchStrategy",
    "PatternLoadError",
    "PatternRegistry",
    "PhoneNormalizer",
    "PostalCodeNormalizer",
    "RolodexterError",
    "StateNormalizer",
    "StringNormalizer",
    "WarningCategory",
    "normalize_value",
    "value_warnings",
]


# ═══════════════════════════════════════════════════════════════════════
#  CONTACT MAPPER (ORCHESTRATOR)
# ═══════════════════════════════════════════════════════════════════════


class ContactMapper(ContactMapperBase):
    """The universal contact field mapper.

    Routes messy, inconsistent contact data to canonical field names
    using a multi-layer strategy pipeline:

    1. Generic exact match against the alias index
    2. Normalised match (CamelCase / dot-path / space → underscore / …)
    3. Fuzzy match for typos and variations (rapidfuzz)
    4. Heuristic match using data-shape regex patterns

    Steps 1-3 depend only on the header, so each unique header is resolved
    **once** and the verdict is cached for reuse across every row of a batch
    (see :meth:`map_batch`).  Step 4 depends on the cell value and runs per
    row.  This makes bulk ingestion of CSV/exports (where every row shares the
    same headers) scale with the number of *unique headers*, not rows.

    *default_region* (ISO 3166-1 alpha-2, e.g. ``"GB"``, ``"AU"``) sets the
    region used by value-shape phone detection and embedded-phone extraction.
    It defaults to ``"US"``; set it to match your data to avoid US-centric
    misparsing.  It can be overridden per call via ``map_payload`` /
    ``identify``.

    Thread-safety: a single ``ContactMapper`` may be shared across threads —
    ``map_payload``/``identify`` are read-only over the registry, and the
    internal header cache and fuzzy-alias cache are guarded for concurrent
    use.

    .. versionchanged:: 2.0.0
        Per-service profiles removed.  The ``default_service`` and
        ``service`` parameters are accepted but ignored.

    .. versionchanged:: 2.6.0
        Added *overrides* parameter for caller-supplied alias mappings
        (e.g. vendor-specific merge fields).

    .. versionchanged:: 2.7.0
        Header resolution is cached across rows; added *default_region*;
        construction loads i18n caches only (no network translation).

    .. versionchanged:: 2.8.0
        Added *strict* and *confidence_threshold*; non-fatal issues are
        reported on :attr:`MappingResult.warnings`.  Added :meth:`map_stream`
        (constant-memory iteration), :meth:`compile_schema` (reusable header
        plan), and :meth:`map_dataframe` (pandas).
    """

    __slots__ = (
        "_cacheable_pipeline",
        "_confidence_threshold",
        "_default_region",
        "_default_service",
        "_header_cache",
        "_header_cache_lock",
        "_header_cache_max_size",
        "_header_strategies",
        "_normalize",
        "_registry",
        "_strategies",
        "_strict",
        "_value_strategies",
    )

    def compile_schema(
        self,
        headers: Iterable[str],
        *,
        default_region: str | None = None,
        strict: bool | None = None,
        confidence_threshold: float | None = None,
    ) -> MappingSchema:
        """Resolve a fixed set of headers once into a reusable mapping plan.

        Returns a :class:`MappingSchema` capturing the header-only verdict for
        each header (exact / normalized / fuzzy).  This warms the mapper's
        per-header cache and exposes a ``column_map`` (header → canonical),
        which is exactly what column-oriented callers — DataFrame renames,
        SQL ``SELECT`` aliases — need.  Value-shape heuristics are inherently
        per-row and are *not* part of a static schema; use ``apply`` / the
        mapper for those.

        .. versionadded:: 2.8.0
        """
        region = default_region if default_region is not None else self._default_region
        threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else self._confidence_threshold
        )
        threshold = _validate_confidence_threshold(threshold)
        is_strict = self._strict if strict is None else strict
        matches: dict[str, FieldMatch] = {}
        warnings: list[str] = []
        for header in headers:
            key = str(header)
            if self._cacheable_pipeline:
                # value=None → only header-only strategies fire; also warms the
                # mapper's _header_cache for subsequent row mapping.
                match = self._resolve(key, None, region)
            else:
                match = self.identify(key, default_region=region)
            if match.is_matched and match.confidence < threshold:
                warnings.append(
                    MappingWarning(
                        f"{key!r}: dropped low-confidence match to "
                        f"{match.canonical!r} (confidence {match.confidence:.2f} "
                        f"< threshold {threshold:.2f})",
                        WarningCategory.LOW_CONFIDENCE,
                    )
                )
                match = self._unknown(key)
            matches[key] = match
        if warnings:
            for warning in warnings:
                logger.warning("%s", warning)
            if is_strict:
                raise NormalizationError("; ".join(warnings))
        return MappingSchema(matches=matches, mapper=self, default_region=region)

    def map_dataframe(
        self,
        df: Any,
        *,
        default_region: str | None = None,
        normalize: bool | None = None,
        strict: bool | None = None,
        confidence_threshold: float | None = None,
    ) -> Any:
        """Return a copy of *df* with columns renamed to canonical fields.

        Column headers are resolved via :meth:`compile_schema`; matched columns
        are renamed to their canonical name and (when *normalize* is on) their
        values are normalized.  Unmatched columns are left untouched, so no
        data is dropped.  If two source columns map to the same canonical
        field, the first keeps the canonical name and later ones get a
        ``<canonical>__N`` suffix (with a logged warning).

        Requires pandas (``pip install rolodexter[pandas]``).

        .. versionadded:: 2.8.0
        """
        try:
            import_module("pandas")
        except ImportError:
            raise ImportError(
                "map_dataframe requires pandas. Install with: "
                "pip install 'rolodexter[pandas]'"
            ) from None

        region = default_region if default_region is not None else self._default_region
        do_norm = self._normalize if normalize is None else normalize
        is_strict = self._strict if strict is None else strict
        threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else self._confidence_threshold
        )
        threshold = _validate_confidence_threshold(threshold)
        schema = self.compile_schema(
            [str(c) for c in df.columns],
            default_region=region,
            strict=is_strict,
            confidence_threshold=threshold,
        )

        columns = list(df.columns)
        if len(columns) != len(set(columns)):
            raise ValueError(
                "map_dataframe requires unique input column labels; duplicate "
                "labels cannot be renamed without ambiguity"
            )

        rename = self._build_rename_map(columns, schema)

        out = df.rename(columns=rename)
        warnings: list[str] = []
        if do_norm:
            warnings = self._normalize_dataframe_columns(out, rename, region)
        if warnings:
            for warning in warnings:
                logger.warning("%s", warning)
            if is_strict:
                raise NormalizationError("; ".join(warnings))
        return out

    @staticmethod
    def _build_rename_map(columns: list[Any], schema: MappingSchema) -> dict[Any, str]:
        """Canonical rename target for each matched column, ambiguity-resolved.

        Unmatched labels remain in the output. Reserve them before assigning
        canonical names so a generated ``<canonical>__N`` label cannot
        collide with an untouched source column and silently hide data. If
        two source columns map to the same canonical field, the first keeps
        the canonical name and later ones get a ``<canonical>__N`` suffix
        (with a logged warning).
        """
        rename: dict[Any, str] = {}
        used_names: set[Any] = {
            col
            for col in columns
            if (match := schema.matches.get(str(col))) is None or not match.is_matched
        }
        next_suffix: dict[str, int] = {}
        for col in columns:
            match = schema.matches.get(str(col))
            if match is None or not match.is_matched:
                continue
            canonical = match.canonical
            suffix = next_suffix.get(canonical, 1)
            new_name = canonical if suffix == 1 else f"{canonical}__{suffix}"
            while new_name in used_names:
                suffix += 1
                new_name = f"{canonical}__{suffix}"
            next_suffix[canonical] = suffix + 1
            used_names.add(new_name)
            if new_name != canonical:
                logger.warning(
                    "map_dataframe: column %r also maps to %r; renamed to %r "
                    "to avoid a collision",
                    col,
                    canonical,
                    new_name,
                )
            rename[col] = new_name
        return rename

    @staticmethod
    def _normalize_dataframe_columns(
        out: Any, rename: dict[Any, str], region: str | None
    ) -> list[str]:
        """Normalize each renamed column of `out` in place; return any value warnings."""
        warnings: list[str] = []
        for old_name, new_name in rename.items():
            canonical = new_name.split("__", 1)[0]
            out[new_name] = out[new_name].map(
                lambda v, c=canonical: normalize_value(c, v, default_region=region)
            )
            if canonical in _PHONE_FIELDS or canonical == "email":
                for final in out[new_name]:
                    warnings.extend(value_warnings(old_name, canonical, final))
        return warnings

    @property
    def registry(self) -> PatternRegistry:
        return self._registry

    def __repr__(self) -> str:
        return (
            f"ContactMapper(strategies={[s.name for s in self._strategies]}, "
            f"normalize={self._normalize})"
        )


@dataclass(frozen=True, slots=True)
class MappingSchema:
    """A reusable header→canonical plan produced by :meth:`ContactMapper.compile_schema`.

    Captures the header-only verdict for a fixed set of headers so column-
    oriented work (DataFrame renames, CSV header mapping) resolves each header
    exactly once.  Per-row value-shape heuristics are not part of the schema;
    :meth:`apply` delegates to the mapper for full per-row semantics.

    .. versionadded:: 2.8.0
    """

    matches: dict[str, FieldMatch]
    mapper: ContactMapper
    default_region: str | None = None

    def column_map(self) -> dict[str, str]:
        """Return ``{header: canonical}`` for the matched headers only."""
        return {h: m.canonical for h, m in self.matches.items() if m.is_matched}

    def unmatched_headers(self) -> list[str]:
        """Return the headers that did not resolve to a canonical field."""
        return [h for h, m in self.matches.items() if not m.is_matched]

    def apply(self, row: dict[str, Any], **kwargs: Any) -> MappingResult:
        """Map a single *row* using the mapper (header verdicts already cached).

        Extra keyword arguments are forwarded to
        :meth:`ContactMapper.map_payload`.
        """
        kwargs.setdefault("default_region", self.default_region)
        return self.mapper.map_payload(row, **kwargs)

    SCHEMA_VERSION: ClassVar[int] = 1

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping plan (a "mapping lockfile").

        Write this next to your import script and load it with
        :meth:`from_dict` to get byte-identical column routing on every later
        run — including after a ``patterns.json`` update or a rolodexter
        upgrade that would otherwise resolve a header differently.  The plan is
        plain JSON, so it can be reviewed in a pull request like any other
        configuration.

        .. versionadded:: 2.11.0
        """
        return {
            "schema_version": self.SCHEMA_VERSION,
            "default_region": self.default_region,
            "columns": {
                header: {
                    "canonical": match.canonical,
                    "confidence": match.confidence,
                    "strategy": match.strategy,
                    "service": match.service,
                }
                for header, match in self.matches.items()
            },
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        mapper: ContactMapper,
        *,
        default_region: str | None = None,
    ) -> MappingSchema:
        """Rebuild a plan saved by :meth:`to_dict` and bind it to *mapper*.

        The restored verdicts are seeded into *mapper*'s header cache, so
        subsequent :meth:`apply` / :meth:`ContactMapper.map_payload` calls route
        columns exactly as the saved plan says rather than re-resolving them.
        That is what makes an import reproducible: the plan wins over whatever
        the current alias table would decide today.

        Value-shape heuristics are per-row by nature and are not part of a
        saved plan, so a header the plan records as ``unknown`` can still be
        matched from its value at run time, exactly as
        :meth:`ContactMapper.compile_schema` documents.

        Raises :class:`PatternLoadError` if *data* is not a plan this version
        understands.

        .. versionadded:: 2.11.0
        """
        if not isinstance(data, dict):
            raise PatternLoadError("Invalid mapping schema: expected an object")
        version = data.get("schema_version")
        if version != cls.SCHEMA_VERSION:
            raise PatternLoadError(
                f"Unsupported mapping schema version {version!r}; "
                f"this rolodexter reads version {cls.SCHEMA_VERSION}"
            )
        columns = data.get("columns")
        if not isinstance(columns, dict):
            raise PatternLoadError(
                "Invalid mapping schema: 'columns' must be an object"
            )

        matches: dict[str, FieldMatch] = {}
        for header, entry in columns.items():
            if not isinstance(header, str) or not isinstance(entry, dict):
                raise PatternLoadError(
                    "Invalid mapping schema: each column must map a string header "
                    "to an object"
                )
            canonical = entry.get("canonical")
            strategy = entry.get("strategy", "schema")
            confidence = entry.get("confidence", EXACT_MATCH_CONFIDENCE)
            service = entry.get("service")
            if not isinstance(canonical, str) or not canonical.strip():
                raise PatternLoadError(
                    f"Invalid mapping schema: column {header!r} has no canonical field"
                )
            if not isinstance(strategy, str) or not isinstance(confidence, int | float):
                raise PatternLoadError(
                    f"Invalid mapping schema: column {header!r} has a malformed "
                    "strategy or confidence"
                )
            matches[header] = FieldMatch(
                original=header,
                canonical=canonical,
                confidence=float(confidence),
                strategy=strategy,
                service=service if isinstance(service, str) else None,
            )

        region = default_region
        if region is None:
            stored = data.get("default_region")
            region = stored if isinstance(stored, str) else None

        if not mapper.cache_info()["cacheable_pipeline"]:
            # A custom strategy order that interleaves value-dependent
            # strategies bypasses the header cache entirely, so a replayed plan
            # would be silently ignored.  Say so rather than pretend.
            logger.warning(
                "MappingSchema.from_dict: this mapper's strategy pipeline is not "
                "cacheable, so the saved plan cannot override live resolution; "
                "use column_map() explicitly instead"
            )
        mapper.seed_header_cache(matches)
        return cls(matches=matches, mapper=mapper, default_region=region)
