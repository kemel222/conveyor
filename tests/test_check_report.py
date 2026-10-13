"""Проверка записки обязана отклонять уже известные бракованные выдачи (V3 и V4 от 2026-10-10)."""
import unittest
from pathlib import Path

from tasks.water_sprinkler.check_report import check_report

ARCHIVE = Path(r"C:\Users\WorkingLaptop\Downloads\Выполнение работ\99_Архив\2026")
BAD = {
    "V3": ARCHIVE / "Водяное пожаротушение — задание 2 — вариант 3 — 2026-10-10" / "outputs" / "V3",
    "V4": ARCHIVE / "Водяное пожаротушение — задание 2 — вариант 4 — 2026-10-10" / "outputs" / "V4",
}


class RejectsKnownBad(unittest.TestCase):
    def test_rejected(self):
        for name, folder in BAD.items():
            with self.subTest(name):
                if not (folder / "report.pdf").is_file():
                    self.skipTest(f"нет {folder}")
                r = check_report(folder / "report.docx", folder / "report.pdf")
                self.assertFalse(r["passed"], f"{name} не должна пройти")
                print(f"\n{name}: {len(r['errors'])} нарушений")
                for e in r["errors"]:
                    print("  -", e)


if __name__ == "__main__":
    unittest.main()
