"""
LLM Metrics

Provides DB-backed recording of LLM call metrics (tokens, latency, model).

Usage at app startup (gateway.py):

    from src.platform.llm.metrics import init_metrics
    init_metrics(db_adaptor)

Usage at call sites (fire-and-forget):

    from src.platform.llm.metrics import get_metrics_service
    svc = get_metrics_service()
    if svc:
        await svc.record(workflow_name=..., resource_id=..., ...)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from src.platform.llm.metrics.service import LLMMetricsService
from src.platform.llm.metrics.batch import LLMMetricsBatch
from src.platform.llm.metrics.workflow_names import WorkflowName

if TYPE_CHECKING:
    from src.platform.infrastructure.databases.relational.sqlalchemy import SqlAlchemyAdaptor

_db_adaptor: Optional["SqlAlchemyAdaptor"] = None


def init_metrics(db_adaptor: "SqlAlchemyAdaptor") -> None:
    """Configure the shared db adaptor used by :func:`get_metrics_service`.

    Call once at application startup (e.g. in the FastAPI lifespan handler)
    before any LLM calls are made.
    """
    global _db_adaptor
    _db_adaptor = db_adaptor


def get_metrics_service() -> Optional[LLMMetricsService]:
    """Return a :class:`LLMMetricsService` instance if the db adaptor has been
    initialised via :func:`init_metrics`, otherwise return ``None``.

    Callers should guard on ``None`` so that metrics are silently skipped when
    running outside of the full application context (tests, scripts, etc.).
    """
    if _db_adaptor is None:
        return None
    return LLMMetricsService(_db_adaptor)


__all__ = ["LLMMetricsService", "LLMMetricsBatch", "WorkflowName", "init_metrics", "get_metrics_service"]
