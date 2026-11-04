import json
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
LEAK = {"core": 1.0, "l1i": 0.1, "l1d": 0.2, "l2": 0.3, "l3": 0.4}
_CID = {"system.core0": "core", "system.core0.icache": "l1i",
        "system.core0.dcache": "l1d", "system.L20": "l2", "system.L30": "l3"}


def _cp(e, leak):
    return ComponentPower(runtime_dynamic_energy_j=e, subthreshold_leakage_w=leak)


class FakeRunner:
    def __init__(self, weights, quadratic_on=None):
        self.w, self.q = weights, quadratic_on
        self.calls = 0

    def __call__(self, xml_text):
        self.calls += 1
        root = ET.fromstring(xml_text)
        vals = {}
        for c in root.iter("component"):
            comp = _CID.get(c.get("id"))
            if comp is None:
                continue
            for s in c.findall("stat"):
                try:
                    vals[(comp, s.get("name"))] = float(s.get("value"))
                except ValueError:
                    pass
        coupling = 1.0
        if self.q:
            total = sum(v for (c, n), v in vals.items() if n == self.q)
            coupling = 1.0 + 0.1 * total / 1e6
        e = {c: 0.0 for c in LEAK}
        for (c, n), v in vals.items():
            e[c] += self.w.get((c, n), 0.0) * v * coupling
        core = ("System", "Core 0")
        return {
            ("System",): _cp(0, 0),
            core: _cp(e["core"] + e["l1i"] + e["l1d"], LEAK["core"] + LEAK["l1i"] + LEAK["l1d"]),
            core + ("Instruction Fetch Unit", "Instruction Cache"): _cp(e["l1i"], LEAK["l1i"]),
            core + ("Load/Store Unit", "Data Cache"): _cp(e["l1d"], LEAK["l1d"]),
            ("System", "L2 Cache 0"): _cp(e["l2"], LEAK["l2"]),
            ("System", "L3 Cache"): _cp(e["l3"], LEAK["l3"]),
        }


def test_recovers_linear_coefficients_exactly():
    co = characterize(base_cfg(), FakeRunner(W), "sha")
    assert co.energy_j["l1d"]["l1d.read_accesses"] == pytest.approx(W[("l1d", "read_accesses")])
    assert co.energy_j["core"]["core.int_insts"] == pytest.approx(
        sum(W[("core", s)] for s in EVENTS["core.int_insts"].increments))
    assert co.leakage_w["l3"] == pytest.approx(LEAK["l3"])
    assert co.leakage_w["core"] == pytest.approx(LEAK["core"])


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
    h = config_hash(base_cfg(), ch.mcpat_sha256(fake_bin), SCHEMA_VERSION)
    d = cache / "failed" / f"{h}-l2.read_accesses"
    assert (d / "input.xml").exists() and "boom" in (d / "error.txt").read_text()
    assert not (cache / f"{h}.json").exists()


@pytest.mark.mcpat
def test_real_characterization_o3_28nm(tmp_path, mcpat_bin):
    co, _ = get_coefficients(base_cfg(), mcpat_bin, tmp_path)
    assert co.implied_vdd == 0.6
    assert all(co.leakage_w[c] > 0 for c in ch.COMPONENTS)
    assert co.energy_j["l1d"]["l1d.read_accesses"] > 0


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
