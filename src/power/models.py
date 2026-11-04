"""Attach McPAT-derived MathExprPowerModels to gem5 SimObjects (needs gem5)."""
from __future__ import annotations

from power.characterize import Coefficients
from power.mapping import dyn_expression, static_expression


def _attach(obj, dyn: str, st: str) -> None:
    from m5.objects import MathExprPowerModel, PowerModel

    def mk(d: str, s: str):
        m = MathExprPowerModel()
        m.dyn = d
        m.st = s
        return m

    obj.power_state.default_state = "ON"
    pm = PowerModel()
    pm.pm = [mk(dyn, st), mk("0", st), mk("0", "0"), mk("0", "0")]
    obj.power_model = pm


def attach_power_models(board, coeffs: Coefficients, cpu_type: str) -> None:
    """Attach power models to every core (O3/MINOR), L1I, L1D, L2 and the L3."""
    hier = board.get_cache_hierarchy()
    cores = board.get_processor().get_cores()
    with_cores = cpu_type in ("O3", "MINOR")

    all_paths = []
    for i, cluster in enumerate(hier.clusters):
        all_paths.append({
            "core": cores[i].core.path() if with_cores else "",
            "l1i": cluster.l1icache.path(),
            "l1d": cluster.l1dcache.path(),
            "l2": cluster.l2cache.path(),
            "l3": hier.l3_cache.path(),
        })

    for i, cluster in enumerate(hier.clusters):
        paths = [all_paths[i]]
        if with_cores:
            c = cores[i].core
            _attach(c, dyn_expression("core", coeffs, cpu_type, paths),
                    static_expression("core", coeffs))
        for comp, obj in (("l1i", cluster.l1icache), ("l1d", cluster.l1dcache),
                          ("l2", cluster.l2cache)):
            _attach(obj, dyn_expression(comp, coeffs, cpu_type, paths),
                    static_expression(comp, coeffs))
    _attach(hier.l3_cache, dyn_expression("l3", coeffs, cpu_type, all_paths),
            static_expression("l3", coeffs))
