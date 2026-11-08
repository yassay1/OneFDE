import { Outlet } from "react-router-dom";
import { LoginPage } from "../features/auth/LoginPage";
import { useSession } from "./session";

export function RequireSession() {
  const session = useSession();
  if (session.isLoading) return <main className="shell-loading" role="status">正在确认登录。</main>;
  if (session.isError) return <LoginPage />;
  return <Outlet />;
}
