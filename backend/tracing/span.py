from datetime import datetime
from typing import Optional, List, Literal, Dict, Any
from pydantic import BaseModel

class TraceSpan(BaseModel):
    span_id: str
    claim_id: str
    agent_name: str
    stage_order: int
    started_at: datetime
    ended_at: Optional[datetime] = None
    elapsed_ms: Optional[int] = None
    input_summary: Optional[Dict[str, Any]] = None
    output_summary: Optional[Dict[str, Any]] = None
    confidence_delta: Optional[float] = None
    errors: List[str] = []
    status: Literal["RUNNING", "SUCCESS", "PARTIAL", "TIMEOUT", "ERROR", "SKIPPED"]
    model_used: str = "none"
