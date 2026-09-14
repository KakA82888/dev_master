// 通用 UI 组件：Toast（事件总线）、StatusBadge、Modal、Empty、Skeleton
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { ReportStatus } from "./types";
import { STATUS_LABEL } from "./types";

/* ---------------- Toast 轻量事件总线 ---------------- */
type ToastType = "success" | "error" | "info";
interface ToastItem {
  id: number;
  msg: string;
  type: ToastType;
}
let toastSeq = 0;
const toastListeners = new Set<(t: ToastItem) => void>();

function pushToast(msg: string, type: ToastType) {
  const item: ToastItem = { id: ++toastSeq, msg, type };
  toastListeners.forEach((fn) => fn(item));
}
export const toast = {
  success: (m: string) => pushToast(m, "success"),
  error: (m: string) => pushToast(m, "error"),
  info: (m: string) => pushToast(m, "info"),
};

export function ToastHost() {
  const [items, setItems] = useState<ToastItem[]>([]);
  useEffect(() => {
    const onToast = (t: ToastItem) => {
      setItems((prev) => [...prev.slice(-3), t]);
      setTimeout(() => setItems((prev) => prev.filter((x) => x.id !== t.id)), 3200);
    };
    toastListeners.add(onToast);
    return () => {
      toastListeners.delete(onToast);
    };
  }, []);
  return (
    <div className="toasts" role="status" aria-live="polite">
      {items.map((t) => (
        <div key={t.id} className={`toast toast-${t.type}`}>
          {t.msg}
        </div>
      ))}
    </div>
  );
}

/* ---------------- 状态徽章（六态，对齐状态机） ---------------- */
export function StatusBadge({ status, version }: { status: string; version?: number }) {
  const st = (status in STATUS_LABEL ? status : "pending") as ReportStatus;
  const running = st === "running" || st === "pending";
  const label = st === "confirmed" && version ? `已确认 v${version}` : STATUS_LABEL[st];
  return (
    <span className={`badge st-${st}`} aria-label={`状态：${label}`}>
      <span className="dot" aria-hidden="true" />
      {running ? `${label}…` : label}
    </span>
  );
}

/* ---------------- Modal ---------------- */
export function Modal({
  title,
  body,
  open,
  okText = "确定",
  cancelText = "取消",
  danger = false,
  onOk,
  onCancel,
  children,
}: {
  title: string;
  /** 简单文本内容；需要表单等复杂内容时改用 children */
  body?: string;
  open: boolean;
  okText?: string;
  cancelText?: string;
  danger?: boolean;
  onOk: () => void;
  onCancel: () => void;
  children?: ReactNode;
}) {
  if (!open) return null;
  return (
    <div className="modal-mask" onClick={onCancel}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <h3>{title}</h3>
        {body ? <p>{body}</p> : null}
        {children}
        <div className="modal-actions">
          <button className="btn btn-secondary" onClick={onCancel}>
            {cancelText}
          </button>
          <button className={`btn ${danger ? "btn-danger" : "btn-primary"}`} onClick={onOk} autoFocus>
            {okText}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ---------------- 空态 / 骨架 ---------------- */
export function EmptyState({ icon = "📄", text }: { icon?: string; text: string }) {
  return (
    <div className="empty">
      <div className="e-icon" aria-hidden="true">
        {icon}
      </div>
      <p className="muted small" style={{ margin: 0 }}>
        {text}
      </p>
    </div>
  );
}

export function SkeletonLines({ lines = 3 }: { lines?: number }) {
  return (
    <div aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="skeleton sk-line" style={{ width: `${88 - i * 9}%` }} />
      ))}
    </div>
  );
}

export function Spinner({ size = 16 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      style={{ animation: "spin 0.9s linear infinite" }}
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </svg>
  );
}
