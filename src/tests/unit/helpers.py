"""Shared test helpers."""
from power.config import CacheParams, CoreParams, PowerConfig


def base_cfg() -> PowerConfig:
    core = CoreParams(kind="ooo", model="o3_arm_v7a", fetch_width=3, decode_width=3,
                      issue_width=8, commit_width=8, rob_entries=40, iq_entries=32,
                      lq_entries=16, sq_entries=16, phys_int_regs=128, phys_fp_regs=48,
                      num_alus=2, num_muls=1, num_fpus=2)
    caches = (
        CacheParams("l1i", 32768, 8, 64, 4, 4),
        CacheParams("l1d", 32768, 8, 64, 4, 4),
        CacheParams("l2", 262144, 16, 64, 20, 6),
        CacheParams("l3", 2097152, 32, 64, 64, 10),
    )
    return PowerConfig(cpu_type="O3", core=core, caches=caches, num_cores=1,
                       clock_mhz=1000, tech_node_nm=28, device_type="LOP",
                       temperature_k=350)
