"""Safe subprocess execution.

Rules enforced here:
* commands are always a list (never a shell string) -> no shell injection
* binaries are resolved via ``shutil.which`` and a clear error is raised if missing
* stdout/stderr are captured; on failure we raise with a trimmed stderr tail
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from .errors import MissingDependencyError
from ..logging_setup import get_logger

log = get_logger("clipforge.shell")


@dataclass
class RunResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


def which(binary: str) -> str | None:
    return shutil.which(binary)


def require(binary: str, *, install_hint: str) -> str:
    path = shutil.which(binary)
    if not path:
        raise MissingDependencyError(
            f"{binary!r} was not found on your PATH.",
            hint=install_hint,
        )
    return path


def run(
    args: Sequence[str],
    *,
    timeout: float | None = None,
    check: bool = True,
    cwd: str | None = None,
) -> RunResult:
    """Run a command. ``args[0]`` must be an absolute path or a resolvable name."""
    arg_list = [str(a) for a in args]
    log.debug("run: %s", " ".join(arg_list))
    try:
        proc = subprocess.run(
            arg_list,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            check=False,
        )
    except FileNotFoundError as e:  # pragma: no cover - defensive
        raise MissingDependencyError(f"Command not found: {arg_list[0]}") from e

    result = RunResult(arg_list, proc.returncode, proc.stdout or "", proc.stderr or "")
    if check and proc.returncode != 0:
        tail = "\n".join((result.stderr or result.stdout).strip().splitlines()[-12:])
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {arg_list[0]} ...\n{tail}"
        )
    return result


def run_streaming(
    args: Sequence[str],
    *,
    on_line: Callable[[str], None],
    stderr: bool = True,
) -> int:
    """Run a command, invoking ``on_line`` for every line of output.

    Used for FFmpeg progress parsing. Returns the exit code.
    """
    arg_list = [str(a) for a in args]
    log.debug("run_streaming: %s", " ".join(arg_list))
    proc = subprocess.Popen(
        arg_list,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if stderr else subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    try:
        for raw in proc.stdout:
            on_line(raw.rstrip("\n"))
    finally:
        proc.stdout.close()
    return proc.wait()


def iter_progress_lines(lines: Iterable[str]):
    """Yield (key, value) pairs from FFmpeg ``-progress pipe:1`` output."""
    for line in lines:
        if "=" in line:
            k, _, v = line.partition("=")
            yield k.strip(), v.strip()
