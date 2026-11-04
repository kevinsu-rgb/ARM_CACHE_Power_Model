"""Shared pytest fixtures."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

DEFAULT_GEM5_BIN = "/home/kevin/Projects/gem5/build/ARM/gem5.opt"
GEM5_TIMEOUT_S = 1800


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def gem5_bin() -> Path:
    path = Path(os.environ.get("GEM5_BIN", DEFAULT_GEM5_BIN))
    if not path.exists():
        pytest.skip(f"gem5 binary not found: {path}")
    return path


@pytest.fixture
def run_gem5(gem5_bin, project_root):
    def _run(args: list[str], outdir: Path, cwd: Path) -> subprocess.CompletedProcess:
        cmd = [str(gem5_bin), "-d", str(outdir),
               str(project_root / "src/main.py"), *args]
        return subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True,
            timeout=GEM5_TIMEOUT_S,
        )

    return _run


@pytest.fixture(scope="session")
def mcpat_bin(project_root) -> Path:
    env = os.environ.get("MCPAT_BIN")
    path = Path(env) if env else project_root / "tools/mcpat/mcpat"
    if not path.exists():
        pytest.skip(f"mcpat binary not found: {path}")
    return path
