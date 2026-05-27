import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app


class BasePoolGenerationTest(unittest.TestCase):
    def test_full_pool_has_1000_direct_numbers(self):
        pool = app.generate_base_pool("full")
        self.assertEqual(1000, len(pool))
        self.assertEqual("000", pool[0])
        self.assertEqual("999", pool[-1])

    def test_group_pools_use_deduplicated_representatives_without_baozi(self):
        self.assertEqual(210, len(app.generate_base_pool("group")))
        self.assertNotIn("000", app.generate_base_pool("group"))
        self.assertEqual(90, len(app.generate_base_pool("group3")))
        self.assertEqual(120, len(app.generate_base_pool("group6")))
        self.assertEqual(10, len(app.generate_base_pool("baozi")))


class PositionFilterTest(unittest.TestCase):
    def test_position_include_and_exclude(self):
        position_filter = app.normalize_position_filter({
            "position_filter": {
                "include": ["12", "", "9"],
                "exclude": ["", "0", ""],
            }
        })
        self.assertTrue(app.passes_position_filter("129", position_filter))
        self.assertFalse(app.passes_position_filter("109", position_filter))
        self.assertFalse(app.passes_position_filter("329", position_filter))
        self.assertFalse(app.passes_position_filter("128", position_filter))

    def test_position_include_exclude_conflict_rejected(self):
        with self.assertRaises(ValueError):
            app.normalize_position_filter({
                "position_filter": {
                    "include": ["1", "", ""],
                    "exclude": ["1", "", ""],
                }
            })


class PairFilterTest(unittest.TestCase):
    def test_pair_sum_pair_tail_and_pair_diff_any_hit(self):
        pair_sum_filter = app.normalize_pair_filter({"pair_filter": {"pair_sums": [5]}})
        pair_tail_filter = app.normalize_pair_filter({"pair_filter": {"pair_sum_tails": [0]}})
        pair_diff_filter = app.normalize_pair_filter({"pair_filter": {"pair_diffs": [7]}})

        self.assertTrue(app.passes_pair_filter("123", pair_sum_filter))
        self.assertTrue(app.passes_pair_filter("019", pair_tail_filter))
        self.assertTrue(app.passes_pair_filter("178", pair_diff_filter))
        self.assertFalse(app.passes_pair_filter("123", pair_diff_filter))

    def test_pair_filter_exclude_mode(self):
        pair_filter = app.normalize_pair_filter({"pair_filter": {"pair_sums": [5], "mode": "exclude"}})
        self.assertFalse(app.passes_pair_filter("123", pair_filter))
        self.assertTrue(app.passes_pair_filter("111", pair_filter))


class ShapeFilterTest(unittest.TestCase):
    def test_basic_shape_types(self):
        group6 = app.normalize_shape_filter({"shape_filter": {"types": ["group6"]}})
        pair = app.normalize_shape_filter({"shape_filter": {"types": ["pair"]}})
        baozi = app.normalize_shape_filter({"shape_filter": {"types": ["baozi"]}})

        self.assertTrue(app.passes_shape_filter("123", group6))
        self.assertTrue(app.passes_shape_filter("112", pair))
        self.assertTrue(app.passes_shape_filter("777", baozi))
        self.assertFalse(app.passes_shape_filter("777", group6))

    def test_consecutive_and_semi_consecutive(self):
        consecutive = app.normalize_shape_filter({"shape_filter": {"types": ["consecutive"]}})
        semi = app.normalize_shape_filter({"shape_filter": {"types": ["semi_consecutive"]}})

        self.assertTrue(app.passes_shape_filter("012", consecutive))
        self.assertTrue(app.passes_shape_filter("789", consecutive))
        self.assertFalse(app.passes_shape_filter("019", consecutive))
        self.assertTrue(app.passes_shape_filter("124", semi))
        self.assertFalse(app.passes_shape_filter("123", semi))

    def test_prime_composite_count(self):
        shape_filter = app.normalize_shape_filter({
            "shape_filter": {"types": ["prime_composite"], "prime_count": [2]}
        })
        self.assertTrue(app.passes_shape_filter("239", shape_filter))
        self.assertTrue(app.passes_shape_filter("125", shape_filter))
        self.assertFalse(app.passes_shape_filter("149", shape_filter))


class RuleFilterTest(unittest.TestCase):
    def test_rule_filters_support_caibao_style_patterns(self):
        filters = app.normalize_rule_filters({
            "rule_filters": [
                {"type": "sum", "values": [12]},
                {"type": "mod012", "values": ["012"]},
                {"type": "odd_even", "values": ["OEO"]},
            ]
        })
        self.assertTrue(app.passes_rule_filters("345", filters))
        self.assertFalse(app.passes_rule_filters("124", filters))

    def test_rule_filter_pair_code_and_pair_sum_diff(self):
        filters = app.normalize_rule_filters({
            "rule_filters": [
                {"type": "pair_code", "values": ["12"]},
                {"type": "pair_sum_diff", "values": ["0", "2"]},
            ]
        })
        self.assertTrue(app.passes_rule_filters("123", filters))
        self.assertFalse(app.passes_rule_filters("456", filters))

    def test_rule_filter_exclude_mode(self):
        filters = app.normalize_rule_filters({
            "rule_filters": [{"type": "big_small", "mode": "exclude", "values": ["SSS"]}]
        })
        self.assertFalse(app.passes_rule_filters("123", filters))
        self.assertTrue(app.passes_rule_filters("568", filters))

    def test_prime_composite_does_not_treat_one_as_prime(self):
        self.assertEqual({"CCC"}, app.rule_filter_values("111", "prime_composite"))
        self.assertEqual({"PPP"}, app.rule_filter_values("235", "prime_composite"))

    def test_average_and_ac_rule_filters(self):
        filters = app.normalize_rule_filters({
            "rule_filters": [
                {"type": "average", "values": ["4"]},
                {"type": "ac", "values": ["3"]},
                {"type": "first_last_diff", "values": ["7"]},
            ]
        })
        self.assertTrue(app.passes_rule_filters("148", filters))
        self.assertFalse(app.passes_rule_filters("123", filters))
        self.assertEqual({"4"}, app.rule_filter_values("148", "average"))
        self.assertEqual({"3"}, app.rule_filter_values("148", "ac"))

    def test_group_stat_pattern_filters_ignore_position_order(self):
        filters = app.normalize_rule_filters({
            "rule_filters": [
                {"type": "odd_even_count", "values": ["2:1"]},
                {"type": "big_small_count", "values": ["0:3"]},
                {"type": "prime_composite_count", "values": ["2:1"]},
                {"type": "mod012_count", "values": ["1:1:1"]},
            ]
        })

        self.assertTrue(app.passes_rule_filters("123", filters))
        self.assertTrue(app.passes_rule_filters("321", filters))
        self.assertFalse(app.passes_rule_filters("456", filters))

    def test_group_stat_pattern_values(self):
        self.assertEqual({"2:1"}, app.rule_filter_values("123", "odd_even_count"))
        self.assertEqual({"0:3"}, app.rule_filter_values("123", "big_small_count"))
        self.assertEqual({"2:1"}, app.rule_filter_values("123", "prime_composite_count"))
        self.assertEqual({"1:1:1"}, app.rule_filter_values("123", "mod012_count"))


class SegmentPatternExpansionTest(unittest.TestCase):
    def test_334_segment_pattern_is_supported(self):
        filters = app.normalize_segment_filters({
            "segment_filters": [
                {"mode": "3-3-4", "groups": ["012", "345", "6789"]}
            ]
        })
        self.assertEqual("3-3-4", filters[0]["mode"])
        self.assertEqual(["012", "345", "6789"], filters[0]["groups_data"])

    def test_segment_filters_are_strict_by_default(self):
        filters = app.normalize_segment_filters({
            "segment_filters": [
                {"mode": "2-3-5", "groups": ["14", "023", "56789"]},
                {"mode": "3-3-4", "groups": ["012", "345", "6789"]},
            ]
        })

        self.assertFalse(app.passes_segment_filters("147", filters))

    def test_segment_filters_allow_configured_tolerance(self):
        filters = app.normalize_segment_filters({
            "segment_filters": [
                {"mode": "2-3-5", "groups": ["14", "023", "56789"]},
                {"mode": "3-3-4", "groups": ["012", "345", "6789"]},
            ]
        })

        self.assertTrue(app.passes_segment_filters("147", filters, tolerance=1))

    def test_segment_tolerance_is_clamped(self):
        self.assertEqual(0, app.normalize_segment_tolerance({"segment_tolerance": -1}))
        self.assertEqual(2, app.normalize_segment_tolerance({"segment_tolerance": 9}))


class CodeFilterExpansionTest(unittest.TestCase):
    def test_code_filter_supports_23_condition(self):
        code_filter = app.validate_code_filter({
            "code_len": 5,
            "condition": "23",
            "digits": "01234",
        })

        self.assertTrue(app.passes_code_filter("124", code_filter))
        self.assertFalse(app.passes_code_filter("567", code_filter))

    def test_code_filter_defaults_to_unique_digit_count(self):
        code_filter = app.validate_code_filter({
            "code_len": 3,
            "condition": "012",
            "digits": "123",
        })

        self.assertFalse(code_filter["count_repeat"])
        self.assertTrue(app.passes_code_filter("112", code_filter))

    def test_code_filter_can_count_repeated_digits(self):
        code_filter = app.validate_code_filter({
            "code_len": 3,
            "condition": "012",
            "digits": "123",
            "count_repeat": True,
        })

        self.assertTrue(code_filter["count_repeat"])
        self.assertFalse(app.passes_code_filter("112", code_filter))


class HistoryHitModeTest(unittest.TestCase):
    def test_direct_history_requires_exact_order(self):
        item = {"base_mode": "direct", "filtered": ["123"]}
        self.assertTrue(app.history_item_hit(item, "123"))
        self.assertFalse(app.history_item_hit(item, "321"))

    def test_group_history_uses_group_match(self):
        item = {"base_mode": "group", "filtered": ["123"]}
        self.assertTrue(app.history_item_hit(item, "321"))


if __name__ == "__main__":
    unittest.main()
