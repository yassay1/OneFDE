"""Trusted local stdin receiver. No network, model call or database mutation."""

import json
import os
import stat
import sys
import tempfile
from pathlib import Path

from onefde.modules.tasks.configuration import ModelConfiguration
from sync_deepseek import PROVIDERS


def main():
    directory = Path("/srv/onefde-local/private")
    if sys.platform != "linux" or os.getuid() != 10001:
        raise SystemExit("Run only as the local onefde user")
    info = directory.stat()
    if (
        directory.resolve() != directory
        or directory.is_symlink()
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise SystemExit("Invalid private directory")
    try:
        packet = json.loads(sys.stdin.buffer.read(32769))
        key = packet["key"]
        profile = ModelConfiguration.model_validate(packet["profile"])
        _, _, secret, allowed_urls = PROVIDERS[profile.provider]
        if (
            not isinstance(key, str)
            or (not key and profile.provider != "mimo")
            or len(key) > 8192
            or any(c.isspace() for c in key)
        ):
            raise ValueError()
        if (
            profile.secret_ref != "env:" + secret
            or profile.base_url.rstrip("/") not in allowed_urls
        ):
            raise ValueError()
    except Exception:
        raise SystemExit("Invalid local provider packet; values withheld") from None
    provider = profile.provider
    for name, data in {
        f"{provider}_api_key": key + "\n",
        f"{provider}-profile.json": json.dumps(profile.model_dump(), indent=2) + "\n",
    }.items():
        destination = directory / name
        if destination.is_symlink():
            raise SystemExit("Refuse symlink destination")
        if name.endswith("_api_key") and not key:
            # Preparation is repeatable and never overwrites an existing key.
            destination.touch(mode=0o600, exist_ok=True)
            continue
        fd, temporary = tempfile.mkstemp(prefix=f".{provider}-", dir=directory)
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(data.encode())
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
    print("Local secret and non-secret profile saved; model execution remains disabled")


if __name__ == "__main__":
    main()
