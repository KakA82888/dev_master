// 入口：鉴权状态 + hash 路由 + Toast 宿主
import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./tokens.css";
import "./styles.css";
import { api, getToken } from "./api";
import type { UserInfo } from "./types";
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
  const [me, setMe] = useState<UserInfo | null>(null);

  useEffect(() => {
    window.location.hash = route === "history" ? "#/history" : "#/workbench";
  }, [route]);

  // 已登录时拉取当前用户信息（含角色），用于控制管理员入口的展示
  useEffect(() => {
    if (!authed) {
      setMe(null);
      return;
    }
    let alive = true;
    api
      .me()
      .then((u) => {
        if (alive) setMe(u);
      })
      .catch(() => {
        /* 拉取失败不阻断使用，仅不展示管理员入口 */
      });
    return () => {
      alive = false;
    };
  }, [authed]);

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
        user={me}
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
            me={me}
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
