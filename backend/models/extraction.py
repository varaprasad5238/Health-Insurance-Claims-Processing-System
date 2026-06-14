from datetime import date
from decimal import Decimal
from typing import Optional, List, Literal, Dict
from pydantic import BaseModel

class LineItem(BaseModel):
    description: str
    amount: Decimal
    coverage_hint: Literal["COVERED", "EXCLUDED", "UNCERTAIN"]

class DocumentUpload(BaseModel):
    file_id: str
    mime_type: str
    raw_bytes: Optional[bytes] = None
    url: Optional[str] = None

class TypedDocument(BaseModel):
    file_id: str
    detected_type: Literal["PRESCRIPTION", "HOSPITAL_BILL", "LAB_REPORT", "PHARMACY_BILL", "DENTAL_REPORT", "DISCHARGE_SUMMARY"]
    confidence: float

class GatingResult(BaseModel):
    passed: bool = True
    documents_typed: List[TypedDocument]

class GatingError(BaseModel):
    passed: bool = False
    error_code: Literal["WRONG_TYPE", "UNREADABLE", "PATIENT_MISMATCH", "MISSING_REQUIRED"]
    human_message: str
    detail: dict

class VisionReadingResult(BaseModel):
    file_id: str
    raw_transcript: str
    readability_score: float
    quality_flags: List[Literal["HANDWRITTEN", "STAMP_OVER_TEXT", "LOW_CONTRAST", "PARTIAL_PAGE", "MULTILINGUAL", "ALTERATION_MARK"]]
    field_confidences: Dict[str, float]
    agent_status: Literal["SUCCESS", "PARTIAL", "TIMEOUT", "ERROR"]

class ExtractionResult(BaseModel):
    patient_name: Optional[str] = None
    doctor_name: Optional[str] = None
    doctor_registration: Optional[str] = None
    doctor_registration_valid: Optional[bool] = None
    diagnosis_primary: Optional[str] = None
    diagnosis_icd_hint: Optional[str] = None
    treatment_date: Optional[date] = None
    hospital_name: Optional[str] = None
    is_network_hospital: Optional[bool] = None
    line_items: List[LineItem] = []
    amount_claimed: Optional[Decimal] = None
    field_confidences: Dict[str, float] = {}
    agent_status: Literal["SUCCESS", "PARTIAL", "TIMEOUT", "ERROR"]

class DiscrepancyFlag(BaseModel):
    type: str
    expected: Decimal
    found: Decimal

class FraudIndicator(BaseModel):
    type: str
    source: str

class ReconciliationResult(BaseModel):
    bill_total_extracted: Optional[Decimal] = None
    line_items_sum: Optional[Decimal] = None
    claimed_amount: Decimal
    discrepancy_flags: List[DiscrepancyFlag] = []
    fraud_indicators: List[FraudIndicator] = []
    agent_status: Literal["SUCCESS", "PARTIAL", "TIMEOUT", "ERROR"]

class ConflictEntry(BaseModel):
    field: str
    resolution_strategy: str

class MergedClaim(BaseModel):
    patient_name: Optional[str] = None
    doctor_name: Optional[str] = None
    doctor_registration: Optional[str] = None
    diagnosis_primary: Optional[str] = None
    treatment_date: Optional[date] = None
    hospital_name: Optional[str] = None
    is_network_hospital: Optional[bool] = None
    line_items: List[LineItem] = []
    amount_claimed: Optional[Decimal] = None
    extraction_confidence: float
    failed_agents: List[str] = []
    conflict_log: List[ConflictEntry] = []
