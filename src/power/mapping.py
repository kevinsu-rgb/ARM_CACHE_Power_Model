"""Map McPAT events to gem5 stat expressions and build MathExprPowerModel strings."""
from __future__ import annotations

import ast
import math
import re
from decimal import Decimal

from power.characterize import Coefficients

_CORE = "{core}"

# Rows shared by O3 and MINOR: event -> template.
_CORE_COMMON: dict[str, str] = {
    # idle/suspended cores report numCycles = 0, deliberately modelling them as clock-gated (leakage only)
    "core.cycles": "{core}.numCycles",
    "core.int_insts": "{core}.commitStats0.numIntInsts",
    # proxy: ARM FP/SIMD activity is reported in the Vec* stats
    "core.fp_insts": "{core}.commitStats0.numFpInsts + {core}.commitStats0.numVecInsts",
    "core.load_insts": "{core}.commitStats0.numLoadInsts",
    "core.store_insts": "{core}.commitStats0.numStoreInsts",
    # proxy: executed branches, so O3 includes squashed ones
    "core.branch_insts": "{core}.executeStats0.numBranches",
    "core.ialu": "{core}.executeStats0.numIntAluAccesses",
    # proxy: ARM FP ops execute on the vector ALU
    "core.fpu": "{core}.executeStats0.numVecAluAccesses",
    "core.int_rf_reads": "{core}.executeStats0.numIntRegReads",
    "core.int_rf_writes": "{core}.executeStats0.numIntRegWrites",
    # proxy: FP register file is the vector register file on ARM
    "core.fp_rf_reads": "{core}.executeStats0.numVecRegReads",
    "core.fp_rf_writes": "{core}.executeStats0.numVecRegWrites",
}

_CORE_O3_ONLY: dict[str, str] = {
    "core.rob_reads": "{core}.rob.reads",
    "core.rob_writes": "{core}.rob.writes",
    "core.int_rename_reads": "{core}.rename.intLookups",
    # proxy: renamedOperands counts all renamed operands, not just int writes
    "core.int_rename_writes": "{core}.rename.renamedOperands",
    "core.fp_rename_reads": "{core}.rename.vecLookups",
    "core.int_iq_reads": "{core}.intInstQueueReads",
    "core.int_iq_writes": "{core}.intInstQueueWrites",
    "core.int_iq_wakeups": "{core}.intInstQueueWakeupAccesses",
    "core.fp_iq_reads": "{core}.fpInstQueueReads",
    "core.fp_iq_writes": "{core}.fpInstQueueWrites",
    "core.fp_iq_wakeups": "{core}.fpInstQueueWakeupAccesses",
}

_CACHE_ROWS: dict[str, str] = {
    "read_accesses": "({X}.overallAccesses - {X}.WriteReq.accesses)",
    "write_accesses": ("({X}.WriteReq.accesses + {X}.WritebackDirty.accesses"
                       " + {X}.WritebackClean.accesses)"),
    # proxy: includes write misses; <Cmd>.misses is a Vector and unusable
    "read_misses": "{X}.overallMisses",
}


def _cache_rows() -> dict[str, str]:
    rows: dict[str, str] = {}
    for c in ("l1i", "l1d", "l2", "l3"):
        for stat, tmpl in _CACHE_ROWS.items():
            if (c, stat) == ("l1i", "write_accesses"):
                continue  # McPAT icache has no write_accesses stat
            rows[f"{c}.{stat}"] = tmpl.replace("{X}", "{" + c + "}")
    return rows


_CACHES = _cache_rows()

MAPPING: dict[str, dict[str, str]] = {
    "O3": {**_CORE_COMMON, **_CORE_O3_ONLY, **_CACHES},
    "MINOR": {**_CORE_COMMON, **_CACHES},
    "TIMING": dict(_CACHES),
    "ATOMIC": dict(_CACHES),
}


def _fmt(v: float) -> str:
    """Plain fixed-point literal, never exponent notation.

    gem5's MathExpr splits on the '-'/'+' of an exponent, silently corrupting
    the value, so exponents must not appear in any expression string.
    """
    if not math.isfinite(v):
        raise ValueError(f"non-finite coefficient {v!r}")
    return format(Decimal(repr(float(v))), "f")


def dyn_expression(component: str, coeffs: Coefficients, cpu_type: str,
                   paths: list[dict[str, str]]) -> str:
    """Build the dynamic-power expression for one component.

    Core-scoped events are summed over every entry of ``paths``; cache events
    use ``paths[0]``. Events outside MAPPING[cpu_type] and zero coefficients are
    dropped. Negative coefficients become subtractions.
    """
    table = MAPPING[cpu_type]
    energies = coeffs.energy_j.get(component, {})
    out = ""
    for event, tmpl in table.items():
        e = energies.get(event, 0.0)
        if e == 0.0:
            continue
        if event.startswith("core."):
            expr = " + ".join(f"({tmpl.format(**p)})" for p in paths)
        else:
            expr = tmpl.format(**paths[0])
        term = f"{_fmt(abs(e))}*({expr})"
        if not out:
            out = term if e > 0 else f"0 - {term}"
        else:
            out += (" + " if e > 0 else " - ") + term
    if not out:
        return "0"
    return f"({out}) / simSeconds"


def static_expression(component: str, coeffs: Coefficients) -> str:
    """Leakage power literal in watts; "0" when the component has no entry."""
    w = coeffs.leakage_w.get(component)
    if w is None:
        return "0"
    return _fmt(w) if w >= 0 else f"(0 - {_fmt(-w)})"


_NAME_RE = re.compile(r"(?<![A-Za-z0-9_.])[A-Za-z_][A-Za-z0-9_.]*")


def stat_names(expr: str) -> list[str]:
    """Stat names in first-appearance order, deduplicated, excluding simSeconds."""
    seen: dict[str, None] = {}
    for n in _NAME_RE.findall(expr):
        if n != "simSeconds":
            seen.setdefault(n)
    return list(seen)


def eval_expression(expr: str, stats: dict[str, float]) -> float:
    """Safely evaluate a power expression against a stats dict.

    Names resolve via ``name`` then ``name::total``; missing names are 0.0.
    Division by zero yields 0.0.

    Raises:
        ValueError: the expression uses anything beyond + - * /, numbers, names.
    """
    table: dict[str, str] = {}

    def sub(m: re.Match[str]) -> str:
        ph = f"__s{len(table)}"
        table[ph] = m.group(0)
        return ph

    try:
        tree = ast.parse(_NAME_RE.sub(sub, expr).strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"bad expression: {exc}") from exc

    def lookup(name: str) -> float:
        for k in (name, name + "::total"):
            if k in stats:
                return float(stats[k])
        return 0.0

    def ev(n: ast.AST) -> float:
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and type(n.value) in (int, float):
            return float(n.value)
        if isinstance(n, ast.Name):
            if n.id not in table:
                raise ValueError(f"disallowed name {n.id!r}")
            return lookup(table[n.id])
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)) \
                and isinstance(n.operand, ast.Constant):
            v = ev(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Add):
                return a + b
            if isinstance(n.op, ast.Sub):
                return a - b
            if isinstance(n.op, ast.Mult):
                return a * b
            return a / b if b != 0.0 else 0.0
        raise ValueError(f"disallowed expression element {type(n).__name__}")

    return ev(tree)
