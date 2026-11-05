"""Trusted Knowledge tool dispatch. Caller owns any DB transaction (handoffs are files)."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from onefde.core.errors import ApiException
from onefde.core.knowledge import DENIED_TOOL_NAMES, ROLE_REVISION, TOOL_NAMES
from onefde.modules.knowledge import access, catalog
from onefde.modules.knowledge import schemas as kn


def _forbidden(tool: str):
    if tool in DENIED_TOOL_NAMES:
        raise ApiException(
            403,
            "KNOWLEDGE_TOOL_FORBIDDEN",
            "该操作不在 Knowledge 受控工具白名单内",
            details={"tool": tool},
        )
    raise ApiException(
        403,
        "KNOWLEDGE_TOOL_UNKNOWN",
        "未知或不允许的 Knowledge 工具",
        details={"tool": tool},
    )


def _match(asset: dict, query: str) -> bool:
    q = query.strip().lower()
    if not q:
        return True
    hay = " ".join(
        [
            str(asset.get("id", "")),
            str(asset.get("name", "")),
            str(asset.get("problem", "")),
            " ".join(asset.get("keywords") or []),
        ]
    ).lower()
    return all(token in hay for token in q.split())


def _search(call: kn.KnowledgeToolCall) -> dict:
    query = str(call.arguments.get("query", ""))
    hits = []
    for asset in catalog.load_manifests():
        if not access.can_list(asset, purpose=call.purpose):
            continue
        if not _match(asset, query):
            continue
        hits.append(access.project_for_list(asset, purpose=call.purpose))
    return {"query": query, "purpose": call.purpose, "items": hits, "count": len(hits)}


def _get(call: kn.KnowledgeToolCall) -> dict:
    asset_id = str(call.arguments.get("asset_id", "")).strip()
    if not asset_id:
        raise ApiException(400, "KNOWLEDGE_BAD_ARGUMENTS", "get_asset 需要 asset_id")
    asset = catalog.get_manifest(asset_id)
    if asset is None:
        # Do not reveal whether a restricted id exists.
        raise ApiException(404, "NOT_FOUND", "资产不存在或不可见")
    projected = access.project_for_get(asset, purpose=call.purpose)
    if projected is None:
        raise ApiException(404, "NOT_FOUND", "资产不存在或不可见")
    return {"asset": projected}


_HANDOFF_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,60}$")


def handoff_root() -> Path:
    return catalog.repo_root() / "engagements" / "business-handoffs"


def _handoff(call: kn.KnowledgeToolCall, actor: str) -> dict:
    if call.caller_role != "business":
        raise ApiException(
            403,
            "KNOWLEDGE_ROLE_DENIED",
            "仅 Business 角色可记录经营交接（不派发工程）",
        )
    data = kn.BusinessHandoff.model_validate(call.arguments)
    slug = re.sub(r"[^a-z0-9]+", "-", data.title.lower()).strip("-")[:48] or "handoff"
    if not _HANDOFF_NAME.match(slug):
        slug = "handoff-" + uuid4().hex[:8]
    handoff_id = f"{slug}-{uuid4().hex[:8]}"
    root = handoff_root()
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{handoff_id}.md"
    lines = [
        f"# Business 交接：{data.title}",
        "",
        f"- ID: `{handoff_id}`",
        f"- 记录人: `{actor}`",
        f"- 时间: {datetime.now(timezone.utc).isoformat()}",
        f"- 模拟: {'是' if data.is_demo else '否'}",
        f"- 目标: {data.goal}",
        "",
        "## 来源",
        *[f"- {s}" for s in data.sources],
        "",
        "## 未知项",
        *(
            [f"- {u}" for u in data.unknowns]
            if data.unknowns
            else ["- （无）"]
        ),
        "",
        "## 说明",
        data.notes or "（无）",
        "",
        "## 边界",
        "- 本记录不构成价格/合同承诺。",
        "- 不直接派发客户工程；由 FDE 澄清后建 Task。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    rel = str(path)
    try:
        rel = str(path.relative_to(catalog.repo_root())).replace("\\", "/")
    except ValueError:
        rel = str(path).replace("\\", "/")
    meta = {
        "id": handoff_id,
        "path": rel,
        "title": data.title,
        "is_demo": data.is_demo,
        "sources": list(data.sources),
        "dispatched_engineering": False,
    }
    (root / f"{handoff_id}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return meta


_HANDLERS = {
    "search_assets": lambda call, actor: _search(call),
    "get_asset": lambda call, actor: _get(call),
    "record_business_handoff": _handoff,
}


def invoke(actor: str, call: kn.KnowledgeToolCall) -> kn.KnowledgeToolResult:
    if call.tool not in TOOL_NAMES or call.tool not in _HANDLERS:
        _forbidden(call.tool)
    payload = _HANDLERS[call.tool](call, actor)
    return kn.KnowledgeToolResult(
        tool=call.tool,
        role_revision=ROLE_REVISION,
        caller_role=call.caller_role,
        purpose=call.purpose,
        actor=actor,
        result=payload,
    )
