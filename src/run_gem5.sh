#!/bin/bash

###############################
# GEM5 + main.py run wrapper
###############################

# Default paths (you can change these)
GEM5_BIN=~/Source-builds/gem5/build/ARM/gem5.opt
MAIN_PY=main.py

##########################################
# Parse arguments with defaults
##########################################

# Required
BINARY=""
WORKLOAD_ARGS=""

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

# CPU type
CPU_TYPE="TIMING"   # options: TIMING, ATOMIC, KVM

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
    echo "  --l2_replacement_policy <str>     Default: LRURP"
    echo "  --l3_replacement_policy <str>     Default: LRURP"
    echo "  --cpu_type <TIMING|ATOMIC|KVM>     Default: TIMING"
    echo ""
    exit 1
}

##########################################
# Parse CLI parameters
##########################################

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --binary) BINARY="$2"; shift ;;
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

        --help) usage ;;
        *)
            # Anything else is treated as benchmark arguments
            WORKLOAD_ARGS="$WORKLOAD_ARGS $1"
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

##########################################
# Build the GEM5 command
##########################################

CMD="$GEM5_BIN $MAIN_PY \
  --binary $BINARY \
  --l1i_size $L1I_SIZE \
  --l1i_assoc $L1I_ASSOC \
  --l1d_size $L1D_SIZE \
  --l1d_assoc $L1D_ASSOC \
  --l2_size $L2_SIZE \
  --l2_assoc $L2_ASSOC \
  --l3_size $L3_SIZE \
  --l3_assoc $L3_ASSOC \
  --block_size $BLOCK_SIZE \
  --l1i_replacement_policy $L1I_RP \
  --l1d_replacement_policy $L1D_RP \
  --l2_replacement_policy $L2_RP \
  --l3_replacement_policy $L3_RP \
  --cpu_type $CPU_TYPE \
  $WORKLOAD_ARGS"

##########################################
# Show the final command
##########################################

echo "========================================="
echo " Running gem5 with:"
echo "  Binary: $BINARY"
echo "  Benchmark args: $WORKLOAD_ARGS"
echo "-----------------------------------------"
echo " Full command:"
echo "$CMD"
echo "========================================="

##########################################
# Execute command
##########################################

eval $CMD
