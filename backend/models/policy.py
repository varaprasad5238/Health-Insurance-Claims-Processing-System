from typing import List, Dict, Optional
from pydantic import BaseModel

class PolicyHolder(BaseModel):
    company_name: str
    employee_count: int
    policy_start_date: str
    policy_end_date: str
    renewal_status: str

class FamilyFloater(BaseModel):
    enabled: bool
    combined_limit: int
    covered_relationships: List[str]

class CoverageConfig(BaseModel):
    sum_insured_per_employee: int
    annual_opd_limit: int
    per_claim_limit: int
    family_floater: FamilyFloater

class OPDCategory(BaseModel):
    sub_limit: int
    copay_percent: int
    network_discount_percent: int = 0
    requires_prescription: bool
    requires_pre_auth: bool = False
    covered: bool
    branded_drug_copay_percent: Optional[int] = None
    generic_mandatory: Optional[bool] = None
    requires_dental_report: Optional[bool] = None
    covered_procedures: Optional[List[str]] = None
    excluded_procedures: Optional[List[str]] = None
    covered_items: Optional[List[str]] = None
    excluded_items: Optional[List[str]] = None
    requires_registered_practitioner: Optional[bool] = None
    max_sessions_per_year: Optional[int] = None
    covered_systems: Optional[List[str]] = None
    pre_auth_threshold: Optional[int] = None
    high_value_tests_requiring_pre_auth: Optional[List[str]] = None

class WaitingPeriods(BaseModel):
    initial_waiting_period_days: int
    pre_existing_conditions_days: int
    specific_conditions: Dict[str, int]

class ExclusionList(BaseModel):
    conditions: List[str]
    dental_exclusions: List[str]
    vision_exclusions: List[str]

class PreAuthConfig(BaseModel):
    required_for: List[str]
    validity_days: int

class SubmissionRules(BaseModel):
    deadline_days_from_treatment: int
    minimum_claim_amount: int
    currency: str

class DocumentRequirements(BaseModel):
    required: List[str]
    optional: List[str]

class FraudThresholds(BaseModel):
    same_day_claims_limit: int
    monthly_claims_limit: int
    high_value_claim_threshold: int
    auto_manual_review_above: int
    fraud_score_manual_review_threshold: float

class PolicyMember(BaseModel):
    member_id: str
    name: str
    date_of_birth: str
    gender: Optional[str] = None
    relationship: str
    join_date: Optional[str] = None
    dependents: Optional[List[str]] = None
    primary_member_id: Optional[str] = None

class Policy(BaseModel):
    policy_id: str
    policy_name: str
    insurer: str
    policy_holder: PolicyHolder
    coverage: CoverageConfig
    opd_categories: Dict[str, OPDCategory]
    waiting_periods: WaitingPeriods
    exclusions: ExclusionList
    pre_authorization: PreAuthConfig
    network_hospitals: List[str]
    submission_rules: SubmissionRules
    document_requirements: Dict[str, DocumentRequirements]
    fraud_thresholds: FraudThresholds
    members: List[PolicyMember]
