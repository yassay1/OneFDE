import { type Evidence, type Run, type RunEvent } from "./fixtures";
import { Icon } from "./visuals";

const eventTypes = { state: "状态", progress: "进展", check: "检查", artifact: "产物" };

export function RunTimeline({ events }: { events: RunEvent[] }) {
  return (
    <ol className="eng-timeline">
      {events.map((event) => (
        <li key={event.time + event.title}>
          <span className={`eng-event-mark eng-event-${event.kind}`} aria-hidden="true" />
          <div className="eng-event-copy">
            <strong>{event.title}</strong>
            <p>{event.detail}</p>
          </div>
          <div className="eng-event-meta">
            <span>{eventTypes[event.kind]}</span>
            <time>{event.time}</time>
          </div>
        </li>
      ))}
    </ol>
  );
}

function CheckList({ checks }: { checks: Evidence["validation_checks"] }) {
  return (
    <ul className="eng-check-list">
      {checks.map((check) => {
        const passed = check.exit_code === 0 && !check.timeout;
        const label = check.timeout ? "超时" : check.exit_code === null ? "未验证" : passed ? "通过" : `退出码 ${check.exit_code}`;
        return (
          <li key={check.name}>
            <span className={`eng-check-icon${passed ? " is-passed" : ""}`}>{passed ? <Icon name="check" size={12} /> : "!"}</span>
            <div><strong>{check.name}</strong><code>{check.command}</code></div>
            <span className={passed ? "eng-pass" : "eng-muted"}>{label}</span>
          </li>
        );
      })}
    </ul>
  );
}

function Diff({ evidence }: { evidence: Evidence }) {
  const diff = evidence.diff.split("\n");
  let oldLine = 40;
  let newLine = 40;
  return (
    <>
      <div className="eng-file-line">
        <div><Icon name="file" size={16} /><strong>{evidence.file}</strong></div>
        <div className="eng-diff-count"><span>+{diff.filter((line) => line.startsWith("+")).length}</span><span>−{diff.filter((line) => line.startsWith("-")).length}</span></div>
      </div>
      <div className="eng-diff" aria-label="固定源码差异" role="region" tabIndex={0}>
        <div className="eng-diff-head"><span>{evidence.file}</span><small>{evidence.baseline}</small></div>
        <pre>
          {diff.map((line, index) => {
            const added = line.startsWith("+");
            const removed = line.startsWith("-");
            const before = added ? "" : ++oldLine;
            const after = removed ? "" : ++newLine;
            return <span key={index} className={`eng-diff-row${added ? " added" : removed ? " removed" : ""}`}>
              <span className="eng-line-num" aria-hidden="true">{before}</span>
              <span className="eng-line-num" aria-hidden="true">{after}</span>
              <code>{line}</code>
            </span>;
          })}
        </pre>
      </div>
      {evidence.diff_truncated && <p className="eng-muted">当前显示差异节选。</p>}
      <p className="eng-diff-note">{evidence.design}</p>
    </>
  );
}

function Artifacts({ evidence }: { evidence: Evidence }) {
  return (
    <div className="eng-artifacts">
      {evidence.artifacts.map((artifact) => (
        <details key={artifact.id} className="eng-artifact">
          <summary>
            <span className="eng-artifact-icon"><Icon name="box" /></span>
            <span><strong>{artifact.name}</strong><small>{artifact.kind} · {artifact.size}</small></span>
          </summary>
          <dl><dt>SHA-256</dt><dd><code>{artifact.sha256}</code></dd></dl>
        </details>
      ))}
    </div>
  );
}

export function EvidenceDetails({ run, readOnly }: {
  run: Run;
  readOnly: boolean;
}) {
  const evidence = run.evidence;
  const checks = evidence?.validation_checks ?? [];
  const passed = checks.filter((check) => check.exit_code === 0 && !check.timeout).length;
  return (
    <section className="eng-evidence" aria-label="固定证据">
      <p className="eng-evidence-reference">规格 v{run.task_spec_version}{readOnly && " · 只读"}</p>
      <p>{run.summary}</p>
      {evidence ? (
        <>
          <section className="eng-verification">
            <div><h3>固定归档独立复验</h3><span className={passed === checks.length && passed > 0 ? "eng-pass" : "eng-muted"}>{checks.length ? `${passed}/${checks.length} 通过` : "未验证"}</span></div>
            <CheckList checks={checks} />
          </section>
          <details className="eng-evidence-disclosure"><summary>代码差异</summary><Diff evidence={evidence} /></details>
          <details className="eng-evidence-disclosure"><summary>固定产物 <span>{evidence.artifacts.length}</span></summary><Artifacts evidence={evidence} /></details>
          <details className="eng-evidence-disclosure"><summary>工程自测</summary><CheckList checks={evidence.self_checks} /></details>
        </>
      ) : <div className="eng-evidence-empty"><strong>本轮暂无固定证据</strong><p>可返回对话查看该轮运行活动。</p></div>}
    </section>
  );
}
