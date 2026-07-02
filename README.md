# Lotto Auto Analyzer

로또 전체 당첨 데이터를 CSV로 넣고, 여러 분석 항목을 교차 점수화해서 상위 번호와 추천 조합 5개를 생성하는 프로그램입니다.

중요: 로또 추첨은 독립 시행이라 어떤 통계도 당첨을 보장하지 않습니다. 이 프로그램은 예측 확정 도구가 아니라, 과거 데이터를 이용해 번호 조합을 체계적으로 필터링하는 분석 도구입니다.

## 데이터 파일 위치

실제 전체 데이터를 아래 파일로 저장하세요.

```text
outputs/lotto-auto/data/lotto.csv
```

이번 작업에서는 공개 JSON 미러를 변환해 `data/lotto.csv`를 생성해두었습니다. 다시 갱신하려면:

```bash
cd /Users/mac/Documents/Codex/2026-06-18/new-chat/outputs/lotto-auto
python3 import_lotto_history_json.py
```

CSV 형식:

```csv
draw_no,date,n1,n2,n3,n4,n5,n6,bonus,rnk1_winners,rnk1_prize,rnk2_winners,rnk2_prize,rnk3_winners,rnk3_prize
1,2002-12-07,10,23,29,33,37,40,16,0,0,1,143934100,28,5140500
```

한국어 헤더도 일부 지원합니다.

```csv
회차,날짜,번호1,번호2,번호3,번호4,번호5,번호6,보너스
```

## 실행

터미널에서:

```bash
cd /Users/mac/Documents/Codex/2026-06-18/new-chat/outputs/lotto-auto
python3 lotto_auto.py --target-date 2026-06-18 --seed 18
```

`data/lotto.csv`가 없으면 테스트용 샘플 데이터인 `data/lotto_sample.csv`로 실행됩니다. 샘플은 프로그램 확인용이며, 실제 전체 당첨 데이터로 교체해서 사용하세요.

분석 결과를 파일로 저장하려면:

```bash
python3 lotto_auto.py --target-date 2026-06-18 --seed 18 --report reports/analysis_2026-06-18.txt
```

## 데스크톱 앱 기능

`LottoAuto.app`은 로컬 웹 대시보드 방식으로 실행됩니다. 바탕화면 앱을 열면 브라우저에서 아래 주소가 자동으로 열립니다.

```text
http://127.0.0.1:8765/
```

새 대시보드는 다음 기능을 제공합니다.

- 저번주/최신 회차 당첨번호와 보너스 번호 표시
- 1~3등 당첨자수와 1인 당첨금 표시
- 중요 메인 기법 4개 별도 배치
  - 같은 날짜
  - 로또용지 선 패턴
  - 건너뛰기
  - 앞번호
- 보조 번호 분석 기법 체크 선택
- 조합 필터 체크 선택
- 추천 조합 카드
- 번호별 점수 테이블
- 같은 날짜/선 모양 근거 패널
- 상세 리포트 패널과 저장
- 데이터 갱신

## 카카오톡 자동 전송

GitHub Actions를 이용해 매주 수요일 12:00(KST)에 분석 결과를 카카오톡 `나와의 채팅`으로 보낼 수 있습니다.

추가로 매주 일요일 11:00(KST)에 수요일 추천번호와 최신 당첨번호를 비교한 결과를 카카오톡으로 받을 수 있습니다.

설정 순서:

```text
KAKAO_SETUP.md
```

카톡 발송 없이 메시지만 확인:

```bash
python3 weekly_kakao_report.py --dry-run --skip-refresh
```

자동 실행 파일:

```text
.github/workflows/lotto-kakao-weekly.yml
.github/workflows/lotto-kakao-sunday-result.yml
```

수요일 워크플로는 발송한 추천번호를 `reports/latest_recommendations.json`으로 저장하고 GitHub에 커밋합니다. 일요일 워크플로는 이 파일을 읽어 최신 회차 당첨번호와 비교합니다.

일요일 결과 카톡 dry-run:

```bash
python3 sunday_kakao_result.py --dry-run --skip-refresh
```

## 적용된 분석 항목

1. 과거 같은 날짜 분석
   - 예: 기준일이 6월 18일이면 과거 6월 18일 회차의 1등 번호를 추출해서 점수화합니다.

2. 로또용지 선 패턴 분석
   - 1~45 번호를 7열 격자로 배치합니다.
   - 각 회차의 6개 번호를 낮은 번호부터 선으로 이었다고 보고 이동 방향/거리 패턴을 만듭니다.
   - 역대 자주 나온 선 모양과 비슷한 조합에 점수를 줍니다.

3. 전 20회차 건너뛰기 분석
   - 직전 회차 번호가 다음 회차에 재출현하는 패턴
   - 저저번 회차 번호가 한 주 건너 재출현하는 패턴
   - 3~5회차 간격 재출현 패턴
   - 특히 한 주 건너뛰기 패턴에 더 높은 가중치를 줍니다.

4. 앞번호 패턴 분석
   - 각 회차의 첫 번호, 즉 가장 작은 번호의 출현 빈도와 재출현 간격을 분석합니다.
   - 추천 조합의 첫 번호가 현재 흐름상 유리한지 점수화합니다.

5. 통계 필터
   - 최근 20회 흐름
   - 전체 출현 빈도
   - 미출현 기간
   - 끝수 패턴
   - 홀짝 비율
   - 저/고 번호 비율
   - 6개 번호 합계
   - 연속 번호 개수
   - 자주 같이 나온 번호쌍
   - 과거 당첨 조합과 너무 비슷한 조합 감점

## 자주 쓰는 옵션

```bash
python3 lotto_auto.py --data data/lotto.csv --target-date 2026-06-18
python3 lotto_auto.py --recent-window 20 --candidates 100000 --pool-size 32
python3 lotto_auto.py --count 10 --top-numbers 20 --seed 777
```

옵션 설명:

- `--target-date`: 같은 날짜 분석 기준일
- `--recent-window`: 최근 흐름 분석 회차 수, 기본 20
- `--candidates`: 무작위 후보 조합 생성 수, 많을수록 느리지만 더 넓게 탐색
- `--pool-size`: 상위 번호 후보군 크기
- `--count`: 출력할 추천 조합 개수
- `--seed`: 같은 결과를 다시 얻기 위한 난수 고정값

## 테스트

```bash
cd /Users/mac/Documents/Codex/2026-06-18/new-chat/outputs/lotto-auto
python3 -m unittest discover
```
