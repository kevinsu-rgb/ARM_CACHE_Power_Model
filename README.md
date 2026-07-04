# ARM Cache Power Model

This project builds a custom three-level cache hierarchy for gem5 and attaches simple power models to the L1/L2/L3 caches. It is designed for ARM SE-mode simulations and is meant to be run with an ARM build of gem5.

## What this project does

- Creates a private L1 instruction cache, private L1 data cache, private L2 cache, and shared L3 cache
- Configures the hierarchy through a custom gem5 component in [src/three_level.py](src/three_level.py)
- Attaches power models to each cache level during simulation setup
- Runs a user-specified ARM64 Linux binary through [src/main.py](src/main.py)

# Cache Hierarchy Block Diagram
![Alt text](/images/Cache_Hierarchy.png)

## Project structure

- [src/main.py](src/main.py) — command-line entrypoint for launching gem5 simulations
- [src/three_level.py](src/three_level.py) — custom cache hierarchy and power-model definitions
- [src/tests/test_sample.c](src/tests/test_sample.c) — simple sample C program

## Requirements

- A gem5 build for ARM, for example:
  - [gem5/build/ARM/gem5.opt](../gem5/build/ARM/gem5.opt)
- A cross-compiler for ARM64 Linux binaries
  - `aarch64-linux-gnu-gcc` is recommended
- Python environment compatible with your gem5 build

## Build a sample ARM64 program

From the project source directory:

```bash
cd /home/kevin/Projects/gem5_projects/ARM_CACHE_Power_Model/src

aarch64-linux-gnu-gcc -static -O2 -o tests/test_sample_arm64 tests/test_sample.c
```

If `aarch64-linux-gnu-gcc` is not available, try:

```bash
clang --target=aarch64-linux-gnu --sysroot=/usr/aarch64-linux-gnu -static -O2 \
  -o tests/test_sample_arm64 tests/test_sample.c
```

## Run a simulation

Run the sample binary with the provided script:

```bash
cd /home/kevin/Projects/gem5_projects/ARM_CACHE_Power_Model/src
/home/kevin/Projects/gem5_projects/gem5/build/ARM/gem5.opt main.py \
  --binary tests/test_sample_arm64
```

## Useful options

The launcher accepts the following common options:

- `--binary` — path to the ARM64 binary to execute
- `--l1i_size`, `--l1d_size`, `--l2_size`, `--l3_size` — cache sizes
- `--l1i_assoc`, `--l1d_assoc`, `--l2_assoc`, `--l3_assoc` — cache associativity
- `--block_size` — cache line size in bytes
- `--l1i_replacement_policy`, `--l1d_replacement_policy`, `--l2_replacement_policy`, `--l3_replacement_policy` — replacement policy (`LRURP`, `FIFORP`, `TreePLRURP`)
- `--cpu_type` — CPU model (`TIMING`, `ATOMIC`, `KVM`)

Example with custom cache sizes:

```bash
/home/kevin/Projects/gem5_projects/gem5/build/ARM/gem5.opt main.py \
  --binary tests/test_sample_arm64 \
  --l1i_size 16KiB \
  --l1d_size 16KiB \
  --l2_size 128KiB \
  --l3_size 1MiB
```

## Expected output

A successful run prints the program output and writes statistics to:

```text
m5out/stats.txt
```

## Notes

- The current setup is intended for simple SE-mode ARM workloads.
- The power model is attached after the board pre-instantiation step so that the cache objects exist before the model is wired up.
