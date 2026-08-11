"""Anonymous install/usage ping for the ``rolodexter`` CLI. See SECURITY.md.

Fires at most once per 24h, and only from the CLI entry point in
``__main__.py`` — never on ``import rolodexter``, so embedding the library in
a script, notebook, or pipeline stays exactly as network-silent as it always
was. The request carries nothing but a random per-install id, the running
version, and a coarse OS tag; it never touches contact data.

The endpoint relays GitHub's ``releases/latest`` JSON for this repo verbatim,
so the same request doubles as the CLI's update check — there is no separate
``api.github.com`` call anywhere in this package.

Always fire-and-forget: the HTTP call runs on a daemon thread so it can never
delay or block the command the user actually ran, it carries a hard 5s
timeout, every failure is swallowed, and there is no retry loop. Opt out with
``ROLODEXTER_NO_PING=1``; it is also skipped automatically under pytest and
common CI environments.
"""

from __future__ import annotations

import json
import os
import platform
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

PING_URL = "https://studio.connections.icu/v1/app/rolodexter/latest"

_TIMEOUT_SECS = 5
_THROTTLE_SECS = 24 * 60 * 60
_STATE_FILENAME = "ping-state.json"


def _state_dir() -> Path:
    """Per-user config directory, following each OS's own convention."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "rolodexter"


def _load_state() -> dict[str, Any]:
    try:
        raw = (_state_dir() / _STATE_FILENAME).read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(state: dict[str, Any]) -> None:
    # Best-effort: a failed write just means the next run pings again, which
    # is the safe direction to fail in (never crashes, never spams).
    try:
        state_dir = _state_dir()
        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / _STATE_FILENAME
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def _os_tag() -> str:
    """A coarse, non-identifying OS tag, e.g. ``win11-26100`` or ``linux``."""
    system = platform.system()
    if system == "Windows":
        try:
            build = int(platform.version().rsplit(".", maxsplit=1)[-1])
        except (ValueError, IndexError):
            return "windows"
        generation = "win11" if build >= 22000 else "win10"
        return f"{generation}-{build}"
    if system == "Darwin":
        return "macos"
    if system == "Linux":
        return "linux"
    return system.lower() or "unknown"


def _disabled() -> bool:
    if os.environ.get("ROLODEXTER_NO_PING") == "1":
        return True
    # Dev/test/CI runs never ping: pytest stamps this for every test process,
    # and CI/GITHUB_ACTIONS are the conventional signals every major CI
    # provider (including GitHub Actions) sets.
    if os.environ.get("PYTEST_CURRENT_TEST") is not None:
        return True
    return bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))


def _send(install_id: str, version: str, *, new_install: bool) -> bool:
    query = f"v={version}&os={_os_tag()}"
    if new_install:
        query += "&new=1"
    request = Request(  # fixed https URL, never user input
        f"{PING_URL}?{query}", headers={"X-Install-Id": install_id}
    )
    try:
        with urlopen(request, timeout=_TIMEOUT_SECS) as response:
            status = int(response.status)
            return 200 <= status < 300
    except Exception:  # fire-and-forget: any failure is silent, never raised
        return False


def _worker(state: dict[str, Any], version: str) -> None:
    try:
        install_id = state.get("install_id")
        if not isinstance(install_id, str) or not install_id:
            install_id = str(uuid.uuid4())
            state["install_id"] = install_id
        new_install = not state.get("reported", False)
        ok = _send(install_id, version, new_install=new_install)
        if ok and new_install:
            state["reported"] = True
        _save_state(state)
    except Exception:  # background thread must never crash the app
        pass


def maybe_ping(version: str) -> None:
    """Fire the anonymous install ping in the background, at most once/24h.

    Safe to call unconditionally from the CLI entry point: every failure mode
    (disk, network, clock, a bug in this module) is swallowed here so a ping
    can never be the reason a command fails.
    """
    try:
        if _disabled():
            return
        state = _load_state()
        last_ping = state.get("last_ping")
        if isinstance(last_ping, (int, float)) and (
            time.time() - last_ping
        ) < _THROTTLE_SECS:
            return
        # Stamp before the request completes so a second command invoked
        # moments later (before this one's background thread finishes) does
        # not also queue a duplicate ping.
        state["last_ping"] = time.time()
        _save_state(state)
        threading.Thread(target=_worker, args=(state, version), daemon=True).start()
    except Exception:  # never let telemetry break the CLI
        pass
