"""Tests for orchestrator stream-event normalization.

Covers the three regressions hallocination.md exposed:
  1. Reasoning deltas must land in ``reasoning_delta``, not ``delta``.
  2. Plain-text ``<think>…</think>`` tags (LiteLLM path) must be stripped
     from final-answer deltas and routed nowhere.
  3. Handoff events must not duplicate when the SDK emits multiple
     sub-events for the same transition.
"""
from __future__ import annotations

from types import SimpleNamespace

from indie_market_analyst.agent.orchestrator import (
    _normalize,
    _NormState,
    _sanitize_final,
)


def _raw(dtype: str, delta: str) -> SimpleNamespace:
    return SimpleNamespace(type="raw_response_event", data=SimpleNamespace(type=dtype, delta=delta))


def _run_item(name: str, **kw) -> SimpleNamespace:
    return SimpleNamespace(type="run_item_stream_event", name=name, item=SimpleNamespace(**kw))


def test_output_text_delta_goes_to_delta() -> None:
    state = _NormState()
    evs = _normalize(_raw("response.output_text.delta", "Hello, "), state)
    assert len(evs) == 1
    assert evs[0].kind == "delta"
    assert evs[0].data == "Hello, "


def test_reasoning_delta_goes_to_reasoning_delta() -> None:
    state = _NormState()
    evs = _normalize(_raw("response.reasoning_text.delta", "thinking..."), state)
    assert len(evs) == 1
    assert evs[0].kind == "reasoning_delta"
    assert state.saw_reasoning_delta is True


def test_reasoning_item_created_is_suppressed_after_streamed_reasoning() -> None:
    state = _NormState()
    streamed = _normalize(_raw("response.reasoning_text.delta", "thinking..."), state)
    item = _run_item("reasoning_item_created", text="thinking...")
    created = _normalize(item, state)
    assert len(streamed) == 1
    assert streamed[0].kind == "reasoning_delta"
    assert created == []


def test_reasoning_item_created_still_works_without_streamed_reasoning() -> None:
    state = _NormState()
    evs = _normalize(_run_item("reasoning_item_created", text="thinking..."), state)
    assert len(evs) == 1
    assert evs[0].kind == "reasoning_delta"
    assert evs[0].data == "thinking..."


def test_think_tags_stripped_from_output_delta() -> None:
    """LiteLLM path: reasoning comes inside <think>...</think> in plain deltas."""
    state = _NormState()
    # Tag spans a single delta: "Pre<think>inner</think>Post"
    evs = _normalize(_raw("response.output_text.delta", "Pre<think>inner</think>Post"), state)
    assert len(evs) == 1
    assert evs[0].kind == "delta"
    assert evs[0].data == "PrePost"
    assert state.inside_think is False


def test_think_tags_stripped_across_deltas() -> None:
    state = _NormState()
    # Open tag in chunk 1, close in chunk 3.
    e1 = _normalize(_raw("response.output_text.delta", "Start <think>one"), state)
    e2 = _normalize(_raw("response.output_text.delta", " two"), state)
    e3 = _normalize(_raw("response.output_text.delta", " three</think>End"), state)
    texts = [ev.data for ev in (e1 + e2 + e3) if ev.kind == "delta"]
    assert "".join(texts) == "Start End"
    assert state.inside_think is False


def test_handoff_deduped_within_window() -> None:
    state = _NormState()
    item1 = _run_item("handoff_occured", target_agent_name="equity_researcher")
    item2 = _run_item("handoff_occured", target_agent_name="equity_researcher")
    out1 = _normalize(item1, state)
    out2 = _normalize(item2, state)
    assert len(out1) == 1 and out1[0].kind == "handoff"
    assert len(out2) == 0  # deduped


def test_handoff_allows_different_targets() -> None:
    state = _NormState()
    a = _run_item("handoff_occured", target_agent_name="verifier")
    b = _run_item("handoff_occured", target_agent_name="calculator")
    assert len(_normalize(a, state)) == 1
    assert len(_normalize(b, state)) == 1


def test_tool_call_start_and_end_pair() -> None:
    state = _NormState()
    start = SimpleNamespace(type="run_item_stream_event", name="tool_called",
                            item=SimpleNamespace(
                                raw_item=SimpleNamespace(
                                    call_id="c1", name="get_quote",
                                    arguments='{"symbol":"JSWSTEEL"}',
                                )))
    end = SimpleNamespace(type="run_item_stream_event", name="tool_output",
                          item=SimpleNamespace(
                              output={"price": 1274.5},
                              raw_item=SimpleNamespace(call_id="c1", name="get_quote")))
    out_start = _normalize(start, state)
    out_end = _normalize(end, state)
    assert out_start[0].kind == "tool_call_start"
    assert out_start[0].data["arguments"] == {"symbol": "JSWSTEEL"}
    assert out_end[0].kind == "tool_call_end"
    assert out_end[0].data["result"] == {"price": 1274.5}
    assert isinstance(out_end[0].data["duration_ms"], int)


def test_sanitize_final_strips_handoff_and_think_tags() -> None:
    raw = """→ {"to":"equity_researcher","team":"equity_research"}
<think>internal</think>
JSW Steel last price: 1274.5"""
    cleaned = _sanitize_final(raw)
    assert "→" not in cleaned
    assert "<think>" not in cleaned
    assert "JSW Steel" in cleaned
