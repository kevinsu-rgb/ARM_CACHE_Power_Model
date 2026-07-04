"""
This module contains a three-level cache hierarchy with private L1 caches,
private L2 caches, and a shared L3 cache.
"""

from m5.objects import PowerModel, MathExprPowerModel
from gem5.components.boards.abstract_board import AbstractBoard
from gem5.components.cachehierarchies.classic.abstract_classic_cache_hierarchy import (
    AbstractClassicCacheHierarchy,
)

from m5.objects import LRURP

from m5.objects import (
    BadAddr,
    Cache,
    L2XBar,
    SystemXBar,
    SubSystem,
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
        l1d_replacement_policy=LRURP(),
        l1i_replacement_policy=LRURP(),
        l2_replacement_policy=LRURP(),
        l3_replacement_policy=LRURP(),
        # l1d_block_size=64,
        # l1i_block_size=64,
        # l2_block_size=64,
        # l3_block_size=64,
    ):
        AbstractClassicCacheHierarchy.__init__(self)

        # Save the sizes to use later. We have to use leading underscores
        # because the SimObject (SubSystem) does not have these attributes as
        # parameters.
        self._l1d_size = l1d_size
        self._l1i_size = l1i_size
        self._l2_size = l2_size
        self._l3_size = l3_size
        self._l1d_assoc = l1d_assoc
        self._l1i_assoc = l1i_assoc
        self._l2_assoc = l2_assoc
        self._l3_assoc = l3_assoc
        self._l1d_replacement_policy = l1d_replacement_policy
        self._l1i_replacement_policy = l1i_replacement_policy
        self._l2_replacement_policy = l2_replacement_policy
        self._l3_replacement_policy = l3_replacement_policy
        # self._l1d_block_size = l1d_block_size
        # self._l1i_block_size = l1i_block_size
        # self._l2_block_size = l2_block_size
        # self._l3_block_size = l3_block_size

        # Use a high-bandwidth system crossbar.
        self.membus = SystemXBar(width=64)
        # For FS mode
        self.membus.badaddr_responder = BadAddr()
        self.membus.default = self.membus.badaddr_responder.pio

        # We can't create the caches yet, because we don't know how many cores there are.

    # To connect the memory system to the caches
    def get_mem_side_port(self):
        return self.membus.mem_side_ports

    # For FS mode. This is a coherent port.
    def get_cpu_side_port(self):
        return self.membus.cpu_side_ports

    # This is where the bulk of the work happens.
    # The board calls this function after it has created the processor and
    # memory system. The cache hierarchy is responsible for connecting things.
    def incorporate_cache(self, board):
        # Connect the system port to the memory system.
        board.connect_system_port(self.membus.cpu_side_ports)

        # Connect the memory system to the memory port on the board.
        for _, port in board.get_memory().get_mem_ports():
            self.membus.mem_side_ports = port

        # Create an L3 crossbar
        self.l3_bus = L2XBar()

        self.clusters = [
            self._create_core_cluster(
                core, self.l3_bus, board.get_processor().get_isa()
            )
            for core in board.get_processor().get_cores()
        ]

        self.l3_cache = L3Cache(
            size=self._l3_size,
            assoc=self._l3_assoc,
            replacement_policy=self._l3_replacement_policy,
        )

        # Connect the L3 cache to the system crossbar and L3 crossbar
        self.l3_cache.mem_side = self.membus.cpu_side_ports
        self.l3_cache.cpu_side = self.l3_bus.mem_side_ports

        if board.has_coherent_io():
            self._setup_io_cache(board)

    def _create_core_cluster(self, core, l3_bus, isa):
        """
        Create a core cluster with the given core.
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

        cluster.l2_bus = L2XBar()

        # Connect the core to the caches
        core.connect_icache(cluster.l1icache.cpu_side)
        core.connect_dcache(cluster.l1dcache.cpu_side)

        # Connect the caches to the L2 bus
        cluster.l1dcache.mem_side = cluster.l2_bus.cpu_side_ports
        cluster.l1icache.mem_side = cluster.l2_bus.cpu_side_ports

        cluster.l2cache.cpu_side = cluster.l2_bus.mem_side_ports

        cluster.l2cache.mem_side = l3_bus.cpu_side_ports

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

    def add_power_model(self):
        """called after preinstantiate"""

        self.l3_cache.power_state.default_state = "ON"
        self.l3_cache.power_model = L3PowerModel(self.l3_cache.path(), self._l3_size)

        # L1/L2 for every core cluster
        for cluster in self.clusters:
            # --- L1I ---
            cluster.l1icache.power_state.default_state = "ON"
            cluster.l1icache.power_model = L1PowerModel(
                cluster.l1icache.path(), self._l1i_size
            )

            # --- L1D ---
            cluster.l1dcache.power_state.default_state = "ON"
            cluster.l1dcache.power_model = L1PowerModel(
                cluster.l1dcache.path(), self._l1d_size
            )

            # --- L2 ---
            cluster.l2cache.power_state.default_state = "ON"
            cluster.l2cache.power_model = L2PowerModel(
                cluster.l2cache.path(), self._l2_size
            )


# Configured latency similar to ARM Cortex A55
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


# L3 Cache Power Class Definitions
class L3PowerOn(MathExprPowerModel):
    def __init__(self, l3_path, size, **kwargs):
        super().__init__(**kwargs)
        # Example to report l3 Cache overallAccesses
        # The estimated power is converted to Watt and will vary based
        # on the size of the cache
        # 80pJ access and 240pJ miss
        self.dyn = (
            f"({l3_path}.overallAccesses * 0.000_000_000_080 + "
            f"{l3_path}.overallMisses * 0.000_000_000_240) / (simSeconds)"
        )
        size_bytes = toMemorySize(size)
        print(size_bytes)
        self.st = f"{size_bytes} * 5 / 1000000000000"  # 5 pW per byte


class L3PowerClkGated(MathExprPowerModel):
    def __init__(self, size, **kwargs):
        super().__init__(**kwargs)
        size_bytes = toMemorySize(size)
        gated_fraction = 0.3  # assume 30% of full static power
        self.dyn = "0"
        self.st = f"({size_bytes} * {gated_fraction} * 5 / 1000000000000)"


class L3PowerSRAMRetention(MathExprPowerModel):
    def __init__(self, size, **kwargs):
        super().__init__(**kwargs)
        size_bytes = toMemorySize(size)
        retention_fraction = 0.05  # 5% of full static power
        self.dyn = "0"
        self.st = f"({size_bytes} * {retention_fraction} * 5 / 1000000000000)"


class L3PowerOff(MathExprPowerModel):
    dyn = "0"
    st = "0"


# L2 Cache Power Class Definitions
class L2PowerOn(MathExprPowerModel):
    def __init__(self, l2_path, size, **kwargs):
        super().__init__(**kwargs)
        # Example to report l2 Cache overallAccesses
        # The estimated power is converted to Watt and will vary based
        # on the size of the cache
        self.dyn = (
            f"({l2_path}.overallAccesses * 0.000_000_000_060 + "
            f"{l2_path}.overallMisses * 0.000_000_000_180) / (simSeconds)"
        )
        size_bytes = toMemorySize(size)
        print(size_bytes)
        self.st = f"{size_bytes} * 4 / 1000000000000"  # 4 pW per byte


class L2PowerClkGated(MathExprPowerModel):
    def __init__(self, size, **kwargs):
        super().__init__(**kwargs)
        size_bytes = toMemorySize(size)
        gated_fraction = 0.3  # assume 30% of full static power
        self.dyn = "0"
        self.st = f"({size_bytes} * {gated_fraction} * 4 / 1000000000000)"


class L2PowerSRAMRetention(MathExprPowerModel):
    def __init__(self, size, **kwargs):
        super().__init__(**kwargs)
        size_bytes = toMemorySize(size)
        retention_fraction = 0.05  # 5% of full static power
        self.dyn = "0"
        self.st = f"({size_bytes} * {retention_fraction} * 4/ 1000000000000)"


class L2PowerOff(MathExprPowerModel):
    dyn = "0"
    st = "0"


# L1 Cache Power Class Definitions
class L1PowerOn(MathExprPowerModel):
    def __init__(self, l1_path, size, **kwargs):
        super().__init__(**kwargs)
        # Example to report l1 Cache overallAccesses
        # The estimated power is converted to Watt and will vary based
        # on the size of the cache
        self.dyn = (
            f"({l1_path}.overallAccesses * 0.000_000_000_012 + "
            f"{l1_path}.overallMisses * 0.000_000_000_045) / (simSeconds)"
        )
        size_bytes = toMemorySize(size)
        print(size_bytes)
        self.st = f"{size_bytes} * 3 / 1000000000000"  # 3 pW per byte


class L1PowerClkGated(MathExprPowerModel):
    def __init__(self, size, **kwargs):
        super().__init__(**kwargs)
        size_bytes = toMemorySize(size)
        gated_fraction = 0.3  # assume 30% of full static power
        self.dyn = "0"
        self.st = f"({size_bytes} * {gated_fraction} * 3/ 1000000000000)"


class L1PowerSRAMRetention(MathExprPowerModel):
    def __init__(self, size, **kwargs):
        super().__init__(**kwargs)
        size_bytes = toMemorySize(size)
        retention_fraction = 0.05  # 5% of full static power
        self.dyn = "0"
        self.st = f"({size_bytes} * {retention_fraction} * 3 / 1000000000000)"


class L1PowerOff(MathExprPowerModel):
    dyn = "0"
    st = "0"


class L3PowerModel(PowerModel):
    def __init__(self, l3_path, size, **kwargs):
        super().__init__(**kwargs)
        # Choose a power model for every power state
        self.pm = [
            L3PowerOn(l3_path, size),  # ON
            L3PowerClkGated(size),  # CLK_GATED
            L3PowerSRAMRetention(size),  # SRAM_RETENTION
            L3PowerOff(),  # OFF
        ]


class L2PowerModel(PowerModel):
    def __init__(self, l2_path, size, **kwargs):
        super().__init__(**kwargs)
        # Choose a power model for every power state
        self.pm = [
            L2PowerOn(l2_path, size),  # ON
            L2PowerClkGated(size),  # CLK_GATED
            L2PowerSRAMRetention(size),  # SRAM_RETENTION
            L2PowerOff(),  # OFF
        ]


class L1PowerModel(PowerModel):
    def __init__(self, l1_path, size, **kwargs):
        super().__init__(**kwargs)
        # Choose a power model for every power state
        self.pm = [
            L1PowerOn(l1_path, size),  # ON
            L1PowerClkGated(size),  # CLK_GATED
            L1PowerSRAMRetention(size),  # SRAM_RETENTION
            L1PowerOff(),  # OFF
        ]
