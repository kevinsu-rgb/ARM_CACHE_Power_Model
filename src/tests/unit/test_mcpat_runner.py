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


def _script(tmp_path, body, name="fake_mcpat"):
    p = tmp_path / name
    p.write_text("#!/bin/sh\n" + body)
    p.chmod(0o755)
    return p


def test_run_mcpat_failure_reports_stdout_and_keeps_streams(tmp_path):
    b = _script(tmp_path, 'echo "ERROR: no valid data array organizations found"\n'
                          'echo "warn-on-stderr" 1>&2\nexit 1\n')
    with pytest.raises(McpatError) as ei:
        run_mcpat("<x/>", b, tmp_path / "wd")
    msg = str(ei.value)
    assert "no valid data array organizations found" in msg and "warn-on-stderr" in msg
    assert "no valid data array" in ei.value.stdout and "warn-on-stderr" in ei.value.stderr


def test_run_mcpat_failure_tails_are_2000_chars(tmp_path):
    b = _script(tmp_path, "printf 'HEAD%05000dTAIL' 0\nexit 3\n")
    with pytest.raises(McpatError) as ei:
        run_mcpat("<x/>", b, tmp_path / "wd")
    assert "TAIL" in str(ei.value) and "HEAD" not in str(ei.value)
    assert ei.value.stdout.startswith("HEAD")          # attribute is not truncated


def test_run_mcpat_unparseable_output_reports_stdout(tmp_path):
    b = _script(tmp_path, 'echo "something odd"\nexit 0\n')
    with pytest.raises(McpatError, match="something odd") as ei:
        run_mcpat("<x/>", b, tmp_path / "wd")
    assert ei.value.stdout.strip() == "something odd"


def test_find_bin_explicit_missing_is_not_skipped(tmp_path, monkeypatch):
    (tmp_path / "tools/mcpat").mkdir(parents=True)
    (tmp_path / "tools/mcpat/mcpat").write_bytes(b"x")       # fallback exists
    monkeypatch.delenv("MCPAT_BIN", raising=False)
    bad = tmp_path / "nope/mcpat"
    with pytest.raises(McpatNotFound, match=str(bad)):
        find_mcpat_bin(str(bad), tmp_path)


def test_find_bin_env_missing_is_not_skipped(tmp_path, monkeypatch):
    (tmp_path / "tools/mcpat").mkdir(parents=True)
    (tmp_path / "tools/mcpat/mcpat").write_bytes(b"x")
    bad = tmp_path / "env/mcpat"
    monkeypatch.setenv("MCPAT_BIN", str(bad))
    with pytest.raises(McpatNotFound, match=r"\$MCPAT_BIN.*" + str(bad)):
        find_mcpat_bin(None, tmp_path)


def test_find_bin_order(tmp_path, monkeypatch):
    (tmp_path / "tools/mcpat").mkdir(parents=True)
    fallback = tmp_path / "tools/mcpat/mcpat"
    fallback.write_bytes(b"x")
    env = tmp_path / "env_mcpat"
    env.write_bytes(b"x")
    explicit = tmp_path / "explicit_mcpat"
    explicit.write_bytes(b"x")
    monkeypatch.delenv("MCPAT_BIN", raising=False)
    assert find_mcpat_bin(None, tmp_path) == fallback
    monkeypatch.setenv("MCPAT_BIN", str(env))
    assert find_mcpat_bin(None, tmp_path) == env
    assert find_mcpat_bin(str(explicit), tmp_path) == explicit
