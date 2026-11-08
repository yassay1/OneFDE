import { label, RUN_STATE, TASK_STATE } from "./labels";

export function TaskStatus({ state }: { state: string }) {
  return <span className={`status-badge task-state-${state}`}>{label(TASK_STATE, state)}</span>;
}

export function RunStatus({ state, outcome }: { state: string; outcome?: string | null }) {
  const text = outcome ? `${label(RUN_STATE, state)} / ${outcome}` : label(RUN_STATE, state);
  return <span className={`status-badge run-state-${state}`}>{text}</span>;
}
