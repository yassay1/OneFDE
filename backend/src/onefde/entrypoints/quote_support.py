"""Operate the explicitly authorized local quote support pilot."""

import argparse
import hashlib
import tarfile
import time
from datetime import timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener
from uuid import UUID

from sqlalchemy.orm import Session

from onefde.core.clock import now
from onefde.core.config import Settings
from onefde.infrastructure.artifacts import PrivateArtifactStore
from onefde.infrastructure.db.session import make_engine
from onefde.infrastructure.runtime.engineering import archive_manifest
from onefde.infrastructure.runtime.openhands import archive_workspace
from onefde.modules.fde import quote_support

PRODUCT = "products/demo-supplier-quotes/"
PUBLIC_FILES = ("index.html", "compare.js", "app.js", "business.js")
SAMPLES = "engagements/demo-supplier-quotes/samples/"
SEED_FILES = {
    *(PRODUCT + name for name in (*PUBLIC_FILES, "check.mjs")),
    *(
        SAMPLES + name
        for name in (
            "s01-same-basis.csv",
            "s02-missing-net-weight.csv",
            "s03-different-grade.csv",
            "s05-mixed.csv",
        )
    ),
}
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(
            req.full_url, code, "Preview redirects are forbidden", headers, fp
        )


def verify_preview(store, artifact, url):
    target = urlsplit(url)
    if (
        target.scheme != "http"
        or target.hostname != "127.0.0.1"
        or target.netloc != f"127.0.0.1:{target.port}"
        or not target.port
        or target.path != "/"
        or target.query
        or target.fragment
        or artifact.kind != "source-snapshot"
    ):
        raise ValueError(
            "Use an explicitly approved loopback product Origin with an explicit port"
        )
    evidence = {"sha256": artifact.sha256, "size_bytes": artifact.size_bytes}
    store.verify(artifact.object_key, evidence)
    manifest = {
        name: (digest, size)
        for name, digest, size in archive_manifest(
            store.path(artifact.object_key).read_bytes()
        )
    }
    client = build_opener(ProxyHandler({}), NoRedirect())
    for name in PUBLIC_FILES:
        expected = manifest.get(PRODUCT + name)
        if expected is None:
            raise ValueError(f"Accepted archive is missing {name}")
        digest, size = expected
        if name == "index.html":
            endpoint = url
        else:
            endpoint = url + name
        with client.open(endpoint, timeout=3) as response:
            content = response.read(size + 1)
        if len(content) != size or hashlib.sha256(content).hexdigest() != digest:
            raise ValueError(
                f"Preview content does not match accepted artifact: {name}"
            )


def prepare_preview(store, artifact, directory):
    if artifact.kind != "source-snapshot":
        raise ValueError("Preview requires an accepted source snapshot")
    store.verify(
        artifact.object_key,
        {"sha256": artifact.sha256, "size_bytes": artifact.size_bytes},
    )
    with tarfile.open(store.path(artifact.object_key), "r:gz") as archive:
        files = {}
        for name in PUBLIC_FILES:
            member = archive.getmember(PRODUCT + name)
            if not member.isfile() or member.size > MAX_ARCHIVE_BYTES:
                raise ValueError(f"Invalid preview member: {name}")
            with archive.extractfile(member) as stream:
                files[name] = stream.read()
    directory.mkdir(mode=0o700)
    for name, content in files.items():
        (directory / name).write_bytes(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    enroll = commands.add_parser("enroll")
    enroll.add_argument("--case", required=True, type=UUID)
    enroll.add_argument("--engagement", required=True, type=UUID)
    enroll.add_argument("--profile", required=True, type=UUID)
    enroll.add_argument(
        "--minutes", required=True, type=int, choices=range(1, 241), metavar="1..240"
    )
    enroll.add_argument("--seed", required=True, type=Path)
    enroll.add_argument("--store", required=True, type=Path)
    enroll.add_argument("--max-runs", required=True, type=int, choices=(1, 2, 3))
    preview = commands.add_parser("verify-preview")
    prepare = commands.add_parser("prepare-preview")
    for command in (preview, prepare):
        command.add_argument("--case", required=True, type=UUID)
        command.add_argument("--artifact", required=True, type=UUID)
        command.add_argument("--store", required=True, type=Path)
    preview.add_argument("--url", required=True)
    prepare.add_argument("--directory", required=True, type=Path)
    commands.add_parser("once")
    commands.add_parser("run")
    args = parser.parse_args()
    engine = make_engine(Settings().database_url.get_secret_value())
    try:
        if args.command == "enroll":
            data, _ = archive_workspace(args.seed, MAX_ARCHIVE_BYTES)
            if {name for name, _, _ in archive_manifest(data)} != SEED_FILES:
                parser.error(
                    "seed must be a staged quote-only baseline preserving repository paths"
                )
            digest = hashlib.sha256(data).hexdigest()
            key = f"engagements/{args.engagement}/support-seeds/{digest}.tar.gz"
            store = PrivateArtifactStore(args.store)
            source = {
                **store.put(key, data),
                "object_key": key,
                "allowed_paths": [PRODUCT + "compare.js"],
            }
            with Session(engine) as db, db.begin():
                quote_support.enroll(
                    db,
                    args.case,
                    args.engagement,
                    args.profile,
                    now() + timedelta(minutes=args.minutes),
                    source,
                    max_runs=args.max_runs,
                )
            print(f"Enrolled {args.case}")
        elif args.command in ("prepare-preview", "verify-preview"):
            with Session(engine) as db:
                artifact = quote_support.preview_artifact(db, args.case, args.artifact)
                db.expunge(artifact)
            if args.command == "prepare-preview":
                prepare_preview(
                    PrivateArtifactStore(args.store), artifact, args.directory
                )
                print(f"Prepared preview for {args.case}")
                return
            verify_preview(PrivateArtifactStore(args.store), artifact, args.url)
            with Session(engine) as db, db.begin():
                quote_support.register_verified_preview(
                    db,
                    args.case,
                    args.artifact,
                    args.url,
                    now() + timedelta(seconds=60),
                )
            print(f"Verified preview for {args.case}")
        else:
            while True:
                with Session(engine) as db:
                    case_ids = quote_support.pending_cases(db)
                count = 0
                for case_id in case_ids:
                    with Session(engine) as db, db.begin():
                        count += quote_support.advance(db, case_id)
                if args.command == "once":
                    print(f"Advanced {count} case(s)")
                    break
                if not count:
                    time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
