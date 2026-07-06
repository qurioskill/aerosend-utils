"""Re-import bounce log CSVs into deliverability_events for a date range."""

import csv
from datetime import datetime

import click

from .bounce_classifier import classify
from .db import connect


@click.command()
@click.argument("csv_path", type=click.Path(exists=True))
@click.option("--batch-size", default=5000)
def main(csv_path: str, batch_size: int) -> None:
    rows = []
    with open(csv_path) as f:
        for r in csv.DictReader(f):
            rows.append((
                datetime.fromisoformat(r["time"]), int(r["domain_id"]), int(r["mailbox_id"]),
                classify(int(r["smtp_code"]), r["diagnostic"]),
            ))
    with connect() as conn, conn.cursor() as cur:
        for i in range(0, len(rows), batch_size):
            cur.executemany(
                "INSERT INTO deliverability_events (time, domain_id, mailbox_id, kind, bounce_type) "
                "VALUES (%s, %s, %s, 'BOUNCE', %s)",
                rows[i:i + batch_size],
            )
    click.echo(f"backfilled {len(rows)} bounces")


if __name__ == "__main__":
    main()
