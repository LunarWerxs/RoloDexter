"""Audit fixes for language packs: M12, L22 (contract C5), L24.

M12: a generation where some phrases failed is recorded as such, retried
field by field, reported as "N of M fields" with exit status 2, and the
per-request timeout is enforced (deep-translator never applied it).
C5: ``ROLODEXTER_CACHE_DIR`` is the folder packs are read from and written to.
L24: ``--retranslate-fields`` rejects unknown names; ``--dry-run`` works
without deep-translator installed.
"""

from __future__ import annotations

import builtins
import json
import sys
import threading
import time
import types
from pathlib import Path
from typing import Any

import pytest

from rolodexter import i18n


@pytest.fixture
def cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty pack folder via ROLODEXTER_CACHE_DIR; no packaged packs."""
    package_root = tmp_path / "package"
    package_root.mkdir()
    monkeypatch.setattr(i18n.resources, "files", lambda _pkg_name: package_root)
    target = tmp_path / "packs"
    monkeypatch.setenv("ROLODEXTER_CACHE_DIR", str(target))
    fake_dt = types.ModuleType("deep_translator")
    fake_dt.GoogleTranslator = type("GoogleTranslator", (), {})  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "deep_translator", fake_dt)
    return target


def _fake_batch(calls: list[list[str]], failing: set[str]) -> Any:
    def translate(phrases: list[str], *_args: Any, **_kwargs: Any) -> list[str | None]:
        calls.append(list(phrases))
        return [None if p in failing else f"zz {p}" for p in phrases]

    return translate


def test_m12_failed_fields_are_recorded_and_only_they_are_retried(
    cache_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(i18n, "_translate_batch", _fake_batch(calls, {"email"}))

    first = i18n.generate_language("es")
    assert first["failed_fields"] == ["email"]
    assert "email" not in first["fields"]
    on_disk = json.loads((cache_dir / "es.json").read_text(encoding="utf-8"))
    assert on_disk["failed_fields"] == ["email"]

    calls.clear()
    monkeypatch.setattr(i18n, "_translate_batch", _fake_batch(calls, set()))
    second = i18n.generate_language("es")
    assert calls == [["email"]]
    assert "failed_fields" not in second
    assert second["fields"]["email"]

    # Complete now: the cache is returned without translating anything.
    calls.clear()
    assert i18n.generate_language("es")["fields"] == second["fields"]
    assert calls == []


def test_m12_cli_prints_n_of_m_fields_and_exits_2(
    cache_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(i18n, "_translate_batch", _fake_batch([], {"email"}))
    monkeypatch.setattr(i18n.sys, "argv", ["i18n", "--languages", "es"])

    with pytest.raises(SystemExit) as exit_info:
        i18n.main()

    assert exit_info.value.code == 2
    out = capsys.readouterr().out
    total = len(i18n._derive_field_phrases(i18n._load_master()))
    assert f"[es] Spanish: {total - 1} of {total} fields," in out
    assert "; 1 failed (email)" in out
    assert "Incomplete 1 language(s): es; run again to retry the failed fields." in out
    assert "Done." not in out


def test_m12_translate_timeout_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    release = threading.Event()

    class HangingTranslator:
        def __init__(self, **kwargs: Any) -> None:
            assert "timeout" not in kwargs

        def translate_batch(self, phrases: list[str]) -> list[str]:
            release.wait(10)
            return list(phrases)

        def translate(self, phrase: str) -> str:
            release.wait(10)
            return phrase

    fake_dt = types.ModuleType("deep_translator")
    fake_dt.GoogleTranslator = HangingTranslator  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "deep_translator", fake_dt)

    started = time.monotonic()
    try:
        results = i18n._translate_batch(
            ["hello", "world"], "es", timeout=0.05, retries=0, retry_backoff=0
        )
    finally:
        release.set()
    assert results == [None, None]
    assert time.monotonic() - started < 5


def test_c5_rolodexter_cache_dir_is_read_and_written(cache_dir: Path) -> None:
    assert i18n.get_cache_dir() == cache_dir
    assert cache_dir.is_dir()
    pack = {
        "language_code": "es",
        "language_name": "Spanish",
        "fields": {"email": ["correo electronico"]},
    }
    (cache_dir / "es.json").write_text(json.dumps(pack), encoding="utf-8")
    assert i18n.load_cached("es") == pack
    assert cache_dir in i18n.get_all_cache_dirs()


def test_l24_unknown_retranslate_fields_are_a_usage_error(
    cache_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        i18n.sys,
        "argv",
        ["i18n", "--languages", "es", "--retranslate-fields", "email,emial,score"],
    )
    with pytest.raises(SystemExit) as exit_info:
        i18n.main()
    assert exit_info.value.code == 2
    err = capsys.readouterr().err
    assert (
        "error: argument --retranslate-fields: unknown or untranslated field(s): "
        "'emial', 'score'"
    ) in err


def test_l24_dry_run_works_without_deep_translator(
    cache_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    original_import = builtins.__import__

    def block(name: str, *args: Any, **kwargs: Any) -> Any:
        if "deep_translator" in name:
            raise ImportError("not installed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", block)
    monkeypatch.delitem(sys.modules, "deep_translator", raising=False)
    monkeypatch.setattr(i18n.sys, "argv", ["i18n", "--languages", "es", "--dry-run"])

    i18n.main()

    out = capsys.readouterr().out
    assert "[es] Spanish: would generate (0 fields)" in out
    assert "Done." in out
