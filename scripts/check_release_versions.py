from __future__ import annotations

import json
import os
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
