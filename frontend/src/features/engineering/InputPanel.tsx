import { Alert, Button, Input, Select } from "antd";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";
import {
  api,
  conflictMessage,
  createIdempotencyGate,
  invalidateEngineering,
  postJson,
  problem,
  queryKeys,
  type Task,
  type TaskInput,
  type TaskInputPage,
  type TaskSpec,
} from "../../api";

type Props = {
  task: Task;
  readOnly: boolean;
};

const KIND_LABEL: Record<string, string> = {
  clarification: "澄清",
  change_request: "修改要求",
  question: "工程提问",
  answer: "答复",
};

const STATUS_LABEL: Record<string, string> = {
  pending: "待处理",
  applied: "已采用",
  rejected: "已拒绝",
};

export function InputPanel({ task, readOnly }: Props) {
  const client = useQueryClient();
  const appendGate = useRef(createIdempotencyGate()).current;
  const applyGate = useRef(createIdempotencyGate()).current;
  const [text, setText] = useState("");
  const [kind, setKind] = useState<"clarification" | "answer" | "change_request">("clarification");
  const [replyTo, setReplyTo] = useState<string>();
  const [applyReason, setApplyReason] = useState("采用当前待处理输入");
  const [notice, setNotice] = useState<string>();
  const [busy, setBusy] = useState(false);

  const inputs = useQuery({
    queryKey: queryKeys.taskInputs(task.id),
    queryFn: () => api<TaskInputPage>(`/api/v1/tasks/${task.id}/inputs?limit=100`),
    refetchInterval: () => {
      if (document.hidden) return false;
      return task.state === "waiting_input" || task.pending_input_count > 0 ? 10000 : false;
    },
  });

  const pending = useMemo(
    () => (inputs.data?.items ?? []).filter((item) => item.status === "pending"),
    [inputs.data],
  );
  const openQuestions = useMemo(
    () =>
      (inputs.data?.items ?? []).filter(
        (item) => item.kind === "question" && item.status === "pending" && !item.resolved_by_input_id,
      ),
    [inputs.data],
  );

  async function append() {
    if (readOnly || busy || !text.trim()) return;
    if (kind === "answer" && !replyTo) {
      setNotice("答复必须引用原问题。");
      return;
    }
    const body: Record<string, unknown> = {
      expected_revision: task.revision,
      kind,
      text: text.trim(),
      evidence_artifact_ids: [],
    };
    if (kind === "answer") body.reply_to_input_id = replyTo;
    setBusy(true);
    setNotice(undefined);
    try {
      await postJson(`/api/v1/tasks/${task.id}/inputs`, body, appendGate.keyFor(body));
      appendGate.reset();
      setText("");
      await invalidateEngineering(client, {
        engagementId: task.engagement_id,
        taskId: task.id,
        runId: task.active_run_id ?? task.latest_run_id,
      });
      setNotice("输入已记录为 pending，尚未进入规格。");
    } catch (error) {
      const conflict = conflictMessage(error);
      if (conflict) {
        await invalidateEngineering(client, { engagementId: task.engagement_id, taskId: task.id });
        setNotice(conflict);
      } else setNotice(problem(error));
    } finally {
      setBusy(false);
    }
  }

  async function applyPending(ids: string[], nextSpec?: TaskSpec) {
    if (readOnly || busy || !ids.length || !applyReason.trim()) return;
    const needsSpec = pending.some(
      (item) => ids.includes(item.id) && (item.kind === "clarification" || item.kind === "change_request"),
    );
    if (needsSpec && !nextSpec) {
      setNotice("采用澄清或修改要求时必须提交完整新规格。");
      return;
    }
    const body = {
      expected_revision: task.revision,
      apply_ids: ids,
      reject_ids: [] as string[],
      reason: applyReason.trim(),
      ...(needsSpec ? { spec: nextSpec } : {}),
    };
    setBusy(true);
    setNotice(undefined);
    try {
      await postJson(`/api/v1/tasks/${task.id}/apply-inputs`, body, applyGate.keyFor(body));
      applyGate.reset();
      await invalidateEngineering(client, {
        engagementId: task.engagement_id,
        taskId: task.id,
        runId: task.active_run_id ?? task.latest_run_id,
      });
      setNotice("已采用输入。规格版本已更新时，可再准备/继续执行。");
    } catch (error) {
      const conflict = conflictMessage(error);
      if (conflict) {
        await invalidateEngineering(client, { engagementId: task.engagement_id, taskId: task.id });
        setNotice(conflict);
      } else setNotice(problem(error));
    } finally {
      setBusy(false);
    }
  }

  const answerable = openQuestions.map((item) => ({
    value: item.id,
    label: `#${item.sequence} ${item.text.slice(0, 80)}`,
  }));

  return (
    <section className="eng-inputs" aria-label="任务输入">
      <h3>输入与问题</h3>
      {inputs.isError ? <Alert type="error" message={problem(inputs.error)} /> : null}
      <ul className="eng-input-list">
        {(inputs.data?.items ?? []).slice().reverse().map((item) => (
          <InputRow key={item.id} item={item} />
        ))}
      </ul>
      {!inputs.data?.items.length && !inputs.isLoading ? (
        <p className="eng-muted">还没有输入记录。</p>
      ) : null}

      {!readOnly ? (
        <div className="eng-composer">
          <div className="eng-composer-toolbar">
            <Select
              value={kind}
              style={{ minWidth: 140 }}
              options={[
                { value: "clarification", label: "补充澄清" },
                { value: "answer", label: "答复问题" },
                { value: "change_request", label: "修改要求" },
              ]}
              onChange={(value) => {
                setKind(value);
                if (value !== "answer") setReplyTo(undefined);
              }}
            />
            {kind === "answer" ? (
              <Select
                style={{ minWidth: 220 }}
                placeholder="引用原问题"
                value={replyTo}
                options={answerable}
                onChange={setReplyTo}
              />
            ) : null}
          </div>
          <Input.TextArea
            rows={3}
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder={
              kind === "answer"
                ? "答复工程提问…"
                : kind === "change_request"
                  ? "说明需要修改的内容…"
                  : "记录补充或澄清…"
            }
          />
          <div className="eng-composer-footer">
            <span>保存为 pending，不会热更新正在执行的 Run。</span>
            <Button type="primary" loading={busy} disabled={!text.trim()} onClick={append}>
              保存输入
            </Button>
          </div>
        </div>
      ) : null}

      {!readOnly && pending.length ? (
        <div className="eng-apply">
          <Input
            value={applyReason}
            onChange={(event) => setApplyReason(event.target.value)}
            placeholder="采用理由"
          />
          <div className="eng-apply-actions">
            <Button
              loading={busy}
              disabled={!applyReason.trim()}
              onClick={() => {
                const answers = pending.filter((item) => item.kind === "answer").map((item) => item.id);
                if (!answers.length) {
                  setNotice("当前待处理项需要完整新规格才能采用澄清/修改要求。请先在规格编辑中确认后再采用。");
                  return;
                }
                void applyPending(answers);
              }}
            >
              采用待处理答复
            </Button>
            <Button
              loading={busy}
              disabled={!applyReason.trim()}
              onClick={() => void applyPending(
                pending.map((item) => item.id),
                task.spec,
              )}
            >
              采用全部待处理（沿用当前完整规格）
            </Button>
          </div>
          <p className="eng-muted">
            采用 clarification / change_request 时服务端要求完整新 spec；上面第二按钮在范围未变时提交当前规格副本。
          </p>
        </div>
      ) : null}

      {notice ? <Alert type="info" showIcon message={notice} style={{ marginTop: 12 }} /> : null}
    </section>
  );
}

function InputRow({ item }: { item: TaskInput }) {
  return (
    <li className={`eng-input-row status-${item.status}`}>
      <div>
        <strong>
          {KIND_LABEL[item.kind] ?? item.kind} · {STATUS_LABEL[item.status] ?? item.status}
        </strong>
        <p>{item.text}</p>
        <small className="eng-muted">
          #{item.sequence}
          {item.reply_to_input_id ? ` · 答复 ${item.reply_to_input_id.slice(0, 8)}…` : ""}
          {item.applied_spec_version ? ` · 进入规格 v${item.applied_spec_version}` : ""}
        </small>
      </div>
    </li>
  );
}
