# McPAT-Calibrated Power Model for the Multicore ARM Simulation — Design

Date: 2026-11-03
Branch: `kevin_dev`
Status: Draft for review

## 1. Intent

**Goal.** Make the ARM_CACHE_Power_Model project run correctly on the gem5
install at `/home/kevin/Projects/gem5` (v25.1.0.1). Replace the hand-picked
cache power constants with numbers from an established tool, add per-core
CPU power, and support more than one simulated core.

**What "more accurate" means here.** The numbers come from McPAT/CACTI for
the exact simulated configuration, so they can be cited and their origin
traced. They are *not* calibrated against measurements from a real chip.
Trends across cache and core configurations are the main deliverable;
absolute watts are "McPAT-accurate", with McPAT's known limitations.

**Decisions made during brainstorming:**

| Topic | Decision |
|---|---|
| Overall method | **B2**: run McPAT/CACTI per configuration to get per-event energies and leakage, then feed them into gem5 `MathExprPowerModel`s |
| How coefficients are produced | **Approach 1**: automatic characterization, cached by configuration hash |
| CPU models | `--cpu_type O3` or `MINOR`. O3 has `--core_model o3_arm_v7a` (default, A15-class) or `neoverse_v2`; MINOR uses `HPI` (A53-class) |
| Technology | 28 nm (interpolated by McPAT between 32 and 22 nm), LOP devices, 1 GHz |
| Voltage | Pure McPAT: no voltage flag. The voltage follows the device flavour (LOP at 28 nm = 0.6 V) |
| Cross-check | `validate_mcpat.py` sends a finished run's real counts through McPAT and compares the result with gem5 |

## 2. Current state (findings)

**Bugs that stop the project running on gem5 25.1:**
1. `src/main.py:151-157`. `patched_pre_instantiate` drops the Root object
   that `AbstractBoard._pre_instantiate` returns. `Simulator._instantiate`
   then fails `assert self._root is not None` and gem5 exits with code 1
   and no message.
2. `src/three_level.py:133-148`. `ArmMMU.connectWalkerPorts(iport, dport)`
   in 25.1 connects only `dport` (there is a single walker), so
   `iptw_cache` is left unconnected and the run fails with
   `fatal: Cache ports on ...iptw_cache are not connected`.

**Smaller defects:**
- Static power of about 1e-7 W rounds to `0.000000` in `stats.txt`.
- `main.py` prints `board.clk_domain.clock` as a list object.
- `main.py` says "2GB" (it is 2 GiB) and hard-codes `m5out/` in its final message.
- `run_gem5.sh` points at `~/Source-builds/gem5`.
- The README points at a stale second checkout (`gem5_projects/gem5`).
- `import PowerModel, MathExprPowerModel` appears twice in `three_level.py`.

**Power model today.** Only the caches have power, using made-up constants
(12/60/80 pJ per access, 3–5 pW per byte). There is no core power and the
core count is fixed at `num_cores=1`.

**McPAT availability (verified by a probe).**
- `gem5/ext/mcpat` is the AMD-refactored McPAT 0.8. It builds with `make`.
- All 9 of its regression tests reproduce their reference output exactly.
  One run takes 0.07–3 s.
- The bundled `ARM_A9*.xml` files use the *old* XML format and segfault.
  We therefore write our own ARM descriptions in the AMD format, modelled
  on `regression/test-*/power_region0.xml`.
- McPAT has no voltage setting; voltage comes from its technology tables.
- It rejects nodes below 22 nm and above 180 nm.
- `machine_type` selects an out-of-order or in-order core.

## 3. Architecture

```
ARM_CACHE_Power_Model/
  src/
    main.py               # CLI + board setup (bug fixes, new flags)
    three_level.py        # cache hierarchy only (walker-cache fix); power classes removed
    power/                # NEW package; Python standard library only (runs in gem5's Python 3.12)
      __init__.py
      config.py           # PowerConfig dataclass + validation + stable hash
      cores.py            # loads ARM core classes from <gem5_root>/configs/common/cores/arm
      mcpat_xml.py        # PowerConfig + activity counts -> AMD-format McPAT XML
      mcpat_runner.py     # find/run the mcpat binary, parse per-component output
      characterize.py     # baseline + per-event runs -> coefficients JSON (cached); also a CLI
      mapping.py          # per-CPU-model table: McPAT event -> gem5 stat expression
      models.py           # build gem5 PowerModel/MathExprPowerModel objects from coefficients
    validate_mcpat.py     # cross-check of a finished run against a full McPAT evaluation
    extract_gem5_stats.py # multicore-aware stats -> CSV
    run_gem5.sh           # updated gem5 path and new flags
    tests/                # pytest unit tests + the existing sample programs
  tools/mcpat/            # McPAT build output (gitignored)
  power_cache/            # coefficient JSON files (gitignored)
  docs/superpowers/specs/ # this file
```

Each unit has one job:
- `config.py` knows nothing about McPAT or gem5 objects.
- `mcpat_xml.py` and `mcpat_runner.py` know nothing about gem5.
- `mapping.py` is the only place that knows gem5 stat names.
- `models.py` is the only place that creates gem5 power objects.

## 4. Command line (`main.py`)

| Flag | Default | Notes |
|---|---|---|
| `--cpu_type` | `O3` | `O3`, `MINOR`, `TIMING`, `ATOMIC`. `KVM` is removed (it cannot run ARM on an x86 host). `TIMING`/`ATOMIC` model cache power only and print a warning |
| `--core_model` | `o3_arm_v7a` | `o3_arm_v7a` (`O3_ARM_v7a_3`) or `neoverse_v2` (`NeoverseV2`). Valid only with `O3`; passing it with another CPU type is an error. `neoverse_v2` prints a warning that absolute power is overstated at ≥22 nm (real V2 silicon is 4–5 nm) |
| `--num_cores` | `1` | ≥1. All cores share the single SE process; idle cores still leak |
| `--clk_freq` | `1GHz` | Used for both the gem5 board clock and the McPAT target clock |
| `--tech_node` | `28` | Integer nm, 22–180 |
| `--device_type` | `LOP` | `HP`, `LSTP`, `LOP`. Applies to all McPAT components. The implied Vdd is printed |
| `--temperature` | `350` | Kelvin, passed to McPAT |
| `--gem5_root` | `$GEM5_ROOT` or `/home/kevin/Projects/gem5` | Used to import the ARM core configs |
| `--mcpat_bin` | `$MCPAT_BIN` or `<project>/tools/mcpat/mcpat` | |
| `--power_cache_dir` | `<project>/power_cache` | |

All existing cache, replacement-policy, block-size and workload flags keep
their current names and defaults.

## 5. Data flow

### 5.1 Run-time sequence

1. `main.py` parses the flags and builds a `PowerConfig` containing:
   - CPU type and core model.
   - The core parameters read from the gem5 core class: fetch/decode/issue/commit
     widths, ROB/IQ/LQ/SQ entries, physical int/fp registers, in-order vs OoO.
   - Per-level cache size, associativity, line size, latencies and MSHRs.
   - Core count, clock, node, device type and temperature.
2. `characterize.get_coefficients(config)` returns the cached JSON if it
   exists, and otherwise characterizes (§5.2).
3. Inside the fixed `_pre_instantiate` hook, which now returns the Root,
   `models.attach(board, coefficients, mapping)` gives every core, L1I, L1D,
   L2 and the L3 a `PowerModel`. Each has 4 power states:
   - ON = dynamic + static.
   - CLK_GATED = static only.
   - SRAM_RETENTION and OFF = 0.

   The old `*ClkGated`/`*SRAMRetention`/`*Off` classes are removed.
4. gem5 reports `power_model.dynamicPower` / `staticPower` for each
   component in `stats.txt`.

### 5.2 Characterization (`characterize.py`)

1. **Build.** `mcpat_xml.build(config, counts)` writes one McPAT system containing:
   - N cores, each with its own I-cache and D-cache.
   - N private L2s.
   - One shared L3.
   - `machine_type` = OoO for O3 and in-order for MINOR.
   - All duty-cycle stats fixed at 1.0, in characterization and validation alike.
2. **Baseline.** `total_cycles = C0 = 1_000_000` and every other count 0.
   - Gives each component's leakage (subthreshold + gate), which becomes its
     static power.
   - Gives the baseline runtime dynamic energy `E0`.
3. **Per-event runs.** For each event `e`, set its count to `N_e = 100_000`
   (for the cycle event, add `C0` cycles), keeping everything else at baseline.
   - `energy_per_event[e] = (E_e − E0) / N_e`, using McPAT's
     *Runtime Dynamic Energy*.
   - Each event belongs to exactly one gem5 component, which gets its energy.
4. **Events:**
   - **Core:** committed int / fp / load / store / branch instructions, branch
     mispredictions, cycles.
   - **O3 only:** ROB reads and writes; int and fp rename reads and writes;
     int and fp issue-queue reads, writes and wakeups; int and fp register
     file reads and writes; ALU, MUL and FPU accesses.
   - **Each cache instance type** (L1I, L1D, L2, L3): read accesses, write
     accesses, read misses, write misses.

   With per-core symmetry, events are characterized on core 0 and its caches
   and reused for every core.
5. **Superposition check.** Run once more with every event at `N_e`
   simultaneously.
   - Require `|E_all − (E0 + Σ e_e·N_e)| / (E_all − E0) ≤ 1%`.
   - On failure, raise an error naming the worst contributors and write no
     cache file.
6. **Write** `power_cache/<hash>.json` containing:
   - Schema version.
   - The full `PowerConfig`.
   - The McPAT binary's SHA-256.
   - Implied Vdd.
   - Per-component leakage (W).
   - Per-event energies (J).
   - Timestamp.

   The hash is the SHA-256 of the canonical JSON of
   (`PowerConfig`, McPAT binary SHA-256, schema version), truncated to 16
   hex characters.

`characterize.py` also runs standalone, so a configuration can be
characterized or inspected without gem5:
`python -m power.characterize --config cfg.json`.

### 5.3 Mapping gem5 stats to McPAT events (`mapping.py`)

- There is one table per CPU model (`O3`, `MINOR`). An entry is
  `mcpat_event -> gem5 stat expression (per core / per cache)`.
- For MINOR, the O3-only structure events are absent, and register-file
  activity is approximated from the instruction mix. Every approximation is
  marked `# proxy:` with its rationale.
- Exact 25.1 stat names are confirmed from a real `stats.txt` during
  implementation and pinned in the tests.
- With N > 1, gem5 stat paths are indexed (`clusters0…`, `cores0…`). With
  N = 1 they are not. The mapping handles both.

Component expressions in gem5:

```
dyn = (Σ_e energy_per_event[e] * <gem5 stat expr for e>) / simSeconds
st  = leakage_W
```

### 5.4 Validation (`validate_mcpat.py`)

1. Read a finished run's `stats.txt` and `config.json`, plus the coefficient
   JSON named in the run's output.
2. Use the same `mapping.py` to fill a McPAT description with the run's
   actual counts and cycles.
3. Run McPAT once.
4. Report McPAT power against gem5-reported power for each component and in
   total. Exit non-zero if any component differs by more than 1%.

## 6. Scope of the model

**Modelled:**
- Each core, including TLBs, BTB and pipeline logic as McPAT includes them.
- L1I, L1D, L2 and L3.
- DRAM energy is reported from gem5's existing DRAMPower stats; this is not McPAT.

**Not modelled, and documented in the README:**
- Crossbars/buses, the memory controller, page-table-walker caches and
  the I/O cache.
- Thermal feedback.
- DVFS and voltage scaling.
- Measured-silicon calibration.

## 7. Error handling

Every case below stops the run; none of them produces zeros silently.

| Condition | Behaviour |
|---|---|
| McPAT binary missing | Stop before simulating and print the build command: `make -C <gem5_root>/ext/mcpat BUILD_DIR=<project>/tools` (McPAT's makefile writes the binary to `$(BUILD_DIR)/mcpat/mcpat`, i.e. `<project>/tools/mcpat/mcpat`) |
| McPAT exits non-zero, segfaults, or its output does not parse | Stop. Keep the XML and stdout/stderr in `power_cache/failed/<hash>-<event>/` |
| Superposition check fails | Stop with the per-event deviation report. No cache file is written |
| A stat referenced by the mapping is missing from gem5's stat registry | Stop at the pre-instantiate hook, naming the stat |
| Configuration outside McPAT's range (node not in 22–180 nm, clock ≤ 0, cores < 1) | Rejected while parsing flags |
| `--core_model` given with a CPU type other than O3 | Rejected while parsing flags |
| `--core_model neoverse_v2` | One warning about overstated absolute power |
| `TIMING` / `ATOMIC` | One warning: cache power only |
| Cache JSON whose schema version or McPAT hash does not match | Treated as missing and regenerated |

## 8. Outputs

- **`stats.txt`:** gem5's own per-component `dynamicPower` / `staticPower`.
  All values are in watts. McPAT leakage is in the mW range rather than the
  old ~1e-7 W, so it shows up in the 6-decimal text output. The end-to-end
  tests assert that every component's static power is non-zero in
  `stats.txt`.
- **`extract_gem5_stats.py`:**
  - Handles any number of cores.
  - For each core: instructions, cycles, IPC, dynamic power, static power.
  - For each cache instance: accesses, misses, miss rate, dynamic power,
    static power.
  - Totals: core, cache and chip power; DRAM energy; total energy.
  - Labels: config hash, CPU type, core model, node, device type, implied Vdd.
- **`main.py`** prints a readable clock, "2 GiB", and the real output
  directory.

## 9. Testing

**Unit tests.** These use pytest outside gem5. pytest is added to the
project `.venv`, where it is not installed yet.
- `config.py`: validation errors; hash stability (same config, same hash;
  any field change, different hash).
- `mcpat_xml.py`: well-formed XML; required components and parameters for
  O3 and MINOR; N cores giving N core / L1 / L2 blocks.
- `mcpat_runner.py`: parses captured McPAT output, including a
  multi-component one; non-zero exit and garbage output raise errors.
- `characterize.py`, using a fake runner with known linear energies: the
  recovered coefficients are exact; a non-linear fake trips the
  superposition check; a cache hit skips the runner.
- `mapping.py`: every event of each CPU model has an expression; index
  handling for N = 1 vs N > 1.

**McPAT build check.** The 9 bundled regression tests match their reference
output.

**End-to-end runs** (gem5, `tests/small_loop`, output to a temporary
directory):
- O3/o3_arm_v7a and MINOR/HPI, each with 1 and 2 cores.
- O3/neoverse_v2 with 1 core.
- Each must exit 0, report non-zero dynamic and static power for every core
  and cache, and pass `validate_mcpat.py` within 1%.

**Plausibility checks** (not accuracy claims):
- An A15-class core at 28 nm LOP and 1 GHz is between 0.05 and 2 W. The
  range is wide because LOP sits at 0.6 V.
- L1D dynamic power is greater than L3 dynamic power on `small_loop`.
- L2 static power rises as the L2 size goes 128 KiB → 256 KiB → 1 MiB.

**Regression for the original bugs.** The README's plain command, run with
the defaults, produces a non-empty `stats.txt`.

## 10. Housekeeping

- `.gitignore`: add `tools/` and `power_cache/`.
- `run_gem5.sh`: point `GEM5_BIN` at `/home/kevin/Projects/gem5/build/ARM/gem5.opt`
  and pass the new flags through.
- README:
  - Fix the gem5 paths.
  - Add a "Power model" section covering the method, the McPAT build command,
    the flags, the scope (§6), the limitations, and how to run
    `validate_mcpat.py`.
- Remove the duplicate imports and the unused power-state classes.

## 11. Out of scope

- Calibration against measured hardware.
- Voltage scaling and DVFS.
- A custom A72-class core config.
- Per-core different binaries (`set_se_multi_binary_workload`).
- Power for the interconnect and the memory controller.
- Time-varying power traces (periodic stat dumps).
- FS mode.
