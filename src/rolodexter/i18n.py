"""On-demand i18n alias generator for rolodexter.

English aliases ship out of the box.  When a user requests any other
language the generator translates canonical field names via
``deep-translator`` (Google Translate) and caches the result as a
JSON file so it only needs to happen once.

Generated files are written to the platform user cache directory
(``~/.cache/rolodexter/i18n/`` on Linux, ``%LOCALAPPDATA%\\rolodexter\\i18n\\``
on Windows). Packaged ``rolodexter/i18n/*.json`` files, if a future release
ships curated packs, are read-only inputs and are never used for generated
cache writes.

Usage from code
───────────────
::

    from rolodexter.i18n import generate_language, SUPPORTED_LANGUAGES

    # Generate Spanish aliases once (cached for future use). This makes a
    # network call to the translation service, so do it as an explicit,
    # offline build step — never on a request path.
    data = generate_language("es")

    # ContactMapper / PatternRegistry only *load* cached aliases at
    # construction; they never translate over the network themselves.
    from rolodexter import ContactMapper
    mapper = ContactMapper(languages=["es"])  # loads the cache generated above

CLI
───
::

    python -m rolodexter.i18n                        # generate all supported
    python -m rolodexter.i18n --languages es,fr      # specific languages
    python -m rolodexter.i18n --force                # re-translate everything
    python -m rolodexter.i18n --dry-run              # preview only
"""
# pylint: disable=import-outside-toplevel  # optional-dep lazy imports are intentional

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import tempfile
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import suppress
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any, TypeVar, cast

DEFAULT_TRANSLATE_TIMEOUT: float = 10.0
DEFAULT_TRANSLATE_RETRIES: int = 1
DEFAULT_TRANSLATE_RETRY_BACKOFF: float = 0.5
MAX_I18N_WORKERS: int = 8
_T = TypeVar("_T")

__all__ = [
    "DEFAULT_TRANSLATE_RETRIES",
    "DEFAULT_TRANSLATE_RETRY_BACKOFF",
    "DEFAULT_TRANSLATE_TIMEOUT",
    "MAX_I18N_WORKERS",
    "SUPPORTED_LANGUAGES",
    "discover_cached",
    "generate_language",
    "get_all_cache_dirs",
    "get_cache_dir",
    "get_writable_cache_dir",
    "load_cached",
    "main",
]

# ═══════════════════════════════════════════════════════════════════════
#  SUPPORTED LANGUAGES
# ═══════════════════════════════════════════════════════════════════════
# Canonical mapping: display code → (translation code, display name).
# The translation code is what deep-translator/Google Translate expects.

SUPPORTED_LANGUAGES: dict[str, tuple[str, str]] = {
    "es": ("es", "Spanish"),
    "fr": ("fr", "French"),
    "de": ("de", "German"),
    "pt": ("pt", "Portuguese"),
    "it": ("it", "Italian"),
    "nl": ("nl", "Dutch"),
    "pl": ("pl", "Polish"),
    "ro": ("ro", "Romanian"),
    "tr": ("tr", "Turkish"),
    "ru": ("ru", "Russian"),
    "ja": ("ja", "Japanese"),
    "zh": ("zh-CN", "Chinese (Simplified)"),
    "ko": ("ko", "Korean"),
    "ar": ("ar", "Arabic"),
    "hi": ("hi", "Hindi"),
    "sv": ("sv", "Swedish"),
    "da": ("da", "Danish"),
    "nb": ("no", "Norwegian"),
    "fi": ("fi", "Finnish"),
    "cs": ("cs", "Czech"),
    "uk": ("uk", "Ukrainian"),
    "el": ("el", "Greek"),
    "hu": ("hu", "Hungarian"),
    "th": ("th", "Thai"),
    "vi": ("vi", "Vietnamese"),
    "id": ("id", "Indonesian"),
    "ms": ("ms", "Malay"),
    "he": ("iw", "Hebrew"),
    "bg": ("bg", "Bulgarian"),
    "hr": ("hr", "Croatian"),
    "sk": ("sk", "Slovak"),
    "sl": ("sl", "Slovenian"),
    "sr": ("sr", "Serbian"),
    "lt": ("lt", "Lithuanian"),
    "lv": ("lv", "Latvian"),
    "et": ("et", "Estonian"),
    "ca": ("ca", "Catalan"),
    "tl": ("tl", "Filipino"),
    "sw": ("sw", "Swahili"),
    "af": ("af", "Afrikaans"),
}


# ═══════════════════════════════════════════════════════════════════════
#  CACHE DIRECTORY RESOLUTION
# ═══════════════════════════════════════════════════════════════════════


def _package_i18n_dir() -> Path | None:
    """Return the package ``i18n/`` directory if it already exists."""
    try:
        pkg = resources.files("rolodexter")
        d = Path(str(pkg)) / "i18n"
    except Exception:  # pylint: disable=broad-exception-caught
        return None
    return d if d.is_dir() else None


def _user_cache_dir(*, create: bool = False) -> Path:
    """Platform-specific user-writable cache directory."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    d = base / "rolodexter" / "i18n"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def _ensure_writable_cache_dir(path: Path) -> Path | None:
    """Create *path* if needed and return it when it is writable."""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    if not path.is_dir() or not os.access(path, os.W_OK):
        return None
    return path


def get_writable_cache_dir() -> Path:
    """Return the user-writable i18n generation cache directory."""
    cache_dir = _ensure_writable_cache_dir(_user_cache_dir())
    if cache_dir is not None:
        return cache_dir
    raise OSError("No writable i18n cache directory available")


def get_cache_dir() -> Path:
    """Return the user-writable i18n generation cache directory."""
    return get_writable_cache_dir()


def get_all_cache_dirs() -> list[Path]:
    """Return existing directories that might contain cached i18n files."""
    dirs: list[Path] = []
    pkg_dir = _package_i18n_dir()
    if pkg_dir is not None:
        dirs.append(pkg_dir)
    user_dir = _user_cache_dir()
    if user_dir.is_dir() and user_dir not in dirs:
        dirs.append(user_dir)
    return dirs


# ═══════════════════════════════════════════════════════════════════════
#  ALIAS VARIANT GENERATION
# ═══════════════════════════════════════════════════════════════════════


def _try_unidecode(text: str) -> str | None:
    """Transliterate to ASCII via unidecode if available."""
    try:
        from unidecode import unidecode

        result = unidecode(text).strip()
        return result if result and result != text else None
    except ImportError:
        return None


def _to_alias_variants(text: str) -> set[str]:
    """Generate alias variants from a translated phrase."""
    variants: set[str] = set()
    low = text.lower().strip()
    if len(low) < 2:
        return variants
    variants.add(low)
    underscored = re.sub(r"\s+", "_", low)
    variants.add(underscored)
    concat = re.sub(r"[\s_\-]+", "", low)
    if len(concat) > 1:
        variants.add(concat)
    hyphenated = re.sub(r"\s+", "-", low)
    if hyphenated != low:
        variants.add(hyphenated)
    ascii_ver = _try_unidecode(low)
    if ascii_ver:
        variants.add(ascii_ver)
        variants.add(re.sub(r"\s+", "_", ascii_ver))
        ascii_concat = re.sub(r"[\s_\-]+", "", ascii_ver)
        if len(ascii_concat) > 1:
            variants.add(ascii_concat)
    return {v for v in variants if len(v) > 1}


# ═══════════════════════════════════════════════════════════════════════
#  TRANSLATION ENGINE
# ═══════════════════════════════════════════════════════════════════════


def _non_negative_int(raw: str) -> int:
    value = int(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return value


def _non_negative_float(raw: str) -> float:
    value = float(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return value


def _bounded_workers(requested: int, target_count: int) -> int:
    if target_count <= 0:
        return 1
    return min(max(1, requested), target_count, MAX_I18N_WORKERS)


def _translator(lang_code: str, timeout: float) -> Any:
    from deep_translator import (  # type: ignore[import-untyped]
        GoogleTranslator,
    )

    try:
        return GoogleTranslator(source="en", target=lang_code, timeout=timeout)
    except TypeError:
        # Older deep-translator versions may not expose a timeout parameter.
        return GoogleTranslator(source="en", target=lang_code)


def _call_with_retries(
    func: Callable[[], _T],
    *,
    retries: int,
    retry_backoff: float,
    context: str,
    log: logging.Logger,
) -> _T:
    attempts = max(0, retries) + 1
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            if attempt >= attempts:
                raise
            log.warning(
                "%s failed on attempt %s/%s (%s); retrying.",
                context,
                attempt,
                attempts,
                exc,
            )
            if retry_backoff:
                time.sleep(retry_backoff * attempt)
    raise RuntimeError("unreachable retry state")


def _translate_batch(
    phrases: list[str],
    lang_code: str,
    *,
    timeout: float = DEFAULT_TRANSLATE_TIMEOUT,
    retries: int = DEFAULT_TRANSLATE_RETRIES,
    retry_backoff: float = DEFAULT_TRANSLATE_RETRY_BACKOFF,
) -> list[str | None]:
    """Translate English phrases to *lang_code* via deep-translator.

    Tries a single batch call first; on failure, falls back to per-phrase
    translation with a brief inter-call delay to be polite to the API.  Calls
    use a bounded retry/timeout budget where supported by the translator.
    Per-phrase failures are logged as warnings rather than swallowed
    silently so callers can diagnose partial-translation results.
    """
    log = logging.getLogger(__name__)
    retries = max(0, retries)
    timeout = max(0.0, timeout)
    retry_backoff = max(0.0, retry_backoff)

    try:
        translator = _translator(lang_code, timeout)
        results = _call_with_retries(
            lambda: translator.translate_batch(phrases),
            retries=retries,
            retry_backoff=retry_backoff,
            context=f"Batch translate for {lang_code}",
            log=log,
        )
        return [r.strip() if r else None for r in results]
    except Exception as batch_exc:  # pylint: disable=broad-exception-caught
        log.warning(
            "Batch translate failed for %s (%s); falling back to per-phrase.",
            lang_code,
            batch_exc,
        )
        out: list[str | None] = []
        for phrase in phrases:
            try:
                translator = _translator(lang_code, timeout)

                def translate_phrase(
                    translator: Any = translator, phrase: str = phrase
                ) -> Any:
                    return translator.translate(phrase)

                r = _call_with_retries(
                    translate_phrase,
                    retries=retries,
                    retry_backoff=retry_backoff,
                    context=f"Translate {phrase!r} to {lang_code}",
                    log=log,
                )
                out.append(r.strip() if r else None)
                time.sleep(0.05)
            except Exception as phrase_exc:  # pylint: disable=broad-exception-caught
                log.warning(
                    "Per-phrase translate failed for %r → %s: %s",
                    phrase,
                    lang_code,
                    phrase_exc,
                )
                out.append(None)
        return out


# ═══════════════════════════════════════════════════════════════════════
#  FIELD DERIVATION
# ═══════════════════════════════════════════════════════════════════════

# Fields that don't benefit from translation (technical/English-universal).
# Split into named categories so adding a new field is self-documenting:
# just decide *why* it's skipped and add it to the right set.

# Timestamps — machine-generated, never user-labeled in other languages
_TIMESTAMP_SKIP: frozenset[str] = frozenset(
    {"created_at", "updated_at", "last_contacted"}
)

# CRM / pipeline internals — English-only technical concepts
_CRM_SKIP: frozenset[str] = frozenset(
    {
        "utm_parameters",
        "metadata",
        "score",
        "owner",
        "tags",
        "lead_status",
        "lifecycle_stage",
        "email_opt_out",
        "currency",
        "source",
        "referrer_url",
        "timezone",
    }
)

# Niche platforms whose name IS the universal label
# (major platforms like linkedin/twitter/facebook DO get translated aliases)
_PLATFORM_SKIP: frozenset[str] = frozenset({"discord", "telegram"})

_SKIP_FIELDS: frozenset[str] = _TIMESTAMP_SKIP | _CRM_SKIP | _PLATFORM_SKIP


def _derive_field_phrases(master: dict[str, Any]) -> dict[str, str]:
    """Canonical field name → human phrase to translate."""
    return {
        canonical: canonical.replace("_", " ")
        for canonical in master.get("fields", {})
        if canonical not in _SKIP_FIELDS
    }


def _get_english_aliases(master: dict[str, Any]) -> set[str]:
    """Collect the English alias set from patterns.json."""
    aliases: set[str] = set()
    for alias_list in master.get("fields", {}).values():
        for alias in alias_list:
            aliases.add(alias.lower().strip())
    return aliases


# ═══════════════════════════════════════════════════════════════════════
#  LOADING MASTER DATA
# ═══════════════════════════════════════════════════════════════════════


def _load_master() -> dict[str, Any]:
    """Load the bundled patterns.json."""
    try:
        pkg = resources.files("rolodexter")
        text = pkg.joinpath("patterns.json").read_text(encoding="utf-8")
        return cast(dict[str, Any], json.loads(text))
    except Exception:  # pylint: disable=broad-exception-caught
        # Fallback: try filesystem path relative to this file
        p = Path(__file__).resolve().parent / "patterns.json"
        with open(p, encoding="utf-8") as fh:
            return cast(dict[str, Any], json.load(fh))


# ═══════════════════════════════════════════════════════════════════════
#  CACHED FILE I/O
# ═══════════════════════════════════════════════════════════════════════


_CACHE_SCHEMA_KEYS = ("language_code", "language_name", "fields")


def _validate_cache_schema(data: Any, path: Path) -> dict[str, Any] | None:
    """Check *data* looks like a generated i18n cache file.

    Returns *data* (typed as a dict) when it passes a light structural
    check, or ``None`` (after logging a warning) when it's the wrong shape
    — e.g. truncated, hand-edited, or written by an unrelated tool sharing
    the cache directory.  This only validates *shape*; it doesn't verify
    alias values.
    """
    if not isinstance(data, dict):
        logging.getLogger(__name__).warning(
            "Ignoring corrupt i18n cache file %s: expected a JSON object, got %s.",
            path,
            type(data).__name__,
        )
        return None
    missing = [key for key in _CACHE_SCHEMA_KEYS if key not in data]
    if missing:
        logging.getLogger(__name__).warning(
            "Ignoring corrupt i18n cache file %s: missing required key(s) %s.",
            path,
            ", ".join(missing),
        )
        return None
    if not isinstance(data.get("fields"), dict):
        logging.getLogger(__name__).warning(
            "Ignoring corrupt i18n cache file %s: 'fields' must be an object, got %s.",
            path,
            type(data.get("fields")).__name__,
        )
        return None
    return cast(dict[str, Any], data)


def load_cached(lang_code: str) -> dict[str, Any] | None:
    """Load a previously-generated i18n file from any cache directory.

    Returns the parsed JSON dict, or ``None`` if not found.  A file that
    exists but fails to parse as JSON or doesn't match the expected cache
    schema is treated as corrupt: it's skipped (falling through to the next
    cache directory, if any) and a warning is logged rather than silently
    swallowed, since a poisoned per-user cache file would otherwise make
    aliases for that language silently vanish.
    """
    for cache_dir in get_all_cache_dirs():
        path = cache_dir / f"{lang_code}.json"
        if path.exists():
            try:
                with open(path, encoding="utf-8") as fh:
                    parsed = json.load(fh)
            except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
                logging.getLogger(__name__).warning(
                    "Ignoring corrupt i18n cache file %s: %s", path, exc
                )
                continue
            validated = _validate_cache_schema(parsed, path)
            if validated is not None:
                return validated
    return None


def _write_cache(lang_data: dict[str, Any]) -> Path:
    """Write an i18n JSON file to the cache directory."""
    cache_dir = get_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{lang_data['language_code']}.json"
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=cache_dir,
            prefix=f".{path.stem}.",
            suffix=".tmp",
            delete=False,
        ) as fh:
            tmp_path = Path(fh.name)
            json.dump(lang_data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path is not None:
            with suppress(OSError):
                tmp_path.unlink(missing_ok=True)
        raise
    return path


# ═══════════════════════════════════════════════════════════════════════
#  PUBLIC API — generate_language()
# ═══════════════════════════════════════════════════════════════════════


def generate_language(  # pylint: disable=too-many-locals
    lang_code: str,
    *,
    force: bool = False,
    force_fields: set[str] | None = None,
    timeout: float = DEFAULT_TRANSLATE_TIMEOUT,
    retries: int = DEFAULT_TRANSLATE_RETRIES,
    retry_backoff: float = DEFAULT_TRANSLATE_RETRY_BACKOFF,
) -> dict[str, Any]:
    """Generate (or retrieve cached) i18n aliases for *lang_code*.

    Parameters
    ----------
    lang_code : str
        Language code, e.g. ``"es"``, ``"fr"``, ``"de"``.
        Must be a key in :data:`SUPPORTED_LANGUAGES`.
    force : bool
        If ``True``, re-translate even if a cached file exists.
    force_fields : set[str] | None
        Specific canonical fields to re-translate (merge with cache).
    timeout : float
        Translation request timeout, passed to deep-translator when supported.
    retries : int
        Number of retries after the first failed translation attempt.
    retry_backoff : float
        Base seconds to sleep between retries; multiplied by attempt number.

    Returns
    -------
    dict
        The i18n data dict with keys ``language_code``,
        ``language_name``, ``generated_at``, ``source_version``,
        ``fields``.

    Raises
    ------
    ValueError
        If *lang_code* is not in :data:`SUPPORTED_LANGUAGES`.
    ImportError
        If ``deep-translator`` is not installed.
    """
    if lang_code not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Unsupported language: {lang_code!r}. "
            f"Supported: {sorted(SUPPORTED_LANGUAGES)}"
        )

    # Check cache first
    if not force and not force_fields:
        cached = load_cached(lang_code)
        if cached is not None:
            return cached

    # Need to translate — ensure deep-translator is available
    try:
        from deep_translator import (  # pylint: disable=unused-import
            GoogleTranslator,  # noqa: F401
        )
    except ImportError:
        raise ImportError(
            "deep-translator is required for i18n generation. "
            "Install it with: pip install deep-translator"
        ) from None

    translate_code, lang_name = SUPPORTED_LANGUAGES[lang_code]
    master = _load_master()
    field_phrases = _derive_field_phrases(master)
    english_aliases = _get_english_aliases(master)
    master_version = master.get("version", "unknown")

    # Load existing cached data for incremental merge
    existing = load_cached(lang_code) if not force else None
    existing_fields: dict[str, list[str]] = (existing or {}).get("fields", {})
    all_canonicals = set(field_phrases.keys())
    force_fields = force_fields or set()

    # Determine which fields need translating
    if force:
        to_translate = set(all_canonicals)
    else:
        to_translate = {
            c for c in all_canonicals if c not in existing_fields or c in force_fields
        }

    new_translations: dict[str, list[str]] = {}
    if to_translate:
        canonicals = sorted(to_translate)
        phrases = [field_phrases[c] for c in canonicals]
        if (
            timeout == DEFAULT_TRANSLATE_TIMEOUT
            and retries == DEFAULT_TRANSLATE_RETRIES
            and retry_backoff == DEFAULT_TRANSLATE_RETRY_BACKOFF
        ):
            results = _translate_batch(phrases, translate_code)
        else:
            results = _translate_batch(
                phrases,
                translate_code,
                timeout=timeout,
                retries=retries,
                retry_backoff=retry_backoff,
            )
        for canonical, translated in zip(canonicals, results, strict=False):
            if not translated:
                continue
            variants = _to_alias_variants(translated)
            filtered = sorted(
                v for v in variants if v not in english_aliases and len(v) > 1
            )
            if filtered:
                new_translations[canonical] = filtered

    # Merge: keep existing, overlay new, prune obsolete fields
    merged: dict[str, list[str]] = {
        k: v for k, v in existing_fields.items() if k in all_canonicals
    }
    merged.update(new_translations)

    lang_data: dict[str, Any] = {
        "language_code": lang_code,
        "language_name": lang_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_version": master_version,
        "fields": merged,
    }

    # Cache the result — but skip writing an empty file that would
    # short-circuit future runs.  If we attempted translation and got
    # nothing, leave the cache state unchanged so the next invocation
    # can retry rather than reading back an empty file.
    if merged or existing is not None:
        _write_cache(lang_data)
    else:
        import logging

        logging.getLogger(__name__).warning(
            "No translations produced for %s; skipping cache write so a "
            "future run can retry.",
            lang_code,
        )
    return lang_data


def discover_cached() -> dict[str, Path]:
    """Return a dict of ``{lang_code: path}`` for all cached i18n files."""
    found: dict[str, Path] = {}
    for cache_dir in get_all_cache_dirs():
        if not cache_dir.exists():
            continue
        for item in cache_dir.iterdir():
            if item.suffix == ".json" and item.stem not in found:
                found[item.stem] = item
    return found


# ═══════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════


def main() -> None:  # pylint: disable=too-many-locals
    """Command-line entry point for i18n generation."""
    parser = argparse.ArgumentParser(
        description="Generate i18n language files for rolodexter (on-demand, cached).",
    )
    parser.add_argument(
        "--languages",
        help="Comma-separated language codes (default: all supported)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List supported languages and exit",
    )
    parser.add_argument(
        "--retranslate-fields",
        help="Comma-separated canonical fields to force re-translate",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-translate ALL fields, ignoring cache",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing files",
    )
    parser.add_argument(
        "--workers",
        type=_non_negative_int,
        default=6,
        help=f"Parallel workers, clamped to {MAX_I18N_WORKERS} max (default: 6)",
    )
    parser.add_argument(
        "--timeout",
        type=_non_negative_float,
        default=DEFAULT_TRANSLATE_TIMEOUT,
        help=(
            "Translation request timeout in seconds, when supported by the "
            f"translator (default: {DEFAULT_TRANSLATE_TIMEOUT:g})"
        ),
    )
    parser.add_argument(
        "--retries",
        type=_non_negative_int,
        default=DEFAULT_TRANSLATE_RETRIES,
        help=f"Retries after a failed translation attempt (default: {DEFAULT_TRANSLATE_RETRIES})",
    )
    parser.add_argument(
        "--retry-backoff",
        type=_non_negative_float,
        default=DEFAULT_TRANSLATE_RETRY_BACKOFF,
        help=(
            "Base seconds between retries, multiplied by attempt number "
            f"(default: {DEFAULT_TRANSLATE_RETRY_BACKOFF:g})"
        ),
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.list:
        print(f"Supported languages ({len(SUPPORTED_LANGUAGES)}):\n")
        for code, (_, name) in sorted(SUPPORTED_LANGUAGES.items()):
            cached = load_cached(code)
            status = "cached" if cached else "not generated"
            print(f"  {code:5s}  {name:25s}  [{status}]")
        return

    # Determine target languages
    if args.languages:
        requested = [c.strip() for c in args.languages.split(",")]
        unknown = [c for c in requested if c not in SUPPORTED_LANGUAGES]
        if unknown:
            print(f"ERROR: Unknown language code(s): {unknown}")
            print("Run with --list to see supported languages.")
            sys.exit(1)
        target_codes = requested
    else:
        target_codes = sorted(SUPPORTED_LANGUAGES.keys())

    # Force-fields
    force_fields: set[str] | None = None
    if args.retranslate_fields:
        force_fields = {f.strip() for f in args.retranslate_fields.split(",")}

    # Verify deep-translator
    try:
        from deep_translator import (  # pylint: disable=unused-import
            GoogleTranslator,  # noqa: F401
        )
    except ImportError:
        print(
            "ERROR: deep-translator is required. Install with: pip install deep-translator"
        )
        sys.exit(1)

    print(f"\nGenerating {len(target_codes)} language(s)...")
    if args.dry_run:
        cache_dirs = get_all_cache_dirs()
        cache_dir_text = ", ".join(str(d) for d in cache_dirs) if cache_dirs else "none"
        print(f"  Existing cache dirs: {cache_dir_text}\n")
    else:
        print(f"  Cache dir: {get_cache_dir()}\n")

    def _process(code: str) -> tuple[str, dict[str, Any]]:
        return code, generate_language(
            code,
            force=args.force,
            force_fields=force_fields,
            timeout=args.timeout,
            retries=args.retries,
            retry_backoff=args.retry_backoff,
        )

    if args.dry_run:
        for code in target_codes:
            _, name = SUPPORTED_LANGUAGES[code]
            cached = load_cached(code)
            status = "cached" if cached else "would generate"
            n_fields = len((cached or {}).get("fields", {}))
            print(f"  [{code}] {name}: {status} ({n_fields} fields)")
    else:
        worker_count = _bounded_workers(args.workers, len(target_codes))
        failures: list[tuple[str, str]] = []
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = {pool.submit(_process, c): c for c in target_codes}
            for future in as_completed(futures):
                code = futures[future]
                try:
                    _, data = future.result()
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    failures.append((code, str(exc)))
                    print(f"  [{code}] FAILED: {exc}")
                    continue
                n_fields = len(data.get("fields", {}))
                n_aliases = sum(len(v) for v in data.get("fields", {}).values())
                print(
                    f"  [{code}] {data['language_name']}: {n_fields} fields, {n_aliases} aliases"
                )
        if failures:
            print(f"\nFailed {len(failures)} language(s):")
            for code, error in failures:
                print(f"  [{code}] {error}")
            sys.exit(1)

    print("\nDone.")


if __name__ == "__main__":
    main()
