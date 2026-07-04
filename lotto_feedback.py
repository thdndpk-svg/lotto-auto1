#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Sequence

from lotto_knowledge_net import pattern_nodes, pattern_slug, pattern_title


APP_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = APP_DIR / "knowledge"
DEFAULT_FEEDBACK_PATH = KNOWLEDGE_DIR / "feedback_memory.json"
FEEDBACK_SUMMARY_SLUG = "feedback-learning-summary"
FEEDBACK_LATEST_SLUG = "feedback-latest-result"

FACTOR_MAX_POINTS = {
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
    "knowledge_net": 6.0,
    "feedback": 5.0,
}

FACTOR_LABELS = {
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
    "knowledge_net": "지식그물",
    "same_date": "같은날짜",
    "skip": "건너뛰기",
    "overdue": "미출현",
    "frequency": "전체빈도",
    "shape": "선패턴",
    "knowledge": "지식그물",
    "feedback": "피드백학습",
}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def default_feedback_memory() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": None,
        "observation_count": 0,
        "number_bias": {},
        "pattern_bias": {},
        "factor_bias": {},
        "outcomes": [],
        "latest_event": None,
    }


def load_feedback_memory(path: Path = DEFAULT_FEEDBACK_PATH) -> dict[str, Any]:
    if not path.exists():
        return default_feedback_memory()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default_feedback_memory()
    memory = default_feedback_memory()
    memory.update(raw)
    memory["number_bias"] = {str(k): float(v) for k, v in memory.get("number_bias", {}).items()}
    memory["pattern_bias"] = {str(k): float(v) for k, v in memory.get("pattern_bias", {}).items()}
    memory["factor_bias"] = {str(k): float(v) for k, v in memory.get("factor_bias", {}).items()}
    memory["outcomes"] = list(memory.get("outcomes", []))[-80:]
    return memory


def save_feedback_memory(memory: dict[str, Any], path: Path = DEFAULT_FEEDBACK_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(memory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def has_feedback(memory: dict[str, Any]) -> bool:
    return int(memory.get("observation_count") or 0) > 0


def feedback_number_scores(numbers: Sequence[int], memory: dict[str, Any]) -> dict[int, float]:
    if not has_feedback(memory):
        return {int(number): 0.0 for number in numbers}
    bias = memory.get("number_bias", {})
    return {
        int(number): round(clamp(46.0 + 28.0 * float(bias.get(str(int(number)), 0.0)), 0.0, 100.0), 2)
        for number in numbers
    }


def factor_multiplier(name: str, memory: dict[str, Any]) -> float:
    if not has_feedback(memory):
        return 1.0
    bias = float(memory.get("factor_bias", {}).get(name, 0.0))
    return round(clamp(1.0 + 0.18 * bias, 0.82, 1.18), 4)


def adjust_factor_weights(weights: dict[str, float], memory: dict[str, Any]) -> dict[str, float]:
    if not has_feedback(memory):
        return dict(weights)
    return {
        name: round(value * factor_multiplier(name, memory), 4)
        for name, value in weights.items()
    }


def apply_combo_factor_feedback(parts: dict[str, float], memory: dict[str, Any]) -> dict[str, float]:
    if not has_feedback(memory):
        return dict(parts)
    adjusted = {}
    for name, value in parts.items():
        if value > 0:
            adjusted[name] = value * factor_multiplier(name, memory)
        else:
            adjusted[name] = value
    return adjusted


def feedback_combo_points(combo: Sequence[int], memory: dict[str, Any], max_points: float = 5.0) -> float:
    if not has_feedback(memory):
        return 0.0
    number_bias = memory.get("number_bias", {})
    pattern_bias = memory.get("pattern_bias", {})
    numbers = [int(n) for n in combo]
    number_part = mean(float(number_bias.get(str(n), 0.0)) for n in numbers)
    patterns = pattern_nodes(numbers)
    pattern_part = mean(float(pattern_bias.get(pattern, 0.0)) for pattern in patterns)
    factor_part = mean(float(v) for v in memory.get("factor_bias", {}).values()) if memory.get("factor_bias") else 0.0
    normalized = clamp(0.48 + number_part * 0.30 + pattern_part * 0.26 + factor_part * 0.10, 0.0, 1.0)
    return round(max_points * normalized, 2)


def prize_label(match_count: int, bonus_match: bool) -> str:
    if match_count == 6:
        return "1등"
    if match_count == 5 and bonus_match:
        return "2등"
    if match_count == 5:
        return "3등"
    if match_count == 4:
        return "4등"
    if match_count == 3:
        return "5등"
    return "낙첨"


def combo_pattern_profile(numbers: Sequence[int]) -> dict[str, int]:
    nums = sorted(int(n) for n in numbers)
    return {
        "sum": sum(nums),
        "odd": sum(n % 2 for n in nums),
        "low": sum(n <= 22 for n in nums),
        "ending_dup": 6 - len({n % 10 for n in nums}),
        "consecutive": sum(1 for a, b in zip(nums, nums[1:]) if b == a + 1),
        "front": nums[0],
    }


def profile_distance(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    return {
        "sum": abs(left["sum"] - right["sum"]),
        "odd": abs(left["odd"] - right["odd"]),
        "low": abs(left["low"] - right["low"]),
        "ending_dup": abs(left["ending_dup"] - right["ending_dup"]),
        "consecutive": abs(left["consecutive"] - right["consecutive"]),
        "front": abs(left["front"] - right["front"]),
    }


def extract_recommendation_combos(recommendations: dict[str, Any]) -> list[dict[str, Any]]:
    combos = []
    for combo in recommendations.get("combos", [])[:5]:
        numbers = sorted(int(n) for n in combo.get("numbers", []))
        if len(numbers) != 6:
            continue
        combos.append(
            {
                "rank": combo.get("rank", len(combos) + 1),
                "numbers": numbers,
                "score": float(combo.get("score", 0.0)),
                "parts": {str(k): float(v) for k, v in (combo.get("parts") or {}).items()},
            }
        )
    return combos


def build_feedback_event(recommendations: dict[str, Any], latest_draw: Any) -> dict[str, Any]:
    combos = extract_recommendation_combos(recommendations)
    winning_numbers = sorted(int(n) for n in latest_draw.numbers)
    winning_set = set(winning_numbers)
    bonus = int(latest_draw.bonus) if latest_draw.bonus else None
    winning_profile = combo_pattern_profile(winning_numbers)
    winning_patterns = pattern_nodes(winning_numbers)

    combo_results = []
    factor_effect = defaultdict(float)
    recommended_numbers = Counter()
    recommended_patterns = Counter()
    best_match = 0
    best_bonus = False
    best_rank = "-"

    for combo in combos:
        numbers = combo["numbers"]
        recommended_numbers.update(numbers)
        recommended_patterns.update(pattern_nodes(numbers))
        matched_numbers = sorted(set(numbers) & winning_set)
        match_count = len(matched_numbers)
        bonus_match = bonus in numbers if bonus else False
        if (match_count, bonus_match) > (best_match, best_bonus):
            best_match = match_count
            best_bonus = bonus_match
            best_rank = combo["rank"]

        profile = combo_pattern_profile(numbers)
        distance = profile_distance(profile, winning_profile)
        hit_strength = (match_count - 2.0) / 4.0
        if bonus_match:
            hit_strength += 0.08
        for factor, value in combo["parts"].items():
            if factor == "history_penalty":
                continue
            max_point = FACTOR_MAX_POINTS.get(factor, max(abs(value), 1.0))
            strength = clamp(abs(value) / max_point, 0.0, 1.0)
            factor_effect[factor] += hit_strength * strength

        combo_results.append(
            {
                "rank": combo["rank"],
                "numbers": numbers,
                "matched_numbers": matched_numbers,
                "match_count": match_count,
                "bonus_match": bonus_match,
                "label": prize_label(match_count, bonus_match),
                "profile": profile,
                "distance": distance,
            }
        )

    causes = []
    hit_factors = []
    if combos:
        rec_profiles = [combo_pattern_profile(combo["numbers"]) for combo in combos]
        sum_values = [profile["sum"] for profile in rec_profiles]
        odd_values = [profile["odd"] for profile in rec_profiles]
        low_values = [profile["low"] for profile in rec_profiles]
        front_values = {profile["front"] for profile in rec_profiles}
        ending_values = [profile["ending_dup"] for profile in rec_profiles]
        consecutive_values = [profile["consecutive"] for profile in rec_profiles]

        if winning_profile["sum"] < min(sum_values) - 12 or winning_profile["sum"] > max(sum_values) + 12:
            causes.append(f"번호합 범위 이탈: 추천 {min(sum_values)}~{max(sum_values)}, 당첨 {winning_profile['sum']}")
        else:
            hit_factors.append(f"번호합 범위 근접: 당첨 {winning_profile['sum']}")
        if winning_profile["odd"] not in odd_values:
            causes.append(f"홀짝비율 불일치: 당첨 홀수 {winning_profile['odd']}개")
        else:
            hit_factors.append(f"홀짝비율 적중 축: 홀수 {winning_profile['odd']}개")
        if winning_profile["low"] not in low_values:
            causes.append(f"저/고 비율 불일치: 당첨 저번호 {winning_profile['low']}개")
        else:
            hit_factors.append(f"저/고 비율 적중 축: 저번호 {winning_profile['low']}개")
        if winning_profile["front"] not in front_values:
            causes.append(f"앞번호 불일치: 당첨 첫번호 {winning_profile['front']:02d}번")
        else:
            hit_factors.append(f"앞번호 후보 포함: {winning_profile['front']:02d}번")
        if winning_profile["ending_dup"] not in ending_values:
            causes.append(f"끝수 중복 패턴 불일치: 당첨 {winning_profile['ending_dup']}개")
        if winning_profile["consecutive"] not in consecutive_values:
            causes.append(f"연속수 패턴 불일치: 당첨 {winning_profile['consecutive']}개")

    if best_match < 3:
        causes.insert(0, f"최고 일치 {best_match}개로 5등권 미달")
    elif best_match >= 3:
        hit_factors.insert(0, f"{best_rank}번 조합이 {best_match}개 일치")

    winning_not_recommended = [n for n in winning_numbers if n not in recommended_numbers]
    if winning_not_recommended:
        causes.append("미포함 당첨번호: " + " ".join(f"{n:02d}" for n in winning_not_recommended))

    return {
        "event_id": f"{recommendations.get('generated_at', '-')}_{latest_draw.draw_no}",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "recommendation_target_date": recommendations.get("target_date"),
        "recommendation_generated_at": recommendations.get("generated_at"),
        "analysis_latest_draw_no": recommendations.get("latest_draw_no_at_analysis"),
        "draw_no": latest_draw.draw_no,
        "draw_date": latest_draw.draw_date.isoformat(),
        "winning_numbers": winning_numbers,
        "bonus": bonus,
        "winning_profile": winning_profile,
        "winning_patterns": winning_patterns,
        "combo_results": combo_results,
        "best_match": best_match,
        "best_bonus_match": best_bonus,
        "best_label": prize_label(best_match, best_bonus),
        "causes": causes[:8],
        "hit_factors": hit_factors[:8],
        "recommended_numbers": dict(recommended_numbers),
        "recommended_patterns": dict(recommended_patterns),
        "winning_not_recommended": winning_not_recommended,
        "factor_effect": {key: round(value, 4) for key, value in factor_effect.items()},
    }


def event_already_recorded(memory: dict[str, Any], event_id: str) -> bool:
    return any(item.get("event_id") == event_id for item in memory.get("outcomes", []))


def update_feedback_memory(memory: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    if event_already_recorded(memory, event["event_id"]):
        memory["latest_event"] = event
        return memory

    number_bias = defaultdict(float, memory.get("number_bias", {}))
    pattern_bias = defaultdict(float, memory.get("pattern_bias", {}))
    factor_bias = defaultdict(float, memory.get("factor_bias", {}))

    for key in list(number_bias):
        number_bias[key] *= 0.985
    for key in list(pattern_bias):
        pattern_bias[key] *= 0.985
    for key in list(factor_bias):
        factor_bias[key] *= 0.975

    winning = set(int(n) for n in event["winning_numbers"])
    recommended = {int(k): int(v) for k, v in event.get("recommended_numbers", {}).items()}
    for number, count in recommended.items():
        delta = 0.045 if number in winning else -0.018 * min(2, count)
        number_bias[str(number)] += delta
    for number in winning:
        if number not in recommended:
            number_bias[str(number)] += 0.038

    winning_patterns = set(event.get("winning_patterns", []))
    recommended_patterns = event.get("recommended_patterns", {})
    for pattern in winning_patterns:
        pattern_bias[pattern] += 0.055
    for pattern, count in recommended_patterns.items():
        if pattern not in winning_patterns:
            pattern_bias[pattern] -= 0.014 * min(2, int(count))

    for factor, value in event.get("factor_effect", {}).items():
        factor_bias[factor] += 0.075 * float(value)
    if event.get("best_match", 0) < 3:
        factor_bias["feedback"] += 0.025
    else:
        factor_bias["feedback"] += 0.045

    memory["number_bias"] = {
        str(key): round(clamp(float(value), -1.35, 1.35), 4)
        for key, value in number_bias.items()
        if abs(value) >= 0.003
    }
    memory["pattern_bias"] = {
        str(key): round(clamp(float(value), -1.25, 1.25), 4)
        for key, value in pattern_bias.items()
        if abs(value) >= 0.003
    }
    memory["factor_bias"] = {
        str(key): round(clamp(float(value), -1.0, 1.0), 4)
        for key, value in factor_bias.items()
        if abs(value) >= 0.003
    }
    memory["observation_count"] = int(memory.get("observation_count") or 0) + 1
    memory["updated_at"] = datetime.now().isoformat(timespec="seconds")
    memory["latest_event"] = event
    memory["outcomes"] = (list(memory.get("outcomes", [])) + [event])[-80:]
    return memory


def feedback_summary(memory: dict[str, Any]) -> dict[str, Any]:
    outcomes = list(memory.get("outcomes", []))
    recent = outcomes[-10:]
    best_matches = [int(item.get("best_match") or 0) for item in recent]
    number_bias = sorted(
        ((int(k), float(v)) for k, v in memory.get("number_bias", {}).items()),
        key=lambda item: (-item[1], item[0]),
    )
    factor_bias = sorted(
        ((str(k), float(v)) for k, v in memory.get("factor_bias", {}).items()),
        key=lambda item: (-item[1], item[0]),
    )
    pattern_bias = sorted(
        ((str(k), float(v)) for k, v in memory.get("pattern_bias", {}).items()),
        key=lambda item: (-item[1], item[0]),
    )
    return {
        "observationCount": int(memory.get("observation_count") or 0),
        "updatedAt": memory.get("updated_at"),
        "recentAverageMatch": round(mean(best_matches), 2) if best_matches else 0.0,
        "topNumbers": [{"number": n, "bias": round(v, 4)} for n, v in number_bias[:8]],
        "weakNumbers": [{"number": n, "bias": round(v, 4)} for n, v in sorted(number_bias, key=lambda item: (item[1], item[0]))[:8]],
        "topFactors": [{"key": k, "label": FACTOR_LABELS.get(k, k), "bias": round(v, 4)} for k, v in factor_bias[:8]],
        "topPatterns": [
            {"key": k, "label": pattern_title(k), "slug": pattern_slug(k), "bias": round(v, 4)}
            for k, v in pattern_bias[:8]
        ],
        "latestEvent": memory.get("latest_event"),
    }


def write_feedback_pages(memory: dict[str, Any], vault_dir: Path = KNOWLEDGE_DIR) -> None:
    wiki_dir = vault_dir / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    summary = feedback_summary(memory)
    latest = summary.get("latestEvent") or {}

    top_numbers = "\n".join(
        f"- [[number-{item['number']:02d}|{item['number']:02d}번]] — 보정 {item['bias']:+.3f}"
        for item in summary["topNumbers"]
    ) or "- 데이터 없음"
    top_factors = "\n".join(
        f"- {item['label']} — 보정 {item['bias']:+.3f}"
        for item in summary["topFactors"]
    ) or "- 데이터 없음"
    top_patterns = "\n".join(
        f"- [[{item['slug']}|{item['label']}]] — 보정 {item['bias']:+.3f}"
        for item in summary["topPatterns"]
    ) or "- 데이터 없음"
    summary_page = f"""---
type: note
created: {datetime.now().date().isoformat()}
updated: {datetime.now().date().isoformat()}
sources: ["knowledge/feedback_memory.json"]
aliases: ["피드백 학습", "오답노트", "실패 원인"]
---

# 피드백 학습 요약

- 누적 결과 분석: {summary['observationCount']}회
- 최근 평균 일치: {summary['recentAverageMatch']}개
- 마지막 갱신: {summary.get('updatedAt') or '-'}

## 강화 번호
{top_numbers}

## 강화 기법
{top_factors}

## 강화 패턴
{top_patterns}

## 관련
- [[feedback-latest-result]]
- [[lotto-history-knowledge-summary]]
"""
    (wiki_dir / f"{FEEDBACK_SUMMARY_SLUG}.md").write_text(summary_page, encoding="utf-8")

    cause_text = "\n".join(f"- {item}" for item in latest.get("causes", [])) or "- 데이터 없음"
    hit_text = "\n".join(f"- {item}" for item in latest.get("hit_factors", [])) or "- 데이터 없음"
    combo_text = "\n".join(
        "- {rank}위 [{numbers}] — 일치 {match_count}개, {label}".format(
            rank=item.get("rank"),
            numbers=" ".join(f"{int(n):02d}" for n in item.get("numbers", [])),
            match_count=item.get("match_count"),
            label=item.get("label"),
        )
        for item in latest.get("combo_results", [])
    ) or "- 데이터 없음"
    latest_page = f"""---
type: note
created: {datetime.now().date().isoformat()}
updated: {datetime.now().date().isoformat()}
sources: ["reports/latest_recommendations.json", "data/lotto.csv"]
aliases: ["최근 결과 피드백", "최근 실패 원인"]
---

# 최근 결과 피드백

- 확인 회차: {latest.get('draw_no', '-')}회
- 당첨번호: {" ".join(f"{int(n):02d}" for n in latest.get('winning_numbers', [])) or "-"}
- 최고 일치: {latest.get('best_match', '-')}개 / {latest.get('best_label', '-')}

## 실패 원인
{cause_text}

## 적중 요인
{hit_text}

## 추천 조합별 결과
{combo_text}

## 관련
- [[feedback-learning-summary]]
- [[lotto-history-knowledge-summary]]
"""
    (wiki_dir / f"{FEEDBACK_LATEST_SLUG}.md").write_text(latest_page, encoding="utf-8")


def analyze_and_save_feedback(
    recommendations: dict[str, Any],
    latest_draw: Any,
    memory_path: Path = DEFAULT_FEEDBACK_PATH,
    vault_dir: Path = KNOWLEDGE_DIR,
) -> dict[str, Any]:
    analysis_draw_no = recommendations.get("latest_draw_no_at_analysis")
    if analysis_draw_no is not None and int(latest_draw.draw_no) <= int(analysis_draw_no):
        memory = load_feedback_memory(memory_path)
        return {
            "status": "waiting_for_new_draw",
            "message": "추천 이후 신규 당첨 회차가 없어 피드백 학습을 건너뜁니다.",
            "memory": memory,
            "summary": feedback_summary(memory),
        }

    memory = load_feedback_memory(memory_path)
    event = build_feedback_event(recommendations, latest_draw)
    duplicate = event_already_recorded(memory, event["event_id"])
    memory = update_feedback_memory(memory, event)
    save_feedback_memory(memory, memory_path)
    write_feedback_pages(memory, vault_dir)
    return {
        "status": "duplicate" if duplicate else "updated",
        "event": event,
        "memory": memory,
        "summary": feedback_summary(memory),
    }


def feedback_kakao_lines(result: dict[str, Any], max_causes: int = 3) -> list[str]:
    if result.get("status") == "waiting_for_new_draw":
        return ["피드백학습: 신규 회차 대기"]
    event = result.get("event") or result.get("summary", {}).get("latestEvent") or {}
    causes = event.get("causes", [])[:max_causes]
    hits = event.get("hit_factors", [])[:2]
    lines = [f"피드백학습: {result.get('status', 'updated')}"]
    if causes:
        lines.append("보완점: " + " / ".join(causes))
    if hits:
        lines.append("유지할 요인: " + " / ".join(hits))
    return lines
