from __future__ import annotations

import pytest

from backend.ai_platform.schemas import DecisionMessageOutput, DocumentVisionListOutput, LLMResult, StructuredExtractionOutput
from backend.policy.engine import PolicyDecisionResult
from backend.tasks import ingestion
from backend.tests.conftest import extraction_output, reconciliation_result, vision_document
from backend.workflow.decision import DecisionSynthesisStage
from backend.workflow.entity import EntityExtractionStage
from backend.workflow.orchestrator import ClaimMergeStage
from backend.workflow.reconciler import AmountReconciliationStage
from backend.workflow.vision_reader import VisionReaderStage, truncate_text


class FakeTraceStore:
    started = []
    finished = []
    updates = []

    @classmethod
    def reset(cls):
        cls.started = []
        cls.finished = []
        cls.updates = []

    @classmethod
    async def start_span(cls, claim_id, agent_name, **kwargs):
        cls.started.append((claim_id, agent_name, kwargs))
        return f"span-{agent_name}"

    @classmethod
    async def finish_span(cls, span_id, **kwargs):
        cls.finished.append((span_id, kwargs))

    @classmethod
    async def update_claim_state(cls, claim_id, **kwargs):
        cls.updates.append((claim_id, kwargs))


class FakeLLMPlatform:
    def __init__(self, raw_text: str, *, model: str = "fake-model"):
        self.raw_text = raw_text
        self.model = model

    async def get_llm_response(self, **kwargs):
        return LLMResult(model=self.model, raw_text=self.raw_text, latency_ms=1, input_tokens=1, output_tokens=1)


@pytest.fixture(autouse=True)
def reset_fake_trace():
    FakeTraceStore.reset()


@pytest.mark.asyncio
async def test_vision_reader_classifies_documents(monkeypatch):
    payload = DocumentVisionListOutput(documents=[vision_document("PRESCRIPTION")]).model_dump_json()
    monkeypatch.setattr("backend.workflow.vision_reader.TraceStore", FakeTraceStore)
    monkeypatch.setattr("backend.workflow.vision_reader.get_llm_platform", lambda: FakeLLMPlatform(payload))

    result = await VisionReaderStage().classify_documents(
        claim_id="CLM-1",
        claim_category="CONSULTATION",
        documents=[{"file_name": "rx.png", "content_type": "image/png", "raw_bytes": b"img", "size_bytes": 3}],
    )

    assert result[0].document_type == "PRESCRIPTION"
    assert FakeTraceStore.finished[0][1]["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_vision_reader_validates_document_count():
    with pytest.raises(ValueError, match="At least one document"):
        await VisionReaderStage().classify_documents(claim_id="CLM-1", claim_category="CONSULTATION", documents=[])
    with pytest.raises(ValueError, match="maximum of 4"):
        await VisionReaderStage().classify_documents(
            claim_id="CLM-1",
            claim_category="CONSULTATION",
            documents=[{"file_name": str(index), "content_type": "image/png"} for index in range(5)],
        )


def test_truncate_text_short_long_and_none():
    assert truncate_text(None) is None
    assert truncate_text("short", limit=10) == "short"
    assert truncate_text("x" * 12, limit=5) == "xxxxx...[truncated]"


@pytest.mark.asyncio
async def test_entity_stage_extracts_and_finishes_span(monkeypatch):
    extraction = extraction_output().model_dump_json()
    monkeypatch.setattr("backend.workflow.entity.TraceStore", FakeTraceStore)
    monkeypatch.setattr("backend.workflow.entity.get_policy", lambda: type("Policy", (), {"exclusions": type("Exclusions", (), {"conditions": []})()})())
    monkeypatch.setattr("backend.workflow.entity.get_llm_platform", lambda: FakeLLMPlatform(extraction))

    result = await EntityExtractionStage().extract(claim_id="CLM-1", claim_category="CONSULTATION", documents=[vision_document("PRESCRIPTION")])

    assert result.patient_name == "Rajesh Kumar"
    assert FakeTraceStore.finished[0][1]["output_summary"]["fields_extracted"] > 0


@pytest.mark.asyncio
async def test_reconciler_and_merge_async_wrappers(monkeypatch):
    monkeypatch.setattr("backend.workflow.reconciler.TraceStore", FakeTraceStore)
    reconciliation = await AmountReconciliationStage().reconcile(
        claim_id="CLM-1",
        claimed_amount="1000.00",
        extraction=extraction_output(),
    )
    monkeypatch.setattr("backend.workflow.orchestrator.TraceStore", FakeTraceStore)
    merged = await ClaimMergeStage().merge(
        claim_id="CLM-1",
        documents=[vision_document("PRESCRIPTION")],
        extraction=extraction_output(),
        reconciliation=reconciliation,
        failed_agents=[],
    )

    assert reconciliation.agent_status == "SUCCESS"
    assert merged.payable_basis_amount == "1000.00"


@pytest.mark.asyncio
async def test_decision_synthesis_success_and_fallback(monkeypatch, make_merged_claim):
    policy_decision = PolicyDecisionResult(
        decision="APPROVED",
        approved_amount="900.00",
        member_message="template",
        ops_summary="template ops",
        confidence_score=0.9,
    )
    payload = DecisionMessageOutput(member_message="synthesized", ops_summary="synth ops").model_dump_json()
    monkeypatch.setattr("backend.workflow.decision.TraceStore", FakeTraceStore)
    monkeypatch.setattr("backend.workflow.decision.get_llm_platform", lambda: FakeLLMPlatform(payload))

    synthesized = await DecisionSynthesisStage().synthesize(
        claim_id="CLM-1",
        policy_decision=policy_decision,
        merged_claim=make_merged_claim(),
    )

    assert synthesized.member_message == "synthesized"

    class BrokenPlatform:
        async def get_llm_response(self, **kwargs):
            raise RuntimeError("down")

    monkeypatch.setattr("backend.workflow.decision.get_llm_platform", lambda: BrokenPlatform())
    fallback = await DecisionSynthesisStage().synthesize(
        claim_id="CLM-2",
        policy_decision=policy_decision,
        merged_claim=make_merged_claim(),
    )
    assert fallback.member_message == "template"


class FakeVisionReader:
    async def classify_documents(self, **kwargs):
        return [vision_document("PRESCRIPTION"), vision_document("HOSPITAL_BILL")]


class FakeGatingStage:
    async def run(self, **kwargs):
        return type("Gating", (), {"passed": True})()


class FakeEntityStage:
    async def extract(self, **kwargs):
        return extraction_output()


class FakeReconciliationStage:
    async def reconcile(self, **kwargs):
        return reconciliation_result()


class FakeMergeStage:
    async def merge(self, **kwargs):
        return kwargs["reconciliation"].model_copy(update={}) and kwargs.get("merged") or __import__("backend.workflow.orchestrator", fromlist=["MergedClaimResult"]).MergedClaimResult(
            patient_name="Rajesh Kumar",
            diagnosis_primary="Viral Fever",
            hospital_name=None,
            line_items=[],
            extracted_total_amount="1000.00",
            claimed_amount="1000.00",
            payable_basis_amount="1000.00",
            extraction_confidence=0.9,
        )


class LowConfidenceMergeStage(FakeMergeStage):
    async def merge(self, **kwargs):
        merged = await super().merge(**kwargs)
        return merged.model_copy(update={"extraction_confidence": 0.5})


class FakePolicyEngine:
    async def evaluate(self, **kwargs):
        return PolicyDecisionResult(
            decision="APPROVED",
            approved_amount="1000.00",
            member_message="approved",
            ops_summary="ok",
            confidence_score=0.9,
        )


class FakeDecisionStage:
    async def synthesize(self, **kwargs):
        return kwargs["policy_decision"]


@pytest.mark.asyncio
async def test_run_claim_ingestion_success_and_low_confidence(monkeypatch):
    writes = []
    completes = []
    monkeypatch.setattr(ingestion, "TraceStore", FakeTraceStore)
    monkeypatch.setattr(ingestion, "VisionReaderStage", FakeVisionReader)
    monkeypatch.setattr(ingestion, "DocumentGatingStage", FakeGatingStage)
    monkeypatch.setattr(ingestion, "EntityExtractionStage", FakeEntityStage)
    monkeypatch.setattr(ingestion, "AmountReconciliationStage", FakeReconciliationStage)
    monkeypatch.setattr(ingestion, "ClaimMergeStage", FakeMergeStage)
    monkeypatch.setattr(ingestion, "PolicyEngine", FakePolicyEngine)
    monkeypatch.setattr(ingestion, "DecisionSynthesisStage", FakeDecisionStage)
    monkeypatch.setattr(ingestion, "write_decision", lambda claim_id, policy_decision: writes.append((claim_id, policy_decision)))

    async def fake_complete_stage(*args, **kwargs):
        completes.append((args, kwargs))

    async def fake_write_decision(claim_id, *, policy_decision):
        writes.append((claim_id, policy_decision.decision))

    monkeypatch.setattr(ingestion, "complete_stage", fake_complete_stage)
    monkeypatch.setattr(ingestion, "write_decision", fake_write_decision)

    await ingestion.run_claim_ingestion(
        "CLM-1",
        member_id="EMP001",
        claim_category="CONSULTATION",
        treatment_date="2024-11-01",
        claimed_amount="1000.00",
        hospital_name="Apollo",
        documents=[{"file_name": "rx.png"}],
    )

    assert writes == [("CLM-1", "APPROVED")]
    assert completes
    assert FakeTraceStore.updates[-1][1]["status"] == "DECIDED"

    monkeypatch.setattr(ingestion, "ClaimMergeStage", LowConfidenceMergeStage)
    await ingestion.run_claim_ingestion(
        "CLM-2",
        member_id="EMP001",
        claim_category="CONSULTATION",
        treatment_date="2024-11-01",
        claimed_amount="1000.00",
        documents=[{"file_name": "rx.png"}],
    )
    assert FakeTraceStore.updates[-1][1]["status"] == "MANUAL_REVIEW"


@pytest.mark.asyncio
async def test_run_claim_ingestion_stops_on_vision_and_gating_failures(monkeypatch):
    class BrokenVisionReader:
        async def classify_documents(self, **kwargs):
            raise RuntimeError("vision failed")

    class FailedGatingStage:
        async def run(self, **kwargs):
            return type("Gating", (), {"passed": False, "error_code": "MISSING_REQUIRED"})()

    monkeypatch.setattr(ingestion, "TraceStore", FakeTraceStore)
    monkeypatch.setattr(ingestion, "VisionReaderStage", BrokenVisionReader)
    await ingestion.run_claim_ingestion(
        "CLM-3",
        member_id="EMP001",
        claim_category="CONSULTATION",
        treatment_date="2024-11-01",
        claimed_amount="1000.00",
        documents=[{"file_name": "rx.png"}],
    )
    assert FakeTraceStore.updates[-1][1]["status"] == "MANUAL_REVIEW"

    monkeypatch.setattr(ingestion, "VisionReaderStage", FakeVisionReader)
    monkeypatch.setattr(ingestion, "DocumentGatingStage", FailedGatingStage)
    await ingestion.run_claim_ingestion(
        "CLM-4",
        member_id="EMP001",
        claim_category="CONSULTATION",
        treatment_date="2024-11-01",
        claimed_amount="1000.00",
        documents=[{"file_name": "rx.png"}],
    )
    assert FakeTraceStore.updates[-1][0] == "CLM-3"


def test_ingestion_money_and_time_helpers():
    assert ingestion.money(__import__("decimal").Decimal("1.235")) == "1.24"
    assert "T" in ingestion.utc_now_iso()
