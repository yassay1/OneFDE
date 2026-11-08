import { Alert, Button } from "antd";
import type { KnowledgePurpose } from "../../api";
import { assetLabel } from "./assetLabels";
function typeLabel(value: string | null) { if (!value) return "资产"; return ({ business_module: "业务模块", industry_knowledge: "行业知识", engineering_experience: "工程经验" } as Record<string,string>)[value] ?? value; }

export function AssetDetail({
  asset,
  purpose,
  citation,
  copied,
  onCopy,
}: {
  asset: Record<string, unknown>;
  purpose: KnowledgePurpose;
  citation: string;
  copied?: string;
  onCopy: () => void;
}) {
  const publicOnly = purpose === "public_marketing" || asset.visibility === "public_summary_only";
  const listFields = [
    ["问题", asset.problem],
    ["类型", asset.type ? typeLabel(String(asset.type)) : null],
    ["验证状态", assetLabel(asset.verification_status)],
    ["可见性", assetLabel(asset.visibility)],
    ["复用范围", assetLabel(asset.reuse_scope)],
    ["来源项目", asset.source_engagement],
    ["实现引用", asset.implementation_ref],
    ["更新时间", asset.updated_at],
    ["输入", asset.inputs],
    ["输出", asset.outputs],
    ["实现归档摘要", asset.implementation_archive_sha256],
  ] as const;

  return (
    <article className="knowledge-asset">
      <header>
        <div className="knowledge-result-top">
          <span className="knowledge-type-badge">{typeLabel(asset.type ? String(asset.type) : null)}</span>
          {asset.verification_status ? (
            <span className="knowledge-verify-badge">{String(assetLabel(asset.verification_status))}</span>
          ) : null}
        </div>
        <h3>{String(asset.name ?? asset.id)}</h3>
        <p className="eng-muted">
          {String(asset.id)}@{String(asset.version ?? "")}
        </p>
      </header>

      {publicOnly ? (
        <>
          <Alert type="info" showIcon message="公开营销用途仅显示公开摘要投影，不含私有实现字段。" />
          <p className="business-message">{String(asset.public_summary ?? "无公开摘要。")}</p>
        </>
      ) : (
        <>
          <dl className="knowledge-facts">
            {listFields.map(([label, value]) =>
              value ? (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{Array.isArray(value) ? value.join("；") : String(value)}</dd>
                </div>
              ) : null,
            )}
          </dl>
          {Array.isArray(asset.applicable_when) && asset.applicable_when.length ? (
            <>
              <h4>适用条件</h4>
              <ul>
                {asset.applicable_when.map((item) => (
                  <li key={String(item)}>{String(item)}</li>
                ))}
              </ul>
            </>
          ) : null}
          {Array.isArray(asset.not_applicable_when) && asset.not_applicable_when.length ? (
            <>
              <h4>限制 / 不适用</h4>
              <ul>
                {asset.not_applicable_when.map((item) => (
                  <li key={String(item)}>{String(item)}</li>
                ))}
              </ul>
            </>
          ) : null}
          {Array.isArray(asset.evidence) && asset.evidence.length ? (
            <details open>
              <summary>获准来源 / 证据引用</summary>
              <ul>
                {asset.evidence.map((item) => (
                  <li key={String(item)}>
                    <code>{String(item)}</code>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
          {Array.isArray(asset.verified_samples) && asset.verified_samples.length ? (
            <details>
              <summary>验证样例</summary>
              <p>{asset.verified_samples.map(String).join("、")}</p>
            </details>
          ) : null}
        </>
      )}

      <div className="knowledge-cite">
        <code>{citation || "无可复制引用"}</code>
        <Button type="primary" disabled={!citation} onClick={onCopy}>
          复制固定版本引用
        </Button>
      </div>
      {copied ? <p className="eng-muted">已复制 {copied}</p> : null}
      <p className="eng-muted">引用供回到原工作使用；查询结果不自动变成资产确认或执行授权。</p>
    </article>
  );
}
