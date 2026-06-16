import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from backend.workflow.decision import DecisionSynthesisStage
from backend.workflow.entity import EntityExtractionStage
from backend.workflow.gating import DocumentGatingStage
from backend.workflow.orchestrator import ClaimMergeStage
from backend.workflow.reconciler import AmountReconciliationStage
from backend.workflow.vision_reader import VisionReaderStage
from backend.ai_platform.schemas import DocumentVisionOutput
from backend.database.connection import AsyncSessionLocal
from backend.database.models import ClaimDecisionModel
from backend.logging_config import get_logger
from backend.policy.engine import PolicyDecisionResult, PolicyEngine
from backend.tracing.store import TraceStore

logger = get_logger(__name__)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


async def complete_stage(
    claim_id: str,
    agent_name: str,
    *,
    stage_order: int,
    input_summary: dict[str, Any],
    output_summary: dict[str, Any],
    model_used: str = "none",
    confidence_delta: float | None = None,
    delay_seconds: float = 0.25,
) -> None:
    span_id = await TraceStore.start_span(
        claim_id,
        agent_name,
        stage_order=stage_order,
        input_summary=input_summary,
        model_used=model_used,
        current_stage=agent_name,
    )
    await asyncio.sleep(delay_seconds)
    await TraceStore.finish_span(
        span_id,
        status="SUCCESS",
        output_summary=output_summary,
        confidence_delta=confidence_delta,
        current_stage=None,
    )


async def write_decision(
    claim_id: str,
    *,
    policy_decision: PolicyDecisionResult,
) -> None:
    async with AsyncSessionLocal() as session:
        existing = await session.get(ClaimDecisionModel, claim_id)
        if existing:
            await session.delete(existing)
            await session.flush()

        session.add(
            ClaimDecisionModel(
                claim_id=claim_id,
                decision=policy_decision.decision,
                approved_amount=policy_decision.approved_amount,
                copay_deducted=policy_decision.copay_deducted,
                network_discount_applied=policy_decision.network_discount_applied,
                rejection_reasons=json.dumps(policy_decision.rejection_reasons, default=str),
                partial_items=json.dumps([item.model_dump() for item in policy_decision.partial_items], default=str) if policy_decision.partial_items else None,
                member_message=policy_decision.member_message,
                ops_summary=policy_decision.ops_summary,
                confidence_score=policy_decision.confidence_score,
                manual_review_note=policy_decision.manual_review_note,
                decided_at=utc_now_iso(),
            )
        )
        await session.commit()


async def run_claim_ingestion(
    claim_id: str,
    *,
    member_id: str,
    claim_category: str,
    treatment_date: str,
    claimed_amount: str,
    documents: list[dict[str, Any]],
    ytd_claims_amount: str | None = None,
    hospital_name: str | None = None,
    same_day_claim_count: int = 0,
) -> None:
    logger.info("Starting claim ingestion: claim_id=%s member_id=%s category=%s documents=%s", claim_id, member_id, claim_category, len(documents))

    # ------------------------------------
    #      initialize pipeline state
    # ------------------------------------
    vision_reader = VisionReaderStage()
    gating_stage = DocumentGatingStage()
    entity_stage = EntityExtractionStage()
    reconciliation_stage = AmountReconciliationStage()
    merge_stage = ClaimMergeStage()
    policy_engine = PolicyEngine()
    decision_stage = DecisionSynthesisStage()

    # ------------------------------------
    #      vision document reading
    # ------------------------------------
    try:
        classified_documents = await vision_reader.classify_documents(
            claim_id=claim_id,
            documents=documents,
            claim_category=claim_category,
        )
    except Exception:
        logger.exception("Vision classification failed; routing claim to manual review: claim_id=%s", claim_id)
        await TraceStore.update_claim_state(claim_id, status="MANUAL_REVIEW", current_stage=None)
        return

    # ------------------------------------
    #      document gating
    # ------------------------------------
    gating_result = await gating_stage.run(
        claim_id=claim_id,
        claim_category=claim_category,
        documents=classified_documents,
    )
    if not gating_result.passed:
        logger.info("Claim stopped by document gating: claim_id=%s error_code=%s", claim_id, gating_result.error_code)
        return
    logger.info("Document gating passed: claim_id=%s documents=%s", claim_id, len(classified_documents))

    # ------------------------------------
    #      entity extraction
    # ------------------------------------
    try:
        extraction = await entity_stage.extract(
            claim_id=claim_id,
            claim_category=claim_category,
            documents=classified_documents,
        )
    except Exception:
        logger.exception("Entity extraction failed; routing claim to manual review: claim_id=%s", claim_id)
        await TraceStore.update_claim_state(claim_id, status="MANUAL_REVIEW", current_stage=None)
        return

    # ------------------------------------
    #      amount reconciliation
    # ------------------------------------
    try:
        reconciliation = await reconciliation_stage.reconcile(
            claim_id=claim_id,
            claimed_amount=claimed_amount,
            extraction=extraction,
        )
    except Exception:
        logger.exception("Amount reconciliation failed; routing claim to manual review: claim_id=%s", claim_id)
        await TraceStore.update_claim_state(claim_id, status="MANUAL_REVIEW", current_stage=None)
        return

    # ------------------------------------
    #      orchestration and confidence
    # ------------------------------------
    try:
        merged_claim = await merge_stage.merge(
            claim_id=claim_id,
            documents=classified_documents,
            extraction=extraction,
            reconciliation=reconciliation,
            failed_agents=[],
        )
        if hospital_name and not merged_claim.hospital_name:
            merged_claim = merged_claim.model_copy(update={"hospital_name": hospital_name})
    except Exception:
        logger.exception("Orchestration failed; routing claim to manual review: claim_id=%s", claim_id)
        await TraceStore.update_claim_state(claim_id, status="MANUAL_REVIEW", current_stage=None)
        return

    # ------------------------------------
    #      confidence gate
    # ------------------------------------
    if merged_claim.extraction_confidence < 0.65:
        logger.info("Extraction confidence below threshold; routing to manual review: claim_id=%s confidence=%s", claim_id, merged_claim.extraction_confidence)
        await TraceStore.update_claim_state(claim_id, status="MANUAL_REVIEW", current_stage=None)
        return

    # ------------------------------------
    #      policy evaluation
    # ------------------------------------
    try:
        policy_decision = await policy_engine.evaluate(
            claim_id=claim_id,
            member_id=member_id,
            claim_category=claim_category,
            treatment_date=treatment_date,
            merged_claim=merged_claim,
            ytd_claims_amount=ytd_claims_amount,
            same_day_claim_count=same_day_claim_count,
        )
    except Exception:
        logger.exception("Policy evaluation failed; routing claim to manual review: claim_id=%s", claim_id)
        await TraceStore.update_claim_state(claim_id, status="MANUAL_REVIEW", current_stage=None)
        return

    # ------------------------------------
    #      decision synthesis
    # ------------------------------------
    policy_decision = await decision_stage.synthesize(
        claim_id=claim_id,
        policy_decision=policy_decision,
        merged_claim=merged_claim,
    )

    # ------------------------------------
    #      persist final decision
    # ------------------------------------
    await write_decision(
        claim_id,
        policy_decision=policy_decision,
    )

    # ------------------------------------
    #      finalize claim
    # ------------------------------------
    await complete_stage(
        claim_id,
        "final",
        stage_order=8,
        input_summary={"claim_id": claim_id},
        output_summary={"decision": policy_decision.decision},
        delay_seconds=0.08,
    )
    final_status = "MANUAL_REVIEW" if policy_decision.decision == "MANUAL_REVIEW" else "DECIDED"
    await TraceStore.update_claim_state(claim_id, status=final_status, current_stage=None)
    logger.info("Claim ingestion completed: claim_id=%s status=%s", claim_id, final_status)