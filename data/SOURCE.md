# Lotto Data Source

`lotto.csv` was generated on 2026-06-18 from this public JSON mirror:

https://raw.githubusercontent.com/DDARK00/Korean-Lotto/main/data/lotto_history.json

The JSON fields were converted into the analyzer's standard CSV format:

```csv
draw_no,date,n1,n2,n3,n4,n5,n6,bonus,rnk1_winners,rnk1_prize,rnk2_winners,rnk2_prize,rnk3_winners,rnk3_prize
```

The source JSON includes draw numbers and winning numbers, but not draw dates. Dates were derived from Lotto 6/45 draw 1:

```text
1회 = 2002-12-07
date = 2002-12-07 + 7 days * (draw_no - 1)
```

Current imported range:

```text
1회 2002-12-07
1228회 2026-06-13
```

The official dhlottery endpoints are supported by `fetch_lotto_data.py`, but direct access to `www.dhlottery.co.kr` timed out from this execution environment during import.
