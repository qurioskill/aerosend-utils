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
- `aerosend_utils/seed_local.py` – local development only: creates sample domains for customers 1 and 2 through core's API, then adds their status and 14 days of deliverability data. Needs `AEROSEND_DB_URL` set to a localhost database, and core running. See [Local seed data](#local-seed-data).
- `sql/` – handy TimescaleDB queries (burn candidates, chunk sizes, compression status).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

Scripts read `AEROSEND_DB_URL` (defaults to the local docker-compose DB from aerosend-core).

## Local seed data

`aero-seed-local` skips domains that already exist, so their dates stop moving and they slowly drop out of the dashboard's 14-day and 3-day windows. `aero-seed-local --reset` fixes that: it deletes the seeded domains and their `deliverability_events` rows, seeds them again with fresh dates and refreshes `domain_daily_stats`. The domains get new IDs. It runs only after the localhost check, and it touches only the names in `SEED_DOMAINS`.

Core must be running for `--reset`. If it is down, the seeded domains are deleted and the run then fails, so start core and run `--reset` again.

Besides the six original domains, the seed covers these cases for the dashboard:

| Domain | Case |
|---|---|
| `northwind-stale.example` | `HEALTHY` status, bounce rate rising from 2% to 7% |
| `northwind-silent.example` | No events at all |
| `northwind-lowvol.example` | 8 sends a day, so 24 in 3 days, under the minimum of 30 |
| `northwind-nosends.example` | 3 bounces a day with no sends |
| `northwind-sparse.example` | One placement result, on the oldest day of the window |
| `contoso-outreach.example` | Customer 2, high bounce rate. Must not appear for customer 1 |

The sparse domain's placement result falls out of the 14-day window the day after seeding, and then shows as not tested until the next `--reset`.
