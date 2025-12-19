#!/usr/bin/env python3
import matplotlib.pyplot as plt
import numpy as np

# ============================================================
# 1. Data: extracted from your LIVERMORE runs
#    Config indices:
#      0 -> Default (LRURP, base sizes)
#      1 -> FIFORP  (base sizes)
#      2 -> Small caches (LRURP)
# ============================================================

config_labels = [
    "Default (LRURP, base sizes)",
    "FIFORP (base sizes)",
    "Small caches (LRURP)",
]

# Miss rates (%) per level for LIVERMORE
miss_rate = {
    "L1I": [
        4.49e-06,       # default
        2.24e-05,       # FIFORP
        7.50e-05,       # small caches
    ],
    "L1D": [
        6.709549153,    # default
        6.405139538,    # FIFORP
        6.580527954,    # small caches
    ],
    "L2": [
        99.76037445,    # default
        98.58510159,    # FIFORP
        96.1857112,     # small caches
    ],
    "L3": [
        89.94441199,    # default
        86.89289679,    # FIFORP
        99.99863594,    # small caches
    ],
}

# Dynamic power (W) per level for LIVERMORE
dyn_power = {
    "L1I": [
        0.002285,   # default
        0.002352,   # FIFORP
        0.002272,   # small caches
    ],
    "L1D": [
        0.001076,   # default
        0.001108,   # FIFORP
        0.001073,   # small caches
    ],
    "L2": [
        0.001152,   # default
        0.001133,   # FIFORP
        0.001101,   # small caches
    ],
    "L3": [
        0.001419,   # default
        0.001357,   # FIFORP
        0.001453,   # small caches
    ],
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

        # log scale for all power plots
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

    ax.set_yscale("log")
    ax.set_ylabel("Total dynamic power (W) [log]")

    ax.set_title(title)
    ax.grid(axis="y", linestyle="--", alpha=0.4)

    fig.tight_layout()
    fig.savefig(filename, dpi=300, bbox_inches="tight")
    print(f"Saved {filename}")


# ============================================================
# 4. Produce all plots for LIVERMORE
# ============================================================

if __name__ == "__main__":
    # A. Replacement policy experiment (LIVERMORE)
    plot_miss_rates(
        policy_indices,
        policy_xlabels,
        "LIVERMORE: Miss Rates vs Replacement Policy (sizes fixed)",
        "livermore_miss_rate_vs_policy.png",
    )

    plot_dynamic_power(
        policy_indices,
        policy_xlabels,
        "LIVERMORE: Dynamic Power vs Replacement Policy (sizes fixed)",
        "livermore_dynamic_power_vs_policy.png",
    )

    plot_total_dynamic_power(
        policy_indices,
        policy_xlabels,
        "LIVERMORE: Total Dynamic Power vs Replacement Policy (sizes fixed)",
        "livermore_total_dynamic_power_vs_policy.png",
    )

    # B. Cache size experiment (LIVERMORE)
    plot_miss_rates(
        size_indices,
        size_xlabels,
        "LIVERMORE: Miss Rates vs Cache Size (LRURP)",
        "livermore_miss_rate_vs_size.png",
    )

    plot_dynamic_power(
        size_indices,
        size_xlabels,
        "LIVERMORE: Dynamic Power vs Cache Size (LRURP)",
        "livermore_dynamic_power_vs_size.png",
    )

    plot_total_dynamic_power(
        size_indices,
        size_xlabels,
        "LIVERMORE: Total Dynamic Power vs Cache Size (LRURP)",
        "livermore_total_dynamic_power_vs_size.png",
    )
