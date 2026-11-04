import json
import re

import pytest

pytestmark = [pytest.mark.gem5, pytest.mark.mcpat]

_PW = re.compile(r"^(\S+)\.power_model\.(dynamicPower|staticPower)\s+(\S+)", re.M)


def power_stats(stats_text):
    """{path: (dyn, st)} for every "<path>.power_model.dynamicPower"/"staticPower"."""
    out = {}
    for path, kind, val in _PW.findall(stats_text):
        d = out.setdefault(path, [0.0, 0.0])
        d[0 if kind == "dynamicPower" else 1] = float(val)
    return {p: tuple(v) for p, v in out.items()}


@pytest.fixture
def hello(project_root):
    return str(project_root / "src/tests/test_sample_arm64")


@pytest.mark.parametrize("cpu,model,n", [("O3", "o3_arm_v7a", 1), ("O3", "o3_arm_v7a", 2),
                                         ("MINOR", None, 1), ("MINOR", None, 2),
                                         ("O3", "neoverse_v2", 1)])
def test_power_models_report_nonzero(run_gem5, hello, tmp_path, cpu, model, n):
    args = ["--cpu_type", cpu, "--num_cores", str(n), "--binary", hello]
    if model:
        args += ["--core_model", model]
    r = run_gem5(args, outdir=tmp_path / "m5", cwd=tmp_path)
    assert r.returncode == 0, r.stderr[-3000:]
    ps = power_stats((tmp_path / "m5/stats.txt").read_text())
    assert len(ps) == 4 * n + 1          # n cores + n*(l1i,l1d,l2) + l3
    assert all(st > 0 for _, st in ps.values())
    active = [p for p in ps if ".cores" in p and (n == 1 or "cores0" in p)] + \
             [p for p in ps if "l1dcache" in p and (n == 1 or "clusters0" in p)]
    assert active
    assert all(ps[p][0] > 0 for p in active)
    meta = json.loads((tmp_path / "m5/power_meta.json").read_text())
    assert meta["implied_vdd"] == pytest.approx(0.6) and meta["num_cores"] == n
    if model == "neoverse_v2":
        assert "overstated" in r.stdout


def test_timing_cache_only(run_gem5, hello, tmp_path):
    r = run_gem5(["--cpu_type", "TIMING", "--binary", hello], outdir=tmp_path / "m5", cwd=tmp_path)
    assert r.returncode == 0
    ps = power_stats((tmp_path / "m5/stats.txt").read_text())
    assert len(ps) == 4 and not any(".processor." in p for p in ps)
    assert r.stdout.count("has no core power model") == 1


def test_core_model_with_minor_rejected(run_gem5, hello, tmp_path):
    r = run_gem5(["--cpu_type", "MINOR", "--core_model", "neoverse_v2", "--binary", hello],
                 outdir=tmp_path / "m5", cwd=tmp_path)
    assert r.returncode != 0 and "core_model" in (r.stderr + r.stdout)


def test_kvm_removed(run_gem5, hello, tmp_path):
    r = run_gem5(["--cpu_type", "KVM", "--binary", hello], outdir=tmp_path / "m5", cwd=tmp_path)
    assert r.returncode != 0
