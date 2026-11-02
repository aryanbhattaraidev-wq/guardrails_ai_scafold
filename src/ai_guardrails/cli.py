"""Command-line interface: config checks, local validation, and serving.

Uses the same config loader and ``GuardrailsService`` as the Python API and the
HTTP server, so all three behave identically.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from ai_guardrails.config import Settings, load_config
from ai_guardrails.core.exceptions import GuardrailsError
from ai_guardrails.core.service import GuardrailsService
from ai_guardrails.core.types import ValidationStage
from ai_guardrails.observability.logging import configure_logging

app = typer.Typer(help="Provider-agnostic guardrails for AI applications.", no_args_is_help=True)

DEFAULT_CONFIG = [Path("configs/default.yaml")]

ConfigOption = Annotated[
    list[Path],
    typer.Option(
        "--config",
        "-c",
        help="YAML config file. Repeat to layer overrides (later files win).",
    ),
]


@app.callback()
def _main() -> None:
    """Keep the CLI in subcommand mode."""


def _fail(message: str) -> typer.Exit:
    typer.echo(f"error: {message}", err=True)
    return typer.Exit(code=1)


def _load(config: list[Path]) -> Settings:
    try:
        return load_config(*config)
    except GuardrailsError as exc:
        raise _fail(str(exc)) from exc


def _build(settings: Settings) -> GuardrailsService:
    try:
        return GuardrailsService.from_config(settings)
    except GuardrailsError as exc:
        raise _fail(str(exc)) from exc


@app.command("config-check")
def config_check(config: ConfigOption = DEFAULT_CONFIG) -> None:
    """Validate config files, then build every guard to prove validators are installed."""
    settings = _load(config)
    service = _build(settings)
    typer.echo(f"OK: {len(settings.profiles)} profile(s): {', '.join(service.profile_names)}")


@app.command()
def validate(
    stage: Annotated[ValidationStage, typer.Option(help="Pipeline stage to run.")],
    text: Annotated[str, typer.Option(help="Text to validate, or '-' to read stdin.")],
    profile: Annotated[
        str | None, typer.Option(help="Profile name (default: config default).")
    ] = None,
    config: ConfigOption = DEFAULT_CONFIG,
    show_content: Annotated[
        bool,
        typer.Option(
            "--show-content",
            help="Print the validated text. Off by default because text may contain PII.",
        ),
    ] = False,
) -> None:
    """Validate text locally. Exit code 0 if allowed, 1 if blocked or errored."""
    service = _build(_load(config))
    payload = sys.stdin.read() if text == "-" else text
    try:
        result = service.validate_sync(stage, payload, profile=profile)
    except GuardrailsError as exc:
        raise _fail(str(exc)) from exc

    output = {
        "status": result.status.value,
        "is_allowed": result.is_allowed,
        "stage": result.stage.value,
        "policy": result.profile,
        "failed_validators": list(result.failed_validators),
        "reason_code": result.reason_code.value if result.reason_code else None,
        "request_id": result.request_id,
        "duration_ms": round(result.duration_ms, 3),
    }
    if show_content:
        output["content"] = result.content
    typer.echo(json.dumps(output, indent=2))
    raise typer.Exit(code=0 if result.is_allowed else 1)


@app.command()
def serve(
    config: ConfigOption = DEFAULT_CONFIG,
    host: Annotated[str | None, typer.Option(help="Override api.host.")] = None,
    port: Annotated[int | None, typer.Option(help="Override api.port.")] = None,
) -> None:
    """Run the HTTP API (needs the `api` settings in your config)."""
    import uvicorn

    from ai_guardrails.config import settings_from_dict
    from ai_guardrails.integrations.fastapi import create_app

    settings = _load(config)
    if host or port:
        # Re-validate so e.g. a non-loopback --host without auth is still rejected.
        data = settings.model_dump(mode="json")
        data["api"].update({k: v for k, v in {"host": host, "port": port}.items() if v})
        try:
            settings = settings_from_dict(data)
        except GuardrailsError as exc:
            raise _fail(str(exc)) from exc
    configure_logging(settings.app.log_level)
    service = _build(settings)
    try:
        api = create_app(service)
    except GuardrailsError as exc:
        raise _fail(str(exc)) from exc
    uvicorn.run(api, host=settings.api.host, port=settings.api.port, log_level="warning")
