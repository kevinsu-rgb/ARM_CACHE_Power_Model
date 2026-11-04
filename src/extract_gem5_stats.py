#!/usr/bin/env python3
import argparse
import csv
import json
import re
import sys
from pathlib import Path


def get_stat(stats, name):
    return stats.get(name, 0)


def get_total_counter(stats, base):
    """
    Prefer <base>::total if it exists, otherwise <base>.
    """
    if f"{base}::total" in stats:
        return stats[f"{base}::total"]
    return stats.get(base, 0)


def parse_stats_file(path):
    """
    Parse gem5 stats.txt into a dict: { stat_name: numeric_value }.
    """
    stats = {}
    with open(path, "r") as f:
        for line in f:
            line = line.strip()

            # Skip comments/empty
            if not line or line.startswith("#"):
                continue

            # Remove inline comments
            if "#" in line:
                line, _ = line.split("#", 1)
                line = line.strip()
                if not line:
                    continue

            parts = line.split()
            if len(parts) < 2:
                continue

            name = parts[0]
            val_str = parts[1]

            # parse number
            try:
                if "." in val_str or "e" in val_str or "E" in val_str:
                    value = float(val_str)
                else:
                    value = int(val_str)
            except ValueError:
                continue

            stats[name] = value

    return stats


def lookup(stats, name, default=0):
    """Return stats[name], else stats[name + '::total'], else default."""
    if name in stats:
        return stats[name]
    return stats.get(name + "::total", default)


_PATTERNS = {
    "cores": re.compile(r"^(board\.processor\.cores(\d*)\.core)\."),
    "l1i": re.compile(r"^(board\.cache_hierarchy\.clusters(\d*)\.l1icache)\."),
    "l1d": re.compile(r"^(board\.cache_hierarchy\.clusters(\d*)\.l1dcache)\."),
    "l2": re.compile(r"^(board\.cache_hierarchy\.clusters(\d*)\.l2cache)\."),
}
_L3 = "board.cache_hierarchy.l3_cache"
_CACHE_LEVELS = ("l1i", "l1d", "l2")


def discover_components(stats):
    """Find component stat prefixes (no trailing dot), in index order.

    Unindexed (single core) paths count as index 0. Raises ValueError on mixed
    indexed/unindexed paths or when core/L1/L2 counts differ.
    """
    found = {}
    for key, rx in _PATTERNS.items():
        by_idx = {}
        unindexed = False
        for name in stats:
            m = rx.match(name)
            if m:
                if m.group(2) == "":
                    unindexed = True
                    by_idx[0] = m.group(1)
                else:
                    by_idx[int(m.group(2))] = m.group(1)
        indexed = any(rx.match(n) and rx.match(n).group(2) != "" for n in stats)
        if unindexed and indexed:
            raise ValueError(f"both indexed and unindexed {key} paths in stats")
        found[key] = [by_idx[i] for i in sorted(by_idx)]
    counts = {k: len(v) for k, v in found.items()}
    if len(set(counts.values())) != 1:
        raise ValueError(f"component counts differ: {counts}")
    has_l3 = any(n.startswith(_L3 + ".") for n in stats)
    found["l3"] = [_L3] if has_l3 else []
    return found


def _cache_fields(stats, prefix):
    acc = lookup(stats, f"{prefix}.overallAccesses")
    miss = lookup(stats, f"{prefix}.overallMisses")
    return {
        "accesses": acc,
        "misses": miss,
        "miss_rate_pct": (miss / acc * 100.0) if acc else 0.0,
        "dynamic_W": stats.get(f"{prefix}.power_model.dynamicPower", 0.0),
        "static_W": stats.get(f"{prefix}.power_model.staticPower", 0.0),
    }


def build_row(stats, meta, benchmark, benchmark_args):
    """Build one CSV row (ordered dict) from parsed stats and power_meta."""
    comps = discover_components(stats)
    sim_seconds = stats.get("simSeconds", 0.0)
    row = {
        "benchmark": benchmark,
        "benchmark_args": benchmark_args,
        "config_hash": meta.get("config_hash"),
        "cpu_type": meta.get("cpu_type"),
        "core_model": meta.get("core_model"),
        "num_cores": meta.get("num_cores"),
        "tech_node_nm": meta.get("tech_node_nm"),
        "device_type": meta.get("device_type"),
        "implied_vdd": meta.get("implied_vdd"),
        "clock_mhz": meta.get("clock_mhz"),
        "simSeconds": sim_seconds,
    }
    core_total = 0.0
    for i, prefix in enumerate(comps["cores"]):
        insts = lookup(stats, f"{prefix}.commitStats0.numInsts")
        cycles = lookup(stats, f"{prefix}.numCycles")
        dyn = stats.get(f"{prefix}.power_model.dynamicPower", 0.0)
        st = stats.get(f"{prefix}.power_model.staticPower", 0.0)
        row[f"core{i}_insts"] = insts
        row[f"core{i}_cycles"] = cycles
        row[f"core{i}_ipc"] = (insts / cycles) if cycles else 0
        row[f"core{i}_dynamic_W"] = dyn
        row[f"core{i}_static_W"] = st
        core_total += dyn + st
    cache_total = 0.0
    for lvl in _CACHE_LEVELS:
        for i, prefix in enumerate(comps[lvl]):
            f = _cache_fields(stats, prefix)
            for k, v in f.items():
                row[f"{lvl}{i}_{k}"] = v
            cache_total += f["dynamic_W"] + f["static_W"]
    if comps["l3"]:
        f = _cache_fields(stats, comps["l3"][0])
    else:
        f = {"accesses": 0, "misses": 0, "miss_rate_pct": 0.0,
             "dynamic_W": 0.0, "static_W": 0.0}
    for k, v in f.items():
        row[f"l3_{k}"] = v
    cache_total += f["dynamic_W"] + f["static_W"]
    chip_total = core_total + cache_total
    dram_pj = sum(
        v for k, v in stats.items()
        if re.fullmatch(r"board\.memory\.mem_ctrl\d*\.dram\.rank\d+\.totalEnergy", k)
    )
    chip_energy = chip_total * sim_seconds
    dram_energy = dram_pj * 1e-12
    row["core_total_W"] = core_total
    row["cache_total_W"] = cache_total
    row["chip_total_W"] = chip_total
    row["chip_energy_J"] = chip_energy
    row["dram_energy_J"] = dram_energy
    row["total_energy_J"] = chip_energy + dram_energy
    return row


def print_row(row):
    print("=== Extracted Stats (with units) ===")
    print(f"Benchmark: {row['benchmark']}")
    print(f"Arguments: {row['benchmark_args']}")
    print(f"Config: {row['cpu_type']} {row['core_model']} x{row['num_cores']}, "
          f"{row['tech_node_nm']} nm {row['device_type']}, Vdd {row['implied_vdd']} V, "
          f"{row['clock_mhz']} MHz")
    print(f"Execution time: {row['simSeconds']:.10f} s\n")
    for k in sorted({k.split("_")[0] for k in row if re.match(r"core\d+_", k)},
                    key=lambda x: int(x[4:])):
        print(f"--- {k.upper()} ---")
        print(f"Instructions:    {row[k + '_insts']}")
        print(f"Cycles:          {row[k + '_cycles']}")
        print(f"IPC:             {row[k + '_ipc']:.10f}")
        print(f"Dynamic power:   {row[k + '_dynamic_W']:.10f} W")
        print(f"Static power:    {row[k + '_static_W']:.10f} W\n")
    cache_names = sorted({m.group(1) for k in row
                          if (m := re.match(r"((?:l1i|l1d|l2)\d+|l3)_accesses$", k))})
    for c in cache_names:
        print(f"--- {c.upper()} ---")
        print(f"Accesses:        {row[c + '_accesses']} accesses")
        print(f"Misses:          {row[c + '_misses']} misses")
        print(f"Miss rate:       {row[c + '_miss_rate_pct']:.10f} %")
        print(f"Dynamic power:   {row[c + '_dynamic_W']:.10f} W")
        print(f"Static power:    {row[c + '_static_W']:.10f} W\n")
    print("--- Totals ---")
    for k, unit in (("core_total_W", "W"), ("cache_total_W", "W"), ("chip_total_W", "W"),
                    ("chip_energy_J", "J"), ("dram_energy_J", "J"), ("total_energy_J", "J")):
        print(f"{k + ':':<17}{row[k]:.10f} {unit}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stats", type=str, default="m5out/stats.txt",
                        help="Path to gem5 stats.txt")
    parser.add_argument("--meta", type=str, default=None,
                        help="Path to power_meta.json (default: next to --stats)")
    parser.add_argument("--out", type=str, default="filtered_stats.csv", help="Output CSV")
    parser.add_argument("--benchmark", type=str, default="benchmark")
    parser.add_argument("--benchmark_args", type=str, default="")
    args = parser.parse_args()

    meta_path = Path(args.meta) if args.meta else Path(args.stats).resolve().parent / "power_meta.json"
    if not meta_path.is_file():
        sys.exit(f"error: power_meta.json not found at {meta_path} (use --meta)")
    meta = json.loads(meta_path.read_text())
    stats = parse_stats_file(args.stats)
    try:
        row = build_row(stats, meta, args.benchmark, args.benchmark_args)
    except ValueError as e:
        sys.exit(f"error: {e}")

    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerow(row)
    print(f"\nSaved CSV -> {args.out}\n")
    print_row(row)


if __name__ == "__main__":
    main()
