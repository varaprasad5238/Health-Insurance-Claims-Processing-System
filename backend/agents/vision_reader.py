from typing import Any

from backend.ai_platform.llm import get_llm_platform
from backend.ai_platform.prompts import DOCUMENT_CLASSIFICATION_PROMPT
from backend.ai_platform.schemas import DocumentVisionOutput
from backend.ai_platform.llm import parse_model_json
from backend.tracing.store import TraceStore
from backend.logging_config import get_logger

logger = get_logger(__name__)


class VisionReaderAgent:
	stage_order = 1
	model_used = "vision-platform"

	async def classify_document(
		self,
		*,
		claim_id: str,
		document_index: int,
		document: dict[str, Any],
		claim_category: str,
	) -> DocumentVisionOutput:
		agent_name = f"vision_read_doc_{document_index}"
		input_summary = {
			"file_name": document["file_name"],
			"content_type": document["content_type"],
			"size_bytes": document.get("size_bytes"),
			"claim_category": claim_category,
		}
		span_id = await TraceStore.start_span(
			claim_id,
			agent_name,
			stage_order=self.stage_order,
			input_summary=input_summary,
			model_used=self.model_used,
			current_stage=agent_name,
		)
		try:
			logger.info("Classifying document: claim_id=%s document=%s file=%s", claim_id, document_index, document["file_name"])
			result = await get_llm_platform().get_llm_response(
				prompt=DOCUMENT_CLASSIFICATION_PROMPT,
				image_bytes=document.get("raw_bytes"),
				mime_type=document.get("content_type"),
				context=input_summary,
			)
			classification = parse_model_json(result.raw_text or "", DocumentVisionOutput)
			logger.info(
				"Document classified: claim_id=%s document=%s type=%s readability=%s model=%s fallback=%s",
				claim_id,
				document_index,
				classification.document_type,
				classification.readability,
				result.model,
				result.fallback_used,
			)
			await TraceStore.finish_span(
				span_id,
				status="SUCCESS",
				output_summary={
					"document_type": classification.document_type,
					"readability": classification.readability,
					"quality_flags": classification.quality_flags,
					"confidence": classification.confidence,
					"patient_name_raw": classification.patient_name_raw,
					"transcript": classification.transcript,
					"model_used": result.model,
					"fallback_used": result.fallback_used,
					"primary_error": result.primary_error,
				},
				confidence_delta=0.02,
				current_stage=None,
			)
			return classification
		except Exception as exc:
			logger.exception("Document classification failed: claim_id=%s document=%s", claim_id, document_index)
			await TraceStore.finish_span(
				span_id,
				status="ERROR",
				output_summary=None,
				errors=[str(exc)],
				current_stage=None,
			)
			raise
