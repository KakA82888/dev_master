// 后端 API 客户端（fetch 封装）。401 统一抛出，由页面层回登录。
import type {
  FeedbackInfo,
  ReportDetail,
  ReportSummary,
  ScheduleInfo,
  UserInfo,
} from "./types";

const TOKEN_KEY = "ra_token";
const USER_KEY = "ra_user";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setSession(token: string, username: string) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, username);
}
export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}
export function getUsername(): string {
  return localStorage.getItem(USER_KEY) || "";
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function http<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(path, { ...options, headers });
  if (res.status === 204) return undefined as T;
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    /* 非 JSON */
  }
  if (!res.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `请求失败（HTTP ${res.status}）`;
    throw new ApiError(res.status, detail);
  }
  return body as T;
}

export interface TokenResp {
  access_token: string;
  token_type?: string;
}

export const api = {
  register: (username: string, password: string) =>
    http<TokenResp>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  login: (username: string, password: string) =>
    http<TokenResp>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  // 当前用户信息（含角色），登录后拉取以决定是否展示管理员入口
  me: () => http<UserInfo>("/api/auth/me"),

  generate: (instruction: string) =>
    http<ReportDetail>("/api/reports/generate", {
      method: "POST",
      body: JSON.stringify({ instruction }),
    }),
  getReport: (id: number) => http<ReportDetail>(`/api/reports/${id}`),
  listReports: (limit = 50, scope: "self" | "all" = "self") =>
    http<ReportSummary[]>(`/api/reports?limit=${limit}&scope=${scope}`),
  // 批量任务：一次提交多条指令（任务书 §2.2 目标 1）
  generateBatch: (instructions: string[]) =>
    http<{ batch_id: string; report_ids: number[]; total: number }>(
      "/api/reports/generate/batch",
      { method: "POST", body: JSON.stringify({ instructions }) },
    ),

  // 修改意见（任务书 §2.2 目标 4：修改意见沉淀用于优化生成模板）
  createFeedback: (reportId: number, category: string, content: string) =>
    http<FeedbackInfo>(`/api/reports/${reportId}/feedback`, {
      method: "POST",
      body: JSON.stringify({ category, content }),
    }),
  listFeedback: (reportId: number) =>
    http<FeedbackInfo[]>(`/api/reports/${reportId}/feedback`),

  // 定时任务（任务书 §2.2 目标 1 / §3.2「定时调度器」）
  listSchedules: () => http<ScheduleInfo[]>("/api/schedules"),
  createSchedule: (body: { name: string; instruction: string; cron: string; enabled: boolean }) =>
    http<ScheduleInfo>("/api/schedules", { method: "POST", body: JSON.stringify(body) }),
  updateSchedule: (
    id: number,
    body: Partial<{ name: string; instruction: string; cron: string; enabled: boolean }>,
  ) => http<ScheduleInfo>(`/api/schedules/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteSchedule: (id: number) => http<void>(`/api/schedules/${id}`, { method: "DELETE" }),
  runSchedule: (id: number) => http<ScheduleInfo>(`/api/schedules/${id}/run`, { method: "POST" }),
  confirm: (id: number) =>
    http<ReportDetail>(`/api/reports/${id}/confirm`, { method: "POST" }),
  archive: (id: number) =>
    http<ReportDetail>(`/api/reports/${id}/archive`, { method: "POST" }),
  remove: (id: number) =>
    http<void>(`/api/reports/${id}`, { method: "DELETE" }),

  // 导出下载：解析 Content-Disposition 中文文件名（filename*=UTF-8''...）
  async download(id: number, fmt: "docx" | "markdown"): Promise<void> {
    const res = await fetch(`/api/reports/${id}/export?fmt=${fmt}`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    if (!res.ok) {
      let detail = `导出失败（HTTP ${res.status}）`;
      try {
        const j = await res.json();
        if (j && j.detail) detail = String(j.detail);
      } catch {
        /* ignore */
      }
      throw new ApiError(res.status, detail);
    }
    const blob = await res.blob();
    const cd = res.headers.get("Content-Disposition") || "";
    let filename = `report-${id}.${fmt === "docx" ? "docx" : "md"}`;
    const star = cd.match(/filename\*=UTF-8''([^;]+)/i);
    if (star) {
      filename = decodeURIComponent(star[1]);
    } else {
      const plain = cd.match(/filename="?([^";]+)"?/i);
      if (plain) filename = plain[1];
    }
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
};

export function humanTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(
    d.getHours(),
  )}:${p(d.getMinutes())}`;
}
