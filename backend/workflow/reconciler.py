from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from pydantic import BaseModel, Field

from backend.ai_platform.schemas import StructuredExtractionOutput
from backend.logging_config import get_logger
from backend.tracing.store import TraceStore

logger = get_logger(__name__)


class DiscrepancyFlag(BaseModel):
	type: str
	expected: str | None = None
	found: str | None = None
	severity: str = "MEDIUM"
	message: str


class FraudIndicator(BaseModel):
	type: str
	source: str
	severity: str = "LOW"
	message: str


class AmountReconciliationResult(BaseModel):
	bill_total_extracted: str | None = None
	line_items_sum: str | None = None
	claimed_amount: str
	payable_basis_amount: str
	discrepancy_flags: list[DiscrepancyFlag] = Field(default_factory=list)
	fraud_indicators: list[FraudIndicator] = Field(default_factory=list)
	agent_status: str = "SUCCESS"


class AmountReconciliationStage:
	agent_name = "amount_reconciler"
	stage_order = 4

	async def reconcile(
		self,
		*,
		claim_id: str,
		claimed_amount: str,
		extraction: StructuredExtractionOutput,
	) -> AmountReconciliationResult:
		span_id = await TraceStore.start_span(
			claim_id,
			self.agent_name,
			stage_order=self.stage_order,
			input_summary={
				"claimed_amount": claimed_amount,
				"extracted_total": extraction.total_amount,
				"line_items": len(extraction.line_items),
			},
			current_stage=self.agent_name,
		)
		try:
			result = self.evaluate(claimed_amount=claimed_amount, extraction=extraction)
			await TraceStore.finish_span(
				span_id,
				status="SUCCESS" if not result.discrepancy_flags else "PARTIAL",
				output_summary=result.model_dump(),
				confidence_delta=-0.05 if result.discrepancy_flags else 0.02,
				current_stage=None,
			)
			logger.info(
				"Amount reconciliation completed: claim_id=%s discrepancies=%s fraud_indicators=%s",
				claim_id,
				len(result.discrepancy_flags),
				len(result.fraud_indicators),
			)
			return result
		except Exception as exc:
			logger.exception("Amount reconciliation failed: claim_id=%s", claim_id)
			await TraceStore.finish_span(
				span_id,
				status="ERROR",
				output_summary=None,
				errors=[str(exc)],
				current_stage=None,
			)
			raise

	def evaluate(self, *, claimed_amount: str, extraction: StructuredExtractionOutput) -> AmountReconciliationResult:
		claimed = parse_money(claimed_amount)
		extracted_total = parse_money(extraction.total_amount) if extraction.total_amount else None
		line_sum = sum((parse_money(item.amount) for item in extraction.line_items), Decimal("0.00")) if extraction.line_items else None
		discrepancy_flags: list[DiscrepancyFlag] = []
		fraud_indicators: list[FraudIndicator] = []

		if extracted_total is not None and line_sum is not None and abs(extracted_total - line_sum) > Decimal("1.00"):
			discrepancy_flags.append(
				DiscrepancyFlag(
					type="TOTAL_MISMATCH",
					expected=money(line_sum),
					found=money(extracted_total),
					severity="HIGH",
					message=f"Line items sum to {money(line_sum)}, but extracted bill total is {money(extracted_total)}.",
				)
			)

		comparison_total = extracted_total or line_sum
		if comparison_total is not None and abs(claimed - comparison_total) > Decimal("1.00"):
			discrepancy_flags.append(
				DiscrepancyFlag(
					type="CLAIMED_AMOUNT_MISMATCH",
					expected=money(comparison_total),
					found=money(claimed),
					severity="HIGH",
					message=f"Claimed amount is {money(claimed)}, but document amount is {money(comparison_total)}.",
				)
			)

		transcript_missing_total = extracted_total is None and line_sum is None
		if transcript_missing_total:
			discrepancy_flags.append(
				DiscrepancyFlag(
					type="AMOUNT_NOT_FOUND",
					severity="HIGH",
					message="No reliable amount was extracted from the uploaded documents.",
				)
			)

		payable_basis = min([amount for amount in [claimed, comparison_total] if amount is not None]) if comparison_total is not None else claimed

		if any("alter" in field.lower() or "correction" in field.lower() for field in extraction.missing_fields):
			fraud_indicators.append(
				FraudIndicator(
					type="POSSIBLE_ALTERATION",
					source="entity_extraction.missing_fields",
					severity="MEDIUM",
					message="Extraction reported possible alteration or correction-related uncertainty.",
				)
			)

		return AmountReconciliationResult(
			bill_total_extracted=money(extracted_total) if extracted_total is not None else None,
			line_items_sum=money(line_sum) if line_sum is not None else None,
			claimed_amount=money(claimed),
			payable_basis_amount=money(payable_basis),
			discrepancy_flags=discrepancy_flags,
			fraud_indicators=fraud_indicators,
			agent_status="PARTIAL" if discrepancy_flags else "SUCCESS",
		)


def parse_money(value: str) -> Decimal:
	try:
		normalized = str(value).replace("₹", "").replace(",", "").strip()
		return Decimal(normalized).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
	except (InvalidOperation, ValueError) as exc:
		raise ValueError(f"Invalid money value: {value}") from exc


def money(value: Decimal) -> str:
	return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
