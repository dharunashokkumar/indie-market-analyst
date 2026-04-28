"""Entry runtime. Wraps `Runner.run_streamed` and yields normalized events.

Consumers (api_server SSE, CLI REPL) iterate over ``run_turn`` and format the
events as they please.

Event kinds emitted:
    - ``delta``             — final-answer text chunk (goes in message bubble)
    - ``reasoning_delta``   — thinking-drawer text chunk (never shown as answer)
    - ``tool_call_start``   — tool invocation began; data: {call_id, name, arguments}
    - ``tool_call_end``     — tool result ready; data: {call_id, name, result, duration_ms}
    - ``handoff``           — one handoff per real transition; data: {to}
    - ``agent_updated``     — active agent switched; data: {name}
    - ``final``             — full markdown for persistence; data: {markdown, session_id}
    - ``error``             — fatal; data: str
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from agents import Runner

from ..guardrails.disclaimer import decorate
from ..memory.store import get_store
from ..session.manager import Session, get_session, new_session
from ..swarm.dispatcher import load_and_build
from .router import pick_team


@dataclass
class StreamEvent:
    kind: str
    data: Any


@dataclass
class _NormState:
    """Per-turn mutable state for the normalizer."""
    tool_starts: dict[str, float] = field(default_factory=dict)
    last_handoff_to: str | None = None
    last_handoff_at: float = 0.0
    inside_think: bool = False  # across delta boundaries
    saw_reasoning_delta: bool = False


_THINK_OPEN = re.compile(r"<think(?:ing)?>", re.IGNORECASE)
_THINK_CLOSE = re.compile(r"</think(?:ing)?>", re.IGNORECASE)
_HANDOFF_LINE = re.compile(r"^\s*→\s*\{.*?\}\s*$", re.MULTILINE)
_DEFAULT_HISTORY_MESSAGES = 20
_DEFAULT_HISTORY_MAX_CHARS = 32_000


async def run_turn(
    user_text: str, session_id: str | None = None, team_override: str | None = None,
) -> AsyncIterator[StreamEvent]:
    """Run a single user turn against the swarm, streaming normalized events."""
    session: Session = get_session(session_id) if session_id else new_session()
    store = get_store()
    history = store.get_messages_for_llm(
        session.id,
        limit=_env_int("CHAT_HISTORY_MESSAGES", _DEFAULT_HISTORY_MESSAGES),
        max_chars=_env_int("CHAT_HISTORY_MAX_CHARS", _DEFAULT_HISTORY_MAX_CHARS),
    )
    store.add_message(session.id, "user", user_text)

    team_name = team_override or pick_team(user_text)
    try:
        root_agent = load_and_build(team_name)
    except Exception as e:  # noqa: BLE001
        yield StreamEvent("error", f"failed to build team {team_name!r}: {e}")
        return

    yield StreamEvent("handoff", {"to": root_agent.name, "team": team_name,
                                  "session_id": session.id})

    ctx: dict[str, Any] = {"tool_calls": [], "session_id": session.id}
    state = _NormState()
    final_deltas: list[str] = []
    run_input = [*history, {"role": "user", "content": user_text}]
    try:
        result = Runner.run_streamed(root_agent, input=run_input, context=ctx)
        async for ev in result.stream_events():
            for norm in _normalize(ev, state):
                if norm.kind == "delta" and isinstance(norm.data, str):
                    final_deltas.append(norm.data)
                yield norm
        final_text = _extract_final_text(result, final_deltas)
        final_text = _sanitize_final(final_text)
        final_text = decorate(final_text)
        store.add_message(session.id, "assistant", final_text,
                          payload={"team": team_name})
        yield StreamEvent("final", {"markdown": final_text, "session_id": session.id})
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001
        yield StreamEvent("error", str(e))


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(0, value)


def _normalize(ev: Any, state: _NormState) -> list[StreamEvent]:
    """Map one SDK stream event to zero-or-more normalized StreamEvents.

    Splits ``raw_response_event`` into ``delta`` (final answer) vs
    ``reasoning_delta`` (thinking drawer) based on the underlying OpenAI
    responses event type. Uses ``run_item_stream_event`` for handoffs and
    tool invocations so we get exactly one event per real transition.
    """
    etype = getattr(ev, "type", None) or ev.__class__.__name__
    out: list[StreamEvent] = []

    if etype == "raw_response_event":
        data = getattr(ev, "data", None)
        dtype = getattr(data, "type", "") or ""
        delta = getattr(data, "delta", None)
        if not isinstance(delta, str) or not delta:
            return out
        if dtype == "response.output_text.delta":
            cleaned = _split_think(delta, state)
            if cleaned:
                out.append(StreamEvent("delta", cleaned))
            return out
        if dtype in {
            "response.reasoning_text.delta",
            "response.reasoning_summary_text.delta",
        }:
            state.saw_reasoning_delta = True
            out.append(StreamEvent("reasoning_delta", delta))
            return out
        return out

    if etype == "run_item_stream_event":
        name = getattr(ev, "name", "") or ""
        item = getattr(ev, "item", None)
        if name in {"handoff_occured", "handoff_occurred"}:
            to_name = _agent_name(item)
            now = time.time()
            if to_name and (
                state.last_handoff_to != to_name or (now - state.last_handoff_at) > 1.0
            ):
                state.last_handoff_to = to_name
                state.last_handoff_at = now
                out.append(StreamEvent("handoff", {"to": to_name}))
            return out
        if name == "tool_called":
            cid, tname, targs = _tool_called_fields(item)
            if cid:
                state.tool_starts[cid] = time.time()
            out.append(StreamEvent("tool_call_start", {
                "call_id": cid, "name": tname, "arguments": targs,
            }))
            return out
        if name == "tool_output":
            cid, tname, toutput = _tool_output_fields(item)
            dur_ms: int | None = None
            if cid and cid in state.tool_starts:
                dur_ms = int((time.time() - state.tool_starts.pop(cid)) * 1000)
            out.append(StreamEvent("tool_call_end", {
                "call_id": cid, "name": tname, "result": toutput,
                "duration_ms": dur_ms,
            }))
            return out
        if name == "reasoning_item_created":
            if state.saw_reasoning_delta:
                return out
            text = _reasoning_text(item)
            if text:
                out.append(StreamEvent("reasoning_delta", text))
            return out
        return out

    if etype == "agent_updated_stream_event":
        new_agent = getattr(ev, "new_agent", None)
        aname = getattr(new_agent, "name", None)
        if aname:
            out.append(StreamEvent("agent_updated", {"name": aname}))
        return out

    return out


def _split_think(delta: str, state: _NormState) -> str:
    """Safety net: strip ``<think>…</think>`` tags from a delta, tracking
    open state across chunk boundaries. Some providers send reasoning as
    plain text deltas with inline think tags instead of proper reasoning
    events — this catches that case.
    """
    out_parts: list[str] = []
    cursor = 0
    text = delta
    while cursor < len(text):
        if state.inside_think:
            m = _THINK_CLOSE.search(text, cursor)
            if not m:
                return "".join(out_parts)
            cursor = m.end()
            state.inside_think = False
        else:
            m = _THINK_OPEN.search(text, cursor)
            if not m:
                out_parts.append(text[cursor:])
                break
            out_parts.append(text[cursor:m.start()])
            cursor = m.end()
            state.inside_think = True
    return "".join(out_parts)


def _agent_name(item: Any) -> str | None:
    for attr in ("target_agent_name", "to_agent_name", "agent_name"):
        v = getattr(item, attr, None)
        if isinstance(v, str) and v:
            return v
    target = getattr(item, "target_agent", None) or getattr(item, "to_agent", None)
    if target is not None:
        return getattr(target, "name", None)
    raw = getattr(item, "raw_item", None)
    if raw is not None:
        for attr in ("target_agent_name", "agent_name", "name"):
            v = getattr(raw, attr, None)
            if isinstance(v, str) and v:
                return v
    return None


def _tool_called_fields(item: Any) -> tuple[str | None, str | None, dict[str, Any]]:
    raw = getattr(item, "raw_item", item)
    cid = (
        getattr(raw, "call_id", None)
        or getattr(item, "call_id", None)
        or getattr(raw, "id", None)
        or getattr(item, "id", None)
    )
    name = getattr(raw, "name", None) or getattr(raw, "tool_name", None)
    args_raw = getattr(raw, "arguments", None)
    args: dict[str, Any] = {}
    if isinstance(args_raw, dict):
        args = args_raw
    elif isinstance(args_raw, str):
        try:
            import json as _json
            parsed = _json.loads(args_raw)
            if isinstance(parsed, dict):
                args = parsed
        except Exception:  # noqa: BLE001
            args = {"_raw": args_raw}
    return cid, name, args


def _tool_output_fields(item: Any) -> tuple[str | None, str | None, Any]:
    raw = getattr(item, "raw_item", item)
    cid = (
        getattr(raw, "call_id", None)
        or getattr(item, "call_id", None)
        or getattr(raw, "tool_call_id", None)
        or getattr(item, "tool_call_id", None)
    )
    if isinstance(raw, dict):
        cid = cid or raw.get("call_id") or raw.get("tool_call_id")
    name = getattr(raw, "name", None) or getattr(raw, "tool_name", None)
    output = getattr(item, "output", None)
    if output is None:
        output = getattr(raw, "output", None)
    if hasattr(output, "model_dump"):
        try:
            output = output.model_dump()
        except Exception:  # noqa: BLE001
            pass
    return cid, name, output


def _reasoning_text(item: Any) -> str | None:
    raw = getattr(item, "raw_item", item)
    for attr in ("text", "summary_text", "content"):
        v = getattr(raw, attr, None)
        if isinstance(v, str) and v:
            return v
    return None


def _extract_final_text(result: Any, streamed_deltas: list[str]) -> str:
    """Prefer typed Pydantic payloads; fall back to the concatenated delta stream."""
    out = getattr(result, "final_output", None)
    if out is not None:
        for attr in ("markdown", "message_markdown", "summary_markdown"):
            v = getattr(out, attr, None)
            if isinstance(v, str) and v.strip():
                return v
        if hasattr(out, "model_dump"):
            try:
                dump = out.model_dump()
                for key in ("markdown", "message_markdown", "summary_markdown"):
                    if isinstance(dump.get(key), str) and dump[key].strip():
                        return dump[key]
            except Exception:  # noqa: BLE001
                pass
        if isinstance(out, str) and out.strip():
            return out
    joined = "".join(streamed_deltas).strip()
    if joined:
        return joined
    if out is not None:
        return str(out)
    return ""


def _sanitize_final(text: str) -> str:
    """Belt-and-braces: strip any leaked handoff JSON lines and stray think tags."""
    if not text:
        return text
    text = _HANDOFF_LINE.sub("", text)
    text = _THINK_OPEN.sub("", text)
    text = _THINK_CLOSE.sub("", text)
    # Collapse 3+ blank lines left behind.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
