import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.ai_platform.schemas import DocumentVisionOutput
from backend.database.connection import AsyncSessionLocal
from backend.database.models import GatingErrorModel
from backend.tracing.store import TraceStore


READABILITY_THRESHOLD = 0.4


class GatingPassed(BaseModel):
	passed: Literal[True] = True
	docs_validated: int
	patient_name_match: bool
	required_docs: list[str]
	found_docs: list[str]
	patient_names: list[str] = Field(default_factory=list)


class GatingFailed(BaseModel):
	passed: Literal[False] = False
	error_code: Literal["WRONG_TYPE", "UNREADABLE", "PATIENT_MISMATCH", "MISSING_REQUIRED"]
	human_message: str
	detail: dict[str, Any]


GatingOutcome = GatingPassed | GatingFailed


class DocumentGatingStage:
	agent_name = "gating"
	stage_order = 2

	def __init__(self, policy_path: Path | None = None):
		self.policy_path = policy_path or Path(__file__).resolve().parents[2] / "assignment" / "policy_terms.json"

	async def run(
		self,
		*,
		claim_id: str,
		claim_category: str,
		documents: list[DocumentVisionOutput],
	) -> GatingOutcome:
		required_docs = self.required_documents_for(claim_category)
		found_docs = [document.document_type for document in documents]
		span_id = await TraceStore.start_span(
			claim_id,
			self.agent_name,
			stage_order=self.stage_order,
			input_summary={
				"claim_category": claim_category,
				"required_docs": required_docs,
				"found_docs": found_docs,
				"documents": len(documents),
			},
			current_stage=self.agent_name,
		)

		outcome = self.evaluate(claim_category=claim_category, documents=documents, required_docs=required_docs)
		if outcome.passed:
			await TraceStore.finish_span(
				span_id,
				status="SUCCESS",
				output_summary=outcome.model_dump(),
				confidence_delta=0.03,
				current_stage=None,
			)
			return outcome

		await self.write_gating_error(claim_id=claim_id, failure=outcome)
		await TraceStore.finish_span(
			span_id,
			status="ERROR",
			output_summary=outcome.model_dump(),
			errors=[outcome.human_message],
			current_stage=None,
			claim_status="GATING_FAILED",
		)
		return outcome

	def required_documents_for(self, claim_category: str) -> list[str]:
		with self.policy_path.open("r", encoding="utf-8") as policy_file:
			policy = json.load(policy_file)
		requirements = policy["document_requirements"].get(claim_category)
		if not requirements:
			return []
		return list(requirements.get("required", []))

	def evaluate(
		self,
		*,
		claim_category: str,
		documents: list[DocumentVisionOutput],
		required_docs: list[str],
	) -> GatingOutcome:
		found_docs = [document.document_type for document in documents]

		unreadable = [document for document in documents if document.readability < READABILITY_THRESHOLD]
		if unreadable:
			document = unreadable[0]
			return GatingFailed(
				error_code="UNREADABLE",
				human_message=(
					f"The {friendly_doc_type(document.document_type)} is not readable enough to process. "
					"Please re-upload a clearer image or PDF of that document."
				),
				detail={
					"document_type": document.document_type,
					"readability": document.readability,
					"threshold": READABILITY_THRESHOLD,
				},
			)

		missing = missing_required_docs(required_docs=required_docs, found_docs=found_docs)
		if missing:
			duplicate_types = duplicate_document_types(found_docs)
			error_code = "WRONG_TYPE" if duplicate_types else "MISSING_REQUIRED"
			return GatingFailed(
				error_code=error_code,
				human_message=missing_docs_message(
					claim_category=claim_category,
					required_docs=required_docs,
					found_docs=found_docs,
					missing_docs=missing,
					duplicate_types=duplicate_types,
				),
				detail={
					"required": required_docs,
					"found": found_docs,
					"missing": missing,
					"duplicates": duplicate_types,
				},
			)

		patient_names = [document.patient_name_raw for document in documents if document.patient_name_raw]
		mismatch = first_patient_mismatch(patient_names)
		if mismatch:
			first_name, second_name = mismatch
			return GatingFailed(
				error_code="PATIENT_MISMATCH",
				human_message=(
					f"The uploaded documents appear to belong to different patients: {first_name} and {second_name}. "
					"Please upload documents for the same patient."
				),
				detail={"patient_names": patient_names, "first": first_name, "second": second_name},
			)

		return GatingPassed(
			docs_validated=len(documents),
			patient_name_match=True,
			required_docs=required_docs,
			found_docs=found_docs,
			patient_names=patient_names,
		)

	async def write_gating_error(self, *, claim_id: str, failure: GatingFailed) -> None:
		async with AsyncSessionLocal() as session:
			existing = await session.get(GatingErrorModel, claim_id)
			if existing:
				await session.delete(existing)
				await session.flush()
			session.add(
				GatingErrorModel(
					claim_id=claim_id,
					error_code=failure.error_code,
					human_message=failure.human_message,
					detail=json.dumps(failure.detail, default=str),
					occurred_at=datetime.now(timezone.utc).isoformat(),
				)
			)
			await session.commit()


def missing_required_docs(*, required_docs: list[str], found_docs: list[str]) -> list[str]:
	found_counts = Counter(found_docs)
	missing: list[str] = []
	for required_doc in required_docs:
		if found_counts[required_doc] > 0:
			found_counts[required_doc] -= 1
		else:
			missing.append(required_doc)
	return missing


def duplicate_document_types(found_docs: list[str]) -> list[str]:
	counts = Counter(found_docs)
	return [doc_type for doc_type, count in counts.items() if count > 1]


def missing_docs_message(
	*,
	claim_category: str,
	required_docs: list[str],
	found_docs: list[str],
	missing_docs: list[str],
	duplicate_types: list[str],
) -> str:
	if duplicate_types:
		duplicate_text = ", ".join(friendly_doc_type(doc_type) for doc_type in duplicate_types)
		required_text = ", ".join(friendly_doc_type(doc_type) for doc_type in required_docs)
		missing_text = ", ".join(friendly_doc_type(doc_type) for doc_type in missing_docs)
		return (
			f"You uploaded duplicate {duplicate_text} documents, but a {claim_category.lower().replace('_', ' ')} claim "
			f"requires {required_text}. Please upload the missing {missing_text}."
		)
	missing_text = ", ".join(friendly_doc_type(doc_type) for doc_type in missing_docs)
	found_text = ", ".join(friendly_doc_type(doc_type) for doc_type in found_docs) or "no recognizable documents"
	return (
		f"A {claim_category.lower().replace('_', ' ')} claim requires {missing_text}. "
		f"We found {found_text}. Please upload the required document."
	)


def friendly_doc_type(document_type: str) -> str:
	return document_type.lower().replace("_", " ")


def normalize_name(name: str) -> str:
	return re.sub(r"[^a-z]", "", name.lower())


def first_patient_mismatch(patient_names: list[str]) -> tuple[str, str] | None:
	if len(patient_names) < 2:
		return None
	baseline = patient_names[0]
	baseline_normalized = normalize_name(baseline)
	for candidate in patient_names[1:]:
		candidate_normalized = normalize_name(candidate)
		distance = levenshtein_distance(baseline_normalized, candidate_normalized)
		allowed_distance = max(2, int(max(len(baseline_normalized), len(candidate_normalized)) * 0.2))
		if distance > allowed_distance:
			return baseline, candidate
	return None


def levenshtein_distance(left: str, right: str) -> int:
	if left == right:
		return 0
	if not left:
		return len(right)
	if not right:
		return len(left)

	previous = list(range(len(right) + 1))
	for left_index, left_char in enumerate(left, start=1):
		current = [left_index]
		for right_index, right_char in enumerate(right, start=1):
			insert_cost = current[right_index - 1] + 1
			delete_cost = previous[right_index] + 1
			replace_cost = previous[right_index - 1] + (left_char != right_char)
			current.append(min(insert_cost, delete_cost, replace_cost))
		previous = current
	return previous[-1]
