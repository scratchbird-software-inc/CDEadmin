"""YSQL admission of retained PG-wire mechanics."""
from ..pgwire_driver import RetainedPGWireClient


class YugabyteDBYSQLClient(RetainedPGWireClient):
    """YSQL owns retry/ambiguity and distributed transaction outcomes."""
