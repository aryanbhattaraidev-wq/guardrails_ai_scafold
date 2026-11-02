"""In-process counters. Export them however your application prefers."""

from __future__ import annotations

import threading
from collections import Counter

from ai_guardrails.core.types import ValidationResult


class Metrics:
    """Thread-safe counters for outcomes, validator failures, and latency."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status: Counter[tuple[str, str, str]] = Counter()
        self._validator_failures: Counter[str] = Counter()
        self._latency_total_ms = 0.0
        self._latency_max_ms = 0.0
        self._count = 0

    def record(self, result: ValidationResult) -> None:
        with self._lock:
            self._status[(result.stage.value, result.profile, result.status.value)] += 1
            for validator_id in result.failed_validators:
                self._validator_failures[validator_id] += 1
            self._count += 1
            self._latency_total_ms += result.duration_ms
            self._latency_max_ms = max(self._latency_max_ms, result.duration_ms)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            by_status: Counter[str] = Counter()
            for (_, _, status), n in self._status.items():
                by_status[status] += n
            return {
                "validations_total": self._count,
                "by_status": dict(by_status),
                "by_stage_profile_status": {
                    "/".join(key): n for key, n in sorted(self._status.items())
                },
                "validator_failures": dict(self._validator_failures),
                "latency_ms_avg": self._latency_total_ms / self._count if self._count else 0.0,
                "latency_ms_max": self._latency_max_ms,
            }
