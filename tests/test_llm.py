"""Tests for optional LLM routing helpers."""

from __future__ import annotations

import os

from phi.detect.llm import _api_key_env_var_for_model, _configure_litellm_api_key


def test_api_key_env_var_for_common_litellm_models() -> None:
    assert _api_key_env_var_for_model("anthropic/claude-haiku-4-5") == "ANTHROPIC_API_KEY"
    assert _api_key_env_var_for_model("openai/gpt-4o-mini") == "OPENAI_API_KEY"
    assert _api_key_env_var_for_model("gemini/gemini-1.5-flash") == "GEMINI_API_KEY"
    assert _api_key_env_var_for_model("openrouter/openai/gpt-4o-mini") == "OPENROUTER_API_KEY"


def test_generic_api_key_is_passed_to_litellm(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    kwargs = _configure_litellm_api_key("anthropic/claude-haiku-4-5", "test-key")

    assert kwargs == {"api_key": "test-key"}
    assert os.getenv("ANTHROPIC_API_KEY") == "test-key"
    assert _api_key_env_var_for_model("unknown/model") is None
