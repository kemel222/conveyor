"""Офлайн-тест проверки чисел в тексте Sol. Вызова модели не делает."""
import unittest

from tasks.water_sprinkler import check_prose, hydraulics, report


def _design():
    v = dict(number=3, supported=True, sprinkler="СВВ-12", length=25.0, width=27.0, height=4.0,
             room="Выставочный павильон", room_type="Выставочный павильон", storage_height=None)
    return hydraulics.design(v)


class Numbers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = _design()

    def _errs(self, text):
        answer = {"annotation": [text]}
        out = check_prose.check_sections(answer, self.d, report.BIBLIOGRAPHY, keys=["annotation"])
        return " ".join(out.get("annotation", []))

    def test_area_written_with_comma_zero_is_accepted(self):
        self.assertNotIn("675", self._errs("Площадь помещения составляет 675 м2."))

    def test_metres_converted_to_mm_is_accepted(self):
        self.assertNotIn("2700", self._errs("Шаг рядков составляет 2700 мм."))

    def test_foreign_number_is_still_rejected(self):
        self.assertIn("987", self._errs("Расход составляет 987 л/с."))


if __name__ == "__main__":
    unittest.main()
