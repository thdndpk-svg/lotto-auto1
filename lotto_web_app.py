#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from typing import Any

from lotto_auto import (
    COMBO_FACTOR_LABELS,
    DEFAULT_COMBO_FACTORS,
    DEFAULT_NUMBER_FACTORS,
    NUMBER_FACTOR_LABELS,
    LottoAnalyzer,
    load_draws,
    parse_date,
    print_report,
)
from lotto_knowledge_net import write_knowledge_vault


APP_DIR = Path(__file__).resolve().parent
DATA_PATH = APP_DIR / "data" / "lotto.csv"
REPORT_DIR = APP_DIR / "reports"
HOST = "127.0.0.1"
PORT = 8765


MAIN_TECHNIQUES = [
    {
        "id": "same_date",
        "title": "같은 날짜",
        "subtitle": "6월 18일이면 역대 6월 18일",
        "description": "과거 같은 월/일에 나온 1등 번호를 우선 점수화합니다.",
        "numberFactors": ["same_date"],
        "comboFactors": [],
    },
    {
        "id": "shape",
        "title": "로또용지 선 패턴",
        "subtitle": "번호를 선으로 이은 모양",
        "description": "자주 나온 선 이동 방향과 비슷한 조합을 찾습니다.",
        "numberFactors": ["shape"],
        "comboFactors": ["line_shape"],
    },
    {
        "id": "skip",
        "title": "건너뛰기",
        "subtitle": "저저번주가 이번주로",
        "description": "최근 20회에서 한 주, 두 주 건너 재출현 흐름을 분석합니다.",
        "numberFactors": ["skip"],
        "comboFactors": [],
    },
    {
        "id": "front",
        "title": "앞번호",
        "subtitle": "첫 번호 반복 간격",
        "description": "조합의 시작 번호가 반복되는 주기와 흐름을 봅니다.",
        "numberFactors": ["front"],
        "comboFactors": ["front"],
    },
    {
        "id": "knowledge",
        "title": "지식그물",
        "subtitle": "번호·유형·패턴 연결망",
        "description": "번호, 동반출현, 최근 패턴, 선 모양을 연결한 지식지도 점수를 반영합니다.",
        "numberFactors": ["knowledge"],
        "comboFactors": ["knowledge_net"],
    },
]


def money(value: Any) -> str:
    try:
        amount = int(value or 0)
    except (TypeError, ValueError):
        amount = 0
    return f"{amount:,}원" if amount else "-"


def count_text(value: Any) -> str:
    try:
        count = int(value or 0)
    except (TypeError, ValueError):
        count = 0
    return f"{count:,}명" if count else "-"


def read_rows() -> list[dict[str, str]]:
    with DATA_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def latest_payload() -> dict[str, Any]:
    rows = read_rows()
    if not rows:
        raise ValueError("lotto.csv is empty")
    row = rows[-1]
    numbers = [int(row[f"n{i}"]) for i in range(1, 7)]
    return {
        "drawNo": int(row["draw_no"]),
        "date": row["date"],
        "numbers": numbers,
        "bonus": int(row["bonus"]),
        "totalRows": len(rows),
        "prizes": [
            {"rank": "1등", "winners": count_text(row.get("rnk1_winners")), "amount": money(row.get("rnk1_prize"))},
            {"rank": "2등", "winners": count_text(row.get("rnk2_winners")), "amount": money(row.get("rnk2_prize"))},
            {"rank": "3등", "winners": count_text(row.get("rnk3_winners")), "amount": money(row.get("rnk3_prize"))},
        ],
    }


def analyze_payload(request: dict[str, Any]) -> dict[str, Any]:
    target = parse_date(str(request.get("targetDate") or time.strftime("%Y-%m-%d")))
    candidates = int(request.get("candidates") or 50000)
    candidates = max(1000, min(candidates, 200000))
    seed_raw = str(request.get("seed") or "").strip()
    seed = int(seed_raw) if seed_raw else None
    number_factors = request.get("numberFactors") or list(DEFAULT_NUMBER_FACTORS)
    combo_factors = request.get("comboFactors") or list(DEFAULT_COMBO_FACTORS)

    draws = load_draws(DATA_PATH)
    analyzer = LottoAnalyzer(draws)
    front_sequence_candidates = analyzer.front_sequence_candidates()
    front_cycle_candidates = analyzer.front_cycle_candidates()
    front_anchor = None
    if "front" in number_factors or "front" in combo_factors:
        front_anchor = analyzer.front_anchor_candidate()
    ranked, diagnostics = analyzer.number_scores(
        target=target,
        window=20,
        enabled_factors=number_factors,
    )
    combos = analyzer.generate_combinations(
        ranked,
        target=target,
        count=5,
        candidates=candidates,
        pool_size=30,
        window=20,
        seed=seed,
        combo_factors=combo_factors,
        front_anchor=front_anchor.number if front_anchor else None,
    )

    report_buffer = StringIO()
    print_report(DATA_PATH, target, analyzer, ranked, diagnostics, combos, top_numbers=15, output=report_buffer)
    report = report_buffer.getvalue()

    return {
        "latest": latest_payload(),
        "targetDate": target.isoformat(),
        "sameDateMatches": [
            {
                "drawNo": draw.draw_no,
                "date": draw.draw_date.isoformat(),
                "numbers": list(draw.numbers),
                "bonus": draw.bonus,
            }
            for draw in diagnostics["same_date_matches"][-8:]
        ],
        "topShapes": [
            {"signature": " > ".join(signature), "count": count}
            for signature, count in diagnostics["top_shapes"]
        ],
        "frontAnchor": front_anchor.__dict__ if front_anchor else None,
        "frontSequenceCandidates": [candidate.__dict__ for candidate in front_sequence_candidates],
        "frontCycleCandidates": [candidate.__dict__ for candidate in front_cycle_candidates],
        "knowledgeInsights": diagnostics.get("knowledge_insights"),
        "topNumbers": [
            {
                "rank": index + 1,
                "number": item.number,
                "score": item.total,
                "factors": [
                    {"key": key, "label": NUMBER_FACTOR_LABELS.get(key, key), "score": value}
                    for key, value in sorted(item.factors.items())
                ],
            }
            for index, item in enumerate(ranked[:30])
        ],
        "combos": [
            {
                "rank": index + 1,
                "numbers": list(combo.numbers),
                "score": combo.score,
                "parts": [
                    {"key": key, "label": COMBO_FACTOR_LABELS.get(key, key), "score": value}
                    for key, value in combo.parts.items()
                ],
            }
            for index, combo in enumerate(combos)
        ],
        "active": {
            "numberFactors": number_factors,
            "comboFactors": combo_factors,
        },
        "report": report,
    }


def save_report(report: str, target_date: str) -> dict[str, str]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"analysis_{target_date}.txt"
    path.write_text(report, encoding="utf-8")
    return {"path": str(path)}


class LottoRequestHandler(BaseHTTPRequestHandler):
    server_version = "LottoAuto/2.0"

    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/?"):
            self.send_html(INDEX_HTML)
        elif self.path == "/api/latest":
            self.send_json(latest_payload())
        elif self.path == "/api/config":
            self.send_json(
                {
                    "numberFactors": NUMBER_FACTOR_LABELS,
                    "comboFactors": COMBO_FACTOR_LABELS,
                    "defaultNumberFactors": list(DEFAULT_NUMBER_FACTORS),
                    "defaultComboFactors": list(DEFAULT_COMBO_FACTORS),
                    "mainTechniques": MAIN_TECHNIQUES,
                }
            )
        elif self.path == "/api/open-folder":
            subprocess.run(["open", str(APP_DIR)], check=False)
            self.send_json({"ok": True})
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        try:
            payload = self.read_json()
            if self.path == "/api/analyze":
                self.send_json(analyze_payload(payload))
            elif self.path == "/api/refresh":
                subprocess.run(
                    [sys.executable, str(APP_DIR / "import_lotto_history_json.py")],
                    cwd=str(APP_DIR),
                    check=True,
                    text=True,
                    capture_output=True,
                )
                write_knowledge_vault(load_draws(DATA_PATH), APP_DIR / "knowledge")
                self.send_json({"ok": True, "latest": latest_payload()})
            elif self.path == "/api/save-report":
                self.send_json(save_report(str(payload.get("report") or ""), str(payload.get("targetDate") or "latest")))
            else:
                self.send_error(404)
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=500)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


INDEX_HTML = r"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lotto Auto Analyzer</title>
  <style>
    :root {
      --bg: #eef2f7;
      --panel: #ffffff;
      --ink: #17202c;
      --muted: #6a7483;
      --line: #dbe3ee;
      --blue: #2563eb;
      --green: #10b981;
      --red: #ef4444;
      --amber: #f59e0b;
      --violet: #7c3aed;
      --shadow: 0 16px 45px rgba(30, 41, 59, .12);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      background:
        linear-gradient(180deg, rgba(255,255,255,.74), rgba(238,242,247,.92)),
        radial-gradient(circle at 12% 4%, rgba(37,99,235,.16), transparent 28%),
        radial-gradient(circle at 92% 0%, rgba(16,185,129,.13), transparent 26%),
        var(--bg);
      font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Noto Sans KR", Segoe UI, sans-serif;
    }
    button, input { font: inherit; }
    .app { width: min(1480px, calc(100vw - 40px)); margin: 22px auto 36px; }
    .topbar { display: flex; align-items: center; justify-content: space-between; gap: 18px; margin-bottom: 18px; }
    .brand h1 { margin: 0; font-size: 30px; letter-spacing: 0; }
    .brand p { margin: 5px 0 0; color: var(--muted); font-size: 14px; }
    .status { padding: 9px 13px; border: 1px solid var(--line); border-radius: 999px; background: rgba(255,255,255,.78); color: var(--muted); }
    .grid { display: grid; grid-template-columns: 380px 1fr; gap: 18px; align-items: start; }
    .panel { background: rgba(255,255,255,.9); border: 1px solid rgba(219,227,238,.86); border-radius: 14px; box-shadow: var(--shadow); }
    .panel-inner { padding: 18px; }
    .latest { display: grid; grid-template-columns: 1.2fr .8fr; gap: 16px; margin-bottom: 18px; }
    .draw-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .draw-title strong { font-size: 21px; }
    .chip { color: var(--muted); border: 1px solid var(--line); background: #f8fafc; border-radius: 999px; padding: 7px 10px; font-size: 13px; }
    .balls { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 18px; }
    .ball {
      width: 44px; height: 44px; border-radius: 50%;
      display: inline-grid; place-items: center;
      font-family: Menlo, Consolas, monospace; font-weight: 800;
      color: #111827; box-shadow: inset 0 -7px 12px rgba(0,0,0,.12), 0 7px 16px rgba(15,23,42,.12);
    }
    .b-yellow { background: #f7c948; }
    .b-blue { background: #60a5fa; }
    .b-red { background: #fb7185; }
    .b-gray { background: #cbd5e1; }
    .b-green { background: #34d399; }
    .plus { font-weight: 900; color: var(--muted); padding: 0 2px; }
    .prize-table { width: 100%; border-collapse: collapse; }
    .prize-table th { color: var(--muted); font-size: 12px; text-align: right; padding: 4px 0 8px; }
    .prize-table td { text-align: right; padding: 7px 0; border-top: 1px solid #edf2f7; font-weight: 700; }
    .controls { display: grid; gap: 14px; }
    .section-title { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 12px; }
    .section-title h2 { margin: 0; font-size: 17px; }
    .section-title span { color: var(--muted); font-size: 12px; }
    label.field { display: grid; gap: 7px; margin-bottom: 11px; color: var(--muted); font-size: 13px; }
    input[type="text"], input[type="number"] {
      width: 100%; border: 1px solid var(--line); border-radius: 10px; padding: 11px 12px;
      background: #fbfdff; color: var(--ink); outline: none;
    }
    input:focus { border-color: var(--blue); box-shadow: 0 0 0 3px rgba(37,99,235,.12); }
    .main-techniques { display: grid; gap: 10px; }
    .tech-card {
      text-align: left; width: 100%; border: 1px solid var(--line); border-radius: 12px; background: #fbfdff;
      padding: 13px; cursor: pointer; display: grid; grid-template-columns: 34px 1fr; gap: 11px;
      transition: transform .12s ease, border-color .12s ease, box-shadow .12s ease, background .12s ease;
    }
    .tech-card:hover { transform: translateY(-1px); box-shadow: 0 9px 18px rgba(15,23,42,.08); }
    .tech-card.active { border-color: rgba(37,99,235,.55); background: #eff6ff; }
    .tech-mark { width: 34px; height: 34px; border-radius: 10px; display: grid; place-items: center; color: white; font-weight: 900; }
    .tech-card:nth-child(1) .tech-mark { background: var(--blue); }
    .tech-card:nth-child(2) .tech-mark { background: var(--violet); }
    .tech-card:nth-child(3) .tech-mark { background: var(--green); }
    .tech-card:nth-child(4) .tech-mark { background: var(--amber); }
    .tech-card:nth-child(5) .tech-mark { background: var(--red); }
    .tech-title { font-weight: 800; font-size: 15px; }
    .tech-subtitle { color: var(--muted); font-size: 12px; margin-top: 3px; }
    .tech-desc { color: #4b5563; font-size: 12px; margin-top: 7px; line-height: 1.45; }
    details { border-top: 1px solid #edf2f7; padding-top: 12px; }
    summary { cursor: pointer; font-weight: 800; }
    .checks { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; margin-top: 12px; }
    .check { display: flex; align-items: center; gap: 7px; color: #374151; font-size: 13px; }
    .actions { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .btn {
      border: none; border-radius: 11px; padding: 12px 14px; cursor: pointer; font-weight: 850;
      display: inline-flex; align-items: center; justify-content: center; gap: 8px;
    }
    .btn-primary { background: var(--blue); color: white; box-shadow: 0 12px 22px rgba(37,99,235,.22); }
    .btn-soft { background: #edf2f7; color: #1f2937; }
    .btn-green { background: var(--green); color: white; }
    .btn:disabled { opacity: .55; cursor: not-allowed; }
    .results { display: grid; gap: 18px; }
    .combo-list { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; }
    .combo-card { border: 1px solid var(--line); border-radius: 14px; background: #ffffff; padding: 13px; min-height: 290px; }
    .combo-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
    .combo-rank { font-weight: 900; }
    .score { color: var(--blue); font-weight: 900; }
    .combo-balls { display: flex; flex-wrap: wrap; gap: 6px; margin: 11px 0; }
    .mini-ball { width: 30px; height: 30px; font-size: 12px; }
    .ticket-pattern {
      position: relative;
      width: 100%;
      aspect-ratio: 7 / 6;
      border: 1px solid #dbe3ee;
      border-radius: 10px;
      background: linear-gradient(180deg, #fff, #fbfdff);
      overflow: hidden;
      margin: 10px 0 12px;
    }
    .ticket-grid {
      position: absolute;
      inset: 0;
      display: grid;
      grid-template-columns: repeat(7, 1fr);
      grid-template-rows: repeat(7, 1fr);
      z-index: 1;
    }
    .ticket-cell {
      display: grid;
      place-items: center;
      border-right: 1px solid #edf2f7;
      border-bottom: 1px solid #edf2f7;
      color: #d1495b;
      font: 700 9px Menlo, Consolas, monospace;
      position: relative;
    }
    .ticket-cell:nth-child(7n) { border-right: none; }
    .ticket-cell:nth-child(n+43) { border-bottom: none; }
    .ticket-cell.selected {
      color: #111827;
      font-weight: 900;
      text-shadow: 0 1px 0 rgba(255,255,255,.72);
    }
    .ticket-cell.selected::after {
      content: "";
      position: absolute;
      width: 21px;
      height: 21px;
      border-radius: 50%;
      background: rgba(37, 99, 235, .16);
      border: 2px solid rgba(37, 99, 235, .58);
      z-index: -1;
    }
    .ticket-line {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      z-index: 2;
      pointer-events: none;
    }
    .ticket-line polyline {
      fill: none;
      stroke: #1d4ed8;
      stroke-width: 2.8;
      stroke-linecap: round;
      stroke-linejoin: round;
      filter: drop-shadow(0 2px 2px rgba(15, 23, 42, .18));
    }
    .ticket-line circle {
      fill: #64748b;
      stroke: white;
      stroke-width: 1.5;
    }
    .part { margin-top: 7px; display: grid; grid-template-columns: 74px 1fr 44px; gap: 8px; align-items: center; color: var(--muted); font-size: 12px; }
    .bar { height: 7px; border-radius: 999px; background: #e5e7eb; overflow: hidden; }
    .bar span { display: block; height: 100%; background: linear-gradient(90deg, var(--green), var(--blue)); }
    .insight-grid { display: grid; grid-template-columns: .88fr 1.12fr; gap: 16px; }
    .number-table { width: 100%; border-collapse: collapse; }
    .number-table th { color: var(--muted); font-size: 12px; text-align: left; border-bottom: 1px solid var(--line); padding: 9px 8px; }
    .number-table td { border-bottom: 1px solid #edf2f7; padding: 9px 8px; vertical-align: top; }
    .number-pill { display: inline-grid; place-items: center; width: 34px; height: 34px; border-radius: 50%; font-family: Menlo, monospace; font-weight: 900; }
    .small-list { display: grid; gap: 8px; }
    .small-item { display: flex; align-items: center; justify-content: space-between; gap: 10px; border: 1px solid #edf2f7; border-radius: 10px; padding: 10px; background: #fbfdff; }
    .anchor-box {
      border: 1px solid rgba(37,99,235,.28);
      background: #eff6ff;
      border-radius: 12px;
      padding: 12px;
      margin-bottom: 12px;
    }
    .anchor-box strong { font-size: 16px; }
    .anchor-box p { margin: 6px 0 0; color: #334155; font-size: 13px; line-height: 1.45; }
    .report {
      white-space: pre-wrap; max-height: 300px; overflow: auto; border: 1px solid var(--line); border-radius: 12px;
      padding: 13px; background: #0f172a; color: #dbeafe; font-family: Menlo, Consolas, monospace; font-size: 12px; line-height: 1.55;
    }
    .toast { min-height: 22px; color: var(--muted); font-size: 13px; }
    @media (max-width: 1180px) {
      .grid, .latest, .insight-grid { grid-template-columns: 1fr; }
      .combo-list { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 720px) {
      .app { width: calc(100vw - 20px); margin-top: 10px; }
      .combo-list, .checks { grid-template-columns: 1fr; }
      .actions { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main class="app">
    <div class="topbar">
      <div class="brand">
        <h1>Lotto Auto Analyzer</h1>
        <p>같은 날짜, 선 패턴, 건너뛰기, 앞번호 중심의 조합 분석 대시보드</p>
      </div>
      <div id="status" class="status">준비됨</div>
    </div>

    <section class="latest">
      <div class="panel"><div class="panel-inner">
        <div class="draw-title">
          <strong id="latestTitle">최신 회차 로딩 중</strong>
          <span id="latestRows" class="chip"></span>
        </div>
        <div id="latestBalls" class="balls"></div>
      </div></div>
      <div class="panel"><div class="panel-inner">
        <div class="section-title"><h2>저번주 당첨 정보</h2><span>1인 기준</span></div>
        <table class="prize-table"><thead><tr><th>등수</th><th>당첨자</th><th>당첨금</th></tr></thead><tbody id="prizeBody"></tbody></table>
      </div></div>
    </section>

    <section class="grid">
      <aside class="panel"><div class="panel-inner controls">
        <div>
          <div class="section-title"><h2>분석 설정</h2><span>원하는 조건만 켜기</span></div>
          <label class="field">기준일<input id="targetDate" type="text"></label>
          <label class="field">후보 조합 수<input id="candidates" type="number" value="50000" min="1000" max="200000" step="1000"></label>
          <label class="field">시드<input id="seed" type="text" value="18"></label>
        </div>

        <div>
          <div class="section-title"><h2>메인 기법</h2><span>중요 기법 따로 배치</span></div>
          <div id="mainTechniques" class="main-techniques"></div>
        </div>

        <details open>
          <summary>보조 번호 기법</summary>
          <div id="numberChecks" class="checks"></div>
        </details>
        <details>
          <summary>조합 필터</summary>
          <div id="comboChecks" class="checks"></div>
        </details>

        <div class="actions">
          <button id="analyzeBtn" class="btn btn-primary">분석 실행</button>
          <button id="refreshBtn" class="btn btn-green">데이터 갱신</button>
          <button id="saveBtn" class="btn btn-soft">리포트 저장</button>
          <button id="folderBtn" class="btn btn-soft">폴더 열기</button>
        </div>
        <div id="toast" class="toast"></div>
      </div></aside>

      <section class="results">
        <div class="panel"><div class="panel-inner">
          <div class="section-title"><h2>추천 조합 TOP 5</h2><span id="activeSummary">분석 전</span></div>
          <div id="comboList" class="combo-list"></div>
        </div></div>

        <div class="insight-grid">
          <div class="panel"><div class="panel-inner">
            <div class="section-title"><h2>번호 점수 TOP 15</h2><span>100점 환산</span></div>
            <table class="number-table"><thead><tr><th>#</th><th>번호</th><th>점수</th><th>강점</th></tr></thead><tbody id="numberBody"></tbody></table>
          </div></div>
          <div class="panel"><div class="panel-inner">
            <div class="section-title"><h2>패턴 근거</h2><span>같은 날짜 / 선 모양</span></div>
            <div id="evidence" class="small-list"></div>
          </div></div>
        </div>

        <div class="panel"><div class="panel-inner">
          <div class="section-title"><h2>상세 리포트</h2><span>저장 가능</span></div>
          <div id="report" class="report">아직 분석 전입니다. 왼쪽에서 기법을 선택하고 분석 실행을 눌러주세요.</div>
        </div></div>
      </section>
    </section>
  </main>

  <script>
    const state = { config: null, latest: null, lastResult: null };
    const $ = (id) => document.getElementById(id);

    function ballClass(n) {
      if (n <= 10) return "b-yellow";
      if (n <= 20) return "b-blue";
      if (n <= 30) return "b-red";
      if (n <= 40) return "b-gray";
      return "b-green";
    }
    function ball(n, mini=false) {
      return `<span class="ball ${mini ? "mini-ball" : ""} ${ballClass(n)}">${String(n).padStart(2, "0")}</span>`;
    }
    function ticketPattern(numbers) {
      const selected = new Set(numbers);
      const sorted = [...numbers].sort((a, b) => a - b);
      const points = sorted.map(n => {
        const col = (n - 1) % 7;
        const row = Math.floor((n - 1) / 7);
        return `${((col + 0.5) / 7 * 100).toFixed(3)},${((row + 0.5) / 7 * 100).toFixed(3)}`;
      }).join(" ");
      const dots = sorted.map(n => {
        const col = (n - 1) % 7;
        const row = Math.floor((n - 1) / 7);
        return `<circle cx="${((col + 0.5) / 7 * 100).toFixed(3)}" cy="${((row + 0.5) / 7 * 100).toFixed(3)}" r="2.1"></circle>`;
      }).join("");
      const cells = Array.from({length: 45}, (_, i) => {
        const n = i + 1;
        return `<span class="ticket-cell ${selected.has(n) ? "selected" : ""}">${String(n).padStart(2, "0")}</span>`;
      }).join("");
      return `<div class="ticket-pattern">
        <div class="ticket-grid">${cells}</div>
        <svg class="ticket-line" viewBox="0 0 100 100" preserveAspectRatio="none">
          <polyline points="${points}"></polyline>${dots}
        </svg>
      </div>`;
    }
    function setStatus(text) { $("status").textContent = text; }
    function toast(text) { $("toast").textContent = text; }
    function checkedValues(name) {
      return [...document.querySelectorAll(`input[name="${name}"]:checked`)].map(el => el.value);
    }
    async function getJson(url) {
      const res = await fetch(url);
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    }
    async function postJson(url, payload={}) {
      const res = await fetch(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
      const data = await res.json();
      if (!res.ok || data.ok === false) throw new Error(data.error || "요청 실패");
      return data;
    }
    function renderLatest(latest) {
      $("latestTitle").textContent = `${latest.drawNo}회  ${latest.date}`;
      $("latestRows").textContent = `총 ${latest.totalRows.toLocaleString()}회차`;
      $("latestBalls").innerHTML = latest.numbers.map(n => ball(n)).join("") + `<span class="plus">+</span>` + ball(latest.bonus);
      $("prizeBody").innerHTML = latest.prizes.map(p => `<tr><td>${p.rank}</td><td>${p.winners}</td><td>${p.amount}</td></tr>`).join("");
    }
    function renderChecks() {
      const cfg = state.config;
      $("mainTechniques").innerHTML = cfg.mainTechniques.map((t, i) => `
        <button class="tech-card active" data-number="${t.numberFactors.join(",")}" data-combo="${t.comboFactors.join(",")}">
          <span class="tech-mark">${i + 1}</span>
          <span><span class="tech-title">${t.title}</span><span class="tech-subtitle">${t.subtitle}</span><span class="tech-desc">${t.description}</span></span>
        </button>`).join("");

      const mainNumber = new Set(cfg.mainTechniques.flatMap(t => t.numberFactors));
      $("numberChecks").innerHTML = Object.entries(cfg.numberFactors)
        .filter(([key]) => !mainNumber.has(key))
        .map(([key, label]) => `<label class="check"><input type="checkbox" name="numberFactor" value="${key}" ${cfg.defaultNumberFactors.includes(key) ? "checked" : ""}>${label}</label>`)
        .join("");
      $("comboChecks").innerHTML = Object.entries(cfg.comboFactors)
        .map(([key, label]) => `<label class="check"><input type="checkbox" name="comboFactor" value="${key}" ${cfg.defaultComboFactors.includes(key) ? "checked" : ""}>${label}</label>`)
        .join("");

      document.querySelectorAll(".tech-card").forEach(btn => btn.addEventListener("click", () => {
        btn.classList.toggle("active");
        syncTechniqueComboChecks();
      }));
      syncTechniqueComboChecks();
    }
    function selectedMainFactors() {
      const active = [...document.querySelectorAll(".tech-card.active")];
      return {
        number: active.flatMap(btn => btn.dataset.number.split(",").filter(Boolean)),
        combo: active.flatMap(btn => btn.dataset.combo.split(",").filter(Boolean))
      };
    }
    function syncTechniqueComboChecks() {
      const selected = selectedMainFactors();
      document.querySelectorAll('input[name="comboFactor"]').forEach(input => {
        if (selected.combo.includes(input.value)) input.checked = true;
      });
    }
    function selectedFactors() {
      const main = selectedMainFactors();
      return {
        numberFactors: [...new Set([...main.number, ...checkedValues("numberFactor")])],
        comboFactors: [...new Set([...main.combo, ...checkedValues("comboFactor")])]
      };
    }
    function renderCombos(combos) {
      $("comboList").innerHTML = combos.map(c => `
        <article class="combo-card">
          <div class="combo-head"><span class="combo-rank">${c.rank}위</span><span class="score">${c.score.toFixed(2)}점</span></div>
          <div class="combo-balls">${c.numbers.map(n => ball(n, true)).join("")}</div>
          ${ticketPattern(c.numbers)}
          ${c.parts.filter(p => p.key !== "history_penalty").slice(0, 5).map(p => `
            <div class="part"><span>${p.label}</span><span class="bar"><span style="width:${Math.max(4, Math.min(100, Math.abs(p.score) * 8))}%"></span></span><b>${p.score > 0 ? "+" : ""}${p.score.toFixed(1)}</b></div>
          `).join("")}
        </article>`).join("");
    }
    function renderNumbers(numbers) {
      $("numberBody").innerHTML = numbers.slice(0, 15).map(n => `
        <tr>
          <td>${n.rank}</td>
          <td>${ball(n.number, true)}</td>
          <td><b>${n.score.toFixed(2)}</b></td>
          <td>${n.factors.slice(0, 4).map(f => `${f.label} ${f.score.toFixed(1)}`).join(", ")}</td>
        </tr>`).join("");
    }
    function renderEvidence(result) {
      const anchor = result.frontAnchor
        ? `<div class="anchor-box"><strong>공통 앞번호 앵커: ${String(result.frontAnchor.number).padStart(2, "0")}번</strong><p>${result.frontAnchor.reason} · 점수 ${result.frontAnchor.score.toFixed(2)} · 신뢰도 ${(result.frontAnchor.confidence * 100).toFixed(0)}%</p></div>`
        : `<div class="anchor-box"><strong>공통 앞번호 앵커 없음</strong><p>최근 앞번호 순서와 같은 과거 패턴에서 확실한 다음 번호가 잡히지 않아 조합별 점수 방식으로 생성했습니다.</p></div>`;
      const knowledge = result.knowledgeInsights || {};
      const knowledgeNumbers = (knowledge.topNumbers || []).slice(0, 6).map(n => `
        <div class="small-item"><span>${String(n.number).padStart(2, "0")}번 · 전체 ${n.count}회 · 최근 ${n.recentCount}회</span><b>${n.score.toFixed(1)}점</b></div>
      `).join("") || `<div class="small-item"><span>지식그물 번호 없음</span><b>-</b></div>`;
      const knowledgePatterns = (knowledge.recentPatterns || []).slice(0, 5).map(p => `
        <div class="small-item"><span>${p.label}</span><b>${p.count}/${p.allCount}회</b></div>
      `).join("") || `<div class="small-item"><span>최근 패턴 없음</span><b>-</b></div>`;
      const knowledgePairs = (knowledge.topPairs || []).slice(0, 5).map(p => `
        <div class="small-item"><span>${String(p.numbers[0]).padStart(2, "0")} + ${String(p.numbers[1]).padStart(2, "0")}</span><b>${p.count}회</b></div>
      `).join("") || `<div class="small-item"><span>동반출현 없음</span><b>-</b></div>`;
      const sequences = result.frontSequenceCandidates.slice(0, 5).map(c => `
        <div class="small-item"><span>${c.pattern.map(n => String(n).padStart(2, "0")).join(" → ")} → ${String(c.number).padStart(2, "0")} · ${c.hit_count}/${c.support}회</span><b>${c.score.toFixed(1)}점</b></div>
      `).join("") || `<div class="small-item"><span>같은 순서 패턴 없음</span><b>-</b></div>`;
      const cycles = result.frontCycleCandidates.slice(0, 3).map(c => `
        <div class="small-item"><span>${String(c.number).padStart(2, "0")}번 · ${c.reason}</span><b>${c.score.toFixed(1)}점</b></div>
      `).join("");
      const same = result.sameDateMatches.map(d => `
        <div class="small-item"><span>${d.drawNo}회 ${d.date}</span><span>${d.numbers.map(n => String(n).padStart(2, "0")).join(" ")}</span></div>
      `).join("") || `<div class="small-item"><span>같은 날짜 데이터 없음</span><span>-</span></div>`;
      const shapes = result.topShapes.map(s => `
        <div class="small-item"><span>${s.signature}</span><b>${s.count}회</b></div>
      `).join("");
      $("evidence").innerHTML = `${anchor}<b>지식그물 중심 번호</b>${knowledgeNumbers}<b style="margin-top:10px;display:block">지식그물 최근 패턴</b>${knowledgePatterns}<b style="margin-top:10px;display:block">지식그물 동반출현</b>${knowledgePairs}<b style="margin-top:10px;display:block">앞번호 순서 패턴 후보</b>${sequences}<b style="margin-top:10px;display:block">앞번호 간격 참고</b>${cycles}<b style="margin-top:10px;display:block">같은 날짜</b>${same}<b style="margin-top:10px;display:block">선 모양 TOP</b>${shapes}`;
    }
    async function analyze() {
      const factors = selectedFactors();
      if (!factors.numberFactors.length) return toast("번호 기법을 하나 이상 켜주세요.");
      if (!factors.comboFactors.length) return toast("조합 필터를 하나 이상 켜주세요.");
      setBusy(true, "분석 중...");
      try {
        const result = await postJson("/api/analyze", {
          targetDate: $("targetDate").value,
          candidates: Number($("candidates").value || 50000),
          seed: $("seed").value,
          numberFactors: factors.numberFactors,
          comboFactors: factors.comboFactors
        });
        state.lastResult = result;
        renderLatest(result.latest);
        renderCombos(result.combos);
        renderNumbers(result.topNumbers);
        renderEvidence(result);
        $("report").textContent = result.report;
        $("activeSummary").textContent = `${factors.numberFactors.length}개 번호 기법 · ${factors.comboFactors.length}개 조합 필터`;
        toast("분석 완료");
      } catch (err) {
        toast(err.message);
        $("report").textContent = err.stack || err.message;
      } finally {
        setBusy(false, "준비됨");
      }
    }
    function setBusy(isBusy, label) {
      setStatus(label);
      $("analyzeBtn").disabled = isBusy;
      $("refreshBtn").disabled = isBusy;
    }
    async function refreshData() {
      setBusy(true, "데이터 갱신 중...");
      try {
        const data = await postJson("/api/refresh", {});
        state.latest = data.latest;
        renderLatest(data.latest);
        toast("데이터 갱신 완료");
      } catch (err) {
        toast(err.message);
      } finally {
        setBusy(false, "준비됨");
      }
    }
    async function saveReport() {
      if (!state.lastResult) return toast("먼저 분석을 실행해주세요.");
      const saved = await postJson("/api/save-report", {report: state.lastResult.report, targetDate: state.lastResult.targetDate});
      toast(`저장됨: ${saved.path}`);
    }
    async function boot() {
      $("targetDate").value = new Date().toISOString().slice(0, 10);
      state.config = await getJson("/api/config");
      state.latest = await getJson("/api/latest");
      renderChecks();
      renderLatest(state.latest);
      $("analyzeBtn").addEventListener("click", analyze);
      $("refreshBtn").addEventListener("click", refreshData);
      $("saveBtn").addEventListener("click", saveReport);
      $("folderBtn").addEventListener("click", () => getJson("/api/open-folder"));
      toast("원하는 기법을 고르고 분석 실행을 누르세요.");
    }
    boot().catch(err => { setStatus("오류"); toast(err.message); });
  </script>
</body>
</html>
"""


def open_existing_or_serve() -> int:
    try:
        server = ThreadingHTTPServer((HOST, PORT), LottoRequestHandler)
    except OSError:
        webbrowser.open(f"http://{HOST}:{PORT}/")
        return 0

    url = f"http://{HOST}:{PORT}/"
    threading.Thread(target=lambda: (time.sleep(0.4), webbrowser.open(url)), daemon=True).start()
    print(f"Lotto Auto running at {url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(open_existing_or_serve())
