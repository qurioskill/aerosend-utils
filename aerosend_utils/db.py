import os

import psycopg

DEFAULT_URL = "postgresql://aerosend:aerosend@localhost:5432/aerosend"


def connect() -> psycopg.Connection:
    return psycopg.connect(os.environ.get("AEROSEND_DB_URL", DEFAULT_URL))
