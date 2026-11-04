"""Run McPAT and parse its text output. Standard library only."""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_GEM5_ROOT = "/home/kevin/Projects/gem5"

_HEADER_RE = re.compile(r"^(\s*)(\S.*?):\s*$")
_VALUE_RE = re.compile(r"^\s*(.+?)\s*=\s*(\S+)(?:\s+\S+)?\s*$")

_FIELD_BY_KEY = {
    "Area": "area_mm2",
    "Peak Dynamic Power": "peak_dynamic_w",
    "Subthreshold Leakage Power": "subthreshold_leakage_w",
    "Gate Leakage Power": "gate_leakage_w",
    "Runtime Dynamic Power": "runtime_dynamic_w",
    "Runtime Dynamic Energy": "runtime_dynamic_energy_j",
}


class McpatError(RuntimeError):
    """McPAT failed or produced unusable output."""


class McpatNotFound(McpatError):
    """McPAT binary could not be located."""


@dataclass(frozen=True)
class ComponentPower:
    area_mm2: float = 0.0
    peak_dynamic_w: float = 0.0
    subthreshold_leakage_w: float = 0.0
    gate_leakage_w: float = 0.0
    runtime_dynamic_w: float = 0.0
    runtime_dynamic_energy_j: float = 0.0

    @property
    def leakage_w(self) -> float:
        return self.subthreshold_leakage_w + self.gate_leakage_w


McpatResult = dict[tuple[str, ...], ComponentPower]


def find_mcpat_bin(explicit: str | None, project_root: Path) -> Path:
    """Locate the McPAT binary: explicit, $MCPAT_BIN, then tools/mcpat/mcpat."""
    candidates = [explicit, os.environ.get("MCPAT_BIN"),
                  str(Path(project_root) / "tools/mcpat/mcpat")]
    for c in candidates:
        if c and Path(c).is_file():
            return Path(c)
    gem5_root = os.environ.get("GEM5_ROOT") or DEFAULT_GEM5_ROOT
    raise McpatNotFound(
        "McPAT binary not found. Build it with: "
        f"make -C {gem5_root}/ext/mcpat BUILD_DIR={project_root}/tools"
    )


def parse_mcpat_output(text: str) -> McpatResult:
    """Parse McPAT's indented tree output into a path-keyed dict."""
    fields: dict[tuple[str, ...], dict[str, float]] = {}
    stack: list[tuple[int, str]] = []
    started = False
    for line in text.splitlines():
        m = _HEADER_RE.match(line)
        if m and "=" not in line:
            indent, name = len(m.group(1)), m.group(2).strip()
            if not started:
                if name != "System":
                    continue
                started = True
            while stack and stack[-1][0] >= indent:
                stack.pop()
            stack.append((indent, name))
            fields.setdefault(tuple(n for _, n in stack), {})
            continue
        if not started or not stack:
            continue
        v = _VALUE_RE.match(line)
        if not v:
            continue
        field = _FIELD_BY_KEY.get(v.group(1))
        if field is None:
            continue
        try:
            val = float(v.group(2))
        except ValueError:
            continue
        fields[tuple(n for _, n in stack)][field] = val
    return {k: ComponentPower(**v) for k, v in fields.items()}


def _require_components(result: McpatResult, context: str) -> McpatResult:
    if not result:
        raise McpatError(f"McPAT output contained no components ({context})")
    return result


def run_mcpat(xml_text: str, mcpat_bin: Path, workdir: Path,
              timeout: float = 300) -> McpatResult:
    """Write input.xml in workdir, run McPAT, and parse its output."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    xml_path = workdir / "input.xml"
    xml_path.write_text(xml_text)
    try:
        proc = subprocess.run(
            [str(mcpat_bin), "-infile", "input.xml", "-print_level", "5"],
            cwd=workdir, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise McpatError(f"McPAT timed out after {timeout}s on {xml_path}") from e
    if proc.returncode != 0:
        kind = (f"killed by signal {-proc.returncode}"
                if proc.returncode < 0 else "failed")
        raise McpatError(
            f"McPAT {kind} (returncode={proc.returncode}) on {xml_path}; "
            f"stderr tail: {proc.stderr[-2000:]}"
        )
    return _require_components(parse_mcpat_output(proc.stdout),
                               f"returncode={proc.returncode}, {xml_path}")


def mcpat_sha256(mcpat_bin: Path) -> str:
    h = hashlib.sha256()
    with open(mcpat_bin, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
