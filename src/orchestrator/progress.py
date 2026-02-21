"""Real-time progress logging for agent execution."""

from __future__ import annotations

import sys
import threading
import time

_GREY = "\033[90m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RESET = "\033[0m"
_BOLD = "\033[1m"


def log_tool_call(tool_name: str, args: dict) -> None:
    """Print a tool invocation as it happens."""
    if tool_name == "write_file":
        fname = args.get("filename", "?")
        size = len(args.get("content", ""))
        print(f"  {_GREEN}✎ write{_RESET}  {fname} ({size:,} bytes)")
    elif tool_name == "read_file":
        fname = args.get("filename", "?")
        print(f"  {_CYAN}◉ read{_RESET}   {fname}")
    elif tool_name == "list_files":
        directory = args.get("directory", ".")
        print(f"  {_CYAN}◎ list{_RESET}   {directory}/")
    elif tool_name == "run_command":
        cmd = args.get("command", "?")
        print(f"  {_YELLOW}▶ run{_RESET}    {cmd[:80]}")
    elif tool_name == "run_tests":
        print(f"  {_YELLOW}▶ test{_RESET}   running tests...")
    else:
        print(f"  {_GREY}⚙ {tool_name}{_RESET}")


def log_llm_start(agent_name: str, iteration: int = 0) -> None:
    """Print that the LLM is thinking."""
    suffix = f" (tool round {iteration})" if iteration > 0 else ""
    print(f"  {_GREY}⏳ {agent_name} thinking…{suffix}{_RESET}", flush=True)


def log_llm_done(agent_name: str, elapsed: float) -> None:
    """Print that the LLM finished."""
    print(f"  {_GREY}✓ {agent_name} responded ({elapsed:.1f}s){_RESET}")


def log_agent_start(agent_name: str) -> None:
    """Print agent start banner."""
    label = agent_name.upper().replace("_", " ")
    sep = "─" * 60
    print(f"\n┌{sep}┐")
    print(f"│ {_BOLD}{label:^58}{_RESET} │")
    print(f"└{sep}┘")


def log_agent_done(agent_name: str, elapsed: float, file_count: int = 0) -> None:
    """Print agent completion summary."""
    parts = [f"{elapsed:.1f}s"]
    if file_count:
        parts.append(f"{file_count} files written")
    summary = ", ".join(parts)
    print(f"  {_GREEN}✓ {agent_name} complete ({summary}){_RESET}\n")


class Spinner:
    """Simple terminal spinner for long-running LLM calls."""

    _FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, label: str) -> None:
        self._label = label
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join()
        sys.stdout.write("\r" + " " * 80 + "\r")
        sys.stdout.flush()

    def _spin(self) -> None:
        i = 0
        t0 = time.time()
        while self._running:
            elapsed = time.time() - t0
            frame = self._FRAMES[i % len(self._FRAMES)]
            sys.stdout.write(f"\r  {_GREY}{frame} {self._label} ({elapsed:.0f}s){_RESET}")
            sys.stdout.flush()
            time.sleep(0.1)
            i += 1
