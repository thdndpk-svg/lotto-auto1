#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any

from import_lotto_history_json import DEFAULT_URL, load_json_from_url, write_standard_csv
from lotto_auto import LottoAnalyzer, load_draws, print_report
from lotto_feedback import feedback_summary, load_feedback_memory


APP_DIR = Path(__file__).resolve().parent
DATA_PATH = APP_DIR / "data" / "lotto.csv"
REPORT_DIR = APP_DIR / "reports"
RECOMMENDATION_PATH = REPORT_DIR / "latest_recommendations.json"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
MEMO_SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
LOCAL_TOKEN_PATH = APP_DIR / "kakao_token.local.json"


def post_form(url: str, data: dict[str, str], headers: dict[str, str] | None = None) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def refresh_access_token(rest_api_key: str, refresh_token: str, client_secret: str | None = None) -> str:
    payload = {
        "grant_type": "refresh_token",
        "client_id": rest_api_key,
        "refresh_token": refresh_token,
    }
    if client_secret:
        payload["client_secret"] = client_secret
    token = post_form(TOKEN_URL, payload)
    access_token = token.get("access_token")
    if not access_token:
        raise RuntimeError(f"Kakao access_token refresh failed: {token}")
    return str(access_token)


def send_kakao_memo(access_token: str, text: str, link_url: str = "https://www.dhlottery.co.kr/") -> dict[str, Any]:
    template_object = {
        "object_type": "text",
        "text": text[:1000],
        "link": {
            "web_url": link_url,
            "mobile_web_url": link_url,
        },
        "button_title": "동행복권 열기",
    }
    return post_form(
        MEMO_SEND_URL,
        {"template_object": json.dumps(template_object, ensure_ascii=False)},
        {"Authorization": f"Bearer {access_token}"},
    )


def load_local_token() -> dict[str, str]:
    if not LOCAL_TOKEN_PATH.exists():
        return {}
    raw = json.loads(LOCAL_TOKEN_PATH.read_text(encoding="utf-8"))
    values = {}
    if raw.get("rest_api_key"):
        values["rest_api_key"] = str(raw["rest_api_key"])
    if raw.get("refresh_token"):
        values["refresh_token"] = str(raw["refresh_token"])
    if raw.get("client_secret"):
        values["client_secret"] = str(raw["client_secret"])
    return values


def refresh_lotto_data() -> None:
    rows = load_json_from_url(DEFAULT_URL)
    write_standard_csv(rows, DATA_PATH)


def save_recommendations(
    target_date: date,
    latest_draw_no: int,
    latest_draw_date: date,
    candidates: int,
    seed: int | None,
    combos,
    feedback,
) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "target_date": target_date.isoformat(),
        "latest_draw_no_at_analysis": latest_draw_no,
        "latest_draw_date_at_analysis": latest_draw_date.isoformat(),
        "candidates": candidates,
        "seed": seed,
        "feedback_snapshot": feedback,
        "combos": [
            {
                "rank": idx,
                "numbers": list(combo.numbers),
                "score": combo.score,
                "parts": combo.parts,
            }
            for idx, combo in enumerate(combos, 1)
        ],
    }
    RECOMMENDATION_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return RECOMMENDATION_PATH


def build_analysis(target_date: date, candidates: int, seed: int | None) -> tuple[str, str, str]:
    draws = load_draws(DATA_PATH)
    analyzer = LottoAnalyzer(draws)
    feedback = feedback_summary(load_feedback_memory())
    number_factors = ["same_date", "skip", "front", "shape", "recent", "overdue", "frequency", "ending", "knowledge", "feedback"]
    combo_factors = ["number", "line_shape", "front", "sum", "odd_even", "low_high", "ending", "consecutive", "pair", "recent_hot", "knowledge_net", "feedback", "history_penalty"]

    front_anchor = analyzer.front_anchor_candidate()
    ranked, diagnostics = analyzer.number_scores(
        target=target_date,
        window=20,
        enabled_factors=number_factors,
    )
    combos = analyzer.generate_combinations(
        ranked,
        target=target_date,
        count=5,
        candidates=candidates,
        pool_size=30,
        window=20,
        seed=seed,
        combo_factors=combo_factors,
        front_anchor=front_anchor.number if front_anchor else None,
    )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"analysis_{target_date.isoformat()}.txt"
    with report_path.open("w", encoding="utf-8") as f:
        print_report(DATA_PATH, target_date, analyzer, ranked, diagnostics, combos, top_numbers=15, output=f)

    latest = draws[-1]
    recommendation_path = save_recommendations(target_date, latest.draw_no, latest.draw_date, candidates, seed, combos, feedback)
    anchor_text = "없음"
    if front_anchor:
        anchor_text = f"{front_anchor.number:02d}번 ({front_anchor.reason}, {front_anchor.score:.1f}점)"
    feedback_text = "없음"
    if feedback.get("observationCount", 0) > 0:
        top_factors = ", ".join(item["label"] for item in feedback.get("topFactors", [])[:3]) or "보정값"
        feedback_text = f"{feedback['observationCount']}회 학습 · {top_factors}"
    combo_lines = [
        f"{idx}. " + " ".join(f"{n:02d}" for n in combo.numbers) + f"  {combo.score:.1f}점"
        for idx, combo in enumerate(combos, 1)
    ]
    message = "\n".join(
        [
            "[로또 자동 분석]",
            f"기준일: {target_date.isoformat()}",
            f"최신 데이터: {latest.draw_no}회 {latest.draw_date.isoformat()}",
            "",
            f"앞번호 순서 앵커: {anchor_text}",
            f"피드백 보정: {feedback_text}",
            "",
            "추천 조합 TOP 5",
            *combo_lines,
            "",
            f"리포트: {report_path.name}",
            f"추천저장: {recommendation_path.name}",
        ]
    )
    return message, str(report_path), str(recommendation_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Weekly LottoAuto Kakao sender.")
    parser.add_argument("--target-date", default=date.today().isoformat())
    parser.add_argument("--candidates", type=int, default=50000)
    parser.add_argument("--seed", type=int, default=18)
    parser.add_argument("--dry-run", action="store_true", help="Print message without sending KakaoTalk.")
    parser.add_argument("--skip-refresh", action="store_true", help="Do not refresh lotto.csv before analysis.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    target_date = date.fromisoformat(args.target_date)
    if not args.skip_refresh:
        refresh_lotto_data()
    message, report_path, recommendation_path = build_analysis(target_date, args.candidates, args.seed)
    print(message)
    print(f"\nReport saved: {report_path}")
    print(f"Recommendations saved: {recommendation_path}")

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
