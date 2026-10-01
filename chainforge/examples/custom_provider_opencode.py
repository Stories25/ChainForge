"""
    A custom model provider for OpenCode Zen (https://opencode.ai/zen),
    OpenCode's curated gateway of coding-agent models.

    OpenCode has no Python SDK on PyPI; its Zen gateway exposes an
    OpenAI-compatible chat completions endpoint at
    https://opencode.ai/zen/v1/chat/completions, authenticated with
    OPENCODE_API_KEY. So the backbone here is the `openai` SDK pointed at
    the Zen base URL.

    Requirements:
      - `openai` package installed (already a ChainForge dependency)
      - OPENCODE_API_KEY set in your environment or in a local .env file
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

# Zen base URL (OpenAI-compatible). All models below use /chat/completions.
ZEN_BASE_URL = "https://opencode.ai/zen/v1"

# Curated Zen models served through the OpenAI-compatible endpoint.
# See https://opencode.ai/docs/zen/ for the full list, pricing, and
# models served on other endpoints (/v1/messages, /v1/responses).
ZEN_MODELS = [
    "gpt-5.5",
    "gpt-5.4-mini",
    "gpt-5-nano",
    "grok-4.7",
    "grok-build-0.1",
    "kimi-k3",
    "kimi-k2.7-code",
    "kimi-k2.5",
    "glm-5.3",
    "glm-5.3-flash",
    "glm-5",
    "deepseek-v4-pro",
    "deepseek-v4-flash",
    "minimax-m3",
    "minimax-m2.5",
    "qwen3.8-max",
    "big-pickle",       # free stealth model
    "space-bunny-free", # free stealth model
    "mimo-v2.6-flash-free",
    "nemotron-3-ultra-free",
]


def _client() -> OpenAI:
    api_key = os.environ.get("OPENCODE_API_KEY")
    if not api_key:
        raise Exception(
            "OPENCODE_API_KEY is not set. Get a key at https://opencode.ai/zen "
            "and add it to your environment or a .env file."
        )
    return OpenAI(api_key=api_key, base_url=ZEN_BASE_URL)


# JSON schemas to pass react-jsonschema-form: settings + UI spec.
OPENCODE_SETTINGS_SCHEMA = {
    "settings": {
        "temperature": {
            "type": "number",
            "title": "temperature",
            "description": "Controls the 'creativity' or randomness of the response.",
            "default": 0.7,
            "minimum": 0,
            "maximum": 2.0,
            "multipleOf": 0.01,
        },
        "max_tokens": {
            "type": "integer",
            "title": "max_tokens",
            "description": "Maximum number of tokens to generate in the response.",
            "default": 4096,
            "minimum": 1,
            "maximum": 65536,
        },
        "reasoning_effort": {
            "type": "string",
            "title": "reasoning_effort",
            "description": "How much thinking the model should do before answering. Ignored by models that don't support it.",
            "default": "medium",
            "enum": ["low", "medium", "high"],
        },
        "system_msg": {
            "type": "string",
            "title": "system_msg",
            "description": "System message sent ahead of the user prompt. Overridden at run time by a {system_prompt} template variable, when connected.",
            "default": "",
            "allow_empty_str": True,
        },
    },
    "ui": {
        "temperature": {
            "ui:help": "Defaults to 0.7.",
            "ui:widget": "range",
        },
        "max_tokens": {
            "ui:widget": "range",
        },
        "reasoning_effort": {
            "ui:help": "low / medium / high. Defaults to medium.",
        },
        "system_msg": {
            "ui:widget": "textarea",
        },
    },
}


@provider(name="OpenCode Zen",
          emoji="⛏",
          category="model",
          models=ZEN_MODELS,
          rate_limit=60,
          settings_schema=OPENCODE_SETTINGS_SCHEMA)
def OpenCodeZenCompletion(
    prompt: str,
    model: Optional[str] = None,
    chat_history: Optional[list] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    reasoning_effort: str = "medium",
    system_msg: str = "",
    **kwargs,
) -> str:
    """Call an OpenCode Zen model through the OpenAI-compatible gateway."""
    client = _client()

    messages = list(chat_history) if chat_history else []
    # Settings-defined system message; a connected {system_prompt} template var
    # overrides this at run time (the front-end passes it via the same kwarg).
    if system_msg:
        messages = [{"role": "system", "content": system_msg}] + messages
    messages.append({"role": "user", "content": prompt})

    request_kwargs = dict(
        model=model or ZEN_MODELS[0],
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if reasoning_effort in ("low", "medium", "high"):
        request_kwargs["reasoning_effort"] = reasoning_effort

    response = client.chat.completions.create(**request_kwargs, **kwargs)
    return response.choices[0].message.content or ""
