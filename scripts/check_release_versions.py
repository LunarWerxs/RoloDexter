from __future__ import annotations

import json
import os
import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_json = json.loads(
        (ROOT / "packages/js/package.json").read_text(encoding="utf-8")
    )
    python_version = pyproject["project"]["version"]
    npm_version = package_json["version"]
    errors: list[str] = []

    if python_version != npm_version:
        errors.append(
            f"Python version {python_version!r} does not match NPM version "
            f"{npm_version!r}"
        )

    # packages/js/src/index.ts hardcodes the version it reports from
    # `rolodexter --version` and from the exported `version`/`__version__`.
    # Nothing compared it to package.json, so 2.11.0 shipped to npm reporting
    # itself as 2.10.0. Python reads its version from importlib.metadata and
    # cannot drift this way; the JS literal can, so check it here.
    index_ts = (ROOT / "packages/js/src/index.ts").read_text(encoding="utf-8")
    match = re.search(r'^export const version = "([^"]+)";', index_ts, re.MULTILINE)
    if match is None:
        errors.append(
            "could not find `export const version = \"...\"` in "
            "packages/js/src/index.ts"
        )
    elif match.group(1) != npm_version:
        errors.append(
            f"packages/js/src/index.ts version {match.group(1)!r} does not match "
            f"NPM version {npm_version!r}"
        )

    ref_type = os.environ.get("GITHUB_REF_TYPE")
    ref_name = os.environ.get("GITHUB_REF_NAME")
    if ref_type == "tag" and ref_name:
        tag_version = ref_name.removeprefix("v")
        if tag_version != python_version:
            errors.append(
                f"release tag {ref_name!r} does not match package version "
                f"{python_version!r}"
            )

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(f"release versions match: {python_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
