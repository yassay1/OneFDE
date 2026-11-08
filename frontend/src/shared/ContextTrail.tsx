import { Link } from "react-router-dom";

type Crumb = { label: string; to?: string };

export function ContextTrail({ items }: { items: Crumb[] }) {
  return (
    <nav className="context-trail" aria-label="当前位置">
      {items.map((item, index) => (
        <span key={`${item.label}-${index}`}>
          {index > 0 ? <span className="trail-sep" aria-hidden="true">/</span> : null}
          {item.to ? <Link to={item.to}>{item.label}</Link> : <span aria-current="page">{item.label}</span>}
        </span>
      ))}
    </nav>
  );
}
