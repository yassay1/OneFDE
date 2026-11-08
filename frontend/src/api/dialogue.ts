export type StaffTurn = {
  id: string;
  role: string;
  author: string;
  text: string;
  basis: Record<string, unknown>;
  adapter: "staff" | "scripted" | "live";
  created_at: string;
};

export type DialoguePage = { turns: StaffTurn[] };

export type RuntimeBeat = {
  name: "fde_agent" | "engineering_worker";
  state: "running" | "not_running";
  beat_at: string | null;
  age_seconds: number | null;
  detail: string;
};

export type RuntimeStatus = {
  fde_agent: RuntimeBeat;
  engineering_worker: RuntimeBeat;
};

export function adapterLabel(adapter: string) {
  if (adapter === "live") return "模型";
  if (adapter === "scripted") return "测试替身";
  return "员工";
}
