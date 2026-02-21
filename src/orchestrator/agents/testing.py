"""Testing agent — writes and runs tests against the generated code."""

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
from src.orchestrator.prompts.templates import TESTING_SYSTEM_PROMPT
from src.orchestrator.state import OrchestratorState
from src.orchestrator.tools.file_tools import write_file, read_file, list_files
from src.orchestrator.tools.test_tools import run_tests, run_command

TESTING_TOOLS = [write_file, read_file, list_files, run_tests, run_command]

FAILURE_KEYWORDS = ["FAILED", "ERROR", "FAILURE", "AssertionError", "Exception"]


def _summarize_code_files(code_files: dict[str, str]) -> str:
    if not code_files:
        return "(no code files)"
    lines = []
    for fname, content in code_files.items():
        preview = content[:500] + "..." if len(content) > 500 else content
        lines.append(f"### {fname}\n```\n{preview}\n```")
    return "\n\n".join(lines)


def _detect_passing(test_output: str) -> bool:
    upper = test_output.upper()
    for kw in FAILURE_KEYWORDS:
        if kw.upper() in upper:
            return False
    return True


def testing_agent(state: OrchestratorState) -> dict:
    """Write test files and execute them, reporting results."""
    t0 = time.time()
    log_agent_start("testing")

    model = get_model(temperature=0.0, tools=TESTING_TOOLS, agent_role="testing")

    code_files = state.get("code_files", {})
    prompt = TESTING_SYSTEM_PROMPT.format(
        system_design=state.get("system_design", "(no design)"),
        code_files_summary=_summarize_code_files(code_files),
    )

    messages = [SystemMessage(content=prompt)] + state["messages"]

    spinner = Spinner("Validating & writing tests")
    spinner.start()
    llm_t0 = time.time()
    response: AIMessage = invoke_with_retry(model, messages)
    spinner.stop()
    log_llm_done("testing", time.time() - llm_t0)

    result_messages = [response]
    all_tool_outputs: list[str] = []
    files_written = 0
    iteration = 0

    while response.tool_calls:
        iteration += 1
        tool_results = []
        tool_map = {t.name: t for t in TESTING_TOOLS}
        for call in response.tool_calls:
            tool_fn = tool_map.get(call["name"])
            if tool_fn is None:
                continue
            log_tool_call(call["name"], call["args"])
            tool_result = tool_fn.invoke(call["args"])
            result_str = str(tool_result)
            all_tool_outputs.append(result_str)
            if call["name"] == "write_file":
                files_written += 1
            tool_results.append(
                ToolMessage(content=result_str, tool_call_id=call["id"])
            )
        result_messages.extend(tool_results)

        log_llm_start("testing", iteration)
        llm_t0 = time.time()
        response = invoke_with_retry(model, messages + result_messages)
        log_llm_done("testing", time.time() - llm_t0)
        result_messages.append(response)

    test_output = response.content if isinstance(response.content, str) else str(response.content)

    combined_output = test_output + "\n".join(all_tool_outputs)
    tests_passing = _detect_passing(combined_output)

    status = "PASSING" if tests_passing else "FAILING"
    log_agent_done("testing", time.time() - t0, file_count=files_written)
    print(f"  Tests: {status}")

    return {
        "messages": result_messages,
        "test_results": test_output,
        "tests_passing": tests_passing,
        "current_phase": "testing",
    }
