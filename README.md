# Gold Price Feed

Public JSON feed for hourly gold prices used by `money_tracker_together`.

## Output

- `data/latest.json`: latest scraped point.
- `data/history/YYYY-MM.json`: hourly points for each month.

The feed is intentionally public and contains only market prices, never app user
data.

## Run locally

```bash
python3 -m pip install -r requirements.txt
python3 scripts/fetch_gold_prices.py
```

