import { Button } from "antd";
import type { StaffTurn } from "../../api";

type Pending = {
  status?: string;
  action?: string;
  impact?: string;
  expected_revision?: number | null;
  spec_version?: number | null;
  object?: Record<string, unknown>;
};

export function hasPendingAction(turns: StaffTurn[] | undefined) {
  return (turns ?? []).some((turn) => pendingOf(turn)?.status === "pending");
}

function pendingOf(turn: StaffTurn): Pending | null {
  const value = turn.basis.pending_action;
  if (!value || typeof value !== "object") return null;
  return value as Pending;
}

export function PendingActionCard({
  turn,
  busy,
  onDecide,
}: {
  turn: StaffTurn;
  busy: boolean;
  onDecide: (turnId: string, decision: "confirm" | "decline") => void;
}) {
  const pending = pendingOf(turn);
  if (!pending || turn.author !== "assistant") return null;
  if (pending.status === "confirmed") {
    return <p className="eng-chat-notice">已确认并执行：{pending.impact}</p>;
  }
  if (pending.status === "declined") {
    return <p className="eng-chat-notice">已放弃：{pending.impact}</p>;
  }
  if (pending.status !== "pending") return null;
  const objectId = pending.object?.case_id || pending.object?.task_id || pending.object?.engagement_id;
  return (
    <div className="eng-chat-notice">
      <p>{pending.impact || pending.action}</p>
      <p>
        动作 {pending.action}
        {objectId ? ` · 对象 ${String(objectId)}` : ""}
        {pending.expected_revision ? ` · 修订 ${pending.expected_revision}` : ""}
        {pending.spec_version ? ` · 规格 ${pending.spec_version}` : ""}
      </p>
      <Button size="small" type="primary" disabled={busy} onClick={() => onDecide(turn.id, "confirm")}>
        确认执行
      </Button>{" "}
      <Button size="small" disabled={busy} onClick={() => onDecide(turn.id, "decline")}>
        放弃
      </Button>
    </div>
  );
}
