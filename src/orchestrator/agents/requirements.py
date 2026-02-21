"""Requirements gathering agent — extracts and structures project requirements."""

from __future__ import annotations

import time

from langchain_core.messages import AIMessage, SystemMessage

from src.orchestrator.llm import get_model, invoke_with_retry
from src.orchestrator.progress import Spinner, log_agent_done, log_agent_start, log_llm_done
from src.orchestrator.prompts.templates import REQUIREMENTS_SYSTEM_PROMPT
from src.orchestrator.state import OrchestratorState


def requirements_agent(state: OrchestratorState) -> dict:
    """Analyze the conversation so far and produce structured requirements."""
    t0 = time.time()
    log_agent_start("requirements")

    model = get_model(temperature=0.2, agent_role="requirements")
    messages = [SystemMessage(content=REQUIREMENTS_SYSTEM_PROMPT)] + state["messages"]

    spinner = Spinner("Analyzing requirements")
    spinner.start()
    llm_t0 = time.time()
    response: AIMessage = invoke_with_retry(model, messages)
    spinner.stop()
    log_llm_done("requirements", time.time() - llm_t0)

    log_agent_done("requirements", time.time() - t0)

    return {
        "messages": [response],
        "requirements": response.content,
        "current_phase": "requirements",
    }
