# Architecture

## Flow

```
                your app's own provider SDK / local model
                              |
user text -> InputGuard -> (validated text) -> model call -> OutputGuard -> caller
```

`GuardrailsService` is created once at startup from validated settings. Every
`(profile, stage)` plan and every Guardrails AI guard is built eagerly, so bad config or a
missing validator package fails at startup rather than on the first request.

A call to `service.validate(stage, text, profile=...)`:

1. `PolicyResolver` returns the prebuilt `StagePlan` (unknown profile -> `UnknownProfileError`).
2. Non-text content is blocked or skipped per `runtime.on_unsupported_content`.
3. `PolicyExecutor` runs the plan's steps in order, feeding each the previous step's output,
   applying the failure action and fail-closed rules.
4. The result is recorded in `Metrics` and logged without content.

## Module responsibilities

| Package | Responsibility |
|---|---|
| `config/` | YAML -> pydantic `Settings`; env substitution; deep-merge of layered files. |
| `core/` | `ValidationResult`/status/stage types, exceptions, `GuardrailsService`. Types never import Guardrails AI. |
| `engine/` | The Guardrails AI adapter: build guards, run them, map results. |
| `validators/` | Registry of allowed config names + the custom validators. |
| `policies/` | Resolve profile+stage to a plan; execute it with the failure policy. |
| `integrations/` | `guarded_call` for any callable; the thin FastAPI transport. |
| `observability/` | JSON logging (content off by default) and in-process counters. |

Guardrails AI's concrete API is confined to `engine/` and `validators/` (validators *are*
Guardrails classes). Everything else sees only `Checker`/`CheckOutcome`/`ValidationResult`.

## Design decisions

- **One `AsyncGuard` per validator.** Failure attribution is exact, and per-validator
  action, timeout, and crash handling are simple. Cost: guards are small and cheap.
- **Project actions map onto Guardrails actions** (`engine/guard_factory.py`):
  `block`/`log_and_continue` -> `NOOP` (engine only reports; the executor decides),
  `redact`/`fix` -> `FIX` (engine applies the validator's `fix_value`). Verified against
  guardrails-ai 0.11; see `engine/result_mapper.py` for the observed semantics.
- **A fix is trusted only if** the engine considers it valid, it differs from the original,
  and it is non-blank. Otherwise a `redact`/`fix` step blocks.
- **Async-first.** The executor is written once as async; `*_sync` methods run it with
  `asyncio.run` and refuse to run inside an active loop.
- **Validator crash != violation.** Crashes/timeouts fail closed (`error`) for critical
  validators when `fail_closed_on_validator_error` is true. Skipping requires
  `critical: false` or an explicit fail-open setting, and is recorded in diagnostics.
- **Fixed registry, no dynamic imports from YAML.**
- **Tool payloads** are serialized as canonical JSON (never `repr()`); the result's
  `content` for tool stages is that serialized text.

## Deviations from PLAN.md

- `validators/custom/length.py` holds one `MaxLength` class exposed as both `input_length`
  and `output_length` (the plan listed `input_length.py`).
- Added `pii_regex` and `ban_list`. No maintained, offline PII or prompt-injection validator
  package was available: `guardrails-ai-detect-pii` is built on Presidio (heavy NLP dependencies, typically needing
  spaCy models; not verified here), and `guardrails-ai-detect-prompt-injection` is built on
  the Rebuff library, which was not suitable for an offline default. The
  default config therefore uses a small regex validator and a phrase list, both labelled as
  heuristics.
- Telemetry: Guardrails AI sends anonymous spans to a hosted endpoint unless disabled; the
  adapter disables it (`engine/guard_factory.py`).
- Added `runtime.on_unsupported_content`, `critical` on validators, and an `api` section.
