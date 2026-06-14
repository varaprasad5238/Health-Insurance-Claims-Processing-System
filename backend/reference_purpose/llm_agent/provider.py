import json
from typing import List, Optional, Union, Dict, Type, Any, AsyncIterator
from collections.abc import Mapping

from agno.exceptions import ModelProviderError
from agno.models.openai import OpenAILike
from agno.models.message import Message
from agno.models.response import ModelResponse
from agno.run.agent import RunOutput
from pydantic import BaseModel

from src.platform.credits.context import resolve_credit_user_identifier
from src.platform.credits.exceptions import InsufficientCreditsError
from src.platform.credits.guard import assert_can_invoke_llm
from src.platform.credits.headers import (
    ATTR_X_CLIENT,
    ATTR_X_PROJECT_ID,
    ATTR_X_USER_IDENTIFIER,
    log_llm_gateway_attribution,
)


class SlingshotGateway(OpenAILike):
    """
    Overrides the OpenAILike class to clean empty messages and add enterprise headers.
    This is required because Anthropic models don't support empty messages.
    Also adds x-client and x-project-id headers for enterprise API invocations.
    """

    def __init__(
        self,
        *args,
        account_id: Optional[str] = None,
        project_id: Optional[str] = None,
        user_identifier: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize SlingshotGateway with optional enterprise headers.
        
        Args:
            account_id: Optional account ID for x-client header
            project_id: Optional project ID for x-project-id header
            user_identifier: Triggering user email/id for x-user-identifier (service token)
            *args, **kwargs: Arguments passed to OpenAILike parent class
        """
        super().__init__(*args, **kwargs)
        self.account_id = account_id
        self.project_id = project_id
        self._user_identifier = (user_identifier or "").strip() or None

        if not hasattr(self, "default_headers") or self.default_headers is None:
            self.default_headers = {}

        if self.account_id:
            self.default_headers[ATTR_X_CLIENT] = self.account_id
        if self.project_id:
            self.default_headers[ATTR_X_PROJECT_ID] = self.project_id

    def _enterprise_headers_for_request(self) -> dict[str, str]:
        """Build per-request enterprise headers (used via Agno ``extra_headers``)."""
        headers = dict(self.default_headers or {})
        user_id = resolve_credit_user_identifier(explicit=self._user_identifier)
        if user_id:
            headers[ATTR_X_USER_IDENTIFIER] = user_id
        else:
            headers.pop(ATTR_X_USER_IDENTIFIER, None)
        return headers

    async def _apply_credit_guard_and_headers(self) -> None:
        await assert_can_invoke_llm(user_identifier=self._user_identifier)
        headers = self._enterprise_headers_for_request()
        # Per-request headers — Agno passes extra_headers on each completions.create();
        # mutating default_headers alone is not enough when the HTTP client is cached.
        self.extra_headers = headers
        self.default_headers = dict(headers)
        log_llm_gateway_attribution(
            transport="agno",
            headers=headers,
            model=getattr(self, "id", None),
            use_service_token=True,
        )

    @staticmethod
    def _clean_empty_messages(messages: list[Message]) -> list[Message]:
        for message in messages:
            if message.content is None or message.content == "":
                message.content = "Tool Call"
        return messages

    @staticmethod
    def _extract_message_from_payload(payload: Any) -> Optional[str]:
        if isinstance(payload, str):
            return payload.strip() or None
        if not isinstance(payload, Mapping):
            return None

        # Handles OpenAI shape: {"error": {"message": "..."}}
        error_obj = payload.get("error")
        if isinstance(error_obj, Mapping):
            for key in ("message", "detail", "error_description", "title", "error"):
                val = error_obj.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()

        # Handles enterprise/gateway shapes: {"message": "..."} / {"detail": "..."}
        for key in ("message", "detail", "error_description", "title", "reason"):
            val = payload.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()

        return None

    @staticmethod
    def _extract_error_code(payload: Any) -> Optional[Any]:
        if not isinstance(payload, Mapping):
            return None
        error_obj = payload.get("error")
        if isinstance(error_obj, Mapping):
            for key in ("code", "errorCode", "type"):
                if key in error_obj:
                    return error_obj.get(key)
        for key in ("code", "errorCode", "type", "status"):
            if key in payload:
                return payload.get(key)
        return None

    @staticmethod
    def _extract_status_code(exc: Exception) -> Optional[int]:
        status_code = getattr(exc, "status_code", None)
        if isinstance(status_code, int):
            return status_code

        response = getattr(exc, "response", None)
        if response is not None:
            response_status = getattr(response, "status_code", None)
            if isinstance(response_status, int):
                return response_status
        return None

    @staticmethod
    def _response_payload(exc: Exception) -> Any:
        response = getattr(exc, "response", None)
        if response is None:
            return None

        try:
            return response.json()
        except Exception:
            text = getattr(response, "text", None)
            if isinstance(text, str) and text.strip():
                try:
                    return json.loads(text)
                except Exception:
                    return text
        return None

    @classmethod
    def _build_enriched_error_message(cls, exc: Exception) -> str:
        payload = cls._response_payload(exc)
        message = cls._extract_message_from_payload(payload)
        error_code = cls._extract_error_code(payload)
        status_code = cls._extract_status_code(exc)

        parts: list[str] = []
        if status_code is not None:
            parts.append(f"HTTP {status_code}")
        if error_code not in (None, "", status_code):
            parts.append(f"code={error_code}")
        if message:
            parts.append(message)

        if not parts:
            fallback = str(exc).strip()
            return fallback if fallback else "Model request failed"
        return " | ".join(parts)

    @classmethod
    def _normalize_model_provider_error(cls, error: ModelProviderError) -> ModelProviderError:
        raw_message = str(error).strip()
        if raw_message and raw_message.lower() != "unknown model error":
            return error

        candidate = error.__cause__ if error.__cause__ else error
        normalized_message = cls._build_enriched_error_message(candidate)
        return ModelProviderError(
            message=normalized_message,
            status_code=getattr(error, "status_code", 502),
            model_name=getattr(error, "model_name", None),
            model_id=getattr(error, "model_id", None),
        )

    async def ainvoke(
        self,
        messages: List[Message],
        assistant_message: Message,
        response_format: Optional[Union[Dict, Type[BaseModel]]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        run_response: Optional[RunOutput] = None,
        compress_tool_results: Optional[bool] = None,
    ) -> ModelResponse:
        try:
            await self._apply_credit_guard_and_headers()
            return await super().ainvoke(
                self._clean_empty_messages(messages),
                assistant_message,
                response_format,
                tools,
                tool_choice,
                run_response,
                compress_tool_results=compress_tool_results,
            )
        except InsufficientCreditsError:
            raise
        except ModelProviderError as error:
            raise self._normalize_model_provider_error(error) from error

    async def ainvoke_stream(
        self,
        messages: List[Message],
        assistant_message: Message,
        response_format: Optional[Union[Dict, Type[BaseModel]]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        run_response: Optional[RunOutput] = None,
        compress_tool_results: Optional[bool] = None,
    ) -> AsyncIterator[ModelResponse]:
        # Since the parent method is an async generator (uses yield),
        # we need to make this an async generator too and yield from it
        try:
            await self._apply_credit_guard_and_headers()
            async for response in super().ainvoke_stream(
                self._clean_empty_messages(messages),
                assistant_message,
                response_format,
                tools,
                tool_choice,
                run_response,
                compress_tool_results=compress_tool_results,
            ):
                yield response
        except InsufficientCreditsError:
            raise
        except ModelProviderError as error:
            raise self._normalize_model_provider_error(error) from error


__all__ = ["SlingshotGateway"]
