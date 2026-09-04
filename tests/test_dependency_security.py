from __future__ import annotations

from pathlib import Path

import idna
import pytest

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def locked_version(package_name: str) -> tuple[int, ...]:
    lock = tomllib.loads((REPOSITORY_ROOT / "uv.lock").read_text("utf-8"))
    package = next(
        package for package in lock["package"] if package["name"] == package_name
    )
    return tuple(int(part) for part in package["version"].split("."))


def test_lock_uses_patched_dependency_floors_and_registry_sources() -> None:
    lock = tomllib.loads((REPOSITORY_ROOT / "uv.lock").read_text("utf-8"))
    assert locked_version("idna") >= (3, 15)
    assert locked_version("pygments") >= (2, 20, 0)

    for package in lock["package"]:
        source = package.get("source", {})
        assert "git" not in source, package["name"]
        assert "url" not in source, package["name"]
        assert "path" not in source, package["name"]
        if registry := source.get("registry"):
            assert registry == "https://pypi.org/simple"


def test_idna_rejects_hostile_contextual_input_and_keeps_valid_domains() -> None:
    with pytest.raises(idna.IDNAError):
        idna.encode("a" * 100_000 + "\u200d")

    assert idna.encode("münchen.de") == b"xn--mnchen-3ya.de"
