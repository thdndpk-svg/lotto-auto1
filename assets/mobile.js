const $ = (id) => document.getElementById(id);

const PART_LABELS = {
  number: "번호점수",
  line_shape: "선모양",
  front: "첫번호",
  sum: "번호합",
  odd_even: "홀짝",
  low_high: "저고",
  ending: "끝수",
  consecutive: "연속수",
  pair: "동반",
  recent_hot: "최근",
  knowledge_net: "지식",
  feedback: "피드백",
  history_penalty: "과거"
};

const state = {
  draws: [],
  recommendations: null,
  feedback: null,
  latestScores: []
};

function pad2(value) {
  return String(value).padStart(2, "0");
}

function todayLocal() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

function setStatus(text) {
  $("statusText").textContent = text;
}

function ballClass(number) {
  if (number <= 10) return "s1";
  if (number <= 20) return "s2";
  if (number <= 30) return "s3";
  if (number <= 40) return "s4";
  return "s5";
}

function ball(number) {
  return `<span class="ball ${ballClass(number)}">${pad2(number)}</span>`;
}

function money(value) {
  const n = Number(value || 0);
  return n ? `${n.toLocaleString("ko-KR")}원` : "-";
}

function countText(value) {
  const n = Number(value || 0);
  return n ? `${n.toLocaleString("ko-KR")}명` : "-";
}

async function fetchText(path) {
  const response = await fetch(`${path}?t=${Date.now()}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path} ${response.status}`);
  return response.text();
}

async function fetchJsonSafe(path) {
  try {
    const response = await fetch(`${path}?t=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) return null;
    return await response.json();
  } catch (_) {
    return null;
  }
}

function parseCsv(text) {
  const lines = text.trim().split(/\r?\n/);
  const header = lines.shift().split(",");
  return lines.map((line) => {
    const cols = line.split(",");
    const row = {};
    header.forEach((key, idx) => {
      row[key] = cols[idx] ?? "";
    });
    return {
      drawNo: Number(row.draw_no),
      date: row.date,
      numbers: [row.n1, row.n2, row.n3, row.n4, row.n5, row.n6].map(Number),
      bonus: Number(row.bonus),
      rnk1Winners: Number(row.rnk1_winners || 0),
      rnk1Prize: Number(row.rnk1_prize || 0),
      rnk2Winners: Number(row.rnk2_winners || 0),
      rnk2Prize: Number(row.rnk2_prize || 0),
      rnk3Winners: Number(row.rnk3_winners || 0),
      rnk3Prize: Number(row.rnk3_prize || 0)
    };
  }).filter((draw) => draw.drawNo && draw.numbers.length === 6);
}

function renderLatest() {
  const latest = state.draws.at(-1);
  if (!latest) return;
  $("drawNo").textContent = latest.drawNo;
  $("latestMeta").textContent = latest.date;
  $("latestBalls").innerHTML = latest.numbers.map(ball).join("") + `<span class="plus">+</span>${ball(latest.bonus)}`;
  $("prizeBody").innerHTML = [
    ["1등", latest.rnk1Winners, latest.rnk1Prize],
    ["2등", latest.rnk2Winners, latest.rnk2Prize],
    ["3등", latest.rnk3Winners, latest.rnk3Prize]
  ].map(([rank, winners, prize]) => `<tr><td>${rank}</td><td>${countText(winners)}</td><td>${money(prize)}</td></tr>`).join("");
}

function coord(number) {
  return { x: (number - 1) % 7, y: Math.floor((number - 1) / 7) };
}

function shapeSignature(numbers) {
  const coords = [...numbers].sort((a, b) => a - b).map(coord);
  const moves = [];
  for (let i = 0; i < coords.length - 1; i += 1) {
    const a = coords[i];
    const b = coords[i + 1];
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const sx = dx > 0 ? "R" : dx < 0 ? "L" : "S";
    const sy = dy > 0 ? "D" : dy < 0 ? "U" : "S";
    const dist = Math.min(6, Math.abs(dx) + Math.abs(dy));
    moves.push(`${sx}${sy}${dist}`);
  }
  return moves.join(">");
}

function ticketPattern(numbers) {
  const selected = new Set(numbers.map(Number));
  const sorted = [...numbers].sort((a, b) => a - b);
  const points = sorted.map((n) => {
    const c = coord(n);
    return `${c.x + 0.5},${c.y + 0.5}`;
  }).join(" ");
  const cells = Array.from({ length: 49 }, (_, idx) => {
    const n = idx + 1;
    const label = n <= 45 ? pad2(n) : "";
    const hit = selected.has(n) ? " hit" : "";
    return `<span class="pattern-cell${hit}">${label}</span>`;
  }).join("");
  return `
    <div class="pattern">
      <div class="pattern-grid">${cells}</div>
      <svg viewBox="0 0 7 7" preserveAspectRatio="none">
        <polyline points="${points}" fill="none" stroke="#ff6b6b" stroke-width=".08" stroke-linecap="round" stroke-linejoin="round"></polyline>
      </svg>
    </div>
  `;
}

function partRows(parts = {}) {
  return Object.entries(parts)
    .filter(([key]) => key !== "history_penalty")
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
    .slice(0, 5)
    .map(([key, value]) => {
      const width = Math.max(5, Math.min(100, Math.abs(Number(value)) * 7));
      return `
        <div class="part">
          <span>${PART_LABELS[key] || key}</span>
          <span class="bar"><i style="width:${width}%"></i></span>
          <b>${Number(value) > 0 ? "+" : ""}${Number(value).toFixed(1)}</b>
        </div>
      `;
    }).join("");
}

function renderCombos(target, combos) {
  if (!combos || !combos.length) {
    target.innerHTML = `<div class="notice">표시할 조합이 없습니다.</div>`;
    return;
  }
  target.innerHTML = combos.map((combo, idx) => {
    const numbers = combo.numbers || [];
    const rank = combo.rank || idx + 1;
    const score = Number(combo.score || 0);
    return `
      <article class="combo-card">
        <div class="combo-head"><span class="rank">${rank}위</span><span class="score">${score.toFixed(2)}점</span></div>
        <div class="balls">${numbers.map(ball).join("")}</div>
        ${ticketPattern(numbers)}
        <div class="parts">${partRows(combo.parts || {})}</div>
      </article>
    `;
  }).join("");
}

function renderSavedRecommendations() {
  const rec = state.recommendations;
  if (!rec) {
    $("savedPanel").innerHTML = `<div class="notice">저장된 추천 파일을 읽지 못했습니다.</div>`;
    $("comboMeta").textContent = "-";
    return;
  }
  $("updatedAt").textContent = rec.generated_at ? `추천 ${rec.generated_at.replace("T", " ")}` : "-";
  $("comboMeta").textContent = `${rec.target_date || "-"} · ${Number(rec.candidates || 0).toLocaleString("ko-KR")}개`;
  renderCombos($("savedPanel"), rec.combos || []);
}

function buildCounter(values) {
  const counter = new Map();
  for (const value of values) counter.set(value, (counter.get(value) || 0) + 1);
  return counter;
}

function maxCounter(counter) {
  return Math.max(1, ...counter.values());
}

function normalize(value, high) {
  return high > 0 ? Math.max(0, Math.min(1, value / high)) : 0;
}

function consecutiveCount(numbers) {
  const sorted = [...numbers].sort((a, b) => a - b);
  let count = 0;
  for (let i = 0; i < sorted.length - 1; i += 1) {
    if (sorted[i + 1] === sorted[i] + 1) count += 1;
  }
  return count;
}

function mulberry32(seed) {
  let a = seed >>> 0;
  return function random() {
    a += 0x6D2B79F5;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function weightedSample(pool, weights, k, random) {
  const items = [...pool];
  const itemWeights = [...weights];
  const result = [];
  for (let pickIndex = 0; pickIndex < k; pickIndex += 1) {
    const total = itemWeights.reduce((sum, value) => sum + value, 0);
    let pick = random() * total;
    let chosen = 0;
    for (let i = 0; i < itemWeights.length; i += 1) {
      pick -= itemWeights[i];
      if (pick <= 0) {
        chosen = i;
        break;
      }
    }
    result.push(items.splice(chosen, 1)[0]);
    itemWeights.splice(chosen, 1);
  }
  return result;
}

function analyzeNumbers(targetDate) {
  const draws = state.draws;
  const recent = draws.slice(-20);
  const sameDate = draws.filter((draw) => draw.date.slice(5) === targetDate.slice(5));
  const allNumbers = draws.flatMap((draw) => draw.numbers);
  const recentNumbers = recent.flatMap((draw) => draw.numbers);
  const allCounter = buildCounter(allNumbers);
  const recentCounter = buildCounter(recentNumbers);
  const sameCounter = buildCounter(sameDate.flatMap((draw) => draw.numbers));
  const endingCounter = buildCounter(allNumbers.map((number) => number % 10));
  const frontCounter = buildCounter(draws.map((draw) => Math.min(...draw.numbers)));
  const recentFrontCounter = buildCounter(recent.map((draw) => Math.min(...draw.numbers)));
  const highAll = maxCounter(allCounter);
  const highRecent = maxCounter(recentCounter);
  const highSame = maxCounter(sameCounter);
  const highEnding = maxCounter(endingCounter);
  const highFront = maxCounter(frontCounter);
  const highRecentFront = maxCounter(recentFrontCounter);
  const lastDraws = [draws.at(-1), draws.at(-2), draws.at(-3)].filter(Boolean);

  const sourceCounts = new Map();
  const repeatCounts = new Map();
  for (const gap of [1, 2, 3]) {
    for (let i = gap; i < draws.length; i += 1) {
      const source = draws[i - gap].numbers;
      const target = new Set(draws[i].numbers);
      for (const number of source) {
        const key = `${gap}:${number}`;
        sourceCounts.set(key, (sourceCounts.get(key) || 0) + 1);
        if (target.has(number)) repeatCounts.set(key, (repeatCounts.get(key) || 0) + 1);
      }
    }
  }

  const scores = [];
  for (let number = 1; number <= 45; number += 1) {
    const frequency = 65 * normalize(allCounter.get(number) || 0, highAll);
    const recentScore = 95 * normalize(recentCounter.get(number) || 0, highRecent);
    const sameScore = sameDate.length ? 80 * normalize(sameCounter.get(number) || 0, highSame) : 0;
    const ending = 42 * normalize(endingCounter.get(number % 10) || 0, highEnding);
    const front = 70 * (
      normalize(frontCounter.get(number) || 0, highFront) * 0.55 +
      normalize(recentFrontCounter.get(number) || 0, highRecentFront) * 0.45
    );
    let skip = 0;
    lastDraws.forEach((draw, idx) => {
      const gap = idx + 1;
      if (!draw.numbers.includes(number)) return;
      const key = `${gap}:${number}`;
      const rate = (repeatCounts.get(key) || 0) / Math.max(1, sourceCounts.get(key) || 0);
      skip += rate * (gap === 2 ? 115 : gap === 1 ? 80 : 60);
    });
    const feedbackBias = state.feedback?.number_bias?.[String(number)] || 0;
    const feedback = Math.max(0, Math.min(30, 15 + feedbackBias * 24));
    const total = (
      frequency * 0.16 +
      recentScore * 0.18 +
      sameScore * 0.16 +
      skip * 0.20 +
      front * 0.12 +
      ending * 0.09 +
      feedback * 0.09
    );
    const factors = [
      ["최근", recentScore],
      ["건너", skip],
      ["같은날", sameScore],
      ["빈도", frequency],
      ["앞번호", front],
      ["끝수", ending]
    ].sort((a, b) => b[1] - a[1]).slice(0, 3);
    scores.push({ number, score: total, factors });
  }
  scores.sort((a, b) => b.score - a.score || a.number - b.number);
  const top = scores[0]?.score || 1;
  state.latestScores = scores.map((item, idx) => ({
    ...item,
    rank: idx + 1,
    score: Math.max(0, Math.min(100, 100 * item.score / top))
  }));
  return state.latestScores;
}

function pairCounter(draws) {
  const counter = new Map();
  for (const draw of draws) {
    const nums = [...draw.numbers].sort((a, b) => a - b);
    for (let i = 0; i < nums.length; i += 1) {
      for (let j = i + 1; j < nums.length; j += 1) {
        const key = `${nums[i]}:${nums[j]}`;
        counter.set(key, (counter.get(key) || 0) + 1);
      }
    }
  }
  return counter;
}

function distributionCounter(draws, fn) {
  return buildCounter(draws.map(fn));
}

function shapeSimilarity(left, right) {
  if (!left || !right) return 0;
  const a = left.split(">");
  const b = right.split(">");
  if (a.length !== b.length) return 0;
  let total = 0;
  a.forEach((move, idx) => {
    const other = b[idx];
    const sameX = move[0] === other[0];
    const sameY = move[1] === other[1];
    const distA = Number(move.slice(2)) || 0;
    const distB = Number(other.slice(2)) || 0;
    const direction = sameX && sameY ? 0.7 : sameX || sameY ? 0.35 : 0;
    const distance = 0.3 * Math.max(0, 1 - Math.abs(distA - distB) / 6);
    total += direction + distance;
  });
  return total / a.length;
}

function comboScore(combo, context) {
  const scoreMap = context.scoreMap;
  const sum = combo.reduce((acc, value) => acc + value, 0);
  const odd = combo.filter((n) => n % 2).length;
  const low = combo.filter((n) => n <= 22).length;
  const endingDup = 6 - new Set(combo.map((n) => n % 10)).size;
  const consecutive = consecutiveCount(combo);
  const signature = shapeSignature(combo);
  const numberPart = combo.reduce((acc, n) => acc + (scoreMap.get(n) || 0), 0) / combo.length * 0.45;
  const sumPart = 10 * Math.max(0, 1 - Math.abs(sum - context.recentSumMean) / context.sumTolerance);
  const oddPart = 7 * normalize(context.oddDist.get(odd) || 0, context.oddHigh);
  const lowPart = 5 * normalize(context.lowDist.get(low) || 0, context.lowHigh);
  const endingPart = 5 * normalize(context.endingDist.get(endingDup) || 0, context.endingHigh);
  const consecutivePart = 4 * normalize(context.consecutiveDist.get(consecutive) || 0, context.consecutiveHigh);
  let pairTotal = 0;
  for (let i = 0; i < combo.length; i += 1) {
    for (let j = i + 1; j < combo.length; j += 1) {
      pairTotal += context.pairs.get(`${combo[i]}:${combo[j]}`) || 0;
    }
  }
  const pairPart = 4 * normalize(pairTotal, context.pairHigh * 2.5);
  const hotPart = 3 * Math.max(0, 1 - Math.abs(combo.filter((n) => context.hot.has(n)).length - 2) / 2);
  const shapePart = 12 * Math.max(...context.topShapes.map(([shape, boost]) => shapeSimilarity(signature, shape) * boost), 0);
  let historyPenalty = 0;
  const key = combo.join(":");
  if (context.fullHistory.has(key)) historyPenalty = 18;
  else {
    for (let omit = 0; omit < combo.length; omit += 1) {
      const five = combo.filter((_, idx) => idx !== omit).join(":");
      if (context.fiveHistory.has(five)) {
        historyPenalty = 8;
        break;
      }
    }
  }
  const parts = {
    number: numberPart,
    line_shape: shapePart,
    sum: sumPart,
    odd_even: oddPart,
    low_high: lowPart,
    ending: endingPart,
    consecutive: consecutivePart,
    pair: pairPart,
    recent_hot: hotPart,
    history_penalty: -historyPenalty
  };
  const total = Object.values(parts).reduce((acc, value) => acc + value, 0);
  return { numbers: combo, score: Math.max(0, Math.min(100, 100 * total / 102)), parts };
}

function generateCombos(targetDate, candidates, seed, poolSize) {
  const scores = analyzeNumbers(targetDate);
  const pool = scores.slice(0, poolSize).map((item) => item.number);
  const weights = scores.slice(0, poolSize).map((item) => Math.max(1, item.score));
  const random = mulberry32(Number(seed) || 18);
  const recent = state.draws.slice(-20);
  const recentSums = recent.map((draw) => draw.numbers.reduce((acc, n) => acc + n, 0));
  const recentSumMean = recentSums.reduce((a, b) => a + b, 0) / recentSums.length;
  const recentCounter = buildCounter(recent.flatMap((draw) => draw.numbers));
  const hot = new Set([...recentCounter.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6).map(([n]) => n));
  const pairs = pairCounter(state.draws);
  const shapeCounter = buildCounter(state.draws.map((draw) => shapeSignature(draw.numbers)));
  const shapeHigh = maxCounter(shapeCounter);
  const topShapes = [...shapeCounter.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12)
    .map(([shape, count]) => [shape, 0.4 + 0.6 * normalize(count, shapeHigh)]);
  const fullHistory = new Set(state.draws.map((draw) => [...draw.numbers].sort((a, b) => a - b).join(":")));
  const fiveHistory = new Set();
  for (const draw of state.draws) {
    const nums = [...draw.numbers].sort((a, b) => a - b);
    for (let omit = 0; omit < nums.length; omit += 1) {
      fiveHistory.add(nums.filter((_, idx) => idx !== omit).join(":"));
    }
  }
  const context = {
    scoreMap: new Map(scores.map((item) => [item.number, item.score])),
    recentSumMean,
    sumTolerance: 28,
    oddDist: distributionCounter(state.draws, (draw) => draw.numbers.filter((n) => n % 2).length),
    lowDist: distributionCounter(state.draws, (draw) => draw.numbers.filter((n) => n <= 22).length),
    endingDist: distributionCounter(state.draws, (draw) => 6 - new Set(draw.numbers.map((n) => n % 10)).size),
    consecutiveDist: distributionCounter(state.draws, (draw) => consecutiveCount(draw.numbers)),
    pairs,
    pairHigh: maxCounter(pairs),
    hot,
    topShapes,
    fullHistory,
    fiveHistory
  };
  context.oddHigh = maxCounter(context.oddDist);
  context.lowHigh = maxCounter(context.lowDist);
  context.endingHigh = maxCounter(context.endingDist);
  context.consecutiveHigh = maxCounter(context.consecutiveDist);

  const seen = new Set();
  const scored = [];
  const topSeed = [...pool.slice(0, 6)].sort((a, b) => a - b);
  seen.add(topSeed.join(":"));
  scored.push(comboScore(topSeed, context));
  for (let i = 0; i < candidates; i += 1) {
    const combo = weightedSample(pool, weights, 6, random).sort((a, b) => a - b);
    const key = combo.join(":");
    if (seen.has(key)) continue;
    seen.add(key);
    scored.push(comboScore(combo, context));
  }
  scored.sort((a, b) => b.score - a.score || a.numbers.join("").localeCompare(b.numbers.join("")));
  const diversified = [];
  for (const combo of scored) {
    if (diversified.every((prev) => combo.numbers.filter((n) => prev.numbers.includes(n)).length <= 4)) {
      diversified.push({ ...combo, rank: diversified.length + 1, score: Number(combo.score.toFixed(2)) });
    }
    if (diversified.length >= 5) break;
  }
  return diversified;
}

function renderSignals(targetDate) {
  const latestScores = analyzeNumbers(targetDate);
  const hotText = latestScores.slice(0, 3).map((item) => pad2(item.number)).join(" ");
  const same = state.draws.filter((draw) => draw.date.slice(5) === targetDate.slice(5)).slice(-3);
  const front = latestScores.find((item) => item.factors.some(([label]) => label === "앞번호"));
  $("hotMetric").textContent = hotText || "-";
  $("sameMetric").textContent = same.length ? `${same.at(-1).drawNo}회` : "-";
  $("frontMetric").textContent = front ? `${pad2(front.number)}번` : "-";
  $("feedbackMetric").textContent = state.feedback?.observation_count ? `${state.feedback.observation_count}회` : "대기";
  $("signalMeta").textContent = `${latestScores.length}개 번호`;
  $("numberBody").innerHTML = latestScores.slice(0, 10).map((item) => `
    <tr>
      <td>${item.rank}</td>
      <td>${ball(item.number)}</td>
      <td>${item.factors.map(([label, score]) => `${label} ${score.toFixed(0)}`).join(", ")}</td>
      <td>${item.score.toFixed(1)}</td>
    </tr>
  `).join("");
}

async function loadAll() {
  setStatus("갱신 중");
  $("analysisState").textContent = "불러오는 중";
  const [csvText, recommendations, feedback] = await Promise.all([
    fetchText("data/lotto.csv"),
    fetchJsonSafe("reports/latest_recommendations.json"),
    fetchJsonSafe("knowledge/feedback_memory.json")
  ]);
  state.draws = parseCsv(csvText);
  state.recommendations = recommendations;
  state.feedback = feedback;
  renderLatest();
  renderSavedRecommendations();
  renderSignals($("targetDate").value || todayLocal());
  $("analysisState").textContent = "준비";
  setStatus("정상");
}

async function runMobileAnalysis() {
  if (!state.draws.length) return;
  $("analyzeBtn").disabled = true;
  $("analysisState").textContent = "분석 중";
  setStatus("분석 중");
  await new Promise((resolve) => setTimeout(resolve, 40));
  try {
    const targetDate = $("targetDate").value || todayLocal();
    const candidates = Math.max(1000, Math.min(60000, Number($("candidates").value || 12000)));
    const poolSize = Math.max(18, Math.min(36, Number($("poolSize").value || 30)));
    const combos = generateCombos(targetDate, candidates, $("seed").value, poolSize);
    renderCombos($("mobilePanel"), combos);
    renderSignals(targetDate);
    activateTab("mobile");
    $("analysisState").textContent = "완료";
    setStatus("정상");
  } catch (error) {
    $("analysisState").textContent = "오류";
    $("notice").textContent = error.message;
    setStatus("확인 필요");
  } finally {
    $("analyzeBtn").disabled = false;
  }
}

function activateTab(name) {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.tab === name);
  });
  $("savedPanel").classList.toggle("hidden", name !== "saved");
  $("mobilePanel").classList.toggle("hidden", name !== "mobile");
}

function bindEvents() {
  $("targetDate").value = todayLocal();
  $("analyzeBtn").addEventListener("click", runMobileAnalysis);
  $("reloadBtn").addEventListener("click", loadAll);
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => activateTab(tab.dataset.tab));
  });
}

bindEvents();
loadAll().catch((error) => {
  setStatus("오류");
  $("analysisState").textContent = "오류";
  $("notice").textContent = error.message;
});
