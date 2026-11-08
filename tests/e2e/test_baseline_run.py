import pytest

pytestmark = [pytest.mark.gem5]


def test_timing_hello_world_produces_stats(run_gem5, project_root, tmp_path):
    out = tmp_path / "m5"
    r = run_gem5(["--cpu_type", "TIMING", "--binary",
                  str(project_root / "tests/test_sample_arm64")],
                 outdir=out, cwd=tmp_path)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    stats = (out / "stats.txt").read_text()
    assert "simInsts" in stats
    assert "Hello from my own ARM64 binary" in r.stdout
    assert "Clock frequency: 1GHz" in r.stdout
    assert f"Statistics dumped to {out}/stats.txt" in r.stdout
