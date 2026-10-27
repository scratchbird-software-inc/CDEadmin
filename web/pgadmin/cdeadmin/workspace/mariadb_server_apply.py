"""Durable one-use native MariaDB server reviews."""
from .mysql_server_apply import MySQLServerApplications


class MariaDBServerApplications(MySQLServerApplications):
    format = 'scratchrobin.mariadb.server-plan@1'
