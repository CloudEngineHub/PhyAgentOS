"""Small regression fixes without changing the Agent Loop's turn lifecycle."""

from __future__ import annotations

import base64
import json
import random
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from PhyAgentOS.agent.budget import fit_history, request_budget
from PhyAgentOS.agent.loop import AgentLoop
from PhyAgentOS.agent.memory import MemoryConsolidator, MemoryStore
from PhyAgentOS.bus.events import InboundMessage
from PhyAgentOS.providers.base import GenerationSettings, LLMResponse, ToolCallRequest
from PhyAgentOS.session.manager import SessionManager
from PhyAgentOS.utils import helpers


class Provider:
    generation = GenerationSettings(max_tokens=8192)

    def __init__(self):
        self.calls = []
        self.responses = []

    def get_default_model(self):
        return "review-model"

    async def chat_with_retry(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0) if self.responses else LLMResponse("plain reply")


class Bus:
    async def publish_outbound(self, message):
        pass


def success():
    return LLMResponse(None, tool_calls=[ToolCallRequest("save", "save_memory", {
        "history_entry": "Saved", "memory_update": "Saved facts",
    })])


@pytest.mark.parametrize("kb", [40, 60, 120, 1024])
def test_image_estimate_is_independent_of_base64_length(kb):
    p = Provider()
    url = "data:image/jpeg;base64," + base64.b64encode(random.Random(147).randbytes(kb * 1024)).decode()
    messages = [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": url}}, {"type": "text", "text": "Describe"},
    ]}]
    count = helpers.estimate_prompt_tokens(messages)
    assert 2048 <= count < 2200
    fit_history(messages, p, p.get_default_model(), 54068, [])
    assert messages[0]["content"][0]["image_url"]["url"] == url


async def test_real_image_reaches_provider_with_original_bytes(tmp_path, monkeypatch):
    import litellm
    monkeypatch.setitem(litellm.model_cost, "review-model", {"max_input_tokens": 65536})
    p = Provider()
    image = Path(__file__).resolve().parents[1] / "docs/imgs/benchmark-robotwin-en.png"
    loop = AgentLoop(bus=Bus(), provider=p, workspace=tmp_path)
    reply = await loop._process_message(InboundMessage(
        channel="cli", sender_id="test", chat_id="test", content="Describe", media=[str(image)],
    ))
    assert reply.content == "plain reply"
    assert len(p.calls) == 1
    part = next(part for part in p.calls[0]["messages"][-1]["content"] if part["type"] == "image_url")
    assert base64.b64decode(part["image_url"]["url"].split(",", 1)[1]) == image.read_bytes()


@pytest.mark.parametrize("tokenizer_available", [True, False])
def test_image_allowance_scales_by_image_count_not_encoded_size(monkeypatch, tokenizer_available):
    if not tokenizer_available:
        monkeypatch.setattr(helpers, "tiktoken", None)
    content = [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + "x" * 100000}}] * 3
    count, source = helpers.estimate_prompt_tokens_chain(Provider(), "model", [{"role": "user", "content": content}])
    assert 6144 <= count < 6600
    assert source == ("tiktoken" if tokenizer_available else "utf8_bytes")


def test_text_tool_arguments_and_reasoning_still_count():
    message = {"role": "assistant", "content": "", "reasoning_content": "reason " * 5000,
               "tool_calls": [{"arguments": "payload " * 5000}]}
    assert helpers.estimate_prompt_tokens([message]) > 9000
    # A data URL in actual text is still text, not a vision block.
    assert helpers.estimate_prompt_tokens([{"role": "user", "content": "data:image/png;base64," + random.Random(1).randbytes(60000).hex()}]) > 54068


def test_known_model_window_is_independent_of_archival_threshold(monkeypatch):
    import litellm
    monkeypatch.setitem(litellm.model_cost, "review-model", {"max_input_tokens": 200000})
    p = Provider()
    assert request_budget(p, p.get_default_model(), 65536)[0] == 181808
    assert request_budget(p, p.get_default_model(), 20000)[0] == 181808
    assert request_budget(p, p.get_default_model(), 65536, archival=True)[0] < 65536


@pytest.mark.parametrize("threshold", [65536, 200000, 0, -1])
def test_unknown_model_has_no_invented_request_cap(threshold):
    p = Provider()
    budget, _ = request_budget(p, "unknown-deployment-alias", threshold)
    assert budget is None
    message = [{"role": "user", "content": "large input"}]
    assert fit_history(message, p, "unknown-deployment-alias", budget, []) == (message, False)
    assert request_budget(p, "unknown-deployment-alias", threshold, archival=True)[0] > 0


async def test_nonpositive_threshold_disables_archival_without_unknown_64k_cap(tmp_path):
    p = Provider()
    sm = SessionManager(tmp_path)
    session = sm.get_or_create("cli:test")
    session.add_message("user", "x" * 600000)
    c = MemoryConsolidator(tmp_path, p, "unknown-deployment-alias", sm, 0, lambda **kw: [], lambda: [])
    assert await c.maybe_consolidate_by_tokens(session) is None
    assert not p.calls
    assert request_budget(p, "unknown-deployment-alias", 0)[0] is None


def test_fixed_context_error_explains_why_new_will_not_help():
    p = Provider()
    with pytest.raises(ValueError, match="/new does not remove fixed context"):
        fit_history([{"role": "system", "content": "policy " * 2000}, {"role": "user", "content": "hi"}], p, "model", 200, [])


async def test_auto_prose_gets_only_one_safe_format_retry(tmp_path):
    p = Provider()
    p.responses = [LLMResponse("prose"), success()]
    store = MemoryStore(tmp_path)
    assert await store.consolidate([{"role": "user", "content": "remember"}], p, p.get_default_model())
    assert len(p.calls) == 2
    assert all(call["tool_choice"] == "auto" for call in p.calls)
    assert "Plain text is not accepted" in p.calls[1]["messages"][0]["content"]
    assert store.read_long_term() == "Saved facts"


async def test_persistent_prose_fails_after_bounded_retry(tmp_path):
    p = Provider()
    store = MemoryStore(tmp_path)
    assert not await store.consolidate([{"role": "user", "content": "remember"}], p, p.get_default_model())
    assert len(p.calls) == 2
    assert not store.history_file.exists()


async def test_provider_error_is_not_retried_as_a_format_problem(tmp_path):
    p = Provider()
    p.responses = [LLMResponse("400 thinking", finish_reason="error")]
    assert not await MemoryStore(tmp_path).consolidate([{"role": "user", "content": "remember"}], p, p.get_default_model())
    assert len(p.calls) == 1


@pytest.mark.parametrize("invalid_value", ["object", "cycle"])
async def test_new_reports_serialization_failure_without_clearing(tmp_path, invalid_value):
    loop = AgentLoop(bus=Bus(), provider=Provider(), workspace=tmp_path)
    session = loop.sessions.get_or_create("cli:test")
    session.add_message("user", "keep")
    session.metadata["invalid"] = object() if invalid_value == "object" else session.metadata
    result = await loop.process_direct("/new", session_key=session.key)
    assert "not cleared" in result
    assert session.messages[0]["content"] == "keep"


async def test_archival_prefers_complete_jsonl_messages(tmp_path):
    p = Provider()
    p.chat_with_retry = AsyncMock(side_effect=lambda **kw: success())
    sm = SessionManager(tmp_path)
    session = sm.get_or_create("cli:test")
    for _ in range(30):
        session.add_message("user", "record " * 50)
    c = MemoryConsolidator(tmp_path, p, p.get_default_model(), sm, 2048, lambda **kw: [], lambda: [])
    assert await c.archive_unconsolidated(session)
    calls = p.chat_with_retry.call_args_list
    assert len(calls) > 1
    for call in calls:
        text = call.kwargs["messages"][1]["content"].split("\n## Conversation to Process\n", 1)[1]
        assert all(json.loads(line)["role"] == "user" for line in text.splitlines())


def test_context_fitting_uses_logarithmic_boundary_probes():
    probes = []
    def counter(provider, model, messages, tools):
        probes.append(len(messages))
        return len(messages) * 100, "test"
    messages = [{"role": "system", "content": "p"}] + [{"role": "user", "content": str(i)} for i in range(1000)]
    with patch("PhyAgentOS.agent.budget.estimate_prompt_tokens_chain", counter):
        fitted, reduced = fit_history(messages, Provider(), "model", 200, [])
    assert reduced and len(fitted) == 2
    assert fitted[-1] == messages[-1]
    assert len(probes) <= 13
