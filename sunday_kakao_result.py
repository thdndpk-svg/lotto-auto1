#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from lotto_feedback import analyze_and_save_feedback, feedback_kakao_lines
from lotto_auto import load_draws
from weekly_kakao_report import (
    APP_DIR,
    DATA_PATH,
    RECOMMENDATION_PATH,
    refresh_access_token,
    refresh_lotto_data,
    send_kakao_memo,
    load_local_token,
)


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


def format_numbers(numbers: list[int], winning: set[int], bonus: int | None) -> str:
    parts = []
    for number in numbers:
        marker = "★" if number in winning else "☆" if bonus and number == bonus else ""
        parts.append(f"{number:02d}{marker}")
    return " ".join(parts)


def load_recommendations(recommendation_path: Path = RECOMMENDATION_PATH) -> dict | None:
    if not recommendation_path.exists():
        return None
    return json.loads(recommendation_path.read_text(encoding="utf-8"))


def build_result_message(recommendations: dict | None, feedback_result: dict | None = None) -> str:
    if not recommendations:
        return "\n".join(
            [
                "[로또 추천번호 결과]",
                "저장된 수요일 추천번호가 없습니다.",
                "다음 수요일 자동 분석 이후부터 일요일 결과 확인이 가능합니다.",
            ]
        )

    draws = load_draws(DATA_PATH)
    latest = draws[-1]
    winning = set(latest.numbers)
    bonus = latest.bonus

    lines = [
        "[로또 추천번호 결과]",
        f"추천 기준일: {recommendations.get('target_date', '-')}",
        f"확인 회차: {latest.draw_no}회 ({latest.draw_date.isoformat()})",
        "당첨번호: " + " ".join(f"{n:02d}" for n in latest.numbers) + (f" + 보너스 {bonus:02d}" if bonus else ""),
        "",
        "수요일 추천번호 결과",
    ]

    for combo in recommendations.get("combos", [])[:5]:
        numbers = [int(n) for n in combo.get("numbers", [])]
        matched = len(set(numbers) & winning)
        bonus_match = bonus in numbers if bonus else False
        label = prize_label(matched, bonus_match)
        lines.append(
            f"{combo.get('rank', '-')}. {format_numbers(numbers, winning, bonus)}"
            f" | 일치 {matched}개"
            f"{' + 보너스' if bonus_match else ''}"
            f" | {label}"
        )

    lines.extend(
        [
            "",
            *(feedback_kakao_lines(feedback_result) if feedback_result else []),
            "",
            "표시: ★ 당첨번호, ☆ 보너스번호",
            "로또는 독립 시행이라 이 결과는 기록/검증용입니다.",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sunday Lotto result Kakao sender.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-refresh", action="store_true", help="Do not refresh lotto.csv before checking result.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.skip_refresh:
        refresh_lotto_data()

    recommendations = load_recommendations()
    feedback_result = None
    if recommendations:
        latest = load_draws(DATA_PATH)[-1]
        feedback_result = analyze_and_save_feedback(
            recommendations,
            latest,
            vault_dir=APP_DIR / "knowledge",
        )
        print(f"Feedback status: {feedback_result['status']}")

    message = build_result_message(recommendations, feedback_result)
    print(message)

    if args.dry_run:
        return 0

    local_token = load_local_token()
    rest_api_key = os.environ.get("KAKAO_REST_API_KEY") or local_token.get("rest_api_key")
    refresh_token = os.environ.get("KAKAO_REFRESH_TOKEN") or local_token.get("refresh_token")
    client_secret = os.environ.get("KAKAO_CLIENT_SECRET") or local_token.get("client_secret")
    if not rest_api_key or not refresh_token:
        raise SystemExit("Missing KAKAO_REST_API_KEY or KAKAO_REFRESH_TOKEN environment variable.")

    access_token = refresh_access_token(rest_api_key, refresh_token, client_secret)
    response = send_kakao_memo(access_token, message)
    print(f"Kakao send response: {response}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
