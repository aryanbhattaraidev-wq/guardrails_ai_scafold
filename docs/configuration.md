# Configuration reference

Load with `load_config("a.yaml", "b.yaml")`; later files are deep-merged over earlier ones
(mappings merge, lists and scalars replace). Unknown keys are errors. `${NAME}` and
`${NAME:-default}` are expanded in string values. Never put secrets in YAML.

## `app`
| key | default | notes |
|---|---|---|
| `name` | `ai-guardrails` | |
| `environment` | `development` | `development`, `test`, `production` |
| `log_level` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

## `runtime`
| key | default | notes |
|---|---|---|
| `default_profile` | `default` | must exist under `profiles` |
| `validation_timeout_seconds` | `5` | per validator |
| `fail_closed_on_validator_error` | `true` | crash/timeout of a *critical* validator -> `error` |
| `on_unsupported_content` | `block` | `block` or `skip` for non-text payloads |
| `log_content` | `false` | logs raw prompts/outputs; **rejected when `environment: production`** |

## `api`
| key | default | notes |
|---|---|---|
| `host` / `port` | `127.0.0.1` / `8000` | non-loopback host requires `auth_enabled: true` |
| `max_text_chars` | `100000` | larger text -> HTTP 413 |
| `auth_enabled` | `false` | when true, clients send `X-API-Key` |
| `api_key_env` | `AI_GUARDRAILS_API_KEY` | *name* of the env var holding the key |

## `profiles.<name>.<stage>`
Stages: `input`, `output`, `retrieval`, `tool_input`, `tool_output`. A missing stage is
disabled and returns `skipped` (`reason_code: stage_disabled`).

```yaml
profiles:
  support_bot:
    input:
      enabled: true
      validators:
        - name: input_length        # registry name
          enabled: true             # default true; disabled validators are not built
          on_fail: block            # block | redact | fix | log_and_continue
          critical: true            # default true
          params: {max_characters: 4000}
```

### `on_fail`
| value | behaviour |
|---|---|
| `block` | stop; stage is `blocked`, content withheld |
| `redact` / `fix` | continue with the corrected text (`modified`) **only** if the validator supplied a trustworthy fix; otherwise `blocked` |
| `log_and_continue` | record the violation and continue. Requires `critical: false` |

### Startup validation
`GuardrailsService.from_config` (and `ai-guardrails config-check`) fails if a validator name
is unknown, its params are invalid, or its package is not installed.

## Built-in validator params
- `non_empty`: none
- `input_length`, `output_length`: `max_characters` (int > 0)
- `pii_regex`: `entities` (subset of `EMAIL_ADDRESS`, `PHONE_NUMBER`, `US_SSN`, `CREDIT_CARD`)
- `ban_list`: `banned_words` (list), `max_l_dist` (0-3, default 0; higher = fuzzy, more false positives)
