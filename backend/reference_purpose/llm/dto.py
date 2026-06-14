from typing import Optional, Any

from pydantic import BaseModel


class LLMTuningParamsDTO(BaseModel):
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None


class LLMRequestOpts(BaseModel):
    model: str
    streaming: bool = False
    parameters: Optional[LLMTuningParamsDTO] = None


class LLMChatRequestDTO(BaseModel):
    source: str = "slingshot_lcm"
    message: str
    additional_user_messages: list[str] = []
    system_prompt: str = ""
    options: LLMRequestOpts


class LLMChatResponseDTO(BaseModel):
    text: str
    raw_response: Any = {}
    usage: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    error: Optional[str] = None

    def has_error(self) -> bool:
        """Check if the response contains an error."""
        return self.error is not None
