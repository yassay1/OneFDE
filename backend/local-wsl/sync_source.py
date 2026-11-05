"""Windows -> dedicated WSL source copy; excludes secrets and local state."""

import io
import subprocess
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
files = (
    subprocess.check_output(
        ["git", "ls-files", "-c", "-o", "--exclude-standard", "-z"], cwd=root
    )
    .decode("utf-8")
    .split("\0")
)
data = io.BytesIO()
count = 0
with tarfile.open(fileobj=data, mode="w:gz") as archive:
    for name in sorted(set(files) - {""}):
        path = Path(name)
        if any(
            p in {".git", ".planning", "work", ".venv", "__pycache__"}
            for p in path.parts
        ):
            continue
        if path.name.startswith(".env") and path.name not in {
            ".env.example",
            ".env.worker.example",
        }:
            continue
        source = root / path
        if (
            source.is_symlink()
            or not source.is_file()
            or not source.resolve().is_relative_to(root)
        ):
            raise SystemExit("Unsafe source path")
        archive.add(source, arcname=path.as_posix(), recursive=False)
        count += 1
subprocess.run(
    [
        "wsl",
        "-d",
        "OneFDE",
        "-u",
        "onefde",
        "--cd",
        "/home/onefde",
        "--exec",
        "tar",
        "-xzf",
        "-",
        "--no-same-owner",
        "-C",
        "/home/onefde/OneFDE",
    ],
    input=data.getvalue(),
    check=True,
)
print(
    f"Copied {count} source files; excluded local secrets/state. No deletion or service restart."
)
