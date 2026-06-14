import json
from .span import TraceSpan
from backend.database.connection import AsyncSessionLocal
from backend.database.models import TraceSpanModel

class TraceStore:
    @staticmethod
    async def add_span(span: TraceSpan) -> None:
        async with AsyncSessionLocal() as session:
            db_span = TraceSpanModel(
                span_id=span.span_id,
                claim_id=span.claim_id,
                agent_name=span.agent_name,
                stage_order=span.stage_order,
                started_at=span.started_at.isoformat() if span.started_at else None,
                ended_at=span.ended_at.isoformat() if span.ended_at else None,
                elapsed_ms=span.elapsed_ms,
                status=span.status,
                input_summary=json.dumps(span.input_summary) if span.input_summary else None,
                output_summary=json.dumps(span.output_summary) if span.output_summary else None,
                confidence_delta=span.confidence_delta,
                errors=json.dumps(span.errors) if span.errors else "[]",
                model_used=span.model_used
            )
            session.add(db_span)
            await session.commit()
