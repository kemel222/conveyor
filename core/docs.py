"""Общие операции с документами: DOCX -> PDF через LibreOffice, поиск страниц заголовков."""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote

import pymupdf

SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"


def docx_to_pdf(docx_path: Path, timeout: int = 240) -> Path:
    exe = SOFFICE if Path(SOFFICE).exists() else shutil.which("soffice")
    if not exe:
        raise FileNotFoundError("LibreOffice (soffice) не найден")
    profile = Path(tempfile.gettempdir()) / "conveyor_lo_profile"
    url = "file:///" + quote(profile.as_posix(), safe="/:")
    cmd = [exe, f"-env:UserInstallation={url}", "--headless", "--convert-to", "pdf",
           "--outdir", str(docx_path.parent), str(docx_path)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
    pdf = docx_path.with_suffix(".pdf")
    if not pdf.is_file() or pdf.stat().st_mtime < docx_path.stat().st_mtime - 1:
        raise RuntimeError(f"PDF не создан для {docx_path.name}")
    return pdf


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("ё", "е").replace("Ё", "Е")).strip().lower()


def pdf_pages_text(pdf: Path) -> list[str]:
    with pymupdf.open(str(pdf)) as d:
        return [p.get_text() for p in d]


def heading_pages(pdf: Path, headings: list[str], start_page: int) -> dict[str, int]:
    """Страница каждого заголовка: заголовок ищется как целая строка, поэтому строки содержания
    (заголовок + номер страницы) не совпадают."""
    pages = [[norm(line) for line in t.splitlines() if line.strip()] for t in pdf_pages_text(pdf)]
    found, cur = {}, start_page
    for h in headings:
        key = norm(h)
        for i in range(cur, len(pages)):
            lines = pages[i]
            joined = [lines[j] + (" " + lines[j + 1] if j + 1 < len(lines) else "") for j in range(len(lines))]
            if key in lines or key in joined:
                found[h] = i + 1
                cur = i
                break
    return found
