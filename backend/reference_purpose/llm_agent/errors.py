"""Shared error extraction utilities for Agno agent run outputs."""

from __future__ import annotations

from typing import Any

_GENERIC_ERROR_MARKERS = frozenset(
    {
        "unknown model error",
        "unknown streaming error",
        "agent execution failed with unknown error",
    }
)


def extract_run_output_error(response: Any) -> str:
    """Extract the most descriptive error string from an Agno RunOutput.

    Agno may surface a generic string (e.g. ``"Unknown model error"``) in
    ``response.content``.  This function probes ``model_provider_data`` and
    embedded run events for richer diagnostics, skipping known generic
    placeholders so callers always get an actionable message.

    Args:
        response: An Agno ``RunOutput`` (or any object with compatible attrs).

    Returns:
        The most descriptive error string available, never an empty string.
    """
    candidates: list[str] = []

    # Primary content
    content = getattr(response, "content", None)
    if content:
        s = str(content).strip()
        if s:
            candidates.append(s)

    # Provider metadata
    model_provider_data = getattr(response, "model_provider_data", None)
    if isinstance(model_provider_data, dict):
        for key in ("error", "message", "detail", "error_message"):
            val = model_provider_data.get(key)
            if isinstance(val, str) and val.strip():
                candidates.append(val.strip())

        status = model_provider_data.get("status_code")
        code = model_provider_data.get("code")
        if status is not None or code is not None:
            candidates.append(f"provider_status={status}, provider_code={code}")

    # Embedded run events often carry richer details
    for event in getattr(response, "events", []) or []:
        if getattr(event, "event", "") != "RunError":
            continue
        event_content = getattr(event, "content", None)
        if event_content:
            s = str(event_content).strip()
            if s:
                candidates.append(s)
        error_type = getattr(event, "error_type", None)
        additional_data = getattr(event, "additional_data", None)
        if error_type:
            candidates.append(f"error_type={error_type}")
        if additional_data:
            candidates.append(f"additional_data={additional_data}")

    # Return first non-generic candidate, otherwise fall back to first available.
    for candidate in candidates:
        if candidate.lower() not in _GENERIC_ERROR_MARKERS:
            return candidate

    return candidates[0] if candidates else "Agent execution failed with unknown error"


def extract_run_event_error(event: Any) -> str:
    """Extract the most descriptive error string from an Agno RunErrorEvent.

    Agno may surface a generic string (e.g. ``"Unknown model error"``) in
    ``event.content``.  This function probes additional attributes that Agno
    or the underlying provider may have populated with richer diagnostics.

    Args:
        event: An Agno ``RunErrorEvent`` (or any object with compatible attrs).

    Returns:
        The most descriptive error string available, never an empty string.
    """
    candidates: list[str] = []

    content = getattr(event, "content", None)
    if content:
        s = str(content).strip()
        if s:
            candidates.append(s)

    for attr in ("error_type", "additional_data", "model_provider_data"):
        val = getattr(event, attr, None)
        if val:
            candidates.append(f"{attr}={val}")

    for candidate in candidates:
        if candidate.lower() not in _GENERIC_ERROR_MARKERS:
            return candidate

    return candidates[0] if candidates else "Agent execution failed with unknown error"
