"""The i18n command line: generate, translate, cache write and read.

Extracted verbatim from ``test_rolodexter.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest


class TestI18nLoadMaster:
    """Test _load_master()."""

    def test_returns_dict_with_fields(self) -> None:
        from rolodexter.i18n import _load_master

        data = _load_master()
        assert isinstance(data, dict)
        assert "fields" in data
        assert "version" in data


class TestI18nLoadCached:
    """Test load_cached() with nonexistent language."""

    def test_missing_language_returns_none(self) -> None:
        from rolodexter.i18n import load_cached

        assert load_cached("zz_nonexistent") is None


class TestI18nDiscoverCached:
    """Test discover_cached()."""

    def test_returns_dict(self) -> None:
        from rolodexter.i18n import discover_cached

        found = discover_cached()
        assert isinstance(found, dict)


class TestI18nTryUnidecode:
    """Test _try_unidecode fallback."""

    def test_ascii_input_returns_none(self) -> None:
        from rolodexter.i18n import _try_unidecode

        # Pure ASCII text → unidecode returns same → None
        result = _try_unidecode("hello")
        # Either None (same text) or None (unidecode not installed)
        assert result is None

    def test_empty_returns_none(self) -> None:
        from rolodexter.i18n import _try_unidecode

        result = _try_unidecode("")
        assert result is None


class TestI18nGenerateLanguageErrors:
    """Test generate_language error paths."""

    def test_unsupported_language_raises(self) -> None:
        from rolodexter.i18n import generate_language

        with pytest.raises(ValueError, match="Unsupported language"):
            generate_language("xx_fake")


class TestI18nPackageDir:
    """Test _package_i18n_dir directly."""

    def test_returns_path_on_editable_install(self) -> None:
        from rolodexter.i18n import _package_i18n_dir

        result = _package_i18n_dir()
        # On editable install this should return a valid Path
        if result is not None:
            assert isinstance(result, Path)
            assert result.exists()


class TestI18nWriteAndLoadCache:
    """Test _write_cache + load_cached round-trip."""

    def test_write_and_load(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from rolodexter.i18n import _write_cache, load_cached

        # Monkeypatch get_cache_dir to use tmp_path
        monkeypatch.setattr("rolodexter.i18n.get_cache_dir", lambda: tmp_path)
        monkeypatch.setattr("rolodexter.i18n.get_all_cache_dirs", lambda: [tmp_path])

        lang_data = {
            "language_code": "sw",
            "language_name": "Swahili",
            "generated_at": "2026-01-01T00:00:00+00:00",
            "source_version": "2.10.0",
            "fields": {"email": ["correo_test"]},
        }
        path = _write_cache(lang_data)
        assert path.exists()

        loaded = load_cached("sw")
        assert loaded is not None
        assert loaded["language_code"] == "sw"
        assert loaded["fields"]["email"] == ["correo_test"]


class TestI18nCliList:
    """Test i18n CLI --list option."""

    def test_list_languages(self, capsys: pytest.CaptureFixture[str]) -> None:
        import sys

        from rolodexter.i18n import main

        old_argv = sys.argv
        try:
            sys.argv = ["rolodexter.i18n", "--list"]
            main()
        finally:
            sys.argv = old_argv
        captured = capsys.readouterr()
        assert "Spanish" in captured.out
        assert "French" in captured.out
        assert "es" in captured.out


class TestI18nGenerateLanguageCached:
    """Test generate_language when cached data already exists."""

    def test_returns_cached_without_translating(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from rolodexter.i18n import generate_language

        cached_data = {
            "language_code": "es",
            "language_name": "Spanish",
            "generated_at": "2026-01-01",
            "source_version": "2.10.0",
            "fields": {"email": ["correo"]},
        }
        monkeypatch.setattr(
            "rolodexter.i18n.load_cached",
            lambda code: cached_data if code == "es" else None,
        )
        result = generate_language("es")
        assert result == cached_data

    def test_force_bypasses_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With force=True and no deep-translator, ImportError is raised."""
        # Remove deep-translator from available imports
        import builtins

        from rolodexter.i18n import generate_language

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "deep_translator":
                raise ImportError("mocked")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        with pytest.raises(ImportError, match="deep-translator is required"):
            generate_language("es", force=True)


class TestI18nTranslateBatch:
    """Test _translate_batch when deep-translator is not available."""

    def test_returns_nones_without_translator(self) -> None:
        from rolodexter.i18n import _translate_batch

        results = _translate_batch(["hello", "world"], "es")
        # Without deep-translator installed, all results should be None
        # (or actual translations if it IS installed)
        assert isinstance(results, list)
        assert len(results) == 2


class TestI18nLoadMasterFallback:
    """Test _load_master filesystem fallback."""

    def test_direct_call_returns_data(self) -> None:
        from rolodexter.i18n import _load_master

        data = _load_master()
        assert "fields" in data
        assert len(data["fields"]) > 30

    def test_fallback_when_resources_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from rolodexter import i18n

        def broken_files(_pkg_name):
            raise Exception("mocked resources failure")

        monkeypatch.setattr("rolodexter.i18n.resources.files", broken_files)
        data = i18n._load_master()
        assert "fields" in data
        assert "version" in data


class TestI18nGenerateLanguageFull:
    """Test generate_language with mocked translation pipeline."""

    def test_force_with_mocked_translator(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Full generate_language with mocked _translate_batch and deep-translator."""
        import sys
        import types

        from rolodexter import i18n

        # Mock _translate_batch to return fake translations (one per phrase)
        def mock_translate(phrases, lang_code):
            return [f"translated_{i}" for i in range(len(phrases))]

        monkeypatch.setattr(i18n, "_translate_batch", mock_translate)
        monkeypatch.setattr(i18n, "get_cache_dir", lambda: tmp_path)
        monkeypatch.setattr(i18n, "get_all_cache_dirs", lambda: [tmp_path])

        # Mock the deep-translator import check inside generate_language
        fake_module = types.ModuleType("deep_translator")
        fake_module.GoogleTranslator = type("GoogleTranslator", (), {})  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "deep_translator", fake_module)

        result = i18n.generate_language("es", force=True)
        assert result["language_code"] == "es"
        assert "fields" in result
        assert len(result["fields"]) > 0
        # Verify cache was written
        assert (tmp_path / "es.json").exists()

    def test_non_force_with_mocked_translator(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-force generate_language — covers the else branch for to_translate."""
        import sys
        import types

        from rolodexter import i18n

        def mock_translate(phrases, lang_code):
            # Return some None results to cover the 'continue' branch
            results = []
            for i, p in enumerate(phrases):
                results.append(
                    None if i % 3 == 0 else f"translated_{p.replace(' ', '_')}"
                )
            return results

        monkeypatch.setattr(i18n, "_translate_batch", mock_translate)
        monkeypatch.setattr(i18n, "get_cache_dir", lambda: tmp_path)
        monkeypatch.setattr(i18n, "get_all_cache_dirs", lambda: [tmp_path])

        fake_module = types.ModuleType("deep_translator")
        fake_module.GoogleTranslator = type("GoogleTranslator", (), {})  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "deep_translator", fake_module)

        result = i18n.generate_language("es")
        assert result["language_code"] == "es"
        assert "fields" in result
        assert (tmp_path / "es.json").exists()


class TestI18nTranslateBatchFallback:
    """Test _translate_batch fallback when batch translation fails."""

    def test_batch_retry_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Transient batch failures are retried within the configured budget."""
        from rolodexter import i18n

        call_count = {"batch": 0}
        seen_timeout: list[float] = []

        class RetryTranslator:
            def __init__(self, **kwargs):
                seen_timeout.append(kwargs["timeout"])

            def translate_batch(self, phrases):
                call_count["batch"] += 1
                if call_count["batch"] == 1:
                    raise Exception("transient")
                return [f"translated_{phrase}" for phrase in phrases]

        import types

        fake_dt = types.ModuleType("deep_translator")
        fake_dt.GoogleTranslator = RetryTranslator  # type: ignore[attr-defined]
        monkeypatch.setitem(__import__("sys").modules, "deep_translator", fake_dt)

        results = i18n._translate_batch(
            ["hello", "world"],
            "es",
            timeout=3.5,
            retries=1,
            retry_backoff=0,
        )
        assert call_count["batch"] == 2
        assert seen_timeout == [3.5]
        assert results == ["translated_hello", "translated_world"]

    def test_fallback_per_phrase(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When batch translate throws, falls back to per-phrase."""
        from rolodexter import i18n

        call_count = {"batch": 0, "single": 0}

        class MockTranslator:
            def __init__(self, **_kwargs):
                pass

            def translate_batch(self, phrases):
                call_count["batch"] += 1
                raise Exception("batch failed")

            def translate(self, phrase):
                call_count["single"] += 1
                return f"translated_{phrase}"

        # Create a fake module with our mock
        import types

        fake_dt = types.ModuleType("deep_translator")
        fake_dt.GoogleTranslator = MockTranslator  # type: ignore[attr-defined]
        monkeypatch.setitem(__import__("sys").modules, "deep_translator", fake_dt)

        results = i18n._translate_batch(["hello", "world"], "es")
        assert call_count["batch"] == 2
        assert call_count["single"] == 2
        assert results == ["translated_hello", "translated_world"]

    def test_fallback_per_phrase_also_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When both batch and per-phrase fail, returns Nones."""
        from rolodexter import i18n

        class FailTranslator:
            def __init__(self, **_kwargs):
                pass

            def translate_batch(self, phrases):
                raise Exception("batch failed")

            def translate(self, phrase):
                raise Exception("single failed")

        import types

        fake_dt = types.ModuleType("deep_translator")
        fake_dt.GoogleTranslator = FailTranslator  # type: ignore[attr-defined]
        monkeypatch.setitem(__import__("sys").modules, "deep_translator", fake_dt)

        results = i18n._translate_batch(["hello", "world"], "es")
        assert results == [None, None]

    def test_worker_count_clamped(self) -> None:
        from rolodexter import i18n

        assert i18n._bounded_workers(0, 5) == 1
        assert i18n._bounded_workers(99, 5) == 5
        assert i18n._bounded_workers(99, 99) == i18n.MAX_I18N_WORKERS


class TestI18nCliDryRun:
    """Test i18n CLI --dry-run and error paths."""

    def test_dry_run(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import sys
        import types

        from rolodexter.i18n import main

        # Mock deep-translator so the import check passes
        fake_dt = types.ModuleType("deep_translator")
        fake_dt.GoogleTranslator = type("GoogleTranslator", (), {})  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "deep_translator", fake_dt)

        old_argv = sys.argv
        try:
            sys.argv = ["rolodexter.i18n", "--dry-run", "--languages", "es"]
            main()
        finally:
            sys.argv = old_argv
        captured = capsys.readouterr()
        assert "Generating 1 language" in captured.out
        assert "[es]" in captured.out

    def test_generate_via_cli(
        self,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """CLI generate path (non-dry-run) with mocked translator."""
        import sys
        import types

        from rolodexter import i18n
        from rolodexter.i18n import main

        def mock_translate(phrases, lang_code):
            return [f"mock_{i}" for i in range(len(phrases))]

        monkeypatch.setattr(i18n, "_translate_batch", mock_translate)
        monkeypatch.setattr(i18n, "get_cache_dir", lambda: tmp_path)
        monkeypatch.setattr(i18n, "get_all_cache_dirs", lambda: [tmp_path])

        fake_dt = types.ModuleType("deep_translator")
        fake_dt.GoogleTranslator = type("GoogleTranslator", (), {})  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "deep_translator", fake_dt)

        old_argv = sys.argv
        try:
            sys.argv = ["rolodexter.i18n", "--languages", "es", "--force"]
            main()
        finally:
            sys.argv = old_argv
        captured = capsys.readouterr()
        assert "Generating 1 language" in captured.out
        assert "[es]" in captured.out
        assert "Spanish" in captured.out

    def test_cli_reports_per_language_failures(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import sys
        import types

        from rolodexter import i18n
        from rolodexter.i18n import main

        fake_dt = types.ModuleType("deep_translator")
        fake_dt.GoogleTranslator = type("GoogleTranslator", (), {})  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "deep_translator", fake_dt)

        def fake_generate(code, **_kwargs):
            if code == "es":
                raise RuntimeError("network budget exhausted")
            return {
                "language_code": code,
                "language_name": i18n.SUPPORTED_LANGUAGES[code][1],
                "fields": {"email": ["correo"]},
            }

        monkeypatch.setattr(i18n, "generate_language", fake_generate)

        old_argv = sys.argv
        try:
            sys.argv = ["rolodexter.i18n", "--languages", "es,fr", "--workers", "99"]
            with pytest.raises(SystemExit) as excinfo:
                main()
        finally:
            sys.argv = old_argv
        captured = capsys.readouterr()
        assert excinfo.value.code == 1
        assert "[fr]" in captured.out
        assert "[es] FAILED: network budget exhausted" in captured.out
        assert "Failed 1 language" in captured.out

    def test_default_all_languages(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CLI with no --languages flag defaults to all supported."""
        import sys
        import types

        from rolodexter.i18n import main

        fake_dt = types.ModuleType("deep_translator")
        fake_dt.GoogleTranslator = type("GoogleTranslator", (), {})  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "deep_translator", fake_dt)

        old_argv = sys.argv
        try:
            sys.argv = ["rolodexter.i18n", "--dry-run"]
            main()
        finally:
            sys.argv = old_argv
        captured = capsys.readouterr()
        assert "Generating" in captured.out

    def test_unknown_language_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        import sys

        from rolodexter.i18n import main

        old_argv = sys.argv
        try:
            sys.argv = ["rolodexter.i18n", "--languages", "xx_fake"]
            with pytest.raises(SystemExit):
                main()
        finally:
            sys.argv = old_argv
        captured = capsys.readouterr()
        assert "Unknown language" in captured.out

    def test_no_deep_translator_error(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import builtins
        import sys

        from rolodexter.i18n import main

        # Ensure deep-translator is NOT available
        original_import = builtins.__import__

        def block_deep_translator(name, *args, **kwargs):
            if "deep_translator" in name:
                raise ImportError("not installed")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", block_deep_translator)
        # Also remove from sys.modules if cached
        monkeypatch.delitem(sys.modules, "deep_translator", raising=False)

        old_argv = sys.argv
        try:
            sys.argv = ["rolodexter.i18n", "--languages", "es"]
            with pytest.raises(SystemExit):
                main()
        finally:
            sys.argv = old_argv
        captured = capsys.readouterr()
        assert "deep-translator is required" in captured.out


class TestI18nCacheDirFallback:
    """Test generated i18n cache writes use the user cache."""

    def test_user_cache_used_when_pkg_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from rolodexter.i18n import _user_cache_dir, get_cache_dir

        monkeypatch.setattr("rolodexter.i18n.sys.platform", "linux")
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        result = get_cache_dir()
        assert result == _user_cache_dir()
        assert result.is_dir()
