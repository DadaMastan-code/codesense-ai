from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any


def _is_tracing_enabled() -> bool:
    return bool(
        os.getenv("LANGSMITH_API_KEY")
        and os.getenv("LANGSMITH_TRACING_ENABLED", "false").lower() == "true"
    )


def traceable(name: str | None = None, **kwargs: Any) -> Callable:
    """Decorator that adds LangSmith tracing when configured, otherwise is a no-op."""
    if _is_tracing_enabled():
        try:
            from langsmith import traceable as _langsmith_traceable
            return _langsmith_traceable(name=name, **kwargs)
        except ImportError:
            pass

    def _noop_decorator(fn: Callable) -> Callable:
        return fn

    return _noop_decorator
