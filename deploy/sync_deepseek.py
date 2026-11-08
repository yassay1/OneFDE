"""Sync one model provider from Windows backend/.env via local stdin."""

import argparse
import io
import json
import subprocess
from pathlib import Path

from dotenv import dotenv_values

PROVIDERS = {
    "deepseek": (
        "https://api.deepseek.com",
        "deepseek-flash",
        "ONEFDE_MODEL_ENGINEERING",
        {"https://api.deepseek.com", "https://api.deepseek.com/v1"},
    ),
    "mimo": (
        "https://api.xiaomimimo.com/v1",
        "mimo-v2.6-pro",
        "ONEFDE_MODEL_ENGINEERING_MIMO",
        {"https://api.xiaomimimo.com/v1"},
    ),
}


def read_config(path, provider="deepseek", *, prepare=False):
    # No shell evaluation or ${...} expansion of other credentials.
    values = dotenv_values(
        stream=io.StringIO(path.read_text(encoding="utf-8-sig")), interpolate=False
    )
    default_url, default_model, secret, allowed_urls = PROVIDERS[provider]
    prefix = provider.upper()
    key = "" if prepare else (values.get(f"{prefix}_API_KEY") or "").strip()
    endpoint = (values.get(f"{prefix}_BASE_URL") or default_url).strip().rstrip("/")
    model = (values.get(f"{prefix}_MODEL") or default_model).strip()
    if endpoint not in allowed_urls:
        raise ValueError("Expected the selected provider's approved endpoint")
    if not model or any(c.isspace() for c in model) or "/" in model:
        raise ValueError("Invalid model ID")
    if key and (len(key) > 8192 or any(c.isspace() for c in key)):
        raise ValueError("Invalid key format")
    return {
        "key": key,
        "profile": {
            "provider": provider,
            "model": "openai/" + model,
            "base_url": endpoint,
            "secret_ref": "env:" + secret,
            "max_requests": 20,
            "timeout_seconds": 60,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=PROVIDERS, default="deepseek")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument(
        "--prepare", action="store_true", help="Prepare MiMo without a key"
    )
    args = parser.parse_args()
    if args.prepare and args.provider != "mimo":
        parser.error("--prepare requires --provider mimo")
    root = Path(__file__).resolve().parents[1]
    try:
        packet = read_config(root / "backend/.env", args.provider, prepare=args.prepare)
    except (OSError, ValueError):
        raise SystemExit(
            "Cannot load valid provider fields; configuration values withheld"
        ) from None
    if args.check:
        print(
            json.dumps(
                {
                    "key_configured": bool(packet["key"]),
                    "model_execution_enabled": False,
                }
            )
        )
        return
    if not packet["key"] and not args.prepare:
        raise SystemExit(
            f"Fill {args.provider.upper()}_API_KEY in backend/.env and save first"
        )
    result = subprocess.run(
        [
            "wsl",
            "-d",
            "OneFDE",
            "-u",
            "onefde",
            "--",
            "/home/onefde/OneFDE/backend/.venv/bin/python",
            "/home/onefde/OneFDE/deploy/receive_deepseek.py",
        ],
        input=json.dumps(packet).encode(),
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise SystemExit("Local secret synchronization failed; values withheld")
    # Never echo child output, even on errors.
    print(
        f"{args.provider} configuration synchronized locally; no model call. Recreate standby Worker to load."
    )


if __name__ == "__main__":
    main()
