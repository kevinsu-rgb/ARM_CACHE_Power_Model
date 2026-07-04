#!/usr/bin/env python3
import argparse
import csv


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


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--stats", type=str, default="m5out/stats.txt", help="Path to gem5 stats.txt"
    )
    parser.add_argument(
        "--out", type=str, default="filtered_stats.csv", help="Output CSV"
    )

    # run metadata
    parser.add_argument("--benchmark", type=str, default="benchmark")
    parser.add_argument("--benchmark_args", type=str, default="")

    # Cache config (defaults must match your main.py)
    parser.add_argument("--l1i_size", type=str, default="32KiB")
    parser.add_argument("--l1i_assoc", type=int, default=8)
    parser.add_argument("--l1d_size", type=str, default="32KiB")
    parser.add_argument("--l1d_assoc", type=int, default=8)
    parser.add_argument("--l2_size", type=str, default="256KiB")
    parser.add_argument("--l2_assoc", type=int, default=16)
    parser.add_argument("--l3_size", type=str, default="2MiB")
    parser.add_argument("--l3_assoc", type=int, default=32)
    parser.add_argument("--block_size", type=int, default=64)
    parser.add_argument("--cpu_type", type=str, default="TIMING")

    args = parser.parse_args()

    # -------------------------
    # Parse stats file
    # -------------------------
    stats = parse_stats_file(args.stats)

    # -------------------------
    # Global stats
    # -------------------------
    sim_seconds = stats.get("simSeconds", 0.0)
    final_tick = stats.get("finalTick", 0)

    # -------------------------
    # Cache stats prefixes
    # -------------------------
    prefixes = {
        "l1d": "board.cache_hierarchy.clusters.l1dcache",
        "l1i": "board.cache_hierarchy.clusters.l1icache",
        "l2": "board.cache_hierarchy.clusters.l2cache",
        "l3": "board.cache_hierarchy.l3_cache",
    }

    cache = {}

    for level, prefix in prefixes.items():
        acc = get_total_counter(stats, f"{prefix}.overallAccesses")
        miss = get_total_counter(stats, f"{prefix}.overallMisses")

        dyn = stats.get(f"{prefix}.power_model.dynamicPower", 0.0)
        st = stats.get(f"{prefix}.power_model.staticPower", 0.0)

        miss_rate = (miss / acc * 100.0) if acc else 0.0

        cache[level] = {
            "accesses": acc,
            "misses": miss,
            "miss_rate_pct": miss_rate,
            "dynamic_power_W": dyn,
            "static_power_W": st,
        }

    # -------------------------
    # Build CSV row
    # -------------------------
    row = {
        "benchmark": args.benchmark,
        "benchmark_args": args.benchmark_args,
        "cpu_type": args.cpu_type,
        "l1i_size": args.l1i_size,
        "l1i_assoc": args.l1i_assoc,
        "l1d_size": args.l1d_size,
        "l1d_assoc": args.l1d_assoc,
        "l2_size": args.l2_size,
        "l2_assoc": args.l2_assoc,
        "l3_size": args.l3_size,
        "l3_assoc": args.l3_assoc,
        "block_size": args.block_size,
        "simSeconds": sim_seconds,
        "finalTick": final_tick,
    }

    # flatten cache rows
    for level in ["l1i", "l1d", "l2", "l3"]:
        row[f"{level}_accesses"] = cache[level]["accesses"]
        row[f"{level}_misses"] = cache[level]["misses"]
        row[f"{level}_miss_rate_pct"] = cache[level]["miss_rate_pct"]
        row[f"{level}_dynamic_power_W"] = cache[level]["dynamic_power_W"]
        row[f"{level}_static_power_W"] = cache[level]["static_power_W"]

    # -------------------------
    # Write CSV
    # -------------------------
    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        writer.writeheader()
        writer.writerow(row)

    print(f"\nSaved CSV → {args.out}\n")

    # -------------------------
    # Pretty printed WITH units (10 decimal places)
    # -------------------------
    print("=== Extracted Stats (with units) ===")
    print(f"Benchmark: {args.benchmark}")
    print(f"Arguments: {args.benchmark_args}")
    print("")
    print(f"Execution time: {sim_seconds:.10f} s")
    print(f"Final tick: {final_tick} ticks ({(final_tick / 1e12):.10f} s)\n")

    for level in ["l1i", "l1d", "l2", "l3"]:
        c = cache[level]
        print(f"--- {level.upper()} ---")
        print(f"Accesses:        {c['accesses']} accesses")
        print(f"Misses:          {c['misses']} misses")
        print(f"Miss rate:       {c['miss_rate_pct']:.10f} %")
        print(f"Dynamic power:   {c['dynamic_power_W']:.10f} W")
        print(f"Static power:    {c['static_power_W']:.10f} W")
        print("")


if __name__ == "__main__":
    main()
