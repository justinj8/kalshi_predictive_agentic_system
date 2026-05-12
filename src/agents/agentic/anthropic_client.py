"""Shared Anthropic SDK wrapper for the agentic core.

Centralizes:
  - SDK client instantiation
  - Prompt caching on system prompts and tool definitions
  - Tool-use loop with bounded iterations
  - Forced "final tool" enforcement (e.g. emit_trading_signal, submit_evidence)
  - Retry with exponential backoff on transient errors
  - Token / tool-call telemetry

Designed so every agent (Research, Bull/Bear/RedTeam, Judge, Calibration,
Reflection, Scout) talks to Claude through one path.
"""
from __future__ import annotations

import time
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from anthropic import Anthropic
from anthropic import APIError, APIStatusError, APIConnectionError, RateLimitError

from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Single shared SDK client. The Anthropic SDK is thread-safe for read-only use,
# and our orchestrator dispatches debate agents via asyncio.gather to_thread.
_client: Optional[Anthropic] = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=settings.anthropic_api_key)
    return _client


# Anthropic's built-in web search server tool. Available in current SDKs;
# served entirely server-side, no client-side tool implementation needed.
WEB_SEARCH_TOOL: Dict[str, Any] = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 5,
}


@dataclass
class ToolCallRecord:
    name: str
    input: Dict[str, Any]
    output: Any
    duration_s: float
    error: Optional[str] = None


@dataclass
class AgentRunResult:
    """Telemetry + final output of one agent invocation."""
    text: str = ""
    final_tool_use: Optional[Dict[str, Any]] = None
    all_tool_uses: List[Dict[str, Any]] = field(default_factory=list)
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    iterations: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    thinking_tokens: int = 0
    stop_reason: Optional[str] = None
    truncated: bool = False  # True if loop hit max_iterations before final tool


def _is_retriable(exc: BaseException) -> bool:
    if isinstance(exc, (APIConnectionError, RateLimitError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in (408, 425, 429, 500, 502, 503, 504)
    return False


def _create_with_retry(client: Anthropic, max_retries: int = 4, **kwargs) -> Any:
    """SDK call with exponential backoff on transient errors."""
    last_exc: Optional[BaseException] = None
    for attempt in range(max_retries + 1):
        try:
            return client.messages.create(**kwargs)
        except (APIError, APIConnectionError, RateLimitError) as exc:
            last_exc = exc
            if attempt >= max_retries or not _is_retriable(exc):
                raise
            delay = (2 ** attempt) + random.uniform(0, 0.5)
            logger.warning(
                f"Anthropic API error (attempt {attempt + 1}/{max_retries + 1}): "
                f"{type(exc).__name__}: {exc}. Retrying in {delay:.1f}s"
            )
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc


def _extract_text_blocks(content: List[Any]) -> str:
    out: List[str] = []
    for block in content:
        btype = getattr(block, "type", None) or (
            block.get("type") if isinstance(block, dict) else None
        )
        if btype == "text":
            text = getattr(block, "text", None) or (
                block.get("text") if isinstance(block, dict) else ""
            )
            if text:
                out.append(text)
    return "\n".join(out).strip()


def _block_to_dict(block: Any) -> Dict[str, Any]:
    """Normalize SDK block (object or dict) to a plain dict for tool_use entries."""
    if isinstance(block, dict):
        return block
    btype = getattr(block, "type", None)
    if btype == "tool_use":
        return {
            "type": "tool_use",
            "id": getattr(block, "id", ""),
            "name": getattr(block, "name", ""),
            "input": getattr(block, "input", {}) or {},
        }
    if btype == "text":
        return {"type": "text", "text": getattr(block, "text", "")}
    if btype == "thinking":
        return {
            "type": "thinking",
            "thinking": getattr(block, "thinking", ""),
        }
    # Fallback - preserve unknown blocks verbatim.
    try:
        return dict(block.__dict__)
    except Exception:
        return {"type": btype or "unknown"}


def run_agent(
    *,
    model: str,
    system: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_executor: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
    final_tool_name: Optional[str] = None,
    max_tokens: int = 4096,
    max_iterations: int = 8,
    temperature: float = 0.7,
    thinking_budget_tokens: Optional[int] = None,
    cache_system: bool = True,
    cache_tools: bool = True,
    extra_headers: Optional[Dict[str, str]] = None,
) -> AgentRunResult:
    """Drive a multi-turn tool-use loop with one Claude agent.

    Args:
        model: Anthropic model id.
        system: System prompt (will be cached if cache_system).
        messages: Initial message list.
        tools: List of tool schemas (local + optional web_search). Cached if cache_tools.
        tool_executor: Callable(name, input) -> result dict. Required if tools includes
            client-side tools. Server tools like web_search are handled by Anthropic.
        final_tool_name: If set, the loop only terminates once Claude calls this tool.
            If max_iterations is hit before that, AgentRunResult.truncated is True.
        max_tokens: Per-call token budget.
        max_iterations: Hard cap on tool-use rounds.
        temperature: Sampling temperature.
        thinking_budget_tokens: If set, enables extended thinking with this budget.
        cache_system: Add cache_control to system prompt.
        cache_tools: Add cache_control to final tool definition.
        extra_headers: Additional headers (e.g. beta features).

    Returns:
        AgentRunResult with final assistant text, structured tool_use (if any),
        and telemetry.
    """
    client = get_client()

    # Build system parameter with prompt caching.
    if cache_system:
        system_param: Any = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]
    else:
        system_param = system

    tools_param: Optional[List[Dict[str, Any]]] = None
    if tools:
        tools_param = [dict(t) for t in tools]
        if cache_tools and tools_param:
            # Cache the last tool definition to cache the whole tools block.
            tools_param[-1] = {
                **tools_param[-1],
                "cache_control": {"type": "ephemeral"},
            }

    # Working message list (we append assistant turns + tool_results as we loop).
    working_messages: List[Dict[str, Any]] = [dict(m) for m in messages]

    result = AgentRunResult()

    for iteration in range(1, max_iterations + 1):
        result.iterations = iteration

        # On the LAST allowed iteration, if we have a required final tool and
        # haven't seen it yet, force Claude to call it via tool_choice.
        tool_choice: Optional[Dict[str, Any]] = None
        if (
            final_tool_name
            and tools_param
            and iteration == max_iterations
            and result.final_tool_use is None
        ):
            tool_choice = {"type": "tool", "name": final_tool_name}

        create_kwargs: Dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_param,
            "messages": working_messages,
        }
        if tools_param:
            create_kwargs["tools"] = tools_param
        if tool_choice:
            create_kwargs["tool_choice"] = tool_choice
        if thinking_budget_tokens and thinking_budget_tokens > 0:
            create_kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": thinking_budget_tokens,
            }
            # Extended thinking requires temperature=1.0
            create_kwargs["temperature"] = 1.0
        if extra_headers:
            create_kwargs["extra_headers"] = extra_headers

        response = _create_with_retry(client, **create_kwargs)

        # Accumulate token usage.
        usage = getattr(response, "usage", None)
        if usage is not None:
            result.input_tokens += getattr(usage, "input_tokens", 0) or 0
            result.output_tokens += getattr(usage, "output_tokens", 0) or 0
            result.cache_read_tokens += (
                getattr(usage, "cache_read_input_tokens", 0) or 0
            )
            result.cache_creation_tokens += (
                getattr(usage, "cache_creation_input_tokens", 0) or 0
            )

        # Collect tool_use blocks from the assistant turn.
        tool_use_blocks: List[Dict[str, Any]] = []
        assistant_blocks: List[Dict[str, Any]] = []
        for block in response.content:
            btype = getattr(block, "type", None)
            if btype == "thinking":
                thinking_text = getattr(block, "thinking", "") or ""
                result.thinking_tokens += max(0, len(thinking_text) // 4)
            if btype == "tool_use":
                tu = _block_to_dict(block)
                tool_use_blocks.append(tu)
                result.all_tool_uses.append(tu)
                if final_tool_name and tu.get("name") == final_tool_name:
                    result.final_tool_use = tu
            assistant_blocks.append(_block_to_dict(block))

        # Append the assistant message (raw blocks - includes any thinking/text/tool_use).
        working_messages.append({"role": "assistant", "content": assistant_blocks})

        result.text = _extract_text_blocks(response.content)
        result.stop_reason = getattr(response, "stop_reason", None)

        # Terminate if we got the required final tool.
        if final_tool_name and result.final_tool_use is not None:
            break

        # No tool calls -> Claude is done speaking. Terminate.
        if not tool_use_blocks:
            break

        # Otherwise: execute each local tool call and feed results back.
        tool_result_blocks: List[Dict[str, Any]] = []
        for tu in tool_use_blocks:
            tool_name = tu.get("name", "")
            tool_input = tu.get("input", {}) or {}
            tu_id = tu.get("id", "")

            # The "final" tool (e.g. submit_evidence, emit_trading_signal) does
            # not need execution — we capture it and break next loop.
            if final_tool_name and tool_name == final_tool_name:
                # Provide a benign acknowledgement so the conversation closes cleanly.
                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu_id,
                        "content": "Decision recorded.",
                    }
                )
                continue

            if tool_executor is None:
                err = f"No tool_executor configured; cannot run '{tool_name}'."
                logger.error(err)
                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu_id,
                        "content": err,
                        "is_error": True,
                    }
                )
                continue

            t0 = time.perf_counter()
            try:
                output = tool_executor(tool_name, tool_input)
                err_msg = None
            except Exception as exc:  # noqa: BLE001 - surface any error to the model
                logger.warning(f"Tool '{tool_name}' raised: {exc}", exc_info=True)
                output = {"ok": False, "error": str(exc)}
                err_msg = str(exc)
            dur = time.perf_counter() - t0

            result.tool_calls.append(
                ToolCallRecord(
                    name=tool_name,
                    input=tool_input,
                    output=output,
                    duration_s=dur,
                    error=err_msg,
                )
            )

            tool_result_blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu_id,
                    "content": _stringify_tool_output(output),
                    "is_error": bool(err_msg),
                }
            )

        working_messages.append({"role": "user", "content": tool_result_blocks})

    if final_tool_name and result.final_tool_use is None:
        result.truncated = True
        logger.warning(
            f"Agent loop exited without final tool '{final_tool_name}' "
            f"after {result.iterations} iterations."
        )

    return result


def _stringify_tool_output(output: Any) -> str:
    """Render tool output for the model. Compact JSON-ish string."""
    import json

    try:
        return json.dumps(output, default=str, ensure_ascii=False)
    except Exception:
        return str(output)
