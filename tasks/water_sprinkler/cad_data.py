"""Данные для чертежей: всё, что должно быть на листах, вычисляется из модели здесь.

Astra получает этот JSON и пишет только оформление (ezdxf). Числа он не считает и не выдумывает.
"""
from __future__ import annotations


def fmt(x: float, n: int = 2) -> str:
    return f"{x:.{n}f}".replace(".", ",")


STANDARD_SCALES = (100, 200, 400)
PLAN_BOX = (150.0, 150.0)
AXON_BOX = (215.0, 120.0)


def plan_scale(length_mm: float, width_mm: float, extra_mm: float = 6000.0) -> int:
    """Наименьший стандартный масштаб, при котором план с насосной станцией помещается в поле листа."""
    for den in STANDARD_SCALES:
        if (length_mm + extra_mm) / den <= PLAN_BOX[0] + 30 and width_mm / den <= PLAN_BOX[1]:
            return den
    raise ValueError(f"Помещение {length_mm / 1000:g}×{width_mm / 1000:g} м не помещается на лист А3 в масштабе 1:400")


def axon_scale(length_mm: float, width_mm: float, height_mm: float, extra_mm: float = 6000.0) -> int:
    k = 0.5 * 0.7071
    for den in STANDARD_SCALES:
        w = (length_mm + extra_mm + k * width_mm) / den
        h = (k * width_mm + height_mm + 3000.0) / den
        if w <= AXON_BOX[0] and h <= AXON_BOX[1]:
            return den
    raise ValueError("Аксонометрия не помещается на лист А3 в масштабе 1:400")


def sheet_data(d: dict, meta: dict) -> dict:
    v, g = d["variant"], d["grid"]
    secs = d["sections"]
    dist = secs[0]
    feed = next(s for s in secs if s["kind"] != "Распределительный")
    hd = d["head"]
    # План: начало координат – левый нижний угол помещения, оси X вдоль питающего трубопровода, мм.
    L, W = g["main_len"] * 1000, g["row_len"] * 1000
    rows_x = [round((g["a"] / 2 + i * g["a"]) * 1000) for i in range(g["n_rows"])]
    pos_y = [round((g["b"] / 2 + j * g["b"]) * 1000) for j in range(g["n_r"])]
    zone_rows = d["zone"]["rows"]
    main_y = round(W / 2)
    riser = dict(x=round(L + 1500), y=main_y)
    result_rows = [[str(i), f"{s['kind']} трубопровод. Участок {s['name']}", fmt(s["flow"], 3), s["pipe"],
                    fmt(s["length"]), fmt(s["loss"], 3)] for i, s in enumerate(secs, 1)]
    n = len(secs)
    result_rows += [["", "Итого потерь по расчёту", "", "", "", fmt(hd["sum_loss"], 3)],
                    [str(n + 1), "С учётом потерь в местных сопротивлениях (+20 %)", "", "", "Нм =", fmt(hd["sum_loss"] * 1.2, 3)],
                    [str(n + 2), "Потери напора в узле управления", "", "", "Нуу =", fmt(hd["huu"], 3)],
                    [str(n + 3), "Разность гидравлических отметок", "", "", "Z =", fmt(hd["z"], 1)],
                    [str(n + 4), "Напор у диктующего оросителя", "", "", "Hд =", fmt(hd["h1"], 1)],
                    ["", "Итого требуемый напор", "", "", "Нтр =", fmt(hd["total"], 2)]]
    spec = [[str(r["pos"]), r["mark"], r["name"], fmt(r["qty"], 1) if isinstance(r["qty"], float) else str(r["qty"])]
            for r in d["specification"]]
    title = dict(
        org=meta.get("org", ""),
        work=f"Расчёт спринклерной установки водяного пожаротушения. {v['room']}, вариант {v['number']}",
        student=meta.get("student", ""), teacher=meta.get("teacher", ""), date=meta.get("date", ""),
        code=f"КР-ППА-{v['number']:02d}", sheets_total=3,
    )
    den_plan = plan_scale(L, W)
    den_axon = axon_scale(L, W, v["height"] * 1000)
    zone_count = zone_rows * g["n_r"]
    dims_plan = sorted({round(L), round(W), round(g["a"] * 1000), round(g["b"] * 1000), round(g["a"] * 500),
                        round(g["b"] * 500)})
    return dict(
        variant=v["number"],
        room=dict(name=v["room"], length_mm=round(L), width_mm=round(W), height_m=v["height"],
                  axis_note="X – вдоль питающего трубопровода, Y – вдоль рядков; начало в левом нижнем углу помещения"),
        sprinkler=dict(name=d["sprinkler"]["name"], mount=d["sprinkler"]["mount"]),
        grid=dict(rows_x_mm=rows_x, positions_y_mm=pos_y, step_rows_mm=round(g["a"] * 1000),
                  step_in_row_mm=round(g["b"] * 1000), wall_x_mm=round(g["a"] * 500), wall_y_mm=round(g["b"] * 500),
                  dictating_zone_rows=list(range(1, zone_rows + 1)), dictating_sprinkler=dict(row=1, pos=1),
                  sprinklers_total=len(rows_x) * len(pos_y), dictating_count=zone_count),
        scales=dict(plan=den_plan, axon=den_axon),
        plan_dimensions_mm=dims_plan,
        pipes=dict(distribution=dict(dn=dist["dn"], label=f"Ø{dist['pipe']}"),
                   feed=dict(dn=feed["dn"], label=f"Ø{feed['pipe']}", y_mm=main_y, x_from_mm=rows_x[0], x_to_mm=riser["x"]),
                   riser=dict(x_mm=riser["x"], y_mm=riser["y"], height_m=v["height"] + 3.0)),
        pump_station=dict(x_mm=riser["x"] + 1500, y_mm=riser["y"], pump=d["pump"]["name"], valve=d["valve"]["name"]),
        hydraulic_scheme=dict(points=n + 1, per_side=g["per_side"], rows=zone_rows,
                              sections=[dict(name=s["name"], kind=s["kind"], pipe=s["pipe"], length=fmt(s["length"]))
                                        for s in secs]),
        equipment=dict(pump=d["pump"]["name"], valve=d["valve"]["name"], sprinkler_k=fmt(d["sprinkler"]["K"], 2)),
        result_table=dict(caption="Таблица. Гидравлические потери в трубопроводах",
                          header=["№ п/п", "Наименование трубопровода", "Расход Q, л/с", "Труба по ГОСТ 10704-91",
                                  "Длина L, м", "Потери H, м"], rows=result_rows),
        specification=dict(header=["Поз.", "Обозначение", "Наименование", "Кол."], rows=spec),
        legend=[["●", "ороситель диктующей зоны"], ["○", "ороситель спринклерный"],
                ["▬", f"питающий трубопровод Ø{feed['pipe']}"], ["—", f"распределительный трубопровод Ø{dist['pipe']}"]],
        must_show=dict(
            plan=[f"Ø{dist['pipe']}", f"Ø{feed['pipe']}", fmt(g["a"] * 1000, 0), fmt(g["b"] * 1000, 0),
                  "Насосная станция", d["sprinkler"]["name"]],
            axon=[f"Ø{dist['pipe']}", f"Ø{feed['pipe']}", "Узел управления"],
            hydraulic=[fmt(hd["total"], 2), fmt(secs[-1]["flow"], 3), fmt(hd["huu"], 3), d["sprinkler"]["name"],
                       "Узел управления"],
        ),
        title_block=title,
        sheets=[dict(file="plan", title="План помещения с трубной разводкой", number=1, scale=f"1:{den_plan}"),
                dict(file="axon", title="Аксонометрическая схема установки", number=2, scale=f"1:{den_axon}"),
                dict(file="hydraulic", title="Расчётная схема и таблица гидравлического расчёта", number=3, scale="б/м"),
                ],
    )
