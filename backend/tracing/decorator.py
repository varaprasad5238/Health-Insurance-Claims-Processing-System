import asyncio
import inspect
import threading
from functools import wraps
from typing import Any, Optional
from .store import TraceStore
from .span import TraceStatus, stage_order_for_agent
from pydantic import BaseModel

def summarize_arg(arg: Any) -> Any:
    if isinstance(arg, BaseModel):
        dump = arg.model_dump()
        return {k: ("..." if isinstance(v, str) and len(v) > 50 else v) for k, v in dump.items()}
    elif isinstance(arg, dict):
        return {k: summarize_arg(v) for k, v in arg.items()}
    elif isinstance(arg, list):
        if len(arg) <= 5:
            return [summarize_arg(item) for item in arg]
        return f"list[{len(arg)}]"
    elif isinstance(arg, tuple):
        return tuple(summarize_arg(item) for item in arg)
    return str(arg)

def run_async_blocking(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: list[Any] = []
    error: list[BaseException] = []

    def runner():
        try:
            result.append(asyncio.run(coro))
        except BaseException as exc:
            error.append(exc)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()

    if error:
        raise error[0]
    return result[0] if result else None

def call_context(func, args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    signature = inspect.signature(func)
    bound = signature.bind_partial(*args, **kwargs)
    bound.apply_defaults()
    arguments = {key: value for key, value in bound.arguments.items() if key != "self"}
    claim_id = str(arguments.get("claim_id") or kwargs.get("claim_id") or "UNKNOWN")
    input_summary = {key: summarize_arg(value) for key, value in arguments.items()}
    return claim_id, input_summary

async def finish_started_span(
    span_id: Optional[str],
    *,
    status: TraceStatus,
    output_summary: Optional[dict[str, Any]],
    errors: Optional[list[str]] = None,
) -> None:
    if not span_id:
        return
    await TraceStore.finish_span(
        span_id,
        status=status,
        output_summary=output_summary,
        errors=errors or [],
        current_stage=None,
    )

def traced(agent_name: str, stage_order: Optional[int] = None, model_used: str = "none"):
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            claim_id, input_summary = call_context(func, args, kwargs)
            trace_stage_order = stage_order if stage_order is not None else stage_order_for_agent(agent_name)
            span_id = None
            if claim_id != "UNKNOWN":
                span_id = await TraceStore.start_span(
                    claim_id,
                    agent_name,
                    stage_order=trace_stage_order,
                    input_summary=input_summary,
                    model_used=model_used,
                )

            try:
                result = await func(*args, **kwargs)
                await finish_started_span(
                    span_id,
                    status="SUCCESS",
                    output_summary=summarize_arg(result),
                )
                return result
            except Exception as e:
                await finish_started_span(
                    span_id,
                    status="ERROR",
                    output_summary=None,
                    errors=[str(e)],
                )
                raise
                
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            claim_id, input_summary = call_context(func, args, kwargs)
            trace_stage_order = stage_order if stage_order is not None else stage_order_for_agent(agent_name)
            span_id = None
            if claim_id != "UNKNOWN":
                span_id = run_async_blocking(
                    TraceStore.start_span(
                        claim_id,
                        agent_name,
                        stage_order=trace_stage_order,
                        input_summary=input_summary,
                        model_used=model_used,
                    )
                )

            try:
                result = func(*args, **kwargs)
                run_async_blocking(
                    finish_started_span(
                        span_id,
                        status="SUCCESS",
                        output_summary=summarize_arg(result),
                    )
                )
                return result
            except Exception as e:
                run_async_blocking(
                    finish_started_span(
                        span_id,
                        status="ERROR",
                        output_summary=None,
                        errors=[str(e)],
                    )
                )
                raise

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator
