"""Use guardrails inside your own FastAPI app. Run:
    uv run uvicorn examples.fastapi_integration:app --port 8001

Your app owns the model call; guardrails sit before and after it.
"""

from fastapi import FastAPI
from pydantic import BaseModel

from ai_guardrails import GuardrailsService, load_config
from ai_guardrails.integrations import guarded_call

app = FastAPI()
guardrails = GuardrailsService.from_config(load_config("configs/default.yaml"))


class Ask(BaseModel):
    question: str


def call_my_model(prompt: str) -> str:
    return f"(model answer to: {prompt})"  # replace with your provider call


@app.post("/ask")
async def ask(body: Ask) -> dict[str, object]:
    result = await guarded_call(body.question, call_my_model, guardrails=guardrails)
    if not result.is_allowed:
        return {"error": result.reason_code, "message": result.message}
    return {"answer": result.content, "request_id": result.request_id}
