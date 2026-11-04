import json
import re
import xml.etree.ElementTree as ET

import pytest
from helpers import base_cfg, cfg

from power import characterize as ch
from power.characterize import (Coefficients, SuperpositionError, characterize,
                                get_coefficients)
from power.config import HPI_FALLBACK_CORE, SCHEMA_VERSION, config_hash
from power.events import EVENTS
from power.mcpat_runner import ComponentPower, McpatError

_STATS = sorted({(e.target, s) for e in EVENTS.values() for s in e.increments})
W = {k: (i + 1) * 1e-12 for i, k in enumerate(_STATS)}
W_CYC = 3.5e-13  # fake McPAT energy per SYSTEM cycle, charged to every core
LEAK = {"core": 1.0, "l1i": 0.1, "l1d": 0.2, "l2": 0.3, "l3": 0.4}
_CID = {"system.core0": "core", "system.core0.icache": "l1i",
        "system.core0.dcache": "l1d", "system.L20": "l2", "system.L30": "l3"}


def _cp(e, leak):
    return ComponentPower(runtime_dynamic_energy_j=e, subthreshold_leakage_w=leak)


_SUFFIX = {"": "core", "icache": "l1i", "dcache": "l1d"}


class FakeRunner:
    """Models McPAT: core energy has a base term proportional to the system
    component's total_cycles (per core), independent of the core's own cycles."""

    def __init__(self, weights, quadratic_on=None):
        self.w, self.q = weights, quadratic_on
        self.calls = 0

    def __call__(self, xml_text):
        self.calls += 1
        root = ET.fromstring(xml_text)
        vals = {}
        cores = set()
        sys_cycles = 0.0
        for c in root.iter("component"):
            cid = c.get("id")
            if cid == "system":
                for s in c.findall("stat"):
                    if s.get("name") == "total_cycles":
                        sys_cycles = float(s.get("value"))
                continue
            m = re.fullmatch(r"system\.core(\d+)(?:\.(icache|dcache))?", cid or "")
            if m:
                comp = _SUFFIX[m.group(2) or ""]
                idx = int(m.group(1))
                cores.add(idx)
            elif cid == "system.L20":
                comp, idx = "l2", 0
            elif cid == "system.L30":
                comp, idx = "l3", 0
            else:
                continue
            for s in c.findall("stat"):
                try:
                    vals[(idx, comp, s.get("name"))] = float(s.get("value"))
                except ValueError:
                    pass
        coupling = 1.0
        if self.q:
            total = sum(v for (i, c, n), v in vals.items() if n == self.q)
            coupling = 1.0 + 0.1 * total / 1e6
        out = {("System",): _cp(0, 0), ("System", "L3 Cache"): _cp(0, LEAK["l3"])}
        for i in sorted(cores):
            e = {c: 0.0 for c in LEAK}
            for (j, c, n), v in vals.items():
                if n == "total_cycles":
                    continue  # real McPAT ignores a core's own total_cycles
                if j == i or c in ("l2", "l3"):
                    e[c] += self.w.get((c, n), 0.0) * v * coupling
            e["core"] += W_CYC * sys_cycles
            core = ("System", f"Core {i}")
            out[core] = _cp(e["core"] + e["l1i"] + e["l1d"],
                            LEAK["core"] + LEAK["l1i"] + LEAK["l1d"])
            out[core + ("Instruction Fetch Unit", "Instruction Cache")] = _cp(e["l1i"], LEAK["l1i"])
            out[core + ("Load/Store Unit", "Data Cache")] = _cp(e["l1d"], LEAK["l1d"])
            out[("System", f"L2 Cache {i}")] = _cp(e["l2"], LEAK["l2"])
            out[("System", "L3 Cache")] = _cp(e["l3"], LEAK["l3"])
        return out


def test_recovers_linear_coefficients_exactly():
    co = characterize(base_cfg(), FakeRunner(W), "sha")
    assert co.energy_j["l1d"]["l1d.read_accesses"] == pytest.approx(W[("l1d", "read_accesses")])
    assert co.energy_j["core"]["core.int_insts"] == pytest.approx(
        sum(W[("core", s)] for s in EVENTS["core.int_insts"].increments))
    assert co.leakage_w["l3"] == pytest.approx(LEAK["l3"])
    assert co.leakage_w["core"] == pytest.approx(LEAK["core"])


def _assert_cycles_only_core(co):
    assert co.energy_j["core"]["core.cycles"] == pytest.approx(W_CYC)
    for c in ("l1i", "l1d", "l2", "l3"):
        assert co.energy_j[c].get("core.cycles", 0.0) == 0.0


def test_recovers_system_cycle_energy():
    _assert_cycles_only_core(characterize(base_cfg(), FakeRunner(W), "sha"))


def test_recovers_system_cycle_energy_two_cores():
    # Every core is charged W_CYC per system cycle; attribution is per core,
    # not system-wide (core 0's coefficient must not be doubled).
    _assert_cycles_only_core(characterize(cfg(num_cores=2), FakeRunner(W), "sha"))


def test_nonlinear_runner_trips_superposition():
    with pytest.raises(SuperpositionError) as ei:
        characterize(base_cfg(), FakeRunner(W, quadratic_on="read_accesses"), "sha")
    assert ei.value.deviations


def test_inorder_skips_ooo_events():
    co = characterize(cfg(core=HPI_FALLBACK_CORE, cpu_type="MINOR"), FakeRunner(W), "sha")
    assert not any(e.startswith("core.rob") for c in co.energy_j.values() for e in c)


def test_json_roundtrip():
    co = characterize(base_cfg(), FakeRunner(W), "sha")
    assert Coefficients.from_json(co.to_json()) == co


class _Boom:
    def __call__(self, *a, **k):
        raise AssertionError("runner must not be called")


@pytest.fixture
def fake_bin(tmp_path):
    p = tmp_path / "mcpat"
    p.write_bytes(b"fake")
    return p


def _patch(monkeypatch, fake):
    monkeypatch.setattr(ch, "run_mcpat", lambda xml, b, wd: fake(xml))


def test_cache_hit_skips_runner(tmp_path, monkeypatch, fake_bin):
    cache = tmp_path / "cache"
    _patch(monkeypatch, FakeRunner(W))
    c1, p1 = get_coefficients(base_cfg(), fake_bin, cache)
    assert p1.exists() and p1.parent == cache
    _patch(monkeypatch, _Boom())
    c2, p2 = get_coefficients(base_cfg(), fake_bin, cache)
    assert c1 == c2 and p1 == p2


def test_stale_schema_regenerates(tmp_path, monkeypatch, fake_bin):
    cache = tmp_path / "cache"
    _patch(monkeypatch, FakeRunner(W))
    c1, p = get_coefficients(base_cfg(), fake_bin, cache)
    d = json.loads(p.read_text())
    d["schema_version"] = 0
    p.write_text(json.dumps(d))
    runner = FakeRunner(W)
    _patch(monkeypatch, runner)
    c2, _ = get_coefficients(base_cfg(), fake_bin, cache)
    assert runner.calls > 0
    assert json.loads(p.read_text())["schema_version"] == SCHEMA_VERSION == c2.schema_version


def test_corrupt_cache_regenerates(tmp_path, monkeypatch, fake_bin):
    cache = tmp_path / "cache"
    _patch(monkeypatch, FakeRunner(W))
    _, p = get_coefficients(base_cfg(), fake_bin, cache)
    p.write_text("{not json")
    c, _ = get_coefficients(base_cfg(), fake_bin, cache)
    assert json.loads(p.read_text())["config_hash"] == c.config_hash


def test_mcpat_failure_writes_failed_dir(tmp_path, monkeypatch, fake_bin):
    cache = tmp_path / "cache"
    inner = FakeRunner(W)

    def failing(xml):
        root = ET.fromstring(xml)
        for c in root.iter("component"):
            if c.get("id") == "system.L20":
                for s in c.findall("stat"):
                    if s.get("name") == "read_accesses" and float(s.get("value")) > 0:
                        raise McpatError("boom")
        return inner(xml)

    _patch(monkeypatch, failing)
    with pytest.raises(McpatError):
        get_coefficients(base_cfg(), fake_bin, cache)
    h = ch.cache_key(base_cfg(), ch.mcpat_sha256(fake_bin))
    d = cache / "failed" / f"{h}-l2.read_accesses"
    assert (d / "input.xml").exists() and "boom" in (d / "error.txt").read_text()
    assert not (cache / f"{h}.json").exists()


@pytest.mark.mcpat
def test_real_characterization_o3_28nm(tmp_path, mcpat_bin):
    co, _ = get_coefficients(base_cfg(), mcpat_bin, tmp_path)
    assert co.implied_vdd == 0.6
    assert all(co.leakage_w[c] > 0 for c in ch.COMPONENTS)
    assert co.energy_j["l1d"]["l1d.read_accesses"] > 0
    assert co.energy_j["core"]["core.cycles"] == pytest.approx(2.688e-10, rel=0.01)


@pytest.mark.mcpat
def test_real_characterization_inorder_28nm(tmp_path, mcpat_bin):
    c = cfg(cpu_type="MINOR", core=HPI_FALLBACK_CORE)
    co, _ = get_coefficients(c, mcpat_bin, tmp_path)
    assert co.energy_j["core"]["core.cycles"] == pytest.approx(4.13e-11, rel=0.01)


@pytest.mark.mcpat
@pytest.mark.slow
def test_real_l2_leakage_monotonic(tmp_path, mcpat_bin):
    import dataclasses
    leaks = []
    for size in (128 * 1024, 256 * 1024, 1024 * 1024):
        b = base_cfg()
        caches = tuple(dataclasses.replace(c, size_bytes=size) if c.name == "l2" else c
                       for c in b.caches)
        co, _ = get_coefficients(dataclasses.replace(b, caches=caches), mcpat_bin, tmp_path)
        leaks.append(co.leakage_w["l2"])
    assert leaks[2] > leaks[1] > leaks[0]


def test_stdout_only_failure_lands_in_message_and_failed_dir(tmp_path):
    b = tmp_path / "fake_mcpat"
    b.write_text('#!/bin/sh\necho "ERROR: no valid data array organizations found"\nexit 1\n')
    b.chmod(0o755)
    cache = tmp_path / "cache"
    with pytest.raises(McpatError) as ei:
        get_coefficients(base_cfg(), b, cache)
    h = ch.cache_key(base_cfg(), ch.mcpat_sha256(b))
    d = cache / "failed" / f"{h}-baseline"
    msg = str(ei.value)
    assert "no valid data array organizations found" in msg and str(d) in msg
    assert "no valid data array" in (d / "stdout.txt").read_text()
    assert (d / "stderr.txt").read_text() == ""
    assert (d / "input.xml").read_text().startswith('<component id="root"')
    assert "no valid data array" in (d / "error.txt").read_text()


def test_missing_node_writes_failed_dir(tmp_path, monkeypatch, fake_bin):
    inner = FakeRunner(W)

    def no_l2(xml):
        r = dict(inner(xml))
        r.pop(("System", "L2 Cache 0"))
        return r

    _patch(monkeypatch, no_l2)
    cache = tmp_path / "cache"
    with pytest.raises(ch.CharacterizationRunError, match="L2 Cache 0") as ei:
        get_coefficients(base_cfg(), fake_bin, cache)
    assert isinstance(ei.value.__cause__.__cause__, ch.McpatOutputError)
    h = ch.cache_key(base_cfg(), ch.mcpat_sha256(fake_bin))
    d = cache / "failed" / f"{h}-baseline"
    assert "L2 Cache 0" in (d / "error.txt").read_text() and (d / "input.xml").exists()
    assert str(d) in str(ei.value)


def test_node_missing_raises_output_error_with_stdout():
    from power.mcpat_runner import McpatOutput
    r = McpatOutput({("System",): _cp(0, 0)})
    r.stdout = "the raw output"
    with pytest.raises(ch.McpatOutputError, match="Core 0") as ei:
        ch.component_energies(r, 0)
    assert isinstance(ei.value, McpatError) and ei.value.stdout == "the raw output"


# ---- F5: the cache key fingerprints the generator --------------------------
def test_cache_key_includes_generator_fingerprint():
    c = base_cfg()
    assert ch.cache_key(c, "sha") == config_hash(c, "sha", SCHEMA_VERSION,
                                                 ch.generator_fingerprint(c))
    assert ch.cache_key(c, "sha") != config_hash(c, "sha", SCHEMA_VERSION)


@pytest.mark.parametrize("name,value", [("N_EVENT", 100_000), ("C0", 2_000_000)])
def test_cache_key_changes_with_constants(monkeypatch, name, value):
    before = ch.cache_key(base_cfg(), "sha")
    monkeypatch.setattr(ch, name, value)
    assert ch.cache_key(base_cfg(), "sha") != before


def test_cache_key_changes_with_baseline_xml(monkeypatch):
    before = ch.cache_key(base_cfg(), "sha")
    real = ch.build_xml
    monkeypatch.setattr(ch, "build_xml", lambda *a, **k: real(*a, **k) + "<!-- v2 -->")
    assert ch.cache_key(base_cfg(), "sha") != before


def test_cache_key_changes_with_event_list(monkeypatch):
    before = ch.cache_key(base_cfg(), "sha")
    real = ch.events_for
    monkeypatch.setattr(ch, "events_for", lambda kind: real(kind)[:-1])
    assert ch.cache_key(base_cfg(), "sha") != before


def test_get_coefficients_file_named_by_cache_key(tmp_path, monkeypatch, fake_bin):
    _patch(monkeypatch, FakeRunner(W))
    co, p = get_coefficients(base_cfg(), fake_bin, tmp_path)
    h = ch.cache_key(base_cfg(), ch.mcpat_sha256(fake_bin))
    assert p.name == f"{h}.json" and co.config_hash == h
