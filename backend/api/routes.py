import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, File, UploadFile, Form, Depends, BackgroundTasks, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import desc, func, select
from typing import Any, List

from backend.database.connection import AsyncSessionLocal
from backend.database.models import ClaimModel, TraceSpanModel, ClaimDecisionModel, GatingErrorModel, MemberModel, PolicyModel
from backend.services.document_preprocessor import prepare_for_vision_call
from backend.storage.local import save_uploaded_document
from backend.tasks.ingestion import run_claim_ingestion

router = APIRouter(prefix="/api/claims", tags=["claims"])

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


@router.get("/policies/members")
async def list_policies_and_members(db: AsyncSession = Depends(get_db)):
    policies_result = await db.execute(select(PolicyModel).order_by(PolicyModel.policy_id))
    members_result = await db.execute(select(MemberModel).order_by(MemberModel.policy_id, MemberModel.member_id))
    members_by_policy: dict[str, list[MemberModel]] = {}
    for member in members_result.scalars().all():
        members_by_policy.setdefault(member.policy_id, []).append(member)

    return {
        "policies": [
            {
                "policy_id": policy.policy_id,
                "policy_name": policy.policy_name,
                "insurer": policy.insurer,
                "company_name": policy.company_name,
                "status": policy.status,
                "full_pledged_amount": policy.full_pledged_amount,
                "annual_opd_limit": policy.annual_opd_limit,
                "remaining_opd_limit": policy.remaining_opd_limit,
                "family_floater_limit": policy.family_floater_limit,
                "family_floater_remaining": policy.family_floater_remaining,
                "members": [
                    {
                        "member_id": member.member_id,
                        "name": member.name,
                        "relationship": member.relationship,
                        "primary_member_id": member.primary_member_id,
                        "join_date": member.join_date,
                        "annual_opd_limit": member.annual_opd_limit,
                        "ytd_claimed_amount": member.ytd_claimed_amount,
                        "remaining_opd_limit": member.remaining_opd_limit,
                    }
                    for member in members_by_policy.get(policy.policy_id, [])
                ],
            }
            for policy in policies_result.scalars().all()
        ]
    }

@router.post("/")
async def submit_claim(
    background_tasks: BackgroundTasks,
    member_id: str = Form(...),
    claim_category: str = Form(...),
    treatment_date: str = Form(...),
    claimed_amount: str = Form(...),
    documents: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db)
):
    claim_id = f"CLM-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    now_iso = datetime.now(timezone.utc).isoformat()
    member = await db.get(MemberModel, member_id)
    policy = await db.get(PolicyModel, "PLUM_GHI_2024")
    if not member:
        raise HTTPException(status_code=400, detail=f"Unknown member_id: {member_id}")
    if not policy:
        raise HTTPException(status_code=500, detail="Policy PLUM_GHI_2024 is not seeded")
    
    document_payloads: list[dict[str, Any]] = []
    for index, document in enumerate(documents, start=1):
        raw_bytes = await document.read()
        file_name = document.filename or f"document_{index}"
        content_type = document.content_type or "application/octet-stream"
        saved_path = save_uploaded_document(
            claim_id=claim_id,
            file_name=file_name,
            content=raw_bytes,
            index=index,
        )
        page_images = prepare_for_vision_call(str(saved_path), content_type)
        for page_index, image_bytes in enumerate(page_images, start=1):
            document_payloads.append(
                {
                    "file_name": file_name,
                    "content_type": "image/png" if content_type == "application/pdf" else content_type,
                    "raw_bytes": image_bytes,
                    "size_bytes": len(image_bytes),
                    "stored_path": str(saved_path),
                    "source_page_range": str(page_index),
                    "source_upload_index": index,
                }
            )

    new_claim = ClaimModel(
        claim_id=claim_id,
        member_id=member_id,
        policy_id="PLUM_GHI_2024",
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

    background_tasks.add_task(
        run_claim_ingestion,
        claim_id,
        member_id=member_id,
        claim_category=claim_category,
        treatment_date=treatment_date,
        claimed_amount=claimed_amount,
        documents=document_payloads,
    )
    
    return {
        "claim_id": claim_id,
        "status": "PROCESSING",
        "trace_id": new_claim.trace_id
    }

@router.get("/")
async def list_claims(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    status: str | None = None,
    date: str | None = None,
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2000, le=2100),
):
    filters = []
    if status:
        filters.append(ClaimModel.status == status)
    if date:
        filters.append(ClaimModel.created_at.like(f"{date}%"))
    if year:
        if month:
            filters.append(ClaimModel.created_at.like(f"{year:04d}-{month:02d}%"))
        else:
            filters.append(ClaimModel.created_at.like(f"{year:04d}%"))

    base_query = select(ClaimModel).where(*filters).order_by(desc(ClaimModel.updated_at))
    total_result = await db.execute(select(func.count()).select_from(ClaimModel).where(*filters))
    total = total_result.scalar_one()
    claims_result = await db.execute(base_query.offset((page - 1) * page_size).limit(page_size))
    claims = claims_result.scalars().all()

    decision_result = await db.execute(select(ClaimDecisionModel))
    decisions = {decision.claim_id: decision for decision in decision_result.scalars().all()}

    member_result = await db.execute(select(MemberModel))
    members = {member.member_id: member for member in member_result.scalars().all()}

    policy_result = await db.execute(select(PolicyModel))
    policies = {policy.policy_id: policy for policy in policy_result.scalars().all()}

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": max((total + page_size - 1) // page_size, 1),
        "claims": [
            {
                "claim_id": claim.claim_id,
                "member_id": claim.member_id,
                "member_name": members[claim.member_id].name if claim.member_id in members else None,
                "member_relationship": members[claim.member_id].relationship if claim.member_id in members else None,
                "member_remaining_opd_limit": members[claim.member_id].remaining_opd_limit if claim.member_id in members else None,
                "policy_id": claim.policy_id,
                "policy_name": policies[claim.policy_id].policy_name if claim.policy_id in policies else None,
                "policy_remaining_opd_limit": policies[claim.policy_id].remaining_opd_limit if claim.policy_id in policies else None,
                "policy_full_pledged_amount": policies[claim.policy_id].full_pledged_amount if claim.policy_id in policies else None,
                "claim_category": claim.claim_category,
                "claimed_amount": claim.claimed_amount,
                "status": claim.status,
                "current_stage": claim.current_stage,
                "updated_at": claim.updated_at,
                "created_at": claim.created_at,
                "decision": decisions[claim.claim_id].decision if claim.claim_id in decisions else None,
                "approved_amount": decisions[claim.claim_id].approved_amount if claim.claim_id in decisions else None,
                "confidence_score": decisions[claim.claim_id].confidence_score if claim.claim_id in decisions else None,
            }
            for claim in claims
        ]
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
            "input_summary": parse_json(s.input_summary),
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
