import unittest

import app


class AdvancedFilterTest(unittest.TestCase):
    def test_advanced_condition_values(self):
        self.assertEqual("6", app.advanced_condition_value("123", "sum"))
        self.assertEqual("6", app.advanced_condition_value("123", "sum_tail"))
        self.assertEqual("2", app.advanced_condition_value("123", "span"))
        self.assertEqual("2:1", app.advanced_condition_value("123", "odd_even"))

    def test_condition_miss_range(self):
        advanced = app.normalize_advanced_filter({
            "advanced_filter": {
                "conditions": [
                    {"type": "sum", "values": ["6"]},
                    {"type": "span", "values": ["2"]},
                    {"type": "odd_even", "values": ["1:2"]},
                ],
                "miss_min": 1,
                "miss_max": 1,
            }
        })
        self.assertTrue(app.passes_advanced_filter("123", advanced))
        self.assertFalse(app.passes_advanced_filter("114", advanced))

    def test_invalid_miss_range_rejected(self):
        with self.assertRaises(ValueError):
            app.normalize_advanced_filter({
                "advanced_filter": {
                    "conditions": [{"type": "sum", "values": ["6"]}],
                    "miss_min": 2,
                    "miss_max": 1,
                }
            })

    def test_ratio_values_must_total_three(self):
        with self.assertRaises(ValueError):
            app.normalize_advanced_filter({
                "advanced_filter": {
                    "conditions": [{"type": "big_small", "values": ["2:2"]}],
                }
            })


if __name__ == "__main__":
    unittest.main()
