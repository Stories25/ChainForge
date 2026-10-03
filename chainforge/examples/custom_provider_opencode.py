"""
    A custom model provider for OpenCode Zen (https://opencode.ai/zen),
    OpenCode's curated gateway of coding-agent models.

    Two transports are available:

      transport="sdk"     (default) calls the models through the official
                          OpenCode JavaScript SDK. The provider starts
                          `chainforge/examples/opencode_bridge.mjs`, which uses
                          `@opencode-ai/sdk` to run `opencode serve` and to
                          drive one session per completion. OpenCode Zen refuses
                          its free models for requests that do not come from a
                          real OpenCode client ("OpenCode's free tier can only
                          be used from within OpenCode"), so the SDK transport is
                          the only way to reach the free tier.

      transport="direct"  calls the Zen HTTP gateway itself, the way the
                          provider did before. It is faster and adds no agent
                          scaffolding, but the gateway rejects every free model
                          with 403 FreeTierError, so use it for paid models only.

    The Zen gateway is not uniformly OpenAI-compatible: each model speaks one
    of several protocols (see https://opencode.ai/docs/zen/):

      - /v1/responses          OpenAI Responses API      (GPT, Grok, Muse)
      - /v1/messages           Anthropic protocol       (Claude, Qwen Plus)
      - /v1/models/<id>:generateContent  Google protocol (Gemini)
      - /v1/chat/completions   OpenAI-compatible chat   (DeepSeek, GLM, Kimi, ...)
      - /v1/systemone          TypeSafe Jev             (not supported here)

    Only the direct transport needs this protocol map; OpenCode itself resolves
    the right endpoint when the SDK transport is used.

    Requirements:
      - `openai` package installed (already a ChainForge dependency), for the
        direct transport
      - Node.js and the OpenCode CLI on PATH, plus `npm install @opencode-ai/sdk`
        in the ChainForge folder, for the SDK transport
      - a Zen API key: `OPENCODE_API_KEY` in your environment or in a local .env
        file (e.g. project root, gitignored), or `opencode auth login`.
        `.env` is read for both transports.
"""
import atexit
import os
import re
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

from chainforge.providers import provider
from openai import BadRequestError, OpenAI

try:
    import requests
except ImportError:  # requests is a ChainForge dependency, but stay defensive.
    requests = None


def _package_dir() -> Path:
    """Directory of the installed `chainforge` package.

    `__file__` cannot be trusted here. ChainForge pre-registers this provider by
    exec'ing its source inside flask_app.py:

        with open(example_path) as f:
            exec(f.read(), globals(), None)

    In that context `__file__` is chainforge/flask_app.py, so
    `Path(__file__).parent` is `chainforge/` and every path derived from it
    loses the `examples/` segment. The package directory is always right,
    whether the file is imported normally or exec'd.
    """
    try:
        import chainforge
        return Path(chainforge.__file__).resolve().parent
    except Exception:
        return Path(__file__).resolve().parent


# .../ChainForge/chainforge -> its parent is .../ChainForge
PROJECT_ROOT = _package_dir().parent
EXAMPLES_DIR = _package_dir() / "examples"


def _load_env_file() -> None:
    """Minimal .env loader (no python-dotenv dependency).
    Looks for a .env in the current directory, then in the project root."""
    for candidate in (Path.cwd() / ".env", PROJECT_ROOT / ".env"):
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

# Zen base URL (OpenAI-compatible). Used by the direct transport only; the SDK
# transport talks to the local bridge.
ZEN_BASE_URL = "https://opencode.ai/zen/v1"

# The bridge that fronts the OpenCode SDK. It spawns `opencode serve`. It sits
# next to this file in the examples folder of the package.
BRIDGE_SCRIPT = EXAMPLES_DIR / "opencode_bridge.mjs"
BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = int(os.environ.get("OPENCODE_BRIDGE_PORT", "8765"))
BRIDGE_URL = f"http://{BRIDGE_HOST}:{BRIDGE_PORT}"
# `opencode serve` port, owned by the bridge's OpenCode SDK child process.
SERVER_PORT = int(os.environ.get("OPENCODE_SERVER_PORT", "4096"))

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

# Flat list of model IDs, in catalogue order. This is what gets registered
# with the @provider decorator and sent as the `model` param to the API.
ZEN_MODELS = [row[0] for row in ZEN_CATALOG]

# Models whose text is safe for the direct (non-agent) transport as well.
# Everything marked FREE is rejected by the gateway on the direct transport, and
# jev-* speaks the /systemone protocol, which this provider cannot call at all.
FREE_MODELS = {row[0] for row in ZEN_CATALOG if row[7] == "FREE"}

# Which gateway protocol each model speaks. Derived from the 'Endpoint'
# column of https://opencode.ai/docs/zen/. Calling a model over the wrong
# protocol returns 400 ModelProtocolUnsupported. Direct transport only.
ZEN_PROTOCOLS = {
    "responses": [
        "gpt-6-astra", "gpt-6-sol", "gpt-6.1-sol", "gpt-6-luna",
        "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna",
        "gpt-5.5", "gpt-5.5-pro", "gpt-5.4", "gpt-5.4-pro",
        "gpt-5.4-mini", "gpt-5.4-nano", "gpt-5.3-codex", "gpt-5.3-codex-spark",
        "gpt-5.2", "gpt-5.2-codex", "gpt-5.1", "gpt-5.1-codex",
        "gpt-5.1-codex-max", "gpt-5.1-codex-mini", "gpt-5", "gpt-5-codex",
        "gpt-5-nano", "grok-4.7", "grok-4.6", "grok-4.5", "grok-build-0.1",
        "muse-spark-1.3", "muse-spark-1.2", "muse-spark-1.3-contributor-free",
    ],
    "messages": [
        "claude-fable-5-1", "claude-fable-5", "claude-opus-5-5", "claude-opus-5",
        "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6", "claude-opus-4-5",
        "claude-sonnet-5", "claude-sonnet-4-6", "claude-sonnet-4-5", "claude-haiku-4-5",
        "qwen3.8-flash", "qwen3.7-max", "qwen3.7-plus", "qwen3.6-plus", "qwen3.5-plus",
    ],
    "google": [
        "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash",
        "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-pro", "gemini-3-flash",
    ],
    "chat": [
        "qwen3.8-max", "deepseek-v4.1-flash", "deepseek-v4-pro", "deepseek-v4-flash",
        "deepseek-v4-flash-vision-exp", "minimax-m3", "minimax-m2.7", "minimax-m2.5",
        "glm-5.3-flash", "glm-5.3", "glm-5.2", "glm-5.1", "glm-5",
        "kimi-k3", "kimi-k2.7-code", "kimi-k2.6", "kimi-k2.5",
        "big-pickle", "space-bunny-free", "longcat-2.5-preview-free",
        "mimo-v2.6-flash-free", "mimo-v2.5-free", "ling-3.0-flash-fin-free",
        "nemotron-3-ultra-free", "nemotron-3.5-lightning-free",
    ],
    "systemone": ["jev-1.13", "jev-1.13-free"],
}
ZEN_MODEL_PROTOCOL = {
    mid: proto for proto, mids in ZEN_PROTOCOLS.items() for mid in mids
}

# JSON schemas to pass react-jsonschema-form: settings + UI spec.
OPENCODE_SETTINGS_SCHEMA = {
    "settings": {
        "transport": {
            "type": "string",
            "title": "transport",
            "description": "How to reach the model. 'sdk' drives the official OpenCode SDK (a local bridge runs 'opencode serve'); it is the only transport that the Zen free tier accepts. 'direct' calls the Zen HTTP gateway itself: faster and free of agent scaffolding, but the gateway answers 403 FreeTierError for every free model.",
            "default": "sdk",
            "enum": ["sdk", "direct"],
        },
        "temperature": {
            "type": "number",
            "title": "temperature",
            "description": "Controls the 'creativity' or randomness of the response. With the sdk transport the bridge snaps this to the nearest step of 0, 0.2, 0.4, 0.7, 1.0 or 1.5, because the OpenCode session API takes no sampling parameters.",
            "default": 0.7,
            "minimum": 0,
            "maximum": 2.0,
            "multipleOf": 0.01,
        },
        "max_tokens": {
            "type": "integer",
            "title": "max_tokens",
            "description": "Maximum number of tokens to generate in the response. Used by the direct transport; OpenCode decides the limit itself on the sdk transport.",
            "default": 4096,
            "minimum": 1,
            "maximum": 65536,
        },
        "reasoning_effort": {
            "type": "string",
            "title": "reasoning_effort",
            "description": "How much thinking the model should do before answering. Low = fastest and cheapest; high = deepest reasoning. Sent through to the Zen gateway on the direct transport; ignored on the sdk transport.",
            "default": "medium",
            "enum": ["low", "medium", "high"],
        },
        "system_msg": {
            "type": "string",
            "title": "system_message",
            "description": "Sent as the system-role message ahead of the user prompt. Leave empty to send no system message. Overridden at run time when a {system_prompt} template variable is connected to the node.",
            "default": "",
            "allow_empty_str": True,
        },
    },
    "ui": {
        # Field order matches the mock dialogue:
        # model -> transport -> system_message -> reasoning_effort -> temperature
        # -> max_tokens -> shortname.
        "ui:order": ["model", "transport", "system_msg", "reasoning_effort",
                     "temperature", "max_tokens", "shortname"],
        "transport": {
            "ui:help": "sdk = through the OpenCode SDK (needed for free models). direct = straight to the Zen gateway (paid models only).",
            "ui:widget": "select",
        },
        "temperature": {
            "ui:help": "Defaults to 0.7.",
            "ui:widget": "range",
        },
        "max_tokens": {
            "ui:help": "Range 1-65536.",
            "ui:widget": "range",
        },
        "reasoning_effort": {
            "ui:help": "Defaults to medium.",
        },
        "system_msg": {
            "ui:widget": "textarea",
        },
        # The model field is a searchable dropdown of the full Zen catalogue,
        # each option labelled with its per-1M-token pricing.
        "model": {
            "ui:widget": "zenModel",
            "ui:help": "Prices shown are per 1M tokens (input/output). The gateway protocol for each model is handled automatically.",
        },
    },
    # Tells the settings modal which env var / .env key holds the API key,
    # so it can warn when the key is missing (and disable submit).
    "api_key_env": "OPENCODE_API_KEY",
    # Fixed gateway endpoint, shown (disabled) in the settings modal when the
    # key is missing.
    "base_url": ZEN_BASE_URL,
}


# ---------------------------------------------------------------------------
# SDK transport: the local bridge in front of `opencode serve`
# ---------------------------------------------------------------------------

_bridge_lock = threading.Lock()
_bridge_process = None


def _bridge_healthy(timeout: float = 2.0) -> bool:
    """True when the bridge already answers /health."""
    try:
        if requests is None:
            return False
        response = requests.get(f"{BRIDGE_URL}/health", timeout=timeout)
        return response.status_code == 200 and response.json().get("ok") is True
    except Exception:
        return False


def _port_in_use(port: int) -> bool:
    """True when something is already listening on the port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((BRIDGE_HOST, port)) == 0


def _bridge_pid_file() -> Path:
    return Path(os.environ.get("TEMP", ".")) / f"chainforge-opencode-bridge-{BRIDGE_PORT}.pid"


def _stop_stale_bridge() -> None:
    """Terminate a bridge from an earlier run that is stuck on the port.

    The bridge writes its pid next to its log, so this only ever targets a
    bridge ChainForge started itself.
    """
    pid_file = _bridge_pid_file()
    try:
        pid = int(pid_file.read_text(encoding="utf8").strip())
    except Exception:
        return
    if pid == os.getpid():
        return
    for sig in (signal.SIGTERM, signal.SIGKILL if hasattr(signal, "SIGKILL") else signal.SIGTERM):
        try:
            os.kill(pid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            break
        deadline = time.time() + 5
        while time.time() < deadline and _port_in_use(BRIDGE_PORT):
            time.sleep(0.25)
        if not _port_in_use(BRIDGE_PORT):
            break
    try:
        pid_file.unlink()
    except OSError:
        pass


def _stop_bridge() -> None:
    global _bridge_process
    if _bridge_process is not None and _bridge_process.poll() is None:
        _bridge_process.terminate()
    _bridge_process = None


def ensure_bridge(wait_seconds: float = 90.0) -> None:
    """Start the OpenCode SDK bridge if it is not already running.

    The bridge is a long-lived process: it owns one `opencode serve` child and
    keeps OpenCode's session identity warm, which the Zen free tier requires.
    """
    global _bridge_process
    with _bridge_lock:
        if _bridge_healthy():
            return

        if not BRIDGE_SCRIPT.is_file():
            raise Exception(
                f"The OpenCode SDK bridge script is missing: {BRIDGE_SCRIPT}. "
                "Reinstall ChainForge or set transport to 'direct' for paid models."
            )
        # A bridge left over from an earlier run can hold the bridge port. The
        # opencode server port is left alone on purpose: the bridge attaches to
        # a server that is already running there.
        if _port_in_use(BRIDGE_PORT):
            _stop_bridge()
            _stop_stale_bridge()

        env = dict(os.environ)
        env.setdefault("OPENCODE_BRIDGE_PORT", str(BRIDGE_PORT))
        if os.environ.get("CHAINFORGE_OPENCODE_BRIDGE_LOG"):
            log_path = Path(os.environ["CHAINFORGE_OPENCODE_BRIDGE_LOG"])
        else:
            log_path = Path(os.environ.get("TEMP", ".")) / "chainforge-opencode-bridge.log"
        _stop_bridge()
        log_handle = open(log_path, "w", encoding="utf8")
        _bridge_process = subprocess.Popen(
            ["node", str(BRIDGE_SCRIPT)],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=str(BRIDGE_SCRIPT.parent),
            # New process group, so the child `opencode serve` dies with us.
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        atexit.register(_stop_bridge)

        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            if _bridge_process.poll() is not None:
                tail = ""
                try:
                    tail = log_path.read_text(encoding="utf8")[-800:]
                except Exception:
                    pass
                raise Exception(
                    "The OpenCode SDK bridge stopped while starting. Bridge log "
                    f"({log_path}):\n{tail}"
                )
            if _bridge_healthy():
                return
            time.sleep(1.0)
        raise Exception(
            f"The OpenCode SDK bridge did not become ready within {wait_seconds:.0f}s. "
            f"Bridge log ({log_path}): check that Node.js and the opencode CLI are on PATH."
        )


def _complete_sdk(model: str, messages: list, temperature: float,
                  api_key: Optional[str]) -> str:
    """Run one completion through the OpenCode SDK bridge.

    OpenCode owns the whole request, so it picks the gateway protocol of the
    model and attaches the identity headers that the Zen free tier demands.
    """
    ensure_bridge()
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if api_key:
        payload["api_key"] = api_key
    response = requests.post(f"{BRIDGE_URL}/v1/chat/completions",
                             json=payload, timeout=600)
    if response.status_code >= 400:
        detail = response.text
        try:
            detail = response.json().get("error", {}).get("message", detail)
        except Exception:
            pass
        raise Exception(f"OpenCode SDK bridge error {response.status_code}: {detail}")
    data = response.json()
    choices = data.get("choices") or []
    text = choices[0].get("message", {}).get("content") if choices else None
    if not text:
        raise Exception(
            f"OpenCode SDK bridge returned no text for model '{model}'. "
            "OpenCode Zen decides the free tier per model, not per client: the "
            "same key and the same headers are accepted for some free models "
            "(space-bunny-free) and refused for others (longcat, big-pickle) "
            "with 403 FreeTierError, even when the request comes from the real "
            "opencode CLI. Pick another free model, or a paid one."
        )
    return text


# ---------------------------------------------------------------------------
# Direct transport: the Zen HTTP gateway
# ---------------------------------------------------------------------------


def _client(api_key: Optional[str] = None) -> OpenAI:
    # A key pasted in the settings modal (this session only) wins over the env.
    api_key = api_key or os.environ.get("OPENCODE_API_KEY")
    if not api_key:
        raise Exception(
            "OPENCODE_API_KEY is not set. Get a key at https://opencode.ai/zen "
            "and add it to your environment or a .env file."
        )
    return OpenAI(api_key=api_key, base_url=ZEN_BASE_URL)


def _split_system(messages: list) -> tuple:
    """Split a chat message list into (system_text, non_system_messages)."""
    system_texts = [m["content"] for m in messages if m["role"] == "system"]
    rest = [m for m in messages if m["role"] != "system"]
    return "\n".join(system_texts), rest


# Models on the Responses API that only accept the default reasoning effort
# (OpenAI's "Pro" models). Sending reasoning.effort to them is rejected.
NO_REASONING_EFFORT_MODELS = {"gpt-5.5-pro", "gpt-5.4-pro"}


def _call_with_param_retry(call_fn, request_kwargs: dict):
    """Run an OpenAI SDK call.

    If the gateway rejects the request with 400 code=unsupported_parameter
    naming a request parameter (e.g. 'temperature' or 'reasoning.effort'),
    drop exactly that parameter and retry once. Any other error, and a
    second failure, is re-raised.
    """
    try:
        return call_fn(request_kwargs)
    except BadRequestError as e:
        param = None
        body = getattr(e, "body", None)
        if isinstance(body, dict):
            err = body.get("error") or {}
            param = err.get("param") if isinstance(err, dict) else None
        if not param:
            m = re.search(r"'param'\s*:\s*'([^']+)'", str(e))
            param = m.group(1) if m else None
        # 'reasoning.effort' -> drop the whole 'reasoning' object
        key = "reasoning" if param and param.startswith("reasoning") else param
        if key and key in request_kwargs:
            retry_kwargs = {k: v for k, v in request_kwargs.items() if k != key}
            return call_fn(retry_kwargs)
        raise


def _complete_chat(api_key: str, messages: list, temperature: float,
                   max_tokens: int, reasoning_effort: str, extra_kwargs: dict) -> str:
    """OpenAI-compatible chat completions protocol (/v1/chat/completions).

    Used by DeepSeek, GLM, Kimi, MiniMax, Qwen3.8 Max and the stealth/free
    models. These are standard instruct models: temperature (0-2) and
    max_tokens are supported. reasoning_effort is sent only if the caller's
    extra kwargs are for a model that supports it (the gateway rejects it
    otherwise, in which case it is dropped and retried).
    """
    client = OpenAI(api_key=api_key, base_url=ZEN_BASE_URL)
    request_kwargs = dict(
        model=extra_kwargs.pop("model"),
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        **extra_kwargs,
    )
    if reasoning_effort in ("low", "medium", "high"):
        request_kwargs["reasoning_effort"] = reasoning_effort

    def _call(kw):
        return client.chat.completions.create(**kw)

    response = _call_with_param_retry(_call, request_kwargs)
    return response.choices[0].message.content or ""


def _complete_responses(api_key: str, model: str, messages: list,
                        temperature: float, max_tokens: int,
                        reasoning_effort: str) -> str:
    """OpenAI Responses API protocol (/v1/responses) — GPT, Grok, Muse models.

    All of these are reasoning models, which reject sampling parameters
    outright (400 unsupported_parameter for 'temperature', 'top_p', penalty
    params), so none are sent. reasoning.effort is sent except to the "Pro"
    models, which only accept the default effort.
    """
    client = OpenAI(api_key=api_key, base_url=ZEN_BASE_URL)
    request_kwargs = dict(
        model=model,
        input=messages,
        max_output_tokens=max_tokens,
    )
    if reasoning_effort in ("low", "medium", "high") and \
            model not in NO_REASONING_EFFORT_MODELS:
        request_kwargs["reasoning"] = {"effort": reasoning_effort}

    def _call(kw):
        return client.responses.create(**kw)

    response = _call_with_param_retry(_call, request_kwargs)
    return getattr(response, "output_text", None) or ""


def _complete_messages(api_key: str, model: str, messages: list,
                       temperature: float, max_tokens: int) -> str:
    """Anthropic protocol (/v1/messages) — Claude & Qwen 'Plus' models.

    Anthropic's temperature range is 0-1 (hard error outside it), so the
    ChainForge setting (0-2) is clamped into it. max_tokens is required.
    Extended thinking is not used, so reasoning_effort does not apply.
    """
    system_text, rest = _split_system(messages)
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": rest,
    }
    if system_text:
        payload["system"] = system_text
    if temperature is not None:
        payload["temperature"] = max(0.0, min(1.0, float(temperature)))
    r = requests.post(
        ZEN_BASE_URL + "/messages",
        headers={
            "x-api-key": api_key,
            "authorization": f"Bearer {api_key}",
            "anthropic-version": "2023-06-01",
        },
        json=payload,
        timeout=300,
    )
    if r.status_code >= 400:
        raise Exception(f"Zen gateway error {r.status_code}: {r.text}")
    data = r.json()
    return "".join(
        block.get("text", "") for block in data.get("content", [])
        if isinstance(block, dict) and block.get("type") == "text"
    )


def _complete_google(api_key: str, model: str, messages: list,
                     temperature: float, max_tokens: int) -> str:
    """Google protocol (/v1/models/<id>:generateContent) — Gemini models.

    Gemini supports temperature (0-2, clamped) and maxOutputTokens; the
    system message maps to systemInstruction.
    """
    system_text, rest = _split_system(messages)
    contents = [
        {"role": "model" if m["role"] == "assistant" else "user",
         "parts": [{"text": m["content"]}]}
        for m in rest
    ]
    gen_config = {"maxOutputTokens": max_tokens}
    if temperature is not None:
        gen_config["temperature"] = max(0.0, min(2.0, float(temperature)))
    payload = {"contents": contents, "generationConfig": gen_config}
    if system_text:
        payload["systemInstruction"] = {"parts": [{"text": system_text}]}
    r = requests.post(
        f"{ZEN_BASE_URL}/models/{model}:generateContent",
        headers={
            "x-goog-api-key": api_key,
            "authorization": f"Bearer {api_key}",
        },
        json=payload,
        timeout=300,
    )
    if r.status_code >= 400:
        raise Exception(f"Zen gateway error {r.status_code}: {r.text}")
    data = r.json()
    candidates = data.get("candidates") or [{}]
    parts = ((candidates[0].get("content") or {}).get("parts")) or []
    return "".join(p.get("text", "") for p in parts if isinstance(p, dict))


def _complete_direct(api_key: str, model_id: str, messages: list,
                     temperature: float, max_tokens: int,
                     reasoning_effort: str, extra_kwargs: dict) -> str:
    """Call the Zen gateway over HTTP, routed by the model's protocol."""
    protocol = ZEN_MODEL_PROTOCOL.get(model_id, "chat")
    if protocol == "systemone":
        raise Exception(
            f"Model '{model_id}' uses Zen's /systemone protocol (Jev), "
            "which is not supported by this chat provider."
        )
    if model_id in FREE_MODELS:
        raise Exception(
            f"Model '{model_id}' is a Zen free model. OpenCode Zen admits free "
            "models per model, not per client: the gateway refuses most of them "
            "with 403 FreeTierError even for the real opencode CLI. Set "
            "transport to 'sdk' so the call goes through the OpenCode SDK; if "
            "it still fails, this model is not open to your account."
        )
    if protocol == "chat":
        return _complete_chat(api_key, messages, temperature, max_tokens,
                              reasoning_effort, {"model": model_id, **extra_kwargs})
    if protocol == "responses":
        return _complete_responses(api_key, model_id, messages, temperature,
                                   max_tokens, reasoning_effort)
    if protocol == "messages":
        return _complete_messages(api_key, model_id, messages, temperature,
                                  max_tokens)
    return _complete_google(api_key, model_id, messages, temperature,
                            max_tokens)


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
    transport: str = "sdk",
    temperature: float = 0.7,
    max_tokens: int = 4096,
    reasoning_effort: str = "medium",
    system_msg: str = "",
    **kwargs,
) -> str:
    """Call an OpenCode Zen model over the OpenCode SDK or the Zen gateway."""
    # A key pasted in the settings modal (this session only) wins over the env.
    # Pop it so it never leaks into the API call kwargs below.
    session_api_key = kwargs.pop("api_key", None)
    api_key = session_api_key or os.environ.get("OPENCODE_API_KEY")

    model_id = model or ZEN_MODELS[0]
    transport = (transport or "sdk").lower()

    messages = list(chat_history) if chat_history else []
    # Settings-defined system message; a connected {system_prompt} template var
    # overrides this at run time (the front-end passes it via the same kwarg).
    if system_msg:
        messages = [{"role": "system", "content": system_msg}] + messages
    messages.append({"role": "user", "content": prompt})

    if transport == "direct":
        if not api_key:
            raise Exception(
                "OPENCODE_API_KEY is not set. Get a key at https://opencode.ai/zen "
                "and add it to your environment or a .env file."
            )
        return _complete_direct(api_key, model_id, messages, temperature,
                                max_tokens, reasoning_effort, kwargs)

    if transport != "sdk":
        raise Exception(
            f"Unknown transport '{transport}'. Use 'sdk' or 'direct'."
        )
    return _complete_sdk(model_id, messages, temperature, session_api_key)
