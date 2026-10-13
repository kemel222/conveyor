"""Варианты задания: таблица 1.1 хрестоматии (читается из исходного DOCX заказа)."""
from __future__ import annotations

import re
from pathlib import Path

import docx

LATIN_TO_CYR = str.maketrans({"C": "С", "B": "В", "H": "Н", "c": "с", "x": "х", "X": "х", "×": "х"})


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(LATIN_TO_CYR)).strip()


def read_variants(readerbook: Path) -> dict[int, dict]:
    document = docx.Document(str(readerbook))
    table = next(
        (t for t in document.tables if t.rows and "журналу" in t.rows[0].cells[0].text),
        None,
    )
    if table is None:
        raise ValueError(f"В {readerbook.name} не найдена таблица 1.1 вариантов")
    result: dict[int, dict] = {}
    for row in table.rows[1:]:
        cells = [_norm(c.text) for c in row.cells]
        if not cells[0].isdigit():
            continue
        number = int(cells[0])
        sprinkler, dims, room = cells[1], cells[2], cells[3]
        if not sprinkler or not dims:
            result[number] = dict(number=number, supported=False, room=room or dims,
                                  reason="вариант не относится к спринклерной АУП помещения")
            continue
        parts = [float(p.replace(",", ".")) for p in dims.split("х")]
        storage = re.search(r"Нхр\.?\s*=\s*([\d.,]+)", room)
        result[number] = dict(
            number=number,
            supported=True,
            sprinkler=sprinkler.replace(" ", ""),
            length=parts[0],
            width=parts[1],
            height=parts[2],
            room=room,
            room_type=re.sub(r"\.\s*Нхр.*$", "", room).strip(),
            storage_height=float(storage.group(1).replace(",", ".")) if storage else None,
            source=f"{readerbook.name}, таблица 1.1, строка {number}",
        )
    return result
