"""On-demand i18n alias generator for rolodexter.

English aliases ship out of the box.  When a user requests any other
language the generator translates canonical field names via
``deep-translator`` (Google Translate) and caches the result as a
JSON file so it only needs to happen once.

Cached files are written to ``_data/i18n/<lang>.json`` **inside the
installed package** when the directory is writable (editable / dev
installs), or to the platform cache directory
(``~/.cache/rolodexter/i18n/`` on Linux, ``%LOCALAPPDATA%\\rolodexter\\i18n\\``
on Windows) when it is not (e.g. site-packages in a venv).

Usage from code
───────────────
::

    from rolodexter.i18n import generate_language, SUPPORTED_LANGUAGES

    # Generate Spanish aliases (cached for future use)
    data = generate_language("es")

    # Automatic when using ContactMapper / PatternRegistry with languages=
    from rolodexter import ContactMapper
    mapper = ContactMapper(languages=["es"])  # generates on first use

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
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any, cast

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
    """Return ``i18n/`` inside the installed package, if writable."""
    try:
        pkg = resources.files("rolodexter")
        d = Path(str(pkg)) / "i18n"
        d.mkdir(parents=True, exist_ok=True)
        # Quick write-test
        probe = d / ".probe"
        probe.write_text("ok")
        probe.unlink()
        return d
    except Exception:  # pylint: disable=broad-exception-caught
        return None


def _user_cache_dir() -> Path:
    """Platform-specific user-writable cache directory."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    d = base / "rolodexter" / "i18n"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_cache_dir() -> Path:
    """Return the best available i18n cache directory."""
    pkg_dir = _package_i18n_dir()
    if pkg_dir is not None:
        return pkg_dir
    return _user_cache_dir()


def get_all_cache_dirs() -> list[Path]:
    """Return all directories that might contain cached i18n files."""
    dirs: list[Path] = []
    pkg_dir = _package_i18n_dir()
    if pkg_dir is not None:
        dirs.append(pkg_dir)
    user_dir = _user_cache_dir()
    if user_dir.exists() and user_dir not in dirs:
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


def _translate_batch(phrases: list[str], lang_code: str) -> list[str | None]:
    """Translate English phrases to *lang_code* via deep-translator."""
    try:
        from deep_translator import GoogleTranslator

        results = GoogleTranslator(source="en", target=lang_code).translate_batch(
            phrases
        )
        return [r.strip() if r else None for r in results]
    except Exception:  # pylint: disable=broad-exception-caught
        out: list[str | None] = []
        for phrase in phrases:
            try:
                from deep_translator import (
                    GoogleTranslator,  # type: ignore[import-untyped]
                )

                r = GoogleTranslator(source="en", target=lang_code).translate(phrase)
                out.append(r.strip() if r else None)
                time.sleep(0.05)
            except Exception:  # pylint: disable=broad-exception-caught
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


def load_cached(lang_code: str) -> dict[str, Any] | None:
    """Load a previously-generated i18n file from any cache directory.

    Returns the parsed JSON dict, or ``None`` if not found.
    """
    for cache_dir in get_all_cache_dirs():
        path = cache_dir / f"{lang_code}.json"
        if path.exists():
            try:
                with open(path, encoding="utf-8") as fh:
                    return cast(dict[str, Any], json.load(fh))
            except Exception:  # pylint: disable=broad-exception-caught
                continue
    return None


def _write_cache(lang_data: dict[str, Any]) -> Path:
    """Write an i18n JSON file to the cache directory."""
    cache_dir = get_cache_dir()
    path = cache_dir / f"{lang_data['language_code']}.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(lang_data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


# ═══════════════════════════════════════════════════════════════════════
#  PUBLIC API — generate_language()
# ═══════════════════════════════════════════════════════════════════════


def generate_language(  # pylint: disable=too-many-locals
    lang_code: str,
    *,
    force: bool = False,
    force_fields: set[str] | None = None,
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
        results = _translate_batch(phrases, translate_code)
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

    # Cache the result
    _write_cache(lang_data)
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
        type=int,
        default=6,
        help="Parallel workers (default: 6)",
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
    print(f"  Cache dir: {get_cache_dir()}\n")

    def _process(code: str) -> tuple[str, dict[str, Any]]:
        return code, generate_language(
            code,
            force=args.force,
            force_fields=force_fields,
        )

    if args.dry_run:
        for code in target_codes:
            _, name = SUPPORTED_LANGUAGES[code]
            cached = load_cached(code)
            status = "cached" if cached else "would generate"
            n_fields = len((cached or {}).get("fields", {}))
            print(f"  [{code}] {name}: {status} ({n_fields} fields)")
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(_process, c): c for c in target_codes}
            for future in as_completed(futures):
                code, data = future.result()
                n_fields = len(data.get("fields", {}))
                n_aliases = sum(len(v) for v in data.get("fields", {}).values())
                print(
                    f"  [{code}] {data['language_name']}: {n_fields} fields, {n_aliases} aliases"
                )

    print("\nDone.")


if __name__ == "__main__":
    main()
