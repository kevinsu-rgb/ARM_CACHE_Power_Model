#!/usr/bin/env python3
import matplotlib.pyplot as plt
import numpy as np

# ============================================================
# 1. Data: extracted from your HPCCG runs
# ============================================================

config_labels = [
    "Default (LRURP, base sizes)",
    "FIFORP (base sizes)",
    "Small caches (LRURP)",
]

# Miss rates (%) per level
miss_rate = {
    "L1I": [
        0.0003884851871,
        0.000399504642,
        0.0007992764256,
    ],
    "L1D": [
        7.493462501,
        7.669729121,
        7.76561045,
    ],
    "L2": [
        99.99394274,
        97.69639517,
        96.48300664,
    ],
    "L3": [
        86.4174234,
        86.88187526,
        90.622725,
    ],
}

# Dynamic power (W)
dyn_power = {
    "L1I": [0.002015, 0.002008, 0.001984],
    "L1D": [0.001087, 0.001089, 0.001079],
    "L2":  [0.001272, 0.001275, 0.001264],
    "L3":  [0.001523, 0.001524, 0.001553],
}

# ============================================================
# 2. Define experimental views
# ============================================================

policy_indices = [0, 1]        # Default vs FIFORP
policy_xlabels = ["LRURP", "FIFORP"]

size_indices = [0, 2]          # Default vs Small
size_xlabels = ["Base sizes", "Small caches"]


# ============================================================
# 3. Plotting utilities
# ============================================================

def plot_miss_rates(indices, xlabels, title, filename):
    levels = ["L1I", "L1D", "L2", "L3"]
    fig, axes = plt.subplots(2, 2, figsize=(10, 6), sharex=True)
    axes = axes.flatten()

    x = np.arange(len(indices))

    for i, level in enumerate(levels):
        ax = axes[i]
        vals = [miss_rate[level][idx] for idx in indices]
        ax.bar(x, vals)

        ax.set_title(level)
        ax.set_xticks(x)

        if i >= 2:
            ax.set_xticklabels(xlabels, rotation=15, ha="right")
        else:
            ax.set_xticklabels([])

        if level == "L1I":
            ax.set_yscale("log")
            ax.set_ylabel("Miss rate (%) [log]")
        else:
            ax.set_ylabel("Miss rate (%)")

        ax.grid(axis="y", linestyle="--", alpha=0.4)

    fig.suptitle(title, fontsize=14)
    fig.tight_layout(rect=[0, 0.03, 1, 0.95])
    fig.savefig(filename, dpi=300, bbox_inches="tight")
    print(f"Saved {filename}")


def plot_dynamic_power(indices, xlabels, title, filename):
    levels = ["L1I", "L1D", "L2", "L3"]
    fig, axes = plt.subplots(2, 2, figsize=(10, 6), sharex=True)
    axes = axes.flatten()

    x = np.arange(len(indices))

    for i, level in enumerate(levels):
        ax = axes[i]
        vals = [dyn_power[level][idx] for idx in indices]
        ax.bar(x, vals)

        ax.set_title(level)
        ax.set_xticks(x)

        if i >= 2:
            ax.set_xticklabels(xlabels, rotation=15, ha="right")
        else:
            ax.set_xticklabels([])

        # NEW: Use log scale for all power plots
        ax.set_yscale("log")
        ax.set_ylabel("Dynamic power (W) [log]")
        ax.grid(axis="y", linestyle="--", alpha=0.4)

    fig.suptitle(title, fontsize=14)
    fig.tight_layout(rect=[0, 0.03, 1, 0.95])
    fig.savefig(filename, dpi=300, bbox_inches="tight")
    print(f"Saved {filename}")


def plot_total_dynamic_power(indices, xlabels, title, filename):
    x = np.arange(len(indices))
    totals = []

    for idx in indices:
        tot = (
            dyn_power["L1I"][idx]
            + dyn_power["L1D"][idx]
            + dyn_power["L2"][idx]
            + dyn_power["L3"][idx]
        )
        totals.append(tot)

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(x, totals, width=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels(xlabels, rotation=15, ha="right")

    # NEW: log scale here too
    ax.set_yscale("log")
    ax.set_ylabel("Total dynamic power (W) [log]")

    ax.set_title(title)
    ax.grid(axis="y", linestyle="--", alpha=0.4)

    fig.tight_layout()
    fig.savefig(filename, dpi=300, bbox_inches="tight")
    print(f"Saved {filename}")


# ============================================================
# 4. Produce all plots
# ============================================================

if __name__ == "__main__":
    # A. Replacement policy experiment
    plot_miss_rates(
        policy_indices,
        policy_xlabels,
        "HPCCG: Miss Rates vs Replacement Policy (sizes fixed)",
        "hpccg_miss_rate_vs_policy.png"
    )

    plot_dynamic_power(
        policy_indices,
        policy_xlabels,
        "HPCCG: Dynamic Power vs Replacement Policy (sizes fixed)",
        "hpccg_dynamic_power_vs_policy.png"
    )

    plot_total_dynamic_power(
        policy_indices,
        policy_xlabels,
        "HPCCG: Total Dynamic Power vs Replacement Policy (sizes fixed)",
        "hpccg_total_dynamic_power_vs_policy.png"
    )

    # B. Cache size experiment  
    plot_miss_rates(
        size_indices,
        size_xlabels,
        "HPCCG: Miss Rates vs Cache Size (LRURP)",
        "hpccg_miss_rate_vs_size.png"
    )

    plot_dynamic_power(
        size_indices,
        size_xlabels,
        "HPCCG: Dynamic Power vs Cache Size (LRURP)",
        "hpccg_dynamic_power_vs_size.png"
    )

    plot_total_dynamic_power(
        size_indices,
        size_xlabels,
        "HPCCG: Total Dynamic Power vs Cache Size (LRURP)",
        "hpccg_total_dynamic_power_vs_size.png"
    )
