import json
from pathlib import Path

import pytest

from extract_gem5_stats import build_row, discover_components, parse_stats_file

FIX = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.mark.parametrize("n,fx", [(1, "stats_n1.txt"), (2, "stats_n2.txt")])
def test_discover_and_row(n, fx):
    stats = parse_stats_file(FIX / fx)
    meta = json.loads((FIX / f"power_meta_n{n}.json").read_text())
    comps = discover_components(stats)
    assert len(comps["cores"]) == n and len(comps["l2"]) == n and len(comps["l3"]) == 1
    row = build_row(stats, meta, "hello", "")
    assert row["chip_total_W"] == pytest.approx(row["core_total_W"] + row["cache_total_W"])
    assert row["dram_energy_J"] > 0
    assert all(row[f"core{i}_static_W"] > 0 for i in range(n))
    if n == 2:
        assert row["core1_cycles"] == 0 and row["core1_ipc"] == 0


def test_discover_prefix_forms():
    c1 = discover_components(parse_stats_file(FIX / "stats_n1.txt"))
    assert c1["cores"] == ["board.processor.cores.core"]
    assert c1["l3"] == ["board.cache_hierarchy.l3_cache"]
    c2 = discover_components(parse_stats_file(FIX / "stats_n2.txt"))
    assert c2["cores"][1] == "board.processor.cores1.core"
    assert c2["l1d"][0] == "board.cache_hierarchy.clusters0.l1dcache"


def test_discover_mixed_raises():
    stats = {
        "board.processor.cores.core.numCycles": 1,
        "board.processor.cores0.core.numCycles": 1,
    }
    with pytest.raises(ValueError):
        discover_components(stats)


def test_discover_count_mismatch_raises():
    stats = {
        "board.processor.cores0.core.numCycles": 1,
        "board.processor.cores1.core.numCycles": 1,
        "board.cache_hierarchy.clusters0.l1icache.overallAccesses::total": 1,
        "board.cache_hierarchy.clusters0.l1dcache.overallAccesses::total": 1,
        "board.cache_hierarchy.clusters0.l2cache.overallAccesses::total": 1,
    }
    with pytest.raises(ValueError):
        discover_components(stats)
