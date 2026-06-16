from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from backend.ai_platform.config import PlatformSettings, get_platform_settings
from backend.ai_platform.errors import InvalidModelOutput, ProviderUnavailable, SchemaValidationFailed
from backend.ai_platform.llm import (
    LLMPlatform,
    StubLLMClient,
    _CIRCUITS,
    circuit_is_open,
    estimate_text_tokens,
    estimate_tokens,
    extract_gemini_usage,
    extract_openai_usage,
    normalize_provider_error,
    parse_model_json,
    record_model_failure,
    record_model_success,
)
from backend.ai_platform.metrics import normalize_agent_name, split_provider_model
from backend.ai_platform.schemas import DecisionMessageOutput, DocumentVisionListOutput, StructuredExtractionOutput


def settings(**overrides):
    defaults = {
        "llm_provider": "primary",
        "fallback_llm_provider": "fallback",
        "gemini_api_key": None,
        "openai_api_key": None,
        "openai_base_url": None,
        "vision_model": "model-a",
        "fallback_vision_model": "model-b",
        "fast_model": "fast",
        "llm_timeout_seconds": 1.0,
        "llm_max_retries": 0,
        "circuit_failure_threshold": 2,
        "circuit_cooldown_seconds": 30.0,
        "use_stub_llm": False,
    }
    defaults.update(overrides)
    return PlatformSettings(**defaults)


def test_parse_model_json_success_and_errors():
    parsed = parse_model_json('{"member_message":"ok","ops_summary":"done"}', DecisionMessageOutput)

    assert parsed.member_message == "ok"
    with pytest.raises(InvalidModelOutput):
        parse_model_json("not json", DecisionMessageOutput)
    with pytest.raises(SchemaValidationFailed):
        parse_model_json('{"member_message":"missing ops"}', DecisionMessageOutput)


def test_token_and_usage_helpers():
    assert estimate_text_tokens(None) == 0
    assert estimate_text_tokens("abcd") == 1
    assert estimate_tokens("abcd", context={"key": "value"}, image_bytes=b"123") > 800

    openai_usage = SimpleNamespace(prompt_tokens=3, completion_tokens=4, total_tokens=7)
    gemini_usage = SimpleNamespace(prompt_token_count=5, candidates_token_count=6, total_token_count=0)
    assert extract_openai_usage(SimpleNamespace(usage=openai_usage)) == (3, 4, 7)
    assert extract_openai_usage(SimpleNamespace(usage=None)) == (0, 0, 0)
    assert extract_gemini_usage(SimpleNamespace(usage_metadata=gemini_usage)) == (5, 6, 11)
    assert extract_gemini_usage(SimpleNamespace(usage_metadata=None)) == (0, 0, 0)


def test_circuit_state_opens_and_resets():
    _CIRCUITS.clear()
    platform_settings = settings(circuit_failure_threshold=2, circuit_cooldown_seconds=60)

    record_model_failure("model-a", platform_settings)
    assert not circuit_is_open("model-a")
    record_model_failure("model-a", platform_settings)
    assert circuit_is_open("model-a")
    record_model_success("model-a")
    assert not circuit_is_open("model-a")


def test_normalize_provider_error_categories():
    assert normalize_provider_error(SimpleNamespace(status_code=429, __str__=lambda self: "quota")).code == "PROVIDER_QUOTA_EXCEEDED"
    assert normalize_provider_error(Exception("api key invalid")).code == "PROVIDER_AUTH_FAILED"
    assert normalize_provider_error(SimpleNamespace(status_code=404, __str__=lambda self: "not found")).code == "PROVIDER_MODEL_UNAVAILABLE"
    assert normalize_provider_error(Exception("boom")).code == "PROVIDER_UNAVAILABLE"


@pytest.mark.asyncio
async def test_stub_llm_payloads_for_supported_tasks():
    client = StubLLMClient()

    extraction = await client.get_llm_response(prompt="extract", context={"task": "structured_extraction"})
    decision = await client.get_llm_response(
        prompt="decide",
        context={"task": "decision_synthesis", "policy_decision": {"decision": "PARTIAL", "approved_amount": "300.00"}},
    )
    vision = await client.get_llm_response(prompt="vision", context={"file_name": "lab_report.png"})

    assert parse_model_json(extraction.raw_text, StructuredExtractionOutput).patient_name == "Rajesh Kumar"
    assert parse_model_json(decision.raw_text, DecisionMessageOutput).member_message.endswith("300.00.")
    assert parse_model_json(vision.raw_text, DocumentVisionListOutput).documents[0].document_type == "LAB_REPORT"


class FailingClient:
    async def get_llm_response(self, **kwargs):
        raise ProviderUnavailable("down", code="PROVIDER_DOWN")


class SuccessfulClient:
    async def get_llm_response(self, **kwargs):
        from backend.ai_platform.schemas import LLMResult

        return LLMResult(model=kwargs["model"], raw_text="{}", latency_ms=1, input_tokens=2, output_tokens=3)


@pytest.mark.asyncio
async def test_llm_platform_uses_fallback_and_records_metric(monkeypatch):
    recorded = []

    async def fake_record_metric(**kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr("backend.ai_platform.llm.safe_record_llm_metric", fake_record_metric)
    platform = LLMPlatform(None, settings())
    platform._clients = {"primary": FailingClient(), "fallback": SuccessfulClient()}

    result = await platform.get_llm_response(prompt="hello", claim_id="CLM-1", agent_name="entity_extraction")

    assert result.model == "fallback:model-b"
    assert result.fallback_used is True
    assert result.primary_error == "PROVIDER_DOWN"
    assert [entry["status"] for entry in recorded] == ["ERROR", "SUCCESS"]


def test_llm_platform_client_factory_supports_stub_and_rejects_unknown():
    platform = LLMPlatform(None, settings(llm_provider="stub"))

    assert isinstance(platform.client_for_provider("stub"), StubLLMClient)
    with pytest.raises(ProviderUnavailable, match="Unsupported LLM provider"):
        platform.client_for_provider("unknown")


def test_platform_settings_loads_from_environment(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("USE_STUB_LLM", raising=False)
    monkeypatch.delenv("LLM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("USE_STUB_LLM", "false")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "2.5")
    get_platform_settings.cache_clear()

    loaded = get_platform_settings()

    assert loaded.llm_provider == "gemini"
    assert loaded.llm_timeout_seconds == 2.5
    assert loaded.use_stub_llm is False


def test_metric_helpers_normalize_values():
    assert split_provider_model("gemini:model") == ("gemini", "model")
    assert split_provider_model("plain-model") == ("unknown", "plain-model")
    assert normalize_agent_name(None) == "unknown"
    assert normalize_agent_name("vision_read_doc_2") == "vision_reader"
    assert normalize_agent_name("policy_engine") == "policy_engine"
