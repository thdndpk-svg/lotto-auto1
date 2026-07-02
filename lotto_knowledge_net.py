#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from itertools import combinations
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Sequence


LOTTO_MIN = 1
LOTTO_MAX = 45
PICK_COUNT = 6
DEFAULT_RECENT_WINDOW = 20


@dataclass
class KnowledgeMetrics:
    draw_count: int
    number_scores: dict[int, float]
    number_counts: Counter
    recent_number_counts: Counter
    pattern_counts: Counter
    recent_pattern_counts: Counter
    number_pattern_counts: dict[int, Counter]
    pattern_number_counts: dict[str, Counter]
    pair_counts: Counter
    skip_repeat_rates: dict[tuple[int, int], float]
    grid_cols: int


def safe_ratio(value: float, high: float) -> float:
    if high <= 0:
        return 0.0
    return max(0.0, min(1.0, value / high))


def bucket_label(prefix: str, value: int, width: int) -> str:
    low = (value // width) * width
    high = low + width - 1
    return f"{prefix}-{low:03d}-{high:03d}"


def coord(number: int, grid_cols: int = 7) -> tuple[int, int]:
    return ((number - 1) % grid_cols, (number - 1) // grid_cols)


def shape_signature(numbers: Sequence[int], grid_cols: int = 7) -> tuple[str, ...]:
    coords = [coord(n, grid_cols) for n in sorted(numbers)]
    moves = []
    for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
        dx = x2 - x1
        dy = y2 - y1
        sx = "R" if dx > 0 else "L" if dx < 0 else "S"
        sy = "D" if dy > 0 else "U" if dy < 0 else "S"
        dist = min(6, abs(dx) + abs(dy))
        moves.append(f"{sx}{sy}{dist}")
    return tuple(moves)


def consecutive_count(numbers: Sequence[int]) -> int:
    nums = sorted(numbers)
    return sum(1 for a, b in zip(nums, nums[1:]) if b == a + 1)


def pattern_nodes(numbers: Sequence[int], grid_cols: int = 7) -> list[str]:
    nums = tuple(sorted(numbers))
    odd_count = sum(n % 2 for n in nums)
    low_count = sum(n <= 22 for n in nums)
    ending_dup = PICK_COUNT - len({n % 10 for n in nums})
    shape = "-".join(shape_signature(nums, grid_cols))
    return [
        bucket_label("sum", sum(nums), 30),
        f"odd-even-{odd_count}-{PICK_COUNT - odd_count}",
        f"low-high-{low_count}-{PICK_COUNT - low_count}",
        f"ending-dup-{ending_dup}",
        f"consecutive-{consecutive_count(nums)}",
        f"front-{nums[0]:02d}",
        f"shape-{shape}",
    ]


def pattern_title(key: str) -> str:
    if key.startswith("sum-"):
        return key.replace("sum-", "번호합 ")
    if key.startswith("odd-even-"):
        _, _, odd, even = key.split("-")
        return f"홀짝 {odd}:{even}"
    if key.startswith("low-high-"):
        _, _, low, high = key.split("-")
        return f"저고 {low}:{high}"
    if key.startswith("ending-dup-"):
        return f"끝수 중복 {key.rsplit('-', 1)[-1]}개"
    if key.startswith("consecutive-"):
        return f"연속수 {key.rsplit('-', 1)[-1]}개"
    if key.startswith("front-"):
        return f"앞번호 {key.rsplit('-', 1)[-1]}번"
    if key.startswith("shape-"):
        return "선패턴 " + key.removeprefix("shape-").replace("-", " > ")
    return key


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9가-힣]+", "-", value)
    return re.sub(r"-+", "-", value).strip("-") or "untitled"


def pattern_slug(key: str) -> str:
    return "pattern-" + slugify(key)


def number_slug(number: int) -> str:
    return f"number-{number:02d}"


def build_knowledge_metrics(
    draws: Sequence[Any],
    grid_cols: int = 7,
    recent_window: int = DEFAULT_RECENT_WINDOW,
) -> KnowledgeMetrics:
    draw_list = list(draws)
    number_counts = Counter()
    recent_number_counts = Counter()
    pattern_counts = Counter()
    recent_pattern_counts = Counter()
    number_pattern_counts: dict[int, Counter] = {n: Counter() for n in range(LOTTO_MIN, LOTTO_MAX + 1)}
    pattern_number_counts: dict[str, Counter] = defaultdict(Counter)
    pair_counts = Counter()

    recent_start = max(0, len(draw_list) - max(1, recent_window))
    for index, draw in enumerate(draw_list):
        numbers = tuple(sorted(int(n) for n in draw.numbers))
        patterns = pattern_nodes(numbers, grid_cols)
        number_counts.update(numbers)
        pattern_counts.update(patterns)
        for number in numbers:
            number_pattern_counts[number].update(patterns)
            for pattern in patterns:
                pattern_number_counts[pattern][number] += 1
        for pair in combinations(numbers, 2):
            pair_counts[pair] += 1
        if index >= recent_start:
            recent_number_counts.update(numbers)
            recent_pattern_counts.update(patterns)

    source_counts = Counter()
    repeat_counts = Counter()
    for gap in (1, 2, 3):
        for index in range(gap, len(draw_list)):
            source = set(draw_list[index - gap].numbers)
            target = set(draw_list[index].numbers)
            for number in source:
                key = (gap, int(number))
                source_counts[key] += 1
                if number in target:
                    repeat_counts[key] += 1

    skip_repeat_rates = {
        key: repeat_counts[key] / source_counts[key]
        for key in source_counts
        if source_counts[key]
    }

    frequency_high = max(number_counts.values(), default=1)
    recent_high = max(recent_number_counts.values(), default=1)
    pair_high = max(pair_counts.values(), default=1)
    recent_pattern_high = max(recent_pattern_counts.values(), default=1)

    recent_hot_numbers = {number for number, _ in recent_number_counts.most_common(10)}
    number_scores: dict[int, float] = {}
    for number in range(LOTTO_MIN, LOTTO_MAX + 1):
        frequency_part = safe_ratio(number_counts[number], frequency_high)
        recent_part = safe_ratio(recent_number_counts[number], recent_high)

        affinity_weight = 0.0
        affinity_total = 0.0
        for pattern, recent_count in recent_pattern_counts.items():
            weight = safe_ratio(recent_count, recent_pattern_high)
            affinity_weight += weight
            high_for_pattern = max(pattern_number_counts[pattern].values(), default=1)
            affinity_total += weight * safe_ratio(number_pattern_counts[number][pattern], high_for_pattern)
        pattern_part = affinity_total / affinity_weight if affinity_weight else 0.0

        co_scores = []
        for hot_number in recent_hot_numbers:
            if hot_number == number:
                continue
            pair = tuple(sorted((number, hot_number)))
            co_scores.append(safe_ratio(pair_counts[pair], pair_high))
        co_part = mean(co_scores) if co_scores else 0.0

        skip_part = 0.0
        skip_weights = {1: 0.70, 2: 1.00, 3: 0.65}
        for gap, weight in skip_weights.items():
            if len(draw_list) >= gap and number in draw_list[-gap].numbers:
                skip_part += weight * skip_repeat_rates.get((gap, number), 0.0)
        skip_part = safe_ratio(skip_part, sum(skip_weights.values()))

        score = 100.0 * (
            frequency_part * 0.20
            + recent_part * 0.18
            + pattern_part * 0.30
            + co_part * 0.20
            + skip_part * 0.12
        )
        number_scores[number] = round(score, 2)

    return KnowledgeMetrics(
        draw_count=len(draw_list),
        number_scores=number_scores,
        number_counts=number_counts,
        recent_number_counts=recent_number_counts,
        pattern_counts=pattern_counts,
        recent_pattern_counts=recent_pattern_counts,
        number_pattern_counts=number_pattern_counts,
        pattern_number_counts=dict(pattern_number_counts),
        pair_counts=pair_counts,
        skip_repeat_rates=skip_repeat_rates,
        grid_cols=grid_cols,
    )


def combo_knowledge_points(
    combo: Sequence[int],
    metrics: KnowledgeMetrics,
    max_points: float = 6.0,
) -> float:
    numbers = tuple(sorted(int(n) for n in combo))
    avg_number = mean(metrics.number_scores.get(n, 0.0) for n in numbers) / 100.0

    pair_high = max(metrics.pair_counts.values(), default=1)
    pair_scores = [
        safe_ratio(metrics.pair_counts[tuple(sorted(pair))], pair_high)
        for pair in combinations(numbers, 2)
    ]
    pair_part = mean(pair_scores) if pair_scores else 0.0

    pattern_high = max(metrics.pattern_counts.values(), default=1)
    recent_pattern_high = max(metrics.recent_pattern_counts.values(), default=1)
    patterns = pattern_nodes(numbers, metrics.grid_cols)
    pattern_part = mean(safe_ratio(metrics.pattern_counts[p], pattern_high) for p in patterns)
    recent_part = mean(safe_ratio(metrics.recent_pattern_counts[p], recent_pattern_high) for p in patterns)

    score = max_points * (
        avg_number * 0.38
        + pair_part * 0.26
        + pattern_part * 0.24
        + recent_part * 0.12
    )
    return round(max(0.0, min(max_points, score)), 2)


def knowledge_insights(metrics: KnowledgeMetrics, top_n: int = 8) -> dict[str, Any]:
    top_numbers = [
        {
            "number": number,
            "score": score,
            "count": metrics.number_counts[number],
            "recentCount": metrics.recent_number_counts[number],
        }
        for number, score in sorted(metrics.number_scores.items(), key=lambda item: (-item[1], item[0]))[:top_n]
    ]
    top_patterns = [
        {
            "key": key,
            "slug": pattern_slug(key),
            "label": pattern_title(key),
            "count": count,
            "recentCount": metrics.recent_pattern_counts[key],
        }
        for key, count in metrics.pattern_counts.most_common(top_n)
    ]
    top_pairs = [
        {"numbers": list(pair), "count": count}
        for pair, count in metrics.pair_counts.most_common(top_n)
    ]
    recent_patterns = [
        {
            "key": key,
            "slug": pattern_slug(key),
            "label": pattern_title(key),
            "count": count,
            "allCount": metrics.pattern_counts[key],
        }
        for key, count in metrics.recent_pattern_counts.most_common(top_n)
    ]
    return {
        "drawCount": metrics.draw_count,
        "topNumbers": top_numbers,
        "topPatterns": top_patterns,
        "topPairs": top_pairs,
        "recentPatterns": recent_patterns,
    }


def yaml_list(values: Iterable[str]) -> str:
    items = list(values)
    if not items:
        return "[]"
    return "[" + ", ".join(json.dumps(item, ensure_ascii=False) for item in items) + "]"


def page(frontmatter: dict[str, Any], body: str) -> str:
    lines = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, list):
            lines.append(f"{key}: {yaml_list(str(v) for v in value)}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    lines.append(body.strip())
    lines.append("")
    return "\n".join(lines)


def build_number_page(number: int, metrics: KnowledgeMetrics, today: str) -> str:
    patterns = metrics.number_pattern_counts[number].most_common(10)
    pairs = [
        (pair, count)
        for pair, count in metrics.pair_counts.most_common()
        if number in pair
    ][:8]
    body = [
        f"# {number:02d}번",
        "",
        f"- 전체 출현: {metrics.number_counts[number]}회",
        f"- 최근 출현: {metrics.recent_number_counts[number]}회",
        f"- 지식그물 점수: {metrics.number_scores[number]:.2f}",
        "",
        "## 자주 연결된 패턴",
    ]
    body.extend(
        f"- [[{pattern_slug(key)}|{pattern_title(key)}]] — {count}회"
        for key, count in patterns
    )
    body.append("")
    body.append("## 자주 같이 나온 번호")
    body.extend(
        f"- [[{number_slug(pair[0] if pair[1] == number else pair[1])}]] — {count}회"
        for pair, count in pairs
    )
    body.append("")
    body.append("## 관련")
    body.append("- [[lotto-history-knowledge-summary]]")
    return page(
        {
            "type": "entity",
            "created": today,
            "updated": today,
            "sources": ["data/lotto.csv"],
            "aliases": [f"{number:02d}", f"{number}번"],
        },
        "\n".join(body),
    )


def build_pattern_page(key: str, metrics: KnowledgeMetrics, today: str) -> str:
    numbers = metrics.pattern_number_counts.get(key, Counter()).most_common(12)
    body = [
        f"# {pattern_title(key)}",
        "",
        f"- 전체 출현: {metrics.pattern_counts[key]}회",
        f"- 최근 출현: {metrics.recent_pattern_counts[key]}회",
        "",
        "## 강하게 연결된 번호",
    ]
    body.extend(
        f"- [[{number_slug(number)}|{number:02d}번]] — {count}회"
        for number, count in numbers
    )
    body.append("")
    body.append("## 관련")
    body.append("- [[lotto-history-knowledge-summary]]")
    return page(
        {
            "type": "concept",
            "created": today,
            "updated": today,
            "sources": ["data/lotto.csv"],
            "aliases": [pattern_title(key)],
        },
        "\n".join(body),
    )


def build_summary_page(metrics: KnowledgeMetrics, today: str) -> str:
    insights = knowledge_insights(metrics, top_n=10)
    body = [
        "# 로또 지식그물 요약",
        "",
        f"- 분석 회차 수: {metrics.draw_count}회",
        "- 목적: 회차 데이터를 번호, 유형, 선패턴, 동반출현 관계로 분해해 다음 분석 점수의 보조 근거로 사용한다.",
        "",
        "## 중심 번호",
    ]
    body.extend(
        f"- [[{number_slug(item['number'])}|{item['number']:02d}번]] — {item['score']:.2f}점"
        for item in insights["topNumbers"]
    )
    body.append("")
    body.append("## 핵심 패턴")
    body.extend(
        f"- [[{item['slug']}|{item['label']}]] — {item['count']}회"
        for item in insights["topPatterns"]
    )
    body.append("")
    body.append("## 최근 강한 패턴")
    body.extend(
        f"- [[{item['slug']}|{item['label']}]] — 최근 {item['count']}회"
        for item in insights["recentPatterns"]
    )
    body.append("")
    body.append("## 열린 질문")
    body.append("- 특정 패턴이 실제 다음 회차 적중률을 높이는지 백테스트로 계속 검증해야 한다.")
    return page(
        {
            "type": "source",
            "created": today,
            "updated": today,
            "sources": ["data/lotto.csv"],
            "aliases": ["로또 지식그물", "lotto knowledge net"],
        },
        "\n".join(body),
    )


def build_latest_note(metrics: KnowledgeMetrics, today: str) -> str:
    insights = knowledge_insights(metrics, top_n=6)
    body = [
        "# 최신 지식그물 분석 노트",
        "",
        "## 번호 후보",
    ]
    body.extend(
        f"- [[{number_slug(item['number'])}|{item['number']:02d}번]] — 지식그물 {item['score']:.2f}점, 최근 {item['recentCount']}회"
        for item in insights["topNumbers"]
    )
    body.append("")
    body.append("## 동반출현 축")
    body.extend(
        f"- [[{number_slug(item['numbers'][0])}|{item['numbers'][0]:02d}번]] + [[{number_slug(item['numbers'][1])}|{item['numbers'][1]:02d}번]] — {item['count']}회"
        for item in insights["topPairs"]
    )
    body.append("")
    body.append("## 최근 패턴 축")
    body.extend(
        f"- [[{item['slug']}|{item['label']}]] — 최근 {item['count']}회"
        for item in insights["recentPatterns"]
    )
    return page(
        {
            "type": "note",
            "created": today,
            "updated": today,
            "sources": ["data/lotto.csv"],
            "aliases": ["최신 지식그물 노트"],
        },
        "\n".join(body),
    )


def write_if_changed(path: Path, text: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def build_index(entries: list[tuple[str, str, str, str]], today: str) -> str:
    sections = ["source", "entity", "concept", "note"]
    lines = [
        "# index",
        "",
        "로또 자동분석용 지식그물 색인입니다.",
        "",
    ]
    for section in sections:
        lines.append(f"## {section}")
        for page_type, slug, summary, updated in sorted(entries, key=lambda item: item[1]):
            if page_type == section:
                lines.append(f"- [[{slug}]] — {summary} ({updated})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_knowledge_vault(
    draws: Sequence[Any],
    vault_dir: Path,
    grid_cols: int = 7,
    recent_window: int = DEFAULT_RECENT_WINDOW,
    pattern_limit: int = 60,
) -> dict[str, Any]:
    today = date.today().isoformat()
    metrics = build_knowledge_metrics(draws, grid_cols=grid_cols, recent_window=recent_window)
    wiki_dir = vault_dir / "wiki"
    entries: list[tuple[str, str, str, str]] = []
    changed = []

    schema = """# lotto knowledge net schema

netwaif/knot의 평문 마크다운 vault 방식을 로또 분석용으로 축소 적용한다.

- `wiki/`: 번호, 패턴, 최신 분석 노트의 상호링크 페이지
- `index.md`: 모든 wiki 페이지 색인
- `log.md`: 생성/갱신 이력
- `data/lotto.csv`: 근거 데이터

페이지 타입은 `source`, `entity`, `concept`, `note` 네 가지를 사용한다.
"""
    if write_if_changed(vault_dir / "schema.md", schema):
        changed.append("schema.md")
    for dirname in ("inbox", "raw", "scripts"):
        (vault_dir / dirname).mkdir(parents=True, exist_ok=True)

    summary_slug = "lotto-history-knowledge-summary"
    if write_if_changed(wiki_dir / f"{summary_slug}.md", build_summary_page(metrics, today)):
        changed.append(f"wiki/{summary_slug}.md")
    entries.append(("source", summary_slug, f"{metrics.draw_count}회차 지식그물 요약", today))

    note_slug = "latest-knowledge-insights"
    if write_if_changed(wiki_dir / f"{note_slug}.md", build_latest_note(metrics, today)):
        changed.append(f"wiki/{note_slug}.md")
    entries.append(("note", note_slug, "최근 번호/동반출현/패턴 연결 분석", today))

    for number in range(LOTTO_MIN, LOTTO_MAX + 1):
        slug = number_slug(number)
        if write_if_changed(wiki_dir / f"{slug}.md", build_number_page(number, metrics, today)):
            changed.append(f"wiki/{slug}.md")
        entries.append(("entity", slug, f"{number:02d}번 출현과 연결 패턴", today))

    pattern_keys = [key for key, _ in metrics.pattern_counts.most_common(pattern_limit)]
    pattern_keys.extend(key for key, _ in metrics.recent_pattern_counts.most_common(20) if key not in pattern_keys)
    for key in pattern_keys:
        slug = pattern_slug(key)
        if write_if_changed(wiki_dir / f"{slug}.md", build_pattern_page(key, metrics, today)):
            changed.append(f"wiki/{slug}.md")
        entries.append(("concept", slug, pattern_title(key), today))

    index = build_index(entries, today)
    if write_if_changed(vault_dir / "index.md", index):
        changed.append("index.md")

    log_path = vault_dir / "log.md"
    log_entry = (
        f"\n## [{datetime.now().isoformat(timespec='seconds')}] build — lotto knowledge net\n"
        f"- draw_count: {metrics.draw_count}\n"
        f"- pages: {len(entries)}\n"
        f"- changed: {len(changed)}\n"
    )
    previous_log = log_path.read_text(encoding="utf-8") if log_path.exists() else "# log\n"
    write_if_changed(log_path, previous_log.rstrip() + "\n" + log_entry)

    manifest = {
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "drawCount": metrics.draw_count,
        "pageCount": len(entries),
        "changedCount": len(changed),
        "insights": knowledge_insights(metrics),
    }
    if write_if_changed(vault_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"):
        changed.append("manifest.json")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build LottoAuto knowledge-net markdown vault.")
    parser.add_argument("--data", default="data/lotto.csv")
    parser.add_argument("--vault", default="knowledge")
    parser.add_argument("--recent-window", type=int, default=DEFAULT_RECENT_WINDOW)
    parser.add_argument("--grid-cols", type=int, default=7)
    return parser


def main() -> int:
    from lotto_auto import load_draws

    args = build_parser().parse_args()
    app_dir = Path(__file__).resolve().parent
    data_path = Path(args.data)
    if not data_path.is_absolute():
        data_path = app_dir / data_path
    vault_path = Path(args.vault)
    if not vault_path.is_absolute():
        vault_path = app_dir / vault_path

    draws = load_draws(data_path)
    manifest = write_knowledge_vault(
        draws,
        vault_path,
        grid_cols=args.grid_cols,
        recent_window=args.recent_window,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
