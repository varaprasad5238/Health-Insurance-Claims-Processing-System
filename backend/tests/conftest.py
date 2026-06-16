from __future__ import annotations

from pathlib import Path

import pytest

from backend.ai_platform.schemas import DocumentVisionOutput, LineItemOutput, StructuredExtractionOutput
from backend.policy.loader import load_policy
from backend.workflow.orchestrator import MergedClaimResult
from backend.workflow.reconciler import AmountReconciliationResult


@pytest.fixture(scope="session")
def assignment_policy():
    policy_path = Path(__file__).resolve().parents[2] / "assignment" / "policy_terms.json"
    return load_policy(str(policy_path))


def line_item(description: str, amount: str, coverage_hint: str = "UNCERTAIN", coverage_reason: str | None = None) -> LineItemOutput:
    return LineItemOutput(
        description=description,
        amount=amount,
        coverage_hint=coverage_hint,
        coverage_reason=coverage_reason,
    )


@pytest.fixture
def make_merged_claim():
    def factory(
        *,
        amount: str = "1000.00",
        diagnosis: str = "Viral Fever",
        hospital_name: str | None = None,
        items: list[LineItemOutput] | None = None,
        confidence: float = 0.91,
    ) -> MergedClaimResult:
        return MergedClaimResult(
            patient_name="Rajesh Kumar",
            doctor_name="Dr. Arun Sharma",
            doctor_registration="KA/45678/2015",
            diagnosis_primary=diagnosis,
            treatment_date="2024-11-01",
            hospital_name=hospital_name,
            line_items=items or [line_item("Consultation Fee", amount, "COVERED")],
            extracted_total_amount=amount,
            claimed_amount=amount,
            payable_basis_amount=amount,
            extraction_confidence=confidence,
        )

    return factory


def vision_document(
    document_type: str,
    *,
    patient_name: str | None = "Rajesh Kumar",
    readability: float = 0.9,
    confidence: float = 0.92,
) -> DocumentVisionOutput:
    return DocumentVisionOutput(
        document_type=document_type,
        confidence=confidence,
        readability=readability,
        patient_name_raw=patient_name,
        quality_flags=[],
        transcript="Patient: Rajesh Kumar\nTotal Amount: 1000.00",
        source_file_name=f"{document_type.lower()}.png",
    )


def extraction_output(
    *,
    total_amount: str | None = "1000.00",
    items: list[LineItemOutput] | None = None,
    missing_fields: list[str] | None = None,
    confidences: dict[str, float] | None = None,
) -> StructuredExtractionOutput:
    return StructuredExtractionOutput(
        patient_name="Rajesh Kumar",
        doctor_name="Dr. Arun Sharma",
        doctor_registration="KA/45678/2015",
        diagnosis_primary="Viral Fever",
        treatment_date="2024-11-01",
        hospital_name="Apollo Hospitals",
        line_items=[line_item("Consultation Fee", "1000.00", "COVERED")] if items is None else items,
        total_amount=total_amount,
        field_confidences=confidences or {"patient_name": 0.9, "total_amount": 0.95, "diagnosis_primary": 0.8},
        missing_fields=missing_fields or [],
    )


def reconciliation_result(
    *,
    claimed_amount: str = "1000.00",
    payable_basis_amount: str = "1000.00",
    discrepancy_flags: list | None = None,
    fraud_indicators: list | None = None,
) -> AmountReconciliationResult:
    return AmountReconciliationResult(
        bill_total_extracted=payable_basis_amount,
        line_items_sum=payable_basis_amount,
        claimed_amount=claimed_amount,
        payable_basis_amount=payable_basis_amount,
        discrepancy_flags=discrepancy_flags or [],
        fraud_indicators=fraud_indicators or [],
        agent_status="PARTIAL" if discrepancy_flags else "SUCCESS",
    )
