from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from indie_market_analyst.agent import orchestrator
from indie_market_analyst.memory.store import MemoryStore
from indie_market_analyst.session import manager as session_manager


class _FakeStreamResult:
    def __init__(self, text: str) -> None:
        self.final_output = text

    async def stream_events(self):
        yield SimpleNamespace(
            type="raw_response_event",
            data=SimpleNamespace(type="response.output_text.delta", delta=self.final_output),
        )


async def test_run_turn_replays_bounded_session_history(tmp_path, monkeypatch) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    session_manager._sessions.clear()
    monkeypatch.setattr(orchestrator, "get_store", lambda: store)
    monkeypatch.setattr(session_manager, "get_store", lambda: store)
    monkeypatch.setattr(
        orchestrator,
        "load_and_build",
        lambda _team: SimpleNamespace(name="test_root"),
    )

    calls: list[list[dict[str, Any]]] = []

    def fake_run_streamed(_agent, input, context):  # noqa: ANN001
        assert context["session_id"]
        calls.append(input)
        current = input[-1]["content"]
        if current == "What stock did I name earlier?":
            text = (
                "You named INFY."
                if any(msg["content"] == "The stock is INFY." for msg in input[:-1])
                else "I do not know."
            )
        elif current == "The stock is INFY.":
            text = "Noted INFY."
        else:
            text = "Noted the risk limit."
        return _FakeStreamResult(text)

    monkeypatch.setattr(orchestrator.Runner, "run_streamed", fake_run_streamed)

    async def collect(text: str, session_id: str | None = None):
        events = [
            ev
            async for ev in orchestrator.run_turn(
                text,
                session_id=session_id,
                team_override="general_qa",
            )
        ]
        assert [ev.data for ev in events if ev.kind == "error"] == []
        return events

    first = await collect("The stock is INFY.")
    session_id = next(ev.data["session_id"] for ev in first if ev.kind == "final")
    await collect("I have a 5% risk limit.", session_id=session_id)
    third = await collect("What stock did I name earlier?", session_id=session_id)

    third_final = next(ev.data["markdown"] for ev in third if ev.kind == "final")
    assert "You named INFY." in third_final

    assert calls[0] == [{"role": "user", "content": "The stock is INFY."}]
    assert [msg["role"] for msg in calls[2]] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
    ]
    assert calls[2][0]["content"] == "The stock is INFY."
    assert calls[2][2]["content"] == "I have a 5% risk limit."
    assert calls[2][-1]["content"] == "What stock did I name earlier?"

    persisted = store.get_messages(session_id)
    assert [msg["role"] for msg in persisted] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_get_messages_for_llm_returns_recent_messages_in_chronological_order(tmp_path) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    session_id = store.create_session()
    for i in range(25):
        store.add_message(session_id, "user", f"message-{i}")

    history = store.get_messages_for_llm(session_id, limit=3, max_chars=1_000)

    assert history == [
        {"role": "user", "content": "message-22"},
        {"role": "user", "content": "message-23"},
        {"role": "user", "content": "message-24"},
    ]


def test_get_messages_for_llm_applies_character_budget(tmp_path) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    session_id = store.create_session()
    store.add_message(session_id, "user", "first")
    store.add_message(session_id, "assistant", "second")
    store.add_message(session_id, "user", "third")

    history = store.get_messages_for_llm(session_id, limit=20, max_chars=11)

    assert history == [
        {"role": "assistant", "content": "second"},
        {"role": "user", "content": "third"},
    ]
