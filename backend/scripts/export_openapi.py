"""Export live Pydantic contract and merge it with explicitly planned operations.

Run from backend: uv run --locked python -m scripts.export_openapi [--check]
The untouched pre-implementation YAML is the comparison baseline, never a runtime router.
"""

import argparse
import copy
import json
from pathlib import Path

import yaml

from onefde.entrypoints.api import create_app

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/architecture"
METHODS = {"get", "post", "patch", "put", "delete"}


def deref(doc, value):
    if "$ref" in value:
        result = doc
        for part in value["$ref"][2:].split("/"):
            result = result[part]
        return result
    return value


def compare_fields(planned, actual):
    lines = []
    for name in [
        "EngagementCreate",
        "Engagement",
        "TaskSpec",
        "TaskCreate",
        "Task",
        "OwnerSession",
        "ApiError",
        "TaskAction",
        "ActionAccepted",
        "Run",
        "TaskInputCreate",
        "TaskInput",
        "TaskInputsApply",
        "TaskReviewCreate",
        "TaskReview",
        "TaskEvent",
        "RunEvent",
        "Artifact",
        "ModelProfile",
    ]:
        before, after = (
            planned["components"]["schemas"][name],
            actual["components"]["schemas"][name],
        )
        old, new = set(before["properties"]), set(after["properties"])
        missing = sorted(old - new)
        required_missing = sorted(
            set(before["required"]) - set(after.get("required", []))
        )
        if missing or required_missing:
            raise RuntimeError(
                f"{name}: lost fields {missing}, required {required_missing}"
            )
        lines.append(
            f"- {name}: 无缺失字段；原必填字段均保留。新增字段：{sorted(new - old)}。"
        )
    for path, item in actual["paths"].items():
        for method, operation in item.items():
            if method not in METHODS:
                continue
            before = planned["paths"].get(path, {}).get(method)
            if before is None:
                reviewed = {
                    "/api/v1/tasks/{task_id}/versions": "读取不可变版本快照",
                    "/api/v1/tasks/{task_id}/versions/{spec_version}": "读取不可变版本快照",
                    "/api/v1/engagements/{engagement_id}/delivery": "P1最小项目交付详情",
                    "/api/v1/engagements/{engagement_id}/fde/tools": "P1薄FDE受控工具调用",
                    "/api/v1/knowledge/tools": "P3 Knowledge受控工具调用",
                }
                if path not in reviewed:
                    raise RuntimeError("Unreviewed added operation: " + path)
                lines.append(
                    f"- 新增已实现接口：{method.upper()} `{path}`，用于{reviewed[path]}。"
                )
                continue
            assert operation["operationId"] == before["operationId"], (path, method)
            success = next(code for code in before["responses"] if code.startswith("2"))
            assert success in operation["responses"], (path, success)
            if "requestBody" in before:
                old = deref(
                    planned,
                    before["requestBody"]["content"]["application/json"]["schema"],
                )
                new = deref(
                    actual,
                    operation["requestBody"]["content"]["application/json"]["schema"],
                )
                assert set(old["properties"]) <= set(new["properties"]), (
                    path,
                    "request fields",
                )
                assert set(old["required"]) <= set(new["required"]), (
                    path,
                    "required request fields",
                )
    return lines


def artifacts():
    app = create_app()
    actual = app.openapi()
    app.state.engine.dispose()
    planned = yaml.safe_load(
        (DOCS / "openapi.planned.yaml").read_text(encoding="utf-8")
    )
    field_lines = compare_fields(planned, actual)
    merged = copy.deepcopy(planned)
    merged["info"] = actual["info"] | {
        "description": "C0+C1b 持久控制已实现；x-onefde-status=planned 的操作仅为后续设计，不在运行服务暴露。已实现字段由 FastAPI/Pydantic 导出。"
    }
    for name, definition in actual["components"]["schemas"].items():
        if (
            name in merged["components"]["schemas"]
            and definition != merged["components"]["schemas"][name]
        ):
            # Planned operations keep their original complete Task lifecycle schemas.
            renamed = "Planned" + name
            merged["components"]["schemas"][renamed] = merged["components"]["schemas"][
                name
            ]
            oldref, newref = (
                f"#/components/schemas/{name}",
                f"#/components/schemas/{renamed}",
            )

            def replace(node):
                if isinstance(node, dict):
                    for key, value in node.items():
                        if key == "$ref" and value == oldref:
                            node[key] = newref
                        else:
                            replace(value)
                elif isinstance(node, list):
                    for value in node:
                        replace(value)

            replace(merged["paths"])
            # Also preserve planned schema-to-schema references.
            replace(merged["components"]["schemas"])
    merged["components"]["schemas"].update(actual["components"]["schemas"])
    merged["components"]["securitySchemes"].update(
        actual["components"].get("securitySchemes", {})
    )
    for path, item in actual["paths"].items():
        if path not in merged["paths"]:
            merged["paths"][path] = copy.deepcopy(item)
    implemented, future = [], []
    for path, item in merged["paths"].items():
        for method, operation in list(item.items()):
            if method not in METHODS:
                continue
            if method in actual["paths"].get(path, {}):
                item[method] = copy.deepcopy(actual["paths"][path][method])
                item[method]["x-onefde-status"] = "implemented"
                if not item[method].get("security"):
                    item[method]["security"] = []
                implemented.append(f"- {method.upper()} `{path}`")
            else:
                operation["x-onefde-status"] = "planned"
                operation["description"] = "【规划中，当前服务未实现】" + operation.get(
                    "description", ""
                )
                future.append(f"- {method.upper()} `{path}`")
    report = "\n".join(
        [
            "# OneFDE OpenAPI 检查",
            "",
            "生成命令：`uv run --locked python -m scripts.export_openapi`。输入为运行时 Pydantic 与原始设计快照 `openapi.planned.yaml`。",
            "运行契约：`openapi.implemented.json`；同路径 `openapi.yaml` 合并后续设计并用 x-onefde-status 标记，不能用它推断未来接口可调用。",
            "",
            "## 字段与成功状态检查",
            "",
            *field_lines,
            "",
            "所有已实现操作的 operationId、成功状态码、请求字段和原必填字段已自动核对。",
            "",
            "## 已审阅适配差异",
            "",
            "- Task/Run由持久控制层维护；C2独立Worker消费作业与回填，无公共认领/伪成功回调。真实模型/隔离节点尚未验证，仍无前端。",
            "- 空白 title/goal/objective/scope/task_key/original_request/完成条件被拒绝；is_demo 不接受字符串布尔值。",
            "- related_task_id 输入额外接受 null，等同未提供；跨项目409，不存在404。Task 输出该字段总是存在。",
            "- X-CSRF-Token 保留必填/minLength=1；缺失/空值校验异常统一映射403，错误值同样403，不暴露框架错误正文。",
            "- Cookie 安全方案运行导出名 APIKeyCookie，安全 Cookie 名仍为 __Host-onefde_session；显式本地 HTTP 配置改用 onefde_dev_session。",
            "- Origin 与 JSON Content-Type 在依赖中校验；logout 无请求体，调用时仍应显式传 application/json。",
            "- 错误按具体状态列出 ApiError，details 可省略；JSON Schema anyOf/const 是 Pydantic 对 nullable/单值枚举的等价输出。",
            "- 列表游标按 created_at/id 升序，游标包含列表作用域；不是授权凭据，所有读取仍鉴权。",
            "- 版本列表/详情为两项显式新增接口；TaskInput 增加 processed_by/processing_reason/processed_at/resolved_by_input_id 供核查采用依据。",
            "- TaskAction/采用/评审等跨字段条件由Pydantic model_validator及领域服务检查，生成Schema不重复手写if/then。",
            "- Run完成/产物元数据由内部受控领域服务登记，无公开伪造成功接口；确定性适配仅用于测试。模型修订元数据当前通过部署供给/测试fixture写入，无编辑接口，列表不含配置/密钥。",
            "- Artifact只有元数据读取，无上传/签名下载；有原始证据时必须同项目，评审必须同Run。未认领作业可在事务内证明未执行并撤销；已开始的停止只记录意图，确认停止前保留占用。",
            "- 非空 dependencies 返回409 DEPENDENCIES_NOT_SUPPORTED；capability_versions 仅保存引用文本，尚无能力库校验。",
            "",
            f"## 已实现（{len(implemented)} 个操作）",
            "",
            *implemented,
            "",
            f"## 规划中（{len(future)} 个操作）",
            "",
            *future,
            "",
        ]
    )
    return {
        DOCS / "openapi.implemented.json": json.dumps(
            actual, ensure_ascii=False, indent=2
        )
        + "\n",
        DOCS / "openapi.yaml": yaml.safe_dump(
            merged, allow_unicode=True, sort_keys=False
        ),
        DOCS / "openapi-diff.md": report,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, content in artifacts().items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                raise SystemExit(f"Contract export is stale: {path.name}")
        else:
            path.write_text(content, encoding="utf-8")
        print(("checked " if args.check else "exported ") + path.name)


if __name__ == "__main__":
    main()
