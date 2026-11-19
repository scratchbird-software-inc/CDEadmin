"""Bounded PostgreSQL row pages and session-owned row identities."""

import base64
from contextlib import nullcontext
from datetime import date, datetime, time
from decimal import Decimal
import math
from uuid import UUID, uuid4

from psycopg import sql
from psycopg.types.json import Jsonb


def wire_value(value):
    if value is None or isinstance(value, (bool, int, str)):
        return str(value) if type(value) is int and abs(value) >= 2**53 else value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if isinstance(value, (bytes, memoryview)):
        data = bytes(value)
        return {'encoding': 'base64', 'data': base64.b64encode(data).decode('ascii'),
                'byte_length': len(data)}
    if isinstance(value, (tuple, list)):
        return [wire_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): wire_value(item) for key, item in value.items()}
    return str(value)


class RowPage:
    def __init__(self, connection, relation_oid, token, buffer_limit, *, allow_edit=False,
                 native_scope=nullcontext):
        self.token = token
        self.relation_oid = relation_oid
        self.pending = []
        self.identities = {}
        self.keys = []
        self.operations = []
        with connection.cursor() as catalog:
            def catalog_query(source, parameters):
                with native_scope():
                    catalog.execute(source, parameters)

            catalog_query(
                """SELECT n.nspname, c.relname, c.relkind, c.relhassubclass
                     FROM pg_catalog.pg_class c
                     JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.oid = %s AND c.relkind IN ('r', 'p', 'v', 'm', 'f')""",
                (relation_oid,),
            )
            relation = catalog.fetchone()
            if not relation:
                raise ValueError('PostgreSQL relation is unavailable')
            catalog_query(
                """SELECT attname, pg_catalog.format_type(atttypid, atttypmod), attnotnull
                     FROM pg_catalog.pg_attribute
                    WHERE attrelid = %s AND attnum > 0 AND NOT attisdropped
                    ORDER BY attnum""",
                (relation_oid,),
            )
            self.relation = sql.Identifier(*relation[:2])
            self.columns = [
                {'name': name, 'native_type': kind, 'nullable': not required,
                 'editable': False, 'read_only': True, 'insertable': False}
                for name, kind, required in catalog.fetchall()
            ]
            if allow_edit and relation[2] == 'r' and not relation[3]:
                catalog_query(
                    """SELECT a.attname FROM pg_catalog.pg_index i
                         CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, position)
                         JOIN pg_catalog.pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum
                        WHERE i.indrelid = %s AND i.indisprimary AND i.indisvalid
                          AND k.position <= i.indnkeyatts ORDER BY k.position""", (relation_oid,)
                )
                self.keys = [row[0] for row in catalog.fetchall()]
                if self.keys:
                    catalog_query(
                        """SELECT has_table_privilege(%s::oid, 'INSERT'), has_table_privilege(%s::oid, 'UPDATE'),
                                  has_table_privilege(%s::oid, 'DELETE')""", (relation_oid,) * 3
                    )
                    self.operations = [operation for operation, available in zip(
                        ('insert', 'update', 'delete'), catalog.fetchone()) if available]
                    catalog_query(
                        """SELECT attname, attgenerated, attidentity
                             FROM pg_catalog.pg_attribute
                            WHERE attrelid = %s AND attnum > 0 AND NOT attisdropped""", (relation_oid,)
                    )
                    attributes = {name: (generated, identity) for name, generated, identity in catalog.fetchall()}
                    for column in self.columns:
                        name = column['name']
                        generated, identity = attributes[name]
                        supported = column['native_type'] != 'bytea' and not generated and identity != 'a'
                        column.update(key=name in self.keys,
                                      insertable=supported and 'insert' in self.operations,
                                      editable=supported and 'update' in self.operations and name not in self.keys)
                        column['read_only'] = not column['editable']
        self.cursor = connection.cursor(
            name='scratchrobin_' + token, scrollable=False,
            withhold=connection.autocommit,
        )
        try:
            with native_scope():
                self.cursor.execute(
                    sql.SQL('SELECT *{} FROM {} LIMIT {}').format(
                        sql.SQL(', xmin::text') if self.operations else sql.SQL(''),
                        self.relation, sql.Literal(buffer_limit + 1)
                    )
                )
        except BaseException:
            self.cursor.close()
            raise

    def fetch(self, limit, *, native_scope=nullcontext):
        with native_scope():
            page = self.pending + self.cursor.fetchmany(limit + 1 - len(self.pending))
        self.pending = page[limit:]
        names = [column['name'] for column in self.columns]
        rows = []
        for row in page[:limit]:
            values = dict(zip(names, row))
            result = {'values': {name: wire_value(value) for name, value in values.items()}}
            if self.operations:
                token = uuid4().hex
                self.identities[token] = (tuple(values[name] for name in self.keys), row[-1])
                result['identity_token'] = token
            rows.append(result)
        return {
            'columns': self.columns, 'rows': rows,
            'editable': bool(self.operations),
            'identity_policy': 'primary-key-and-version' if self.operations else 'read-only-relation',
            'row_operations': self.operations,
            'continuation': self.token if self.pending else None,
        }

    def mutation(self, operation, draft):
        if operation not in self.operations or not isinstance(draft, dict):
            raise ValueError('PostgreSQL row operation is unavailable')
        if operation == 'insert':
            values = draft.get('values')
            permitted = {column['name'] for column in self.columns if column['insertable']}
        else:
            token = (draft.get('selector') or {}).get('identity_token')
            if not isinstance(token, str) or token not in self.identities:
                raise ValueError('PostgreSQL row identity has expired')
            keys, version = self.identities[token]
            predicates = [sql.SQL('{} = %s').format(sql.Identifier(name)) for name in self.keys]
            where = sql.SQL(' WHERE ') + sql.SQL(' AND ').join([*predicates, sql.SQL('xmin::text = %s')])
            identity = (*keys, version)
            if operation == 'delete':
                return sql.SQL('DELETE FROM {}').format(self.relation) + where, identity
            values = draft.get('changes')
            permitted = {column['name'] for column in self.columns if column['editable']}
        if not isinstance(values, dict) or values.keys() - permitted:
            raise ValueError('PostgreSQL row changes contain a non-writable field')
        if not values:
            if operation == 'insert':
                return sql.SQL('INSERT INTO {} DEFAULT VALUES').format(self.relation), ()
            raise ValueError('No PostgreSQL row changes were supplied')
        names = sql.SQL(', ').join(map(sql.Identifier, values))
        record = sql.SQL('SELECT {} FROM pg_catalog.jsonb_populate_record(NULL::{}, %s)').format(names, self.relation)
        if operation == 'insert':
            return sql.SQL('INSERT INTO {} ({}) ').format(self.relation, names) + record, (Jsonb(values),)
        return sql.SQL('UPDATE {} SET ({}) = ({})').format(self.relation, names, record) + where, (Jsonb(values), *identity)

    def close(self):
        self.cursor.close()
