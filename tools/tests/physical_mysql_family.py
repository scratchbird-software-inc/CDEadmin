"""Shared harness for MySQL and MariaDB forward -> edit -> reverse -> plan tests of physical-schema edits.

Two sources feed the same pipeline:

* ``GoldenEnv`` builds the catalog resources by hand in the exact shape the capture modules emit
  (SHOW CREATE TABLE text plus the COLUMNS / KEY_COLUMN_USAGE children). It needs no server and is the only
  evidence level available for MySQL in this container (see docs/en_US/ddn_physical_schema_vocabulary.rst).
* ``LiveEnv`` (tests/test_mariadb_physical_roundtrip.py) captures a real MariaDB server.

Edits go through DDN's public source-patch API (physical_roundtrip.py), exactly like a records-table edit.
"""
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT / 'web', ROOT / 'tools', ROOT / 'tools' / 'tests'):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

import physical_roundtrip as rt  # noqa: E402
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export  # noqa: E402
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog  # noqa: E402
from pgadmin.cdeadmin.workspace.firebird_relational_review import handoff, read_relations  # noqa: E402

ENDPOINT, TARGET = 'ep', 'physrt'
VERSION = {'mysql': '9.7.0', 'mariadb': '12.2.2'}


def plan_function(engine):
    if engine == 'mysql':
        from pgadmin.cdeadmin.workspace.mysql_schema_plan import plan
    else:
        from pgadmin.cdeadmin.workspace.mariadb_schema_plan import plan
    return plan


def tick(name):
    return '`' + name.replace('`', '``') + '`'


def quote(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


class Env:
    """The pipeline shared by golden and live fixtures; subclasses supply ``resources()``."""

    def __init__(self, engine, database=TARGET):
        self.engine, self.database = engine, database

    # --- identities
    def rid(self, kind, name):
        root = self.engine + ':' + quote([self.database, 'database', None, self.database])
        return self.engine + ':' + quote([self.database, kind, root, name])

    def uid(self, resource_id):
        return self.engine + ':' + ENDPOINT + ':' + TARGET + ':' + resource_id

    def child(self, table, kind, name):
        """Resource id of an index/primary-key/unique/check element of ``table``."""
        return self.rid('table', table) + ':' + kind + ':' + quote(name)

    def column(self, table, name):
        return self.rid('table', table) + ':' + quote(name)

    def foreign_key(self, table, name):
        return self.rid('table', table) + ':foreign-key:' + quote(name)

    # --- pipeline
    def export(self):
        self.catalog = build_export(self.resources(), endpoint_id=ENDPOINT, target_id=TARGET, generation='g1', engine=self.engine)
        self.diagram = self.catalog['diagram']
        return self.diagram

    def review(self, edited, **flags):
        result = handoff(self.catalog['snapshot'], self.diagram['snapshot'], edited, engine=self.engine, **flags)
        self.pair = (read_catalog(result['baseline'], engine=self.engine), read_catalog(result['desired'], engine=self.engine))
        return result, self.plan()

    def handoff_only(self, edited, **flags):
        return handoff(self.catalog['snapshot'], self.diagram['snapshot'], edited, engine=self.engine, **flags)

    def current(self, generation='g2'):
        return build_export(self.resources(), endpoint_id=ENDPOINT, target_id=TARGET, generation=generation,
                            engine=self.engine, native_model=True)

    def plan(self):
        return plan_function(self.engine)(self.pair[0], self.pair[1], self.current())

    def edit(self, resource_id, **values):
        return rt.edit_vocabulary(self.diagram, resource_id, **values)

    def draft(self, table, role, title, values, snapshot=None):
        rid = self.rid('table', table)
        edited, _uid = rt.add_draft_element(self.diagram, snapshot or self.diagram['snapshot'], rid, self.uid(rid), role, title,
                                            values, self.engine)
        return edited

    def draft_foreign_key(self, source, target, title, values, snapshot=None):
        edited, _uid = rt.add_draft_foreign_key(self.diagram, snapshot or self.diagram['snapshot'], self.rid('table', source),
                                                self.rid('table', target), self.uid(self.rid('table', source)), title, values, self.engine)
        return edited

    def vocabulary(self, snapshot=None):
        """{physical_name or (table, name): physical dict} as the reverse reader sees the diagram."""
        rows = read_relations(snapshot or self.diagram['snapshot'], engine=self.engine)
        found = {}
        for row in rows.values():
            if row.get('physical'):
                found[row['resource_id']] = row['physical']
            for edge in row.get('graphical_relationships', []):
                if edge.get('physical'):
                    found[edge['uid']] = edge['physical']
        return found


def sources(plan):
    return [item['source'] for item in plan['operations']]


def operations(plan):
    return [(item['name'], item['operation']) for item in plan['operations']]


# ---------------------------------------------------------------------------------------------- golden fixtures

PARENT_MYSQL = ('CREATE TABLE `parent` (\n  `id` int NOT NULL,\n  `code` varchar(20) DEFAULT NULL,\n  `region` varchar(20) DEFAULT NULL,\n'
                '  PRIMARY KEY (`id`),\n  UNIQUE KEY `parent_code_key` (`code`)\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci')
CHILD_MYSQL = ('CREATE TABLE `child` (\n  `id` int NOT NULL,\n  `parent_id` int DEFAULT NULL,\n  `amount` int DEFAULT NULL,\n'
               '  `note` varchar(40) DEFAULT NULL,\n  `body` text,\n  KEY `child_amount_idx` (`amount`),\n  KEY `child_parent_fk` (`parent_id`),\n'
               '  FULLTEXT KEY `child_body_ft` (`body`),\n'
               '  CONSTRAINT `child_parent_fk` FOREIGN KEY (`parent_id`) REFERENCES `parent` (`id`) ON DELETE CASCADE,\n'
               '  CONSTRAINT `child_amount_check` CHECK ((`amount` > 0))\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci')
PARENT_MARIADB = ('CREATE TABLE `parent` (\n  `id` int(11) NOT NULL,\n  `code` varchar(20) DEFAULT NULL,\n  `region` varchar(20) DEFAULT NULL,\n'
                  '  PRIMARY KEY (`id`),\n  UNIQUE KEY `parent_code_key` (`code`)\n) ENGINE=InnoDB DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci')
CHILD_MARIADB = ('CREATE TABLE `child` (\n  `id` int(11) NOT NULL,\n  `parent_id` int(11) DEFAULT NULL,\n  `amount` int(11) DEFAULT NULL,\n'
                 '  `note` varchar(40) DEFAULT NULL,\n  `body` text DEFAULT NULL,\n  KEY `child_amount_idx` (`amount`),\n  KEY `child_parent_fk` (`parent_id`),\n'
                 '  FULLTEXT KEY `child_body_ft` (`body`),\n'
                 '  CONSTRAINT `child_parent_fk` FOREIGN KEY (`parent_id`) REFERENCES `parent` (`id`) ON DELETE CASCADE,\n'
                 '  CONSTRAINT `child_amount_check` CHECK (`amount` > 0)\n) ENGINE=InnoDB DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci')
COLUMNS = {'parent': [('id', 'int', False), ('code', 'varchar(20)', True), ('region', 'varchar(20)', True)],
           'child': [('id', 'int', False), ('parent_id', 'int', True), ('amount', 'int', True), ('note', 'varchar(40)', True),
                     ('body', 'text', True)]}
FOREIGN = {'child': [('child_parent_fk', 'parent_id', 'parent', 'id')]}


class GoldenEnv(Env):
    """A catalog built by hand in the capture modules' exact shape; ``tables`` maps name -> SHOW CREATE TABLE text."""

    def __init__(self, engine, tables=None, columns=None, foreign=None, database=TARGET):
        super().__init__(engine, database)
        self.tables = dict(tables or {'parent': PARENT_MYSQL if engine == 'mysql' else PARENT_MARIADB,
                                      'child': CHILD_MYSQL if engine == 'mysql' else CHILD_MARIADB})
        self.columns = dict(columns or COLUMNS)
        self.foreign = dict(foreign or FOREIGN)

    def resources(self):
        engine, db = self.engine, self.database
        root_id = engine + ':' + quote([db, 'database', None, db])
        context = {'sql_mode': '', 'character_set_client': 'utf8mb4', 'collation_connection': 'utf8mb4_0900_ai_ci'}
        identity = {'database_name': db, 'version': VERSION[engine], 'sql_mode': '',
                    'character_set_client': 'utf8mb4', 'collation_connection': 'utf8mb4_0900_ai_ci'}
        identity['server_uuid' if engine == 'mysql' else 'server_uid'] = 'golden-server'
        out = [{'resource_id': root_id, 'resource_kind': 'database', 'display_name': db, 'display_path': [db],
                'native': {'system_object': False, 'database': db, 'catalog_row': identity, 'definition': 'CREATE DATABASE ' + tick(db),
                           'definition_context': context,
                           'catalog_observations': [{'section': s, 'available': True} for s in
                                                    ('KEY_COLUMN_USAGE', 'VIEW_TABLE_USAGE', 'ROUTINE_LIBRARIES')]}}]
        for name, definition in sorted(self.tables.items()):
            children = {'COLUMNS': [{'table_name': name, 'column_name': column, 'column_type': type_,
                                     'is_nullable': 'YES' if nullable else 'NO', 'ordinal_position': index + 1}
                                    for index, (column, type_, nullable) in enumerate(self.columns[name])]}
            usage = [{'table_name': name, 'constraint_name': fk, 'column_name': column, 'ordinal_position': 1,
                      'referenced_table_schema': db, 'referenced_table_name': target, 'referenced_column_name': referenced}
                     for fk, column, target, referenced in self.foreign.get(name, [])]
            if usage:
                children['KEY_COLUMN_USAGE'] = usage
            out.append({'resource_id': engine + ':' + quote([db, 'table', root_id, name]), 'resource_kind': 'table',
                        'display_name': name, 'display_path': [db, name],
                        'native': {'system_object': False, 'database': db, 'navigator_parent_resource_id': root_id,
                                   'definition': definition, 'definition_context': dict(context), 'catalog_row': {'table_name': name},
                                   'children': children}})
        return out

    def alter(self, table, old, new):
        """Pretend the server applied a change: textual replacement in a table's SHOW CREATE TABLE."""
        assert old in self.tables[table], (old, self.tables[table])
        self.tables[table] = self.tables[table].replace(old, new)
