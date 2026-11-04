"""Generate McPAT input XML from a PowerConfig and activity counts.

Default parameter dicts below are copied verbatim from the bundled McPAT
regression inputs (gem5/ext/mcpat/regression): test-0 (OoO core, machine_type 0)
and test-1 (in-order core, machine_type 1). Only fields listed in
``_core_overrides`` / ``_cache_overrides`` / ``_system_overrides`` come from cfg.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from .config import DEVICE_TYPES, CacheParams, PowerConfig
from .events import EVENTS, ActivityCounts

# Source: test-0 system
SYSTEM_PARAMS = {'core_tech_node': '40',
 'target_core_clockrate': '1700',
 'temperature': '380',
 'interconnect_projection_type': '1',
 'device_type': '0',
 'longer_channel_device': '0',
 'machine_bits': '64',
 'virtual_address_width': '64',
 'physical_address_width': '36',
 'virtual_memory_page_size': '4096',
 'wire_is_mat_type': '2',
 'wire_os_mat_type': '2',
 'delay_wt': '100',
 'area_wt': '0',
 'dynamic_power_wt': '100',
 'leakage_power_wt': '0',
 'cycle_time_wt': '0',
 'delay_dev': '10000',
 'area_dev': '10000',
 'dynamic_power_dev': '10000',
 'leakage_power_dev': '10000',
 'cycle_time_dev': '10000',
 'ed': '2',
 'burst_len': '1',
 'int_prefetch_w': '1',
 'page_sz_bits': '0',
 'rpters_in_htree': '1',
 'ver_htree_wires_over_array': '0',
 'nuca': '0',
 'nuca_bank_count': '0',
 'force_cache_config': '0',
 'wt': '0',
 'force_wiretype': '0',
 'print_detail': '1',
 'add_ecc_b_': '1',
 'broadcast_addr_din_over_ver_htrees': '0'}

# Source: test-0 system
SYSTEM_STATS = ['total_cycles']

# Source: test-0 core0
OOO_CORE_PARAMS = {'clock_rate': '1700',
 'opt_local': '0',
 'instruction_length': '32',
 'opcode_width': '8',
 'x86': '1',
 'micro_opcode_width': '8',
 'machine_type': '0',
 'number_hardware_threads': '2',
 'fetch_width': '1',
 'number_instruction_fetch_ports': '1',
 'decode_width': '2',
 'issue_width': '2',
 'peak_issue_width': '2',
 'commit_width': '2',
 'fp_issue_width': '2',
 'prediction_width': '1',
 'int_pipelines': '2',
 'fp_pipelines': '1',
 'int_pipeline_depth': '12',
 'fp_pipeline_depth': '13',
 'ALU_per_core': '2',
 'MUL_per_core': '1',
 'FPU_per_core': '1',
 'instruction_buffer_size': '16',
 'instruction_window_scheme': '0',
 'instruction_window_size': '7',
 'fp_instruction_window_size': '18',
 'ROB_size': '56',
 'archi_Regs_IRF_size': '30',
 'archi_Regs_FRF_size': '48',
 'phy_Regs_IRF_size': '34',
 'phy_Regs_FRF_size': '40',
 'rename_scheme': '0',
 'register_window_size': '0',
 'register_window_throughput': '4',
 'register_window_latency': '4',
 'store_buffer_size': '32',
 'load_buffer_size': '22',
 'memory_ports': '1',
 'RAS_size': '16',
 'execu_wire_mat_type': '2',
 'execu_bypass_base_width': '1',
 'execu_bypass_base_height': '1',
 'execu_bypass_start_wiring_level': '3',
 'execu_bypass_route_over_perc': '1',
 'globalCheckpoint': '32',
 'perThreadState': '8',
 'ROB_assoc': '1',
 'ROB_nbanks': '1',
 'ROB_tag_width': '0',
 'scheduler_assoc': '0',
 'scheduler_nbanks': '1',
 'register_window_assoc': '1',
 'register_window_nbanks': '1',
 'register_window_tag_width': '0',
 'register_window_rw_ports': '1',
 'phy_Regs_IRF_assoc': '1',
 'phy_Regs_IRF_nbanks': '1',
 'phy_Regs_IRF_tag_width': '0',
 'phy_Regs_IRF_rd_ports': '1',
 'phy_Regs_IRF_wr_ports': '1',
 'phy_Regs_FRF_assoc': '1',
 'phy_Regs_FRF_nbanks': '1',
 'phy_Regs_FRF_tag_width': '0',
 'phy_Regs_FRF_rd_ports': '1',
 'phy_Regs_FRF_wr_ports': '1',
 'front_rat_nbanks': '1',
 'front_rat_rw_ports': '1',
 'retire_rat_nbanks': '1',
 'retire_rat_rw_ports': '0',
 'freelist_nbanks': '1',
 'freelist_rw_ports': '1',
 'load_buffer_assoc': '0',
 'load_buffer_nbanks': '1',
 'store_buffer_assoc': '0',
 'store_buffer_nbanks': '1',
 'instruction_buffer_assoc': '1',
 'instruction_buffer_nbanks': '1',
 'instruction_buffer_tag_width': '0'}

# Source: test-0 core0
OOO_CORE_STATS = ['total_instructions',
 'int_instructions',
 'fp_instructions',
 'branch_instructions',
 'branch_mispredictions',
 'load_instructions',
 'store_instructions',
 'committed_instructions',
 'committed_int_instructions',
 'committed_fp_instructions',
 'pipeline_duty_cycle',
 'total_cycles',
 'ROB_reads',
 'ROB_writes',
 'rename_reads',
 'rename_writes',
 'fp_rename_reads',
 'fp_rename_writes',
 'inst_window_reads',
 'inst_window_writes',
 'inst_window_wakeup_accesses',
 'fp_inst_window_reads',
 'fp_inst_window_writes',
 'fp_inst_window_wakeup_accesses',
 'int_regfile_reads',
 'float_regfile_reads',
 'int_regfile_writes',
 'float_regfile_writes',
 'function_calls',
 'context_switches',
 'ialu_accesses',
 'fpu_accesses',
 'mul_accesses',
 'cdb_alu_accesses',
 'cdb_mul_accesses',
 'cdb_fpu_accesses',
 'IFU_duty_cycle',
 'LSU_duty_cycle',
 'MemManU_I_duty_cycle',
 'MemManU_D_duty_cycle',
 'ALU_duty_cycle',
 'MUL_duty_cycle',
 'FPU_duty_cycle',
 'ALU_cdb_duty_cycle',
 'MUL_cdb_duty_cycle',
 'FPU_cdb_duty_cycle']

# Source: test-1 core0
INORDER_CORE_PARAMS = {'opt_local': '0',
 'clock_rate': '2000',
 'instruction_length': '32',
 'opcode_width': '6',
 'machine_type': '1',
 'number_hardware_threads': '1',
 'fetch_width': '1',
 'number_instruction_fetch_ports': '1',
 'decode_width': '1',
 'issue_width': '1',
 'peak_issue_width': '1',
 'commit_width': '1',
 'fp_issue_width': '1',
 'prediction_width': '1',
 'int_pipelines': '1',
 'fp_pipelines': '1',
 'int_pipeline_depth': '7',
 'fp_pipeline_depth': '10',
 'ALU_per_core': '1',
 'FPU_per_core': '1',
 'MUL_per_core': '1',
 'instruction_buffer_size': '16',
 'instruction_window_scheme': '0',
 'instruction_window_size': '0',
 'fp_instruction_window_size': '0',
 'ROB_size': '0',
 'archi_Regs_IRF_size': '32',
 'archi_Regs_FRF_size': '32',
 'phy_Regs_IRF_size': '32',
 'phy_Regs_FRF_size': '32',
 'rename_scheme': '0',
 'register_window_size': '0',
 'store_buffer_size': '8',
 'load_buffer_size': '0',
 'memory_ports': '1',
 'RAS_size': '32',
 'execu_wire_mat_type': '2',
 'execu_bypass_base_width': '1',
 'execu_bypass_base_height': '1',
 'execu_bypass_start_wiring_level': '3',
 'execu_bypass_route_over_perc': '1',
 'globalCheckpoint': '32',
 'perThreadState': '8',
 'ROB_assoc': '1',
 'ROB_nbanks': '1',
 'ROB_tag_width': '0',
 'scheduler_assoc': '0',
 'scheduler_nbanks': '1',
 'register_window_assoc': '1',
 'register_window_nbanks': '1',
 'register_window_tag_width': '0',
 'register_window_rw_ports': '1',
 'phy_Regs_IRF_assoc': '1',
 'phy_Regs_IRF_nbanks': '1',
 'phy_Regs_IRF_tag_width': '0',
 'phy_Regs_IRF_rd_ports': '1',
 'phy_Regs_IRF_wr_ports': '1',
 'phy_Regs_FRF_assoc': '1',
 'phy_Regs_FRF_nbanks': '1',
 'phy_Regs_FRF_tag_width': '0',
 'phy_Regs_FRF_rd_ports': '1',
 'phy_Regs_FRF_wr_ports': '1',
 'front_rat_nbanks': '1',
 'front_rat_rw_ports': '1',
 'retire_rat_nbanks': '1',
 'retire_rat_rw_ports': '0',
 'freelist_nbanks': '1',
 'freelist_rw_ports': '1',
 'load_buffer_assoc': '0',
 'load_buffer_nbanks': '1',
 'store_buffer_assoc': '0',
 'store_buffer_nbanks': '1',
 'instruction_buffer_assoc': '1',
 'instruction_buffer_nbanks': '1',
 'instruction_buffer_tag_width': '0'}

# Source: test-1 core0
INORDER_CORE_STATS = ['total_instructions',
 'int_instructions',
 'fp_instructions',
 'branch_instructions',
 'branch_mispredictions',
 'load_instructions',
 'store_instructions',
 'committed_instructions',
 'committed_int_instructions',
 'committed_fp_instructions',
 'total_cycles',
 'idle_cycles',
 'busy_cycles',
 'ROB_reads',
 'ROB_writes',
 'rename_reads',
 'rename_writes',
 'fp_rename_reads',
 'fp_rename_writes',
 'inst_window_reads',
 'inst_window_writes',
 'inst_window_wakeup_accesses',
 'fp_inst_window_reads',
 'fp_inst_window_writes',
 'fp_inst_window_wakeup_accesses',
 'int_regfile_reads',
 'float_regfile_reads',
 'int_regfile_writes',
 'float_regfile_writes',
 'function_calls',
 'context_switches',
 'ialu_accesses',
 'fpu_accesses',
 'mul_accesses',
 'cdb_alu_accesses',
 'cdb_mul_accesses',
 'cdb_fpu_accesses',
 'IFU_duty_cycle',
 'LSU_duty_cycle',
 'MemManU_I_duty_cycle',
 'MemManU_D_duty_cycle',
 'ALU_duty_cycle',
 'MUL_duty_cycle',
 'FPU_duty_cycle',
 'ALU_cdb_duty_cycle',
 'MUL_cdb_duty_cycle',
 'FPU_cdb_duty_cycle']

# system.core0.predictor
OOO_PREDICTOR_PARAMS = {'assoc': '1',
 'nbanks': '1',
 'local_l1_predictor_size': '12',
 'local_l2_predictor_size': '4',
 'local_predictor_entries': '8192',
 'global_predictor_entries': '8192',
 'global_predictor_bits': '4',
 'chooser_predictor_entries': '8192',
 'chooser_predictor_bits': '4'}

# system.core0.predictor
OOO_PREDICTOR_STATS = []

# system.core0.bpred
INORDER_PREDICTOR_PARAMS = {'assoc': '1',
 'nbanks': '1',
 'local_l1_predictor_size': '10',
 'local_l2_predictor_size': '3',
 'local_predictor_entries': '1024',
 'global_predictor_entries': '4096',
 'global_predictor_bits': '2',
 'chooser_predictor_entries': '4096',
 'chooser_predictor_bits': '2'}

# system.core0.bpred
INORDER_PREDICTOR_STATS = []

# system.core0.itlb
OOO_ITLB_PARAMS = {'number_entries': '512', 'latency': '8', 'throughput': '3', 'assoc': '0', 'nbanks': '1'}

# system.core0.itlb
OOO_ITLB_STATS = ['total_accesses', 'total_misses', 'conflicts']

# system.core0.itlb
INORDER_ITLB_PARAMS = {'number_entries': '64', 'latency': '8', 'throughput': '3', 'assoc': '0', 'nbanks': '1'}

# system.core0.itlb
INORDER_ITLB_STATS = ['total_accesses', 'total_misses', 'conflicts']

# system.core0.dtlb
OOO_DTLB_PARAMS = {'number_entries': '512', 'latency': '8', 'throughput': '3', 'assoc': '0', 'nbanks': '1'}

# system.core0.dtlb
OOO_DTLB_STATS = ['read_accesses', 'read_misses', 'conflicts']

# system.core0.dtlb
INORDER_DTLB_PARAMS = {'number_entries': '64', 'latency': '8', 'throughput': '3', 'assoc': '0', 'nbanks': '1'}

# system.core0.dtlb
INORDER_DTLB_STATS = ['read_accesses', 'write_accesses', 'read_misses', 'write_misses', 'conflicts']

# system.core0.btargetbuf
BTB_PARAMS = {'size': '8192',
 'block_size': '4',
 'assoc': '2',
 'num_banks': '1',
 'latency': '1',
 'throughput': '3',
 'rw_ports': '1'}

# system.core0.btargetbuf
BTB_STATS = ['read_accesses', 'write_accesses']

# system.core0.icache
L1I_PARAMS = {'level': '1',
 'size': '32768',
 'block_size': '64',
 'assoc': '2',
 'num_banks': '1',
 'latency': '8',
 'throughput': '3',
 'miss_buffer_size': '2',
 'fetch_buffer_size': '2',
 'prefetch_buffer_size': '2',
 'writeback_buffer_size': '0',
 'clockrate': '0',
 'tech_type': '0',
 'Directory_type': '2',
 'device_type': '0',
 'core_type': '1',
 'wire_mat_type': '2',
 'wire_type': '0',
 'miss_buffer_assoc': '0',
 'fetch_buffer_assoc': '0',
 'prefetch_buffer_assoc': '0',
 'writeback_buffer_assoc': '0',
 'miss_buffer_banks': '1',
 'fetch_buffer_banks': '1',
 'prefetch_buffer_banks': '1',
 'writeback_buffer_banks': '1',
 'cache_access_mode': '0',
 'miss_buff_access_mode': '2',
 'fetch_buff_access_mode': '2',
 'prefetch_buff_access_mode': '2',
 'writeback_buff_access_mode': '2',
 'cache_rw_ports': '1',
 'cache_rd_ports': '0',
 'cache_wr_ports': '0',
 'cache_se_rd_ports': '0',
 'cache_search_ports': '0',
 'miss_buff_rw_ports': '1',
 'miss_buff_rd_ports': '0',
 'miss_buff_wr_ports': '0',
 'miss_buff_se_rd_ports': '0',
 'miss_buff_search_ports': '1',
 'fetch_buff_rw_ports': '1',
 'fetch_buff_rd_ports': '0',
 'fetch_buff_wr_ports': '0',
 'fetch_buff_se_rd_ports': '0',
 'fetch_buff_search_ports': '1',
 'pf_buff_rw_ports': '1',
 'pf_buff_rd_ports': '0',
 'pf_buff_wr_ports': '0',
 'pf_buff_se_rd_ports': '0',
 'pf_buff_search_ports': '1',
 'wb_buff_rw_ports': '1',
 'wb_buff_rd_ports': '0',
 'wb_buff_wr_ports': '0',
 'wb_buff_se_rd_ports': '0',
 'wb_buff_search_ports': '1',
 'pure_ram': '0'}

# system.core0.icache
L1I_STATS = ['read_accesses', 'read_misses', 'conflicts', 'duty_cycle']

# system.core0.dcache
L1D_PARAMS = {'level': '1',
 'size': '32768',
 'block_size': '64',
 'assoc': '8',
 'num_banks': '1',
 'latency': '8',
 'throughput': '3',
 'miss_buffer_size': '8',
 'fetch_buffer_size': '8',
 'prefetch_buffer_size': '8',
 'writeback_buffer_size': '8',
 'clockrate': '0',
 'tech_type': '0',
 'Directory_type': '2',
 'device_type': '0',
 'core_type': '1',
 'wire_mat_type': '2',
 'wire_type': '0',
 'miss_buffer_assoc': '0',
 'fetch_buffer_assoc': '0',
 'prefetch_buffer_assoc': '0',
 'writeback_buffer_assoc': '0',
 'miss_buffer_banks': '1',
 'fetch_buffer_banks': '1',
 'prefetch_buffer_banks': '1',
 'writeback_buffer_banks': '1',
 'cache_access_mode': '0',
 'miss_buff_access_mode': '2',
 'fetch_buff_access_mode': '2',
 'prefetch_buff_access_mode': '2',
 'writeback_buff_access_mode': '2',
 'cache_rw_ports': '1',
 'cache_rd_ports': '0',
 'cache_wr_ports': '0',
 'cache_se_rd_ports': '0',
 'cache_search_ports': '0',
 'miss_buff_rw_ports': '1',
 'miss_buff_rd_ports': '0',
 'miss_buff_wr_ports': '0',
 'miss_buff_se_rd_ports': '0',
 'miss_buff_search_ports': '1',
 'fetch_buff_rw_ports': '1',
 'fetch_buff_rd_ports': '0',
 'fetch_buff_wr_ports': '0',
 'fetch_buff_se_rd_ports': '0',
 'fetch_buff_search_ports': '1',
 'pf_buff_rw_ports': '1',
 'pf_buff_rd_ports': '0',
 'pf_buff_wr_ports': '0',
 'pf_buff_se_rd_ports': '0',
 'pf_buff_search_ports': '1',
 'wb_buff_rw_ports': '1',
 'wb_buff_rd_ports': '0',
 'wb_buff_wr_ports': '0',
 'wb_buff_se_rd_ports': '0',
 'wb_buff_search_ports': '1',
 'pure_ram': '0'}

# system.core0.dcache
L1D_STATS = ['read_accesses', 'write_accesses', 'read_misses', 'write_misses', 'conflicts', 'duty_cycle']

# system.L20
L2_PARAMS = {'level': '2',
 'size': '524288',
 'block_size': '64',
 'assoc': '16',
 'num_banks': '1',
 'latency': '8',
 'throughput': '23',
 'miss_buffer_size': '16',
 'fetch_buffer_size': '16',
 'prefetch_buffer_size': '16',
 'writeback_buffer_size': '16',
 'clockrate': '1700',
 'tech_type': '0',
 'Directory_type': '2',
 'device_type': '0',
 'core_type': '1',
 'wire_mat_type': '2',
 'wire_type': '0',
 'miss_buffer_assoc': '0',
 'fetch_buffer_assoc': '0',
 'prefetch_buffer_assoc': '0',
 'writeback_buffer_assoc': '0',
 'miss_buffer_banks': '1',
 'fetch_buffer_banks': '1',
 'prefetch_buffer_banks': '1',
 'writeback_buffer_banks': '1',
 'cache_access_mode': '1',
 'miss_buff_access_mode': '0',
 'fetch_buff_access_mode': '0',
 'prefetch_buff_access_mode': '0',
 'writeback_buff_access_mode': '0',
 'cache_rw_ports': '1',
 'cache_rd_ports': '0',
 'cache_wr_ports': '0',
 'cache_se_rd_ports': '0',
 'cache_search_ports': '0',
 'miss_buff_rw_ports': '1',
 'miss_buff_rd_ports': '0',
 'miss_buff_wr_ports': '0',
 'miss_buff_se_rd_ports': '0',
 'miss_buff_search_ports': '1',
 'fetch_buff_rw_ports': '1',
 'fetch_buff_rd_ports': '0',
 'fetch_buff_wr_ports': '0',
 'fetch_buff_se_rd_ports': '0',
 'fetch_buff_search_ports': '1',
 'pf_buff_rw_ports': '1',
 'pf_buff_rd_ports': '0',
 'pf_buff_wr_ports': '0',
 'pf_buff_se_rd_ports': '0',
 'pf_buff_search_ports': '1',
 'wb_buff_rw_ports': '1',
 'wb_buff_rd_ports': '0',
 'wb_buff_wr_ports': '0',
 'wb_buff_se_rd_ports': '0',
 'wb_buff_search_ports': '1',
 'pure_ram': '0'}

# system.L20
L2_STATS = ['read_accesses', 'write_accesses', 'read_misses', 'write_misses', 'conflicts', 'duty_cycle']


CACHE_STAT_NAMES = ("read_accesses", "write_accesses", "read_misses", "write_misses",
                    "conflicts", "duty_cycle")
_TARGET_ID = {"l1i": "icache", "l1d": "dcache"}
_LEVEL = {"l1i": 1, "l1d": 1, "l2": 2, "l3": 3}


def _num(v: float) -> str:
    """Format a count; whole numbers print as integers."""
    if float(v).is_integer():
        return str(int(v))
    return repr(float(v))


def _add(parent: ET.Element, cid: str, name: str, ctype: str,
         params: dict[str, str], stats: dict[str, str]) -> ET.Element:
    comp = ET.SubElement(parent, "component", id=cid, name=name, type=ctype)
    for k, v in params.items():
        ET.SubElement(comp, "param", name=k, value=str(v))
    for k, v in stats.items():
        ET.SubElement(comp, "stat", name=k, value=v)
    return comp


def _zero_stats(names, extra=()) -> dict[str, str]:
    out = {n: ("1.0" if n.endswith("duty_cycle") else "0") for n in names}
    for n in extra:
        out.setdefault(n, "1.0" if n.endswith("duty_cycle") else "0")
    return out


def _system_params(cfg: PowerConfig) -> dict[str, str]:
    p = dict(SYSTEM_PARAMS)
    p["core_tech_node"] = str(cfg.tech_node_nm)
    p["target_core_clockrate"] = str(cfg.clock_mhz)
    p["temperature"] = str(cfg.temperature_k)
    p["device_type"] = str(DEVICE_TYPES[cfg.device_type])
    return p


def _core_params(cfg: PowerConfig) -> dict[str, str]:
    ooo = cfg.core.kind == "ooo"
    c = cfg.core
    p = dict(OOO_CORE_PARAMS if ooo else INORDER_CORE_PARAMS)
    p["machine_type"] = "0" if ooo else "1"
    p["clock_rate"] = str(cfg.clock_mhz)
    p.update(fetch_width=str(c.fetch_width), decode_width=str(c.decode_width),
             issue_width=str(c.issue_width), commit_width=str(c.commit_width),
             ALU_per_core=str(c.num_alus), MUL_per_core=str(c.num_muls),
             FPU_per_core=str(c.num_fpus))
    # Window/buffer/register sizes: a 0 (e.g. in-order HPI) keeps the template
    # value, since 0-sized structures are not meaningful to McPAT for these.
    sized = {"ROB_size": c.rob_entries, "instruction_window_size": c.iq_entries,
             "load_buffer_size": c.lq_entries, "store_buffer_size": c.sq_entries,
             "phy_Regs_IRF_size": c.phys_int_regs, "phy_Regs_FRF_size": c.phys_fp_regs}
    for k, v in sized.items():
        if v > 0:
            p[k] = str(v)
    return p


def _cache_params(cfg: PowerConfig, target: str) -> dict[str, str]:
    base = {"l1i": L1I_PARAMS, "l1d": L1D_PARAMS, "l2": L2_PARAMS, "l3": L2_PARAMS}[target]
    cp: CacheParams = next(c for c in cfg.caches if c.name == target)
    p = dict(base)
    p.update(level=str(_LEVEL[target]), size=str(cp.size_bytes), assoc=str(cp.assoc),
             block_size=str(cp.block_size), latency=str(cp.latency_cycles),
             miss_buffer_size=str(cp.mshrs))
    p["device_type"] = str(DEVICE_TYPES[cfg.device_type])
    # clockrate 0 in the template L1s means "inherit the core clock"; keep it.
    if p.get("clockrate", "0") != "0":
        p["clockrate"] = str(cfg.clock_mhz)
    return p


def _cache_base_stats(target: str) -> tuple[str, ...]:
    return {"l1i": L1I_STATS, "l1d": L1D_STATS, "l2": L2_STATS, "l3": L2_STATS}[target]


def _validate_counts(cfg: PowerConfig, counts: ActivityCounts,
                     core_cycles: dict[int, int]) -> None:
    kind = cfg.core.kind
    for i in range(cfg.num_cores):
        if i not in core_cycles:
            raise ValueError(f"core_cycles missing core {i}")
    for (idx, ev) in counts:
        if ev == "core.cycles":
            raise ValueError("core.cycles must be passed via core_cycles, not counts")
        spec = EVENTS.get(ev)
        if spec is None:
            raise ValueError(f"unknown event {ev!r}")
        if spec.ooo_only and kind != "ooo":
            raise ValueError(f"event {ev!r} is OoO-only but core kind is {kind!r}")
        if spec.target == "l3":
            if idx != 0:
                raise ValueError(f"L3 event {ev!r} must use core_index 0, got {idx}")
        elif not 0 <= idx < cfg.num_cores:
            raise ValueError(f"event {ev!r}: core_index {idx} out of range")


def build_xml(cfg: PowerConfig, counts: ActivityCounts, system_cycles: int,
              core_cycles: dict[int, int]) -> str:
    """Return McPAT input XML for cfg with the given activity counts.

    Args:
        cfg: power configuration.
        counts: (core_index, event) -> count; never contains "core.cycles".
        system_cycles: system-level total_cycles.
        core_cycles: core_index -> that core's total_cycles.

    Raises:
        ValueError: unknown/OoO-only-on-in-order event, core.cycles in counts,
            out-of-range core index, or missing core_cycles entry.
    """
    _validate_counts(cfg, counts, core_cycles)
    ooo = cfg.core.kind == "ooo"

    # (component id, stat name) -> accumulated value
    acc: dict[tuple[str, str], float] = {}
    for (idx, ev), n in counts.items():
        spec = EVENTS[ev]
        if spec.target == "core":
            cid = f"system.core{idx}"
        elif spec.target in _TARGET_ID:
            cid = f"system.core{idx}.{_TARGET_ID[spec.target]}"
        elif spec.target == "l2":
            cid = f"system.L2{idx}"
        else:
            cid = "system.L30"
        for stat_name, mult in spec.increments.items():
            acc[(cid, stat_name)] = acc.get((cid, stat_name), 0.0) + n * mult

    def stats(cid: str, names, extra=()) -> dict[str, str]:
        s = _zero_stats(names, extra)
        for (c, name), v in acc.items():
            if c != cid:
                continue
            if name not in s:
                raise ValueError(f"stat {name!r} does not exist on {cid}")
            s[name] = _num(v)
        return s

    root = ET.Element("component", id="root", name="root")
    system = _add(root, "system", "system", "System", _system_params(cfg),
                  _zero_stats(SYSTEM_STATS))
    system.find("stat[@name='total_cycles']").set("value", _num(system_cycles))

    core_stat_names = OOO_CORE_STATS if ooo else INORDER_CORE_STATS
    pred = OOO_PREDICTOR_PARAMS if ooo else INORDER_PREDICTOR_PARAMS
    itlb, itlb_s = (OOO_ITLB_PARAMS, OOO_ITLB_STATS) if ooo else (INORDER_ITLB_PARAMS, INORDER_ITLB_STATS)
    dtlb, dtlb_s = (OOO_DTLB_PARAMS, OOO_DTLB_STATS) if ooo else (INORDER_DTLB_PARAMS, INORDER_DTLB_STATS)
    for i in range(cfg.num_cores):
        cid = f"system.core{i}"
        cs = stats(cid, core_stat_names)
        cs["total_cycles"] = _num(core_cycles[i])
        core = _add(system, cid, f"core{i}", "Core", _core_params(cfg), cs)
        _add(core, f"{cid}.predictor", "PBT" if ooo else "bpred", "BranchPredictor", pred, {})
        _add(core, f"{cid}.itlb", "itlb", "InstructionTLB", itlb, stats(f"{cid}.itlb", itlb_s))
        _add(core, f"{cid}.icache", "Instruction Cache", "CacheUnit",
             _cache_params(cfg, "l1i"),
             stats(f"{cid}.icache", _cache_base_stats("l1i"), CACHE_STAT_NAMES))
        _add(core, f"{cid}.dtlb", "dtlb", "DataTLB", dtlb, stats(f"{cid}.dtlb", dtlb_s))
        _add(core, f"{cid}.dcache", "Data Cache", "CacheUnit",
             _cache_params(cfg, "l1d"),
             stats(f"{cid}.dcache", _cache_base_stats("l1d"), CACHE_STAT_NAMES))
        _add(core, f"{cid}.btargetbuf", "btargetbuf", "BranchTargetBuffer", BTB_PARAMS,
             stats(f"{cid}.btargetbuf", BTB_STATS))
    for i in range(cfg.num_cores):
        _add(system, f"system.L2{i}", f"L2 Cache {i}", "CacheUnit", _cache_params(cfg, "l2"),
             stats(f"system.L2{i}", _cache_base_stats("l2"), CACHE_STAT_NAMES))
    _add(system, "system.L30", "L3 Cache", "CacheUnit", _cache_params(cfg, "l3"),
         stats("system.L30", _cache_base_stats("l3"), CACHE_STAT_NAMES))

    ET.indent(root)
    return ET.tostring(root, encoding="unicode")
