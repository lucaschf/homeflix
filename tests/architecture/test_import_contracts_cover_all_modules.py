"""The import-linter contracts see every bounded context and every file in it.

``lint-imports`` (ADR-037) only checks what it is told about, and it fails
open in two quiet ways:

* the contracts in ``pyproject.toml`` list the bounded contexts by name, so a
  new module under ``src/modules/`` is outside both contracts until someone
  remembers to add it;
* grimp, the graph builder behind import-linter, skips directories without an
  ``__init__.py``. A namespace package inside a module is invisible, and so is
  every import made from it. When the contracts were introduced, 18 such
  directories existed (all of ``preferences`` and most of ``library``).

Either gap leaves the build green while the boundary is unguarded. This test
closes both: the module list of each contract must equal the directories
under ``src/modules/``, and every directory holding Python code there must be
a regular package.
"""

import tomllib
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_MODULES = _ROOT / "src" / "modules"


def _bounded_contexts() -> set[str]:
    return {
        f"src.modules.{path.name}"
        for path in _MODULES.iterdir()
        if path.is_dir() and not path.name.startswith(("_", "."))
    }


def _contracts() -> list[dict[str, object]]:
    config = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    contracts: list[dict[str, object]] = config["tool"]["importlinter"]["contracts"]
    return contracts


@pytest.mark.unit
@pytest.mark.parametrize("contract", _contracts(), ids=lambda c: str(c["name"]))
def test_contract_lists_every_bounded_context(contract: dict[str, object]) -> None:
    """Each contract names exactly the modules that exist under ``src/modules``."""
    listed = contract.get("modules") or contract.get("containers")
    assert isinstance(listed, list)

    assert set(listed) == _bounded_contexts()


@pytest.mark.unit
def test_every_module_directory_is_a_regular_package() -> None:
    """No directory with Python code under ``src/modules`` lacks ``__init__.py``."""
    missing = sorted(
        str(directory.relative_to(_ROOT))
        for directory in _MODULES.rglob("*")
        if directory.is_dir()
        and directory.name != "__pycache__"
        and any(directory.rglob("*.py"))
        and not (directory / "__init__.py").exists()
    )

    assert missing == []
