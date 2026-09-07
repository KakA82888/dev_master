// 轻量 Markdown 块解析：仅覆盖后端 report_builder 固定结构
// # 标题 / > 引用 / ## 小节 / 管道表格 / - 列表 / --- / 普通段落

export type Block =
  | { kind: "h1"; text: string }
  | { kind: "h2"; text: string }
  | { kind: "h3"; text: string }
  | { kind: "quote"; text: string }
  | { kind: "p"; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "table"; rows: string[][]; header: string[] };

const RE_TABLE_ROW = /^\|/;
const RE_TABLE_SEP = /^\|[\s:\-|]+\|?$/;
const RE_LIST = /^[-*]\s+(.*)$/;

export function parseBlocks(md: string): Block[] {
  const lines = md.split(/\r?\n/);
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i].trim();
    if (!line) {
      i += 1;
      continue;
    }
    if (line.startsWith("# ")) {
      blocks.push({ kind: "h1", text: line.slice(2).trim() });
      i += 1;
      continue;
    }
    if (line.startsWith("## ")) {
      blocks.push({ kind: "h2", text: line.slice(3).trim() });
      i += 1;
      continue;
    }
    if (line.startsWith("### ")) {
      blocks.push({ kind: "h3", text: line.slice(4).trim() });
      i += 1;
      continue;
    }
    if (line.startsWith("> ")) {
      blocks.push({ kind: "quote", text: line.slice(2).trim() });
      i += 1;
      continue;
    }
    if (RE_TABLE_ROW.test(line)) {
      const rows: string[][] = [];
      while (i < lines.length && RE_TABLE_ROW.test(lines[i].trim())) {
        const raw = lines[i].trim();
        if (!RE_TABLE_SEP.test(raw)) {
          rows.push(raw.replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim()));
        }
        i += 1;
      }
      if (rows.length > 0) {
        blocks.push({ kind: "table", header: rows[0], rows: rows.slice(1) });
      }
      continue;
    }
    const lm = line.match(RE_LIST);
    if (lm) {
      const items = [lm[1].trim()];
      i += 1;
      while (i < lines.length) {
        const inner = lines[i].trim().match(RE_LIST);
        if (!inner) break;
        items.push(inner[1].trim());
        i += 1;
      }
      blocks.push({ kind: "list", items });
      continue;
    }
    if (/^-{3,}\s*$/.test(line)) {
      i += 1;
      continue;
    }
    blocks.push({ kind: "p", text: line });
    i += 1;
  }
  return blocks;
}

/** 行内 **加粗** 拆分成片段（用于渲染富文本） */
export function splitInline(text: string): Array<{ bold: boolean; text: string }> {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts
    .filter(Boolean)
    .map((p) =>
      p.startsWith("**") && p.endsWith("**") && p.length > 4
        ? { bold: true, text: p.slice(2, -2) }
        : { bold: false, text: p },
    );
}
