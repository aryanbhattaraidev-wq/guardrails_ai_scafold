"""Load, merge, substitute and validate YAML configuration."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ai_guardrails.config.schema import Settings
from ai_guardrails.core.exceptions import ConfigurationError

# ${NAME} or ${NAME:-default}
_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def load_config(
    *paths: str | Path,
    env: Mapping[str, str] | None = None,
) -> Settings:
    """Load settings from one or more YAML files.

    Later files are deep-merged over earlier ones (dicts merge, lists and
    scalars are replaced), so an environment file only needs to contain its
    differences from the base file.

    ``env`` is only used for ``${VAR}`` substitution and defaults to
    ``os.environ``. Reading the environment happens here, once, never later.
    """
    if not paths:
        raise ConfigurationError("load_config() needs at least one YAML path")
    environment = os.environ if env is None else env

    merged: dict[str, Any] = {}
    for path in paths:
        merged = _deep_merge(merged, _read_yaml(Path(path)))

    return settings_from_dict(_substitute_env(merged, environment))


def settings_from_dict(data: Mapping[str, Any]) -> Settings:
    """Validate an already-parsed mapping, translating pydantic errors."""
    try:
        return Settings.model_validate(data)
    except ValidationError as exc:
        # Only location + message: pydantic's default text echoes input values,
        # which could include substituted secrets.
        lines = [
            f"  - {'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
            for err in exc.errors(include_input=False, include_url=False)
        ]
        raise ConfigurationError("Invalid configuration:\n" + "\n".join(lines)) from None


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(f"Cannot read config file '{path}': {exc.strerror}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Config file '{path}' is not valid YAML: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigurationError(
            f"Config file '{path}' must contain a YAML mapping at the top level"
        )
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _substitute_env(value: Any, env: Mapping[str, str]) -> Any:
    """Recursively expand ``${VAR}`` in string values (keys are left alone)."""
    if isinstance(value, str):
        return _expand(value, env)
    if isinstance(value, list):
        return [_substitute_env(item, env) for item in value]
    if isinstance(value, dict):
        return {key: _substitute_env(item, env) for key, item in value.items()}
    return value


def _expand(text: str, env: Mapping[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        name, default = match.group(1), match.group(2)
        if name in env:
            return env[name]
        if default is not None:
            return default
        raise ConfigurationError(
            f"Config references environment variable '{name}' which is not set "
            "(use ${NAME:-default} to provide a fallback)"
        )

    return _ENV_PATTERN.sub(replace, text)
