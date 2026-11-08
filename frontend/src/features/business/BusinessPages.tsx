import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Checkbox, Form, Input, Select } from "antd";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { adapterLabel, api, postJson, problem, queryKeys, type DialoguePage, type StaffTurn } from "../../api";
import { PendingActionCard, hasPendingAction } from "../dialogue/PendingAction";
import { useSession } from "../../app/session";
import { AsyncState } from "../../shared/AsyncState";
import { ContextTrail } from "../../shared/ContextTrail";
import { uuidOrEmpty } from "../../shared/ids";
import { bannerTone } from "../../shared/labels";

const STAFF = "/api/v1/business";
const OWNER: Record<string, string> = { business: "Business", founder: "创始人", fde: "FDE" };
const STATE: Record<string, string> = {
  open: "待跟进",
  clarifying: "待客户补充",
  founder_queue: "待创始人接手",
  fde_queue: "待 FDE 接手",
  handling: "处理中",
  awaiting_retest: "待客户复试",
  closed: "已关闭",
};
const WORKFLOW: Record<string, string> = {
  inquiry: "客户咨询",
  support: "售后",
  outreach: "演示邀请",
};
const MSG_KIND: Record<string, string> = {
  customer: "客户原话",
  reply: "对外回复",
  note: "内部备注",
};

function BusinessHero({
  title = "Business",
  subtitle = "客户、Case 与处理进度",
  status,
}: {
  title?: string;
  subtitle?: string;
  status?: string;
}) {
  const [sceneFailed, setSceneFailed] = useState(false);

  return (
    <header className="business-hero">
      <div className={`business-hero-scene${!sceneFailed ? " has-art" : ""}`} aria-hidden="true">
        <img
          className="business-hero-scene-img"
          src="/business-hero-scene.png"
          alt=""
          onLoad={() => setSceneFailed(false)}
          onError={(event) => {
            setSceneFailed(true);
            event.currentTarget.style.display = "none";
          }}
        />
        {sceneFailed ? (
          <div className="business-hero-scene-ph">
            <span>场景暂不可用</span>
          </div>
        ) : null}
      </div>
      <div className="business-hero-copy">
        <h1>{title}</h1>
        <p>{subtitle}</p>
        {status ? (
          <p className={`business-status-pill is-${bannerTone(status)}`}>
            <span className="business-status-dot" aria-hidden />
            {status}
          </p>
        ) : null}
      </div>
    </header>
  );
}

function stateTone(state: string) {
  if (state === "closed") return "done";
  if (state === "founder_queue" || state === "awaiting_retest") return "attention";
  if (state === "handling" || state === "fde_queue") return "active";
  return "idle";
}

type Summary = {
  id: string;
  source: string;
  workflow: string;
  state: string;
  owner: string;
  handler: string | null;
  next_step: string;
  created_at: string;
};
type Message = {
  id: number;
  kind: string;
  author: string;
  text: string;
  reference: Record<string, unknown> | null;
};
type Detail = Summary & {
  engagement_id: string | null;
  reported_version: string | null;
  task_id: string | null;
  invitation_id: string | null;
  handoff: {
    id: string;
    title: string;
    goal: string;
    sources: string[];
    confirmed_facts: string[];
    unknowns: string[];
    reproduction: string | null;
  } | null;
  retest: {
    version: string;
    steps: string;
    passed?: boolean;
    artifact_id: string;
    access_url: string;
  } | null;
  messages: Message[];
  has_more: boolean;
  last_message_id: number;
};
type Candidate = {
  id: string;
  source: string;
  name: string;
  address: string;
  reason: string;
  queried_at: string;
  invited_at: string | null;
};
type CasePage = { items: Summary[]; next_cursor: string | null };
type Values = Record<string, string | boolean | undefined>;

function loadCase(caseId: string) {
  return async () => {
    let page = await api<Detail>(`${STAFF}/cases/${caseId}`);
    const messages = [...page.messages];
    while (page.has_more) {
      page = await api<Detail>(`${STAFF}/cases/${caseId}?after=${page.last_message_id}`);
      messages.push(...page.messages);
    }
    return { ...page, messages };
  };
}

function CaseConversation({ caseId }: { caseId: string }) {
  const session = useSession();
  const username = session.data?.username ?? "";
  const query = useQueryClient();
  const { write, busy, error } = useWrite();
  const [text, setText] = useState("");
  const [askText, setAskText] = useState("");
  const [mode, setMode] = useState<"reply" | "note">("note");
  const [notice, setNotice] = useState<string>();
  const asker = useWrite();
  const decisionGate = useRef({ body: "", key: "" });
  const [deciding, setDeciding] = useState(false);
  const detail = useQuery({
    queryKey: queryKeys.businessCase(caseId),
    queryFn: loadCase(caseId),
    refetchInterval: () => (document.hidden ? false : 8000),
  });
  const assistant = useQuery({
    queryKey: [...queryKeys.businessCase(caseId), "assistant"],
    queryFn: () => api<DialoguePage>(`${STAFF}/cases/${caseId}/assistant`),
    refetchInterval: (query) => {
      if (document.hidden) return false;
      return hasPendingAction(query.state.data?.turns) ? 4000 : 8000;
    },
  });
  const item = detail.data;
  const canReply = Boolean(item && item.state === "handling" && item.handler === username && username);
  const closed = item?.state === "closed";

  useEffect(() => {
    if (!canReply) setMode("note");
  }, [canReply, caseId]);

  function ask() {
    const body = askText.trim();
    if (!item || asker.busy || !body) return;
    void asker.write<DialoguePage>(`${STAFF}/cases/${item.id}/assistant`, { text: body }, () => {
      setAskText("");
      setNotice("已记下这次问答。回复仍未发给客户。");
      void query.invalidateQueries({ queryKey: [...queryKeys.businessCase(caseId), "assistant"] });
    });
  }

  async function decide(turnId: string, choice: "confirm" | "decline") {
    const body = JSON.stringify({ decision: choice, turnId });
    if (decisionGate.current.body !== body) decisionGate.current = { body, key: crypto.randomUUID() };
    setDeciding(true);
    try {
      await postJson(`/api/v1/dialogue/turns/${turnId}/decision`, { decision: choice }, decisionGate.current.key);
      decisionGate.current = { body: "", key: "" };
      setNotice(choice === "confirm" ? "已按这个对象执行。" : "已放弃这个对象。");
      await query.invalidateQueries({ queryKey: [...queryKeys.businessCase(caseId), "assistant"] });
      await query.invalidateQueries({ queryKey: ["business"] });
    } catch (error) {
      setNotice(problem(error));
    } finally {
      setDeciding(false);
    }
  }

  function placeDraft(turn: StaffTurn) {
    const draft = turn.basis.draft_reply;
    if (!canReply || typeof draft !== "string" || !draft.trim()) return;
    setMode("reply");
    setText(draft);
    setNotice("草稿已放入回复框，尚未发送。");
  }

  function send() {
    if (!item || closed || busy || !text.trim()) return;
    const action = mode === "reply" && canReply ? "reply" : "note";
    void write<Detail>(`${STAFF}/cases/${item.id}/actions`, { action, text: text.trim() }, () => {
      setText("");
      setNotice(action === "reply" ? "已写入对外回复。" : "已写入内部备注，客户入口看不到。");
      void query.invalidateQueries({ queryKey: ["business"] });
    });
  }

  return (
    <>
      <div className="business-chat-thread" aria-live="polite">
        {detail.isPending ? <p className="eng-muted">正在读取这个 Case 的消息。</p> : null}
        {detail.error ? <Alert type="error" showIcon message={problem(detail.error)} /> : null}
        {item?.messages.map((message) => (
          <article
            key={message.id}
            className={`business-chat-bubble ${
              message.kind === "customer" ? "is-founder" : message.kind === "note" ? "is-note" : "is-business"
            }`}
          >
            <header>
              {message.kind === "reply" ? (
                <img src="/avatars/business.png" alt="" width={28} height={28} />
              ) : null}
              {MSG_KIND[message.kind] ?? message.kind} · {message.author}
            </header>
            <p>{message.text}</p>
          </article>
        ))}
        {item && !item.messages.length ? <p className="eng-muted">这个 Case 还没有消息。</p> : null}
        {assistant.data?.turns.map((turn) => (
          <article
            key={turn.id}
            className={`business-chat-bubble ${turn.author === "assistant" ? "is-business" : "is-founder"}`}
          >
            <header>
              {turn.author === "assistant" ? `${adapterLabel(turn.adapter)} · 未发送` : turn.author}
            </header>
            <p>{turn.text}</p>
            {turn.author === "assistant" && typeof turn.basis.draft_reply === "string" && canReply ? (
              <Button size="small" disabled={busy || asker.busy} onClick={() => placeDraft(turn)}>
                放入回复框
              </Button>
            ) : null}
            <PendingActionCard turn={turn} busy={deciding} onDecide={(id, choice) => void decide(id, choice)} />
          </article>
        ))}
        {assistant.error ? <Alert type="error" showIcon message={problem(assistant.error)} /> : null}
      </div>
      <form
        className="business-chat-composer"
        onSubmit={(event) => {
          event.preventDefault();
          ask();
        }}
      >
        <Input.TextArea
          value={askText}
          rows={2}
          disabled={!item || asker.busy}
          placeholder="问 Business。回答只依据这个 Case，不会发给客户。"
          onChange={(event) => setAskText(event.target.value)}
        />
        <Button htmlType="submit" loading={asker.busy} disabled={!item || !askText.trim()}>
          提问
        </Button>
      </form>
      {asker.error ? <Alert type="error" showIcon message={asker.error} /> : null}
      <form
        className="business-chat-composer"
        onSubmit={(event) => {
          event.preventDefault();
          send();
        }}
      >
        {canReply ? (
          <select
            aria-label="写入类型"
            value={mode}
            disabled={busy || closed}
            onChange={(event) => setMode(event.target.value === "reply" ? "reply" : "note")}
          >
            <option value="reply">对外回复</option>
            <option value="note">内部备注</option>
          </select>
        ) : null}
        <Input.TextArea
          value={text}
          rows={2}
          disabled={!item || closed || busy}
          placeholder={
            closed
              ? "会话已关闭，不能写入。"
              : canReply && mode === "reply"
                ? "写给客户的回复"
                : "内部备注，不会出现在客户入口"
          }
          onChange={(event) => setText(event.target.value)}
        />
        <Button type="primary" htmlType="submit" loading={busy} disabled={!item || closed || !text.trim()}>
          {canReply && mode === "reply" ? "发送回复" : "记下备注"}
        </Button>
      </form>
      {item && !canReply && !closed ? <p className="eng-chat-notice">当前不能对外回复。下一步：{item.next_step}</p> : null}
      {item ? (
        <p className="eng-chat-notice">
          <Link to={`/business/${item.id}`}>打开处理页</Link>
          ，交接、澄清和复试在那里按 Case 状态操作。
        </p>
      ) : null}
      {notice ? <p className="eng-chat-notice">{notice}</p> : null}
      {error ? <Alert type="error" showIcon message={error} /> : null}
    </>
  );
}

function useWrite() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const pending = useRef<{ fingerprint: string; key: string } | undefined>(undefined);
  const active = useRef(false);
  async function write<T>(url: string, data: Record<string, unknown>, success: (result: T) => void) {
    if (active.current) return;
    active.current = true;
    setBusy(true);
    setError(undefined);
    const fingerprint = JSON.stringify([url, data]);
    if (pending.current?.fingerprint !== fingerprint) {
      pending.current = { fingerprint, key: crypto.randomUUID() };
    }
    try {
      const result = await api<T>(url, {
        method: "POST",
        headers: { "Idempotency-Key": pending.current.key },
        body: JSON.stringify(data),
      });
      pending.current = undefined;
      success(result);
    } catch (caught) {
      setError(problem(caught));
    } finally {
      active.current = false;
      setBusy(false);
    }
  }
  return { write, busy, error };
}

function CandidateSearch({ productUrl }: { productUrl: string }) {
  const { write, busy, error } = useWrite();
  const [results, setResults] = useState<Candidate[]>();
  const [readError, setReadError] = useState<string>();
  const [form] = Form.useForm();
  async function loadCandidates() {
    try {
      const { adcode } = await form.validateFields(["adcode"]);
      const result = await api<{ items: Candidate[] }>(
        `${STAFF}/candidates?adcode=${encodeURIComponent(adcode)}`,
      );
      setResults(result.items);
      setReadError(undefined);
    } catch (caught) {
      setReadError(problem(caught));
    }
  }
  return (
    <section className="business-panel" aria-labelledby="candidate-heading">
      <h2 id="candidate-heading">主动找店</h2>
      <p>输入六位区县行政区划代码。生成邀请链接不等于已向外发送；需创始人自行分享。</p>
      <Form
        form={form}
        layout="vertical"
        onFinish={(data) => {
          setReadError(undefined);
          void write<{ items: Candidate[] }>(`${STAFF}/candidate-search`, data, (result) =>
            setResults(result.items),
          );
        }}
      >
        <Form.Item label="区县代码" name="adcode" rules={[{ required: true, pattern: /^[1-9][0-9]{5}$/ }]}>
          <Input inputMode="numeric" maxLength={6} placeholder="例如 440106" />
        </Form.Item>
        <Form.Item name="sample" valuePropName="checked">
          <Checkbox>使用模拟样例（非真实门店）</Checkbox>
        </Form.Item>
        <div className="actions">
          <Button type="primary" htmlType="submit" loading={busy}>
            搜索候选
          </Button>
          <Button onClick={() => void loadCandidates()} disabled={busy}>
            查看已保存候选
          </Button>
        </div>
      </Form>
      {error || readError ? <Alert type="error" showIcon message={error || readError} /> : null}
      {results?.length === 0 ? <p>该区县暂无候选。</p> : null}
      {results?.map((item) => {
        const link = new URL(productUrl);
        link.hash = new URLSearchParams({ invite: item.id }).toString();
        const sample = item.source === "sample";
        return (
          <article className="business-candidate" key={item.id}>
            <div className="business-candidate-head">
              <strong>{item.name}</strong>
              <span className={`status-badge ${sample ? "source-sample" : "source-live"}`}>
                {sample ? "模拟样例" : "高德 POI"}
              </span>
            </div>
            <p>
              {item.address} · {item.reason}
            </p>
            <p className="eng-muted">{new Date(item.queried_at).toLocaleString("zh-CN")}</p>
            {item.invited_at ? (
              <label>
                演示邀请链接（仅生成，未自动外发）
                <Input readOnly value={link.href} onFocus={(event) => event.currentTarget.select()} />
              </label>
            ) : (
              <Button
                disabled={busy}
                onClick={() =>
                  void write<Candidate>(`${STAFF}/candidates/${item.id}/invite`, {}, (updated) =>
                    setResults((list) => list?.map((row) => (row.id === item.id ? updated : row))),
                  )
                }
              >
                选店并生成演示邀请
              </Button>
            )}
          </article>
        );
      })}
    </section>
  );
}

export function BusinessInbox({ productUrl }: { productUrl: string }) {
  const [params, setParams] = useSearchParams();
  const cursor = params.get("cursor") ?? "";
  const workflow = params.get("workflow") ?? "";
  const state = params.get("state") ?? "";
  const owner = params.get("owner") ?? "";
  const caseId = uuidOrEmpty(params.get("case"));
  const view = params.get("view") ?? "workspace";

  const inbox = useQuery({
    queryKey: queryKeys.businessCases(cursor, workflow, state, owner),
    queryFn: () => {
      const search = new URLSearchParams();
      if (cursor) search.set("cursor", cursor);
      if (workflow) search.set("workflow", workflow);
      if (state) search.set("state", state);
      if (owner) search.set("owner", owner);
      const query = search.toString();
      return api<CasePage>(`${STAFF}/cases${query ? `?${query}` : ""}`);
    },
  });

  const filtered = inbox.data?.items ?? [];

  function patch(next: Record<string, string | null>, resetCursor = false) {
    const updated = new URLSearchParams(params);
    for (const [key, value] of Object.entries(next)) {
      if (!value) updated.delete(key);
      else updated.set(key, value);
    }
    if (resetCursor) updated.delete("cursor");
    setParams(updated);
  }

  const focusItems = useMemo(
    () => filtered.filter((item) => item.state !== "closed"),
    [filtered],
  );

  const showCandidates = view === "candidates";

  const knowledgeHref = `/knowledge?from=business&role=business&purpose=delivery${
    caseId ? `&case=${caseId}` : ""
  }${uuidOrEmpty(params.get("project")) ? `&project=${uuidOrEmpty(params.get("project"))}` : ""}`;

  return (
    <div className="page business-page">
      <ContextTrail items={[{ label: "OneFDE", to: "/" }, { label: "客户与经营" }]} />
      <BusinessHero
        status={
          inbox.isLoading ? "读取中" : inbox.isError ? "读取失败" : focusItems.length ? "工作中" : "本页无未关闭"
        }
      />

      <div className="business-toolbar">
        <p className="business-toolbar-links">
          <Link to={knowledgeHref}>查 Knowledge</Link>
          <Link to="/">回办公室</Link>
        </p>
      </div>

      <div className="business-workspace">
        <section className="business-panel business-chat-panel" aria-labelledby="chat-heading">
          <div className="section-head">
            <h2 id="chat-heading">当前会话</h2>
          </div>
          {caseId ? (
            <CaseConversation key={caseId} caseId={caseId} />
          ) : (
            <>
              <div className="business-chat-thread">
                <p className="eng-muted">
                  从右侧选择一个 Case。这里显示该会话的客户原话、对外回复和内部备注，没有单独的经营对话。
                </p>
              </div>
              <form className="business-chat-composer" onSubmit={(event) => event.preventDefault()}>
                <Input.TextArea disabled rows={2} placeholder="先选择 Case，再写回复或内部备注。" />
                <Button type="primary" disabled>
                  发送回复
                </Button>
              </form>
            </>
          )}
        </section>

        <section className="business-panel" aria-labelledby="inbox-heading">
          <div className="section-head">
            <h2 id="inbox-heading">客户与 Case</h2>
            <Button size="small" onClick={() => void inbox.refetch()} loading={inbox.isFetching}>
              刷新
            </Button>
          </div>
          <div className="business-filters">
            <Select
              allowClear
              placeholder="工作流"
              style={{ minWidth: 120 }}
              value={workflow || undefined}
              options={Object.entries(WORKFLOW).map(([value, name]) => ({ value, label: name }))}
              onChange={(value) => patch({ workflow: value ?? null }, true)}
            />
            <Select
              allowClear
              placeholder="状态"
              style={{ minWidth: 140 }}
              value={state || undefined}
              options={Object.entries(STATE).map(([value, name]) => ({ value, label: name }))}
              onChange={(value) => patch({ state: value ?? null }, true)}
            />
            <Select
              allowClear
              placeholder="负责人"
              style={{ minWidth: 120 }}
              value={owner || undefined}
              options={Object.entries(OWNER).map(([value, name]) => ({ value, label: name }))}
              onChange={(value) => patch({ owner: value ?? null }, true)}
            />
          </div>
          <AsyncState
            loading={inbox.isLoading}
            error={inbox.error}
            empty={!filtered.length}
            emptyText={<p>当前没有匹配的 Case。</p>}
            onRetry={() => inbox.refetch()}
          >
            <ul className="business-case-list">
              {filtered.map((item) => (
                <li key={item.id} className={item.id === caseId ? "is-selected" : undefined}>
                  <button type="button" className="business-case-card" onClick={() => patch({ case: item.id })}>
                    <div className="business-case-head">
                      <strong>
                        {WORKFLOW[item.workflow] ?? item.workflow} · {STATE[item.state] ?? item.state}
                      </strong>
                      <span className={`status-badge business-tone-${stateTone(item.state)}`}>
                        {OWNER[item.owner] ?? item.owner}
                      </span>
                    </div>
                    <p className="business-next-step">{item.next_step}</p>
                  </button>
                </li>
              ))}
            </ul>
          </AsyncState>
          <p className="eng-muted">
            本页 {filtered.length} 条，未关闭 {focusItems.length} 条。筛选由服务端分页，不是全库数量。
          </p>
          <p className="eng-muted">
            {cursor ? (
              <Button size="small" onClick={() => patch({ cursor: null })}>
                回到首页
              </Button>
            ) : null}{" "}
            {inbox.data?.next_cursor ? (
              <Button size="small" onClick={() => patch({ cursor: inbox.data?.next_cursor || null })}>
                下一页
              </Button>
            ) : null}
          </p>
          <p className="project-summary-actions">
            <button type="button" className="text-link-button" onClick={() => patch({ view: showCandidates ? null : "candidates" })}>
              {showCandidates ? "收起找店" : "找店候选"}
            </button>
          </p>
          {showCandidates ? <CandidateSearch productUrl={productUrl} /> : null}
        </section>
      </div>
    </div>
  );
}

function field(name: string, label: string, { optional = false, multiline = false } = {}) {
  return (
    <Form.Item label={label} name={name} rules={[{ required: !optional, whitespace: true }]}>
      {multiline ? <Input.TextArea rows={3} /> : <Input />}
    </Form.Item>
  );
}

const lines = (value: Values[string]) =>
  String(value || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

function ActionFields({ action }: { action: string }) {
  const taskId = Form.useWatch("task_id");
  switch (action) {
    case "reply":
      return field("text", "对外回复（客户可见）", { multiline: true });
    case "note":
      return field("text", "内部备注（客户不可见）", { multiline: true });
    case "handoff":
      return (
        <>
          {field("title", "交接标题")}
          {field("goal", "目标", { multiline: true })}
          {field("confirmed_facts", "已确认事实（每行一项）", { optional: true, multiline: true })}
          {field("unknowns", "待确认项（每行一项）", { optional: true, multiline: true })}
          {field("reproduction", "故障复现", { optional: true, multiline: true })}
        </>
      );
    case "accept_handoff":
      return (
        <>
          {field("engagement_id", "核实后的项目 ID")}
          {field("reported_version", "核实后的客户版本（售后必填）", { optional: true })}
          {field("task_id", "关联现有 Task ID（留空则创建）", { optional: true })}
          {!String(taskId || "").trim() ? (
            <>
              {field("task_title", "新 Task 标题")}
              {field("objective", "目标")}
              {field("scope", "范围")}
              {field("completion", "完成条件（每行一项）", { multiline: true })}
            </>
          ) : null}
        </>
      );
    case "record_input":
      return field("message_id", "客户消息编号");
    case "approve_fde_feedback":
      return field("text", "已核准给客户的方案反馈", { multiline: true });
    case "notify_retest":
      return (
        <>
          {field("artifact_id", "已接受的修复产物 ID")}
          {field("version", "固定修复版本")}
          {field("access_url", "已验证可访问的修复地址")}
          {field("steps", "给客户的复试步骤", { multiline: true })}
          {field("access_evidence", "内部访问检查证据", { multiline: true })}
        </>
      );
    default:
      return null;
  }
}

function payload(action: string, values: Values) {
  switch (action) {
    case "handoff":
      return {
        action,
        ...values,
        confirmed_facts: lines(values.confirmed_facts),
        unknowns: lines(values.unknowns),
        reproduction: values.reproduction || null,
      };
    case "accept_handoff": {
      const taskId = String(values.task_id || "").trim();
      return {
        action,
        engagement_id: String(values.engagement_id).trim(),
        reported_version: String(values.reported_version || "").trim() || null,
        ...(taskId
          ? { task_id: taskId }
          : {
              spec: {
                title: values.task_title,
                objective: values.objective,
                scope: values.scope,
                completion_criteria: lines(values.completion),
                inputs: [],
                confirmed_rules: [],
                dependencies: [],
                capability_versions: [],
              },
            }),
      };
    }
    case "record_input":
      return { action, message_id: Number(values.message_id) };
    default:
      return { action, ...values };
  }
}

const ACTION_SUBMIT: Record<string, string> = {
  note: "记下内部备注",
  reply: "发送对外回复",
  take_over: "接管",
  handoff: "提交交接",
  accept_handoff: "确认交接",
  record_input: "登记待采用输入",
  notify_retest: "通知客户复试",
  approve_fde_feedback: "核准待转达",
};

function CaseActions({ item }: { item: Detail }) {
  const session = useSession();
  const username = session.data?.username ?? "";
  const [action, setAction] = useState("note");
  const [form] = Form.useForm();
  const { write, busy, error } = useWrite();
  const query = useQueryClient();
  const options = [{ value: "note", label: "内部 · 记备注" }];
  const automated = item.handler?.startsWith("service:fde:") ?? false;
  const canApprove =
    item.handler === "service:fde:delivery" &&
    item.state === "handling" &&
    item.workflow !== "support" &&
    !!item.engagement_id;
  const fdeWork = useQuery({
    queryKey: queryKeys.fdeWork(item.engagement_id ?? ""),
    queryFn: () =>
      api<
        {
          id: string;
          case_id: string | null;
          task_id: string | null;
          state: string;
          report: { summary?: string; error?: string };
        }[]
      >(`/api/v1/engagements/${item.engagement_id}/fde/work`),
    enabled: canApprove,
    refetchInterval: canApprove ? 4000 : false,
  });
  const feedback = fdeWork.data?.find(
    (work) =>
      work.case_id === item.id &&
      work.task_id === item.task_id &&
      work.state === "reported" &&
      work.report.summary &&
      !work.report.error,
  );
  const publicHead = item.messages.filter((message) => message.kind !== "note").slice(-1)[0]?.id;
  if (canApprove && feedback && publicHead) {
    options.push({ value: "approve_fde_feedback", label: "对外 · 批准转达 FDE 方案反馈" });
  }
  if (["open", "clarifying", "founder_queue"].includes(item.state) || (automated && item.state === "handling")) {
    options.push({ value: "take_over", label: "内部 · 创始人接管（按服务端事实暂停自动化）" });
  }
  if (["open", "clarifying"].includes(item.state) || (item.state === "handling" && item.owner === "founder")) {
    options.push({ value: "handoff", label: "内部 · 转 FDE" });
  }
  if (item.state === "fde_queue") options.push({ value: "accept_handoff", label: "内部 · FDE 确认交接" });
  if (item.state === "handling" && !automated && item.handler === username) {
    options.push({ value: "reply", label: "对外 · 发回复" });
    if (item.owner === "fde" && item.task_id) {
      options.push({ value: "record_input", label: "内部 · 登记待采用 TaskInput" });
      if (item.workflow === "support") {
        options.push({ value: "notify_retest", label: "对外 · 确认修复并通知复试" });
      }
    }
  }
  if (item.state === "closed") return null;
  const selected = options.some((option) => option.value === action) ? action : "note";
  return (
    <section className="business-panel" aria-labelledby="case-actions-heading">
      <h2 id="case-actions-heading">当前处理</h2>
      <p className="eng-muted">一次突出一个下一步。对外动作与内部动作已分开标注。</p>
      <Form
        form={form}
        layout="vertical"
        onFinish={(values: Values) => {
          const body =
            selected === "approve_fde_feedback"
              ? {
                  action: selected,
                  text: values.text,
                  fde_work_id: feedback?.id,
                  expected_last_public_message_id: publicHead,
                }
              : payload(selected, values);
          void write(`${STAFF}/cases/${item.id}/actions`, body, () => {
            form.resetFields();
            setAction("note");
            void query.invalidateQueries({ queryKey: ["business"] });
            void query.invalidateQueries({ queryKey: queryKeys.businessCase(item.id) });
          });
        }}
      >
        <label>
          处理动作
          <select
            value={selected}
            disabled={busy}
            onChange={(event) => {
              form.resetFields();
              setAction(event.currentTarget.value);
            }}
          >
            {options.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        {selected === "approve_fde_feedback" ? (
          <p className="business-message">FDE 回报　{feedback?.report.summary}</p>
        ) : null}
        <ActionFields action={selected} />
        <Button htmlType="submit" type="primary" loading={busy}>
          {ACTION_SUBMIT[selected] ?? "保存操作"}
        </Button>
      </Form>
      {error ? <Alert type="error" showIcon message={error} /> : null}
    </section>
  );
}

function facts(label: string, value: ReactNode) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{value || "待确认"}</dd>
    </>
  );
}

type ClarificationDraft = {
  source_message_id: number;
  last_public_message_id: number;
  public_reply: string;
  internal_summary: string;
};

function Clarification({ item }: { item: Detail }) {
  const customerMessages = item.messages.filter((message) => message.kind === "customer");
  const [source, setSource] = useState("");
  const [understanding, setUnderstanding] = useState("");
  const [question, setQuestion] = useState("");
  const [kind, setKind] = useState("clarify");
  const [draft, setDraft] = useState<ClarificationDraft>();
  const [reply, setReply] = useState("");
  const [sent, setSent] = useState(false);
  const { write, busy, error } = useWrite();
  const query = useQueryClient();
  const base = `${STAFF}/cases/${item.id}`;
  const latestPublic = item.messages.filter((message) => message.kind !== "note").at(-1)?.id;
  const stale = Boolean(draft && latestPublic !== draft.last_public_message_id);

  function prepare() {
    setDraft(undefined);
    setSent(false);
    void write<ClarificationDraft>(
      `${base}/clarification-draft`,
      {
        source_message_id: Number(source),
        understanding,
        kind,
        question: kind === "clarify" ? question : null,
      },
      (value) => {
        setDraft(value);
        setReply(value.public_reply);
      },
    );
  }

  return (
    <section className="business-panel" aria-label="澄清草稿">
      <h2>准备澄清</h2>
      <p className="eng-muted">预览不等于已发送。水位过期后须重新预览；内部摘要不会进入公开消息。</p>
      <label>
        客户原话
        <select
          value={source}
          onChange={(event) => {
            setSource(event.target.value);
            setDraft(undefined);
          }}
        >
          <option value="">选择本会话的客户消息</option>
          {customerMessages.map((message) => (
            <option value={message.id} key={message.id}>
              #{message.id} {message.text.slice(0, 80)}
            </option>
          ))}
        </select>
      </label>
      <label>
        回复用途
        <select
          value={kind}
          onChange={(event) => {
            setKind(event.target.value);
            setDraft(undefined);
          }}
        >
          <option value="clarify">澄清需求</option>
          <option value="commitment">请负责人确认承诺</option>
        </select>
      </label>
      <label>
        用商家的话复述目标
        <Input
          value={understanding}
          maxLength={500}
          onChange={(event) => {
            setUnderstanding(event.target.value);
            setDraft(undefined);
          }}
        />
      </label>
      {kind === "clarify" ? (
        <label>
          影响交付的待确认问题
          <Input
            value={question}
            maxLength={500}
            onChange={(event) => {
              setQuestion(event.target.value);
              setDraft(undefined);
            }}
          />
        </label>
      ) : null}
      <Button
        loading={busy}
        disabled={!source || !understanding.trim() || (kind === "clarify" && !question.trim())}
        onClick={prepare}
      >
        预览澄清草稿
      </Button>
      {draft ? (
        <>
          <h3>内部摘要（不发送）</h3>
          <pre style={{ whiteSpace: "pre-wrap" }}>{draft.internal_summary}</pre>
          <label>
            商家会看到的回复
            <Input.TextArea value={reply} maxLength={4000} onChange={(event) => setReply(event.target.value)} />
          </label>
          {stale ? <Alert type="warning" showIcon message="会话已有更新，草稿水位过期。请重新预览后再发送。" /> : null}
          <Button
            type="primary"
            loading={busy}
            disabled={stale || !reply.trim()}
            onClick={() => {
              void write<Detail>(
                `${base}/actions`,
                {
                  action: "send_clarification",
                  text: reply,
                  source_message_id: draft.source_message_id,
                  expected_last_public_message_id: draft.last_public_message_id,
                },
                () => {
                  setDraft(undefined);
                  setSent(true);
                  void query.invalidateQueries({ queryKey: queryKeys.businessCase(item.id) });
                },
              );
            }}
          >
            发送预览回复
          </Button>
        </>
      ) : null}
      {sent ? <Alert type="success" showIcon message="已在原会话发送。" /> : null}
      {error ? <Alert type="error" showIcon message={error} /> : null}
    </section>
  );
}

function FdeHandoffLink({ item }: { item: Detail }) {
  const navigate = useNavigate();
  const projects = useQuery({
    queryKey: ["fde-handoff-projects"],
    queryFn: async () => {
      const items: { id: string; title: string }[] = [];
      let cursor: string | null = null;
      do {
        const page: { items: typeof items; next_cursor: string | null } = await api(
          `/api/v1/engagements${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`,
        );
        items.push(...page.items);
        cursor = page.next_cursor;
      } while (cursor);
      return items;
    },
    enabled: !item.engagement_id,
  });
  if (item.engagement_id) {
    return (
      <p className="project-summary-actions">
        <Link to={`/fde?project=${item.engagement_id}&case=${item.id}`}>打开 FDE 工作</Link>
        <Link to={`/projects/${item.engagement_id}?case=${item.id}`}>项目中心</Link>
        {item.task_id ? (
          <Link to={`/engineering?project=${item.engagement_id}&task=${item.task_id}`}>Engineering</Link>
        ) : null}
      </p>
    );
  }
  return (
    <>
      <Form
        layout="vertical"
        onFinish={({ project }: { project: string }) => navigate(`/fde?project=${project}&case=${item.id}`)}
      >
        <Form.Item name="project" label="交接到现有项目" rules={[{ required: true, message: "请选择已核实的项目。" }]}>
          <Select
            loading={projects.isPending}
            options={projects.data?.map((project) => ({ value: project.id, label: project.title }))}
          />
        </Form.Item>
        <Button htmlType="submit" disabled={!projects.isSuccess}>
          打开 FDE 交付工作
        </Button>
      </Form>
      {projects.error ? <Alert type="error" showIcon message={problem(projects.error)} /> : null}
    </>
  );
}

export function BusinessCase() {
  const { caseId: rawCaseId } = useParams();
  const caseId = uuidOrEmpty(rawCaseId);
  const detail = useQuery({
    queryKey: queryKeys.businessCase(caseId ?? ""),
    enabled: Boolean(caseId),
    queryFn: loadCase(caseId ?? ""),
    refetchInterval: () => (document.hidden ? false : 8000),
  });
  const item = detail.data;
  const serviceHandled = item?.handler?.startsWith("service:") ?? false;

  if (!caseId) {
    return <div className="page business-page"><Alert type="warning" showIcon message="会话地址无效，请从 Case 收件箱选择会话。" /><Link to="/business">打开 Case 收件箱</Link></div>;
  }

  return (
    <div className="page business-page">
      <ContextTrail
        items={[
          { label: "OneFDE", to: "/" },
          { label: "Business", to: "/business" },
          { label: item ? WORKFLOW[item.workflow] : "会话" },
        ]}
      />
      <AsyncState loading={detail.isPending} error={detail.error} onRetry={() => detail.refetch()}>
        {item ? (
          <>
            <BusinessHero
              title={`${WORKFLOW[item.workflow]}会话`}
              subtitle={`${STATE[item.state]} · ${OWNER[item.owner]}${
                item.handler ? ` · ${item.handler}` : ""
              }${serviceHandled ? " · 服务接手，不代表正在运行" : ""}`}
              status={STATE[item.state]}
            />

            <div className="business-next-banner" role="status">
              <strong>当前下一步</strong>
              <p>{item.next_step}</p>
            </div>

            <p className="project-summary-actions business-case-links">
              <Button onClick={() => void detail.refetch()} loading={detail.isFetching}>
                刷新会话
              </Button>
              <Link to={`/knowledge?from=business&case=${item.id}&role=business&purpose=delivery`}>
                查 Knowledge
              </Link>
              {item.engagement_id ? (
                <Link to={`/projects/${item.engagement_id}?case=${item.id}`}>项目中心</Link>
              ) : null}
              {item.engagement_id && item.task_id ? (
                <Link to={`/engineering?project=${item.engagement_id}&task=${item.task_id}`}>
                  Engineering
                </Link>
              ) : null}
            </p>

            <div className="business-case-grid">
              <section className="business-panel business-thread-panel" aria-labelledby="thread-heading">
                <h2 id="thread-heading">会话记录</h2>
                <p className="eng-muted">客户原话 / 对外回复 / 内部备注分区显示，不混写。</p>
                <ol className="business-thread">
                  {item.messages.map((message) => (
                    <li key={message.id} className={`msg-${message.kind}`}>
                      <strong>
                        {MSG_KIND[message.kind] ?? message.kind} · #{message.id} · {message.author}
                      </strong>
                      <p className="business-message">{message.text}</p>
                      {message.reference && Object.values(message.reference).some(Boolean) ? (
                        <details>
                          <summary>来源与关联</summary>
                          <pre>{JSON.stringify(message.reference, null, 2)}</pre>
                        </details>
                      ) : null}
                    </li>
                  ))}
                </ol>
              </section>

              <aside className="business-detail-side">
                <section className="business-panel">
                  <h2>当前 Case</h2>
                  <dl className="business-facts">
                    {facts(
                      "来源",
                      item.invitation_id ? `演示邀请 ${item.invitation_id}` : "报价产品入口",
                    )}
                    {facts(
                      "已核实项目",
                      item.engagement_id ? (
                        <Link to={`/projects/${item.engagement_id}?case=${item.id}`}>
                          {item.engagement_id}
                        </Link>
                      ) : null,
                    )}
                    {facts("已核实客户版本", item.reported_version)}
                    {facts(
                      "当前 Task",
                      item.task_id && item.engagement_id ? (
                        <Link to={`/engineering?project=${item.engagement_id}&task=${item.task_id}`}>
                          {item.task_id}
                        </Link>
                      ) : (
                        item.task_id
                      ),
                    )}
                    {item.retest
                      ? facts(
                          "复试",
                          `${item.retest.version} · ${
                            item.retest.passed === undefined
                              ? "待客户确认"
                              : item.retest.passed
                                ? "客户确认可用"
                                : "客户反馈仍失败"
                          }`,
                        )
                      : null}
                  </dl>
                  {item.workflow === "support" ? (
                    <Alert
                      type="info"
                      showIcon
                      message="售后须客户复试通过才关闭。Engineering 接受修复不会自动关闭本 Case。"
                    />
                  ) : null}
                  {item.handoff ? (
                    <details open className="business-handoff">
                      <summary>FDE 交接 · {item.handoff.title}</summary>
                      <p>{item.handoff.goal}</p>
                      <p>原话引用 {item.handoff.sources.join("、")}</p>
                      <p>已确认 {item.handoff.confirmed_facts.join("、") || "无"}</p>
                      <p>待核实 {item.handoff.unknowns.join("、") || "无"}</p>
                      {item.handoff.reproduction ? <p>复现 {item.handoff.reproduction}</p> : null}
                    </details>
                  ) : null}
                  {item.handoff && item.owner === "fde" ? <FdeHandoffLink item={item} /> : null}
                </section>

                {item.owner === "fde" &&
                item.state === "handling" &&
                !item.handler?.startsWith("service:fde:") ? (
                  <Clarification key={item.id} item={item} />
                ) : null}
                <CaseActions key={item.id} item={item} />
              </aside>
            </div>
          </>
        ) : null}
      </AsyncState>
    </div>
  );
}
