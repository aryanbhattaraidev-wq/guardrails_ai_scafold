# Security notes

Guardrails are one defence layer, not a substitute for authorization, access control,
parameterized queries, tool allowlists, output encoding, rate limits, or a secure system prompt.

## What the defaults do and do not give you

- **Prompt injection.** The shipped `ban_list` check is a phrase filter. It stops obvious
  strings ("ignore previous instructions") and nothing more; paraphrase, other languages,
  encoding tricks and indirect injection defeat it. Tests assert known examples are caught,
  not that attacks are prevented. Do not rely on it to protect tools or data.
- **Retrieved documents and tool output are untrusted.** Injection can arrive through them.
  Enable the `retrieval`/`tool_output` stages for profiles that use them, and still enforce
  tool permissions outside the model.
- **PII.** `pii_regex` is pattern-based. It will miss much real PII.

## Failure behaviour

- Input blocked -> model is never called. Output blocked -> nothing is returned.
- A critical validator that crashes or times out yields `error` (fail closed). Fail-open is
  possible only via `critical: false` or `fail_closed_on_validator_error: false`, and is
  recorded in `diagnostics["skipped_validators"]`.
- A missing validator package fails startup; validators are never silently omitted.
- Non-text content is blocked unless `on_unsupported_content: skip` is set explicitly. A
  skipped result has `content=None`; the payload was not inspected.

## Privacy

- Logs contain request ID, stage, profile, status, validator IDs, reason code and timing.
  Not content. `runtime.log_content` opts in, logs a startup warning, and is rejected in
  production.
- `ValidationResult.content`/`diagnostics` are excluded from `repr`, so accidental logging of
  a result object does not leak text.
- User-facing messages come from a fixed table; validator messages and exception text are
  never shown to callers. Exceptions raised by validators are reduced to their type name.
- **Guardrails AI telemetry.** guardrails-ai 0.11 enables anonymous metrics by default and
  exports OpenTelemetry spans to a hosted endpoint at the first guard call. This package
  turns that off (`engine/guard_factory.py`), including after `Guard.configure()` re-reads
  `~/.guardrailsrc`. A test asserts it. If you construct Guardrails objects yourself, disable it too.

## Timeouts

`validation_timeout_seconds` bounds how long a request waits per validator. Guardrails AI
runs synchronous validators in a worker thread, so a timed-out validator keeps running until
it finishes; it cannot be killed. Keep validators fast, and rate-limit callers.

## HTTP service

- Bind to loopback by default; a non-loopback host requires `api.auth_enabled`, and startup
  fails if the key environment variable is unset. Keys are compared in constant time.
- Request bodies are limited by `Content-Length` and by `api.max_text_chars`. A chunked
  request without `Content-Length` is only caught by the text-length check after parsing;
  put a reverse proxy with a body limit in front for hostile networks.
- Validation errors never echo the submitted text; unexpected errors return a generic 500.
- `metadata` and `request_id` are untrusted; they are echoed back and never drive decisions.
- Transport security (TLS), rate limiting and network policy are the deployer's job.

## Dependencies

`uv.lock` pins every version. Update validator packages deliberately and review their source:
third-party validators run arbitrary code in your process.
