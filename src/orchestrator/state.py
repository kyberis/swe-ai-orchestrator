from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class OrchestratorState(TypedDict):
    """Shared state that flows through every node in the orchestrator graph."""

    messages: Annotated[list[BaseMessage], add_messages]

    requirements: str
    system_design: str
    code_files: dict[str, str]
    test_results: str
    tests_passing: bool
    monitoring_config: str

    original_prompt: str

    current_phase: str
    iteration_count: int
