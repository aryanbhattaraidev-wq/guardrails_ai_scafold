"""Project-specific exceptions.

Messages on these exceptions are written for developers/operators (startup and
programming errors). They must never contain user content or PII.
"""

from __future__ import annotations


class GuardrailsError(Exception):
    """Base class for every error raised by this package."""


class ConfigurationError(GuardrailsError):
    """The configuration is malformed, incomplete, or unsafe."""


class UnknownProfileError(GuardrailsError):
    """A caller asked for a profile that is not defined in the configuration."""


class ValidatorUnavailableError(GuardrailsError):
    """A configured validator is unknown or its package is not installed."""


class GuardrailsExecutionError(GuardrailsError):
    """A validator crashed or timed out (as opposed to finding a violation)."""


class UnsupportedContentError(GuardrailsError):
    """The content cannot be turned into text that validators can inspect."""


class ModelCallError(GuardrailsError):
    """The application's own model callable failed (raised only on request)."""
