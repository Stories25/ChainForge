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

# Full Zen catalogue, grouped by upstream provider category.
# Per-row: (model id, display name, category, $in/1M, $out/1M, cached-read/1M, cached-write/1M, flag)
# Prices are the base (short-context) tier rates from https://opencode.ai/docs/zen/;
# "Free" marks limited-time free models; None = not offered by that model.
ZEN_CATALOG = [
    ("gpt-6-astra", "GPT 6 Astra", "openai", 10, 50, 1.00, 12.50, None),
    ("gpt-6-sol", "GPT 6 Sol", "openai", 2, 10, 0.20, 2.50, None),
    ("gpt-6.1-sol", "GPT 6.1 Sol", "openai", 2, 10, 0.10, 2.50, None),
    ("gpt-6-luna", "GPT 6 Luna", "openai", 0.10, 0.50, 0.01, 0.125, None),
    ("gpt-5.6-sol", "GPT 5.6 Sol", "openai", 4, 20, 0.40, 5, None),
    ("gpt-5.6-terra", "GPT 5.6 Terra", "openai", 2, 12, 0.20, 2.50, None),
    ("gpt-5.6-luna", "GPT 5.6 Luna", "openai", 0.20, 1.20, 0.02, 0.25, None),
    ("gpt-5.5", "GPT 5.5", "openai", 5, 30, 0.50, None, None),
    ("gpt-5.5-pro", "GPT 5.5 Pro", "openai", 30, 180, 30, None, None),
    ("gpt-5.4", "GPT 5.4", "openai", 2.50, 15, 0.25, None, None),
    ("gpt-5.4-pro", "GPT 5.4 Pro", "openai", 30, 180, 30, None, None),
    ("gpt-5.4-mini", "GPT 5.4 Mini", "openai", 0.75, 4.50, 0.075, None, None),
    ("gpt-5.4-nano", "GPT 5.4 Nano", "openai", 0.20, 1.25, 0.02, None, None),
    ("gpt-5.3-codex", "GPT 5.3 Codex", "openai", 1.75, 14, 0.175, None, None),
    ("gpt-5.3-codex-spark", "GPT 5.3 Codex Spark", "openai", 1.75, 14, 0.175, None, None),
    ("gpt-5.2", "GPT 5.2", "openai", 1.75, 14, 0.175, None, "DEPRECATED"),
    ("gpt-5.2-codex", "GPT 5.2 Codex", "openai", 1.75, 14, 0.175, None, "DEPRECATED"),
    ("gpt-5.1", "GPT 5.1", "openai", 1.07, 8.50, 0.107, None, "DEPRECATED"),
    ("gpt-5.1-codex", "GPT 5.1 Codex", "openai", 1.07, 8.50, 0.107, None, "DEPRECATED"),
    ("gpt-5.1-codex-max", "GPT 5.1 Codex Max", "openai", 1.25, 10, 0.125, None, "DEPRECATED"),
    ("gpt-5.1-codex-mini", "GPT 5.1 Codex Mini", "openai", 0.25, 2.00, 0.025, None, "DEPRECATED"),
    ("gpt-5", "GPT 5", "openai", 1.07, 8.50, 0.107, None, None),
    ("gpt-5-codex", "GPT 5 Codex", "openai", 1.07, 8.50, 0.107, None, "DEPRECATED"),
    ("gpt-5-nano", "GPT 5 Nano", "openai", 0.05, 0.40, 0.005, None, None),
    ("claude-fable-5-1", "Claude Fable 5.1", "anthropic", 10, 50, 0.25, 12.50, None),
    ("claude-fable-5", "Claude Fable 5", "anthropic", 10, 50, 1.00, 12.50, None),
    ("claude-opus-5-5", "Claude Opus 5.5", "anthropic", 4, 20, 0.20, 5, None),
    ("claude-opus-5", "Claude Opus 5", "anthropic", 5, 25, 0.50, 6.25, None),
    ("claude-opus-4-8", "Claude Opus 4.8", "anthropic", 5, 25, 0.50, 6.25, None),
    ("claude-opus-4-7", "Claude Opus 4.7", "anthropic", 5, 25, 0.50, 6.25, None),
    ("claude-opus-4-6", "Claude Opus 4.6", "anthropic", 5, 25, 0.50, 6.25, None),
    ("claude-opus-4-5", "Claude Opus 4.5", "anthropic", 5, 25, 0.50, 6.25, None),
    ("claude-sonnet-5", "Claude Sonnet 5", "anthropic", 2, 10, 0.20, 2.50, None),
    ("claude-sonnet-4-6", "Claude Sonnet 4.6", "anthropic", 3, 15, 0.30, 3.75, None),
    ("claude-sonnet-4-5", "Claude Sonnet 4.5", "anthropic", 3, 15, 0.30, 3.75, None),
    ("claude-haiku-4-5", "Claude Haiku 4.5", "anthropic", 1, 5, 0.10, 1.25, None),
    ("gemini-3.8-flash", "Gemini 3.8 Flash", "google", 1.50, 7.50, 0.15, None, None),
    ("gemini-3.7-flash", "Gemini 3.7 Flash", "google", 1.50, 7.50, 0.15, None, None),
    ("gemini-3.6-flash", "Gemini 3.6 Flash", "google", 1.50, 7.50, 0.15, None, None),
    ("gemini-3.5-flash", "Gemini 3.5 Flash", "google", 1.50, 9.00, 0.15, None, None),
    ("gemini-3.5-flash-lite", "Gemini 3.5 Flash Lite", "google", 0.30, 2.50, 0.03, None, None),
    ("gemini-3.1-pro", "Gemini 3.1 Pro", "google", 2, 12, 0.20, None, None),
    ("gemini-3-flash", "Gemini 3 Flash", "google", 0.50, 3.00, 0.05, None, None),
    ("grok-4.7", "Grok 4.7", "xai", 2, 6, 0.50, None, None),
    ("grok-4.6", "Grok 4.6", "xai", 2, 6, 0.50, None, None),
    ("grok-4.5", "Grok 4.5", "xai", 2, 6, 0.30, None, None),
    ("grok-build-0.1", "Grok Build 0.1", "xai", 1, 2, 0.20, None, None),
    ("muse-spark-1.3", "Muse Spark 1.3", "muse", 1.25, 4.25, 0.15, None, None),
    ("muse-spark-1.2", "Muse Spark 1.2", "muse", 1.25, 4.25, 0.15, None, None),
    ("muse-spark-1.3-contributor-free", "Muse Spark 1.3 Contributor Free", "free", "Free", "Free", "Free", None, "FREE"),
    ("qwen3.8-max", "Qwen3.8 Max", "alibaba", 2, 6, 0.25, 2.50, None),
    ("qwen3.8-flash", "Qwen3.8 Flash", "alibaba", 0.15, 0.47, 0.016, 0.20, None),
    ("qwen3.7-max", "Qwen3.7 Max", "alibaba", 2.50, 7.50, 0.50, 3.125, None),
    ("qwen3.7-plus", "Qwen3.7 Plus", "alibaba", 0.40, 1.60, 0.04, 0.50, None),
    ("qwen3.6-plus", "Qwen3.6 Plus", "alibaba", 0.50, 3.00, 0.05, 0.625, None),
    ("qwen3.5-plus", "Qwen3.5 Plus", "alibaba", 0.20, 1.20, 0.02, 0.25, None),
    ("deepseek-v4.1-flash", "DeepSeek V4.1 Flash", "deepseek", 0.30, 1.20, 0.006, None, None),
    ("deepseek-v4-pro", "DeepSeek V4 Pro", "deepseek", 1.74, 3.48, 0.145, None, None),
    ("deepseek-v4-flash", "DeepSeek V4 Flash", "deepseek", 0.14, 0.28, 0.028, None, None),
    ("deepseek-v4-flash-vision-exp", "DeepSeek V4 Flash Vision Exp", "deepseek", 0.14, 0.28, 0.028, None, None),
    ("minimax-m3", "MiniMax M3", "minimax", 0.30, 1.20, 0.06, None, None),
    ("minimax-m2.7", "MiniMax M2.7", "minimax", 0.30, 1.20, 0.06, None, None),
    ("minimax-m2.5", "MiniMax M2.5", "minimax", 0.30, 1.20, 0.06, None, None),
    ("glm-5.3-flash", "GLM 5.3 Flash", "zhipu", 0.15, 0.50, 0.03, None, None),
    ("glm-5.3", "GLM 5.3", "zhipu", 1.40, 4.40, 0.26, None, None),
    ("glm-5.2", "GLM 5.2", "zhipu", 1.40, 4.40, 0.26, None, None),
    ("glm-5.1", "GLM 5.1", "zhipu", 1.40, 4.40, 0.26, None, None),
    ("glm-5", "GLM 5", "zhipu", 1.00, 3.20, 0.20, None, None),
    ("kimi-k3", "Kimi K3", "moonshot", 3, 15, 0.30, None, None),
    ("kimi-k2.7-code", "Kimi K2.7 Code", "moonshot", 0.95, 4.00, 0.19, None, None),
    ("kimi-k2.6", "Kimi K2.6", "moonshot", 0.95, 4.00, 0.16, None, None),
    ("kimi-k2.5", "Kimi K2.5", "moonshot", 0.60, 3.00, 0.10, None, None),
    ("jev-1.13", "Jev 1.13", "typesafe", 0.042, "Free", None, None, None),
    ("jev-1.13-free", "Jev 1.13 Free", "free", "Free", "Free", None, None, "FREE"),
    ("big-pickle", "Big Pickle", "free", "Free", "Free", "Free", None, "FREE"),
    ("space-bunny-free", "Space Bunny Free", "free", "Free", "Free", "Free", None, "FREE"),
    ("longcat-2.5-preview-free", "LongCat 2.5 Preview Free", "free", "Free", "Free", "Free", None, "FREE"),
    ("mimo-v2.6-flash-free", "MiMo-V2.6-Flash Free", "free", "Free", "Free", "Free", None, "FREE"),
    ("mimo-v2.5-free", "MiMo-V2.5 Free", "free", "Free", "Free", "Free", None, "FREE"),
    ("ling-3.0-flash-fin-free", "Ling 3.0 Flash Fin Free", "free", "Free", "Free", "Free", None, "FREE"),
    ("nemotron-3-ultra-free", "Nemotron 3 Ultra Free", "free", "Free", "Free", "Free", None, "FREE"),
    ("nemotron-3.5-lightning-free", "Nemotron 3.5 Lightning Free", "free", "Free", "Free", "Free", None, "FREE"),
]

# Display labels for each upstream provider category.
CATEGORY_LABELS = {
    "openai": "OpenAI (GPT)",
    "anthropic": "Anthropic (Claude)",
    "google": "Google (Gemini)",
    "xai": "xAI (Grok)",
    "muse": "Muse",
    "alibaba": "Alibaba (Qwen)",
    "deepseek": "DeepSeek",
    "minimax": "MiniMax",
    "zhipu": "Zhipu (GLM)",
    "moonshot": "Moonshot (Kimi)",
    "typesafe": "TypeSafe (Jev / System One)",
    "free": "Free / Stealth",
}


def _fmt_price(v) -> str:
    """Formats a per-1M-token price like the Zen docs do."""
    if v is None:
        return "\u2014"
    if isinstance(v, str):
        return v  # "Free"
    return f"${v:.2f}" if v >= 0.1 else f"${v:.3f}"


# Flat list of model IDs, in catalogue order. This is what gets registered
# with the @provider decorator and sent as the `model` param to the API.
ZEN_MODELS = [row[0] for row in ZEN_CATALOG]


def _zen_picker_ui() -> dict:
    """Builds the ui:options payload for the settings modal's model picker:
    a provider-category dropdown that filters a priced model dropdown.
    Rendered by the `zenModelPicker` custom widget in ModelSettingsModal."""
    categories = []
    seen = []
    for (mid, name, cat, pin, pout, *_rest) in ZEN_CATALOG:
        if cat not in seen:
            seen.append(cat)
            categories.append({"id": cat, "label": CATEGORY_LABELS[cat], "models": []})
        entry = next(c for c in categories if c["id"] == cat)
        flag = next((r[7] for r in ZEN_CATALOG if r[0] == mid), None)
        if pin == "Free" and pout == "Free":
            price = "Free"
        else:
            price = f"{_fmt_price(pin)} in / {_fmt_price(pout)} out per 1M tokens"
        entry["models"].append({
            "id": mid,
            "label": name,
            "price": price,
            "flag": flag,
        })
    return {"ui:widget": "zenModelPicker", "ui:options": {"categories": categories}}


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
        # The model field is rendered by a custom widget in the settings modal:
        # a provider-category dropdown that filters a priced model dropdown.
        "model": _zen_picker_ui(),
    },
    # Tells the settings modal which env var / .env key holds the API key,
    # so it can warn when the key is missing (and disable submit).
    "api_key_env": "OPENCODE_API_KEY",
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
