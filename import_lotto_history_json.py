#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Iterable, List


DEFAULT_URL = "https://raw.githubusercontent.com/DDARK00/Korean-Lotto/main/data/lotto_history.json"
FIRST_DRAW_DATE = date(2002, 12, 7)


def load_json_from_url(url: str) -> List[Dict[str, int]]:
    request = urllib.request.Request(url, headers={"User-Agent": "LottoAutoAnalyzer/1.0"})
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.load(response)


def draw_date(draw_no: int) -> date:
    return FIRST_DRAW_DATE + timedelta(days=(draw_no - 1) * 7)


def write_standard_csv(rows: Iterable[Dict[str, int]], output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "draw_no",
                "date",
                "n1",
                "n2",
                "n3",
                "n4",
                "n5",
                "n6",
                "bonus",
                "rnk1_winners",
                "rnk1_prize",
                "rnk2_winners",
                "rnk2_prize",
                "rnk3_winners",
                "rnk3_prize",
            ]
        )
        for item in sorted(rows, key=lambda x: int(x["ltEpsd"])):
            draw_no = int(item["ltEpsd"])
            writer.writerow(
                [
                    draw_no,
                    draw_date(draw_no).isoformat(),
                    int(item["tm1WnNo"]),
                    int(item["tm2WnNo"]),
                    int(item["tm3WnNo"]),
                    int(item["tm4WnNo"]),
                    int(item["tm5WnNo"]),
                    int(item["tm6WnNo"]),
                    int(item["bnsWnNo"]),
                    int(item.get("rnk1WnNope", 0)),
                    int(item.get("rnk1WnAmt", 0)),
                    int(item.get("rnk2WnNope", 0)),
                    int(item.get("rnk2WnAmt", 0)),
                    int(item.get("rnk3WnNope", 0)),
                    int(item.get("rnk3WnAmt", 0)),
                ]
            )
            count += 1
    return count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import lotto_history.json into data/lotto.csv.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", default="data/lotto.csv")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    base_dir = Path(__file__).resolve().parent
    output = Path(args.output)
    if not output.is_absolute():
        output = base_dir / output
    rows = load_json_from_url(args.url)
    count = write_standard_csv(rows, output)
    first = min(int(row["ltEpsd"]) for row in rows)
    latest = max(int(row["ltEpsd"]) for row in rows)
    print(f"saved {count} rows to {output}")
    print(f"first draw: {first} {draw_date(first).isoformat()}")
    print(f"latest draw: {latest} {draw_date(latest).isoformat()}")
    print(f"source: {args.url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
