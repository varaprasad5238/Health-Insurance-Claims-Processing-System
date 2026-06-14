"""
LLM Configuration Settings

Defines configuration settings for Language Model API connections.
"""

from functools import lru_cache
from typing import Literal, Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.platform.auth.service_token_config import get_service_token_config
from src.platform.auth.service_token_manager import get_service_token
from src.platform.logging import get_logger

logger = get_logger(__name__)


class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="allow",
    )
    llm_provider: Literal["openailike"] = Field(default="openailike")
    llm_endpoint: str = Field(
        default="",
        description="The endpoint of the LLM provider, generally an OpenAI-compatible API endpoint",
        validation_alias=AliasChoices("ENT__LLM_SVC_URL", "LLM_ENDPOINT"),
    )
    llm_default_model: str = Field(
        default="gpt-4o",
        description="The default model to use if not specified",
        validation_alias=AliasChoices("LLM_DEFAULT_MODEL"),
    )
    llm_max_output_tokens: Optional[int] = Field(
        default=25000,
        description="Maximum output tokens for LLM responses; used e.g. in flow summarization. When unset, provider default applies.",
        validation_alias=AliasChoices("LLM_MAX_OUTPUT_TOKENS"),
    )
    llm_max_output_tokens_current_spec: Optional[int] = Field(
        default=20000,
        description="Maximum output tokens for current spec generation",
        validation_alias=AliasChoices("LLM_MAX_OUTPUT_TOKENS_CURRENT_SPEC"),
    )
    llm_max_output_tokens_target_spec: Optional[int] = Field(
        default=20000,     
        description="Maximum output tokens for target spec generation",
        validation_alias=AliasChoices("LLM_MAX_OUTPUT_TOKENS_TARGET_SPEC"),
    )
    llm_default_small_model: Optional[str] = Field(
        default=None,
        description="Fast/cheap model for light tasks (e.g. JSON repair). Falls back to llm_default_model when unset.",
        validation_alias=AliasChoices("LLM_DEFAULT_SMALL_MODEL"),
    )
    llm_temperature: float = Field(
        default=1.0,
        description="The temperature for the LLM provider",
        validation_alias=AliasChoices("LLM_TEMPERATURE"),
    )
    llm_timeout: int = Field(
        default=300,
        description="The timeout for the LLM provider in seconds",
        validation_alias=AliasChoices("LLM_TIMEOUT_SEC"),
    )
    llm_max_retries: int = Field(
        default=3,
        description="The maximum number of retry attempts for transient LLM errors",
        validation_alias=AliasChoices("LLM_MAX_RETRIES"),
    )
    llm_retry_base_delay: float = Field(
        default=5.0,
        description="Base delay in seconds for exponential backoff retries (delay = base * 2^attempt)",
        validation_alias=AliasChoices("LLM_RETRY_BASE_DELAY"),
    )
    encoding_model: str = Field(
        default="gpt-4o",
        description="Model name to use for tiktoken encoding",
        validation_alias=AliasChoices("ENCODING_MODEL"),
    )
    use_parser_model: bool = Field(
        default=True,
        description="Whether to use parser_model for specification generation",
        validation_alias=AliasChoices("USE_PARSER_MODEL"),
    )
    compression_model: str = Field(
        default="claude-sonnet-4-5@20250929",
        description="Model name to use for tool compression used during calling an agent",
        validation_alias=AliasChoices("LLM_COMPRESSION_MODEL"),
    )
    compress_token_limit: int = Field(
        default=32000,
        description="Token limit post which tool compression is triggered",
        validation_alias=AliasChoices("LLM_COMPRESS_TOKEN_LIMIT"),
    )
    llm_fallback_model: Optional[str] = Field(
        default=None,
        description=(
            "Fallback LLM model used automatically when the primary model's "
            "circuit breaker opens or after all primary-model retries are exhausted."
        ),
        validation_alias=AliasChoices("LLM_FALLBACK_MODEL"),
    )
    llm_circuit_breaker_failure_threshold: int = Field(
        default=3,
        description=(
            "Number of consecutive transient failures on the primary model before "
            "the circuit breaker transitions to the OPEN state."
        ),
        validation_alias=AliasChoices("LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD"),
    )
    llm_circuit_breaker_recovery_timeout: int = Field(
        default=60,
        description=(
            "Seconds to wait in the OPEN state before the circuit breaker "
            "transitions to HALF_OPEN and retries the primary model."
        ),
        validation_alias=AliasChoices("LLM_CIRCUIT_BREAKER_RECOVERY_TIMEOUT"),
    )

    llm_display_names: dict[str, str] = Field(
        default_factory=lambda: {
            # GPT Models
            "gpt-5": "GPT-5",
            # Gemini Models
            "gemini-2.5-pro": "Gemini 2.5 Pro",
            # Claude Models
            "claude-sonnet-4-5@20250929": "Claude Sonnet 4.5",
        },
        description="Mapping of LLM IDs to human-readable display names",
        validation_alias=AliasChoices("LLM_DISPLAY_NAMES"),
    )

    # Backward compatibility aliases
    @property
    def provider(self) -> str:
        """Alias for llm_provider"""
        return self.llm_provider

    @property
    def endpoint(self) -> str:
        """Alias for llm_endpoint"""
        return self.llm_endpoint

    @property
    def llmendpoint(self) -> str:
        """Alias for llm_endpoint (alternative name)"""
        return self.llm_endpoint

    @property
    def default_model(self) -> str:
        """Alias for llm_default_model"""
        return self.llm_default_model

    @property
    def small_model(self) -> str:
        """Model for light tasks (e.g. JSON repair). Falls back to llm_default_model when unset."""
        return self.llm_default_small_model or self.llm_default_model

    @property
    def temperature(self) -> float:
        """Alias for temperature"""
        return self.llm_temperature

    @property
    def timeout(self) -> int:
        """Alias for llm_timeout"""
        return self.llm_timeout

    @property
    def max_retries(self) -> int:
        """Alias for llm_max_retries"""
        return self.llm_max_retries

    async def get_api_key(self, auth_token: Optional[str] = None) -> str:
        """
        Get API key for LLM service.

        Behavior depends on AUTH_USE_SERVICE_TOKEN configuration:
        - If True: Service token takes precedence over explicit auth_token (current behavior)
        - If False: Use auth_token directly, skip service token lookup

        Args:
            auth_token: Optional authentication token to use as API key (required when AUTH_USE_SERVICE_TOKEN is False)

        Returns:
            API key string

        Raises:
            ValueError: If neither service_token nor auth_token is provided
        """
        service_token_config = get_service_token_config()

        # Service token is enabled - try service token first, then fallback to auth_token
        if service_token_config.auth_use_service_token:
            try:
                service_token = await get_service_token()
                if service_token:
                    logger.debug("Using service token for LLM service")
                    return service_token
            except Exception as e:
                logger.warning(
                    "Failed to obtain service token, falling back to auth_token",
                    error=str(e),
                )

        # If service token usage is disabled or service token retrieval failed, use auth_token
        if auth_token:
            logger.debug("Using auth_token for LLM service")
            return auth_token

        # No valid authentication available
        logger.error("No service_token or auth_token available for LLM service")
        raise ValueError(
            "Either service_token or auth_token is required for LLM service"
        )


@lru_cache
def get_llm_config() -> LLMConfig:
    return LLMConfig()
