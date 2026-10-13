"""Задача «Водяное пожаротушение (задание 2)»: полный маршрут одного варианта.

расчёт (код) → проза (Sol) → проверка прозы (код) → DOCX/PDF (код) → проверка записки (код)
→ чертежи (Astra пишет генератор, код запускает и проверяет) → комплект.
"""
from __future__ import annotations

import json
from pathlib import Path

from core import llm
from core.docs import docx_to_pdf, heading_pages, pdf_pages_text
from core.log import Log
from . import check_prose, check_report, figures, hydraulics, prose, report

MAX_PROSE_ATTEMPTS = 4


def build_text(variant: dict, out: Path, work: Path, cfg: dict, meta: dict, log: Log) -> dict:
    d = log.step("Гидравлический расчёт", lambda: hydraulics.design(variant))
    if not all(d["checks"].values()):
        raise RuntimeError(f"Расчёт не удовлетворяет нормам: {d['checks']}")
    (work / "model.json").write_text(json.dumps(d, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    figs = log.step("Рисунки записки", lambda: dict(
        plan=figures.plan(d, work / "fig_plan.png"),
        scheme=figures.scheme(d, work / "fig_scheme.png"),
        pump=figures.pump_chart(d, work / "fig_pump.png")))

    prose_path = work / "prose.json"
    accepted: dict = {}
    if prose_path.is_file() and cfg.get("reuse_prose"):
        saved = json.loads(prose_path.read_text(encoding="utf-8"))
        bad = check_prose.check_sections(saved, d, report.BIBLIOGRAPHY)
        accepted = {k: v for k, v in saved.items() if k in prose.SECTIONS and k not in bad}
    pending = [k for k in prose.SECTIONS if k not in accepted]
    fix: dict = {}
    previous: dict = {}
    for attempt in range(1, MAX_PROSE_ATTEMPTS + 1):
        if not pending:
            break
        text = prose.prompt(d, report.BIBLIOGRAPHY, pending, fix, previous)
        keys = list(pending)
        cand = log.step(f"Sol пишет текст (попытка {attempt}, разделов {len(keys)})",
                        lambda: llm.sol_json(text, prose.schema(keys), work / "sol", cfg, f"prose{attempt}"))
        merged = dict(accepted, **{k: cand.get(k, []) for k in keys})
        bad = check_prose.check_sections(merged, d, report.BIBLIOGRAPHY)
        for k in keys:
            if k not in bad:
                accepted[k] = cand[k]
        pending = [k for k in prose.SECTIONS if k not in accepted]
        fix = {k: bad[k] for k in pending if k in bad}
        previous = {k: cand.get(k, []) for k in pending}
        prose_path.write_text(json.dumps(accepted, ensure_ascii=False, indent=1), encoding="utf-8")
        log.note("Проверка текста: " + ("все разделы приняты" if not pending else
                  "; ".join(f"«{prose.SECTIONS[k][0]}»: {'; '.join(fix.get(k, ['не принят']))}" for k in pending)))
    if pending:
        raise RuntimeError("Sol не дал приемлемый текст разделов: " +
                           ", ".join(prose.SECTIONS[k][0] for k in pending))
    answer = accepted

    docx_path = out / "Пояснительная_записка.docx"

    def render(pages=None, counts=None):
        info = report.build_report(d, answer, meta, figs, docx_path, pages, counts)
        pdf = docx_to_pdf(docx_path)
        return info, pdf

    info, pdf = log.step("Сборка DOCX/PDF (проход 1)", render)
    for i in range(2):
        npages = len(pdf_pages_text(pdf))
        pages = heading_pages(pdf, info["headings"], start_page=3)
        info, pdf = log.step(f"Сборка DOCX/PDF (проход {i + 2}, нумерация содержания)",
                             lambda: render(pages, dict(pages=npages)))
        if heading_pages(pdf, info["headings"], start_page=3) == pages and len(pdf_pages_text(pdf)) == npages:
            break
    res = log.step("Проверка записки", lambda: check_report.check_report(docx_path, pdf, d))
    (work / "report_check.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    if not res["passed"]:
        raise RuntimeError("Записка не прошла проверку:\n- " + "\n- ".join(res["errors"]))
    log.note(f"Записка: {res['pages']} с., формул {res['equations']}")
    return dict(design=d, docx=docx_path, pdf=pdf, check=res)
