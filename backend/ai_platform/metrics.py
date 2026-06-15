import uuid
from datetime import datetime, timezone

from backend.database.connection import AsyncSessionLocal
from backend.database.models import LLMMetricModel


def split_provider_model(value: str) -> tuple[str, str]:
    if ":" in value:
        provider, model = value.split(":", 1)
        return provider, model
    return "unknown", value


def normalize_agent_name(agent_name: str | None) -> str:
    if not agent_name:
        return "unknown"
    if agent_name.startswith("vision_read_doc_"):
        return "vision_reader"
    return agent_name


async def record_llm_metric(
    *,
    claim_id: str | None,
    agent_name: str | None,
    model_value: str,
    is_fallback: bool,
    primary_error: str | None,
    latency_ms: int | None,
    status: str,
    error_category: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    provider, model = split_provider_model(model_value)
    normalized_agent_name = normalize_agent_name(agent_name)
    total_tokens = input_tokens + output_tokens
    async with AsyncSessionLocal() as session:
        session.add(
            LLMMetricModel(
                metric_id=str(uuid.uuid4()),
                claim_id=claim_id,
                agent_name=normalized_agent_name,
                provider=provider,
                model=model,
                is_fallback=str(is_fallback).lower(),
                primary_error=primary_error,
                latency_ms=latency_ms,
                status=status,
                error_category=error_category,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        await session.commit()