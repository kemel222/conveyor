"""Мини-построитель редактируемых формул Word (OMML).

Синтаксис: обычный текст, а также \\sub{осн}{инд}, \\sup{осн}{степ}, \\sqrt{x}, \\frac{числ}{знам}.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from docx.oxml import parse_xml

M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
COMMANDS = {"sub": 2, "sup": 2, "sqrt": 1, "frac": 2}


def _group(s: str, i: int) -> tuple[str, int]:
    if i >= len(s) or s[i] != "{":
        raise ValueError(f"ожидалась {{ в позиции {i}: {s}")
    depth, j = 0, i
    while j < len(s):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    raise ValueError(f"незакрытая скобка: {s}")


def _run(text: str, size: int) -> str:
    if not text:
        return ""
    return (f'<m:r><m:rPr><m:sty m:val="p"/></m:rPr><w:rPr><w:rFonts w:ascii="Cambria Math" w:hAnsi="Cambria Math" '
            f'w:cs="Cambria Math"/><w:sz w:val="{size}"/></w:rPr><m:t xml:space="preserve">{escape(text)}</m:t></m:r>')


def to_omml(s: str, size: int = 28) -> str:
    out, buf, i = [], [], 0
    while i < len(s):
        if s[i] == "\\":
            j = i + 1
            while j < len(s) and s[j].isalpha():
                j += 1
            name = s[i + 1:j]
            if name in COMMANDS:
                out.append(_run("".join(buf), size))
                buf = []
                args = []
                for _ in range(COMMANDS[name]):
                    g, j = _group(s, j)
                    args.append(to_omml(g, size))
                if name == "sub":
                    out.append(f"<m:sSub><m:e>{args[0]}</m:e><m:sub>{args[1]}</m:sub></m:sSub>")
                elif name == "sup":
                    out.append(f"<m:sSup><m:e>{args[0]}</m:e><m:sup>{args[1]}</m:sup></m:sSup>")
                elif name == "sqrt":
                    out.append(f'<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr><m:deg/><m:e>{args[0]}</m:e></m:rad>')
                else:
                    out.append(f"<m:f><m:num>{args[0]}</m:num><m:den>{args[1]}</m:den></m:f>")
                i = j
                continue
        buf.append(s[i])
        i += 1
    out.append(_run("".join(buf), size))
    return "".join(out)


def add_equation(doc, formula: str, size: int = 28):
    p = doc.add_paragraph()
    p.paragraph_format.first_line_indent = 0
    p.alignment = 1
    xml = f'<m:oMathPara xmlns:m="{M}" xmlns:w="{W}"><m:oMath>{to_omml(formula, size)}</m:oMath></m:oMathPara>'
    p._p.append(parse_xml(xml))
    return p
