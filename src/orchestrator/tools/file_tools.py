"""File I/O tools for agents that need to create and read project artifacts."""

from __future__ import annotations

import os
from pathlib import Path

from langchain_core.tools import tool


def _get_output_dir() -> str:
    return os.environ.get("ORCHESTRATOR_OUTPUT_DIR", "output")


def _resolve_path(filename: str) -> Path:
    base = Path(_get_output_dir())
    resolved = (base / filename).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        raise ValueError(f"Path traversal detected: {filename}")
    return resolved


@tool
def write_file(filename: str, content: str) -> str:
    """Write content to a file in the output directory.

    Args:
        filename: Relative path within the output directory (e.g. "src/main.py").
        content: The full content to write.

    Returns:
        Confirmation message with the written file path.
    """
    path = _resolve_path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"Written {len(content)} bytes to {path}"


@tool
def read_file(filename: str) -> str:
    """Read a file from the output directory.

    Args:
        filename: Relative path within the output directory.

    Returns:
        The file content as a string.
    """
    path = _resolve_path(filename)
    if not path.exists():
        return f"File not found: {filename}"
    return path.read_text(encoding="utf-8")


@tool
def list_files(directory: str = ".") -> str:
    """List files in a directory under the output directory.

    Args:
        directory: Relative directory path (default: root of output).

    Returns:
        Newline-separated list of file paths relative to the output directory.
    """
    base = _resolve_path(directory)
    if not base.exists():
        return f"Directory not found: {directory}"
    output_dir = _get_output_dir()
    files = sorted(
        str(p.relative_to(Path(output_dir).resolve()))
        for p in base.rglob("*")
        if p.is_file()
    )
    return "\n".join(files) if files else "(empty)"
