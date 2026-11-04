"""Event catalogue: gem5 activity events and the McPAT stats they drive."""
from __future__ import annotations

from dataclasses import dataclass, field

TARGETS = ("core", "l1i", "l1d", "l2", "l3")


@dataclass(frozen=True)
class EventSpec:
    """One characterizable event.

    target: component class receiving the increments.
    increments: McPAT stat name -> multiplier per event.
    ooo_only: event is meaningless for in-order cores.
    """
    target: str
    increments: dict[str, int] = field(default_factory=dict)
    ooo_only: bool = False


# (core_index, event name) -> count. L3 events use core_index 0.
ActivityCounts = dict[tuple[int, str], float]


def _core(*stats: str, ooo_only: bool = False) -> EventSpec:
    return EventSpec("core", {s: 1 for s in stats}, ooo_only)


EVENTS: dict[str, EventSpec] = {
    "core.cycles": _core("total_cycles"),
    "core.int_insts": _core("total_instructions", "int_instructions",
                            "committed_instructions", "committed_int_instructions"),
    "core.fp_insts": _core("total_instructions", "fp_instructions",
                           "committed_instructions", "committed_fp_instructions"),
    "core.load_insts": _core("load_instructions"),
    "core.store_insts": _core("store_instructions"),
    "core.branch_insts": _core("branch_instructions"),
    "core.branch_mispredicts": _core("branch_mispredictions"),
    "core.ialu": _core("ialu_accesses", "cdb_alu_accesses"),
    "core.fpu": _core("fpu_accesses", "cdb_fpu_accesses"),
    "core.int_rf_reads": _core("int_regfile_reads"),
    "core.int_rf_writes": _core("int_regfile_writes"),
    "core.fp_rf_reads": _core("float_regfile_reads"),
    "core.fp_rf_writes": _core("float_regfile_writes"),
    "core.rob_reads": _core("ROB_reads", ooo_only=True),
    "core.rob_writes": _core("ROB_writes", ooo_only=True),
    "core.int_rename_reads": _core("rename_reads", ooo_only=True),
    "core.int_rename_writes": _core("rename_writes", ooo_only=True),
    "core.fp_rename_reads": _core("fp_rename_reads", ooo_only=True),
    "core.int_iq_reads": _core("inst_window_reads", ooo_only=True),
    "core.int_iq_writes": _core("inst_window_writes", ooo_only=True),
    "core.int_iq_wakeups": _core("inst_window_wakeup_accesses", ooo_only=True),
    "core.fp_iq_reads": _core("fp_inst_window_reads", ooo_only=True),
    "core.fp_iq_writes": _core("fp_inst_window_writes", ooo_only=True),
    "core.fp_iq_wakeups": _core("fp_inst_window_wakeup_accesses", ooo_only=True),
}
for _t in ("l1i", "l1d", "l2", "l3"):
    for _s in ("read_accesses", "write_accesses", "read_misses"):
        EVENTS[f"{_t}.{_s}"] = EventSpec(_t, {_s: 1})


def events_for(kind: str) -> list[str]:
    """Event names applicable to a core kind ("ooo" or "inorder")."""
    if kind not in ("ooo", "inorder"):
        raise ValueError(f"unknown core kind {kind!r}")
    return [n for n, e in EVENTS.items() if kind == "ooo" or not e.ooo_only]
