"""
    A custom model provider for Echo (https://echo.fulcrum.inc/dev/),
    an OpenAI-compatible chat gateway.

    Echo exposes an OpenAI-compatible API at
    https://echo.fulcrum.inc/api/v1/chat/completions, authenticated with
    ECHO_API_KEY. So the backbone here is the `openai` SDK pointed at the
    Echo base URL.

    Echo specifics (verified against the live API):
      - The gateway currently serves a single model, "echo".
      - Every request must carry a `persona`: the name of the writer Echo
        writes as (e.g. "Emily Dickinson").
      - Echo sets its own system prompt; requests may NOT include a system
        message. Use the `persona` setting to steer it instead.

    Requirements:
      - `openai` package installed (already a ChainForge dependency)
      - ECHO_API_KEY set in your environment or in a local .env file
        (e.g. project root). .env is gitignored.
"""
import os
from pathlib import Path
from typing import Optional

from chainforge.providers import provider
from openai import OpenAI


def _load_env_file() -> None:
    """Minimal .env loader (no python-dotenv dependency).
    Looks for a .env next to this project root or the current directory."""
    for candidate in (Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"):
        if not candidate.is_file():
            continue
        for line in candidate.read_text(encoding="utf8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())
        break


_load_env_file()

# Echo base URL (OpenAI-compatible). NOTE: the /dev/ path serves the web
# portal; the API lives under /api/v1.
ECHO_BASE_URL = "https://echo.fulcrum.inc/api/v1"

ECHO_MODELS = ["echo"]


@provider(
    name="Echo",
    emoji="📣",
    model=ECHO_MODELS,
    rate_limit=60,  # requests per minute, across all users & API keys
    settings_schema={
        "settings": {
            # Echo requires a persona on every request; default to its own
            # docs' example so calls work out of the box.
            "persona": {
                "title": "Persona",
                "description": "The writer Echo writes as (required by the Echo API).",
                "type": "string",
                "default": "Emily Dickinson",
                "ui": {"widget": "textfield"},
            },
            "temperature": {
                "title": "Temperature",
                "description": "Higher values give more creative, less predictable responses.",
                "type": "number",
                "minimum": 0,
                "maximum": 2,
                "default": 1.0,
            },
            "max_tokens": {
                "title": "Max tokens",
                "description": "Upper limit on the tokens generated in the response.",
                "type": "integer",
                "minimum": 1,
                "maximum": 65536,
                "default": 4096,
            },
        },
        "ui": {
            # Echo rejects system messages: it sets its own system prompt.
            "system_msg": {"ui:widget": "hidden"},
            "persona": {"ui:help": 'Required by Echo, e.g. "Emily Dickinson" — names the writer Echo writes as.'},
            "temperature": {"ui:widget": "range"},
            "max_tokens": {"ui:widget": "range"},
        },
    },
)
def EchoCompletion(
    prompt: str,
    model: str,
    persona: str = "Emily Dickinson",
    temperature: Optional[float] = 1.0,
    max_tokens: Optional[int] = 4096,
    **kwargs,
) -> str:
    """
    Generates a response from the Echo gateway.

    Args:
        prompt: The prompt to send to the model.
        model: The model to use (currently only "echo").
        persona: The writer Echo writes as (required by the API).
        temperature: Sampling temperature (0-2).
        max_tokens: Maximum number of tokens to generate.

    Returns:
        The generated response as a string.
    """
    api_key = os.environ.get("ECHO_API_KEY")
    if not api_key:
        raise RuntimeError(
            "No API key found for Echo. "
            "Set ECHO_API_KEY in your environment or in a local .env file."
        )

    client = OpenAI(api_key=api_key, base_url=ECHO_BASE_URL)

    # `persona` is not a standard OpenAI parameter, so pass it via extra_body.
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body={"persona": persona},
    )

    response = resp.choices[0].message.content
    if response is None:
        raise RuntimeError("Echo API response object returned an empty response.")
    return response
