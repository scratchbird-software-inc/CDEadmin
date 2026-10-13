"""Disabled native binary logging is distinct from denied or failed discovery."""
import pytest
from pgadmin.cdeadmin.providers.mysql_family.provider import _resources, MARIADB_PROFILE


@pytest.mark.parametrize('enabled,code,partial', [(0,1381,False), (1,1381,True),
    (None,1381,True), (0,1142,True), (0,2006,True)])
def test_binary_log_unavailability_requires_both_native_error_and_disabled_observation(enabled, code, partial):
    class NativeError(Exception):
        errno = code
        sqlstate = 'HY000'
    class Cursor:
        description = ()
        def execute(self, source, parameters=()):
            self.source = source
            if source == 'SHOW BINARY LOGS': raise NativeError()
        def fetchall(self):
            if self.source.startswith('SELECT VERSION()'):
                row = [None] * 20
                row[0] = '12.2.2-MariaDB'; row[15] = enabled
                return [tuple(row)]
            return []
        def close(self): pass
    class Connection:
        def cursor(self): return Cursor()
    resources = _resources(Connection(), {}, MARIADB_PROFILE)
    server = next(row for row in resources if row['resource_kind'] == 'server')
    coverage = server['native']['catalog_coverage']
    assert (coverage['state'] == 'partial') == partial
    assert bool(coverage.get('unavailable')) == (not partial)
    assert coverage['failed_query_count'] == int(partial)
    assert not any(row['resource_kind'] == 'binary-log' for row in resources)
