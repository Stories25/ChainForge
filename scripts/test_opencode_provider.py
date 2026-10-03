"""
    Smoke test for the OpenCode Zen provider.

    Runs a prompt through the provider's two transports and prints the result,
    so the SDK bridge, the free tier and the direct gateway can be checked from
    a terminal:

        python scripts/test_opencode_provider.py
        python scripts/test_opencode_provider.py --model space-bunny-free
        python scripts/test_opencode_provider.py --transport direct --model glm-5.3-flash

    Exits non-zero when every attempt failed.
"""
import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chainforge.examples.custom_provider_opencode import (  # noqa: E402
    BRIDGE_SCRIPT,
    BRIDGE_URL,
    ZEN_MODELS,
    OpenCodeZenCompletion,
)

PROMPT = "What is 1+1? Answer in one short sentence."
SYSTEM = "Respond in ast100 technical simplified english."


def probe_bridge():
    """Report whether the OpenCode SDK bridge is already up."""
    try:
        import requests
        response = requests.get(f"{BRIDGE_URL}/health", timeout=2)
        print(f"bridge: {response.status_code} {response.text.strip()}")
    except Exception as error:
        print(f"bridge: not running ({error.__class__.__name__})")


def run(model: str, transport: str) -> bool:
    started = time.time()
    try:
        answer = OpenCodeZenCompletion(
            prompt=PROMPT,
            model=model,
            transport=transport,
            temperature=0.0,
            max_tokens=256,
            system_msg=SYSTEM,
        )
    except Exception as error:
        print(f"FAIL [{transport}] {model}: {error}")
        return False
    text = " ".join((answer or "").split())
    if not text:
        print(f"FAIL [{transport}] {model}: empty response")
        return False
    print(f"PASS [{transport}] {model} ({time.time() - started:.1f}s)")
    print(f"     {text[:300]}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="space-bunny-free",
                        help="Zen model id (default: space-bunny-free)")
    parser.add_argument("--transport", default="sdk",
                        choices=["sdk", "direct", "both"],
                        help="Which transport to exercise (default: sdk)")
    parser.add_argument("--list", action="store_true",
                        help="Print the model ids and exit")
    args = parser.parse_args()

    if args.list:
        for model_id in ZEN_MODELS:
            print(model_id)
        return 0

    print(f"node:   {os.environ.get('OPENCODE_BRIDGE_PORT', '8765')} port")
    print(f"script: {BRIDGE_SCRIPT} ({'found' if BRIDGE_SCRIPT.is_file() else 'MISSING'})")
    probe_bridge()

    transports = ["sdk", "direct"] if args.transport == "both" else [args.transport]
    results = [run(args.model, transport) for transport in transports]
    if any(results):
        return 0
    print("\nAll attempts failed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
