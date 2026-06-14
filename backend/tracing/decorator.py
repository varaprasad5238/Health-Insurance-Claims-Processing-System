import time
import uuid
import inspect
from functools import wraps
from datetime import datetime, timezone
from typing import Any
from .span import TraceSpan
from .store import TraceStore
from pydantic import BaseModel

def summarize_arg(arg: Any) -> Any:
    if isinstance(arg, BaseModel):
        dump = arg.model_dump()
        return {k: ("..." if isinstance(v, str) and len(v)>50 else v) for k,v in dump.items()}
    elif isinstance(arg, list):
        return f"list[{len(arg)}]"
    return str(arg)

def traced(agent_name: str):
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            claim_id = kwargs.get("claim_id", "UNKNOWN")
            
            started_at = datetime.now(timezone.utc)
            start_time = time.time()
            
            input_summary = {k: summarize_arg(v) for k, v in kwargs.items()}
            status = "SUCCESS"
            errors = []
            output_summary = {}
            
            try:
                result = await func(*args, **kwargs)
                output_summary = summarize_arg(result)
                return result
            except Exception as e:
                status = "ERROR"
                errors.append(str(e))
                raise
            finally:
                ended_at = datetime.now(timezone.utc)
                elapsed_ms = int((time.time() - start_time) * 1000)
                
                span = TraceSpan(
                    span_id=str(uuid.uuid4()),
                    claim_id=claim_id,
                    agent_name=agent_name,
                    started_at=started_at,
                    ended_at=ended_at,
                    elapsed_ms=elapsed_ms,
                    input_summary=input_summary,
                    output_summary=output_summary,
                    confidence_delta=None,
                    errors=errors,
                    status=status
                )
                TraceStore.add_span(span)
                
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            claim_id = kwargs.get("claim_id", "UNKNOWN")
            started_at = datetime.now(timezone.utc)
            start_time = time.time()
            
            input_summary = {k: summarize_arg(v) for k, v in kwargs.items()}
            status = "SUCCESS"
            errors = []
            output_summary = {}
            
            try:
                result = func(*args, **kwargs)
                output_summary = summarize_arg(result)
                return result
            except Exception as e:
                status = "ERROR"
                errors.append(str(e))
                raise
            finally:
                ended_at = datetime.now(timezone.utc)
                elapsed_ms = int((time.time() - start_time) * 1000)
                
                span = TraceSpan(
                    span_id=str(uuid.uuid4()),
                    claim_id=claim_id,
                    agent_name=agent_name,
                    started_at=started_at,
                    ended_at=ended_at,
                    elapsed_ms=elapsed_ms,
                    input_summary=input_summary,
                    output_summary=output_summary,
                    confidence_delta=None,
                    errors=errors,
                    status=status
                )
                TraceStore.add_span(span)

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator
