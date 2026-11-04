from pathlib import Path

import pytest
from helpers import cfg

from extract_gem5_stats import discover_components, parse_stats_file, sim_time
from power.characterize import Coefficients
from power.mcpat_runner import ComponentPower
from validate_mcpat import _discover, _system_cycles, compare, counts_from_stats, max_rel_err

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


def _setup(n=2, prep=None):
    stats, c, comps = _load(n)
    if prep:
        prep(stats)
    coeffs = Coefficients(
        schema_version=1, config={}, config_hash="x", mcpat_sha256="x",
        implied_vdd=0.6, leakage_w=dict(LEAK),
        energy_j={"core": {"core.cycles": E_CYC, "core.int_insts": E_INT},
                  "l1i": {}, "l1d": {}, "l2": {}, "l3": {}},
        created="t")
    all_counts, core_cyc, sys_cyc = counts_from_stats(stats, c, comps)
    sim = sim_time(stats)
    res = {}
    cyc = {i: stats[f"{comps['cores'][i]}.numCycles"] for i in range(n)}
    for i in range(n):
        ints = all_counts[(i, "core.int_insts")]
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


def test_idle_core_is_precision_limited_and_passes():
    stats, coeffs, c, comps, res = _setup()
    rows = compare(stats, coeffs, c, comps, res)
    idle = next(r for r in rows if r.component_path == "core1")
    assert idle.precision_limited and idle.rel_err <= 0.01 and idle.allowance_J > 0
    assert idle.mcpat_dyn_J_raw > 1e5 * abs(idle.mcpat_dyn_J) - 1e-30 and idle.mcpat_dyn_J_raw > 0


def test_busy_core_small_error_fails_unflagged():
    stats, coeffs, c, comps, res = _setup()
    stats[f"{comps['cores'][0]}.power_model.dynamicPower"] *= 1.0101
    row = next(r for r in compare(stats, coeffs, c, comps, res)
               if r.component_path == "core0")
    assert not row.precision_limited and row.rel_err > 0.01


def _light_core1(factor):
    """Core 1 with adjusted = 1e-3 * raw and gem5 = factor * adjusted.

    The clock coefficient is scaled up 1000x so the values (~0.1 mW) are well
    above gem5's 6-decimal print precision and McPAT's 6 digits dominate the
    allowance (gem5 part ~5% of it).
    """
    stats, coeffs, c, comps, res = _setup()
    e_cyc = 1000 * E_CYC
    coeffs.energy_j["core"]["core.cycles"] = e_cyc
    sys_cyc = counts_from_stats(stats, c, comps)[2]
    k = e_cyc * (sys_cyc - stats[f"{comps['cores'][1]}.numCycles"])
    adj = k / 999.0                       # raw = adj + k = 1000 * adj
    node = res[("System", "Core 1")]
    res[("System", "Core 1")] = ComponentPower(
        runtime_dynamic_energy_j=adj + k,
        subthreshold_leakage_w=node.subthreshold_leakage_w)
    stats[f"{comps['cores'][1]}.power_model.dynamicPower"] = adj * factor / sim_time(stats)
    return next(r for r in compare(stats, coeffs, c, comps, res)
                if r.component_path == "core1")


def test_lightly_active_core_5pct_error_never_unflagged_pass():
    row = _light_core1(1.05)
    # a ~ 1e-5*raw = 1e-2*adj > 0.1*tol*adj -> flagged; 5% error > a + 1% -> fails
    assert row.precision_limited
    assert row.rel_err > 0.01
    # a within-allowance error is flagged and passes
    ok = _light_core1(1.015)
    assert ok.precision_limited and ok.rel_err <= 0.01


def test_coreless_run_has_cache_rows_and_no_core_rows():
    stats, coeffs, c, comps, res = _setup(1)
    stats = {k: v for k, v in stats.items() if ".processor." not in k}
    t_cfg = cfg(num_cores=1, cpu_type="TIMING")
    comps = _discover(stats, t_cfg)
    assert comps["cores"] == [] and len(comps["l1i"]) == 1 and comps["l3"]
    rows = compare(stats, coeffs, t_cfg, comps, res)
    names = [r.component_path for r in rows]
    assert names == ["l1i0", "l1d0", "l20", "l3", "total"]
    assert all(r.rel_err <= 0.01 and r.static_rel_err <= 0.01 for r in rows)


# ---- F2: exact sim time and gem5 print-precision allowance ----------------
T_EXACT = 170319000 / 1e12


def _exact_time(stats):
    """Rounded simSeconds (as gem5 prints it) plus exact simTicks/simFreq."""
    stats["simSeconds"] = 0.000170
    stats["simTicks"] = 170319000
    stats["simFreq"] = 1000000000000


def test_system_cycles_use_exact_time():
    stats, c, comps = _load(1)
    _exact_time(stats)
    stats[f"{comps['cores'][0]}.numCycles"] = 10
    assert _system_cycles(stats, c, comps) == 170319


def test_compare_uses_exact_time_not_rounded_sim_seconds():
    stats, coeffs, c, comps, res = _setup(prep=_exact_time)
    rows = compare(stats, coeffs, c, comps, res)
    core0 = next(r for r in rows if r.component_path == "core0")
    assert core0.rel_err < 1e-9          # simSeconds would give ~1.9e-3


def _cache_row(stats, coeffs, c, comps, res, name):
    return next(r for r in compare(stats, coeffs, c, comps, res) if r.component_path == name)


def _with_l1d0_energy(e_mcpat, g_watts):
    stats, coeffs, c, comps, res = _setup(prep=_exact_time)
    key = ("System", "Core 0", "Load/Store Unit", "Data Cache")
    res[key] = ComponentPower(runtime_dynamic_energy_j=e_mcpat,
                              subthreshold_leakage_w=res[key].subthreshold_leakage_w)
    core = res[("System", "Core 0")]
    res[("System", "Core 0")] = ComponentPower(
        runtime_dynamic_energy_j=core.runtime_dynamic_energy_j + e_mcpat,
        subthreshold_leakage_w=core.subthreshold_leakage_w)
    stats[f"{comps['l1d'][0]}.power_model.dynamicPower"] = g_watts
    return _cache_row(stats, coeffs, c, comps, res, "l1d0")


def test_cache_row_print_rounding_is_precision_limited_and_passes():
    # True power 3.66e-7 W prints as 0.000000 W in stats.txt: 100% error,
    # entirely within the gem5 print allowance 5e-7 W * T.
    row = _with_l1d0_energy(3.66e-7 * T_EXACT, 0.0)
    assert row.precision_limited and row.rel_err <= 0.01
    assert row.allowance_J == pytest.approx(1e-5 * 3.66e-7 * T_EXACT + 5e-7 * T_EXACT)


def test_cache_row_large_error_beyond_allowance_fails():
    row = _with_l1d0_energy(3.66e-7 * T_EXACT, 2e-6)
    assert row.precision_limited and row.rel_err > 0.01


def test_normal_cache_row_gets_no_allowance():
    e = 1e-2 * T_EXACT                    # 10 mW: far above print precision
    row = _with_l1d0_energy(e, 1.015e-2)
    assert not row.precision_limited and row.allowance_J == 0.0
    assert row.rel_err == pytest.approx(0.015, rel=1e-6)


def test_static_row_print_precision_allowance():
    stats, coeffs, c, comps, res = _setup()
    key = ("System", "L2 Cache 0")
    res[key] = ComponentPower(subthreshold_leakage_w=3e-7)
    stats[f"{comps['l2'][0]}.power_model.staticPower"] = 0.0     # prints 0.000000
    row = _cache_row(stats, coeffs, c, comps, res, "l20")
    assert row.static_precision_limited and row.static_rel_err <= 0.01
    assert row.allowance_W == pytest.approx(1e-5 * 3e-7 + 5e-7)
    stats[f"{comps['l2'][0]}.power_model.staticPower"] = 2e-6
    row = _cache_row(stats, coeffs, c, comps, res, "l20")
    assert row.static_rel_err > 0.01


def test_max_rel_err_skips_precision_limited_rows():
    stats, coeffs, c, comps, res = _setup()
    rows = compare(stats, coeffs, c, comps, res)
    assert any(r.precision_limited for r in rows)
    expect = max([r.rel_err for r in rows if not r.precision_limited]
                 + [r.static_rel_err for r in rows if not r.static_precision_limited])
    assert max_rel_err(rows) == expect
