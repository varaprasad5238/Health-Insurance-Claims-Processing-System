class PlatformError(Exception):
    """Base class for platform-level failures."""

    code = "PLATFORM_ERROR"

    def __init__(self, message: str | None = None, *, code: str | None = None):
        super().__init__(message or self.code)
        self.code = code or self.code


class ProviderTimeout(PlatformError):
    """Raised when an LLM provider call exceeds its timeout."""

    code = "PROVIDER_TIMEOUT"


class ProviderUnavailable(PlatformError):
    """Raised when a configured provider cannot be used."""

    code = "PROVIDER_UNAVAILABLE"


class InvalidModelOutput(PlatformError):
    """Raised when model output cannot be parsed as expected."""

    code = "INVALID_MODEL_OUTPUT"


class SchemaValidationFailed(PlatformError):
    """Raised when parsed model output does not match the requested schema."""

    code = "SCHEMA_VALIDATION_FAILED"


class AgentExecutionError(PlatformError):
    """Raised when an agent wrapper cannot complete successfully."""

    code = "AGENT_EXECUTION_ERROR"
