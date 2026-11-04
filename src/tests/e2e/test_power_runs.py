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
    assert all(st > 0 for _, st in ps.values())
    assert r.stdout.count("has no core power model") == 1


def test_core_model_with_minor_rejected(run_gem5, hello, tmp_path):
    r = run_gem5(["--cpu_type", "MINOR", "--core_model", "neoverse_v2", "--binary", hello],
                 outdir=tmp_path / "m5", cwd=tmp_path)
    assert r.returncode != 0 and "core_model" in (r.stderr + r.stdout)


def test_kvm_removed(run_gem5, hello, tmp_path):
    r = run_gem5(["--cpu_type", "KVM", "--binary", hello], outdir=tmp_path / "m5", cwd=tmp_path)
    assert r.returncode != 0


def test_mcpat_failure_reported_cleanly(run_gem5, mcpat_bin, hello, tmp_path):
    # 1 KiB L1D is a valid power-of-two geometry but CACTI cannot organise it;
    # McPAT reports that on stdout only.
    cache = tmp_path / "cache"
    r = run_gem5(["--cpu_type", "O3", "--l1d_size", "1KiB", "--binary", hello,
                  "--power_cache_dir", str(cache)], outdir=tmp_path / "m5", cwd=tmp_path)
    out = r.stdout + r.stderr
    assert r.returncode != 0
    assert "Traceback" not in out
    assert "ERROR: power characterization failed" in out
    assert "no valid data array organizations found" in out
    failed = list((cache / "failed").iterdir())
    assert failed and str(failed[0]) in out
    assert "no valid data array" in (failed[0] / "stdout.txt").read_text()


@pytest.mark.parametrize("args,msg", [
    (["--l2_assoc", "12"], "--l2_assoc 12: McPAT requires a power of two"),
    (["--l1d_size", "48KiB"], "--l1d_size 48KiB: McPAT requires a power of two"),
])
def test_non_power_of_two_geometry_rejected(run_gem5, hello, tmp_path, args, msg):
    r = run_gem5(["--cpu_type", "O3", "--binary", hello, *args],
                 outdir=tmp_path / "m5", cwd=tmp_path)
    assert r.returncode != 0 and msg in r.stderr, r.stderr[-2000:]
    assert "Traceback" not in r.stderr
