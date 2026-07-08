import unittest

from bikescraper.matcher import evaluate_size, extract_size, normalize_config_size


class TestSizeExtraction(unittest.TestCase):
    def test_detects_standalone_medium_large_xl_letters(self):
        self.assertEqual(extract_size(None, "Nice bike, size M, low miles"), "M")
        self.assertEqual(extract_size(None, "Frame is L, rides great"), "L")
        self.assertEqual(extract_size(None, "XL frame, tall rider"), "XL")

    def test_detects_spelled_out_words_case_insensitively(self):
        self.assertEqual(extract_size(None, "This is a medium frame"), "M")
        self.assertEqual(extract_size(None, "This is a Large frame"), "L")
        self.assertEqual(extract_size(None, "MEDIUM size, great condition"), "M")

    def test_detects_extra_large_variants(self):
        self.assertEqual(extract_size(None, "X-Large frame, fits tall riders"), "XL")
        self.assertEqual(extract_size(None, "XLarge frame"), "XL")
        self.assertEqual(extract_size(None, "Extra Large frame"), "XL")
        self.assertEqual(extract_size(None, "extra-large frame"), "XL")

    def test_lowercase_standalone_letters_not_treated_as_size(self):
        # "m"/"l" alone are common words/abbreviations elsewhere in a
        # description -- only the spelled-out or uppercase forms count.
        self.assertIsNone(extract_size(None, "this bike has a m ok drivetrain"))
        self.assertIsNone(extract_size(None, "runs at l rpm smoothly"))

    def test_structured_frame_size_field(self):
        self.assertEqual(extract_size("Medium", ""), "M")
        self.assertEqual(extract_size("L", ""), "L")


class TestNormalizeConfigSize(unittest.TestCase):
    def test_lowercase_letters_normalize_to_uppercase(self):
        self.assertEqual(normalize_config_size("s"), "S")
        self.assertEqual(normalize_config_size("m"), "M")
        self.assertEqual(normalize_config_size("l"), "L")
        self.assertEqual(normalize_config_size("xl"), "XL")

    def test_numeric_sizes_unaffected(self):
        self.assertEqual(normalize_config_size("52"), "52")
        self.assertEqual(normalize_config_size("54"), "54")

    def test_evaluate_size_matches_regardless_of_config_casing(self):
        allowed_sizes = {normalize_config_size(s) for s in ["s", "m", "52"]}
        detected, in_target = evaluate_size(None, "Great Medium size bike", allowed_sizes)
        self.assertEqual(detected, "M")
        self.assertTrue(in_target)


if __name__ == "__main__":
    unittest.main()
