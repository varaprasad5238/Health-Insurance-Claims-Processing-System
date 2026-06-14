from datetime import date
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field

class ClaimSummary(BaseModel):
    claim_id: str
    treatment_date: date
    claimed_amount: Decimal
    approved_amount: Decimal
    status: str

class Member(BaseModel):
    member_id: str
    name: str
    date_of_birth: date
    join_date: date
    relationship: str
    primary_member_id: Optional[str] = None
    ytd_claimed: Decimal = Field(default=Decimal("0.0"))
    claims_history: List[ClaimSummary] = Field(default_factory=list)
