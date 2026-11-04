import argparse
import json
import os
import sys
from pathlib import Path

from three_level import PrivateL1PrivateL2SharedL3CacheHierarchy
from gem5.isas import ISA
from gem5.utils.requires import requires
from gem5.components.memory.multi_channel import DualChannelDDR4_2400
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.components.processors.base_cpu_processor import BaseCPUProcessor
from gem5.components.processors.base_cpu_core import BaseCPUCore
from gem5.components.boards.simple_board import SimpleBoard
from gem5.resources.resource import BinaryResource
from gem5.simulate.simulator import Simulator

import m5
from m5.util.convert import toFrequency

from power.characterize import SuperpositionError, get_coefficients
from power.config import (DEVICE_TYPES, HPI_FALLBACK_CORE, ConfigError,
                          PowerConfig, validate)
from power.cores import core_params_from_core, load_core_class, resolve_core_model
from power.mcpat_runner import McpatError, find_mcpat_bin
from power.models import attach_power_models

DEFAULT_GEM5_ROOT = "/home/kevin/Projects/gem5"

# ----------------- CLI -----------------
parser = argparse.ArgumentParser()

parser.add_argument(
    "--binary",
    type=str,
    default="program_arm64",
    help="Path to ARM64 binary",
)

# Everything after script options is passed to the benchmark
parser.add_argument(
    "workload_args",
    nargs=argparse.REMAINDER,
    help="Arguments passed to the benchmark binary",
)

parser.add_argument("--l1i_size", type=str, default="32KiB")
parser.add_argument("--l1i_assoc", type=int, default=8)
parser.add_argument("--l1d_size", type=str, default="32KiB")
parser.add_argument("--l1d_assoc", type=int, default=8)
parser.add_argument("--l2_size", type=str, default="256KiB")
parser.add_argument("--l2_assoc", type=int, default=16)
parser.add_argument("--l3_size", type=str, default="2MiB")
parser.add_argument("--l3_assoc", type=int, default=32)

# in bytes
parser.add_argument("--block_size", type=int, default=64)

parser.add_argument("--l1i_replacement_policy", type=str, default="LRURP")
parser.add_argument("--l1d_replacement_policy", type=str, default="LRURP")
parser.add_argument("--l2_replacement_policy", type=str, default="LRURP")
parser.add_argument("--l3_replacement_policy", type=str, default="LRURP")

parser.add_argument(
    "--cpu_type",
    type=str,
    default="O3",
    choices=["O3", "MINOR", "TIMING", "ATOMIC"],
)
parser.add_argument(
    "--core_model",
    type=str,
    default=None,
    choices=["o3_arm_v7a", "neoverse_v2"],
    help="O3 core model (default o3_arm_v7a); invalid with other cpu types",
)
parser.add_argument("--num_cores", type=int, default=1)
parser.add_argument("--clk_freq", type=str, default="1GHz")
parser.add_argument("--tech_node", type=int, default=28,
                    help="McPAT technology node in nm (22..90)")
parser.add_argument("--device_type", type=str, default="LOP",
                    choices=sorted(DEVICE_TYPES))
parser.add_argument("--temperature", type=int, default=350,
                    help="K; McPAT needs 300..400 in steps of 10")
parser.add_argument("--gem5_root", type=str, default=None)
parser.add_argument("--mcpat_bin", type=str, default=None)
parser.add_argument("--power_cache_dir", type=str, default=None)

args = parser.parse_args()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GEM5_ROOT = Path(args.gem5_root or os.environ.get("GEM5_ROOT") or DEFAULT_GEM5_ROOT)
CACHE_DIR = Path(args.power_cache_dir) if args.power_cache_dir else PROJECT_ROOT / "power_cache"

# ----------------- Require ARM -----------------
requires(isa_required=ISA.ARM)

# ----------------- Argument validation -----------------
if args.num_cores < 1:
    parser.error("--num_cores must be >= 1")
try:
    core_model = resolve_core_model(args.cpu_type, args.core_model)
    clock_mhz = round(toFrequency(args.clk_freq) / 1e6)
except (ConfigError, ValueError) as exc:
    parser.error(str(exc))

# ----------------- CPU -----------------
if args.cpu_type in ("O3", "MINOR"):
    core_cls = load_core_class(GEM5_ROOT, args.cpu_type, args.core_model)
    processor = BaseCPUProcessor(
        cores=[BaseCPUCore(core=core_cls(cpu_id=i), isa=ISA.ARM)
               for i in range(args.num_cores)]
    )
else:
    processor = SimpleProcessor(
        cpu_type=CPUTypes.TIMING if args.cpu_type == "TIMING" else CPUTypes.ATOMIC,
        isa=ISA.ARM,
        num_cores=args.num_cores,
    )

hierarchy = PrivateL1PrivateL2SharedL3CacheHierarchy(
    l1d_size=args.l1d_size,
    l1d_assoc=args.l1d_assoc,
    l1i_size=args.l1i_size,
    l1i_assoc=args.l1i_assoc,
    l2_size=args.l2_size,
    l2_assoc=args.l2_assoc,
    l3_size=args.l3_size,
    l3_assoc=args.l3_assoc,
    l1d_replacement_policy=args.l1d_replacement_policy,
    l1i_replacement_policy=args.l1i_replacement_policy,
    l2_replacement_policy=args.l2_replacement_policy,
    l3_replacement_policy=args.l3_replacement_policy,
)

# ----------------- Power coefficients (before simulating) -----------------
if args.cpu_type in ("O3", "MINOR"):
    core_params = core_params_from_core(processor.get_cores()[0].core, core_model)
else:
    core_params = HPI_FALLBACK_CORE

power_cfg = PowerConfig(
    cpu_type=args.cpu_type,
    core=core_params,
    caches=hierarchy.get_cache_params(args.block_size),
    num_cores=args.num_cores,
    clock_mhz=clock_mhz,
    tech_node_nm=args.tech_node,
    device_type=args.device_type,
    temperature_k=args.temperature,
)
try:
    validate(power_cfg)
except ConfigError as exc:
    parser.error(str(exc))

if core_model == "neoverse_v2":
    print(f"WARNING: core_model neoverse_v2 is a 4-5 nm design; "
          f"absolute power at {args.tech_node} nm is overstated.")
if args.cpu_type in ("TIMING", "ATOMIC"):
    print(f"WARNING: cpu_type {args.cpu_type} has no core power model; "
          "reporting cache power only.")

try:
    coeffs, coeffs_path = get_coefficients(
        power_cfg, find_mcpat_bin(args.mcpat_bin, PROJECT_ROOT), CACHE_DIR)
except (McpatError, SuperpositionError) as exc:
    sys.exit(f"ERROR: power characterization failed: {exc}")

print(f"Implied Vdd: {coeffs.implied_vdd:.2f} V "
      f"({args.tech_node} nm {args.device_type})")

outdir = Path(m5.options.outdir)
outdir.mkdir(parents=True, exist_ok=True)
(outdir / "power_meta.json").write_text(json.dumps({
    "config_hash": coeffs.config_hash,
    "coefficients_path": str(Path(coeffs_path).resolve()),
    "cpu_type": args.cpu_type,
    "core_model": core_model if args.cpu_type == "O3" else None,
    "num_cores": args.num_cores,
    "tech_node_nm": args.tech_node,
    "device_type": args.device_type,
    "temperature_k": args.temperature,
    "implied_vdd": coeffs.implied_vdd,
    "clock_mhz": clock_mhz,
}, indent=2))

board = SimpleBoard(
    cache_hierarchy=hierarchy,
    processor=processor,
    memory=DualChannelDDR4_2400(size="2GiB"),
    clk_freq=args.clk_freq,
)

# Cache line size for the whole system
board.cache_line_size = args.block_size

# ----------------- Workload -----------------
binary = BinaryResource(local_path=args.binary)

print("\n===== Simulation Configuration =====")
print(f"Binary: {binary.get_local_path()}")

print("\n--- Cache Configuration ---")
print(f"L1I: size={args.l1i_size}, assoc={args.l1i_assoc}, "
      f"replacement={args.l1i_replacement_policy}")
print(f"L1D: size={args.l1d_size}, assoc={args.l1d_assoc}, "
      f"replacement={args.l1d_replacement_policy}")
print(f"L2:  size={args.l2_size}, assoc={args.l2_assoc}, "
      f"replacement={args.l2_replacement_policy}")
print(f"L3:  size={args.l3_size}, assoc={args.l3_assoc}, "
      f"replacement={args.l3_replacement_policy}")
print(f"Block size: {args.block_size} bytes")

print("\n--- CPU Configuration ---")
print(f"CPU type: {args.cpu_type}")
print(f"Core model: {core_model}")
print(f"Num cores: {processor.get_num_cores()}")

print("\n--- Memory System ---")
print("Memory: DualChannelDDR4_2400, size=2GiB")
print(f"Clock frequency: {args.clk_freq}")

print("\n===== End Configuration =====\n")

# Pass benchmark arguments correctly to SE workload
# Example:
# gem5.opt main.py --binary benchmarks/needle/needle 2048 10 1
# -> args.workload_args == ['2048', '10', '1']
board.set_se_binary_workload(binary, arguments=args.workload_args)

# ----------------- Power model hook -----------------
original_pre_instantiate = board._pre_instantiate

def patched_pre_instantiate(*p_args, **p_kwargs):
    """Call original pre_instantiate, then add power models."""
    root = original_pre_instantiate(*p_args, **p_kwargs)

    # After caches are built & connected, attach power models
    attach_power_models(board, coeffs, args.cpu_type)
    print("Power model added successfully!")
    return root

board._pre_instantiate = patched_pre_instantiate

# ----------------- Run -----------------
sim = Simulator(board)
print("Beginning simulation with power model...")
sim.run()
print(f"Statistics dumped to {m5.options.outdir}/stats.txt")