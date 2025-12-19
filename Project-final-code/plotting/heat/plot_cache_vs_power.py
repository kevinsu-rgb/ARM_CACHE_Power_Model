#!/usr/bin/env python3
import matplotlib.pyplot as plt
import numpy as np

# ============================================================
# 1. Data: extracted from your HEAT runs
#    Configs:
#      0 -> Default (LRURP, base sizes)
#      1 -> FIFORP  (base sizes)
#      2 -> Small caches (LRURP)
# ============================================================

config_labels = [
    "Default (LRURP, base sizes)",
    "FIFORP (base sizes)",
    "Small caches (LRURP)",
]

# Miss rates (%) per level for HEAT
miss_rate = {
    "L1I": [
        0.009822471337,   # default
        0.00999939784,    # FIFORP
        0.01024953531,    # small caches
    ],
    "L1D": [
        5.236823558,      # default
        5.246418945,      # FIFORP
        5.237174762,      # small caches
    ],
    "L2": [
        5.97272558,       # default
        5.81397842,       # FIFORP
        99.96562836,      # small caches
    ],
    "L3": [
        42.24327457,      # default
        43.30437633,      # FIFORP
        2.52336404,       # small caches
    ],
}

# Dynamic power (W) per level for HEAT
dyn_power = {
    "L1I": [
        0.003587,  # default
        0.003587,  # FIFORP
        0.002866,  # small caches
    ],
    "L1D": [
        0.002086,  # default
        0.002087,  # FIFORP
        0.001667,  # small caches
    ],
    "L2": [
        0.00054,   # default
        0.000539,  # FIFORP
        0.001464,  # small caches
    ],
    "L3": [
        0.000083,  # default  (8.30E-05)
        0.000082,  # FIFORP   (8.20E-05)
        0.000525,  # small caches
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

        # Use log scale for all power plots
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
# 4. Produce all plots for HEAT
# ============================================================

if __name__ == "__main__":
    # A. Replacement policy experiment (HEAT)
    plot_miss_rates(
        policy_indices,
        policy_xlabels,
        "HEAT: Miss Rates vs Replacement Policy (sizes fixed)",
        "heat_miss_rate_vs_policy.png",
    )

    plot_dynamic_power(
        policy_indices,
        policy_xlabels,
        "HEAT: Dynamic Power vs Replacement Policy (sizes fixed)",
        "heat_dynamic_power_vs_policy.png",
    )

    plot_total_dynamic_power(
        policy_indices,
        policy_xlabels,
        "HEAT: Total Dynamic Power vs Replacement Policy (sizes fixed)",
        "heat_total_dynamic_power_vs_policy.png",
    )

    # B. Cache size experiment (HEAT)
    plot_miss_rates(
        size_indices,
        size_xlabels,
        "HEAT: Miss Rates vs Cache Size (LRURP)",
        "heat_miss_rate_vs_size.png",
    )

    plot_dynamic_power(
        size_indices,
        size_xlabels,
        "HEAT: Dynamic Power vs Cache Size (LRURP)",
        "heat_dynamic_power_vs_size.png",
    )

    plot_total_dynamic_power(
        size_indices,
        size_xlabels,
        "HEAT: Total Dynamic Power vs Cache Size (LRURP)",
        "heat_total_dynamic_power_vs_size.png",
    )
