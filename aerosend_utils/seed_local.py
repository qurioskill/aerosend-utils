"""Local development only: seed sample domains and 14 days of deliverability data.

Domains are created through core's API so that outbox events fire. Core has no route for server
batches, burn status, DNS verification or telemetry, so those are written with SQL. Safe to re-run:
domains that already exist are skipped. Seeded days age out of the dashboard's windows, so --reset
deletes the seeded domains and creates them again with fresh dates.
"""

import json
import os
import random
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import click
import psycopg
from psycopg.conninfo import conninfo_to_dict

from .db import connect

CUSTOMER_ID = 1
REGION = "local-seed"
# Core refuses an eleventh domain in a batch (aerosend.provisioning.domains-per-batch), and customer 1
# has eleven seed domains, so the newer ones sit in a second batch.
SECOND_REGION = "local-seed-2"
DAYS = 14
SENT_PER_DAY = 150
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


@dataclass(frozen=True)
class SeedDomain:
    name: str
    burn_status: str
    dns_verified: bool
    # Each pair is (oldest day, most recent day), so a domain can trend over the window.
    bounce_rate: tuple[float, float]
    reply_rate: tuple[float, float]
    placement: tuple[float, float]
    warmup: tuple[float, float]
    customer_id: int = CUSTOMER_ID
    sent_per_day: int = SENT_PER_DAY
    bounces_per_day: int | None = None  # a fixed count that overrides bounce_rate
    placement_every_days: int = 1  # counted from the oldest day, so 14 means that day only
    region: str = REGION


NO_RATE = (0.0, 0.0)

SEED_DOMAINS = [
    SeedDomain("northwind-outreach.example", "HEALTHY", True, (0.01, 0.01), (0.03, 0.03), (0.94, 0.95), (93, 95)),
    SeedDomain("northwind-sales.example", "HEALTHY", True, (0.01, 0.012), (0.025, 0.03), (0.92, 0.93), (91, 94)),
    SeedDomain("getnorthwind.example", "HEALTHY", True, (0.015, 0.01), (0.02, 0.025), (0.88, 0.92), (88, 92)),
    SeedDomain("trynorthwind.example", "HEALTHY", False, (0.012, 0.012), (0.02, 0.02), (0.9, 0.9), (86, 90)),
    SeedDomain("northwind-mail.example", "AT_RISK", True, (0.012, 0.038), (0.02, 0.006), (0.88, 0.72), (90, 84)),
    SeedDomain("northwind-hello.example", "BURNED", True, (0.015, 0.09), (0.02, 0.002), (0.85, 0.42), (88, 61)),
    # Bad figures behind a HEALTHY status, so the sort cannot be mistaken for the old badge.
    SeedDomain(
        "northwind-stale.example", "HEALTHY", True, (0.02, 0.07), (0.025, 0.015), (0.9, 0.84), (90, 86),
        region=SECOND_REGION,
    ),
    # No data at all.
    SeedDomain(
        "northwind-silent.example", "HEALTHY", True, NO_RATE, NO_RATE, NO_RATE, NO_RATE,
        sent_per_day=0, region=SECOND_REGION,
    ),
    # 24 sends in 3 days is under the minimum of 30. One bounce a day would top the table if it counted.
    SeedDomain(
        "northwind-lowvol.example", "HEALTHY", True, (0.125, 0.125), (0.03, 0.03), (0.9, 0.9), (88, 90),
        sent_per_day=8, region=SECOND_REGION,
    ),
    # Bounces with no sends.
    SeedDomain(
        "northwind-nosends.example", "HEALTHY", True, NO_RATE, NO_RATE, NO_RATE, NO_RATE,
        sent_per_day=0, bounces_per_day=3, region=SECOND_REGION,
    ),
    # One placement result in the whole window.
    SeedDomain(
        "northwind-sparse.example", "HEALTHY", True, (0.015, 0.015), (0.025, 0.025), (0.9, 0.9), (89, 91),
        placement_every_days=14, region=SECOND_REGION,
    ),
    # A second customer, whose high bounce rate would stand out if it leaked into customer 1's page.
    SeedDomain(
        "contoso-outreach.example", "AT_RISK", True, (0.08, 0.11), (0.02, 0.01), (0.8, 0.7), (80, 72),
        customer_id=2,
    ),
]


def is_local_url(url: str) -> bool:
    return conninfo_to_dict(url).get("host") in LOCAL_HOSTS


def interpolate(span: tuple[float, float], progress: float) -> float:
    return span[0] + (span[1] - span[0]) * progress


def daily_events(
    domain: SeedDomain, domain_id: int, day: datetime, day_index: int, rng: random.Random
) -> list[tuple]:
    """Events for one day. day_index counts from 0 on the oldest day of the window."""

    def at() -> datetime:
        return day + timedelta(seconds=rng.randrange(86_400))

    progress = day_index / (DAYS - 1)
    sent = domain.sent_per_day
    bounces = domain.bounces_per_day
    if bounces is None:
        bounces = round(sent * interpolate(domain.bounce_rate, progress))
    replies = round(sent * interpolate(domain.reply_rate, progress))
    rows = [(at(), domain_id, "SENT", None, None) for _ in range(sent)]
    rows += [(at(), domain_id, "BOUNCE", rng.choice(["HARD", "SOFT", "BLOCK"]), None) for _ in range(bounces)]
    rows += [(at(), domain_id, "REPLY", None, None) for _ in range(replies)]
    if sent > 0:  # a domain that sends nothing has no placement or warmup readings
        if day_index % domain.placement_every_days == 0:
            rows.append((at(), domain_id, "PLACEMENT", None, interpolate(domain.placement, progress)))
        rows.append((at(), domain_id, "WARMUP_SCORE", None, interpolate(domain.warmup, progress)))
    return rows


def provision(core_url: str, customer_id: int, batch_id: int, name: str) -> int:
    body = json.dumps({"customerId": customer_id, "serverBatchId": batch_id, "name": name}).encode()
    request = urllib.request.Request(
        f"{core_url}/api/v1/domains", data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)["id"]


def seed_batch(conn: psycopg.Connection, customer_id: int, region: str = REGION) -> int:
    found = conn.execute(
        "SELECT id FROM server_batches WHERE customer_id = %s AND region = %s", (customer_id, region)
    ).fetchone()
    if found:
        return found[0]
    return conn.execute(
        "INSERT INTO server_batches (customer_id, region) VALUES (%s, %s) RETURNING id", (customer_id, region)
    ).fetchone()[0]


def delete_seeded(conn: psycopg.Connection) -> None:
    """Delete the seeded domains and their events, all or nothing. Server batches are kept and reused."""
    names = [domain.name for domain in SEED_DOMAINS]
    with conn.transaction():
        conn.execute(
            "DELETE FROM deliverability_events "
            "WHERE domain_id IN (SELECT id FROM domains WHERE name = ANY(%s))",
            (names,),
        )
        conn.execute("DELETE FROM domains WHERE name = ANY(%s)", (names,))


@click.command()
@click.option("--core-url", default="http://localhost:8081", show_default=True)
@click.option("--reset", is_flag=True, help="Delete the seeded domains and their events, then seed again.")
def main(core_url: str, reset: bool) -> None:
    db_url = os.environ.get("AEROSEND_DB_URL")
    if not db_url:
        raise click.ClickException("Set AEROSEND_DB_URL explicitly, so this cannot seed the wrong database.")
    if not is_local_url(db_url):
        raise click.ClickException("Refusing to seed a database that is not on localhost.")

    with connect() as conn:
        conn.autocommit = True  # refresh_continuous_aggregate cannot run inside a transaction
        if reset:
            delete_seeded(conn)
            click.echo(f"deleted {len(SEED_DOMAINS)} seeded domains and their events")
        existing = {row[0] for row in conn.execute("SELECT name FROM domains")}
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        for domain in SEED_DOMAINS:
            if domain.name in existing:
                click.echo(f"skipped {domain.name}: already exists")
                continue
            batch_id = seed_batch(conn, domain.customer_id, domain.region)
            domain_id = provision(core_url, domain.customer_id, batch_id, domain.name)
            conn.execute(
                "UPDATE domains SET burn_status = %s, dns_verified = %s WHERE id = %s",
                (domain.burn_status, domain.dns_verified, domain_id),
            )
            rng = random.Random(domain.name)
            rows = []
            for day_index in range(DAYS):  # stops at yesterday: only complete days are aggregated
                day = today - timedelta(days=DAYS - day_index)
                rows += daily_events(domain, domain_id, day, day_index, rng)
            if rows:
                with conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO deliverability_events (time, domain_id, kind, bounce_type, value) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        rows,
                    )
            click.echo(f"seeded {domain.name}: {domain.burn_status}, {len(rows)} events")

        # The whole range, because --reset can delete rows far older than the days seeded here.
        conn.execute("CALL refresh_continuous_aggregate('domain_daily_stats', NULL, NULL)")


if __name__ == "__main__":
    main()
