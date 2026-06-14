from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, Iterator

_current_metrics_recorder: ContextVar[Any] = ContextVar(
    "current_metrics_recorder",
    default=None,
)
_current_metrics_slug: ContextVar[str | None] = ContextVar(
    "current_metrics_slug",
    default=None,
)


def get_current_metrics_recorder() -> Any:
    return _current_metrics_recorder.get()


def get_current_metrics_slug() -> str | None:
    return _current_metrics_slug.get()


@contextmanager
def push_metrics_context(*, recorder: Any = None, slug: str | None = None) -> Iterator[None]:
    recorder_token: Token = _current_metrics_recorder.set(recorder)
    slug_token: Token = _current_metrics_slug.set(slug)
    try:
        yield
    finally:
        _current_metrics_recorder.reset(recorder_token)
        _current_metrics_slug.reset(slug_token)
