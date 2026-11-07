import json
import random
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from io import BytesIO

import pytest
from click.testing import CliRunner

from aerosend_utils import seed_local
from aerosend_utils.seed_local import (
    DAYS,
    REGION,
    SECOND_REGION,
    SEED_DOMAINS,
    SeedDomain,
    daily_events,
    is_local_url,
)

DAY = datetime(2026, 11, 1, tzinfo=timezone.utc)


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1"])
def test_local_hosts_are_allowed(host):
    assert is_local_url(f"postgresql://aerosend:aerosend@{host}:15432/aerosend")


@pytest.mark.parametrize("host", ["db.aerosend.io", "10.0.0.5"])
def test_other_hosts_are_refused(host):
    assert not is_local_url(f"postgresql://aerosend:aerosend@{host}:5432/aerosend")


def domain(**overrides):
    fields = {
        "name": "test.example",
        "burn_status": "HEALTHY",
        "dns_verified": True,
        "bounce_rate": (0.02, 0.02),
        "reply_rate": (0.04, 0.04),
        "placement": (0.9, 0.9),
        "warmup": (90, 90),
    }
    return SeedDomain(**(fields | overrides))


def seed_domain(name):
    return next(d for d in SEED_DOMAINS if d.name == name)


def window_events(seed):
    rng = random.Random(seed.name)
    return [
        daily_events(seed, 1, DAY + timedelta(days=day_index), day_index, rng) for day_index in range(DAYS)
    ]


def kinds(rows):
    return Counter(row[2] for row in rows)


def test_defaults_match_the_original_seed():
    assert kinds(daily_events(domain(), 1, DAY, 0, random.Random(1))) == {
        "SENT": 150,
        "BOUNCE": 3,
        "REPLY": 6,
        "PLACEMENT": 1,
        "WARMUP_SCORE": 1,
    }


def test_original_domains_keep_the_default_fields():
    for seed in SEED_DOMAINS[:6]:
        assert (seed.customer_id, seed.sent_per_day, seed.bounces_per_day, seed.placement_every_days) == (
            1,
            150,
            None,
            1,
        )
        assert seed.region == REGION


def test_rates_trend_from_oldest_to_most_recent_day():
    days = window_events(seed_domain("northwind-stale.example"))
    assert kinds(days[0])["BOUNCE"] == 3  # 2% of 150
    assert kinds(days[-1])["BOUNCE"] == 11  # 7% of 150, rounded up


def test_low_volume_domain_stays_under_the_three_day_minimum():
    days = window_events(seed_domain("northwind-lowvol.example"))
    assert all(kinds(rows)["SENT"] == 8 for rows in days)
    assert all(kinds(rows)["BOUNCE"] == 1 for rows in days)
    assert sum(kinds(rows)["SENT"] for rows in days[-3:]) == 24


def test_fixed_bounce_count_overrides_the_rate():
    assert kinds(daily_events(domain(bounces_per_day=0), 1, DAY, 0, random.Random(1)))["BOUNCE"] == 0
    assert kinds(daily_events(domain(bounces_per_day=7), 1, DAY, 0, random.Random(1)))["BOUNCE"] == 7


def test_bounces_with_no_sends():
    for rows in window_events(seed_domain("northwind-nosends.example")):
        assert kinds(rows) == {"BOUNCE": 3}


def test_silent_domain_has_no_events():
    assert all(rows == [] for rows in window_events(seed_domain("northwind-silent.example")))


@pytest.mark.parametrize(
    ("every", "expected_days"), [(1, list(range(DAYS))), (5, [0, 5, 10]), (14, [0])]
)
def test_placement_rows_only_on_expected_days(every, expected_days):
    days = window_events(domain(placement_every_days=every))
    assert [index for index, rows in enumerate(days) if kinds(rows)["PLACEMENT"]] == expected_days
    assert all(kinds(rows)["PLACEMENT"] <= 1 for rows in days)
    assert all(kinds(rows)["WARMUP_SCORE"] == 1 for rows in days)


def test_sparse_domain_has_one_placement_inside_the_window():
    days = window_events(seed_domain("northwind-sparse.example"))
    assert sum(kinds(rows)["PLACEMENT"] for rows in days) == 1


def test_second_customer_domain():
    assert seed_domain("contoso-outreach.example").customer_id == 2


def test_no_batch_exceeds_cores_limit():
    # Matches aerosend.provisioning.domains-per-batch in core's application.yml.
    batches = Counter((seed.customer_id, seed.region) for seed in SEED_DOMAINS)
    assert max(batches.values()) <= 10


def test_provision_sends_the_customer_id(monkeypatch):
    sent = {}

    def urlopen(request, timeout):
        sent.update(json.loads(request.data))
        return BytesIO(b'{"id": 5}')

    monkeypatch.setattr(seed_local.urllib.request, "urlopen", urlopen)
    assert seed_local.provision("http://core", 2, 9, "x.example") == 5
    assert sent == {"customerId": 2, "serverBatchId": 9, "name": "x.example"}


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def __iter__(self):
        return iter(self.rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeConn:
    """Records statements and keeps just enough state to show their order matters."""

    def __init__(self, names=()):
        self.names = set(names)
        self.batches = {}
        self.statements = []
        self.inserted = []
        self.open_transactions = 0
        self.autocommit = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @contextmanager
    def transaction(self):
        self.open_transactions += 1
        yield
        self.open_transactions -= 1

    def cursor(self):
        return self

    def executemany(self, sql, rows):
        self.inserted.append(rows)

    def execute(self, sql, params=None):
        self.statements.append((sql, params, self.open_transactions))
        if sql.startswith("DELETE FROM domains"):
            self.names -= set(params[0])
        if sql == "SELECT name FROM domains":
            return FakeResult([(name,) for name in self.names])
        if sql.startswith("SELECT id FROM server_batches"):
            return FakeResult([(self.batches[params],)] if params in self.batches else [])
        if sql.startswith("INSERT INTO server_batches"):
            self.batches[params] = len(self.batches) + 1
            return FakeResult([(self.batches[params],)])
        return FakeResult([])

    def sql(self):
        return [statement[0] for statement in self.statements]


@pytest.fixture
def seed_run(monkeypatch):
    """Runs the CLI against a FakeConn and a fake core, and returns what was provisioned."""
    provisioned = []

    def provision(core_url, customer_id, batch_id, name):
        provisioned.append((customer_id, batch_id, name))
        return len(provisioned)

    monkeypatch.setattr(seed_local, "provision", provision)
    monkeypatch.setenv("AEROSEND_DB_URL", "postgresql://aerosend:aerosend@localhost:15432/aerosend")

    def run(conn, *args):
        monkeypatch.setattr(seed_local, "connect", lambda: conn)
        result = CliRunner().invoke(seed_local.main, args)
        assert result.exit_code == 0, result.output
        return provisioned

    return run


@pytest.mark.parametrize("db_url", [None, "postgresql://aerosend:aerosend@db.aerosend.io:5432/aerosend"])
def test_reset_never_connects_to_a_refused_database(monkeypatch, db_url):
    def connect():
        raise AssertionError("connected before the host guard")

    monkeypatch.setattr(seed_local, "connect", connect)
    monkeypatch.delenv("AEROSEND_DB_URL", raising=False)
    if db_url:
        monkeypatch.setenv("AEROSEND_DB_URL", db_url)

    result = CliRunner().invoke(seed_local.main, ["--reset"])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)


def test_reset_deletes_then_seeds_again_then_refreshes(seed_run):
    names = [seed.name for seed in SEED_DOMAINS]
    conn = FakeConn(names + ["unrelated.example"])

    provisioned = seed_run(conn, "--reset")

    events_delete, domains_delete = conn.statements[:2]
    assert events_delete[0].startswith("DELETE FROM deliverability_events")
    assert domains_delete[0].startswith("DELETE FROM domains")
    assert events_delete[1] == domains_delete[1] == (names,)
    assert events_delete[2] == domains_delete[2] == 1  # both inside one transaction
    assert [row[2] for row in provisioned] == names
    assert "unrelated.example" in conn.names
    assert conn.sql()[-1] == "CALL refresh_continuous_aggregate('domain_daily_stats', NULL, NULL)"


def test_without_reset_existing_domains_are_kept(seed_run):
    conn = FakeConn(seed.name for seed in SEED_DOMAINS)

    provisioned = seed_run(conn)

    assert provisioned == []
    assert not any(sql.startswith("DELETE") for sql in conn.sql())
    assert conn.sql()[-1].startswith("CALL refresh_continuous_aggregate")


def test_each_domain_is_provisioned_into_its_own_customers_batch(seed_run):
    conn = FakeConn()

    provisioned = seed_run(conn)

    batch_ids = {name: (customer, batch) for customer, batch, name in provisioned}
    assert set(conn.batches) == {(1, REGION), (1, SECOND_REGION), (2, REGION)}
    assert batch_ids["contoso-outreach.example"] == (2, conn.batches[(2, REGION)])
    assert batch_ids["northwind-outreach.example"] == (1, conn.batches[(1, REGION)])
    assert batch_ids["northwind-sparse.example"] == (1, conn.batches[(1, SECOND_REGION)])


def test_silent_domain_inserts_nothing(seed_run):
    conn = FakeConn()

    seed_run(conn)

    assert len(conn.inserted) == len(SEED_DOMAINS) - 1
    assert all(conn.inserted)
