"""Простой журнал прогона: шаги с длительностью, в консоль и в файл."""
from __future__ import annotations

import time
import traceback
from pathlib import Path


class Log:
    def __init__(self, path: Path):
        self.path = path
        self.started = time.time()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write(f"=== старт {time.strftime('%Y-%m-%d %H:%M:%S')}")

    def _write(self, line: str):
        print(line, flush=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def note(self, text: str):
        self._write(f"    {text}")

    def step(self, title: str, fn):
        t0 = time.time()
        self._write(f"[{self.elapsed()}] {title} ...")
        try:
            result = fn()
        except Exception:
            self._write(f"    ОШИБКА за {time.time() - t0:.0f} с:\n" + traceback.format_exc())
            raise
        self._write(f"    готово за {time.time() - t0:.0f} с")
        return result

    def elapsed(self) -> str:
        s = int(time.time() - self.started)
        return f"{s // 60:02d}:{s % 60:02d}"
