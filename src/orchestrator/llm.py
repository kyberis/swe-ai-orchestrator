"""Shared LLM factory with automatic retry on transient errors.

Model selection per agent role:
- Coding & System Design use the strongest coding model (default: o4-mini).
- Supervisor, Requirements, Testing, Monitoring use a general-purpose model (default: gpt-4o).
- Every model is overridable via environment variables.

Retries cover: rate-limit (429), connection/SSL errors, server errors (500/502/503).
"""

from __future__ import annotations

import os
import time

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI


MAX_RETRIES = 7
INITIAL_BACKOFF = 2.0

_RETRYABLE_PATTERNS = [
    "429",
    "rate_limit",
    "rate limit",
    "connection error",
    "connecterror",
    "ssl",
    "eof occurred",
    "unexpected_eof",
    "timeout",
    "timed out",
    "server_error",
    "500",
    "502",
    "503",
    "overloaded",
    "bad gateway",
    "service unavailable",
]

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


def _is_retryable(exc: Exception) -> str | None:
    """Return a short label if the exception is transient and worth retrying."""
    error_str = str(exc).lower()
    cls_name = type(exc).__name__.lower()
    combined = f"{cls_name} {error_str}"
    for pattern in _RETRYABLE_PATTERNS:
        if pattern in combined:
            if "429" in pattern or "rate" in pattern:
                return "rate limit"
            if "ssl" in pattern or "eof" in pattern or "connect" in pattern:
                return "connection error"
            if "timeout" in pattern or "timed" in pattern:
                return "timeout"
            return "server error"
    return None


def invoke_with_retry(model, messages: list[BaseMessage], **kwargs):
    """Invoke the model with exponential backoff on transient errors.

    Retries on: rate limits (429), SSL/connection drops, timeouts, and 5xx server errors.
    """
    backoff = INITIAL_BACKOFF
    for attempt in range(MAX_RETRIES):
        try:
            return model.invoke(messages, **kwargs)
        except Exception as e:
            label = _is_retryable(e)
            if label and attempt < MAX_RETRIES - 1:
                wait = backoff * (2 ** attempt)
                print(
                    f"  ⚠ {label} (attempt {attempt + 1}/{MAX_RETRIES}), "
                    f"retrying in {wait:.0f}s..."
                )
                time.sleep(wait)
            else:
                raise
