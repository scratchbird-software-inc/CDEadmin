"""Peer-bound standalone CHECKPOINT; acknowledgement loss never means no effect."""
from psycopg import Cursor
from psycopg.rows import dict_row
from .destructive_identity import CONTEXT


def applies(request):return request.get('resource_kind')=='server'and request.get('operation_id')=='checkpoint'


def peer(connection):
    with Cursor(connection,row_factory=dict_row)as cursor:
        cursor.execute(CONTEXT);row=cursor.fetchone()
        if row is not None:
            cursor.execute('SELECT CURRENT_USER::pg_catalog.regrole::oid::text AS effective_principal_oid,SESSION_USER::pg_catalog.regrole::oid::text AS authenticated_principal_oid')
            row.update(cursor.fetchone())
    if row is None:raise ValueError('Native checkpoint peer identity is unavailable')
    return dict(row)
