from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace
from urllib.error import URLError

import pytest

from onefde.entrypoints.quote_support import (
    PRODUCT,
    PUBLIC_FILES,
    prepare_preview,
    verify_preview,
)
from onefde.infrastructure.artifacts import PrivateArtifactStore
from onefde.infrastructure.runtime.openhands import archive_workspace


def test_loopback_preview_verifies_accepted_bytes(tmp_path):
    root = tmp_path / "source"
    folder = root / PRODUCT
    folder.mkdir(parents=True)
    for name in PUBLIC_FILES:
        (folder / name).write_text(name, encoding="utf-8")
    archive, _ = archive_workspace(root, 16384)
    store = PrivateArtifactStore(tmp_path / "artifacts")
    key = "fixture.tar.gz"
    artifact = SimpleNamespace(
        **store.put(key, archive), object_key=key, kind="source-snapshot"
    )
    public = tmp_path / "public"
    prepare_preview(store, artifact, public)
    handler = partial(SimpleHTTPRequestHandler, directory=public)
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        thread = Thread(target=server.serve_forever)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}/"
        try:
            verify_preview(store, artifact, url)
            (public / "compare.js").write_text("stale version", encoding="utf-8")
            with pytest.raises(ValueError, match="does not match"):
                verify_preview(store, artifact, url)
        finally:
            server.shutdown()
            thread.join()
    with pytest.raises(URLError):
        verify_preview(store, artifact, url)
    with pytest.raises(ValueError, match="loopback"):
        verify_preview(store, artifact, "http://localhost:8766/")
