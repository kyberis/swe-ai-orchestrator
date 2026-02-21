"""Test execution tools for the testing agent."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from langchain_core.tools import tool


def _get_output_dir() -> str:
    return os.environ.get("ORCHESTRATOR_OUTPUT_DIR", "output")


@tool
def run_tests(test_path: str = ".", timeout: int = 120) -> str:
    """Run pytest on the specified path within the output directory.

    Args:
        test_path: Relative path to a test file or directory (default: run all).
        timeout: Maximum seconds to wait for tests to complete.

    Returns:
        Combined stdout and stderr from pytest.
    """
    base = Path(_get_output_dir()).resolve()
    target = (base / test_path).resolve()
    if not str(target).startswith(str(base)):
        return "Error: path traversal detected."

    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", str(target), "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(base),
        )
        output = result.stdout
        if result.stderr:
            output += "\n--- STDERR ---\n" + result.stderr
        output += f"\n\nReturn code: {result.returncode}"
        return output
    except subprocess.TimeoutExpired:
        return f"Error: tests timed out after {timeout}s"
    except FileNotFoundError:
        return "Error: pytest not found. Make sure it is installed."


@tool
def run_command(command: str, timeout: int = 60) -> str:
    """Run an arbitrary shell command in the output directory. Use sparingly.

    Args:
        command: The shell command to execute.
        timeout: Maximum seconds to wait.

    Returns:
        Combined stdout and stderr.
    """
    base = Path(_get_output_dir()).resolve()
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(base),
        )
        output = result.stdout
        if result.stderr:
            output += "\n--- STDERR ---\n" + result.stderr
        return output
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s"
