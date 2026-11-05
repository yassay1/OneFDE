"""Local terminal-only secret input; never prints or overwrites an existing key."""

import argparse
import getpass
import os
import stat
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if sys.platform != "linux" or os.getuid() != 10001:
        raise SystemExit("Run as onefde inside the OneFDE WSL terminal")
    directory = Path("/srv/onefde-local/private")
    if directory.is_symlink() or directory.resolve() != directory:
        raise SystemExit("Unexpected private directory")
    info = directory.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise SystemExit("Private directory must be owned by onefde with mode 700")
    path = directory / "deepseek_api_key"
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise SystemExit("Secret must be a regular owner-only file (600)")
        if args.prepare or args.check:
            print(
                f"{path}: "
                + ("configured" if info.st_size else "empty; awaiting local input")
            )
            return
        if info.st_size:
            raise SystemExit("Key already exists; kept unchanged")
        if not sys.stdin.isatty():
            raise SystemExit("Open an interactive OneFDE WSL terminal first")
        value = getpass.getpass("DeepSeek API Key (hidden): ").strip()
        if not value or any(c.isspace() for c in value):
            raise SystemExit("Empty or invalid key; nothing saved")
        with os.fdopen(os.dup(fd), "wb") as output:
            output.write(value.encode("utf-8") + b"\n")
            output.flush()
            os.fsync(output.fileno())
        print("Key saved locally with mode 600. Model execution remains disabled.")
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
