from pydantic import BaseModel, Field

from backend.workflow.reconciler import AmountReconciliationResult
from backend.ai_platform.schemas import DocumentVisionOutput, LineItemOutput, StructuredExtractionOutput
from backend.logging_config import get_logger
from backend.tracing.store import TraceStore

logger = get_logger(__name__)


class ConflictEntry(BaseModel):
	field: str
	resolution_strategy: str
	reason: str


class MergedClaimResult(BaseModel):
	patient_name: str | None = None
	doctor_name: str | None = None
	doctor_registration: str | None = None
	diagnosis_primary: str | None = None
	treatment_date: str | None = None
	hospital_name: str | None = None
	line_items: list[LineItemOutput] = Field(default_factory=list)
	extracted_total_amount: str | None = None
	claimed_amount: str
	payable_basis_amount: str
	extraction_confidence: float
	failed_agents: list[str] = Field(default_factory=list)
	failed_stages: list[str] = Field(default_factory=list)
	conflict_log: list[ConflictEntry] = Field(default_factory=list)
	discrepancy_flags: list[dict] = Field(default_factory=list)
	fraud_indicators: list[dict] = Field(default_factory=list)
	document_confidence: float | None = None
	entity_confidence: float | None = None
	reconciliation_confidence: float | None = None


class ClaimMergeStage:
	agent_name = "orchestrator"
	stage_order = 5

	async def merge(
		self,
		*,
		claim_id: str,
		documents: list[DocumentVisionOutput],
		extraction: StructuredExtractionOutput,
		reconciliation: AmountReconciliationResult,
		failed_agents: list[str] | None = None,
	) -> MergedClaimResult:
		span_id = await TraceStore.start_span(
			claim_id,
			self.agent_name,
			stage_order=self.stage_order,
			input_summary={
				"documents": len(documents),
				"patient_name": extraction.patient_name,
				"diagnosis_primary": extraction.diagnosis_primary,
				"claimed_amount": reconciliation.claimed_amount,
				"payable_basis_amount": reconciliation.payable_basis_amount,
				"discrepancies": len(reconciliation.discrepancy_flags),
				"fraud_indicators": len(reconciliation.fraud_indicators),
				"failed_agents": failed_agents or [],
				"failed_stages": failed_agents or [],
			},
			current_stage=self.agent_name,
		)
		try:
			result = self.evaluate(
				documents=documents,
				extraction=extraction,
				reconciliation=reconciliation,
				failed_agents=failed_agents or [],
			)
			await TraceStore.finish_span(
				span_id,
				status="SUCCESS" if result.extraction_confidence >= 0.65 else "PARTIAL",
				output_summary={
					"merged_confidence": result.extraction_confidence,
					"failed_agents": result.failed_agents,
					"failed_stages": result.failed_stages,
					"conflicts_resolved": len(result.conflict_log),
					"patient_name": result.patient_name,
					"diagnosis_primary": result.diagnosis_primary,
					"payable_basis_amount": result.payable_basis_amount,
					"discrepancies": len(result.discrepancy_flags),
					"fraud_indicators": len(result.fraud_indicators),
					"document_confidence": result.document_confidence,
					"entity_confidence": result.entity_confidence,
					"reconciliation_confidence": result.reconciliation_confidence,
					"conflict_log": [conflict.model_dump() for conflict in result.conflict_log],
				},
				confidence_delta=round(result.extraction_confidence - 0.85, 3),
				current_stage=None,
			)
			logger.info(
				"Orchestration completed: claim_id=%s confidence=%s conflicts=%s failed_stages=%s",
				claim_id,
				result.extraction_confidence,
				len(result.conflict_log),
				len(result.failed_stages),
			)
			return result
		except Exception as exc:
			logger.exception("Orchestration failed: claim_id=%s", claim_id)
			await TraceStore.finish_span(
				span_id,
				status="ERROR",
				output_summary=None,
				errors=[str(exc)],
				current_stage=None,
			)
			raise

	def evaluate(
		self,
		*,
		documents: list[DocumentVisionOutput],
		extraction: StructuredExtractionOutput,
		reconciliation: AmountReconciliationResult,
		failed_agents: list[str],
	) -> MergedClaimResult:
		conflict_log: list[ConflictEntry] = []
		discrepancy_flags = [flag.model_dump() for flag in reconciliation.discrepancy_flags]
		fraud_indicators = [indicator.model_dump() for indicator in reconciliation.fraud_indicators]

		if reconciliation.discrepancy_flags:
			conflict_log.append(
				ConflictEntry(
					field="amount",
					resolution_strategy="Use reconciled payable_basis_amount for downstream placeholder decisioning.",
					reason="Amount reconciler found discrepancy flags.",
				)
			)

		document_confidence = compute_document_confidence(documents)
		entity_confidence = compute_entity_confidence(extraction.field_confidences)
		reconciliation_confidence = compute_reconciliation_confidence(
			discrepancy_count=len(reconciliation.discrepancy_flags),
			fraud_indicator_count=len(reconciliation.fraud_indicators),
		)

		confidence = compute_extraction_confidence(
			document_confidence=document_confidence,
			entity_confidence=entity_confidence,
			reconciliation_confidence=reconciliation_confidence,
			field_confidences=extraction.field_confidences,
			failed_agents=failed_agents,
			discrepancy_count=len(reconciliation.discrepancy_flags),
			fraud_indicator_count=len(reconciliation.fraud_indicators),
		)

		return MergedClaimResult(
			patient_name=extraction.patient_name,
			doctor_name=extraction.doctor_name,
			doctor_registration=extraction.doctor_registration,
			diagnosis_primary=extraction.diagnosis_primary,
			treatment_date=extraction.treatment_date,
			hospital_name=extraction.hospital_name,
			line_items=extraction.line_items,
			extracted_total_amount=extraction.total_amount,
			claimed_amount=reconciliation.claimed_amount,
			payable_basis_amount=reconciliation.payable_basis_amount,
			extraction_confidence=confidence,
			failed_agents=failed_agents,
			failed_stages=failed_agents,
			conflict_log=conflict_log,
			discrepancy_flags=discrepancy_flags,
			fraud_indicators=fraud_indicators,
			document_confidence=document_confidence,
			entity_confidence=entity_confidence,
			reconciliation_confidence=reconciliation_confidence,
		)


def compute_extraction_confidence(
	*,
	document_confidence: float,
	entity_confidence: float,
	reconciliation_confidence: float,
	field_confidences: dict[str, float],
	failed_agents: list[str],
	discrepancy_count: int,
	fraud_indicator_count: int,
) -> float:
	base_confidence = (document_confidence * 0.35) + (entity_confidence * 0.45) + (reconciliation_confidence * 0.20)
	penalty = (0.15 * len(failed_agents)) + (0.05 * discrepancy_count) + (0.08 * fraud_indicator_count)
	return round(max(0.0, min(1.0, base_confidence - penalty)), 3)


def compute_document_confidence(documents: list[DocumentVisionOutput]) -> float:
	if not documents:
		return 0.0
	scores = [(document.confidence * 0.60) + (document.readability * 0.40) for document in documents]
	return round(sum(scores) / len(scores), 3)


def compute_entity_confidence(field_confidences: dict[str, float]) -> float:
	weights = {
		"total_amount": 0.30,
		"amount": 0.30,
		"patient_name": 0.25,
		"diagnosis_primary": 0.20,
		"diagnosis": 0.20,
		"doctor_name": 0.15,
		"doctor_registration": 0.15,
		"treatment_date": 0.10,
	}
	weighted_total = 0.0
	weight_sum = 0.0
	for field, weight in weights.items():
		if field in field_confidences:
			weighted_total += field_confidences[field] * weight
			weight_sum += weight
	return round(weighted_total / weight_sum, 3) if weight_sum else 0.0


def compute_reconciliation_confidence(*, discrepancy_count: int, fraud_indicator_count: int) -> float:
	return round(max(0.0, 1.0 - (0.12 * discrepancy_count) - (0.18 * fraud_indicator_count)), 3)
