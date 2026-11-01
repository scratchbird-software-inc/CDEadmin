"""CockroachDB admission of retained PostgreSQL-wire mechanics."""
from ..pgwire_driver import RetainedPGWireClient
from ...ui_descriptors.field_contract import DescriptorFieldContract


class CockroachDBClient(DescriptorFieldContract, RetainedPGWireClient):
    """CockroachDB owns retry/ambiguity and native transaction outcomes."""
    descriptor_engine = 'cockroachdb'
