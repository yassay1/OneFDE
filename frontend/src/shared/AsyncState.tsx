import { Alert, Button, Skeleton } from "antd";
import type { ReactNode } from "react";
import { problem } from "../api";

type Props = {
  loading?: boolean;
  error?: unknown;
  empty?: boolean;
  emptyText?: ReactNode;
  onRetry?: () => void;
  children: ReactNode;
};

export function AsyncState({ loading, error, empty, emptyText, onRetry, children }: Props) {
  if (loading) {
    return (
      <div className="async-state" role="status" aria-live="polite">
        <Skeleton active paragraph={{ rows: 4 }} />
      </div>
    );
  }
  if (error) {
    return (
      <div className="async-state">
        <Alert
          type="error"
          showIcon
          message={problem(error)}
          action={onRetry ? <Button size="small" onClick={onRetry}>重试</Button> : undefined}
        />
      </div>
    );
  }
  if (empty) {
    return <div className="async-state async-empty">{emptyText ?? "暂无数据。"}</div>;
  }
  return <>{children}</>;
}
