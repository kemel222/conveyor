"""Проверка листа чертежа по фактическому DXF и PDF. Пишется кодом; Astra её не видит и не запускает.

Проверяется: рамка и штамп на месте, всё внутри рамки, тексты не налезают друг на друга, текст не
пересекает линии геометрии и трубопроводов, на листе есть обязательные надписи, номер варианта и
нет чужих вариантов, PDF – один лист А3 из этого DXF.
"""
from __future__ import annotations

import re
from pathlib import Path

import ezdxf
import pymupdf

from core.cad_kit import FRAME, STAMP, text_box

GEOMETRY_LAYERS = {"WALL", "PIPE_FEED", "PIPE_DIST", "SPRINKLER", "EQUIP"}
TEXT_LAYERS = {"TEXT", "DIM", "TABLE"}
CLEARANCE = 0.4


def _segments(e):
    t = e.dxftype()
    if t == "LINE":
        yield (e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)
    elif t == "LWPOLYLINE":
        pts = [(p[0], p[1]) for p in e.get_points()]
        if e.closed:
            pts.append(pts[0])
        yield from zip(pts, pts[1:])
    elif t == "CIRCLE":
        c, r = e.dxf.center, e.dxf.radius
        yield (c.x - r, c.y - r), (c.x + r, c.y + r)


def _seg_hits_box(p, q, box) -> bool:
    x0, y0, x1, y1 = box[0] + CLEARANCE, box[1] + CLEARANCE, box[2] - CLEARANCE, box[3] - CLEARANCE
    if x0 >= x1 or y0 >= y1:
        return False
    (ax, ay), (bx, by) = p, q
    t0, t1 = 0.0, 1.0
    dx, dy = bx - ax, by - ay
    for pp, qq in ((-dx, ax - x0), (dx, x1 - ax), (-dy, ay - y0), (dy, y1 - ay)):
        if abs(pp) < 1e-12:
            if qq < 0:
                return False
        else:
            r = qq / pp
            if pp < 0:
                t0 = max(t0, r)
            else:
                t1 = min(t1, r)
            if t0 > t1:
                return False
    return True


def _overlap(a, b) -> bool:
    return min(a[2], b[2]) - max(a[0], b[0]) > CLEARANCE and min(a[3], b[3]) - max(a[1], b[1]) > CLEARANCE


def _text_entities(msp):
    out = []
    for e in msp.query("TEXT"):
        align = e.get_placement()[0].name.lower()
        key = {"bottom_left": "left", "left": "left", "bottom_center": "center", "center": "center",
               "bottom_right": "right", "right": "right", "middle_center": "middle", "middle": "middle",
               "middle_left": "middle_left"}.get(align, "left")
        p = e.get_placement()[1]
        x, y = p.x, p.y
        box = text_box(e.dxf.text, x, y, e.dxf.height, key, e.dxf.get("rotation", 0.0))
        out.append(dict(text=e.dxf.text, layer=e.dxf.layer, box=box))
    return out


def check_sheet(dxf_path: Path, pdf_path: Path | None, must_show: list[str], variant: int,
                stamp_title: str) -> dict:
    errors: list[str] = []
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()
    texts = _text_entities(msp)
    all_text = " ".join(t["text"] for t in texts)

    frames = [e for e in msp.query("LWPOLYLINE[layer=='FRAME']")]
    if not any(abs(min(p[0] for p in f.get_points()) - FRAME[0]) < 0.5 for f in frames):
        errors.append("нет рамки листа по ГОСТ 2.301")
    if not any(abs(max(p[0] for p in f.get_points()) - STAMP[2]) < 0.5 and
               abs(min(p[0] for p in f.get_points()) - STAMP[0]) < 0.5 for f in frames):
        errors.append("нет основной надписи 185×55 по ГОСТ 2.104")
    if stamp_title.split()[0] not in all_text:
        errors.append("в штампе нет наименования листа")

    for e in msp:
        if e.dxf.layer in ("AXIS",):
            continue
        for p, q in _segments(e):
            for x, y in (p, q):
                if not (FRAME[0] - 0.01 <= x <= FRAME[2] + 0.01 and FRAME[1] - 0.01 <= y <= FRAME[3] + 0.01):
                    errors.append(f"объект слоя {e.dxf.layer} выходит за рамку ({x:.1f}; {y:.1f})")
                    break
    for t in texts:
        b = t["box"]
        if b[0] < FRAME[0] or b[2] > FRAME[2] or b[1] < FRAME[1] or b[3] > FRAME[3]:
            errors.append(f"текст «{t['text']}» выходит за рамку")
        if t["layer"] != "STAMP" and _overlap(b, STAMP):
            errors.append(f"текст «{t['text']}» залезает в основную надпись")

    free = [t for t in texts if t["layer"] in TEXT_LAYERS]
    for i in range(len(free)):
        for j in range(i + 1, len(free)):
            if _overlap(free[i]["box"], free[j]["box"]):
                errors.append(f"тексты налезают: «{free[i]['text']}» и «{free[j]['text']}»")

    geo = [(p, q, e.dxf.layer) for e in msp if e.dxf.layer in GEOMETRY_LAYERS for p, q in _segments(e)]
    for t in free:
        for p, q, layer in geo:
            if _seg_hits_box(p, q, t["box"]):
                errors.append(f"текст «{t['text']}» пересекает линию слоя {layer}")
                break
    grid_lines = [(p, q) for e in msp if e.dxf.layer in ("STAMP", "FRAME", "TABLE") for p, q in _segments(e)]
    for t in texts:
        if t["layer"] not in ("STAMP", "TABLE"):
            continue
        for p, q in grid_lines:
            if _seg_hits_box(p, q, t["box"]):
                errors.append(f"текст «{t['text']}» пересекает линию таблицы/штампа")
                break

    for s in must_show:
        if s not in all_text:
            errors.append(f"на листе нет обязательной надписи «{s}»")
    other = {int(m) for m in re.findall(r"[Вв]ариант\w*\s+(\d+)\b", all_text)}
    if other and other != {variant}:
        errors.append(f"на листе указаны чужие варианты: {sorted(other - {variant})}")
    if variant not in other:
        errors.append(f"на листе не указан вариант {variant}")
    if not (list(msp.query("*[layer=='SPRINKLER']")) or list(msp.query("*[layer=='PIPE_FEED']"))):
        errors.append("на листе нет геометрии установки (оросители/трубопровод)")

    if pdf_path is not None:
        if not pdf_path.is_file():
            errors.append("нет PDF листа")
        else:
            with pymupdf.open(str(pdf_path)) as pdf:
                if len(pdf) != 1:
                    errors.append(f"PDF содержит {len(pdf)} стр., нужен 1 лист")
                r = pdf[0].rect
                w, h = sorted((r.width * 25.4 / 72, r.height * 25.4 / 72))
                if abs(w - 297) > 3 or abs(h - 420) > 3:
                    errors.append(f"PDF не А3: {w:.0f}×{h:.0f} мм")
                if pdf_path.stat().st_mtime < dxf_path.stat().st_mtime - 1:
                    errors.append("PDF старше DXF – напечатан не из этого файла")
    uniq = list(dict.fromkeys(errors))
    return dict(passed=not uniq, errors=uniq[:60], error_count=len(uniq), texts=len(texts))
