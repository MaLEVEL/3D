import unittest
import sys
import os

# Ensure the parent directory is on the path so we can import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app


class GenerateCodeCombosTest(unittest.TestCase):
    def test_5_code_generates_30_combos(self):
        result = app.generate_code_combos("01234")
        self.assertEqual(30, len(result))
        group6 = [n for n in result if len(set(n)) == 3]
        group3 = [n for n in result if len(set(n)) == 2]
        self.assertEqual(10, len(group6))
        self.assertEqual(20, len(group3))

    def test_6_code_generates_50_combos(self):
        result = app.generate_code_combos("012345")
        self.assertEqual(50, len(result))
        group6 = [n for n in result if len(set(n)) == 3]
        group3 = [n for n in result if len(set(n)) == 2]
        self.assertEqual(20, len(group6))
        self.assertEqual(30, len(group3))

    def test_7_code_generates_77_combos(self):
        result = app.generate_code_combos("0123456")
        self.assertEqual(77, len(result))
        group6 = [n for n in result if len(set(n)) == 3]
        group3 = [n for n in result if len(set(n)) == 2]
        self.assertEqual(35, len(group6))
        self.assertEqual(42, len(group3))

    def test_all_combos_use_only_input_digits(self):
        result = app.generate_code_combos("147")
        allowed = set("147")
        for n in result:
            self.assertTrue(set(n).issubset(allowed))

    def test_no_duplicates_in_result(self):
        result = app.generate_code_combos("01234")
        self.assertEqual(len(result), len(set(result)))

    def test_invalid_input_too_short_raises(self):
        with self.assertRaises(ValueError):
            app.generate_code_combos("01")

    def test_duplicate_digits_raises(self):
        with self.assertRaises(ValueError):
            app.generate_code_combos("01123")


if __name__ == "__main__":
    unittest.main()
