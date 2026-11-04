#!/bin/bash

###############################
# GEM5 + main.py run wrapper
###############################

# Paths. The script works from any directory: main.py and
# extract_gem5_stats.py are found next to this script, and relative
# --binary/--outdir paths are taken relative to the caller's cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GEM5_BIN="${GEM5_BIN:-/home/kevin/Projects/gem5/build/ARM/gem5.opt}"
MAIN_PY="$SCRIPT_DIR/main.py"
EXTRACT_PY="$SCRIPT_DIR/extract_gem5_stats.py"
PYTHON_BIN="${PYTHON:-python3}"

# Absolute form of a user path, relative to the caller's original cwd.
abspath() {
    case "$1" in
        /*) printf '%s\n' "$1" ;;
        *)  printf '%s\n' "$PWD/$1" ;;
    esac
}

##########################################
# Parse arguments with defaults
##########################################

# Required
BINARY=""
WORKLOAD_ARGS=()

# Output directory (gem5 -d)
OUTDIR="m5out"

# Cache parameters (defaults match main.py)
L1I_SIZE="32KiB"
L1I_ASSOC=8
L1D_SIZE="32KiB"
L1D_ASSOC=8
L2_SIZE="256KiB"
L2_ASSOC=16
L3_SIZE="2MiB"
L3_ASSOC=32

BLOCK_SIZE=64

# Replacement policies
L1I_RP="LRURP"
L1D_RP="LRURP"
L2_RP="LRURP"
L3_RP="LRURP"

# CPU / power model parameters (defaults match main.py)
CPU_TYPE="O3"       # options: O3, MINOR, TIMING, ATOMIC
CORE_MODEL=""       # O3 only: o3_arm_v7a (default) or neoverse_v2
NUM_CORES=1
CLK_FREQ="1GHz"
TECH_NODE=28
DEVICE_TYPE="LOP"   # options: HP, LOP, LSTP
TEMPERATURE=350

##########################################
# Print help
##########################################
usage() {
    echo ""
    echo "Usage:"
    echo "  ./run_gem5.sh --binary <benchmark> [benchmark args] [options]"
    echo ""
    echo "Example:"
    echo "  ./run_gem5.sh --binary benchmarks/needle/needle 8000 50 1 --l2_size 1MiB"
    echo ""
    echo "Options (with defaults):"
    echo "  --binary <path>                    Path to ARM64 binary (REQUIRED)"
    echo "  --outdir <dir>                     gem5 output directory. Default: m5out"
    echo ""
    echo "Relative --binary/--outdir paths are relative to the current directory."
    echo "Environment: GEM5_BIN (gem5 binary), PYTHON (interpreter for extraction)."
    echo ""
    echo "  --l1i_size <size>                  Default: 32KiB"
    echo "  --l1i_assoc <int>                  Default: 8"
    echo "  --l1d_size <size>                  Default: 32KiB"
    echo "  --l1d_assoc <int>                  Default: 8"
    echo "  --l2_size <size>                   Default: 256KiB"
    echo "  --l2_assoc <int>                   Default: 16"
    echo "  --l3_size <size>                   Default: 2MiB"
    echo "  --l3_assoc <int>                   Default: 32"
    echo "  --block_size <int>                 Default: 64"
    echo "  --l1i_replacement_policy <str>     Default: LRURP"
    echo "  --l1d_replacement_policy <str>     Default: LRURP"
    echo "  --l2_replacement_policy <str>      Default: LRURP"
    echo "  --l3_replacement_policy <str>      Default: LRURP"
    echo "  --cpu_type <O3|MINOR|TIMING|ATOMIC> Default: O3"
    echo "  --core_model <o3_arm_v7a|neoverse_v2>"
    echo "                                     O3 only. Default: o3_arm_v7a"
    echo "  --num_cores <int>                  Default: 1"
    echo "  --clk_freq <freq>                  Default: 1GHz"
    echo "  --tech_node <nm>                   22..90. Default: 28"
    echo "  --device_type <HP|LOP|LSTP>        Default: LOP"
    echo "  --temperature <K>                  300..400 in steps of 10. Default: 350"
    echo ""
    exit 1
}

##########################################
# Parse CLI parameters
##########################################

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --binary) BINARY="$2"; shift ;;
        --outdir) OUTDIR="$2"; shift ;;
        --l1i_size) L1I_SIZE="$2"; shift ;;
        --l1i_assoc) L1I_ASSOC="$2"; shift ;;
        --l1d_size) L1D_SIZE="$2"; shift ;;
        --l1d_assoc) L1D_ASSOC="$2"; shift ;;
        --l2_size) L2_SIZE="$2"; shift ;;
        --l2_assoc) L2_ASSOC="$2"; shift ;;
        --l3_size) L3_SIZE="$2"; shift ;;
        --l3_assoc) L3_ASSOC="$2"; shift ;;
        --block_size) BLOCK_SIZE="$2"; shift ;;

        --l1i_replacement_policy) L1I_RP="$2"; shift ;;
        --l1d_replacement_policy) L1D_RP="$2"; shift ;;
        --l2_replacement_policy) L2_RP="$2"; shift ;;
        --l3_replacement_policy) L3_RP="$2"; shift ;;

        --cpu_type) CPU_TYPE="$2"; shift ;;
        --core_model) CORE_MODEL="$2"; shift ;;
        --num_cores) NUM_CORES="$2"; shift ;;
        --clk_freq) CLK_FREQ="$2"; shift ;;
        --tech_node) TECH_NODE="$2"; shift ;;
        --device_type) DEVICE_TYPE="$2"; shift ;;
        --temperature) TEMPERATURE="$2"; shift ;;

        --help) usage ;;
        *)
            # Anything else is treated as benchmark arguments
            WORKLOAD_ARGS+=("$1")
            ;;
    esac
    shift
done

##########################################
# Validate required args
##########################################

if [[ -z "$BINARY" ]]; then
    echo "ERROR: --binary <benchmark> is required."
    usage
fi

# Resolve user paths against the caller's cwd before anything else.
BINARY_NAME="$(basename "$BINARY")"
BINARY="$(abspath "$BINARY")"
OUTDIR="$(abspath "$OUTDIR")"

##########################################
# Build the GEM5 command
##########################################

CMD=("$GEM5_BIN" -d "$OUTDIR" "$MAIN_PY"
  --binary "$BINARY"
  --l1i_size "$L1I_SIZE"
  --l1i_assoc "$L1I_ASSOC"
  --l1d_size "$L1D_SIZE"
  --l1d_assoc "$L1D_ASSOC"
  --l2_size "$L2_SIZE"
  --l2_assoc "$L2_ASSOC"
  --l3_size "$L3_SIZE"
  --l3_assoc "$L3_ASSOC"
  --block_size "$BLOCK_SIZE"
  --l1i_replacement_policy "$L1I_RP"
  --l1d_replacement_policy "$L1D_RP"
  --l2_replacement_policy "$L2_RP"
  --l3_replacement_policy "$L3_RP"
  --cpu_type "$CPU_TYPE"
  --num_cores "$NUM_CORES"
  --clk_freq "$CLK_FREQ"
  --tech_node "$TECH_NODE"
  --device_type "$DEVICE_TYPE"
  --temperature "$TEMPERATURE")

if [[ -n "$CORE_MODEL" ]]; then
    CMD+=(--core_model "$CORE_MODEL")
fi

# Workload args must come last (main.py collects the remainder)
CMD+=("${WORKLOAD_ARGS[@]}")

##########################################
# Show the final command
##########################################

echo "========================================="
echo " Running gem5 with:"
echo "  Binary: $BINARY"
echo "  Benchmark args: ${WORKLOAD_ARGS[*]:-}"
echo "  Output dir: $OUTDIR"
echo "-----------------------------------------"
echo " Full command:"
printf '%q ' "${CMD[@]}"; echo
echo "========================================="

##########################################
# Execute command
##########################################

"${CMD[@]}"
STATUS=$?
if [[ $STATUS -ne 0 ]]; then
    echo "ERROR: gem5 exited with status $STATUS" >&2
    exit "$STATUS"
fi

##########################################
# Extract filtered stats
##########################################

"$PYTHON_BIN" "$EXTRACT_PY" \
    --stats "$OUTDIR/stats.txt" \
    --out "$OUTDIR/filtered_stats.csv" \
    --benchmark "$BINARY_NAME" \
    --benchmark_args "${WORKLOAD_ARGS[*]:-}"
