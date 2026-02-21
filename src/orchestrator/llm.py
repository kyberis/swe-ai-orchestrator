"""Shared LLM factory with automatic retry on rate-limit errors.

Model selection per agent role:
- Coding & System Design use the strongest coding model (default: o4-mini).
- Supervisor, Requirements, Testing, Monitoring use a general-purpose model (default: gpt-4o).
- Every model is overridable via environment variables.
"""

from __future__ import annotations

import os
import time

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI


MAX_RETRIES = 5
INITIAL_BACKOFF = 2.0

AGENT_MODEL_DEFAULTS = {
    "supervisor": "gpt-4o",
    "requirements": "gpt-4o",
    "system_design": "o4-mini",
    "coding": "o4-mini",
    "testing": "gpt-4o",
    "monitoring": "gpt-4o",
    "default": "gpt-4o",
}


def get_model(
    temperature: float = 0.0,
    tools: list | None = None,
    agent_role: str | None = None,
) -> ChatOpenAI:
    """Create a ChatOpenAI instance with the best model for the given agent role.

    Model resolution order:
    1. OPENAI_MODEL_<ROLE> env var  (e.g. OPENAI_MODEL_CODING=o3)
    2. OPENAI_MODEL env var         (global override for all agents)
    3. Built-in per-role default    (o4-mini for coding/design, gpt-4o otherwise)
    """
    role = (agent_role or "default").lower()

    role_env = os.environ.get(f"OPENAI_MODEL_{role.upper()}")
    global_env = os.environ.get("OPENAI_MODEL")
    builtin = AGENT_MODEL_DEFAULTS.get(role, AGENT_MODEL_DEFAULTS["default"])

    model_name = role_env or global_env or builtin

    is_reasoning = any(model_name.startswith(p) for p in ("o1", "o3", "o4"))
    kwargs = {"model": model_name}
    if not is_reasoning:
        kwargs["temperature"] = temperature

    model = ChatOpenAI(**kwargs)
    if tools:
        model = model.bind_tools(tools)
    return model


def invoke_with_retry(model, messages: list[BaseMessage], **kwargs):
    """Invoke the model with exponential backoff on rate-limit (429) errors."""
    backoff = INITIAL_BACKOFF
    for attempt in range(MAX_RETRIES):
        try:
            return model.invoke(messages, **kwargs)
        except Exception as e:
            error_str = str(e)
            is_rate_limit = "429" in error_str or "rate_limit" in error_str.lower()
            if is_rate_limit and attempt < MAX_RETRIES - 1:
                wait = backoff * (2 ** attempt)
                print(f"  [Rate limit hit, waiting {wait:.0f}s before retry {attempt + 2}/{MAX_RETRIES}...]")
                time.sleep(wait)
            else:
                raise
