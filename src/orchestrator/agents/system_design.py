"""System design agent — transforms requirements into architecture and API contracts."""

from __future__ import annotations

import time

from langchain_core.messages import AIMessage, SystemMessage

from src.orchestrator.llm import get_model, invoke_with_retry
from src.orchestrator.progress import Spinner, log_agent_done, log_agent_start, log_llm_done
from src.orchestrator.prompts.templates import SYSTEM_DESIGN_SYSTEM_PROMPT
from src.orchestrator.state import OrchestratorState


def system_design_agent(state: OrchestratorState) -> dict:
    """Produce a system design document from the gathered requirements."""
    t0 = time.time()
    log_agent_start("system_design")

    model = get_model(temperature=0.2, agent_role="system_design")

    prompt = SYSTEM_DESIGN_SYSTEM_PROMPT.format(
        requirements=state.get("requirements", "(no requirements yet)"),
    )

    messages = [SystemMessage(content=prompt)] + state["messages"]

    spinner = Spinner("Designing architecture (ERD)")
    spinner.start()
    llm_t0 = time.time()
    response: AIMessage = invoke_with_retry(model, messages)
    spinner.stop()
    log_llm_done("system_design", time.time() - llm_t0)

    log_agent_done("system_design", time.time() - t0)

    return {
        "messages": [response],
        "system_design": response.content,
        "current_phase": "system_design",
    }
