"""
LLM Circuit Breaker

Provides a per-model aiobreaker-based circuit breaker that guards calls to LLM
models.  Each distinct primary model gets its own independent breaker so that
tripping one model's circuit does not affect requests to other models.

When the failure counter for a model reaches ``llm_circuit_breaker_failure_threshold``
its circuit transitions to OPEN and callers should route requests to the
configured fallback model instead.  After ``llm_circuit_breaker_recovery_timeout``
seconds the circuit moves to HALF-OPEN and allows one probe request through.

Excluded from failure counting
-------------------------------
- ``LLMNonRetryableError``: HTTP 4xx client errors — the model is reachable but
  the request itself is invalid.  These do not indicate availability problems.
- ``LLMStreamCutoffError``: The model responded but the output hit the token
  limit.  This is a configuration/content issue, not a model outage.
"""

from __future__ import annotations

from datetime import timedelta
from functools import lru_cache

import aiobreaker

from src.platform.logging import get_logger

logger = get_logger(__name__)


class _LLMCircuitBreakerListener(aiobreaker.CircuitBreakerListener):
    """Logs circuit-breaker state transitions and per-call outcomes."""

    def state_change(
        self,
        cb: aiobreaker.CircuitBreaker,
        old_state,
        new_state,
    ) -> None:
        logger.warning(
            "LLM circuit breaker state changed",
            circuit_name=cb.name,
            old_state=old_state.state.name if old_state is not None else None,
            new_state=new_state.state.name,
        )

    def failure(self, cb: aiobreaker.CircuitBreaker, exc: BaseException) -> None:
        logger.warning(
            "LLM circuit breaker recorded failure",
            circuit_name=cb.name,
            fail_counter=cb.fail_counter,
            fail_max=cb.fail_max,
            exception_type=type(exc).__name__,
        )

    def success(self, cb: aiobreaker.CircuitBreaker) -> None:
        logger.debug(
            "LLM circuit breaker recorded success",
            circuit_name=cb.name,
        )


@lru_cache(maxsize=None)
def get_primary_model_circuit_breaker(model_name: str) -> aiobreaker.CircuitBreaker:
    """
    Return the circuit breaker for ``model_name``.

    One breaker is created per distinct model name (lru_cache) so that
    failure counts are isolated: a flaky model trips only its own breaker
    and does not affect requests routed to other models.
    """
    # Late import to avoid circular dependency at module load time.
    from src.platform.llm.config import get_llm_config
    from src.platform.llm.exceptions import LLMNonRetryableError, LLMStreamCutoffError

    config = get_llm_config()
    cb = aiobreaker.CircuitBreaker(
        fail_max=config.llm_circuit_breaker_failure_threshold,
        timeout_duration=timedelta(seconds=config.llm_circuit_breaker_recovery_timeout),
        exclude=[LLMNonRetryableError, LLMStreamCutoffError],
        listeners=[_LLMCircuitBreakerListener()],
        name=f"llm_model:{model_name}",
    )
    logger.info(
        "LLM circuit breaker initialised",
        model=model_name,
        fail_max=config.llm_circuit_breaker_failure_threshold,
        reset_timeout=config.llm_circuit_breaker_recovery_timeout,
    )
    return cb
