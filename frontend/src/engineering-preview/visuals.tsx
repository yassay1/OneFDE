import type { ReactNode } from "react";

const paths: Record<string, ReactNode> = {
  folder: <path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />,
  code: <path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-15-2 18" />,
  arrow: <path d="M4 12h15m-6-6 6 6-6 6" />,
  file: <path d="M13 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V10zm0 0v7h7M8 14h8m-8 3h5" />,
  check: <path d="m5 12 4 4L19 6" />,
  history: <><path d="M3 12a9 9 0 1 1 3 6.7M3 6v6h6" /><path d="M12 7v5l3 2" /></>,
  box: <><path d="m3 7 9-4 9 4v10l-9 4-9-4zM3 7l9 4 9-4m-9 4v10" /></>,
};

export function Icon({ name, size = 18 }: { name: keyof typeof paths; size?: number }) {
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}
