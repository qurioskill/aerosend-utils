# utils

## Overview

The `aerosend-utils` Python package (version 0.9.0, Python 3.12 or later) and SQL snippets for data jobs, backfills and deliverability analysis. It writes directly to core's `deliverability_events` table, so core's Flyway schema is its main external contract. Dependencies are `psycopg[binary]` and `click`, with `pytest` and `ruff` as dev extras.

## Subdirectories & Boundaries

- aerosend_utils: [./aerosend_utils/AGENTS.md](./aerosend_utils/AGENTS.md) - The `aero-placement`, `aero-backfill` and `aero-seed-local` CLIs, the bounce classifier and the database connection helper.
- sql: [./sql/AGENTS.md](./sql/AGENTS.md) - Read-only queries for burn candidates and hypertable health.
- tests: Unit tests for `classify`, `placement_rate` and the `seed_local` host check, seed cases and `--reset`. This directory has no contract file.

## Verification

- Run: `pytest`, after `pip install -e '.[dev]'`
