import json
import uuid
from datetime import datetime, timezone
from typing import Any, Sequence

from fastapi import BackgroundTasks, HTTPException, UploadFile
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ai_platform.metrics import normalize_agent_name
from backend.api.test_suite_utils import (
    TEST_SUITE_ROOT,
    content_type_for,
    find_assignment_test_case,
    load_assignment_test_cases,
    none_or_str,
    suite_documents_for,
    suite_manifest_for,
)
from backend.database.models import ClaimDecisionModel, ClaimModel, GatingErrorModel, LLMMetricModel, MemberModel, PolicyModel, TraceSpanModel
from backend.policy.loader import get_policy
from backend.services.document_preprocessor import prepare_for_vision_call
from backend.storage.local import save_uploaded_document
from backend.tasks.ingestion import run_claim_ingestion


async def list_policies_and_members(db: AsyncSession) -> dict[str, Any]:
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


def get_policy_options() -> dict[str, Any]:
    policy = get_policy()
    return {
        "network_hospitals": policy.network_hospitals,
        "minimum_claim_amount": policy.submission_rules.minimum_claim_amount,
        "per_claim_limit": policy.coverage.per_claim_limit,
        "claim_categories": list(policy.document_requirements.keys()),
    }


async def get_llm_metrics_summary(db: AsyncSession) -> dict[str, Any]:
    metrics_result = await db.execute(select(LLMMetricModel))
    metrics = metrics_result.scalars().all()
    total_calls = len(metrics)
    successful_calls = sum(1 for metric in metrics if metric.status == "SUCCESS")
    failed_calls = total_calls - successful_calls
    fallback_calls = sum(1 for metric in metrics if metric.is_fallback == "true")
    latencies = [metric.latency_ms for metric in metrics if metric.latency_ms is not None]
    avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0
    total_input_tokens = sum(metric.input_tokens or 0 for metric in metrics)
    total_output_tokens = sum(metric.output_tokens or 0 for metric in metrics)
    total_tokens = sum(metric.total_tokens or 0 for metric in metrics)

    by_provider: dict[str, int] = {}
    by_agent: dict[str, int] = {}
    by_error: dict[str, int] = {}
    tokens_by_provider: dict[str, dict[str, int]] = {}
    tokens_by_agent: dict[str, dict[str, int]] = {}
    for metric in metrics:
        agent_name = normalize_agent_name(metric.agent_name)
        by_provider[metric.provider] = by_provider.get(metric.provider, 0) + 1
        by_agent[agent_name] = by_agent.get(agent_name, 0) + 1
        tokens_by_provider.setdefault(metric.provider, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0})
        tokens_by_provider[metric.provider]["input_tokens"] += metric.input_tokens or 0
        tokens_by_provider[metric.provider]["output_tokens"] += metric.output_tokens or 0
        tokens_by_provider[metric.provider]["total_tokens"] += metric.total_tokens or 0
        tokens_by_agent.setdefault(agent_name, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0})
        tokens_by_agent[agent_name]["input_tokens"] += metric.input_tokens or 0
        tokens_by_agent[agent_name]["output_tokens"] += metric.output_tokens or 0
        tokens_by_agent[agent_name]["total_tokens"] += metric.total_tokens or 0
        if metric.error_category:
            by_error[metric.error_category] = by_error.get(metric.error_category, 0) + 1

    return {
        "total_calls": total_calls,
        "successful_calls": successful_calls,
        "failed_calls": failed_calls,
        "fallback_calls": fallback_calls,
        "success_rate": round(successful_calls / total_calls, 3) if total_calls else 0,
        "fallback_rate": round(fallback_calls / total_calls, 3) if total_calls else 0,
        "avg_latency_ms": avg_latency,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens": total_tokens,
        "by_provider": by_provider,
        "by_agent": by_agent,
        "tokens_by_provider": tokens_by_provider,
        "tokens_by_agent": tokens_by_agent,
        "by_error": by_error,
    }


async def get_recent_llm_metrics(db: AsyncSession, *, limit: int) -> dict[str, Any]:
    result = await db.execute(select(LLMMetricModel).order_by(desc(LLMMetricModel.created_at)).limit(limit))
    return {
        "metrics": [
            {
                "metric_id": metric.metric_id,
                "claim_id": metric.claim_id,
                "agent_name": normalize_agent_name(metric.agent_name),
                "stage_name": normalize_agent_name(metric.agent_name),
                "provider": metric.provider,
                "model": metric.model,
                "is_fallback": metric.is_fallback == "true",
                "primary_error": metric.primary_error,
                "latency_ms": metric.latency_ms,
                "status": metric.status,
                "error_category": metric.error_category,
                "input_tokens": metric.input_tokens,
                "output_tokens": metric.output_tokens,
                "total_tokens": metric.total_tokens,
                "created_at": metric.created_at,
            }
            for metric in result.scalars().all()
        ]
    }


async def submit_claim(
    *,
    background_tasks: BackgroundTasks,
    db: AsyncSession,
    member_id: str,
    claim_category: str,
    treatment_date: str,
    claimed_amount: str,
    ytd_claims_amount: str | None,
    hospital_name: str | None,
    documents: Sequence[UploadFile],
) -> dict[str, Any]:
    claim_id = f"CLM-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    now_iso = datetime.now(timezone.utc).isoformat()
    member = await db.get(MemberModel, member_id)
    policy = await db.get(PolicyModel, "PLUM_GHI_2024")
    if not member:
        raise HTTPException(status_code=400, detail=f"Unknown member_id: {member_id}")
    if not policy:
        raise HTTPException(status_code=500, detail="Policy PLUM_GHI_2024 is not seeded")

    document_payloads = await prepare_uploaded_document_payloads(claim_id=claim_id, documents=documents)
    new_claim = ClaimModel(
        claim_id=claim_id,
        member_id=member_id,
        policy_id="PLUM_GHI_2024",
        claim_category=claim_category,
        treatment_date=treatment_date,
        submission_date=now_iso,
        claimed_amount=claimed_amount,
        hospital_name=hospital_name or None,
        status="PROCESSING",
        current_stage="vision_read_doc_1",
        trace_id=f"trace-{claim_id}",
        created_at=now_iso,
        updated_at=now_iso,
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
        ytd_claims_amount=ytd_claims_amount,
        hospital_name=hospital_name,
        documents=document_payloads,
    )

    return {"claim_id": claim_id, "status": "PROCESSING", "trace_id": new_claim.trace_id}


def list_test_suite_cases() -> dict[str, Any]:
    cases = []
    for test_case in load_assignment_test_cases():
        case_id = test_case["case_id"]
        expected = test_case.get("expected", {})
        manifest = suite_manifest_for(case_id) or {}
        documents = []
        documents_dir = TEST_SUITE_ROOT / case_id / "documents"
        if documents_dir.exists():
            documents = [str(path.relative_to(TEST_SUITE_ROOT / case_id)).replace("\\", "/") for path in sorted(documents_dir.iterdir()) if path.is_file()]
        cases.append(
            {
                "case_id": case_id,
                "case_name": test_case.get("case_name"),
                "description": test_case.get("description"),
                "member_id": test_case.get("input", {}).get("member_id"),
                "claim_category": test_case.get("input", {}).get("claim_category"),
                "claimed_amount": test_case.get("input", {}).get("claimed_amount"),
                "expected_decision": expected.get("decision"),
                "expected_approved_amount": expected.get("approved_amount"),
                "documents": documents,
                "test_context": manifest.get("test_context", {}),
                "api_mode_note": "Runs through the normal upload ingestion path using test_suite document artifacts.",
            }
        )
    return {"cases": cases}


async def run_test_suite_case(*, case_id: str, background_tasks: BackgroundTasks, db: AsyncSession) -> dict[str, Any]:
    test_case = find_assignment_test_case(case_id)
    case_id = test_case["case_id"]
    case_input = test_case["input"]
    member_id = case_input["member_id"]
    policy_id = case_input.get("policy_id") or "PLUM_GHI_2024"

    member = await db.get(MemberModel, member_id)
    policy = await db.get(PolicyModel, policy_id)
    if not member:
        raise HTTPException(status_code=400, detail=f"Unknown member_id in {case_id}: {member_id}")
    if not policy:
        raise HTTPException(status_code=500, detail=f"Policy {policy_id} is not seeded")

    claim_id = f"CLM-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{case_id}-{uuid.uuid4().hex[:4].upper()}"
    now_iso = datetime.now(timezone.utc).isoformat()
    document_payloads = prepare_suite_document_payloads(claim_id=claim_id, case_id=case_id)

    new_claim = ClaimModel(
        claim_id=claim_id,
        member_id=member_id,
        policy_id=policy_id,
        claim_category=case_input["claim_category"],
        treatment_date=case_input["treatment_date"],
        submission_date=now_iso,
        claimed_amount=str(case_input["claimed_amount"]),
        hospital_name=none_or_str(case_input.get("hospital_name")),
        status="PROCESSING",
        current_stage="vision_read_doc_1",
        trace_id=f"trace-{claim_id}",
        created_at=now_iso,
        updated_at=now_iso,
    )
    db.add(new_claim)
    await db.commit()

    same_day_claim_count = len(case_input.get("claims_history", []))
    background_tasks.add_task(
        run_claim_ingestion,
        claim_id,
        member_id=member_id,
        claim_category=case_input["claim_category"],
        treatment_date=case_input["treatment_date"],
        claimed_amount=str(case_input["claimed_amount"]),
        ytd_claims_amount=none_or_str(case_input.get("ytd_claims_amount")),
        hospital_name=none_or_str(case_input.get("hospital_name")),
        same_day_claim_count=same_day_claim_count,
        documents=document_payloads,
    )

    manifest = suite_manifest_for(case_id)
    return {
        "case_id": case_id,
        "claim_id": claim_id,
        "status": "PROCESSING",
        "trace_id": new_claim.trace_id,
        "expected": test_case.get("expected", {}),
        "same_day_claim_count": same_day_claim_count,
        "simulation_note": manifest.get("test_context") if manifest else None,
    }


async def list_claims(
    *,
    db: AsyncSession,
    page: int,
    page_size: int,
    status: str | None,
    date: str | None,
    month: int | None,
    year: int | None,
) -> dict[str, Any]:
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
        ],
    }


async def get_claim_status(*, claim_id: str, db: AsyncSession) -> dict[str, Any]:
    result = await db.execute(select(ClaimModel).where(ClaimModel.claim_id == claim_id))
    claim = result.scalars().first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    spans_result = await db.execute(select(TraceSpanModel).where(TraceSpanModel.claim_id == claim_id).order_by(TraceSpanModel.started_at))
    spans = spans_result.scalars().all()
    decision_result = await db.execute(select(ClaimDecisionModel).where(ClaimDecisionModel.claim_id == claim_id))
    decision = decision_result.scalars().first()
    gating_error_result = await db.execute(select(GatingErrorModel).where(GatingErrorModel.claim_id == claim_id))
    gating_error = gating_error_result.scalars().first()

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
            "manual_review_note": decision.manual_review_note,
        }

    gating_error_data = None
    if gating_error:
        gating_error_data = {
            "error_code": gating_error.error_code,
            "human_message": gating_error.human_message,
            "detail": parse_json(gating_error.detail),
        }

    return {
        "claim_id": claim.claim_id,
        "claimed_amount": claim.claimed_amount,
        "claim_category": claim.claim_category,
        "member_id": claim.member_id,
        "status": claim.status,
        "current_stage": claim.current_stage,
        "updated_at": claim.updated_at,
        "spans": [
            {
                "span_id": span.span_id,
                "agent_name": span.agent_name,
                "stage_name": span.agent_name,
                "stage_order": span.stage_order,
                "status": span.status,
                "elapsed_ms": span.elapsed_ms,
                "started_at": span.started_at,
                "ended_at": span.ended_at,
                "input_summary": parse_json(span.input_summary),
                "output_summary": parse_json(span.output_summary),
                "confidence_delta": span.confidence_delta,
                "errors": parse_json(span.errors) or [],
                "model_used": span.model_used,
            }
            for span in spans
        ],
        "decision": decision_data,
        "gating_error": gating_error_data,
    }


async def prepare_uploaded_document_payloads(*, claim_id: str, documents: Sequence[UploadFile]) -> list[dict[str, Any]]:
    document_payloads: list[dict[str, Any]] = []
    for index, document in enumerate(documents, start=1):
        raw_bytes = await document.read()
        file_name = document.filename or f"document_{index}"
        content_type = document.content_type or "application/octet-stream"
        saved_path = save_uploaded_document(claim_id=claim_id, file_name=file_name, content=raw_bytes, index=index)
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
    return document_payloads


def prepare_suite_document_payloads(*, claim_id: str, case_id: str) -> list[dict[str, Any]]:
    document_payloads: list[dict[str, Any]] = []
    for upload_index, document_path in enumerate(suite_documents_for(case_id), start=1):
        raw_bytes = document_path.read_bytes()
        content_type = content_type_for(document_path)
        saved_path = save_uploaded_document(claim_id=claim_id, file_name=document_path.name, content=raw_bytes, index=upload_index)
        page_images = prepare_for_vision_call(str(saved_path), content_type)
        for page_index, image_bytes in enumerate(page_images, start=1):
            document_payloads.append(
                {
                    "file_name": document_path.name,
                    "content_type": "image/png" if content_type == "application/pdf" else content_type,
                    "raw_bytes": image_bytes,
                    "size_bytes": len(image_bytes),
                    "stored_path": str(saved_path),
                    "source_page_range": str(page_index),
                    "source_upload_index": upload_index,
                    "suite_case_id": case_id,
                }
            )
    return document_payloads


def parse_json(value: str | None) -> Any | None:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value
