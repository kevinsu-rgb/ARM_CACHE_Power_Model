import subprocess
from pathlib import Path

import pytest

from power.mcpat_runner import (McpatError, McpatNotFound, _require_components,
                                find_mcpat_bin, mcpat_sha256,
                                parse_mcpat_output, run_mcpat)

FIX = Path(__file__).resolve().parents[1] / "fixtures"
REG = Path("/home/kevin/Projects/gem5/ext/mcpat/regression")


def test_parse_test0_tree():
    r = parse_mcpat_output((FIX / "mcpat_test0.out").read_text())
    core = r[("System", "Core 0")]
    assert core.runtime_dynamic_energy_j == pytest.approx(1.25634e-07)
    assert core.leakage_w == pytest.approx(4.64481 + 0.193831)
    assert ("System", "Core 0", "Instruction Fetch Unit", "Instruction Cache") in r
    assert ("System", "Core 0", "Load/Store Unit", "Data Cache") in r
    assert ("System", "L2 Cache") in r


def test_parse_test1_two_cores():
    r = parse_mcpat_output((FIX / "mcpat_test1.out").read_text())
    assert ("System", "Core 1") in r


def test_parse_garbage_raises():
    assert parse_mcpat_output("not mcpat output") == {}
    with pytest.raises(McpatError):
        _require_components(parse_mcpat_output("not mcpat output"), "ctx")


def test_parse_nan_inf():
    r = parse_mcpat_output("  System:\n    Area = nan mm^2\n"
                           "    Peak Dynamic Power = inf W\n")
    assert r[("System",)].peak_dynamic_w == float("inf")


def test_find_bin_missing_message(tmp_path, monkeypatch):
    monkeypatch.delenv("MCPAT_BIN", raising=False)
    with pytest.raises(McpatNotFound, match=r"make -C .*ext/mcpat BUILD_DIR="):
        find_mcpat_bin(None, tmp_path)


def test_sha256(tmp_path):
    f = tmp_path / "x"
    f.write_bytes(b"abc")
    assert mcpat_sha256(f).startswith("ba7816bf")


@pytest.mark.mcpat
@pytest.mark.parametrize("t", [f"test-{i}" for i in range(9)])
def test_bundled_regressions_match(mcpat_bin, t):
    ref = REG / t / "region0.out.ref"
    if not ref.exists():
        pytest.skip("no reference output")
    out = subprocess.run(
        [str(mcpat_bin), "-infile", "power_region0.xml", "-print_level", "10"],
        cwd=REG / t, capture_output=True, text=True, timeout=300).stdout
    assert out.splitlines()[1:] == ref.read_text().splitlines()[1:]


@pytest.mark.mcpat
def test_run_mcpat_nonzero_exit_raises(mcpat_bin, tmp_path):
    with pytest.raises(McpatError, match="input.xml"):
        run_mcpat("<component id='root'/>", mcpat_bin, tmp_path)
