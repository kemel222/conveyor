"""Вызов внешних исполнителей: Sol и CAD-Astra через `codex exec`.

Исполнитель получает только свою узкую задачу в отдельной рабочей папке. Он не видит
проверок, не может закрыть этап и не пишет доказательства: результат проверяет код.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunResult:
    ok: bool
    exit_code: int | None
    seconds: float
    stdout_path: Path
    stderr_path: Path
    error: str | None = None


def _kill_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.killpg(pid, 9)
        except OSError:
            pass


def run_bounded(cmd: list[str], cwd: Path, log_prefix: Path, timeout: int, stdin_text: str | None = None,
                stall: int | None = None, watch: list[Path] | None = None) -> RunResult:
    """Запуск с жёстким лимитом времени и остановкой при отсутствии активности (stall)."""
    out = log_prefix.with_suffix(".stdout.txt")
    err = log_prefix.with_suffix(".stderr.txt")
    started = time.time()
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with out.open("w", encoding="utf-8") as fo, err.open("w", encoding="utf-8") as fe:
        proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=fo, stderr=fe,
                                stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
                                creationflags=flags, text=True, encoding="utf-8")
        if stdin_text is not None:
            proc.stdin.write(stdin_text)
            proc.stdin.close()
        last_activity = time.time()
        last_sig = None
        while proc.poll() is None:
            time.sleep(2)
            now = time.time()
            if now - started > timeout:
                _kill_tree(proc.pid)
                return RunResult(False, None, now - started, out, err, f"превышен лимит {timeout} с")
            if stall:
                paths = [out, err] + list(watch or [])
                sig = tuple(_mtime_tree(p) for p in paths)
                if sig != last_sig:
                    last_sig, last_activity = sig, now
                elif now - last_activity > stall:
                    _kill_tree(proc.pid)
                    return RunResult(False, None, now - started, out, err, f"нет активности {stall} с")
    code = proc.returncode
    return RunResult(code == 0, code, time.time() - started, out, err, None if code == 0 else f"код выхода {code}")


def _mtime_tree(path: Path) -> float:
    if not path.exists():
        return 0.0
    if path.is_file():
        return path.stat().st_mtime
    return max((p.stat().st_mtime for p in path.rglob("*") if p.is_file()), default=path.stat().st_mtime)


def find_exe(name: str, configured: str | None = None) -> str:
    candidate = configured or shutil.which(name)
    if not candidate or not Path(candidate).exists():
        raise FileNotFoundError(f"Не найден исполняемый файл {name}")
    return candidate


def sol_json(prompt: str, schema: dict, workdir: Path, cfg: dict, tag: str) -> dict:
    """Sol пишет текст. Песочница только для чтения: файлов он не создаёт, отвечает JSON по схеме."""
    workdir.mkdir(parents=True, exist_ok=True)
    schema_path = workdir / f"{tag}.schema.json"
    answer_path = workdir / f"{tag}.answer.json"
    schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=1), encoding="utf-8")
    answer_path.unlink(missing_ok=True)
    cmd = [find_exe("codex", cfg.get("codex")), "exec", "--ephemeral", "--skip-git-repo-check",
           "--sandbox", "read-only", "-C", str(workdir), "--output-schema", str(schema_path),
           "--output-last-message", str(answer_path)]
    if cfg.get("sol_model"):
        cmd += ["-m", cfg["sol_model"]]
    cmd.append("-")
    res = run_bounded(cmd, workdir, workdir / tag, timeout=int(cfg.get("sol_timeout", 900)), stdin_text=prompt)
    if not res.ok:
        raise RuntimeError(f"Sol ({tag}): {res.error}; журнал {res.stderr_path}")
    if not answer_path.is_file():
        raise RuntimeError(f"Sol ({tag}) не вернул ответ; журнал {res.stdout_path}")
    return json.loads(answer_path.read_text(encoding="utf-8"))


def astra_cad_task(prompt: str, workdir: Path, cfg: dict, tag: str) -> RunResult:
    """Astra работает только внутри своей папки и пишет генератор чертежей.

    Проверки запускаются драйвером после завершения модели; Astra не получает
    права подписывать этап и не может менять исходные данные заказа.
    """
    prompt_file = workdir / f"{tag}.prompt.md"
    prompt_file.write_text(prompt, encoding="utf-8")
    short = (f"Прочитай задание в файле {prompt_file.name} в текущей папке и выполни его полностью в этом "
             "ходе: напиши generate.py, запусти его и self_check.py и исправляй до «ЗАМЕЧАНИЙ НЕТ».")
    cmd = [find_exe("codex", cfg.get("codex")), "exec", "--ephemeral",
           "--skip-git-repo-check", "--approve-for-me",
           "-C", str(workdir),
           "--config", f"model_reasoning_effort={cfg.get('astra_reasoning_effort', 'high')}",
           "-m", cfg.get("astra_model", "gpt-6-astra"), "-"]
    return run_bounded(cmd, workdir, workdir / tag, timeout=int(cfg.get("astra_timeout", 1800)),
                       stall=int(cfg.get("astra_stall", 480)), watch=[workdir], stdin_text=short)
