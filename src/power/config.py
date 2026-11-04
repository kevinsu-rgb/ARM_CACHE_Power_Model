"""Power-model configuration types, validation, hashing and implied Vdd."""
from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass

DEVICE_TYPES = {"HP": 0, "LSTP": 1, "LOP": 2}
SCHEMA_VERSION = 1
CPU_TYPES = ("O3", "MINOR", "TIMING", "ATOMIC")
CACHE_NAMES = ("l1i", "l1d", "l2", "l3")
MIN_NODE_NM = 22
MAX_NODE_NM = 90

# McPAT cacti/technology.cc Vdd: node -> (HP, LSTP, LOP)
_VDD_TABLE = {
    22: (0.8, 0.8, 0.6),
    32: (0.9, 1.0, 0.6),
    45: (1.0, 1.1, 0.7),
    65: (1.1, 1.2, 0.8),
    90: (1.2, 1.3, 0.9),
}


class ConfigError(ValueError):
    """Invalid power configuration."""


@dataclass(frozen=True)
class CoreParams:
    kind: str  # "ooo" | "inorder"
    model: str
    fetch_width: int
    decode_width: int
    issue_width: int
    commit_width: int
    rob_entries: int
    iq_entries: int
    lq_entries: int
    sq_entries: int
    phys_int_regs: int
    phys_fp_regs: int
    num_alus: int
    num_muls: int
    num_fpus: int


@dataclass(frozen=True)
class CacheParams:
    name: str  # "l1i" | "l1d" | "l2" | "l3"
    size_bytes: int
    assoc: int
    block_size: int
    latency_cycles: int
    mshrs: int


@dataclass(frozen=True)
class PowerConfig:
    cpu_type: str
    core: CoreParams
    caches: tuple[CacheParams, ...]  # order: l1i, l1d, l2, l3
    num_cores: int
    clock_mhz: int
    tech_node_nm: int
    device_type: str
    temperature_k: int


HPI_FALLBACK_CORE = CoreParams(
    kind="inorder", model="hpi", fetch_width=2, decode_width=2, issue_width=2,
    commit_width=2, rob_entries=0, iq_entries=0, lq_entries=0, sq_entries=0,
    phys_int_regs=0, phys_fp_regs=0, num_alus=2, num_muls=1, num_fpus=1)


def implied_vdd(node_nm: int, device_type: str) -> float:
    """Vdd McPAT uses, linearly interpolated between table nodes."""
    if device_type not in DEVICE_TYPES:
        raise ConfigError(f"unknown device_type {device_type!r}")
    if not MIN_NODE_NM <= node_nm <= MAX_NODE_NM:
        raise ConfigError(f"tech_node_nm {node_nm} outside {MIN_NODE_NM}..{MAX_NODE_NM}")
    col = DEVICE_TYPES[device_type]
    nodes = sorted(_VDD_TABLE)
    if node_nm in _VDD_TABLE:
        return _VDD_TABLE[node_nm][col]
    hi = next(n for n in nodes if n > node_nm)
    lo = nodes[nodes.index(hi) - 1]
    w_lo = (hi - node_nm) / (hi - lo)
    return w_lo * _VDD_TABLE[lo][col] + (1 - w_lo) * _VDD_TABLE[hi][col]


def validate(cfg: PowerConfig) -> None:
    """Raise ConfigError if cfg is not a usable configuration."""
    if cfg.cpu_type not in CPU_TYPES:
        raise ConfigError(f"cpu_type {cfg.cpu_type!r} not in {CPU_TYPES}")
    if cfg.num_cores < 1:
        raise ConfigError("num_cores must be >= 1")
    if cfg.clock_mhz <= 0:
        raise ConfigError("clock_mhz must be > 0")
    if cfg.temperature_k <= 0:
        raise ConfigError("temperature_k must be > 0")
    if cfg.device_type not in DEVICE_TYPES:
        raise ConfigError(f"unknown device_type {cfg.device_type!r}")
    if not MIN_NODE_NM <= cfg.tech_node_nm <= MAX_NODE_NM:
        raise ConfigError(f"tech_node_nm {cfg.tech_node_nm} outside {MIN_NODE_NM}..{MAX_NODE_NM}")
    if cfg.core.kind not in ("ooo", "inorder"):
        raise ConfigError(f"core.kind {cfg.core.kind!r} must be 'ooo' or 'inorder'")
    if cfg.cpu_type == "MINOR" and cfg.core.kind != "inorder":
        raise ConfigError("MINOR requires an inorder core")
    if cfg.cpu_type == "O3" and cfg.core.kind != "ooo":
        raise ConfigError("O3 requires an ooo core")
    if tuple(c.name for c in cfg.caches) != CACHE_NAMES:
        raise ConfigError(f"caches must be exactly {CACHE_NAMES} in order")
    for c in cfg.caches:
        if c.size_bytes <= 0 or c.assoc <= 0 or c.block_size <= 0:
            raise ConfigError(f"cache {c.name}: size, assoc and block_size must be positive")


def config_to_dict(cfg: PowerConfig) -> dict:
    return dataclasses.asdict(cfg)


def config_from_dict(d: dict) -> PowerConfig:
    return PowerConfig(
        cpu_type=d["cpu_type"],
        core=CoreParams(**d["core"]),
        caches=tuple(CacheParams(**c) for c in d["caches"]),
        num_cores=d["num_cores"],
        clock_mhz=d["clock_mhz"],
        tech_node_nm=d["tech_node_nm"],
        device_type=d["device_type"],
        temperature_k=d["temperature_k"],
    )


def config_hash(cfg: PowerConfig, mcpat_sha: str, schema_version: int) -> str:
    payload = json.dumps({"config": config_to_dict(cfg), "mcpat": mcpat_sha,
                          "schema": schema_version}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
