// 报告预览：markdown 块 → 组件化渲染；异常行/异常区样式化；操作条对齐后端守卫
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReportDetail } from "./types";
import { TYPE_LABEL, STATUS_LABEL } from "./types";
import { api, ApiError, humanTime } from "./api";
import { parseBlocks, splitInline, type Block } from "./markdown";
import { toast, StatusBadge, Modal, Spinner } from "./ui";

/* 行内富文本 */
function Inline({ text }: { text: string }) {
  return (
    <>
      {splitInline(text).map((s, i) =>
        s.bold ? (
          <strong key={i}>{s.text}</strong>
        ) : (
          <span key={i}>{s.text}</span>
        ),
      )}
    </>
  );
}

/* 提取异常区主词：'⚠️ 客单价异动（环比 ±15%）' -> ['客单价'] */
function alertKeys(items: string[]): string[] {
  const keys: string[] = [];
  for (const it of items) {
    const cleaned = it.replace(/^[^\u4e00-\u9fa5A-Za-z]+/, ""); // 去掉 ⚠️ 等
    const m = cleaned.match(/[\u4e00-\u9fa5A-Za-z]+/);
    if (m && m[0].length >= 2) keys.push(m[0]);
  }
  return keys;
}

function SectionTitle({ text }: { text: string }) {
  return <h2>{text}</h2>;
}

function ReportBlocks({ blocks }: { blocks: Block[] }) {
  const [alertRows, setAlertRows] = useState<string[]>([]);
  const pendingKeys = useRef<string[]>([]);

  // 检测 h2 标题含“异常”后的列表 → 作为异常区（先收集 key，表格渲染时用）
  const prepared = useMemo(() => {
    const sections: Array<{ block: Block; inAlert: boolean }> = [];
    let inAlert = false;
    for (const b of blocks) {
      if (b.kind === "h2" && /异常/.test(b.text)) inAlert = true;
      else if (inAlert && b.kind !== "list" && b.kind !== "quote") inAlert = false;
      sections.push({ block: b, inAlert });
      if (b.kind === "h2") inAlert = false;
    }
    return sections;
  }, [blocks]);

  const keys = useMemo(() => {
    const arr: string[] = [];
    for (const { block, inAlert } of prepared) {
      if (inAlert && block.kind === "list") arr.push(...alertKeys(block.items));
    }
    return arr;
  }, [prepared]);

  useEffect(() => {
    setAlertRows(keys);
    pendingKeys.current = keys;
  }, [keys]);

  const isAlertRow = (firstCell: string) =>
    alertRows.some((k) => firstCell.includes(k) || k.includes(firstCell));

  return (
    <div className="report">
      {prepared.map(({ block, inAlert }, idx) => {
        const b = block;
        if (b.kind === "h1")
          return (
            <h1 key={idx}>
              <Inline text={b.text} />
            </h1>
          );
        if (b.kind === "h2") return <SectionTitle key={idx} text={b.text} />;
        if (b.kind === "h3") return <h3 key={idx}>{b.text}</h3>;
        if (b.kind === "quote")
          return (
            <p className="quote" key={idx}>
              <Inline text={b.text} />
            </p>
          );
        if (b.kind === "p")
          return (
            <p key={idx}>
              <Inline text={b.text} />
            </p>
          );
        if (b.kind === "list") {
          if (inAlert || b.items.some((it) => /⚠|✕|!|异动|异常/.test(it))) {
            return (
              <div key={idx} role="alert">
                {b.items.map((it, j) => (
                  <div className="alert-item" style={{ marginTop: j === 0 ? 8 : 6 }} key={j}>
                    <Inline text={it} />
                  </div>
                ))}
              </div>
            );
          }
          return (
            <ul key={idx}>
              {b.items.map((it, j) => (
                <li key={j}>
                  <span className="li-dot" aria-hidden="true" />
                  <Inline text={it} />
                </li>
              ))}
            </ul>
          );
        }
        if (b.kind === "table") {
          const ncol = Math.max(b.header.length, ...b.rows.map((r) => r.length));
          const cells = (row: string[], c: number) => (c < row.length ? row[c] : "");
          return (
            <table key={idx}>
              <thead>
                <tr>
                  {Array.from({ length: ncol }).map((_, c) => (
                    <th key={c}>{cells(b.header, c)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {b.rows.map((row, ri) => {
                  const alert = isAlertRow(cells(row, 0));
                  return (
                    <tr key={ri} className={alert ? "alert-row" : undefined}>
                      {Array.from({ length: ncol }).map((_, c) => (
                        <td key={c}>
                          <Inline text={cells(row, c)} />
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          );
        }
        return null;
      })}
    </div>
  );
}

export function ReportViewer({ report }: { report: ReportDetail }) {
  const blocks = useMemo(
    () => parseBlocks(report.markdown || ""),
    [report.markdown],
  );
  const type = report.report_type ? TYPE_LABEL[report.report_type] || report.report_type : "";
  const market = report.market && report.market !== "ALL" ? report.market : "全市场";
  return (
    <article aria-label="报告预览">
      <ReportBlocks blocks={blocks} />
      <div className="meta-bar">
        <span className="meta-kv">
          {type} · {market}
        </span>
        {report.period_start && (
          <>
            <span className="sep">|</span>
            <span>
              {report.period_start} ~ {report.period_end}
            </span>
          </>
        )}
        <span className="sep">|</span>
        <StatusBadge status={report.status} version={report.version} />
        <span className="sep">|</span>
        <span className="muted">生成 {humanTime(report.created_at)}</span>
      </div>
    </article>
  );
}

/* ---------------- 操作条（对齐后端状态守卫） ---------------- */
export function ReportActions({
  report,
  onChanged,
}: {
  report: ReportDetail;
  onChanged: (fresh: ReportDetail) => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const st = report.status;
  const canConfirm = st === "drafted";
  const canArchive = st === "drafted" || st === "confirmed";
  const canExport = st === "drafted" || st === "confirmed" || st === "archived";

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node))
        setExportOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  async function act(kind: "confirm" | "archive" | "delete") {
    setBusy(kind);
    try {
      if (kind === "delete") {
        await api.remove(report.id);
        toast.info("报告已删除");
        onChanged({} as ReportDetail);
      } else {
        const fresh = kind === "confirm" ? await api.confirm(report.id) : await api.archive(report.id);
        if (kind === "confirm") toast.success(`已确认 v${fresh.version}`);
        else toast.success("已归档");
        onChanged(fresh);
      }
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "操作失败");
    } finally {
      setBusy(null);
      setConfirmOpen(false);
      setDeleteOpen(false);
    }
  }

  async function doExport(fmt: "docx" | "markdown") {
    setExportOpen(false);
    setBusy("export");
    try {
      await api.download(report.id, fmt);
      toast.success(`已开始下载${fmt === "docx" ? " Word(.docx)" : " Markdown(.md)"}`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "导出失败");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="actions" aria-label="报告操作">
      <button
        className="btn btn-primary"
        disabled={!canConfirm || busy !== null}
        title={canConfirm ? "确认后进入已确认态（version+1）" : `当前状态：${STATUS_LABEL[st] || st}，不可确认`}
        onClick={() => setConfirmOpen(true)}
      >
        {busy === "confirm" ? <Spinner size={14} /> : "✓ 确认报告"}
      </button>
      <button
        className="btn btn-secondary"
        disabled={!canArchive || busy !== null}
        title={canArchive ? "归档后进入已归档态" : "仅草稿/已确认可归档"}
        onClick={() => act("archive")}
      >
        {busy === "archive" ? <Spinner size={14} /> : "归档"}
      </button>
      <div className="dropdown" ref={menuRef}>
        <button
          className="btn btn-secondary"
          disabled={!canExport || busy !== null}
          onClick={() => setExportOpen((v) => !v)}
          aria-haspopup="menu"
          aria-expanded={exportOpen}
        >
          导出 ▾
        </button>
        {exportOpen && (
          <div className="dropdown-menu" role="menu">
            <button role="menuitem" onClick={() => doExport("docx")}>
              Word (.docx)
            </button>
            <button role="menuitem" onClick={() => doExport("markdown")}>
              Markdown (.md)
            </button>
          </div>
        )}
      </div>
      <button
        className="btn btn-danger"
        disabled={busy !== null}
        title="删除该报告（不可恢复）"
        onClick={() => setDeleteOpen(true)}
      >
        {busy === "delete" ? <Spinner size={14} /> : "删除"}
      </button>
      {st === "failed" && report.error && (
        <span className="alert err small" style={{ flex: 1 }}>
          失败原因：{report.error}
        </span>
      )}

      <Modal
        open={confirmOpen}
        title="确认报告"
        body="确认后报告进入「已确认」状态，版本将 +1，之后可归档或导出。"
        okText="确认"
        onOk={() => act("confirm")}
        onCancel={() => setConfirmOpen(false)}
      />
      <Modal
        open={deleteOpen}
        title="删除报告"
        body="删除后不可恢复，确定删除该报告？"
        okText="删除"
        danger
        onOk={() => act("delete")}
        onCancel={() => setDeleteOpen(false)}
      />
    </div>
  );
}
