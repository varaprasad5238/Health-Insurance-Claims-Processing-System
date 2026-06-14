from datetime import date
from decimal import Decimal
from typing import Optional, Literal
from pydantic import BaseModel
from .decision import ClaimDecision

class Claim(BaseModel):
    claim_id: str
    member_id: str
    policy_id: str
    claim_category: Literal["CONSULTATION", "DIAGNOSTIC", "PHARMACY", "DENTAL", "VISION", "ALTERNATIVE_MEDICINE"]
    treatment_date: date
    submission_date: date
    claimed_amount: Decimal
    hospital_name: Optional[str] = None
    status: Literal["PENDING", "PROCESSING", "DECIDED", "MANUAL_REVIEW"]
    decision: Optional[ClaimDecision] = None
    trace_id: str
