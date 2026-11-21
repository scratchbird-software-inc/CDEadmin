"""Per-database PostgreSQL runtime capability discovery & lossless SQL_ASCII handling (PG-AUDIT-CAPABILITIES-01 & PG-AUDIT-LANGUAGE-01).

Inspects actual installed extensions, available versions, prerequisite dependencies,
relocatability, procedural languages, foreign-data wrappers, access methods,
database encoding, and diagnostic views (`pg_stat_statements`, `amcheck`) without
inferring availability from generic `CREATE EXTENSION` syntax.
"""
from __future__ import annotations

import base64
from psycopg import sql
from psycopg.rows import dict_row

from .support_policy import effective_capabilities_for_version


def inspect_runtime_capabilities(conn) -> dict:
    """Discover installed & available runtime capabilities on an active PostgreSQL connection."""
    with conn.cursor(row_factory=dict_row) as cur:
        header = cur.execute(
            """
            SELECT
                (SELECT system_identifier::text FROM pg_catalog.pg_control_system()) AS system_identifier,
                current_setting('server_version_num')::int AS server_version_num,
                current_setting('server_version') AS server_version,
                pg_catalog.current_database() AS database,
                pg_catalog.pg_encoding_to_char(d.encoding) AS server_encoding,
                d.datcollate AS lc_collate,
                d.datctype AS lc_ctype,
                current_setting('shared_preload_libraries') AS shared_preload_libraries
            FROM pg_catalog.pg_database d
            WHERE d.datname = pg_catalog.current_database()
            """
        ).fetchone()

        installed_extensions = cur.execute(
            """
            SELECT
                e.extname AS name,
                n.nspname AS schema,
                e.extversion AS version,
                e.extrelocatable AS relocatable,
                COALESCE(
                    (
                        SELECT array_agg(req.extname ORDER BY req.extname)
                        FROM pg_catalog.pg_depend dep
                        JOIN pg_catalog.pg_extension req
                          ON req.oid = dep.refobjid
                        WHERE dep.classid = 'pg_extension'::regclass
                          AND dep.objid = e.oid
                          AND dep.refclassid = 'pg_extension'::regclass
                          AND dep.deptype = 'n'
                    ),
                    ARRAY[]::name[]
                ) AS installed_dependencies,
                (
                    SELECT count(*)::int
                    FROM pg_catalog.pg_depend dep
                    WHERE dep.refclassid = 'pg_extension'::regclass
                      AND dep.refobjid = e.oid
                      AND dep.deptype = 'e'
                ) AS owned_object_count
            FROM pg_catalog.pg_extension e
            JOIN pg_catalog.pg_namespace n ON n.oid = e.extnamespace
            ORDER BY e.extname
            """
        ).fetchall()

        available_extensions = cur.execute(
            """
            SELECT
                a.name,
                a.default_version,
                a.installed_version,
                a.comment,
                COALESCE(
                    (
                        SELECT array_agg(DISTINCT u ORDER BY u)
                        FROM (
                            SELECT unnest(v.requires) AS u
                            FROM pg_catalog.pg_available_extension_versions v
                            WHERE v.name = a.name AND v.version = a.default_version
                        ) sub
                    ),
                    ARRAY[]::name[]
                ) AS requires,
                (
                    SELECT v.relocatable
                    FROM pg_catalog.pg_available_extension_versions v
                    WHERE v.name = a.name AND v.version = a.default_version
                    LIMIT 1
                ) AS relocatable,
                (
                    SELECT v.trusted
                    FROM pg_catalog.pg_available_extension_versions v
                    WHERE v.name = a.name AND v.version = a.default_version
                    LIMIT 1
                ) AS trusted
            FROM pg_catalog.pg_available_extensions a
            ORDER BY a.name
            """
        ).fetchall()

        languages = cur.execute(
            """
            SELECT
                l.lanname AS name,
                l.lanispl AS is_procedural,
                l.lanpltrusted AS trusted,
                l.laninline <> 0 AS supports_inline_do,
                l.lanvalidator <> 0 AS has_validator
            FROM pg_catalog.pg_language l
            ORDER BY l.lanname
            """
        ).fetchall()

        fdws = cur.execute(
            """
            SELECT
                f.fdwname AS name,
                f.fdwhandler <> 0 AS has_handler,
                f.fdwvalidator <> 0 AS has_validator
            FROM pg_catalog.pg_foreign_data_wrapper f
            ORDER BY f.fdwname
            """
        ).fetchall()

        access_methods = cur.execute(
            """
            SELECT amname AS name, amtype AS kind
            FROM pg_catalog.pg_am
            ORDER BY amtype, amname
            """
        ).fetchall()

        installed_set = {row['name'] for row in installed_extensions}
        diagnostics = {
            'pg_stat_statements_installed': 'pg_stat_statements' in installed_set,
            'pg_stat_statements_preloaded': 'pg_stat_statements' in {
                p.strip() for p in (header['shared_preload_libraries'] or '').split(',') if p.strip()
            },
            'amcheck_installed': 'amcheck' in installed_set,
            'postgres_fdw_installed': 'postgres_fdw' in installed_set,
            'pg_stat_io_available': int(header['server_version_num']) >= 160000,
        }

    return {
        'system_identifier': header['system_identifier'],
        'server_version': header['server_version'],
        'server_version_num': int(header['server_version_num']),
        'version_capabilities': effective_capabilities_for_version(int(header['server_version_num'])),
        'database': header['database'],
        'encoding': {
            'server_encoding': header['server_encoding'],
            'lc_collate': header['lc_collate'],
            'lc_ctype': header['lc_ctype'],
            'arbitrary_bytes_allowed': header['server_encoding'] == 'SQL_ASCII',
        },
        'installed_extensions': list(installed_extensions),
        'available_extensions': list(available_extensions),
        'languages': list(languages),
        'foreign_data_wrappers': list(fdws),
        'access_methods': list(access_methods),
        'diagnostics': diagnostics,
    }


def decode_sql_ascii_cell(raw_bytes: bytes | str | None) -> dict:
    """Losslessly represent SQL_ASCII text/identifier bytes without Unicode replacement corruption."""
    if raw_bytes is None:
        return {'is_null': True, 'utf8_valid': True, 'text': None, 'raw_base64': None, 'raw_hex': None}
    if isinstance(raw_bytes, str):
        encoded = raw_bytes.encode('utf8', errors='surrogateescape')
        try:
            clean = encoded.decode('utf8', errors='strict')
            return {
                'is_null': False,
                'utf8_valid': True,
                'text': clean,
                'raw_base64': base64.b64encode(encoded).decode('ascii'),
                'raw_hex': encoded.hex(),
            }
        except UnicodeDecodeError:
            return {
                'is_null': False,
                'utf8_valid': False,
                'text': None,
                'raw_base64': base64.b64encode(encoded).decode('ascii'),
                'raw_hex': encoded.hex(),
            }
    data = bytes(raw_bytes)
    try:
        decoded = data.decode('utf8', errors='strict')
        return {
            'is_null': False,
            'utf8_valid': True,
            'text': decoded,
            'raw_base64': base64.b64encode(data).decode('ascii'),
            'raw_hex': data.hex(),
        }
    except UnicodeDecodeError:
        return {
            'is_null': False,
            'utf8_valid': False,
            'text': None,
            'raw_base64': base64.b64encode(data).decode('ascii'),
            'raw_hex': data.hex(),
        }


def fetch_sql_ascii_rows_lossless(conn, schema_name: str, table_name: str, *, limit: int = 100) -> list[list[dict]]:
    """Read rows from a SQL_ASCII database as raw wire bytes (`convert_to(..., 'SQL_ASCII')` / bytea) without U+FFFD loss."""
    from psycopg.types.string import ByteaLoader
    with conn.cursor() as cur:
        cur.adapters.register_loader(17, ByteaLoader)
        cols = [
            r[0].decode('utf8', errors='surrogateescape') if isinstance(r[0], bytes) else r[0]
            for r in cur.execute(
                """
                SELECT a.attname
                FROM pg_catalog.pg_attribute a
                JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
                JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = %s AND c.relname = %s AND a.attnum > 0 AND NOT a.attisdropped
                ORDER BY a.attnum
                """,
                (schema_name, table_name),
            ).fetchall()
        ]
        exprs = sql.SQL(', ').join(
            sql.SQL('pg_catalog.convert_to({}::text, \'SQL_ASCII\')').format(sql.Identifier(c))
            for c in cols
        )
        rows = cur.execute(
            sql.SQL('SELECT {} FROM {}.{} LIMIT %s').format(
                exprs, sql.Identifier(schema_name), sql.Identifier(table_name)
            ),
            (int(limit),),
        ).fetchall()
        return [[decode_sql_ascii_cell(cell) for cell in row] for row in rows]
