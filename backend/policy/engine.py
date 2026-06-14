import json
from pathlib import Path
from typing import List, Optional
from backend.models.policy import Policy
from backend.models.claim import Claim
from backend.models.extraction import MergedClaim
from backend.tracing.decorator import traced
from pydantic import BaseModel

class RuleResult(BaseModel):
    rule_id: str
    outcome: str
    reason: str
    approved_amount: Optional[float] = None
    deducted_amount: Optional[float] = None
    deduction_reason: Optional[str] = None

class PolicyEngine:
    def __init__(self, policy: Policy):
        self.policy = policy

    @traced("policy_engine")
    def evaluate(self, claim_id: str, merged_claim: MergedClaim) -> List[RuleResult]:
        # Evaluates 14 ordered rules
        results = []
        # Mock logic
        results.append(RuleResult(rule_id="ELIGIBILITY", outcome="PASS", reason="Member is eligible"))
        return results
