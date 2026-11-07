# sql

## Overview

Read-only TimescaleDB queries for manual deliverability analysis. No Python code in this repo loads them, so they run only when someone executes them by hand.

## Interface

- `burn_candidates.sql`: one row per domain and day from the last 3 days with a bounce rate above `0.03` or `inbox_placement` below `0.7`. It returns `name`, `day`, `sent`, `bounces`, `bounce_rate`, `inbox_placement` and `warmup_score`, sorted by `bounce_rate` descending with nulls last.
- `hypertable_health.sql`: chunk count and total size for the `deliverability_events` hypertable.

## Invariants

- Both files are single `SELECT` statements.
- They depend on core's schema: `domain_daily_stats`, `domains` and `deliverability_events`. Core's Flyway migrations own those objects.
- `hypertable_health.sql` needs the TimescaleDB view `timescaledb_information.chunks` and the function `chunks_detailed_size`.
- `nullif(s.sent, 0)` guards against division by zero, so a domain-day with no sends gets a null `bounce_rate`.

## Side Effects

- None

## Verification

- Run: `pytest` from `repos/utils`
- `pytest` does not execute these queries. Checking them requires a database with core's schema.
