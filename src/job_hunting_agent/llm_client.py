"""One guarded path for every LLM call (ATS writing review, interview review, MCQs).

Guardrails applied to every call:

- Spend caps: a daily budget for the whole deployment and a smaller one per
  user (``JOB_AGENT_LLM_DAILY_BUDGET_USD``, ``JOB_AGENT_LLM_USER_DAILY_BUDGET_USD``),
  plus a token cap per agent run (``JOB_AGENT_LLM_RUN_TOKEN_BUDGET``). When a
  cap is reached the call is skipped and the caller uses its local evaluator.
- Untrusted text (job descriptions, resumes, answers) is wrapped in DATA
  blocks with a policy that it is never to be followed as instructions.
- Protected attributes are removed from resume text before it is sent.
- Structured JSON output is required; anything that does not parse is dropped.
- Usage and latency are recorded for metrics; prompts and keys are never logged.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import time
from typing import Any

import requests

from . import http_client, ops_db
from .guardrails import DATA_POLICY, data_block

logger = logging.getLogger(__name__)

# Tokens still available to the current agent run (None = no run-level cap set).
RUN_TOKEN_BUDGET: contextvars.ContextVar[list[int] | None] = contextvars.ContextVar("job_agent_llm_run_budget", default=None)
CURRENT_USER: contextvars.ContextVar[str] = contextvars.ContextVar("job_agent_llm_user", default="")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def start_run_budget(user_email: str = "") -> None:
    """Give the current context (one agent run) its own token allowance."""
    RUN_TOKEN_BUDGET.set([int(_env_float("JOB_AGENT_LLM_RUN_TOKEN_BUDGET", 24000))])
    CURRENT_USER.set(user_email or "")


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    price_in = _env_float("JOB_AGENT_LLM_PRICE_INPUT_PER_1M", 0.15)
    price_out = _env_float("JOB_AGENT_LLM_PRICE_OUTPUT_PER_1M", 0.60)
    return round(input_tokens * price_in / 1_000_000 + output_tokens * price_out / 1_000_000, 6)


def budget_state(user_email: str = "") -> dict[str, Any]:
    daily_cap = _env_float("JOB_AGENT_LLM_DAILY_BUDGET_USD", 5.0)
    user_cap = _env_float("JOB_AGENT_LLM_USER_DAILY_BUDGET_USD", 0.25)
    try:
        spent = ops_db.llm_spend()
        user_spent = ops_db.llm_spend(user_email=user_email) if user_email else 0.0
    except Exception:  # metrics storage must never break a feature
        spent = user_spent = 0.0
    return {
        "daily_cap_usd": daily_cap, "daily_spent_usd": round(spent, 4),
        "user_cap_usd": user_cap, "user_spent_usd": round(user_spent, 4),
        "allowed": spent < daily_cap and (not user_email or user_spent < user_cap),
    }


def _key(names: tuple[str, ...]) -> str:
    return next((os.getenv(name, "").strip() for name in names if os.getenv(name, "").strip()), "")


def enabled(key_envs: tuple[str, ...] = ("JOB_AGENT_LLM_API_KEY",)) -> bool:
    return bool(_key(key_envs)) and os.getenv("JOB_AGENT_LLM", "on").strip().lower() not in {"off", "false", "0"}


def call_json(
    feature: str,
    *,
    instructions: str,
    data: dict[str, str],
    schema: dict[str, Any],
    schema_name: str,
    key_envs: tuple[str, ...] = ("JOB_AGENT_LLM_API_KEY",),
    endpoint_envs: tuple[str, ...] = ("JOB_AGENT_LLM_ENDPOINT",),
    model_envs: tuple[str, ...] = ("JOB_AGENT_LLM_MODEL",),
    max_output_tokens: int = 1200,
    timeout: float | tuple[float, float] = 25,
    user_email: str = "",
    max_chars_per_block: int = 16000,
) -> dict[str, Any] | None:
    """Run one structured-output call; ``None`` means "use the local fallback"."""
    api_key = _key(key_envs)
    if not api_key or os.getenv("JOB_AGENT_LLM", "on").strip().lower() in {"off", "false", "0"}:
        return None
    user_email = user_email or CURRENT_USER.get()
    endpoint = _key(endpoint_envs) or "https://api.openai.com/v1/responses"
    model = _key(model_envs) or "gpt-4o-mini"
    prompt = "\n\n".join([instructions.strip(), DATA_POLICY, *(data_block(label, text, max_chars_per_block) for label, text in data.items())])
    estimated_in = estimate_tokens(prompt)
    budget = budget_state(user_email)
    run_budget = RUN_TOKEN_BUDGET.get()
    if not budget["allowed"]:
        _emit(feature, "skipped_budget", user_email)
        return None
    if run_budget is not None and run_budget[0] < estimated_in + max_output_tokens:
        _emit(feature, "skipped_run_budget", user_email)
        return None
    started = time.monotonic()
    input_tokens, output_tokens, ok = estimated_in, 0, False
    try:
        response = http_client.post(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "store": False,
                "input": prompt,
                "max_output_tokens": int(max_output_tokens),
                "text": {"format": {"type": "json_schema", "name": schema_name, "strict": True, "schema": schema}},
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        usage = payload.get("usage") or {}
        input_tokens = int(usage.get("input_tokens") or estimated_in)
        output_text = payload.get("output_text") or next(
            (
                content.get("text", "")
                for item in payload.get("output", []) or []
                for content in item.get("content", []) or []
                if content.get("type") == "output_text"
            ),
            "",
        )
        output_tokens = int(usage.get("output_tokens") or estimate_tokens(output_text or ""))
        parsed = json.loads(output_text)
        ok = isinstance(parsed, dict)
        return parsed if ok else None
    except (requests.RequestException, KeyError, TypeError, ValueError, json.JSONDecodeError, AttributeError) as exc:
        # Type only: request exceptions can include URLs and headers.
        logger.info("LLM call for %s failed (%s)", feature, type(exc).__name__)
        return None
    finally:
        latency_ms = round((time.monotonic() - started) * 1000)
        if run_budget is not None:
            run_budget[0] -= input_tokens + output_tokens
        cost = cost_usd(input_tokens, output_tokens)
        try:
            ops_db.record_llm_usage(feature, user_email=user_email, input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost, ok=ok)
        except Exception:
            pass
        _emit(feature, "ok" if ok else "failed", user_email, latency_ms=latency_ms, tokens=input_tokens + output_tokens, cost_usd=cost)


def _emit(feature: str, outcome: str, user_email: str, **values: Any) -> None:
    from .metrics import emit

    emit("llm_call", user_email=user_email, persist=False, feature=feature, outcome=outcome, **values)
