from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from rolodexter import i18n


def _use_linux_cache_env(
    monkeypatch: pytest.MonkeyPatch,
    user_cache_base: Path,
) -> None:
    monkeypatch.setattr(i18n.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CACHE_HOME", str(user_cache_base))


def test_read_only_cache_lookup_does_not_create_dirs_or_probe(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_root = tmp_path / "package"
    package_root.mkdir()
    user_cache_base = tmp_path / "user-cache"

    monkeypatch.setattr(i18n.resources, "files", lambda _pkg_name: package_root)
    _use_linux_cache_env(monkeypatch, user_cache_base)

    assert i18n.get_all_cache_dirs() == []
    assert i18n.load_cached("zz_missing") is None
    assert i18n.discover_cached() == {}
    assert not (package_root / "i18n").exists()
    assert not user_cache_base.exists()
    assert not list(tmp_path.rglob(".probe"))


def test_read_only_cache_lookup_reads_existing_dirs_without_creating_user_cache(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_root = tmp_path / "package"
    package_i18n = package_root / "i18n"
    package_i18n.mkdir(parents=True)
    user_cache_base = tmp_path / "user-cache"
    cached = {
        "language_code": "es",
        "language_name": "Spanish",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "test",
        "fields": {"email": ["correo"]},
    }
    (package_i18n / "es.json").write_text(json.dumps(cached), encoding="utf-8")

    monkeypatch.setattr(i18n.resources, "files", lambda _pkg_name: package_root)
    _use_linux_cache_env(monkeypatch, user_cache_base)

    assert i18n.load_cached("es") == cached
    assert i18n.discover_cached() == {"es": package_i18n / "es.json"}
    assert not user_cache_base.exists()
    assert not list(tmp_path.rglob(".probe"))


def test_write_cache_creates_selected_dir_without_probe_or_leftover_temp(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_root = tmp_path / "package"
    package_root.mkdir()
    user_cache_base = tmp_path / "user-cache"
    lang_data = {
        "language_code": "zz_write",
        "language_name": "Write Test",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_version": "test",
        "fields": {"email": ["correo"]},
    }

    monkeypatch.setattr(i18n.resources, "files", lambda _pkg_name: package_root)
    _use_linux_cache_env(monkeypatch, user_cache_base)

    path = i18n._write_cache(lang_data)

    assert path == i18n._user_cache_dir() / "zz_write.json"
    assert json.loads(path.read_text(encoding="utf-8")) == lang_data
    assert not (path.parent / ".probe").exists()
    assert not list(path.parent.glob("*.tmp"))
    assert path.is_relative_to(user_cache_base)
    assert not (package_root / "i18n").exists()


def test_cli_dry_run_does_not_create_cache_dirs_or_probe(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    package_root = tmp_path / "package"
    package_root.mkdir()
    user_cache_base = tmp_path / "user-cache"
    fake_deep_translator = types.ModuleType("deep_translator")
    fake_deep_translator.GoogleTranslator = type("GoogleTranslator", (), {})

    monkeypatch.setattr(i18n.resources, "files", lambda _pkg_name: package_root)
    monkeypatch.setattr(i18n.sys, "argv", ["i18n", "--languages", "es", "--dry-run"])
    monkeypatch.setitem(i18n.sys.modules, "deep_translator", fake_deep_translator)
    _use_linux_cache_env(monkeypatch, user_cache_base)

    i18n.main()

    out = capsys.readouterr().out
    assert "Existing cache dirs: none" in out
    assert not (package_root / "i18n").exists()
    assert not user_cache_base.exists()
    assert not list(tmp_path.rglob(".probe"))
