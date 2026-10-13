"""MariaDB owner admission with shared sealed-lease monitoring infrastructure."""
from .mysql_monitoring_host import MySQLMonitoringHost, init_app as init_native_host


class MariaDBMonitoringHost(MySQLMonitoringHost):
    engine = 'mariadb'
    profile_id = 'mariadb-native'
    provider_id = 'org.cdeadmin.mariadb'
    identity_key = 'server_uid'


def init_app(app, shared_host):
    return init_native_host(app, shared_host, MariaDBMonitoringHost)
