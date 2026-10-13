"""Набор для листов А3 по ЕСКД: рамка (ГОСТ 2.301/2.104), основная надпись форма 1, текст, размеры, таблицы.

Пишется и поддерживается кодом. Astra использует только эти функции и данные листа из JSON;
рамку, штамп и шрифт он не рисует сам. Все построения – в миллиметрах листа (модель = лист 1:1),
геометрия объекта масштабируется функцией Sheet.to_paper().
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import ezdxf
from ezdxf.enums import TextEntityAlignment

A3_W, A3_H = 420.0, 297.0
FRAME = (20.0, 5.0, 415.0, 292.0)          # левое поле 20 мм, остальные 5 мм
STAMP = (FRAME[2] - 185.0, FRAME[1], FRAME[2], FRAME[1] + 55.0)
TEXT_STYLE = "GOST"
WIDTH_FACTOR = 0.8
CHAR_W = 0.62  # средняя ширина символа ISOCPEUR в долях высоты при WIDTH_FACTOR = 0.8

LAYERS = {
    "FRAME": dict(color=7, lw=50), "STAMP": dict(color=7, lw=25), "TEXT": dict(color=7, lw=18),
    "WALL": dict(color=7, lw=70), "PIPE_FEED": dict(color=1, lw=70), "PIPE_DIST": dict(color=5, lw=35),
    "SPRINKLER": dict(color=3, lw=25), "EQUIP": dict(color=6, lw=35), "DIM": dict(color=8, lw=18),
    "TABLE": dict(color=7, lw=25), "AXIS": dict(color=8, lw=13), "HATCH": dict(color=9, lw=13),
}
ALIGN = {"left": TextEntityAlignment.BOTTOM_LEFT, "center": TextEntityAlignment.BOTTOM_CENTER,
         "right": TextEntityAlignment.BOTTOM_RIGHT, "middle": TextEntityAlignment.MIDDLE_CENTER,
         "middle_left": TextEntityAlignment.MIDDLE_LEFT}


def text_box(s: str, x: float, y: float, h: float, align: str = "left", rot: float = 0.0) -> tuple:
    """Габарит текста (xmin, ymin, xmax, ymax) – тот же, что использует проверка листа."""
    w = max(len(s), 1) * h * CHAR_W
    if align in ("left", "middle_left"):
        x0 = 0.0
    elif align in ("center", "middle"):
        x0 = -w / 2
    else:
        x0 = -w
    y0 = -h / 2 if align.startswith("middle") else 0.0
    corners = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]
    c, sn = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    pts = [(x + px * c - py * sn, y + px * sn + py * c) for px, py in corners]
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


@dataclass
class Sheet:
    title: str
    number: int
    scale: str
    stamp: dict
    doc: ezdxf.document.Drawing = field(init=False)

    def __post_init__(self):
        self.doc = ezdxf.new("R2010", setup=True)
        self.doc.header["$INSUNITS"] = 4
        self.doc.header["$LWDISPLAY"] = 1
        self.doc.styles.add(TEXT_STYLE, font="isocpeur.ttf").dxf.width = WIDTH_FACTOR
        for name, a in LAYERS.items():
            self.doc.layers.add(name, color=a["color"], lineweight=a["lw"])
        self.msp = self.doc.modelspace()
        self._frame()
        self._stamp()

    # ------------------------------------------------------------- примитивы
    def line(self, p1, p2, layer="AXIS"):
        return self.msp.add_line(p1, p2, dxfattribs={"layer": layer})

    def polyline(self, pts, layer="AXIS", closed=False):
        return self.msp.add_lwpolyline(pts, close=closed, dxfattribs={"layer": layer})

    def rect(self, x0, y0, x1, y1, layer="AXIS"):
        return self.polyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], layer, closed=True)

    def circle(self, c, r, layer="SPRINKLER", filled=False):
        e = self.msp.add_circle(c, r, dxfattribs={"layer": layer})
        if filled:
            h = self.msp.add_hatch(dxfattribs={"layer": layer})
            h.paths.add_edge_path().add_arc(c, r, 0, 360)
        return e

    def text(self, s: str, x: float, y: float, h: float = 3.5, align: str = "left", rot: float = 0.0,
             layer: str = "TEXT"):
        t = self.msp.add_text(str(s), height=h, rotation=rot,
                              dxfattribs={"layer": layer, "style": TEXT_STYLE, "width": WIDTH_FACTOR})
        t.set_placement((x, y), align=ALIGN[align])
        return t

    def dim(self, p1, p2, offset: float, label: str, h: float = 2.5):
        """Линейный размер (горизонтальный или вертикальный): выносные, размерная линия, засечки, текст."""
        (x1, y1), (x2, y2) = p1, p2
        if abs(y1 - y2) < 1e-6:
            y = y1 + offset
            self.line((x1, y1), (x1, y + math.copysign(2, offset)), "DIM")
            self.line((x2, y2), (x2, y + math.copysign(2, offset)), "DIM")
            self.line((x1, y), (x2, y), "DIM")
            for x in (x1, x2):
                self.line((x - 1, y - 1), (x + 1, y + 1), "DIM")
            self.text(label, (x1 + x2) / 2, y + 0.8, h, "center", layer="DIM")
        else:
            x = x1 + offset
            self.line((x1, y1), (x + math.copysign(2, offset), y1), "DIM")
            self.line((x2, y2), (x + math.copysign(2, offset), y2), "DIM")
            self.line((x, y1), (x, y2), "DIM")
            for y in (y1, y2):
                self.line((x - 1, y - 1), (x + 1, y + 1), "DIM")
            self.text(label, x - 0.8, (y1 + y2) / 2, h, "center", rot=90, layer="DIM")

    def leader(self, p_from, p_to, label: str, h: float = 2.5):
        """Выноска: наклонная линия, полка под текстом, текст над полкой."""
        self.line(p_from, p_to, "DIM")
        w = len(label) * h * CHAR_W + 1.0
        direction = 1 if p_to[0] >= p_from[0] else -1
        end = (p_to[0] + direction * w, p_to[1])
        self.line(p_to, end, "DIM")
        x = p_to[0] + 0.5 if direction > 0 else end[0] + 0.5
        self.text(label, x, p_to[1] + 0.7, h, "left", layer="DIM")

    def table(self, x: float, y_top: float, header: list[str], rows: list[list[str]], widths: list[float],
              h: float = 2.5, row_h: float = 6.0, header_h: float = 10.0, title: str | None = None) -> float:
        """Таблица с сеткой; длинный текст ячейки переносится. Возвращает нижнюю координату таблицы."""
        if title:
            self.text(title, x, y_top + 2.0, 3.5)
        total_w = sum(widths)
        lines = []
        y = y_top
        all_rows = [(header, True)] + [(r, False) for r in rows]
        for cells, is_head in all_rows:
            wrapped = [self._wrap(str(c), w - 2.0, h) for c, w in zip(cells, widths)]
            n = max(len(wc) for wc in wrapped)
            rh = max(header_h if is_head else row_h, n * (h * 1.6) + 2.0)
            cx = x
            for wc, w, j in zip(wrapped, widths, range(len(widths))):
                block = len(wc) * h * 1.6
                ty = y - (rh - block) / 2 - h * 1.25
                for k, part in enumerate(wc):
                    if is_head or j != 1:
                        self.text(part, cx + w / 2, ty - k * h * 1.6, h, "center", layer="TABLE")
                    else:
                        self.text(part, cx + 1.0, ty - k * h * 1.6, h, "left", layer="TABLE")
                cx += w
            lines.append(y)
            y -= rh
        lines.append(y)
        for yy in lines:
            self.line((x, yy), (x + total_w, yy), "TABLE")
        cx = x
        for w in [0.0] + widths:
            cx += w
            self.line((cx, y_top), (cx, y), "TABLE")
        return y

    @staticmethod
    def _wrap(s: str, width: float, h: float) -> list[str]:
        per = max(int(width / (h * CHAR_W)), 1)
        words, out, cur = s.split(), [], ""
        for w in words:
            if len(cur) + len(w) + (1 if cur else 0) <= per:
                cur = f"{cur} {w}".strip()
            else:
                if cur:
                    out.append(cur)
                while len(w) > per:
                    out.append(w[:per])
                    w = w[per:]
                cur = w
        out.append(cur)
        return out or [""]

    # ------------------------------------------------------------- компоновка
    @staticmethod
    def free_area() -> tuple:
        """Поле чертежа без основной надписи: (xmin, ymin, xmax, ymax). Над штампом свободно."""
        return (FRAME[0] + 5, FRAME[1] + 5, FRAME[2] - 5, FRAME[3] - 5)

    @staticmethod
    def stamp_box() -> tuple:
        return STAMP

    @staticmethod
    def to_paper(origin: tuple, scale_den: int):
        """Функция перевода координат объекта (мм натуры) в мм листа для масштаба 1:scale_den."""
        ox, oy = origin
        return lambda x_mm, y_mm: (ox + x_mm / scale_den, oy + y_mm / scale_den)

    def save(self, path):
        self.doc.saveas(str(path))

    # ------------------------------------------------------------- рамка и штамп
    def _frame(self):
        self.rect(0, 0, A3_W, A3_H, "AXIS")
        self.rect(*FRAME, "FRAME")

    def _stamp(self):
        """Основная надпись по ГОСТ 2.104, форма 1: 185×55 мм в правом нижнем углу рамки."""
        x0, y0, x1, y1 = STAMP
        s = self.stamp
        L = lambda a, b, layer="STAMP": self.line(a, b, layer)
        self.rect(x0, y0, x1, y1, "FRAME")
        # Левый блок 65 мм: графы 7/10/23/15/10, 11 строк по 5 мм.
        xs = [x0]
        for c in (7, 10, 23, 15, 10):
            xs.append(xs[-1] + c)
        xl = xs[-1]
        for i in range(1, 11):
            L((x0, y0 + i * 5), (xl, y0 + i * 5), "FRAME" if i == 6 else "STAMP")
        for xx in xs[1:5]:
            L((xx, y0 + 25 if xx == xs[1] else y0), (xx, y1))
        L((xl, y0), (xl, y1), "FRAME")
        # Правый блок 120 мм: обозначение (15 мм), наименование работы (25 мм) / стадия-лист-листов, наименование
        # листа (15 мм) / организация.
        L((xl, y1 - 15), (x1, y1 - 15), "FRAME")
        L((xl, y0 + 15), (x1, y0 + 15), "FRAME")
        xr = xl + 70
        L((xr, y0), (xr, y1 - 15), "FRAME")
        L((xr, y0 + 35), (x1, y0 + 35))
        L((xr, y0 + 30), (x1, y0 + 30))
        L((xr + 15, y0 + 30), (xr + 15, y0 + 40))
        L((xr + 30, y0 + 30), (xr + 30, y0 + 40))
        names = ("Изм.", "Лист", "№ докум.", "Подп.", "Дата")
        for name, (a, b) in zip(names, [(xs[0], xs[1]), (xs[1], xs[2]), (xs[2], xs[3]), (xs[3], xs[4]), (xs[4], xs[5])]):
            self.text(name, (a + b) / 2, y0 + 25 + 1.3, 2.0, "center", layer="STAMP")
        roles = [("Разраб.", s.get("student", "")), ("Пров.", s.get("teacher", "")), ("", ""), ("", ""),
                 ("Н.контр.", ""), ("Утв.", "")]
        for k, (role, name) in enumerate(roles):
            yy = y0 + 20 - k * 5 + 1.3
            if yy < y0:
                break
            if role:
                self.text(role, xs[0] + 0.8, yy, 2.2, layer="STAMP")
            if name:
                self.text(name, xs[2] + 0.8, yy, 2.2, layer="STAMP")
        if s.get("date"):
            self.text(s["date"], (xs[4] + xs[5]) / 2, y0 + 20 + 1.3, 2.0, "center", layer="STAMP")
        self.text(s.get("code", ""), (xl + x1) / 2, y1 - 9.5, 5.0, "center", layer="STAMP")
        work = self._wrap(s.get("work", ""), 66, 3.0)[:4]
        top = y0 + 15 + 25 / 2 + (len(work) - 1) * 2.2
        for k, part in enumerate(work):
            self.text(part, xl + 35, top - k * 4.4, 3.0, "middle", layer="STAMP")
        title = self._wrap(self.title, 66, 3.0)[:3]
        top = y0 + 7.5 + (len(title) - 1) * 2.0
        for k, part in enumerate(title):
            self.text(part, xl + 35, top - k * 4.0, 3.0, "middle", layer="STAMP")
        for label, cx in (("Стадия", xr + 7.5), ("Лист", xr + 22.5), ("Листов", xr + 40)):
            self.text(label, cx, y0 + 36.2, 2.2, "center", layer="STAMP")
        self.text("У", xr + 7.5, y0 + 32.5, 3.0, "middle", layer="STAMP")
        self.text(str(self.number), xr + 22.5, y0 + 32.5, 3.0, "middle", layer="STAMP")
        self.text(str(s.get("sheets_total", 3)), xr + 40, y0 + 32.5, 3.0, "middle", layer="STAMP")
        self.text(f"Масштаб {self.scale}", xr + 25, y0 + 22.5, 3.0, "middle", layer="STAMP")
        org = self._wrap(s.get("org", ""), 46, 2.5)[:3]
        top = y0 + 7.5 + (len(org) - 1) * 1.8
        for k, part in enumerate(org):
            self.text(part, xr + 25, top - k * 3.6, 2.5, "middle", layer="STAMP")

