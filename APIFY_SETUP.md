# APIFY Setup and Operations

This project treats APIFY as a required food input with weekly refresh.

## 1. Account and token
1. Create/login to [Apify Console](https://console.apify.com/).
2. Generate API token in Settings -> Integrations.
3. Put token in project `.env`:

```bash
APIFY_TOKEN=your_token_here
```

## 2. Actor redundancy
Default actors (in order):
1. `sunny_eternity/loblaws-grocery-scraper`
2. `ko_red/loblaws-grocery-scraper`

You can override with:

```bash
APIFY_ACTOR_IDS=actor_one,actor_two
```

The scraper tries actors in order and uses the first that returns valid normalized records.

## 3. Input settings
Defaults:
- `APIFY_CATEGORY_URL=https://www.realcanadiansuperstore.ca/food/dairy-eggs/c/28003`
- `APIFY_MAX_ITEMS=50`

Optional override:

```bash
APIFY_CATEGORY_URL=https://www.realcanadiansuperstore.ca/food/fresh-fruit/c/28407
APIFY_MAX_ITEMS=40
```

## 4. Cadence and freshness
- APIFY run cadence: weekly.
- Publish gate requirement: APIFY age must be <=14 days.
- UI/API display age as `updated X days ago`.

## 5. Validation contract
Each APIFY item must provide:
- product name (`name`/`title`/`productName`/`displayName`)
- price (`price.value`/`price.amount`/`currentPrice`...)

Malformed records are rejected during normalization.

## 6. Troubleshooting
- `APIFY_TOKEN not found`: check `.env` and shell environment.
- `Apify client init failed`: verify Python is 3.11 and reinstall dependencies.
- `no valid records returned`: actor schema drift or category URL issue.
- gate failure `APIFY missing or older than 14 days`: run APIFY ingestion manually.

Manual test command:

```bash
python3 -c "from scrapers.grocery_apify import scrape_grocery_apify; q,h=scrape_grocery_apify(); print(len(q)); print(h[0].status, h[0].detail)"
```

## 7. Operational triage
1. Check latest run status: `GET /v1/releases/latest`.
2. If APIFY failed, inspect `data/latest.json` `source_health` details.
3. Re-run ingestion after actor/input adjustments.
4. Confirm publish status is `published` before release.
