#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional


OFFICIAL_API = "https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo={draw_no}"


@dataclass(frozen=True)
class LottoRow:
    draw_no: int
    date: str
    n1: int
    n2: int
    n3: int
    n4: int
    n5: int
    n6: int
    bonus: int


def fetch_json(draw_no: int, timeout: float) -> Optional[Dict[str, object]]:
    url = OFFICIAL_API.format(draw_no=draw_no)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 LottoAutoAnalyzer/1.0",
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://www.dhlottery.co.kr/gameResult.do?method=byWin",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", "replace")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        snippet = body[:200].replace("\n", " ")
        raise RuntimeError(f"Unexpected non-JSON response for draw {draw_no}: {snippet}") from exc


def json_to_row(payload: Dict[str, object]) -> Optional[LottoRow]:
    if payload.get("returnValue") != "success":
        return None
    return LottoRow(
        draw_no=int(payload["drwNo"]),
        date=str(payload["drwNoDate"]),
        n1=int(payload["drwtNo1"]),
        n2=int(payload["drwtNo2"]),
        n3=int(payload["drwtNo3"]),
        n4=int(payload["drwtNo4"]),
        n5=int(payload["drwtNo5"]),
        n6=int(payload["drwtNo6"]),
        bonus=int(payload["bnusNo"]),
    )


def find_latest_draw(max_probe: int, timeout: float, sleep: float) -> int:
    low = 1
    high = max_probe
    latest = 0
    while low <= high:
        mid = (low + high) // 2
        payload = fetch_json(mid, timeout)
        row = json_to_row(payload or {})
        time.sleep(sleep)
        if row:
            latest = mid
            low = mid + 1
        else:
            high = mid - 1
    if latest <= 0:
        raise RuntimeError("Could not find latest draw number.")
    return latest


def fetch_rows(start: int, end: int, timeout: float, sleep: float) -> List[LottoRow]:
    rows: List[LottoRow] = []
    failures = []
    for draw_no in range(start, end + 1):
        try:
            payload = fetch_json(draw_no, timeout)
            row = json_to_row(payload or {})
            if row:
                rows.append(row)
            else:
                failures.append(draw_no)
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            failures.append(draw_no)
            print(f"warn: draw {draw_no} failed: {exc}")
        time.sleep(sleep)
    if failures:
        print(f"warn: {len(failures)} draw(s) failed or unavailable: {failures[:12]}")
    return rows


def write_csv(rows: Iterable[LottoRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["draw_no", "date", "n1", "n2", "n3", "n4", "n5", "n6", "bonus"])
        for row in rows:
            writer.writerow([row.draw_no, row.date, row.n1, row.n2, row.n3, row.n4, row.n5, row.n6, row.bonus])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch Lotto 6/45 draw data from dhlottery.")
    parser.add_argument("--output", default="data/lotto.csv", help="CSV output path.")
    parser.add_argument("--start", type=int, default=1, help="First draw number.")
    parser.add_argument("--end", type=int, default=None, help="Last draw number. If omitted, probe latest.")
    parser.add_argument("--max-probe", type=int, default=1400, help="Upper bound used when finding latest.")
    parser.add_argument("--timeout", type=float, default=12.0, help="HTTP timeout in seconds.")
    parser.add_argument("--sleep", type=float, default=0.08, help="Delay between requests.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    base_dir = Path(__file__).resolve().parent
    output = Path(args.output)
    if not output.is_absolute():
        output = base_dir / output
    end = args.end
    if end is None:
        end = find_latest_draw(args.max_probe, args.timeout, args.sleep)
    rows = fetch_rows(args.start, end, args.timeout, args.sleep)
    if not rows:
        raise SystemExit("No data was fetched.")
    write_csv(rows, output)
    print(f"saved {len(rows)} rows to {output}")
    print(f"first draw: {rows[0].draw_no} {rows[0].date}")
    print(f"latest draw: {rows[-1].draw_no} {rows[-1].date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
