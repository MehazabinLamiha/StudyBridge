import unittest
from datetime import date
from decimal import Decimal as D

from studybridge import credit, fx, remittance, tuition
from studybridge.money import mid_rate, norm_ccy


class TestMoney(unittest.TestCase):
    def test_aliases(self):
        self.assertEqual(norm_ccy("rmb"), "CNY")
        self.assertEqual(norm_ccy("Taka"), "BDT")
        with self.assertRaises(ValueError):
            norm_ccy("XYZ")

    def test_cross_rate(self):
        self.assertAlmostEqual(float(mid_rate("BDT", "CNY") * mid_rate("CNY", "BDT")), 1.0, places=12)


class TestFx(unittest.TestCase):
    def test_spread_applied(self):
        qt = fx.quote(10000, "BDT", "CNY")
        self.assertLess(qt["applied_rate"], qt["mid_rate"])
        self.assertEqual(qt["you_get"], D("573.11"))

    def test_rejects_non_positive(self):
        with self.assertRaises(ValueError):
            fx.quote(0, "BDT", "CNY")


class TestRemittance(unittest.TestCase):
    def test_ranked_by_recipient_amount(self):
        res = remittance.compare(50000, "BDT", "CNY")
        eligible = [o["recipient_gets"] for o in res["options"] if o["eligible"]]
        self.assertEqual(eligible, sorted(eligible, reverse=True))
        self.assertEqual(res["best"]["provider_id"], "digital_a")

    def test_deadline_filters_slow_provider(self):
        res = remittance.compare(50000, "BDT", "CNY", deadline_days=1)
        swift = next(o for o in res["options"] if o["provider_id"] == "bank_swift")
        self.assertFalse(swift["eligible"])

    def test_corridor_and_max_limits(self):
        res = remittance.compare(200000, "BDT", "EUR")
        wallet_c = next(o for o in res["options"] if o["provider_id"] == "wallet_c")
        self.assertIn("corridor BDT->EUR not supported", wallet_c["reasons"])
        self.assertIn("above provider maximum", wallet_c["reasons"])

    def test_inverse_is_exact(self):
        p = remittance.provider_by_id("digital_a")
        need = remittance.source_needed(p, 5700, "BDT", "CNY")
        got = remittance.evaluate(p, need, "BDT", "CNY")["recipient_gets"]
        self.assertEqual(got, D("5700.00"))


class TestTuition(unittest.TestCase):
    BAL = {"BDT": D("520000"), "CNY": D("3200")}

    def test_on_track_four_tranches(self):
        res = tuition.plan(26000, "CNY", date(2026, 11, 15), date(2026, 10, 13), self.BAL)
        self.assertEqual(res["status"], "ON_TRACK")
        self.assertEqual(len(res["tranches"]), 4)
        self.assertEqual(sum(t["recipient_gets"] for t in res["tranches"]), D("22800.00"))

    def test_funding_gap(self):
        res = tuition.plan(26000, "CNY", date(2026, 11, 15), date(2026, 10, 13), {"BDT": D("100000"), "CNY": D(0)})
        self.assertEqual(res["status"], "FUNDING_GAP")
        self.assertGreater(res["funding_gap"], 0)

    def test_urgent_and_overdue(self):
        urgent = tuition.plan(26000, "CNY", date(2026, 10, 14), date(2026, 10, 13), self.BAL)
        self.assertEqual(urgent["status"], "URGENT")
        overdue = tuition.plan(26000, "CNY", date(2026, 10, 1), date(2026, 10, 13), self.BAL)
        self.assertEqual(overdue["status"], "OVERDUE")

    def test_covered(self):
        res = tuition.plan(1000, "CNY", date(2026, 11, 15), date(2026, 10, 13), self.BAL)
        self.assertEqual(res["status"], "COVERED")


class TestCredit(unittest.TestCase):
    def test_thin_file(self):
        res = credit.assess({"months_in_country": 1})
        self.assertEqual(res["stage"], "THIN_FILE")
        self.assertTrue(any("bank account" in a for a in res["actions"]))

    def test_high_utilisation_flagged(self):
        res = credit.assess({"months_in_country": 24, "has_local_bank_account": True, "has_credit_card": True,
                             "card_limit": 1000, "card_balance": 600, "on_time_payments_12m": 12})
        self.assertEqual(res["utilisation_pct"], D("60.00"))
        self.assertTrue(any("below 30%" in a for a in res["actions"]))

    def test_established(self):
        res = credit.assess({"months_in_country": 24, "has_local_bank_account": True, "has_credit_card": True,
                             "has_phone_contract": True, "card_limit": 1000, "card_balance": 50,
                             "on_time_payments_12m": 12})
        self.assertEqual(res["stage"], "ESTABLISHED")


if __name__ == "__main__":
    unittest.main()
