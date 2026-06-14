import uuid
from datetime import datetime, UTC
from typing import Optional, Union

from src.platform.infrastructure.databases.relational.sqlalchemy import SqlAlchemyAdaptor
from src.platform.llm.metrics.models import LLMMetric
from src.platform.llm.metrics.workflow_names import WorkflowName
from src.platform.logging import get_logger

logger = get_logger(__name__)


class LLMMetricsService:
    def __init__(self, db_adaptor: SqlAlchemyAdaptor) -> None:
        self.db_adaptor = db_adaptor

    async def record(
        self,
        *,
        workflow_name: Union[WorkflowName, str],
        resource_id: Optional[uuid.UUID | str],
        model_used: str,
        input_tokens: int,
        output_tokens: int,
        response_time_ms: int,
        other_details: Optional[dict] = None,
    ) -> None:
        """Fire-and-forget metric write. Swallows errors to never block the LLM path."""
        try:
            resolved_resource_id: Optional[uuid.UUID] = None
            if isinstance(resource_id, str):
                resolved_resource_id = uuid.UUID(resource_id)
            else:
                resolved_resource_id = resource_id

            metric = LLMMetric(
                id=uuid.uuid4(),
                workflow_name=workflow_name,
                resource_id=resolved_resource_id,
                model_used=model_used,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                response_time_ms=response_time_ms,
                recorded_at=datetime.now(UTC),
                other_details=other_details,
            )
            async with self.db_adaptor.get_async_session() as session:
                session.add(metric)
                await session.commit()
        except Exception:
            logger.warning(
                "Failed to record LLM metric",
                workflow_name=workflow_name,
                resource_id=str(resource_id),
                exc_info=True,
            )
