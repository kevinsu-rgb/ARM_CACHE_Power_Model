"""Load the project's ``.env`` file into ``os.environ``.

Format (kept identical to the loader in ``src/run_gem5.sh``):

* one ``KEY=VALUE`` per line, optionally prefixed with ``export``;
* blank lines and lines starting with ``#`` are ignored (no inline comments,
  so a ``#`` inside a value is kept);
* whitespace around the key and the value is stripped, and one pair of
  matching single or double quotes around the value is removed;
* no expansion: ``$VAR`` and ``~`` stay literal.

Variables that are already set in the environment take precedence and are
left unchanged. A missing file is not an error.
"""
from __future__ import annotations

import os
import re
from collections.abc import MutableMapping
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"

_LINE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")


class EnvFileError(ValueError):
    """A line in the .env file is not ``KEY=VALUE``."""


def parse_env_file(path: Path) -> dict[str, str]:
    """Return the ``KEY=VALUE`` pairs of ``path`` in file order."""
    values: dict[str, str] = {}
    for n, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE.match(line)
        if not m:
            raise EnvFileError(f"{path}:{n}: expected KEY=VALUE, got: {raw!r}")
        key, value = m.group(1), m.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key] = value
    return values


def load_env(path: Path | None = None,
             environ: MutableMapping[str, str] = os.environ) -> dict[str, str]:
    """Set every variable from the .env file that ``environ`` does not have.

    Returns the variables that were set. ``path`` defaults to
    ``<project>/.env``.
    """
    path = DEFAULT_ENV_FILE if path is None else Path(path)
    if not path.is_file():
        return {}
    applied = {k: v for k, v in parse_env_file(path).items() if k not in environ}
    environ.update(applied)
    return applied
