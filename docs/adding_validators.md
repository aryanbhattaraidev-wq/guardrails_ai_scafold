# Adding a validator

Validators use Guardrails AI's own mechanism; there is no second engine.

## 1. Write it

```python
# src/ai_guardrails/validators/custom/no_urls.py
import re
from guardrails.validators import FailResult, PassResult, Validator, register_validator


@register_validator(name="ai_guardrails/no_urls", data_type="string")
class NoUrls(Validator):
    def _validate(self, value, metadata):
        if re.search(r"https?://", value):
            # Non-sensitive message: never include the matched text.
            return FailResult(
                error_message="Text contains a URL",
                fix_value=re.sub(r"https?://\S+", "<URL>", value),
            )
        return PassResult()
```

- Return `fix_value` only when a fix is genuinely safe. `redact`/`fix` steps block if none is given.
- Keep messages free of content and PII.

## 2. Register it

Add a params model and factory in `validators/registry.py` and register it in
`default_registry()`:

```python
class _NoUrlsParams(_Params):
    pass


def _no_urls(_: _NoUrlsParams, on_fail):
    return NoUrls(on_fail=on_fail)


registry.register(ValidatorSpec("no_urls", _NoUrlsParams, _no_urls, "Reject URLs"))
```

Or, without editing the package, build a registry yourself:

```python
registry = default_registry()
registry.register(ValidatorSpec("no_urls", _NoUrlsParams, _no_urls))
service = GuardrailsService.from_config(settings, registry=registry)
```

Params models forbid unknown keys, so typos fail at startup.

## 3. Use it

```yaml
- name: no_urls
  on_fail: redact
```

## Wrapping a third-party validator package

Install it with `uv add <package>` (public PyPI; no Guardrails Hub login). Import it
**inside the factory** and raise `ValidatorUnavailableError` with an install hint on
`ImportError` (see `_ban_list` in the registry). Read the package's source first: check its
constructor arguments, whether it needs a model download, and whether it calls an external
service. Do not enable a validator in a shipped config that cannot run offline unless the
docs say so.

For stronger PII detection, `guardrails-ai-detect-pii` (Presidio) is the obvious candidate.
It is built on Presidio, has heavy dependencies (likely including NLP model downloads), was
not tested here, and is not installed by default.

## Tests

Add unit tests for pass, fail, boundaries and invalid params (see
`tests/unit/test_custom_validators.py`), and make sure the failure message contains no
content.
