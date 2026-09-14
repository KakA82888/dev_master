// 页面：Login / Workbench / History + App 外壳与 hash 路由
import { useCallback, useEffect, useRef, useState } from "react";
import type { ReportDetail, ReportSummary, UserInfo } from "./types";
import { TYPE_LABEL, STATUS_LABEL, isGateBlocked, failureTitle, isAdmin } from "./types";
import { api, ApiError, getUsername, humanTime, setSession, clearSession } from "./api";
import { toast, StatusBadge, EmptyState, SkeletonLines, Spinner } from "./ui";
import { ReportViewer, ReportActions } from "./report";

/* ================= 登录 / 注册 ================= */
export function LoginPage({ onLogin }: { onLogin: (username: string) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setError("");
    if (!username.trim() || password.length < 6) {
      setError("请输入用户名，密码至少 6 位");
      return;
    }
    setBusy(true);
    try {
      const r =
        mode === "login"
          ? await api.login(username.trim(), password)
          : await api.register(username.trim(), password);
      setSession(r.access_token, username.trim());
      toast.success(mode === "login" ? "登录成功" : "注册成功，已自动登录");
      onLogin(username.trim());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "网络错误，请稍后再试");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <div className="auth-logo">
          <div className="mark" aria-hidden="true">
            报
          </div>
          <h1>电商运营报表自动化 Agent</h1>
          <p>自然语言下指令，自动生成经营报表</p>
        </div>
        <label className="label" htmlFor="u">
          用户名
        </label>
        <input
          id="u"
          className="input"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="请输入用户名"
        />
        <div style={{ height: 12 }} />
        <label className="label" htmlFor="p">
          密码
        </label>
        <input
          id="p"
          className="input"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder={mode === "register" ? "至少 6 位" : "请输入密码"}
        />
        {error && (
          <p className="field-error" role="alert">
            {error}
          </p>
        )}
        <div style={{ height: 16 }} />
        <button className="btn btn-primary" style={{ width: "100%" }} disabled={busy} onClick={submit}>
          {busy ? <Spinner size={14} /> : mode === "login" ? "登 录" : "注册并登录"}
        </button>
        <p className="auth-switch">
          {mode === "login" ? "还没有账号？" : "已有账号？"}
          <button
            onClick={() => {
              setMode(mode === "login" ? "register" : "login");
              setError("");
            }}
          >
            {mode === "login" ? "立即注册" : "去登录"}
          </button>
        </p>
        <p className="auth-switch muted small">演示种子账号：demo / demo1234</p>
      </div>
    </div>
  );
}

/* ================= 顶部外壳 ================= */
export function AppShell({
  route,
  user,
  onRoute,
  onLogout,
  children,
}: {
  route: string;
  user: UserInfo | null;
  onRoute: (r: string) => void;
  onLogout: () => void;
  children: React.ReactNode;
}) {
  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <span className="brand-mark" aria-hidden="true">
              报
            </span>
            报表 Agent
          </div>
          <nav className="nav" aria-label="主导航">
            <a className={route === "workbench" ? "active" : ""} onClick={() => onRoute("workbench")}>
              工作台
            </a>
            <a className={route === "history" ? "active" : ""} onClick={() => onRoute("history")}>
              历史报告
            </a>
          </nav>
          <div className="spacer" />
          <span className="user-chip">
            <span aria-hidden="true">👤</span> {getUsername()}
            {isAdmin(user) && (
              <span className="role-badge" title="管理员：可查看全部用户的报告">
                管理员
              </span>
            )}
          </span>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => {
              clearSession();
              onLogout();
            }}
          >
            退出
          </button>
        </div>
      </header>
      {children}
    </>
  );
}

/* ================= 工作台 ================= */
const EXAMPLES = ["生成昨日日报", "上周德国周报", "本月全市场月报"];

export function WorkbenchPage({
  onOpenHistory,
  initialReportId,
}: {
  onOpenHistory: () => void;
  initialReportId?: number | null;
}) {
  const [instruction, setInstruction] = useState("");
  const [generating, setGenerating] = useState<ReportDetail | null>(null);
  const [current, setCurrent] = useState<ReportDetail | null>(null);
  const [recent, setRecent] = useState<ReportSummary[]>([]);
  const [loadingRecent, setLoadingRecent] = useState(true);
  const [submitBusy, setSubmitBusy] = useState(false);
  const timer = useRef<number | null>(null);
  const GENERATING_KEY = "wb_report_generating_id";

  // 从历史页定位到指定报告
  useEffect(() => {
    if (!initialReportId) return;
    api
      .getReport(initialReportId)
      .then((d) => setCurrent(d))
      .catch((e) =>
        toast.error(e instanceof ApiError ? e.message : "加载报告失败"),
      );
  }, [initialReportId]);

  // 页面刷新后：若之前有正在生成的报告，自动恢复轮询
  useEffect(() => {
    const saved = localStorage.getItem(GENERATING_KEY);
    if (!saved) return;
    const id = Number(saved);
    if (!id) {
      localStorage.removeItem(GENERATING_KEY);
      return;
    }
    api
      .getReport(id)
      .then((r) => {
        if (r.status === "pending" || r.status === "running") {
          setGenerating(r);
          toast.info("恢复轮询生成中的报告…");
        } else {
          setCurrent(r);
          localStorage.removeItem(GENERATING_KEY);
        }
      })
      .catch(() => localStorage.removeItem(GENERATING_KEY));
  }, []);

  const loadRecent = useCallback(async () => {
    try {
      const list = await api.listReports(8);
      setRecent(list);
    } catch {
      /* 忽略 */
    } finally {
      setLoadingRecent(false);
    }
  }, []);

  useEffect(() => {
    loadRecent();
  }, [loadRecent]);

  // 生成后轮询：1.5s/次，直到非 running/pending
  useEffect(() => {
    if (!generating) return;
    const id = generating.id;
    const poll = async () => {
      try {
        const r = await api.getReport(id);
        setGenerating(r);
        if (r.status !== "running" && r.status !== "pending") {
          setCurrent(r);
          setGenerating(null);
          localStorage.removeItem(GENERATING_KEY);
          if (r.status === "drafted") toast.info("报告已生成，请审阅确认");
          else if (r.status === "failed") {
            // 区分「安全网关拦截」（应改写指令）与「技术故障」（应重试/排查），
            // 避免一律提示"生成失败"导致用户误判为系统故障而反复重试
            if (isGateBlocked(r.error_code)) {
              toast.error(`${failureTitle(r.error_code)}：${r.error ?? "请改写指令后重试"}`);
            } else {
              toast.error(`生成失败${r.error ? "：" + r.error : ""}`);
            }
          }
          loadRecent();
        }
      } catch {
        // 不直接清空 generating，允许用户刷新页面后继续轮询
        toast.error("查询报告状态失败，刷新页面可恢复轮询");
      }
    };
    timer.current = window.setInterval(poll, 1500);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [generating, loadRecent]);

  async function submit() {
    const text = instruction.trim();
    if (!text || submitBusy) return;
    setSubmitBusy(true);
    try {
      const rep = await api.generate(text);
      setGenerating(rep);
      localStorage.setItem(GENERATING_KEY, String(rep.id));
      setCurrent(null);
      setInstruction("");
      toast.info("已提交，正在生成…");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "提交失败");
    } finally {
      setSubmitBusy(false);
    }
  }

  function pickReport(r: ReportSummary) {
    api
      .getReport(r.id)
      .then((d) => setCurrent(d))
      .catch((e) => toast.error(e instanceof ApiError ? e.message : "加载失败"));
  }

  return (
    <div className="page">
      <div className="split">
        <div style={{ minWidth: 0 }}>
          <section className="card">
            <h2 className="card-title">下达指令</h2>
            <textarea
              className="textarea"
              rows={2}
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submit();
                }
              }}
              placeholder="输入指令，例如：生成上周德国周报 / 2010年11月22日到28日的日报"
              aria-label="报表生成指令"
            />
            <div className="row-flex" style={{ marginTop: 8 }}>
              <button className="btn btn-primary" disabled={submitBusy || !instruction.trim()} onClick={submit}>
                {submitBusy ? <Spinner size={14} /> : "生成报告"}
              </button>
              <span className="muted small">Enter 提交 · Shift+Enter 换行</span>
            </div>
            <div className="chips">
              {EXAMPLES.map((ex) => (
                <button key={ex} className="chip" onClick={() => setInstruction(ex)}>
                  {ex}
                </button>
              ))}
            </div>
          </section>

          {generating && (
            <section className="card" aria-live="polite">
              <h2 className="card-title">生成中</h2>
              <div className="row-flex">
                <StatusBadge status={generating.status} />
                <span className="muted small">{generating.instruction}</span>
              </div>
              <div style={{ marginTop: 12 }}>
                <SkeletonLines lines={4} />
              </div>
            </section>
          )}

          {current && current.id ? (
            <section className="card">
              <div className="row-flex" style={{ justifyContent: "space-between" }}>
                <h2 className="card-title" style={{ margin: 0 }}>
                  报告预览
                </h2>
                <span className="muted small">{current.instruction}</span>
              </div>
              <ReportViewer report={current} />
              <ReportActions report={current} onChanged={(fresh) => { if (fresh.id) { setCurrent(fresh); loadRecent(); } else { setCurrent(null); loadRecent(); } }} />
            </section>
          ) : !generating ? (
            <section className="card">
              <EmptyState icon="📊" text="输入指令并生成后，报告预览将显示在这里" />
            </section>
          ) : null}
        </div>

        <aside style={{ minWidth: 0 }}>
          <section className="card">
            <div className="row-flex" style={{ justifyContent: "space-between" }}>
              <h2 className="card-title" style={{ margin: 0 }}>
                最近报告
              </h2>
              <button className="btn btn-ghost btn-sm" onClick={onOpenHistory}>
                全部 ›
              </button>
            </div>
            {loadingRecent ? (
              <SkeletonLines lines={4} />
            ) : recent.length === 0 ? (
              <EmptyState icon="🗂" text="还没有报告，先生成一份吧" />
            ) : (
              <div>
                {recent.map((r) => (
                  <div key={r.id} className="list-item" onClick={() => pickReport(r)}>
                    <div className="list-main">
                      <div className="list-title">{r.instruction}</div>
                      <div className="list-sub">
                        {(r.report_type && TYPE_LABEL[r.report_type]) || "—"} ·{" "}
                        {r.market && r.market !== "ALL" ? r.market : "全市场"} ·{" "}
                        {r.period_start ? `${r.period_start}~${r.period_end}` : ""} ·{" "}
                        {humanTime(r.created_at)}
                      </div>
                    </div>
                    <StatusBadge status={r.status} />
                  </div>
                ))}
              </div>
            )}
          </section>
        </aside>
      </div>
    </div>
  );
}

/* ================= 历史 ================= */
export function HistoryPage({
  onOpenReport,
  me,
}: {
  onOpenReport: (id: number) => void;
  me: UserInfo | null;
}) {
  const admin = isAdmin(me);
  const [list, setList] = useState<ReportSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [type, setType] = useState("");
  const [market, setMarket] = useState("");
  const [status, setStatus] = useState("");
  const [keyword, setKeyword] = useState("");
  const [markets, setMarkets] = useState<string[]>([]);
  // 管理员可切换查看范围（对应任务书 §6.2「按角色控制数据访问权限」）
  const [scope, setScope] = useState<"self" | "all">("self");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await api.listReports(200, admin ? scope : "self");
      setList(rows);
      const ms = Array.from(new Set(rows.map((r) => (r.market && r.market !== "ALL" ? r.market : "全市场"))));
      setMarkets(ms);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "加载历史失败");
    } finally {
      setLoading(false);
    }
  }, [admin, scope]);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = list.filter((r) => {
    if (type && TYPE_LABEL[r.report_type || ""] !== type) return false;
    const m = r.market && r.market !== "ALL" ? r.market : "全市场";
    if (market && m !== market) return false;
    if (status && STATUS_LABEL[r.status] !== status) return false;
    if (keyword && !r.instruction.includes(keyword.trim())) return false;
    return true;
  });

  return (
    <div className="page">
      <section className="card">
        <h2 className="card-title">历史报告</h2>
        <div className="filter-row">
          {admin && (
            <select
              className="input"
              value={scope}
              onChange={(e) => setScope(e.target.value as "self" | "all")}
              aria-label="数据范围"
            >
              <option value="self">仅我的报告</option>
              <option value="all">全部用户报告</option>
            </select>
          )}
          <input
            className="input"
            style={{ flex: 1, minWidth: 180 }}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="搜索指令关键字…"
            aria-label="搜索关键字"
          />
          <select className="input" value={type} onChange={(e) => setType(e.target.value)} aria-label="按类型筛选">
            <option value="">全部类型</option>
            <option value="日报">日报</option>
            <option value="周报">周报</option>
            <option value="月报">月报</option>
          </select>
          <select className="input" value={market} onChange={(e) => setMarket(e.target.value)} aria-label="按市场筛选">
            <option value="">全部市场</option>
            {markets.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          <select className="input" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="按状态筛选">
            <option value="">全部状态</option>
            <option>排队</option>
            <option>生成中</option>
            <option>待确认</option>
            <option>已确认</option>
            <option>已归档</option>
            <option>失败</option>
          </select>
        </div>
        {loading ? (
          <SkeletonLines lines={5} />
        ) : filtered.length === 0 ? (
          <EmptyState icon="🔍" text="没有符合条件的报告" />
        ) : (
          <div>
            {filtered.map((r) => (
              <div key={r.id} className="list-item" onClick={() => onOpenReport(r.id)}>
                <div className="list-main">
                  <div className="list-title">{r.instruction}</div>
                  <div className="list-sub">
                    {admin && r.owner ? `${r.owner.username} · ` : ""}
                    {(r.report_type && TYPE_LABEL[r.report_type]) || "—"} ·{" "}
                    {r.market && r.market !== "ALL" ? r.market : "全市场"} ·{" "}
                    {r.period_start ? `${r.period_start}~${r.period_end}` : "—"} · {humanTime(r.created_at)}
                  </div>
                </div>
                <StatusBadge status={r.status} />
              </div>
            ))}
            <p className="muted small" style={{ marginTop: 10 }}>
              共 {filtered.length} 条{list.length > 200 ? "（仅显示最近 200 条）" : ""}
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
