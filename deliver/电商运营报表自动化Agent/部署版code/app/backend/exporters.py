"""S5 报告导出服务：Markdown 原样导出 + Word(docx) 结构化渲染。

设计原则：docx 与 markdown「内容同源」——docx 渲染器把报告已存 markdown（即用户预览的事实）
按结构（标题/引用/小节/表格/列表/分隔线）转为 Word，保证「内容与预览一致」可测试断言。

技术栈决策：python-docx（1.2.0）程序化排版。
- 报表含动态行表格（核心指标 9 行 + 逐日明细 7~31 行），docxtpl 的行级 Jinja 模板在此类动态
  表格场景易错，故数据报表导出采用 python-docx 程序化渲染；
- docxtpl（0.20.2）保留于依赖中，用于「无动态表格」的正式模板文档场景（如后续封面/说明页）。
- 取舍结论与技术验证记录见《06_测试报告》§S5。

使用：export_markdown(report) -> str；export_docx(report) -> bytes
"""
import re
from io import BytesIO
from typing import Iterator

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

from .models import Report

# markdown 结构解析：逐行归类为 block
_H1 = re.compile(r"^#\s+(.*)$")
_H2 = re.compile(r"^##\s+(.*)$")
_H3 = re.compile(r"^###\s+(.*)$")
_QUOTE = re.compile(r"^>\s?(.*)$")
_LIST = re.compile(r"^[-*]\s+(.*)$")
_TABLE_ROW = re.compile(r"^\|")
_TABLE_SEP = re.compile(r"^\|[\s:\-|]+\|?$")
_HR = re.compile(r"^-{3,}\s*$")

_ACCENT = RGBColor(0x1F, 0x38, 0x64)  # 深蓝：标题
_GRAY = RGBColor(0x59, 0x59, 0x59)  # 灰：引用/脚注


def export_markdown(report: Report) -> str:
    """Markdown 原样导出（即已存正文，用户预览的事实）。"""
    return report.markdown or ""


def export_docx(report: Report) -> bytes:
    """把报告 markdown 结构化渲染为 docx 字节流。"""
    md = report.markdown or ""
    doc = Document()
    _setup_styles(doc)
    if report.title:
        doc.core_properties.title = report.title
    for block in _parse_blocks(md):
        _render_block(doc, block)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- 解析层
def _parse_blocks(md: str) -> Iterator[tuple]:
    """把 markdown 文本流式切成 block：(kind, payload)。

    kind: h1/h2/h3 | quote | table(rows) | list(items) | p | hr
    """
    lines = md.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        m = _H1.match(line)
        if m:
            yield ("h1", m.group(1).strip())
            i += 1
            continue
        m = _H2.match(line)
        if m:
            yield ("h2", m.group(1).strip())
            i += 1
            continue
        m = _H3.match(line)
        if m:
            yield ("h3", m.group(1).strip())
            i += 1
            continue
        m = _QUOTE.match(line)
        if m:
            yield ("quote", m.group(1).strip())
            i += 1
            continue
        m = _LIST.match(line)
        if m:
            items = [m.group(1).strip()]
            i += 1
            while i < n:
                lm = _LIST.match(lines[i].strip())
                if not lm:
                    break
                items.append(lm.group(1).strip())
                i += 1
            yield ("list", items)
            continue
        if _TABLE_ROW.match(line):
            rows = []
            while i < n and _TABLE_ROW.match(lines[i].strip()):
                row_text = lines[i].strip()
                if not _TABLE_SEP.match(row_text):
                    cells = [c.strip() for c in row_text.strip("|").split("|")]
                    rows.append(cells)
                i += 1
            if rows:
                yield ("table", rows)
            continue
        if _HR.match(line):
            i += 1
            continue  # 分隔线在 docx 中用空段即可，不单独渲染
        yield ("p", line)
        i += 1


# ---------------------------------------------------------------- 渲染层
def _setup_styles(doc: Document) -> None:
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    try:
        rpr = normal.element.get_or_add_rPr()
        rfonts = rpr.get_or_add_rFonts()
        rfonts.set(qn("w:eastAsia"), "微软雅黑")
    except Exception:  # noqa: BLE001  样式兜底，不影响正文
        pass
    for name in ("Heading 1", "Heading 2", "Heading 3", "Title"):
        try:
            st = doc.styles[name]
            st.font.name = "Calibri"
            st.font.color.rgb = _ACCENT
            rpr2 = st.element.get_or_add_rPr()
            rfonts2 = rpr2.get_or_add_rFonts()
            rfonts2.set(qn("w:eastAsia"), "微软雅黑")
        except Exception:  # noqa: BLE001
            pass


def _render_block(doc: Document, block: tuple) -> None:
    kind, payload = block
    if kind == "h1":
        _add_heading(doc, payload, level=0)
    elif kind == "h2":
        _add_heading(doc, payload, level=1)
    elif kind == "h3":
        _add_heading(doc, payload, level=2)
    elif kind == "quote":
        p = doc.add_paragraph()
        run = p.add_run(payload)
        run.italic = True
        run.font.color.rgb = _GRAY
    elif kind == "table":
        _add_table(doc, payload)
    elif kind == "list":
        for item in payload:
            p = doc.add_paragraph(style="List Bullet")
            _add_inline(p, item)
    else:  # p
        p = doc.add_paragraph()
        _add_inline(p, payload)


def _add_heading(doc: Document, text: str, level: int) -> None:
    h = doc.add_heading(level=level)
    run = h.add_run(text)
    run.font.color.rgb = _ACCENT
    try:
        rpr = run._element.get_or_add_rPr()
        rfonts = rpr.get_or_add_rFonts()
        rfonts.set(qn("w:eastAsia"), "微软雅黑")
    except Exception:  # noqa: BLE001
        pass


def _add_table(doc: Document, rows: list[list[str]]) -> None:
    if not rows:
        return
    ncol = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=ncol)
    try:
        table.style = "Table Grid"
    except Exception:  # noqa: BLE001
        pass
    for i, row in enumerate(rows):
        for j in range(ncol):
            cell = table.cell(i, j)
            cell.text = ""
            p = cell.paragraphs[0]
            _add_inline(p, row[j] if j < len(row) else "")
            if i == 0:  # 表头加粗
                for run in p.runs:
                    run.font.bold = True


def _add_inline(paragraph, text: str) -> None:
    """支持行内 **加粗** 标记，其余按普通文本。"""
    parts = re.split(r"(\*\*.+?\*\*)", text)
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            run = paragraph.add_run(part[2:-2])
            run.font.bold = True
        else:
            paragraph.add_run(part)


def sanitize_filename(name: str, fallback: str = "report") -> str:
    """去掉文件名非法字符并限长，供 Content-Disposition 使用。"""
    base = re.sub(r'[\\/:*?"<>|\r\n]+', "_", (name or "").strip())
    base = base.strip(" ._")
    return (base[:48] or fallback).strip()
