"""The i18n module surface: cache dirs, alias variants, field derivation.

Extracted verbatim from ``test_rolodexter.py``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch as _mock_patch

import pytest

from rolodexter import (
    PatternRegistry,
)


class TestI18nModule:
    """Test the i18n module itself — internal helpers and public API."""

    # --- SUPPORTED_LANGUAGES ---

    def test_supported_languages_dict(self) -> None:
        from rolodexter.i18n import SUPPORTED_LANGUAGES

        assert len(SUPPORTED_LANGUAGES) >= 30
        assert "es" in SUPPORTED_LANGUAGES
        assert "fr" in SUPPORTED_LANGUAGES
        assert "de" in SUPPORTED_LANGUAGES

    def test_supported_languages_structure(self) -> None:
        from rolodexter.i18n import SUPPORTED_LANGUAGES

        for code, (translate_code, display_name) in SUPPORTED_LANGUAGES.items():
            assert isinstance(code, str) and len(code) >= 2
            assert isinstance(translate_code, str) and len(translate_code) >= 2
            assert isinstance(display_name, str) and len(display_name) >= 3

    # --- generate_language ---

    def test_generate_language_unsupported_raises(self) -> None:
        from rolodexter.i18n import generate_language

        with pytest.raises(ValueError, match="Unsupported language"):
            generate_language("xx_fake")

    # --- discover / load ---

    def test_discover_cached_returns_dict(self) -> None:
        from rolodexter.i18n import discover_cached

        result = discover_cached()
        assert isinstance(result, dict)

    def test_load_cached_missing_returns_none(self) -> None:
        from rolodexter.i18n import load_cached

        assert load_cached("zz_nonexistent_lang") is None

    # --- cache dirs ---

    def test_get_cache_dir_returns_path(self) -> None:
        from pathlib import Path

        from rolodexter.i18n import get_cache_dir

        d = get_cache_dir()
        assert isinstance(d, Path)
        assert d.exists()

    def test_get_all_cache_dirs(self) -> None:
        from rolodexter.i18n import get_all_cache_dirs

        dirs = get_all_cache_dirs()
        assert isinstance(dirs, list)
        for d in dirs:
            assert isinstance(d, Path)
            assert d.is_dir()

    def test_package_i18n_dir(self) -> None:
        from rolodexter.i18n import _package_i18n_dir

        d = _package_i18n_dir()
        # In an editable install this should succeed
        if d is not None:
            assert d.is_dir()

    def test_user_cache_dir(self) -> None:
        from rolodexter.i18n import _user_cache_dir

        d = _user_cache_dir()
        assert isinstance(d, Path)
        assert d.name == "i18n"

    # --- alias variant generation ---

    def test_to_alias_variants_basic(self) -> None:
        from rolodexter.i18n import _to_alias_variants

        variants = _to_alias_variants("correo electrónico")
        assert "correo electrónico" in variants
        assert "correo_electrónico" in variants
        assert "correoelectrónico" in variants
        assert "correo-electrónico" in variants

    def test_to_alias_variants_short_ignored(self) -> None:
        from rolodexter.i18n import _to_alias_variants

        assert _to_alias_variants("") == set()
        assert _to_alias_variants("x") == set()

    def test_to_alias_variants_single_word(self) -> None:
        from rolodexter.i18n import _to_alias_variants

        variants = _to_alias_variants("Empresa")
        assert "empresa" in variants

    def test_to_alias_variants_preserves_case_lower(self) -> None:
        from rolodexter.i18n import _to_alias_variants

        variants = _to_alias_variants("NachName")
        assert "nachname" in variants
        assert "NachName" not in variants

    # --- field derivation ---

    def test_derive_field_phrases(self) -> None:
        from rolodexter.i18n import _derive_field_phrases

        master = {"fields": {"first_name": [], "email": [], "metadata": [], "tags": []}}
        result = _derive_field_phrases(master)
        assert result["first_name"] == "first name"
        assert result["email"] == "email"
        # Skip fields are excluded
        assert "metadata" not in result
        assert "tags" not in result

    def test_derive_field_phrases_empty(self) -> None:
        from rolodexter.i18n import _derive_field_phrases

        assert _derive_field_phrases({}) == {}
        assert _derive_field_phrases({"fields": {}}) == {}

    def test_get_english_aliases(self) -> None:
        from rolodexter.i18n import _get_english_aliases

        master = {
            "fields": {
                "email": ["e-mail", "Email Address", "EmailAddress"],
                "first_name": ["fname", "First Name"],
            }
        }
        aliases = _get_english_aliases(master)
        assert "e-mail" in aliases
        assert "email address" in aliases
        assert "emailaddress" in aliases
        assert "fname" in aliases
        assert "first name" in aliases

    # --- load_master ---

    def test_load_master_returns_dict(self) -> None:
        from rolodexter.i18n import _load_master

        master = _load_master()
        assert isinstance(master, dict)
        assert "fields" in master
        assert "version" in master
        assert len(master["fields"]) >= 40

    # --- write / load round-trip ---

    def test_write_and_load_cache(self, tmp_path: Path) -> None:
        """Write a cache file via _write_cache, read it back with load_cached."""
        import json

        from rolodexter.i18n import _write_cache, load_cached

        lang_data = {
            "language_code": "es",
            "language_name": "Test Language",
            "generated_at": "2026-01-01T00:00:00+00:00",
            "source_version": "2.2.0",
            "fields": {"email": ["prueba"]},
        }
        # Patch get_cache_dir to use tmp_path
        with _mock_patch("rolodexter.i18n.get_cache_dir", return_value=tmp_path):
            written = _write_cache(lang_data)
        assert written.exists()
        assert json.loads(written.read_text("utf-8"))["language_code"] == "es"
        # Now load it back
        with _mock_patch("rolodexter.i18n.get_all_cache_dirs", return_value=[tmp_path]):
            loaded = load_cached("es")
        assert loaded is not None
        assert loaded["fields"]["email"] == ["prueba"]

    def test_load_cached_bad_json(self, tmp_path: Path, caplog) -> None:
        """Corrupt JSON is skipped, with a warning rather than silent failure."""
        from rolodexter.i18n import load_cached

        bad_file = tmp_path / "fr.json"
        bad_file.write_text("NOT JSON{{{", encoding="utf-8")
        with (
            _mock_patch("rolodexter.i18n.get_all_cache_dirs", return_value=[tmp_path]),
            caplog.at_level("WARNING", logger="rolodexter.i18n"),
        ):
            assert load_cached("fr") is None
        assert "corrupt" in caplog.text.lower()

    def test_load_cached_wrong_schema(self, tmp_path: Path, caplog) -> None:
        """Valid JSON that doesn't match the cache schema is treated as corrupt."""
        import json

        from rolodexter.i18n import load_cached

        bad_file = tmp_path / "de.json"
        bad_file.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
        with (
            _mock_patch("rolodexter.i18n.get_all_cache_dirs", return_value=[tmp_path]),
            caplog.at_level("WARNING", logger="rolodexter.i18n"),
        ):
            assert load_cached("de") is None
        assert "corrupt" in caplog.text.lower()

    def test_load_cached_missing_keys(self, tmp_path: Path, caplog) -> None:
        """A JSON object missing required cache keys is treated as corrupt."""
        import json

        from rolodexter.i18n import load_cached

        bad_file = tmp_path / "it.json"
        bad_file.write_text(json.dumps({"language_code": "it"}), encoding="utf-8")
        with (
            _mock_patch("rolodexter.i18n.get_all_cache_dirs", return_value=[tmp_path]),
            caplog.at_level("WARNING", logger="rolodexter.i18n"),
        ):
            assert load_cached("it") is None
        assert "corrupt" in caplog.text.lower()

    # --- discover_cached with tmp dir ---

    def test_discover_cached_finds_files(self, tmp_path: Path) -> None:
        from rolodexter.i18n import discover_cached

        (tmp_path / "es.json").write_text('{"language_code":"es"}', encoding="utf-8")
        (tmp_path / "fr.json").write_text('{"language_code":"fr"}', encoding="utf-8")
        (tmp_path / "readme.txt").write_text("ignore me", encoding="utf-8")
        with _mock_patch("rolodexter.i18n.get_all_cache_dirs", return_value=[tmp_path]):
            found = discover_cached()
        assert "es" in found
        assert "fr" in found
        assert "readme" not in found

    # --- translate batch (mocked) ---

    def test_translate_batch_mocked(self) -> None:
        """Verify _translate_batch calls deep-translator correctly."""
        mock_translator = type(
            "MockTranslator",
            (),
            {
                "translate_batch": lambda self, phrases: [p.upper() for p in phrases],
            },
        )()
        with _mock_patch(
            "rolodexter.i18n.GoogleTranslator",
            return_value=mock_translator,
            create=True,
        ):
            # We need to mock the actual import inside the function
            import rolodexter.i18n as i18n_mod

            original = i18n_mod._translate_batch

            def patched_batch(phrases, lang_code):
                return [p.upper() for p in phrases]

            i18n_mod._translate_batch = patched_batch
            try:
                results = i18n_mod._translate_batch(["hello", "world"], "es")
                assert results == ["HELLO", "WORLD"]
            finally:
                i18n_mod._translate_batch = original

    # --- generate_language full flow (mocked translation) ---

    def test_generate_language_mocked(self, tmp_path: Path) -> None:
        """Full generate_language with mocked translation engine."""
        import rolodexter.i18n as i18n_mod

        def fake_translate(phrases, lang_code):
            return [f"translated_{p}" for p in phrases]

        with (
            _mock_patch.object(
                i18n_mod, "_translate_batch", side_effect=fake_translate
            ),
            _mock_patch.object(i18n_mod, "get_cache_dir", return_value=tmp_path),
            _mock_patch.object(i18n_mod, "get_all_cache_dirs", return_value=[tmp_path]),
            _mock_patch("rolodexter.i18n.GoogleTranslator", create=True),
        ):
            data = i18n_mod.generate_language("es", force=True)

        assert data["language_code"] == "es"
        assert data["language_name"] == "Spanish"
        assert "fields" in data
        assert "generated_at" in data
        # Should have written a cache file
        assert (tmp_path / "es.json").exists()

    def test_generate_language_uses_cache(self, tmp_path: Path) -> None:
        """generate_language returns cached data without translating."""
        import json

        import rolodexter.i18n as i18n_mod

        cached = {
            "language_code": "de",
            "language_name": "German",
            "generated_at": "2026-01-01T00:00:00+00:00",
            "source_version": "2.2.0",
            "fields": {"first_name": ["vorname"]},
        }
        (tmp_path / "de.json").write_text(json.dumps(cached), encoding="utf-8")
        with _mock_patch.object(
            i18n_mod, "get_all_cache_dirs", return_value=[tmp_path]
        ):
            data = i18n_mod.generate_language("de")
        assert data == cached

    # --- CLI ---

    def test_main_list_flag(self, capsys) -> None:
        """CLI --list prints supported languages."""
        import rolodexter.i18n as i18n_mod

        with _mock_patch("sys.argv", ["i18n", "--list"]):
            i18n_mod.main()
        out = capsys.readouterr().out
        assert "Spanish" in out
        assert "French" in out
        assert "German" in out

    def test_main_dry_run(self, capsys, tmp_path: Path) -> None:
        """CLI --dry-run does not write files."""
        import rolodexter.i18n as i18n_mod

        with (
            _mock_patch("sys.argv", ["i18n", "--languages", "es", "--dry-run"]),
            _mock_patch.object(i18n_mod, "get_cache_dir", return_value=tmp_path),
            _mock_patch.object(i18n_mod, "get_all_cache_dirs", return_value=[tmp_path]),
        ):
            i18n_mod.main()
        out = capsys.readouterr().out
        assert "es" in out
        # No file should have been created
        assert not (tmp_path / "es.json").exists()

    def test_main_unknown_language_exits(self) -> None:
        """CLI with unknown language exits with error."""
        import rolodexter.i18n as i18n_mod

        with (
            _mock_patch("sys.argv", ["i18n", "--languages", "zz_bad"]),
            pytest.raises(SystemExit),
        ):
            i18n_mod.main()


# ═══════════════════════════════════════════════════════════════
#  v2.5 — COVERAGE BOOST: i18n.py GAPS
# ═══════════════════════════════════════════════════════════════


class TestI18nCacheDirs:
    """Test i18n cache directory resolution."""

    def test_get_cache_dir_returns_path(self) -> None:
        from rolodexter.i18n import get_cache_dir

        d = get_cache_dir()
        assert isinstance(d, Path)
        assert d.exists()

    def test_get_all_cache_dirs(self) -> None:
        from rolodexter.i18n import get_all_cache_dirs

        dirs = get_all_cache_dirs()
        assert isinstance(dirs, list)
        for d in dirs:
            assert isinstance(d, Path)
            assert d.is_dir()

    def test_user_cache_dir(self) -> None:
        from rolodexter.i18n import _user_cache_dir

        d = _user_cache_dir()
        assert isinstance(d, Path)
        assert d.name == "i18n"


class TestI18nAliasVariants:
    """Test _to_alias_variants() variant generation."""

    def test_basic_variants(self) -> None:
        from rolodexter.i18n import _to_alias_variants

        variants = _to_alias_variants("First Name")
        assert "first name" in variants
        assert "first_name" in variants
        assert "firstname" in variants
        assert "first-name" in variants

    def test_single_char_excluded(self) -> None:
        from rolodexter.i18n import _to_alias_variants

        assert _to_alias_variants("x") == set()

    def test_empty_excluded(self) -> None:
        from rolodexter.i18n import _to_alias_variants

        assert _to_alias_variants("") == set()


class TestI18nFieldDerivation:
    """Test _derive_field_phrases and _get_english_aliases."""

    def test_derive_field_phrases(self) -> None:
        from rolodexter.i18n import _derive_field_phrases

        master = {"fields": {"first_name": ["fname"], "email": ["e_mail"]}}
        result = _derive_field_phrases(master)
        assert result["first_name"] == "first name"
        assert result["email"] == "email"

    def test_skip_fields_excluded(self) -> None:
        from rolodexter.i18n import _derive_field_phrases

        master = {"fields": {"first_name": ["fname"], "metadata": ["meta"]}}
        result = _derive_field_phrases(master)
        assert "metadata" not in result

    def test_get_english_aliases(self) -> None:
        from rolodexter.i18n import _get_english_aliases

        master = {"fields": {"first_name": ["FName", "Given"], "email": ["E-Mail"]}}
        aliases = _get_english_aliases(master)
        assert "fname" in aliases
        assert "given" in aliases
        assert "e-mail" in aliases


class TestI18nLoadsCacheOnly:
    """Construction never translates over the network (the H1 reliability fix)."""

    def test_uncached_supported_language_warns_and_skips(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        import rolodexter.i18n as _i18n_mod

        def _no_cache(_code: str) -> None:
            return None

        def _must_not_be_called(*_a: object, **_kw: object) -> dict:
            raise AssertionError("generate_language must not run during construction")

        monkeypatch.setattr(_i18n_mod, "load_cached", _no_cache)
        monkeypatch.setattr(_i18n_mod, "generate_language", _must_not_be_called)

        with caplog.at_level(logging.WARNING, logger="rolodexter.core"):
            reg = PatternRegistry(languages=["es"])

        # No network call, language not loaded, and the user is warned how to
        # generate it offline.
        assert reg.loaded_languages == []
        assert any("python -m rolodexter.i18n" in r.message for r in caplog.records)
