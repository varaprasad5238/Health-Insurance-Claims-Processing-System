from __future__ import annotations

from decimal import Decimal

import pytest

from backend.tests.conftest import extraction_output, line_item, reconciliation_result, vision_document
from backend.workflow.entity import average_confidence, count_extracted_fields
from backend.workflow.gating import (
    DocumentGatingStage,
    duplicate_document_types,
    first_patient_mismatch,
    friendly_doc_type,
    levenshtein_distance,
    missing_docs_message,
    missing_required_docs,
    normalize_name,
)
from backend.workflow.orchestrator import (
    ClaimMergeStage,
    compute_document_confidence,
    compute_entity_confidence,
    compute_extraction_confidence,
    compute_reconciliation_confidence,
)
from backend.workflow.reconciler import AmountReconciliationStage, parse_money


def test_gating_passes_when_required_documents_and_patient_match():
    stage = DocumentGatingStage()
    documents = [vision_document("PRESCRIPTION"), vision_document("HOSPITAL_BILL")]

    outcome = stage.evaluate(claim_category="CONSULTATION", documents=documents, required_docs=["PRESCRIPTION", "HOSPITAL_BILL"])

    assert outcome.passed is True
    assert outcome.docs_validated == 2
    assert outcome.patient_names == ["Rajesh Kumar", "Rajesh Kumar"]


def test_gating_rejects_unreadable_first():
    stage = DocumentGatingStage()
    documents = [vision_document("PRESCRIPTION", readability=0.2)]

    outcome = stage.evaluate(claim_category="CONSULTATION", documents=documents, required_docs=["PRESCRIPTION"])

    assert outcome.passed is False
    assert outcome.error_code == "UNREADABLE"
    assert outcome.detail["threshold"] == 0.4


def test_gating_rejects_missing_and_duplicate_documents():
    stage = DocumentGatingStage()
    duplicate_documents = [vision_document("PRESCRIPTION"), vision_document("PRESCRIPTION")]

    missing_outcome = stage.evaluate(claim_category="CONSULTATION", documents=[], required_docs=["PRESCRIPTION"])
    duplicate_outcome = stage.evaluate(
        claim_category="CONSULTATION",
        documents=duplicate_documents,
        required_docs=["PRESCRIPTION", "HOSPITAL_BILL"],
    )

    assert missing_outcome.error_code == "MISSING_REQUIRED"
    assert duplicate_outcome.error_code == "WRONG_TYPE"
    assert duplicate_outcome.detail["duplicates"] == ["PRESCRIPTION"]


def test_gating_rejects_patient_mismatch():
    stage = DocumentGatingStage()
    documents = [vision_document("PRESCRIPTION", patient_name="Rajesh Kumar"), vision_document("HOSPITAL_BILL", patient_name="Priya Singh")]

    outcome = stage.evaluate(claim_category="CONSULTATION", documents=documents, required_docs=["PRESCRIPTION", "HOSPITAL_BILL"])

    assert outcome.error_code == "PATIENT_MISMATCH"
    assert outcome.detail["first"] == "Rajesh Kumar"


def test_gating_required_documents_read_from_policy(assignment_policy):
    stage = DocumentGatingStage()

    assert stage.required_documents_for("CONSULTATION") == assignment_policy.document_requirements["CONSULTATION"].required
    assert stage.required_documents_for("NOT_A_CATEGORY") == []


def test_gating_helper_functions():
    assert missing_required_docs(required_docs=["A", "A", "B"], found_docs=["A"]) == ["A", "B"]
    assert duplicate_document_types(["A", "A", "B"]) == ["A"]
    assert "duplicate prescription" in missing_docs_message(
        claim_category="CONSULTATION",
        required_docs=["PRESCRIPTION", "HOSPITAL_BILL"],
        found_docs=["PRESCRIPTION", "PRESCRIPTION"],
        missing_docs=["HOSPITAL_BILL"],
        duplicate_types=["PRESCRIPTION"],
    )
    assert "no recognizable documents" in missing_docs_message(
        claim_category="VISION",
        required_docs=["PRESCRIPTION"],
        found_docs=[],
        missing_docs=["PRESCRIPTION"],
        duplicate_types=[],
    )
    assert friendly_doc_type("HOSPITAL_BILL") == "hospital bill"
    assert normalize_name("Rajesh K.") == "rajeshk"
    assert first_patient_mismatch(["Rajesh Kumar", "Rajesh Kumaar"]) is None
    assert first_patient_mismatch(["Rajesh Kumar", "Priya Singh"]) == ("Rajesh Kumar", "Priya Singh")
    assert levenshtein_distance("kitten", "sitting") == 3
    assert levenshtein_distance("", "abc") == 3


def test_amount_reconciliation_success_and_discrepancies():
    stage = AmountReconciliationStage()
    success = stage.evaluate(claimed_amount="1000.00", extraction=extraction_output())
    mismatch = stage.evaluate(
        claimed_amount="900.00",
        extraction=extraction_output(
            total_amount="1000.00",
            items=[line_item("Consultation", "600.00"), line_item("Lab", "300.00")],
            missing_fields=["possible correction on amount"],
        ),
    )
    missing = stage.evaluate(claimed_amount="500.00", extraction=extraction_output(total_amount=None, items=[]))

    assert success.agent_status == "SUCCESS"
    assert success.payable_basis_amount == "1000.00"
    assert [flag.type for flag in mismatch.discrepancy_flags] == ["TOTAL_MISMATCH", "CLAIMED_AMOUNT_MISMATCH"]
    assert mismatch.fraud_indicators[0].type == "POSSIBLE_ALTERATION"
    assert missing.discrepancy_flags[0].type == "AMOUNT_NOT_FOUND"
    assert missing.payable_basis_amount == "500.00"


def test_reconciliation_invalid_money_raises_value_error():
    with pytest.raises(ValueError, match="Invalid money value"):
        parse_money("not-money")


def test_orchestrator_merge_confidence_and_conflict_log():
    documents = [vision_document("PRESCRIPTION", confidence=0.8, readability=0.7)]
    extraction = extraction_output(confidences={"patient_name": 0.8, "total_amount": 0.9, "doctor_name": 0.6})
    reconciliation = reconciliation_result(discrepancy_flags=[{"type": "CLAIMED_AMOUNT_MISMATCH", "message": "Mismatch"}])

    result = ClaimMergeStage().evaluate(
        documents=documents,
        extraction=extraction,
        reconciliation=reconciliation,
        failed_agents=["vision_reader"],
    )

    assert result.conflict_log[0].field == "amount"
    assert result.failed_stages == ["vision_reader"]
    assert result.document_confidence == 0.76
    assert result.reconciliation_confidence == 0.88
    assert result.extraction_confidence < 0.8


def test_orchestrator_confidence_helpers():
    documents = [vision_document("PRESCRIPTION", confidence=1.0, readability=0.5), vision_document("HOSPITAL_BILL", confidence=0.5, readability=1.0)]

    assert compute_document_confidence([]) == 0.0
    assert compute_document_confidence(documents) == 0.75
    assert compute_entity_confidence({}) == 0.0
    assert compute_entity_confidence({"total_amount": 1.0, "patient_name": 0.5}) == 0.773
    assert compute_reconciliation_confidence(discrepancy_count=2, fraud_indicator_count=1) == 0.58
    assert compute_extraction_confidence(
        document_confidence=0.9,
        entity_confidence=0.8,
        reconciliation_confidence=0.7,
        field_confidences={},
        failed_agents=["a"],
        discrepancy_count=1,
        fraud_indicator_count=1,
    ) == 0.535


def test_entity_helpers_count_fields_and_default_confidence():
    extraction = extraction_output(items=[line_item("Consultation", "500.00"), line_item("Lab", "500.00")])

    assert average_confidence({"patient_name": 0.8, "ignored": "high", "total": 1.0}) == 0.9
    assert average_confidence({}) == 0.7
    assert count_extracted_fields(extraction) == 9
