"""CockroachDB admission of retained PostgreSQL-wire mechanics."""
from ..pgwire_driver import RetainedPGWireClient


class CockroachDBClient(RetainedPGWireClient):
    """CockroachDB owns retry/ambiguity and native transaction outcomes."""
