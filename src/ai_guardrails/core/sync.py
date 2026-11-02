"""Helper for the synchronous convenience methods."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

from ai_guardrails.core.exceptions import GuardrailsError


def run_sync[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine to completion from synchronous code.

    Refuses to run inside an active event loop: blocking a running loop would
    stall the application. Async callers should ``await`` the async API.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    coro.close()
    raise GuardrailsError(
        "A synchronous guardrails method was called from a running event loop; "
        "use the async method instead."
    )
