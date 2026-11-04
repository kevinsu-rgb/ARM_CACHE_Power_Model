#!/usr/bin/env python3
"""Cross-check gem5's in-simulation power model against a full McPAT evaluation.

The run's real activity counts (``stats.txt``, via the same ``MAPPING`` the
in-simulation model uses) are turned into ONE McPAT run. McPAT's per-component
dynamic energy and leakage are then compared with what gem5 reported
(``<prefix>.power_model.{dynamicPower,staticPower}``). Exit status is 1 if any
component deviates by more than the tolerance (default 1%).

Core-energy adjustment: McPAT charges each core its base energy per *system*
cycle (system ``total_cycles``) regardless of the core's own cycle count, while
gem5's model charges ``core.cycles * <core>.numCycles`` (0 for idle, suspended
cores, which are modelled as clock-gated). The core comparison therefore uses

    mcpat_core_adj = mcpat_core - e_cyc * (system_cycles - numCycles_i)

with ``e_cyc`` the ``core.cycles`` coefficient. Run time is the exact
``T = simTicks / simFreq`` (``simSeconds`` is printed with 6 decimals only).

Print precision: McPAT prints 6 significant digits (relative 1e-5 of the raw,
unadjusted value) and gem5 prints ``dynamicPower``/``staticPower`` with 6
decimals (5e-7 W absolute, i.e. 5e-7 W * T for energies). Every row, dynamic
and static separately, gets the allowance ``a = 1e-5*|raw_mcpat| + a_g``. When
``a`` exceeds 10% of the tolerance band the value is PRECISION-LIMITED and
passes iff |g-m| <= a + tol*|m|; all other values get no allowance at all.
Both the raw and the adjusted McPAT values are reported.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from extract_gem5_stats import (discover_components, parse_stats_file,  # noqa: E402
                                sim_time)
from power.characterize import (Coefficients, component_energies,  # noqa: E402
                                component_leakage)
from power.config import PowerConfig, config_from_dict  # noqa: E402
from power.events import ActivityCounts  # noqa: E402
from power.mapping import MAPPING, eval_expression  # noqa: E402
from power.mcpat_runner import (McpatError, McpatResult, find_mcpat_bin,  # noqa: E402
                                run_mcpat)
from power.mcpat_xml import build_xml  # noqa: E402

PROJECT_ROOT = _SRC.parent
CORELESS = ("TIMING", "ATOMIC")
EPS = 1e-15


@dataclass
class Row:
    component_path: str
    gem5_dyn_J: float
    mcpat_dyn_J: float          # adjusted (see module docstring)
    rel_err: float
    gem5_static_W: float
    mcpat_static_W: float
    mcpat_dyn_J_raw: float = 0.0
    static_rel_err: float = 0.0
    precision_limited: bool = False         # dynamic value is print-precision limited
    allowance_J: float = 0.0
    static_precision_limited: bool = False
    allowance_W: float = 0.0


PRINT_NOISE = 1e-5  # McPAT prints 6 significant digits; relative resolution <= 1e-5
GEM5_PRINT_W = 5e-7  # gem5 prints power with 6 decimals: half a unit in the last place


def _rel(g: float, m: float) -> float:
    """|g - m| / max(|m|, 1e-15); 0 when both sides are below 1e-15."""
    if abs(g) < EPS and abs(m) < EPS:
        return 0.0
    return abs(g - m) / max(abs(m), EPS)


def _allowance(raw: float, a_gem5: float) -> float:
    """Absolute print-precision allowance: McPAT's 6 digits plus gem5's 6 decimals."""
    return PRINT_NOISE * abs(raw) + a_gem5


def _check(g: float, m: float, a: float, tol: float) -> tuple[float, bool, float]:
    """(error, precision_limited, allowance_used) for one compared value.

    The value is precision-limited when the allowance ``a`` exceeds 10% of the
    tolerance band; it then passes iff |g-m| <= a + tol*|m|. Otherwise the
    plain relative error is used and no allowance is applied.
    """
    if a <= 0.1 * tol * max(abs(m), EPS):
        return _rel(g, m), False, 0.0
    if abs(g) < EPS and abs(m) < EPS:
        return 0.0, True, a
    return max(0.0, abs(g - m) - a) / max(abs(m), EPS), True, a


def _row(name: str, g: float, m: float, raw: float, a_dyn: float,
         g_st: float, m_st: float, a_st: float, tol: float) -> Row:
    err, lim, used = _check(g, m, a_dyn, tol)
    st_err, st_lim, st_used = _check(g_st, m_st, a_st, tol)
    return Row(name, g, m, err, g_st, m_st, raw, st_err, lim, used, st_lim, st_used)


def max_rel_err(rows: list[Row]) -> float:
    """Largest dynamic or static error over values that are not precision-limited."""
    errs = [r.rel_err for r in rows if not r.precision_limited]
    errs += [r.static_rel_err for r in rows if not r.static_precision_limited]
    return max(errs, default=0.0)


def _num_cycles(stats: dict, comps: dict, i: int) -> int:
    if i >= len(comps["cores"]):
        return 0
    return int(stats.get(f"{comps['cores'][i]}.numCycles", 0))


def _system_cycles(stats: dict, cfg: PowerConfig, comps: dict) -> int:
    cyc = [_num_cycles(stats, comps, i) for i in range(cfg.num_cores)]
    sim = round(sim_time(stats) * cfg.clock_mhz * 1e6)
    return max(sim, max(cyc, default=0), 1)


def counts_from_stats(stats: dict, cfg: PowerConfig, comps: dict
                      ) -> tuple[ActivityCounts, dict[int, int], int]:
    """Evaluate the mapped events against stats.

    Returns (counts, core_cycles, system_cycles); core.cycles is never in counts.
    """
    counts: ActivityCounts = {}
    l3 = comps["l3"][0] if comps["l3"] else ""
    for i in range(cfg.num_cores):
        sub = {"core": comps["cores"][i] if i < len(comps["cores"]) else "",
               "l1i": comps["l1i"][i], "l1d": comps["l1d"][i],
               "l2": comps["l2"][i], "l3": l3}
        for event, tmpl in MAPPING[cfg.cpu_type].items():
            if event == "core.cycles":
                continue
            if event.startswith("l3."):
                if i != 0:
                    continue
                key = (0, event)
            else:
                key = (i, event)
            counts[key] = max(0.0, float(eval_expression(tmpl.format(**sub), stats)))
    core_cycles = {i: max(_num_cycles(stats, comps, i), 1) for i in range(cfg.num_cores)}
    return counts, core_cycles, _system_cycles(stats, cfg, comps)


def compare(stats: dict, coeffs: Coefficients, cfg: PowerConfig, comps: dict,
            mcpat_result: McpatResult, tolerance: float = 0.01) -> list[Row]:
    """One Row per compared component plus a final "total" row.

    The total's allowances are the sums of the component allowances.
    """
    sim = sim_time(stats)
    sys_cyc = _system_cycles(stats, cfg, comps)
    e_cyc = coeffs.energy_j.get("core", {}).get("core.cycles", 0.0)
    has_core = cfg.cpu_type not in CORELESS
    a_g_dyn = GEM5_PRINT_W * sim

    def gem5(prefix: str) -> tuple[float, float]:
        return (stats.get(f"{prefix}.power_model.dynamicPower", 0.0) * sim,
                stats.get(f"{prefix}.power_model.staticPower", 0.0))

    rows: list[Row] = []
    a_dyn_sum = a_st_sum = 0.0

    def add(name: str, prefix: str, raw: float, adj: float, leak: float) -> None:
        nonlocal a_dyn_sum, a_st_sum
        g_dyn, g_st = gem5(prefix)
        a_dyn = _allowance(raw, a_g_dyn)
        a_st = _allowance(leak, GEM5_PRINT_W)
        a_dyn_sum += a_dyn
        a_st_sum += a_st
        rows.append(_row(name, g_dyn, adj, raw, a_dyn, g_st, leak, a_st, tolerance))

    for i in range(cfg.num_cores):
        en = component_energies(mcpat_result, i)
        lk = component_leakage(mcpat_result, i)
        if has_core:
            raw = en["core"]
            adj = raw - e_cyc * (sys_cyc - _num_cycles(stats, comps, i))
            add(f"core{i}", comps["cores"][i], raw, adj, lk["core"])
        for c in ("l1i", "l1d", "l2"):
            add(f"{c}{i}", comps[c][i], en[c], en[c], lk[c])
        if i == 0 and comps["l3"]:
            add("l3", comps["l3"][0], en["l3"], en["l3"], lk["l3"])
    gd = sum(r.gem5_dyn_J for r in rows)
    md = sum(r.mcpat_dyn_J for r in rows)
    gs = sum(r.gem5_static_W for r in rows)
    ms = sum(r.mcpat_static_W for r in rows)
    raw_total = sum(r.mcpat_dyn_J_raw for r in rows)
    err, lim, used = _check(gd, md, a_dyn_sum, tolerance)
    st_err, st_lim, st_used = _check(gs, ms, a_st_sum, tolerance)
    rows.append(Row("total", gd, md, err, gs, ms, raw_total, st_err, lim, used,
                    st_lim, st_used))
    return rows


def format_table(rows: list[Row], tolerance: float) -> str:
    hdr = ("McPAT cross-check (dynamic energy J, leakage W). mcpat_dyn_J is adjusted: "
           "core rows subtract e_cyc*(system_cycles - numCycles_i) because McPAT "
           "charges core base energy per SYSTEM cycle; mcpat_raw is unadjusted. "
           "PRECISION-LIMITED values are limited by McPAT's 6-digit and gem5's "
           "6-decimal output.\n")
    cols = (f"{'component':<10}{'gem5_dyn_J':>14}{'mcpat_dyn_J':>14}{'mcpat_raw':>14}"
            f"{'rel_err':>10}{'gem5_st_W':>12}{'mcpat_st_W':>12}{'st_err':>10}  status\n")
    lines = []
    for r in rows:
        ok = r.rel_err <= tolerance and r.static_rel_err <= tolerance
        tag = ""
        if r.precision_limited:
            tag += f"  PRECISION-LIMITED dyn (allowance {r.allowance_J:.2e} J)"
        if r.static_precision_limited:
            tag += f"  PRECISION-LIMITED static (allowance {r.allowance_W:.2e} W)"
        lines.append(f"{r.component_path:<10}{r.gem5_dyn_J:14.6e}{r.mcpat_dyn_J:14.6e}"
                     f"{r.mcpat_dyn_J_raw:14.6e}{r.rel_err:10.2e}{r.gem5_static_W:12.6f}"
                     f"{r.mcpat_static_W:12.6f}{r.static_rel_err:10.2e}  "
                     f"{'ok' if ok else 'FAIL'}{tag}")
    return hdr + cols + "\n".join(lines)


_CLUSTER_RX = {
    "l1i": re.compile(r"^(board\.cache_hierarchy\.clusters(\d*)\.l1icache)\."),
    "l1d": re.compile(r"^(board\.cache_hierarchy\.clusters(\d*)\.l1dcache)\."),
    "l2": re.compile(r"^(board\.cache_hierarchy\.clusters(\d*)\.l2cache)\."),
}
_L3_PREFIX = "board.cache_hierarchy.l3_cache"


def _discover(stats: dict, cfg: PowerConfig) -> dict:
    try:
        return discover_components(stats)
    except ValueError:
        if cfg.cpu_type not in CORELESS:
            raise
    # Core-less runs: discover caches directly from the cluster stats.
    comps: dict[str, list[str]] = {"cores": []}
    for k, rx in _CLUSTER_RX.items():
        by_idx = {}
        for name in stats:
            m = rx.match(name)
            if m:
                by_idx[int(m.group(2) or 0)] = m.group(1)
        comps[k] = [by_idx[i] for i in sorted(by_idx)]
    comps["l3"] = ([_L3_PREFIX]
                   if any(n.startswith(_L3_PREFIX + ".") for n in stats) else [])
    return comps


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--outdir", required=True, type=Path)
    ap.add_argument("--mcpat_bin")
    ap.add_argument("--tolerance", type=float, default=0.01)
    args = ap.parse_args(argv)

    try:
        meta = json.loads((args.outdir / "power_meta.json").read_text())
        coeffs = Coefficients.from_json(Path(meta["coefficients_path"]).read_text())
        cfg = config_from_dict(coeffs.config)
        stats = parse_stats_file(args.outdir / "stats.txt")
        comps = _discover(stats, cfg)
        counts, core_cycles, sys_cyc = counts_from_stats(stats, cfg, comps)
        xml = build_xml(cfg, counts, sys_cyc, core_cycles)
        mcpat_bin = find_mcpat_bin(args.mcpat_bin, PROJECT_ROOT)
    except (OSError, KeyError, ValueError, McpatError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    work = Path(tempfile.mkdtemp(prefix="validate_mcpat_"))
    try:
        result = run_mcpat(xml, mcpat_bin, work)
    except McpatError as e:
        print(f"error: McPAT failed: {e}", file=sys.stderr)
        return 2
    finally:
        shutil.rmtree(work, ignore_errors=True)

    rows = compare(stats, coeffs, cfg, comps, result, args.tolerance)
    print(format_table(rows, args.tolerance))
    bad = [r.component_path for r in rows
           if r.rel_err > args.tolerance or r.static_rel_err > args.tolerance]
    n_lim = sum(r.precision_limited or r.static_precision_limited for r in rows)
    if bad:
        print(f"FAIL: components over {args.tolerance:.2%}: {', '.join(bad)} "
              f"({n_lim} precision-limited rows)",
              file=sys.stderr)
        return 1
    print(f"PASS: all components within {args.tolerance:.2%} "
          f"({len(rows) - n_lim} normal, {n_lim} precision-limited); "
          f"max rel_err (non-precision-limited) {max_rel_err(rows):.3e}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
