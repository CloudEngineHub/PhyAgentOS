"""Local request budgets; no network model discovery or destructive history edits."""

from __future__ import annotations

import sys
from typing import Any

from PhyAgentOS.utils.helpers import estimate_prompt_tokens_chain


def request_budget(provider: Any, model: str, configured_window: int, *, archival: bool = False) -> tuple[int | None, int]:
    # contextWindowTokens is an archival threshold, not a model capability.
    # Do not guess a hard request ceiling for unknown deployment aliases.
    catalog = getattr(sys.modules.get("litellm"), "model_cost", {})
    known_input = catalog.get(model, {}).get("max_input_tokens")
    window = known_input if isinstance(known_input, int) and known_input > 0 else None
    generation = getattr(provider, "generation", None)
    output = max(1, getattr(generation, "max_tokens", 4096))
    if archival:
        chunk_window = configured_window if configured_window > 0 else 65_536
        window = min(window, chunk_window) if window else chunk_window
        output = min(output, 4096, max(1, window // 8))
    if window is None:
        return None, output
    return max(0, window - output - max(16, window // 20)), output


def fit_history(messages: list[dict], provider: Any, model: str, budget: int | None, tools: list[dict]) -> tuple[list[dict], bool]:
    """Fit complete user turns to a known model window without mutating history."""
    original = list(messages)
    if budget is None or estimate_prompt_tokens_chain(provider, model, original, tools)[0] <= budget:
        return original, False
    starts = [i for i, item in enumerate(original) if item.get("role") == "user"]
    prefix = original[:starts[0]] if starts else original
    if estimate_prompt_tokens_chain(provider, model, prefix, tools)[0] > budget:
        raise ValueError(
            "System instructions, memory or tool definitions exceed the model input budget. "
            "Reduce injected context or maxTokens; /new does not remove fixed context."
        )
    # Search user-turn boundaries rather than recounting every successive tail.
    low, high, best = 1, len(starts) - 1, None
    while low <= high:
        mid = (low + high) // 2
        candidate = prefix + original[starts[mid]:]
        if estimate_prompt_tokens_chain(provider, model, candidate, tools)[0] <= budget:
            best, high = candidate, mid - 1
        else:
            low = mid + 1
    if best is None:
        raise ValueError(
            "Current turn exceeds the model context budget. Reduce input/tool output or maxTokens; "
            "the original session is preserved. contextWindowTokens only controls archival."
        )
    return best, True
