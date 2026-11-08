import { Button, ConfigProvider, Drawer, Input } from "antd";
import zhCN from "antd/locale/zh_CN";
import { StrictMode, useRef, useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter, useSearchParams } from "react-router-dom";
import { EvidenceDetails, RunTimeline } from "./EvidencePanel";
import { fixtures, runLabels, taskLabels, type Review, type Run, type Task, type Verdict } from "./fixtures";
import { Icon } from "./visuals";
import "./preview.css";

function taskLabel(task: Task) {
  return task.state === "waiting_input" && task.inputs.some((item) => item.kind === "answer" && item.status === "applied")
    ? "待续作"
    : taskLabels[task.state];
}

function TaskList({ tasks, selectedId, onSelect }: {
  tasks: Task[];
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <aside className="eng-sidebar" aria-label="工程任务">
      <h2>工程任务</h2>
      <p className="eng-project-label"><Icon name="folder" size={15} />水果店项目</p>
      <ul>
        {tasks.map((task) => (
          <li key={task.id}>
            <button type="button" aria-current={task.id === selectedId ? "page" : undefined} onClick={() => onSelect(task.id)}>
              <i className={`eng-state-dot eng-state-${task.state}`} aria-hidden="true" />
              <span>{task.title}</span>
              <small>{taskLabel(task)}</small>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}

function ThreadEntry({ name, tone, children }: {
  name: string;
  tone: "fde" | "engineering" | "founder";
  children: ReactNode;
}) {
  return (
    <article className={`eng-entry eng-entry-${tone}`} aria-label={name}>
      <div className="eng-entry-icon" aria-hidden="true">
        {tone === "engineering" ? <Icon name="code" size={16} /> : tone === "fde" ? "F" : "创"}
      </div>
      <div className="eng-entry-content">
        <h2>{name}</h2>
        {children}
      </div>
    </article>
  );
}

function ReviewForm({ verdict, run, onBack, onSave }: {
  verdict: Verdict;
  run: Run;
  onBack: () => void;
  onSave: (review: Review) => void;
}) {
  const [reason, setReason] = useState("");
  const [check, setCheck] = useState("");
  const accept = verdict === "accept";
  const artifacts = run.evidence?.artifacts ?? [];
  const valid = Boolean(reason.trim() && (!accept || check.trim()) && artifacts.length);

  return (
    <form className="eng-review-form" onSubmit={(event) => {
      event.preventDefault();
      if (!valid) return;
      onSave({
        runId: run.id, specVersion: run.task_spec_version,
        artifactIds: artifacts.map((item) => item.id), verdict,
        reason: reason.trim(), check: check.trim(),
      });
    }}>
      <h3>{accept ? "接受提交" : "要求修改"}</h3>
      <p className="eng-muted">{accept ? "业务接受将绑定本轮固定成果。" : "修改意见将记录在当前任务中，等待采用。"}</p>
      <label className="eng-field">
        评审意见
        <Input.TextArea autoFocus required rows={3} maxLength={500} value={reason} onChange={(event) => setReason(event.target.value)} />
      </label>
      {accept && <label className="eng-field">
        检查依据
        <Input required maxLength={300} value={check} onChange={(event) => setCheck(event.target.value)} />
      </label>}
      <div className="eng-actions">
        <Button onClick={onBack}>返回证据</Button>
        <Button type="primary" htmlType="submit" disabled={!valid}>{accept ? "确认接受" : "记录修改意见"}</Button>
      </div>
    </form>
  );
}

function Workspace({ task, run, readOnly, onTask }: {
  task: Task;
  run: Run;
  readOnly: boolean;
  onTask: (task: Task) => void;
}) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [verdict, setVerdict] = useState<Verdict>();
  const [draft, setDraft] = useState("");
  const submissionButton = useRef<HTMLButtonElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const pending = task.inputs.filter((item) => item.status === "pending");
  const reviewable = !readOnly && task.state === "review" && run.task_spec_version === task.spec_version
    && run.state === "submitted" && Boolean(run.evidence?.artifacts.length);
  const review = task.reviews.find((record) => record.runId === run.id);
  const canWrite = !readOnly && task.state !== "succeeded";
  const answering = run.state === "needs_input" && Boolean(run.question);
  const answered = task.inputs.some((item) => item.runId === run.id && item.kind === "answer");
  const canAdopt = canWrite && task.state !== "running" && pending.length > 0;
  const checks = run.evidence?.validation_checks ?? [];
  const passed = checks.filter((item) => item.exit_code === 0 && !item.timeout).length;

  function closeDrawer() {
    setDrawerOpen(false);
    setVerdict(undefined);
  }

  function revealUpdate() {
    requestAnimationFrame(() => end.current?.scrollIntoView({ block: "nearest" }));
  }

  function saveReview(next: Review) {
    if (!reviewable || next.runId !== run.id || (next.verdict === "accept" && pending.length)) return;
    onTask({
      ...task,
      state: next.verdict === "accept" ? "succeeded" : "draft",
      reviews: [...task.reviews, next],
      inputs: next.verdict === "accept" ? task.inputs : [...task.inputs, {
        id: crypto.randomUUID(), runId: run.id, kind: "change_request", text: next.reason, status: "pending",
      }],
    });
    closeDrawer();
    revealUpdate();
  }

  return (
    <>
      <div className="eng-thread">
        <ThreadEntry name="FDE 交接" tone="fde"><p>{task.handoff}</p></ThreadEntry>
        <ThreadEntry name="Engineering" tone="engineering">
          <p>{run.summary}</p>
          <details className="eng-run-events">
            <summary>第 {run.attempt} 轮运行活动</summary>
            <p className="eng-run-reference">{run.id.toUpperCase()} · 规格 v{run.task_spec_version}</p>
            <RunTimeline events={run.events} />
          </details>
          {run.question && (
            <div className="eng-question"><strong>{answered || readOnly ? "本轮问题" : "待答问题"}</strong><p>{run.question}</p></div>
          )}
          {run.state === "submitted" && (
            <div className="eng-submission">
              <span className="eng-submission-icon"><Icon name="file" size={18} /></span>
              <div><strong>第 {run.attempt} 轮提交</strong><small>{checks.length ? `独立复验 ${passed}/${checks.length} 通过` : "暂无复验明细"}</small></div>
              <Button ref={submissionButton} type={reviewable ? "primary" : "default"} onClick={() => setDrawerOpen(true)}>
                查看提交 <Icon name="arrow" size={15} />
              </Button>
            </div>
          )}
        </ThreadEntry>
        {task.inputs.filter((item) => item.runId === run.id).map((item) => (
          <ThreadEntry key={item.id} name={item.kind === "change_request" ? "业务评审 · 要求修改" : item.kind === "answer" ? "创始人答复" : "创始人补充"} tone="founder">
            <p>{item.text}</p>
            <span className="eng-input-status">{item.status === "pending" ? "待采用" : `已采用 · v${item.appliedVersion}`}</span>
          </ThreadEntry>
        ))}
        {review?.verdict === "accept" && (
          <ThreadEntry name="业务评审 · 已接受" tone="founder">
            <p>{review.reason}</p>
            <small className="eng-muted">检查依据 · {review.check}</small>
          </ThreadEntry>
        )}
        {canAdopt && <div className="eng-adopt">
          <Button onClick={() => {
            const spec_version = task.spec_version + 1;
            onTask({
              ...task, spec_version, state: task.state === "waiting_input" ? "waiting_input" : "draft",
              inputs: task.inputs.map((item) => item.status === "pending" ? { ...item, status: "applied", appliedVersion: spec_version } : item),
            });
            revealUpdate();
          }}>采用{answering ? "答复" : "输入"}</Button>
          <span>生成规格 v{task.spec_version + 1}，保留本轮规格</span>
        </div>}
        <div ref={end} />
      </div>

      {canWrite && (!answering || !answered) && (
        <form className="eng-composer" onSubmit={(event) => {
          event.preventDefault();
          if (!draft.trim()) return;
          onTask({ ...task, inputs: [...task.inputs, {
            id: crypto.randomUUID(), runId: run.id, text: draft.trim(),
            kind: answering ? "answer" : "clarification", status: "pending",
          }] });
          setDraft("");
          revealUpdate();
        }}>
          <Input.TextArea
            aria-label={answering ? "答复本轮问题" : "补充当前任务"}
            placeholder={answering ? "答复本轮问题…" : "补充当前任务…"}
            autoSize={{ minRows: 2, maxRows: 5 }} maxLength={500}
            value={draft} onChange={(event) => setDraft(event.target.value)}
          />
          <div className="eng-composer-footer">
            <span>记录到当前任务，待采用</span>
            <Button htmlType="submit" disabled={!draft.trim()}>{answering ? "保存答复" : "记录补充"}</Button>
          </div>
        </form>
      )}
      {canWrite && answering && answered && !pending.length &&
        <p className="eng-thread-notice" role="status">答复已采用，等待续作。原 Run 保留规格 v{run.task_spec_version}。</p>}

      <Drawer
        rootClassName="eng-review-drawer"
        title={`第 ${run.attempt} 轮提交`}
        open={drawerOpen}
        onClose={closeDrawer}
        afterOpenChange={(open) => { if (!open) submissionButton.current?.focus({ preventScroll: true }); }}
        width="min(640px, 100vw)"
        footer={reviewable && !verdict ? <div className="eng-drawer-footer">
          <span>{pending.length ? "有待采用输入，暂不能接受" : "等待业务评审"}</span>
          <div className="eng-actions">
            <Button onClick={() => setVerdict("request_changes")}>要求修改</Button>
            <Button type="primary" disabled={Boolean(pending.length)} onClick={() => setVerdict("accept")}>接受提交</Button>
          </div>
        </div> : undefined}
      >
        {verdict && reviewable
          ? <><p className="eng-review-binding">规格 v{run.task_spec_version} · {run.evidence?.artifacts.map((item) => item.name).join("、")}</p>
            <ReviewForm key={verdict} verdict={verdict} run={run} onBack={() => setVerdict(undefined)} onSave={saveReview} /></>
          : <EvidenceDetails run={run} readOnly={readOnly} />}
      </Drawer>
    </>
  );
}

function Preview() {
  const [tasks, setTasks] = useState(fixtures);
  const [params, setParams] = useSearchParams();
  const task = tasks.find((item) => item.id === params.get("task")) ?? tasks[0];
  const run = task.runs.find((item) => item.id === params.get("run")) ?? task.runs[0];
  const historical = run.id !== task.runs[0].id;
  const invalidSelection = (params.has("task") && params.get("task") !== task.id)
    || (params.has("run") && params.get("run") !== run.id);
  const selectTask = (id: string) => setParams({ task: id });

  return (
    <div className="eng-app">
      <header className="eng-topbar">
        <div className="eng-breadcrumb"><span className="eng-brand"><Icon name="code" size={17} />OneFDE</span><span aria-hidden="true">/</span><strong>Engineering</strong><span className="eng-crumb-project">/　水果店项目</span></div>
        <span className="eng-demo-label">原型 · 模拟数据</span>
      </header>
      <div className="eng-layout">
        <TaskList tasks={tasks} selectedId={task.id} onSelect={selectTask} />
        <main className="eng-main">
          <div className="eng-workspace">
            <div className="eng-narrow-tasks"><label htmlFor="eng-task">工程任务</label><select id="eng-task" value={task.id} onChange={(event) => selectTask(event.target.value)}>
              {tasks.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
            </select></div>
            <header className="eng-task-header">
              <div><h1>{task.title}</h1><span className={`eng-status eng-state-${task.state}`}>{historical ? "历史运行 · 只读" : taskLabel(task)}</span></div>
              {historical ? <Button size="small" onClick={() => selectTask(task.id)}>返回当前轮次</Button>
                : task.runs.length > 1 && <details key={task.id} className="eng-history">
                  <summary><Icon name="history" size={16} />历史</summary>
                  <div>{task.runs.slice(1).map((prior) => <button type="button" key={prior.id} onClick={() => setParams({ task: task.id, run: prior.id })}>
                    第 {prior.attempt} 轮 <small>{runLabels[prior.state]}</small>
                  </button>)}</div>
                </details>}
            </header>
            {invalidSelection && <div className="eng-thread-notice" role="status">
              所选任务或轮次不可用。<Button size="small" type="link" onClick={() => selectTask(task.id)}>打开当前轮次</Button>
            </div>}
            <Workspace key={run.id} task={task} run={run} readOnly={historical || invalidSelection}
              onTask={(next) => setTasks((current) => current.map((item) => item.id === next.id ? next : item))} />
          </div>
        </main>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ConfigProvider locale={zhCN} button={{ autoInsertSpace: false }} theme={{ token: {
      colorPrimary: "#6148cf", colorText: "#26233a", colorBorder: "#e2ddeb",
      fontFamily: '"Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif', borderRadius: 9,
    } }}>
      <HashRouter><Preview /></HashRouter>
    </ConfigProvider>
  </StrictMode>,
);
