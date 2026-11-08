import { Alert, Button, Input } from "antd";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import {
  conflictMessage,
  createIdempotencyGate,
  invalidateEngineering,
  postJson,
  problem,
  type Artifact,
  type Run,
  type RunReviewEvidence,
  type Task,
} from "../../api";

type Props = {
  task: Task;
  run: Run;
  artifacts: Artifact[];
  evidence: RunReviewEvidence | null | undefined;
  readOnly: boolean;
  onDone?: () => void;
};

export function ReviewForm({ task, run, artifacts, evidence, readOnly, onDone }: Props) {
  const client = useQueryClient();
  const gate = useRef(createIdempotencyGate()).current;
  const [reason, setReason] = useState("");
  const [checkEvidence, setCheckEvidence] = useState("");
  const [notice, setNotice] = useState<string>();
  const [busy, setBusy] = useState<"accept" | "request_changes" | null>(null);

  useEffect(() => {
    setReason("");
    setCheckEvidence("");
    setNotice(undefined);
    gate.reset();
  }, [run.id, task.spec_version, gate]);

  const reviewable =
    !readOnly &&
    task.state === "review" &&
    run.id === task.latest_run_id &&
    run.task_spec_version === task.spec_version &&
    run.outcome === "submitted" &&
    artifacts.length > 0 &&
    task.pending_input_count === 0;

  async function submit(verdict: "accept" | "request_changes") {
    if (!reviewable || busy) return;
    if (!reason.trim()) return;
    if (verdict === "accept" && !checkEvidence.trim()) return;
    const body = {
      expected_revision: task.revision,
      run_id: run.id,
      task_spec_version: task.spec_version,
      artifact_ids: artifacts.map((item) => item.id),
      verdict,
      reason: reason.trim(),
      check_evidence: verdict === "accept" ? [checkEvidence.trim()] : [],
    };
    setBusy(verdict);
    setNotice(undefined);
    try {
      await postJson(`/api/v1/tasks/${task.id}/reviews`, body, gate.keyFor(body));
      gate.reset();
      await invalidateEngineering(client, {
        engagementId: task.engagement_id,
        taskId: task.id,
        runId: run.id,
      });
      setNotice(verdict === "accept" ? "已接受这一版固定提交。" : "已要求修改，任务回到草稿。");
      onDone?.();
    } catch (error) {
      const conflict = conflictMessage(error);
      if (conflict) {
        await invalidateEngineering(client, {
          engagementId: task.engagement_id,
          taskId: task.id,
          runId: run.id,
        });
        setNotice(conflict);
      } else setNotice(problem(error));
    } finally {
      setBusy(null);
    }
  }

  if (readOnly) {
    return <p className="eng-muted">历史轮次不可评审。</p>;
  }

  if (!reviewable) {
    return (
      <div className="eng-review-gate">
        <p className="eng-muted">
          只有当前待评审、规格匹配、带有固定产物且无 pending 输入的提交可以正式评审。
        </p>
        {task.pending_input_count > 0 ? <p>存在待处理输入，请先采用或拒绝。</p> : null}
        {evidence === null ? <Alert type="warning" showIcon message="本轮没有固定评审证据，请勿把缺失当成已通过。" /> : null}
        {evidence && evidence.validation_passed === false ? (
          <Alert type="warning" showIcon message="独立复验未通过。若仍要接受，须在检查依据中说明理由。" />
        ) : null}
        {evidence && evidence.validation_passed === null ? (
          <Alert type="info" showIcon message="独立复验结论为未验证。" />
        ) : null}
      </div>
    );
  }

  return (
    <section className="eng-review-form" aria-label="业务评审">
      <h3>业务评审</h3>
      <p className="eng-review-binding">
        绑定 Run {run.id.slice(0, 8)}… · 规格 v{task.spec_version} · 产物 {artifacts.length} 个
      </p>
      {evidence?.validation_passed === false ? (
        <Alert type="warning" showIcon message="独立复验未通过。接受前请写明检查依据。" />
      ) : null}
      {evidence?.validation_passed === null ? (
        <Alert type="info" showIcon message="独立复验未验证。接受前请写明检查依据。" />
      ) : null}
      <label className="eng-field">
        评审意见
        <Input.TextArea rows={3} value={reason} onChange={(event) => setReason(event.target.value)} />
      </label>
      <label className="eng-field">
        接受时的检查依据
        <Input
          value={checkEvidence}
          onChange={(event) => setCheckEvidence(event.target.value)}
          placeholder="例如：核对 Diff、自测与独立复验结果"
        />
      </label>
      <div className="eng-actions">
        <Button
          loading={busy === "request_changes"}
          disabled={!reason.trim() || Boolean(busy)}
          onClick={() => submit("request_changes")}
        >
          要求修改
        </Button>
        <Button
          type="primary"
          loading={busy === "accept"}
          disabled={!reason.trim() || !checkEvidence.trim() || Boolean(busy)}
          onClick={() => submit("accept")}
        >
          接受成果
        </Button>
      </div>
      {notice ? <Alert type="info" showIcon message={notice} style={{ marginTop: 12 }} /> : null}
    </section>
  );
}
