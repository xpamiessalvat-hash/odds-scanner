import unittest

from bet365_ah1_validator import extract_ah1_quotes


class AH1ParserTests(unittest.TestCase):
    def test_parses_explicit_home_and_away_quotes(self):
        text = """
        FC Example
        Away United
        Asian Handicap
        FC Example -1
        1.91
        Away United +1
        1.95
        """
        result = extract_ah1_quotes(text, "FC Example", "Away United")
        self.assertTrue(result["ok"])
        self.assertEqual(result["home_odd"], 1.91)
        self.assertEqual(result["away_odd"], 1.95)

    def test_rejects_ambiguous_or_missing_selection(self):
        text = """
        FC Example
        Away United
        Handicap
        FC Example -1
        1.91
        1.87
        Away United +1
        1.95
        """
        result = extract_ah1_quotes(text, "FC Example", "Away United")
        self.assertFalse(result["ok"])

    def test_rejects_match_without_handicap_heading(self):
        text = """
        FC Example
        Away United
        Match Result
        FC Example
        1.70
        Away United
        2.10
        """
        result = extract_ah1_quotes(text, "FC Example", "Away United")
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
