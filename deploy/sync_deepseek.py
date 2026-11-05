"""Read ONLY DeepSeek fields from Windows backend/.env; send via local stdin."""

import argparse
import io
import json
import subprocess
from pathlib import Path

from dotenv import dotenv_values


def read_config(path):
    # No shell evaluation or ${...} expansion of other credentials.
    values = dotenv_values(
        stream=io.StringIO(path.read_text(encoding="utf-8-sig")), interpolate=False
    )
    key = (values.get("DEEPSEEK_API_KEY") or "").strip()
    endpoint = (values.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").strip()
    model = (values.get("DEEPSEEK_MODEL") or "deepseek-flash").strip()
    if endpoint.rstrip("/") not in {
        "https://api.deepseek.com",
        "https://api.deepseek.com/v1",
    }:
        raise ValueError("Expected the official DeepSeek endpoint")
    if not model or any(c.isspace() for c in model) or "/" in model:
        raise ValueError("Invalid DeepSeek model ID")
    if key and (len(key) > 8192 or any(c.isspace() for c in key)):
        raise ValueError("Invalid key format")
    return {
        "key": key,
        "profile": {
            "provider": "deepseek",
            "model": "openai/" + model,
            "base_url": endpoint,
            "secret_ref": "env:ONEFDE_MODEL_ENGINEERING",
            "max_requests": 20,
            "timeout_seconds": 60,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        packet = read_config(root / "backend/.env")
    except (OSError, ValueError):
        raise SystemExit(
            "Cannot load valid DeepSeek fields; configuration values withheld"
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
    if not packet["key"]:
        raise SystemExit("Fill DEEPSEEK_API_KEY in backend/.env and save first")
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
        "DeepSeek fields synchronized locally; no model call. Recreate standby Worker to load."
    )


if __name__ == "__main__":
    main()
