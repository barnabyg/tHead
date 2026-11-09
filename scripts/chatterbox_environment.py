"""Verify exact prepared dependencies and source packages without loading the model."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import re
import sysconfig
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "docs/runtime/chatterbox/requirements-maintained.lock"
RUNTIME_LOCK = ROOT / "chatterbox-maintained-lock.json"


def canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def expected_inventory(lock: dict[str, Any]) -> dict[str, str]:
    result = {}
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or line[0].isspace():
            continue
        if match := re.fullmatch(r"([A-Za-z0-9._-]+)==([A-Za-z0-9.+!-]+)\s*\\?", line):
            name, version = match.groups()
        elif line.startswith("torch @ https://"):
            name, version = "torch", lock["torch"]
        else:
            raise ValueError("Cannot verify a non-exact dependency declaration")
        name = canonical_name(name)
        if name in result:
            raise ValueError(f"Duplicate locked dependency: {name}")
        result[name] = version
    for project in lock["source_projects"]:
        name = canonical_name(project["name"])
        if name in result:
            raise ValueError(f"Source project collides with a locked wheel: {name}")
        result[name] = project["version"]
    return result


def check_inventory(lock: dict[str, Any]) -> None:
    if platform.python_version() != lock["python"]:
        raise ValueError("Python differs from the selected runtime pin")
    actual = {}
    for distribution in importlib.metadata.distributions():
        name = canonical_name(distribution.metadata["Name"])
        if name in actual:
            raise ValueError(f"Duplicate installed distribution: {name}")
        actual[name] = distribution.version
    expected = expected_inventory(lock)
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        changed = sorted(
            name for name in actual.keys() & expected if actual[name] != expected[name]
        )
        raise ValueError(
            f"Dependency inventory differs (missing={missing}, extra={extra}, changed={changed})"
        )


def package_files(directory: Path) -> dict[str, Path]:
    return {
        path.relative_to(directory).as_posix(): path
        for path in directory.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }


def check_sources(state: Path, lock: dict[str, Any]) -> None:
    site = Path(sysconfig.get_paths()["purelib"])
    for project in lock["source_projects"]:
        source = package_files(state / project["directory"] / "src" / project["package"])
        installed = package_files(site / project["package"])
        if not source or source.keys() != installed.keys():
            raise ValueError(f"Installed {project['name']} files differ from the pinned source")
        for name, path in source.items():
            if digest(path) != digest(installed[name]):
                raise ValueError(f"Installed {project['name']} content differs: {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()
    checkpoint = args.state / "prepared-environment.json"
    try:
        lock = json.loads(RUNTIME_LOCK.read_text(encoding="utf-8"))
        pins = {
            "requirements_sha256": digest(REQUIREMENTS),
            "runtime_lock_sha256": digest(RUNTIME_LOCK),
        }
        if not args.record and (
            not checkpoint.is_file() or json.loads(checkpoint.read_text(encoding="utf-8")) != pins
        ):
            raise ValueError("Package pins changed or have not been verified in this state")
        check_inventory(lock)
        check_sources(args.state, lock)
        if args.record:
            temporary = checkpoint.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(pins, indent=2) + "\n", encoding="utf-8")
            temporary.replace(checkpoint)
        print(
            "Verified exact dependency inventory and installed source files; no reinstall required."
        )
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Candidate needs strict preparation: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
