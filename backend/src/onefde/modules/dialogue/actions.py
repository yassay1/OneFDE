"""Bind a staff proposal to the current anchor and execute only that object."""

from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import attributes

from onefde.core.errors import ApiException
from onefde.modules.business import operations, rules
from onefde.modules.business import schemas as business_schemas
from onefde.modules.business import service as cases
from onefde.modules.dialogue import models as dialogue_models
from onefde.modules.dialogue.schemas import StaffTurnView
from onefde.modules.fde.agent_schemas import StartWork
from onefde.modules.fde.agent_work import start as start_work
from onefde.modules.knowledge import tools as knowledge_tools
from onefde.modules.knowledge.schemas import KnowledgeToolCall
from onefde.modules.tasks import models as task_models
from onefde.modules.tasks import schemas as task_schemas
from onefde.modules.tasks import service as tasks
from onefde.modules.tasks.queries import require_task

_ALLOWED = {
    "business": {"handoff_case", "send_reply"},
    "fde": {
        "register_work",
        "commit_scope",
        "apply_inputs",
        "start_run",
        "continue_run",
        "retry_run",
        "accept_review",
        "request_changes",
        "record_knowledge_feedback",
    },
    "engineering": {
        "append_answer",
        "apply_inputs",
        "start_run",
        "continue_run",
        "retry_run",
    },
}
_IMMEDIATE = {"handoff_case", "register_work", "append_answer"}
_RUNS = {"start_run": "start", "continue_run": "continue", "retry_run": "retry"}


def _reject(basis, code):
    proposal = basis.get("proposal")
    basis["proposal_rejected"] = code
    basis["pending_action"] = None
    if isinstance(proposal, dict):
        basis["proposal"] = {"action": proposal.get("action"), "rejected": code}
    return basis


def _text(value, limit):
    return " ".join(str(value or "").split())[:limit]


def _uuid(value):
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _foreign(role, anchor, obj):
    if role == "business" and obj.get("case_id") not in (None, "", anchor):
        return True
    if role == "fde" and obj.get("engagement_id") not in (None, "", anchor):
        return True
    if role == "engineering" and obj.get("task_id") not in (None, "", anchor):
        return True
    return False


def _task_on_anchor(db, role, anchor, task_id):
    task = require_task(db, task_id)
    if role == "engineering" and str(task.id) != anchor:
        raise ApiException(409, "STAFF_ANCHOR_MISMATCH", "只能处理当前任务")
    if role == "fde" and str(task.engagement_id) != anchor:
        raise ApiException(409, "STAFF_ANCHOR_MISMATCH", "只能处理当前项目里的任务")
    return task


def _profile(db, value):
    identifier = _uuid(value)
    row = db.get(task_models.ModelProfileRevision, identifier) if identifier else None
    if row is None or row.integration_status == "unavailable":
        raise ApiException(409, "STAFF_PROFILE_UNAVAILABLE", "没有可用的模型修订")
    return row.revision_id


def settle(db, role, anchor, actor, question, context, text, basis):
    proposal = basis.get("proposal")
    if not isinstance(proposal, dict):
        return text, basis
    action = proposal.get("action")
    obj = proposal.get("object") if isinstance(proposal.get("object"), dict) else {}
    if action not in _ALLOWED.get(role, set()) or _foreign(role, anchor, obj):
        return text, _reject(basis, "anchor_or_role")
    impact = _text(proposal.get("impact"), 500) or _text(text, 500)
    try:
        if action in _IMMEDIATE:
            return _immediate(
                db, role, anchor, actor, question, context, text, basis, action, obj
            )
        pending = _hold(db, role, anchor, action, obj, impact)
    except (ApiException, ValidationError) as exc:
        code = exc.code if isinstance(exc, ApiException) else "STAFF_ACTION_INCOMPLETE"
        message = exc.message if isinstance(exc, ApiException) else "提案字段不完整"
        basis = _reject(basis, code)
        return text + f"\n没有执行：{message}", basis
    basis["pending_action"] = pending
    basis["proposal"] = {"action": action, "held": True}
    return text, basis


def _immediate(db, role, anchor, actor, question, context, text, basis, action, obj):
    if action == "handoff_case":
        return _handoff(db, anchor, actor, text, basis, obj)
    if action == "register_work":
        view = start_work(db, UUID(anchor), StartWork(goal=question), actor)
        basis["registered"] = True
        basis["work_id"] = str(view["id"])
        basis["proposal"] = {"action": action, "executed": True}
        return text, basis
    return _append_answer(db, anchor, actor, question, text, basis, obj)


def _handoff(db, anchor, actor, text, basis, obj):
    row = cases.case_for(db, UUID(anchor), lock=True)
    messages = cases.customer_messages(db, row)
    if row.handoff:
        basis["handoff_id"] = row.handoff.get("id")
        basis["proposal"] = {"action": "handoff_case", "executed": False}
        return text + "\n当前 Case 已有交接，没有新建。", basis
    ready, reason = _handoff_ready(row, messages, obj.get("confirmed_facts") or [])
    if not ready:
        basis["proposal_rejected"] = "facts_or_consent"
        basis["proposal"] = {"action": "handoff_case", "rejected": "facts_or_consent"}
        return text + f"\n需要确认：{reason}", basis
    facts = [item.strip() for item in obj["confirmed_facts"] if str(item).strip()]
    operations.handle(
        db,
        row,
        business_schemas.HandoffCommand(
            action="handoff",
            title=_text(obj.get("title"), 200) or _text(messages[-1].text, 80),
            goal=_text(obj.get("goal"), 4000) or _text(messages[-1].text, 500),
            confirmed_facts=facts,
            unknowns=[
                item.strip()
                for item in (obj.get("unknowns") or [])
                if str(item).strip()
            ],
            reproduction=_text(obj.get("reproduction"), 4000) or None,
        ),
        actor,
    )
    basis["handoff_id"] = row.handoff.get("id")
    basis["proposal"] = {"action": "handoff_case", "executed": True}
    return text, basis


def _handoff_ready(row, messages, facts):
    if not messages:
        return False, "当前 Case 还没有客户原话。"
    corpus = "\n".join(item.text for item in messages)
    clean = [str(item).strip() for item in facts if str(item).strip()]
    if not clean or any(item not in corpus for item in clean):
        return False, "交接事实必须来自当前 Case 的客户原话。"
    if row.invitation_id and row.workflow != "support":
        agreed = any(
            (item.reference or {}).get("willing_to_continue")
            and len(item.text.strip()) >= 8
            and rules.concrete(item.text, False)
            for item in messages
        )
        if not agreed:
            return False, "还没有客户的具体需求和继续意愿。"
    return True, ""


def _append_answer(db, anchor, actor, question, text, basis, obj):
    task = require_task(db, UUID(anchor))
    target = db.get(task_models.TaskInput, _uuid(obj.get("question_id")))
    if (
        target is None
        or target.task_id != task.id
        or target.kind != "question"
        or target.status != "pending"
    ):
        basis["proposal_rejected"] = "question_scope"
        basis["proposal"] = {"action": "append_answer", "rejected": "question_scope"}
        return text + "\n没有写入输入：要回答的问题不属于当前任务或已处理。", basis
    recorded = tasks.append_input(
        db,
        task.id,
        task_schemas.TaskInputCreate(
            expected_revision=task.revision,
            kind="answer",
            text=question,
            evidence_artifact_ids=[],
            reply_to_input_id=target.id,
        ),
        actor,
    )
    basis["input_created"] = True
    basis["input_id"] = str(recorded.input.id)
    basis["proposal"] = {"action": "append_answer", "executed": True}
    return text, basis


def _hold(db, role, anchor, action, obj, impact):
    pending = {
        "status": "pending",
        "action": action,
        "impact": impact,
        "object": {},
        "expected_revision": None,
        "spec_version": None,
    }
    if action == "send_reply":
        reply = _text(obj.get("text"), 4000)
        if not reply:
            raise ApiException(409, "STAFF_ACTION_INCOMPLETE", "对外回复没有具体正文")
        row = cases.case_for(db, UUID(anchor))
        pending["object"] = {
            "case_id": anchor,
            "text": reply,
            "state": row.state,
            "handler": row.handler,
        }
        return pending
    if action == "commit_scope":
        spec = _spec(obj)
        pending["object"] = {
            "engagement_id": anchor,
            "original_request": _text(obj.get("original_request"), 4000),
            "spec": spec.model_dump(mode="json"),
        }
        if not pending["object"]["original_request"]:
            raise ApiException(409, "STAFF_ACTION_INCOMPLETE", "范围承诺缺少原始请求")
        return pending
    if action == "record_knowledge_feedback":
        task = _task_on_anchor(db, role, anchor, _uuid(obj.get("task_id")))
        summary = _text(obj.get("summary"), 2000)
        sources = [
            str(item).strip() for item in obj.get("sources") or [] if str(item).strip()
        ]
        if not summary or not sources:
            raise ApiException(409, "STAFF_ACTION_INCOMPLETE", "经验反馈缺少摘要或来源")
        pending["object"] = {
            "task_id": str(task.id),
            "engagement_id": str(task.engagement_id),
            "summary": summary,
            "sources": sources[:12],
        }
        pending["expected_revision"] = task.revision
        pending["spec_version"] = task.spec_version
        return pending
    task = _task_on_anchor(db, role, anchor, _uuid(obj.get("task_id") or anchor))
    pending["expected_revision"] = task.revision
    pending["spec_version"] = task.spec_version
    if action == "apply_inputs":
        apply_ids = _id_list(obj.get("apply_ids"))
        reject_ids = _id_list(obj.get("reject_ids"))
        if not apply_ids and not reject_ids:
            raise ApiException(409, "STAFF_ACTION_INCOMPLETE", "没有要处理的输入")
        pending["object"] = {
            "task_id": str(task.id),
            "apply_ids": apply_ids,
            "reject_ids": reject_ids,
            "reason": _text(obj.get("reason"), 500) or "员工确认采用或拒绝",
        }
        return pending
    if action in _RUNS:
        profile = _profile(db, obj.get("model_profile_revision_id"))
        expected_run = _uuid(obj.get("expected_run_id") or task.latest_run_id)
        if _RUNS[action] != "start" and expected_run is None:
            raise ApiException(
                409, "STAFF_ACTION_INCOMPLETE", "继续或重试必须指向当前运行"
            )
        pending["object"] = {
            "task_id": str(task.id),
            "command": _RUNS[action],
            "model_profile_revision_id": str(profile),
            "expected_run_id": str(expected_run) if expected_run else None,
        }
        return pending
    verdict = "accept" if action == "accept_review" else "request_changes"
    evidence = [
        str(item).strip()
        for item in obj.get("check_evidence") or []
        if str(item).strip()
    ]
    artifacts = _id_list(obj.get("artifact_ids"))
    if not artifacts or not _text(obj.get("reason"), 1800):
        raise ApiException(409, "STAFF_ACTION_INCOMPLETE", "评审缺少产物或理由")
    if verdict == "accept" and not evidence:
        raise ApiException(409, "STAFF_ACTION_INCOMPLETE", "接受前必须写明检查证据")
    pending["object"] = {
        "task_id": str(task.id),
        "run_id": str(_uuid(obj.get("run_id") or task.latest_run_id)),
        "artifact_ids": artifacts,
        "verdict": verdict,
        "reason": _text(obj.get("reason"), 1800),
        "check_evidence": evidence,
    }
    if pending["object"]["run_id"] == "None":
        raise ApiException(409, "STAFF_ACTION_INCOMPLETE", "评审必须指向当前提交")
    return pending


def _spec(obj):
    raw = obj.get("spec") if isinstance(obj.get("spec"), dict) else obj
    return task_schemas.TaskSpec.model_validate(
        {
            "title": raw.get("title"),
            "objective": raw.get("objective"),
            "scope": raw.get("scope"),
            "inputs": raw.get("inputs") or [],
            "confirmed_rules": raw.get("confirmed_rules") or [],
            "completion_criteria": raw.get("completion_criteria") or [],
            "dependencies": [],
            "capability_versions": raw.get("capability_versions") or [],
        }
    )


def _id_list(values):
    found = []
    for item in values or []:
        identifier = _uuid(item)
        if identifier and str(identifier) not in found:
            found.append(str(identifier))
    return found


def decide(db, turn_id, decision, actor):
    turn = db.get(dialogue_models.StaffTurn, turn_id, with_for_update=True)
    pending = (turn.basis or {}).get("pending_action") if turn else None
    if (
        turn is None
        or turn.author != "assistant"
        or turn.adapter != "live"
        or not isinstance(pending, dict)
    ):
        raise ApiException(404, "NOT_FOUND", "没有可确认的员工提案")
    status = pending.get("status")
    if status != "pending":
        raise ApiException(409, "STAFF_ACTION_DECIDED", "这个动作已经处理过")
    if decision == "decline":
        pending = pending | {"status": "declined"}
        turn.basis = turn.basis | {"pending_action": pending}
        attributes.flag_modified(turn, "basis")
        return StaffTurnView.model_validate(turn)
    _execute(db, turn, pending, actor)
    return StaffTurnView.model_validate(turn)


def _execute(db, turn, pending, actor):
    action = pending["action"]
    obj = pending["object"]
    if action == "send_reply":
        row = cases.case_for(db, UUID(turn.anchor_id), lock=True)
        if row.state != obj["state"] or row.handler != obj["handler"]:
            raise ApiException(409, "STAFF_OBJECT_STALE", "会话状态已变化，请重新提案")
        operations.handle(
            db,
            row,
            business_schemas.StaffMessage(action="reply", text=obj["text"]),
            actor,
        )
        result = {"message": "reply"}
    elif action == "commit_scope":
        created = tasks.create_task(
            db,
            UUID(turn.anchor_id),
            task_schemas.TaskCreate(
                request_id=turn.id,
                task_key=f"staff-{turn.id.hex[:12]}",
                original_request=obj["original_request"],
                spec=task_schemas.TaskSpec.model_validate(obj["spec"]),
                owner_role="fde",
                executor_role="engineering",
            ),
            actor,
        )
        result = {"task_id": str(created.id)}
    elif action == "record_knowledge_feedback":
        task = require_task(db, UUID(obj["task_id"]))
        if task.revision != pending["expected_revision"]:
            raise ApiException(409, "STAFF_OBJECT_STALE", "任务修订已变化，请重新提案")
        recorded = knowledge_tools.invoke(
            actor,
            KnowledgeToolCall(
                tool="record_delivery_feedback",
                caller_role="fde",
                purpose="delivery",
                arguments=obj,
            ),
            db,
        )
        result = recorded.result
    elif action == "apply_inputs":
        task = require_task(db, UUID(obj["task_id"]))
        if task.revision != pending["expected_revision"]:
            raise ApiException(409, "STAFF_OBJECT_STALE", "任务修订已变化，请重新提案")
        applied = tasks.apply_inputs(
            db,
            task.id,
            task_schemas.TaskInputsApply(
                expected_revision=task.revision,
                apply_ids=[UUID(item) for item in obj["apply_ids"]],
                reject_ids=[UUID(item) for item in obj["reject_ids"]],
                reason=obj["reason"],
            ),
            actor,
        )
        result = {"revision": applied.task.revision}
    elif action in _RUNS:
        task = require_task(db, UUID(obj["task_id"]))
        if (
            task.revision != pending["expected_revision"]
            or task.spec_version != pending["spec_version"]
        ):
            raise ApiException(409, "STAFF_OBJECT_STALE", "任务修订已变化，请重新提案")
        accepted = _start(db, task, obj, actor)
        result = {
            "run_id": str(accepted.run.id) if accepted.run else None,
            "operation_id": str(accepted.operation_id),
        }
        turn.basis = turn.basis | {"run_started": True}
    else:
        task = require_task(db, UUID(obj["task_id"]))
        if (
            task.revision != pending["expected_revision"]
            or task.spec_version != pending["spec_version"]
        ):
            raise ApiException(409, "STAFF_OBJECT_STALE", "任务修订已变化，请重新提案")
        reviewed = tasks.review(
            db,
            task.id,
            task_schemas.TaskReviewCreate(
                expected_revision=task.revision,
                run_id=UUID(obj["run_id"]),
                task_spec_version=task.spec_version,
                artifact_ids=[UUID(item) for item in obj["artifact_ids"]],
                verdict=obj["verdict"],
                reason=obj["reason"],
                check_evidence=obj["check_evidence"],
            ),
            actor,
            role="founder",
        )
        result = {
            "review_id": str(reviewed.review.id),
            "state": reviewed.task.state,
        }
    if action == "send_reply":
        turn.basis = turn.basis | {"sent": True}
    pending = pending | {"status": "confirmed", "result": result}
    turn.basis = turn.basis | {"pending_action": pending}
    attributes.flag_modified(turn, "basis")


def _start(db, task, obj, actor):
    command = obj["command"]
    profile = UUID(obj["model_profile_revision_id"])
    if command == "start" and task.state == "draft":
        queued = tasks.action(
            db,
            task.id,
            task_schemas.TaskAction(
                command="queue",
                expected_revision=task.revision,
                expected_run_id=None,
            ),
            actor,
        )
        return tasks.action(
            db,
            task.id,
            task_schemas.TaskAction(
                command="start",
                expected_revision=queued.task.revision,
                expected_run_id=None,
                model_profile_revision_id=profile,
            ),
            actor,
        )
    return tasks.action(
        db,
        task.id,
        task_schemas.TaskAction(
            command=command,
            expected_revision=task.revision,
            expected_run_id=UUID(obj["expected_run_id"])
            if obj.get("expected_run_id")
            else None,
            model_profile_revision_id=profile,
        ),
        actor,
    )
