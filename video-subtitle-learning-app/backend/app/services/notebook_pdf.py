from __future__ import annotations

import re
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from backend.app.services.app_paths import get_app_root


PDF_PAGE_SIZE = A4
PDF_MARGIN_X = 16 * mm
PDF_MARGIN_TOP = 16 * mm
PDF_MARGIN_BOTTOM = 14 * mm
PDF_CONTENT_WIDTH = PDF_PAGE_SIZE[0] - PDF_MARGIN_X * 2

PRIMARY_FONT_NAME = "NotebookPdfPrimaryFont"
KOREAN_FONT_NAME = "NotebookPdfKoreanFont"
FALLBACK_FONT_NAME = "STSong-Light"
HANGUL_RE = re.compile(r"[\u1100-\u11FF\u3130-\u318F\uA960-\uA97F\uAC00-\uD7AF]+")


def _font_candidates() -> dict[str, list[Path]]:
    app_root = get_app_root()
    return {
        "primary": [
            app_root / "assets" / "fonts" / "NotoSansSC-Regular.otf",
            app_root / "assets" / "fonts" / "SourceHanSansSC-Regular.otf",
            Path(r"C:\Windows\Fonts\msyh.ttc"),
            Path(r"C:\Windows\Fonts\msyh.ttf"),
            Path(r"C:\Windows\Fonts\simhei.ttf"),
            Path(r"C:\Windows\Fonts\simsun.ttc"),
        ],
        "korean": [
            app_root / "assets" / "fonts" / "NotoSansKR-Regular.otf",
            app_root / "assets" / "fonts" / "SourceHanSansK-Regular.otf",
            Path(r"C:\Windows\Fonts\malgun.ttf"),
            Path(r"C:\Windows\Fonts\malgunsl.ttf"),
            Path(r"C:\Windows\Fonts\batang.ttc"),
        ],
    }


def ensure_pdf_fonts() -> dict[str, str]:
    registered = set(pdfmetrics.getRegisteredFontNames())

    if PRIMARY_FONT_NAME not in registered:
        for candidate in _font_candidates()["primary"]:
            if not candidate.exists():
                continue
            try:
                pdfmetrics.registerFont(TTFont(PRIMARY_FONT_NAME, str(candidate)))
                break
            except Exception:
                continue

    if PRIMARY_FONT_NAME not in set(pdfmetrics.getRegisteredFontNames()):
        if FALLBACK_FONT_NAME not in registered:
            pdfmetrics.registerFont(UnicodeCIDFont(FALLBACK_FONT_NAME))
        primary_font = FALLBACK_FONT_NAME
    else:
        primary_font = PRIMARY_FONT_NAME

    if KOREAN_FONT_NAME not in set(pdfmetrics.getRegisteredFontNames()):
        for candidate in _font_candidates()["korean"]:
            if not candidate.exists():
                continue
            try:
                pdfmetrics.registerFont(TTFont(KOREAN_FONT_NAME, str(candidate)))
                break
            except Exception:
                continue

    korean_font = KOREAN_FONT_NAME if KOREAN_FONT_NAME in set(pdfmetrics.getRegisteredFontNames()) else primary_font
    return {"primary": primary_font, "korean": korean_font}


def _styles(fonts: dict[str, str]) -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    primary_font = fonts["primary"]
    return {
        "title": ParagraphStyle(
            "NotebookPdfTitle",
            parent=sample["Heading1"],
            fontName=primary_font,
            fontSize=18,
            leading=24,
            textColor=colors.HexColor("#111827"),
            spaceAfter=8,
            alignment=TA_LEFT,
        ),
        "subtitle": ParagraphStyle(
            "NotebookPdfSubtitle",
            parent=sample["BodyText"],
            fontName=primary_font,
            fontSize=9,
            leading=14,
            textColor=colors.HexColor("#6b7280"),
            spaceAfter=4,
        ),
        "entry_title": ParagraphStyle(
            "NotebookPdfEntryTitle",
            parent=sample["Heading2"],
            fontName=primary_font,
            fontSize=13,
            leading=18,
            textColor=colors.HexColor("#111827"),
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "NotebookPdfBody",
            parent=sample["BodyText"],
            fontName=primary_font,
            fontSize=10.2,
            leading=15,
            textColor=colors.HexColor("#1f2937"),
            spaceAfter=5,
        ),
        "meta": ParagraphStyle(
            "NotebookPdfMeta",
            parent=sample["BodyText"],
            fontName=primary_font,
            fontSize=8.7,
            leading=12,
            textColor=colors.HexColor("#6b7280"),
            spaceAfter=3,
        ),
        "footer": ParagraphStyle(
            "NotebookPdfFooter",
            parent=sample["BodyText"],
            fontName=primary_font,
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#6b7280"),
            alignment=TA_CENTER,
        ),
    }


def _safe(value: Any, empty: str = "未填写") -> str:
    text = str(value or "").strip()
    return text or empty


def _has_hangul(text: str) -> bool:
    return bool(HANGUL_RE.search(text))


def _rich_text(text: Any, fonts: dict[str, str]) -> str:
    raw = str(text or "")
    if not raw:
        return ""

    if fonts["primary"] == fonts["korean"] or not _has_hangul(raw):
        return escape(raw).replace("\n", "<br/>")

    parts: list[str] = []
    cursor = 0
    for match in HANGUL_RE.finditer(raw):
        if match.start() > cursor:
            parts.append(escape(raw[cursor : match.start()]))
        hangul = escape(match.group(0))
        parts.append(f'<font name="{fonts["korean"]}">{hangul}</font>')
        cursor = match.end()
    if cursor < len(raw):
        parts.append(escape(raw[cursor:]))
    return "".join(parts).replace("\n", "<br/>")


def _para(text: Any, style: ParagraphStyle, fonts: dict[str, str]) -> Paragraph:
    return Paragraph(_rich_text(text, fonts), style)


def _markup_para(markup: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(markup, style)


def _label_value(label: str, value: Any, style: ParagraphStyle, fonts: dict[str, str], *, empty: str = "未填写") -> Paragraph:
    return Paragraph(f"<b>{escape(label)}</b> {_rich_text(_safe(value, empty), fonts)}", style)


def _time_range_label(entry: dict[str, Any]) -> str:
    start_time = entry.get("start_time")
    end_time = entry.get("end_time")
    if start_time is None and end_time is None:
        return "未记录"
    return f"{_seconds_label(start_time)} - {_seconds_label(end_time)}"


def _seconds_label(value: Any) -> str:
    if value is None:
        return "--:--"
    try:
        total = float(value)
    except (TypeError, ValueError):
        return str(value)
    minutes = int(total // 60)
    seconds = int(total % 60)
    return f"{minutes:02d}:{seconds:02d}"


def _header_footer(notebook: dict[str, Any], styles: dict[str, ParagraphStyle]):
    exported_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    notebook_label = "词语收集册" if notebook["type"] == "word" else "句子收集册"

    def draw(canvas, doc):  # noqa: ANN001
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d1d5db"))
        canvas.line(PDF_MARGIN_X, A4[1] - 10 * mm, A4[0] - PDF_MARGIN_X, A4[1] - 10 * mm)
        canvas.line(PDF_MARGIN_X, 10 * mm, A4[0] - PDF_MARGIN_X, 10 * mm)

        canvas.setFont(styles["meta"].fontName, 8.5)
        canvas.setFillColor(colors.HexColor("#6b7280"))
        canvas.drawString(PDF_MARGIN_X, A4[1] - 8 * mm, f"{notebook_label} · {notebook['name']}")
        canvas.drawRightString(A4[0] - PDF_MARGIN_X, 7 * mm, f"第 {canvas.getPageNumber()} 页 · 导出时间 {exported_at}")
        canvas.restoreState()

    return draw


def _summary_table(notebook: dict[str, Any], styles: dict[str, ParagraphStyle], fonts: dict[str, str]) -> Table:
    notebook_label = "词语收集册" if notebook["type"] == "word" else "句子收集册"
    rows = [
        [
            _markup_para(f"<b>{_rich_text(notebook['name'], fonts)}</b>", styles["entry_title"]),
            _para(f"{notebook_label} · 共 {notebook['entry_count']} 条", styles["subtitle"], fonts),
        ],
        [
            _label_value("源语言", notebook.get("source_lang"), styles["body"], fonts, empty="未设置"),
            _label_value("学习语言", notebook.get("learning_lang"), styles["body"], fonts, empty="未设置"),
        ],
        [
            _label_value("母语", notebook.get("native_lang"), styles["body"], fonts, empty="未设置"),
            _label_value("描述", notebook.get("description"), styles["body"], fonts, empty="无"),
        ],
    ]
    table = Table(rows, colWidths=[PDF_CONTENT_WIDTH * 0.5, PDF_CONTENT_WIDTH * 0.5], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#dbe2ea")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _word_entry_card(index: int, entry: dict[str, Any], styles: dict[str, ParagraphStyle], fonts: dict[str, str]) -> Table:
    content = [
        _para(f"{index}. {_safe(entry.get('word'))}", styles["entry_title"], fonts),
        _label_value("释义", entry.get("meaning"), styles["body"], fonts),
        _label_value("备注", entry.get("note"), styles["body"], fonts, empty="无"),
        Spacer(1, 2),
        _label_value("原句", entry.get("source_sentence"), styles["body"], fonts),
        _label_value("学习语言句子", entry.get("learning_sentence"), styles["body"], fonts),
    ]
    return _entry_card(content)


def _analysis_options(options: dict[str, Any] | None) -> dict[str, bool]:
    base = {
        "include_improved_translation": True,
        "include_structure_explanation": True,
        "include_learning_tip": True,
        "include_keywords": True,
        "include_grammar_points": True,
    }
    if not options:
        return base
    for key in list(base):
        if key in options:
            base[key] = bool(options[key])
    return base


def _sentence_entry_card(
    index: int,
    entry: dict[str, Any],
    styles: dict[str, ParagraphStyle],
    fonts: dict[str, str],
    options: dict[str, bool],
) -> Table:
    analysis_payload = entry.get("analysis_payload") or {}
    keywords = analysis_payload.get("keywords") or []
    grammar_points = analysis_payload.get("grammar_points") or []

    content = [
        _para(f"{index}. 句子", styles["entry_title"], fonts),
        _label_value("原句", entry.get("source_text"), styles["body"], fonts),
        _label_value("学习语言句子", entry.get("learning_text"), styles["body"], fonts),
    ]

    if options["include_improved_translation"] and analysis_payload.get("improved_translation"):
        content.append(_label_value("优化译文", analysis_payload.get("improved_translation"), styles["body"], fonts))
    if options["include_structure_explanation"] and analysis_payload.get("structure_explanation"):
        content.append(_label_value("句子结构", analysis_payload.get("structure_explanation"), styles["body"], fonts))
    if options["include_learning_tip"] and analysis_payload.get("learning_tip"):
        content.append(_label_value("学习提示", analysis_payload.get("learning_tip"), styles["body"], fonts))
    if options["include_keywords"] and keywords:
        keyword_text = "；".join(f"{item.get('word', '')}：{item.get('meaning', '')}" for item in keywords if item.get("word"))
        if keyword_text:
            content.append(_label_value("关键词", keyword_text, styles["body"], fonts))
    if options["include_grammar_points"] and grammar_points:
        grammar_text = "；".join(str(item) for item in grammar_points if str(item).strip())
        if grammar_text:
            content.append(_label_value("语法点", grammar_text, styles["body"], fonts))

    return _entry_card(content)


def _entry_card(content: list[Any]) -> Table:
    table = Table([[content]], colWidths=[PDF_CONTENT_WIDTH], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#dbe2ea")),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def build_notebook_pdf(payload: dict[str, Any], options: dict[str, Any] | None = None) -> bytes:
    notebook = payload["notebook"]
    entries = payload["entries"]
    fonts = ensure_pdf_fonts()
    styles = _styles(fonts)
    sentence_options = _analysis_options(options)

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=PDF_PAGE_SIZE,
        leftMargin=PDF_MARGIN_X,
        rightMargin=PDF_MARGIN_X,
        topMargin=PDF_MARGIN_TOP,
        bottomMargin=PDF_MARGIN_BOTTOM,
        title=str(notebook["name"]),
        author="Video Subtitle Learning App",
    )

    story: list[Any] = [
        _para(notebook["name"], styles["title"], fonts),
        _para("打印学习版 · 浅色 A4 布局", styles["subtitle"], fonts),
        Spacer(1, 4),
        _summary_table(notebook, styles, fonts),
        Spacer(1, 10),
        HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#d1d5db")),
        Spacer(1, 10),
    ]

    for index, entry in enumerate(entries, start=1):
        if notebook["type"] == "word":
            story.append(_word_entry_card(index, entry, styles, fonts))
        else:
            story.append(_sentence_entry_card(index, entry, styles, fonts, sentence_options))
        story.append(Spacer(1, 8))

    document.build(story, onFirstPage=_header_footer(notebook, styles), onLaterPages=_header_footer(notebook, styles))
    return buffer.getvalue()
