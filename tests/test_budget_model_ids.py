"""Use PAOS configuration IDs without borrowing a different route's limits."""

from __future__ import annotations

import sys
from unittest.mock import Mock

import pytest

from PhyAgentOS.agent.budget import request_budget
from PhyAgentOS.config.schema import Config
from PhyAgentOS.providers.base import GenerationSettings


class Provider:
    generation = GenerationSettings(max_tokens=8192)


@pytest.mark.parametrize("configured,canonical", [
    ("anthropic/claude-opus-4-5", "claude-opus-4-5"),
    ("anthropic/claude-sonnet-4-5", "claude-sonnet-4-5"),
    ("openai/gpt-4o", "gpt-4o"),
])
def test_native_prefixed_ids_share_their_catalog_window(configured, canonical):
    import litellm

    assert litellm.model_cost[canonical]["max_input_tokens"] > 0
    budget, _ = request_budget(Provider(), configured, 65536)
    assert budget is not None
    assert budget == request_budget(Provider(), canonical, 65536)[0]


def test_schema_default_id_receives_request_protection():
    import litellm

    configured = Config().agents.defaults.model
    assert configured == "anthropic/claude-opus-4-5"
    window = litellm.model_cost["claude-opus-4-5"]["max_input_tokens"]
    assert request_budget(Provider(), configured, 65536)[0] == window - 8192 - window // 20


@pytest.mark.parametrize("model", ["deepseek/deepseek-chat", "azure/gpt-4o"])
def test_exact_route_metadata_wins_without_provider_parsing(monkeypatch, model):
    import litellm

    window = litellm.model_cost[model]["max_input_tokens"]
    parser = Mock(side_effect=AssertionError("exact catalog match needs no parsing"))
    monkeypatch.setattr(litellm, "get_llm_provider", parser)
    assert request_budget(Provider(), model, 65536)[0] == window - 8192 - window // 20
    parser.assert_not_called()


def test_route_specific_entry_precedes_native_fallback(monkeypatch):
    import litellm

    monkeypatch.setitem(litellm.model_cost, "openai/gpt-4o", {"max_input_tokens": 64000})
    monkeypatch.setitem(litellm.model_cost, "gpt-4o", {"max_input_tokens": 128000})
    assert request_budget(Provider(), "openai/gpt-4o", 65536)[0] == 52608


def test_parser_resolved_route_is_checked_before_native_entry(monkeypatch):
    import litellm

    monkeypatch.setattr(litellm, "get_llm_provider", lambda **kw: ("review-native", "openai", None, None))
    monkeypatch.setitem(litellm.model_cost, "openai/review-native", {"max_input_tokens": 64000})
    monkeypatch.setitem(litellm.model_cost, "review-native", {"max_input_tokens": 200000})
    assert request_budget(Provider(), "review-alias", 65536)[0] == 52608


@pytest.mark.parametrize("gateway,native", [("openrouter", "openai/gpt-4o-mini"), ("azure", "gpt-4o")])
def test_gateway_without_own_metadata_does_not_inherit_native_limit(monkeypatch, gateway, native):
    import litellm

    model = f"{gateway}/{native}"
    monkeypatch.delitem(litellm.model_cost, model, raising=False)
    monkeypatch.setitem(litellm.model_cost, native, {"max_input_tokens": 128000})
    monkeypatch.setattr(litellm, "get_llm_provider", lambda **kw: (native, gateway, None, None))
    assert request_budget(Provider(), model, 65536)[0] is None


def test_openrouter_own_catalog_entry_enables_protection(monkeypatch):
    import litellm

    model = "openrouter/openai/gpt-4o-mini"
    monkeypatch.setitem(litellm.model_cost, model, {"max_input_tokens": 64000})
    assert request_budget(Provider(), model, 65536)[0] == 52608


def test_unrecognized_deployment_alias_remains_unknown(monkeypatch):
    import litellm

    monkeypatch.setattr(litellm, "get_llm_provider", Mock(side_effect=ValueError("unknown deployment")))
    assert request_budget(Provider(), "private-deployment-alias", 65536)[0] is None


@pytest.mark.parametrize("window", [None, 0, -1, True, "200000", 200000.0])
def test_invalid_catalog_window_does_not_create_a_request_limit(monkeypatch, window):
    import litellm

    monkeypatch.setitem(litellm.model_cost, "review-invalid", {"max_input_tokens": window})
    assert request_budget(Provider(), "review-invalid", 65536)[0] is None


def test_direct_only_path_does_not_import_litellm(monkeypatch):
    import builtins

    monkeypatch.delitem(sys.modules, "litellm", raising=False)
    real_import = builtins.__import__

    def guard(name, *args, **kwargs):
        assert name != "litellm", "Budgeting must not import the optional heavy provider path"
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guard)
    assert request_budget(Provider(), "openai/gpt-4o", 65536)[0] is None
    assert request_budget(Provider(), "openai/gpt-4o", 65536, archival=True)[0] > 0
