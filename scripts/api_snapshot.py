"""Golden public-API snapshots for both packages, with a breaking-change verdict.

The behavioral tests and parity probes pin what the mappers *do*; nothing
pinned what the packages *export*.  A release could drop a method, re-shape an
options interface or rename a ``CanonicalField`` member, and every import of it
in a caller's code would break on upgrade with no test noticing.  This renders
the public surface of ``rolodexter``, ``rolodexter.core`` and
``rolodexter.i18n`` in Python, and of the npm package's three entry points
(through ``packages/js/scripts/api-surface.mjs``), into reviewable goldens:

* ``scripts/api_golden/<lang>/<module>/<Name>.txt``: one file per export, so an
  API change is a file diff a reviewer reads before release.
* ``scripts/api_golden/<lang>/_types/<Name>.txt``: the non-exported types an
  export's signature reaches, so a change deep in a shared type is visible too.
* ``scripts/api_golden/<lang>.json``: an 8-character hash per export and per
  member.  Each hash covers the entry's own text and every local type it
  depends on, transitively, so a change in ``MappingResult`` re-hashes
  ``ContactMapper.map_payload`` that returns it.

Comparing the hashes gives a verdict CI can gate on: a name that disappeared
is BREAKING, a changed hash is POTENTIALLY_BREAKING, a new name is
POTENTIALLY_NON_BREAKING.  Renaming a canonical field removes a member in
both languages at once, so it reads as BREAKING twice.

    python scripts/api_snapshot.py                   # fails on any API change
    python scripts/api_snapshot.py --update-goldens  # accept a deliberate one
    python scripts/api_snapshot.py --json            # machine-readable report
    python scripts/api_snapshot.py --lang python     # skip the Node half

``--update-goldens`` writes, rewrites or deletes exactly the affected files.
The idea follows TensorFlow's api_compatibility_test (Apache-2.0) and React
Native's per-export API hashes (MIT); the code is written fresh for this repo.
"""

from __future__ import annotations

import argparse
import dataclasses
import enum
import hashlib
import importlib
import inspect
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = Path(__file__).with_name("api_golden")
JS_SURFACE = ROOT / "packages" / "js" / "scripts" / "api-surface.mjs"
MODULES = ("rolodexter", "rolodexter.core", "rolodexter.i18n")
LANGS = ("python", "js")
TYPES_DIR = "_types"

BREAKING = "BREAKING"
POTENTIALLY_BREAKING = "POTENTIALLY_BREAKING"
POTENTIALLY_NON_BREAKING = "POTENTIALLY_NON_BREAKING"

# Dunder methods that are part of how a caller uses a class; every other
# underscore name is private by the package's own convention.
PUBLIC_DUNDERS = frozenset(
    {
        "__init__",
        "__call__",
        "__iter__",
        "__len__",
        "__getitem__",
        "__contains__",
        "__enter__",
        "__exit__",
    }
)
MAX_VALUE_REPR = 200
_IDENTIFIER = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_ADDRESS = re.compile(r" at 0x[0-9A-Fa-f]+")


# ── Hashing and diffing (language-neutral) ────────────────────────────────


def _closure(text: str, refs: list[str], types: dict[str, Any], own: str) -> list[str]:
    """Every local type ``text`` names, and every type those name, in order."""
    seen: set[str] = set()
    pending = [*_IDENTIFIER.findall(text), *refs]
    while pending:
        name = pending.pop()
        if name == own or name in seen or name not in types:
            continue
        seen.add(name)
        pending.extend(_IDENTIFIER.findall(types[name]["text"]))
        pending.extend(types[name].get("refs", []))
    return sorted(seen)


def api_hash(text: str, deps: list[str], types: dict[str, Any]) -> str:
    """8-char sha256 over a declaration plus the declarations it depends on."""
    digest = hashlib.sha256(text.encode("utf-8"))
    for name in deps:
        digest.update(f"\n{name}\n{types[name]['text']}".encode())
    return digest.hexdigest()[:8]


def build_manifest(surface: dict[str, Any]) -> tuple[dict[str, dict[str, str]], set[str]]:
    """Hash every export and member; also return the local types they reach."""
    types = surface["types"]
    manifest: dict[str, dict[str, str]] = {}
    reached: set[str] = set()
    for module, exports in surface["modules"].items():
        hashes: dict[str, str] = {}
        for name, entry in exports.items():
            deps = _closure(entry["text"], entry.get("refs", []), types, name)
            reached.update(deps)
            hashes[name] = api_hash(entry["text"], deps, types)
            for member, line in entry.get("members", {}).items():
                member_deps = _closure(line, [], types, name)
                hashes[f"{name}.{member}"] = api_hash(line, member_deps, types)
        manifest[module] = dict(sorted(hashes.items()))
    return manifest, reached


def diff_manifests(
    golden: dict[str, dict[str, str]], live: dict[str, dict[str, str]]
) -> list[tuple[str, str, str]]:
    """``(verdict, module, name)`` for every entry that differs, sorted."""
    changes: list[tuple[str, str, str]] = []
    for module in sorted(set(golden) | set(live)):
        before = golden.get(module, {})
        after = live.get(module, {})
        for name in sorted(set(before) | set(after)):
            if name not in after:
                changes.append((BREAKING, module, name))
            elif name not in before:
                changes.append((POTENTIALLY_NON_BREAKING, module, name))
            elif before[name] != after[name]:
                changes.append((POTENTIALLY_BREAKING, module, name))
    return changes


def suggested_bump(changes: list[tuple[str, str, str]]) -> str:
    verdicts = {verdict for verdict, _, _ in changes}
    if BREAKING in verdicts:
        return "major"
    if POTENTIALLY_BREAKING in verdicts:
        return "review (major if a caller can observe the change, else minor)"
    if POTENTIALLY_NON_BREAKING in verdicts:
        return "minor"
    return "none"


def golden_files(
    surface: dict[str, Any], manifest: dict[str, dict[str, str]], reached: set[str]
) -> dict[str, str]:
    """Relative path -> content for every golden text file of one language."""
    files: dict[str, str] = {}
    exported = {name for exports in surface["modules"].values() for name in exports}
    for module, exports in surface["modules"].items():
        names = _file_names(exports)
        for name, entry in exports.items():
            header = f"# {module}.{name}  api-hash {manifest[module][name]}\n"
            files[f"{module}/{names[name]}.txt"] = header + entry["text"] + "\n"
    hidden = sorted(reached - exported)
    names = _file_names(hidden)
    for name in hidden:
        files[f"{TYPES_DIR}/{names[name]}.txt"] = surface["types"][name]["text"] + "\n"
    return files


def _file_names(names: Any) -> dict[str, str]:
    # Windows and macOS fold case, so ``Foo`` and ``foo`` must not share a
    # file: a name whose folded form collides gets a stable suffix.
    folded: dict[str, int] = {}
    for name in names:
        folded[name.casefold()] = folded.get(name.casefold(), 0) + 1
    return {
        name: name
        if folded[name.casefold()] == 1
        else f"{name}~{hashlib.sha256(name.encode()).hexdigest()[:6]}"
        for name in names
    }


# ── Python surface ────────────────────────────────────────────────────────


class _Annotation:
    """Prints a string annotation bare, as it reads in the source."""

    def __init__(self, text: str) -> None:
        self.text = text

    def __repr__(self) -> str:
        return self.text


def _annotation(value: Any) -> Any:
    if value is inspect.Parameter.empty:
        return value
    return _Annotation(value if isinstance(value, str) else inspect.formatannotation(value))


def _stable_repr(value: Any) -> str:
    # Set order follows the per-process string hash seed; sort it away.
    if isinstance(value, (set, frozenset)):
        return f"{type(value).__name__}({{{', '.join(sorted(map(_stable_repr, value)))}}})"
    if isinstance(value, dict):
        items = ", ".join(f"{_stable_repr(k)}: {_stable_repr(v)}" for k, v in value.items())
        return f"{{{items}}}"
    if isinstance(value, (list, tuple)):
        body = ", ".join(_stable_repr(v) for v in value)
        return f"[{body}]" if isinstance(value, list) else f"({body}{',' if len(value) == 1 else ''})"
    return _ADDRESS.sub("", repr(value))


def _signature(func: Any) -> str:
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return "(...)"
    params = [
        p.replace(
            annotation=_annotation(p.annotation),
            default=p.default if p.default is p.empty else _Annotation(_stable_repr(p.default)),
        )
        for p in sig.parameters.values()
    ]
    return str(sig.replace(parameters=params, return_annotation=_annotation(sig.return_annotation)))


def _returns(func: Any) -> str:
    try:
        annotation = inspect.signature(func).return_annotation
    except (TypeError, ValueError):
        return ""
    return "" if annotation is inspect.Signature.empty else repr(_annotation(annotation))


def _is_public(name: str) -> bool:
    return not name.startswith("_") or name in PUBLIC_DUNDERS


def _is_own(obj: Any) -> bool:
    return str(getattr(obj, "__module__", "") or "").startswith("rolodexter")


def _member_line(name: str, attr: Any) -> str:
    if isinstance(attr, staticmethod):
        return f"@staticmethod def {name}{_signature(attr.__func__)}"
    if isinstance(attr, classmethod):
        return f"@classmethod def {name}{_signature(attr.__func__)}"
    if isinstance(attr, property):
        returns = _returns(attr.fget) if attr.fget else ""
        setter = " (settable)" if attr.fset else ""
        return f"@property {name} -> {returns}{setter}"
    if isinstance(attr, dataclasses.Field):
        default = "" if attr.default is dataclasses.MISSING else f" = {_stable_repr(attr.default)}"
        if attr.default_factory is not dataclasses.MISSING:
            default = " = <factory>"
        return f"{name}: {_annotation(attr.type)!r}{default}"
    if inspect.isfunction(attr):
        return f"def {name}{_signature(attr)}"
    shown = _stable_repr(attr)
    value = f" = {shown}" if len(shown) <= MAX_VALUE_REPR else ""
    return f"{name}: {type(attr).__name__}{value}"


def _class_members(cls: type) -> dict[str, str]:
    attrs: dict[str, Any] = {}
    # Base first, so an override replaces what it overrides.
    for klass in reversed(cls.__mro__):
        if klass is cls or _is_own(klass):
            attrs.update({k: v for k, v in vars(klass).items() if _is_public(k)})
    if dataclasses.is_dataclass(cls):
        attrs.update({f.name: f for f in dataclasses.fields(cls) if _is_public(f.name)})
    if issubclass(cls, enum.Enum):
        for name in cls.__members__:
            attrs.pop(name, None)
        members = {name: f"{name} = {member.value!r}" for name, member in cls.__members__.items()}
    else:
        members = {}
    for name, attr in attrs.items():
        if type(attr).__name__ in {"member_descriptor", "getset_descriptor"}:
            continue  # slot storage behind a dataclass field, already listed
        members[name] = _member_line(name, attr)
    return dict(sorted(members.items()))


def _base_name(base: type, name: str) -> str:
    # The public ContactMapper extends a private one of the same name.
    if base.__name__ == name:
        return f"{base.__module__}.{base.__qualname__}"
    if _is_own(base) or base.__module__ == "builtins":
        return base.__qualname__
    return f"{base.__module__}.{base.__qualname__}"


def render_python(name: str, obj: Any) -> dict[str, Any]:
    members: dict[str, str] = {}
    if inspect.isclass(obj) and _is_own(obj):
        lines = []
        params = getattr(obj, "__dataclass_params__", None)
        if params is not None:
            lines.append(f"@dataclass(frozen={params.frozen})")
        bases = ", ".join(_base_name(b, name) for b in obj.__bases__ if b is not object)
        lines.append(f"class {name}({bases})" if bases else f"class {name}")
        members = _class_members(obj)
    elif (inspect.isclass(obj) or callable(obj)) and not _is_own(obj):
        # Re-exported from a dependency: its internals are not ours to pin.
        lines = [f"{name} = {getattr(obj, '__module__', '?')}.{getattr(obj, '__qualname__', '?')}"]
    elif callable(obj):
        lines = [f"def {name}{_signature(obj)}"]
    else:
        shown = _stable_repr(obj)
        value = f" = {shown}" if len(shown) <= MAX_VALUE_REPR else ""
        lines = [f"{name}: {type(obj).__name__}{value}"]
        if isinstance(obj, dict):
            members = {str(k): f"{k!s}: {_stable_repr(v)}" for k, v in obj.items()}
    lines.extend(f"  {line}" for line in members.values())
    return {"text": "\n".join(lines), "refs": [], "members": members}


def python_surface() -> dict[str, Any]:
    sys.path.insert(0, str(ROOT / "src"))
    modules: dict[str, Any] = {}
    for module_name in MODULES:
        module = importlib.import_module(module_name)
        modules[module_name] = {
            name: render_python(name, getattr(module, name))
            for name in sorted(module.__all__)
        }
    types: dict[str, Any] = {}
    for module_name, module in sorted(sys.modules.items()):
        if module_name.split(".")[0] != "rolodexter" or module is None:
            continue
        for name, obj in sorted(vars(module).items()):
            if inspect.isclass(obj) and _is_own(obj) and name not in types:
                types[name] = render_python(name, obj)
    return {"modules": modules, "types": types}


def js_surface() -> dict[str, Any]:
    completed = subprocess.run(
        ["node", str(JS_SURFACE)],
        cwd=str(JS_SURFACE.parents[1]),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(f"api-surface.mjs failed:\n{completed.stderr}")
    return json.loads(completed.stdout)


# ── Goldens on disk ───────────────────────────────────────────────────────


def _read_files(lang_dir: Path) -> dict[str, str]:
    if not lang_dir.is_dir():
        return {}
    return {
        path.relative_to(lang_dir).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(lang_dir.rglob("*.txt"))
    }


def _write_goldens(lang: str, manifest: dict[str, Any], files: dict[str, str]) -> int:
    """Write, rewrite or delete exactly the files that differ; count them."""
    lang_dir = GOLDEN_DIR / lang
    on_disk = _read_files(lang_dir)
    touched = 0
    for rel in sorted(set(on_disk) - set(files)):
        (lang_dir / rel).unlink()
        touched += 1
    for rel, content in sorted(files.items()):
        if on_disk.get(rel) != content:
            target = lang_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
            touched += 1
    for folder in sorted(lang_dir.rglob("*"), reverse=True):
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
    manifest_path = GOLDEN_DIR / f"{lang}.json"
    text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if not manifest_path.exists() or manifest_path.read_text(encoding="utf-8") != text:
        manifest_path.write_text(text, encoding="utf-8", newline="\n")
        touched += 1
    return touched


def snapshot(lang: str, update: bool) -> dict[str, Any]:
    surface = python_surface() if lang == "python" else js_surface()
    live, reached = build_manifest(surface)
    files = golden_files(surface, live, reached)
    manifest_path = GOLDEN_DIR / f"{lang}.json"
    golden = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    on_disk = _read_files(GOLDEN_DIR / lang)
    stale = sorted(rel for rel in set(on_disk) | set(files) if on_disk.get(rel) != files.get(rel))
    report: dict[str, Any] = {
        "changes": [
            {"verdict": verdict, "module": module, "name": name}
            for verdict, module, name in diff_manifests(golden, live)
        ],
        "stale_files": stale,
    }
    if update:
        report["files_written"] = _write_goldens(lang, live, files)
    return report


def _parity_key(name: str) -> str:
    # Python members are snake_case and JS ones camelCase (map_payload vs
    # mapPayload); fold both so one change in both packages reads as one.
    return name.replace("_", "").casefold()


def _parity_notes(reports: dict[str, Any]) -> list[str]:
    """Changes one package made that its counterpart did not make."""
    seen: dict[tuple[str, str], dict[str, str]] = {}
    shown: dict[tuple[str, str], str] = {}
    for lang, report in reports.items():
        for change in report["changes"]:
            key = (change["module"], _parity_key(change["name"]))
            seen.setdefault(key, {})[lang] = change["verdict"]
            shown.setdefault(key, change["name"])
    if len(reports) < 2:
        return []
    return [
        f"{key[0]} {shown[key]}: " + ", ".join(f"{lang} {verdicts.get(lang, 'unchanged')}" for lang in reports)
        for key, verdicts in sorted(seen.items())
        if len(set(verdicts.values())) != 1 or len(verdicts) != len(reports)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--update-goldens", action="store_true", help="accept the current API as the golden")
    parser.add_argument("--lang", choices=[*LANGS, "both"], default="both", help="which package to snapshot")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args()

    langs = LANGS if args.lang == "both" else (args.lang,)
    reports = {lang: snapshot(lang, args.update_goldens) for lang in langs}
    all_changes = [
        (c["verdict"], c["module"], c["name"]) for report in reports.values() for c in report["changes"]
    ]
    summary = {
        "languages": reports,
        "parity": _parity_notes(reports),
        "suggested_bump": suggested_bump(all_changes),
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        for lang, report in reports.items():
            counts = {v: 0 for v in (BREAKING, POTENTIALLY_BREAKING, POTENTIALLY_NON_BREAKING)}
            for change in report["changes"]:
                counts[change["verdict"]] += 1
            print(f"{lang}: " + ", ".join(f"{n} {v}" for v, n in counts.items()))
            for change in report["changes"]:
                print(f"  {change['verdict']:<26} {change['module']} {change['name']}")
            if report["stale_files"] and not report["changes"]:
                print(f"  {len(report['stale_files'])} golden file(s) out of date")
            if "files_written" in report:
                print(f"  wrote {report['files_written']} golden file(s)")
        for note in summary["parity"]:
            print(f"parity: {note}")
        print(f"suggested bump: {summary['suggested_bump']}")
    if args.update_goldens:
        return 0
    drift = any(report["changes"] or report["stale_files"] for report in reports.values())
    if drift:
        print("API changed: review the diff, then run scripts/api_snapshot.py --update-goldens", file=sys.stderr)
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
