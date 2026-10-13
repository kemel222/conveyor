"""Чертежи: GPT-6 Astra пишет генератор листов, код запускает его сам и проверяет результат.

Астра получает только папку cad/<вариант>/ с данными листов и набором функций. Ни проверку, ни печать,
ни закрытие этапа он не выполняет: driver заново запускает generate.py в отдельном процессе, проверяет
каждый DXF, печатает PDF через AutoCAD и проверяет ещё раз. Замечания возвращаются Astra списком.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from core import llm
from core.cad_check import check_sheet
from core.cad_plot import autocad_plot, preview_png
from core.log import Log
from .cad_data import sheet_data

ROOT = Path(__file__).resolve().parents[2]
MAX_ROUNDS = 3
SHEETS = ("plan", "axon", "hydraulic")

PROMPT = """Ты — инженер-чертёжник GPT-6 Astra. В текущей папке напиши Python-скрипт generate.py, который строит три листа А3
(ГОСТ, ЕСКД) по данным sheet_data.json и сохраняет plan.dxf, axon.dxf, hydraulic.dxf в эту же папку.

Обязательно:
- Используй только набор функций из kit_api.md (класс Sheet из core.cad_kit). Рамку, основную надпись и шрифт
  создаёт Sheet сам — не рисуй их. Подключение: sys.path.insert(0, r"{root}"); from core.cad_kit import Sheet.
- Все числа, надписи, марки и таблицы бери ТОЛЬКО из sheet_data.json. Ничего не вычисляй и не придумывай.
- На каждом листе укажи «Вариант {variant}». Других номеров вариантов быть не должно.
- Лист 1 (plan, М 1:100 или 1:200 – выбери, чтобы план поместился в свободное поле над/левее штампа):
  стены помещения (слой WALL), все оросители по rows_x_mm × positions_y_mm (SPRINKLER; диктующая зона –
  закрашенные), распределительные рядки (PIPE_DIST), питающий трубопровод и стояк (PIPE_FEED), насосная
  станция (EQUIP, прямоугольник с подписью «Насосная станция»), размеры: шаг рядков, шаг в рядке, до стен,
  габариты помещения; выноски с диаметрами труб; условные обозначения (legend) и спецификация (specification).
- Лист 2 (axon): аксонометрическая схема установки под 45° (ось Y сокращается в 0,5): насосная станция, узел
  управления, стояк, питающий трубопровод, все рядки с оросителями; выноски с диаметрами; обозначение
  «Узел управления».
- Лист 3 (hydraulic): слева расчётная схема диктующей зоны без масштаба с номерами точек 1…N (hydraulic_scheme),
  диаметрами и длинами участков, тип оросителя; справа таблица result_table целиком.
- Тексты не должны налезать друг на друга, пересекать линии и залезать в основную надпись (Sheet.stamp_box()).
  Подписи ставь выносками в свободное место. Высота текста не меньше 2,5 мм.
- После написания запусти: python generate.py, затем python self_check.py. Исправляй generate.py, пока
  self_check.py не напишет «ЗАМЕЧАНИЙ НЕТ». Открой preview_*.png и посмотри листы глазами: схема должна читаться.
- Не меняй sheet_data.json, kit_api.md, self_check.py и файлы вне этой папки. Не пиши отчётов и json-квитанций.
{fix}"""

KIT_API = """# Набор функций листа (core.cad_kit)

Sheet(title, number, scale, stamp)       – новый лист А3, рамка и основная надпись уже нарисованы.
  title/number/scale – из sheet_data["sheets"][i]; stamp = sheet_data["title_block"].
s.line(p1, p2, layer)                    – отрезок; p = (x, y) в мм листа.
s.polyline(pts, layer, closed=False)
s.rect(x0, y0, x1, y1, layer)
s.circle(center, r, layer="SPRINKLER", filled=False)
s.text(s, x, y, h=3.5, align="left"|"center"|"right"|"middle"|"middle_left", rot=0, layer="TEXT")
s.dim(p1, p2, offset, label, h=2.5)      – линейный размер; p1, p2 на одной горизонтали или вертикали.
s.leader(p_from, p_to, label, h=2.5)     – выноска с полкой.
s.table(x, y_top, header, rows, widths, h=2.5, title=None) -> y_bottom   – таблица с переносом текста.
Sheet.free_area() -> (xmin, ymin, xmax, ymax)   поле внутри рамки.
Sheet.stamp_box() -> (xmin, ymin, xmax, ymax)   основная надпись – туда ничего не ставить.
Sheet.to_paper(origin, scale_den) -> f(x_mm, y_mm) -> (x, y)   перевод натуры в мм листа.
s.save(path)

Слои: WALL, PIPE_FEED, PIPE_DIST, SPRINKLER, EQUIP, DIM, TEXT, TABLE, AXIS.
Подписи к трубам и оросителям – слой DIM или TEXT; геометрия – WALL/PIPE_*/SPRINKLER/EQUIP.
Лист 210×297 не нужен: только А3 420×297, начало координат – левый нижний угол листа.
"""

SELF_CHECK = """import json, sys
from pathlib import Path
sys.path.insert(0, r"{root}")
from core.cad_check import check_sheet
from core.cad_plot import preview_png
here = Path(__file__).parent
data = json.loads((here / "sheet_data.json").read_text(encoding="utf-8"))
bad = 0
for sh in data["sheets"]:
    dxf = here / (sh["file"] + ".dxf")
    if not dxf.is_file():
        print(f"{{sh['file']}}: НЕТ ФАЙЛА"); bad += 1; continue
    r = check_sheet(dxf, None, data["must_show"][sh["file"]], data["variant"], sh["title"])
    preview_png(dxf, here / f"preview_{{sh['file']}}.png")
    for e in r["errors"]:
        print(f"{{sh['file']}}: {{e}}")
    bad += r["error_count"]
print("ЗАМЕЧАНИЙ НЕТ" if bad == 0 else f"ЗАМЕЧАНИЙ: {{bad}}")
"""


def _hash_code() -> str:
    """Хэш общего и дисциплинарного кода до запуска внешнего исполнителя."""
    h = hashlib.sha256()
    for folder in (ROOT / "core", ROOT / "tasks"):
        for p in sorted(folder.rglob("*.py")):
            h.update(str(p.relative_to(ROOT)).encode("utf-8"))
            h.update(p.read_bytes())
    return h.hexdigest()


def _prepare(work: Path, data: dict) -> None:
    work.mkdir(parents=True, exist_ok=True)
    (work / "sheet_data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    (work / "kit_api.md").write_text(KIT_API, encoding="utf-8")
    (work / "self_check.py").write_text(SELF_CHECK.format(root=ROOT), encoding="utf-8")


def _run_generator(work: Path, data_json: str, log: Log) -> None:
    if (work / "sheet_data.json").read_text(encoding="utf-8") != data_json:
        raise RuntimeError("Исполнитель изменил sheet_data.json")
    for name in SHEETS:
        (work / f"{name}.dxf").unlink(missing_ok=True)
    r = subprocess.run([sys.executable, "-X", "utf8", "generate.py"], cwd=str(work), capture_output=True, text=True,
                       timeout=180, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"generate.py завершился с ошибкой:\n{r.stderr[-1500:]}")


def _check_all(work: Path, data: dict, with_pdf: bool) -> list[str]:
    errs = []
    for sh in data["sheets"]:
        dxf = work / f"{sh['file']}.dxf"
        if not dxf.is_file():
            errs.append(f"{sh['file']}: generate.py не создал {dxf.name}")
            continue
        pdf = work / f"{sh['file']}.pdf" if with_pdf else None
        r = check_sheet(dxf, pdf, data["must_show"][sh["file"]], data["variant"], sh["title"])
        errs += [f"{sh['file']}: {e}" for e in r["errors"]]
    return errs


def build_drawings(design: dict, meta: dict, out: Path, work: Path, cfg: dict, log: Log) -> dict:
    data = sheet_data(design, meta)
    _prepare(work, data)
    data_json = (work / "sheet_data.json").read_text(encoding="utf-8")
    code_hash = _hash_code()
    errs: list[str] = []
    if (work / "generate.py").is_file() and cfg.get("reuse_cad"):
        try:
            _run_generator(work, data_json, log)
            errs = _check_all(work, data, with_pdf=False)
        except RuntimeError as e:
            errs = [str(e)]
        if not errs:
            log.note("Использован существующий generate.py: замечаний нет")
    else:
        errs = ["generate.py ещё не написан"]
    for rnd in range(1, MAX_ROUNDS + 1):
        if not errs:
            break
        fix = "" if rnd == 1 and errs == ["generate.py ещё не написан"] else \
            "\nПРЕДЫДУЩАЯ ВЕРСИЯ ОТКЛОНЕНА ПРОВЕРКОЙ. Исправь в generate.py:\n- " + "\n- ".join(errs[:40])
        prompt = PROMPT.format(root=ROOT, variant=data["variant"], fix=fix)
        res = log.step(f"Astra пишет генератор чертежей (раунд {rnd})",
                       lambda: llm.astra_cad_task(prompt, work, cfg, f"astra{rnd}"))
        if _hash_code() != code_hash:
            raise RuntimeError("Исполнитель изменил файлы конвейера в core/ или tasks/ – результат отклонён")
        if not res.ok:
            log.note(f"Astra: {res.error}; журнал {res.stderr_path}")
            if not (work / "generate.py").is_file():
                continue
        try:
            log.step("Запуск generate.py конвейером", lambda: _run_generator(work, data_json, log))
            errs = _check_all(work, data, with_pdf=False)
        except RuntimeError as e:
            errs = [str(e)]
        log.note("Проверка листов: " + ("без замечаний" if not errs else f"{len(errs)} замечаний"))
        for e in errs[:15]:
            log.note("  - " + e)
    if errs:
        raise RuntimeError("Чертежи не прошли проверку за допустимое число раундов:\n- " + "\n- ".join(errs[:30]))

    out.mkdir(parents=True, exist_ok=True)
    for sh in data["sheets"]:
        dxf = work / f"{sh['file']}.dxf"
        log.step(f"AutoCAD: DWG и PDF листа {sh['number']}",
                 lambda: autocad_plot(dxf, work / f"{sh['file']}.dwg", work / f"{sh['file']}.pdf"))
    errs = _check_all(work, data, with_pdf=True)
    if errs:
        raise RuntimeError("Напечатанные листы не прошли проверку:\n- " + "\n- ".join(errs[:30]))
    files = {}
    for sh in data["sheets"]:
        base = f"Лист_{sh['number']}_{sh['file']}"
        for ext in ("dwg", "dxf", "pdf"):
            dst = out / f"{base}.{ext}"
            shutil.copy2(work / f"{sh['file']}.{ext}", dst)
            files.setdefault(sh["file"], []).append(dst)
        preview_png(work / f"{sh['file']}.dxf", work / f"preview_{sh['file']}.png")
    return dict(files=files, data=data)
