from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from pydantic import BaseModel, Field

from backend.agents.orchestrator import MergedClaimResult
from backend.models.policy import Policy, PolicyMember
from backend.policy.loader import get_policy
from backend.tracing.store import TraceStore


class RuleResult(BaseModel):
    rule_id: str
    outcome: Literal["PASS", "FAIL", "PARTIAL", "SKIP"]
    reason: str
    approved_amount: str | None = None
    deducted_amount: str | None = None
    deduction_reason: str | None = None
    metadata: dict = Field(default_factory=dict)


class LineItemDecision(BaseModel):
    description: str
    amount: str
    decision: Literal["APPROVED", "REJECTED"]
    reason: str | None = None


class PolicyDecisionResult(BaseModel):
    decision: Literal["APPROVED", "PARTIAL", "REJECTED", "MANUAL_REVIEW"]
    approved_amount: str
    copay_deducted: str = "0.00"
    network_discount_applied: str = "0.00"
    rejection_reasons: list[dict] = Field(default_factory=list)
    partial_items: list[LineItemDecision] | None = None
    member_message: str
    ops_summary: str
    confidence_score: float
    manual_review_note: str | None = None
    rule_results: list[RuleResult] = Field(default_factory=list)


class PolicyEngine:
    agent_name = "policy_engine"
    stage_order = 6

    def __init__(self, policy: Policy | None = None):
        self.policy = policy or get_policy()

    async def evaluate(
        self,
        *,
        claim_id: str,
        member_id: str,
        claim_category: str,
        treatment_date: str,
        merged_claim: MergedClaimResult,
        ytd_claims_amount: str | None = None,
        same_day_claim_count: int = 0,
    ) -> PolicyDecisionResult:
        span_id = await TraceStore.start_span(
            claim_id,
            self.agent_name,
            stage_order=self.stage_order,
            input_summary={
                "member_id": member_id,
                "claim_category": claim_category,
                "treatment_date": treatment_date,
                "payable_basis_amount": merged_claim.payable_basis_amount,
                "confidence": merged_claim.extraction_confidence,
            },
            current_stage=self.agent_name,
        )
        try:
            result = self.evaluate_sync(
                member_id=member_id,
                claim_category=claim_category,
                treatment_date=treatment_date,
                merged_claim=merged_claim,
                ytd_claims_amount=ytd_claims_amount,
                same_day_claim_count=same_day_claim_count,
            )
            await TraceStore.finish_span(
                span_id,
                status="SUCCESS" if result.decision in {"APPROVED", "PARTIAL"} else "PARTIAL",
                output_summary={
                    "rules_evaluated": len(result.rule_results),
                    "rules_failed": sum(1 for rule in result.rule_results if rule.outcome == "FAIL"),
                    "rules_skipped": sum(1 for rule in result.rule_results if rule.outcome == "SKIP"),
                    "decision": result.decision,
                    "approved_amount": result.approved_amount,
                    "rule_results": [rule.model_dump() for rule in result.rule_results],
                },
                current_stage=None,
            )
            return result
        except Exception as exc:
            await TraceStore.finish_span(span_id, status="ERROR", output_summary=None, errors=[str(exc)], current_stage=None)
            raise

    def evaluate_sync(
        self,
        *,
        member_id: str,
        claim_category: str,
        treatment_date: str,
        merged_claim: MergedClaimResult,
        ytd_claims_amount: str | None = None,
        same_day_claim_count: int = 0,
    ) -> PolicyDecisionResult:
        rules: list[RuleResult] = []
        category = self.policy.opd_categories.get(claim_category.lower())
        treatment = parse_date(treatment_date)
        amount = parse_money(merged_claim.payable_basis_amount)
        member = find_member(self.policy, member_id)

        if not member:
            rules.append(RuleResult(rule_id="MEMBER_ELIGIBILITY", outcome="FAIL", reason=f"Member {member_id} is not in roster."))
            return rejected("Member is not eligible under this policy.", rules, merged_claim.extraction_confidence)
        rules.append(RuleResult(rule_id="MEMBER_ELIGIBILITY", outcome="PASS", reason="Member exists in policy roster."))

        if not is_date_between(treatment, self.policy.policy_holder.policy_start_date, self.policy.policy_holder.policy_end_date):
            rules.append(RuleResult(rule_id="POLICY_ACTIVE", outcome="FAIL", reason="Treatment date is outside policy period."))
            return rejected("Treatment date is outside the active policy period.", rules, merged_claim.extraction_confidence)
        rules.append(RuleResult(rule_id="POLICY_ACTIVE", outcome="PASS", reason="Treatment date is within policy period."))

        if amount < Decimal(str(self.policy.submission_rules.minimum_claim_amount)):
            rules.append(RuleResult(rule_id="MINIMUM_CLAIM_AMOUNT", outcome="FAIL", reason="Claim amount is below minimum."))
            return rejected("Claim amount is below the minimum allowed amount.", rules, merged_claim.extraction_confidence)
        rules.append(RuleResult(rule_id="MINIMUM_CLAIM_AMOUNT", outcome="PASS", reason="Claim amount meets minimum threshold."))

        join_date = parse_date(member.join_date or self.policy.policy_holder.policy_start_date)
        initial_eligible_date = join_date + timedelta(days=self.policy.waiting_periods.initial_waiting_period_days)
        if treatment < initial_eligible_date:
            rules.append(RuleResult(rule_id="INITIAL_WAITING_PERIOD", outcome="FAIL", reason=f"Initial waiting period ends on {initial_eligible_date.isoformat()}."))
            return rejected(f"Initial waiting period applies until {initial_eligible_date.isoformat()}.", rules, merged_claim.extraction_confidence)
        rules.append(RuleResult(rule_id="INITIAL_WAITING_PERIOD", outcome="PASS", reason="Initial waiting period completed."))

        specific_wait = specific_waiting_period(merged_claim.diagnosis_primary or "", self.policy.waiting_periods.specific_conditions)
        if specific_wait:
            condition, days = specific_wait
            eligible_date = join_date + timedelta(days=days)
            if treatment < eligible_date:
                rules.append(RuleResult(rule_id="CONDITION_WAITING_PERIOD", outcome="FAIL", reason=f"{condition} waiting period ends on {eligible_date.isoformat()}."))
                return rejected(f"{condition.title()} related claims are eligible from {eligible_date.isoformat()}.", rules, merged_claim.extraction_confidence, reason_id="WAITING_PERIOD")
        rules.append(RuleResult(rule_id="CONDITION_WAITING_PERIOD", outcome="PASS", reason="No active condition waiting period applies."))

        exclusion_reason = exclusion_match(merged_claim, self.policy.exclusions.conditions)
        if exclusion_reason:
            rules.append(RuleResult(rule_id="EXCLUSION_CHECK", outcome="FAIL", reason=f"Excluded treatment detected: {exclusion_reason}."))
            return rejected("This treatment is excluded under the policy.", rules, merged_claim.extraction_confidence, reason_id="EXCLUDED_CONDITION")
        rules.append(RuleResult(rule_id="EXCLUSION_CHECK", outcome="PASS", reason="No exclusion matched."))

        if not category or not category.covered:
            rules.append(RuleResult(rule_id="COVERAGE_CATEGORY", outcome="FAIL", reason=f"Category {claim_category} is not covered."))
            return rejected("Claim category is not covered under this policy.", rules, merged_claim.extraction_confidence)
        rules.append(RuleResult(rule_id="COVERAGE_CATEGORY", outcome="PASS", reason="Claim category is covered."))

        partial_items: list[LineItemDecision] | None = None
        if claim_category == "DENTAL":
            partial_items, amount = dental_line_item_decisions(merged_claim, category.covered_procedures or [], category.excluded_procedures or [])
            rules.append(RuleResult(rule_id="DENTAL_LINE_ITEM_FILTER", outcome="PARTIAL" if has_rejected_items(partial_items) else "PASS", reason="Dental line items adjudicated.", approved_amount=money(amount)))
        elif claim_category == "VISION":
            partial_items, amount = category_line_item_decisions(
                merged_claim,
                covered=category.covered_items or [],
                excluded=category.excluded_items or [],
                category_label="vision",
            )
            rules.append(RuleResult(rule_id="VISION_LINE_ITEM_FILTER", outcome="PARTIAL" if has_rejected_items(partial_items) else "PASS", reason="Vision line items adjudicated.", approved_amount=money(amount)))
        else:
            rules.append(RuleResult(rule_id="DENTAL_LINE_ITEM_FILTER", outcome="SKIP", reason="Not a dental claim."))

        if amount <= Decimal("0.00"):
            rules.append(RuleResult(rule_id="COVERED_AMOUNT", outcome="FAIL", reason="No payable covered amount remains after exclusions."))
            return rejected("No payable covered amount remains after exclusions.", rules, merged_claim.extraction_confidence, reason_id="NO_COVERED_AMOUNT")

        if pre_auth_missing(claim_category, merged_claim, amount, category):
            rules.append(RuleResult(rule_id="PRE_AUTH_CHECK", outcome="FAIL", reason="Pre-authorization required but missing."))
            return rejected("Pre-authorization was required for this claim and was not provided.", rules, merged_claim.extraction_confidence, reason_id="PRE_AUTH_MISSING")
        rules.append(RuleResult(rule_id="PRE_AUTH_CHECK", outcome="PASS", reason="No missing pre-authorization detected."))

        if same_day_claim_count > self.policy.fraud_thresholds.same_day_claims_limit:
            rules.append(RuleResult(rule_id="FRAUD_SIGNAL_CHECK", outcome="FAIL", reason="Same-day claim threshold exceeded."))
            return manual_review("Unusual same-day claim pattern detected.", rules, merged_claim.extraction_confidence)
        rules.append(RuleResult(rule_id="FRAUD_SIGNAL_CHECK", outcome="PASS", reason="No fraud threshold breach."))

        cap_amount, cap_source = benefit_cap_for_category(category, self.policy.coverage.per_claim_limit)
        if amount > cap_amount:
            rules.append(
                RuleResult(
                    rule_id="BENEFIT_CAP",
                    outcome="FAIL",
                    reason=f"Payable amount {money(amount)} exceeds {cap_source} cap {money(cap_amount)}.",
                    approved_amount="0.00",
                    deducted_amount=money(amount),
                    deduction_reason=cap_source,
                    metadata={"cap_source": cap_source, "cap_amount": money(cap_amount), "amount": money(amount)},
                )
            )
            reason_id = "SUB_LIMIT_EXCEEDED" if cap_source == "SUB_LIMIT" else "PER_CLAIM_EXCEEDED"
            return rejected(f"The payable amount {money(amount)} exceeds the {cap_source.lower().replace('_', ' ')} cap of {money(cap_amount)}.", rules, merged_claim.extraction_confidence, reason_id=reason_id)
        else:
            rules.append(RuleResult(rule_id="BENEFIT_CAP", outcome="PASS", reason=f"Payable amount is within {cap_source} cap {money(cap_amount)}.", metadata={"cap_source": cap_source, "cap_amount": money(cap_amount)}))

        if ytd_claims_amount and str(ytd_claims_amount).strip():
            ytd_amount = parse_money(ytd_claims_amount)
            annual_limit = Decimal(str(self.policy.coverage.annual_opd_limit))
            projected_total = ytd_amount + amount
            if projected_total > annual_limit:
                rules.append(
                    RuleResult(
                        rule_id="ANNUAL_LIMIT",
                        outcome="FAIL",
                        reason=(
                            f"YTD claimed amount {money(ytd_amount)} plus current claim {money(amount)} "
                            f"exceeds annual OPD limit {money(annual_limit)}."
                        ),
                        metadata={
                            "ytd_claims_amount": money(ytd_amount),
                            "current_claim_amount": money(amount),
                            "projected_total": money(projected_total),
                            "annual_opd_limit": money(annual_limit),
                        },
                    )
                )
                return rejected("Annual OPD limit would be exceeded.", rules, merged_claim.extraction_confidence, reason_id="ANNUAL_LIMIT_EXCEEDED")
            rules.append(
                RuleResult(
                    rule_id="ANNUAL_LIMIT",
                    outcome="PASS",
                    reason=(
                        f"YTD claimed amount {money(ytd_amount)} plus current claim {money(amount)} "
                        f"is within annual OPD limit {money(annual_limit)}."
                    ),
                    metadata={
                        "ytd_claims_amount": money(ytd_amount),
                        "current_claim_amount": money(amount),
                        "projected_total": money(projected_total),
                        "annual_opd_limit": money(annual_limit),
                        "remaining_after_claim": money(annual_limit - projected_total),
                    },
                )
            )
        else:
            rules.append(RuleResult(rule_id="ANNUAL_LIMIT", outcome="SKIP", reason="YTD amount not provided."))

        network_discount = Decimal("0.00")
        if merged_claim.hospital_name and is_network_hospital(merged_claim.hospital_name, self.policy.network_hospitals):
            network_discount = amount * Decimal(str(category.network_discount_percent or 0)) / Decimal("100")
            amount -= network_discount
            rules.append(RuleResult(rule_id="NETWORK_DISCOUNT", outcome="PASS", reason="Network hospital discount applied.", deducted_amount=money(network_discount), deduction_reason="NETWORK_DISCOUNT"))
        else:
            rules.append(RuleResult(rule_id="NETWORK_DISCOUNT", outcome="SKIP", reason="No network hospital discount applied."))

        copay = amount * Decimal(str(category.copay_percent or 0)) / Decimal("100")
        approved = amount - copay
        rules.append(RuleResult(rule_id="COPAY_APPLICATION", outcome="PASS", reason="Copay applied.", approved_amount=money(approved), deducted_amount=money(copay), deduction_reason="COPAY"))

        decision = "PARTIAL" if has_rejected_items(partial_items) else "APPROVED"
        return PolicyDecisionResult(
            decision=decision,
            approved_amount=money(approved),
            copay_deducted=money(copay),
            network_discount_applied=money(network_discount),
            partial_items=partial_items,
            member_message=f"Your claim is {decision.lower()} for {money(approved)}.",
            ops_summary=f"Policy engine completed with decision {decision}.",
            confidence_score=merged_claim.extraction_confidence,
            rule_results=rules,
        )


def rejected(message: str, rules: list[RuleResult], confidence: float, reason_id: str | None = None) -> PolicyDecisionResult:
    failed = [rule for rule in rules if rule.outcome == "FAIL"]
    reason = reason_id or (failed[-1].rule_id if failed else "REJECTED")
    return PolicyDecisionResult(decision="REJECTED", approved_amount="0.00", rejection_reasons=[{"rule_id": reason, "reason": message}], member_message=message, ops_summary=f"Rejected due to {reason}.", confidence_score=confidence, rule_results=rules)


def manual_review(message: str, rules: list[RuleResult], confidence: float) -> PolicyDecisionResult:
    return PolicyDecisionResult(decision="MANUAL_REVIEW", approved_amount="0.00", member_message=message, ops_summary="Manual review required by policy engine.", confidence_score=confidence, manual_review_note=message, rule_results=rules)


def parse_money(value: str) -> Decimal:
    return Decimal(str(value).replace("₹", "").replace(",", "").strip()).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def parse_date(value: str) -> date:
    return datetime.fromisoformat(value).date()


def is_date_between(candidate: date, start: str, end: str) -> bool:
    return parse_date(start) <= candidate <= parse_date(end)


def find_member(policy: Policy, member_id: str) -> PolicyMember | None:
    return next((member for member in policy.members if member.member_id == member_id), None)


def specific_waiting_period(diagnosis: str, conditions: dict[str, int]) -> tuple[str, int] | None:
    diagnosis_lower = diagnosis.lower()
    aliases = {"diabetes": ["diabetes", "t2dm", "type 2 diabetes"], "hypertension": ["hypertension", "htn"], "obesity_treatment": ["obesity", "bariatric"]}
    for condition, days in conditions.items():
        terms = aliases.get(condition, [condition.replace("_", " ")])
        if any(term in diagnosis_lower for term in terms):
            return condition.replace("_", " "), days
    return None


def exclusion_match(merged_claim: MergedClaimResult, exclusions: list[str]) -> str | None:
    haystack = " ".join([merged_claim.diagnosis_primary or "", *(item.description for item in merged_claim.line_items)]).lower()
    for exclusion in exclusions:
        terms = [exclusion.lower()]
        if "obesity" in exclusion.lower() or "bariatric" in exclusion.lower():
            terms.extend(["obesity", "bariatric", "weight loss"])
        if any(term in haystack for term in terms):
            return exclusion
    return None


def pre_auth_missing(claim_category: str, merged_claim: MergedClaimResult, amount: Decimal, category) -> bool:
    if claim_category != "DIAGNOSTIC":
        return False
    text = " ".join(item.description for item in merged_claim.line_items).lower()
    high_value_tests = category.high_value_tests_requiring_pre_auth or []
    threshold = Decimal(str(category.pre_auth_threshold or 0))
    return amount > threshold and any(test.lower() in text for test in high_value_tests)


def dental_line_item_decisions(merged_claim: MergedClaimResult, covered: list[str], excluded: list[str]) -> tuple[list[LineItemDecision], Decimal]:
    return category_line_item_decisions(merged_claim, covered=covered, excluded=excluded, category_label="dental")


def category_line_item_decisions(merged_claim: MergedClaimResult, *, covered: list[str], excluded: list[str], category_label: str) -> tuple[list[LineItemDecision], Decimal]:
    decisions: list[LineItemDecision] = []
    approved_total = Decimal("0.00")
    for item in merged_claim.line_items:
        amount = parse_money(item.amount)
        description_lower = item.description.lower()
        excluded_match = next((term for term in excluded if term.lower() in description_lower), None)
        covered_match = next((term for term in covered if term.lower() in description_lower), None)
        if excluded_match:
            decisions.append(LineItemDecision(description=item.description, amount=money(amount), decision="REJECTED", reason=f"Excluded {category_label} item: {excluded_match}"))
        elif covered_match or item.coverage_hint == "COVERED":
            approved_total += amount
            decisions.append(LineItemDecision(description=item.description, amount=money(amount), decision="APPROVED", reason=f"Covered {category_label} item."))
        else:
            approved_total += amount
            decisions.append(LineItemDecision(description=item.description, amount=money(amount), decision="APPROVED", reason=f"No {category_label} exclusion matched."))
    return decisions, approved_total


def has_rejected_items(items: list[LineItemDecision] | None) -> bool:
    return bool(items and any(item.decision == "REJECTED" for item in items))


def benefit_cap_for_category(category, per_claim_limit: int) -> tuple[Decimal, str]:
    sub_limit = getattr(category, "sub_limit", None)
    if sub_limit is not None:
        return Decimal(str(sub_limit)), "SUB_LIMIT"
    return Decimal(str(per_claim_limit)), "PER_CLAIM_LIMIT"


def is_network_hospital(hospital_name: str, network_hospitals: list[str]) -> bool:
    normalized = hospital_name.lower()
    return any(hospital.lower() in normalized or normalized in hospital.lower() for hospital in network_hospitals)