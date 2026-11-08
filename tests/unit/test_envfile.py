"""The .env loader (src/power/envfile.py) and its bash twin in run_gem5.sh."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from power.envfile import DEFAULT_ENV_FILE, EnvFileError, load_env, parse_env_file

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SAMPLE = (
    "# comment\n"
    "\n"
    "PLAIN=/opt/gem5\n"
    "  SPACED  =  /a b/c  \n"
    "export EXPORTED=/x\n"
    "DQ=\"/quoted path\"\n"
    "SQ='/single'\n"
    "HASH=/a#b\n"
    "LITERAL=$HOME/~/x\n"
    "EMPTY=\n"
    "CRLF=/crlf\r\n"
    "LAST=/no-newline"
)
EXPECTED = {
    "PLAIN": "/opt/gem5",
    "SPACED": "/a b/c",
    "EXPORTED": "/x",
    "DQ": "/quoted path",
    "SQ": "/single",
    "HASH": "/a#b",
    "LITERAL": "$HOME/~/x",
    "EMPTY": "",
    "CRLF": "/crlf",
    "LAST": "/no-newline",
}


def test_default_path_is_project_root():
    assert DEFAULT_ENV_FILE == PROJECT_ROOT / ".env"


def test_parse(tmp_path):
    f = tmp_path / ".env"
    f.write_bytes(SAMPLE.encode())
    assert parse_env_file(f) == EXPECTED


@pytest.mark.parametrize("line", ["NO_EQUALS", "1BAD=x", "export ONLY", "A B=c"])
def test_malformed_line_names_file_and_line(tmp_path, line):
    f = tmp_path / ".env"
    f.write_text(f"# ok\n{line}\n")
    with pytest.raises(EnvFileError, match=rf"{f}:2:"):
        parse_env_file(f)


def test_existing_variables_win(tmp_path):
    f = tmp_path / ".env"
    f.write_text("GEM5_ROOT=/from/file\nMCPAT_BIN=/from/file/mcpat\n")
    env = {"GEM5_ROOT": "/from/shell"}
    applied = load_env(f, env)
    assert applied == {"MCPAT_BIN": "/from/file/mcpat"}
    assert env == {"GEM5_ROOT": "/from/shell", "MCPAT_BIN": "/from/file/mcpat"}


def test_set_but_empty_variable_also_wins(tmp_path):
    f = tmp_path / ".env"
    f.write_text("GEM5_ROOT=/from/file\n")
    env = {"GEM5_ROOT": ""}
    assert load_env(f, env) == {}
    assert env == {"GEM5_ROOT": ""}


def test_missing_file_is_a_no_op(tmp_path):
    env = {}
    assert load_env(tmp_path / "absent.env", env) == {}
    assert env == {}


# ----------------- run_gem5.sh -----------------

def _copy_wrapper(tmp_path: Path, env_text: str | None) -> Path:
    """A throwaway project: <tmp>/src/run_gem5.sh and <tmp>/.env."""
    (tmp_path / "src").mkdir()
    script = tmp_path / "src" / "run_gem5.sh"
    shutil.copy(PROJECT_ROOT / "src" / "run_gem5.sh", script)
    if env_text is not None:
        (tmp_path / ".env").write_bytes(env_text.encode())
    (tmp_path / "bench").write_text("")
    return script


def _run_wrapper(script: Path, cwd: Path, extra_env: dict[str, str] | None = None):
    env = {"PATH": os.environ["PATH"], **(extra_env or {})}
    return subprocess.run(["bash", str(script), "--binary", "bench"], cwd=cwd,
                          env=env, capture_output=True, text=True, timeout=60)


def test_wrapper_reads_env_file(tmp_path):
    script = _copy_wrapper(tmp_path, "GEM5_ROOT=/nonexistent/gem5\n"
                                     "GEM5_BIN='/nonexistent/gem5.opt'\n")
    r = _run_wrapper(script, tmp_path)
    assert r.returncode == 1
    assert "GEM5_ROOT is not a directory: /nonexistent/gem5" in r.stderr
    assert "GEM5_BIN is not an executable file: /nonexistent/gem5.opt" in r.stderr
    assert "MCPAT_BIN is not set" in r.stderr


def test_wrapper_shell_variable_wins(tmp_path):
    script = _copy_wrapper(tmp_path, "GEM5_ROOT=/from/file\n")
    r = _run_wrapper(script, tmp_path, {"GEM5_ROOT": "/from/shell"})
    assert "GEM5_ROOT is not a directory: /from/shell" in r.stderr
    assert "/from/file" not in r.stderr


def test_wrapper_malformed_line(tmp_path):
    script = _copy_wrapper(tmp_path, "GEM5_ROOT=/x\nnot a setting\n")
    r = _run_wrapper(script, tmp_path)
    assert r.returncode == 1
    assert f"{tmp_path / '.env'}:2: expected KEY=VALUE" in r.stderr


def test_wrapper_without_env_file(tmp_path):
    script = _copy_wrapper(tmp_path, None)
    r = _run_wrapper(script, tmp_path)
    assert r.returncode == 1
    assert "GEM5_ROOT is not set" in r.stderr


def test_bash_and_python_parsers_agree(tmp_path):
    """Source only the bash loader and print what it exported."""
    f = tmp_path / ".env"
    f.write_bytes(SAMPLE.encode())
    src = (PROJECT_ROOT / "src" / "run_gem5.sh").read_text()
    start = src.index("load_env_file() {")
    end = src.index("\n}\n", start) + 3
    prog = src[start:end] + f'load_env_file "{f}"\n' + "".join(
        f'printf "%s\\0%s\\0" {k} "${{{k}}}"\n' for k in EXPECTED)
    out = subprocess.run(["bash", "-c", prog], env={"PATH": os.environ["PATH"]},
                         capture_output=True, check=True, timeout=30).stdout.decode()
    parts = out.split("\0")[:-1]
    assert dict(zip(parts[::2], parts[1::2])) == EXPECTED
