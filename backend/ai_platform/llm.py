import asyncio
import base64
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from backend.ai_platform.config import PlatformSettings, get_platform_settings
from backend.ai_platform.errors import InvalidModelOutput, PlatformError, ProviderTimeout, ProviderUnavailable, SchemaValidationFailed
from backend.ai_platform.metrics import record_llm_metric
from backend.ai_platform.prompts import JSON_REPAIR_PROMPT
from backend.ai_platform.schemas import (
    DecisionMessageOutput,
    DocumentVisionOutput,
    DocumentVisionListOutput,
    LLMResult,
    StructuredExtractionOutput,
    VisionReadingOutput,
)
from backend.logging_config import get_logger

T = TypeVar("T", bound=BaseModel)
logger = get_logger(__name__)


@dataclass
class CircuitState:
    failures: int = 0
    opened_until: float = 0.0


_CIRCUITS: dict[str, CircuitState] = {}


def circuit_is_open(model: str) -> bool:
    state = _CIRCUITS.get(model)
    return bool(state and state.opened_until > time.time())


def record_model_success(model: str) -> None:
    _CIRCUITS.pop(model, None)


def record_model_failure(model: str, settings: PlatformSettings) -> None:
    state = _CIRCUITS.setdefault(model, CircuitState())
    state.failures += 1
    if state.failures >= settings.circuit_failure_threshold:
        state.opened_until = time.time() + settings.circuit_cooldown_seconds


def normalize_provider_error(exc: Exception) -> PlatformError:
    status_code = getattr(exc, "status_code", None)
    message = str(exc).strip() or type(exc).__name__
    lowered = message.lower()
    if status_code == 429 or "resource_exhausted" in lowered or "quota" in lowered or "rate" in lowered:
        return ProviderUnavailable("Gemini quota or rate limit exceeded", code="PROVIDER_QUOTA_EXCEEDED")
    if status_code in {401, 403} or "api key" in lowered or "permission" in lowered:
        return ProviderUnavailable("Gemini authentication or permission failed", code="PROVIDER_AUTH_FAILED")
    if status_code == 404 or "not found" in lowered or "unknown model" in lowered:
        return ProviderUnavailable("Configured Gemini model is unavailable", code="PROVIDER_MODEL_UNAVAILABLE")
    return ProviderUnavailable(f"Gemini request failed: {message}")


class BaseLLMClient(ABC):
    @abstractmethod
    async def get_llm_response(
        self,
        *,
        prompt: str,
        model: str | None = None,
        image_bytes: bytes | None = None,
        mime_type: str | None = None,
        context: dict[str, Any] | None = None,
        claim_id: str | None = None,
        agent_name: str | None = None,
    ) -> LLMResult:
        raise NotImplementedError


class StubLLMClient(BaseLLMClient):
    async def get_llm_response(
        self,
        *,
        prompt: str,
        model: str | None = None,
        image_bytes: bytes | None = None,
        mime_type: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> LLMResult:
        started = time.perf_counter()
        parsed = self._stub_payload(context or {})
        latency_ms = int((time.perf_counter() - started) * 1000)
        raw_text = parsed.model_dump_json()
        input_tokens = estimate_tokens(prompt, context=context, image_bytes=image_bytes)
        output_tokens = estimate_text_tokens(raw_text)
        return LLMResult(model=model or "stub-llm", raw_text=raw_text, latency_ms=latency_ms, input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=input_tokens + output_tokens)

    def _stub_payload(self, context: dict[str, Any]) -> BaseModel:
        if context.get("task") == "structured_extraction":
            return StructuredExtractionOutput(
                patient_name="Rajesh Kumar",
                doctor_name="Dr. Arun Sharma",
                doctor_registration="KA/45678/2015",
                diagnosis_primary="Viral Fever",
                treatment_date="2024-11-01",
                hospital_name="City Medical Centre",
                line_items=[
                    {"description": "Consultation Fee", "amount": "1000.00", "coverage_hint": "COVERED"},
                    {"description": "CBC Test", "amount": "200.00", "coverage_hint": "COVERED"},
                    {"description": "Dengue NS1 Test", "amount": "300.00", "coverage_hint": "COVERED"},
                ],
                total_amount="1500.00",
                field_confidences={
                    "patient_name": 0.95,
                    "doctor_name": 0.9,
                    "diagnosis_primary": 0.9,
                    "treatment_date": 0.9,
                    "total_amount": 0.95,
                },
                missing_fields=[],
            )
        if context.get("task") == "decision_synthesis":
            decision = context.get("policy_decision", {}).get("decision", "APPROVED")
            approved_amount = context.get("policy_decision", {}).get("approved_amount", "0.00")
            return DecisionMessageOutput(
                member_message=f"Your claim is {str(decision).lower()} for {approved_amount}.",
                ops_summary=f"Decision synthesis completed for {decision} with approved amount {approved_amount}.",
            )
        file_name = str(context.get("file_name", "")).lower()
        document_type = "PRESCRIPTION"
        if "bill" in file_name or "invoice" in file_name or "receipt" in file_name:
            document_type = "HOSPITAL_BILL"
        elif "lab" in file_name or "report" in file_name:
            document_type = "LAB_REPORT"
        elif "pharmacy" in file_name:
            document_type = "PHARMACY_BILL"
        return DocumentVisionListOutput(documents=[DocumentVisionOutput(
            document_type=document_type,
            confidence=0.92,
            readability=0.9,
            patient_name_raw=context.get("patient_name") or "Rajesh Kumar",
            quality_flags=[],
            transcript="Patient: Rajesh Kumar\nDiagnosis: Viral Fever\nTotal Amount: 1500.00",
            source_file_name=context.get("file_name"),
            source_page_range="1",
        )])


class GeminiLLMClient(BaseLLMClient):
    def __init__(self, settings: PlatformSettings):
        if not settings.gemini_api_key:
            raise ProviderUnavailable("GEMINI_API_KEY is required when LLM_PROVIDER=gemini")
        self.settings = settings

    async def get_llm_response(
        self,
        *,
        prompt: str,
        model: str | None = None,
        image_bytes: bytes | None = None,
        mime_type: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> LLMResult:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise ProviderUnavailable("Install google-genai to use Gemini: uv add google-genai") from exc

        selected_model = model or self.settings.vision_model
        logger.info("Calling Gemini: model=%s has_image=%s", selected_model, image_bytes is not None)
        client = genai.Client(api_key=self.settings.gemini_api_key)
        content: list[Any] = [prompt]
        if context:
            content.append(json.dumps(context, default=str))
        if image_bytes is not None:
            content.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type or "image/png"))

        started = time.perf_counter()
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=selected_model,
                    contents=content,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0,
                    ),
                ),
                timeout=self.settings.llm_timeout_seconds,
            )
        except TimeoutError as exc:
            raise ProviderTimeout(f"Gemini call exceeded {self.settings.llm_timeout_seconds}s") from exc
        except Exception as exc:
            raise normalize_provider_error(exc) from exc

        raw_text = response.text or ""
        latency_ms = int((time.perf_counter() - started) * 1000)
        input_tokens, output_tokens, total_tokens = extract_gemini_usage(response)
        if getattr(response, "usage_metadata", None) is None:
            input_tokens = estimate_tokens(prompt, context=context, image_bytes=image_bytes)
            output_tokens = estimate_text_tokens(raw_text)
            total_tokens = input_tokens + output_tokens
        logger.info("Gemini response received: model=%s latency_ms=%s", selected_model, latency_ms)
        return LLMResult(model=selected_model, raw_text=raw_text, latency_ms=latency_ms, input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=total_tokens)


class OpenAILLMClient(BaseLLMClient):
    def __init__(self, settings: PlatformSettings):
        if not settings.openai_api_key:
            raise ProviderUnavailable("OPENAI_API_KEY is required when using OpenAI")
        self.settings = settings

    async def get_llm_response(
        self,
        *,
        prompt: str,
        model: str | None = None,
        image_bytes: bytes | None = None,
        mime_type: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> LLMResult:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ProviderUnavailable("Install openai to use OpenAI fallback: uv add openai") from exc

        selected_model = model or self.settings.fallback_vision_model or "gpt-4o-mini"
        logger.info("Calling OpenAI: model=%s has_image=%s", selected_model, image_bytes is not None)
        client = OpenAI(api_key=self.settings.openai_api_key, base_url=self.settings.openai_base_url or None)
        text_parts = [prompt]
        if context:
            text_parts.append(json.dumps(context, default=str))

        user_message_content: str | list[dict[str, Any]] = "\n\n".join(text_parts)
        if image_bytes is not None:
            if mime_type and not mime_type.startswith("image/"):
                raise ProviderUnavailable(
                    f"OpenAI vision fallback currently supports image/* uploads, got {mime_type}",
                    code="PROVIDER_UNSUPPORTED_MIME",
                )
            encoded = base64.b64encode(image_bytes).decode("ascii")
            user_message_content = [
                {"type": "text", "text": "\n\n".join(text_parts)},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type or 'image/png'};base64,{encoded}"},
                },
            ]

        started = time.perf_counter()
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.chat.completions.create,
                    model=selected_model,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant. Return exactly what the user asks for."},
                        {"role": "user", "content": user_message_content},
                    ],
                ),
                timeout=self.settings.llm_timeout_seconds,
            )
        except TimeoutError as exc:
            raise ProviderTimeout(f"OpenAI call exceeded {self.settings.llm_timeout_seconds}s") from exc
        except Exception as exc:
            raise normalize_provider_error(exc) from exc

        raw_text = response.choices[0].message.content or ""
        latency_ms = int((time.perf_counter() - started) * 1000)
        input_tokens, output_tokens, total_tokens = extract_openai_usage(response)
        if total_tokens == 0:
            input_tokens = estimate_tokens(prompt, context=context, image_bytes=image_bytes)
            output_tokens = estimate_text_tokens(raw_text)
            total_tokens = input_tokens + output_tokens
        logger.info("OpenAI response received: model=%s latency_ms=%s", selected_model, latency_ms)
        return LLMResult(model=selected_model, raw_text=raw_text, latency_ms=latency_ms, input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=total_tokens)


class LLMPlatform:
    def __init__(self, client: BaseLLMClient | None, settings: PlatformSettings):
        self.client = client
        self.settings = settings
        self._clients: dict[str, BaseLLMClient] = {}
        if client is not None:
            self._clients[settings.llm_provider] = client

    def client_for_provider(self, provider: str) -> BaseLLMClient:
        provider = provider.strip().lower()
        if provider in self._clients:
            return self._clients[provider]
        if provider == "gemini":
            client = GeminiLLMClient(self.settings)
        elif provider == "openai":
            client = OpenAILLMClient(self.settings)
        elif provider == "stub":
            client = StubLLMClient()
        else:
            raise ProviderUnavailable(f"Unsupported LLM provider: {provider}")
        self._clients[provider] = client
        return client
    
    async def get_llm_response(
        self,
        *,
        prompt: str,
        model: str | None = None,
        image_bytes: bytes | None = None,
        mime_type: str | None = None,
        context: dict[str, Any] | None = None,
        claim_id: str | None = None,
        agent_name: str | None = None,
    ) -> LLMResult:
        last_error: Exception | None = None
        attempts = self.settings.llm_max_retries + 1
        primary_model = model or self.settings.vision_model
        fallback_model = self.settings.fallback_vision_model
        primary_provider = self.settings.llm_provider
        fallback_provider = self.settings.fallback_llm_provider or primary_provider
        candidates: list[tuple[str, str, bool, str | None]] = []
        if circuit_is_open(primary_model) and fallback_model and fallback_model != primary_model:
            candidates.append((fallback_provider, fallback_model, True, "CIRCUIT_OPEN"))
        else:
            candidates.append((primary_provider, primary_model, False, None))
            if fallback_model and (fallback_model != primary_model or fallback_provider != primary_provider):
                candidates.append((fallback_provider, fallback_model, True, None))

        primary_error: str | None = None
        for candidate_provider, candidate_model, fallback_used, circuit_reason in candidates:
            if circuit_reason:
                primary_error = circuit_reason
            for attempt in range(attempts):
                try:
                    logger.info(
                        "LLM attempt: provider=%s model=%s attempt=%s fallback=%s circuit_reason=%s",
                        candidate_provider,
                        candidate_model,
                        attempt + 1,
                        fallback_used,
                        circuit_reason,
                    )
                    active_prompt = prompt if attempt == 0 else f"{prompt}\n\n{JSON_REPAIR_PROMPT}"
                    result = await self.client_for_provider(candidate_provider).get_llm_response(
                        prompt=active_prompt,
                        model=candidate_model,
                        image_bytes=image_bytes,
                        mime_type=mime_type,
                        context=context,
                    )
                    record_model_success(candidate_model)
                    result.model = f"{candidate_provider}:{result.model}"
                    result.fallback_used = fallback_used
                    result.primary_error = primary_error
                    await safe_record_llm_metric(
                        claim_id=claim_id,
                        agent_name=agent_name,
                        result=result,
                        status="SUCCESS",
                    )
                    logger.info(
                        "LLM attempt succeeded: model=%s fallback=%s primary_error=%s",
                        result.model,
                        fallback_used,
                        primary_error,
                    )
                    return result
                except (InvalidModelOutput, SchemaValidationFailed, ProviderTimeout, ProviderUnavailable) as exc:
                    last_error = exc
                    if isinstance(exc, PlatformError):
                        primary_error = primary_error or exc.code
                    await safe_record_llm_metric(
                        claim_id=claim_id,
                        agent_name=agent_name,
                        result=LLMResult(
                            model=f"{candidate_provider}:{candidate_model}",
                            raw_text=None,
                            latency_ms=None,
                            fallback_used=fallback_used,
                            primary_error=primary_error,
                        ),
                        status="ERROR",
                        error_category=getattr(exc, "code", type(exc).__name__),
                    )
                    logger.warning(
                        "LLM attempt failed: provider=%s model=%s attempt=%s error_code=%s",
                        candidate_provider,
                        candidate_model,
                        attempt + 1,
                        getattr(exc, "code", type(exc).__name__),
                    )
                    if attempt == attempts - 1:
                        record_model_failure(candidate_model, self.settings)
                        break
        raise last_error or InvalidModelOutput("LLM generation failed")


async def safe_record_llm_metric(
    *,
    claim_id: str | None,
    agent_name: str | None,
    result: LLMResult,
    status: str,
    error_category: str | None = None,
) -> None:
    try:
        await record_llm_metric(
            claim_id=claim_id,
            agent_name=agent_name,
            model_value=result.model,
            is_fallback=result.fallback_used,
            primary_error=result.primary_error,
            latency_ms=result.latency_ms,
            status=status,
            error_category=error_category,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
    except Exception:
        logger.exception("Failed to record LLM metric")


def parse_model_json(raw_text: str, response_model: type[T]) -> T:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise InvalidModelOutput("Model did not return valid JSON") from exc
    try:
        return response_model.model_validate(payload)
    except ValidationError as exc:
        raise SchemaValidationFailed(str(exc)) from exc


def estimate_text_tokens(text: str | None) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_tokens(prompt: str, *, context: dict[str, Any] | None = None, image_bytes: bytes | None = None) -> int:
    text = prompt
    if context:
        text += json.dumps(context, default=str)
    text_tokens = estimate_text_tokens(text)
    image_tokens = 800 if image_bytes else 0
    return text_tokens + image_tokens


def extract_openai_usage(response) -> tuple[int, int, int]:
    usage = getattr(response, "usage", None)
    if not usage:
        return 0, 0, 0
    input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    total_tokens = int(getattr(usage, "total_tokens", input_tokens + output_tokens) or 0)
    return input_tokens, output_tokens, total_tokens


def extract_gemini_usage(response) -> tuple[int, int, int]:
    usage = getattr(response, "usage_metadata", None)
    if not usage:
        return 0, 0, 0
    input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
    output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
    total_tokens = int(getattr(usage, "total_token_count", input_tokens + output_tokens) or 0)
    if total_tokens == 0 and (input_tokens or output_tokens):
        total_tokens = input_tokens + output_tokens
    return input_tokens, output_tokens, total_tokens


def get_llm_platform() -> LLMPlatform:
    settings = get_platform_settings()
    if settings.use_stub_llm:
        return LLMPlatform(StubLLMClient(), settings)
    if settings.llm_provider == "gemini":
        return LLMPlatform(GeminiLLMClient(settings), settings)
    if settings.llm_provider == "openai":
        return LLMPlatform(OpenAILLMClient(settings), settings)
    raise ProviderUnavailable(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")
