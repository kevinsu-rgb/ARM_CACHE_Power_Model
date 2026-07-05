import argparse
from types import MethodType

import m5

from three_level import PrivateL1PrivateL2SharedL3CacheHierarchy
from gem5.isas import ISA
from gem5.utils.requires import requires
from gem5.components.memory.multi_channel import DualChannelDDR4_2400
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.simulate.simulator import Simulator
from gem5.components.boards.simple_board import SimpleBoard
from gem5.resources.resource import BinaryResource
from m5.objects import LRURP, FIFORP, TreePLRURP


# ----------------- CLI -----------------
parser = argparse.ArgumentParser()

parser.add_argument(
    "--binary",
    type=str,
    default="tests/test_sample_arm64",
    help="Path to ARM64 binary",
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
    default="o3",
    choices=["o3", "timing", "atomic", "kvm"],
)

args = parser.parse_args()

# ----------------- Require ARM -----------------
requires(isa_required=ISA.ARM)


# ----------------- Cache Policy -----------------
l1i_policy = LRURP()
l1d_policy = LRURP()
l2_policy = LRURP()
l3_policy = LRURP()

if args.l1i_replacement_policy == "LRURP":
    l1i_policy = LRURP()
elif args.l1i_replacement_policy == "FIFORP":
    l1i_policy = FIFORP()
elif args.l1i_replacement_policy == "TreePLRURP":
    l1i_policy = TreePLRURP()
else:
    print("Invalid policy for l1i cache, default to LRURP")
    l1i_policy = LRURP()

if args.l1d_replacement_policy == "LRURP":
    l1d_policy = LRURP()
elif args.l1d_replacement_policy == "FIFORP":
    l1d_policy = FIFORP()
elif args.l1d_replacement_policy == "TreePLRURP":
    l1d_policy = TreePLRURP()
else:
    print("Invalid policy for l1d cache, default to LRURP")
    l1d_policy = LRURP()

if args.l2_replacement_policy == "LRURP":
    l2_policy = LRURP()
elif args.l2_replacement_policy == "FIFORP":
    l2_policy = FIFORP()
elif args.l2_replacement_policy == "TreePLRURP":
    l2_policy = TreePLRURP()
else:
    print("Invalid policy for l2 cache, default to LRURP")
    l2_policy = LRURP()

if args.l3_replacement_policy == "LRURP":
    l3_policy = LRURP()
elif args.l3_replacement_policy == "FIFORP":
    l3_policy = FIFORP()
elif args.l3_replacement_policy == "TreePLRURP":
    l3_policy = TreePLRURP()
else:
    print("Invalid policy for l3 cache, default to LRURP")
    l3_policy = LRURP()

# ----------------- CPU -----------------
if args.cpu_type == "timing":
    cpu_type = CPUTypes.TIMING
elif args.cpu_type == "atomic":
    cpu_type = CPUTypes.ATOMIC
elif args.cpu_type == "kvm":
    cpu_type = CPUTypes.KVM
elif args.cpu_type == "o3":
    cpu_type = CPUTypes.O3

processor = SimpleProcessor(
    cpu_type=cpu_type,
    isa=ISA.ARM,
    num_cores=1,
)

board = SimpleBoard(
    cache_hierarchy=PrivateL1PrivateL2SharedL3CacheHierarchy(
        l1d_size=args.l1i_size,
        l1d_assoc=args.l1i_assoc,
        l1i_size=args.l1d_size,
        l1i_assoc=args.l1d_assoc,
        l2_size=args.l2_size,
        l2_assoc=args.l2_assoc,
        l3_size=args.l3_size,
        l3_assoc=args.l3_assoc,
        l1d_replacement_policy=l1d_policy,
        l1i_replacement_policy=l1i_policy,
        l2_replacement_policy=l2_policy,
        l3_replacement_policy=l3_policy,
        # l1d_block_size=args.l1d_block_size,
        # l1i_block_size=args.l1i_block_size,
        # l2_block_size=args.l2_block_size,
        # l3_block_size=args.l3_block_size,
    ),
    processor=processor,
    memory=DualChannelDDR4_2400(size="4GB"),
    clk_freq="1GHz",
)

board.cache_line_size = args.block_size

# ----------------- Workload -----------------
binary = BinaryResource(local_path=args.binary)
print("\n===== Simulation Configuration =====")

print(f"Binary: {binary.get_local_path()}")

print("\n--- Cache Configuration ---")
print(
    f"L1I: size={args.l1i_size}, assoc={args.l1i_assoc}, "
    f"replacement={args.l1i_replacement_policy}"
)
print(
    f"L1D: size={args.l1d_size}, assoc={args.l1d_assoc}, "
    f"replacement={args.l1d_replacement_policy}"
)
print(
    f"L2:  size={args.l2_size}, assoc={args.l2_assoc}, "
    f"replacement={args.l2_replacement_policy}"
)
print(
    f"L3:  size={args.l3_size}, assoc={args.l3_assoc}, "
    f"replacement={args.l3_replacement_policy}"
)
print(f"Block size: {args.block_size} bytes")

print("\n--- CPU Configuration ---")
print(f"CPU type: {args.cpu_type}")

print("\n--- Memory System ---")
print("Memory: DualChannelDDR4_2400, size=2GB")
print("Clock frequency:", board.clk_domain.clock)

print("\n--- Replacement Policies ---")
print(f"L1I policy: {args.l1i_replacement_policy}")
print(f"L1D policy: {args.l1d_replacement_policy}")
print(f"L2 policy:  {args.l2_replacement_policy}")
print(f"L3 policy:  {args.l3_replacement_policy}")

print("\n===== End Configuration =====\n")

board.set_se_binary_workload(binary)


def set_up_power_model(board):
    board.get_cache_hierarchy().add_power_model()


def _instantiate_with_power_model(simulator):
    root = simulator._board._pre_instantiate(
        full_system=simulator._full_system
    )
    assert root is not None

    set_up_power_model(simulator._board)
    print("Power model added successfully!")

    if m5._simulate_module._instantiated:
        raise Exception(
            "m5.instantiate() called before `Simulator.run`"
            " Use either legacy m5.simulate or stdlib."
        )

    m5._simulate_module._instantiated = True
    m5._simulate_module._fix_all_objects(root)
    m5._simulate_module._dump_configs(root, str(simulator._outdir))

    if simulator._board._checkpoint:
        m5._simulate_module._create_cpp_objects(
            root, ckpt_dir=simulator._board._checkpoint.as_posix()
        )
    else:
        m5._simulate_module._create_cpp_objects(root, ckpt_dir=None)

    m5._simulate_module._dump_configs_post_cpp(root, str(simulator._outdir))

    simulator._root = root
    simulator._instantiated = True
    simulator._board._post_instantiate()


# Create and run simulator normally
sim = Simulator(board)
print("Beginning simulation with power model...")
sim._instantiate = MethodType(_instantiate_with_power_model, sim)
sim.run()

# Print where to find power stats
print("Statistics dumped to m5out/stats.txt")
