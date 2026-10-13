"""Проверка прозы Sol до сборки: объём разделов, запрещённые слова, числа только из блока ДАННЫЕ.

Возвращает замечания по каждому разделу отдельно, чтобы переписывать только отклонённые разделы.
"""
from __future__ import annotations

import json
import re

from . import prose as P
from .check_report import FORBIDDEN


def _num_tokens(text: str) -> set[str]:
    return {t.replace(".", ",").rstrip(",") for t in re.findall(r"(?<![\w])\d+(?:[.,]\d+)?", text)}


def _expand(tokens: set[str]) -> set[str]:
    """Допустимые числа: как записаны в данных (675,0), в целом виде (675) и в мм (27 м -> 27000 мм)."""
    out = set(tokens)
    for t in tokens:
        try:
            v = float(t.replace(",", "."))
        except ValueError:
            continue
        for m in (v, v * 1000):
            if abs(m - round(m)) < 1e-9:
                out.add(str(int(round(m))))
    return out


def word_count(paras: list[str]) -> int:
    return len(" ".join(paras).split())


def check_sections(answer: dict, design: dict, bibliography: list[str], keys=None) -> dict[str, list[str]]:
    allowed = _expand(_num_tokens(json.dumps(P.facts(design, bibliography), ensure_ascii=False)))
    allowed |= _expand({"5.13130.2009", "10.13130.2009", "123", "2008", "2009", "1985", "2002", "68", "0,1"})
    allowed |= _expand(_num_tokens(" ".join(bibliography)))
    out: dict[str, list[str]] = {}
    for key in keys or P.SECTIONS:
        title, lo, hi, _what = P.SECTIONS[key]
        paras = [p for p in (answer.get(key) or []) if p.strip()]
        text = " ".join(paras)
        errs = []
        words = word_count(paras)
        if words < lo:
            errs.append(f"{words} слов, нужно не менее {lo} (допустимо {lo}–{hi}); добавь содержания, а не повторов")
        elif words > hi * 1.2:
            errs.append(f"{words} слов, нужно не более {hi}")
        low = text.lower()
        for pat in FORBIDDEN:
            if re.search(pat, low):
                errs.append(f"запрещённое слово или шаблон «{pat}»")
        if re.search(r"[A-Za-z]{4,}", text):
            errs.append("латиница в тексте")
        if re.search(r"\d\.\d", re.sub(r"\d+\.\d+\.\d+|\d+\.13130", "", text)):
            errs.append("десятичная точка вместо запятой")
        if re.search(r"^\s*[-•*#]", "\n".join(paras), flags=re.M):
            errs.append("список или разметка вместо абзацев")
        bad = sorted(t for t in _num_tokens(text) - allowed if not re.fullmatch(r"\d{1,2}", t))
        if bad:
            errs.append(f"числа не из блока ДАННЫЕ: {', '.join(bad[:8])}")
        refs = {int(r) for r in re.findall(r"\[(\d+)\]", text)}
        if any(r < 1 or r > len(bibliography) for r in refs):
            errs.append("ссылка на несуществующий источник")
        if errs:
            out[key] = errs
    seen: dict[str, str] = {}
    for key in P.SECTIONS:
        for p in answer.get(key) or []:
            k = p.strip()[:120]
            if len(k) > 80 and k in seen and seen[k] != key:
                out.setdefault(key, []).append(f"повторяет абзац из раздела «{P.SECTIONS[seen[k]][0]}»")
            seen.setdefault(k, key)
    return out


def check_prose(answer: dict, design: dict, bibliography: list[str]) -> list[str]:
    return [f"раздел «{P.SECTIONS[k][0]}»: {e}" for k, es in check_sections(answer, design, bibliography).items()
            for e in es]
