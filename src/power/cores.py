"""ARM core class loading and core-parameter extraction (needs gem5 at call time)."""
from __future__ import annotations

import sys
from pathlib import Path

from power.config import ConfigError, CoreParams

# (ALUs, multipliers, FPUs) per core model; not derivable from the gem5 params.
FU_COUNTS = {"o3_arm_v7a": (2, 1, 2), "neoverse_v2": (6, 2, 4), "hpi": (2, 1, 1)}

DEFAULT_O3_MODEL = "o3_arm_v7a"


def resolve_core_model(cpu_type: str, core_model: str | None) -> str | None:
    """Return the effective core model, or None for types without one.

    Raises:
        ConfigError: core_model given with a non-O3 cpu_type, or unknown.
    """
    if cpu_type == "MINOR":
        if core_model is not None:
            raise ConfigError("--core_model is only valid with --cpu_type O3 "
                              "(MINOR always uses the HPI core)")
        return "hpi"
    if cpu_type != "O3":
        if core_model is not None:
            raise ConfigError("--core_model is only valid with --cpu_type O3")
        return None
    model = core_model or DEFAULT_O3_MODEL
    if model not in ("o3_arm_v7a", "neoverse_v2"):
        raise ConfigError(f"unknown core_model {model!r}; expected o3_arm_v7a or neoverse_v2")
    return model


def load_core_class(gem5_root: Path, cpu_type: str, core_model: str | None) -> type:
    """Import and return the gem5 CPU class for (cpu_type, core_model)."""
    configs = str(Path(gem5_root) / "configs")
    if configs not in sys.path:
        sys.path.insert(0, configs)
    model = resolve_core_model(cpu_type, core_model)
    if model == "o3_arm_v7a":
        from common.cores.arm.O3_ARM_v7a import O3_ARM_v7a_3
        return O3_ARM_v7a_3
    if model == "neoverse_v2":
        from common.cores.arm.neoverse_v2 import NeoverseV2
        return NeoverseV2
    if model == "hpi":
        from common.cores.arm.HPI import HPI
        return HPI
    raise ConfigError(f"cpu_type {cpu_type!r} has no ARM core class")


def core_params_from_core(cpu, model: str) -> CoreParams:
    """Build CoreParams from a constructed gem5 CPU instance."""
    alus, muls, fpus = FU_COUNTS[model]
    if model == "hpi":
        return CoreParams(
            kind="inorder", model=model,
            fetch_width=int(cpu.decodeInputWidth), decode_width=int(cpu.decodeInputWidth),
            issue_width=int(cpu.executeIssueLimit), commit_width=int(cpu.executeCommitLimit),
            rob_entries=0, iq_entries=0, lq_entries=0, sq_entries=0,
            phys_int_regs=0, phys_fp_regs=0,
            num_alus=alus, num_muls=muls, num_fpus=fpus)
    queues = cpu.instQueues
    if not isinstance(queues, (list, tuple)):
        try:
            queues = list(queues)
        except TypeError:
            queues = [queues]
    return CoreParams(
        kind="ooo", model=model,
        fetch_width=int(cpu.fetchWidth), decode_width=int(cpu.decodeWidth),
        issue_width=int(cpu.issueWidth), commit_width=int(cpu.commitWidth),
        rob_entries=int(cpu.numROBEntries),
        iq_entries=sum(int(q.numEntries) for q in queues),
        lq_entries=int(cpu.LQEntries), sq_entries=int(cpu.SQEntries),
        phys_int_regs=int(cpu.numPhysIntRegs), phys_fp_regs=int(cpu.numPhysVecRegs),
        num_alus=alus, num_muls=muls, num_fpus=fpus)
