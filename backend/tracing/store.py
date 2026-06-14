import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select

from backend.database.connection import AsyncSessionLocal
from backend.database.models import ClaimModel, TraceSpanModel
from backend.storage.local import write_intermediate_output
from .span import TraceSpan, TraceStatus, stage_order_for_agent

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def to_json(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, default=str)

def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)

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

    @staticmethod
    async def update_claim_state(
        claim_id: str,
        *,
        status: Optional[str] = None,
        current_stage: Optional[str] = None,
    ) -> None:
        async with AsyncSessionLocal() as session:
            claim = await session.get(ClaimModel, claim_id)
            if not claim:
                return
            if status is not None:
                claim.status = status
            claim.current_stage = current_stage
            claim.updated_at = utc_now_iso()
            await session.commit()

    @staticmethod
    async def start_span(
        claim_id: str,
        agent_name: str,
        *,
        stage_order: Optional[int] = None,
        input_summary: Optional[dict[str, Any]] = None,
        model_used: str = "none",
        current_stage: Optional[str] = None,
    ) -> str:
        span_id = str(uuid.uuid4())
        now = utc_now_iso()
        async with AsyncSessionLocal() as session:
            db_span = TraceSpanModel(
                span_id=span_id,
                claim_id=claim_id,
                agent_name=agent_name,
                stage_order=stage_order if stage_order is not None else stage_order_for_agent(agent_name),
                started_at=now,
                ended_at=None,
                elapsed_ms=None,
                status="RUNNING",
                input_summary=to_json(input_summary),
                output_summary=None,
                confidence_delta=None,
                errors="[]",
                model_used=model_used,
            )
            session.add(db_span)

            claim = await session.get(ClaimModel, claim_id)
            if claim:
                claim.status = "PROCESSING"
                claim.current_stage = current_stage or agent_name
                claim.updated_at = now

            await session.commit()
        return span_id

    @staticmethod
    async def finish_span(
        span_id: str,
        *,
        status: TraceStatus,
        output_summary: Optional[dict[str, Any]] = None,
        confidence_delta: Optional[float] = None,
        errors: Optional[list[str]] = None,
        current_stage: Optional[str] = None,
        claim_status: Optional[str] = None,
    ) -> None:
        now = utc_now_iso()
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(TraceSpanModel).where(TraceSpanModel.span_id == span_id))
            span = result.scalars().first()
            if not span:
                return

            span.ended_at = now
            span.elapsed_ms = int((parse_datetime(now) - parse_datetime(span.started_at)).total_seconds() * 1000)
            span.status = status
            span.output_summary = to_json(output_summary)
            span.confidence_delta = confidence_delta
            span.errors = to_json(errors or [])

            try:
                write_intermediate_output(
                    claim_id=span.claim_id,
                    stage_order=span.stage_order,
                    agent_name=span.agent_name,
                    span_id=span.span_id,
                    payload={
                        "span_id": span.span_id,
                        "claim_id": span.claim_id,
                        "agent_name": span.agent_name,
                        "stage_order": span.stage_order,
                        "status": status,
                        "started_at": span.started_at,
                        "ended_at": span.ended_at,
                        "elapsed_ms": span.elapsed_ms,
                        "input_summary": json.loads(span.input_summary) if span.input_summary else None,
                        "output_summary": output_summary,
                        "confidence_delta": confidence_delta,
                        "errors": errors or [],
                        "model_used": span.model_used,
                    },
                )
            except Exception:
                pass

            claim = await session.get(ClaimModel, span.claim_id)
            if claim:
                if claim_status is not None:
                    claim.status = claim_status
                claim.current_stage = current_stage
                claim.updated_at = now

            await session.commit()

    @staticmethod
    async def write_skipped_span(
        claim_id: str,
        agent_name: str,
        *,
        stage_order: Optional[int] = None,
        reason: str,
        model_used: str = "none",
    ) -> str:
        span_id = await TraceStore.start_span(
            claim_id,
            agent_name,
            stage_order=stage_order,
            input_summary={"reason": reason},
            model_used=model_used,
            current_stage=agent_name,
        )
        await TraceStore.finish_span(
            span_id,
            status="SKIPPED",
            output_summary={"skipped": True},
            errors=[reason],
            current_stage=None,
        )
        return span_id
