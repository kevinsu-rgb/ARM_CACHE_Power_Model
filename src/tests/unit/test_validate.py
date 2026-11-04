import dataclasses
from pathlib import Path

import pytest
from helpers import cfg

from extract_gem5_stats import discover_components, parse_stats_file
from power.characterize import Coefficients
from power.mcpat_runner import ComponentPower
from validate_mcpat import Row, compare, counts_from_stats

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def _load(n):
    stats = parse_stats_file(FIX / f"stats_n{n}.txt")
    return stats, cfg(num_cores=n), discover_components(stats)


def test_idle_core_cycles_clamped():
    stats, c, comps = _load(2)
    counts, core_cyc, sys_cyc = counts_from_stats(stats, c, comps)
    assert core_cyc[1] == 1 and sys_cyc >= core_cyc[0] > 1


def test_counts_use_both_cores():
    stats, c, comps = _load(2)
    counts, _, _ = counts_from_stats(stats, c, comps)
    assert counts[(0, "core.int_insts")] > 0 and (1, "core.int_insts") in counts
    assert counts[(1, "core.int_insts")] == 0.0
    assert not any(ev == "core.cycles" for _, ev in counts)
    assert all(i == 0 for i, ev in counts if ev.startswith("l3."))
    assert all(isinstance(v, float) and v >= 0 for v in counts.values())


def test_l3_events_evaluated_once():
    stats, c, comps = _load(2)
    counts, _, _ = counts_from_stats(stats, c, comps)
    l3 = comps["l3"][0]
    assert counts[(0, "l3.read_misses")] == stats[f"{l3}.overallMisses::total"]


# ---- compare() with a synthetic, self-consistent setup -------------------
E_CYC = 1e-12
E_INT = 2e-12
LEAK = {"core": 1.0, "l1i": 0.1, "l1d": 0.2, "l2": 0.3, "l3": 0.4}


def _setup(n=2):
    stats, c, comps = _load(n)
    coeffs = Coefficients(
        schema_version=1, config={}, config_hash="x", mcpat_sha256="x",
        implied_vdd=0.6, leakage_w=dict(LEAK),
        energy_j={"core": {"core.cycles": E_CYC, "core.int_insts": E_INT},
                  "l1i": {}, "l1d": {}, "l2": {}, "l3": {}},
        created="t")
    _, core_cyc, sys_cyc = counts_from_stats(stats, c, comps)
    sim = stats["simSeconds"]
    res = {}
    cyc = {i: stats[f"{comps['cores'][i]}.numCycles"] for i in range(n)}
    for i in range(n):
        ints = counts_from_stats(stats, c, comps)[0][(i, "core.int_insts")]
        g = E_CYC * cyc[i] + E_INT * ints
        pre = comps["cores"][i]
        stats[f"{pre}.power_model.dynamicPower"] = g / sim
        stats[f"{pre}.power_model.staticPower"] = LEAK["core"]
        raw = g + E_CYC * (sys_cyc - cyc[i])      # McPAT: per system cycle
        base = ("System", f"Core {i}")
        res[base] = ComponentPower(runtime_dynamic_energy_j=raw,
                                   subthreshold_leakage_w=LEAK["core"] + LEAK["l1i"] + LEAK["l1d"])
        res[base + ("Instruction Fetch Unit", "Instruction Cache")] = ComponentPower(
            subthreshold_leakage_w=LEAK["l1i"])
        res[base + ("Load/Store Unit", "Data Cache")] = ComponentPower(
            subthreshold_leakage_w=LEAK["l1d"])
        res[("System", f"L2 Cache {i}")] = ComponentPower(subthreshold_leakage_w=LEAK["l2"])
        for k, key in (("l1i", "l1i"), ("l1d", "l1d"), ("l2", "l2")):
            p = comps[k][i]
            stats[f"{p}.power_model.dynamicPower"] = 0.0
            stats[f"{p}.power_model.staticPower"] = LEAK[key]
    res[("System", "L3 Cache")] = ComponentPower(subthreshold_leakage_w=LEAK["l3"])
    stats[f"{comps['l3'][0]}.power_model.dynamicPower"] = 0.0
    stats[f"{comps['l3'][0]}.power_model.staticPower"] = LEAK["l3"]
    return stats, coeffs, c, comps, res


def test_compare_consistent_passes_and_has_raw_vs_adjusted():
    stats, coeffs, c, comps, res = _setup()
    rows = compare(stats, coeffs, c, comps, res)
    assert rows[-1].component_path == "total"
    assert len(rows) == 2 * 4 + 1 + 1
    assert all(r.rel_err <= 0.01 and r.static_rel_err <= 0.01 for r in rows)
    idle = next(r for r in rows if r.component_path == "core1")
    assert idle.mcpat_dyn_J_raw > idle.mcpat_dyn_J == pytest.approx(0.0, abs=1e-15)


def test_compare_flags_dynamic_mismatch():
    stats, coeffs, c, comps, res = _setup()
    k = f"{comps['cores'][0]}.power_model.dynamicPower"
    stats[k] *= 1.05
    rows = compare(stats, coeffs, c, comps, res)
    bad = [r.component_path for r in rows if r.rel_err > 0.01]
    assert "core0" in bad and "total" in bad


def test_compare_flags_leakage_mismatch():
    stats, coeffs, c, comps, res = _setup()
    stats[f"{comps['l3'][0]}.power_model.staticPower"] *= 1.1
    rows = compare(stats, coeffs, c, comps, res)
    assert [r.component_path for r in rows if r.static_rel_err > 0.01] == ["l3", "total"]


def test_row_defaults():
    r = Row("x", 0.0, 0.0, 0.0, 1.0, 1.0)
    assert dataclasses.is_dataclass(r)
