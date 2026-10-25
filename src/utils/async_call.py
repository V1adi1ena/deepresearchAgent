"""Keep synchronous model calls off the event loop; late results are never committed."""
from __future__ import annotations

import asyncio
import inspect
import logging
from contextvars import ContextVar
import functools
import time

logger = logging.getLogger(__name__)
model_budget = ContextVar("model_budget", default=None)
model_call_records = ContextVar("model_call_records", default=None)
request_deadline = ContextVar("request_deadline", default=None)
tool_call_records = ContextVar("tool_call_records", default=None)


def track_tool(tool):
    """Count provider executions, including failed/replanned calls and review searches."""
    original = tool.execute
    @functools.wraps(original)
    async def execute(*args, **kwargs):
        calls = tool_call_records.get()
        record = {"tool": tool.name, "status": "running"}
        started = time.monotonic()
        if calls is not None:
            calls.append(record)
        try:
            result = await original(*args, **kwargs)
            record["status"] = "failed" if isinstance(result, dict) and result.get("error") else "completed"
            return result
        except asyncio.CancelledError:
            record["status"] = "cancelled"
            raise
        except Exception as exc:
            record.update(status="failed", error_type=type(exc).__name__)
            raise
        finally:
            record["elapsed_seconds"] = time.monotonic()-started
    tool.execute = execute
    return tool


async def call_model(policy, messages):
    # Review must see the full candidate/evidence; do not silently trigger the
    # SDK wrapper's 35K-character truncation and then approve a partial check.
    if sum(len(str(message.get("content", ""))) for message in messages) > 34000:
        raise RuntimeError("Full review input exceeds context budget; original retained")
    budget = model_budget.get()
    if budget is not None:
        if budget["used"] >= budget["limit"]:
            budget["exhausted"] = True
            raise RuntimeError("Model call budget exhausted")
        budget["used"] += 1
    return await call_sync(policy, messages)


async def call_sync(func, *args, **kwargs):
    if inspect.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    future = asyncio.create_task(asyncio.to_thread(func, *args, **kwargs))
    try:
        return await asyncio.shield(future)
    except asyncio.CancelledError:
        # Cancelling the await does not kill an in-flight SDK request.
        def discard(done):
            if not done.cancelled():
                done.exception()  # Retrieve errors without admitting a late result.
                logger.warning("Discarded late result from %s", getattr(func, "__name__", type(func).__name__))
        future.add_done_callback(discard)
        raise
