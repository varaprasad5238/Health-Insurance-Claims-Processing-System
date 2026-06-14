"""
LLM Metrics Batch Accumulator

For high-volume workflows (e.g. code ingestion) that issue thousands of LLM calls,
writing one DB row per call causes unnecessary table bloat and write pressure.

LLMMetricsBatch accumulates metrics in memory and, on flush, writes a single
aggregated row per (workflow_name, model_used, resource_id) combination.

Usage as an async context manager (recommended):

    from src.platform.llm.metrics.batch import LLMMetricsBatch

    async with LLMMetricsBatch(db_adaptor) as batch:
        llm = StreamingLLM(..., metrics_batch=batch)
        # ... run workflow ...
    # flush() called automatically on exit

Usage with explicit flush:

    batch = LLMMetricsBatch(db_adaptor)
    llm = StreamingLLM(..., metrics_batch=batch)
    # ... run workflow ...
    await batch.flush()
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Optional, Union

from src.platform.infrastructure.databases.relational.sqlalchemy import SqlAlchemyAdaptor
from src.platform.llm.metrics.models import LLMMetric
from src.platform.llm.metrics.workflow_names import WorkflowName
from src.platform.logging import get_logger

logger = get_logger(__name__)


@dataclass
class _Bucket:
    """In-memory accumulator for a single (workflow_name, model_used, resource_id) slice."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_response_time_ms: int = 0
    call_count: int = 0
    first_recorded_at: Optional[datetime] = None


class LLMMetricsBatch:
    """
    In-memory accumulator for LLM metrics.

    Drop-in replacement for LLMMetricsService at high-volume call sites.
    ``record()`` is identical in signature to LLMMetricsService.record() so
    StreamingLLM can accept either type.
    """

    def __init__(self, db_adaptor: SqlAlchemyAdaptor) -> None:
        self._db_adaptor = db_adaptor
        # Key: (workflow_name, model_used, resource_id_str)
        self._buckets: dict[tuple, _Bucket] = defaultdict(_Bucket)

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
        """Accumulate a single LLM call metric into memory (no DB write)."""
        phase = (other_details or {}).get("phase", "")
        key = (str(workflow_name), str(model_used), str(resource_id), phase)
        bucket = self._buckets[key]
        bucket.input_tokens += input_tokens
        bucket.output_tokens += output_tokens
        bucket.total_response_time_ms += response_time_ms
        bucket.call_count += 1
        if bucket.first_recorded_at is None:
            bucket.first_recorded_at = datetime.now(UTC)

    async def flush(self) -> None:
        """Write one aggregated row per bucket to the DB. Swallows errors."""
        if not self._buckets:
            return

        rows_to_write = list(self._buckets.items())
        try:
            metrics = []
            for (workflow_name, model_used, resource_id_str, phase), bucket in rows_to_write:
                resolved_resource_id: Optional[uuid.UUID] = None
                if resource_id_str and resource_id_str != "None":
                    try:
                        resolved_resource_id = uuid.UUID(resource_id_str)
                    except ValueError:
                        pass

                avg_response_time_ms = (
                    bucket.total_response_time_ms // bucket.call_count
                    if bucket.call_count
                    else 0
                )
                row_extra: dict = {
                    "call_count": bucket.call_count, "aggregated": True}
                if phase:
                    row_extra["phase"] = phase
                metrics.append(
                    LLMMetric(
                        id=uuid.uuid4(),
                        workflow_name=workflow_name,
                        resource_id=resolved_resource_id,
                        model_used=model_used,
                        input_tokens=bucket.input_tokens,
                        output_tokens=bucket.output_tokens,
                        response_time_ms=avg_response_time_ms,
                        recorded_at=bucket.first_recorded_at or datetime.now(
                            UTC),
                        other_details=row_extra,
                    )
                )

            async with self._db_adaptor.get_async_session() as session:
                session.add_all(metrics)
                await session.commit()

            logger.info(
                "LLM metrics batch flushed",
                rows_written=len(metrics),
                total_calls=sum(b.call_count for _, b in rows_to_write),
            )
        except Exception:
            logger.warning(
                "Failed to flush LLM metrics batch",
                rows=len(rows_to_write),
                exc_info=True,
            )
        finally:
            self._buckets.clear()

    # ── async context manager ─────────────────────────────────────────────────

    async def __aenter__(self) -> "LLMMetricsBatch":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.flush()
        return None  # do not suppress exceptions
