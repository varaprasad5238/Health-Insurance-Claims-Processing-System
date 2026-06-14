
import json
import asyncio
import time
import uuid as _uuid

import httpx
from typing import List, Optional, Tuple, Union
import numpy as np
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)
import logging as _logging

try:
    import tiktoken  # type: ignore
except Exception:
    tiktoken = None  # Graceful fallback if not installed

import aiobreaker

from src.platform.logging import get_logger
from src.platform.llm.config import get_llm_config
from src.platform.llm.exceptions import LLMException, LLMNonRetryableError, LLMStreamCutoffError
from src.platform.llm.circuit_breaker import get_primary_model_circuit_breaker
from src.platform.llm.metrics.workflow_names import WorkflowName
from src.context_store.config.embedding import get_embedding_config
from src.context_store.infrastructure.embeddings.embedding_service import (
    EmbeddingService,
)
from src.platform.auth.service_token_manager import get_service_token
from src.platform.auth.service_token_config import get_service_token_config
from src.platform.credits.exceptions import InsufficientCreditsError
from src.platform.credits.guard import assert_can_invoke_llm
from src.platform.credits.headers import build_llm_gateway_headers, log_llm_gateway_attribution
from src.platform.credits.context import resolve_credit_user_identifier
from src.platform.error_codes import SLINAM0046


logger = get_logger(__name__)


class LLM:

    def __init__(
        self,
        auth_token: Optional[str] = None,
        account_id: Optional[str] = None,
        project_id: Optional[str] = None,
        workflow_name: Union[WorkflowName, str] = WorkflowName.UNKNOWN,
        resource_id: Optional[_uuid.UUID] = None,
        user_identifier: Optional[str] = None,
    ):
        """
        Initialize LLM client.

        Uses service token manager by default for authentication.
        If auth_token is explicitly provided, it will be used instead.

        Args:
            auth_token: Optional authentication token. If provided, uses this token.
                       If not provided, uses service token manager automatically.
            account_id: Optional account ID for x-client header (required for enterprise APIs)
            project_id: Optional project ID for x-project-id header (required for enterprise APIs)
            workflow_name: Workflow name for metrics recording (e.g. WorkflowName.EPIC_GENERATION)
            resource_id: Resource UUID for metrics recording
        """
        # Get configuration from environment variables
        self.llm_config = get_llm_config()
        self.embedding_config = get_embedding_config()

        # LLM endpoint - append /chat/completions to the base LLM endpoint
        endpoint = self.llm_config.llm_endpoint.rstrip("/")
        self.base_url = f"{endpoint}/chat/completions"

        self.auth_token = auth_token
        self.account_id = account_id
        self.project_id = project_id
        self.workflow_name = workflow_name
        self.resource_id = resource_id
        self._user_identifier = (user_identifier or "").strip() or None

        # Embedding endpoint - append /embeddings to the base vectors endpoint
        self.embedding_url = (
            f"{self.embedding_config.embedding_url.rstrip('/')}/embeddings"
        )
        self.embedding_model = self.embedding_config.embedding_model
        self.default_model = self.llm_config.llm_default_model
        self.encoding_model = self.llm_config.encoding_model

        logger.info(
            "Initializing LLM client",
            base_url=self.base_url,
            embedding_url=self.embedding_url,
            embedding_model=self.embedding_model,
            default_model=self.default_model,
            encoding_model=self.encoding_model,
        )

        # Initialize OpenAI client for embeddings (will be updated with token when needed)
        self.openai_client = None

    async def _get_auth_token(self) -> Optional[str]:
        """
        Retrieve authentication token for API calls.

        Behavior depends on AUTH_USE_SERVICE_TOKEN configuration:
        - If True: Service token takes precedence over explicit auth_token (current behavior)
        - If False: Use auth_token directly, skip service token lookup

        Returns:
            Authentication token string or None if unable to obtain.
        """
        service_token_config = get_service_token_config()

        # If service token usage is disabled, use auth_token directly
        if not service_token_config.auth_use_service_token:
            if not self.auth_token:
                logger.error(
                    "No authentication token available (AUTH_USE_SERVICE_TOKEN is False)"
                )
                raise ValueError(
                    "auth_token is required when AUTH_USE_SERVICE_TOKEN is False"
                )
            logger.debug("Using auth_token from API (AUTH_USE_SERVICE_TOKEN is False)")
            return self.auth_token

        # Service token is enabled - try service token first, then fallback to auth_token
        try:
            service_token = await get_service_token()
            if service_token:
                return service_token
        except Exception as e:
            logger.error("Failed to obtain service token", error=str(e))

        # Fallback to explicit auth_token if service token is not available
        if not self.auth_token:
            logger.error("No authentication token available")
            raise ValueError(
                "No auth_token or service token provided during LLM initialization"
            )

        logger.warning("Using fallback explicit auth_token")
        return self.auth_token

    def _get_encoding(self, model_name: str):
        if tiktoken is None:
            logger.debug("tiktoken not available, encoding estimation disabled")
            return None
        # Best-effort choose encoding by model; fallback to ENCODING_MODEL
        try:
            encoding = tiktoken.encoding_for_model(model_name)
            logger.debug("Using model-specific encoding", model=model_name)
            return encoding
        except Exception as e:
            logger.debug(
                "Failed to get model-specific encoding, trying encoding model",
                model=model_name,
                encoding_model=self.encoding_model,
                error=str(e),
            )
            try:
                # Try using the encoding model from environment variable
                encoding = tiktoken.encoding_for_model(self.encoding_model)
                logger.debug("Using encoding model", encoding_model=self.encoding_model)
                return encoding
            except Exception as e2:
                logger.warning(
                    "Failed to get encoding, token estimation unavailable",
                    model=model_name,
                    encoding_model=self.encoding_model,
                    error=str(e2),
                )
                return None

    def _estimate_tokens_for_text(self, text: str, model_name: str) -> int:
        enc = self._get_encoding(model_name)
        if enc is None:
            # Fallback heuristic: ~4 chars per token
            estimated = max(1, len(text) // 4)
            logger.debug(
                "Estimated tokens using fallback heuristic",
                model=model_name,
                text_length=len(text),
                estimated_tokens=estimated,
            )
            return estimated
        try:
            token_count = len(enc.encode(text or ""))
            logger.debug(
                "Estimated tokens for text",
                model=model_name,
                text_length=len(text),
                token_count=token_count,
            )
            return token_count
        except Exception as e:
            estimated = max(1, len(text) // 4)
            logger.warning(
                "Token estimation failed, using fallback heuristic",
                model=model_name,
                text_length=len(text),
                error=str(e),
                estimated_tokens=estimated,
            )
            return estimated

    def _estimate_tokens_for_messages(self, messages, model_name: str) -> int:
        combined = []
        for m in messages or []:
            role = m.get("role", "")
            content = m.get("content", "")
            combined.append(f"{role}: {content}")
        return self._estimate_tokens_for_text("\n".join(combined), model_name)

    # Public helpers for external modules
    def estimate_tokens_text(self, model_name: str, text: str) -> int:
        return self._estimate_tokens_for_text(text, model_name)

    def estimate_tokens_messages(self, model_name: str, messages) -> int:
        return self._estimate_tokens_for_messages(messages, model_name)

    async def _execute_with_retry(
        self, messages: List[dict], model_name: str
    ) -> Tuple[str, Optional[dict]]:
        """
        Execute one LLM query with tenacity retry for transient failures.

        Returns:
            ``(content, stream_usage_dict)`` on success.

        Raises:
            LLMNonRetryableError: Non-retryable HTTP 4xx (excluded from the
                circuit breaker's failure counter).
            LLMStreamCutoffError: Output hit the token limit (excluded from the
                circuit breaker's failure counter).
            LLMException: After exhausting all retries for transient errors;
                counted as a circuit breaker failure.
        """
        timeout = float(self.llm_config.llm_timeout)
        max_retries = self.llm_config.max_retries
        base_delay = self.llm_config.llm_retry_base_delay

        class _RetryableSignal(Exception):
            """Internal sentinel; converted to LLMException after all retries."""

            def __init__(self, msg: str):
                super().__init__(msg)

        @retry(
            retry=retry_if_exception_type(_RetryableSignal),
            stop=stop_after_attempt(max_retries + 1),
            wait=wait_exponential(
                multiplier=base_delay, min=base_delay, max=base_delay * (2**max_retries)
            ),
            before_sleep=before_sleep_log(
                _logging.getLogger(__name__), _logging.WARNING
            ),
            reraise=True,
        )
        async def _attempt() -> Tuple[str, Optional[dict]]:
            try:
                try:
                    await assert_can_invoke_llm(user_identifier=self._user_identifier)
                except InsufficientCreditsError:
                    raise LLMNonRetryableError(SLINAM0046.code)

                # Fetch a fresh token on every attempt so an expired token that
                # caused a 401 is replaced before the next request.
                auth_token = await self._get_auth_token()
                if not auth_token:
                    raise _RetryableSignal("LLM_ERROR: Unable to obtain authentication token")

                service_token_config = get_service_token_config()
                if service_token_config.auth_use_service_token:
                    user_id = resolve_credit_user_identifier(
                        explicit=self._user_identifier,
                    ) or None
                    headers = await build_llm_gateway_headers(
                        account_id=self.account_id,
                        project_id=self.project_id,
                        user_identifier=user_id,
                        fallback_auth_token=self.auth_token,
                    )
                    headers["Content-Type"] = "application/json"
                    log_llm_gateway_attribution(
                        transport="httpx",
                        headers=headers,
                        model=model_name,
                        use_service_token=True,
                    )
                else:
                    headers = {
                        "Authorization": f"Bearer {auth_token}",
                        "Content-Type": "application/json",
                    }
                    if self.account_id:
                        headers["x-client"] = self.account_id
                    if self.project_id:
                        headers["x-project-id"] = self.project_id
                    log_llm_gateway_attribution(
                        transport="httpx",
                        headers=headers,
                        model=model_name,
                        use_service_token=False,
                    )

                async with httpx.AsyncClient(verify=False) as client:
                    stream_body = {
                        "messages": messages,
                        "model": model_name,
                        "stream": True,
                        "stream_options": {"include_usage": True},
                    }
                    max_output_tokens = getattr(
                        self.llm_config, "llm_max_output_tokens", None
                    )
                    if isinstance(max_output_tokens, int) and max_output_tokens > 0:
                        stream_body["max_completion_tokens"] = max_output_tokens
                    async with client.stream(
                        "POST",
                        self.base_url,
                        json=stream_body,
                        headers=headers,
                        timeout=timeout,
                    ) as response:
                        if response.status_code == 200:
                            full_content = ""
                            truncated = False
                            stream_usage: Optional[dict] = None
                            async for raw_line in response.aiter_lines():
                                line = raw_line.strip()
                                if not line.startswith("data:"):
                                    continue
                                data = line[5:].strip()
                                if data == "[DONE]":
                                    break
                                try:
                                    obj = json.loads(data)
                                except json.JSONDecodeError:
                                    continue
                                # Capture usage from the dedicated usage chunk
                                if obj.get("usage"):
                                    stream_usage = obj["usage"]
                                choices = obj.get("choices") or []
                                if not choices:
                                    continue
                                c0 = choices[0]
                                delta = c0.get("delta") or {}
                                piece = delta.get("content")
                                if piece:
                                    full_content += piece
                                if c0.get("finish_reason") == "length":
                                    truncated = True
                            if truncated:
                                raise LLMStreamCutoffError(
                                    model=model_name,
                                    partial_content=full_content,
                                )
                            if not full_content.strip():
                                logger.error(
                                    "LLM streaming query returned no usable content",
                                    model=model_name,
                                )
                                raise _RetryableSignal(
                                    "LLM_ERROR: Unexpected response format: empty or unparseable stream"
                                )
                            return full_content, stream_usage
                        err_text = (await response.aread()).decode(
                            "utf-8", errors="replace"
                        )
                        if response.status_code == 401:
                            raise _RetryableSignal(
                                f"LLM_ERROR: HTTP 401: {err_text[:2000]}"
                            )
                        if response.status_code == 429:
                            raise _RetryableSignal(
                                f"LLM_ERROR: HTTP 429 (rate limited): {err_text[:2000]}"
                            )
                        if 400 <= response.status_code < 500:
                            err = (
                                f"LLM_ERROR: HTTP {response.status_code}: "
                                f"{err_text[:2000]}"
                            )
                            logger.error(
                                "LLM streaming query failed with non-retryable client error",
                                model=model_name,
                                status_code=response.status_code,
                            )
                            raise LLMNonRetryableError(err)
                        logger.warning(
                            "LLM streaming query received unhandled HTTP status",
                            model=model_name,
                            status_code=response.status_code,
                            response_preview=err_text[:300],
                        )
                        raise _RetryableSignal(
                            f"LLM_ERROR: HTTP {response.status_code}: {err_text[:2000]}"
                        )
            except (_RetryableSignal, LLMNonRetryableError, LLMStreamCutoffError):
                raise
            except httpx.TimeoutException as e:
                raise _RetryableSignal(f"LLM_ERROR: Request timeout: {e}")
            except httpx.RequestError as e:
                raise _RetryableSignal(f"LLM_ERROR: Request error: {e}")
            except Exception as e:
                logger.error(
                    "LLM query failed with unexpected error",
                    model=model_name,
                    error=str(e),
                    error_type=type(e).__name__,
                    exc_info=True,
                )
                raise _RetryableSignal(f"LLM_ERROR: Unexpected error: {e}")

        try:
            return await _attempt()
        except _RetryableSignal as e:
            # Convert to LLMException so the circuit breaker can count it.
            raise LLMException(str(e)) from e

    async def query(self, prompt, model_name, context=None, user_query=None):
        """
        Query the LLM API with automatic service token management and circuit
        breaker / fallback support.

        Normal flow:
            1. The primary ``model_name`` is attempted through the circuit
               breaker (tenacity retries apply internally).
            2. If the circuit is OPEN or the primary model exhausts all retries,
               the call is transparently retried on the configured
               ``llm_fallback_model`` without any user intervention.
            3. Non-retryable 4xx errors and token-cutoff events are returned
               immediately as error strings without affecting the circuit.

        Args:
            prompt: The prompt to send to the LLM.
            model_name: The primary model name to use.
            context: Optional context to include.
            user_query: Optional user query.

        Returns:
            Response text, or an ``LLM_ERROR: …`` string on failure.
        """
        messages = [
            {"role": "user", "content": prompt},
        ]
        if context:
            messages.append({"role": "user", "content": context})

        _start_time = time.time()
        circuit_breaker = get_primary_model_circuit_breaker(model_name)
        fallback_model = self.llm_config.llm_fallback_model
        actual_model = model_name
        full_content: str
        stream_usage: Optional[dict] = None

        try:
            full_content, stream_usage = await circuit_breaker.call_async(
                self._execute_with_retry, messages, model_name
            )
        except aiobreaker.CircuitBreakerError:
            logger.warning(
                "LLM circuit breaker is OPEN for primary model; routing to fallback",
                primary_model=model_name,
                fallback_model=fallback_model,
            )
            if not fallback_model or fallback_model == model_name:
                return (
                    "LLM_ERROR: Primary model circuit open and no fallback model configured"
                )
            actual_model = fallback_model
            try:
                full_content, stream_usage = await self._execute_with_retry(
                    messages, fallback_model
                )
            except LLMNonRetryableError as fb_err:
                return fb_err.error_str
            except LLMStreamCutoffError as fb_err:
                return f"LLM_ERROR: {fb_err}"
            except LLMException as fb_err:
                return f"LLM_ERROR: Fallback model also failed: {fb_err}"
        except LLMNonRetryableError as e:
            # Non-retryable 4xx — return immediately, no circuit impact.
            return e.error_str
        except LLMStreamCutoffError as e:
            return f"LLM_ERROR: {e}"
        except LLMException as e:
            # Primary model exhausted all retries; circuit recorded a failure.
            logger.warning(
                "Primary model failed after all retries; trying fallback",
                primary_model=model_name,
                fallback_model=fallback_model,
                error=str(e),
            )
            if not fallback_model or fallback_model == model_name:
                return f"LLM_ERROR: {e}"
            actual_model = fallback_model
            try:
                full_content, stream_usage = await self._execute_with_retry(
                    messages, fallback_model
                )
            except LLMNonRetryableError as fb_err:
                return fb_err.error_str
            except LLMStreamCutoffError as fb_err:
                return f"LLM_ERROR: {fb_err}"
            except LLMException as fb_err:
                return f"LLM_ERROR: Both primary and fallback models failed: {fb_err}"

        # Fire-and-forget metrics recording using real token counts when available
        try:
            from src.platform.llm.metrics import get_metrics_service

            metrics_svc = get_metrics_service()
            if metrics_svc:
                if stream_usage:
                    input_tokens = stream_usage.get("prompt_tokens", 0)
                    output_tokens = stream_usage.get("completion_tokens", 0)
                else:
                    # Fallback: estimate via tiktoken if API didn't return usage
                    input_tokens = self._estimate_tokens_for_messages(
                        messages, actual_model
                    )
                    output_tokens = self._estimate_tokens_for_text(
                        full_content, actual_model
                    )
                await metrics_svc.record(
                    workflow_name=self.workflow_name,
                    resource_id=self.resource_id,
                    model_used=actual_model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    response_time_ms=int((time.time() - _start_time) * 1000),
                )
        except Exception:
            pass  # Never block the LLM path for metrics

        return full_content

    def call_llm(self, system_prompt):
        # Use default model from LLM config
        model_name = self.default_model
        # logger.debug("Calling LLM", model=model_name, prompt_length=len(system_prompt))
        # Call async query method synchronously using asyncio
        try:
            # Try to get the current event loop
            # If we're here, there's a running loop - run in a thread to avoid blocking
            import concurrent.futures

            def run_in_thread():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(
                        self.query(prompt=system_prompt, model_name=model_name)
                    )
                finally:
                    new_loop.close()

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_thread)
                response = future.result()
        except RuntimeError:
            # No event loop is running, create a new one
            response = asyncio.run(
                self.query(prompt=system_prompt, model_name=model_name)
            )
        return response

    async def _query_embeddings(self, texts: List[str]) -> Tuple[np.ndarray, List[int]]:
        """
        Async method to query embeddings API for a list of texts.

        Filters empty/whitespace-only texts before calling EmbeddingService, so
        callers do not need to pre-filter. Returns (embeddings, valid_indices) where
        valid_indices maps each returned embedding row back to its original position
        in `texts`.

        Delegates all batching, token-safe chunking, concurrency, and per-batch retry
        to EmbeddingService.

        Args:
            texts: List of texts to generate embeddings for

        Returns:
            Tuple of (ndarray shape [n_valid, dim], list of valid original indices)

        Raises:
            ValueError: If all texts are empty or the embedding API fails
            httpx.HTTPStatusError: On non-200 HTTP response after retries
            httpx.TimeoutException: On request timeout
        """
        non_empty = [(i, t) for i, t in enumerate(texts) if t.strip()]
        if len(non_empty) < len(texts):
            logger.warning(
                "Skipping %d empty/whitespace texts before embedding",
                len(texts) - len(non_empty),
            )
        if not non_empty:
            raise ValueError(
                "All input texts are empty — no embeddings can be generated"
            )
        valid_indices, valid_texts = zip(*non_empty)
        valid_indices = list(valid_indices)
        valid_texts = list(valid_texts)

        service = EmbeddingService(
            account_id=self.account_id, project_id=self.project_id
        )
        embeddings, embedded_input_indices = (
            await service._generate_embeddings_batch_with_indices(valid_texts)
        )
        # embedded_input_indices are positions into valid_texts; map back to original texts positions.
        final_valid_indices = [valid_indices[i] for i in embedded_input_indices]
        return np.array(embeddings), final_valid_indices

    def generate_embeddings(self, texts: List[str]) -> Optional[np.ndarray]:
        """
        Generate embeddings for a list of texts.
        Synchronous wrapper around EmbeddingService.

        Args:
            texts: List of texts to generate embeddings for

        Returns:
            list of embeddings, or None if failed
        """
        try:
            try:
                import concurrent.futures

                def run_in_thread():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(
                            self._query_embeddings(texts)
                        )
                    finally:
                        new_loop.close()

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_in_thread)
                    arr, _ = future.result()
                    return arr
            except RuntimeError:
                arr, _ = asyncio.run(self._query_embeddings(texts))
                return arr
        except Exception as e:
            logger.error("Failed to generate embeddings", error=str(e), exc_info=True)
            return None

    def generate_single_embedding(self, text: str) -> Optional[np.ndarray]:
        """Generate embedding for a single text."""
        # logger.debug("Generating single embedding", text_length=len(text))
        embeddings = self.generate_embeddings([text])
        if embeddings is not None:
            # logger.debug("Single embedding generated successfully")
            return embeddings[0]
        else:
            logger.warning("Failed to generate single embedding")
            return None

    async def get_llm_models(self) -> List[str]:
        """
        Get list of available LLM models.

        Returns:
            List of model names
        """
        # For now, return a static list based on configuration
        # In a production system, this might query the LLM provider's API
        try:
            # Get current auth token (fresh service token if needed)
            auth_token = await self._get_auth_token()

            if not auth_token:
                logger.error(
                    "Unable to obtain authentication token to fetch LLM models"
                )
                return []

            headers = {
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json",
            }

            # Add mandatory enterprise headers
            if self.account_id:
                headers["x-client"] = self.account_id
            if self.project_id:
                headers["x-project-id"] = self.project_id

            # Example: Call a hypothetical /models endpoint
            models_url = f"{self.llm_config.llm_endpoint.rstrip('/')}/models"
            timeout = float(self.llm_config.llm_timeout)
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    models_url, headers=headers, timeout=timeout
                )
                if response.status_code == 200:
                    result = response.json()
                    model_names = [model["id"] for model in result.get("data", [])]
                    logger.info(
                        "Fetched LLM models successfully",
                        model_count=len(model_names),
                    )
                    return model_names
                else:
                    logger.error(
                        "Failed to fetch LLM models",
                        status_code=response.status_code,
                        response_text=response.text[:500],
                    )
                    return []
        except Exception as e:
            logger.error(
                "Failed to obtain authentication token for LLM models",
                error=str(e),
            )
            return []
