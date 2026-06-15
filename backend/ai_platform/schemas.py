from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

DocumentType = Literal[
    "PRESCRIPTION",
    "HOSPITAL_BILL",
    "LAB_REPORT",
    "PHARMACY_BILL",
    "DENTAL_REPORT",
    "DISCHARGE_SUMMARY",
    "UNKNOWN",
]

QualityFlag = Literal[
    "HANDWRITTEN",
    "STAMP_OVER_TEXT",
    "LOW_CONTRAST",
    "PARTIAL_PAGE",
    "MULTILINGUAL",
    "ALTERATION_MARK",
]


class DocumentVisionOutput(BaseModel):
    document_type: DocumentType
    confidence: float = Field(ge=0.0, le=1.0)
    readability: float = Field(ge=0.0, le=1.0)
    patient_name_raw: str | None = None
    quality_flags: list[QualityFlag] = Field(default_factory=list)
    transcript: str
    source_file_name: str | None = None
    source_page_range: str | None = None

    @field_validator("source_page_range", mode="before")
    @classmethod
    def coerce_source_page_range(cls, value):
        if value is None or isinstance(value, str):
            return value
        if isinstance(value, list):
            return ",".join(str(item) for item in value)
        return str(value)


class DocumentVisionListOutput(BaseModel):
    documents: list[DocumentVisionOutput] = Field(default_factory=list)

class VisionReadingOutput(BaseModel):
    raw_transcript: str
    readability: float = Field(ge=0.0, le=1.0)
    quality_flags: list[QualityFlag] = Field(default_factory=list)
    unclear_regions: list[str] = Field(default_factory=list)


class LineItemOutput(BaseModel):
    description: str
    amount: str
    coverage_hint: Literal["COVERED", "EXCLUDED", "UNCERTAIN"] = "UNCERTAIN"


class StructuredExtractionOutput(BaseModel):
    patient_name: str | None = None
    doctor_name: str | None = None
    doctor_registration: str | None = None
    diagnosis_primary: str | None = None
    treatment_date: str | None = None
    hospital_name: str | None = None
    line_items: list[LineItemOutput] = Field(default_factory=list)
    total_amount: str | None = None
    field_confidences: dict[str, float] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)


class DecisionMessageOutput(BaseModel):
    member_message: str
    ops_summary: str


class LLMResult(BaseModel):
    model: str
    raw_text: str | None = None
    latency_ms: int | None = None
    fallback_used: bool = False
    primary_error: str | None = None
