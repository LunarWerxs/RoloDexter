#!/usr/bin/env python3
"""Rolodexter i18n generator — incremental, dynamic, parallel.

Reads patterns.json to get languages and fields. On each run it only
translates fields that are MISSING from an existing language file —
existing translations are preserved and merged. Use --force or
--retranslate-fields to override specific entries.

Usage:
    python scripts/generate_i18n.py                         # update all (incremental)
    python scripts/generate_i18n.py --languages es,fr       # specific languages
    python scripts/generate_i18n.py --retranslate-fields age,company  # re-do specific fields
    python scripts/generate_i18n.py --force                 # ignore cache, redo everything
    python scripts/generate_i18n.py --no-translate          # offline, preserve existing
    python scripts/generate_i18n.py --dry-run               # preview without writing
    python scripts/generate_i18n.py --workers 10            # parallelism
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MASTER_PATH = ROOT / "src" / "rolodexter" / "_data" / "patterns.json"
I18N_DIR = ROOT / "src" / "rolodexter" / "_data" / "i18n"


# ── Alias helpers ──────────────────────────────────────────────────────

def _try_unidecode(text: str) -> str | None:
    try:
        from unidecode import unidecode
        result = unidecode(text).strip()
        return result if result and result != text else None
    except ImportError:
        return None


def _to_alias_variants(text: str) -> set[str]:
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


# ── Translation ────────────────────────────────────────────────────────

def _translate_batch(phrases: list[str], lang_code: str) -> list[str | None]:
    try:
        from deep_translator import GoogleTranslator
        results = GoogleTranslator(source="en", target=lang_code).translate_batch(phrases)
        return [r.strip() if r else None for r in results]
    except Exception:
        out = []
        for phrase in phrases:
            try:
                from deep_translator import GoogleTranslator
                r = GoogleTranslator(source="en", target=lang_code).translate(phrase)
                out.append(r.strip() if r else None)
                time.sleep(0.05)
            except Exception:
                out.append(None)
        return out


# ── Field derivation ───────────────────────────────────────────────────

def derive_field_phrases(master: dict) -> dict[str, str]:
    """Canonical field name -> human phrase to translate.

    first_name -> "first name".  Derived entirely from patterns.json["fields"].
    """
    skip = {
        "utm_parameters", "metadata", "score", "owner", "tags",
        "lead_status", "lifecycle_stage", "email_opt_out",
        "created_at", "updated_at", "last_contacted",
        "currency", "source",
    }
    return {
        canonical: canonical.replace("_", " ")
        for canonical in master.get("fields", {})
        if canonical not in skip
    }


# ── Existing file loading ──────────────────────────────────────────────

def load_existing(path: Path) -> dict:
    if path.exists():
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass
    return {}


# ── Per-language generation (incremental) ─────────────────────────────

def generate_language(
    lang_code: str,
    lang_name: str,
    field_phrases: dict[str, str],
    english_aliases: set[str],
    master_version: str,
    file_code: str,
    existing: dict,
    *,
    translate: bool = True,
    force: bool = False,
    force_fields: set[str] | None = None,
) -> tuple[dict, int, int]:
    """Generate/update i18n data for one language incrementally.

    Returns (lang_data, n_translated, n_reused).
    """
    existing_fields: dict[str, list[str]] = existing.get("fields", {})
    all_canonicals = set(field_phrases.keys())
    force_fields = force_fields or set()

    n_translated = 0
    n_reused = 0

    if translate:
        # Determine which fields need (re-)translating
        if force:
            to_translate = set(all_canonicals)
        else:
            to_translate = {
                c for c in all_canonicals
                if c not in existing_fields or c in force_fields
            }

        new_translations: dict[str, list[str]] = {}
        if to_translate:
            canonicals = sorted(to_translate)
            phrases = [field_phrases[c] for c in canonicals]
            results = _translate_batch(phrases, lang_code)
            for canonical, translated in zip(canonicals, results):
                if not translated:
                    continue
                variants = _to_alias_variants(translated)
                filtered = sorted(v for v in variants if v not in english_aliases and len(v) > 1)
                if filtered:
                    new_translations[canonical] = filtered

        # Merge: keep existing entries that are still valid, overlay new translations,
        # prune fields no longer in patterns.json
        merged: dict[str, list[str]] = {
            k: v for k, v in existing_fields.items() if k in all_canonicals
        }
        merged.update(new_translations)

        n_translated = len(to_translate)
        n_reused = len(all_canonicals) - len(to_translate)
    else:
        # No translation — carry forward existing (pruned to current field set)
        merged = {k: v for k, v in existing_fields.items() if k in all_canonicals}
        n_reused = len(merged)

    return (
        {
            "language_code": file_code,
            "language_name": lang_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_version": master_version,
            "fields": merged,
        },
        n_translated,
        n_reused,
    )


def write_language_file(lang_data: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{lang_data['language_code']}.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(lang_data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


# ── CLI ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate / update i18n language files for rolodexter (incremental).",
    )
    parser.add_argument("--languages", help="Comma-separated language codes (default: all)")
    parser.add_argument("--output", default=str(I18N_DIR), help="Output directory")
    parser.add_argument(
        "--retranslate-fields",
        help="Comma-separated canonical field names to force re-translate (e.g. age,company)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-translate ALL fields for targeted languages, ignoring existing files",
    )
    parser.add_argument("--no-translate", action="store_true", help="Skip translation API (offline mode)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing files")
    parser.add_argument("--workers", type=int, default=6, help="Parallel language workers (default: 6)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    with open(MASTER_PATH, encoding="utf-8") as fh:
        master = json.load(fh)

    i18n_cfg = master.get("i18n_config", {})
    all_languages: dict[str, str] = i18n_cfg.get("languages", {})
    file_code_overrides: dict[str, str] = i18n_cfg.get("file_code_overrides", {})
    translate_code_overrides: dict[str, str] = i18n_cfg.get("translate_code_overrides", {})

    if not all_languages:
        print("ERROR: patterns.json has no i18n_config.languages section.")
        sys.exit(1)

    # Filter to requested languages
    if args.languages:
        requested = {c.strip() for c in args.languages.split(",")}
        target_langs = {k: v for k, v in all_languages.items() if k in requested}
        if not target_langs:
            print(f"ERROR: No match for: {args.languages}")
            print(f"Available: {', '.join(all_languages)}")
            sys.exit(1)
    else:
        target_langs = all_languages

    # Fields to force re-translate
    force_fields: set[str] = set()
    if args.retranslate_fields:
        force_fields = {f.strip() for f in args.retranslate_fields.split(",")}

    field_phrases = derive_field_phrases(master)

    english_aliases: set[str] = set()
    for alias_list in master.get("fields", {}).values():
        for alias in alias_list:
            english_aliases.add(alias.lower().strip())

    do_translate = not args.no_translate
    if do_translate:
        try:
            from deep_translator import GoogleTranslator  # noqa: F401
        except ImportError:
            print("WARNING: deep-translator not installed. Run: pip install deep-translator")
            do_translate = False

    output_dir = Path(args.output)
    master_version = master.get("version", "unknown")

    mode = "force (re-translate all)" if args.force else "incremental (new/changed fields only)"
    print(f"\nUpdating {len(target_langs)} language(s)  —  patterns.json v{master_version}")
    print(f"  Mode    : {mode}")
    print(f"  Fields  : {len(field_phrases)} (from patterns.json)")
    if force_fields:
        print(f"  Re-translate : {sorted(force_fields)}")
    print(f"  Output  : {output_dir}\n")

    def _process(lang_code: str, lang_name: str) -> tuple:
        file_code = file_code_overrides.get(lang_code, lang_code)
        translate_code = translate_code_overrides.get(lang_code, lang_code)
        existing_path = output_dir / f"{file_code}.json"
        existing = load_existing(existing_path) if not args.force else {}
        data, n_new, n_reused = generate_language(
            translate_code, lang_name, field_phrases, english_aliases,
            master_version, file_code, existing,
            translate=do_translate,
            force=args.force,
            force_fields=force_fields,
        )
        return lang_code, data, n_new, n_reused

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_process, code, name): code for code, name in target_langs.items()}
        total_new = 0
        total_reused = 0
        for future in as_completed(futures):
            lang_code, data, n_new, n_reused = future.result()
            total_new += n_new
            total_reused += n_reused
            fc = data["language_code"]
            n_aliases = sum(len(v) for v in data["fields"].values())
            n_fields = len(data["fields"])
            if do_translate:
                detail = f"{n_new} translated, {n_reused} reused  ({n_fields} fields, {n_aliases} aliases)"
            else:
                detail = f"{n_fields} fields, {n_aliases} aliases (no translation)"
            if args.dry_run:
                print(f"  [{fc}] {data['language_name']}: {detail}  (dry run)")
                if args.verbose:
                    for canon, aliases in sorted(data["fields"].items()):
                        print(f"    {canon}: {aliases}")
            else:
                path = write_language_file(data, output_dir)
                print(f"  [{fc}] {data['language_name']}: {detail}  -> {path.name}")

    action = "would update" if args.dry_run else "updated"
    print(f"\nDone — {action} {len(target_langs)} file(s).  API calls: {total_new} fields translated, {total_reused} reused from cache.")


if __name__ == "__main__":
    main()
