"""``[tool.sevlint]`` in pyproject.toml, or a top-level table in .sevlint.toml."""
from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]

KEYS = {"odoo", "caller", "modules", "names", "disable", "target-python"}


class ConfigError(ValueError):
    pass


def find(start: Path) -> Path | None:
    start = start if start.is_dir() else start.parent
    for parent in [start, *start.parents]:
        dotfile = parent / ".sevlint.toml"
        if dotfile.is_file():
            return dotfile
        pyproject = parent / "pyproject.toml"
        if pyproject.is_file() and "[tool.sevlint]" in pyproject.read_text(encoding="utf-8", errors="replace"):
            return pyproject
    return None


def load(path: Path) -> dict:
    if tomllib is None:
        raise ConfigError(f"{path}: reading config needs Python 3.11+ or the 'tomli' package")
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    if path.name == "pyproject.toml":
        data = data.get("tool", {}).get("sevlint", {})
    unknown = set(data) - KEYS
    if unknown:
        raise ConfigError(f"{path}: unknown key(s) {', '.join(sorted(unknown))}")
    for key in ("modules", "names", "disable"):
        if key in data and not (isinstance(data[key], list) and all(isinstance(v, str) for v in data[key])):
            raise ConfigError(f"{path}: '{key}' must be a list of strings")
    return data
