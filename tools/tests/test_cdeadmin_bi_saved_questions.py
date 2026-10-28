##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Saved question and collection tests: validation, per-engine compilation,
service lifecycle and live SQLite / DuckDB execution of compiled SQL."""

from __future__ import annotations

import copy
import sqlite3
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

try:
    import duckdb
except ImportError:  # pragma: no cover
    duckdb = None


ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / 'web'
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(WEB / 'pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.bi import (  # noqa: E402
    BIConflict, BIError, BIService, validate_question,
)
from pgadmin.cdeadmin.sdk.actual_engine import (  # noqa: E402
    ActualEnginePilotProvider,
)
from pgadmin.cdeadmin.providers.duckdb.provider import (  # noqa: E402
    PROFILE as DUCKDB,
)
from pgadmin.cdeadmin.providers.firebird.provider import (  # noqa: E402
    PROFILE as FIREBIRD,
)
from pgadmin.cdeadmin.providers.mysql_family.provider import (  # noqa: E402
    MARIADB_PROFILE as MARIADB, MYSQL_PROFILE as MYSQL,
)
from pgadmin.cdeadmin.providers.sqlite.provider import (  # noqa: E402
    PROFILE as SQLITE,
)
from pgadmin.cdeadmin.semantic_models import (  # noqa: E402
    SemanticModelService,
)


def pilot(profile):
    provider = object.__new__(ActualEnginePilotProvider)
    provider.profile = profile
    return provider


class PostgreSQLDialectProvider:
    """Mirror of PostgreSQLProvider's semantic hooks.

    The real class pulls in the Flask application stack at import time, so
    the test carries the same dialect contract it declares.
    """

    @staticmethod
    def semantic_model_descriptor():
        return {'engine_id': 'postgresql', 'model_family': 'relational',
                'language_profile': 'postgresql-sql'}

    @staticmethod
    def compile_semantic_query(model, query):
        from pgadmin.cdeadmin.semantic_models.compiler import compile_sql
        return compile_sql(model, query, {
            'language_profile': 'postgresql-sql',
            'quote_open': '"', 'quote_close': '"',
            'supports_rollup': True, 'limit_style': 'limit',
            'true_literal': 'TRUE', 'false_literal': 'FALSE',
            'time_operations': ('as_of', 'range', 'period_to_date',
                                'period_comparison'),
            'window_operations': ('running_sum', 'moving_sum',
                                  'moving_average', 'lag', 'delta',
                                  'percent_change', 'rank', 'dense_rank'),
            'contract_complete': True,
        })


PROVIDERS = {
    'postgresql': PostgreSQLDialectProvider(),
    'mysql': pilot(MYSQL), 'mariadb': pilot(MARIADB),
    'firebird': pilot(FIREBIRD), 'sqlite': pilot(SQLITE),
    'duckdb': pilot(DUCKDB),
}
ROWS = [
    ('east', 'apple', 10, 1), ('east', 'pear', 30, 3),
    ('west', 'apple', 20, 2), ('west', 'pear', 40, 4),
    ('west', 'plum', 5, 1),
]


def detail_question(**overrides):
    value = {
        'name': 'Big sales',
        'query': {'kind': 'builder', 'builder': {
            'source': {'relation': ['sales']},
            'columns': ['region', {'column': 'amount', 'alias': 'total'}],
            'filters': [{'column': 'amount', 'operator': 'gt', 'value': 10}],
            'order_by': [{'column': 'amount', 'direction': 'desc'}],
            'limit': 3,
        }},
    }
    value.update(overrides)
    return value


def summary_question(**overrides):
    value = {
        'name': 'Revenue by region',
        'parameters': [{'id': 'min_amount', 'type': 'integer',
                        'default': 0}],
        'query': {'kind': 'builder', 'builder': {
            'source': {'relation': ['sales']},
            'group_by': ['region'],
            'aggregations': [
                {'function': 'sum', 'column': 'amount', 'alias': 'revenue'},
                {'function': 'count', 'alias': 'orders'},
            ],
            'filters': [{'column': 'amount', 'operator': 'gte',
                         'parameter_id': 'min_amount'}],
            'order_by': [{'column': 'revenue', 'direction': 'desc'}],
            'limit': 10,
        }},
        'visualization': {'type': 'bar', 'settings': {'x': 'region'}},
    }
    value.update(overrides)
    return value


class MemoryBI:
    def __init__(self):
        self.cols, self.qs, self.snaps = {}, {}, {}

    def collections(self, user_id):
        return sorted([c for c in self.cols.values()
                       if c.user_id == user_id], key=lambda c: c.name)

    def get_collection(self, user_id, collection_id):
        c = self.cols.get(collection_id)
        return c if c and c.user_id == user_id else None

    @staticmethod
    def new_collection(**values):
        return SimpleNamespace(**values)

    def save_collection(self, row):
        self.cols[row.id] = row

    def delete_collection(self, row):
        self.cols.pop(row.id)

    def collection_has_questions(self, user_id, collection_id):
        return any(q.collection_id == collection_id
                   for q in self.qs.values())

    def questions(self, user_id, endpoint_id, collection_id=None,
                  every_collection=True):
        return sorted([
            q for q in self.qs.values()
            if q.user_id == user_id and q.endpoint_id == endpoint_id and (
                every_collection or q.collection_id == collection_id)
        ], key=lambda q: q.name)

    def get_question(self, user_id, endpoint_id, question_id):
        q = self.qs.get(question_id)
        if q and q.user_id == user_id and q.endpoint_id == endpoint_id:
            return q
        return None

    @staticmethod
    def new_question(**values):
        return SimpleNamespace(**values)

    def save_question(self, row, snapshot):
        self.qs[row.id] = row
        self.snaps.setdefault(row.id, []).append(SimpleNamespace(
            revision=row.revision, status=row.status, definition=snapshot,
            created_at=datetime.now(timezone.utc)))

    def revisions(self, question_id):
        return sorted(self.snaps.get(question_id, []),
                      key=lambda s: s.revision, reverse=True)

    def delete_question(self, row):
        self.qs.pop(row.id)


class MemorySemantic:
    def __init__(self):
        self.rows, self.snaps = {}, {}

    @staticmethod
    def new_definition(**values):
        return SimpleNamespace(**values)

    def get(self, user_id, endpoint_id, model_id):
        r = self.rows.get(model_id)
        return r if r and r.user_id == user_id and (
            r.endpoint_id == endpoint_id) else None

    def save(self, row, snapshot):
        self.rows[row.id] = row
        self.snaps.setdefault(row.id, []).append(SimpleNamespace(
            revision=row.revision, status=row.status, definition=snapshot,
            created_at=datetime.now(timezone.utc)))

    def revisions(self, model_id):
        return sorted(self.snaps.get(model_id, []),
                      key=lambda s: s.revision, reverse=True)

    def list(self, user_id, endpoint_id):
        return []


def service():
    return BIService(SemanticModelService(MemorySemantic()), MemoryBI())


class ValidationTests(unittest.TestCase):
    def test_rejects_malformed_specs(self):
        bad = [
            {'query': {'kind': 'nope'}},
            {'query': {'kind': 'sql', 'sql': '   '}},
            {'query': {'kind': 'semantic', 'builder': {
                'aggregations': [{'measure_id': 'm'}]}}},
        ]
        for overrides in bad:
            with self.assertRaises(BIError):
                validate_question({'name': 'x', **overrides})
        b = copy.deepcopy(detail_question())
        b['query']['builder']['group_by'] = ['region']
        with self.assertRaises(BIError):
            validate_question(b)
        b = copy.deepcopy(detail_question())
        b['query']['builder']['limit'] = 0
        with self.assertRaises(BIError):
            validate_question(b)
        b = copy.deepcopy(detail_question())
        b['query']['builder']['filters'] = [
            {'column': 'a', 'parameter_id': 'missing'}]
        with self.assertRaises(BIError):
            validate_question(b)
        with self.assertRaises(BIError):
            validate_question(detail_question(
                visualization={'type': 'hologram'}))

    def test_normalizes_defaults(self):
        item = validate_question(detail_question())
        self.assertEqual(item['visualization']['type'], 'table')
        self.assertEqual(item['query']['builder']['columns'][0],
                         {'column': 'region'})


class DialectTests(unittest.TestCase):
    def compile(self, engine, question):
        return service().compile(
            PROVIDERS[engine], 1, 'ep', definition=question)['source']

    def test_detail_question_per_engine(self):
        quoted = (
            'SELECT "src"."region" AS "region", "src"."amount" AS "total" '
            'FROM "sales" AS "src" WHERE "src"."amount" > 10 '
            'ORDER BY "total" DESC')
        ticks = quoted.replace('"', '`')
        expected = {
            'postgresql': quoted + ' LIMIT 3',
            'sqlite': quoted + ' LIMIT 3',
            'duckdb': quoted + ' LIMIT 3',
            'mysql': ticks + ' LIMIT 3',
            'mariadb': ticks + ' LIMIT 3',
            'firebird': quoted + ' ROWS 1 TO 3',
        }
        for engine, sql in expected.items():
            with self.subTest(engine=engine):
                self.assertEqual(self.compile(engine, detail_question()), sql)

    def test_summary_question_per_engine(self):
        for engine in PROVIDERS:
            with self.subTest(engine=engine):
                sql = self.compile(engine, summary_question())
                q = '`' if engine in {'mysql', 'mariadb'} else '"'
                self.assertIn(f'SUM({q}src{q}.{q}amount{q}) AS {q}revenue{q}',
                              sql)
                self.assertIn('COUNT(*) AS ' + q + 'orders' + q, sql)
                self.assertIn('>= 0', sql)  # parameter default bound
                self.assertIn(f'GROUP BY {q}src{q}.{q}region{q}', sql)
                self.assertIn(f'ORDER BY {q}revenue{q} DESC', sql)
                if engine == 'firebird':
                    self.assertTrue(sql.endswith('ROWS 1 TO 10'))
                    self.assertNotIn(' LIMIT ', sql)
                else:
                    self.assertTrue(sql.endswith('LIMIT 10'))
                    self.assertNotIn(' ROWS ', sql)

    def test_quote_escaping_and_string_literals(self):
        question = detail_question()
        question['query']['builder']['columns'] = [
            {'column': 'we"ird`col', 'alias': 'x'}]
        question['query']['builder']['filters'] = [
            {'column': 'region', 'operator': 'eq', 'value': "o'brien"}]
        question['query']['builder']['order_by'] = []
        self.assertIn('"src"."we""ird`col"',
                      self.compile('postgresql', question))
        self.assertIn('`src`.`we"ird``col`',
                      self.compile('mysql', question))
        self.assertIn("= 'o''brien'", self.compile('firebird', question))

    def test_parameter_value_overrides_default(self):
        result = service().compile(
            PROVIDERS['sqlite'], 1, 'ep', definition=summary_question(),
            parameters={'min_amount': 15})
        self.assertIn('>= 15', result['source'])
        with self.assertRaises(BIError):
            service().compile(PROVIDERS['sqlite'], 1, 'ep',
                              definition=summary_question(),
                              parameters={'nope': 1})

    def test_raw_sql_is_passed_through(self):
        question = {'name': 'raw', 'query': {
            'kind': 'sql', 'sql': 'SELECT 1 FROM RDB$DATABASE'}}
        result = service().compile(PROVIDERS['firebird'], 1, 'ep',
                                   definition=question)
        self.assertEqual(result['source'], 'SELECT 1 FROM RDB$DATABASE')
        self.assertEqual(result['kind'], 'sql')

    def test_order_by_unknown_output_rejected(self):
        question = detail_question()
        question['query']['builder']['order_by'] = [{'column': 'nope'}]
        with self.assertRaises(BIError):
            self.compile('sqlite', question)


class LiveExecutionTests(unittest.TestCase):
    def rows(self, engine, question, parameters=None):
        compiled = service().compile(PROVIDERS[engine], 1, 'ep',
                                     definition=question,
                                     parameters=parameters)
        if engine == 'sqlite':
            db = sqlite3.connect(':memory:')
            db.execute('CREATE TABLE sales (region TEXT, product TEXT, '
                       'amount INTEGER, qty INTEGER)')
            db.executemany('INSERT INTO sales VALUES (?,?,?,?)', ROWS)
            return db.execute(compiled['source']).fetchall()
        db = duckdb.connect(':memory:')
        db.execute('CREATE TABLE sales (region VARCHAR, product VARCHAR, '
                   'amount INTEGER, qty INTEGER)')
        db.executemany('INSERT INTO sales VALUES (?,?,?,?)', ROWS)
        return db.execute(compiled['source']).fetchall()

    def engines(self):
        return ['sqlite'] + (['duckdb'] if duckdb else [])

    def test_detail_rows(self):
        for engine in self.engines():
            with self.subTest(engine=engine):
                self.assertEqual(
                    self.rows(engine, detail_question()),
                    [('west', 40), ('east', 30), ('west', 20)])

    def test_summary_rows(self):
        for engine in self.engines():
            with self.subTest(engine=engine):
                self.assertEqual(
                    [tuple(r) for r in self.rows(engine,
                                                 summary_question())],
                    [('west', 65, 3), ('east', 40, 2)])
                self.assertEqual(
                    [tuple(r) for r in self.rows(
                        engine, summary_question(),
                        parameters={'min_amount': 20})],
                    [('west', 60, 2), ('east', 30, 1)])

    def test_hostile_filter_value_is_a_literal(self):
        question = detail_question()
        question['query']['builder']['filters'] = [
            {'column': 'region', 'operator': 'eq',
             'value': "x'; DROP TABLE sales; --"}]
        for engine in self.engines():
            with self.subTest(engine=engine):
                self.assertEqual(self.rows(engine, question), [])


class SemanticModelBoundTests(unittest.TestCase):
    def setUp(self):
        self.repo = MemorySemantic()
        self.semantic = SemanticModelService(self.repo)
        self.bi = BIService(self.semantic, MemoryBI())
        model = {
            'name': 'Sales', 'sources': [{
                'id': 'sales', 'resource_id': 'table:sales',
                'relation': ['sales'], 'alias': 'sales'}],
            'dimensions': [{'id': 'region', 'name': 'Region',
                            'field': {'source_id': 'sales',
                                      'field': 'region'}}],
            'measures': [{'id': 'revenue', 'name': 'Revenue',
                          'aggregation': 'sum',
                          'field': {'source_id': 'sales',
                                    'field': 'amount'}}],
        }
        self.model = self.semantic.create(1, 'ep', model)
        self.question = {
            'name': 'Cube question',
            'semantic_model': {'id': self.model['model_id'],
                               'revision': 1},
            'query': {'kind': 'semantic', 'builder': {
                'group_by': ['region'],
                'aggregations': [{'measure_id': 'revenue'}],
                'order_by': [{'id': 'revenue', 'direction': 'desc'}],
                'limit': 5}},
        }

    def test_compile_and_live_rows(self):
        stored = self.bi.create_question(1, 'ep', self.question)
        compiled = self.bi.compile(PROVIDERS['sqlite'], 1, 'ep',
                                   question_id=stored['question_id'])
        self.assertIn('ORDER BY "revenue" DESC LIMIT 5', compiled['source'])
        db = sqlite3.connect(':memory:')
        db.execute('CREATE TABLE sales (region TEXT, amount INTEGER)')
        db.executemany('INSERT INTO sales VALUES (?,?)',
                       [(r[0], r[2]) for r in ROWS])
        self.assertEqual(db.execute(compiled['source']).fetchall(),
                         [('west', 65), ('east', 40)])

    def test_unknown_model_or_revision_rejected(self):
        for ref in ({'id': 'missing', 'revision': None},
                    {'id': self.model['model_id'], 'revision': 9}):
            with self.assertRaises(BIError):
                self.bi.create_question(
                    1, 'ep', {**self.question, 'semantic_model': ref})

    def test_other_users_model_is_unavailable(self):
        with self.assertRaises(BIError):
            self.bi.create_question(2, 'ep', self.question)


class ServiceTests(unittest.TestCase):
    def test_question_revisions_are_immutable_snapshots(self):
        bi = service()
        created = bi.create_question(1, 'ep', detail_question())
        edited = detail_question(description='v2')
        updated = bi.update_question(1, 'ep', created['question_id'], 1,
                                     edited)
        self.assertEqual(updated['revision'], 2)
        history = bi.history(1, 'ep', created['question_id'])
        self.assertEqual([h['revision'] for h in history], [2, 1])
        first = bi.revision(1, 'ep', created['question_id'], 1)
        self.assertEqual(first['definition']['description'], '')
        with self.assertRaises(BIConflict):
            bi.update_question(1, 'ep', created['question_id'], 1, edited)
        # compiling a pinned revision uses that snapshot
        compiled = bi.compile(PROVIDERS['sqlite'], 1, 'ep',
                              question_id=created['question_id'],
                              revision=1)
        self.assertIn('LIMIT 3', compiled['source'])

    def test_owner_only(self):
        bi = service()
        created = bi.create_question(1, 'ep', detail_question())
        qid = created['question_id']
        for call in (
            lambda: bi.get_question(2, 'ep', qid),
            lambda: bi.get_question(1, 'other-endpoint', qid),
            lambda: bi.delete_question(2, 'ep', qid, 1),
            lambda: bi.update_question(2, 'ep', qid, 1, detail_question()),
            lambda: bi.compile(PROVIDERS['sqlite'], 2, 'ep',
                               question_id=qid),
        ):
            with self.assertRaises(BIError):
                call()
        self.assertEqual(bi.list_questions(2, 'ep'), [])
        folder = bi.create_collection(1, {'name': 'Mine'})
        with self.assertRaises(BIError):
            bi.create_question(2, 'ep', detail_question(
                collection_id=folder['collection_id']))
        with self.assertRaises(BIError):
            bi.update_collection(2, folder['collection_id'],
                                 {'name': 'Stolen'})
        self.assertEqual(bi.list_collections(2), [])

    def test_collection_tree_rules(self):
        bi = service()
        root = bi.create_collection(1, {'name': 'Root'})
        child = bi.create_collection(
            1, {'name': 'Child', 'parent_id': root['collection_id']})
        tree = bi.list_collections(1)
        self.assertEqual(tree[0]['children'][0]['name'], 'Child')
        with self.assertRaises(BIError):  # cycle
            bi.update_collection(1, root['collection_id'], {
                'name': 'Root', 'parent_id': child['collection_id']})
        with self.assertRaises(BIError):  # duplicate sibling
            bi.create_collection(1, {'name': 'Child',
                                     'parent_id': root['collection_id']})
        question = bi.create_question(1, 'ep', detail_question(
            collection_id=child['collection_id']))
        with self.assertRaises(BIError):  # not empty
            bi.delete_collection(1, child['collection_id'])
        moved = bi.move_question(1, 'ep', question['question_id'], 1, None)
        self.assertIsNone(moved['collection_id'])
        bi.delete_collection(1, child['collection_id'])
        bi.delete_collection(1, root['collection_id'])
        self.assertEqual(bi.list_collections(1), [])

    def test_duplicate_name_in_collection_rejected(self):
        bi = service()
        bi.create_question(1, 'ep', detail_question())
        with self.assertRaises(BIError):
            bi.create_question(1, 'ep', detail_question())
        clone = bi.clone_question(1, 'ep', bi.list_questions(
            1, 'ep')[0]['question_id'], 'Copy')
        self.assertEqual(clone['name'], 'Copy')


if __name__ == '__main__':
    unittest.main()
