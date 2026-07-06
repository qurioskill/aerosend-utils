"""Biweekly inbox placement test: send to a seed list, read where each message landed."""

from dataclasses import dataclass
from datetime import datetime, timezone

import click

from .db import connect


@dataclass
class SeedResult:
    domain_id: int
    provider: str  # gmail | outlook | yahoo | other
    landed: str    # inbox | spam | missing


def placement_rate(results: list[SeedResult]) -> float:
    if not results:
        return 0.0
    return sum(r.landed == "inbox" for r in results) / len(results)


def record(domain_id: int, rate: float) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO deliverability_events (time, domain_id, kind, value) VALUES (%s, %s, 'PLACEMENT', %s)",
            (datetime.now(timezone.utc), domain_id, rate),
        )


@click.command()
@click.option("--domain-id", type=int, required=True)
@click.option("--dry-run", is_flag=True)
def main(domain_id: int, dry_run: bool) -> None:
    # TODO: fetch real seed results from the GlockApps-style seed provider
    results = [SeedResult(domain_id, "gmail", "inbox"), SeedResult(domain_id, "outlook", "spam")]
    rate = placement_rate(results)
    click.echo(f"domain {domain_id}: {rate:.0%} inbox placement")
    if not dry_run:
        record(domain_id, rate)


if __name__ == "__main__":
    main()
