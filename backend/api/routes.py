import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, File, UploadFile, Form, Depends, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional

from backend.database.connection import AsyncSessionLocal
from backend.database.models import ClaimModel, TraceSpanModel, ClaimDecisionModel, GatingErrorModel

router = APIRouter(prefix="/api/claims", tags=["claims"])

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

@router.post("/")
async def submit_claim(
    member_id: str = Form(...),
    claim_category: str = Form(...),
    treatment_date: str = Form(...),
    claimed_amount: str = Form(...),
    documents: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db)
):
    claim_id = f"CLM-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    now_iso = datetime.now(timezone.utc).isoformat()
    
    new_claim = ClaimModel(
        claim_id=claim_id,
        member_id=member_id,
        policy_id="POL-DEFAULT",
        claim_category=claim_category,
        treatment_date=treatment_date,
        submission_date=now_iso,
        claimed_amount=claimed_amount,
        hospital_name=None,
        status="PROCESSING",
        current_stage="vision_read_doc_1",
        trace_id=f"trace-{claim_id}",
        created_at=now_iso,
        updated_at=now_iso
    )
    db.add(new_claim)
    await db.commit()
    
    return {
        "claim_id": claim_id,
        "status": "PROCESSING",
        "trace_id": new_claim.trace_id
    }

@router.get("/{claim_id}/status")
async def get_claim_status(claim_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ClaimModel).where(ClaimModel.claim_id == claim_id))
    claim = result.scalars().first()
    
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
        
    spans_result = await db.execute(
        select(TraceSpanModel)
        .where(TraceSpanModel.claim_id == claim_id)
        .order_by(TraceSpanModel.started_at)
    )
    spans = spans_result.scalars().all()
    
    decision_result = await db.execute(select(ClaimDecisionModel).where(ClaimDecisionModel.claim_id == claim_id))
    decision = decision_result.scalars().first()
    
    gating_error_result = await db.execute(select(GatingErrorModel).where(GatingErrorModel.claim_id == claim_id))
    gating_error = gating_error_result.scalars().first()
    
    def parse_json(val):
        if val:
            try: return json.loads(val)
            except: return val
        return None
        
    spans_data = []
    for s in spans:
        spans_data.append({
            "span_id": s.span_id,
            "agent_name": s.agent_name,
            "stage_order": s.stage_order,
            "status": s.status,
            "elapsed_ms": s.elapsed_ms,
            "started_at": s.started_at,
            "ended_at": s.ended_at,
            "output_summary": parse_json(s.output_summary),
            "confidence_delta": s.confidence_delta,
            "errors": parse_json(s.errors) or [],
            "model_used": s.model_used
        })
        
    decision_data = None
    if decision:
        decision_data = {
            "decision": decision.decision,
            "approved_amount": decision.approved_amount,
            "copay_deducted": decision.copay_deducted,
            "network_discount_applied": decision.network_discount_applied,
            "rejection_reasons": parse_json(decision.rejection_reasons) or [],
            "partial_items": parse_json(decision.partial_items),
            "member_message": decision.member_message,
            "ops_summary": decision.ops_summary,
            "confidence_score": decision.confidence_score,
            "manual_review_note": decision.manual_review_note
        }
        
    gating_error_data = None
    if gating_error:
        gating_error_data = {
            "error_code": gating_error.error_code,
            "human_message": gating_error.human_message,
            "detail": parse_json(gating_error.detail)
        }
        
    return {
        "claim_id": claim.claim_id,
        "status": claim.status,
        "current_stage": claim.current_stage,
        "updated_at": claim.updated_at,
        "spans": spans_data,
        "decision": decision_data,
        "gating_error": gating_error_data
    }
