"""YSQL admission of retained PG-wire mechanics."""
from ..pgwire_driver import RetainedPGWireClient
from ...ui_descriptors.field_contract import DescriptorFieldContract


class YugabyteDBYSQLClient(DescriptorFieldContract, RetainedPGWireClient):
    """YSQL owns retry/ambiguity and distributed transaction outcomes."""
    descriptor_engine = 'yugabytedb'
