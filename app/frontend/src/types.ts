// 报告状态机（对齐后端 models.py）
export type ReportStatus =
  | "pending"
  | "running"
  | "drafted"
  | "confirmed"
  | "archived"
  | "failed";

export interface UserInfo {
  id: number;
  username: string;
  role: string;
}

export const ROLE_ADMIN = "admin";

export function isAdmin(user?: UserInfo | null): boolean {
  return !!user && user.role === ROLE_ADMIN;
}

export interface ReportSummary {
  id: number;
  instruction: string;
  report_type?: string | null;
  period_start?: string | null;
  period_end?: string | null;
  market?: string | null;
  status: string;
  error?: string | null;
  error_code?: string | null;
  // 报告归属：管理员查看他人报告时用于区分（普通用户即本人，非敏感信息）
  owner?: UserInfo | null;
  created_at?: string | null;
}

export interface ReportDetail extends ReportSummary {
  title?: string | null;
  markdown?: string | null;
  metrics_json?: string | null;
  version?: number;
  updated_at?: string | null;
  confirmed_at?: string | null;
}

// 安全网关拦截 / 指令不合规类原因码：应引导用户改写指令，
// 而不是笼统提示"生成失败"（那会让人误以为是系统故障而反复重试）。
export const GATE_BLOCK_CODES: string[] = [
  "injection",     // 提示词注入
  "overreach",     // 越权
  "fabrication",   // 要求伪造数值
  "unsupported",   // 不支持的口径
  "sqli",          // 危险 SQL 片段
  "out_of_range",  // 日期越界
  "invalid_date",  // 无效日期
  "invalid_range", // 区间起止颠倒
  "blocked",       // 兜底拦截码
];

export function isGateBlocked(code?: string | null): boolean {
  return !!code && GATE_BLOCK_CODES.includes(code);
}

export function failureTitle(code?: string | null): string {
  return isGateBlocked(code) ? "指令被安全网关拦截" : "生成失败";
}

export const STATUS_LABEL: Record<string, string> = {
  pending: "排队",
  running: "生成中",
  drafted: "待确认",
  confirmed: "已确认",
  archived: "已归档",
  failed: "失败",
};

export const TYPE_LABEL: Record<string, string> = {
  daily: "日报",
  weekly: "周报",
  monthly: "月报",
};
