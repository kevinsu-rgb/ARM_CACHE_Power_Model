"""
Three-level cache hierarchy:
- Private L1I / L1D per core
- Private L2 per core
- Shared L3
"""

from gem5.components.boards.abstract_board import AbstractBoard
from gem5.components.cachehierarchies.classic.abstract_classic_cache_hierarchy import (
    AbstractClassicCacheHierarchy,
)
from gem5.components.cachehierarchies.classic.caches.mmu_cache import MMUCache

from gem5.isas import ISA

from m5.objects import (
    BadAddr,
    Cache,
    L2XBar,
    SystemXBar,
    SubSystem,
    PowerModel,
    MathExprPowerModel,
)

from m5.util.convert import toMemorySize


class PrivateL1PrivateL2SharedL3CacheHierarchy(AbstractClassicCacheHierarchy):
    def __init__(
        self,
        l1d_size,
        l1i_size,
        l2_size,
        l3_size,
        l1d_assoc=8,
        l1i_assoc=8,
        l2_assoc=16,
        l3_assoc=32,
        l1d_replacement_policy=None,
        l1i_replacement_policy=None,
        l2_replacement_policy=None,
        l3_replacement_policy=None,
    ):
        super().__init__()

        # Save sizes/assocs/policies for later (e.g., power model)
        self._l1d_size = l1d_size
        self._l1i_size = l1i_size
        self._l2_size  = l2_size
        self._l3_size  = l3_size
        self._l1d_assoc = l1d_assoc
        self._l1i_assoc = l1i_assoc
        self._l2_assoc  = l2_assoc
        self._l3_assoc  = l3_assoc
        self._l1d_replacement_policy = l1d_replacement_policy
        self._l1i_replacement_policy = l1i_replacement_policy
        self._l2_replacement_policy  = l2_replacement_policy
        self._l3_replacement_policy  = l3_replacement_policy

        # High-bandwidth system crossbar.
        self.membus = SystemXBar(width=64)
        self.membus.badaddr_responder = BadAddr()
        self.membus.default = self.membus.badaddr_responder.pio

        # NOTE: Do NOT create self.clusters / self.l3_cache / self.l3_bus here
        # (that would conflict with SimObject param handling). We create them
        # later in incorporate_cache().

    # To connect the memory system to the caches
    def get_mem_side_port(self):
        return self.membus.mem_side_ports

    # For FS mode. This is a coherent port.
    def get_cpu_side_port(self):
        return self.membus.cpu_side_ports

    def incorporate_cache(self, board):
        # Connect the system port to the memory system.
        board.connect_system_port(self.membus.cpu_side_ports)

        # Connect memory to membus
        for _, port in board.get_memory().get_mem_ports():
            self.membus.mem_side_ports = port

        # L3 fabric
        self.l3_bus = L2XBar()

        # One cluster per core: L1I/L1D + private L2
        self.clusters = [
            self._create_core_cluster(
                core, self.l3_bus, board.get_processor().get_isa()
            )
            for core in board.get_processor().get_cores()
        ]

        # Shared L3 cache
        self.l3_cache = L3Cache(
            size=self._l3_size,
            assoc=self._l3_assoc,
            replacement_policy=self._l3_replacement_policy,
        )

        # Connect L3 between per-core L2 bus and membus
        self.l3_cache.cpu_side = self.l3_bus.mem_side_ports
        self.l3_cache.mem_side = self.membus.cpu_side_ports

        if board.has_coherent_io():
            self._setup_io_cache(board)

    def _create_core_cluster(self, core, l3_bus, isa):
        """
        Create a core cluster with (L1I, L1D, L2, MMU caches).
        """
        cluster = SubSystem()

        cluster.l1dcache = L1Cache(
            size=self._l1d_size,
            assoc=self._l1d_assoc,
            replacement_policy=self._l1d_replacement_policy,
        )
        cluster.l1icache = L1Cache(
            size=self._l1i_size,
            assoc=self._l1i_assoc,
            replacement_policy=self._l1i_replacement_policy,
        )
        cluster.l2cache = L2Cache(
            size=self._l2_size,
            assoc=self._l2_assoc,
            replacement_policy=self._l2_replacement_policy,
        )

        cluster.iptw_cache = MMUCache(size="8KiB", writeback_clean=False)
        cluster.dptw_cache = MMUCache(size="8KiB", writeback_clean=False)

        cluster.l2_bus = L2XBar()

        # Core <-> L1I/L1D + TLB walkers
        core.connect_icache(cluster.l1icache.cpu_side)
        core.connect_dcache(cluster.l1dcache.cpu_side)
        core.connect_walker_ports(
            cluster.iptw_cache.cpu_side, cluster.dptw_cache.cpu_side
        )

        # L1 / PTW caches -> L2 bus
        cluster.l1dcache.mem_side = cluster.l2_bus.cpu_side_ports
        cluster.l1icache.mem_side = cluster.l2_bus.cpu_side_ports
        cluster.iptw_cache.mem_side = cluster.l2_bus.cpu_side_ports
        cluster.dptw_cache.mem_side = cluster.l2_bus.cpu_side_ports

        # L2 <-> L2 bus and L3 bus
        cluster.l2cache.cpu_side = cluster.l2_bus.mem_side_ports
        cluster.l2cache.mem_side = l3_bus.cpu_side_ports

        # Interrupt wiring
        if isa == ISA.X86:
            int_req_port = self.membus.mem_side_ports
            int_resp_port = self.membus.cpu_side_ports
            core.connect_interrupt(int_req_port, int_resp_port)
        else:
            core.connect_interrupt()

        return cluster

    def _setup_io_cache(self, board: AbstractBoard) -> None:
        """Create a cache for coherent I/O connections"""
        self.iocache = Cache(
            assoc=8,
            tag_latency=50,
            data_latency=50,
            response_latency=50,
            mshrs=20,
            size="1kB",
            tgts_per_mshr=12,
            addr_ranges=board.mem_ranges,
        )
        self.iocache.mem_side = self.membus.cpu_side_ports
        self.iocache.cpu_side = board.get_mem_side_coherent_io_port()

    # --------------- Power model plumbing ---------------
    def add_power_model(self):
        """Attach power models to all caches after instantiation."""

        # --- L3 ---
        self.l3_cache.power_state.default_state = "ON"
        self.l3_cache.power_model = L3PowerModel(
            self.l3_cache.path(),
            self._l3_size,
        )

        # --- Per-cluster L1I/L1D/L2 ---
        for cluster in self.clusters:
            # L1I
            cluster.l1icache.power_state.default_state = "ON"
            cluster.l1icache.power_model = L1PowerModel(
                cluster.l1icache.path(),
                self._l1i_size,
            )

            # L1D
            cluster.l1dcache.power_state.default_state = "ON"
            cluster.l1dcache.power_model = L1PowerModel(
                cluster.l1dcache.path(),
                self._l1d_size,
            )

            # L2
            cluster.l2cache.power_state.default_state = "ON"
            cluster.l2cache.power_model = L2PowerModel(
                cluster.l2cache.path(),
                self._l2_size,
            )


# --------------- Cache classes ---------------

class L1Cache(Cache):
    def __init__(self, size, assoc, replacement_policy):
        super().__init__()
        self.size = size
        self.assoc = assoc
        self.replacement_policy = replacement_policy
        self.tag_latency = 2
        self.data_latency = 2
        self.response_latency = 1
        self.mshrs = 4
        self.tgts_per_mshr = 8
        self.writeback_clean = False
        self.clusivity = "mostly_incl"


class L2Cache(Cache):
    def __init__(self, size, assoc, replacement_policy):
        super().__init__()
        self.size = size
        self.assoc = assoc
        self.replacement_policy = replacement_policy
        self.tag_latency = 10
        self.data_latency = 10
        self.response_latency = 1
        self.mshrs = 6
        self.tgts_per_mshr = 8
        self.writeback_clean = False
        self.clusivity = "mostly_incl"


class L3Cache(Cache):
    def __init__(self, size, assoc, replacement_policy):
        super().__init__()
        self.size = size
        self.assoc = assoc
        self.replacement_policy = replacement_policy
        self.tag_latency = 32
        self.data_latency = 32
        self.response_latency = 1
        self.mshrs = 10
        self.tgts_per_mshr = 8
        self.writeback_clean = False
        self.clusivity = "mostly_incl"


# --------------- MathExprPowerModel-based power models ---------------

# dyn, st are in Watts.
# We assume:
#   L1: 12 pJ / access, 45 pJ / miss
#   L2: 60 pJ / access, 180 pJ / miss
#   L3: 80 pJ / access, 240 pJ / miss
# Divide by simSeconds (global stat) to get average power.

from m5.objects import PowerModel, MathExprPowerModel

# --------------------------
# L3 Cache Power Model
# --------------------------

class L3PowerOn(MathExprPowerModel):
    def __init__(self, l3_path, size, **kwargs):
        super().__init__(**kwargs)
        # 80 pJ per access, 240 pJ per miss, converted to W by dividing by simSeconds
        self.dyn = (
            f"({l3_path}.overallAccesses * 0.000000000080 + "
            f"{l3_path}.overallMisses * 0.000000000240) / simSeconds"
        )
        size_bytes = toMemorySize(size)
        # 5 pW per byte
        self.st = f"({size_bytes} * 5.0) / 1000000000000.0"


class L3PowerClkGated(MathExprPowerModel):
    def __init__(self, size, **kwargs):
        super().__init__(**kwargs)
        size_bytes = toMemorySize(size)
        gated_fraction = 0.3  # 30% of full static power
        self.dyn = "0"
        self.st = f"({size_bytes} * {gated_fraction} * 5.0) / 1000000000000.0"


class L3PowerSRAMRetention(MathExprPowerModel):
    def __init__(self, size, **kwargs):
        super().__init__(**kwargs)
        size_bytes = toMemorySize(size)
        retention_fraction = 0.05  # 5% of full static power
        self.dyn = "0"
        self.st = f"({size_bytes} * {retention_fraction} * 5.0) / 1000000000000.0"


class L3PowerOff(MathExprPowerModel):
    # Simple constant-zero model
    dyn = "0"
    st  = "0"


# --------------------------
# L2 Cache Power Model
# --------------------------

class L2PowerOn(MathExprPowerModel):
    def __init__(self, l2_path, size, **kwargs):
        super().__init__(**kwargs)
        # 60 pJ per access, 180 pJ per miss
        self.dyn = (
            f"({l2_path}.overallAccesses * 0.000000000060 + "
            f"{l2_path}.overallMisses * 0.000000000180) / simSeconds"
        )
        size_bytes = toMemorySize(size)
        # 4 pW per byte
        self.st = f"({size_bytes} * 4.0) / 1000000000000.0"


class L2PowerClkGated(MathExprPowerModel):
    def __init__(self, size, **kwargs):
        super().__init__(**kwargs)
        size_bytes = toMemorySize(size)
        gated_fraction = 0.3
        self.dyn = "0"
        self.st = f"({size_bytes} * {gated_fraction} * 4.0) / 1000000000000.0"


class L2PowerSRAMRetention(MathExprPowerModel):
    def __init__(self, size, **kwargs):
        super().__init__(**kwargs)
        size_bytes = toMemorySize(size)
        retention_fraction = 0.05
        self.dyn = "0"
        self.st = f"({size_bytes} * {retention_fraction} * 4.0) / 1000000000000.0"


class L2PowerOff(MathExprPowerModel):
    dyn = "0"
    st  = "0"


# --------------------------
# L1 Cache Power Model
# --------------------------

class L1PowerOn(MathExprPowerModel):
    def __init__(self, l1_path, size, **kwargs):
        super().__init__(**kwargs)
        # 12 pJ per access, 45 pJ per miss
        self.dyn = (
            f"({l1_path}.overallAccesses * 0.000000000012 + "
            f"{l1_path}.overallMisses * 0.000000000045) / simSeconds"
        )
        size_bytes = toMemorySize(size)
        # 3 pW per byte
        self.st = f"({size_bytes} * 3.0) / 1000000000000.0"


class L1PowerClkGated(MathExprPowerModel):
    def __init__(self, size, **kwargs):
        super().__init__(**kwargs)
        size_bytes = toMemorySize(size)
        gated_fraction = 0.3
        self.dyn = "0"
        self.st = f"({size_bytes} * {gated_fraction} * 3.0) / 1000000000000.0"


class L1PowerSRAMRetention(MathExprPowerModel):
    def __init__(self, size, **kwargs):
        super().__init__(**kwargs)
        size_bytes = toMemorySize(size)
        retention_fraction = 0.05
        self.dyn = "0"
        self.st = f"({size_bytes} * {retention_fraction} * 3.0) / 1000000000000.0"


class L1PowerOff(MathExprPowerModel):
    dyn = "0"
    st  = "0"


# --------------------------
# Wrapper PowerModel classes
# --------------------------

class L3PowerModel(PowerModel):
    def __init__(self, l3_path, size, **kwargs):
        super().__init__(**kwargs)
        # Order: ON, CLK_GATED, SRAM_RETENTION, OFF
        self.pm = [
            L3PowerOn(l3_path, size),
            L3PowerClkGated(size),
            L3PowerSRAMRetention(size),
            L3PowerOff(),
        ]


class L2PowerModel(PowerModel):
    def __init__(self, l2_path, size, **kwargs):
        super().__init__(**kwargs)
        self.pm = [
            L2PowerOn(l2_path, size),
            L2PowerClkGated(size),
            L2PowerSRAMRetention(size),
            L2PowerOff(),
        ]


class L1PowerModel(PowerModel):
    def __init__(self, l1_path, size, **kwargs):
        super().__init__(**kwargs)
        self.pm = [
            L1PowerOn(l1_path, size),
            L1PowerClkGated(size),
            L1PowerSRAMRetention(size),
            L1PowerOff(),
        ]