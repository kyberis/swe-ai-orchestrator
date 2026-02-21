"""Monitoring agent — produces observability and alerting configuration."""

from __future__ import annotations

import time

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from src.orchestrator.llm import get_model, invoke_with_retry
from src.orchestrator.progress import (
    Spinner,
    log_agent_done,
    log_agent_start,
    log_llm_done,
    log_llm_start,
    log_tool_call,
)
from src.orchestrator.prompts.templates import MONITORING_SYSTEM_PROMPT
from src.orchestrator.state import OrchestratorState
from src.orchestrator.tools.file_tools import write_file, read_file, list_files

MONITORING_TOOLS = [write_file, read_file, list_files]


def _summarize_code_files(code_files: dict[str, str]) -> str:
    if not code_files:
        return "(no code files)"
    return "\n".join(f"- {fname}" for fname in code_files)


def monitoring_agent(state: OrchestratorState) -> dict:
    """Generate monitoring, logging, and alerting configuration files."""
    t0 = time.time()
    log_agent_start("monitoring")

    model = get_model(temperature=0.2, tools=MONITORING_TOOLS, agent_role="monitoring")

    code_files = state.get("code_files", {})
    prompt = MONITORING_SYSTEM_PROMPT.format(
        system_design=state.get("system_design", "(no design)"),
        code_files_summary=_summarize_code_files(code_files),
    )

    messages = [SystemMessage(content=prompt)] + state["messages"]

    spinner = Spinner("Generating monitoring config")
    spinner.start()
    llm_t0 = time.time()
    response: AIMessage = invoke_with_retry(model, messages)
    spinner.stop()
    log_llm_done("monitoring", time.time() - llm_t0)

    result_messages = [response]
    files_written = 0
    iteration = 0

    while response.tool_calls:
        iteration += 1
        tool_results = []
        tool_map = {t.name: t for t in MONITORING_TOOLS}
        for call in response.tool_calls:
            tool_fn = tool_map.get(call["name"])
            if tool_fn is None:
                continue
            log_tool_call(call["name"], call["args"])
            tool_result = tool_fn.invoke(call["args"])
            if call["name"] == "write_file":
                files_written += 1
            tool_results.append(
                ToolMessage(content=str(tool_result), tool_call_id=call["id"])
            )
        result_messages.extend(tool_results)

        log_llm_start("monitoring", iteration)
        llm_t0 = time.time()
        response = invoke_with_retry(model, messages + result_messages)
        log_llm_done("monitoring", time.time() - llm_t0)
        result_messages.append(response)

    log_agent_done("monitoring", time.time() - t0, file_count=files_written)

    return {
        "messages": result_messages,
        "monitoring_config": response.content,
        "current_phase": "monitoring",
    }
