"""Validate input and output in an async app. Run: uv run python examples/basic_async.py"""

import asyncio

from ai_guardrails import GuardrailsService, load_config


async def main() -> None:
    guardrails = GuardrailsService.from_config(load_config("configs/default.yaml"))

    input_result = await guardrails.validate_input("Summarize the Q3 report.")
    if not input_result.is_allowed:
        print("blocked:", input_result.reason_code)
        return

    # The application owns the model call; here it is faked.
    model_text = "Revenue grew. Questions? Call (415) 555-0132."

    output_result = await guardrails.validate_output(model_text)
    if output_result.is_allowed:
        print(output_result.status.value, "->", output_result.content)


asyncio.run(main())
