"""Shared pytest fixtures."""
import os
import subprocess
import warnings
from pathlib import Path

import pytest

from power.envfile import load_env

# Fill tool locations from <project>/.env before any fixture reads them;
# variables exported in the shell take precedence.
load_env()

GEM5_TIMEOUT_S = 1800


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def gem5_bin() -> Path:
    return _require_env("GEM5_BIN", "gem5 binary")


def _require_env(name: str, what: str) -> Path:
    """Path from env var `name`; warn and skip if unset or missing."""
    env = os.environ.get(name)
    if not env:
        msg = f"{name} is not set ({what}); skipping"
        warnings.warn(msg)
        pytest.skip(msg)
    path = Path(env)
    if not path.exists():
        msg = f"{what} not found: {path} (from {name}); skipping"
        warnings.warn(msg)
        pytest.skip(msg)
    return path


@pytest.fixture(scope="session")
def gem5_root() -> Path:
    return _require_env("GEM5_ROOT", "gem5 checkout")


@pytest.fixture
def run_gem5(gem5_bin, gem5_root, mcpat_bin, project_root):
    def _run(args: list[str], outdir: Path, cwd: Path) -> subprocess.CompletedProcess:
        cmd = [str(gem5_bin), "-d", str(outdir),
               str(project_root / "src/main.py"),
               "--gem5_root", str(gem5_root), "--mcpat_bin", str(mcpat_bin), *args]
        return subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True,
            timeout=GEM5_TIMEOUT_S,
        )

    return _run


@pytest.fixture(scope="session")
def mcpat_bin() -> Path:
    return _require_env("MCPAT_BIN", "McPAT binary")
