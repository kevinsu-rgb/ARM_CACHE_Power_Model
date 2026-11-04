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
    LRURP,
    FIFORP,
    TreePLRURP,
)

from m5.util.convert import toMemorySize

from power.config import CacheParams


def _get_policy(name):
    """Return a fresh replacement-policy instance for a policy name."""
    if name is None or name == "LRURP":
        return LRURP()
    if name == "FIFORP":
        return FIFORP()
    if name == "TreePLRURP":
        return TreePLRURP()
    print(f"Invalid policy '{name}', defaulting to LRURP")
    return LRURP()


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

        # Save sizes/assocs/policy names; each cache gets its own policy instance
        self._l1d_size = l1d_size
        self._l1i_size = l1i_size
        self._l2_size  = l2_size
        self._l3_size  = l3_size
        self._l1d_assoc = l1d_assoc
        self._l1i_assoc = l1i_assoc
        self._l2_assoc  = l2_assoc
        self._l3_assoc  = l3_assoc
        self._l1d_replacement_policy = l1d_replacement_policy or "LRURP"
        self._l1i_replacement_policy = l1i_replacement_policy or "LRURP"
        self._l2_replacement_policy  = l2_replacement_policy or "LRURP"
        self._l3_replacement_policy  = l3_replacement_policy or "LRURP"

        # High-bandwidth system crossbar.
        self.membus = SystemXBar(width=64)
        self.membus.badaddr_responder = BadAddr()
        self.membus.default = self.membus.badaddr_responder.pio

        # NOTE: Do NOT create self.clusters / self.l3_cache / self.l3_bus here
        # (that would conflict with SimObject param handling). We create them
        # later in incorporate_cache().

    def get_cache_params(self, block_size: int) -> tuple[CacheParams, ...]:
        """CacheParams for (l1i, l1d, l2, l3) as used by the power model."""
        def cp(name, size, assoc, tag, data, mshrs):
            return CacheParams(
                name=name, size_bytes=int(toMemorySize(size)), assoc=int(assoc),
                block_size=int(block_size),
                latency_cycles=tag + data, mshrs=mshrs)
        return (cp("l1i", self._l1i_size, self._l1i_assoc,
                  L1_TAG_LATENCY, L1_DATA_LATENCY, L1_MSHRS),
                cp("l1d", self._l1d_size, self._l1d_assoc,
                  L1_TAG_LATENCY, L1_DATA_LATENCY, L1_MSHRS),
                cp("l2", self._l2_size, self._l2_assoc,
                  L2_TAG_LATENCY, L2_DATA_LATENCY, L2_MSHRS),
                cp("l3", self._l3_size, self._l3_assoc,
                  L3_TAG_LATENCY, L3_DATA_LATENCY, L3_MSHRS))

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
            replacement_policy=_get_policy(self._l3_replacement_policy),
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
            replacement_policy=_get_policy(self._l1d_replacement_policy),
        )
        cluster.l1icache = L1Cache(
            size=self._l1i_size,
            assoc=self._l1i_assoc,
            replacement_policy=_get_policy(self._l1i_replacement_policy),
        )
        cluster.l2cache = L2Cache(
            size=self._l2_size,
            assoc=self._l2_assoc,
            replacement_policy=_get_policy(self._l2_replacement_policy),
        )

        # gem5 25.1: ARM MMU exposes a single walker port (dptw only)
        nwalk = len(core.get_mmu().walkerPorts())
        if nwalk == 2:
            cluster.iptw_cache = MMUCache(size="8KiB", writeback_clean=False)
        cluster.dptw_cache = MMUCache(size="8KiB", writeback_clean=False)

        cluster.l2_bus = L2XBar()

        # Core <-> L1I/L1D + TLB walkers
        core.connect_icache(cluster.l1icache.cpu_side)
        core.connect_dcache(cluster.l1dcache.cpu_side)
        if nwalk == 2:
            core.connect_walker_ports(
                cluster.iptw_cache.cpu_side, cluster.dptw_cache.cpu_side
            )
        else:
            core.connect_walker_ports(
                cluster.dptw_cache.cpu_side, cluster.dptw_cache.cpu_side
            )

        # L1 / PTW caches -> L2 bus
        cluster.l1dcache.mem_side = cluster.l2_bus.cpu_side_ports
        cluster.l1icache.mem_side = cluster.l2_bus.cpu_side_ports
        if nwalk == 2:
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


# --------------- Cache classes ---------------

L1_TAG_LATENCY = L1_DATA_LATENCY = 2
L1_MSHRS = 4
L2_TAG_LATENCY = L2_DATA_LATENCY = 10
L2_MSHRS = 6
L3_TAG_LATENCY = L3_DATA_LATENCY = 32
L3_MSHRS = 10

class L1Cache(Cache):
    def __init__(self, size, assoc, replacement_policy):
        super().__init__()
        self.size = size
        self.assoc = assoc
        self.replacement_policy = replacement_policy
        self.tag_latency = L1_TAG_LATENCY
        self.data_latency = L1_DATA_LATENCY
        self.response_latency = 1
        self.mshrs = L1_MSHRS
        self.tgts_per_mshr = 8
        self.writeback_clean = False
        self.clusivity = "mostly_incl"


class L2Cache(Cache):
    def __init__(self, size, assoc, replacement_policy):
        super().__init__()
        self.size = size
        self.assoc = assoc
        self.replacement_policy = replacement_policy
        self.tag_latency = L2_TAG_LATENCY
        self.data_latency = L2_DATA_LATENCY
        self.response_latency = 1
        self.mshrs = L2_MSHRS
        self.tgts_per_mshr = 8
        self.writeback_clean = False
        self.clusivity = "mostly_incl"


class L3Cache(Cache):
    def __init__(self, size, assoc, replacement_policy):
        super().__init__()
        self.size = size
        self.assoc = assoc
        self.replacement_policy = replacement_policy
        self.tag_latency = L3_TAG_LATENCY
        self.data_latency = L3_DATA_LATENCY
        self.response_latency = 1
        self.mshrs = L3_MSHRS
        self.tgts_per_mshr = 8
        self.writeback_clean = False
        self.clusivity = "mostly_incl"
