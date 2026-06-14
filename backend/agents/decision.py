from backend.agents.orchestrator import MergedClaimResult
from backend.ai_platform.llm import get_llm_platform, parse_model_json
from backend.ai_platform.prompts import DECISION_SYNTHESIS_PROMPT
from backend.ai_platform.schemas import DecisionMessageOutput
from backend.logging_config import get_logger
from backend.policy.engine import PolicyDecisionResult
from backend.tracing.store import TraceStore

logger = get_logger(__name__)


class DecisionSynthesisAgent:
	agent_name = "decision_synthesis"
	stage_order = 7
	model_used = "llm-platform"

	async def synthesize(
		self,
		*,
		claim_id: str,
		policy_decision: PolicyDecisionResult,
		merged_claim: MergedClaimResult,
	) -> PolicyDecisionResult:
		span_id = await TraceStore.start_span(
			claim_id,
			self.agent_name,
			stage_order=self.stage_order,
			input_summary={
				"decision": policy_decision.decision,
				"approved_amount": policy_decision.approved_amount,
				"rejection_reasons": policy_decision.rejection_reasons,
				"rules": len(policy_decision.rule_results),
			},
			model_used=self.model_used,
			current_stage=self.agent_name,
		)
		try:
			logger.info("Synthesizing decision message: claim_id=%s decision=%s", claim_id, policy_decision.decision)
			result = await get_llm_platform().get_llm_response(
				prompt=DECISION_SYNTHESIS_PROMPT,
				context={
					"task": "decision_synthesis",
					"policy_decision": policy_decision.model_dump(),
					"merged_claim": merged_claim.model_dump(),
				},
			)
			message = parse_model_json(result.raw_text or "", DecisionMessageOutput)
			synthesized = policy_decision.model_copy(
				update={
					"member_message": message.member_message,
					"ops_summary": message.ops_summary,
				}
			)
			await TraceStore.finish_span(
				span_id,
				status="SUCCESS",
				output_summary={
					"decision": synthesized.decision,
					"approved_amount": synthesized.approved_amount,
					"member_message": synthesized.member_message,
					"ops_summary": synthesized.ops_summary,
					"model_used": result.model,
					"fallback_used": result.fallback_used,
					"primary_error": result.primary_error,
					"template_fallback_used": False,
				},
				current_stage=None,
			)
			return synthesized
		except Exception as exc:
			logger.exception("Decision synthesis LLM failed; using policy template: claim_id=%s", claim_id)
			await TraceStore.finish_span(
				span_id,
				status="PARTIAL",
				output_summary={
					"decision": policy_decision.decision,
					"approved_amount": policy_decision.approved_amount,
					"member_message": policy_decision.member_message,
					"ops_summary": policy_decision.ops_summary,
					"template_fallback_used": True,
				},
				errors=[str(exc)],
				current_stage=None,
			)
			return policy_decision
