import { Alert, Button, Input } from "antd";
import { useState, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { createIdempotencyGate, postJson, problem, queryKeys, type Task, type TaskSpec } from "../../api";
import { cleanSpec, TaskSpecFields } from "../../shared/TaskSpecFields";

export function CreateTask({ project, onCreated }: { project: string; onCreated: (id: string) => void }) {
  const client = useQueryClient(); const gate = useRef(createIdempotencyGate()).current;
  const requestId = useRef(crypto.randomUUID());
  const [original, setOriginal] = useState("");
  const [spec, setSpec] = useState<TaskSpec>({ title: "", objective: "", scope: "", inputs: [], confirmed_rules: [], completion_criteria: [], dependencies: [], capability_versions: [] });
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  async function save() {
    const cleaned = cleanSpec(spec);
    if (!original.trim() || !cleaned.title || !cleaned.objective || !cleaned.scope || !cleaned.completion_criteria.length) { setError("请填写原请求、标题、目标、范围和至少一项完成条件。"); return; }
    setBusy(true); setError("");
    const body = { request_id: requestId.current, task_key: "engineering", original_request: original.trim(), spec: cleaned, owner_role: "fde", executor_role: "engineering" };
    try {
      const task = await postJson<Task>(`/api/v1/engagements/${project}/tasks`, body, gate.keyFor(body));
      await client.invalidateQueries({ queryKey: queryKeys.delivery(project) });
      requestId.current = crypto.randomUUID(); gate.reset(); setOriginal("");
      setSpec({ title: "", objective: "", scope: "", inputs: [], confirmed_rules: [], completion_criteria: [], dependencies: [], capability_versions: [] });
      onCreated(task.id);
    } catch (e) { setError(problem(e)); } finally { setBusy(false); }
  }
  return <details className="work-panel create-task"><summary>新建工程任务</summary>
    <p className="eng-muted">以 FDE 所有者职责登记范围。保存后为草稿，不自动启动模型或发布。</p>
    <label className="eng-field">原请求与来源<Input.TextArea value={original} onChange={(e) => setOriginal(e.target.value)} rows={2} /></label>
    <TaskSpecFields spec={spec} onChange={setSpec} />{error && <Alert type="error" showIcon message={error} />}
    <Button type="primary" loading={busy} onClick={() => void save()}>保存任务草稿</Button>
  </details>;
}
