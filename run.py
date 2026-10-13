"""Единственная точка входа конвейера.

    python run.py <папка заказа> [--variants 3 4] [--only text|cad] [--reuse]

Заказ – папка с исходниками (DOCX хрестоматии/методички). Результат – <заказ>/Выдача/Вариант_N/ и ZIP.
Каждый шаг пишет журнал в <заказ>/_conveyor/run.log. Повторный запуск продолжает с готовых файлов (--reuse).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.log import Log  # noqa: E402
from tasks.water_sprinkler import cad, pipeline, variants  # noqa: E402

DEFAULT_CFG = dict(sol_model="gpt-6.1-sol", sol_timeout=900,
                   astra_model="gpt-6-astra", astra_reasoning_effort="high",
                   astra_timeout=1800, astra_stall=480)


def find_readerbook(order: Path) -> Path:
    cands = [p for p in order.rglob("*.docx") if "хрестомат" in p.name.lower() and "_conveyor" not in p.parts
             and "Выдача" not in p.parts]
    if not cands:
        raise FileNotFoundError(f"В {order} нет DOCX хрестоматии с таблицей вариантов")
    return sorted(cands, key=lambda p: len(p.parts))[0]


def load_meta(order: Path) -> dict:
    p = order / "order.json"
    meta = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    meta.setdefault("institution", [])
    meta.setdefault("year", time.strftime("%Y"))
    return meta


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def package(order: Path, done: dict[int, dict], log: Log) -> Path:
    out = order / "Выдача"
    manifest = {}
    for n, r in done.items():
        for p in [r["text"]["docx"], r["text"]["pdf"]] + [f for fs in r["cad"]["files"].values() for f in fs]:
            manifest[str(p.relative_to(out))] = sha256(p)
    (out / "SHA256.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    zpath = order / f"Выдача_{'_'.join(f'В{n}' for n in done)}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in manifest:
            z.write(out / rel, rel)
    with zipfile.ZipFile(zpath) as z:
        for rel, h in manifest.items():
            if hashlib.sha256(z.read(rel.replace("\\", "/"))).hexdigest() != h:
                raise RuntimeError(f"ZIP повреждён: {rel}")
    log.note(f"Комплект: {zpath} ({len(manifest)} файлов, контрольные суммы сверены)")
    return zpath


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("order")
    ap.add_argument("--variants", nargs="+", type=int, required=True)
    ap.add_argument("--only", choices=["text", "cad"])
    ap.add_argument("--reuse", action="store_true", help="переиспользовать прошедшие проверку текст и генератор")
    a = ap.parse_args(argv)
    order = Path(a.order).resolve()
    conv = order / "_conveyor"
    log = Log(conv / "run.log")
    cfg = dict(DEFAULT_CFG, reuse_prose=a.reuse, reuse_cad=a.reuse)
    cfg.update(load_meta(order).get("conveyor", {}))
    meta = load_meta(order)
    table = variants.read_variants(find_readerbook(order))
    done, failed = {}, {}
    for n in a.variants:
        v = table.get(n)
        if not v or not v.get("supported"):
            failed[n] = f"вариант {n} отсутствует в таблице 1.1 или не относится к спринклерной АУП"
            log.note(failed[n])
            continue
        log.note(f"===== Вариант {n}: {v['room']}, {v['length']:g}×{v['width']:g}×{v['height']:g} м, {v['sprinkler']}")
        work = conv / f"V{n}"
        out = order / "Выдача" / f"Вариант_{n}"
        work.mkdir(parents=True, exist_ok=True)
        out.mkdir(parents=True, exist_ok=True)
        try:
            res = {}
            if a.only != "cad":
                res["text"] = pipeline.build_text(v, out, work, cfg, meta, log)
            if a.only != "text":
                design = res["text"]["design"] if "text" in res else \
                    json.loads((work / "model.json").read_text(encoding="utf-8"))
                res["cad"] = cad.build_drawings(design, meta, out / "Чертежи", work / "cad", cfg, log)
            done[n] = res
        except Exception as e:  # noqa: BLE001
            failed[n] = str(e)
            log.note(f"ВАРИАНТ {n} ОСТАНОВЛЕН: {e}")
    if done and a.only is None and not failed:
        package(order, done, log)
    log.note(f"Итог за {log.elapsed()}: готово {sorted(done)}, остановлено {sorted(failed)}")
    for n, why in failed.items():
        log.note(f"  Вариант {n}: {why.splitlines()[0]}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
