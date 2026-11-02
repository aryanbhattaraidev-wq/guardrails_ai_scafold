"""Framework-neutral integrations."""

from ai_guardrails.integrations.callable_wrapper import guarded_call, guarded_call_sync

__all__ = ["guarded_call", "guarded_call_sync"]
