"""Рисунки записки строятся кодом из модели (matplotlib), без участия LLM."""
from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams.update({"font.family": "Times New Roman", "font.size": 11})


def _fmt(x: float, n: int = 2) -> str:
    return f"{x:.{n}f}".replace(".", ",")


def plan(d: dict, path: Path) -> Path:
    g, v = d["grid"], d["variant"]
    L, W = g["main_len"], g["row_len"]
    fig, ax = plt.subplots(figsize=(8.0, 8.0 * W / L + 1.2))
    ax.add_patch(plt.Rectangle((0, 0), L, W, fill=False, lw=2.2, color="black"))
    zone_rows = d["zone"]["rows"]
    x0 = 0.0
    ax.add_patch(plt.Rectangle((x0, 0), zone_rows * g["a"], W, fill=True, color="0.9", lw=0))
    for s in d["sprinklers"]:
        ax.plot(s["x"], s["y"], "o", ms=6, mfc="white" if not s["zone"] else "black", mec="black")
    for i in range(g["n_rows"]):
        x = g["a"] / 2 + i * g["a"]
        ax.plot([x, x], [g["b"] / 2, W - g["b"] / 2], color="black", lw=1)
    ym = W / 2
    ax.plot([g["a"] / 2, L + 1.2], [ym, ym], color="black", lw=2.4)
    ax.plot(L + 1.2, ym, "s", ms=10, mfc="white", mec="black")
    ax.text(L + 1.2, ym + 0.8, "к насосной\nстанции", ha="center", va="bottom", fontsize=9)
    ax.annotate("", xy=(0, -0.9), xytext=(L, -0.9), arrowprops=dict(arrowstyle="<->", lw=0.8))
    ax.text(L / 2, -1.5, f"{_fmt(L, 1)} м", ha="center", va="top")
    ax.annotate("", xy=(-0.9, 0), xytext=(-0.9, W), arrowprops=dict(arrowstyle="<->", lw=0.8))
    ax.text(-1.5, W / 2, f"{_fmt(W, 1)} м", ha="right", va="center", rotation=90)
    ax.annotate("", xy=(g["a"] / 2, W + 0.6), xytext=(g["a"] * 1.5, W + 0.6), arrowprops=dict(arrowstyle="<->", lw=0.8))
    ax.text(g["a"], W + 0.8, f"{_fmt(g['a'])}", ha="center", va="bottom", fontsize=9)
    ax.annotate("", xy=(-0.3, g["b"] / 2), xytext=(-0.3, g["b"] * 1.5), arrowprops=dict(arrowstyle="<->", lw=0.8))
    ax.text(-0.45, g["b"], f"{_fmt(g['b'])}", ha="right", va="center", fontsize=9, rotation=90)
    ax.text(x0 + zone_rows * g["a"] / 2, W + 1.6, "диктующая зона", ha="center", fontsize=9)
    ax.set_xlim(-2.6, L + 2.6)
    ax.set_ylim(-2.4, W + 2.4)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def scheme(d: dict, path: Path) -> Path:
    """Расчётная аксонометрическая схема диктующей зоны с номерами точек, диаметрами и длинами участков."""
    per_side, rows = d["grid"]["per_side"], d["zone"]["rows"]
    dx, dy = 1.0, 0.55
    fig, ax = plt.subplots(figsize=(8.5, 5.6))
    ex, ey = 1.3, 0.75
    feed_x = [0.0]
    for r in range(rows):
        xr, yr = r * 2.2, 0
        for side in (-1, 1):
            pts = [(xr + side * k * ex * 0 + side * (per_side - k) * ex, yr + side * (per_side - k) * ey) for k in range(per_side)]
            xs = [xr] + [p[0] for p in reversed(pts)]
            ys = [yr] + [p[1] for p in reversed(pts)]
            ax.plot(xs, ys, color="black", lw=1.2)
            for px, py in pts:
                ax.plot([px, px], [py, py + 0.25], color="black", lw=1)
                ax.plot(px, py + 0.32, marker="v", ms=6, color="black")
        feed_x.append(xr)
    last = (rows - 1) * 2.2
    ax.plot([0, last + 3.0], [0, 0], color="black", lw=2.6)
    ax.plot([last + 3.0, last + 3.0], [0, -2.6], color="black", lw=2.6)
    ax.plot(last + 3.0, -2.75, marker="s", ms=10, mfc="white", mec="black")
    ax.text(last + 3.35, -2.75, "УУ", va="center")
    secs = d["sections"]
    for i in range(per_side):
        px = -(per_side - i) * ex + 0 * dx
        py = -(per_side - i) * ey
        ax.text(px - 0.15, py - 0.35, str(i + 1), fontsize=10, fontweight="bold", ha="right")
    ax.text(0.05, -0.35, str(per_side + 1), fontsize=10, fontweight="bold")
    for r in range(1, rows):
        ax.text(r * 2.2 + 0.05, -0.35, str(per_side + 1 + r), fontsize=10, fontweight="bold")
    ax.text(last + 3.05, 0.15, str(per_side + rows), fontsize=10, fontweight="bold")
    ax.text(last + 3.05, -2.4, str(per_side + rows + 1), fontsize=10, fontweight="bold")
    dist = secs[0]
    feed = next(s for s in secs if s["kind"] != "Распределительный")
    ax.text(-per_side * ex / 2 - 0.4, -per_side * ey / 2 + 0.2, f"Ø{dist['pipe']}", rotation=30, fontsize=9)
    ax.text(last / 2 + 0.6, 0.12, f"Ø{feed['pipe']}", fontsize=9)
    ax.text(0.2, 2.2, "Рядок I", fontsize=10)
    if rows > 1:
        ax.text(2.4, 2.2, "Рядок II", fontsize=10)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def pump_chart(d: dict, path: Path) -> Path:
    """Характеристика сети H = Hст + S·Q² и номинальный режим выбранного насоса."""
    q_req = d["total_flow_m3h"]
    h_req = d["head"]["total"]
    h_static = d["head"]["z"] + d["h1"]
    s = (h_req - h_static) / q_req ** 2
    pump = d["pump"]
    qmax = max(pump["q_nom"], q_req) * 1.35
    qs = [qmax * i / 100 for i in range(101)]
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    ax.plot(qs, [h_static + s * q * q for q in qs], color="black", lw=1.6, label="характеристика сети")
    ax.plot(q_req, h_req, "o", color="black", ms=7, label=f"требуемый режим: {_fmt(q_req, 1)} м³/ч; {_fmt(h_req, 1)} м")
    ax.plot(pump["q_nom"], pump["h_nom"], "s", mfc="white", mec="black", ms=8,
            label=f"номинальный режим {pump['name']}: {pump['q_nom']:g} м³/ч; {pump['h_nom']:g} м")
    ax.set_xlabel("Подача Q, м³/ч")
    ax.set_ylabel("Напор H, м")
    ax.grid(True, lw=0.4, color="0.7")
    ax.set_xlim(0, qmax)
    ax.set_ylim(0, max(pump["h_nom"], h_req) * 1.3)
    ax.legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path
