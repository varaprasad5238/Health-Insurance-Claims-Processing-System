import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Index, Integer, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.platform.infrastructure.databases.relational.model_base import Base
from src.platform.infrastructure.databases.relational.datetime_mixin import TimestampMixin


class LLMMetric(Base, TimestampMixin):
    __tablename__ = "llm_metrics"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    workflow_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    resource_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        index=True,
    )
    model_used: Mapped[str] = mapped_column(String(255), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_time_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    other_details: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_llm_metrics_resource_workflow", "resource_id", "workflow_name"),
        Index("ix_llm_metrics_recorded_at", "recorded_at"),
    )
