"""Private local immutable blobs. No public download or S3 claim is implied."""

import hashlib
import os
from pathlib import Path, PurePosixPath


class PrivateArtifactStore:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def path(self, key):
        value = PurePosixPath(key)
        if value.is_absolute() or ".." in value.parts or "\\" in key or not value.parts:
            raise ValueError("invalid private artifact key")
        path = self.root.joinpath(*value.parts)
        if not path.resolve().is_relative_to(self.root) or any(
            p.is_symlink() for p in [path, *path.parents] if p.is_relative_to(self.root)
        ):
            raise ValueError("artifact path escapes private store")
        return path

    def put(self, key, data):
        path = self.path(key)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if path.read_bytes() != data:
                raise ValueError("immutable blob collision") from None
        else:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}

    def verify(self, key, evidence):
        data = self.path(key).read_bytes()
        if (
            hashlib.sha256(data).hexdigest() != evidence["sha256"]
            or len(data) != evidence["size_bytes"]
        ):
            raise ValueError("artifact contents do not match registered evidence")

    def receipt(self, run_id, data):
        # Immutable receipts survive database/network failure for later controlled audit.
        from uuid import uuid4

        return self.put(f"receipts/{run_id}/{uuid4()}.json", data)
