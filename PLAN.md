# PLAN.md --- Provider-Agnostic Guardrails Scaffolding for Python AI Applications

> **Purpose:** Give an implementation agent (Claude Code) a precise plan
> for building a reusable, production-minded guardrails layer for AI
> applications.
>
> **Primary library:** Guardrails AI (`guardrails-ai`)\
> **Language:** Python\
> **Package manager:** `uv`\
> **Initial delivery:** An in-process Python library with a small
> FastAPI service and CLI for local testing.\
> **Design priority:** Clear boundaries, simple code,
> configuration-driven behavior, and no dependency on a specific LLM
> provider.

------------------------------------------------------------------------

## 1. Product goal

Build a reusable guardrails scaffolding that can sit in front of and
behind calls to **any text-capable LLM or LLM provider**.

The scaffolding must make it straightforward to:

-   Validate user input before it reaches an LLM.
-   Validate model output before it reaches the user or downstream
    application.
-   Validate retrieved context and tool inputs/outputs where the
    application chooses to use those hooks.
-   Enable, disable, and configure validators without rewriting
    application code.
-   Choose different policies for different application surfaces (for
    example, a public chatbot, an internal assistant, and a financial
    analytics assistant).
-   Add or replace validators without changing the core orchestration
    code.
-   Use the same guardrail layer with hosted APIs, local models,
    self-hosted inference servers, and different orchestration
    frameworks.

This is a **guardrails layer**, not an LLM client, agent framework,
model router, or prompt-management framework. Do not build a new
abstraction that attempts to replace provider SDKs.

## 2. Important architectural decision: provider independence

Guardrails AI provides validation. It does **not** make every LLM
provider interchangeable by itself.

Achieve provider independence by placing validation at the application
boundary:

``` text
                 Provider SDK / Local LLM / Agent Framework
                                  |
User request                     |
     |                            |
     v                            |
+-------------------+             |
| Input Guard       |             |
| Guardrails AI     |             |
+-------------------+             |
     | pass                         |
     v                              |
+----------------------------------+
| Existing application code        |
| Calls whichever LLM it already   |
| uses (OpenAI, Anthropic, Gemini, |
| Ollama, vLLM, etc.)               |
+----------------------------------+
     |
     v
+-------------------+
| Output Guard      |
| Guardrails AI     |
+-------------------+
     |
     v
Validated response
```

The core API should accept ordinary Python strings and small
framework-neutral request/result objects. It must not require an OpenAI
`messages` object, LangChain model, LiteLLM, or any provider-specific
SDK.

### Required integration pattern

Provide a simple wrapper/decorator or service method around an
application's existing model call:

1.  Receive the user's text.
2.  Run the configured input policy.
3.  If input is blocked, return a typed blocked result and do not call
    the model.
4.  If input passes, call the application's existing model function.
5.  Extract the textual response.
6.  Run the configured output policy.
7.  Return the validated text or a typed blocked/error result.

The application remains responsible for calling its model. The
guardrails package must not secretly create an LLM client or make an
extra model call unless a specific validator is explicitly configured to
do so.

### Provider compatibility requirements

-   The basic `validate_input(text)` and `validate_output(text)`
    interfaces must work without any LLM SDK installed.
-   A generic `guarded_call(user_input, llm_callable)` integration must
    accept a normal synchronous or asynchronous Python callable.
-   Support both `str` and `awaitable[str]` model callables.
-   Add optional examples/adapters only when they add real value. Keep
    provider SDKs in optional dependency groups, not core dependencies.
-   Do not claim that every provider's streaming, multimodal,
    tool-calling, or structured-output semantics are automatically
    supported.
-   For streaming, provide a separately designed opt-in integration
    later; do not pretend that validating each token independently is
    equivalent to validating a complete response.
-   For multimodal requests, define an explicit policy: either extract
    supported text for validation or return `unsupported_content`/skip
    only when the policy explicitly allows it. Never silently claim that
    image/audio/video payloads were inspected.

------------------------------------------------------------------------

## 3. Guardrails AI usage and dependency policy

Use Guardrails AI as the validation engine:

-   Core package: `guardrails-ai`.
-   Add only the individual validator packages actually used, for
    example `guardrails-ai-detect-pii` or another currently maintained
    package from the official Guardrails AI validator catalogue.
-   Use `Guard` / `AsyncGuard` and validator classes through a small
    internal adapter module.
-   Use Guardrails AI's validation results and failure mechanisms;
    translate them into this project's stable result types.
-   Prefer local validators and local inference dependencies where
    practical. If a validator calls an external service or model,
    document that explicitly.

**Important current ecosystem note:** Guardrails AI has moved validators
to ordinary public PyPI packages. Do not build the setup around the old
`guardrails hub install` flow, private package registry, or hosted
remote inference. Install validator packages with
`uv add <validator-package>` and import them from their documented
Python namespace. No Guardrails Hub API key should be assumed necessary
for current public PyPI validators. Verify the current official docs and
package names before implementing each validator.

Do not copy old Guardrails examples blindly. Before writing the adapter,
inspect the installed package version's current API and write a small
proof-of-concept test for: - Constructing a guard. - Attaching one
validator. - Running synchronous validation. - Running asynchronous
validation. - Reading pass/fail status and validated output. - Applying
the selected on-fail action.

Pin compatible versions in `uv.lock`. Do not use floating dependency
versions in production.

Official references: - Guardrails AI repository and current README:
https://github.com/guardrails-ai/guardrails - Guardrails AI validator
catalogue: https://guardrailsai.com/hub/ - Current API-key / public-PyPI
validator note: https://guardrailsai.com/hub/keys - Guardrails API
project (optional reference, not a required dependency):
https://github.com/guardrails-ai/guardrails-api

------------------------------------------------------------------------

## 4. Functional scope

### 4.1 Input guardrails

Initial input checks should cover:

-   Prompt-injection / jailbreak detection.
-   Disallowed topic detection (configurable topic policy).
-   PII detection, with configurable handling: block, redact/fix, or
    allow-and-log depending on the use case.
-   Maximum input length.
-   Empty/whitespace-only input.
-   Optional basic content-safety/toxicity validation.

Do not assume one validator catches every prompt injection. Use layered
controls and clearly document the limitations of detection-based
validators.

### 4.2 Output guardrails

Initial output checks should cover:

-   PII detection and configurable redaction/blocking.
-   Toxicity / harmful-content checks where appropriate.
-   Disallowed-topic checks.
-   Maximum output length.
-   Optional refusal / policy phrase checks only if they have a concrete
    application requirement.
-   Optional structured-output validation as a later extension, not a
    requirement for the first version.

Output validation must be independent of the provider. It validates the
extracted output text, not provider-specific response objects.

### 4.3 Tool and retrieval boundaries

Design stable interfaces for these future hooks, but do not overbuild
them in the first milestone:

-   `validate_retrieved_context(text, metadata=None)`
-   `validate_tool_input(tool_name, payload)`
-   `validate_tool_output(tool_name, payload)`

Treat retrieved documents and tool output as **untrusted data**. Prompt
injection can arrive through retrieved content and tool results, not
only through the user's message.

For the first version, support text payloads and document the
serialization policy for dictionaries. Do not stringify arbitrary
objects with `repr()` and pass them to validators.

### 4.4 Policy outcomes

Every validation call must produce a predictable project-level result,
independent of Guardrails AI's internal result class.

Use a small stable status vocabulary:

-   `passed` --- all enabled blocking checks passed.
-   `modified` --- content was changed by an allowed fix/redaction
    action and is safe to continue under policy.
-   `blocked` --- a policy check failed and continuation is forbidden.
-   `error` --- validation could not be completed (for example,
    validator unavailable or timed out).
-   `skipped` --- validation was intentionally skipped by explicit
    configuration, not because of an accidental failure.

Return structured details: - stage (`input`, `output`, `retrieval`,
`tool_input`, `tool_output`) - policy/profile name - status - validated
content, if applicable - failed validator identifiers - safe,
user-facing reason/code - correlation/request ID - duration -
non-sensitive diagnostic details for internal logs

Never expose raw stack traces, secrets, validator internals, or
sensitive PII in user-facing error messages.

------------------------------------------------------------------------

## 5. Non-functional requirements

1.  **Modular:** Each module has one clear responsibility.
2.  **Readable:** Prefer explicit functions and small classes over
    metaprogramming, deep inheritance, or clever abstractions.
3.  **Config-driven:** Policy behavior belongs in validated
    configuration, not scattered `if` statements.
4.  **Provider-neutral:** Core package has no mandatory LLM provider
    dependency.
5.  **Async-ready:** The primary service interface should support async
    applications. Also expose sync methods for simple scripts.
6.  **Safe defaults:** Fail closed for configured critical checks when
    validation errors occur, unless an explicit, reviewed policy says
    otherwise.
7.  **Observable:** Emit structured logs and basic metrics without
    logging raw prompts or model outputs by default.
8.  **Testable:** Validators, policy execution, and provider callables
    must be testable without network access.
9.  **Extensible:** New validators and policies should be added without
    editing the orchestration service.
10. **Portable:** Work on supported Python versions and common OS
    environments. Confirm Guardrails AI's currently supported Python
    versions before choosing the project's minimum version.

------------------------------------------------------------------------

## 6. Proposed repository structure

Use a `src/` layout and a single importable package named
`ai_guardrails`.

``` text
ai-guardrails/
├── PLAN.md
├── README.md
├── pyproject.toml
├── uv.lock
├── .python-version
├── .env.example
├── .gitignore
├── configs/
│   ├── default.yaml
│   ├── development.yaml
│   └── production.example.yaml
├── examples/
│   ├── basic_sync.py
│   ├── basic_async.py
│   ├── provider_agnostic_callable.py
│   └── fastapi_integration.py
├── src/
│   └── ai_guardrails/
│       ├── __init__.py
│       ├── config/
│       │   ├── __init__.py
│       │   ├── loader.py
│       │   ├── schema.py
│       │   └── defaults.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── types.py
│       │   ├── exceptions.py
│       │   ├── protocols.py
│       │   └── service.py
│       ├── engine/
│       │   ├── __init__.py
│       │   ├── guardrails_adapter.py
│       │   ├── guard_factory.py
│       │   └── result_mapper.py
│       ├── validators/
│       │   ├── __init__.py
│       │   ├── registry.py
│       │   └── custom/
│       │       ├── __init__.py
│       │       ├── input_length.py
│       │       └── non_empty.py
│       ├── policies/
│       │   ├── __init__.py
│       │   ├── executor.py
│       │   └── resolver.py
│       ├── integrations/
│       │   ├── __init__.py
│       │   ├── callable_wrapper.py
│       │   └── fastapi/
│       │       ├── __init__.py
│       │       ├── app.py
│       │       └── schemas.py
│       ├── observability/
│       │   ├── __init__.py
│       │   ├── logging.py
│       │   └── metrics.py
│       └── cli.py
├── tests/
│   ├── unit/
│   │   ├── test_config.py
│   │   ├── test_result_mapper.py
│   │   ├── test_policy_executor.py
│   │   ├── test_registry.py
│   │   └── test_callable_wrapper.py
│   ├── integration/
│   │   ├── test_guardrails_adapter.py
│   │   └── test_fastapi.py
│   └── fixtures/
│       └── configs/
└── docs/
    ├── architecture.md
    ├── configuration.md
    ├── adding_validators.md
    └── security_notes.md
```

Do not create empty files for every possible future feature. Implement
only modules needed for the milestones. Keep the proposed structure as
the target, but let the actual implementation grow incrementally.

------------------------------------------------------------------------

## 7. Module responsibilities

### `config/`

-   Load YAML configuration from an explicit path.
-   Validate it with Pydantic models.
-   Support environment-variable substitution for secrets and
    environment-specific values.
-   Reject unknown keys by default so misspellings do not silently
    disable security settings.
-   Resolve configuration once at application startup and pass the
    resulting immutable settings object into services.
-   Never read environment variables throughout business logic.
-   Never store API keys or secrets in YAML.

### `core/`

Define the framework's stable public contracts:

-   `ValidationStage`
-   `ValidationStatus`
-   `ValidationResult`
-   `GuardrailsService` interface / protocol
-   Project-specific exceptions

Keep these types independent of Guardrails AI. This allows the
underlying validation engine to be changed later without rewriting
application code.

### `engine/`

This is the only package that should know Guardrails AI's concrete API.

-   `guardrails_adapter.py`: wraps Guardrails AI sync/async execution.
-   `guard_factory.py`: converts validated policy configuration into
    Guardrails AI guard instances.
-   `result_mapper.py`: converts Guardrails AI outcomes/exceptions into
    project-level `ValidationResult`.
-   Do not leak Guardrails AI objects to the rest of the codebase.

### `validators/`

-   Maintain an explicit registry of supported validator names and their
    constructors.
-   Map safe config identifiers such as `detect_pii` to known Python
    validator classes.
-   Validate parameters before constructing validators.
-   Keep imports of optional validator packages isolated.
-   If a configured validator package is missing, fail at startup with
    an actionable error. Do not silently omit a security validator.
-   Provide a documented way to register a custom validator.
-   Avoid unrestricted `importlib` imports from arbitrary YAML strings.
    Configuration is trusted application configuration, but a fixed
    registry is simpler and safer.

### `policies/`

-   Resolve a named profile and stage to its configured validator
    sequence.
-   Construct or retrieve the corresponding Guardrails AI guard.
-   Execute checks in a predictable way.
-   Apply the configured failure policy.
-   Do not implement policy logic inside FastAPI routes or provider
    examples.

### `integrations/`

-   `callable_wrapper.py` wraps user-supplied model callables without
    owning their SDK clients.
-   FastAPI is a thin optional transport layer around the same
    `GuardrailsService`.
-   Do not duplicate validation logic in API endpoints.
-   Provider-specific adapters, if ever added, should only extract text
    and call the generic wrapper.

### `observability/`

-   Structured logs with request ID, stage, policy, status, failed
    validator IDs, and elapsed time.
-   Redact or omit content by default.
-   Optional content logging must require explicit opt-in and a clear
    warning.
-   Basic counters for pass, modified, blocked, error, skipped,
    validator failures, and latency.
-   Never log secrets, authorization headers, or full raw PII-bearing
    prompts by default.

------------------------------------------------------------------------

## 8. Configuration design

Use YAML for policy configuration and Pydantic for validation. Keep
configuration easy to read and avoid an unnecessarily complicated DSL.

The exact Guardrails AI constructor arguments and validator parameters
must be verified against the versions selected during implementation.
The following is the **project's conceptual configuration format**, not
a claim that Guardrails AI natively accepts this YAML.

Example `configs/default.yaml`:

``` yaml
app:
  name: ai-guardrails
  environment: development
  log_level: INFO

runtime:
  default_profile: default
  validation_timeout_seconds: 5
  fail_closed_on_validator_error: true
  log_content: false

profiles:
  default:
    input:
      enabled: true
      validators:
        - name: non_empty
          enabled: true
          on_fail: block
          params: {}

        - name: input_length
          enabled: true
          on_fail: block
          params:
            max_characters: 12000

        - name: prompt_injection
          enabled: true
          on_fail: block
          params: {}

        - name: detect_pii
          enabled: true
          on_fail: redact
          params:
            entities:
              - EMAIL_ADDRESS
              - PHONE_NUMBER

    output:
      enabled: true
      validators:
        - name: output_length
          enabled: true
          on_fail: block
          params:
            max_characters: 20000

        - name: detect_pii
          enabled: true
          on_fail: redact
          params:
            entities:
              - EMAIL_ADDRESS
              - PHONE_NUMBER

    retrieval:
      enabled: false
      validators: []

    tool_input:
      enabled: false
      validators: []

    tool_output:
      enabled: false
      validators: []

  internal_assistant:
    input:
      enabled: true
      validators:
        - name: non_empty
          enabled: true
          on_fail: block
          params: {}
    output:
      enabled: true
      validators: []
    retrieval:
      enabled: true
      validators: []
    tool_input:
      enabled: true
      validators: []
    tool_output:
      enabled: true
      validators: []
```

### Configuration rules

-   A profile is a named collection of stage policies.
-   A stage can be disabled explicitly.
-   A validator has a stable project identifier, `enabled`, `on_fail`,
    and `params`.
-   Supported `on_fail` values at the project level: `block`, `redact`,
    `fix`, `log_and_continue`.
-   Map these project-level actions to Guardrails AI's supported
    `OnFailAction` / validator behavior in the adapter. Do not assume
    the names are identical.
-   `block` must stop the pipeline.
-   `redact` or `fix` must only continue if the validator returns a
    trustworthy corrected value.
-   `log_and_continue` must be permitted only for non-critical checks
    and should require explicit configuration.
-   A validator failure caused by an exception/timeout is not the same
    as a normal policy violation. Apply `fail_closed_on_validator_error`
    separately.
-   Validate that every configured validator exists in the registry.
-   Validate parameters at startup, not only when the first request
    arrives.
-   Keep environment-specific overrides small. Avoid copying the entire
    config for each environment.
-   Do not permit a production config to accidentally enable raw content
    logging.

------------------------------------------------------------------------

## 9. Stable public Python API

Design the API around a service object created once during application
startup.

Illustrative target API (Claude must implement and adjust based on
actual Guardrails AI APIs):

``` python
from ai_guardrails import GuardrailsService, load_config

settings = load_config("configs/default.yaml")
guardrails = GuardrailsService.from_config(settings)

input_result = await guardrails.validate_input(
    "Please summarize this document.",
    profile="default",
)

if not input_result.is_allowed:
    # Do not call the LLM.
    ...

# The application owns the provider SDK and the model call.
```

Output:

``` python
output_result = await guardrails.validate_output(
    model_text,
    profile="default",
)

if output_result.is_allowed:
    return output_result.content
```

Generic callable wrapper:

``` python
from ai_guardrails.integrations import guarded_call

result = await guarded_call(
    user_input="Summarize the report.",
    llm_call=my_existing_llm_function,
    guardrails=guardrails,
    profile="default",
)

if result.status == "blocked":
    ...
else:
    return result.content
```

The wrapper must: - Validate input before invoking `llm_call`. - Not
invoke the callable if input is blocked or validation errors are
configured to fail closed. - Support sync and async callables without
blocking the event loop. - Pass only the validated input to the
callable. - Validate the returned text before returning it. - Return a
typed result rather than raising for expected policy blocks. - Raise or
return a typed error for unexpected execution failures according to a
documented contract. - Never retry an LLM call automatically. - Preserve
cancellation behavior in async applications. - Allow applications to
pass a request/correlation ID and safe metadata.

Keep this API small. Do not add generic abstractions for every
framework.

------------------------------------------------------------------------

## 10. Custom validator strategy

Implement a couple of tiny custom validators to demonstrate the
extension path:

1.  `non_empty`: reject blank strings.
2.  `input_length` / `output_length`: reject text beyond configured
    character limits.

Use Guardrails AI's documented custom-validator mechanism and result
types. Do not create a second independent validator engine.

For each custom validator: - Have one clear responsibility. - Validate
its own configuration parameters. - Return Guardrails AI's expected
pass/fail result. - Include a useful, non-sensitive failure message. -
Have unit tests for normal, boundary, and invalid input. - Document how
a developer adds a validator and registers it.

Do not write custom ML classifiers for prompt injection, jailbreaks,
toxicity, or PII as part of this scaffold. Prefer a maintained
Guardrails AI validator package where suitable, and clearly record its
model/runtime requirements and limitations.

------------------------------------------------------------------------

## 11. Error handling and security behavior

Use explicit exception types, for example:

-   `ConfigurationError`
-   `ValidatorUnavailableError`
-   `GuardrailsExecutionError`
-   `UnsupportedContentError`

Security rules:

-   Do not call the LLM when the input guard blocks.
-   Do not return model output when output validation blocks.
-   Critical validator errors should fail closed by default.
-   Do not silently skip missing validators.
-   Do not trust retrieved content, tool results, or user-provided
    metadata.
-   Do not execute tools based solely on model-generated text without
    the application's own authorization checks.
-   Guardrails are one defence layer, not a substitute for
    authorization, access control, parameterized queries, tool
    allowlists, output encoding, rate limits, or secure system prompts.
-   Prompt-injection detection is probabilistic and can have false
    positives and false negatives. Treat tool permissions and data
    access as security boundaries outside the LLM.
-   Apply request size limits and validation timeouts.
-   Do not expose PII in logs or exception messages.
-   Keep dependency versions locked and update validator packages
    deliberately.

### Failure matrix

  -----------------------------------------------------------------------
  Situation                           Expected behavior
  ----------------------------------- -----------------------------------
  Input violates a blocking policy    Return `blocked`; do not call LLM

  Input validator redacts             Continue with redacted input;
  successfully                        return/record `modified`

  Output violates a blocking policy   Do not return unsafe output

  Output validator redacts            Return redacted output with
  successfully                        `modified` status

  Critical validator package missing  Fail application startup

  Critical validator times out/throws Fail closed by default; return safe
                                      error

  Optional validator fails            Follow explicit policy; never
                                      silently skip

  Stage intentionally disabled        Return `skipped` with reason

  Unsupported multimodal payload      Return explicit unsupported/skipped
                                      result according to config
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 12. FastAPI service (thin optional layer)

Expose a small API for applications written in other languages or
processes. The Python library remains the source of truth.

Initial endpoints:

-   `GET /health`
-   `POST /v1/validate/input`
-   `POST /v1/validate/output`

Request schema should include: - `text` - optional `profile` - optional
`request_id` - optional safe metadata

Response schema should include: - `status` - `is_allowed` - `content`
when safe/available - `stage` - `policy` - `failed_validators` -
`reason_code` - `request_id` - `duration_ms`

Requirements: - Reuse the exact same `GuardrailsService`; do not
implement a second policy engine. - Load configuration and construct
guards at startup. - Add API authentication configuration before
exposing the service beyond localhost/private network. - Add
request-size limits and timeouts. - Do not expose internal stack
traces. - Document that the endpoint validates text; it is not an
OpenAI-compatible proxy in the first version.

Do not add PostgreSQL, Redis, a dashboard, or a distributed
policy-management system in the initial implementation. These add
operational complexity without being necessary for the core scaffold.

------------------------------------------------------------------------

## 13. CLI

Provide a minimal CLI for local validation and configuration checks:

``` bash
uv run ai-guardrails config-check --config configs/default.yaml
uv run ai-guardrails validate --stage input --text "Hello" --profile default
uv run ai-guardrails validate --stage output --text "Example answer" --profile default
uv run ai-guardrails serve
```

The CLI must use the same config loader and service as the Python API
and FastAPI server.

Do not print secrets or full PII-bearing content unless the user
explicitly requests local debug output.

------------------------------------------------------------------------

## 14. Dependencies and `uv` setup

Use `uv` for all dependency and environment management.

Expected setup commands:

``` bash
uv init --package
uv python pin 3.12
uv add guardrails-ai pydantic pydantic-settings pyyaml
uv add fastapi uvicorn typer
uv add --dev pytest pytest-asyncio httpx ruff mypy
```

Add validator packages only after confirming their current names,
imports, Python support, and transitive requirements. For example, if
the selected PII validator is still published under this name:

``` bash
uv add guardrails-ai-detect-pii
```

Use `pyproject.toml` to define: - Project metadata. - Runtime
dependencies. - Optional dependency groups if needed. - CLI entry
point. - Ruff configuration. - Pytest configuration. - Mypy
configuration.

Use `uv.lock` in version control. Document: - `uv sync` -
`uv run pytest` - `uv run ruff check .` - `uv run mypy src` -
`uv run ai-guardrails --help`

Do not use Poetry, pip-tools, requirements.txt as the primary dependency
manager, or Conda.

Python version: start with Python 3.12 only after verifying
compatibility across Guardrails AI and the chosen validator packages. If
compatibility requires another version, explain the decision in README
and pin it in `.python-version`.

------------------------------------------------------------------------

## 15. Testing plan

### Unit tests

Test without network access:

-   YAML loading and Pydantic validation.
-   Unknown profile / unknown stage handling.
-   Unknown validator rejection.
-   Missing validator dependency error.
-   Registry construction.
-   Pass, fail, modify, and exception result mapping.
-   `block`, `redact`, `fix`, and `log_and_continue` semantics.
-   Fail-closed behavior on validator errors.
-   Sync and async service calls.
-   Sync and async `llm_call` wrappers.
-   Ensure the model callable is not invoked after blocked input.
-   Ensure only validated/redacted input reaches the callable.
-   Ensure blocked output is never returned.
-   Request ID propagation.
-   Content is not logged by default.

Use fake validators and fake LLM callables for deterministic tests.

### Integration tests

Use the actual Guardrails AI package and at least one real, locally
executable validator package.

Test: - Guard construction. - Input validation. - Output validation. -
Sync and async execution. - On-fail behavior. - API response schemas. -
FastAPI error handling.

Do not make CI depend on external model APIs, paid API keys, or remote
inference. If a validator requires a model download, make that test
separately marked and optional.

### Security/regression tests

Include cases for: - Obvious prompt-injection attempts. -
Prompt-injection instructions embedded in retrieved text. - PII-like
input and output. - Empty and oversized input. - Validator
timeout/error. - Malformed configuration. - Missing validator package. -
A model callable that raises. - A model callable that returns an
unexpected type. - Attempts to bypass input validation through the
wrapper.

Do not assert that a probabilistic prompt-injection validator catches
every attack. Test known examples and document that detection is not a
proof of safety.

------------------------------------------------------------------------

## 16. Implementation milestones

Claude should implement in this order. Each milestone must leave the
project runnable and tested.

### Milestone 1 --- Project skeleton and configuration

-   Initialize project with `uv`.
-   Create `src/ai_guardrails`.
-   Add Pydantic config schema and YAML loader.
-   Add example config and `.env.example`.
-   Implement `config-check`.
-   Add tests for valid and invalid configuration.

**Acceptance:** `uv sync` succeeds; config check passes for the sample
YAML; invalid config produces a clear error.

### Milestone 2 --- Core types and Guardrails AI adapter

-   Define project-level result/status/stage types.
-   Verify the current Guardrails AI API with a tiny proof of concept.
-   Implement adapter and result mapper.
-   Add registry and guard factory.
-   Implement the two simple custom validators.

**Acceptance:** Real Guardrails AI guard can validate a string; internal
code does not depend on Guardrails AI result classes outside `engine/`.

### Milestone 3 --- Policy service

-   Implement profile resolution.
-   Implement `validate_input` and `validate_output`.
-   Implement sync and async paths.
-   Implement failure-action mapping and fail-closed behavior.
-   Add tests for all policy outcomes.

**Acceptance:** A caller can validate text using a single service
instance and receive stable project-level results.

### Milestone 4 --- Provider-agnostic callable integration

-   Implement sync/async generic `guarded_call`.
-   Ensure input validation happens before the LLM callable.
-   Ensure output validation happens after it.
-   Add examples using plain Python functions.
-   Add one optional provider example only if useful; keep its SDK
    optional.

**Acceptance:** The integration test uses a fake model callable and
proves the same code works without any provider SDK installed.

### Milestone 5 --- FastAPI and CLI

-   Add the three HTTP endpoints.
-   Add startup configuration and health endpoint.
-   Add CLI validation and serve commands.
-   Add API tests.

**Acceptance:** Local user can validate text from Python, CLI, and HTTP
with identical policy behavior.

### Milestone 6 --- Documentation and quality

-   Write README quickstart.
-   Write architecture/configuration/validator extension/security docs.
-   Add structured logging and basic metrics.
-   Run formatting, linting, type checks, and full tests.
-   Review dependencies and lockfile.

**Acceptance:** A new developer can clone the repository, run `uv sync`,
validate sample text, add a validator, and run tests by following README
only.

------------------------------------------------------------------------

## 17. Definition of done

The first release is complete when:

-   [ ] Project is initialized and locked with `uv`.
-   [ ] A single YAML config controls profiles, stages, validators,
    parameters, and failure actions.
-   [ ] Config is validated at startup; unknown/missing validators fail
    clearly.
-   [ ] Guardrails AI is isolated behind one adapter package.
-   [ ] Input and output validation work synchronously and
    asynchronously.
-   [ ] Generic callable wrapper works with arbitrary provider SDKs and
    local model functions.
-   [ ] Blocked input never reaches the model callable.
-   [ ] Blocked output never reaches the application caller.
-   [ ] Validator errors follow explicit fail-closed policy.
-   [ ] At least two custom validators demonstrate extension.
-   [ ] CLI and FastAPI use the same service.
-   [ ] Tests cover the critical security and failure paths.
-   [ ] Logs avoid raw prompt/output content by default.
-   [ ] README explains installation, configuration, use, extension,
    limitations, and deployment.
-   [ ] No mandatory provider SDK, database, Redis, or external model
    API is required for the core scaffold.

------------------------------------------------------------------------

## 18. Explicit non-goals for version 1

Do **not** implement these unless the core requirements are complete and
tested:

-   LLM provider abstraction or model router.
-   Agent framework or orchestration engine.
-   MCP server/client.
-   Prompt management or context engineering.
-   Semantic cache.
-   Vector database / RAG pipeline.
-   User accounts, dashboard, or policy-management UI.
-   PostgreSQL or Redis.
-   Distributed policy synchronization.
-   Automatic retries or model re-asking across arbitrary providers.
-   Full streaming guardrails.
-   Full image/audio/video moderation.
-   Custom trained safety models.
-   Claims of complete prompt-injection prevention.

These can be separate extensions later.

------------------------------------------------------------------------

## 19. Instructions to Claude Code

1.  Treat this file as the implementation specification.
2.  Start by inspecting the current working directory. If a project
    already exists, preserve it and adapt the plan rather than
    overwriting files.
3.  Before implementation, verify the current Guardrails AI and
    validator package APIs from their official documentation and
    installed package metadata. The ecosystem has changed; do not use
    deprecated `guardrails hub install` instructions.
4.  Implement milestone by milestone. Do not generate the entire
    repository as a mass of untested boilerplate.
5.  After each milestone:
    -   Run the relevant tests.
    -   Run Ruff and type checks where applicable.
    -   Fix failures before proceeding.
    -   Summarize files created, design decisions, commands run, and
        remaining work.
6.  Keep code beginner-readable: explicit names, short functions, type
    hints, docstrings for public APIs, and comments explaining *why*
    rather than restating *what*.
7.  Do not introduce abstractions, dependencies, or infrastructure not
    justified by a requirement.
8.  If a Guardrails AI API differs from the examples implied here, adapt
    the adapter to the current supported API and document the
    difference. Do not fake an API or silently downgrade functionality.
9.  Make the sample config actually executable with the installed
    validator packages. Do not leave placeholder validator names
    enabled.
10. Finish with a working quickstart and a concise architecture
    explanation.

**First task:** Complete Milestone 1, then continue in order. Do not
stop after merely describing the implementation.
