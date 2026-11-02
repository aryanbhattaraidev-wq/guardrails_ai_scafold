from pathlib import Path

import pytest

from ai_guardrails.config import load_config, settings_from_dict
from ai_guardrails.core.exceptions import ConfigurationError

REPO = Path(__file__).resolve().parents[2]


def minimal(**overrides):
    stage = {"enabled": True, "validators": [{"name": "non_empty"}]}
    data = {"profiles": {"default": {"input": stage}}}
    data.update(overrides)
    return data


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_sample_config_loads():
    settings = load_config(REPO / "configs" / "default.yaml")
    assert settings.runtime.default_profile == "default"
    assert {"default", "internal_assistant"} <= set(settings.profiles)
    assert settings.profiles["default"].input.enabled is True
    assert settings.profiles["default"].retrieval.enabled is False


def test_missing_stage_defaults_to_disabled():
    settings = settings_from_dict(minimal())
    assert settings.profiles["default"].output.enabled is False


def test_unknown_key_is_rejected_with_location():
    with pytest.raises(ConfigurationError, match=r"runtime\.fail_closed_on_validater_error"):
        settings_from_dict(minimal(runtime={"fail_closed_on_validater_error": False}))


def test_unknown_on_fail_value_is_rejected():
    data = minimal()
    data["profiles"]["default"]["input"]["validators"][0]["on_fail"] = "shrug"
    with pytest.raises(ConfigurationError, match="on_fail"):
        settings_from_dict(data)


def test_default_profile_must_exist():
    with pytest.raises(ConfigurationError, match="default_profile"):
        settings_from_dict(minimal(runtime={"default_profile": "nope"}))


def test_log_and_continue_requires_explicit_non_critical():
    data = minimal()
    data["profiles"]["default"]["input"]["validators"][0]["on_fail"] = "log_and_continue"
    with pytest.raises(ConfigurationError, match="critical: false"):
        settings_from_dict(data)
    data["profiles"]["default"]["input"]["validators"][0]["critical"] = False
    assert settings_from_dict(data)


def test_production_rejects_content_logging():
    with pytest.raises(ConfigurationError, match="log_content"):
        settings_from_dict(
            minimal(app={"environment": "production"}, runtime={"log_content": True})
        )


def test_non_loopback_host_requires_auth():
    with pytest.raises(ConfigurationError, match="auth_enabled"):
        settings_from_dict(minimal(api={"host": "0.0.0.0"}))
    assert settings_from_dict(minimal(api={"host": "0.0.0.0", "auth_enabled": True}))


def test_env_substitution_with_value_and_default(tmp_path):
    path = write(
        tmp_path,
        "c.yaml",
        "app:\n  name: ${APP_NAME}\n  log_level: ${LEVEL:-WARNING}\nprofiles:\n  default: {}\n",
    )
    settings = load_config(path, env={"APP_NAME": "svc"})
    assert settings.app.name == "svc"
    assert settings.app.log_level == "WARNING"


def test_missing_env_variable_is_an_error(tmp_path):
    path = write(tmp_path, "c.yaml", "app:\n  name: ${NOPE}\nprofiles:\n  default: {}\n")
    with pytest.raises(ConfigurationError, match="NOPE"):
        load_config(path, env={})


def test_error_message_does_not_echo_input_values(tmp_path):
    text = "runtime:\n  validation_timeout_seconds: 'hunter2'\nprofiles:\n  default: {}\n"
    path = write(tmp_path, "c.yaml", text)
    with pytest.raises(ConfigurationError) as info:
        load_config(path, env={})
    assert "hunter2" not in str(info.value)


def test_later_files_override_earlier_ones(tmp_path):
    base = write(tmp_path, "base.yaml", "app:\n  log_level: INFO\nprofiles:\n  default: {}\n")
    over = write(tmp_path, "over.yaml", "app:\n  log_level: DEBUG\n")
    settings = load_config(base, over, env={})
    assert settings.app.log_level == "DEBUG"
    assert "default" in settings.profiles


def test_invalid_yaml_and_missing_file_are_configuration_errors(tmp_path):
    bad = write(tmp_path, "bad.yaml", "a: [unclosed")
    with pytest.raises(ConfigurationError, match="not valid YAML"):
        load_config(bad, env={})
    with pytest.raises(ConfigurationError, match="Cannot read"):
        load_config(tmp_path / "missing.yaml", env={})


def test_top_level_must_be_mapping(tmp_path):
    path = write(tmp_path, "list.yaml", "- a\n- b\n")
    with pytest.raises(ConfigurationError, match="mapping"):
        load_config(path, env={})
