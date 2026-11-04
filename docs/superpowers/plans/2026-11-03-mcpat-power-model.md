# McPAT-Calibrated Power Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ARM_CACHE_Power_Model run on gem5 25.1 and replace its hand-picked cache power constants with McPAT-characterized per-event energies and leakage for every core, L1I, L1D, L2 and L3, across 1..N cores.

**Architecture:**
- A pure-Python `power/` package (standard library only) builds McPAT XML from a `PowerConfig`, then runs McPAT: once at baseline and once per event.
- From those runs it derives per-component leakage plus per-component × per-event energies, and caches them as JSON keyed by a configuration hash.
- A thin gem5-side layer turns the coefficients into `MathExprPowerModel` expressions over gem5 stats.
- `validate_mcpat.py` sends a finished run's real counts back through McPAT as a cross-check.

**Tech Stack:**
- gem5 25.1.0.1 ARM build (embedded Python 3.12).
- McPAT 0.8, AMD refactor, from `gem5/ext/mcpat`.
- Python 3.12 standard library.
- pytest, in `/home/kevin/Projects/gem5_projects/.venv`.

**Spec:** `docs/superpowers/specs/2026-11-03-mcpat-power-model-design.md` (relative to the project root `ARM_CACHE_Power_Model/`)

## Global Constraints

**Paths and tools**
- gem5 binary: `/home/kevin/Projects/gem5/build/ARM/gem5.opt`. gem5 root: `$GEM5_ROOT`, else `/home/kevin/Projects/gem5`.
- Project root `P = /home/kevin/Projects/gem5_projects/ARM_CACHE_Power_Model`. All project-relative paths below are relative to `P`.
- Resolve `tools/` and `power_cache/` from `__file__`, never from the cwd.
- `power/` must import only the Python standard library at module level. Only `power/cores.py` and `power/models.py` may import `m5`/`gem5`, and only inside functions.
- Python for unit tests: `PY=/home/kevin/Projects/gem5_projects/.venv/bin/python`.

**Configuration**
- Defaults: `--cpu_type O3`, `--core_model o3_arm_v7a`, `--num_cores 1`, `--clk_freq 1GHz`, `--tech_node 28`, `--device_type LOP`, `--temperature 350`.
- Core models:
  - `O3` + `o3_arm_v7a` → `O3_ARM_v7a_3`.
  - `O3` + `neoverse_v2` → `NeoverseV2`.
  - `MINOR` → `HPI`.
  - `--core_model` together with a non-O3 CPU type is a config error.
- `KVM` is removed.
- `--tech_node` must be an integer from 22 to 90 inclusive. **Deviation from spec (22–180):** McPAT defines only HP devices at 180 nm, so LSTP/LOP interpolation above 90 nm is undefined.
- There is no voltage flag. The implied Vdd follows McPAT's tables (§Task 3).

**Characterization**
- Constants: `C0 = 1_000_000` cycles; `N_EVENT = 1_000_000` per event; superposition tolerance 1% relative with a 1e-12 J absolute floor. **Deviation from spec (100 000):** printed McPAT energies have 6 significant digits, and 1e6 keeps rounding below 1e-4 relative.
- Every McPAT duty-cycle stat is 1.0 in every XML this project writes.
- Run McPAT as `mcpat -infile <xml> -print_level 5`.

**Cache and commits**
- Coefficient cache: `P/power_cache/<16-hex>.json`; failures go to `P/power_cache/failed/<hash>-<event>/`. `SCHEMA_VERSION = 1`.
- Commit on branch `kevin_dev` after each task. Commit messages end with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Facts Verified During Planning (gem5 25.1 + bundled McPAT)

**`MathExprPowerModel`**
- Evaluates only **Scalar** and **Formula** stats. Vector stats panic with "Unknown stat type" without naming the stat.
- A missing stat fatals at startup with `Failed to evaluate <name>`.
- Variables are written without `::total`.

**Core stat paths**
- With 1 core: `board.processor.cores.core`. With N>1: `board.processor.cores{i}.core`.
- Caches: `board.cache_hierarchy.clusters{i}.{l1icache,l1dcache,l2cache}`, unindexed when N=1. The L3 is `board.cache_hierarchy.l3_cache`.
- Idle cores report `numCycles = 0`.

**Stats used, with types**
- Scalar: `numCycles`, `commitStats0.{numIntInsts,numFpInsts,numVecInsts,numLoadInsts,numStoreInsts}`, `executeStats0.{numBranches,numIntAluAccesses,numVecAluAccesses,numIntRegReads,numIntRegWrites,numVecRegReads,numVecRegWrites}`, `branchPred.condIncorrect`.
- Scalar, O3 only: `rob.{reads,writes}`, `rename.{intLookups,vecLookups,renamedOperands}`, `{int,fp}InstQueue{Reads,Writes,WakeupAccesses}`.
- Formula (caches): `overallAccesses`, `overallMisses`, `<Cmd>.accesses`. `<Cmd>.misses` is a **Vector** and is unusable.
- ARM FP/SIMD activity appears in the `Vec*` stats, not `Fp*`.

**Caches**
- `overallAccesses` includes `ReadReq`/`WriteReq`/`ReadSharedReq`/`ReadExReq` and excludes `WritebackDirty`/`WritebackClean`.
- Per-command stats exist for every `MemCmd`.

**DRAM**
- `board.memory.mem_ctrl{j}.dram.rank{k}.totalEnergy` is in **pJ**.

**Core parameters** (from `config.json`)

| Model | Widths (fetch/decode/issue/commit) | ROB | IQ (Σ `instQueues[].numEntries`) | LQ/SQ | Phys int/fp regs | ALU/MUL/FPU |
|---|---|---|---|---|---|---|
| `O3_ARM_v7a_3` | 3/3/8/8 | 40 | 32 | 16/16 | 128/48 vec | 2/1/2 |
| `NeoverseV2` | 6/6/8/8 | 320 | 192 | 175/80 | 213/256 vec | 6/2/4 |
| `HPI` | `decodeInputWidth` 2, `executeIssueLimit` 2, `executeCommitLimit` 2 | – | – | – | – | 2/1/1 |

**McPAT**
- The AMD-format XML (template: `gem5/ext/mcpat/regression/test-0/power_region0.xml`, an OoO core; `test-1` has 2 in-order cores) segfaults on the old `ARM_A9*.xml`.
- `machine_type`: 0 = OoO, 1 = in-order.
- Output is an indented text tree. Cores print as `Core N`; other components print their XML `name`. Each node has `Area`, `Peak Dynamic Power`, `Subthreshold Leakage Power`, `Gate Leakage Power`, `Runtime Dynamic Power`, `Runtime Dynamic Energy` and `Total Runtime Energy`.
- The L1 caches sit at `Core N/Instruction Fetch Unit/Instruction Cache` and `Core N/Load/Store Unit/Data Cache`.

**McPAT Vdd** (`cacti/technology.cc`; flavours HP / LSTP / LOP)

| Node | HP | LSTP | LOP |
|---|---|---|---|
| 90 nm | 1.2 | 1.3 | 0.9 |
| 65 nm | 1.1 | 1.2 | 0.8 |
| 45 nm | 1.0 | 1.1 | 0.7 |
| 32 nm | 0.9 | 1.0 | 0.6 |
| 22 nm | 0.8 | 0.8 | 0.6 |

Linear between nodes, e.g. 28 nm → HP 0.86, LSTP 0.92, LOP 0.6.

## Review Focus

1. **Multicore stat naming.** N=1 paths are unindexed and N>1 paths are indexed. The extractor and validator must find every core and cluster in both cases, not only `clusters0` or only `clusters` (tests in Task 8 and Task 9).
2. **Idle cores (`numCycles = 0`).** Validation must not divide by zero or hand McPAT `total_cycles = 0`. Idle cores must still report non-zero static power (tests in Task 7 and Task 9).
3. **Stale or colliding coefficient cache.** Changing any cache size, associativity, core model, node, device, temperature, clock or core count, or rebuilding McPAT, must produce a new hash (test in Task 3).
4. **Running from a different cwd** (`src/`, `run_gem5.sh`, `-d outdir`). `tools/`, `power_cache/` and `power_meta.json` must resolve correctly (Task 7's end-to-end tests run with cwd set to a temporary directory).
5. **`TIMING`/`ATOMIC`.** Cache power models attach, no core models attach, and the run exits 0 with a single warning (test in Task 7).

---

## File Map

| File | Responsibility |
|---|---|
| `pytest.ini` (new) | `testpaths = src/tests`, markers `gem5`, `mcpat`, `slow` |
| `.gitignore` | add `tools/`, `power_cache/` |
| `src/main.py` | CLI, processor/board construction, writes `power_meta.json`, hook returns Root |
| `src/three_level.py` | hierarchy only; walker-cache fix; `get_cache_params()`; power classes removed |
| `src/power/config.py` | `CoreParams`, `CacheParams`, `PowerConfig`, `validate`, `config_hash`, `implied_vdd`, JSON (de)serialization |
| `src/power/events.py` | event catalogue: event → McPAT stat increments and scope |
| `src/power/mcpat_xml.py` | `build_xml(cfg, counts) -> str` |
| `src/power/mcpat_runner.py` | `find_mcpat_bin`, `run_mcpat`, `parse_mcpat_output`, `mcpat_sha256` |
| `src/power/characterize.py` | `component_energies`, `component_leakage`, `characterize`, `get_coefficients`, `Coefficients`; CLI |
| `src/power/mapping.py` | per-CPU-model event → gem5 stat expression; `dyn_expression`; `eval_expression` |
| `src/power/cores.py` | gem5-side: load ARM core classes, `core_params_from_core` |
| `src/power/models.py` | gem5-side: `attach_power_models` |
| `src/validate_mcpat.py` | full-run McPAT cross-check |
| `src/extract_gem5_stats.py` | multicore-aware CSV + totals |
| `src/run_gem5.sh`, `README.md` | paths, flags, docs |
| `src/tests/conftest.py` | puts `src/` on `sys.path`; fixtures `gem5_bin`, `mcpat_bin`, `project_root` |
| `src/tests/unit/test_*.py` | pytest unit tests |
| `src/tests/fixtures/` | captured McPAT outputs; small `stats.txt` files for N=1 and N=2 |
| `src/tests/e2e/test_*.py` | gem5 runs (markers `gem5`, `slow`) |

---

### Task 1: Make the existing project run on gem5 25.1

**Files:**
- Create: `pytest.ini`, `src/tests/conftest.py`, `src/tests/e2e/__init__.py`, `src/tests/e2e/test_baseline_run.py`
- Modify: `src/main.py:110-165`, `src/three_level.py:28-150` (constructor defaults, `_create_core_cluster`), `src/run_gem5.sh:9`, `README.md` (gem5 paths), `.gitignore`

**Interfaces:**
- Produces:
  - conftest fixtures:
    - `project_root() -> Path`
    - `gem5_bin() -> Path` (from `$GEM5_BIN`, default `/home/kevin/Projects/gem5/build/ARM/gem5.opt`; `pytest.skip` if missing)
    - `run_gem5(args: list[str], outdir: Path, cwd: Path) -> subprocess.CompletedProcess`, which runs `gem5_bin -d outdir src/main.py *args` with a 1800 s timeout
  - Markers `gem5`, `mcpat` and `slow` registered in `pytest.ini`.

- [ ] **Step 1: Install pytest into the venv**

Run: `$PY -m pip install pytest`
Expected: `Successfully installed ... pytest-...`

- [ ] **Step 2: Write the failing e2e test** in `src/tests/e2e/test_baseline_run.py`

```python
pytestmark = [pytest.mark.gem5]

def test_timing_hello_world_produces_stats(run_gem5, project_root, tmp_path):
    out = tmp_path / "m5"
    r = run_gem5(["--cpu_type", "TIMING", "--binary",
                  str(project_root / "src/tests/test_sample_arm64")],
                 outdir=out, cwd=tmp_path)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    stats = (out / "stats.txt").read_text()
    assert "simInsts" in stats
    assert "Hello from my own ARM64 binary" in r.stdout
    assert "Clock frequency: 1GHz" in r.stdout
    assert f"Statistics dumped to {out}/stats.txt" in r.stdout
```

- [ ] **Step 3: Run it and confirm it fails**

Run: `cd $P && $PY -m pytest src/tests/e2e/test_baseline_run.py -v`
Expected: FAIL. `returncode == 1` with empty stats (the dropped Root).

- [ ] **Step 4: Fix the bugs**
  - `patched_pre_instantiate` returns `original_pre_instantiate(...)`'s value.
  - In `_create_core_cluster`, use `nwalk = len(core.get_mmu().walkerPorts())`.
    - Always create `dptw_cache`.
    - Create `iptw_cache` only when `nwalk == 2`.
    - With 1 port, call `core.connect_walker_ports(cluster.dptw_cache.cpu_side, cluster.dptw_cache.cpu_side)`. This mirrors `gem5/src/python/gem5/components/cachehierarchies/classic/private_l1_private_l2_walk_cache_hierarchy.py:67-93`.
  - The hierarchy's `*_replacement_policy=None` defaults become `LRURP()` instances created in `__init__`.
  - Print `Clock frequency: <args.clk_freq or "1GHz">`, print `Memory: DualChannelDDR4_2400, size=2GiB` (pass `size="2GiB"`), and print `Statistics dumped to {m5.options.outdir}/stats.txt`.
  - Remove the duplicate `PowerModel, MathExprPowerModel` import.
  - Point `run_gem5.sh`'s `GEM5_BIN` at `/home/kevin/Projects/gem5/build/ARM/gem5.opt`. The README's `gem5_projects/gem5/...` paths become `/home/kevin/Projects/gem5/...`.
  - Add `tools/` and `power_cache/` to `.gitignore`.
  - Leave the old cache power classes in place for now; Task 7 removes them.

- [ ] **Step 5: Run the test and confirm it passes**

Run: `cd $P && $PY -m pytest src/tests/e2e/test_baseline_run.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pytest.ini .gitignore README.md src/main.py src/three_level.py src/run_gem5.sh src/tests/conftest.py src/tests/e2e
git commit -m "fix: run on gem5 25.1 (return Root from hook, single ARM walker cache)"
```

---

### Task 2: Build McPAT and parse its output

**Files:**
- Create: `src/power/__init__.py`, `src/power/mcpat_runner.py`, `src/tests/unit/test_mcpat_runner.py`, `src/tests/fixtures/mcpat_test0.out`, `src/tests/fixtures/mcpat_test1.out`
- Modify: `src/tests/conftest.py` (add the `mcpat_bin` fixture)

**Interfaces:**
- Produces, in `power/mcpat_runner.py`:
  - `@dataclass(frozen=True) class ComponentPower`
    - Fields: `area_mm2: float`, `peak_dynamic_w: float`, `subthreshold_leakage_w: float`, `gate_leakage_w: float`, `runtime_dynamic_w: float`, `runtime_dynamic_energy_j: float`.
    - Property: `leakage_w = subthreshold + gate`.
  - `McpatResult = dict[tuple[str, ...], ComponentPower]`, keyed by path, e.g. `("System",)`, `("System","Core 0")`, `("System","Core 0","Instruction Fetch Unit","Instruction Cache")`, `("System","L2 Cache 0")`.
  - `class McpatError(RuntimeError)` and `class McpatNotFound(McpatError)`.
  - `def find_mcpat_bin(explicit: str | None, project_root: Path) -> Path`
    - Order: `explicit`, then `$MCPAT_BIN`, then `project_root/"tools/mcpat/mcpat"`.
    - Raises `McpatNotFound` with a message containing `make -C <gem5_root>/ext/mcpat BUILD_DIR=<project_root>/tools`.
  - `def parse_mcpat_output(text: str) -> McpatResult`
  - `def run_mcpat(xml_text: str, mcpat_bin: Path, workdir: Path, timeout: float = 300) -> McpatResult`
    - Writes `workdir/input.xml` and runs `mcpat -infile input.xml -print_level 5`.
    - Raises `McpatError` on a non-zero return code, a signal, or zero parsed components. The message includes the return code, the last 2000 characters of stderr, and the XML path.
  - `def mcpat_sha256(mcpat_bin: Path) -> str`

- [ ] **Step 1: Build McPAT and verify the gem5 tree stays clean**

Run: `make -C /home/kevin/Projects/gem5/ext/mcpat BUILD_DIR=$P/tools -j8 && ls -l $P/tools/mcpat/mcpat && git -C /home/kevin/Projects/gem5 status --short ext/mcpat`
Expected: the binary exists and git status prints nothing. If the build leaves files in `ext/mcpat`, stop and report it rather than committing anything in the gem5 tree.

- [ ] **Step 2: Capture fixtures**

Run `tools/mcpat/mcpat -infile <gem5>/ext/mcpat/regression/test-0/power_region0.xml -print_level 5 > src/tests/fixtures/mcpat_test0.out`, then do the same for `test-1`.

- [ ] **Step 3: Write the failing tests**

```python
def test_parse_test0_tree():
    r = parse_mcpat_output((FIX / "mcpat_test0.out").read_text())
    core = r[("System", "Core 0")]
    assert core.runtime_dynamic_energy_j == pytest.approx(1.25634e-07)
    assert core.leakage_w == pytest.approx(4.64481 + 0.193831)
    assert ("System", "Core 0", "Instruction Fetch Unit", "Instruction Cache") in r
    assert ("System", "Core 0", "Load/Store Unit", "Data Cache") in r
    assert ("System", "L2 Cache") in r

def test_parse_test1_two_cores():
    r = parse_mcpat_output((FIX / "mcpat_test1.out").read_text())
    assert ("System", "Core 1") in r

def test_parse_garbage_raises():
    assert parse_mcpat_output("not mcpat output") == {}
    with pytest.raises(McpatError):
        _require_components(parse_mcpat_output("not mcpat output"), "ctx")

def test_find_bin_missing_message(tmp_path, monkeypatch):
    monkeypatch.delenv("MCPAT_BIN", raising=False)
    with pytest.raises(McpatNotFound, match=r"make -C .*ext/mcpat BUILD_DIR="):
        find_mcpat_bin(None, tmp_path)

@pytest.mark.mcpat
@pytest.mark.parametrize("t", [f"test-{i}" for i in range(9)])
def test_bundled_regressions_match(mcpat_bin, t):
    ...  # run mcpat -print_level 10 on regression/<t>/power_region0.xml when region0.out.ref exists;
         # assert output lines [1:] == ref lines [1:]

@pytest.mark.mcpat
def test_run_mcpat_nonzero_exit_raises(mcpat_bin, tmp_path):
    with pytest.raises(McpatError, match="input.xml"):
        run_mcpat("<component id='root'/>", mcpat_bin, tmp_path)
```

`_require_components(result: McpatResult, context: str) -> McpatResult` raises `McpatError` when `result` is empty. `run_mcpat` uses it.

- [ ] **Step 4: Run the tests and confirm they fail** (ImportError)

Run: `cd $P && $PY -m pytest src/tests/unit/test_mcpat_runner.py -v`

- [ ] **Step 5: Implement `mcpat_runner.py`**

The parser is indentation-driven:
- A line matching `^(\s*)(.+):\s*$` opens a node whose depth is its indent.
- Pop the node stack until the top's indent is less than this line's indent.
- `Key = value unit` lines fill the fields of the current node.
- Lines before `System:` are ignored.

- [ ] **Step 6: Run the tests and confirm they pass** (including `-m mcpat`)

Run: `cd $P && $PY -m pytest src/tests/unit/test_mcpat_runner.py -v`
Expected: all pass, and the 9 regressions match.

- [ ] **Step 7: Commit**

`git add src/power src/tests/unit/test_mcpat_runner.py src/tests/fixtures src/tests/conftest.py && git commit -m "feat(power): McPAT runner and output parser"`

---

### Task 3: PowerConfig, validation, hashing, implied Vdd

**Files:**
- Create: `src/power/config.py`, `src/tests/unit/test_config.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class CoreParams`
    - Fields: `kind: str` ("ooo" | "inorder"), `model: str`, `fetch_width: int`, `decode_width: int`, `issue_width: int`, `commit_width: int`, `rob_entries: int`, `iq_entries: int`, `lq_entries: int`, `sq_entries: int`, `phys_int_regs: int`, `phys_fp_regs: int`, `num_alus: int`, `num_muls: int`, `num_fpus: int`.
    - In-order cores use 0 for ROB/IQ/LQ/SQ/phys-reg fields.
  - `@dataclass(frozen=True) class CacheParams`
    - Fields: `name: str` ("l1i" | "l1d" | "l2" | "l3"), `size_bytes: int`, `assoc: int`, `block_size: int`, `latency_cycles: int`, `mshrs: int`.
  - `@dataclass(frozen=True) class PowerConfig`
    - Fields: `cpu_type: str`, `core: CoreParams`, `caches: tuple[CacheParams, ...]` (order l1i, l1d, l2, l3), `num_cores: int`, `clock_mhz: int`, `tech_node_nm: int`, `device_type: str`, `temperature_k: int`.
  - `HPI_FALLBACK_CORE: CoreParams`: in-order, model `"hpi"`, widths 2/2/2/2, ALU/MUL/FPU 2/1/1. Used for TIMING/ATOMIC, where McPAT still needs a core to host the L1s.
  - `class ConfigError(ValueError)`
  - `def validate(cfg: PowerConfig) -> None`
  - `def implied_vdd(node_nm: int, device_type: str) -> float`
  - `def config_to_dict(cfg) -> dict` and `def config_from_dict(d) -> PowerConfig`
  - `def config_hash(cfg: PowerConfig, mcpat_sha: str, schema_version: int) -> str`: SHA-256 of `json.dumps({"config":..., "mcpat":..., "schema":...}, sort_keys=True)`, first 16 hex characters.
  - `DEVICE_TYPES = {"HP": 0, "LSTP": 1, "LOP": 2}`; `SCHEMA_VERSION = 1`.

- [ ] **Step 1: Write the failing tests**

```python
def test_implied_vdd_table():
    assert implied_vdd(28, "LOP") == pytest.approx(0.6)
    assert implied_vdd(28, "HP") == pytest.approx(0.86)
    assert implied_vdd(28, "LSTP") == pytest.approx(0.92)
    assert implied_vdd(45, "HP") == pytest.approx(1.0)

@pytest.mark.parametrize("field,value", [("tech_node_nm", 21), ("tech_node_nm", 91),
    ("device_type", "XX"), ("num_cores", 0), ("clock_mhz", 0), ("temperature_k", 0),
    ("cpu_type", "KVM")])
def test_validate_rejects(field, value):
    with pytest.raises(ConfigError):
        validate(dataclasses.replace(base_cfg(), **{field: value}))

def test_hash_stable_and_sensitive():
    c = base_cfg()
    h = config_hash(c, "abc", 1)
    assert h == config_hash(config_from_dict(config_to_dict(c)), "abc", 1)
    assert len(h) == 16
    variants = [dataclasses.replace(c, num_cores=2), dataclasses.replace(c, clock_mhz=2000),
                dataclasses.replace(c, device_type="HP"), dataclasses.replace(c, temperature_k=340),
                dataclasses.replace(c, caches=(c.caches[0], c.caches[1],
                    dataclasses.replace(c.caches[2], size_bytes=1 << 20), c.caches[3])),
                dataclasses.replace(c, core=dataclasses.replace(c.core, model="neoverse_v2"))]
    hashes = {config_hash(v, "abc", 1) for v in variants} | {h, config_hash(c, "def", 1), config_hash(c, "abc", 2)}
    assert len(hashes) == len(variants) + 3
```

`base_cfg()` is a test helper: O3, the `O3_ARM_v7a_3` params from §Facts, caches 32K/8, 32K/8, 256K/16, 2M/32 with block 64, latencies 4/4/20/64, MSHRs 4/4/6/10, 1 core, 1000 MHz, 28 nm, LOP, 350 K.

- [ ] **Step 2: Run them and confirm they fail.** `$PY -m pytest src/tests/unit/test_config.py -v`

- [ ] **Step 3: Implement `config.py`.** `implied_vdd` linearly interpolates on node between the bracketing table rows of §Facts.

- [ ] **Step 4: Run them and confirm they pass.**

- [ ] **Step 5: Commit** `feat(power): PowerConfig, validation, hashing`

---

### Task 4: Event catalogue and McPAT XML generation

**Files:**
- Create: `src/power/events.py`, `src/power/mcpat_xml.py`, `src/tests/unit/test_mcpat_xml.py`

**Interfaces:**
- Consumes: `PowerConfig`, `CoreParams`, `CacheParams`, `DEVICE_TYPES` (Task 3).
- Produces:
  - `events.EVENTS: dict[str, EventSpec]`, where `EventSpec(target: str, increments: dict[str, int], ooo_only: bool)`. `target` is one of `"core"|"l1i"|"l1d"|"l2"|"l3"`. `increments` maps McPAT stat names to multipliers (each is 1).

    | Event | McPAT stats incremented |
    |---|---|
    | `core.cycles` | `total_cycles` |
    | `core.int_insts` | `total_instructions`, `int_instructions`, `committed_instructions`, `committed_int_instructions` |
    | `core.fp_insts` | `total_instructions`, `fp_instructions`, `committed_instructions`, `committed_fp_instructions` |
    | `core.load_insts` | `load_instructions` |
    | `core.store_insts` | `store_instructions` |
    | `core.branch_insts` | `branch_instructions` |
    | `core.branch_mispredicts` | `branch_mispredictions` |
    | `core.ialu` | `ialu_accesses`, `cdb_alu_accesses` |
    | `core.fpu` | `fpu_accesses`, `cdb_fpu_accesses` |
    | `core.int_rf_reads` / `core.int_rf_writes` | `int_regfile_reads` / `int_regfile_writes` |
    | `core.fp_rf_reads` / `core.fp_rf_writes` | `float_regfile_reads` / `float_regfile_writes` |
    | OoO only: `core.rob_reads` / `core.rob_writes` | `ROB_reads` / `ROB_writes` |
    | OoO only: `core.int_rename_reads` / `core.int_rename_writes` / `core.fp_rename_reads` | `rename_reads` / `rename_writes` / `fp_rename_reads` |
    | OoO only: `core.int_iq_reads` / `core.int_iq_writes` / `core.int_iq_wakeups` | `inst_window_reads` / `inst_window_writes` / `inst_window_wakeup_accesses` |
    | OoO only: `core.fp_iq_reads` / `core.fp_iq_writes` / `core.fp_iq_wakeups` | `fp_inst_window_reads` / `fp_inst_window_writes` / `fp_inst_window_wakeup_accesses` |
    | `{l1i,l1d,l2,l3}.read_accesses` | `read_accesses` |
    | `{l1i,l1d,l2,l3}.write_accesses` | `write_accesses` |
    | `{l1i,l1d,l2,l3}.read_misses` | `read_misses` |

    There is no MUL event and no write-miss event, because gem5 exposes no Scalar/Formula stat for them.
  - `events.events_for(kind: str) -> list[str]`: all events for `"ooo"`; the non-`ooo_only` events for `"inorder"`.
  - `ActivityCounts = dict[tuple[int, str], float]`: `(core_index, event) -> count`. L3 events use core_index 0.
  - `mcpat_xml.build_xml(cfg: PowerConfig, counts: ActivityCounts, system_cycles: int, core_cycles: dict[int, int]) -> str`

    Structure:
    - `system` contains `system.core{i}` for i < num_cores.
    - Each core contains `system.core{i}.icache` (`name="Instruction Cache"`) and `system.core{i}.dcache` (`name="Data Cache"`).
    - `system.L2{i}` has `name="L2 Cache {i}"`; `system.L30` has `name="L3 Cache"`.
    - `number_of_cores`, `number_of_L2s` and `number_of_L3s` are set to match.

    Parameters:
    - Every parameter not derived from `cfg` takes the value from `regression/test-0/power_region0.xml` for OoO, or `test-1` for in-order. Keep those defaults as module-level dicts copied from those files.
    - System: `core_tech_node`, `target_core_clockrate`, `temperature`, `device_type`.
    - Core: `machine_type` (0/1) and widths, ROB, IQ, LQ, SQ, phys regs and ALU/MUL/FPU from `CoreParams`.
    - Caches: `size`, `assoc`, `block_size`, `latency`, `miss_buffer_size` (= mshrs) and `level`.
    - All `*duty_cycle` stats are 1.0. Stats not driven by `counts` are 0.

- [ ] **Step 1: Write the failing tests**

```python
def test_xml_structure_ooo_two_cores():
    root = ET.fromstring(build_xml(cfg(num_cores=2), {}, 2_000_000, {0: 1_000_000, 1: 1_000_000}))
    ids = {c.get("id") for c in root.iter("component")}
    assert {"system.core0", "system.core1", "system.core0.icache", "system.core1.dcache",
            "system.L20", "system.L21", "system.L30"} <= ids
    assert param(root, "system", "core_tech_node") == "28"
    assert param(root, "system", "device_type") == "2"
    assert param(root, "system.core0", "machine_type") == "0"
    assert param(root, "system.L30", "size") == str(2 * 1024 * 1024)

def test_xml_inorder_machine_type():
    root = ET.fromstring(build_xml(cfg(core=HPI_FALLBACK_CORE, cpu_type="MINOR"), {}, 2, {0: 1}))
    assert param(root, "system.core0", "machine_type") == "1"

def test_counts_land_on_mcpat_stats():
    x = ET.fromstring(build_xml(cfg(), {(0, "core.int_insts"): 7, (0, "l1d.read_misses"): 3,
                                        (0, "l3.write_accesses"): 5}, 10, {0: 10}))
    assert stat(x, "system.core0", "int_instructions") == "7"
    assert stat(x, "system.core0", "committed_int_instructions") == "7"
    assert stat(x, "system.core0.dcache", "read_misses") == "3"
    assert stat(x, "system.L30", "write_accesses") == "5"
    assert all(s.get("value") == "1.0" for s in x.iter("stat") if s.get("name").endswith("duty_cycle"))

def test_inorder_rejects_ooo_event():
    with pytest.raises(ValueError):
        build_xml(cfg(core=HPI_FALLBACK_CORE, cpu_type="MINOR"), {(0, "core.rob_reads"): 1}, 1, {0: 1})
```

- [ ] **Step 2: Run them and confirm they fail.**

- [ ] **Step 3: Implement `events.py` and `mcpat_xml.py`** (with `xml.etree.ElementTree`).

- [ ] **Step 4: Run them and confirm they pass.**

- [ ] **Step 5: Smoke-test against real McPAT**

Run a throwaway: `build_xml(base_cfg(), {}, 2_000_000, {0: 1_000_000})` → `run_mcpat`. Write this as `@pytest.mark.mcpat test_generated_xml_runs` in `test_mcpat_xml.py`.

Assert:
- The result contains `("System","Core 0","Instruction Fetch Unit","Instruction Cache")`, `("System","L2 Cache 0")` and `("System","L3 Cache")`.
- Every leakage value is > 0.

If McPAT rejects a parameter, copy the missing parameter from the matching regression XML. Do not invent values.

- [ ] **Step 6: Commit** `feat(power): McPAT event catalogue and XML generation`

---

### Task 5: Characterization with superposition check and cache

**Files:**
- Create: `src/power/characterize.py`, `src/tests/unit/test_characterize.py`

**Interfaces:**
- Consumes:
  - `build_xml`, `EVENTS`, `events_for` (Task 4).
  - `run_mcpat`, `McpatResult`, `mcpat_sha256`, `McpatError` (Task 2).
  - `PowerConfig`, `config_hash`, `config_to_dict`, `implied_vdd`, `SCHEMA_VERSION` (Task 3).
- Produces:
  - `COMPONENTS = ("core", "l1i", "l1d", "l2", "l3")`
  - `def component_energies(r: McpatResult, core_index: int = 0) -> dict[str, float]` and `def component_leakage(r: McpatResult, core_index: int = 0) -> dict[str, float]`
    - l1i = `Core i/Instruction Fetch Unit/Instruction Cache`
    - l1d = `Core i/Load/Store Unit/Data Cache`
    - core = `Core i` − l1i − l1d
    - l2 = `L2 Cache i`
    - l3 = `L3 Cache`
  - `@dataclass class Coefficients`
    - Fields: `schema_version: int`, `config: dict`, `config_hash: str`, `mcpat_sha256: str`, `implied_vdd: float`, `leakage_w: dict[str, float]`, `energy_j: dict[str, dict[str, float]]` (component → event → J; entries with |e| < 1e-30 dropped), `created: str` (ISO-8601).
    - Methods: `to_json() -> str`, `from_json(s) -> Coefficients`.
  - `Runner = Callable[[str], McpatResult]`
  - `def characterize(cfg: PowerConfig, runner: Runner, mcpat_sha: str) -> Coefficients`
  - `def get_coefficients(cfg: PowerConfig, mcpat_bin: Path, cache_dir: Path) -> tuple[Coefficients, Path]`: loads `cache_dir/<hash>.json` when its `schema_version` and `mcpat_sha256` match; otherwise characterizes with a real runner and writes the file.
  - `class SuperpositionError(RuntimeError)`, carrying `deviations: dict[str, float]`.
  - CLI: `python -m power.characterize --config cfg.json [--mcpat_bin X] [--cache_dir Y]` prints the JSON path.

**Algorithm** (the part the signatures don't determine):

```
cores = cfg.num_cores; sysc = 2*C0
base_cyc = {i: C0 for i in range(cores)}
E0 = component_energies(run({}, base_cyc)); L = component_leakage(same run)
for e in events_for(cfg.core.kind):
    counts = {(0, e): N_EVENT}; cyc = dict(base_cyc)
    if e == "core.cycles": counts = {}; cyc[0] = C0 + N_EVENT
    Ee = component_energies(run(counts, cyc))
    energy_j[c][e] = (Ee[c] - E0[c]) / N_EVENT  for each c in COMPONENTS
all-at-once run: counts = {(0,e): N_EVENT for e != core.cycles}, cyc[0] = C0 + N_EVENT
for each c: predicted = E0[c] + Σ_e energy_j[c][e]*N_EVENT
    dev = |Eall[c] - predicted| ; fail if dev > max(0.01*|Eall[c]-E0[c]|, 1e-12)
```

On any `McpatError`, copy the XML and the error text to `cache_dir/failed/<hash>-<event>/` and re-raise. On `SuperpositionError`, write no cache file.

- [ ] **Step 1: Write the failing tests**, using a fake runner.

`FakeRunner(weights)` parses the XML's stats. Each component's energy is `Σ weight[(component, mcpat_stat)] * value`, with leakage constants. It returns an `McpatResult` with the same tree shape as real McPAT.

```python
def test_recovers_linear_coefficients_exactly():
    co = characterize(base_cfg(), FakeRunner(W), "sha")
    assert co.energy_j["l1d"]["l1d.read_accesses"] == pytest.approx(W[("l1d", "read_accesses")])
    assert co.energy_j["core"]["core.int_insts"] == pytest.approx(
        sum(W[("core", s)] for s in EVENTS["core.int_insts"].increments))
    assert co.leakage_w["l3"] == pytest.approx(LEAK["l3"])

def test_nonlinear_runner_trips_superposition():
    with pytest.raises(SuperpositionError):
        characterize(base_cfg(), FakeRunner(W, quadratic_on="read_accesses"), "sha")

def test_inorder_skips_ooo_events():
    co = characterize(cfg(core=HPI_FALLBACK_CORE, cpu_type="MINOR"), FakeRunner(W), "sha")
    assert not any(e.startswith("core.rob") for c in co.energy_j.values() for e in c)

def test_cache_hit_skips_runner(tmp_path, monkeypatch):
    ...  # first get_coefficients call writes <hash>.json (runner patched to FakeRunner);
         # second call with a runner that raises must still return equal Coefficients

def test_stale_schema_regenerates(tmp_path, monkeypatch):
    ...  # write <hash>.json with schema_version=0; get_coefficients must call the runner and overwrite it with schema_version=1
def test_mcpat_failure_writes_failed_dir(tmp_path, monkeypatch):
    ...  # runner raises McpatError on "l2.read_accesses" -> McpatError propagates,
         # failed/<hash>-l2.read_accesses/input.xml exists, and no <hash>.json is written
```

- [ ] **Step 2: Run them and confirm they fail.**

- [ ] **Step 3: Implement `characterize.py`.**

- [ ] **Step 4: Run them and confirm they pass.**

- [ ] **Step 5: Real McPAT characterization** (`@pytest.mark.mcpat test_real_characterization_o3_28nm`)

Run `get_coefficients(base_cfg(), mcpat_bin, tmp_path)`.

Assert:
- No `SuperpositionError`.
- `implied_vdd == 0.6`.
- Every component has `leakage_w > 0`.
- `energy_j["l1d"]["l1d.read_accesses"] > 0`.
- The L2 leakage at 1 MiB is greater than at 256 KiB, which is greater than at 128 KiB (three configs).

If superposition fails for a specific event, report the deviation table and stop. Don't loosen the tolerance without asking the user.

- [ ] **Step 6: Commit** `feat(power): McPAT characterization with superposition check and JSON cache`

---

### Task 6: gem5 stat mapping and expressions

**Files:**
- Create: `src/power/mapping.py`, `src/tests/unit/test_mapping.py`

**Interfaces:**
- Consumes: `EVENTS`, `events_for` (Task 4); `Coefficients` (Task 5).
- Produces:
  - `MAPPING: dict[str, dict[str, str]]`: cpu_type (`"O3"`, `"MINOR"`) → event → expression template.
    - Placeholders: `{core}`, `{l1i}`, `{l1d}`, `{l2}`, `{l3}`, filled with SimObject paths.
    - `TIMING` and `ATOMIC` map only cache events.
    - Each approximated entry carries a `# proxy:` comment explaining it.

    | Event | Expression |
    |---|---|
    | `core.cycles` | `{core}.numCycles` |
    | `core.int_insts` | `{core}.commitStats0.numIntInsts` |
    | `core.fp_insts` | `{core}.commitStats0.numFpInsts + {core}.commitStats0.numVecInsts` (proxy: ARM FP/SIMD) |
    | `core.load_insts` | `{core}.commitStats0.numLoadInsts` |
    | `core.store_insts` | `{core}.commitStats0.numStoreInsts` |
    | `core.branch_insts` | `{core}.executeStats0.numBranches` (proxy: executed, so O3 includes squashed branches) |
    | `core.branch_mispredicts` | `{core}.branchPred.condIncorrect` |
    | `core.ialu` | `{core}.executeStats0.numIntAluAccesses` |
    | `core.fpu` | `{core}.executeStats0.numVecAluAccesses` |
    | `core.int_rf_reads` / `writes` | `{core}.executeStats0.numIntRegReads` / `numIntRegWrites` |
    | `core.fp_rf_reads` / `writes` | `{core}.executeStats0.numVecRegReads` / `numVecRegWrites` |
    | O3: `core.rob_reads` / `writes` | `{core}.rob.reads` / `{core}.rob.writes` |
    | O3: `core.int_rename_reads` | `{core}.rename.intLookups` |
    | O3: `core.int_rename_writes` | `{core}.rename.renamedOperands` (proxy) |
    | O3: `core.fp_rename_reads` | `{core}.rename.vecLookups` |
    | O3: `core.{int,fp}_iq_{reads,writes,wakeups}` | `{core}.{int,fp}InstQueue{Reads,Writes,WakeupAccesses}` |
    | `X.read_accesses` | `({X}.overallAccesses - {X}.WriteReq.accesses)` |
    | `X.write_accesses` | `({X}.WriteReq.accesses + {X}.WritebackDirty.accesses + {X}.WritebackClean.accesses)` |
    | `X.read_misses` | `{X}.overallMisses` (proxy: includes write misses; `<Cmd>.misses` is a Vector) |

  - `def dyn_expression(component: str, coeffs: Coefficients, cpu_type: str, paths: list[dict[str, str]]) -> str`
    - `paths[i]` gives core i's `{core,l1i,l1d,l2,l3}` paths.
    - For per-core components, pass a single-element list.
    - For `l3`, pass every core's paths. Core-scoped event terms are summed over all cores; `l3.*` terms use `paths[0]["l3"]`.
    - Output: `"(<e1>*(<expr1>) + ...) / simSeconds"`, with coefficients formatted `%.9e`. Zero terms are omitted. If no terms remain, return `"0"`.
  - `def static_expression(component: str, coeffs: Coefficients) -> str`: `"%.9e" % leakage_w[component]`.
  - `def stat_names(expr: str) -> list[str]` and `def eval_expression(expr: str, stats: dict[str, float]) -> float`
    - Safe evaluation via `ast` (`+ - * /`, numbers, names). A name lookup tries `name`, then `name + "::total"`; a missing name is 0.0.

- [ ] **Step 1: Write the failing tests**

```python
def test_every_characterized_event_is_mapped():
    for cpu, kind in [("O3", "ooo"), ("MINOR", "inorder")]:
        assert set(events_for(kind)) <= set(MAPPING[cpu])

def test_timing_maps_only_cache_events():
    assert all(e.split(".")[0] in ("l1i", "l1d", "l2", "l3") for e in MAPPING["TIMING"])

def test_no_vector_stats_used():
    banned = ("committedControl", "issuedInstType", ".misses", "mispredicted_0")
    for table in MAPPING.values():
        for expr in table.values():
            assert not any(b in expr for b in banned), expr

def test_dyn_expression_and_eval_roundtrip():
    co = coeffs_with({"l1d": {"l1d.read_accesses": 1e-11, "l1d.read_misses": 4e-11}})
    p = [{"core": "c", "l1i": "i", "l1d": "d", "l2": "l2", "l3": "l3"}]
    expr = dyn_expression("l1d", co, "O3", p)
    stats = {"d.overallAccesses::total": 100, "d.WriteReq.accesses::total": 20,
             "d.overallMisses::total": 5, "simSeconds": 2.0}
    assert eval_expression(expr, stats) == pytest.approx((1e-11 * 80 + 4e-11 * 5) / 2.0)

def test_l3_sums_core_events_over_cores():
    co = coeffs_with({"l3": {"core.int_insts": 1e-12, "l3.read_accesses": 2e-12}})
    paths = [{"core": f"c{i}", "l1i": "", "l1d": "", "l2": "", "l3": "L3"} for i in range(2)]
    e = dyn_expression("l3", co, "O3", paths)
    assert "c0.commitStats0.numIntInsts" in e and "c1.commitStats0.numIntInsts" in e
    assert e.count("L3.overallAccesses") == 1

def test_eval_rejects_calls():
    with pytest.raises(ValueError):
        eval_expression("__import__('os')", {})
```

- [ ] **Step 2: Run them and confirm they fail.**

- [ ] **Step 3: Implement `mapping.py`.**

- [ ] **Step 4: Run them and confirm they pass.**

- [ ] **Step 5: Commit** `feat(power): gem5 stat mapping and power expressions`

---

### Task 7: gem5 integration (cores, models, main.py flags)

**Files:**
- Create: `src/power/cores.py`, `src/power/models.py`, `src/tests/e2e/test_power_runs.py`
- Modify: `src/main.py` (flags, processor, hook, `power_meta.json`); `src/three_level.py` (remove `add_power_model` and every `L*Power*` class; add `get_cache_params`)

**Interfaces:**
- Consumes: Tasks 2–6.
- Produces:
  - `cores.load_core_class(gem5_root: Path, cpu_type: str, core_model: str | None) -> type`
    - Inserts `gem5_root/"configs"` into `sys.path`, then imports `common.cores.arm.O3_ARM_v7a.O3_ARM_v7a_3`, `common.cores.arm.neoverse_v2.NeoverseV2` or `common.cores.arm.HPI.HPI`.
  - `cores.core_params_from_core(cpu: BaseCPU, model: str) -> CoreParams`
    - Reads widths, ROB, LQ, SQ and phys regs from the instance.
    - IQ = Σ `instQueues[i].numEntries`.
    - ALU/MUL/FPU from `FU_COUNTS = {"o3_arm_v7a": (2, 1, 2), "neoverse_v2": (6, 2, 4), "hpi": (2, 1, 1)}`.
    - HPI uses `decodeInputWidth`, `executeIssueLimit` and `executeCommitLimit`, with `kind="inorder"`.
  - `PrivateL1PrivateL2SharedL3CacheHierarchy.get_cache_params(block_size: int) -> tuple[CacheParams, ...]`
    - `latency_cycles = tag_latency + data_latency` (4, 4, 20, 64).
    - `mshrs` comes from the cache classes (4, 4, 6, 10).
  - `models.attach_power_models(board, coeffs: Coefficients, cpu_type: str) -> None`
    - Sets `power_state.default_state = "ON"` and a `PowerModel` with `pm = [ON(dyn, st), CLK_GATED("0", st), SRAM_RETENTION("0", "0"), OFF("0", "0")]` on:
      - each `cluster.l1icache`, `cluster.l1dcache` and `cluster.l2cache`;
      - `l3_cache`;
      - for O3 and MINOR only, each `processor.get_cores()[i].core`.
    - Paths come from `SimObject.path()`, not from string formatting.
  - `main.py` writes `<outdir>/power_meta.json`: `{"config_hash", "coefficients_path", "cpu_type", "core_model", "num_cores", "tech_node_nm", "device_type", "temperature_k", "implied_vdd", "clock_mhz"}`.
  - New `main.py` flags, exactly as in Global Constraints, plus `--gem5_root`, `--mcpat_bin` and `--power_cache_dir`.
    - Rejected combinations exit before simulating, via `parser.error`.
    - Warnings are printed once:
      - `WARNING: core_model neoverse_v2 is a 4-5 nm design; absolute power at <node> nm is overstated.`
      - `WARNING: cpu_type <T> has no core power model; reporting cache power only.`
    - The implied Vdd is printed: `Implied Vdd: 0.60 V (28 nm LOP)`.

- [ ] **Step 1: Write the failing e2e tests** in `src/tests/e2e/test_power_runs.py`

Each test runs with `cwd=tmp_path`. Define `HELLO = str(project_root / "src/tests/test_sample_arm64")` as a module-level constant built from the fixture's path.

```python
pytestmark = [pytest.mark.gem5, pytest.mark.mcpat]

def power_stats(stats_text):  # {path: (dyn, st)} for every "<path>.power_model.dynamicPower"/"staticPower"
    ...

@pytest.mark.parametrize("cpu,model,n", [("O3", "o3_arm_v7a", 1), ("O3", "o3_arm_v7a", 2),
                                         ("MINOR", None, 1), ("MINOR", None, 2),
                                         ("O3", "neoverse_v2", 1)])
def test_power_models_report_nonzero(run_gem5, project_root, tmp_path, cpu, model, n):
    args = ["--cpu_type", cpu, "--num_cores", str(n), "--binary", HELLO]
    if model: args += ["--core_model", model]
    r = run_gem5(args, outdir=tmp_path / "m5", cwd=tmp_path)
    assert r.returncode == 0, r.stderr[-3000:]
    ps = power_stats((tmp_path / "m5/stats.txt").read_text())
    assert len(ps) == 4 * n + 1          # n cores + n*(l1i,l1d,l2) + l3
    assert all(st > 0 for _, st in ps.values())
    active = [p for p in ps if ".cores" in p and (n == 1 or "cores0" in p)] + \
             [p for p in ps if "l1dcache" in p and (n == 1 or "clusters0" in p)]
    assert all(ps[p][0] > 0 for p in active)
    meta = json.loads((tmp_path / "m5/power_meta.json").read_text())
    assert meta["implied_vdd"] == pytest.approx(0.6) and meta["num_cores"] == n
    if model == "neoverse_v2": assert "overstated" in r.stdout

def test_timing_cache_only(run_gem5, tmp_path):
    r = run_gem5(["--cpu_type", "TIMING", "--binary", HELLO], outdir=tmp_path / "m5", cwd=tmp_path)
    assert r.returncode == 0
    ps = power_stats((tmp_path / "m5/stats.txt").read_text())
    assert len(ps) == 4 and not any(".processor." in p for p in ps)
    assert r.stdout.count("has no core power model") == 1

def test_core_model_with_minor_rejected(run_gem5, tmp_path):
    r = run_gem5(["--cpu_type", "MINOR", "--core_model", "neoverse_v2", "--binary", HELLO],
                 outdir=tmp_path / "m5", cwd=tmp_path)
    assert r.returncode != 0 and "core_model" in (r.stderr + r.stdout)

def test_kvm_removed(run_gem5, tmp_path):
    r = run_gem5(["--cpu_type", "KVM", "--binary", HELLO], outdir=tmp_path / "m5", cwd=tmp_path)
    assert r.returncode != 0
```

- [ ] **Step 2: Run them and confirm they fail.** `cd $P && $PY -m pytest src/tests/e2e/test_power_runs.py -v`

- [ ] **Step 3: Implement `cores.py`, `models.py`, `get_cache_params`, and the `main.py` wiring**

Processor construction:
- O3/MINOR: `BaseCPUProcessor(cores=[BaseCPUCore(core=cls(cpu_id=i), isa=ISA.ARM) for i in range(n)])`.
- TIMING/ATOMIC: `SimpleProcessor`.

The `PowerConfig` uses `core_params_from_core(cores[0].core, model)` for O3/MINOR and `HPI_FALLBACK_CORE` otherwise. `get_coefficients` runs **before** `Simulator(board)`, so McPAT errors abort early. `attach_power_models` runs inside the fixed hook.

- [ ] **Step 4: Run them and confirm they pass**, along with Task 1's test.

Run: `cd $P && $PY -m pytest src/tests/e2e -v`
Expected: all pass. If gem5 panics with "Unknown stat type", a mapped stat is a Vector: find it with `stat_names` and fix `MAPPING`.

- [ ] **Step 5: Commit** `feat: McPAT-derived power models for cores and caches; O3/MINOR ARM cores; multicore flags`

---

### Task 8: Multicore-aware stats extractor

**Files:**
- Modify: `src/extract_gem5_stats.py` (rewrite `main` and the prefixes)
- Create: `src/tests/unit/test_extract.py`, `src/tests/fixtures/stats_n1.txt`, `src/tests/fixtures/stats_n2.txt` and the matching `power_meta_n1.json`/`power_meta_n2.json` (copied from Task 7 runs; trim each `stats.txt` to the lines the extractor reads)

**Interfaces:**
- Consumes: the `stats.txt` layout and `power_meta.json` (Task 7).
- Produces:
  - `def discover_components(stats: dict) -> dict[str, list[str]]`: keys `"cores"`, `"l1i"`, `"l1d"`, `"l2"`, `"l3"`. Each value lists stat prefixes in index order and handles both unindexed (N=1) and indexed (N>1) paths.
  - `def build_row(stats: dict, meta: dict, benchmark: str, benchmark_args: str) -> dict`

  CSV columns, in order:
  - Metadata: `benchmark`, `benchmark_args`, `config_hash`, `cpu_type`, `core_model`, `num_cores`, `tech_node_nm`, `device_type`, `implied_vdd`, `clock_mhz`, `simSeconds`.
  - For each core i: `core{i}_insts`, `core{i}_cycles`, `core{i}_ipc`, `core{i}_dynamic_W`, `core{i}_static_W`.
  - For each `{l1i,l1d,l2}` and core i: `{lvl}{i}_accesses`, `{lvl}{i}_misses`, `{lvl}{i}_miss_rate_pct`, `{lvl}{i}_dynamic_W`, `{lvl}{i}_static_W`.
  - `l3_*` with the same five fields.
  - Totals: `core_total_W`, `cache_total_W`, `chip_total_W`, `chip_energy_J` (= `chip_total_W` × `simSeconds`), `dram_energy_J` (Σ `rank*.totalEnergy` × 1e-12), `total_energy_J`.
  - The cache-size flags are dropped from the CLI. Configuration comes from `power_meta.json`, via `--meta <path>` with default `<dir of --stats>/power_meta.json`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("n,fx", [(1, "stats_n1.txt"), (2, "stats_n2.txt")])
def test_discover_and_row(n, fx):
    stats = parse_stats_file(FIX / fx); meta = json.loads((FIX / f"power_meta_n{n}.json").read_text())
    comps = discover_components(stats)
    assert len(comps["cores"]) == n and len(comps["l2"]) == n and len(comps["l3"]) == 1
    row = build_row(stats, meta, "hello", "")
    assert row["chip_total_W"] == pytest.approx(row["core_total_W"] + row["cache_total_W"])
    assert row["dram_energy_J"] > 0
    assert all(row[f"core{i}_static_W"] > 0 for i in range(n))
    if n == 2: assert row["core1_cycles"] == 0 and row["core1_ipc"] == 0
```

- [ ] **Step 2: Run them and confirm they fail.**

- [ ] **Step 3: Implement.** An IPC with zero cycles is 0.

- [ ] **Step 4: Run them and confirm they pass.**

- [ ] **Step 5: Commit** `feat: multicore-aware stats extractor with core, cache, chip and DRAM totals`

---

### Task 9: McPAT cross-check validator

**Files:**
- Create: `src/validate_mcpat.py`, `src/tests/unit/test_validate.py`, `src/tests/e2e/test_validate_run.py`

**Interfaces:**
- Consumes:
  - `build_xml` (Task 4), `run_mcpat` (Task 2), `component_energies`, `component_leakage` (Task 5).
  - `MAPPING`, `eval_expression` (Task 6).
  - `discover_components` (Task 8).
  - `Coefficients.from_json`, `config_from_dict` (Tasks 3 and 5).
- Produces:
  - `def counts_from_stats(stats: dict, cfg: PowerConfig, comps: dict) -> tuple[ActivityCounts, dict[int, int], int]`
    - Evaluates each mapped event expression per core, with that core's prefixes substituted. The L3 events use the L3 prefix.
    - Each core's cycles are `max(numCycles, 1)`.
    - `system_cycles = max(max(core cycles), round(simSeconds * clock_mhz * 1e6))`.
    - `core.cycles` is fed through `core_cycles`, not `counts`.
  - `def compare(stats, coeffs, cfg, comps, mcpat_result) -> list[Row]`
    - `Row(component_path, gem5_dyn_J, mcpat_dyn_J, rel_err, gem5_static_W, mcpat_static_W)` for every core, L1I, L1D, L2, the L3 and the total.
    - `gem5_dyn_J = dynamicPower × simSeconds`.
    - The McPAT side comes from `component_energies(r, i)`; l3 comes from i = 0.
  - CLI: `python validate_mcpat.py --outdir <m5out> [--mcpat_bin X] [--tolerance 0.01]`. It prints a table and exits 1 if any `rel_err > tolerance`, where `rel_err = |g − m| / max(|m|, 1e-15)`. Components where both sides are below 1e-15 J pass.

- [ ] **Step 1: Write the failing unit tests**, using the Task 8 fixtures and a fake runner.

```python
def test_idle_core_cycles_clamped():
    counts, core_cyc, sys_cyc = counts_from_stats(stats_n2, cfg_n2, comps_n2)
    assert core_cyc[1] == 1 and sys_cyc >= core_cyc[0] > 1

def test_counts_use_both_cores():
    counts, _, _ = counts_from_stats(stats_n2, cfg_n2, comps_n2)
    assert counts[(0, "core.int_insts")] > 0 and (1, "core.int_insts") in counts
```

- [ ] **Step 2: Write the failing e2e test** (markers `gem5`, `mcpat`)

Run `main.py` with `O3`/`o3_arm_v7a`, 2 cores, on `test_sample_arm64`. Then run `validate_mcpat.py --outdir`. Assert exit code 0.

Then repeat with MINOR on 1 core, and with `--cpu_type O3 --binary src/tests/small_loop` (mark `slow`). For the `small_loop` run, also assert:
- The core's total power is between 0.05 and 2 W.
- L1D dynamic power is greater than L3 dynamic power.

- [ ] **Step 3: Run them and confirm they fail.**

- [ ] **Step 4: Implement `validate_mcpat.py`.**

- [ ] **Step 5: Run them and confirm they pass.**

Run: `cd $P && $PY -m pytest src/tests/unit/test_validate.py src/tests/e2e/test_validate_run.py -v`

If a component exceeds 1%, print the per-event breakdown from `compare`, report it, and stop. Do not loosen the tolerance without asking the user.

- [ ] **Step 6: Commit** `feat: validate_mcpat cross-check of gem5 power against full McPAT evaluation`

---

### Task 10: Docs and wrappers

**Files:**
- Modify: `README.md`, `src/run_gem5.sh`, `src/execute_command`

**Interfaces:** none new.

- [ ] **Step 1: Update `run_gem5.sh`**
  - Parse and pass through `--cpu_type`, `--core_model`, `--num_cores`, `--clk_freq`, `--tech_node`, `--device_type` and `--temperature`. Drop KVM from the help text.
  - After the run, call `extract_gem5_stats.py --stats m5out/stats.txt`, using the outdir when `-d` is given.

- [ ] **Step 2: Update the README**
  - Requirements: gem5 25.1 at `/home/kevin/Projects/gem5`, plus the McPAT build command.
  - A "Power model" section:
    - Method: McPAT characterization → per-event energies and leakage → `MathExprPowerModel`.
    - A flag table with defaults.
    - The implied-Vdd table for 28 nm.
    - Scope: modelled vs not modelled, copied from spec §6.
    - Limitations:
      - No hardware calibration.
      - No MUL or write-miss events (gem5 Vector stats).
      - Branch counts include squashed branches on O3.
      - Neoverse V2 is overstated.
      - The node range is 22–90 nm.
    - Cache location and how to clear it.
    - How to run `validate_mcpat.py`.
    - How to run the tests: `$PY -m pytest -m "not slow"` and `$PY -m pytest`.
  - Remove the old constant-based description.

- [ ] **Step 3: Verify the README's commands literally**

Run the README's build and run commands as written from `src/`, using `test_sample_arm64`, then `validate_mcpat.py --outdir m5out`. Expected: both exit 0. Delete `src/m5out` afterwards.

- [ ] **Step 4: Run the full suite.** `cd $P && $PY -m pytest -v`. Expected: all pass.

- [ ] **Step 5: Commit** `docs: power model README, wrapper flags`
