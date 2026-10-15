from typing import TypeVar

from openai import AzureOpenAI, OpenAIError
from pydantic import BaseModel, ValidationError

from app.config import settings

client = AzureOpenAI(
    api_key=settings.azure_openai_api_key,
    azure_endpoint=settings.azure_openai_endpoint,
    api_version=settings.azure_openai_api_version,
    timeout=settings.llm_timeout_seconds,
)

MODEL = settings.azure_openai_deployment
LIGHT_MODEL = settings.azure_openai_deployment_light

Output = TypeVar("Output", bound=BaseModel)


class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int


class LLMUnavailable(Exception):
    """The language model call failed (rate limit, timeout, outage...)."""


def _usage(response) -> TokenUsage | None:

    if response.usage is None:
        return None

    return TokenUsage(
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        total_tokens=response.usage.total_tokens,
    )


def ask_llm(prompt, max_output_tokens=None, model=MODEL) -> tuple[str, TokenUsage | None]:
    """Free-text answer."""

    try:
        response = client.responses.create(
            model=model,
            input=prompt,
            max_output_tokens=max_output_tokens
        )
    except OpenAIError as e:
        raise LLMUnavailable(str(e)) from e

    return response.output_text.strip(), _usage(response)


def ask_structured(
    prompt, output_type: type[Output], max_output_tokens=None, model=MODEL
) -> tuple[Output | None, TokenUsage | None]:
    """Answer constrained to `output_type`'s JSON schema. The parsed value
    is None when the model refused or its output could not be parsed;
    callers treat that as "fail closed"."""

    try:
        response = client.responses.parse(
            model=model,
            input=prompt,
            text_format=output_type,
            max_output_tokens=max_output_tokens
        )
    except OpenAIError as e:
        raise LLMUnavailable(str(e)) from e
    except ValidationError:
        return None, None

    return response.output_parsed, _usage(response)
