from typing import Any

from pydantic import BaseModel, Field


class PolicyMemberDTO(BaseModel):
    member_id: str
    name: str
    relationship: str
    primary_member_id: str | None = None
    join_date: str | None = None
    annual_opd_limit: str
    ytd_claimed_amount: str
    remaining_opd_limit: str


class PolicyWithMembersDTO(BaseModel):
    policy_id: str
    policy_name: str
    insurer: str
    company_name: str
    status: str
    full_pledged_amount: str
    annual_opd_limit: str
    remaining_opd_limit: str
    family_floater_limit: str | None = None
    family_floater_remaining: str | None = None
    members: list[PolicyMemberDTO] = Field(default_factory=list)


class PoliciesMembersResponse(BaseModel):
    policies: list[PolicyWithMembersDTO]


class PolicyOptionsResponse(BaseModel):
    network_hospitals: list[str]
    minimum_claim_amount: int
    per_claim_limit: int
    claim_categories: list[str]


class LLMMetricSummaryResponse(BaseModel):
    total_calls: int
    successful_calls: int
    failed_calls: int
    fallback_calls: int
    success_rate: float
    fallback_rate: float
    avg_latency_ms: float
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    by_provider: dict[str, int]
    by_agent: dict[str, int]
    tokens_by_provider: dict[str, dict[str, int]]
    tokens_by_agent: dict[str, dict[str, int]]
    by_error: dict[str, int]


class LLMMetricRecentItem(BaseModel):
    metric_id: str
    claim_id: str | None = None
    agent_name: str
    provider: str
    model: str
    is_fallback: bool
    primary_error: str | None = None
    latency_ms: int | None = None
    status: str
    error_category: str | None = None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    created_at: str


class LLMMetricRecentResponse(BaseModel):
    metrics: list[LLMMetricRecentItem]


class SubmitClaimResponse(BaseModel):
    claim_id: str
    status: str
    trace_id: str


class TestSuiteCaseResponse(BaseModel):
    case_id: str
    case_name: str | None = None
    description: str | None = None
    member_id: str | None = None
    claim_category: str | None = None
    claimed_amount: int | float | str | None = None
    expected_decision: str | None = None
    expected_approved_amount: int | float | str | None = None
    documents: list[str] = Field(default_factory=list)
    test_context: dict[str, Any] = Field(default_factory=dict)
    api_mode_note: str


class TestSuiteCasesResponse(BaseModel):
    cases: list[TestSuiteCaseResponse]


class RunTestSuiteCaseResponse(BaseModel):
    case_id: str
    claim_id: str
    status: str
    trace_id: str
    expected: dict[str, Any]
    same_day_claim_count: int
    simulation_note: dict[str, Any] | None = None


class ClaimSummaryDTO(BaseModel):
    claim_id: str
    member_id: str
    member_name: str | None = None
    member_relationship: str | None = None
    member_remaining_opd_limit: str | None = None
    policy_id: str
    policy_name: str | None = None
    policy_remaining_opd_limit: str | None = None
    policy_full_pledged_amount: str | None = None
    claim_category: str
    claimed_amount: str
    status: str
    current_stage: str | None = None
    updated_at: str
    created_at: str
    decision: str | None = None
    approved_amount: str | None = None
    confidence_score: float | None = None


class ClaimsListResponse(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    claims: list[ClaimSummaryDTO]


class TraceSpanDTO(BaseModel):
    span_id: str
    agent_name: str
    stage_order: int
    status: str
    elapsed_ms: int | None = None
    started_at: str
    ended_at: str | None = None
    input_summary: Any | None = None
    output_summary: Any | None = None
    confidence_delta: float | None = None
    errors: list[Any] = Field(default_factory=list)
    model_used: str | None = None


class ClaimDecisionDTO(BaseModel):
    decision: str
    approved_amount: str
    copay_deducted: str
    network_discount_applied: str
    rejection_reasons: list[Any] = Field(default_factory=list)
    partial_items: Any | None = None
    member_message: str
    ops_summary: str
    confidence_score: float
    manual_review_note: str | None = None


class GatingErrorDTO(BaseModel):
    error_code: str
    human_message: str
    detail: Any | None = None


class ClaimStatusResponse(BaseModel):
    claim_id: str
    claimed_amount: str
    claim_category: str
    member_id: str
    status: str
    current_stage: str | None = None
    updated_at: str
    spans: list[TraceSpanDTO]
    decision: ClaimDecisionDTO | None = None
    gating_error: GatingErrorDTO | None = None
