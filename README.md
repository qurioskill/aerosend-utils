# aerosend-utils

Python scripts and SQL snippets for data jobs, one-off backfills and deliverability analysis.

| | |
|---|---|
| Category | utils |
| Change frequency | **medium** |
| Stack | Python 3.12, psycopg 3, TimescaleDB SQL |
| Owners | Platform team + whoever needs a script |

## Contents

- `aerosend_utils/placement_test.py` – runs the biweekly inbox placement test (seed list → placement % per domain) and writes `PLACEMENT` rows to `deliverability_events`.
- `aerosend_utils/bounce_classifier.py` – classifies raw SMTP bounce messages into HARD / SOFT / BLOCK.
- `aerosend_utils/backfill_deliverability.py` – re-imports bounce logs into the hypertable for a date range.
- `sql/` – handy TimescaleDB queries (burn candidates, chunk sizes, compression status).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

Scripts read `AEROSEND_DB_URL` (defaults to the local docker-compose DB from aerosend-core).
