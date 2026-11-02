# ai-guardrails

A provider-agnostic guardrails layer for Python AI applications, built on
[Guardrails AI](https://github.com/guardrails-ai/guardrails).

It validates text **before** it reaches your LLM and **after** it comes back. It is not
an LLM client, agent framework, or model router: your application keeps calling
whichever provider it already uses (OpenAI, Anthropic, Gemini, Ollama, vLLM, ...).
No provider SDK is a dependency.

```
user text -> [input policy] -> your existing model call -> [output policy] -> validated text
```

Policies live in YAML, are validated at startup, and can differ per application
surface ("profiles"). Results use a small stable vocabulary
(`passed | modified | blocked | error | skipped`) independent of Guardrails AI's classes.

## Quickstart

Requires [uv](https://docs.astral.sh/uv/). The project pins Python 3.12.

```bash
uv sync
uv run ai-guardrails config-check                       # builds every guard; fails if a validator is missing
uv run ai-guardrails validate --stage input --text "Email me at jane@example.com" --show-content
uv run pytest
```

Everything in `configs/default.yaml` runs offline: no model downloads, no API keys.

### Python

```python
from ai_guardrails import GuardrailsService, load_config

guardrails = GuardrailsService.from_config(load_config("configs/default.yaml"))  # once, at startup

result = await guardrails.validate_input("Please summarize this.", profile="default")
if result.is_allowed:
    text_for_model = result.content  # redactions already applied
```

Sync scripts use `validate_input_sync` / `validate_output_sync`.

### Wrap your existing model call

```python
from ai_guardrails.integrations import guarded_call

result = await guarded_call("Summarize the report.", my_llm_function, guardrails=guardrails)
if result.is_allowed:
    return result.content
else:
    return result.message  # safe, user-facing; result.reason_code is machine-readable
```

`my_llm_function` is any sync or async callable taking text. If it returns a provider
response object, pass `extract_text=lambda r: r.choices[0].message.content`.
Blocked input never reaches your function; blocked output is never returned; the model is
never retried. See `examples/` and the contract in
`src/ai_guardrails/integrations/callable_wrapper.py`.

### CLI and HTTP

```bash
uv run ai-guardrails validate --stage output --text "Example answer" --profile default
uv run ai-guardrails serve --port 8000
curl -X POST localhost:8000/v1/validate/input -H 'content-type: application/json' \
     -d '{"text": "hello", "profile": "default"}'
```

Endpoints: `GET /health`, `POST /v1/validate/input`, `POST /v1/validate/output`. Policy
outcomes are HTTP 200 with `is_allowed`; HTTP errors are for bad requests, auth, and size
limits. This validates text; it is **not** an OpenAI-compatible proxy.
Enable `api.auth_enabled` (key from the `AI_GUARDRAILS_API_KEY` env var) before binding
to anything but localhost; the config refuses a non-loopback host without it.

## Configuration

One YAML file defines profiles, stages (`input`, `output`, `retrieval`, `tool_input`,
`tool_output`), validators, parameters, and failure actions (`block`, `redact`, `fix`,
`log_and_continue`). Unknown keys are rejected. Layer small overrides:

```bash
uv run ai-guardrails config-check -c configs/default.yaml -c configs/production.yaml
```

Details: [docs/configuration.md](docs/configuration.md).

## Extending

Add a validator in three steps (write it, register it, reference it in YAML):
[docs/adding_validators.md](docs/adding_validators.md).

## Bundled validators

| Name | Source | Notes |
|---|---|---|
| `non_empty` | custom | rejects blank text |
| `input_length`, `output_length` | custom | max characters; no silent truncation |
| `pii_regex` | custom | email, phone, US SSN, Luhn-valid cards; redacts. **Pattern-based, not ML** |
| `ban_list` | `guardrails-ai-ban-list` | banned phrases; used as a *heuristic* injection/topic filter |

## Limitations (read these)

- The default prompt-injection and topic checks are a **phrase list**. They catch only
  obvious wording and are trivially evaded. Detection is probabilistic at best; treat tool
  permissions, data access and authorization as security boundaries outside the LLM.
- `pii_regex` misses names, addresses, free-form identifiers and most non-US formats. For
  real coverage add an ML detector (see the validator docs). Presidio-based packages
  (e.g. `guardrails-ai-detect-pii`) bring heavy NLP dependencies and were deliberately not
  made a default.
- No streaming support (validating per token is not equivalent to validating a response),
  and no image/audio/video inspection: non-text content is **blocked** by default, or
  skipped only if you set `runtime.on_unsupported_content: skip`.
- A validator timeout stops waiting but cannot kill the worker thread running a sync validator.
- Guardrails AI exports anonymous telemetry by default; this package turns it **off**.
  See [docs/security_notes.md](docs/security_notes.md).

## Development

```bash
uv sync
uv run pytest                 # unit + integration, fully offline
uv run ruff check . && uv run ruff format --check .
uv run mypy src
```

Layout: `config/` (YAML + pydantic), `core/` (types, service), `engine/` (the Guardrails AI
adapter), `validators/` (registry + custom validators), `policies/` (resolver + executor),
`integrations/` (callable wrapper, FastAPI), `observability/` (logs, metrics), `cli.py`.
Architecture: [docs/architecture.md](docs/architecture.md).
