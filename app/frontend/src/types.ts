// 报告状态机（对齐后端 models.py）
export type ReportStatus =
  | "pending"
  | "running"
  | "drafted"
  | "confirmed"
  | "archived"
  | "failed";

export interface ReportSummary {
  id: number;
  instruction: string;
  report_type?: string | null;
  period_start?: string | null;
  period_end?: string | null;
  market?: string | null;
  status: string;
  created_at?: string | null;
}

export interface ReportDetail extends ReportSummary {
  title?: string | null;
  markdown?: string | null;
  metrics_json?: string | null;
  error?: string | null;
  version?: number;
  updated_at?: string | null;
  confirmed_at?: string | null;
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
