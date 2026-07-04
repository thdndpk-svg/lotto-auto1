import sys
import unittest
from datetime import date, timedelta
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from lotto_auto import Draw, LottoAnalyzer, load_draws  # noqa: E402
from lotto_feedback import (  # noqa: E402
    build_feedback_event,
    default_feedback_memory,
    feedback_combo_points,
    feedback_number_scores,
    update_feedback_memory,
)


class LottoAutoTests(unittest.TestCase):
    def setUp(self):
        self.draws = load_draws(PROJECT_DIR / "data" / "lotto_sample.csv")
        self.analyzer = LottoAnalyzer(self.draws)

    def test_same_date_scores_find_month_day_matches(self):
        ranked, diagnostics = self.analyzer.number_scores(date(2026, 6, 18), window=20)
        self.assertGreaterEqual(len(diagnostics["same_date_matches"]), 3)
        self.assertEqual(len(ranked), 45)
        self.assertGreater(ranked[0].total, 0)

    def test_generate_combinations_returns_valid_ranked_combos(self):
        ranked, _ = self.analyzer.number_scores(date(2026, 6, 18), window=20)
        combos = self.analyzer.generate_combinations(
            ranked,
            target=date(2026, 6, 18),
            count=5,
            candidates=1500,
            seed=18,
        )
        self.assertEqual(len(combos), 5)
        for combo in combos:
            self.assertEqual(len(combo.numbers), 6)
            self.assertEqual(len(set(combo.numbers)), 6)
            self.assertTrue(all(1 <= n <= 45 for n in combo.numbers))
            self.assertGreaterEqual(combo.score, 0)
            self.assertLessEqual(combo.score, 100)

    def test_factor_selection_limits_number_score_details(self):
        ranked, diagnostics = self.analyzer.number_scores(
            date(2026, 6, 18),
            window=20,
            enabled_factors=["same_date", "skip"],
        )
        self.assertEqual(diagnostics["enabled_number_factors"], ("same_date", "skip"))
        self.assertEqual(set(ranked[0].factors), {"same_date", "skip"})

    def test_combo_factor_selection_limits_combo_score_details(self):
        ranked, _ = self.analyzer.number_scores(date(2026, 6, 18), window=20)
        combos = self.analyzer.generate_combinations(
            ranked,
            target=date(2026, 6, 18),
            count=2,
            candidates=500,
            seed=18,
            combo_factors=["number", "sum", "odd_even"],
        )
        self.assertEqual(set(combos[0].parts), {"number", "sum", "odd_even"})

    def test_knowledge_net_factor_adds_number_and_combo_scores(self):
        ranked, diagnostics = self.analyzer.number_scores(
            date(2026, 6, 18),
            window=20,
            enabled_factors=["knowledge"],
        )
        self.assertEqual(diagnostics["enabled_number_factors"], ("knowledge",))
        self.assertIn("knowledge", ranked[0].factors)
        self.assertIn("knowledge_insights", diagnostics)

        combos = self.analyzer.generate_combinations(
            ranked,
            target=date(2026, 6, 18),
            count=2,
            candidates=500,
            seed=18,
            combo_factors=["knowledge_net"],
        )
        self.assertEqual(set(combos[0].parts), {"knowledge_net"})
        self.assertGreaterEqual(combos[0].parts["knowledge_net"], 0)

    def test_feedback_memory_records_failure_and_adjusts_scores(self):
        recommendations = {
            "generated_at": "2026-06-18T12:00:00",
            "target_date": "2026-06-18",
            "latest_draw_no_at_analysis": 10,
            "combos": [
                {
                    "rank": 1,
                    "numbers": [1, 2, 3, 4, 5, 6],
                    "score": 90,
                    "parts": {"number": 40, "sum": 8, "odd_even": 7, "feedback": 0},
                },
                {
                    "rank": 2,
                    "numbers": [7, 8, 9, 10, 11, 12],
                    "score": 80,
                    "parts": {"number": 35, "sum": 6, "odd_even": 5, "feedback": 0},
                },
            ],
        }
        draw = Draw(
            draw_no=11,
            draw_date=date(2026, 6, 21),
            numbers=(1, 8, 20, 27, 34, 45),
            bonus=12,
        )
        event = build_feedback_event(recommendations, draw)
        memory = update_feedback_memory(default_feedback_memory(), event)
        self.assertEqual(memory["observation_count"], 1)
        self.assertIn("1", memory["number_bias"])
        self.assertIn("feedback", memory["factor_bias"])

        number_scores = feedback_number_scores([1, 2, 20], memory)
        self.assertGreater(number_scores[1], number_scores[2])
        self.assertGreater(feedback_combo_points([1, 8, 20, 27, 34, 45], memory), 0)

    def test_ticket_grid_coordinates_use_real_lotto_paper_layout(self):
        self.assertEqual(self.analyzer.coord(1), (0, 0))
        self.assertEqual(self.analyzer.coord(7), (6, 0))
        self.assertEqual(self.analyzer.coord(8), (0, 1))
        self.assertEqual(self.analyzer.coord(42), (6, 5))
        self.assertEqual(self.analyzer.coord(43), (0, 6))
        self.assertEqual(self.analyzer.coord(45), (2, 6))

    def test_front_cycle_candidates_and_anchor_combos(self):
        candidates = self.analyzer.front_cycle_candidates(limit=3)
        self.assertGreaterEqual(len(candidates), 1)
        anchor = candidates[0].number
        ranked, _ = self.analyzer.number_scores(date(2026, 6, 18), window=20)
        combos = self.analyzer.generate_combinations(
            ranked,
            target=date(2026, 6, 18),
            count=3,
            candidates=500,
            seed=18,
            front_anchor=anchor,
        )
        self.assertTrue(all(anchor in combo.numbers for combo in combos))
        self.assertTrue(all(combo.numbers[0] == anchor for combo in combos))

    def test_front_sequence_pattern_predicts_next_anchor(self):
        first_numbers = [1, 2, 3, 6, 8, 1, 2, 3, 6, 10, 1, 2, 3]
        base = date(2026, 1, 3)
        draws = [
            Draw(
                draw_no=i + 1,
                draw_date=base + timedelta(days=i * 7),
                numbers=tuple(sorted([first, 22, 28, 34, 40, 45])),
                bonus=7,
            )
            for i, first in enumerate(first_numbers)
        ]
        analyzer = LottoAnalyzer(draws)
        candidate = analyzer.front_sequence_anchor_candidate()
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.number, 6)
        self.assertEqual(candidate.pattern, (1, 2, 3))
        self.assertEqual(candidate.hit_count, 2)


if __name__ == "__main__":
    unittest.main()
