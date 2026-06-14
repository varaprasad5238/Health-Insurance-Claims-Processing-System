class LLMException(Exception):
    pass


class LLMAuthException(LLMException):
    pass


class LLMNonRetryableError(LLMException):
    """
    Raised for non-retryable HTTP 4xx client errors (e.g., 400, 404).

    These indicate a problem with the request itself, not model availability,
    so they are excluded from the circuit breaker failure count.

    Attributes:
        error_str: The formatted LLM_ERROR string to return to the caller.
    """

    def __init__(self, error_str: str) -> None:
        self.error_str = error_str
        super().__init__(error_str)


class LLMStreamCutoffError(LLMException):
    """
    Raised when the LLM streaming response is terminated early due to the
    output token limit being reached (finish_reason == "length").

    Attributes:
        partial_content: The text accumulated before the stream was cut off.
        model: The LLM model that produced the truncated response.
    """

    def __init__(self, model: str, partial_content: str = "") -> None:
        self.model = model
        self.partial_content = partial_content
        super().__init__(
            f"LLM stream cut off due to max_tokens limit (finish_reason='length') "
            f"for model '{model}'. Partial content length: {len(partial_content)} chars."
        )
