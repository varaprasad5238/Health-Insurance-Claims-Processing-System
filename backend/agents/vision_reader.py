import asyncio
from typing import Any

from backend.ai_platform.llm import get_llm_platform
from backend.ai_platform.prompts import DOCUMENT_CLASSIFICATION_PROMPT
from backend.ai_platform.schemas import DocumentVisionListOutput, DocumentVisionOutput
from backend.ai_platform.llm import parse_model_json
from backend.ai_platform.errors import SchemaValidationFailed, InvalidModelOutput
from backend.tracing.store import TraceStore
from backend.logging_config import get_logger

logger = get_logger(__name__)


class VisionReaderAgent:
	stage_order = 1
	model_used = "vision-platform"
	max_documents = 4

	async def classify_documents(
		self,
		*,
		claim_id: str,
		documents: list[dict[str, Any]],
		claim_category: str,
	) -> list[DocumentVisionOutput]:
		if not documents:
			raise ValueError("At least one document is required for vision reading.")
		if len(documents) > self.max_documents:
			raise ValueError(f"A maximum of {self.max_documents} documents can be processed per claim.")

		logger.info("Classifying documents in parallel: claim_id=%s documents=%s", claim_id, len(documents))
		results = await asyncio.gather(
			*(
				self.classify_document(
					claim_id=claim_id,
					document_index=index,
					document=document,
					claim_category=claim_category,
				)
				for index, document in enumerate(documents, start=1)
			)
		)
		logical_documents: list[DocumentVisionOutput] = []
		for result in results:
			logical_documents.extend(result)
		return logical_documents

	async def classify_document(
		self,
		*,
		claim_id: str,
		document_index: int,
		document: dict[str, Any],
		claim_category: str,
	) -> list[DocumentVisionOutput]:
		agent_name = f"vision_read_doc_{document_index}"
		input_summary = {
			"file_name": document["file_name"],
			"content_type": document["content_type"],
			"size_bytes": document.get("size_bytes"),
			"source_page_range": document.get("source_page_range"),
			"source_upload_index": document.get("source_upload_index"),
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
		result = None
		try:
			logger.info("Classifying document: claim_id=%s document=%s file=%s", claim_id, document_index, document["file_name"])
			result = await get_llm_platform().get_llm_response(
				prompt=DOCUMENT_CLASSIFICATION_PROMPT,
				image_bytes=document.get("raw_bytes"),
				mime_type=document.get("content_type"),
				context=input_summary,
				claim_id=claim_id,
				agent_name=agent_name,
			)
			classification = parse_model_json(result.raw_text or "", DocumentVisionListOutput)
			logger.info(
				"Document classified: claim_id=%s upload=%s logical_documents=%s model=%s fallback=%s",
				claim_id,
				document_index,
				len(classification.documents),
				result.model,
				result.fallback_used,
			)
			await TraceStore.finish_span(
				span_id,
				status="SUCCESS",
				output_summary={
					"documents": [doc.model_dump() for doc in classification.documents],
					"logical_document_count": len(classification.documents),
					"model_used": result.model,
					"fallback_used": result.fallback_used,
					"primary_error": result.primary_error,
				},
				confidence_delta=0.02,
				current_stage=None,
			)
			return classification.documents
		except (SchemaValidationFailed, InvalidModelOutput) as exc:
			logger.exception("Document classification validation failed: claim_id=%s document=%s", claim_id, document_index)
			await TraceStore.finish_span(
				span_id,
				status="ERROR",
				output_summary={
					"raw_model_output": result.raw_text if result else None,
					"raw_model_output_preview": truncate_text(result.raw_text if result else None),
					"model_used": result.model if result else None,
					"fallback_used": result.fallback_used if result else None,
					"primary_error": result.primary_error if result else None,
				},
				errors=[str(exc)],
				current_stage=None,
			)
			raise
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


def truncate_text(value: str | None, limit: int = 1200) -> str | None:
	if value is None:
		return None
	return value if len(value) <= limit else value[:limit] + "...[truncated]"
