import { Alert, Button, Input } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  adapterLabel,
  api,
  postJson,
  problem,
  queryKeys,
  type DialoguePage,
  type FdeWorkView,
  type RuntimeStatus,
  type StaffTurn,
} from "../../api";
import { PendingActionCard, hasPendingAction } from "../dialogue/PendingAction";

const VERDICT_LABEL = {
  accept: "建议接受",
  request_changes: "建议修改",
  needs_human_check: "待人工核查",
} as const;

type Props = {
  engagementId: string;
  caseId: string | null;
  selectedWorkId?: string | null;
};

type Line = { id: string; role: "user" | "fde"; text: string };

function linesFor(item: FdeWorkView): Line[] {
  const lines: Line[] = [
    { id: `${item.id}-goal`, role: "user", text: `目标 · ${item.goal || "沿用已批准交接，未另写目标。"}` },
  ];
  if (item.state === "pending") {
    lines.push({ id: `${item.id}-wait`, role: "fde", text: "已登记，状态是待处理。没有消费者时不会自动生成报告。" });
  }
  if (item.state === "processing") lines.push({ id: `${item.id}-run`, role: "fde", text: "状态是处理中。这是当前租约，不是已完成。" });
  if (item.report.summary) lines.push({ id: `${item.id}-report`, role: "fde", text: `报告 · ${item.report.summary}` });
  if (item.report.error) lines.push({ id: `${item.id}-error`, role: "fde", text: `失败 · ${item.report.error}` });
  if (item.report.clarification?.public_reply) {
    lines.push({
      id: `${item.id}-clarify`,
      role: "fde",
      text: `澄清草稿 · ${item.report.clarification.public_reply}`,
    });
  }
  if (item.report.review_suggestion) {
    const suggestion = item.report.review_suggestion;
    lines.push({
      id: `${item.id}-suggestion`,
      role: "fde",
      text: `评审建议（非正式）· ${VERDICT_LABEL[suggestion.verdict]}：${suggestion.reason} ${suggestion.next_step}`,
    });
  }
  if (item.state === "reported" && !item.report.summary && !item.report.error) {
    lines.push({ id: `${item.id}-empty`, role: "fde", text: "本轮已报告，但没有可展示摘要。" });
  }
  return lines;
}

export function FdeWorkPanel({ engagementId, caseId, selectedWorkId }: Props) {
  const client = useQueryClient();
  const [, setParams] = useSearchParams();
  const [goal, setGoal] = useState("");
  const [question, setQuestion] = useState("");
  const scroller = useRef<HTMLDivElement>(null);
  const request = useRef<{ body: string; key: string } | null>(null);
  const askKey = useRef<{ body: string; key: string } | null>(null);
  const path = `/api/v1/engagements/${engagementId}/fde/work`;
  const queryKey = queryKeys.fdeWork(engagementId);

  const work = useQuery({
    queryKey,
    queryFn: () => api<FdeWorkView[]>(path),
    refetchOnWindowFocus: true,
    refetchInterval: (query) => {
      if (document.hidden) return false;
      const items = query.state.data ?? [];
      return items.some((item) => item.state === "pending" || item.state === "processing") ? 4000 : false;
    },
  });
  const listed = work.data ?? [];
  const missingSelection = Boolean(selectedWorkId && work.isSuccess && !listed.some((item) => item.id === selectedWorkId));
  const single = useQuery({
    queryKey: [...queryKey, "one", selectedWorkId],
    enabled: missingSelection,
    queryFn: () => api<FdeWorkView>(`${path}/${selectedWorkId}`),
    refetchInterval: (query) => {
      if (document.hidden) return false;
      const state = query.state.data?.state;
      return state === "pending" || state === "processing" ? 4000 : false;
    },
  });

  const dialogue = useQuery({
    queryKey: [...queryKey, "dialogue"],
    queryFn: () => api<DialoguePage>(`/api/v1/engagements/${engagementId}/fde/dialogue`),
    refetchInterval: (query) => {
      if (document.hidden) return false;
      return hasPendingAction(query.state.data?.turns) ? 4000 : false;
    },
  });
  const runtime = useQuery({
    queryKey: queryKeys.runtimeStatus,
    queryFn: () => api<RuntimeStatus>("/api/v1/runtime/status"),
    refetchInterval: () => (document.hidden ? false : 15000),
  });
  const dispatchKey = useRef<{ body: string; key: string } | null>(null);
  const decisionKey = useRef<{ body: string; key: string } | null>(null);
  const [deciding, setDeciding] = useState(false);
  async function decide(turnId: string, choice: "confirm" | "decline") {
    const body = JSON.stringify({ turnId, decision: choice });
    if (decisionKey.current?.body !== body) decisionKey.current = { body, key: crypto.randomUUID() };
    setDeciding(true);
    try {
      await postJson(`/api/v1/dialogue/turns/${turnId}/decision`, { decision: choice }, decisionKey.current.key);
      decisionKey.current = null;
      await client.invalidateQueries({ queryKey: [...queryKey, "dialogue"] });
      await client.invalidateQueries({ queryKey });
    } finally {
      setDeciding(false);
    }
  }
  const dispatch = useMutation({
    mutationFn: (input: { workId: string; decision: "confirm" | "decline" }) => {
      const body = JSON.stringify(input);
      if (dispatchKey.current?.body !== body) dispatchKey.current = { body, key: crypto.randomUUID() };
      return postJson<FdeWorkView>(
        `${path}/${input.workId}/dispatch`,
        { decision: input.decision },
        dispatchKey.current.key,
      );
    },
    onSuccess: async () => {
      dispatchKey.current = null;
      await client.invalidateQueries({ queryKey });
      await client.invalidateQueries({ queryKey: queryKeys.delivery(engagementId) });
    },
  });
  const ask = useMutation({
    mutationFn: (text: string) => {
      const body = JSON.stringify({ text });
      if (askKey.current?.body !== body) askKey.current = { body, key: crypto.randomUUID() };
      return postJson<DialoguePage>(
        `/api/v1/engagements/${engagementId}/fde/dialogue`,
        { text },
        askKey.current.key,
      );
    },
    onSuccess: async () => {
      askKey.current = null;
      setQuestion("");
      await client.invalidateQueries({ queryKey: [...queryKey, "dialogue"] });
    },
  });

  const start = useMutation({
    mutationFn: (goal?: string) => {
      const body = JSON.stringify({ goal: goal?.trim() || null, case_id: caseId });
      if (request.current?.body !== body) request.current = { body, key: crypto.randomUUID() };
      return api<FdeWorkView>(path, {
        method: "POST",
        body,
        headers: { "Idempotency-Key": request.current.key },
      });
    },
    onSuccess: async (created) => {
      request.current = null;
      setGoal("");
      setParams((current) => {
        const next = new URLSearchParams(current);
        next.set("work", created.id);
        return next;
      });
      await client.invalidateQueries({ queryKey });
      await client.invalidateQueries({ queryKey: queryKeys.delivery(engagementId) });
    },
  });

  const existingCase = Boolean(caseId && listed.some((item) => item.case_id === caseId));
  const current = useMemo(() => {
    if (selectedWorkId) return listed.find((item) => item.id === selectedWorkId) ?? single.data ?? null;
    return listed[0] ?? null;
  }, [listed, selectedWorkId, single.data]);
  const thread = useMemo(() => (current ? linesFor(current) : []), [current]);
  const threadKey = thread.map((line) => line.id + line.text).join("|");

  useEffect(() => {
    const node = scroller.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [threadKey, dialogue.data?.turns.length]);
  const consumer = runtime.data?.fde_agent;

  const blocked = existingCase || !work.isSuccess;
  const needsGoal = !caseId;

  return (
    <section className="eng-chat-col" aria-label="与 FDE 对话">
      <header className="eng-chat-head">
        <strong>FDE</strong>
        <span>一项工作的目标与报告</span>
        {listed.length > 1 ? (
          <select
            aria-label="选择 FDE 工作"
            value={current?.id ?? ""}
            onChange={(event) => {
              const value = event.target.value;
              setParams((params) => {
                const next = new URLSearchParams(params);
                if (value) next.set("work", value);
                else next.delete("work");
                return next;
              });
            }}
          >
            {listed.map((item, index) => (
              <option key={item.id} value={item.id}>
                {item.state} · {(item.goal || "交接").slice(0, 42)}
                {index === 0 ? "" : ""}
              </option>
            ))}
          </select>
        ) : null}
      </header>
      <div className="eng-chat-log" ref={scroller}>
        {work.isError || single.isError ? (
          <Alert
            type="error"
            showIcon
            message={problem(work.error ?? single.error)}
            action={
              <Button
                size="small"
                onClick={() => {
                  void work.refetch();
                  void single.refetch();
                }}
              >
                重试
              </Button>
            }
          />
        ) : null}
        {caseId ? (
          <p className="eng-chat-notice">
            来源 <Link to={`/business/${caseId}`}>Business 原会话</Link>
          </p>
        ) : null}
        {consumer ? (
          <p className="eng-chat-notice">
            {consumer.state === "running"
              ? `消费者最近 ${consumer.age_seconds ?? 0} 秒内有心跳。`
              : consumer.detail}
          </p>
        ) : null}
        {current?.report.pending_dispatch?.status === "pending" ? (
          <div className="eng-chat-notice">
            <p>{current.report.pending_dispatch.impact || "工程运行等待确认。"}</p>
            <p>
              动作 {current.report.pending_dispatch.command} · 任务 {current.report.pending_dispatch.task_id} · 修订{" "}
              {current.report.pending_dispatch.expected_revision} · 规格 {current.report.pending_dispatch.spec_version}
            </p>
            <Button
              size="small"
              type="primary"
              loading={dispatch.isPending}
              onClick={() => current && dispatch.mutate({ workId: current.id, decision: "confirm" })}
            >
              确认执行
            </Button>{" "}
            <Button
              size="small"
              disabled={dispatch.isPending}
              onClick={() => current && dispatch.mutate({ workId: current.id, decision: "decline" })}
            >
              放弃
            </Button>
          </div>
        ) : null}
        {current?.report.pending_dispatch?.status === "confirmed" ? (
          <p className="eng-chat-notice">派发已确认，运行 {current.report.pending_dispatch.run_id || "已记录"}。</p>
        ) : null}
        {current?.report.error ? (
          <p className="eng-chat-notice">失败 {current.report.error}。历史运行仍保留，重试会形成新的确认。</p>
        ) : null}
        {dialogue.data?.turns.map((turn: StaffTurn) => (
          <article key={turn.id} className={`eng-msg is-${turn.author === "assistant" ? "engineer" : "user"}`}>
            <p>
              {turn.author === "assistant" ? `${adapterLabel(turn.adapter)} · 未登记\n` : ""}
              {turn.text}
            </p>
            <PendingActionCard turn={turn} busy={deciding} onDecide={(id, choice) => void decide(id, choice)} />
          </article>
        ))}
        {dialogue.isError ? <Alert type="error" showIcon message={problem(dialogue.error)} /> : null}
        {!thread.length && !work.isPending ? (
          <article className="eng-msg is-engineer">
            <p>还没有 FDE 工作。下方会登记一项新目标，返回后保持待处理，直到有消费者写入报告。报告不是方案确认，也不是业务接受。</p>
          </article>
        ) : null}
        {thread.map((line) => (
          <article key={line.id} className={`eng-msg is-${line.role === "user" ? "user" : "engineer"}`}>
            <p>{line.text}</p>
          </article>
        ))}
      </div>
      <form
        className="eng-chat-composer"
        onSubmit={(event) => {
          event.preventDefault();
          const text = question.trim();
          if (!text || ask.isPending) return;
          ask.mutate(text);
        }}
      >
        <Input.TextArea
          value={question}
          rows={2}
          maxLength={4000}
          disabled={ask.isPending}
          placeholder="向 FDE 提问。这只保存问答，不会登记工作。"
          onChange={(event) => setQuestion(event.target.value)}
        />
        <Button htmlType="submit" loading={ask.isPending} disabled={!question.trim()}>
          提问
        </Button>
      </form>
      {ask.error ? <p className="eng-chat-notice">{problem(ask.error)}</p> : null}
      <form
        className="eng-chat-composer"
        onSubmit={(event) => {
          event.preventDefault();
          if (blocked || start.isPending) return;
          if (needsGoal && !goal.trim()) return;
          start.mutate(goal);
        }}
      >
        <Input.TextArea
          value={goal}
          rows={2}
          maxLength={4000}
          disabled={blocked || start.isPending}
          placeholder={
            existingCase
              ? "该原会话已有关联 FDE 工作，不再重复登记。"
              : caseId
                ? "可补充交付目标；留空则沿用已批准交接"
                : "说明要诊断、组织或澄清的交付目标"
          }
          onChange={(event) => setGoal(event.target.value)}
          onPressEnter={(event) => {
            if (!event.shiftKey) {
              event.preventDefault();
              if (!blocked && !start.isPending && (!needsGoal || goal.trim())) start.mutate(goal);
            }
          }}
        />
        <Button type="primary" htmlType="submit" loading={start.isPending} disabled={blocked || (needsGoal && !goal.trim())}>
          登记目标
        </Button>
      </form>
      {current?.trace.length ? (
        <p className="eng-chat-notice">
          工具回执 {current.trace.length} 条
          {current.calls != null ? ` · 调用 ${current.calls}` : ""}
          {current.usage ? ` · 用量已记录 ${Object.keys(current.usage).length} 项` : " · 未记录用量"}
          。这不是完整工具日志。
        </p>
      ) : null}
      {listed.length >= 50 ? <p className="eng-chat-notice">列表只含最近 50 条。地址里更早的工作会单独读取。</p> : null}
      {start.error ? <p className="eng-chat-notice">{problem(start.error)}</p> : null}
    </section>
  );
}
