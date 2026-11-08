"""Pinned OpenHands SDK binding, with independent Docker stop confirmation.

SDK owns the Agent loop. This adapter owns only OneFDE's resource boundary,
deadline, evidence capture, and the translation to an execution report.
"""

import hashlib
import io
import json
import logging
import os
import re
import secrets
import subprocess
import tarfile
import threading
import time
from contextlib import contextmanager
from importlib.metadata import version
from ipaddress import IPv4Address
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import SecretStr

from onefde.core.engineering import check_revision
from onefde.core.execution import ExecutionReport, RuntimeUnavailable
from onefde.infrastructure.artifacts import PrivateArtifactStore
from onefde.infrastructure.runtime import engineering as eng
from onefde.infrastructure.runtime import skills as engineering_skills
from onefde.infrastructure.runtime.model_gate import (
    disable_remote_autotitle,
    start_model_gate,
)

_environment_lock = threading.Lock()


def docker(*args):
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=45, check=False
    )


def aggregate_stopped(containers) -> bool:
    """Every recorded container must be confirmed stopped. A missing id is unknown."""
    if not containers:
        return False
    return all(confirm_stopped(item.get("container_id")) for item in containers)


def _control_halt(stop, deadline):
    if stop is not None and stop.is_set():
        return "STOP_REQUESTED"
    if time.monotonic() >= deadline:
        return "EXECUTION_DEADLINE"
    return None


def run_bounded_command(workspace, command, cwd, stop, deadline, container_id):
    """Run one validation command until it finishes, the run stops, or the deadline."""
    outcome = {}

    def invoke():
        try:
            remaining = deadline - time.monotonic()
            timeout = min(120, max(1, int(remaining)))
            outcome["value"] = workspace.execute_command(
                command, cwd=cwd, timeout=timeout
            )
        except Exception as exc:
            outcome["error"] = exc

    worker = threading.Thread(
        target=invoke, name="onefde-validation-check", daemon=True
    )
    worker.start()
    while worker.is_alive():
        if _control_halt(stop, deadline):
            confirm_stopped(container_id)
            worker.join(timeout=5)
            return None
        worker.join(timeout=min(0.2, max(deadline - time.monotonic(), 0.05)))
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("value")


def confirm_stopped(container_id):
    """Never equate SDK pause/cleanup or an unreachable daemon with stopping."""
    if not container_id or not re.fullmatch(r"[a-f0-9]{64}", container_id):
        return False
    try:
        docker("stop", "--time", "10", container_id)
        # A successful daemon inventory proves absence even with --rm containers.
        inventory = docker("ps", "-a", "--no-trunc", "--format", "{{.ID}}")
        if inventory.returncode != 0:
            return False
        if container_id not in inventory.stdout.splitlines():
            return True
        inspected = docker("inspect", "--format", "{{.State.Running}}", container_id)
        if inspected.returncode == 0:
            return inspected.stdout.strip() == "false"
        # --rm can remove the container between inventory and inspect. Require a
        # new successful inventory proving absence; inspect failure alone is unknown.
        inventory = docker("ps", "-a", "--no-trunc", "--format", "{{.ID}}")
        return (
            inventory.returncode == 0
            and container_id not in inventory.stdout.splitlines()
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def local_workspace_host(container_id, network):
    """Host-to-container access when an internal bridge suppresses published ports."""
    inspected = docker("inspect", container_id)
    if inspected.returncode:
        raise RuntimeUnavailable("Cannot inspect local workspace address")
    address = json.loads(inspected.stdout)[0]["NetworkSettings"]["Networks"][network][
        "IPAddress"
    ]
    value = IPv4Address(address)
    if not value.is_private or value.is_loopback:
        raise RuntimeUnavailable("Unexpected local workspace address")
    return f"http://{value}:8000"


@contextmanager
def server_environment(session_key):
    # SDK copies only these names to Docker, not the trusted Worker's environment.
    values = {"OH_SESSION_API_KEYS_0": session_key, "OH_CONVERSATIONS_PATH": "/session"}
    with _environment_lock:
        previous = {key: os.environ.get(key) for key in values}
        os.environ.update(values)
        try:
            yield list(values)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def resolve_model(snapshot):
    config, profile = snapshot["config"], snapshot["model_profile"]
    reference = config.get("secret_ref", "")
    endpoint = urlsplit(config.get("base_url", ""))
    if (
        config.get("adapter") != "openhands"
        or profile.get("protocol") != "openai_chat_completions"
        or not profile.get("model", "").startswith("openai/")
        or not re.fullmatch(r"env:ONEFDE_MODEL_[A-Z0-9_]+", reference)
        or endpoint.scheme != "https"
        or not endpoint.hostname
        or endpoint.username
        or endpoint.password
        or endpoint.query
        or endpoint.fragment
    ):
        raise RuntimeUnavailable("Unsupported or incomplete model configuration")
    credential = os.environ.get(reference.removeprefix("env:"))
    if not credential:
        raise RuntimeUnavailable("Scoped model secret is absent")
    return credential


def archive_workspace(path, maximum):
    """Read only regular source files beneath this task, after confirmed stop."""
    buffer, count, total = io.BytesIO(), 0, 0
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for file in sorted(path.rglob("*")):
            if file.is_symlink() or not file.resolve().is_relative_to(path.resolve()):
                raise ValueError("workspace contains a symlink")
            if file.is_dir():
                continue
            if not file.is_file():
                raise ValueError("workspace contains a special file")
            relative = file.relative_to(path).as_posix()
            if not eng.is_frozen_source(relative):
                continue
            total += file.stat().st_size
            count += 1
            if total > maximum or count > 10000:
                raise ValueError("workspace exceeds artifact budget")
            archive.add(file, arcname=relative, recursive=False)
    return buffer.getvalue(), count


def sandbox_gateway(settings):
    """Private bridge address the sandbox can reach without a published port."""
    network = settings.network or ""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", network):
        raise RuntimeUnavailable("Model gate requires the sandbox network")
    inspected = docker("network", "inspect", network)
    if inspected.returncode:
        raise RuntimeUnavailable("Cannot inspect the sandbox network")
    try:
        gateway = json.loads(inspected.stdout)[0]["IPAM"]["Config"][0]["Gateway"]
        address = IPv4Address(gateway)
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeUnavailable("Sandbox network has no private gateway") from exc
    if not address.is_private or address.is_loopback or address.is_link_local:
        raise RuntimeUnavailable("Sandbox gateway is not a private address")
    return str(address)


def start_run_model_gate(settings, upstream, limit, timeout):
    """One Run-wide HTTP ceiling in front of the reviewed provider origin."""
    return start_model_gate(
        sandbox_gateway(settings),
        upstream,
        limit,
        timeout=timeout,
        proxy_url=settings.egress_proxy_url,
    )


def sandbox_proxy_flags(settings):
    """Route provider HTTPS via the reviewed CONNECT proxy.

    The model gate is HTTP on the sandbox gateway. It stays out of that proxy
    so the provider credential is not sent to the proxy as cleartext.
    """
    if not settings.egress_proxy_url:
        return []
    bypass = ["localhost", "127.0.0.1"]
    try:
        bypass.append(sandbox_gateway(settings))
    except RuntimeUnavailable:
        pass
    no_proxy = ",".join(bypass)
    return [
        item
        for key, value in (
            ("HTTP_PROXY", settings.egress_proxy_url),
            ("HTTPS_PROXY", settings.egress_proxy_url),
            ("http_proxy", settings.egress_proxy_url),
            ("https_proxy", settings.egress_proxy_url),
            ("NO_PROXY", no_proxy),
            ("no_proxy", no_proxy),
        )
        for item in ("--env", f"{key}={value}")
    ]


def shared_workspace(settings, workspace_path, session_path, session_key, on_resource):
    """Pinned SDK lifecycle with create-time limits; no Agent or model invocation.

    Docker creates sibling containers using daemon-host paths. This narrow
    override replaces only DockerWorkspace's reviewed container startup method.
    """
    from openhands.sdk.workspace import RemoteWorkspace
    from openhands.workspace import DockerWorkspace

    root = settings.root.resolve()
    for path in (workspace_path, session_path):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise RuntimeUnavailable("Unsafe shared workspace mount")
        if not path.is_dir() or path.stat().st_uid != 10001:
            raise RuntimeUnavailable(
                "Shared workspace must exist and belong to UID10001"
            )

    class SharedWorkspace(DockerWorkspace):
        def _start_container(inner, image, context):
            name = "onefde-sandbox-" + str(uuid4())
            flags = [
                "create",
                "--name",
                name,
                "--label",
                "onefde.managed=sandbox",
                "--label",
                "onefde.worker=" + settings.worker_id,
                "--init",
                "--user",
                "10001:10001",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--cpus",
                str(settings.cpus),
                "--memory",
                settings.memory,
                "--memory-swap",
                settings.memory,
                "--pids-limit",
                str(settings.pids_limit),
                "--ulimit",
                "nofile=4096:4096",
                "--log-driver",
                "local",
                "--log-opt",
                "max-size=10m",
                "--log-opt",
                "max-file=3",
                "--network",
                settings.network,
                "--tmpfs",
                # The pinned Agent Server is a bundled executable that extracts
                # shared libraries here. exec is required; size/caps/NNP remain.
                "/tmp:rw,exec,nosuid,nodev,size=268435456,mode=1777",
                "--tmpfs",
                "/home/openhands:rw,nosuid,nodev,size=268435456,uid=10001,gid=10001,mode=700",
                "--mount",
                f"type=bind,src={workspace_path},dst=/workspace",
                "--mount",
                f"type=bind,src={session_path},dst=/session",
                "--env",
                "OH_SESSION_API_KEYS_0=" + session_key,
                "--env",
                "OH_CONVERSATIONS_PATH=/session",
                "--env",
                "LITELLM_LOCAL_MODEL_COST_MAP=True",
                "--env",
                "OPENHANDS_SUPPRESS_BANNER=1",
                "--env",
                "TINI_SUBREAPER=1",
                *sandbox_proxy_flags(settings),
                image,
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
            ]
            allocated = docker(*flags)
            identifier = allocated.stdout.strip()
            if allocated.returncode or not re.fullmatch(r"[a-f0-9]{64}", identifier):
                raise RuntimeUnavailable("Shared sandbox creation failed")
            inner._container_id = identifier
            on_resource(
                {
                    "container_id": identifier,
                    "image": image,
                    "network": settings.network,
                }
            )
            if docker("start", identifier).returncode:
                raise RuntimeUnavailable("Shared sandbox start failed")
            object.__setattr__(
                inner, "host", local_workspace_host(identifier, settings.network)
            )
            object.__setattr__(inner, "api_key", session_key)
            inner._wait_for_health(timeout=inner.health_check_timeout)
            RemoteWorkspace.model_post_init(inner, context)

        def cleanup(inner):
            # Keep failed/unknown resources for operator inspection. Never force rm
            # while stop is uncertain. Remove only this validated private ID.
            identifier = inner._container_id
            if identifier and confirm_stopped(identifier):
                if docker("rm", identifier).returncode == 0:
                    inner._container_id = None

    return SharedWorkspace(
        server_image=settings.server_image,
        working_dir="/workspace",
        volumes=[],
        forward_env=[],
        network=settings.network,
        extra_ports=False,
        detach_logs=False,
        cleanup_image=False,
        health_check_timeout=60,
        read_timeout=15,
    )


def _load_prior_archive(store, meta):
    if not meta:
        return None
    path = store.path(meta["object_key"])
    data = path.read_bytes()
    store.verify(
        meta["object_key"],
        {"sha256": meta["sha256"], "size_bytes": meta["size_bytes"]},
    )
    return data


def _run_conversation(conversation, stop, deadline, poll_seconds):
    """Wait for SDK event delivery as well as the terminal state."""
    done = threading.Event()

    def invoke():
        try:
            conversation.run(
                timeout=max(1, deadline - time.monotonic()), poll_interval=poll_seconds
            )
        except Exception:
            # SDK raises on its ERROR state. The typed event determines the reason.
            pass
        finally:
            done.set()

    threading.Thread(target=invoke, name="onefde-sdk-run", daemon=True).start()
    while not done.wait(poll_seconds):
        if halt := _control_halt(stop, deadline):
            return halt
    if halt := _control_halt(stop, deadline):
        return halt
    state = conversation.state
    if getattr(state.execution_status, "value", state.execution_status) == "finished":
        return "FINISHED"
    for event in reversed(state.events):
        if type(event).__name__ == "ConversationErrorEvent":
            return (
                "ITERATION_LIMIT_REACHED"
                if event.code == "MaxIterationsReached"
                else "SDK_EXECUTION_FAILED"
            )
    return "SDK_EXECUTION_FAILED"


class OpenHandsAdapter:
    def __init__(self, settings):
        self.settings = settings
        self.store = PrivateArtifactStore(settings.root / "artifacts")

    def _open_workspace(
        self, request, workspace_path, session_path, session_key, containers
    ):
        settings = self.settings
        from openhands.workspace import DockerWorkspace

        class BoundedWorkspace(DockerWorkspace):
            def _wait_for_health(inner, timeout):
                containers.append(
                    {"role": "engineering", "container_id": inner._container_id}
                )
                request.on_resource(
                    {
                        "role": "engineering",
                        "container_id": containers[-1]["container_id"],
                        "run_id": str(request.run_id),
                        "session_ref": f"sessions/{request.run_id}",
                        "image": settings.server_image,
                    }
                )
                limited = docker(
                    "update",
                    "--cpus",
                    str(settings.cpus),
                    "--memory",
                    settings.memory,
                    "--memory-swap",
                    settings.memory,
                    "--pids-limit",
                    str(settings.pids_limit),
                    containers[-1]["container_id"],
                )
                if limited.returncode:
                    raise RuntimeError("Container resource limit failed")
                if settings.execution_mode == "local_wsl":
                    object.__setattr__(
                        inner,
                        "host",
                        local_workspace_host(
                            containers[-1]["container_id"], settings.network
                        ),
                    )
                return super()._wait_for_health(timeout=timeout)

        if settings.execution_mode == "ecs_shared":

            def allocated(reference):
                containers.append(
                    {"role": "engineering", "container_id": reference["container_id"]}
                )
                request.on_resource(
                    {
                        **reference,
                        "role": "engineering",
                        "run_id": str(request.run_id),
                        "session_ref": f"sessions/{request.run_id}",
                    }
                )

            return shared_workspace(
                settings, workspace_path, session_path, session_key, allocated
            )
        with server_environment(session_key) as forwarded:
            return BoundedWorkspace(
                server_image=settings.server_image,
                working_dir="/workspace",
                volumes=[
                    f"{workspace_path}:/workspace",
                    f"{session_path}:/session",
                ],
                forward_env=forwarded,
                network=settings.network,
                extra_ports=False,
                detach_logs=False,
                health_check_timeout=60,
                read_timeout=15,
                cleanup_image=False,
                platform="linux/amd64",
            )

    def _validate_fixed_source(
        self,
        request,
        archive,
        checks,
        containers,
        stop,
        deadline,
        *,
        phase=0,
        failure_output=None,
    ):
        """Sequential no-model validation against the frozen source archive."""
        automatic = [item for item in checks if item["kind"] == "automatic"]
        if not automatic:
            return {
                "passed": True,
                "skipped": True,
                "reason": "no automatic checks registered",
            }
        halt = _control_halt(stop, deadline)
        if halt:
            return {
                "passed": False,
                "stopped": True,
                "skipped": True,
                "reason": halt,
                "error_code": halt,
                "results": [],
                "source_unchanged": True,
            }
        settings = self.settings
        if settings.validation_network:
            network = docker("network", "inspect", settings.validation_network)
            if network.returncode or not json.loads(network.stdout)[0]["Internal"]:
                raise RuntimeUnavailable("Validation requires an internal bridge")
            settings = settings.model_copy(
                update={
                    "network": settings.validation_network,
                    "egress_proxy_url": None,
                }
            )
        validation_root = (
            settings.root
            / "tasks"
            / str(request.task_id)
            / "validation"
            / str(request.run_id)
        )
        if phase:
            validation_root = validation_root / "repair"
        role = "validation-repair" if phase else "validation"
        workspace_path = validation_root / "workspace"
        session_path = validation_root / "session"
        if validation_root.exists():
            raise RuntimeUnavailable("Validation workspace already exists")
        session_path.mkdir(mode=0o700, parents=True)
        restored = eng.restore_archive(
            archive, workspace_path, settings.max_artifact_bytes
        )
        before = restored["digest"]
        session_key = secrets.token_urlsafe(32)
        PrivateArtifactStore(settings.root / "private").put(
            f"{request.run_id}/{role}.session.key", session_key.encode()
        )
        workspace, results, halted = None, [], None
        try:

            def allocated(reference):
                containers.append(
                    {"role": role, "container_id": reference["container_id"]}
                )
                request.on_resource(
                    {
                        **reference,
                        "role": role,
                        "run_id": str(request.run_id),
                        "session_ref": f"sessions/{request.run_id}",
                    }
                )

            workspace = shared_workspace(
                settings, workspace_path, session_path, session_key, allocated
            )
            validation_id = next(
                item["container_id"]
                for item in reversed(containers)
                if item.get("role") == role
            )
            for check in automatic:
                halted = _control_halt(stop, deadline)
                if halted:
                    break
                observed = run_bounded_command(
                    workspace,
                    check["command"],
                    check.get("cwd") or "/workspace",
                    stop,
                    deadline,
                    validation_id,
                )
                if observed is None:
                    halted = _control_halt(stop, deadline) or "STOP_REQUESTED"
                    break
                timeout = bool(observed.timeout_occurred)
                if failure_output is not None and (observed.exit_code != 0 or timeout):
                    failure_output[check["id"]] = (observed.stderr or observed.stdout)[
                        -1600:
                    ]
                results.append(
                    {
                        "id": check["id"],
                        "command": check["command"],
                        "cwd": check.get("cwd") or "/workspace",
                        "exit_code": observed.exit_code,
                        "timeout": timeout,
                    }
                )
        finally:
            identifier = next(
                (
                    item["container_id"]
                    for item in reversed(containers)
                    if item.get("role") == role
                ),
                None,
            )
            stopped = confirm_stopped(identifier)
            if workspace is not None and stopped:
                workspace.cleanup()
        after = eng.workspace_digest(workspace_path)
        comparison = eng.compare_workspace_to_archive(workspace_path, archive)
        source_unchanged = eng.frozen_source_unchanged(comparison)
        passed = bool(
            stopped
            and source_unchanged
            and not halted
            and len(results) == len(automatic)
            and all(item["exit_code"] == 0 and not item["timeout"] for item in results)
        )
        return {
            "passed": passed,
            "stopped": stopped,
            "source_digest_before": before,
            "source_digest_after": after,
            "source_unchanged": source_unchanged,
            "comparison": comparison,
            "results": results,
            "error_code": None
            if passed
            else (
                "STOP_UNCONFIRMED"
                if not stopped
                else "SOURCE_MUTATED_DURING_VALIDATION"
                if not source_unchanged
                else halted
                if halted
                else "FIXED_VALIDATION_FAILED"
            ),
        }

    def _finalize_stopped_run(
        self,
        request,
        stop,
        deadline,
        workspace_path,
        containers,
        proof,
        *,
        reason,
        finished,
        messages,
        evidence,
        checks,
        credential,
        session_key,
        checked_candidate=None,
        checkpoint_required=False,
    ):
        """Archive, validate, and decide. Unknown container stop never releases the slot."""
        settings = self.settings
        keys, artifacts = [], []
        try:
            data, count = archive_workspace(workspace_path, settings.max_artifact_bytes)
            if checked_candidate is not None:
                checked_archive, validation = checked_candidate
                if not eng.compare_workspace_to_archive(
                    workspace_path, checked_archive
                )["match"]:
                    reason = "CANDIDATE_CHANGED_AFTER_CHECK"
                else:
                    data = checked_archive
            initial = request.snapshot.get("engineering", {}).get("initial_source")
            if initial:
                baseline = _load_prior_archive(self.store, initial)
                before = dict(
                    (path, sha) for path, sha, _ in eng.archive_manifest(baseline)
                )
                after = dict((path, sha) for path, sha, _ in eng.archive_manifest(data))
                changed = {
                    path
                    for path in before.keys() | after.keys()
                    if before.get(path) != after.get(path)
                }
                proof["changed_paths"] = sorted(changed)
                if (
                    changed - set(initial["allowed_paths"])
                    or not before.keys() <= after.keys()
                ):
                    reason = "WORKSPACE_SCOPE_EXCEEDED"
                elif initial.get("review_paths"):
                    material = eng.build_review_material(
                        data, baseline, initial["review_paths"]
                    ) | {"mode": "engineering"}
                    for field in ("design", "diff"):
                        for secret in filter(None, (credential, session_key)):
                            material[field] = material[field].replace(
                                secret, "[REDACTED]"
                            )
                    proof["review_material"] = material
            source_digest = eng.workspace_digest(workspace_path) if count else None
            if count and reason != "WORKSPACE_SCOPE_EXCEEDED":
                key = f"engagements/{request.engagement_id}/runs/{request.run_id}/{uuid4()}"
                blob = self.store.put(key, data)
                keys.append(key)
                artifacts.append(
                    {"name": "workspace.tar.gz", "kind": "source-snapshot", **blob}
                )
            try:
                if reason == "FINISHED" and finished:
                    proposal = eng.parse_proposal(finished[-1])
                elif reason == "FINISHED" and messages:
                    # Trusted fallback when the model emits JSON in the final chat
                    # message instead of FinishAction (observed with deepseek-flash).
                    proposal = eng.parse_proposal(messages[-1])
                else:
                    proposal = {}
            except (ValueError, TypeError, json.JSONDecodeError):
                proposal, reason = {}, "RESULT_FORMAT_INVALID"

            validation = None
            if (
                reason == "FINISHED"
                and proposal.get("outcome") == "submitted"
                and count
                and any(item["kind"] == "automatic" for item in checks)
            ):
                if checked_candidate is not None:
                    validation = checked_candidate[1]
                elif not checkpoint_required:
                    validation = self._validate_fixed_source(
                        request, data, checks, containers, stop, deadline
                    )
                proof["validation"] = validation
                proof["resources"] = list(containers)
                if validation is not None and not validation.get("stopped", True):
                    proof["stopped"] = False
                    return ExecutionReport(
                        {
                            "state": "interrupted",
                            "summary": "验证现场停止状态未核实",
                            "error_code": "STOP_UNCONFIRMED",
                            "stopped": False,
                            "artifacts": artifacts,
                        },
                        tuple(keys),
                        proof,
                    )

            result, extras = eng.decide_result(
                proposal,
                reason=reason,
                source_count=count,
                checks=checks,
                evidence=evidence,
                validation=validation,
            )
            proof.update(extras)
            if source_digest:
                proof["source_digest"] = source_digest
            for field in ("summary", "question"):
                if field in result:
                    for secret in (credential, session_key):
                        result[field] = result[field].replace(secret, "[REDACTED]")
            result["artifacts"] = artifacts
            proof["stopped"] = aggregate_stopped(containers)
            if not proof["stopped"] and result.get("state") != "interrupted":
                return ExecutionReport(
                    {
                        "state": "interrupted",
                        "summary": "仍有所属容器停止状态未核实",
                        "error_code": "STOP_UNCONFIRMED",
                        "stopped": False,
                        "artifacts": artifacts,
                    },
                    tuple(keys),
                    proof,
                )
            return ExecutionReport(result, tuple(keys), proof)
        except Exception:
            proof["resources"] = list(containers)
            proof["stopped"] = aggregate_stopped(containers)
            if not proof["stopped"]:
                return ExecutionReport(
                    {
                        "state": "interrupted",
                        "summary": "验证或收尾异常，所属容器停止状态未核实",
                        "error_code": "STOP_UNCONFIRMED",
                        "stopped": False,
                        "artifacts": artifacts,
                    },
                    tuple(keys),
                    proof,
                )
            return ExecutionReport(
                {
                    "state": "failed",
                    "summary": "本轮已停止，产物保存或结果解析失败",
                    "error_code": "RESULT_PERSISTENCE_FAILED",
                    "stopped": True,
                },
                proof=proof,
            )

    def _verify_reuse(self, request, stop, engineering):
        settings = self.settings
        network = docker("network", "inspect", "onefde-engineering-offline")
        if (
            settings.blockers(environment_only=True)
            or settings.model_execution_enabled
            or settings.egress_proxy_url
            or settings.execution_mode != "ecs_shared"
            or settings.network != "onefde-engineering-offline"
            or network.returncode
            or not json.loads(network.stdout)[0]["Internal"]
        ):
            raise RuntimeUnavailable(
                "Reuse validation requires the internal offline bridge"
            )
        try:
            source = engineering["initial_source"]
            archive = _load_prior_archive(self.store, source)
        except (KeyError, ValueError, OSError) as exc:
            raise RuntimeUnavailable(
                "Cannot verify the registered reuse archive"
            ) from exc
        checks = engineering["checks"]
        if not any(item["kind"] == "automatic" for item in checks):
            raise RuntimeUnavailable("Reuse validation requires registered checks")
        containers = []
        deadline = time.monotonic() + settings.max_seconds
        validation = self._validate_fixed_source(
            request, archive, checks, containers, stop, deadline
        )
        proof = {
            "stopped": validation["stopped"],
            "resources": containers,
            "validation": validation,
            "reuse_asset": engineering["reuse_asset"],
            "source_sha256": source["sha256"],
            "model_called": False,
        }
        if not validation["passed"]:
            return ExecutionReport(
                {
                    "state": "failed" if validation["stopped"] else "interrupted",
                    "summary": "固定能力归档验证未通过",
                    "error_code": validation["error_code"],
                    "stopped": validation["stopped"],
                },
                proof=proof,
            )
        key = f"engagements/{request.engagement_id}/runs/{request.run_id}/reuse-source"
        blob = self.store.put(key, archive)
        return ExecutionReport(
            {
                "state": "completed",
                "outcome": "submitted",
                "stopped": True,
                "summary": "固定能力归档的独立无模型检查通过",
                "artifacts": [
                    {"name": "workspace.tar.gz", "kind": "source-snapshot", **blob}
                ],
            },
            (key,),
            proof,
        )

    def execute(self, request, stop):
        settings = self.settings
        engineering = request.snapshot.get("engineering") or {}
        if engineering.get("reuse_asset"):
            return self._verify_reuse(request, stop, engineering)
        if settings.blockers():
            raise RuntimeUnavailable("Worker execution preflight failed")
        skill_manifest, skill_files = engineering_skills.load_bundle()
        credential = resolve_model(request.snapshot)
        if any(
            version(name) != "1.59.0"
            for name in ("openhands-sdk", "openhands-workspace", "openhands-tools")
        ):
            raise RuntimeUnavailable("SDK versions differ from reviewed binding")
        logging.getLogger("openhands").setLevel(logging.CRITICAL)
        from openhands.sdk import LLM, Agent, AgentContext, Conversation, Tool
        from openhands.sdk.context import Skill
        from openhands.sdk.tool import register_tool
        from openhands.tools.file_editor import FileEditorTool
        from openhands.tools.terminal import TerminalTool

        trusted_skills = [
            Skill.load(path, skip_mcp=True).model_copy(
                update={"source": None, "resources": None, "version": row["version"]}
            )
            for row, path in skill_files
        ]
        skill_names = {skill.name for skill in trusted_skills}
        if skill_names != set(engineering_skills.SKILL_NAMES):
            raise RuntimeUnavailable("SDK did not load the reviewed skill catalog")
        invoked_skills = []

        workspace_path = settings.root / "tasks" / str(request.task_id) / "workspace"
        session_path = settings.root / "sessions" / str(request.run_id)
        for path in (workspace_path, session_path):
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
            if path.is_symlink() or not path.resolve().is_relative_to(
                settings.root.resolve()
            ):
                raise RuntimeUnavailable("Unsafe persistent path")

        engineering = request.snapshot.get("engineering") or {}
        meta = engineering.get("prior_source") or engineering.get("initial_source")
        prior_archive = _load_prior_archive(self.store, meta)
        gate = eng.evaluate_workspace_gate(workspace_path, prior_archive)
        if gate.get("blocked"):
            return ExecutionReport(
                {
                    "state": "failed",
                    "summary": "工作区与上次固定源码存在未知差异，已阻塞续作",
                    "error_code": "WORKSPACE_DRIFT",
                    "stopped": True,
                },
                proof={
                    "stopped": True,
                    "method": "workspace-compare",
                    "workspace": gate,
                },
            )
        if gate.get("status") == "empty_with_prior" and prior_archive is not None:
            # Controlled restore from the last validated archive; keep current empty tree.
            eng.restore_archive(
                prior_archive, workspace_path, settings.max_artifact_bytes
            )
            gate = {
                **gate,
                "status": "restored_from_prior",
                "restored_digest": eng.workspace_digest(workspace_path),
            }

        workspace_status = dict(gate)
        original = engineering.get("initial_source") or {}
        if original.get("review_guide_revision"):
            workspace_status["review_guide_revision"] = original[
                "review_guide_revision"
            ]
        if engineering.get("recovery_parent_run_id"):
            workspace_status["recovery_parent_run_id"] = engineering[
                "recovery_parent_run_id"
            ]
        context = eng.build_context(
            request.snapshot,
            task_id=request.task_id,
            run_id=request.run_id,
            engagement_id=request.engagement_id,
            spec_version=request.snapshot["spec_version"],
            workspace_status=workspace_status,
            prior_failures=(request.snapshot.get("engineering") or {}).get(
                "prior_failures"
            ),
        )
        registered_checks = context["checks"]
        if settings.browser_support:
            context["runtime"]["browser"] = settings.browser_support
        context["skills"] = {
            "revision": skill_manifest["revision"],
            "manifest_sha256": skill_manifest["manifest_sha256"],
            "catalog": [
                {key: row[key] for key in ("name", "version", "sha256")}
                for row in skill_manifest["skills"]
            ],
            "loading": "on_demand_via_invoke_skill",
        }
        PrivateArtifactStore(settings.root / "private").put(
            f"{request.run_id}/engineering-skills.json",
            json.dumps(
                {
                    "manifest": skill_manifest,
                    "skills": [
                        skill.model_dump(mode="json") for skill in trusted_skills
                    ],
                },
                ensure_ascii=False,
            ).encode(),
        )
        checks_digest = check_revision(registered_checks)
        session_key = secrets.token_urlsafe(32)
        PrivateArtifactStore(settings.root / "private").put(
            f"{request.run_id}/session.key", session_key.encode()
        )
        containers, workspace, conversation, model_gate = [], None, None, None
        finished, messages, evidence, reason = [], [], [], "SDK_EXECUTION_FAILED"
        terminal_failures = {}
        diagnostics, checked_candidate = [], None
        automatic = any(check["kind"] == "automatic" for check in registered_checks)
        started = time.monotonic()
        deadline = started + settings.max_seconds

        def capture(event):
            invoked = engineering_skills.successful_invocation(
                getattr(event, "observation", None), skill_names
            )
            if invoked and invoked not in invoked_skills:
                invoked_skills.append(invoked)
            action = getattr(event, "action", None)
            if type(action).__name__ == "FinishAction":
                finished.append(action.message)
            # RemoteConversation may deliver assistant MessageEvents without FinishAction.
            kind = getattr(event, "kind", None) or type(event).__name__
            if kind in ("MessageEvent", "MessageAction") or type(event).__name__ == (
                "MessageEvent"
            ):
                llm_message = getattr(event, "llm_message", None)
                content = getattr(llm_message, "content", None) if llm_message else None
                if content is None and isinstance(
                    getattr(event, "llm_message", None), dict
                ):
                    content = event.llm_message.get("content")
                texts = []
                for item in content or []:
                    if isinstance(item, dict) and item.get("type") == "text":
                        texts.append(item.get("text") or "")
                    else:
                        text = getattr(item, "text", None)
                        if text:
                            texts.append(text)
                joined = "\n".join(texts).strip()
                if joined:
                    messages.append(joined)
            observed = eng.terminal_evidence(getattr(event, "observation", None))
            if observed is not None:
                evidence.append(observed)
                if observed["command"] in check_commands:
                    terminal_failures[observed["command"]] = (
                        (getattr(event.observation, "text", "") or "")[-1600:]
                        if observed["exit_code"] != 0 or observed["timeout"]
                        else ""
                    )

        try:
            workspace = self._open_workspace(
                request, workspace_path, session_path, session_key, containers
            )
            disable_remote_autotitle(workspace)
            register_tool(TerminalTool.name, TerminalTool)
            register_tool(FileEditorTool.name, FileEditorTool)
            config = request.snapshot["config"]
            limit = min(settings.max_requests, int(config.get("max_requests", 20)))
            model_gate = start_run_model_gate(
                settings,
                config["base_url"],
                limit,
                min(int(config.get("timeout_seconds", 60)), 120),
            )
            llm = LLM(
                model=request.snapshot["model_profile"]["model"],
                model_canonical_name=(
                    "xiaomi_mimo/"
                    + request.snapshot["model_profile"]["model"].removeprefix("openai/")
                    if request.snapshot["model_profile"].get("provider") == "mimo"
                    else None
                ),
                api_key=SecretStr(credential),
                base_url=model_gate.base_url,
                num_retries=0,
                timeout=min(int(config.get("timeout_seconds", 60)), 120),
                max_output_tokens=(
                    8192
                    if request.snapshot["model_profile"].get("provider") == "mimo"
                    else 4096
                ),
                litellm_extra_body=(
                    {"thinking": {"type": "disabled"}}
                    if request.snapshot["model_profile"].get("provider") == "mimo"
                    else {}
                ),
            )
            if request.snapshot["model_profile"].get("provider") == "mimo":
                pricing = llm.model_info or {}
                input_cost = pricing.get("input_cost_per_token")
                output_cost = pricing.get("output_cost_per_token")
                if not input_cost or not output_cost:
                    raise RuntimeUnavailable(
                        "MiMo model pricing metadata is unavailable"
                    )
                # Serialize explicit costs to the pinned remote Agent Server.
                # Its LiteLLM route uses the OpenAI-compatible model alias.
                llm.input_cost_per_token = input_cost
                llm.output_cost_per_token = output_cost
            agent = Agent(
                llm=llm,
                tools=[Tool(name=TerminalTool.name), Tool(name=FileEditorTool.name)],
                agent_context=AgentContext(
                    **eng.agent_context_kwargs(context), skills=trusted_skills
                ),
                condenser=None,
                tool_concurrency_limit=1,
            )
            reserve = min(7, (limit + 2) // 3) if automatic and limit >= 3 else 0
            check_commands = {
                c["command"] for c in registered_checks if c["kind"] == "automatic"
            }
            prompt = eng.user_prompt(context)
            private = PrivateArtifactStore(settings.root / "private")
            closeout_evidence, closeout_digest = None, None
            for phase, allowance in enumerate((limit - reserve, reserve)):
                if model_gate.remaining <= 0:
                    reason = "REQUEST_BUDGET_EXHAUSTED"
                    break
                if not allowance or (halt := _control_halt(stop, deadline)):
                    if allowance:
                        reason = halt
                    break
                finished, messages = [], []
                evidence = (
                    list(closeout_evidence) if closeout_evidence is not None else []
                )
                terminal_failures = {}
                checked_candidate = None
                phase_agent = agent
                if closeout_evidence is not None:
                    phase_agent = Agent(
                        llm=llm,
                        tools=[],
                        agent_context=AgentContext(
                            **eng.agent_context_kwargs(context),
                            skills=[
                                skill
                                for skill in trusted_skills
                                if skill.name
                                in (
                                    "verification-before-completion",
                                    "onefde-engineering-closeout",
                                )
                            ],
                        ),
                        condenser=None,
                        tool_concurrency_limit=1,
                    )
                conversation = Conversation(
                    agent=phase_agent,
                    workspace=workspace,
                    conversation_id=uuid4() if phase else request.run_id,
                    callbacks=[capture],
                    visualizer=None,
                    delete_on_close=False,
                    max_iteration_per_run=allowance,
                    max_budget_per_run=settings.max_cost_usd * allowance / limit,
                )
                conversation.send_message(prompt)
                refused_before = model_gate.refused
                reason = _run_conversation(
                    conversation, stop, deadline, settings.poll_seconds
                )
                if reason != "FINISHED" and model_gate.refused > refused_before:
                    reason = "REQUEST_BUDGET_EXHAUSTED"
                    break
                if (
                    closeout_digest is not None
                    and eng.workspace_digest(workspace_path) != closeout_digest
                ):
                    reason = "CANDIDATE_CHANGED_AFTER_CHECK"
                    break
                if (
                    reason == "ITERATION_LIMIT_REACHED"
                    and not phase
                    and reserve
                    and automatic
                    and not eng.submission_diagnostics(registered_checks, evidence)
                ):
                    closeout_evidence = list(evidence)
                    closeout_digest = eng.workspace_digest(workspace_path)
                    private.put(
                        f"{request.run_id}/bounded-closeout.json",
                        json.dumps(
                            {
                                "remaining_iterations": reserve,
                                "source_digest": closeout_digest,
                                "file_and_terminal_tools": False,
                            }
                        ).encode(),
                    )
                    conversation.close()
                    conversation = None
                    prompt = eng.user_prompt(context) + (
                        "\nThe implementation phase reached its iteration allowance after "
                        "the registered checks passed. Use this final bounded allowance "
                        "to submit the required structured result through finish. The "
                        "registered checks have already passed and source editing tools "
                        "are unavailable in this phase. Independent fixed-source validation "
                        "will still run after your submission. The owner handles browser "
                        "review. Do not explore or request additional tools. Finish message "
                        "must be JSON with outcome=submitted and a factual summary."
                    )
                    continue
                if reason != "FINISHED" or not automatic:
                    break
                try:
                    proposal = eng.parse_proposal((finished or messages or [None])[-1])
                except (ValueError, TypeError):
                    break  # Preserve the existing invalid-result classification.
                if proposal.get("outcome") != "submitted":
                    break
                failures = eng.submission_diagnostics(registered_checks, evidence)
                output = {
                    item["id"]: terminal_failures[item["command"]]
                    for item in failures
                    if terminal_failures.get(item["command"])
                }
                candidate, count = archive_workspace(
                    workspace_path, settings.max_artifact_bytes
                )
                candidate_sha = hashlib.sha256(candidate).hexdigest()
                if not failures and count:
                    validation = self._validate_fixed_source(
                        request,
                        candidate,
                        registered_checks,
                        containers,
                        stop,
                        deadline,
                        phase=phase,
                        failure_output=output,
                    )
                    validation["candidate_sha256"] = candidate_sha
                    validation["check_revision"] = checks_digest
                    validation["spec_version"] = request.snapshot["spec_version"]
                    checked_candidate = (candidate, validation)
                    if validation["passed"]:
                        break
                    if validation["error_code"] != "FIXED_VALIDATION_FAILED":
                        break  # Isolation, stop, source mutation and deadline are hard gates.
                    failures = eng.submission_diagnostics(
                        registered_checks, evidence, validation
                    )
                elif not failures:
                    failures = [{"status": "source_missing"}]
                for secret in (credential, session_key):
                    output = {
                        key: value.replace(secret, "[REDACTED]")
                        for key, value in output.items()
                    }
                diagnostic = {
                    "phase": phase + 1,
                    "candidate_sha256": candidate_sha,
                    "check_revision": checks_digest,
                    "spec_version": request.snapshot["spec_version"],
                    "checks": failures,
                }
                diagnostics.append(diagnostic)
                private.put(
                    f"{request.run_id}/submission-check-{phase + 1}.json",
                    json.dumps(
                        {**diagnostic, "output": output}, ensure_ascii=False
                    ).encode(),
                )
                if phase or not reserve:
                    break
                conversation.close()
                conversation = None
                prompt = eng.repair_prompt(context, diagnostic, output)
        except Exception:
            reason = "SDK_EXECUTION_FAILED"
        finally:
            engineering_id = next(
                (
                    item["container_id"]
                    for item in containers
                    if item.get("role") == "engineering"
                ),
                containers[0]["container_id"] if containers else None,
            )
            stopped = confirm_stopped(engineering_id)
            if conversation is not None:
                try:
                    conversation.close()
                except Exception:
                    pass
            if (
                settings.execution_mode == "ecs_shared"
                and workspace is not None
                and stopped
            ):
                workspace.cleanup()
            if model_gate is not None:
                model_gate.close()

        proof = {
            "stopped": stopped,
            "method": "docker-stop-and-inventory",
            "resources": list(containers),
            "checks": evidence,
            "context_revisions": context["revisions"],
            "skills": {**context["skills"], "invoked": invoked_skills},
            "workspace": gate,
            "submission_diagnostics": diagnostics,
            "stop_reason": reason,
        }
        if model_gate is not None:
            proof["model_requests"] = {
                "limit": model_gate.limit,
                "forwarded": model_gate.forwarded,
                "refused": model_gate.refused,
                "shared_by_run": True,
            }
        if not stopped:
            return ExecutionReport(
                {
                    "state": "interrupted",
                    "summary": "工程现场停止状态未核实",
                    "error_code": "STOP_UNCONFIRMED",
                    "stopped": False,
                },
                proof=proof,
            )
        return self._finalize_stopped_run(
            request,
            stop,
            deadline,
            workspace_path,
            containers,
            proof,
            reason=reason,
            finished=finished,
            messages=messages,
            evidence=evidence,
            checks=registered_checks,
            credential=credential,
            session_key=session_key,
            checked_candidate=checked_candidate,
            checkpoint_required=automatic,
        )
