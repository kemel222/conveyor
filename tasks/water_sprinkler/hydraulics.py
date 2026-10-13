"""Гидравлический расчёт спринклерной АУП по методике хрестоматии и прил. В СП 5.13130.2009.

Единицы методики хрестоматии: напор H — м вод. ст., расход q — л/с.
  q = k·√H                     расход оросителя (k по паспорту, дм3/(с·МПа^0,5) = л/(с·м^0,5))
  ΔH = Q²·l / Kт               потери на участке (Kт — табл. В.2 СП 5, л6/с2)
  B = Q_I² / H_a               характеристика рядка; Q_II = √(B·H_b)
  Hтр = H1 + ΣΔH + 0,2·ΣΔH + Hуу + Z
Модуль не обращается к LLM: результат детерминирован и воспроизводим.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from . import norms


@dataclass
class Section:
    name: str
    kind: str
    flow: float
    dn: int
    pipe: str
    length: float
    loss: float
    velocity: float


def pipe_label(dn: int) -> str:
    outer, wall, _ = norms.PIPES[dn]
    return f"{outer}х{str(wall).replace('.', ',')}"


def pipe_km(dn: int) -> float:
    return norms.PIPES[dn][2]


def velocity(flow: float, dn: int) -> float:
    outer, wall, _ = norms.PIPES[dn]
    inner = (outer - 2 * wall) / 1000.0
    return flow / 1000.0 / (math.pi * inner * inner / 4.0)


def section_loss(flow: float, length: float, dn: int) -> float:
    return flow * flow * length / pipe_km(dn)


def branch(k: float, head_end: float, count: int, spacing: float, tail: float, dn: int, first_point: int = 1) -> dict:
    """Ветвь рядка от крайнего (диктующего) оросителя до точки подключения к питающему трубопроводу."""
    heads, flows, sections = [], [], []
    head, cumulative = head_end, 0.0
    for i in range(count):
        q = k * math.sqrt(head)
        heads.append(head)
        flows.append(q)
        cumulative += q
        length = spacing if i < count - 1 else tail
        dh = section_loss(cumulative, length, dn)
        sections.append(Section(f"{first_point + i}-{first_point + i + 1}", "Распределительный", cumulative, dn,
                                pipe_label(dn), length, dh, velocity(cumulative, dn)))
        head += dh
    return dict(heads=heads, flows=flows, sections=sections, flow=cumulative, head_junction=head)


def network(k: float, h1: float, rows: int, per_side: int, spacing: float, tail: float, row_pitch: float,
            dn_dist: int, dn_feed: int, extra: list[tuple[str, float, float, int]], ring: bool = False,
            symmetric: bool = True) -> dict:
    """Расчёт диктующей зоны: рядки, питающий трубопровод между рядками и участки до узла управления.

    extra: [(вид участка, длина, доля расхода, DN)] после последнего рядка зоны.
    """
    first = branch(k, h1, per_side, spacing, tail, dn_dist)
    row_flow = first["flow"] * (2 if symmetric else 1)
    head = first["head_junction"]
    b_char = row_flow ** 2 / head
    sections = list(first["sections"])
    point = per_side + 1
    total = row_flow
    row_flows = [row_flow]
    row_heads = [head]
    fraction = 0.5 if ring else 1.0
    for _ in range(1, rows):
        q = total * fraction
        dh = section_loss(q, row_pitch, dn_feed)
        sections.append(Section(f"{point}-{point + 1}", "Питающий", q, dn_feed, pipe_label(dn_feed), row_pitch, dh,
                                velocity(q, dn_feed)))
        head += dh
        point += 1
        q_row = math.sqrt(b_char * head)
        row_flows.append(q_row)
        row_heads.append(head)
        total += q_row
    for kind, length, share, dn in extra:
        q = total * share
        dh = section_loss(q, length, dn)
        sections.append(Section(f"{point}-{point + 1}", kind, q, dn, pipe_label(dn), length, dh, velocity(q, dn)))
        head += dh
        point += 1
    return dict(first_branch=first, row_flows=row_flows, row_heads=row_heads, b_char=b_char, total=total,
                sections=sections, sum_loss=sum(s.loss for s in sections), end_point=point, head_end=head)


def required_head(h1: float, sum_loss: float, huu: float, z: float) -> dict:
    hm = norms.LOCAL_LOSS_FACTOR * sum_loss
    return dict(h1=h1, sum_loss=sum_loss, local=hm, huu=huu, z=z, total=h1 + sum_loss + hm + huu + z)


def control_valve(dn_feed: int, flow: float) -> dict:
    dn = min(d for d in norms.CONTROL_VALVES if d >= max(dn_feed, 65))
    xi = norms.CONTROL_VALVES[dn]
    q_m3h = flow * 3.6
    return dict(dn=dn, xi=xi, name=f"УУ-С{dn}/1,6В-ВФ.О4 «Шалтан»", flow_m3h=q_m3h, loss=xi * 1000.0 * q_m3h ** 2)


def room_params(variant: dict) -> dict:
    key = variant["room_type"].lower().replace("ё", "е")
    if key not in norms.ROOM_GROUPS:
        raise ValueError(f"Для помещения «{variant['room_type']}» не задана группа по приложению Б")
    info = dict(norms.ROOM_GROUPS[key])
    group = info["group"]
    if group in norms.TABLE_5_1:
        params = dict(norms.TABLE_5_1[group])
    else:
        storage = variant.get("storage_height") or 1.0
        level = min(h for h in norms.TABLE_5_2 if h >= storage)
        intensity, flow = norms.TABLE_5_2[level][group]
        params = dict(intensity=intensity, flow=flow, **norms.STORAGE_GROUP_COMMON)
    params.update(group=group, group_quote=info["quote"], by_analogy=info.get("by_analogy", False))
    return params


def choose_grid(length: float, width: float, smax: float, omega_max: float) -> dict:
    main_len, row_len = max(length, width), min(length, width)
    best = None
    n_r0 = math.ceil(row_len / smax)
    n_r0 += n_r0 % 2
    for n_r in range(n_r0, n_r0 + 8, 2):
        for n_rows in range(math.ceil(main_len / smax), math.ceil(main_len / smax) + 12):
            a, b = main_len / n_rows, row_len / n_r
            if a > smax + 1e-9 or b > smax + 1e-9 or a * b > omega_max + 1e-9:
                continue
            key = (n_r * n_rows, abs(a - b))
            if best is None or key < best[0]:
                best = (key, dict(n_r=n_r, n_rows=n_rows, a=a, b=b))
            break
    if best is None:
        raise ValueError("Не удалось расставить оросители с соблюдением норм")
    grid = best[1]
    grid.update(main_len=main_len, row_len=row_len, per_side=grid["n_r"] // 2, omega=grid["a"] * grid["b"],
                main_along="length" if length >= width else "width")
    return grid


def _solve_for(variant: dict, params: dict, grid: dict, rows_zone: int, dn_dist: int, dn_feed: int) -> dict:
    sprinkler = norms.SPRINKLERS[variant["sprinkler"]]
    k = sprinkler["K"]
    a, b, per_side = grid["a"], grid["b"], grid["per_side"]
    main_to_riser = grid["main_len"] - a / 2 - (rows_zone - 1) * a
    riser = variant["height"] + norms.CONNECTION_LENGTH
    extra = [("Питающий", main_to_riser, 1.0, dn_feed), ("Подводящий (стояк)", riser, 1.0, dn_feed)]
    h_min = max(norms.SPRINKLER_PASSPORT["p_min_mpa"] * 100.0, (params["intensity"] * grid["omega"] / k) ** 2)

    def run(h1: float) -> dict:
        return network(k, h1, rows_zone, per_side, b, b / 2, a, dn_dist, dn_feed, extra)

    lo, hi = h_min, h_min
    while run(hi)["total"] < params["flow"]:
        hi *= 1.5
        if hi > 100:
            raise ValueError("Нормативный расход не достигается при давлении до 1 МПа")
    if hi > lo:
        for _ in range(60):
            mid = (lo + hi) / 2
            if run(mid)["total"] >= params["flow"]:
                hi = mid
            else:
                lo = mid
    h1 = math.ceil(hi * 10 - 1e-9) / 10
    net = run(h1)
    valve = control_valve(dn_feed, net["total"])
    head = required_head(h1, net["sum_loss"], valve["loss"], variant["height"])
    vmax = max(s.velocity for s in net["sections"])
    return dict(k=k, h1=h1, h_min=h_min, net=net, valve=valve, head=head, vmax=vmax, dn_dist=dn_dist, dn_feed=dn_feed)


def _table_b3_dn(count: int) -> int:
    return next(dn for dn, n in norms.TABLE_B3 if n >= count)


def choose_pump(flow: float, head: float) -> dict:
    q_m3h = flow * 3.6
    fit = [p for p in norms.PUMPS if p[1] >= q_m3h and p[2] >= head]
    if not fit:
        raise ValueError("В перечне насосов нет подходящей марки")
    name, q_nom, h_nom, power = min(fit, key=lambda p: (p[3], p[2], p[1]))
    return dict(name=name, q_nom=q_nom, h_nom=h_nom, power=power, q_req_m3h=q_m3h, h_req=head, source=norms.PUMP_SOURCE)


def _candidates(variant: dict, params: dict, grid: dict, rows_zone: int, dist_ref: int) -> list[dict]:
    series = [25, 32, 40, 50, 65, 80, 100, 125, 150, 200]
    out = []
    for dd in series[series.index(dist_ref):series.index(dist_ref) + 4]:
        for df in series:
            if df <= dd:
                continue
            try:
                r = _solve_for(variant, params, grid, rows_zone, dd, df)
            except ValueError:
                continue
            dist_v = max(s.velocity for s in r["net"]["sections"] if s.kind == "Распределительный")
            feed_v = max(s.velocity for s in r["net"]["sections"] if s.kind != "Распределительный")
            out.append(dict(dn_dist=dd, dn_feed=df, h1=r["h1"], flow=r["net"]["total"], sum_loss=r["net"]["sum_loss"],
                            h_req=r["head"]["total"], v_dist=dist_v, v_feed=feed_v,
                            p_ok=r["head"]["total"] - variant["height"] <= 100.0, result=r))
    return out


def _select(candidates: list[dict]) -> dict | None:
    """Минимальный распределительный DN с допустимой скоростью; питающий DN увеличивается,
    пока следующий типоразмер снижает Нтр более чем на HEAD_GAIN_THRESHOLD."""
    for dd in sorted({c["dn_dist"] for c in candidates}):
        row = sorted((c for c in candidates if c["dn_dist"] == dd), key=lambda c: c["dn_feed"])
        if not row or row[0]["v_dist"] > norms.VELOCITY_LIMIT:
            continue
        ok = [c for c in row if c["v_feed"] <= norms.VELOCITY_LIMIT and c["p_ok"]]
        if not ok:
            continue
        pick = ok[0]
        for nxt in ok[1:]:
            if (pick["h_req"] - nxt["h_req"]) / pick["h_req"] > norms.HEAD_GAIN_THRESHOLD:
                pick = nxt
            else:
                break
        return pick
    return None


def design(variant: dict) -> dict:
    params = room_params(variant)
    sprinkler = norms.SPRINKLERS[variant["sprinkler"]]
    smax = params["spacing"]
    chosen = None
    while smax >= 2.0 - 1e-9 and chosen is None:
        grid = choose_grid(variant["length"], variant["width"], smax, norms.SPRINKLER_PASSPORT["protected_area"])
        n_need = math.ceil(params["area"] / grid["omega"] - 1e-9)
        rows_min = min(grid["n_rows"], max(2, math.ceil(n_need / grid["n_r"])))
        dist_ref = _table_b3_dn(grid["per_side"])
        for rows_zone in range(rows_min, grid["n_rows"] + 1):
            candidates = _candidates(variant, params, grid, rows_zone, dist_ref)
            chosen = _select(candidates)
            if chosen:
                break
        if chosen is None:
            smax = round(smax - 0.25, 2)
    if chosen is None:
        raise ValueError("Ни одно сочетание шага и диаметров не удовлетворяет ограничениям")
    grid["rows_min"] = rows_min
    grid["spacing_limit"] = smax
    grid["spacing_reduced"] = smax < params["spacing"] - 1e-9
    for c in candidates:
        c["chosen"] = c is chosen
    shown = [c for c in candidates if c["dn_dist"] == chosen["dn_dist"]]
    shown += [c for c in candidates if c["dn_feed"] == chosen["dn_feed"] and c["dn_dist"] != chosen["dn_dist"]]
    shown.sort(key=lambda c: (c["dn_dist"], c["dn_feed"]))
    r = chosen["result"]
    net = r["net"]
    pump = choose_pump(net["total"], r["head"]["total"])
    sprinklers = _coordinates(grid, rows_zone)
    spec = _specification(variant, grid, r, sprinkler, pump)
    zone_area = rows_zone * grid["n_r"] * grid["omega"]
    return dict(
        variant=variant,
        params=params,
        sprinkler=dict(name=variant["sprinkler"], **sprinkler, passport=norms.SPRINKLER_PASSPORT),
        grid=grid,
        zone=dict(rows=rows_zone, count=rows_zone * grid["n_r"], area=zone_area, n_need=n_need),
        dn_ref_b3=dist_ref,
        candidates=[{k2: v for k2, v in c.items() if k2 != "result"} for c in shown],
        chosen=dict(dn_dist=r["dn_dist"], dn_feed=r["dn_feed"]),
        h1=r["h1"], h_min=r["h_min"], q1=r["k"] * math.sqrt(r["h1"]),
        q1_required=params["intensity"] * grid["omega"],
        branch=dict(heads=net["first_branch"]["heads"], flows=net["first_branch"]["flows"]),
        row_flows=net["row_flows"], row_heads=net["row_heads"], b_char=net["b_char"],
        sections=[asdict(s) for s in net["sections"]],
        total_flow=net["total"], total_flow_m3h=net["total"] * 3.6,
        head=r["head"], valve=r["valve"], pump=pump,
        water_volume=net["total"] * params["duration"] * 60 / 1000.0,
        sprinklers=sprinklers,
        specification=spec,
        checks=dict(
            flow_ok=net["total"] >= params["flow"],
            intensity_ok=r["k"] * math.sqrt(r["h1"]) >= params["intensity"] * grid["omega"] - 1e-9,
            pressure_min_ok=r["h1"] >= norms.SPRINKLER_PASSPORT["p_min_mpa"] * 100 - 1e-9,
            pressure_max_ok=r["head"]["total"] - variant["height"] <= 100.0,
            spacing_ok=grid["a"] <= params["spacing"] + 1e-9 and grid["b"] <= params["spacing"] + 1e-9,
            wall_ok=grid["a"] / 2 <= params["spacing"] / 2 + 1e-9 and grid["b"] / 2 <= params["spacing"] / 2 + 1e-9,
            area_ok=zone_area >= params["area"] - 1e-9,
        ),
    )


def _coordinates(grid: dict, rows_zone: int) -> list[dict]:
    out = []
    for i in range(grid["n_rows"]):
        x = grid["a"] / 2 + i * grid["a"]
        for j in range(grid["n_r"]):
            y = grid["b"] / 2 + j * grid["b"]
            out.append(dict(row=i + 1, pos=j + 1, x=x, y=y, zone=i < rows_zone))
    return out


def _specification(variant: dict, grid: dict, r: dict, sprinkler: dict, pump: dict) -> list[dict]:
    reserve = 1.06
    dist_len = grid["n_rows"] * (grid["n_r"] - 1) * grid["b"] * reserve
    main_len = (grid["main_len"] - grid["a"] / 2) * reserve
    riser_len = (variant["height"] + norms.CONNECTION_LENGTH) * reserve
    dd, df = r["dn_dist"], r["dn_feed"]
    feed_len = main_len + riser_len
    step_d = 3.0
    step_f = 4.0
    rows = [
        dict(name=f"Ороситель спринклерный водяной «{variant['sprinkler']}» {sprinkler['mount']}, 68 °С",
             mark=f"СВО0-Р{'В' if variant['sprinkler'].startswith('СВВ') else 'Н'}о{str(sprinkler['K']).replace('.', ',')}-R1/2/Р68.В3-«{variant['sprinkler']}»",
             unit="шт.", qty=grid["n_r"] * grid["n_rows"]),
        dict(name=f"Труба стальная электросварная Ду{dd} ({pipe_label(dd)}), вкл. 6 % запаса", mark="ГОСТ 10704-91",
             unit="м", qty=round(dist_len, 1)),
        dict(name=f"Труба стальная электросварная Ду{df} ({pipe_label(df)}), вкл. 6 % запаса", mark="ГОСТ 10704-91",
             unit="м", qty=round(feed_len, 1)),
        dict(name=f"Тройник Ду{df}×Ду{dd}", mark="ГОСТ 17376-2001", unit="шт.", qty=grid["n_rows"]),
        dict(name=f"Отвод крутоизогнутый 90° Ду{df}", mark="ГОСТ 17375-2001", unit="шт.", qty=2),
        dict(name=f"Опора подвесная для трубы Ду{dd}", mark="", unit="шт.", qty=math.ceil(dist_len / step_d)),
        dict(name=f"Опора подвесная для трубы Ду{df}", mark="", unit="шт.", qty=math.ceil(feed_len / step_f)),
        dict(name=r["valve"]["name"], mark="ЗАО «ПО «Спецавтоматика»", unit="шт.", qty=1),
        dict(name=f"Задвижка Ду{r['valve']['dn']}", mark="", unit="шт.", qty=2),
        dict(name="Сигнализатор потока жидкости", mark="", unit="шт.", qty=1),
        dict(name=f"Насос пожарный {pump['name']} (рабочий и резервный)", mark="ГОСТ 22247-96" if pump["name"].startswith("К") else "ГОСТ 10272-87", unit="шт.", qty=2),
        dict(name="Жокей-насос для поддержания давления в дежурном режиме", mark="", unit="шт.", qty=1),
        dict(name="Кран шаровой Ду50 для слива", mark="", unit="шт.", qty=1),
    ]
    for i, row in enumerate(rows, 1):
        row["pos"] = i
    return rows
