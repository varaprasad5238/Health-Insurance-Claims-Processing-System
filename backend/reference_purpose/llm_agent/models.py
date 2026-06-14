import datetime

from pydantic import BaseModel


class Metrics(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int


class ToolCall(BaseModel):
    metrics: Metrics
    timestamp: datetime.datetime
    request: str
    response: str


class FinalResponse(BaseModel):
    content: str
    timestamp: datetime.datetime
    metrics: Metrics


class AgentResponse(BaseModel):
    tool_calls: list[ToolCall]
    final_response: FinalResponse
