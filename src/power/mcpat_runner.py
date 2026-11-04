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


TAIL_CHARS = 2000


class McpatError(RuntimeError):
    """McPAT failed or produced unusable output.

    ``stdout``/``stderr`` hold McPAT's complete output when it is known (McPAT
    reports fatal errors such as CACTI failures on stdout).
    """

    def __init__(self, message: str, *, stdout: str = "", stderr: str = ""):
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


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


class McpatOutput(dict):
    """A McpatResult that also keeps McPAT's raw stdout/stderr for diagnostics."""

    stdout: str = ""
    stderr: str = ""


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


def _tails(stdout: str, stderr: str) -> str:
    """Message suffix with the last TAIL_CHARS characters of both streams."""
    return (f"\n--- McPAT stdout (last {TAIL_CHARS} chars) ---\n{stdout[-TAIL_CHARS:]}"
            f"\n--- McPAT stderr (last {TAIL_CHARS} chars) ---\n{stderr[-TAIL_CHARS:]}")


def _require_components(result: McpatResult, context: str,
                        stdout: str = "", stderr: str = "") -> McpatResult:
    if not result:
        raise McpatError(f"McPAT output contained no components ({context})"
                         + _tails(stdout, stderr), stdout=stdout, stderr=stderr)
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
        out = _text(e.stdout)
        err = _text(e.stderr)
        raise McpatError(f"McPAT timed out after {timeout}s on {xml_path}" + _tails(out, err),
                         stdout=out, stderr=err) from e
    if proc.returncode != 0:
        kind = (f"killed by signal {-proc.returncode}"
                if proc.returncode < 0 else "failed")
        raise McpatError(
            f"McPAT {kind} (returncode={proc.returncode}) on {xml_path}"
            + _tails(proc.stdout, proc.stderr),
            stdout=proc.stdout, stderr=proc.stderr)
    out = McpatOutput(_require_components(parse_mcpat_output(proc.stdout),
                                          f"returncode={proc.returncode}, {xml_path}",
                                          proc.stdout, proc.stderr))
    out.stdout, out.stderr = proc.stdout, proc.stderr
    return out


def _text(b: str | bytes | None) -> str:
    if b is None:
        return ""
    return b.decode(errors="replace") if isinstance(b, bytes) else b


def mcpat_sha256(mcpat_bin: Path) -> str:
    h = hashlib.sha256()
    with open(mcpat_bin, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
