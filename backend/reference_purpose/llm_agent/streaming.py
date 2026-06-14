"""Streaming execution utilities for Agno Agent and Team runs.

Non-streaming (stream=False) Agno calls hit a ~21k token / 10-minute wall on
certain LLM gateways.  These helpers switch the transport to streaming while
still returning the **same RunOutput / TeamRunOutput** the callers already
expect, making the change transparent to all downstream logic.
"""

from __future__ import annotations

from typing import Union

from agno.agent import Agent
from agno.run.agent import RunOutput, RunEvent, RunErrorEvent, RunStatus
from agno.team import Team
from agno.run.team import TeamRunOutput, TeamRunEvent

from src.platform.error_codes import SLINAM0035
from src.platform.llm.exceptions import LLMException
from src.platform.logging import get_logger
from src.platform.llm_agent.errors import (
    extract_run_event_error,
    extract_run_output_error,
    _GENERIC_ERROR_MARKERS,
)

logger = get_logger(__name__)

# Re-export for backward compatibility (chat/service.py imports _extract_run_event_error)
_extract_run_event_error = extract_run_event_error


async def collect_agent_stream(agent: Agent, input: Union[str, object], **kwargs) -> RunOutput:
    """Run an Agno Agent with streaming and return the complete RunOutput.

    Agno's ``arun(stream=True, yield_run_output=True)`` yields intermediate
    events then emits the finalised ``RunOutput`` as the last item.  This
    helper drains the stream -- keeping the HTTP connection alive so long-
    running generations don't time out -- and hands back the same object
    that ``arun(stream=False)`` would have produced.
    """
    kwargs.pop("stream", None)

    run_output: RunOutput | None = None

    async for event in agent.arun(input, stream=True, yield_run_output=True, **kwargs):
        if isinstance(event, RunOutput):
            run_output = event
        elif isinstance(event, RunErrorEvent):
            error_detail = extract_run_event_error(event)
            logger.error("Agent stream error event received", error=error_detail)
            detail = str(error_detail).lower()
            if "unknown model" in detail or ("model" in detail and "not found" in detail) or "404" in detail:
                raise LLMException(SLINAM0035.code)
            raise RuntimeError(f"Agent streaming error: {error_detail}")

    if run_output is None:
        raise RuntimeError("Agent stream completed without producing a RunOutput")

    if run_output.status == RunStatus.error:
        error_msg = extract_run_output_error(run_output)
        logger.error("Agent run completed with error status", error=error_msg)
        raise RuntimeError(f"Agent execution failed: {error_msg}")

    return run_output


async def collect_team_stream(team: Team, input: str, **kwargs) -> TeamRunOutput:
    """Run an Agno Team with streaming and return the complete TeamRunOutput.

    Mirrors :func:`collect_agent_stream` for Team-based workflows.
    """
    kwargs.pop("stream", None)

    run_output: TeamRunOutput | None = None

    async for event in team.arun(input, stream=True, yield_run_output=True, **kwargs):
        if isinstance(event, TeamRunOutput):
            run_output = event
        elif hasattr(event, "event") and event.event == TeamRunEvent.run_error.value:
            error_detail = extract_run_event_error(event)
            logger.error("Team stream error event received", error=error_detail)
            raise RuntimeError(f"Team streaming error: {error_detail}")

    if run_output is None:
        raise RuntimeError("Team stream completed without producing a TeamRunOutput")

    if getattr(run_output, "status", None) == RunStatus.error:
        error_msg = extract_run_output_error(run_output)  # type: ignore[arg-type]
        logger.error("Team run completed with error status", error=error_msg)
        raise RuntimeError(f"Team execution failed: {error_msg}")

    return run_output
