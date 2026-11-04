"""McPAT characterization: leakage and energy-per-event coefficients, with cache."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from power.config import (SCHEMA_VERSION, PowerConfig, config_from_dict,
                          config_hash, config_to_dict, implied_vdd)
from power.events import events_for
from power.mcpat_runner import (McpatError, McpatResult, find_mcpat_bin,
                                mcpat_sha256, run_mcpat)
from power.mcpat_xml import build_xml

C0 = 1_000_000
N_EVENT = 1_000_000
REL_TOL = 0.01
ABS_TOL_J = 1e-12
DROP_BELOW_J = 1e-30
COMPONENTS = ("core", "l1i", "l1d", "l2", "l3")

Runner = Callable[[str], McpatResult]


class SuperpositionError(RuntimeError):
    """The all-at-once run deviates from the sum of single-event runs."""

    def __init__(self, message: str, deviations: dict[str, float]):
        super().__init__(message)
        self.deviations = deviations


class CharacterizationRunError(McpatError):
    """A McPAT run failed; carries the event name and the XML that was run."""

    def __init__(self, message: str, event: str, xml_text: str):
        super().__init__(message)
        self.event = event
        self.xml_text = xml_text


def _node(r: McpatResult, path: tuple[str, ...]):
    try:
        return r[path]
    except KeyError:
        raise KeyError(f"McPAT output has no node {'/'.join(path)!r}") from None


def _paths(i: int) -> dict[str, tuple[str, ...]]:
    core = ("System", f"Core {i}")
    return {
        "core": core,
        "l1i": core + ("Instruction Fetch Unit", "Instruction Cache"),
        "l1d": core + ("Load/Store Unit", "Data Cache"),
        "l2": ("System", f"L2 Cache {i}"),
        "l3": ("System", "L3 Cache"),
    }


def _component_values(r: McpatResult, core_index: int, getter) -> dict[str, float]:
    p = _paths(core_index)
    v = {c: getter(_node(r, p[c])) for c in COMPONENTS}
    v["core"] -= v["l1i"] + v["l1d"]
    return v


def component_energies(r: McpatResult, core_index: int = 0) -> dict[str, float]:
    return _component_values(r, core_index, lambda n: n.runtime_dynamic_energy_j)


def component_leakage(r: McpatResult, core_index: int = 0) -> dict[str, float]:
    return _component_values(r, core_index, lambda n: n.leakage_w)


@dataclass
class Coefficients:
    schema_version: int
    config: dict
    config_hash: str
    mcpat_sha256: str
    implied_vdd: float
    leakage_w: dict[str, float]
    energy_j: dict[str, dict[str, float]]
    created: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, s: str) -> Coefficients:
        return cls(**json.loads(s))


def characterize(cfg: PowerConfig, runner: Runner, mcpat_sha: str) -> Coefficients:
    """Derive leakage and per-event energies by differencing McPAT runs.

    Raises:
        CharacterizationRunError: a McPAT run failed.
        SuperpositionError: the all-events run is not the sum of single-event runs.
    """
    base_cyc = {i: C0 for i in range(cfg.num_cores)}
    sysc = 2 * C0

    def run(label: str, counts: dict, cyc: dict) -> McpatResult:
        xml = build_xml(cfg, counts, sysc, cyc)
        try:
            return runner(xml)
        except CharacterizationRunError:
            raise
        except McpatError as e:
            raise CharacterizationRunError(str(e), label, xml) from e

    base = run("baseline", {}, base_cyc)
    e0 = component_energies(base)
    leak = component_leakage(base)

    events = events_for(cfg.core.kind)

    def one(e: str) -> dict[str, float]:
        if e == "core.cycles":
            counts, cyc = {}, {**base_cyc, 0: C0 + N_EVENT}
        else:
            counts, cyc = {(0, e): N_EVENT}, dict(base_cyc)
        return component_energies(run(e, counts, cyc))

    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as ex:
        results = list(ex.map(one, events))

    energy_j: dict[str, dict[str, float]] = {c: {} for c in COMPONENTS}
    for e, ee in zip(events, results):
        for c in COMPONENTS:
            v = (ee[c] - e0[c]) / N_EVENT
            if abs(v) >= DROP_BELOW_J:
                energy_j[c][e] = v

    all_counts = {(0, e): N_EVENT for e in events if e != "core.cycles"}
    eall = component_energies(run("all", all_counts, {**base_cyc, 0: C0 + N_EVENT}))
    deviations: dict[str, float] = {}
    bad = []
    for c in COMPONENTS:
        predicted = e0[c] + sum(energy_j[c].values()) * N_EVENT
        dev = abs(eall[c] - predicted)
        delta = abs(eall[c] - e0[c])
        deviations[c] = dev / delta if delta > 0 else (0.0 if dev == 0 else float("inf"))
        if dev > max(REL_TOL * delta, ABS_TOL_J):
            bad.append(f"{c}: {deviations[c]:.4g} relative (abs {dev:.4g} J)")
    if bad:
        raise SuperpositionError(
            "superposition check failed (tolerance "
            f"{REL_TOL:.0%}, floor {ABS_TOL_J:g} J): " + "; ".join(bad), deviations)

    h = config_hash(cfg, mcpat_sha, SCHEMA_VERSION)
    return Coefficients(
        schema_version=SCHEMA_VERSION, config=json.loads(json.dumps(config_to_dict(cfg))), config_hash=h,
        mcpat_sha256=mcpat_sha, implied_vdd=implied_vdd(cfg.tech_node_nm, cfg.device_type),
        leakage_w=leak, energy_j=energy_j,
        created=datetime.now(timezone.utc).isoformat())


def _load_valid(path: Path, sha: str) -> Coefficients | None:
    try:
        co = Coefficients.from_json(path.read_text())
    except (OSError, ValueError, TypeError, KeyError):
        return None
    if co.schema_version != SCHEMA_VERSION or co.mcpat_sha256 != sha:
        return None
    return co


def get_coefficients(cfg: PowerConfig, mcpat_bin: Path,
                     cache_dir: Path) -> tuple[Coefficients, Path]:
    """Return cached coefficients for cfg, characterizing with McPAT if needed."""
    cache_dir = Path(cache_dir)
    sha = mcpat_sha256(mcpat_bin)
    h = config_hash(cfg, sha, SCHEMA_VERSION)
    path = cache_dir / f"{h}.json"
    if path.is_file():
        co = _load_valid(path, sha)
        if co is not None:
            return co, path

    cache_dir.mkdir(parents=True, exist_ok=True)
    work_root = cache_dir / ".work"
    work_root.mkdir(exist_ok=True)

    def runner(xml_text: str) -> McpatResult:
        wd = Path(tempfile.mkdtemp(dir=work_root))
        try:
            return run_mcpat(xml_text, mcpat_bin, wd)
        finally:
            shutil.rmtree(wd, ignore_errors=True)

    try:
        co = characterize(cfg, runner, sha)
    except CharacterizationRunError as e:
        d = cache_dir / "failed" / f"{h}-{e.event}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "input.xml").write_text(e.xml_text)
        (d / "error.txt").write_text(str(e) + "\n")
        raise
    finally:
        try:
            work_root.rmdir()
        except OSError:
            pass

    fd, tmp = tempfile.mkstemp(dir=cache_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(co.to_json())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return co, path


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(prog="python -m power.characterize")
    ap.add_argument("--config", required=True, help="JSON from config_to_dict")
    ap.add_argument("--mcpat_bin", default=None)
    ap.add_argument("--cache_dir", default=str(root / "power_cache"))
    a = ap.parse_args(argv)
    cfg = config_from_dict(json.loads(Path(a.config).read_text()))
    _, path = get_coefficients(cfg, find_mcpat_bin(a.mcpat_bin, root), Path(a.cache_dir))
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
