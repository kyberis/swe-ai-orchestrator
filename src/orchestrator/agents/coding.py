"""Coding agent — generates implementation files based on the system design."""

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
from src.orchestrator.prompts.templates import CODING_SYSTEM_PROMPT
from src.orchestrator.state import OrchestratorState
from src.orchestrator.tools.file_tools import list_files, read_file, write_file


CODING_TOOLS = [write_file, read_file, list_files]


def coding_agent(state: OrchestratorState) -> dict:
    """Generate code files based on the system design, using file tools."""
    t0 = time.time()
    log_agent_start("coding")

    model = get_model(temperature=0.0, tools=CODING_TOOLS, agent_role="coding")

    test_failure_context = ""
    test_results = state.get("test_results", "")
    if test_results and "FAILED" in test_results.upper():
        test_failure_context = f"Previous test failures:\n{test_results}"

    prompt = CODING_SYSTEM_PROMPT.format(
        system_design=state.get("system_design", "(no design yet)"),
        test_failure_context=test_failure_context or "N/A — first pass.",
        original_prompt=state.get("original_prompt", "(not available)"),
    )

    messages = [SystemMessage(content=prompt)] + state["messages"]

    spinner = Spinner("Generating code")
    spinner.start()
    llm_t0 = time.time()
    response: AIMessage = invoke_with_retry(model, messages)
    spinner.stop()
    log_llm_done("coding", time.time() - llm_t0)

    result_messages = [response]
    code_files = dict(state.get("code_files", {}))
    files_written = 0
    iteration = 0

    while response.tool_calls:
        iteration += 1
        tool_results = []
        tool_map = {t.name: t for t in CODING_TOOLS}
        for call in response.tool_calls:
            tool_fn = tool_map.get(call["name"])
            if tool_fn is None:
                continue
            log_tool_call(call["name"], call["args"])
            tool_result = tool_fn.invoke(call["args"])
            if call["name"] == "write_file":
                filename = call["args"].get("filename", "")
                content = call["args"].get("content", "")
                code_files[filename] = content
                files_written += 1
            tool_results.append(
                ToolMessage(content=str(tool_result), tool_call_id=call["id"])
            )
        result_messages.extend(tool_results)

        log_llm_start("coding", iteration)
        llm_t0 = time.time()
        response = invoke_with_retry(model, messages + result_messages)
        log_llm_done("coding", time.time() - llm_t0)
        result_messages.append(response)

    log_agent_done("coding", time.time() - t0, file_count=files_written)

    return {
        "messages": result_messages,
        "code_files": code_files,
        "current_phase": "coding",
    }
