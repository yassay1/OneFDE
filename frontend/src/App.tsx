import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./app/AppShell";
import { RequireSession } from "./app/RequireSession";
import { LoginPage } from "./features/auth/LoginPage";
import { BusinessCase, BusinessInbox } from "./features/business";
import { EngineeringPage } from "./features/engineering/EngineeringPage";
import { FdePage } from "./features/fde/FdePage";
import { KnowledgePage } from "./features/knowledge/KnowledgePage";
import { OfficePage } from "./features/office/OfficePage";
import { ProjectDetailPage } from "./features/projects/ProjectDetailPage";
import { ProjectsPage } from "./features/projects/ProjectsPage";

const PRODUCT_ORIGIN = import.meta.env.VITE_QUOTE_PRODUCT_URL || "http://127.0.0.1:8765/";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireSession />}>
        <Route element={<AppShell />}>
          <Route index element={<OfficePage />} />
          <Route path="projects" element={<ProjectsPage />} />
          <Route path="projects/:engagementId" element={<ProjectDetailPage />} />
          <Route path="business" element={<BusinessInbox productUrl={PRODUCT_ORIGIN} />} />
          <Route path="business/:caseId" element={<BusinessCase />} />
          <Route path="fde" element={<FdePage />} />
          <Route path="engineering" element={<EngineeringPage />} />
          <Route path="knowledge" element={<KnowledgePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Route>
    </Routes>
  );
}
