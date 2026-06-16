from __future__ import annotations

from decimal import Decimal

import pytest

from backend.policy.engine import (
    PolicyEngine,
    benefit_cap_for_category,
    category_line_item_decisions,
    claim_level_exclusion_reason,
    dental_line_item_decisions,
    exclusion_match,
    find_member,
    has_rejected_items,
    is_date_between,
    is_network_hospital,
    manual_review,
    money,
    parse_date,
    parse_money,
    pre_auth_missing,
    rejected,
    specific_waiting_period,
)
from backend.tests.conftest import line_item


def evaluate(policy, make_merged_claim, **overrides):
    engine = PolicyEngine(policy=policy)
    defaults = {
        "member_id": "EMP001",
        "claim_category": "CONSULTATION",
        "treatment_date": "2024-11-01",
        "merged_claim": make_merged_claim(),
        "ytd_claims_amount": None,
        "same_day_claim_count": 0,
    }
    defaults.update(overrides)
    return engine.evaluate_sync(**defaults)


def test_approved_consultation_applies_network_discount_and_copay(assignment_policy, make_merged_claim):
    merged_claim = make_merged_claim(amount="1000.00", hospital_name="Apollo Hospitals - Bengaluru")

    result = evaluate(assignment_policy, make_merged_claim, merged_claim=merged_claim)

    assert result.decision == "APPROVED"
    assert result.approved_amount == "720.00"
    assert result.network_discount_applied == "200.00"
    assert result.copay_deducted == "80.00"
    assert [rule.rule_id for rule in result.rule_results][-1] == "COPAY_APPLICATION"


@pytest.mark.parametrize(
    ("overrides", "reason_id"),
    [
        ({"member_id": "UNKNOWN"}, "MEMBER_ELIGIBILITY"),
        ({"treatment_date": "2025-04-01"}, "POLICY_ACTIVE"),
        ({"merged_claim_amount": "499.99"}, "MINIMUM_CLAIM_AMOUNT"),
        ({"member_id": "EMP005", "treatment_date": "2024-09-15"}, "INITIAL_WAITING_PERIOD"),
        ({"claim_category": "UNKNOWN"}, "COVERAGE_CATEGORY"),
    ],
)
def test_policy_rejects_basic_rule_failures(assignment_policy, make_merged_claim, overrides, reason_id):
    merged_claim = make_merged_claim(amount=overrides.pop("merged_claim_amount", "1000.00"))

    result = evaluate(assignment_policy, make_merged_claim, merged_claim=merged_claim, **overrides)

    assert result.decision == "REJECTED"
    assert result.rejection_reasons[0]["rule_id"] == reason_id
    assert result.approved_amount == "0.00"


def test_condition_waiting_period_uses_diagnosis_aliases(assignment_policy, make_merged_claim):
    merged_claim = make_merged_claim(diagnosis="T2DM follow up")

    result = evaluate(
        assignment_policy,
        make_merged_claim,
        treatment_date="2024-05-15",
        merged_claim=merged_claim,
    )

    assert result.decision == "REJECTED"
    assert result.rejection_reasons[0]["rule_id"] == "WAITING_PERIOD"


def test_dental_line_items_can_make_partial_decision(assignment_policy, make_merged_claim):
    merged_claim = make_merged_claim(
        amount="4200.00",
        items=[
            line_item("Root Canal Treatment", "3000.00"),
            line_item("Teeth Whitening", "1200.00"),
        ],
    )

    result = evaluate(assignment_policy, make_merged_claim, claim_category="DENTAL", merged_claim=merged_claim)

    assert result.decision == "PARTIAL"
    assert result.approved_amount == "3000.00"
    assert [item.decision for item in result.partial_items] == ["APPROVED", "REJECTED"]


def test_vision_line_items_filter_exclusions(assignment_policy, make_merged_claim):
    merged_claim = make_merged_claim(
        amount="4500.00",
        items=[line_item("Glasses", "2500.00"), line_item("LASIK Surgery", "2000.00")],
    )

    result = evaluate(assignment_policy, make_merged_claim, claim_category="VISION", merged_claim=merged_claim)

    assert result.decision == "PARTIAL"
    assert result.approved_amount == "2500.00"
    assert result.partial_items[1].reason.startswith("Excluded vision item")


def test_claim_level_exclusion_rejects_when_no_partial_item_filter(assignment_policy, make_merged_claim):
    merged_claim = make_merged_claim(diagnosis="Cosmetic or aesthetic procedures")

    result = evaluate(assignment_policy, make_merged_claim, merged_claim=merged_claim)

    assert result.decision == "REJECTED"
    assert result.rejection_reasons[0]["rule_id"] == "EXCLUDED_CONDITION"


def test_diagnostic_pre_auth_missing_is_rejected(assignment_policy, make_merged_claim):
    merged_claim = make_merged_claim(amount="12000.00", items=[line_item("MRI Brain", "12000.00")])

    result = evaluate(assignment_policy, make_merged_claim, claim_category="DIAGNOSTIC", merged_claim=merged_claim)

    assert result.decision == "REJECTED"
    assert result.rejection_reasons[0]["rule_id"] == "PRE_AUTH_MISSING"


def test_same_day_claim_threshold_routes_to_manual_review(assignment_policy, make_merged_claim):
    result = evaluate(assignment_policy, make_merged_claim, same_day_claim_count=3)

    assert result.decision == "MANUAL_REVIEW"
    assert result.manual_review_note == "Unusual same-day claim pattern detected."


def test_benefit_cap_and_annual_limit_rejections(assignment_policy, make_merged_claim):
    cap_result = evaluate(assignment_policy, make_merged_claim, merged_claim=make_merged_claim(amount="2500.00"))
    annual_result = evaluate(
        assignment_policy,
        make_merged_claim,
        merged_claim=make_merged_claim(amount="1500.00"),
        ytd_claims_amount="49000.00",
    )

    assert cap_result.rejection_reasons[0]["rule_id"] == "SUB_LIMIT_EXCEEDED"
    assert annual_result.rejection_reasons[0]["rule_id"] == "ANNUAL_LIMIT_EXCEEDED"


def test_policy_helper_functions(assignment_policy, make_merged_claim):
    consultation = assignment_policy.opd_categories["consultation"]
    diagnostic = assignment_policy.opd_categories["diagnostic"]
    merged_claim = make_merged_claim(items=[line_item("MRI Brain", "12000.00")])

    assert parse_money("₹1,234.555") == Decimal("1234.56")
    assert money(Decimal("7.125")) == "7.13"
    assert parse_date("2024-04-01").year == 2024
    assert is_date_between(parse_date("2024-04-01"), "2024-04-01", "2024-04-02")
    assert find_member(assignment_policy, "EMP001").name == "Rajesh Kumar"
    assert specific_waiting_period("HTN review", assignment_policy.waiting_periods.specific_conditions) == ("hypertension", 90)
    assert exclusion_match(make_merged_claim(diagnosis="Bariatric surgery"), assignment_policy.exclusions.conditions) == "Obesity and weight loss programs"
    assert claim_level_exclusion_reason(merged_claim=merged_claim, exclusions=assignment_policy.exclusions.conditions, partial_items=None) is None
    assert pre_auth_missing("DIAGNOSTIC", merged_claim, Decimal("12000.00"), diagnostic)
    assert not pre_auth_missing("CONSULTATION", merged_claim, Decimal("12000.00"), consultation)
    assert benefit_cap_for_category(consultation, assignment_policy.coverage.per_claim_limit) == (Decimal("2000"), "SUB_LIMIT")
    assert is_network_hospital("Manipal Hospitals Whitefield", assignment_policy.network_hospitals)


def test_line_item_decision_helpers(make_merged_claim):
    merged_claim = make_merged_claim(
        items=[
            line_item("Covered item", "100.00", "COVERED", "explicitly covered"),
            line_item("Excluded item", "50.00", "EXCLUDED", "explicitly excluded"),
            line_item("Unknown item", "25.00"),
        ]
    )

    decisions, approved_total = category_line_item_decisions(
        merged_claim,
        covered=["covered"],
        excluded=["excluded"],
        category_label="sample",
    )
    dental_decisions, dental_total = dental_line_item_decisions(merged_claim, ["covered"], ["excluded"])

    assert approved_total == Decimal("125.00")
    assert dental_total == Decimal("125.00")
    assert has_rejected_items(decisions)
    assert dental_decisions[1].decision == "REJECTED"


def test_result_factories_preserve_rule_details():
    failed = rejected("Nope", [], 0.44)
    review = manual_review("Needs review", [], 0.55)

    assert failed.rejection_reasons == [{"rule_id": "REJECTED", "reason": "Nope"}]
    assert review.decision == "MANUAL_REVIEW"
    assert review.confidence_score == 0.55
