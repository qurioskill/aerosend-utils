# aerosend_utils

## Overview

Python 3.12 package of data jobs that write deliverability telemetry straight to Postgres with psycopg 3. It ships three click CLIs, plus the bounce classifier and connection helper they use.

## Interface

- `aero-placement` (`placement_test:main`): `--domain-id` (required int), `--dry-run`.
- `aero-backfill` (`backfill_deliverability:main`): `CSV_PATH` (must exist), `--batch-size` (default `5000`).
- `aero-seed-local` (`seed_local:main`): `--core-url` (default `http://localhost:8081`), `--reset`. Local development only.
- `seed_local.SeedDomain`: dataclass for one seeded domain. Optional fields are `customer_id` (`1`), `sent_per_day` (`150`), `bounces_per_day` (`None`, a fixed count that overrides `bounce_rate`), `placement_every_days` (`1`) and `region` (`local-seed`).
- `seed_local.daily_events(domain, domain_id, day, day_index, rng) -> list[tuple]`: one day's event rows. `day_index` is `0` on the oldest day of the window.
- `seed_local.delete_seeded(conn) -> None`: deletes the `SEED_DOMAINS` domains and their events in one transaction.
- `bounce_classifier.classify(smtp_code: int, diagnostic: str) -> str`: returns `HARD`, `SOFT` or `BLOCK`. Pattern lists are `BLOCK_PATTERNS` and `HARD_PATTERNS`.
- `db.connect() -> psycopg.Connection`, with `db.DEFAULT_URL` as the fallback.
- `placement_test.SeedResult`: dataclass with `domain_id`, `provider`, `landed`.
- `placement_test.placement_rate(results) -> float`: the fraction with `landed == "inbox"`, or `0.0` for an empty list.
- `placement_test.record(domain_id, rate) -> None`: inserts one `PLACEMENT` row.

## Invariants

- `placement_test.py` is production code despite its name. Do not move or skip it as a test: `aero-placement` points at its module path. Its name matches pytest's `*_test.py` pattern, so pytest collects it too, but it defines no tests.
- `placement_test.main` does not contact a seed provider yet. Its results are hardcoded behind a `TODO`, so every run reports 50%, and any run without `--dry-run` writes that made-up `0.5` as a real `PLACEMENT` row.
- `classify` checks `BLOCK_PATTERNS` first, so they win at any SMTP code, including 4xx. Otherwise any code `>= 500` is `HARD` and anything lower is `SOFT`. `HARD_PATTERNS` therefore cannot change the result.
- `classify` lowercases the diagnostic, so patterns must be lowercase.
- Return values of `classify` must stay in the `bounce_type` set `HARD | SOFT | BLOCK` documented in core's `V2__deliverability_hypertable.sql`.
- `kind` values written here (`BOUNCE`, `PLACEMENT`) and the `deliverability_events` columns are owned by core's Flyway schema.
- `placement_rate` returns a fraction from 0 to 1, stored in `value`. `sql/burn_candidates.sql` compares its daily average against `0.7`.
- The backfill CSV must have the columns `time` (ISO 8601), `domain_id`, `mailbox_id`, `smtp_code` and `diagnostic`.
- The backfill imports every CSV row. It has no date-range filter, despite its docstring, and loads the whole file into memory first.
- All backfill batches share one transaction, so a failure rolls back the whole run. `deliverability_events` has no unique constraint, so re-running the same file inserts duplicates.
- `connect()` opens a new connection on every call, with no pooling.
- `seed_local` requires `AEROSEND_DB_URL` to be set and to point at localhost. It must not fall back to `DEFAULT_URL`, because port 5432 may belong to another local project.
- `seed_local` creates domains through core's API so that outbox events fire. It uses SQL only for what core has no route for: `server_batches`, `burn_status`, `dns_verified` and `deliverability_events`. The exception is `--reset`, which deletes `domains` rows with SQL because core has no delete route. That emits no outbox event.
- The host check in `seed_local.main` must stay ahead of `connect()`, and so ahead of anything `--reset` does.
- `--reset` must read the existing domain names after deleting, or every domain is skipped as already existing.
- The final `refresh_continuous_aggregate` call must keep `NULL, NULL` bounds. `--reset` can delete rows older than the days it seeds, and a narrower range would leave them in `domain_daily_stats`.
- `delete_seeded` does not touch `mailboxes`, which references `domains`. The seed creates no mailboxes, so if a seeded domain has one, the delete fails and its transaction rolls back.
- Core refuses more than `aerosend.provisioning.domains-per-batch` (10) domains in a server batch, and customer 1 has 11 seed domains. New seed domains set `region` to spread them across batches, and a test enforces the limit.
- A domain with `sent_per_day = 0` gets no `PLACEMENT`, `WARMUP_SCORE` or `REPLY` rows. Only `bounces_per_day` can give it events.

## Side Effects

- `db.connect` reads `AEROSEND_DB_URL`, falling back to the local `DEFAULT_URL`, and opens a Postgres connection.
- `record` and the backfill `main` `INSERT` into `deliverability_events`. Those rows feed core's `domain_daily_stats` aggregate.
- The backfill `main` reads the CSV at `csv_path`.
- Both CLIs print a summary line with `click.echo`.
- `--dry-run` skips only the `INSERT` in `placement_test.main`.
- `seed_local.main` calls `POST /api/v1/domains`, writes the tables listed under Invariants and refreshes `domain_daily_stats`.
- `--reset` also deletes `deliverability_events` and `domains` rows for the seeded names, so those domains get new IDs and core writes new `domain.provisioned` outbox events. Server batches are kept. If core is down, the delete has already happened, and the rollup is not refreshed until a later run succeeds.

## Verification

- Run: `pytest` from `repos/utils`, after `pip install -e '.[dev]'`
- Tests live in `repos/utils/tests` and cover `classify`, `placement_rate` and `seed_local`. The `seed_local` tests use a fake connection and a fake core, so `--reset` has not been tested by them against a real database. Nothing tests `record`, `connect` or the backfill.
