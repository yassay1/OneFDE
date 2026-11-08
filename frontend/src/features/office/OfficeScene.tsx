import { Link } from "react-router-dom";
import type { OfficeRoleId, RoleStatus } from "./roleStatus";

const HOTSPOTS: {
  role: OfficeRoleId;
  to: string;
  name: string;
  title: string;
  left: string;
  width: string;
  bubbleTop: string;
}[] = [
  {
    role: "business",
    to: "/business",
    name: "Business",
    title: "客户与经营",
    left: "2%",
    width: "23.5%",
    bubbleTop: "6%",
  },
  {
    role: "fde",
    to: "/fde",
    name: "FDE",
    title: "方案与交付",
    left: "26%",
    width: "23.5%",
    bubbleTop: "6%",
  },
  {
    role: "engineering",
    to: "/engineering",
    name: "Engineering",
    title: "软件开发",
    left: "50.5%",
    width: "23.5%",
    bubbleTop: "6%",
  },
  {
    role: "knowledge",
    to: "/knowledge?role=fde&purpose=delivery",
    name: "Knowledge",
    title: "知识与能力",
    left: "74.5%",
    width: "23.5%",
    bubbleTop: "6%",
  },
];

type Props = {
  statuses: RoleStatus[];
};

export function OfficeScene({ statuses }: Props) {
  const byRole = Object.fromEntries(statuses.map((s) => [s.role, s])) as Record<
    OfficeRoleId,
    RoleStatus
  >;

  return (
    <div className="office-scene" aria-label="四位员工办公室">
      <img
        className="office-scene-image"
        src="/office-scene.png"
        alt="OneFDE 办公室：Business、FDE、Engineering、Knowledge"
        draggable={false}
      />
      {HOTSPOTS.map((spot) => {
        const status = byRole[spot.role];
        return (
          <Link
            key={spot.role}
            to={spot.to}
            className="office-hotspot"
            style={{ left: spot.left, width: spot.width }}
            aria-label={`进入 ${spot.name}：${status?.label ?? ""}`}
          >
            <span
              className={`office-bubble office-bubble--${status?.tone ?? "idle"}`}
              style={{ top: spot.bubbleTop }}
              title={status?.label}
            >
              <span className="office-bubble-dot" aria-hidden />
              <span className="office-bubble-text">{status?.label ?? "—"}</span>
            </span>
            <span className="office-role-tag">
              <strong>{spot.name}</strong>
              <span>{spot.title}</span>
            </span>
          </Link>
        );
      })}
    </div>
  );
}
