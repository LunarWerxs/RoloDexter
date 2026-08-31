"""The pattern registry: loading, indexing and querying patterns.json.

Extracted verbatim from ``core.py``, which re-imports every name here so
``rolodexter.core`` keeps the whole surface its callers and tests import.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from importlib import resources
from typing import Any, cast

from ._models import PatternLoadError, logger

# ═══════════════════════════════════════════════════════════════════════
#  PATTERN REGISTRY
# ═══════════════════════════════════════════════════════════════════════


class PatternRegistry:
    """Immutable index over the master ``patterns.json`` truth table.

    The optional *languages* parameter controls which i18n language
    aliases are merged into the alias index:

    * ``None`` or ``[]`` (default) — **English only**, no i18n.
    * ``"all"`` — every supported language that has a **cached** alias file.
    * ``["es", "fr"]`` — only the listed language codes, loaded from cache.

    Construction **only loads pre-generated cache files** — it never calls
    out to a translation service.  This keeps object construction fast,
    offline, and free of unbounded network latency.  Languages that have no
    cached file are skipped (with a logged warning); generate them ahead of
    time with the explicit, offline step::

        python -m rolodexter.i18n --languages es,fr   # or i18n.generate_language(...)
    """

    __slots__ = (
        "_alias_set",
        "_all_aliases",
        "_canonical_fields",
        "_data",
        "_languages",
        "_loaded_languages",
        "_reverse_index",
    )

    def __init__(
        self,
        patterns: dict[str, Any] | None = None,
        patterns_path: str | None = None,
        languages: str | Sequence[str] | None = None,
        overrides: dict[str, str] | None = None,
    ) -> None:
        if patterns is not None:
            self._data = self._validate_data(patterns, source="custom patterns")
        elif patterns_path is not None:
            self._data = self._load_from_path(patterns_path)
        else:
            self._data = self._load_default()

        self._languages = languages
        self._reverse_index: dict[str, str] = {}
        self._all_aliases: list[str] = []
        self._alias_set: set[str] = set()
        self._canonical_fields: list[str] = []
        self._loaded_languages: list[str] = []
        self._build_indexes()

        # ── Caller overrides (after base indexes) ─────────────────
        self._apply_overrides(overrides)

    @staticmethod
    def _load_from_path(path: str) -> dict[str, Any]:
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
            raise PatternLoadError(
                f"Failed to load patterns from {path}: {exc}"
            ) from exc
        return PatternRegistry._validate_data(data, source=f"patterns file {path!r}")

    @staticmethod
    def _load_default() -> dict[str, Any]:
        try:
            pkg = resources.files("rolodexter")
            text = pkg.joinpath("patterns.json").read_text(encoding="utf-8")
            data = json.loads(text)
        except Exception as exc:
            raise PatternLoadError(f"Failed to load bundled patterns: {exc}") from exc
        return PatternRegistry._validate_data(data, source="bundled patterns")

    @staticmethod
    def _validate_data(data: Any, *, source: str) -> dict[str, Any]:
        """Validate a pattern registry before building indexes from it.

        Custom registries are part of the public API, so malformed data should
        fail once with an actionable :class:`PatternLoadError` instead of
        leaking an ``AttributeError`` midway through index construction (or,
        worse, treating a string as a sequence of one-character aliases).
        """

        def fail(detail: str) -> None:
            raise PatternLoadError(f"Invalid {source}: {detail}")

        def string_list(value: Any, name: str) -> None:
            if not isinstance(value, list) or any(
                not isinstance(item, str) or not item.strip() for item in value
            ):
                fail(f"{name} must be a list of non-empty strings")

        if not isinstance(data, dict):
            fail("top level must be an object")

        if "version" in data and not isinstance(data["version"], str):
            fail("'version' must be a string")

        fields = data.get("fields", {})
        if not isinstance(fields, dict):
            fail("'fields' must be an object")
        for canonical, aliases in fields.items():
            if not isinstance(canonical, str) or not canonical.strip():
                fail("field names must be non-empty strings")
            string_list(aliases, f"aliases for field {canonical!r}")

        expansion = data.get("expansion")
        if expansion is not None:
            if not isinstance(expansion, dict):
                fail("'expansion' must be an object")
            for key in ("form_prefixes", "social_suffixes", "social_fields"):
                if key in expansion:
                    string_list(expansion[key], f"'expansion.{key}'")
            if "form_fields" in expansion:
                form_fields = expansion["form_fields"]
                if not isinstance(form_fields, dict) or any(
                    not isinstance(key, str)
                    or not key.strip()
                    or not isinstance(value, str)
                    or not value.strip()
                    for key, value in (
                        form_fields.items() if isinstance(form_fields, dict) else ()
                    )
                ):
                    fail(
                        "'expansion.form_fields' must be an object of "
                        "non-empty string keys and values"
                    )

        return cast(dict[str, Any], data)

    def _add_alias(self, key: str, canonical: str) -> None:
        """Register *key* → *canonical* (first-write-wins on reverse_index)
        and append to ``_all_aliases`` only on first sight."""
        if key not in self._reverse_index:
            self._reverse_index[key] = canonical
        if key not in self._alias_set:
            self._alias_set.add(key)
            self._all_aliases.append(key)

    def _build_indexes(self) -> None:  # pylint: disable=too-many-branches
        fields: dict[str, list[str]] = self._data.get("fields", {})
        for canonical, aliases in fields.items():
            self._canonical_fields.append(canonical)
            for alias in aliases:
                self._add_alias(alias.lower().strip(), canonical)

        # ── expansion rules (programmatic alias generation) ─────────
        self._apply_expansion_rules()

        # ── i18n layer (cached files only — never translates over the
        #    network from inside the constructor) ─────────────────────
        from .i18n import SUPPORTED_LANGUAGES, load_cached, normalize_language_code

        if self._languages == "all":
            lang_codes = sorted(SUPPORTED_LANGUAGES.keys())
        elif self._languages:
            lang_codes = (
                list(self._languages)
                if not isinstance(self._languages, str)
                else [self._languages]
            )
        else:
            lang_codes = []

        missing: list[str] = []
        unknown: list[str] = []
        for requested in lang_codes:
            # Case-fold and validate before anything touches the filesystem.
            # A caller-supplied code that is not a supported language is a
            # user error worth reporting, not a path to resolve.
            lang = normalize_language_code(requested)
            if lang is None:
                unknown.append(str(requested))
                continue

            lang_data = load_cached(lang)
            if lang_data is None:
                # Deliberately do NOT translate here: that would issue
                # blocking network calls (with unbounded latency and silent
                # rate-limit failures) from inside object construction.
                # Generation is an explicit, offline step — see the class
                # docstring.
                missing.append(lang)
                continue

            self._loaded_languages.append(lang)
            for canonical, aliases in lang_data.get("fields", {}).items():
                for alias in aliases:
                    self._add_alias(alias.lower().strip(), canonical)

        if missing:
            logger.warning(
                "No cached i18n aliases for %s — these languages were NOT "
                "loaded. Generate them first (offline) with: "
                "python -m rolodexter.i18n --languages %s",
                ", ".join(missing),
                ",".join(missing),
            )
        if unknown:
            # Previously silent: a typo or a wrong-case code ("ES") produced
            # English-only aliases with no explanation of why the caller's
            # localized headers stopped matching.
            logger.warning(
                "Unsupported i18n language code(s) %s — ignored. Supported codes: %s",
                ", ".join(repr(code) for code in unknown),
                ", ".join(sorted(SUPPORTED_LANGUAGES)),
            )

    def _apply_overrides(self, overrides: dict[str, str] | None) -> None:
        """Apply caller-supplied alias overrides with highest priority.

        Use this for vendor-specific field names that rolodexter can't
        know generically (e.g. Mailchimp per-account MMERGE fields)::

            registry = PatternRegistry(overrides={
                "MMERGE3": "full_address",
                "MMERGE6": "company",
            })

        Override entries **replace** any existing mapping for the same
        alias, so callers can correct or extend the alias index at
        construction time.

        .. versionadded:: 2.6.0
        """
        if not overrides:
            return
        if not isinstance(overrides, dict):
            raise PatternLoadError("Invalid overrides: expected an object")
        for alias, canonical in overrides.items():
            if (
                not isinstance(alias, str)
                or not alias.strip()
                or not isinstance(canonical, str)
                or not canonical.strip()
            ):
                raise PatternLoadError(
                    "Invalid overrides: aliases and canonical fields must be "
                    "non-empty strings"
                )
            key = alias.lower().strip()
            self._reverse_index[key] = canonical  # highest priority
            if key not in self._alias_set:
                self._alias_set.add(key)
                self._all_aliases.append(key)

    def _apply_expansion_rules(self) -> None:
        """Expand compact ``expansion`` rules in patterns.json into aliases.

        This eliminates hundreds of hand-written prefix/suffix permutations
        (``billing_email``, ``shipping_city``, ``twitter_url``, …) by
        generating them from concise rule tables at load time.
        """
        expansion = self._data.get("expansion")
        if not expansion:
            return

        def _register(alias: str, canonical: str) -> None:
            self._add_alias(alias.lower().strip(), canonical)

        # ── form prefixes (billing_, shipping_, your_, …) ──────────
        form_prefixes: list[str] = expansion.get("form_prefixes", [])
        form_fields: dict[str, str] = expansion.get("form_fields", {})
        for prefix in form_prefixes:
            for suffix, canonical in form_fields.items():
                _register(f"{prefix}{suffix}", canonical)

        # ── social suffixes (_url, _handle, _profile, …) ───────────
        social_suffixes: list[str] = expansion.get("social_suffixes", [])
        social_fields: list[str] = expansion.get("social_fields", [])
        for platform in social_fields:
            for suffix in social_suffixes:
                _register(f"{platform}{suffix}", platform)

    def exact_lookup(self, header: str) -> str | None:
        return self._reverse_index.get(header.lower().strip())

    def _expansion_form_prefixes(self) -> tuple[str, ...]:
        """Return ``expansion.form_prefixes`` from the loaded patterns data.

        Internal accessor so strategies that need the raw prefix list (e.g.
        address-prefix stripping) read the same truth table the alias
        expansion engine already loads, instead of hand-duplicating it.
        """
        expansion = self._data.get("expansion") or {}
        return tuple(expansion.get("form_prefixes", []))

    @property
    def all_aliases(self) -> list[str]:
        return list(self._all_aliases)

    @property
    def canonical_fields(self) -> list[str]:
        return list(self._canonical_fields)

    @property
    def loaded_languages(self) -> list[str]:
        """Language codes whose i18n aliases were loaded."""
        return list(self._loaded_languages)

    @property
    def available_languages(self) -> list[str]:
        """All supported language codes (whether cached or not)."""
        from .i18n import SUPPORTED_LANGUAGES

        return sorted(SUPPORTED_LANGUAGES.keys())

    @property
    def cached_languages(self) -> list[str]:
        """Language codes that have cached i18n files ready to use."""
        from .i18n import discover_cached

        return sorted(discover_cached().keys())

    @property
    def version(self) -> str:
        return str(self._data.get("version", "0.0.0"))

    def __repr__(self) -> str:
        return (
            f"PatternRegistry(aliases={len(self._reverse_index)}, "
            f"languages={self._loaded_languages}, "
            f"version={self.version!r})"
        )
