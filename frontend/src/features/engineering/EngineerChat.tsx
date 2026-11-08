import { Alert, Button, Input } from "antd";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  adapterLabel,
  api,
  conflictMessage,
  createIdempotencyGate,
  invalidateEngineering,
  postJson,
  problem,
  queryKeys,
  type DialoguePage,
  type Run,
  type RuntimeStatus,
  type RunEvent,
  type Task,
  type TaskInput,
  type TaskInputPage,
} from "../../api";
import { PendingActionCard, hasPendingAction } from "../dialogue/PendingAction";

type Props = {
  task: Task;
  run: Run | null | undefined;
  events: RunEvent[];
  readOnly: boolean;
};

type Bubble = {
  id: string;
  role: "user" | "engineer";
  text: string;
  at: string;
};

function bubbles(task: Task, inputs: TaskInput[], events: RunEvent[], run: Run | null | undefined): Bubble[] {
  const items: Bubble[] = [
    {
      id: "objective",
      role: "user",
      text: task.spec.objective || task.spec.title,
      at: "",
    },
  ];
  for (const input of inputs) {
    const fromEngineer = input.kind === "question" || input.author.startsWith("service:");
    const status = input.status === "applied" ? "已采用" : input.status === "rejected" ? "已拒绝" : "待处理";
    items.push({
      id: `in-${input.id}`,
      role: fromEngineer ? "engineer" : "user",
      text: `${input.kind} · ${status}${input.processing_reason ? ` · ${input.processing_reason}` : ""} · ${input.text}`,
      at: input.created_at,
    });
  }
  for (const event of events) {
    items.push({
      id: `ev-${event.id}`,
      role: "engineer",
      text: `活动摘要 · ${event.summary}`,
      at: event.created_at,
    });
  }
  if (run?.result_summary) {
    items.push({
      id: `sum-${run.id}`,
      role: "engineer",
      text: `结果摘要 · ${run.result_summary}`,
      at: run.created_at ?? "",
    });
  }
  return items.sort((a, b) => a.at.localeCompare(b.at));
}

export function EngineerChat({ task, run, events, readOnly }: Props) {
  const client = useQueryClient();
  const gate = useRef(createIdempotencyGate()).current;
  const scroller = useRef<HTMLDivElement>(null);
  const [text, setText] = useState("");
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState("处理当前输入");
  const [target, setTarget] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [deciding, setDeciding] = useState(false);
  const decisionGate = useRef(createIdempotencyGate()).current;

  const dialogue = useQuery({
    queryKey: [...queryKeys.task(task.id), "dialogue"],
    queryFn: () => api<DialoguePage>(`/api/v1/tasks/${task.id}/dialogue`),
    refetchInterval: (query) => {
      if (document.hidden) return false;
      if (hasPendingAction(query.state.data?.turns)) return 4000;
      return task.state === "running" || task.state === "queued" ? 4000 : false;
    },
  });
  const runtime = useQuery({
    queryKey: queryKeys.runtimeStatus,
    queryFn: () => api<RuntimeStatus>("/api/v1/runtime/status"),
    refetchInterval: () => (document.hidden ? false : 15000),
  });
  const askGate = useRef(createIdempotencyGate()).current;

  const inputs = useQuery({
    queryKey: queryKeys.taskInputs(task.id),
    queryFn: () => api<TaskInputPage>(`/api/v1/tasks/${task.id}/inputs?limit=100`),
    refetchInterval: () => (document.hidden ? false : task.state === "running" || task.state === "queued" ? 2000 : 10000),
  });

  const thread = useMemo(
    () => bubbles(task, inputs.data?.items ?? [], events, run),
    [events, inputs.data, run, task],
  );
  const pending = (inputs.data?.items ?? []).filter((item) => item.status === "pending");
  const openQuestion = pending.find((item) => item.kind === "question" && !item.resolved_by_input_id);
  const closed = task.state === "succeeded" || task.state === "cancelled";
  const locked = readOnly || closed;
  const canSettle = !locked && !task.active_run_id;

  useEffect(() => {
    const node = scroller.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [thread.length, dialogue.data?.turns.length]);

  async function ask() {
    const bodyText = question.trim();
    if (busy || asking || !bodyText) return;
    const body = { text: bodyText };
    setAsking(true);
    setNotice(undefined);
    try {
      await postJson(`/api/v1/tasks/${task.id}/dialogue`, body, askGate.keyFor(body));
      askGate.reset();
      setQuestion("");
      setNotice("已保存这次问答。没有追加输入，也没有启动运行。");
      await client.invalidateQueries({ queryKey: [...queryKeys.task(task.id), "dialogue"] });
    } catch (error) {
      setNotice(problem(error));
    } finally {
      setAsking(false);
    }
  }

  async function send() {
    const bodyText = text.trim();
    if (locked || busy || !bodyText) return;
    const body: Record<string, unknown> = {
      expected_revision: task.revision,
      kind: openQuestion ? "answer" : "clarification",
      text: bodyText,
      evidence_artifact_ids: [],
    };
    if (openQuestion) body.reply_to_input_id = openQuestion.id;
    setBusy(true);
    setNotice(undefined);
    try {
      await postJson(`/api/v1/tasks/${task.id}/inputs`, body, gate.keyFor(body));
      gate.reset();
      setText("");
      setNotice("已保存为待处理输入。尚未采用，也不会改正在执行的 Run。");
      await invalidateEngineering(client, {
        engagementId: task.engagement_id,
        taskId: task.id,
        runId: task.active_run_id ?? task.latest_run_id,
      });
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

  async function settle(kind: "apply" | "reject") {
    const item = pending.find((entry) => entry.id === (target || pending[0]?.id));
    if (!item || !canSettle || busy || !reason.trim()) return;
    if (kind === "apply" && item.kind === "question") {
      setNotice("采用问题必须同时采用对应答复。请选择一条答复。");
      return;
    }
    const body: Record<string, unknown> = {
      expected_revision: task.revision,
      apply_ids: kind === "apply" ? [item.id] : [],
      reject_ids: kind === "reject" ? [item.id] : [],
      reason: reason.trim(),
    };
    if (kind === "apply" && (item.kind === "clarification" || item.kind === "change_request")) {
      body.spec = task.spec;
    }
    setBusy(true);
    setNotice(undefined);
    try {
      await postJson(`/api/v1/tasks/${task.id}/apply-inputs`, body, gate.keyFor(body));
      gate.reset();
      await invalidateEngineering(client, {
        engagementId: task.engagement_id,
        taskId: task.id,
        runId: task.active_run_id ?? task.latest_run_id,
      });
      setNotice(kind === "apply" ? "已采用。澄清或修改要求会连同当前完整规格写入新版本。" : "已拒绝。拒绝不会提升规格版本。");
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

  async function decide(turnId: string, choice: "confirm" | "decline") {
    const body = { decision: choice };
    setDeciding(true);
    setNotice(undefined);
    try {
      await postJson(`/api/v1/dialogue/turns/${turnId}/decision`, body, decisionGate.keyFor({ turnId, ...body }));
      decisionGate.reset();
      await invalidateEngineering(client, {
        engagementId: task.engagement_id,
        taskId: task.id,
        runId: task.active_run_id ?? task.latest_run_id,
      });
      await client.invalidateQueries({ queryKey: [...queryKeys.task(task.id), "dialogue"] });
      setNotice(choice === "confirm" ? "已按这个对象执行。" : "已放弃这个对象。");
    } catch (error) {
      setNotice(conflictMessage(error) ?? problem(error));
    } finally {
      setDeciding(false);
    }
  }

  return (
    <section className="eng-chat-col" aria-label="与 Engineering 对话">
      <header className="eng-chat-head">
        <strong>Engineering</strong>
        <span>AI 软件工程师</span>
      </header>
      <div className="eng-chat-log" ref={scroller}>
        {inputs.isError ? (
          <Alert type="error" showIcon message={problem(inputs.error)} action={<Button size="small" onClick={() => inputs.refetch()}>重试</Button>} />
        ) : null}
        {thread.map((item) => (
          <article key={item.id} className={`eng-msg is-${item.role}`}>
            <p>{item.text}</p>
          </article>
        ))}
        {dialogue.data?.turns.map((turn) => (
          <article key={turn.id} className={`eng-msg is-${turn.author === "assistant" ? "engineer" : "user"}`}>
            <p>
              {turn.author === "assistant" ? `${adapterLabel(turn.adapter)} · 未执行\n` : ""}
              {turn.text}
            </p>
            <PendingActionCard turn={turn} busy={deciding || readOnly} onDecide={(id, choice) => void decide(id, choice)} />
          </article>
        ))}
        {dialogue.isError ? <Alert type="error" showIcon message={problem(dialogue.error)} /> : null}
      </div>
      {run?.state === "failed" ? (
        <p className="eng-chat-notice">
          运行失败{run.error_code ? `：${run.error_code}` : ""}。失败记录保留，重试会新建一轮并再次确认。
        </p>
      ) : null}
      <p className="eng-chat-notice">
        {runtime.data
          ? runtime.data.engineering_worker.state === "running"
            ? `Worker 最近 ${runtime.data.engineering_worker.age_seconds ?? 0} 秒内有心跳。`
            : runtime.data.engineering_worker.detail
          : "正在读取 Worker 心跳。"}
      </p>
      <form
        className="eng-chat-composer"
        onSubmit={(event) => {
          event.preventDefault();
          void ask();
        }}
      >
        <Input.TextArea
          value={question}
          rows={2}
          disabled={asking}
          placeholder="向 Engineering 提问。这不会保存为输入，也不会准备运行。"
          onChange={(event) => setQuestion(event.target.value)}
        />
        <Button htmlType="submit" loading={asking} disabled={asking || !question.trim()}>
          提问
        </Button>
      </form>
      <form
        className="eng-chat-composer"
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
      >
        <Input.TextArea
          value={text}
          rows={2}
          disabled={locked || busy}
          placeholder={
            closed
              ? "任务已结束，不能再写入。"
              : readOnly
                ? "历史轮次只读。"
                : openQuestion
                  ? `答复待处理问题：${openQuestion.text.slice(0, 80)}`
                  : "补充说明。保存后仍是待处理输入。"
          }
          onChange={(event) => setText(event.target.value)}
          onPressEnter={(event) => {
            if (!event.shiftKey) {
              event.preventDefault();
              void send();
            }
          }}
        />
        <Button type="primary" htmlType="submit" loading={busy} disabled={locked || !text.trim()}>
          保存输入
        </Button>
      </form>
      {pending.length && !locked ? (
        <div className="eng-chat-notice">
          <label>
            处理待处理输入
            <select value={target ?? pending[0]?.id} onChange={(event) => setTarget(event.target.value)}>
              {pending.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.kind} · {item.text.slice(0, 48)}
                </option>
              ))}
            </select>
          </label>
          <Input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="处理理由"
            disabled={!canSettle || busy}
          />
          <Button size="small" disabled={!canSettle || busy || !reason.trim()} onClick={() => void settle("apply")}>
            采用
          </Button>
          <Button size="small" disabled={!canSettle || busy || !reason.trim()} onClick={() => void settle("reject")}>
            拒绝
          </Button>
          {task.active_run_id ? <span>有活动 Run，不能采用或拒绝。可先停止本轮。</span> : null}
        </div>
      ) : null}
      {notice ? <p className="eng-chat-notice">{notice}</p> : null}
    </section>
  );
}
