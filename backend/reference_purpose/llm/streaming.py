import asyncio
import logging as _logging
import os
from typing import TYPE_CHECKING
import secrets
import time
import uuid
from functools import lru_cache
from typing import Optional, Any

import aiobreaker

from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

import tiktoken
from openai import AsyncOpenAI, AsyncStream
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
    ChatCompletionChunk,
    ChatCompletion,
)

from src.platform.auth import (
    ValidatedAuthDTO,
    get_service_token_config,
    get_service_token,
)
from src.platform.llm import get_llm_config
from src.platform.llm.circuit_breaker import get_primary_model_circuit_breaker
from src.platform.llm.dto import LLMChatRequestDTO, LLMChatResponseDTO
from src.platform.error_codes import (
    SLINAM0015,
    SLINAM0018,
    SLINAM0034,
    SLINAM0035,
)
from src.platform.credits.exceptions import InsufficientCreditsError
from src.platform.credits.guard import assert_can_invoke_llm
from src.platform.credits.headers import build_llm_gateway_headers, log_llm_gateway_attribution
from src.platform.credits.context import (
    apply_credit_user_from_auth,
    resolve_credit_user_identifier,
)
from src.platform.llm.exceptions import (
    LLMException,
    LLMAuthException,
    LLMStreamCutoffError,
)

from src.platform.llm.metrics.workflow_names import WorkflowName
from src.platform.logging import get_logger, get_trace_id

logger = get_logger(__name__)

# TYPE_CHECKING import to avoid circular dependency at runtime
if TYPE_CHECKING:
    from src.platform.llm.metrics.batch import LLMMetricsBatch


class StreamingLLM:
    def __init__(
        self,
        account_id: Optional[str] = None,
        project_id: Optional[str] = None,
        workflow_name: WorkflowName = WorkflowName.UNKNOWN,
        resource_id: Optional[uuid.UUID] = None,
        metrics_batch: Optional["LLMMetricsBatch"] = None,
        phase: Optional[str] = None,
        user_identifier: Optional[str] = None,
    ):
        self.llm_config = get_llm_config()
        self._user_identifier = (user_identifier or "").strip() or None
        # LLM endpoint - append /chat/completions to the base LLM endpoint
        endpoint = self.llm_config.llm_endpoint.rstrip("/")
        self.base_url = endpoint
        self.default_model = self.llm_config.llm_default_model
        service_token_config = get_service_token_config()
        self.use_service_token = service_token_config.auth_use_service_token
        self.account_id = account_id
        self.project_id = project_id
        self.workflow_name = workflow_name
        self.resource_id = resource_id
        self._metrics_batch = metrics_batch
        self.phase = phase

    async def _get_auth_token(self, auth_token: Optional[str] = None) -> Optional[str]:
        """
        Retrieve authentication token for API calls.

        Behavior depends on AUTH_USE_SERVICE_TOKEN configuration:
        - If True: Service token takes precedence over explicit auth_token (current behavior)
        - If False: Use auth_token directly, skip service token lookup

        Returns:
            Authentication token string or None if unable to obtain.
        """

        # If service token usage is disabled, use auth_token directly
        if not self.use_service_token:
            if not auth_token:
                logger.error(
                    "No authentication token available (AUTH_USE_SERVICE_TOKEN is False)"
                )
                raise ValueError(
                    "auth_token is required when AUTH_USE_SERVICE_TOKEN is False"
                )
            logger.debug("Using auth_token from API (AUTH_USE_SERVICE_TOKEN is False)")
            return auth_token

        # Service token is enabled - try service token first, then fallback to auth_token
        try:
            service_token = await get_service_token()
            if service_token:
                return service_token
        except Exception as e:
            logger.error("Failed to obtain service token", exc_info=e)

        # Fallback to explicit auth_token if service token is not available
        if not auth_token:
            logger.error("No authentication token available")
            raise ValueError(
                "No auth_token or service token provided during LLM initialization"
            )

        logger.warning("Using fallback explicit auth_token")
        return auth_token

    @staticmethod
    def _generate_traceparent() -> str:
        """
        Generate a W3C Trace Context traceparent header value.

        Format: version-trace-id-parent-id-trace-flags
        - version: 00 (2 hex characters)
        - trace-id: 32 hex characters (128-bit)
        - parent-id: 16 hex characters (64-bit)
        - trace-flags: 01 (sampled) or 00 (not sampled)

        Returns:
            A traceparent string following W3C Trace Context specification.
        """
        # Version: 00
        version = "00"
        # Trace ID: 32 hex characters (16 bytes = 128 bits)
        trace_id = secrets.token_hex(16)
        # Parent ID: 16 hex characters (8 bytes = 64 bits)
        parent_id = secrets.token_hex(8)
        # Trace flags: 01 = sampled, 00 = not sampled
        trace_flags = "01"

        traceparent = f"{version}-{trace_id}-{parent_id}-{trace_flags}"
        return traceparent

    @staticmethod
    def _get_encoding_for_model(model_name: str) -> tiktoken.Encoding:
        """
        Get the appropriate tiktoken encoding for a given model.
        Most OpenAI models use cl100k_base encoding.
        """
        try:
            # Try to get encoding for the specific model
            encoding = tiktoken.encoding_for_model(model_name)
            return encoding
        except KeyError:
            # Fallback to cl100k_base for most OpenAI models
            logger.warning(f"Unknown model {model_name}, using cl100k_base encoding")
            return tiktoken.get_encoding("cl100k_base")

    @staticmethod
    def _estimate_tokens(
        messages: list[ChatCompletionMessageParam], model_name: str
    ) -> int:
        """
        Estimate the number of tokens in the messages using tiktoken.

        Returns:
            Estimated token count including message formatting overhead.
        """
        encoding = StreamingLLM._get_encoding_for_model(model_name)

        # Base overhead: 4 tokens per message for formatting
        tokens_per_message = 4

        total_tokens = 0
        for message in messages:
            # Count tokens for role
            total_tokens += tokens_per_message

            # Count tokens for content
            if hasattr(message, "content") and message.content:
                content = (
                    message.content
                    if isinstance(message.content, str)
                    else str(message.content)
                )
                total_tokens += len(encoding.encode(content))

        # Add 2 tokens for the assistant's reply (formatting overhead)
        total_tokens += 2

        return total_tokens

    @staticmethod
    async def __handle_streaming_request(
        messages: list[ChatCompletionMessageParam],
        model_name: str,
        params: dict[str, Any],
        client: AsyncOpenAI,
    ) -> LLMChatResponseDTO:
        try:
            stream: AsyncStream[ChatCompletionChunk] | ChatCompletion = (
                await client.chat.completions.create(
                    model=model_name, messages=messages, stream=True, **params
                )
            )
            # Accumulate the streamed content
            full_content = ""
            usage_info = {}
            response_id = ""

            if not isinstance(stream, AsyncStream):
                logger.error(
                    "llm_streaming_invalid_response_type",
                    trace_id=get_trace_id(),
                    internal_reason="expected AsyncStream from chat.completions.create",
                )
                # Upstream response isn't in the expected stream shape.
                raise LLMException(SLINAM0018.code)
            last_chunk = None
            async for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    choice = chunk.choices[0]
                    if choice.delta.content:
                        full_content += choice.delta.content
                    # Non-retryable because it indicates the LLM stopped generating due to max_tokens limit, not a transient error
                    if getattr(choice, "finish_reason", None) == "length":
                        raise LLMStreamCutoffError(
                            model=model_name, partial_content=full_content
                        )

                # Store response ID if available
                if not response_id and hasattr(chunk, "id"):
                    response_id = chunk.id

                # Collect usage information if available
                if hasattr(chunk, "usage") and chunk.usage:
                    usage_info = chunk.usage.model_dump()

                last_chunk = chunk

            # After the loop, check last_chunk for usage info if not already set
            if last_chunk and hasattr(last_chunk, "usage") and last_chunk.usage:
                usage_info = last_chunk.usage.model_dump()
            
            # Return the accumulated responses
            return LLMChatResponseDTO(
                text=full_content,
                raw_response={"id": response_id, "model": model_name},
                usage=usage_info,
                metadata={
                    "model": model_name,
                    "id": response_id,
                    "provider": "enterprise",
                    "streaming": True,
                },
            )

        except LLMStreamCutoffError:
            raise  # let it propagate; callers decide whether to retry
        except Exception as ex:
            # Log full provider / SDK detail server-side only; never forward str(ex) to callers.
            logger.error(
                "llm_streaming_request_failed",
                trace_id=get_trace_id(),
                internal_reason=str(ex),
                exception_type=type(ex).__name__,
                status_code=getattr(ex, "status_code", None),
                exc_info=True,
            )
            status_code = getattr(ex, "status_code", None)
            if status_code in (401, 403):
                # Provider-side auth failure for the LLM request.
                # Let the central resolver pick the correct SLINAM for LLMAuthException.
                raise LLMAuthException()
            if status_code == 402:
                raise InsufficientCreditsError()
            if status_code == 429:
                # Provider-side rate limiting.
                raise LLMException(SLINAM0034.code)
            if status_code == 404:
                # Model not found, wrong endpoint, etc. — still a provider-side failure.
                # Treat as invalid/unsupported runtime configuration (e.g., wrong model name).
                raise LLMException(SLINAM0035.code)
            # Timeouts from httpx / OpenAI client often have no status_code
            if type(ex).__name__ in (
                "APITimeoutError",
                "ReadTimeout",
                "ConnectTimeout",
                "TimeoutError",
            ) or "timeout" in type(ex).__name__.lower():
                # LLM provider request timed out during generation.
                raise LLMException(SLINAM0015.code)
            # Unknown upstream error: let resolver map the generic LLM provider error.
            raise LLMException()

    async def query(
        self, request: LLMChatRequestDTO, auth: Optional[ValidatedAuthDTO] = None
    ) -> LLMChatResponseDTO:
        apply_credit_user_from_auth(auth)
        if self._user_identifier:
            from src.platform.credits.context import set_credit_user_identifier

            set_credit_user_identifier(self._user_identifier)

        # Prepare messages in enterprise format
        messages: list[ChatCompletionMessageParam] = [
            ChatCompletionSystemMessageParam(
                role="system",
                content=request.system_prompt or "You are a helpful assistant.",
            ),
            ChatCompletionUserMessageParam(role="user", content=request.message),
        ]
        if request.additional_user_messages:
            messages.extend(
                [
                    ChatCompletionUserMessageParam(role="user", content=message)
                    for message in request.additional_user_messages
                ]
            )
        llm_model = request.options.model or self.default_model

        # Estimate and log tokens before making the LLM call
        estimated_tokens = self._estimate_tokens(messages, llm_model)

        # Generate traceparent for distributed tracing
        traceparent = self._generate_traceparent()

        # Prepare parameters
        params = {}
        if request.options and request.options.parameters:
            params_obj = request.options.parameters
            if params_obj.temperature is not None:
                params["temperature"] = params_obj.temperature
            if params_obj.max_tokens is not None:
                params["max_tokens"] = params_obj.max_tokens
            if params_obj.top_p is not None:
                params["top_p"] = params_obj.top_p

        # Update client with traceparent header
        default_headers = {"traceparent": traceparent}
        
        # Add mandatory enterprise headers
        if self.account_id:
            default_headers["x-client"] = self.account_id
        if self.project_id:
            default_headers["x-project-id"] = self.project_id
        
        logger.info(
            f"Sending LLM chat completions request to {self.base_url}",
            model=llm_model,
            estimated_tokens=estimated_tokens,
            traceparent=traceparent,
        )

        max_retries = self.llm_config.max_retries
        base_delay = self.llm_config.llm_retry_base_delay

        @retry(
            retry=retry_if_exception(
                lambda e: isinstance(e, LLMException)
                and not isinstance(e, LLMStreamCutoffError)
                and not isinstance(e, InsufficientCreditsError)
            ),
            stop=stop_after_attempt(max_retries + 1),
            wait=wait_exponential(multiplier=base_delay, min=base_delay, max=base_delay * (2 ** max_retries)),
            before_sleep=before_sleep_log(_logging.getLogger(__name__), _logging.WARNING),
            reraise=True,
        )
        async def _attempt() -> LLMChatResponseDTO:
            await assert_can_invoke_llm(
                user_identifier=self._user_identifier,
                auth=auth,
            )

            # Fetch a fresh token on every attempt so a 401 from an expired
            # token is resolved before the next request.
            auth_token = await self._get_auth_token(auth.user.at if auth else None)
            if self.use_service_token:
                user_id = resolve_credit_user_identifier(
                    explicit=self._user_identifier,
                    auth=auth,
                ) or None
                attempt_headers = await build_llm_gateway_headers(
                    account_id=self.account_id,
                    project_id=self.project_id,
                    user_identifier=user_id,
                    traceparent=traceparent,
                    fallback_auth_token=auth.user.at if auth else None,
                )
                log_llm_gateway_attribution(
                    transport="streaming",
                    headers=attempt_headers,
                    model=llm_model,
                    use_service_token=True,
                )
            else:
                attempt_headers = dict(default_headers)
                log_llm_gateway_attribution(
                    transport="streaming",
                    headers=attempt_headers,
                    model=llm_model,
                    use_service_token=False,
                )
            client = AsyncOpenAI(
                base_url=self.base_url,
                timeout=self.llm_config.llm_timeout,
                api_key=auth_token,
                default_headers=attempt_headers,
            )
            start_time = time.time()
            response = await self.__handle_streaming_request(
                messages, llm_model, params, client
            )
            duration = time.time() - start_time
            logger.info(
                "LLM chat completions request completed",
                model=llm_model,
                duration_seconds=f"{duration:.2f}",
                traceparent=traceparent,
            )

            from src.platform.llm.metrics import get_metrics_service
            metrics_svc = self._metrics_batch or get_metrics_service()
            if metrics_svc:
                other_details: dict = {"traceparent": traceparent}
                if self.phase:
                    other_details["phase"] = self.phase
                    logger.info(
                        "Recording metrics with phase",
                        phase=self.phase,
                        workflow_name=str(self.workflow_name),
                        model=llm_model,
                    )
                await metrics_svc.record(
                    workflow_name=self.workflow_name,
                    resource_id=self.resource_id,
                    model_used=llm_model,
                    input_tokens=response.usage.get("prompt_tokens", 0),
                    output_tokens=response.usage.get("completion_tokens", 0),
                    response_time_ms=int(duration * 1000),
                    other_details=other_details,
                )

            return response

        # ------------------------------------------------------------------
        # Circuit breaker + fallback
        # ------------------------------------------------------------------
        # Tenacity only retries LLMException; InsufficientCreditsError and
        # LLMStreamCutoffError propagate immediately (not retried).
        # When the circuit is OPEN or all primary retries are exhausted, the
        # call is transparently re-issued against the fallback model.
        # ------------------------------------------------------------------
        circuit_breaker = get_primary_model_circuit_breaker(llm_model)
        fallback_model = self.llm_config.llm_fallback_model
        original_model = llm_model

        try:
            return await circuit_breaker.call_async(_attempt)
        except aiobreaker.CircuitBreakerError:
            logger.warning(
                "LLM circuit breaker is OPEN for primary model; routing to fallback",
                primary_model=original_model,
                fallback_model=fallback_model,
            )
            if not fallback_model or fallback_model == original_model:
                raise LLMException(
                    "Primary model circuit open and no fallback model configured"
                )
            llm_model = fallback_model  # closure updated; _attempt() picks it up
            try:
                return await _attempt()
            except LLMStreamCutoffError:
                raise
            except LLMException:
                logger.error(
                    "Fallback model also failed after circuit breaker opened",
                    fallback_model=fallback_model,
                )
                raise
        except LLMStreamCutoffError:
            raise
        except LLMException:
            logger.warning(
                "Primary model failed after all retries; trying fallback",
                primary_model=original_model,
                fallback_model=fallback_model,
                max_retries=max_retries,
            )
            if not fallback_model or fallback_model == original_model:
                logger.error(
                    "LLM streaming request failed and no fallback model configured",
                    model=original_model,
                    max_retries=max_retries,
                )
                raise
            llm_model = fallback_model  # closure updated; _attempt() picks it up
            try:
                return await _attempt()
            except LLMStreamCutoffError:
                raise
            except LLMException:
                logger.error(
                    "Both primary and fallback models failed",
                    primary_model=original_model,
                    fallback_model=fallback_model,
                )
                raise


@lru_cache
def get_streaming_llm_client() -> StreamingLLM:
    return StreamingLLM()
