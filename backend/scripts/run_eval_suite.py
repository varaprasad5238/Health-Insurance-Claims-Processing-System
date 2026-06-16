from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.agents.gating import GatingAgent
from backend.agents.orchestrator import OrchestratorAgent
from backend.agents.reconciler import AmountReconcilerAgent
from backend.ai_platform.schemas import DocumentVisionOutput, LineItemOutput, StructuredExtractionOutput
from backend.policy.engine import PolicyDecisionResult, PolicyEngine


ASSIGNMENT_CASES_PATH = ROOT / "assignment" / "test_cases.json"
SUITE_ROOT = ROOT / "test_suite"
REPORT_JSON_PATH = ROOT / "docs" / "eval_report.json"
REPORT_MD_PATH = ROOT / "docs" / "eval_report.md"

KNOWN_MISMATCH_NOTES = {
    "TC007": "Current policy order evaluates condition waiting period before pre-authorization; the diagnosis text contains herniation, which matches the hernia waiting-period term.",
    "TC008": "Current policy treats the consultation sub-limit as the active cap before the general per-claim limit, so the reason is SUB_LIMIT_EXCEEDED instead of PER_CLAIM_EXCEEDED.",
    "TC010": "Current policy applies the consultation sub-limit before network discount and co-pay, so the claim is rejected before the expected discount calculation can run.",
    "TC012": "Current policy checks obesity-related waiting period before exclusions, so WAITING_PERIOD fires before EXCLUDED_CONDITION.",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 1 component eval suite.")
    parser.add_argument("--mode", choices=["component"], default="component")
    parser.add_argument("--case", dest="case_ids", action="append", help="Run one case id, e.g. TC009. Can be supplied more than once.")
    args = parser.parse_args()

    cases = load_assignment_cases()
    selected_case_ids = {case_id.upper() for case_id in args.case_ids or []}
    if selected_case_ids:
        cases = [case for case in cases if case["case_id"].upper() in selected_case_ids]

    results = [run_component_case(case) for case in cases]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "summary": summarize(results),
        "cases": results,
    }
    write_reports(report)
    print(f"Wrote {REPORT_JSON_PATH.relative_to(ROOT)}")
    print(f"Wrote {REPORT_MD_PATH.relative_to(ROOT)}")
    print(json.dumps(report["summary"], indent=2))


def load_assignment_cases() -> list[dict[str, Any]]:
    payload = json.loads(ASSIGNMENT_CASES_PATH.read_text(encoding="utf-8"))
    return payload["test_cases"]


def run_component_case(case: dict[str, Any]) -> dict[str, Any]:
    case_id = case["case_id"]
    case_input = case["input"]
    expected = case["expected"]
    manifest = load_manifest(case_id)
    documents = build_documents(case_input)

    gating_agent = GatingAgent()
    required_docs = gating_agent.required_documents_for(case_input["claim_category"])
    gating_result = gating_agent.evaluate(
        claim_category=case_input["claim_category"],
        documents=documents,
        required_docs=required_docs,
    )

    if not gating_result.passed:
        output = {
            "stage": "gating",
            "document_artifacts": manifest.get("documents", []),
            "gating": gating_result.model_dump(),
        }
        checks = evaluate_checks(expected=expected, actual_decision=None, approved_amount=None, rejection_reasons=[], output=output)
        return case_result(case=case, manifest=manifest, output=output, checks=checks)

    failed_agents = ["entity_extraction"] if case_input.get("simulate_component_failure") else []
    extraction = build_extraction(case_input, failed_agents=failed_agents)
    reconciliation = AmountReconcilerAgent().evaluate(
        claimed_amount=str(case_input["claimed_amount"]),
        extraction=extraction,
    )
    merged_claim = OrchestratorAgent().evaluate(
        documents=documents,
        extraction=extraction,
        reconciliation=reconciliation,
        failed_agents=failed_agents,
    )

    same_day_claim_count = len(case_input.get("claims_history", []))
    policy_decision = PolicyEngine().evaluate_sync(
        member_id=case_input["member_id"],
        claim_category=case_input["claim_category"],
        treatment_date=case_input["treatment_date"],
        merged_claim=merged_claim,
        ytd_claims_amount=none_or_str(case_input.get("ytd_claims_amount")),
        same_day_claim_count=same_day_claim_count,
    )

    output = {
        "stage": "policy_decision",
        "document_artifacts": manifest.get("documents", []),
        "gating": gating_result.model_dump(),
        "failed_agents": failed_agents,
        "component_simulation": component_simulation_note(failed_agents),
        "same_day_claim_count": same_day_claim_count,
        "extraction": extraction.model_dump(),
        "reconciliation": reconciliation.model_dump(),
        "merged_claim": merged_claim.model_dump(),
        "policy_decision": policy_decision.model_dump(),
    }
    checks = evaluate_checks(
        expected=expected,
        actual_decision=policy_decision.decision,
        approved_amount=policy_decision.approved_amount,
        rejection_reasons=policy_decision.rejection_reasons,
        output=output,
    )
    return case_result(case=case, manifest=manifest, output=output, checks=checks)


def load_manifest(case_id: str) -> dict[str, Any]:
    manifest_path = SUITE_ROOT / case_id / "input.json"
    if not manifest_path.exists():
        return {"case_id": case_id, "documents": sorted(str(path.relative_to(SUITE_ROOT / case_id)) for path in (SUITE_ROOT / case_id / "documents").glob("*"))}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def build_documents(case_input: dict[str, Any]) -> list[DocumentVisionOutput]:
    documents: list[DocumentVisionOutput] = []
    for index, source in enumerate(case_input.get("documents", []), start=1):
        content = source.get("content") or {}
        document_type = source.get("actual_type", "UNKNOWN")
        readability = 0.2 if source.get("quality") == "UNREADABLE" else 0.95
        patient_name = source.get("patient_name_on_doc") or content.get("patient_name")
        documents.append(
            DocumentVisionOutput(
                document_type=document_type,
                confidence=0.96,
                readability=readability,
                patient_name_raw=patient_name,
                transcript=json.dumps(source, ensure_ascii=False),
                source_file_name=source.get("file_name") or f"{source.get('file_id', 'document')}.pdf",
                source_page_range=str(index),
            )
        )
    return documents


def build_extraction(case_input: dict[str, Any], *, failed_agents: list[str]) -> StructuredExtractionOutput:
    contents = [document.get("content") or {} for document in case_input.get("documents", [])]
    line_items = collect_line_items(contents, fallback_amount=str(case_input["claimed_amount"]), category=case_input["claim_category"])
    total_amount = first_value(contents, "total") or sum_line_items(line_items) or str(case_input["claimed_amount"])
    confidence = 0.82 if failed_agents else 0.95
    field_confidences = {
        "total_amount": confidence,
        "amount": confidence,
        "diagnosis_primary": confidence,
        "treatment_date": confidence,
    }
    patient_name = first_value(contents, "patient_name")
    if patient_name:
        field_confidences["patient_name"] = confidence

    return StructuredExtractionOutput(
        patient_name=patient_name,
        doctor_name=first_value(contents, "doctor_name"),
        doctor_registration=first_value(contents, "doctor_registration"),
        diagnosis_primary=first_value(contents, "diagnosis") or first_value(contents, "treatment") or first_value(contents, "test_name"),
        treatment_date=first_value(contents, "date") or case_input["treatment_date"],
        hospital_name=case_input.get("hospital_name") or first_value(contents, "hospital_name"),
        line_items=line_items,
        total_amount=str(total_amount),
        field_confidences=field_confidences,
        missing_fields=["simulated entity extraction component failure"] if failed_agents else [],
    )


def collect_line_items(contents: list[dict[str, Any]], *, fallback_amount: str, category: str) -> list[LineItemOutput]:
    items: list[LineItemOutput] = []
    for content in contents:
        for item in content.get("line_items") or []:
            items.append(
                LineItemOutput(
                    description=str(item.get("description") or category.replace("_", " ").title()),
                    amount=str(item.get("amount") or "0"),
                    coverage_hint=coverage_hint_for(str(item.get("description") or "")),
                )
            )
    if items:
        return items

    description = first_value(contents, "test_name") or first_value(contents, "treatment") or first_value(contents, "diagnosis") or category.replace("_", " ").title()
    return [LineItemOutput(description=str(description), amount=str(fallback_amount), coverage_hint=coverage_hint_for(str(description)))]


def coverage_hint_for(description: str) -> str:
    lowered = description.lower()
    excluded_terms = ["whitening", "bariatric", "obesity", "diet", "weight loss", "cosmetic"]
    return "EXCLUDED" if any(term in lowered for term in excluded_terms) else "UNCERTAIN"


def first_value(contents: list[dict[str, Any]], key: str) -> Any | None:
    for content in contents:
        value = content.get(key)
        if value not in (None, ""):
            return value
    return None


def sum_line_items(items: list[LineItemOutput]) -> str | None:
    if not items:
        return None
    total = Decimal("0.00")
    for item in items:
        total += money_decimal(item.amount)
    return str(total.quantize(Decimal("0.01")))


def evaluate_checks(
    *,
    expected: dict[str, Any],
    actual_decision: str | None,
    approved_amount: str | None,
    rejection_reasons: list[dict[str, Any]],
    output: dict[str, Any],
) -> list[dict[str, Any]]:
    checks = [
        {
            "name": "decision",
            "expected": expected.get("decision"),
            "actual": actual_decision,
            "passed": expected.get("decision") == actual_decision,
        }
    ]

    if "approved_amount" in expected and approved_amount is not None:
        checks.append(
            {
                "name": "approved_amount",
                "expected": money_text(expected["approved_amount"]),
                "actual": money_text(approved_amount),
                "passed": money_text(expected["approved_amount"]) == money_text(approved_amount),
            }
        )

    if expected.get("rejection_reasons"):
        actual_rule_ids = [reason.get("rule_id") for reason in rejection_reasons]
        expected_rule_ids = expected["rejection_reasons"]
        checks.append(
            {
                "name": "rejection_reasons",
                "expected": expected_rule_ids,
                "actual": actual_rule_ids,
                "passed": all(rule_id in actual_rule_ids for rule_id in expected_rule_ids),
            }
        )

    if output.get("failed_agents"):
        confidence = output["policy_decision"]["confidence_score"]
        checks.append(
            {
                "name": "component_failure_visible",
                "expected": "failed agent visible with reduced confidence and eval review recommendation",
                "actual": output["component_simulation"],
                "passed": bool(output["failed_agents"]) and confidence < 0.85,
            }
        )

    return checks


def case_result(case: dict[str, Any], manifest: dict[str, Any], output: dict[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any]:
    notes = []
    if not all(check["passed"] for check in checks) and case["case_id"] in KNOWN_MISMATCH_NOTES:
        notes.append(KNOWN_MISMATCH_NOTES[case["case_id"]])

    return {
        "case_id": case["case_id"],
        "case_name": case["case_name"],
        "matched": all(check["passed"] for check in checks),
        "notes": notes,
        "checks": checks,
        "manifest": manifest,
        "output": output,
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(1 for result in results if result["matched"])
    total = len(results)
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 3) if total else 0,
    }


def write_reports(report: dict[str, Any]) -> None:
    REPORT_JSON_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    REPORT_MD_PATH.write_text(render_markdown_report(report), encoding="utf-8")


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 1 Component Eval Report",
        "",
        f"Generated at: `{report['generated_at']}`",
        f"Mode: `{report['mode']}`",
        "",
        "## Summary",
        "",
        f"Passed {report['summary']['passed']} of {report['summary']['total']} cases.",
        "",
        "| Case | Expected | Actual | Match | Notes |",
        "| --- | --- | --- | --- | --- |",
    ]
    for result in report["cases"]:
        decision_check = next(check for check in result["checks"] if check["name"] == "decision")
        check_notes = "; ".join(f"{check['name']} failed" for check in result["checks"] if not check["passed"])
        notes = check_notes or "ok"
        if result.get("notes"):
            notes = f"{notes}. {result['notes'][0]}"
        lines.append(
            f"| {result['case_id']} | {decision_check['expected']} | {decision_check['actual']} | {'yes' if result['matched'] else 'no'} | {notes} |"
        )

    for result in report["cases"]:
        lines.extend(
            [
                "",
                f"## {result['case_id']} - {result['case_name']}",
                "",
                "### Checks",
                "",
                "```json",
                json.dumps(result["checks"], indent=2, default=str),
                "```",
                "",
                "### Notes",
                "",
                *(result.get("notes") or ["No notes."]),
                "",
                "### Full Decision Output",
                "",
                "```json",
                json.dumps(result["output"], indent=2, default=str),
                "```",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def component_simulation_note(failed_agents: list[str]) -> dict[str, Any] | None:
    if not failed_agents:
        return None
    return {
        "simulated_failure": True,
        "failed_agents": failed_agents,
        "manual_review_recommended": True,
        "note": "Eval harness simulated a component failure without changing the production pipeline.",
    }


def money_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value).replace("₹", "").replace(",", "").strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid money value: {value}") from exc


def money_text(value: Any) -> str:
    return str(money_decimal(value))


def none_or_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


if __name__ == "__main__":
    main()