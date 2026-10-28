##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Saved-question execution: bound parameters, injection, result policy,
paging, export gating, caching and invalidation, and SQL-to-question.

Execution runs on real SQLite and DuckDB connections through the real
semantic compiler and ``ResultService``; see ``bi_live_harness``.
"""

from __future__ import annotations

import copy
import unittest

import bi_live_harness as harness
from bi_live_harness import Stack, duckdb

from pgadmin.cdeadmin.bi import BIError, validate_question
from pgadmin.cdeadmin.semantic_models.models import SemanticModelError
from pgadmin.cdeadmin.bi.convert import sql_to_question
from pgadmin.cdeadmin.bi.sqltext import (
    assert_read_only_select, bind_placeholders, tokenize,
)
from test_cdeadmin_bi_saved_questions import (
    PROVIDERS, detail_question, summary_question,
)

ENGINES = ['sqlite'] + (['duckdb'] if duckdb is not None else [])


def region_question(**policy):
    question = {
        'name': 'Sales by region',
        'parameters': [{'id': 'region', 'type': 'string', 'required': True}],
        'query': {'kind': 'builder', 'builder': {
            'source': {'relation': ['sales']},
            'columns': ['region', 'product', 'amount', 'notes'],
            'filters': [{'column': 'region', 'operator': 'eq',
                         'parameter_id': 'region'}],
            'order_by': [{'column': 'amount', 'direction': 'asc'}],
            'limit': 100,
        }},
    }
    if policy:
        question['result_policy'] = policy
    return question


def sql_question(sql, parameters=(), **policy):
    question = {'name': 'Raw ' + str(abs(hash(sql)) % 10 ** 6),
                'parameters': list(parameters),
                'query': {'kind': 'sql', 'sql': sql}}
    if policy:
        question['result_policy'] = policy
    return question


class BoundParameterTests(unittest.TestCase):
    """The compiled statement carries markers; values travel separately."""

    def compile(self, engine, question, **options):
        # semantic validation errors are SemanticModelError (BIError's base)
        stack = Stack('sqlite')
        return stack.bi.compile_definition(
            PROVIDERS[engine], 1, 'ep', validate_question(question),
            bind=True, **options)

    def test_every_engine_binds_with_its_own_marker(self):
        expected = {'sqlite': '?', 'duckdb': '?', 'firebird': '?',
                    'mysql': '%s', 'mariadb': '%s', 'postgresql': '%s'}
        for engine, marker in expected.items():
            with self.subTest(engine=engine):
                compiled = self.compile(
                    engine, summary_question(),
                    parameters={'min_amount': 15})
                self.assertIn(f'>= {marker}', compiled['source'])
                self.assertNotIn('15', compiled['source'])
                self.assertEqual(compiled['parameters'], [15])
                self.assertTrue(compiled['bound'])

    def test_injection_text_never_reaches_the_statement(self):
        attacks = ["east' OR '1'='1", "'; DROP TABLE sales; --",
                   'x" OR ""="', "\\' OR 1=1 --", 'a%s%%b', "x'/*",
                   '{{region}}', '1; SELECT 1']
        for engine in PROVIDERS:
            for attack in attacks:
                with self.subTest(engine=engine, attack=attack):
                    compiled = self.compile(
                        engine, region_question(),
                        parameters={'region': attack})
                    self.assertEqual(compiled['parameters'], [attack])
                    self.assertNotIn(attack.strip(), compiled['source'])
                    self.assertNotIn('DROP', compiled['source'])
                    self.assertNotIn("'", compiled['source'])

    def test_inline_compile_is_unchanged_without_bind(self):
        stack = Stack('sqlite')
        inline = stack.bi.compile(
            PROVIDERS['sqlite'], 1, 'ep', definition=summary_question(),
            parameters={'min_amount': 15})
        self.assertIn('>= 15', inline['source'])
        self.assertEqual(inline['parameters'], {})

    def test_values_are_bound_in_textual_order_across_clauses(self):
        question = summary_question()
        question['query']['builder']['filters'] += [
            {'column': 'region', 'operator': 'in', 'value': ['a', 'b']},
            {'column': 'amount', 'operator': 'between', 'value': [1, 99]},
        ]
        compiled = self.compile('sqlite', question,
                                parameters={'min_amount': 7})
        self.assertEqual(compiled['parameters'], [7, 'a', 'b', 1, 99])
        self.assertEqual(compiled['source'].count('?'), 5)

    def test_percent_is_escaped_for_format_style_only_when_binding(self):
        question = detail_question()
        question['query']['builder']['columns'] = [
            {'column': '100%', 'alias': 'pct'}]
        question['query']['builder']['filters'] = [
            {'column': 'amount', 'operator': 'gt', 'value': 3}]
        question['query']['builder']['order_by'] = []
        bound = self.compile('postgresql', question)
        self.assertIn('"100%%"', bound['source'])
        self.assertEqual(bound['parameters'], [3])
        none = copy.deepcopy(question)
        none['query']['builder']['filters'] = []
        unbound = self.compile('postgresql', none)
        self.assertIn('"100%"', unbound['source'])
        self.assertEqual(unbound['parameters'], [])

    def test_parameter_types_and_domains_are_enforced(self):
        with self.assertRaises(SemanticModelError):
            self.compile('sqlite', summary_question(),
                         parameters={'min_amount': '1; DROP TABLE x'})
        question = region_question()
        question['parameters'][0]['allowed_values'] = ['east', 'west']
        with self.assertRaises(SemanticModelError):
            self.compile('sqlite', question, parameters={'region': 'north'})
        with self.assertRaises(BIError):
            self.compile('sqlite', summary_question(),
                         parameters={'nope': 1})

    def test_engines_without_a_bind_style_fail_closed(self):
        class Odd:
            @staticmethod
            def semantic_model_descriptor():
                return {'engine_id': 'cassandra', 'model_family':
                        'relational', 'language_profile': 'cql'}
        stack = Stack('sqlite')
        with self.assertRaisesRegex(BIError, 'bound-parameter style'):
            stack.bi.compile_definition(
                Odd(), 1, 'ep',
                sql_to_question('SELECT 1 FROM t')['question'], bind=True)

    def test_raw_sql_markers_replace_only_declared_parameters(self):
        stack = Stack('sqlite')
        sql = ("SELECT '{{region}}' AS lit, region FROM sales "
               "WHERE region = {{region}} -- {{region}}\n AND amount > "
               "{{floor}}")
        question = sql_question(sql, [
            {'id': 'region', 'type': 'string', 'required': True},
            {'id': 'floor', 'type': 'integer', 'default': 3}])
        compiled = stack.bi.compile_definition(
            PROVIDERS['sqlite'], 1, 'ep',
            validate_question(question),
            parameters={'region': 'east'}, bind=True)
        # the quoted literal and the comment are not parameters
        self.assertEqual(compiled['parameters'], ['east', 3])
        self.assertIn("'{{region}}'", compiled['source'])
        self.assertEqual(compiled['source'].count('?'), 2)

    def test_raw_sql_rejects_undeclared_parameters_and_writes(self):
        with self.assertRaisesRegex(BIError, 'undeclared'):
            bind_placeholders('SELECT {{x}}', '?', {'y'})
        for sql in ['DROP TABLE sales', 'SELECT 1; DELETE FROM sales',
                    'WITH d AS (DELETE FROM sales RETURNING *) SELECT 1',
                    'SELECT * INTO copy FROM sales', 'UPDATE sales SET qty=0',
                    'PRAGMA writable_schema=1', '', '   ;  ',
                    'ATTACH DATABASE x AS y']:
            with self.subTest(sql=sql):
                with self.assertRaises(BIError):
                    assert_read_only_select(sql)
        self.assertTrue(assert_read_only_select(
            "SELECT REPLACE(region, 'e', 'E'), \"update\" FROM sales;"))
        self.assertEqual(
            [t.kind for t in tokenize("a 'it''s' {{p}} -- c")
             if t.kind not in {'ws'}],
            ['word', 'string', 'param', 'comment'])
        with self.assertRaises(BIError):
            tokenize("SELECT 'open")


class RawSqlHardeningTests(unittest.TestCase):
    DENIED = [
        "SELECT pg_sleep(5)", "SELECT pg_catalog.pg_read_file('/etc/passwd')",
        "SELECT * FROM sales FOR UPDATE", "SELECT * FROM sales FOR SHARE",
        "SELECT * FROM sales FOR NO KEY UPDATE",
        "SELECT * FROM read_csv('/etc/passwd')", "SELECT * FROM 'x.csv'",
        "SELECT * FROM sales JOIN 'x.parquet' ON 1=1",
        "SELECT load_file('/etc/passwd')", "SELECT SLEEP(10)",
        "SELECT BENCHMARK(100000000, MD5('a'))",
        "SELECT 1 INTO OUTFILE '/tmp/x'", "SELECT * FROM sales LOCK IN SHARE MODE",
        "SELECT nextval('s')", "SELECT lo_import('/x')",
        "SELECT dblink('c', 'select 1')", "SELECT load_extension('x')",
        "SELECT set_config('role', 'postgres', false)",
        "SELECT get_lock('a', 10)",
    ]

    def test_side_effecting_selects_are_refused(self):
        for sql in self.DENIED:
            with self.subTest(sql=sql):
                with self.assertRaises(BIError):
                    assert_read_only_select(sql)

    def test_ordinary_selects_still_pass(self):
        for sql in ["SELECT read_count, write_total FROM stats",
                    "SELECT query FROM log WHERE edit = 1",
                    "WITH c AS (SELECT 1) SELECT * FROM c",
                    "SELECT glob_name, now() FROM t WHERE x = {{p}}"]:
            with self.subTest(sql=sql):
                self.assertTrue(assert_read_only_select(sql))


class RawSqlPolicyTests(unittest.TestCase):
    class _Row:
        def __init__(self, definition):
            self.definition = definition

    def _service(self, rows):
        from pgadmin.cdeadmin.bi.service import BIService
        service = BIService.__new__(BIService)
        service._raw_sql_policies = []
        repository = type('R', (), {'list': lambda _s, *_a: rows})()
        service.semantic = type('S', (), {'repository': repository})()
        return service

    def test_refused_where_models_declare_row_filters(self):
        import json
        rows = [self._Row(json.dumps({'security': {'row_filters': [{'x': 1}]}}))]
        service = self._service(rows)
        with self.assertRaisesRegex(BIError, 'row policies'):
            service.assert_raw_sql_allowed(1, 'e')

    def test_allowed_without_row_policies_and_policy_callback_decides(self):
        import json
        service = self._service([self._Row(json.dumps({'security': {}}))])
        service.assert_raw_sql_allowed(1, 'e')
        service.add_raw_sql_policy(lambda user, endpoint: False)
        with self.assertRaisesRegex(BIError, 'not permitted'):
            service.assert_raw_sql_allowed(1, 'e')
        granted = self._service([self._Row(json.dumps(
            {'security': {'row_filters': [{'x': 1}]}}))])
        granted.add_raw_sql_policy(lambda user, endpoint: True)
        granted.assert_raw_sql_allowed(1, 'e')


class LiveExecutionTests(unittest.TestCase):
    def each(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                yield engine, Stack(engine)

    def test_typed_descriptor_and_rows(self):
        for _engine, stack in self.each():
            outcome = stack.run(definition=summary_question(),
                                parameters={'min_amount': 10})
            descriptor = outcome['result']
            self.assertEqual(descriptor['result_kind'], 'tabular')
            self.assertEqual(
                [c['name'] for c in descriptor['schema']['columns']],
                ['region', 'revenue', 'orders'])
            rows = outcome['page']['view_model']
            self.assertTrue(outcome['page']['redacted'])
            sums = {r['region']: r['revenue']
                    for r in self._records(outcome)}
            self.assertEqual(sums, {'east': 40, 'west': 60})
            self.assertEqual(outcome['bound_parameter_count'], 1)
            self.assertNotIn('10', outcome['sql'].split('WHERE')[1][:12])
            self.assertEqual(stack.studio.closed.__len__(), 1)
            self.assertIsNotNone(rows)

    @staticmethod
    def _records(outcome):
        view = outcome['page']['view_model']
        return view.get('rows', view.get('records', []))

    def test_both_engines_agree(self):
        results = {}
        for engine, stack in self.each():
            outcome = stack.run(definition=detail_question())
            results[engine] = [
                tuple(r.values()) for r in self._records(outcome)]
        if len(results) == 2:
            self.assertEqual(results['sqlite'], results['duckdb'])
        self.assertEqual(results['sqlite'], [
            ('west', 40), ('east', 30), ('west', 20)])

    def test_injection_attempts_return_nothing_and_change_nothing(self):
        attacks = ["east' OR '1'='1", "east'; DROP TABLE sales; --",
                   'east" OR 1=1 --', "' UNION SELECT notes FROM sales --"]
        for _engine, stack in self.each():
            for attack in attacks:
                outcome = stack.run(definition=region_question(),
                                    parameters={'region': attack},
                                    bypass_cache=True)
                self.assertEqual(self._records(outcome), [], attack)
                self.assertEqual(stack.studio.calls[-1]['parameters'],
                                 [attack])
                self.assertNotIn(attack, stack.studio.calls[-1]['source'])
            count = stack.connection.execute(
                'SELECT COUNT(*) FROM sales').fetchone()[0]
            self.assertEqual(count, 5)
            ok = stack.run(definition=region_question(),
                           parameters={'region': 'west'})
            self.assertEqual(len(self._records(ok)), 3)

    def test_raw_sql_question_binds_and_is_read_only(self):
        sql = ('SELECT region, SUM(amount) AS revenue FROM sales '
               'WHERE amount >= {{floor}} GROUP BY region ORDER BY region')
        param = [{'id': 'floor', 'type': 'integer', 'required': True}]
        for _engine, stack in self.each():
            outcome = stack.run(definition=sql_question(sql, param),
                                parameters={'floor': 20})
            self.assertEqual(
                [(r['region'], r['revenue']) for r in self._records(outcome)],
                [('east', 30), ('west', 60)])
            self.assertEqual(stack.studio.calls[-1]['parameters'], [20])
            self.assertNotIn('{{', stack.studio.calls[-1]['source'])
            with self.assertRaises(BIError):
                stack.run(definition=sql_question(
                    'DELETE FROM sales WHERE amount > {{floor}}', param),
                    parameters={'floor': 1})
            with self.assertRaises(BIError):
                stack.run(definition=sql_question(sql, param),
                          parameters={'floor': '1 OR 1=1'})
            self.assertEqual(stack.connection.execute(
                'SELECT COUNT(*) FROM sales').fetchone()[0], 5)

    def test_extra_field_filters_are_bound_values(self):
        for _engine, stack in self.each():
            outcome = stack.run(
                definition=detail_question(),
                extra_filters=[{'column': 'region', 'operator': 'in',
                                'value': ["west", "x'; DROP TABLE sales; --"]
                                }])
            self.assertEqual(len(self._records(outcome)), 2)
            self.assertEqual(stack.studio.calls[-1]['parameters'][-2:],
                             ['west', "x'; DROP TABLE sales; --"])
            self.assertNotIn('DROP', stack.studio.calls[-1]['source'])

    def test_paging_is_bounded_and_cursor_driven(self):
        for _engine, stack in self.each():
            first = stack.run(
                definition=region_question(), parameters={'region': 'west'},
                page_size=2)
            self.assertEqual(first['page']['page']['page_size'], 2)
            cursor = first['page']['page']['next_cursor']
            self.assertIsNotNone(cursor)
            result_id = first['result']['result_id']
            second = stack.executor.page(1, stack.ctx.endpoint_id,
                                         result_id, cursor=cursor,
                                         page_size=2)
            self.assertEqual(second['page']['page_size'], 1)
            self.assertIsNone(second['page']['next_cursor'])
            with self.assertRaises(BIError):
                stack.executor.page(1, stack.ctx.endpoint_id, result_id,
                                    page_size=501)
            with self.assertRaises(BIError):
                stack.run(definition=region_question(),
                          parameters={'region': 'west'}, page_size=0)
            with self.assertRaises(BIError):
                stack.run(definition=region_question(),
                          parameters={'region': 'west'}, page_size=5000)

    def test_redaction_applies_to_pages_schema_and_export(self):
        policy = {'redact_columns': ['notes'],
                  'export': {'enabled': True, 'formats': ['csv']}}
        for _engine, stack in self.each():
            outcome = stack.run(
                definition=region_question(**policy),
                parameters={'region': 'east'})
            text = repr(outcome['page'])
            self.assertNotIn('private-apple', text)
            self.assertNotIn('private-pear', text)
            self.assertEqual(outcome['redacted_columns'], ['notes'])
            self.assertEqual(stack.studio.calls[-1]['output_policy'],
                             {'redact_keys': ['notes']})
            exported = stack.executor.export(
                1, stack.ctx.endpoint_id, outcome['result']['result_id'],
                'csv')
            self.assertIn(b'region', exported['content'])
            self.assertNotIn(b'private-', exported['content'])
            self.assertTrue(exported['redacted'])

    def test_export_is_policy_gated(self):
        for _engine, stack in self.each():
            closed = stack.run(definition=region_question(),
                               parameters={'region': 'east'})
            self.assertEqual(closed['export'],
                             {'enabled': False, 'formats': []})
            with self.assertRaisesRegex(BIError, 'not enabled'):
                stack.executor.export(1, stack.ctx.endpoint_id,
                                      closed['result']['result_id'], 'csv')
            # the typed descriptor itself no longer offers export
            self.assertEqual(closed['result']['export_formats'], [])
            narrow = stack.run(
                definition=region_question(
                    export={'enabled': True, 'formats': ['csv']}),
                parameters={'region': 'east'}, bypass_cache=True)
            rid = narrow['result']['result_id']
            self.assertEqual(narrow['result']['export_formats'], ['csv'])
            self.assertEqual(
                stack.executor.export(1, stack.ctx.endpoint_id, rid, 'csv')[
                    'format'], 'csv')
            with self.assertRaisesRegex(BIError, 'not allowed'):
                stack.executor.export(1, stack.ctx.endpoint_id, rid, 'json')
            with self.assertRaisesRegex(BIError, 'not allowed'):
                stack.executor.export(1, stack.ctx.endpoint_id, rid, 'pdf')

    def test_results_belong_to_the_executing_principal(self):
        for _engine, stack in self.each():
            policy = {'export': {'enabled': True, 'formats': ['csv']}}
            mine = stack.run(user_id=1, definition=region_question(**policy),
                             parameters={'region': 'east'})
            rid = mine['result']['result_id']
            for call in (
                    lambda: stack.executor.page(2, stack.ctx.endpoint_id,
                                                rid),
                    lambda: stack.executor.export(
                        2, stack.ctx.endpoint_id, rid, 'csv'),
                    lambda: stack.executor.page(1, 'other-endpoint', rid)):
                with self.assertRaisesRegex(BIError, 'unavailable'):
                    call()
            self.assertEqual(stack.executor.invalidate(
                user_id=2, result_id=rid), 0)
            self.assertTrue(stack.executor.page(1, stack.ctx.endpoint_id,
                                                rid))

    def test_stored_question_revisions_are_pinned_and_archive_blocks(self):
        for _engine, stack in self.each():
            created = stack.create(region_question())
            qid = created['question_id']
            first = stack.run(question_id=qid, parameters={'region': 'west'})
            self.assertEqual(first['revision'], 1)
            changed = region_question()
            changed['query']['builder']['limit'] = 1
            stack.bi.update_question(1, stack.ctx.endpoint_id, qid, 1,
                                     changed)
            latest = stack.run(question_id=qid,
                               parameters={'region': 'west'})
            self.assertEqual(latest['revision'], 2)
            self.assertEqual(len(self._records(latest)), 1)
            pinned = stack.run(question_id=qid, revision=1,
                               parameters={'region': 'west'})
            self.assertEqual(len(self._records(pinned)), 3)
            stack.bi.set_status(1, stack.ctx.endpoint_id, qid, 2, 'archived')
            with self.assertRaisesRegex(BIError, 'archived'):
                stack.run(question_id=qid, parameters={'region': 'west'})
            with self.assertRaisesRegex(BIError, 'archived'):
                stack.run(question_id=qid, revision=2,
                          parameters={'region': 'west'})
            stack.bi.set_status(1, stack.ctx.endpoint_id, qid, 3, 'active')
            self.assertEqual(len(self._records(stack.run(
                question_id=qid, revision=1,
                parameters={'region': 'west'}))), 3)

    def test_other_users_cannot_run_a_question(self):
        for _engine, stack in self.each():
            qid = stack.create(region_question())['question_id']
            with self.assertRaisesRegex(BIError, 'unavailable'):
                stack.run(user_id=2, question_id=qid,
                          parameters={'region': 'west'})

    def test_provider_failure_is_a_bi_error_and_session_is_closed(self):
        for _engine, stack in self.each():
            question = detail_question()
            question['query']['builder']['source']['relation'] = ['missing']
            with self.assertRaisesRegex(BIError, 'execution failed'):
                stack.run(definition=question)
            self.assertEqual(len(stack.studio.closed), 1)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.stack = Stack('sqlite')
        self.params = {'region': 'west'}

    def run_q(self, **options):
        options.setdefault('parameters', self.params)
        options.setdefault('definition', region_question())
        return self.stack.run(**options)

    def runs(self):
        return len(self.stack.studio.calls)

    def test_hit_miss_and_key_dimensions(self):
        first = self.run_q()
        self.assertFalse(first['cache']['hit'])
        self.assertEqual(self.runs(), 1)
        second = self.run_q()
        self.assertTrue(second['cache']['hit'])
        self.assertEqual(self.runs(), 1)
        self.assertEqual(second['result']['result_id'],
                         first['result']['result_id'])
        self.assertEqual(second['cache']['hits'], 1)
        # different parameters, principal, definition -> miss
        self.assertFalse(self.run_q(parameters={'region': 'east'})[
            'cache']['hit'])
        self.assertFalse(self.run_q(user_id=2)['cache']['hit'])
        other = region_question()
        other['query']['builder']['limit'] = 50
        self.assertFalse(self.run_q(definition=other)['cache']['hit'])
        self.assertEqual(self.runs(), 4)
        # and each principal only ever sees its own entry
        self.assertNotEqual(
            self.run_q(user_id=2)['result']['result_id'],
            first['result']['result_id'])

    def test_stored_question_revision_is_part_of_the_key(self):
        qid = self.stack.create(region_question())['question_id']
        a = self.stack.run(question_id=qid, parameters=self.params)
        b = self.stack.run(question_id=qid, parameters=self.params)
        self.assertTrue(b['cache']['hit'])
        changed = region_question()
        changed['query']['builder']['limit'] = 2
        self.stack.bi.update_question(1, self.stack.ctx.endpoint_id, qid, 1,
                                      changed)
        c = self.stack.run(question_id=qid, parameters=self.params)
        self.assertFalse(c['cache']['hit'])
        self.assertEqual(c['revision'], 2)
        self.assertNotEqual(c['result']['result_id'],
                            a['result']['result_id'])

    def test_ttl_expiry(self):
        question = region_question(cache_ttl_seconds=60)
        self.run_q(definition=question)
        self.stack.clock.advance(59)
        self.assertTrue(self.run_q(definition=question)['cache']['hit'])
        self.stack.clock.advance(2)
        again = self.run_q(definition=question)
        self.assertFalse(again['cache']['hit'])
        self.assertEqual(self.runs(), 2)

    def test_request_may_only_shorten_the_ttl(self):
        question = region_question(cache_ttl_seconds=60)
        # a 5 second ttl on a fresh run expires before the 60 second policy
        self.run_q(definition=question, parameters={'region': 'east'},
                   ttl_seconds=5)
        self.stack.clock.advance(6)
        self.assertFalse(self.run_q(
            definition=question, parameters={'region': 'east'})['cache'][
                'hit'])
        with self.assertRaises(BIError):
            self.run_q(definition=question, ttl_seconds=-1)

    def test_zero_ttl_and_bypass_never_reuse(self):
        question = region_question(cache_ttl_seconds=0)
        self.run_q(definition=question)
        self.assertFalse(self.run_q(definition=question)['cache']['hit'])
        self.assertFalse(self.run_q(definition=question)['cache'][
            'cacheable'])
        self.stack.executor.invalidate(user_id=1)
        self.run_q()
        self.assertFalse(self.run_q(bypass_cache=True)['cache']['hit'])
        self.assertTrue(self.run_q()['cache']['hit'])

    def test_explicit_invalidation_by_result_question_user(self):
        qid = self.stack.create(region_question())['question_id']
        a = self.stack.run(question_id=qid, parameters=self.params)
        self.stack.run(question_id=qid, parameters={'region': 'east'})
        adhoc = self.run_q()
        self.assertEqual(len(self.stack.executor.cache_info(
            1, self.stack.ctx.endpoint_id)), 3)
        self.assertEqual(self.stack.executor.invalidate(result_id=adhoc[
            'result']['result_id']), 1)
        with self.assertRaises(Exception):  # descriptor released
            self.stack.results.descriptor(
                adhoc['result']['result_id'],
                endpoint_id=self.stack.ctx.endpoint_id)
        self.assertEqual(self.stack.executor.invalidate(
            user_id=1, question_id=qid), 2)
        self.assertFalse(self.stack.run(
            question_id=qid, parameters=self.params)['cache']['hit'])
        self.assertNotEqual(
            self.stack.run(question_id=qid, parameters=self.params)[
                'result']['result_id'], a['result']['result_id'])
        with self.assertRaises(BIError):
            self.stack.executor.invalidate()

    def test_question_changes_invalidate_automatically(self):
        qid = self.stack.create(region_question())['question_id']
        run = self.stack.run(question_id=qid, parameters=self.params)
        rid = run['result']['result_id']
        self.stack.bi.set_status(1, self.stack.ctx.endpoint_id, qid, 1,
                                 'archived')
        with self.assertRaises(BIError):
            self.stack.executor.page(1, self.stack.ctx.endpoint_id, rid)
        self.stack.bi.set_status(1, self.stack.ctx.endpoint_id, qid, 2,
                                 'active')
        again = self.stack.run(question_id=qid, parameters=self.params)
        self.stack.bi.delete_question(1, self.stack.ctx.endpoint_id, qid, 3)
        with self.assertRaises(BIError):
            self.stack.executor.page(1, self.stack.ctx.endpoint_id,
                                     again['result']['result_id'])
        self.assertEqual(self.stack.executor.cache_info(
            1, self.stack.ctx.endpoint_id), [])

    def test_lease_expiry_and_capacity_release_descriptors(self):
        stack = self.stack
        first = self.run_q()
        stack.clock.advance(601)
        self.assertEqual(stack.executor.cache_info(
            1, stack.ctx.endpoint_id), [])
        with self.assertRaises(BIError):
            stack.executor.page(1, stack.ctx.endpoint_id,
                                first['result']['result_id'])
        stack.executor.max_entries = 2
        ids = []
        for region in ('east', 'west', 'north'):
            ids.append(self.run_q(parameters={'region': region})[
                'result']['result_id'])
            stack.clock.advance(1)
        self.assertEqual(len(stack.executor.cache_info(
            1, stack.ctx.endpoint_id)), 2)
        self.assertEqual(stack.executor.stats['evictions'], 1)
        with self.assertRaises(Exception):
            stack.results.descriptor(ids[0],
                                     endpoint_id=stack.ctx.endpoint_id)

    def test_result_released_elsewhere_is_a_miss(self):
        first = self.run_q()
        self.stack.results.release(first['result']['result_id'],
                                   endpoint_id=self.stack.ctx.endpoint_id)
        again = self.run_q()
        self.assertFalse(again['cache']['hit'])
        self.assertNotEqual(again['result']['result_id'],
                            first['result']['result_id'])


class SqlToQuestionTests(unittest.TestCase):
    def test_clean_select_maps_exactly(self):
        outcome = sql_to_question(
            'SELECT region, SUM(amount) AS revenue, COUNT(*) AS orders '
            'FROM sales s WHERE s.amount >= {{floor}} AND region <> \'x\' '
            'GROUP BY region ORDER BY revenue DESC LIMIT 5',
            parameter_types={'floor': 'integer'})
        self.assertEqual(outcome['fidelity'], 'exact')
        builder = outcome['question']['query']['builder']
        self.assertEqual(builder['limit'], 5)
        self.assertEqual(builder['group_by'], [{'column': 'region'}])
        self.assertEqual(builder['aggregations'], [
            {'function': 'sum', 'column': 'amount', 'alias': 'revenue'},
            {'function': 'count', 'alias': 'orders'}])
        self.assertEqual(builder['filters'], [
            {'operator': 'gte', 'column': 'amount',
             'parameter_id': 'floor'},
            {'operator': 'ne', 'column': 'region', 'value': 'x'}])
        self.assertEqual(outcome['question']['parameters'][0]['type'],
                         'integer')
        self.assertEqual([i for i in outcome['loss']
                          if i['severity'] != 'info'], [])

    def test_loss_is_reported_for_a_lossy_mapping(self):
        outcome = sql_to_question(
            'select "region", amount from main.sales -- keep\n'
            'where amount between 5 and 30 and region in (\'east\', '
            '\'west\') order by 2 desc')
        self.assertEqual(outcome['fidelity'], 'lossy')
        codes = {item['code'] for item in outcome['loss']}
        self.assertIn('implicit_limit', codes)
        self.assertIn('comments_dropped', codes)
        builder = outcome['question']['query']['builder']
        self.assertEqual(builder['source']['relation'], ['main', 'sales'])
        self.assertEqual(builder['order_by'],
                         [{'column': 'amount', 'direction': 'desc'}])
        self.assertEqual(builder['limit'], 500)

    def test_unmappable_statements_stay_raw_sql_with_reasons(self):
        cases = {
            'SELECT * FROM sales': 'unmappable_star',
            'SELECT a.x FROM a JOIN b ON a.id = b.id': 'unmappable_join',
            'SELECT region FROM sales WHERE a = 1 OR b = 2':
                'unmappable_or',
            'SELECT DISTINCT region FROM sales': 'unmappable_distinct',
            'SELECT region, SUM(amount) FROM sales GROUP BY region '
            'HAVING SUM(amount) > 1': 'unmappable_having',
            'SELECT region FROM (SELECT region FROM sales) t':
                'unmappable_subquery',
            'SELECT amount * 2 FROM sales': 'unmappable_expression',
            'SELECT region FROM sales WHERE amount IN (SELECT 1)':
                'unmappable_subquery',
            'WITH t AS (SELECT 1) SELECT * FROM t': 'unmappable_with',
            'SELECT region FROM sales UNION SELECT region FROM sales':
                'unmappable_union',
            'SELECT SUM(amount) OVER (PARTITION BY region) FROM sales':
                'unmappable_over',
            'SELECT region FROM sales WHERE region LIKE \'e%\'':
                'unmappable_like',
            'SELECT region FROM sales WHERE amount > ?':
                'unmappable_literal',
        }
        for sql, code in cases.items():
            with self.subTest(sql=sql):
                outcome = sql_to_question(sql)
                self.assertEqual(outcome['fidelity'], 'none')
                self.assertFalse(outcome['mapped'])
                self.assertEqual(outcome['question']['query'],
                                 {'kind': 'sql', 'sql': sql})
                codes = [i['code'] for i in outcome['loss']]
                self.assertIn(code, codes)
                self.assertTrue(all(i['severity'] == 'blocking'
                                    for i in outcome['loss']))

    def test_raw_fallback_keeps_declared_parameters(self):
        outcome = sql_to_question(
            'SELECT * FROM sales WHERE region = {{r}}')
        self.assertEqual(outcome['question']['parameters'][0]['id'], 'r')

    def test_mapped_questions_return_the_same_rows_as_the_sql(self):
        statements = [
            ('SELECT region, SUM(amount) AS revenue, COUNT(*) AS orders '
             'FROM sales GROUP BY region ORDER BY revenue DESC LIMIT 10'),
            ('SELECT region, amount FROM sales WHERE amount > 5 '
             'AND region IN (\'east\', \'west\') ORDER BY amount DESC, '
             'region LIMIT 10'),
            ('SELECT product, MIN(amount) AS lo, MAX(amount) AS hi, '
             'AVG(qty) AS avg_qty FROM sales GROUP BY product '
             'ORDER BY product LIMIT 10'),
            ('SELECT COUNT(DISTINCT region) AS regions FROM sales '
             'LIMIT 10'),
            'SELECT region, amount FROM sales WHERE amount BETWEEN 10 AND 30'
            ' ORDER BY amount, region LIMIT 10',
        ]
        for engine in ENGINES:
            stack = Stack(engine)
            for sql in statements:
                with self.subTest(engine=engine, sql=sql):
                    outcome = sql_to_question(sql)
                    self.assertTrue(outcome['mapped'], outcome['loss'])
                    mapped = stack.run(definition=outcome['question'],
                                       bypass_cache=True)
                    got = [tuple(r.values()) for r in
                           LiveExecutionTests._records(mapped)]
                    cursor = stack.connection.execute(sql)
                    expected = [tuple(r) for r in cursor.fetchall()]
                    self.assertEqual(got, expected)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
