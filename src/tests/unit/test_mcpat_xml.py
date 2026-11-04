import xml.etree.ElementTree as ET

import pytest
from helpers import base_cfg, cfg

from power.config import HPI_FALLBACK_CORE
from power.events import EVENTS, events_for
from power.mcpat_runner import run_mcpat
from power.mcpat_xml import build_xml


def _comp(root, cid):
    return next(c for c in root.iter("component") if c.get("id") == cid)


def param(root, cid, name):
    return next(p.get("value") for p in _comp(root, cid).findall("param")
                if p.get("name") == name)


def stat(root, cid, name):
    return next(s.get("value") for s in _comp(root, cid).findall("stat")
                if s.get("name") == name)


def test_xml_structure_ooo_two_cores():
    root = ET.fromstring(build_xml(cfg(num_cores=2), {}, 2_000_000, {0: 1_000_000, 1: 1_000_000}))
    ids = {c.get("id") for c in root.iter("component")}
    assert {"system.core0", "system.core1", "system.core0.icache", "system.core1.dcache",
            "system.L20", "system.L21", "system.L30"} <= ids
    assert param(root, "system", "core_tech_node") == "28"
    assert param(root, "system", "device_type") == "2"
    assert param(root, "system.core0", "machine_type") == "0"
    assert param(root, "system.L30", "size") == str(2 * 1024 * 1024)


def test_xml_inorder_machine_type():
    root = ET.fromstring(build_xml(cfg(core=HPI_FALLBACK_CORE, cpu_type="MINOR"), {}, 2, {0: 1}))
    assert param(root, "system.core0", "machine_type") == "1"


def test_counts_land_on_mcpat_stats():
    x = ET.fromstring(build_xml(cfg(), {(0, "core.int_insts"): 7, (0, "l1d.read_misses"): 3,
                                        (0, "l3.write_accesses"): 5}, 10, {0: 10}))
    assert stat(x, "system.core0", "int_instructions") == "7"
    assert stat(x, "system.core0", "committed_int_instructions") == "7"
    assert stat(x, "system.core0.dcache", "read_misses") == "3"
    assert stat(x, "system.L30", "write_accesses") == "5"
    assert all(s.get("value") == "1.0" for s in x.iter("stat") if s.get("name").endswith("duty_cycle"))


def test_inorder_rejects_ooo_event():
    with pytest.raises(ValueError):
        build_xml(cfg(core=HPI_FALLBACK_CORE, cpu_type="MINOR"), {(0, "core.rob_reads"): 1}, 1, {0: 1})


def test_cycles_via_arguments_only():
    x = ET.fromstring(build_xml(cfg(num_cores=2), {}, 30, {0: 10, 1: 20}))
    assert stat(x, "system", "total_cycles") == "30"
    assert stat(x, "system.core1", "total_cycles") == "20"
    with pytest.raises(ValueError):
        build_xml(cfg(), {(0, "core.cycles"): 5}, 10, {0: 10})


def test_unknown_event_and_core_index_rejected():
    with pytest.raises(ValueError):
        build_xml(cfg(), {(0, "core.bogus"): 1}, 1, {0: 1})
    with pytest.raises(ValueError):
        build_xml(cfg(), {(1, "core.int_insts"): 1}, 1, {0: 1})


def test_params_from_cfg():
    root = ET.fromstring(build_xml(cfg(), {}, 1, {0: 1}))
    assert param(root, "system", "target_core_clockrate") == "1000"
    assert param(root, "system", "temperature") == "350"
    assert param(root, "system.core0", "ROB_size") == "40"
    assert param(root, "system.core0", "instruction_window_size") == "32"
    assert param(root, "system.core0", "phy_Regs_IRF_size") == "128"
    assert param(root, "system.core0.icache", "latency") == "4"
    assert param(root, "system.core0.icache", "miss_buffer_size") == "4"
    assert param(root, "system.L20", "level") == "2"
    assert param(root, "system.L30", "level") == "3"
    assert param(root, "system.L20", "device_type") == "2"
    assert param(root, "system.L20", "clockrate") == "1000"


def test_fractional_and_whole_values():
    x = ET.fromstring(build_xml(cfg(), {(0, "core.int_insts"): 7.0, (0, "core.fpu"): 2.5}, 1, {0: 1}))
    assert stat(x, "system.core0", "int_instructions") == "7"
    assert stat(x, "system.core0", "fpu_accesses") == "2.5"


def test_events_catalogue():
    assert "core.mul" not in EVENTS
    assert "core.rob_reads" in events_for("ooo")
    assert "core.rob_reads" not in events_for("inorder")
    assert set(events_for("inorder")) < set(events_for("ooo"))


def _cfgs():
    return [base_cfg(),
            cfg(cpu_type="MINOR", core=HPI_FALLBACK_CORE),
            cfg(num_cores=2)]


@pytest.mark.mcpat
@pytest.mark.parametrize("c", _cfgs(), ids=["ooo", "inorder", "ooo2"])
def test_generated_xml_runs(mcpat_bin, tmp_path, c):
    n = c.num_cores
    xml = build_xml(c, {}, 2_000_000, {i: 1_000_000 for i in range(n)})
    r = run_mcpat(xml, mcpat_bin, tmp_path)
    for i in range(n):
        assert ("System", f"Core {i}", "Instruction Fetch Unit", "Instruction Cache") in r
        assert ("System", f"Core {i}", "Load/Store Unit", "Data Cache") in r
        assert ("System", f"L2 Cache {i}") in r
    assert ("System", "L3 Cache") in r
    # McPAT itself reports 0 leakage for wire-only / CAM-only blocks (also in the
    # bundled test-0 reference output); every other node must leak.
    zero_ok = ("Bypass", "Instruction Window", "Microcode Decoder")
    bad = [k for k, v in r.items() if not v.leakage_w > 0
           and not any(z in k[-1] for z in zero_ok)]
    assert not bad


@pytest.mark.parametrize("c", [base_cfg(), cfg(cpu_type="MINOR", core=HPI_FALLBACK_CORE)],
                         ids=["ooo", "inorder"])
def test_every_event_maps_to_existing_stat(c):
    kind = c.core.kind
    counts = {(0, e): 1 for e in events_for(kind) if e != "core.cycles"}
    build_xml(c, counts, 1, {0: 1})
