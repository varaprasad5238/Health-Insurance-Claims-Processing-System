from abc import ABC, abstractmethod
from typing import Any

from backend.ai_platform.errors import AgentExecutionError
from backend.tracing.store import TraceStore


class BaseAgent(ABC):
    agent_name: str
    stage_order: int
    model_used: str = "none"

    async def run(self, claim_id: str, **kwargs: Any) -> Any:
        span_id = await TraceStore.start_span(
            claim_id,
            self.agent_name,
            stage_order=self.stage_order,
            input_summary=kwargs,
            model_used=self.model_used,
            current_stage=self.agent_name,
        )
        try:
            result = await self.execute(claim_id=claim_id, **kwargs)
            await TraceStore.finish_span(
                span_id,
                status="SUCCESS",
                output_summary=self.summarize_output(result),
                current_stage=None,
            )
            return result
        except Exception as exc:
            await TraceStore.finish_span(
                span_id,
                status="ERROR",
                output_summary=None,
                errors=[str(exc)],
                current_stage=None,
            )
            raise AgentExecutionError(f"{self.agent_name} failed: {exc}") from exc

    @abstractmethod
    async def execute(self, claim_id: str, **kwargs: Any) -> Any:
        raise NotImplementedError

    def summarize_output(self, result: Any) -> dict[str, Any]:
        if hasattr(result, "model_dump"):
            return result.model_dump()
        if isinstance(result, dict):
            return result
        return {"result": str(result)}