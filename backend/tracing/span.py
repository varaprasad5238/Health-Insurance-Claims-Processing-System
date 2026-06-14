from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel

TraceStatus = Literal["RUNNING", "SUCCESS", "PARTIAL", "TIMEOUT", "ERROR", "SKIPPED"]

STAGE_ORDER_BY_AGENT: dict[str, int] = {
    "vision_reader": 1,
    "gating": 2,
    "entity_extraction": 3,
    "amount_reconciler": 4,
    "orchestrator": 5,
    "policy_engine": 6,
    "decision_synthesis": 7,
    "final": 8,
}

def stage_order_for_agent(agent_name: str) -> int:
    if agent_name.startswith("vision_read_doc_"):
        return 1
    return STAGE_ORDER_BY_AGENT.get(agent_name, 99)

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
    status: TraceStatus
    model_used: str = "none"
