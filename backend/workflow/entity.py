from statistics import mean
from typing import Any

from backend.ai_platform.llm import get_llm_platform, parse_model_json
from backend.ai_platform.prompts import STRUCTURED_EXTRACTION_PROMPT
from backend.ai_platform.schemas import DocumentVisionOutput, StructuredExtractionOutput
from backend.logging_config import get_logger
from backend.policy.loader import get_policy
from backend.tracing.store import TraceStore

logger = get_logger(__name__)


class EntityExtractionStage:
	agent_name = "entity_extraction"
	stage_order = 3
	model_used = "llm-platform"

	async def extract(
		self,
		*,
		claim_id: str,
		claim_category: str,
		documents: list[DocumentVisionOutput],
	) -> StructuredExtractionOutput:
		input_summary = {
			"claim_category": claim_category,
			"documents": [
				{
					"document_type": document.document_type,
					"readability": document.readability,
					"patient_name_raw": document.patient_name_raw,
					"quality_flags": document.quality_flags,
					"transcript_chars": len(document.transcript or ""),
				}
				for document in documents
			],
		}
		span_id = await TraceStore.start_span(
			claim_id,
			self.agent_name,
			stage_order=self.stage_order,
			input_summary=input_summary,
			model_used=self.model_used,
			current_stage=self.agent_name,
		)
		try:
			logger.info("Extracting entities: claim_id=%s documents=%s", claim_id, len(documents))
			result = await get_llm_platform().get_llm_response(
				prompt=STRUCTURED_EXTRACTION_PROMPT,
				context={
					"task": "structured_extraction",
					"claim_category": claim_category,
					"policy_exclusions": get_policy().exclusions.conditions,
					"documents": [document.model_dump() for document in documents],
				},
				claim_id=claim_id,
				agent_name=self.agent_name,
			)
			extraction = parse_model_json(result.raw_text or "", StructuredExtractionOutput)
			confidence = average_confidence(extraction.field_confidences)
			await TraceStore.finish_span(
				span_id,
				status="SUCCESS",
				output_summary={
					"fields_extracted": count_extracted_fields(extraction),
					"confidence": confidence,
					"patient_name": extraction.patient_name,
					"diagnosis_primary": extraction.diagnosis_primary,
					"treatment_date": extraction.treatment_date,
					"hospital_name": extraction.hospital_name,
					"line_items": [item.model_dump() for item in extraction.line_items],
					"total_amount": extraction.total_amount,
					"missing_fields": extraction.missing_fields,
					"model_used": result.model,
					"fallback_used": result.fallback_used,
					"primary_error": result.primary_error,
				},
				confidence_delta=0.04,
				current_stage=None,
			)
			logger.info(
				"Entity extraction completed: claim_id=%s fields=%s confidence=%s model=%s fallback=%s",
				claim_id,
				count_extracted_fields(extraction),
				confidence,
				result.model,
				result.fallback_used,
			)
			return extraction
		except Exception as exc:
			logger.exception("Entity extraction failed: claim_id=%s", claim_id)
			await TraceStore.finish_span(
				span_id,
				status="ERROR",
				output_summary=None,
				errors=[str(exc)],
				current_stage=None,
			)
			raise


def average_confidence(confidences: dict[str, float]) -> float:
	values = [value for value in confidences.values() if isinstance(value, (int, float))]
	if not values:
		return 0.7
	return round(mean(values), 3)


def count_extracted_fields(extraction: StructuredExtractionOutput) -> int:
	scalar_fields = [
		extraction.patient_name,
		extraction.doctor_name,
		extraction.doctor_registration,
		extraction.diagnosis_primary,
		extraction.treatment_date,
		extraction.hospital_name,
		extraction.total_amount,
	]
	return sum(1 for value in scalar_fields if value) + len(extraction.line_items)
