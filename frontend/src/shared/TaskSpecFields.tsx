import { Input } from "antd";
import type { TaskSpec } from "../api";

const FIELDS = [
  ["title", "任务标题"], ["objective", "工作目标"], ["scope", "工作范围与限制"],
  ["inputs", "输入与来源（每行一项）"], ["confirmed_rules", "已确认规则（每行一项）"],
  ["completion_criteria", "完成条件（每行一项，至少一项）"],
  ["capability_versions", "选用能力版本（每行一个 id@version，可留空）"],
] as const;

export function TaskSpecFields({ spec, onChange }: { spec: TaskSpec; onChange: (spec: TaskSpec) => void }) {
  return <div className="spec-fields">{FIELDS.map(([name, label]) => (
    <label key={name} className="eng-field"><span>{label}</span>
      <Input.TextArea rows={name === "title" ? 1 : 2} value={Array.isArray(spec[name]) ? spec[name].join("\n") : spec[name]}
        onChange={(event) => onChange({ ...spec, [name]: Array.isArray(spec[name]) ? event.target.value.split("\n") : event.target.value })} />
    </label>
  ))}</div>;
}

export function cleanSpec(spec: TaskSpec): TaskSpec {
  return { ...spec, title: spec.title.trim(), objective: spec.objective.trim(), scope: spec.scope.trim(),
    inputs: spec.inputs.map((x) => x.trim()).filter(Boolean), confirmed_rules: spec.confirmed_rules.map((x) => x.trim()).filter(Boolean),
    completion_criteria: spec.completion_criteria.map((x) => x.trim()).filter(Boolean), capability_versions: spec.capability_versions.map((x) => x.trim()).filter(Boolean) };
}
