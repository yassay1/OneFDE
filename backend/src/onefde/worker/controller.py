import json
import logging
import threading

from sqlalchemy.orm import Session

from onefde.core.clock import now
from onefde.core.execution import ExecutionReport, ExecutionRequest, RuntimeUnavailable
from onefde.core.fde import QUOTE_SUPPORT_ACTOR
from onefde.infrastructure.artifacts import PrivateArtifactStore
from onefde.modules.engagements.queries import require_engagement
from onefde.modules.fde import agent_work
from onefde.modules.fde.quote_support import claim_allowed
from onefde.modules.tasks import service as tasks


class Worker:
    def __init__(self, engine, settings, adapter):
        self.engine, self.settings, self.adapter = engine, settings, adapter
        self.store = PrivateArtifactStore(settings.root / "artifacts")
        self.shutdown = threading.Event()
        self.last_admission = []

    def transaction(self, function, *args):
        with Session(self.engine, expire_on_commit=False) as db:
            with db.begin():
                return function(db, *args)

    def run_once(self, *, expected_run_id=None, reuse_only=False):
        if self.shutdown.is_set():
            return False
        issues = self.settings.capacity_blockers()
        if issues:
            if issues != self.last_admission:
                logging.getLogger(__name__).warning(
                    "Worker admission blocked: %s", issues
                )
            self.last_admission = issues
            return False
        self.last_admission = []

        def guard(db, run):
            engineering = run.snapshot.get("engineering", {})
            reuse = bool(engineering.get("reuse_asset"))
            return (
                reuse == reuse_only
                and (expected_run_id is None or run.id == expected_run_id)
                and claim_allowed(db, run)
                and agent_work.claim_allowed(db, run, self.settings.max_cost_usd)
                and (
                    not engineering.get("recovery_parent_run_id")
                    or (
                        self.settings.recovery_claim_allowed(
                            run.task_id, now(), engineering.get("recovery_policy")
                        )
                        and agent_work.isolated_demo_database(db)
                    )
                )
            )

        def authorize_recovery(db, run):
            if (
                not self.settings.recovery_allowed(run.task_id, now())
                or not agent_work.isolated_demo_database(db)
                or not require_engagement(db, claim["engagement_id"]).is_demo
                or run.snapshot.get("actor") == QUOTE_SUPPORT_ACTOR
            ):
                return None
            reserve = agent_work.reserve_recovery(db, run, self.settings.max_cost_usd)
            if reserve is None:
                return None
            return reserve, {
                "expires_at": self.settings.recovery_expires_at.isoformat(),
                "max_cost_usd": self.settings.max_cost_usd,
                "max_requests": self.settings.max_requests,
            }

        claim = self.transaction(
            tasks.claim_next,
            self.settings.worker_id,
            self.settings.lease_seconds,
            guard,
        )
        if claim is None:
            return False
        stop, done, lost, allocated = (threading.Event() for _ in range(4))
        args = (claim["operation_id"], self.settings.worker_id, claim["claim_token"])

        def resource(reference):
            allocated.set()
            self.transaction(tasks.register_resource, *args, reference)

        def heartbeat():
            while not done.is_set():
                try:
                    requested = self.transaction(
                        tasks.heartbeat_claim, *args, self.settings.lease_seconds
                    )
                    if requested or self.shutdown.is_set():
                        stop.set()
                except Exception:
                    # Database failure is not evidence of a stopped sandbox.
                    lost.set()
                    stop.set()
                if done.wait(self.settings.heartbeat_seconds):
                    return

        monitor = threading.Thread(
            target=heartbeat, name="onefde-lease-monitor", daemon=True
        )
        monitor.start()
        request = ExecutionRequest(
            operation_id=claim["operation_id"],
            run_id=claim["run_id"],
            task_id=claim["task_id"],
            engagement_id=claim["engagement_id"],
            snapshot=claim["snapshot"],
            on_resource=resource,
        )
        try:
            try:
                report = self.adapter.execute(request, stop)
            except RuntimeUnavailable:
                report = ExecutionReport(
                    {
                        "state": "interrupted" if allocated.is_set() else "failed",
                        "summary": "执行不可用；已分配资源的停止状态须核实"
                        if allocated.is_set()
                        else "执行配置不可用，尚未创建工程现场",
                        "error_code": "RUNTIME_UNCERTAIN"
                        if allocated.is_set()
                        else "RUNTIME_UNAVAILABLE",
                        "stopped": not allocated.is_set(),
                    },
                    proof={
                        "stopped": not allocated.is_set(),
                        "method": "uncertain"
                        if allocated.is_set()
                        else "not-allocated",
                    },
                )
            except Exception:
                report = ExecutionReport(
                    {
                        "state": "interrupted",
                        "summary": "执行适配异常，停止状态尚未核实",
                        "error_code": "RUNTIME_UNCERTAIN",
                        "stopped": False,
                    },
                    proof={"stopped": False},
                )
            try:
                for key, evidence in zip(
                    report.artifact_keys,
                    report.result.get("artifacts", []),
                    strict=True,
                ):
                    self.store.verify(key, evidence)
            except Exception:
                report = ExecutionReport(
                    {
                        "state": "failed"
                        if report.proof.get("stopped")
                        else "interrupted",
                        "summary": "产物持久化校验失败",
                        "error_code": "ARTIFACT_VERIFICATION_FAILED",
                        "stopped": bool(report.proof.get("stopped")),
                    },
                    proof=report.proof,
                )
            self.store.receipt(
                claim["run_id"],
                json.dumps(
                    {
                        "operation_id": str(claim["operation_id"]),
                        "result": report.result,
                        "artifact_keys": report.artifact_keys,
                        "proof": report.proof,
                    },
                    sort_keys=True,
                ).encode(),
            )
            if lost.is_set():
                # Never apply results after ownership became uncertain, even if adapter stopped.
                self.transaction(tasks.expire_claims)
                return True
            self.transaction(
                tasks.complete_claim,
                *args,
                report.result,
                report.artifact_keys,
                report.proof,
                authorize_recovery,
            )
            return True
        finally:
            done.set()
            monitor.join(timeout=self.settings.heartbeat_seconds + 5)
