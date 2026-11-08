import { useMemo, useState } from "react";
import type { Run, RunEvent, RunReviewEvidence, Task } from "../../api";
import { label, RUN_EVENT_KIND, TASK_STATE } from "../../shared/labels";
import { TaskStatus } from "../../shared/StatusBadge";

type FileNode = { path: string; name: string; patch: string };

function splitDiff(diff: string): FileNode[] {
  const text = diff.trim();
  if (!text) return [];
  const parts = text.split(/(?=^diff --git )/m).filter((part) => part.trim());
  const chunks = parts.length ? parts : [text];
  return chunks.map((patch, index) => {
    const named = patch.match(/^\+\+\+ [ab]\/(.+)$/m)?.[1] ?? patch.match(/^diff --git a\/\S+ b\/(\S+)/m)?.[1];
    const path = named && named !== "/dev/null" ? named : `变更 ${index + 1}`;
    return { path, name: path.split("/").pop() ?? path, patch };
  });
}

export function CodeWorkspace({
  task,
  run,
  events,
  evidence,
  evidenceError,
  onRetryEvidence,
}: {
  task: Task;
  run: Run | null | undefined;
  events: RunEvent[];
  evidence: RunReviewEvidence | null | undefined;
  evidenceError?: unknown;
  onRetryEvidence: () => void;
}) {
  const files = useMemo(() => splitDiff(evidence?.diff ?? ""), [evidence?.diff]);
  const [selected, setSelected] = useState<string>();
  const [tab, setTab] = useState<"diff" | "log" | "checks">("diff");
  const current = files.find((item) => item.path === selected) ?? files[0];
  const quietCode = !current && tab === "diff";

  const tree = useMemo(() => {
    const groups = new Map<string, FileNode[]>();
    for (const file of files) {
      const folder = file.path.includes("/") ? file.path.slice(0, file.path.lastIndexOf("/")) : ".";
      groups.set(folder, [...(groups.get(folder) ?? []), file]);
    }
    return [...groups.entries()];
  }, [files]);

  return (
    <section className="eng-code-col" aria-label="工程工作区">
      <header className="eng-code-head">
        <div>
          <strong>{task.spec.title}</strong>
          <TaskStatus state={task.state} />
        </div>
        <p>
          {label(TASK_STATE, task.state)}
          {run ? ` · 第 ${run.attempt} 轮 ${run.state}${run.outcome ? ` / ${run.outcome}` : ""}` : " · 尚无运行"}
          {run?.task_spec_version != null ? ` · 规格 v${run.task_spec_version}` : ""}
        </p>
      </header>
      <div className="eng-code-tabs" role="tablist">
        {(
          [
            ["diff", "补丁摘录"],
            ["log", "运行活动"],
            ["checks", "检查结果"],
          ] as const
        ).map(([id, name]) => (
          <button key={id} type="button" role="tab" aria-selected={tab === id} className={tab === id ? "is-active" : undefined} onClick={() => setTab(id)}>
            {name}
          </button>
        ))}
      </div>
      <div className={quietCode ? "eng-code-body is-empty" : "eng-code-body"}>
        {quietCode ? null : (
        <aside className="eng-file-tree" aria-label="补丁路径">
          {files.length ? (
            tree.map(([folder, items]) => (
              <div key={folder}>
                <p>{folder}</p>
                <ul>
                  {items.map((file) => (
                    <li key={file.path}>
                      <button type="button" className={current?.path === file.path ? "is-active" : undefined} onClick={() => setSelected(file.path)}>
                        {file.name}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))
          ) : (
            <p>这份补丁里没有路径。</p>
          )}
        </aside>
        )}
        <div className={quietCode ? "eng-code-view is-quiet" : "eng-code-view"} role="tabpanel">
          {tab === "diff" ? (
            current ? (
              <>
                {evidence?.diff_truncated ? <p>补丁已截断。下面不是完整改动，也不能当成源码。</p> : <p>这是固定补丁摘录，不是仓库文件。</p>}
                <pre>
                  {current.patch.split("\n").map((line, index) => {
                    const added = line.startsWith("+") && !line.startsWith("+++");
                    const removed = line.startsWith("-") && !line.startsWith("---");
                    return (
                      <span key={index} className={added ? "is-add" : removed ? "is-del" : undefined}>
                        {line || " "}
                      </span>
                    );
                  })}
                </pre>
              </>
            ) : (
              <p>
                {evidenceError
                  ? "固定证据没有读到。"
                  : evidence === undefined
                    ? "正在读取固定补丁…"
                    : "还没有固定补丁。证据缺失时这里留空。"}
                {evidenceError ? (
                  <>
                    {" "}
                    <button type="button" onClick={onRetryEvidence}>重试</button>
                  </>
                ) : null}
              </p>
            )
          ) : null}
          {tab === "log" ? (
            events.length ? (
              <ol>
                {events.map((event) => (
                  <li key={event.id}>
                    <strong>{event.summary}</strong>
                    <small>
                      {RUN_EVENT_KIND[event.kind] ?? event.kind} · {new Date(event.created_at).toLocaleString("zh-CN")}
                    </small>
                  </li>
                ))}
              </ol>
            ) : (
              <p>本轮还没有运行活动。这里是事件摘要，不是完整工具日志，也没有实时流。</p>
            )
          ) : null}
          {tab === "checks" ? (
            evidence?.self_checks.length || evidence?.validation_checks.length ? (
              <ul>
                {[...(evidence.self_checks ?? []), ...(evidence.validation_checks ?? [])].map((check, index) => (
                  <li key={`${check.command}-${index}`}>
                    <code>{check.command}</code>
                    <span>{check.timeout ? "超时" : check.exit_code === 0 ? "通过" : check.exit_code === null ? "未知" : `退出码 ${check.exit_code}`}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p>
                {evidence?.validation_passed === null || evidence === null || evidence === undefined
                  ? "尚无检查结果。缺失不能标为通过。"
                  : evidence.validation_passed
                    ? "独立复验通过，但没有逐条命令。"
                    : "独立复验未通过，但没有逐条命令。"}
              </p>
            )
          ) : null}
        </div>
      </div>
    </section>
  );
}
