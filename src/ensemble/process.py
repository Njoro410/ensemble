"""Subprocess helper that kills the whole process group on timeout."""

from __future__ import annotations

import os
import signal
import subprocess


class ProcessTimeout(Exception):
    def __init__(self, stdout: bytes, stderr: bytes) -> None:
        super().__init__("process timed out")
        self.stdout = stdout
        self.stderr = stderr


def run_capture(
    cmd: list[str],
    *,
    env: dict[str, str],
    cwd: str,
    timeout: float,
) -> subprocess.CompletedProcess[bytes]:
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout, stderr = process.communicate()
        raise ProcessTimeout(stdout, stderr) from None
    return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)
