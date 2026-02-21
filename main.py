"""CLI entry point for the multi-agent engineering orchestrator."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from src.orchestrator.graph import build_graph
from src.orchestrator.llm import AGENT_MODEL_DEFAULTS, get_model, invoke_with_retry

load_dotenv()

PROJECTS_ROOT = Path("projects")
BANNER = """
╔══════════════════════════════════════════════════════════════╗
║           Engineering Orchestrator (Multi-Agent)             ║
║                                                              ║
║  Agents: Requirements → Design → Coding → Testing → Monitor ║
║  Type your project description to begin.                     ║
║  Type 'quit' or 'exit' to stop.                              ║
╚══════════════════════════════════════════════════════════════╝
"""


def _generate_project_slug(description: str) -> str:
    """Ask the LLM for a short, filesystem-safe project name."""
    model = get_model(temperature=0.0)
    response = invoke_with_retry(
        model,
        "Given this project description, respond with ONLY a short project name "
        "(2-4 lowercase words, separated by hyphens, no special characters). "
        "Example: 'user-registration-app' or 'chat-dashboard'.\n\n"
        f"Description: {description}",
    )
    slug = response.content.strip().strip('"').strip("'").lower()
    slug = re.sub(r"[^a-z0-9-]", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "project"


def _unique_project_dir(slug: str) -> Path:
    """Ensure the project directory doesn't collide with an existing one."""
    PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
    candidate = PROJECTS_ROOT / slug
    if not candidate.exists():
        return candidate
    counter = 2
    while True:
        candidate = PROJECTS_ROOT / f"{slug}-{counter}"
        if not candidate.exists():
            return candidate
        counter += 1


def _list_existing_projects() -> list[Path]:
    """Return directories inside PROJECTS_ROOT sorted by name."""
    if not PROJECTS_ROOT.exists():
        return []
    return sorted(p for p in PROJECTS_ROOT.iterdir() if p.is_dir())


def _load_project_files(project_dir: Path) -> dict[str, str]:
    """Recursively read all files inside a project directory into a dict."""
    files: dict[str, str] = {}
    for path in sorted(project_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(project_dir))
        if any(skip in rel for skip in ["node_modules", ".git", "__pycache__", ".DS_Store"]):
            continue
        try:
            files[rel] = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            pass
    return files


def _choose_project_mode() -> tuple[str, Path | None]:
    """Ask the user whether to create a new project or work on an existing one.

    Returns:
        ("new", None) for a brand-new project, or
        ("existing", project_dir) when the user picks an existing one.
    """
    existing = _list_existing_projects()

    if not existing:
        return "new", None

    print("\nWould you like to:")
    print("  [1] Create a NEW project")
    print("  [2] Apply changes to an EXISTING project\n")

    while True:
        choice = input("Choose [1/2]: ").strip()
        if choice == "1":
            return "new", None
        if choice == "2":
            break
        print("Please enter 1 or 2.")

    print("\nExisting projects:")
    for idx, proj in enumerate(existing, 1):
        file_count = sum(1 for _ in proj.rglob("*") if _.is_file())
        print(f"  [{idx}] {proj.name}  ({file_count} files)")

    while True:
        pick = input(f"\nSelect project [1-{len(existing)}]: ").strip()
        if pick.isdigit() and 1 <= int(pick) <= len(existing):
            return "existing", existing[int(pick) - 1]
        print(f"Please enter a number between 1 and {len(existing)}.")


def _summarize_text(text: str, max_lines: int = 10) -> str:
    """Extract the first meaningful lines from a document for a compact preview."""
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("```"):
            continue
        if stripped.startswith("#"):
            lines.append(stripped)
        elif stripped.startswith("-") or stripped.startswith("*") or stripped.startswith("|"):
            lines.append(stripped)
        elif any(stripped.startswith(f"{i}.") for i in range(1, 20)):
            lines.append(stripped)
        else:
            lines.append(stripped)
        if len(lines) >= max_lines:
            break
    if len(text.splitlines()) > max_lines:
        lines.append(f"  ... ({len(text.splitlines())} lines total — press [v] to view full)")
    return "\n".join(lines)


def _run_until_interrupt(graph, config: dict, inputs: dict | None) -> dict | None:
    """Stream graph execution until an interrupt or completion.

    Agents print their own real-time progress (tool calls, spinners, timing).
    This loop only watches for interrupts and tracks state.
    """
    last_state = None
    for event in graph.stream(inputs, config=config, stream_mode="updates"):
        for node_name, update in event.items():
            if node_name == "__interrupt__":
                continue
        last_state = graph.get_state(config)
    return last_state


def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not set. Copy .env.example to .env and add your key.")
        sys.exit(1)

    print(BANNER)

    print("Models:")
    for role in ["supervisor", "requirements", "system_design", "coding", "testing", "monitoring"]:
        role_env = os.environ.get(f"OPENAI_MODEL_{role.upper()}")
        global_env = os.environ.get("OPENAI_MODEL")
        builtin = AGENT_MODEL_DEFAULTS.get(role, "gpt-4o")
        effective = role_env or global_env or builtin
        source = "env (per-agent)" if role_env else ("env (global)" if global_env else "default")
        print(f"  {role:<16} → {effective:<12} ({source})")
    print()

    mode, existing_dir = _choose_project_mode()

    if mode == "existing":
        output_dir = existing_dir
        slug = existing_dir.name
        os.environ["ORCHESTRATOR_OUTPUT_DIR"] = str(output_dir)

        print(f"\nProject: {slug}")
        print(f"Path:    {output_dir.resolve()}")

        print("\nLoading existing project files...")
        existing_files = _load_project_files(output_dir)
        print(f"Loaded {len(existing_files)} files.\n")

        description = input("What would you like to do with this project?\n> ").strip()
        if not description or description.lower() in ("quit", "exit"):
            print("Goodbye.")
            return

        context = (
            f"I have an EXISTING project located at '{slug}'. "
            f"The project already contains these files:\n"
            + "\n".join(f"- {f}" for f in existing_files)
            + f"\n\nThe user's request: {description}"
        )

        initial_state = {
            "messages": [HumanMessage(content=context)],
            "requirements": "",
            "system_design": "",
            "code_files": existing_files,
            "test_results": "",
            "tests_passing": False,
            "monitoring_config": "",
            "original_prompt": description,
            "current_phase": "start",
            "iteration_count": 0,
        }

    else:
        description = input("Describe your project:\n> ").strip()
        if not description or description.lower() in ("quit", "exit"):
            print("Goodbye.")
            return

        print("\nGenerating project name...")
        slug = _generate_project_slug(description)
        output_dir = _unique_project_dir(slug)
        output_dir.mkdir(parents=True, exist_ok=True)

        os.environ["ORCHESTRATOR_OUTPUT_DIR"] = str(output_dir)

        print(f"Project: {slug}")
        print(f"Output:  {output_dir.resolve()}\n")

        initial_state = {
            "messages": [HumanMessage(content=description)],
            "requirements": "",
            "system_design": "",
            "code_files": {},
            "test_results": "",
            "tests_passing": False,
            "monitoring_config": "",
            "original_prompt": description,
            "current_phase": "start",
            "iteration_count": 0,
        }

    checkpointer = MemorySaver()
    thread_id = f"session-{slug}"
    compiled = build_graph(checkpointer=checkpointer, interrupt_before=["coding"])
    config = {"configurable": {"thread_id": thread_id}}

    print("Starting orchestrator...\n")

    state = _run_until_interrupt(compiled, config, initial_state)

    while state and state.next:
        interrupted_at = state.next
        snapshot = state.values if hasattr(state, "values") else {}

        requirements = snapshot.get("requirements", "")
        system_design = snapshot.get("system_design", "")

        print(f"\n{'=' * 60}")
        print(f"⏸  Paused before coding — review the design")
        print(f"{'=' * 60}")

        if requirements:
            summary = _summarize_text(requirements, max_lines=8)
            print(f"\n  REQUIREMENTS (summary):")
            for line in summary.splitlines():
                print(f"    {line}")

        if system_design:
            summary = _summarize_text(system_design, max_lines=12)
            print(f"\n  SYSTEM DESIGN (summary):")
            for line in summary.splitlines():
                print(f"    {line}")

        if not requirements and not system_design:
            print("\n  (No design artifacts produced yet.)")

        print(f"\n{'─' * 60}")
        print("  [c] Continue to coding")
        print("  [f] Provide feedback (re-runs design with your notes)")
        print("  [v] View full design")
        print("  [q] Quit")
        print(f"{'─' * 60}")

        while True:
            choice = input("\n> ").strip().lower()
            if choice in ("c", "continue"):
                state = _run_until_interrupt(compiled, config, None)
                break
            elif choice in ("v", "view"):
                if requirements:
                    print(f"\n┌{'─' * 58}┐")
                    print(f"│ {'REQUIREMENTS':^56} │")
                    print(f"└{'─' * 58}┘")
                    print(requirements)
                if system_design:
                    print(f"\n┌{'─' * 58}┐")
                    print(f"│ {'SYSTEM DESIGN (ERD)':^56} │")
                    print(f"└{'─' * 58}┘")
                    print(system_design)
                print(f"\n{'─' * 60}")
                print("  [c] Continue  [f] Feedback  [q] Quit")
                print(f"{'─' * 60}")
            elif choice in ("f", "feedback"):
                feedback = input("Your feedback:\n> ").strip()
                if feedback:
                    compiled.update_state(
                        config,
                        {"messages": [HumanMessage(content=feedback)]},
                    )
                state = _run_until_interrupt(compiled, config, None)
                break
            elif choice in ("q", "quit"):
                print("Stopped by user.")
                return
            else:
                print("Invalid choice. Try c, f, v, or q.")

    print("\n" + "=" * 60)
    print(f"Orchestration complete: {slug}")
    print(f"Output files are in: {output_dir.resolve()}")
    print("=" * 60)


if __name__ == "__main__":
    main()
