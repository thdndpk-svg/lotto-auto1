#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from itertools import combinations
from pathlib import Path
from statistics import mean, pstdev
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


LOTTO_MIN = 1
LOTTO_MAX = 45
PICK_COUNT = 6

NUMBER_FACTOR_LABELS = {
    "same_date": "같은날짜",
    "skip": "건너뛰기",
    "front": "앞번호",
    "recent": "최근흐름",
    "overdue": "미출현",
    "frequency": "전체빈도",
    "shape": "선패턴",
    "ending": "끝수",
}

COMBO_FACTOR_LABELS = {
    "number": "번호점수",
    "line_shape": "선모양",
    "front": "첫번호",
    "sum": "번호합",
    "odd_even": "홀짝",
    "low_high": "고저",
    "ending": "끝수",
    "consecutive": "연속수",
    "pair": "동반출현",
    "recent_hot": "최근상위",
    "history_penalty": "과거중복감점",
}

DEFAULT_NUMBER_FACTORS = tuple(NUMBER_FACTOR_LABELS.keys())
DEFAULT_COMBO_FACTORS = tuple(COMBO_FACTOR_LABELS.keys())

COMBO_FACTOR_MAX_POINTS = {
    "number": 45.0,
    "line_shape": 12.0,
    "front": 8.0,
    "sum": 10.0,
    "odd_even": 7.0,
    "low_high": 5.0,
    "ending": 5.0,
    "consecutive": 4.0,
    "pair": 4.0,
    "recent_hot": 3.0,
}


@dataclass(frozen=True)
class Draw:
    draw_no: int
    draw_date: date
    numbers: Tuple[int, ...]
    bonus: Optional[int] = None

    @property
    def first_number(self) -> int:
        return self.numbers[0]

    @property
    def total(self) -> int:
        return sum(self.numbers)


@dataclass
class NumberScore:
    number: int
    total: float
    factors: Dict[str, float]


@dataclass
class ComboScore:
    numbers: Tuple[int, ...]
    score: float
    parts: Dict[str, float]


@dataclass
class FrontCycleCandidate:
    kind: str
    number: int
    score: float
    exact: bool
    current_gap: int
    expected_gap: int
    repeat_count: int
    last_draw_no: int
    intervals: Tuple[int, ...]
    reason: str


@dataclass
class FrontSequenceCandidate:
    kind: str
    number: int
    score: float
    pattern: Tuple[int, ...]
    pattern_length: int
    support: int
    hit_count: int
    confidence: float
    example_draws: Tuple[int, ...]
    reason: str


HEADER_ALIASES = {
    "draw_no": ["draw_no", "round", "no", "회차", "추첨회차"],
    "date": ["date", "draw_date", "추첨일", "날짜"],
    "n1": ["n1", "num1", "number1", "번호1", "당첨번호1"],
    "n2": ["n2", "num2", "number2", "번호2", "당첨번호2"],
    "n3": ["n3", "num3", "number3", "번호3", "당첨번호3"],
    "n4": ["n4", "num4", "number4", "번호4", "당첨번호4"],
    "n5": ["n5", "num5", "number5", "번호5", "당첨번호5"],
    "n6": ["n6", "num6", "number6", "번호6", "당첨번호6"],
    "bonus": ["bonus", "bonus_no", "보너스", "보너스번호"],
}


def parse_date(value: str) -> date:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Unsupported date format: {value!r}")


def infer_headers(headers: Sequence[str]) -> Dict[str, str]:
    normalized = {h.strip().lower(): h for h in headers}
    result: Dict[str, str] = {}
    for canonical, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if alias.lower() in normalized:
                result[canonical] = normalized[alias.lower()]
                break
    missing = [k for k in ["draw_no", "date", "n1", "n2", "n3", "n4", "n5", "n6"] if k not in result]
    if missing:
        raise ValueError(
            "CSV header is missing required columns: "
            + ", ".join(missing)
            + "\nSupported example: draw_no,date,n1,n2,n3,n4,n5,n6,bonus"
        )
    return result


def load_draws(path: Path) -> List[Draw]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV file has no header row.")
        mapping = infer_headers(reader.fieldnames)
        draws: List[Draw] = []
        for row in reader:
            if not row or not row.get(mapping["draw_no"], "").strip():
                continue
            nums = tuple(sorted(int(row[mapping[f"n{i}"]]) for i in range(1, 7)))
            validate_numbers(nums)
            bonus = None
            if "bonus" in mapping and row.get(mapping["bonus"], "").strip():
                bonus = int(row[mapping["bonus"]])
            draws.append(
                Draw(
                    draw_no=int(row[mapping["draw_no"]]),
                    draw_date=parse_date(row[mapping["date"]]),
                    numbers=nums,
                    bonus=bonus,
                )
            )
    if len(draws) < 10:
        raise ValueError("At least 10 draw rows are recommended for analysis.")
    return sorted(draws, key=lambda d: (d.draw_no, d.draw_date))


def validate_numbers(numbers: Sequence[int]) -> None:
    if len(numbers) != PICK_COUNT:
        raise ValueError(f"Expected {PICK_COUNT} numbers, got {numbers}")
    if len(set(numbers)) != PICK_COUNT:
        raise ValueError(f"Duplicate numbers are not allowed: {numbers}")
    bad = [n for n in numbers if n < LOTTO_MIN or n > LOTTO_MAX]
    if bad:
        raise ValueError(f"Numbers out of range 1-45: {bad}")


def safe_ratio(value: float, high: float) -> float:
    if high <= 0:
        return 0.0
    return max(0.0, min(1.0, value / high))


def bucket_score(value: float, target: float, tolerance: float) -> float:
    if tolerance <= 0:
        return 0.0
    return max(0.0, 1.0 - abs(value - target) / tolerance)


class LottoAnalyzer:
    def __init__(self, draws: Sequence[Draw], grid_cols: int = 7):
        self.draws = list(draws)
        self.grid_cols = grid_cols
        self.all_numbers = list(range(LOTTO_MIN, LOTTO_MAX + 1))
        self.frequency = Counter(n for d in self.draws for n in d.numbers)

    def recent_draws(self, window: int) -> List[Draw]:
        return self.draws[-max(1, window) :]

    def same_date_scores(self, target: date) -> Tuple[Dict[int, float], List[Draw]]:
        matches = [
            d
            for d in self.draws
            if d.draw_date.month == target.month and d.draw_date.day == target.day
        ]
        counts = Counter(n for d in matches for n in d.numbers)
        high = max(counts.values(), default=0)
        return {n: 100.0 * safe_ratio(counts[n], high) for n in self.all_numbers}, matches

    def frequency_scores(self) -> Dict[int, float]:
        high = max(self.frequency.values(), default=0)
        return {n: 100.0 * safe_ratio(self.frequency[n], high) for n in self.all_numbers}

    def recent_scores(self, window: int) -> Dict[int, float]:
        counts = Counter(n for d in self.recent_draws(window) for n in d.numbers)
        high = max(counts.values(), default=0)
        return {n: 100.0 * safe_ratio(counts[n], high) for n in self.all_numbers}

    def overdue_scores(self) -> Dict[int, float]:
        scores: Dict[int, float] = {}
        for n in self.all_numbers:
            seen_indexes = [i for i, d in enumerate(self.draws) if n in d.numbers]
            if not seen_indexes:
                scores[n] = 0.0
                continue
            current_gap = len(self.draws) - 1 - seen_indexes[-1]
            intervals = [
                seen_indexes[i] - seen_indexes[i - 1]
                for i in range(1, len(seen_indexes))
            ]
            avg_gap = mean(intervals) if intervals else max(1, len(self.draws) / 7)
            scores[n] = 100.0 * safe_ratio(current_gap, avg_gap * 1.5)
        return scores

    def ending_scores(self, window: int) -> Dict[int, float]:
        recent = self.recent_draws(window)
        ending_counts = Counter(n % 10 for d in recent for n in d.numbers)
        high = max(ending_counts.values(), default=0)
        return {
            n: 100.0 * safe_ratio(ending_counts[n % 10], high)
            for n in self.all_numbers
        }

    def skip_scores(self, window: int = 20, max_gap: int = 5) -> Dict[int, float]:
        recent = self.recent_draws(window + max_gap)
        rates: Dict[int, Dict[int, float]] = defaultdict(dict)
        global_rates: Dict[int, float] = {}

        for gap in range(1, max_gap + 1):
            source_count = Counter()
            repeat_count = Counter()
            global_sources = 0
            global_repeats = 0
            for i in range(gap, len(recent)):
                source = set(recent[i - gap].numbers)
                target = set(recent[i].numbers)
                overlap = source & target
                for n in source:
                    source_count[n] += 1
                    global_sources += 1
                for n in overlap:
                    repeat_count[n] += 1
                    global_repeats += 1
            global_rates[gap] = global_repeats / global_sources if global_sources else 0.0
            for n in self.all_numbers:
                if source_count[n]:
                    rates[gap][n] = repeat_count[n] / source_count[n]
                else:
                    rates[gap][n] = global_rates[gap]

        scores = {n: 0.0 for n in self.all_numbers}
        gap_weights = {1: 0.85, 2: 1.35, 3: 0.85, 4: 0.55, 5: 0.40}
        for gap in range(1, max_gap + 1):
            if len(self.draws) < gap:
                continue
            source_draw = self.draws[-gap]
            for n in source_draw.numbers:
                scores[n] += 100.0 * rates[gap].get(n, global_rates[gap]) * gap_weights.get(gap, 0.3)

        high = max(scores.values(), default=0)
        return {n: 100.0 * safe_ratio(scores[n], high) for n in self.all_numbers}

    def front_number_scores(self) -> Dict[int, float]:
        firsts = [d.first_number for d in self.draws]
        counts = Counter(firsts)
        high_count = max(counts.values(), default=0)
        scores = {n: 0.0 for n in self.all_numbers}

        for n in range(LOTTO_MIN, LOTTO_MAX - PICK_COUNT + 2):
            indexes = [i for i, value in enumerate(firsts) if value == n]
            freq_part = 45.0 * safe_ratio(counts[n], high_count)
            if not indexes:
                scores[n] = freq_part
                continue
            current_gap = len(firsts) - 1 - indexes[-1]
            intervals = [indexes[i] - indexes[i - 1] for i in range(1, len(indexes))]
            avg_gap = mean(intervals) if intervals else max(1, len(firsts) / max(1, counts[n]))
            due_part = 55.0 * safe_ratio(current_gap, avg_gap * 1.4)
            scores[n] = freq_part + due_part
        return scores

    def front_cycle_candidates(self, limit: int = 6) -> List[FrontCycleCandidate]:
        firsts = [d.first_number for d in self.draws]
        candidates: List[FrontCycleCandidate] = []
        for n in range(LOTTO_MIN, LOTTO_MAX - PICK_COUNT + 2):
            indexes = [i for i, value in enumerate(firsts) if value == n]
            if len(indexes) < 3:
                continue
            intervals = tuple(indexes[i] - indexes[i - 1] for i in range(1, len(indexes)))
            interval_counts = Counter(intervals)
            current_gap = len(firsts) - indexes[-1]
            expected_gap, repeat_count = interval_counts.most_common(1)[0]
            exact_repeat = interval_counts[current_gap]
            exact = exact_repeat > 0

            recent_intervals = intervals[-5:]
            avg_gap = mean(intervals)
            gap_fit = bucket_score(current_gap, expected_gap, max(2.0, expected_gap * 0.35))
            avg_fit = bucket_score(current_gap, avg_gap, max(2.0, avg_gap * 0.35))
            repeat_strength = safe_ratio(repeat_count, 12.0)
            exact_strength = safe_ratio(exact_repeat, 4.0)
            exact_bonus = (0.18 + 0.18 * exact_strength) if exact else 0.0
            score = 100.0 * min(1.0, exact_bonus + gap_fit * 0.38 + avg_fit * 0.17 + repeat_strength * 0.10)

            if exact:
                reason = f"{current_gap}회 간격이 과거 {exact_repeat}번 반복됨"
                repeat_count = exact_repeat
                expected_gap = current_gap
            else:
                reason = f"대표 간격 {expected_gap}회, 현재 {current_gap}회 경과"

            candidates.append(
                FrontCycleCandidate(
                    kind="cycle",
                    number=n,
                    score=round(score, 2),
                    exact=exact,
                    current_gap=current_gap,
                    expected_gap=expected_gap,
                    repeat_count=repeat_count,
                    last_draw_no=self.draws[indexes[-1]].draw_no,
                    intervals=recent_intervals,
                    reason=reason,
                )
            )

        candidates.sort(key=lambda item: (not item.exact, -item.score, item.number))
        return candidates[:limit]

    def front_sequence_candidates(
        self,
        pattern_lengths: Sequence[int] = (4, 3),
        limit: int = 8,
    ) -> List[FrontSequenceCandidate]:
        firsts = [d.first_number for d in self.draws]
        candidates: List[FrontSequenceCandidate] = []
        seen_keys = set()
        for pattern_length in pattern_lengths:
            if len(firsts) <= pattern_length:
                continue
            pattern = tuple(firsts[-pattern_length:])
            continuation_counts = Counter()
            example_draws: Dict[int, List[int]] = defaultdict(list)
            for start in range(0, len(firsts) - pattern_length):
                if tuple(firsts[start : start + pattern_length]) != pattern:
                    continue
                next_number = firsts[start + pattern_length]
                continuation_counts[next_number] += 1
                example_draws[next_number].append(self.draws[start + pattern_length].draw_no)

            support = sum(continuation_counts.values())
            if support <= 0:
                continue

            for next_number, hit_count in continuation_counts.items():
                key = (pattern_length, pattern, next_number)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                confidence = hit_count / support
                score = 100.0 * min(
                    1.0,
                    confidence * 0.72
                    + safe_ratio(hit_count, 4.0) * 0.18
                    + safe_ratio(pattern_length, 4.0) * 0.10,
                )
                pattern_text = " → ".join(f"{n:02d}" for n in pattern)
                reason = (
                    f"최근 앞번호 {pattern_text} 패턴 후 과거 {support}번 중 "
                    f"{hit_count}번 {next_number:02d}번으로 이어짐"
                )
                candidates.append(
                    FrontSequenceCandidate(
                        kind="sequence",
                        number=next_number,
                        score=round(score, 2),
                        pattern=pattern,
                        pattern_length=pattern_length,
                        support=support,
                        hit_count=hit_count,
                        confidence=round(confidence, 4),
                        example_draws=tuple(example_draws[next_number][-6:]),
                        reason=reason,
                    )
                )

        candidates.sort(
            key=lambda item: (
                -item.score,
                -item.pattern_length,
                -item.confidence,
                -item.hit_count,
                item.number,
            )
        )
        return candidates[:limit]

    def front_sequence_anchor_candidate(
        self,
        minimum_score: float = 70.0,
        minimum_hit_count: int = 2,
        minimum_confidence: float = 0.60,
    ) -> Optional[FrontSequenceCandidate]:
        for candidate in self.front_sequence_candidates(limit=8):
            if (
                candidate.score >= minimum_score
                and candidate.hit_count >= minimum_hit_count
                and candidate.confidence >= minimum_confidence
            ):
                return candidate
        return None

    def front_anchor_candidate(
        self,
        minimum_score: float = 70.0,
    ) -> Optional[FrontSequenceCandidate]:
        return self.front_sequence_anchor_candidate(minimum_score=minimum_score)

    def coord(self, number: int) -> Tuple[int, int]:
        return ((number - 1) % self.grid_cols, (number - 1) // self.grid_cols)

    def shape_signature(self, numbers: Sequence[int]) -> Tuple[str, ...]:
        coords = [self.coord(n) for n in sorted(numbers)]
        moves = []
        for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
            dx = x2 - x1
            dy = y2 - y1
            sx = "R" if dx > 0 else "L" if dx < 0 else "S"
            sy = "D" if dy > 0 else "U" if dy < 0 else "S"
            dist = min(6, abs(dx) + abs(dy))
            moves.append(f"{sx}{sy}{dist}")
        return tuple(moves)

    @staticmethod
    def shape_similarity(left: Tuple[str, ...], right: Tuple[str, ...]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        scores = []
        for a, b in zip(left, right):
            same_x = a[0] == b[0]
            same_y = a[1] == b[1]
            try:
                dist_a = int(a[2:])
                dist_b = int(b[2:])
            except ValueError:
                dist_a = dist_b = 0
            direction_score = 0.0
            if same_x and same_y:
                direction_score = 0.70
            elif same_x or same_y:
                direction_score = 0.35
            distance_score = 0.30 * max(0.0, 1.0 - abs(dist_a - dist_b) / 6.0)
            scores.append(direction_score + distance_score)
        return sum(scores) / len(scores)

    def shape_combo_points(
        self,
        signature: Tuple[str, ...],
        shape_counts: Counter,
        max_shape_count: int,
        top_n: int = 12,
    ) -> float:
        if not shape_counts:
            return 0.0
        best = 0.0
        for known_signature, count in shape_counts.most_common(top_n):
            similarity = self.shape_similarity(signature, known_signature)
            frequency_boost = 0.40 + 0.60 * safe_ratio(count, max_shape_count)
            best = max(best, similarity * frequency_boost)
        return 12.0 * best

    def shape_stats(self) -> Counter:
        return Counter(self.shape_signature(d.numbers) for d in self.draws)

    def shape_number_scores(self, top_n: int = 8) -> Dict[int, float]:
        stats = self.shape_stats()
        top_shapes = {signature for signature, _ in stats.most_common(top_n)}
        counts = Counter(
            n
            for d in self.draws
            if self.shape_signature(d.numbers) in top_shapes
            for n in d.numbers
        )
        high = max(counts.values(), default=0)
        return {n: 100.0 * safe_ratio(counts[n], high) for n in self.all_numbers}

    def number_scores(
        self,
        target: date,
        window: int = 20,
        enabled_factors: Optional[Sequence[str]] = None,
    ) -> Tuple[List[NumberScore], Dict[str, object]]:
        enabled = tuple(enabled_factors or DEFAULT_NUMBER_FACTORS)
        enabled = tuple(name for name in enabled if name in NUMBER_FACTOR_LABELS)
        if not enabled:
            raise ValueError("At least one number analysis factor must be enabled.")

        same_date, same_date_matches = self.same_date_scores(target)
        raw_sources = {
            "same_date": same_date,
            "skip": self.skip_scores(window=window),
            "front": self.front_number_scores(),
            "recent": self.recent_scores(window),
            "overdue": self.overdue_scores(),
            "frequency": self.frequency_scores(),
            "shape": self.shape_number_scores(),
            "ending": self.ending_scores(window),
        }
        weights = {
            "same_date": 1.25,
            "skip": 1.45,
            "front": 0.80,
            "recent": 1.05,
            "overdue": 0.85,
            "frequency": 0.70,
            "shape": 0.85,
            "ending": 0.45,
        }

        totals = {}
        factor_points: Dict[int, Dict[str, float]] = {}
        for n in self.all_numbers:
            factors = {
                name: raw_sources[name][n] * weight
                for name, weight in weights.items()
                if name in enabled
            }
            factor_points[n] = factors
            totals[n] = sum(factors.values())

        high = max(totals.values(), default=1.0)
        ranked = [
            NumberScore(
                number=n,
                total=round(100.0 * safe_ratio(totals[n], high), 2),
                factors={k: round(v, 2) for k, v in factor_points[n].items()},
            )
            for n in self.all_numbers
        ]
        ranked.sort(key=lambda x: (-x.total, x.number))
        diagnostics = {
            "same_date_matches": same_date_matches,
            "top_shapes": self.shape_stats().most_common(5),
            "enabled_number_factors": enabled,
        }
        return ranked, diagnostics

    def pair_counter(self) -> Counter:
        pairs = Counter()
        for d in self.draws:
            for pair in combinations(d.numbers, 2):
                pairs[pair] += 1
        return pairs

    def historical_distribution(self) -> Dict[str, Counter]:
        return {
            "odd": Counter(sum(n % 2 for n in d.numbers) for d in self.draws),
            "low": Counter(sum(n <= 22 for n in d.numbers) for d in self.draws),
            "ending_dup": Counter(PICK_COUNT - len({n % 10 for n in d.numbers}) for d in self.draws),
            "consecutive": Counter(self.consecutive_count(d.numbers) for d in self.draws),
        }

    @staticmethod
    def consecutive_count(numbers: Sequence[int]) -> int:
        nums = sorted(numbers)
        return sum(1 for a, b in zip(nums, nums[1:]) if b == a + 1)

    def combo_score(
        self,
        combo: Tuple[int, ...],
        number_score_map: Dict[int, float],
        front_scores: Dict[int, float],
        top_recent_numbers: set,
        pair_counts: Counter,
        max_pair_count: int,
        shape_counts: Counter,
        max_shape_count: int,
        distributions: Dict[str, Counter],
        recent_sum_mean: float,
        recent_sum_std: float,
        enabled_combo_factors: Optional[Sequence[str]] = None,
    ) -> ComboScore:
        enabled = tuple(enabled_combo_factors or DEFAULT_COMBO_FACTORS)
        enabled = tuple(name for name in enabled if name in COMBO_FACTOR_LABELS)
        if not enabled:
            raise ValueError("At least one combination scoring factor must be enabled.")

        combo = tuple(sorted(combo))
        number_part = mean(number_score_map[n] for n in combo) * 0.45

        signature = self.shape_signature(combo)
        shape_part = self.shape_combo_points(signature, shape_counts, max_shape_count)

        first = combo[0]
        front_part = 8.0 * safe_ratio(front_scores.get(first, 0.0), 100.0)

        total = sum(combo)
        tolerance = max(24.0, recent_sum_std * 2.2)
        sum_part = 10.0 * bucket_score(total, recent_sum_mean, tolerance)

        odd_count = sum(n % 2 for n in combo)
        low_count = sum(n <= 22 for n in combo)
        ending_dup = PICK_COUNT - len({n % 10 for n in combo})
        consecutive = self.consecutive_count(combo)

        odd_part = 7.0 * safe_ratio(distributions["odd"][odd_count], max(distributions["odd"].values()))
        low_part = 5.0 * safe_ratio(distributions["low"][low_count], max(distributions["low"].values()))
        ending_part = 5.0 * safe_ratio(
            distributions["ending_dup"][ending_dup],
            max(distributions["ending_dup"].values()),
        )
        consecutive_part = 4.0 * safe_ratio(
            distributions["consecutive"][consecutive],
            max(distributions["consecutive"].values()),
        )

        pair_total = sum(pair_counts[pair] for pair in combinations(combo, 2))
        pair_part = 4.0 * safe_ratio(pair_total, max_pair_count * 2.5)

        hot_count = len(set(combo) & top_recent_numbers)
        hot_part = 3.0 * bucket_score(hot_count, 2.0, 2.0)

        history_penalty = self.history_similarity_penalty(combo)

        all_parts = {
            "number": number_part,
            "line_shape": shape_part,
            "front": front_part,
            "sum": sum_part,
            "odd_even": odd_part,
            "low_high": low_part,
            "ending": ending_part,
            "consecutive": consecutive_part,
            "pair": pair_part,
            "recent_hot": hot_part,
            "history_penalty": -history_penalty,
        }
        parts = {k: v for k, v in all_parts.items() if k in enabled}
        max_points = sum(COMBO_FACTOR_MAX_POINTS[k] for k in enabled if k in COMBO_FACTOR_MAX_POINTS)
        if max_points <= 0:
            max_points = 1.0
        score = max(0.0, min(100.0, 100.0 * sum(parts.values()) / max_points))
        return ComboScore(combo, round(score, 2), {k: round(v, 2) for k, v in parts.items()})

    def history_similarity_penalty(self, combo: Sequence[int]) -> float:
        combo_set = set(combo)
        best_overlap = max(len(combo_set & set(d.numbers)) for d in self.draws)
        if best_overlap >= 6:
            return 18.0
        if best_overlap == 5:
            return 8.0
        return 0.0

    def generate_combinations(
        self,
        ranked_numbers: Sequence[NumberScore],
        target: date,
        count: int = 5,
        candidates: int = 50000,
        pool_size: int = 30,
        window: int = 20,
        seed: Optional[int] = None,
        combo_factors: Optional[Sequence[str]] = None,
        front_anchor: Optional[int] = None,
    ) -> List[ComboScore]:
        rng = random.Random(seed)
        ranked_pool = list(ranked_numbers[: max(pool_size, PICK_COUNT)])
        if front_anchor is not None:
            ranked_pool = [item for item in ranked_numbers if item.number > front_anchor][: max(pool_size, PICK_COUNT)]
            if len(ranked_pool) < PICK_COUNT - 1:
                ranked_pool = [item for item in ranked_numbers if item.number != front_anchor][: max(pool_size, PICK_COUNT)]
        pool = [item.number for item in ranked_pool]
        weights = [max(0.1, item.total) for item in ranked_pool]
        number_score_map = {item.number: item.total for item in ranked_numbers}
        if front_anchor is not None and front_anchor not in number_score_map:
            number_score_map[front_anchor] = 0.0
        front_scores = self.front_number_scores()
        pair_counts = self.pair_counter()
        max_pair_count = max(pair_counts.values(), default=1)
        shape_counts = self.shape_stats()
        max_shape_count = max(shape_counts.values(), default=1)
        distributions = self.historical_distribution()
        recent = self.recent_draws(window)
        recent_sums = [d.total for d in recent]
        recent_sum_mean = mean(recent_sums)
        recent_sum_std = pstdev(recent_sums) if len(recent_sums) > 1 else 28.0
        recent_counter = Counter(n for d in recent for n in d.numbers)
        top_recent_numbers = {n for n, _ in recent_counter.most_common(6)}

        seen = set()
        scored: List[ComboScore] = []

        if front_anchor is not None:
            top_seed_combo = tuple(sorted([front_anchor] + pool[: PICK_COUNT - 1]))
        else:
            top_seed_combo = tuple(sorted(pool[:PICK_COUNT]))
        seen.add(top_seed_combo)
        scored.append(
            self.combo_score(
                top_seed_combo,
                number_score_map,
                front_scores,
                top_recent_numbers,
                pair_counts,
                max_pair_count,
                shape_counts,
                max_shape_count,
                distributions,
                recent_sum_mean,
                recent_sum_std,
                combo_factors,
            )
        )

        for _ in range(candidates):
            if front_anchor is not None:
                sampled = weighted_sample_without_replacement(pool, weights, PICK_COUNT - 1, rng)
                combo = tuple(sorted([front_anchor] + sampled))
            else:
                combo = tuple(sorted(weighted_sample_without_replacement(pool, weights, PICK_COUNT, rng)))
            if combo in seen:
                continue
            seen.add(combo)
            scored.append(
                self.combo_score(
                    combo,
                    number_score_map,
                    front_scores,
                    top_recent_numbers,
                    pair_counts,
                    max_pair_count,
                    shape_counts,
                    max_shape_count,
                    distributions,
                    recent_sum_mean,
                    recent_sum_std,
                    combo_factors,
                )
            )

        scored.sort(key=lambda x: (-x.score, x.numbers))
        diversified: List[ComboScore] = []
        for item in scored:
            if all(len(set(item.numbers) & set(prev.numbers)) <= 4 for prev in diversified):
                diversified.append(item)
            if len(diversified) == count:
                break
        return diversified or scored[:count]


def weighted_sample_without_replacement(
    population: Sequence[int],
    weights: Sequence[float],
    k: int,
    rng: random.Random,
) -> List[int]:
    items = list(population)
    item_weights = list(weights)
    result: List[int] = []
    for _ in range(k):
        total = sum(item_weights)
        pick = rng.uniform(0, total)
        upto = 0.0
        index = 0
        for i, w in enumerate(item_weights):
            upto += w
            if upto >= pick:
                index = i
                break
        result.append(items.pop(index))
        item_weights.pop(index)
    return result


def format_draw(draw: Draw) -> str:
    nums = " ".join(f"{n:02d}" for n in draw.numbers)
    return f"{draw.draw_no}회 {draw.draw_date.isoformat()} [{nums}]"


def print_report(
    data_path: Path,
    target: date,
    analyzer: LottoAnalyzer,
    ranked: Sequence[NumberScore],
    diagnostics: Dict[str, object],
    combos: Sequence[ComboScore],
    top_numbers: int,
    output=sys.stdout,
) -> None:
    print("=" * 72, file=output)
    print("Lotto Auto Analyzer", file=output)
    print("=" * 72, file=output)
    print(f"데이터: {data_path}", file=output)
    print(f"분석 기준일: {target.isoformat()}", file=output)
    print(f"총 회차 수: {len(analyzer.draws)}", file=output)
    print(file=output)
    print("[주의] 로또 추첨은 독립 시행입니다. 이 결과는 보장이 아니라 데이터 기반 필터입니다.", file=output)
    print(file=output)

    matches = diagnostics["same_date_matches"]
    print("1) 과거 같은 날짜 당첨번호", file=output)
    if matches:
        for draw in matches[-10:]:
            print(f"   - {format_draw(draw)}", file=output)
    else:
        print("   - 같은 월/일 데이터가 없습니다. 이 항목은 0점 처리되었습니다.", file=output)
    print(file=output)

    print("2) 로또용지 선 패턴 TOP 5", file=output)
    for signature, cnt in diagnostics["top_shapes"]:
        print(f"   - {cnt:>3}회: {' > '.join(signature)}", file=output)
    print(file=output)

    print(f"3) 교차 점수 상위 번호 TOP {top_numbers}", file=output)
    enabled = diagnostics.get("enabled_number_factors", DEFAULT_NUMBER_FACTORS)
    print("적용 번호 기법: " + ", ".join(NUMBER_FACTOR_LABELS[k] for k in enabled), file=output)
    for item in ranked[:top_numbers]:
        factor_text = ", ".join(
            f"{NUMBER_FACTOR_LABELS[k]} {v:.1f}" for k, v in sorted(item.factors.items())
        )
        print(f"   - {item.number:02d}: {item.total:>6.2f}점 | {factor_text}", file=output)
    print(file=output)

    print("4) 추천 조합 TOP 5", file=output)
    for i, combo in enumerate(combos, 1):
        nums = " ".join(f"{n:02d}" for n in combo.numbers)
        parts = ", ".join(f"{k} {v:+.1f}" for k, v in combo.parts.items())
        print(f"   {i}. [{nums}]  {combo.score:.2f}점", file=output)
        print(f"      {parts}", file=output)
    print(file=output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lotto historical pattern analyzer and number generator."
    )
    parser.add_argument(
        "--data",
        default="data/lotto.csv",
        help="CSV path. Default: data/lotto.csv",
    )
    parser.add_argument(
        "--target-date",
        default=date.today().isoformat(),
        help="Analysis target date, e.g. 2026-06-18. Default: today.",
    )
    parser.add_argument("--count", type=int, default=5, help="Number of combos to print.")
    parser.add_argument("--top-numbers", type=int, default=15, help="Number ranking size.")
    parser.add_argument("--recent-window", type=int, default=20, help="Recent draw window.")
    parser.add_argument("--candidates", type=int, default=50000, help="Random candidate combos.")
    parser.add_argument("--pool-size", type=int, default=30, help="Top number pool size.")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for repeatability.")
    parser.add_argument("--report", default=None, help="Optional text report output path.")
    parser.add_argument(
        "--number-factors",
        default=",".join(DEFAULT_NUMBER_FACTORS),
        help="Comma-separated number factors.",
    )
    parser.add_argument(
        "--combo-factors",
        default=",".join(DEFAULT_COMBO_FACTORS),
        help="Comma-separated combination factors.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    base_dir = Path(__file__).resolve().parent
    data_path = Path(args.data)
    if not data_path.is_absolute():
        data_path = base_dir / data_path
    if not data_path.exists() and args.data == "data/lotto.csv":
        sample = base_dir / "data" / "lotto_sample.csv"
        print(f"data/lotto.csv가 없어 샘플 파일로 실행합니다: {sample}")
        data_path = sample

    target = parse_date(args.target_date)
    draws = load_draws(data_path)
    analyzer = LottoAnalyzer(draws)
    number_factors = [item.strip() for item in args.number_factors.split(",") if item.strip()]
    combo_factors = [item.strip() for item in args.combo_factors.split(",") if item.strip()]
    ranked, diagnostics = analyzer.number_scores(
        target=target,
        window=args.recent_window,
        enabled_factors=number_factors,
    )
    combos = analyzer.generate_combinations(
        ranked,
        target=target,
        count=args.count,
        candidates=args.candidates,
        pool_size=args.pool_size,
        window=args.recent_window,
        seed=args.seed,
        combo_factors=combo_factors,
    )
    report_args = (
        data_path,
        target,
        analyzer,
        ranked,
        diagnostics,
        combos,
        args.top_numbers,
    )
    print_report(*report_args)
    if args.report:
        report_path = Path(args.report)
        if not report_path.is_absolute():
            report_path = base_dir / report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("w", encoding="utf-8") as f:
            print_report(*report_args, output=f)
        print(f"리포트 저장: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
