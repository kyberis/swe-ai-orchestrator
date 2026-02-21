"""LangGraph graph assembly with supervisor routing and conditional edges."""

from __future__ import annotations

import json
import os
import time

from langchain_core.messages import AIMessage, SystemMessage
from langgraph.graph import END, StateGraph

from src.orchestrator.agents.coding import coding_agent
from src.orchestrator.agents.monitoring import monitoring_agent
from src.orchestrator.agents.requirements import requirements_agent
from src.orchestrator.agents.system_design import system_design_agent
from src.orchestrator.agents.testing import testing_agent
from src.orchestrator.llm import get_model, invoke_with_retry
from src.orchestrator.progress import log_llm_done
from src.orchestrator.prompts.templates import SUPERVISOR_SYSTEM_PROMPT
from src.orchestrator.state import OrchestratorState

AGENT_NODES = {
    "requirements": requirements_agent,
    "system_design": system_design_agent,
    "coding": coding_agent,
    "testing": testing_agent,
    "monitoring": monitoring_agent,
}

VALID_ROUTES = list(AGENT_NODES.keys()) + ["FINISH"]

MAX_ITERATIONS = int(os.environ.get("MAX_ITERATIONS", "12"))


def supervisor(state: OrchestratorState) -> dict:
    """LLM-powered router that decides which agent to call next."""
    model = get_model(temperature=0.0, agent_role="supervisor")

    iteration_count = state.get("iteration_count", 0)
    tests_passing = state.get("tests_passing", False)
    has_requirements = bool(state.get("requirements"))
    has_design = bool(state.get("system_design"))
    has_code = bool(state.get("code_files"))
    has_tests = bool(state.get("test_results"))
    has_monitoring = bool(state.get("monitoring_config"))

    def _check(done: bool) -> str:
        return "x" if done else " "

    checklist = (
        f"  [{_check(has_requirements)}] Requirements\n"
        f"  [{_check(has_design)}] System Design\n"
        f"  [{_check(has_code)}] Code (backend + frontend)\n"
        f"  [{_check(tests_passing)}] Tests passing\n"
        f"  [{_check(has_monitoring)}] Monitoring"
    )

    prompt = SUPERVISOR_SYSTEM_PROMPT.format(
        current_phase=state.get("current_phase", "start"),
        iteration_count=iteration_count,
        max_iterations=MAX_ITERATIONS,
        has_requirements=has_requirements,
        has_design=has_design,
        has_code=has_code,
        has_tests=has_tests,
        tests_passing=tests_passing,
        has_monitoring=has_monitoring,
        checklist=checklist,
    )

    messages = [SystemMessage(content=prompt)] + state["messages"]

    llm_t0 = time.time()
    response: AIMessage = invoke_with_retry(model, messages)
    log_llm_done("supervisor", time.time() - llm_t0)

    try:
        decision = json.loads(response.content)
        next_agent = decision.get("next", "FINISH")
        reason = decision.get("reason", "")
    except (json.JSONDecodeError, AttributeError):
        content = response.content if isinstance(response.content, str) else str(response.content)
        for route in VALID_ROUTES:
            if route.lower() in content.lower():
                next_agent = route
                reason = content
                break
        else:
            next_agent = "FINISH"
            reason = "Could not parse routing decision; finishing."

    if next_agent not in VALID_ROUTES:
        next_agent = "FINISH"
        reason = f"Unknown route '{next_agent}'; finishing."

    if next_agent == "FINISH" and iteration_count < MAX_ITERATIONS:
        all_done = (
            has_requirements and has_design and has_code
            and tests_passing and has_monitoring
        )
        if not all_done:
            missing = []
            if not has_requirements:
                missing.append("requirements")
            if not has_design:
                missing.append("system_design")
            if not has_code:
                missing.append("coding")
            if not tests_passing:
                missing.append("testing (tests not passing)")
            if not has_monitoring:
                missing.append("monitoring")

            next_agent = missing[0].split(" ")[0]
            if next_agent == "testing":
                next_agent = "coding" if has_code else "coding"
            reason = f"Cannot finish yet — incomplete phases: {', '.join(missing)}. Routing to {next_agent}."

    if iteration_count >= MAX_ITERATIONS and next_agent != "FINISH":
        reason = f"Max iterations ({MAX_ITERATIONS}) reached; forcing FINISH."
        next_agent = "FINISH"

    _CYAN = "\033[36m"
    _GREY = "\033[90m"
    _RESET = "\033[0m"
    _BOLD = "\033[1m"
    step = iteration_count + 1
    print(f"\n{_CYAN}▸ Supervisor [{step}/{MAX_ITERATIONS}]:{_RESET} {_BOLD}{next_agent}{_RESET}")
    print(f"  {_GREY}{reason}{_RESET}")

    return {
        "messages": [
            AIMessage(
                content=f"[Supervisor] Routing to **{next_agent}**: {reason}",
                name="supervisor",
            )
        ],
        "current_phase": next_agent if next_agent != "FINISH" else "finished",
        "iteration_count": iteration_count + 1,
    }


def route_after_supervisor(state: OrchestratorState) -> str:
    """Conditional edge: read the phase the supervisor just set and route there."""
    phase = state.get("current_phase", "finished")
    if phase in AGENT_NODES:
        return phase
    return "FINISH"


def build_graph(*, checkpointer=None, interrupt_before: list[str] | None = None):
    """Construct and compile the orchestrator graph.

    Args:
        checkpointer: Optional LangGraph checkpointer for persistence / human-in-the-loop.
        interrupt_before: List of node names to pause before (enables human review).
                          Defaults to ["coding"] so the engineer can review the design.

    Returns:
        A compiled LangGraph that can be invoked or streamed.
    """
    if interrupt_before is None:
        interrupt_before = ["coding"]

    graph = StateGraph(OrchestratorState)

    graph.add_node("supervisor", supervisor)
    for name, fn in AGENT_NODES.items():
        graph.add_node(name, fn)

    graph.set_entry_point("supervisor")

    graph.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {
            "requirements": "requirements",
            "system_design": "system_design",
            "coding": "coding",
            "testing": "testing",
            "monitoring": "monitoring",
            "FINISH": END,
        },
    )

    for name in AGENT_NODES:
        graph.add_edge(name, "supervisor")

    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_before,
    )
