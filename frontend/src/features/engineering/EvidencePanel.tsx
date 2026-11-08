import type { Artifact, ReviewCheck, Run, RunReviewEvidence, Task } from "../../api";
import { ReviewForm } from "./ReviewForm";

function CheckList({ title, checks }: { title: string; checks: ReviewCheck[] }) {
  return (
    <section className="eng-verification">
      <div>
        <h3>{title}</h3>
        <span className="eng-muted">{checks.length ? `${checks.length} 项` : "未登记"}</span>
      </div>
      {checks.length ? (
        <ul className="eng-check-list">
          {checks.map((check, index) => {
            const passed = check.exit_code === 0 && !check.timeout;
            const status = check.timeout
              ? "超时"
              : check.exit_code === null
                ? "未知"
                : passed
                  ? "通过"
                  : `退出码 ${check.exit_code}`;
            return (
              <li key={`${check.command}-${index}`}>
                <span className={`eng-check-icon${passed ? " is-passed" : ""}`} aria-hidden="true">
                  {passed ? "✓" : "!"}
                </span>
                <div>
                  <code>{check.command}</code>
                </div>
                <span className={passed ? "eng-pass" : "eng-muted"}>{status}</span>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="eng-muted">没有登记检查。</p>
      )}
    </section>
  );
}

function DiffView({ evidence }: { evidence: RunReviewEvidence }) {
  const lines = evidence.diff ? evidence.diff.split("\n") : [];
  return (
    <div>
      <div className="eng-diff" aria-label="固定源码差异" role="region" tabIndex={0}>
        <div className="eng-diff-head">
          <span>固定评审差异</span>
          <small>基线 {evidence.baseline_sha256.slice(0, 12)}…</small>
        </div>
        <pre>
          {lines.length ? (
            lines.map((line, index) => {
              const added = line.startsWith("+") && !line.startsWith("+++");
              const removed = line.startsWith("-") && !line.startsWith("---");
              return (
                <span
                  key={index}
                  className={`eng-diff-row${added ? " added" : removed ? " removed" : ""}`}
                >
                  <code>{line || " "}</code>
                </span>
              );
            })
          ) : (
            <span className="eng-diff-row">
              <code>未登记代码差异。</code>
            </span>
          )}
        </pre>
      </div>
      {evidence.diff_truncated ? <p className="eng-muted">当前显示差异节选。</p> : null}
    </div>
  );
}

export function EvidencePanel({
  task,
  run,
  evidence,
  artifacts,
  evidenceError,
  readOnly,
  onReviewed,
}: {
  task: Task;
  run: Run;
  evidence: RunReviewEvidence | null | undefined;
  artifacts: Artifact[];
  evidenceError?: unknown;
  readOnly: boolean;
  onReviewed?: () => void;
}) {
  return (
    <div className="eng-evidence-shell">
      {evidenceError ? <p className="eng-muted">评审证据读取失败。请关闭后重试。</p> : null}
      {evidence === undefined && !evidenceError ? <p role="status">正在读取固定证据。</p> : null}
      {evidence === null ? (
        <div className="eng-evidence-empty">
          <strong>本轮暂无固定证据</strong>
          <p>可能尚未提交、归档不完整，或该 Run 没有匹配的评审证据。缺失不能标为通过。</p>
        </div>
      ) : null}
      {evidence ? (
        <section className="eng-evidence" aria-label="固定提交证据">
          <div className="eng-evidence-banner">
            <strong>代码与检查证据</strong>
            <span>
              独立复验：
              {evidence.validation_passed === null
                ? "未验证"
                : evidence.validation_passed
                  ? "通过"
                  : "未通过"}
            </span>
          </div>
          <p className="eng-evidence-reference">
            规格 v{run.task_spec_version} ·{" "}
            {evidence.mode === "deterministic" ? "确定性演练" : "Engineering 提交"}
          </p>
          <p>
            受检归档 <code>{evidence.artifact_sha256}</code>
          </p>
          <p>
            源码基线 <code>{evidence.baseline_sha256}</code>
          </p>
          {evidence.assembly_revision ? (
            <p>
              Run 装配 {evidence.assembly_revision}
              {evidence.guide_revision ? ` · 指南 ${evidence.guide_revision}` : ""}
            </p>
          ) : null}
          {evidence.known_differences?.length ? (
            <details>
              <summary>已知差异</summary>
              <ul>
                {evidence.known_differences.map((note, index) => (
                  <li key={index}>{note}</li>
                ))}
              </ul>
            </details>
          ) : null}

          <CheckList title="固定归档独立复验" checks={evidence.validation_checks} />
          <p>
            独立复验结论：
            {evidence.validation_passed === null
              ? "未验证"
              : evidence.validation_passed
                ? "通过"
                : "未通过"}
          </p>

          <details className="eng-evidence-disclosure" open>
            <summary>代码差异{evidence.diff_truncated ? "（节选）" : ""}</summary>
            <DiffView evidence={evidence} />
            {evidence.design ? <p className="eng-diff-note">{evidence.design}</p> : null}
          </details>

          <details className="eng-evidence-disclosure">
            <summary>
              固定产物 <span>{artifacts.length}</span>
            </summary>
            {artifacts.length ? (
              <div className="eng-artifacts">
                {artifacts.map((item) => (
                  <details key={item.id} className="eng-artifact">
                    <summary>
                      <span>
                        <strong>{item.name}</strong>
                        <small>
                          {item.kind} · {item.size_bytes} 字节
                        </small>
                      </span>
                    </summary>
                    <dl>
                      <dt>SHA-256</dt>
                      <dd>
                        <code>{item.sha256}</code>
                      </dd>
                    </dl>
                  </details>
                ))}
              </div>
            ) : (
              <p className="eng-muted">没有固定产物元数据。</p>
            )}
          </details>

          <details className="eng-evidence-disclosure">
            <summary>工程自测</summary>
            <CheckList title="工程自测" checks={evidence.self_checks} />
          </details>
        </section>
      ) : null}

      <ReviewForm
        task={task}
        run={run}
        artifacts={artifacts}
        evidence={evidence}
        readOnly={readOnly}
        onDone={onReviewed}
      />
    </div>
  );
}
