"""The header/value resolution half of :class:`~rolodexter.core.ContactMapper`.

Extracted verbatim from ``core.py``. What stayed behind is exactly the part that
touches :class:`MappingSchema`: ``compile_schema`` and the dataframe helpers.
``ContactMapper`` and ``MappingSchema`` reference each other, so they cannot be
separated - this splits the mapper along the one seam that is not part of that
cycle.
"""

from __future__ import annotations

import threading
from collections import Counter, OrderedDict
from collections.abc import Iterable, Iterator, Sequence
from typing import Any, cast

from ._models import (
    CanonicalField,
    FieldMatch,
    MappingProfile,
    MappingResult,
    MappingWarning,
    NormalizationError,
    WarningCategory,
    _validate_confidence_threshold,
    _value_for_matching,
    _warning_category,
    logger,
)
from ._normalizers import _LIST_FIELDS, _PHONE_FIELDS, normalize_value, value_warnings
from ._patterns import PatternRegistry
from ._strategies import (
    HEURISTIC_CONFIDENCE,
    ExactMatchStrategy,
    FuzzyMatchStrategy,
    HeuristicMatchStrategy,
    MatchStrategy,
    NormalizedMatchStrategy,
)

EMBEDDED_PHONE_MAX_TEXT_CHARS: int = 8192
EMBEDDED_PHONE_MAX_MATCHES_PER_FIELD: int = 5
EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD: int = 20
DEFAULT_HEADER_CACHE_MAX_SIZE: int = 4096

# Sentinel distinguishing "no cache entry" from a cached miss (``None``), so
# the header cache can be read without holding the lock across matching.
_CACHE_MISS: Any = object()


def _merge(target: dict[str, Any], key: str, value: Any) -> None:
    """Merge *value* into *target[key]*, promoting to list on collision.

    Duplicate values are dropped so the same normalized phone/email
    from multiple aliases (e.g. ``phone`` + ``mobile`` carrying the
    same number) appears only once.

    .. versionchanged:: 2.11.0
       Blank values (``None`` or whitespace-only) never join a collision: an
       export with two columns for one field and only one of them filled in
       yields the value, not ``["value", ""]``.
    """
    if key in _LIST_FIELDS:
        if key not in target:
            target[key] = list(value) if isinstance(value, list) else value
            return
        incoming = value if isinstance(value, list) else [value]
        existing = target[key] if isinstance(target[key], list) else [target[key]]
        merged = list(existing)
        for item in incoming:
            if item not in merged:
                merged.append(item)
        target[key] = merged
        return

    if key not in target:
        target[key] = value
        return
    # An empty cell carries no information, so it must not turn a good value
    # into a two-element list. This shows up whenever an export has two columns
    # meaning the same field and only one is filled in.
    if value is None or (isinstance(value, str) and not value.strip()):
        return
    existing = target[key]
    if existing is None or (isinstance(existing, str) and not existing.strip()):
        target[key] = value
        return
    if isinstance(existing, list):
        if value not in existing:
            existing.append(value)
    elif existing != value:
        target[key] = [existing, value]


class ContactMapper:
    """Construction, header resolution, payload/batch/stream mapping and profiling.

    Subclassed by :class:`rolodexter.core.ContactMapper`, which adds the
    ``MappingSchema`` half; never instantiated on its own.

    THE NAME IS LOAD-BEARING - do not rename it to ``...Base``. Python builds
    its argument-binding TypeErrors from the DEFINING class's ``__qualname__``,
    so a method that lives on ``ContactMapperBase`` reports
    ``ContactMapperBase.map_payload() missing 1 required positional argument``.
    ``scripts/parity_probe.py`` compares that text against the JavaScript port
    character for character, and four probes failed on exactly that when this
    class was first called ``ContactMapperBase``. Keeping the name keeps the
    qualnames - and the messages - identical to before the split.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        patterns: dict[str, Any] | None = None,
        patterns_path: str | None = None,
        default_service: str | None = None,
        normalize: bool = True,
        strategies: Sequence[MatchStrategy] | None = None,
        languages: str | Sequence[str] | None = None,
        overrides: dict[str, str] | None = None,
        default_region: str | None = "US",
        strict: bool = False,
        confidence_threshold: float = 0.0,
        header_cache_max_size: int | None = DEFAULT_HEADER_CACHE_MAX_SIZE,
    ) -> None:
        self._registry = PatternRegistry(
            patterns=patterns,
            patterns_path=patterns_path,
            languages=languages,
            overrides=overrides,
        )
        self._normalize = normalize
        self._default_region = default_region
        self._strict = strict
        self._confidence_threshold = _validate_confidence_threshold(
            confidence_threshold
        )
        if header_cache_max_size is not None and header_cache_max_size < 0:
            raise ValueError("header_cache_max_size must be non-negative or None")
        self._header_cache_max_size = header_cache_max_size
        self._default_service = (
            default_service  # accepted for backward compat; not used since v2.0
        )

        if strategies is not None:
            self._strategies = list(strategies)
        else:
            self._strategies = [
                ExactMatchStrategy(self._registry),
                NormalizedMatchStrategy(self._registry),
                FuzzyMatchStrategy(self._registry),
                HeuristicMatchStrategy(default_region=default_region),
            ]

        # ── Header-resolution cache (per unique header) ──────────────
        # Steps 1-3 are header_only=True (deterministic per header).  We can
        # split the pipeline and cache the header-only verdict ONLY when every
        # header-only strategy precedes every value-dependent one; otherwise a
        # value-dependent strategy could pre-empt a header-only match on some
        # rows and caching would change results.  Fall back to per-call
        # resolution for such custom pipelines.
        seen_value = False
        cacheable = True
        for strat in self._strategies:
            if strat.header_only:
                if seen_value:
                    cacheable = False
                    break
            else:
                seen_value = True
        self._cacheable_pipeline = cacheable
        self._header_strategies = [s for s in self._strategies if s.header_only]
        self._value_strategies = [s for s in self._strategies if not s.header_only]
        # header -> cached header-only verdict (None = all header-only missed)
        self._header_cache: OrderedDict[str, FieldMatch | None] = OrderedDict()
        self._header_cache_lock = threading.Lock()

    @staticmethod
    def _unknown(header: str) -> FieldMatch:
        return FieldMatch(
            original=header,
            canonical=CanonicalField.UNKNOWN.value,
            confidence=0.0,
            strategy="none",
        )

    def identify(  # pylint: disable=unused-argument
        self,
        header: str,
        *,
        value: str | None = None,
        service: str | None = None,
        default_region: str | None = None,
    ) -> FieldMatch:
        """Resolve a single header to its canonical field.

        The *service* parameter is accepted for backward compatibility
        but is ignored since v2.0.  *default_region* overrides the mapper's
        region for value-shape phone detection on this call only.
        """
        region = default_region if default_region is not None else self._default_region
        for strategy in self._strategies:
            result = strategy.match(header, value=value, default_region=region)
            if result is not None:
                return result
        return self._unknown(header)

    def _resolve(self, header: str, value: Any, region: str | None) -> FieldMatch:
        """Resolve a header, caching the deterministic header-only verdict.

        For a cache-friendly pipeline, header-only strategies (exact /
        normalized / fuzzy) are run at most once per unique header; only the
        value-dependent strategies (heuristic) run per call.  This is what
        makes :meth:`map_batch` scale to large, repetitive exports.
        """
        if not self._cacheable_pipeline:
            return self.identify(
                header, value=_value_for_matching(value), default_region=region
            )

        # Hold the lock only around the cache read and the cache write — never
        # across the strategy chain, which includes rapidfuzz scoring over the
        # whole alias length band.  The class docstring invites callers to
        # share one mapper across threads, and holding the lock through
        # matching serialized exactly that case.  Two threads racing the same
        # cold header may each compute the verdict; that is harmless, because
        # header-only strategies are deterministic per header.
        with self._header_cache_lock:
            cached = self._header_cache.get(header, _CACHE_MISS)
            if cached is not _CACHE_MISS:
                self._header_cache.move_to_end(header)

        if cached is not _CACHE_MISS:
            verdict = cast("FieldMatch | None", cached)
        else:
            verdict = None
            for strategy in self._header_strategies:
                result = strategy.match(header, value=None, default_region=region)
                if result is not None:
                    verdict = result
                    break
            if self._header_cache_max_size != 0:
                with self._header_cache_lock:
                    self._header_cache[header] = verdict
                    self._header_cache.move_to_end(header)
                    if self._header_cache_max_size is not None:
                        while len(self._header_cache) > self._header_cache_max_size:
                            self._header_cache.popitem(last=False)

        if verdict is not None:
            return verdict

        # Header-only strategies missed — the value-dependent ones may still
        # match, and their result can differ per row, so never cache them.
        match_value = _value_for_matching(value)
        for strategy in self._value_strategies:
            result = strategy.match(header, value=match_value, default_region=region)
            if result is not None:
                return result
        return self._unknown(header)

    def seed_header_cache(self, matches: dict[str, FieldMatch]) -> None:
        """Pre-load header verdicts so they win over live resolution.

        Used by :meth:`MappingSchema.from_dict` to replay a saved mapping plan.
        A seeded header resolves to the supplied :class:`FieldMatch` instead of
        being re-derived from the alias table, which is what makes an import
        reproducible across a ``patterns.json`` change.

        Entries whose canonical field is ``unknown`` are skipped rather than
        cached as a miss, so a column the plan could not resolve statically can
        still be matched from its value by the per-row heuristics.

        .. versionadded:: 2.11.0
        """
        with self._header_cache_lock:
            for header, match in matches.items():
                if match.canonical == CanonicalField.UNKNOWN.value:
                    continue
                self._header_cache[header] = match
                self._header_cache.move_to_end(header)
            if self._header_cache_max_size is not None:
                while len(self._header_cache) > self._header_cache_max_size:
                    self._header_cache.popitem(last=False)

    def clear_cache(self) -> None:
        """Clear cached header-resolution verdicts.

        Long-lived mapper instances can call this after processing a tenant or
        import job to release header cache memory without rebuilding the mapper.
        """
        with self._header_cache_lock:
            self._header_cache.clear()

    def cache_info(self) -> dict[str, Any]:
        """Return lightweight header-cache diagnostics."""
        with self._header_cache_lock:
            return {
                "size": len(self._header_cache),
                "max_size": self._header_cache_max_size,
                "cacheable_pipeline": self._cacheable_pipeline,
            }

    def map_payload(  # pylint: disable=unused-argument,too-many-locals,too-many-branches
        self,
        payload: dict[str, Any],
        *,
        service: str | None = None,
        depth: int = 1,
        extract_embedded_phones: bool = False,
        default_region: str | None = None,
        strict: bool | None = None,
        confidence_threshold: float | None = None,
        normalize: bool | None = None,
    ) -> MappingResult:
        """Normalize an entire contact data dictionary.

        Parameters
        ----------
        payload : dict
            Raw contact data to normalize.
        service : str, optional
            Accepted for backward compatibility; ignored since v2.0.
        depth : int, default 1
            Recursion depth for nested payloads.  ``1`` (default) processes
            only the top-level keys.  ``2`` also recurses one level into
            nested dicts.  Maximum supported value is ``5``.
        extract_embedded_phones : bool, default False
            When ``True``, scan all non-phone string values for embedded
            phone numbers (e.g. ``"reach me at +1-555-123-4567"``) using
            :class:`PhoneNumberMatcher` and merge any found numbers into
            the ``phone`` field of the result.

            .. versionadded:: 2.6.0
        default_region : str, optional
            Overrides the mapper's region for value-shape phone detection and
            embedded-phone extraction on this call only.  Falls back to the
            region given at construction (``"US"`` by default).

            .. versionadded:: 2.7.0
        strict : bool, optional
            Overrides the mapper's ``strict`` setting for this call.  When
            truthy, any non-fatal issue (a phone that could not be normalized
            to E.164, or a match dropped by *confidence_threshold*) raises
            :class:`NormalizationError` instead of being recorded on
            :attr:`MappingResult.warnings`.

            .. versionadded:: 2.8.0
        confidence_threshold : float, optional
            Overrides the mapper's threshold for this call.  Matches whose
            confidence is below the threshold are dropped to ``unmapped`` and
            recorded as a warning.  Defaults to ``0.0`` (keep everything).

            .. versionadded:: 2.8.0

        Returns
        -------
        MappingResult
        """
        depth = max(1, min(depth, 5))
        flat = self._flatten(payload, depth) if depth > 1 else payload
        region = default_region if default_region is not None else self._default_region
        threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else self._confidence_threshold
        )
        threshold = _validate_confidence_threshold(threshold)
        is_strict = self._strict if strict is None else strict
        do_normalize = self._normalize if normalize is None else normalize

        normalized: dict[str, Any] = {}
        unmapped: dict[str, Any] = {}
        matches: list[FieldMatch] = []
        warnings: list[str] = []

        for key, value in flat.items():
            match = self._resolve(key, value, region)

            # Drop matches below the confidence floor (recorded, not silent).
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

            matches.append(match)

            if match.is_matched:
                if do_normalize:
                    final = normalize_value(
                        match.canonical, value, default_region=region
                    )
                    # Surface silent degradation: a phone that didn't reach
                    # E.164, or an "email" that isn't shaped like one.
                    warnings.extend(value_warnings(key, match.canonical, final))
                else:
                    final = value
                _merge(normalized, match.canonical, final)
            else:
                unmapped[key] = value

        # ── Embedded phone extraction (opt-in) ─────────────────────
        if extract_embedded_phones:
            self._extract_embedded_phones(
                normalized, unmapped, matches, warnings, region
            )

        if warnings:
            for w in warnings:
                logger.warning("%s", w)
            if is_strict:
                raise NormalizationError("; ".join(warnings))

        return MappingResult(
            normalized=normalized,
            unmapped=unmapped,
            field_matches=tuple(matches),
            warnings=tuple(warnings),
        )

    @staticmethod
    def _extract_embedded_phones(
        normalized: dict[str, Any],
        unmapped: dict[str, Any],
        matches: list[FieldMatch],
        warnings: list[str],
        default_region: str | None = None,
    ) -> None:
        """Scan non-phone string values for embedded phone numbers.

        Found numbers are merged into ``normalized["phone"]`` and
        recorded in *matches* with ``strategy="embedded_phone"``.  Scans are
        bounded by text length and match-count caps so an overlong notes field
        cannot monopolize CPU/memory; any truncation is reported in *warnings*.

        .. versionadded:: 2.6.0
        .. versionchanged:: 2.7.0 Honours *default_region*.
        """
        from . import _phone

        def candidates() -> Iterator[tuple[str, str]]:
            for key, val in unmapped.items():
                if isinstance(val, str) and len(val) > 6:
                    yield key, val
            for key, val in tuple(normalized.items()):
                if key not in _PHONE_FIELDS and isinstance(val, str) and len(val) > 6:
                    yield key, val

        found_total = 0
        warned_payload_limit = False

        def warn_payload_limit() -> None:
            """Report the payload cap once, whichever site reaches it first.

            The cap is reached from two directions - a field that overflows it,
            or a later candidate that finds it already spent - so both sites go
            through one emitter.
            """
            nonlocal warned_payload_limit
            if warned_payload_limit:
                return
            warnings.append(
                MappingWarning(
                    "embedded phone extraction stopped after "
                    f"{EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD} matches "
                    "for this payload",
                    WarningCategory.EMBEDDED_PHONE_LIMIT,
                )
            )
            warned_payload_limit = True

        for key, text in candidates():
            if found_total >= EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD:
                warn_payload_limit()
                break

            scan_text = text
            if len(scan_text) > EMBEDDED_PHONE_MAX_TEXT_CHARS:
                warnings.append(
                    MappingWarning(
                        f"{key!r}: embedded phone scan truncated at "
                        f"{EMBEDDED_PHONE_MAX_TEXT_CHARS} characters",
                        WarningCategory.EMBEDDED_PHONE_LIMIT,
                    )
                )
                scan_text = scan_text[:EMBEDDED_PHONE_MAX_TEXT_CHARS]

            remaining_payload = EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD - found_total
            field_limit = min(
                EMBEDDED_PHONE_MAX_MATCHES_PER_FIELD,
                remaining_payload,
            )
            overflow_for_field = False
            for found_for_field, pm in enumerate(
                _phone.PhoneNumberMatcher(
                    scan_text,
                    default_region=default_region,
                    max_matches=field_limit + 1,
                )
            ):
                if found_for_field >= field_limit:
                    overflow_for_field = True
                    break
                e164 = pm.number.e164
                _merge(normalized, "phone", e164)
                matches.append(
                    FieldMatch(
                        original=key,
                        canonical="phone",
                        confidence=HEURISTIC_CONFIDENCE,
                        strategy="embedded_phone",
                    )
                )
                found_total += 1

            if overflow_for_field:
                if field_limit == EMBEDDED_PHONE_MAX_MATCHES_PER_FIELD:
                    warnings.append(
                        MappingWarning(
                            f"{key!r}: embedded phone extraction stopped after "
                            f"{EMBEDDED_PHONE_MAX_MATCHES_PER_FIELD} matches "
                            "for this field",
                            WarningCategory.EMBEDDED_PHONE_LIMIT,
                        )
                    )
                if found_total >= EMBEDDED_PHONE_MAX_MATCHES_PER_PAYLOAD:
                    warn_payload_limit()

    @staticmethod
    def _flatten(
        payload: dict[str, Any],
        depth: int,
        _prefix: str = "",
        _current: int = 1,
    ) -> dict[str, Any]:
        """Recursively flatten nested dicts up to *depth* levels.

        Nested keys are joined with ``.`` (dot).  Non-dict values and
        dicts beyond the depth limit are preserved as-is.  The dot
        separator is consumed by :class:`NormalizedMatchStrategy`'s
        dot-path resolution.
        """
        result: dict[str, Any] = {}
        for key, value in payload.items():
            full_key = f"{_prefix}{key}" if _prefix else key
            if isinstance(value, dict) and _current < depth:
                result.update(
                    ContactMapper._flatten(value, depth, f"{full_key}.", _current + 1)
                )
            else:
                result[full_key] = value
        return result

    def map_batch(  # pylint: disable=unused-argument
        self,
        payloads: Sequence[dict[str, Any]],
        *,
        service: str | None = None,
        depth: int = 1,
        default_region: str | None = None,
        extract_embedded_phones: bool = False,
        strict: bool | None = None,
        confidence_threshold: float | None = None,
        normalize: bool | None = None,
    ) -> list[MappingResult]:
        """Process multiple payloads, materializing all results into a list.

        Header resolution is cached on the mapper, so payloads that share the
        same headers (the typical CSV/export case) resolve each unique header
        only once across the whole batch rather than once per row.

        For very large inputs prefer :meth:`map_stream`, which yields results
        lazily and keeps memory constant.
        """
        return list(
            self.map_stream(
                payloads,
                depth=depth,
                default_region=default_region,
                extract_embedded_phones=extract_embedded_phones,
                strict=strict,
                confidence_threshold=confidence_threshold,
                normalize=normalize,
            )
        )

    def map_stream(
        self,
        payloads: Iterable[dict[str, Any]],
        *,
        depth: int = 1,
        default_region: str | None = None,
        extract_embedded_phones: bool = False,
        strict: bool | None = None,
        confidence_threshold: float | None = None,
        normalize: bool | None = None,
    ) -> Iterator[MappingResult]:
        """Lazily map an iterable of payloads, yielding one result at a time.

        Unlike :meth:`map_batch`, this never holds more than one result in
        memory, so it scales to million-row CSV/JSONL streams.  Header
        resolution is still cached across rows.

        Example::

            import csv
            with open("contacts.csv") as fh:
                for result in mapper.map_stream(csv.DictReader(fh)):
                    write(result.normalized)

        .. versionadded:: 2.8.0
        """
        for payload in payloads:
            yield self.map_payload(
                payload,
                depth=depth,
                default_region=default_region,
                extract_embedded_phones=extract_embedded_phones,
                strict=strict,
                confidence_threshold=confidence_threshold,
                normalize=normalize,
            )

    def profile(
        self,
        payloads: Iterable[dict[str, Any]],
        *,
        max_rows: int | None = None,
        depth: int = 1,
        default_region: str | None = None,
        extract_embedded_phones: bool = False,
        strict: bool | None = None,
        confidence_threshold: float | None = None,
        normalize: bool | None = None,
    ) -> MappingProfile:
        """Summarize mapping quality across a batch or stream.

        The profiler keeps counters rather than materializing mapped rows, so
        memory use stays bounded for large imports. ``max_rows`` can limit a
        preview without consuming an additional item from an input iterator.
        Existing mapping semantics and options are reused unchanged.

        *normalize* overrides value normalization for the profiling run only.
        Profiling reads nothing but ``field_matches`` and ``warnings``, so
        passing ``normalize=False`` skips all phone/name parsing and makes a
        pre-flight scan of a large export several times faster — at the cost
        of the value-level warning counts (``phone_normalization``,
        ``email_validation``), which can only be produced by normalizing.
        Left at ``None`` the mapper's own setting applies, so counts stay
        complete by default.

        .. versionchanged:: 2.11.0
           Added *normalize*.
        """
        if max_rows is not None:
            if not isinstance(max_rows, int) or isinstance(max_rows, bool):
                raise TypeError("max_rows must be an integer or None")
            if max_rows < 0:
                raise ValueError("max_rows must be non-negative or None")

        canonical_counts: Counter[str] = Counter()
        unmapped_counts: Counter[str] = Counter()
        strategy_counts: Counter[str] = Counter()
        warning_counts: Counter[str] = Counter()
        rows_seen = 0
        matched_count = 0
        unmatched_count = 0
        iterator = iter(payloads)

        while max_rows is None or rows_seen < max_rows:
            try:
                payload = next(iterator)
            except StopIteration:
                break
            result = self.map_payload(
                payload,
                depth=depth,
                default_region=default_region,
                extract_embedded_phones=extract_embedded_phones,
                strict=strict,
                confidence_threshold=confidence_threshold,
                normalize=normalize,
            )
            rows_seen += 1
            for match in result.field_matches:
                strategy_counts[match.strategy] += 1
                if match.is_matched:
                    matched_count += 1
                    canonical_counts[match.canonical] += 1
                else:
                    unmatched_count += 1
                    unmapped_counts[match.original] += 1
            for warning in result.warnings:
                warning_counts[_warning_category(warning)] += 1

        return MappingProfile(
            rows_seen=rows_seen,
            fields_seen=matched_count + unmatched_count,
            matched_count=matched_count,
            unmatched_count=unmatched_count,
            canonical_counts=dict(canonical_counts),
            unmapped_counts=dict(unmapped_counts),
            strategy_counts=dict(strategy_counts),
            warning_counts=dict(warning_counts),
        )
