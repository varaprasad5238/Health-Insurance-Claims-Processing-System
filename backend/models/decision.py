from datetime import date
from decimal import Decimal
from typing import Optional, List, Literal
from pydantic import BaseModel

class RejectionReason(BaseModel):
    rule_id: str
    reason: str

class LineItemDecision(BaseModel):
    description: str
    amount: Decimal
    decision: Literal["APPROVED", "REJECTED"]
    reason: Optional[str] = None

class ClaimDecision(BaseModel):
    claim_id: str
    decision: Literal["APPROVED", "PARTIAL", "REJECTED", "MANUAL_REVIEW"]
    approved_amount: Decimal
    copay_deducted: Decimal
    network_discount_applied: Decimal
    rejection_reasons: List[RejectionReason]
    partial_items: Optional[List[LineItemDecision]] = None
    member_message: str
    ops_summary: str
    confidence_score: float
    manual_review_note: Optional[str] = None
    trace_id: str
