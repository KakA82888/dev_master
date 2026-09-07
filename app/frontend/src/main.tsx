// 入口：鉴权状态 + hash 路由 + Toast 宿主
import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./tokens.css";
import "./styles.css";
import { getToken } from "./api";
import { ToastHost } from "./ui";
import { AppShell, HistoryPage, LoginPage, WorkbenchPage } from "./pages";

function readHash(): string {
  const h = window.location.hash.replace(/^#\/?/, "");
  return h.startsWith("history") ? "history" : "workbench";
}

function App() {
  const [authed, setAuthed] = useState<boolean>(() => Boolean(getToken()));
  const [route, setRoute] = useState<string>(readHash());
  const [pendingReportId, setPendingReportId] = useState<number | null>(null);

  useEffect(() => {
    window.location.hash = route === "history" ? "#/history" : "#/workbench";
  }, [route]);

  if (!authed) {
    return (
      <>
        <LoginPage
          onLogin={() => {
            setAuthed(true);
            setRoute("workbench");
          }}
        />
        <ToastHost />
      </>
    );
  }

  return (
    <>
      <AppShell
        route={route}
        onRoute={(r) => {
          setRoute(r);
          if (r === "history") setPendingReportId(null);
        }}
        onLogout={() => {
          setAuthed(false);
          setPendingReportId(null);
        }}
      >
        {route === "history" ? (
          <HistoryPage
            onOpenReport={(id) => {
              setPendingReportId(id);
              setRoute("workbench");
            }}
          />
        ) : (
          <WorkbenchPage
            initialReportId={pendingReportId}
            onOpenHistory={() => setRoute("history")}
          />
        )}
      </AppShell>
      <ToastHost />
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
