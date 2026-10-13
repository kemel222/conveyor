"""Эталонный тест: расчёт обязан воспроизвести пример хрестоматии (п. 3.2).

Пример: СОБР-17-В, k = 1,28; H1 = 23 м; рядки по 2×3 оросителя, шаг 3 м, хвост 1,9 м;
распределительный 57х3,5 (Kт = 110), питающий кольцевой 159х4,0 (Kт = 36920);
участки 5–6 = 68,5 м (полукольцо) и 6–7 = 25 м; Hуу = 2,955 м; Z = 3 м.
Ответ хрестоматии: Q = 76,872 л/с; Нтр = 50,96 м.
"""
import math
import unittest

from tasks.water_sprinkler import hydraulics as h
from tasks.water_sprinkler import norms


class ReaderbookExample(unittest.TestCase):
    def setUp(self):
        self.net = h.network(k=1.28, h1=23.0, rows=2, per_side=3, spacing=3.0, tail=1.9, row_pitch=3.0,
                             dn_dist=50, dn_feed=150, ring=True,
                             extra=[("Питающий", 68.5, 0.5, 150), ("Питающий", 25.0, 1.0, 150)])

    def test_branch(self):
        b = self.net["first_branch"]
        for got, want in zip(b["flows"], [6.139, 6.274, 6.801]):
            self.assertAlmostEqual(got, want, delta=0.002)
        for got, want in zip(b["heads"], [23.0, 24.028, 28.23]):
            self.assertAlmostEqual(got, want, delta=0.002)
        self.assertAlmostEqual(b["head_junction"], 34.607, delta=0.003)

    def test_sections(self):
        losses = [s.loss for s in self.net["sections"]]
        for got, want in zip(losses, [1.028, 4.202, 6.377, 0.03, 2.741, 4.001]):
            self.assertAlmostEqual(got, want, delta=0.002)

    def test_rows_and_total(self):
        self.assertAlmostEqual(self.net["row_flows"][0], 38.428, delta=0.002)
        self.assertAlmostEqual(self.net["b_char"], 42.67, delta=0.005)
        self.assertAlmostEqual(self.net["row_flows"][1], 38.444, delta=0.003)
        self.assertAlmostEqual(self.net["total"], 76.872, delta=0.004)

    def test_required_head(self):
        head = h.required_head(23.0, self.net["sum_loss"], 2.955, 3.0)
        self.assertAlmostEqual(head["total"], 50.96, delta=50.96 * 0.002)


class Units(unittest.TestCase):
    def test_passport_k_matches_sp5_form(self):
        k = norms.SPRINKLERS["СВВ-12"]["K"]
        h_m = 20.0
        self.assertAlmostEqual(k * math.sqrt(h_m), 10 * k * math.sqrt(h_m / 100.0), places=9)

    def test_control_valve_formula(self):
        v = h.control_valve(100, 20.0)
        self.assertAlmostEqual(v["loss"], 2.01e-7 * 1000 * 72.0 ** 2, places=9)


class Design(unittest.TestCase):
    def _variant(self, **kw):
        base = dict(number=3, supported=True, sprinkler="СВВ-12", length=25.0, width=27.0, height=4.0,
                    room="Выставочный павильон", room_type="Выставочный павильон", storage_height=None)
        base.update(kw)
        return base

    def test_variant_3_satisfies_norms(self):
        d = h.design(self._variant())
        self.assertTrue(all(d["checks"].values()), d["checks"])
        self.assertGreaterEqual(d["total_flow"], d["params"]["flow"])
        self.assertGreaterEqual(d["zone"]["area"], d["params"]["area"])
        hd = d["head"]
        self.assertAlmostEqual(hd["total"], hd["h1"] + hd["sum_loss"] * 1.2 + hd["huu"] + hd["z"], places=9)
        last_branch_head = d["branch"]["heads"][-1]
        self.assertLess(hd["h1"], last_branch_head + 1e-9)

    def test_all_room_variants_solve(self):
        rows = [(1, "СВВ-10", 14, 29, 4, "Концертный зал"), (2, "СВН-12", 22, 25, 4, "Супермаркет"),
                (4, "СВН-12", 20, 25, 2.5, "Торговый зал"), (5, "СВВ-10", 18, 28, 2.5, "Спортивный зал"),
                (7, "СВН-10", 19, 25, 2.5, "Гостиница"), (11, "СВН-12", 14, 20, 2.5, "Деревообрабатывающее пр-во"),
                (14, "СВВ-12", 18, 26, 2.5, "Окрасочная камера"), (16, "СВН-12", 18, 30, 4, "Производство ваты")]
        for n, spr, a, b, hh, room in rows:
            with self.subTest(variant=n):
                d = h.design(self._variant(number=n, sprinkler=spr, length=a, width=b, height=hh, room=room, room_type=room))
                self.assertTrue(all(d["checks"].values()), d["checks"])


if __name__ == "__main__":
    unittest.main()
