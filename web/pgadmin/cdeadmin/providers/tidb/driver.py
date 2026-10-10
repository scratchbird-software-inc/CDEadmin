"""TiDB transaction and cancellation admission over MySQL-wire mechanics."""
from pgadmin.cdeadmin.sdk import RelationalClientError
from ..mysql_wire_driver import RetainedMySQLWireClient


class TiDBNativeClient(RetainedMySQLWireClient):
    retry_errors = frozenset({1213, 9007, 8028})
    _IDENTITY = (
        'SELECT s.DDL_ID, p.ID FROM information_schema.CLUSTER_PROCESSLIST p '
        'JOIN information_schema.TIDB_SERVERS_INFO s '
        "ON p.INSTANCE=CONCAT(s.IP,':',s.STATUS_PORT) WHERE p.ID=")

    def cancellation_identity(self, handle):
        cursor = handle.cursor()
        try:
            cursor.execute(self._IDENTITY + 'CONNECTION_ID()')
            row = cursor.fetchone()
            if row:
                return str(row[0]), int(row[1])
            return None
        except Exception as exc:
            if getattr(exc, 'errno', None) in {1142, 1227}:
                return None
            raise
        finally:
            cursor.close()

    def cancel_native(self, token):
        def arguments(route):
            options = dict(self.config.connect_arguments(route))
            for name in ('pool_name', 'pool_size', 'pool_reset_session',
                         'failover', 'dns_srv'):
                options.pop(name, None)
            options.update(host=token.handle.server_host,
                           port=token.handle.server_port)
            return options

        connection = self._invoke_connector(
            token.request, self.module.connect, connect_arguments=arguments)
        try:
            cursor = connection.cursor()
            try:
                cursor.execute(self._IDENTITY + '%s', (token.identity[1],))
                row = cursor.fetchone()
                if not row or (str(row[0]), int(row[1])) != token.identity:
                    raise RelationalClientError('TiDB query origin changed')
                cursor.execute('KILL TIDB QUERY ' + str(token.identity[1]))
            finally:
                cursor.close()
        finally:
            connection.close()
