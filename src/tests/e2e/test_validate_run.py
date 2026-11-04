import re
import subprocess
import sys

import pytest

pytestmark = [pytest.mark.gem5, pytest.mark.mcpat]
PY = sys.executable


def _validate(project_root, outdir, cwd):
    r = subprocess.run([PY, str(project_root / "src/validate_mcpat.py"), "--outdir", str(outdir)],
                       cwd=cwd, capture_output=True, text=True, timeout=600)
    print(r.stdout, r.stderr)
    return r


def _run(run_gem5, tmp_path, args):
    out = tmp_path / "m5"
    r = run_gem5(args, outdir=out, cwd=tmp_path)
    assert r.returncode == 0, r.stderr[-3000:]
    return out


def _power(stats_text, path_regex):
    d = s = 0.0
    for name, kind, val in re.findall(r"^(\S+)\.power_model\.(dynamicPower|staticPower)\s+(\S+)",
                                      stats_text, re.M):
        if re.search(path_regex, name):
            if kind == "dynamicPower":
                d += float(val)
            else:
                s += float(val)
    return d, s


@pytest.fixture
def hello(project_root):
    return str(project_root / "src/tests/test_sample_arm64")


def test_validate_o3_two_cores(run_gem5, mcpat_bin, project_root, hello, tmp_path):
    out = _run(run_gem5, tmp_path, ["--cpu_type", "O3", "--core_model", "o3_arm_v7a",
                                    "--num_cores", "2", "--binary", hello])
    r = _validate(project_root, out, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_validate_minor(run_gem5, mcpat_bin, project_root, hello, tmp_path):
    out = _run(run_gem5, tmp_path, ["--cpu_type", "MINOR", "--num_cores", "1",
                                    "--binary", hello])
    r = _validate(project_root, out, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.slow
def test_validate_small_loop(run_gem5, mcpat_bin, project_root, tmp_path):
    out = _run(run_gem5, tmp_path, ["--cpu_type", "O3", "--num_cores", "1", "--binary",
                                    str(project_root / "src/tests/small_loop")])
    r = _validate(project_root, out, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    text = (out / "stats.txt").read_text()
    dyn, st = _power(text, r"\.processor\.")
    print("core dyn", dyn, "static", st)
    assert 0.05 <= dyn + st <= 2
    l1d_dyn, _ = _power(text, r"l1dcache")
    l3_dyn, _ = _power(text, r"l3_cache")
    print("l1d dyn", l1d_dyn, "l3 dyn", l3_dyn)
    assert l1d_dyn > l3_dyn
