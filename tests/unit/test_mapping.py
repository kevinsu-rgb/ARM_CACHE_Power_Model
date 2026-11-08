import re

import pytest

from power.characterize import Coefficients
from power.events import events_for
from power.mapping import (MAPPING, _fmt, dyn_expression, eval_expression,
                           static_expression, stat_names)

P1 = [{"core": "c", "l1i": "i", "l1d": "d", "l2": "l2", "l3": "l3"}]


def coeffs_with(energy, leakage=None):
    return Coefficients(1, {}, "h", "s", 0.9, leakage or {}, energy, "now")


def test_every_characterized_event_is_mapped():
    assert set(MAPPING["O3"]) == set(events_for("ooo"))
    assert set(MAPPING["MINOR"]) == set(events_for("inorder"))
    cache_only = {e for e in events_for("inorder") if e.split(".")[0] != "core"}
    assert set(MAPPING["TIMING"]) == set(MAPPING["ATOMIC"]) == cache_only


def test_timing_maps_only_cache_events():
    assert all(e.split(".")[0] in ("l1i", "l1d", "l2", "l3") for e in MAPPING["TIMING"])


def test_no_vector_stats_used():
    banned = ("committedControl", "issuedInstType", ".misses", "mispredicted_0")
    for table in MAPPING.values():
        for expr in table.values():
            assert not any(b in expr for b in banned), expr


def test_dyn_expression_and_eval_roundtrip():
    co = coeffs_with({"l1d": {"l1d.read_accesses": 1e-11, "l1d.read_misses": 4e-11}})
    expr = dyn_expression("l1d", co, "O3", P1)
    stats = {"d.overallAccesses::total": 100, "d.WriteReq.accesses::total": 20,
             "d.overallMisses::total": 5, "simSeconds": 2.0}
    assert eval_expression(expr, stats) == pytest.approx((1e-11 * 80 + 4e-11 * 5) / 2.0)


def test_l3_sums_core_events_over_cores():
    co = coeffs_with({"l3": {"core.int_insts": 1e-12, "l3.read_accesses": 2e-12}})
    paths = [{"core": f"c{i}", "l1i": "", "l1d": "", "l2": "", "l3": "L3"} for i in range(2)]
    e = dyn_expression("l3", co, "O3", paths)
    assert "c0.commitStats0.numIntInsts" in e and "c1.commitStats0.numIntInsts" in e
    assert e.count("L3.overallAccesses") == 1


def test_eval_rejects_calls():
    with pytest.raises(ValueError):
        eval_expression("__import__('os')", {})


@pytest.mark.parametrize("bad", ["a.b ** 2", "(1).real", "[1]", "1 if 1 else 2",
                                 "'s'", "1 < 2", "-a.b", "1 // 2"])
def test_eval_rejects_other_nodes(bad):
    with pytest.raises(ValueError):
        eval_expression(bad, {"a.b": 1})


def test_eval_unary_on_constants_and_div_zero():
    assert eval_expression("-2 + +3", {}) == 1.0
    assert eval_expression("x.y / simSeconds", {"x.y": 4, "simSeconds": 0}) == 0.0
    assert eval_expression("x.y + 1", {}) == 1.0
    assert eval_expression("x.y", {"x.y::total": 3}) == 3.0


def test_stat_names_order_dedupe_and_exclusions():
    e = "1.5e-13*(a.b + c_d.e) + 2*a.b / simSeconds"
    assert stat_names(e) == ["a.b", "c_d.e"]


def test_timing_ignores_core_events_and_unmapped():
    co = coeffs_with({"l1d": {"core.int_insts": 1e-12, "l1d.read_misses": 1e-12,
                              "bogus.event": 1.0}})
    e = dyn_expression("l1d", co, "TIMING", P1)
    assert "c." not in e and "d.overallMisses" in e and "bogus" not in e


def test_no_terms_returns_zero():
    assert dyn_expression("l2", coeffs_with({}), "O3", P1) == "0"
    assert dyn_expression("l2", coeffs_with({"l2": {"l2.read_misses": 0.0}}), "O3", P1) == "0"


def test_negative_coefficients_use_subtraction():
    co = coeffs_with({"l2": {"l2.read_misses": -1.234e-13, "l2.read_accesses": 1e-12}})
    e = dyn_expression("l2", co, "O3", P1)
    assert "+-" not in e and "+ -" not in e and not e.lstrip("( ").startswith("-")
    assert re.search(r"-\s*0\.0000000000001234\*\(", e)
    only_neg = dyn_expression("l2", coeffs_with({"l2": {"l2.read_misses": -1e-13}}),
                              "O3", P1)
    assert not only_neg.lstrip("( ").startswith("-")
    stats = {"l2.overallMisses": 10, "simSeconds": 1.0}
    assert eval_expression(only_neg, stats) == pytest.approx(-1e-12)


def test_static_expression():
    co = coeffs_with({}, {"l2": 0.125})
    assert float(static_expression("l2", co)) == pytest.approx(0.125)
    assert static_expression("l3", co) == "0"


def test_expression_only_safe_characters():
    co = coeffs_with({"core": {e: 1e-12 for e in MAPPING["O3"] if e.startswith("core.")}})
    e = dyn_expression("core", co, "O3", P1)
    assert re.fullmatch(r"[A-Za-z0-9_.+\-*/() ]+", e)
    assert "numBranches" in e and "mispred" not in e


def test_no_exponent_notation_in_expressions():
    co = coeffs_with({"l2": {"l2.read_misses": 1e-14, "l2.read_accesses": 2.7812e-11,
                             "l2.write_accesses": 3.5}},
                     {"l2": 2.7812e-11, "l3": 3.5, "l1d": -1e-14})
    e = dyn_expression("l2", co, "O3", P1)
    stats = {"l2.overallMisses": 10, "l2.overallAccesses": 100,
             "l2.WriteReq.accesses": 20, "l2.WritebackDirty.accesses": 1,
             "l2.WritebackClean.accesses": 2, "simSeconds": 2.0}
    want = (1e-14 * 10 + 2.7812e-11 * 80 + 3.5 * 23) / 2.0
    assert eval_expression(e, stats) == pytest.approx(want)
    neg = dyn_expression("l2", coeffs_with({"l2": {"l2.read_misses": -1e-14}}), "O3", P1)
    assert eval_expression(neg, stats) == pytest.approx(-1e-14 * 10 / 2.0)
    for expr in (e, neg, *(static_expression(c, co) for c in ("l2", "l3", "l1d"))):
        assert re.search(r"\d[eE][+-]?\d", expr) is None, expr
    assert eval_expression(static_expression("l1d", co), {}) == pytest.approx(-1e-14)
    assert eval_expression(static_expression("l2", co), {}) == pytest.approx(2.7812e-11)


@pytest.mark.parametrize("v", [0.0, 1e-14, 2.7812e-11, 3.5, 0.125, 1.5e-7, 123456.789, -1e-13])
def test_fmt_roundtrip(v):
    assert float(_fmt(v)) == v


def test_fmt_rejects_nonfinite():
    for v in (float("nan"), float("inf")):
        with pytest.raises(ValueError):
            _fmt(v)
