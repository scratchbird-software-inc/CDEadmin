##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""BI alerts and subscriptions (docs/en_US/bi_alerts.rst).

Pure condition and state-machine rules; webhook signing and SSRF refusals
with a stubbed resolver and transport; and the service end to end on real
SQLite / DuckDB with a fake clock: edge vs level, re-arm, snooze, change
conditions, pause and resume, permission and credential revocation,
recipient authorization, the row cap, history redaction, subscriptions and
the real tables / migration.
"""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import bi_alerts_harness as ah
from bi_alerts_harness import (
    AlertStack, HOOK_HOST, HOOK_SECRET, ReportSchedulerAccessError,
    ReportSchedulerConflict, ReportSchedulerError, StubResolver,
    StubTransport, alert_definition, column_metric, rows_over,
    subscription_definition,
)
from bi_live_harness import ROOT, duckdb
from bi_permissions_harness import (
    ANALYST, EDITOR, MANAGER, OWNER, STRANGER, VIEWER, board,
)
from test_cdeadmin_bi_dashboards import detail_by_region
from test_cdeadmin_bi_execution import region_question, sql_question
from test_cdeadmin_bi_permissions import RunAsRunnerTests

from pgadmin.cdeadmin.bi import BIError
from pgadmin.cdeadmin.bi import alert_models as am
from pgadmin.cdeadmin.bi.alert_models import AlertError
from pgadmin.cdeadmin.bi.webhook import WebhookChannel, WebhookError

try:
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    MIGRATION_DEPENDENCIES = True
except ImportError:  # pragma: no cover
    MIGRATION_DEPENDENCIES = False

ENGINES = ['sqlite'] + (['duckdb'] if duckdb is not None else [])
PUBLIC = '93.184.216.34'


def question(name='Detail', **policy):
    value = detail_by_region()
    value['name'] = name
    if policy:
        value['result_policy'] = policy
    return value


def export_policy(*formats, **extra):
    return {'export': {'enabled': True, 'formats': list(formats)}, **extra}


# ---------------------------------------------------------------------------
class ConditionTests(unittest.TestCase):
    """Metrics, comparisons and the firing state machine are pure."""

    def evaluate(self, condition, rows, previous=None, count=None):
        columns = list(rows[0]) if rows else ['amount']
        return am.evaluate_condition(
            am.validate_condition(condition), columns=columns, rows=rows,
            row_count=len(rows) if count is None else count,
            previous=previous)

    def test_every_operator(self):
        rows = [{'amount': 10}, {'amount': 30}]
        table = {
            ('>', 39): True, ('>', 40): False, ('>=', 40): True,
            ('<', 40): False, ('<', 41): True, ('<=', 40): True,
            ('==', 40): True, ('==', 41): False, ('!=', 40): False,
            ('!=', 41): True,
        }
        for (operator, bound), expected in table.items():
            with self.subTest(operator=operator, bound=bound):
                out = self.evaluate(column_metric(
                    'amount', 'sum', operator, bound), rows)
                self.assertIs(out['breached'], expected)
        self.assertTrue(self.evaluate(column_metric(
            'amount', 'sum', 'between', [40, 50]), rows)['breached'])
        self.assertTrue(self.evaluate(column_metric(
            'amount', 'sum', 'between', [30, 40]), rows)['breached'])
        self.assertFalse(self.evaluate(column_metric(
            'amount', 'sum', 'between', [41, 50]), rows)['breached'])

    def test_aggregates_and_first_value(self):
        rows = [{'amount': 10}, {'amount': 30}, {'amount': None}]
        values = {}
        for aggregate in ('first', 'sum', 'avg', 'min', 'max'):
            values[aggregate] = self.evaluate(column_metric(
                'amount', aggregate, '>', 0), rows)['value']
        self.assertEqual(values, {'first': 10, 'sum': 40, 'avg': 20,
                                  'min': 10, 'max': 30})

    def test_empty_aggregate_has_no_value_and_does_not_breach(self):
        out = self.evaluate(column_metric('amount', 'sum', '<', 5), [],
                            count=0)
        self.assertIsNone(out['value'])
        self.assertIs(out['breached'], False)
        self.assertEqual(out['detail'], 'no_value')

    def test_results_exist_and_empty(self):
        exist = {'type': 'results', 'state': 'exist'}
        empty = {'type': 'results', 'state': 'empty'}
        self.assertTrue(self.evaluate(exist, [{'a': 1}])['breached'])
        self.assertFalse(self.evaluate(exist, [], count=0)['breached'])
        self.assertTrue(self.evaluate(empty, [], count=0)['breached'])
        self.assertFalse(self.evaluate(empty, [{'a': 1}])['breached'])

    def test_row_count_uses_the_source_count(self):
        out = self.evaluate(rows_over(100), [{'a': 1}], count=101)
        self.assertTrue(out['breached'])

    def test_change_conditions_need_a_previous_value(self):
        rows = [{'amount': 120}]
        change = column_metric('amount', 'sum', '>', 15,
                               against='previous_change')
        first = self.evaluate(change, rows)
        self.assertIsNone(first['breached'])
        self.assertEqual(first['detail'], 'baseline')
        self.assertTrue(self.evaluate(change, rows, 100.0)['breached'])
        self.assertFalse(self.evaluate(change, rows, 110.0)['breached'])
        self.assertEqual(self.evaluate(change, rows, 100.0)['change'], 20.0)

    def test_percent_change_and_zero_previous(self):
        rows = [{'amount': 130}]
        percent = column_metric('amount', 'sum', '>=', 30,
                                against='previous_percent')
        out = self.evaluate(percent, rows, 100.0)
        self.assertTrue(out['breached'])
        self.assertAlmostEqual(out['change'], 30.0)
        # a drop is a negative percentage
        drop = column_metric('amount', 'sum', '<', -20,
                             against='previous_percent')
        self.assertTrue(self.evaluate(drop, [{'amount': 70}],
                                      100.0)['breached'])
        # a percentage of zero is undefined, never a breach
        undefined = self.evaluate(percent, rows, 0.0)
        self.assertIsNone(undefined['breached'])
        self.assertEqual(undefined['detail'], 'indeterminate')
        self.assertEqual(self.evaluate(
            percent, [{'amount': 0}], 0.0)['change'], 0.0)

    def test_validation_rejects_bad_conditions(self):
        bad = [
            {'type': 'metric'}, {'type': 'nope'},
            {'type': 'results', 'state': 'maybe'},
            column_metric('amount', 'median', '>', 1),
            column_metric('amount', 'sum', '~', 1),
            column_metric('amount', 'sum', '>', 'ten'),
            column_metric('amount', 'sum', '>', float('nan')),
            column_metric('amount', 'sum', 'between', [5, 1]),
            column_metric('amount', 'sum', 'between', 5),
            column_metric('amount', 'sum', '>', 1, against='yesterday'),
            column_metric('', 'sum', '>', 1),
            {'type': 'metric', 'metric': {'kind': 'median'},
             'operator': '>', 'value': 1},
        ]
        for condition in bad:
            with self.subTest(condition=condition):
                with self.assertRaises(AlertError):
                    am.validate_condition(condition)


class FiringStateTests(unittest.TestCase):
    """Edge-triggered by default, optional level, mute with a debt."""

    def step(self, state, breached, fire_on='transition', muted=False):
        out = am.advance(
            breach_state=state['breach_state'],
            pending_notify=state['pending_notify'], breached=breached,
            fire_on=fire_on, muted=muted)
        state.update(breach_state=out['breach_state'],
                     pending_notify=out['pending_notify'])
        return out

    @staticmethod
    def fresh():
        return {'breach_state': 'unknown', 'pending_notify': False}

    def test_edge_fires_once_per_breach_and_rearms_on_recovery(self):
        state, fired = self.fresh(), []
        for breached in (True, True, True, False, False, True, True):
            fired.append(self.step(state, breached)['fire'])
        self.assertEqual(fired, [True, False, False, False, False, True,
                                 False])

    def test_level_fires_while_in_breach(self):
        state, fired = self.fresh(), []
        for breached in (True, True, False, True):
            fired.append(self.step(state, breached, 'every_evaluation')[
                'fire'])
        self.assertEqual(fired, [True, True, False, True])

    def test_first_evaluation_in_breach_fires(self):
        out = self.step(self.fresh(), True)
        self.assertTrue(out['fire'])
        self.assertEqual(out['reason'], 'transition')

    def test_ok_first_evaluation_is_quiet_then_breach_fires(self):
        state = self.fresh()
        self.assertFalse(self.step(state, False)['fire'])
        self.assertEqual(state['breach_state'], 'ok')
        self.assertTrue(self.step(state, True)['fire'])

    def test_undecided_evaluation_changes_nothing(self):
        state = {'breach_state': 'breach', 'pending_notify': True}
        out = self.step(state, None)
        self.assertFalse(out['fire'])
        self.assertEqual(state, {'breach_state': 'breach',
                                 'pending_notify': True})

    def test_mute_suppresses_but_owes_one_notification(self):
        state = self.fresh()
        out = self.step(state, True, muted=True)
        self.assertFalse(out['fire'])
        self.assertEqual(out['suppressed'], 'muted')
        self.assertTrue(state['pending_notify'])
        # still muted: nothing, still owed
        self.assertFalse(self.step(state, True, muted=True)['fire'])
        # the mute ended while still in breach: the debt is paid once
        paid = self.step(state, True)
        self.assertTrue(paid['fire'])
        self.assertEqual(paid['reason'], 'unmuted')
        self.assertFalse(self.step(state, True)['fire'])

    def test_recovery_during_a_mute_cancels_the_debt(self):
        state = self.fresh()
        self.step(state, True, muted=True)
        self.step(state, False, muted=True)
        self.assertFalse(state['pending_notify'])
        self.assertFalse(self.step(state, True)['suppressed'] is not None)

    def test_level_under_mute_owes_nothing(self):
        state = self.fresh()
        out = self.step(state, True, 'every_evaluation', muted=True)
        self.assertEqual(out['suppressed'], 'muted')
        self.assertFalse(out['pending_notify'])


class ValidationTests(unittest.TestCase):
    def test_schedule_and_mute_rules(self):
        self.assertEqual(am.validate_schedule(
            {'expression': '*/15  * * * *'}), {
            'expression': '*/15 * * * *', 'timezone': 'UTC'})
        for bad in ({'expression': 'nope'}, {'expression': '* * * *'},
                    {'expression': '0 * * * *', 'timezone': 'Mars/Base'},
                    'hourly'):
            with self.assertRaises(AlertError):
                am.validate_schedule(bad)
        now = datetime(2026, 1, 1, 12, 0)
        self.assertEqual(am.mute_until(now, duration_minutes=30),
                         now + timedelta(minutes=30))
        for kwargs in ({}, {'duration_minutes': 0}, {'duration_minutes': 1e9},
                       {'duration_minutes': 60, 'until': '2026-01-02'},
                       {'until': 'tomorrow'}, {'duration_minutes': True},
                       {'duration_minutes': 60 * 24 * 91}):
            with self.assertRaises(AlertError):
                am.mute_until(now, **kwargs)

    def test_definition_shape_rules(self):
        good = alert_definition('q1', rows_over(1))
        normal = am.validate_alert(good, OWNER)
        self.assertEqual(normal['fire_on'], 'transition')
        self.assertEqual(normal['channels'][0]['recipients'],
                         [{'type': 'user', 'user_id': OWNER}])
        bad = {
            'no channel': {**good, 'channels': []},
            'dashboard alert': {**good, 'resource': {
                'type': 'dashboard', 'id': 'd'}},
            'kind': {**good, 'kind': 'digest'},
            'fire_on': {**good, 'fire_on': 'always'},
            'filters on a question': {**good, 'filters': {'a': 1}},
            'bad channel': {**good, 'channels': [{'type': 'sms'}]},
            'in-app email': {**good, 'channels': [{
                'type': 'in_app', 'recipients': [{
                    'type': 'email', 'address': 'a@b.example'}]}]},
            'duplicate recipient': {**good, 'channels': [{
                'type': 'in_app', 'recipients': [
                    {'type': 'self'}, {'type': 'user', 'user_id': OWNER}]}]},
            'bad object name': {**good, 'channels': [{
                'type': 's3', 'profile_id': 'archive',
                'object_name': '../escape'}]},
            'expiry': {**good, 'expires_in_days': 0},
        }
        for label, value in bad.items():
            with self.subTest(label):
                with self.assertRaises(AlertError):
                    am.validate_alert(value, OWNER)

    def test_subscription_needs_a_format_for_outside_channels(self):
        mail = [{'type': 'email', 'profile_id': 'mail',
                 'recipients': [{'type': 'self'}]}]
        with self.assertRaises(AlertError):
            am.validate_alert(subscription_definition(
                'question', 'q', channels=mail), OWNER)
        ok = am.validate_alert(subscription_definition(
            'question', 'q', fmt='csv', channels=mail), OWNER)
        self.assertEqual(ok['format'], 'csv')
        with self.assertRaises(AlertError):
            am.validate_alert(subscription_definition(
                'question', 'q', fmt='docx', channels=mail), OWNER)

    def test_message_row_cap_has_a_hard_ceiling(self):
        self.assertEqual(am.clamp_rows(5), 5)
        self.assertEqual(am.clamp_rows(10 ** 6), am.HARD_MESSAGE_ROWS)
        self.assertEqual(am.clamp_rows(-3), 0)
        self.assertEqual(am.clamp_rows('many'), 5)
        preview = am.build_preview(['a'], [{'a': i} for i in range(50)], 3)
        self.assertEqual((len(preview['rows']), preview['row_count'],
                          preview['truncated']), (3, 50, True))
        wide = am.build_preview(
            [f'c{i}' for i in range(40)], [{'c0': 'x' * 5000}], 5)
        self.assertEqual(len(wide['columns']), am.MAX_PREVIEW_COLUMNS)
        self.assertLessEqual(len(wide['rows'][0]['c0']), am.MAX_CELL_CHARS)


# ---------------------------------------------------------------------------
class WebhookTests(unittest.TestCase):
    URL = f'https://{HOOK_HOST}/inbound/alerts?src=cde'

    def channel(self, answers=None, status=200, hosts=None, **kwargs):
        self.resolver = StubResolver(answers or {HOOK_HOST: [PUBLIC]})
        self.transport = StubTransport(status)
        return WebhookChannel(
            hosts or {HOOK_HOST: {'secret': HOOK_SECRET, 'key_id': 'k1'}},
            resolver=self.resolver, transport=self.transport,
            clock=lambda: 1_700_000_000, **kwargs)

    def refusal(self, channel, url=None):
        with self.assertRaises(WebhookError) as caught:
            channel.send(self.URL if url is None else url, {'x': 1},
                         'delivery-1')
        self.assertEqual(self.transport.posts, [])
        return caught.exception.code

    def test_signature_covers_timestamp_and_exact_body(self):
        channel = self.channel()
        receipt = channel.send(self.URL, {'b': 2, 'a': 1}, 'delivery-1')
        self.assertEqual(receipt['status'], 200)
        (post,) = self.transport.posts
        headers, body = post['headers'], post['body']
        self.assertEqual(body, b'{"a":1,"b":2}')
        expected = hmac.new(
            HOOK_SECRET.encode(), b'1700000000.' + body,
            hashlib.sha256).hexdigest()
        self.assertEqual(headers['X-CDEadmin-Signature'], f'v1={expected}')
        self.assertEqual(headers['X-CDEadmin-Timestamp'], '1700000000')
        self.assertEqual(headers['X-CDEadmin-Key-Id'], 'k1')
        self.assertEqual(headers['X-CDEadmin-Delivery'], 'delivery-1')
        self.assertNotIn(HOOK_SECRET, json.dumps(headers))
        self.assertEqual((post['address'], post['host'], post['port'],
                          post['target']),
                         (PUBLIC, HOOK_HOST, 443, '/inbound/alerts?src=cde'))
        # a different body or timestamp changes the signature
        other = channel.sign(HOOK_HOST, b'{"a":2}', 1_700_000_000)
        self.assertNotEqual(other, headers['X-CDEadmin-Signature'])
        self.assertNotEqual(
            channel.sign(HOOK_HOST, body, 1_700_000_001),
            headers['X-CDEadmin-Signature'])

    def test_each_host_signs_with_its_own_secret(self):
        channel = self.channel(
            {HOOK_HOST: [PUBLIC], 'other.example.com': [PUBLIC]},
            hosts={HOOK_HOST: {'secret': HOOK_SECRET},
                   'other.example.com': {'secret': 'z' * 32}})
        self.assertNotEqual(channel.sign(HOOK_HOST, b'x', 1),
                            channel.sign('other.example.com', b'x', 1))

    def test_host_allow_list_scheme_and_url_shape(self):
        channel = self.channel()
        cases = {
            'http://hooks.example.com/x': 'url_scheme',
            'ftp://hooks.example.com/x': 'url_scheme',
            'https://evil.example.com/x': 'host_not_allowed',
            'https://hooks.example.com.evil.example/x': 'host_not_allowed',
            'https://user:pw@hooks.example.com/x': 'url_userinfo',
            'https://hooks.example.com:8443/x': 'host_not_allowed',
            'https://hooks.example.com/x#frag': 'url_invalid',
            'https://hooks.example.com/a b': 'url_invalid',
            'https://hooks.example.com/\r\nX-Evil: 1': 'url_invalid',
            'https://127.0.0.1/x': 'host_not_allowed',
            'https://[::1]/x': 'host_not_allowed',
            'https://2130706433/x': 'host_not_allowed',
            'https://localhost/x': 'host_not_allowed',
            '': 'url_invalid', 'https://': 'host_not_allowed',
        }
        for url, code in cases.items():
            with self.subTest(url=url):
                self.assertEqual(self.refusal(channel, url), code)
        self.assertEqual(self.resolver.calls, [])  # refused before DNS
        # a trailing dot and upper case still name the allowed host
        self.assertEqual(channel.check_url(
            'https://HOOKS.example.com./x')[0], HOOK_HOST)

    def test_ip_literals_cannot_be_allow_listed(self):
        for name in ('127.0.0.1', '10.0.0.1', '::1'):
            with self.assertRaises(WebhookError):
                WebhookChannel({name: {'secret': HOOK_SECRET}})
        with self.assertRaises(WebhookError):
            WebhookChannel({HOOK_HOST: {'secret': 'short'}})

    def test_non_public_answers_are_refused(self):
        refused = ['127.0.0.1', '10.1.2.3', '172.16.0.9', '192.168.1.1',
                   '169.254.169.254', '0.0.0.0', '100.64.0.1', '224.0.0.1',
                   '::1', 'fe80::1', 'fc00::1', '::ffff:127.0.0.1',
                   '::ffff:10.0.0.1', '2002:7f00:1::', '64:ff9b::7f00:1']
        for address in refused:
            with self.subTest(address=address):
                channel = self.channel({HOOK_HOST: [address]})
                self.assertEqual(self.refusal(channel), 'address_refused')

    def test_one_private_answer_poisons_the_whole_set(self):
        channel = self.channel({HOOK_HOST: [PUBLIC, '10.0.0.5']})
        self.assertEqual(self.refusal(channel), 'address_refused')
        channel = self.channel({HOOK_HOST: ['10.0.0.5', PUBLIC]})
        self.assertEqual(self.refusal(channel), 'address_refused')

    def test_dns_rebinding_cannot_change_the_connected_address(self):
        # the first answer is public, any later answer is loopback
        channel = self.channel({HOOK_HOST: lambda n: (
            [PUBLIC] if n == 1 else ['127.0.0.1'])})
        channel.send(self.URL, {'x': 1}, 'd')
        (post,) = self.transport.posts
        self.assertEqual(post['address'], PUBLIC)
        self.assertEqual(self.resolver.calls, [HOOK_HOST])  # resolved once
        # and a flip on the first lookup is simply refused
        channel = self.channel({HOOK_HOST: lambda n: (
            ['127.0.0.1'] if n == 1 else [PUBLIC])})
        self.assertEqual(self.refusal(channel), 'address_refused')

    def test_dns_failure_and_empty_answers(self):
        def failing(host, port, type=None):
            raise OSError('no such host')
        channel = self.channel()
        channel.resolver = failing
        self.assertEqual(self.refusal(channel), 'dns_failed')
        channel = self.channel({HOOK_HOST: []})
        self.assertEqual(self.refusal(channel), 'dns_failed')

    def test_redirects_are_never_followed(self):
        for status in (301, 302, 307, 308):
            with self.subTest(status=status):
                channel = self.channel(status=status)
                with self.assertRaises(WebhookError) as caught:
                    channel.send(self.URL, {'x': 1}, 'd')
                self.assertEqual(caught.exception.code, 'redirect_refused')
                self.assertTrue(caught.exception.outcome_unknown)
                self.assertEqual(len(self.transport.posts), 1)

    def test_status_and_transport_failures_have_finality(self):
        with self.assertRaises(WebhookError) as caught:
            self.channel(status=400).send(self.URL, {}, 'd')
        self.assertEqual((caught.exception.code,
                          caught.exception.outcome_unknown),
                         ('http_error', False))
        with self.assertRaises(WebhookError) as caught:
            self.channel(status=503).send(self.URL, {}, 'd')
        self.assertTrue(caught.exception.outcome_unknown)
        channel = self.channel()
        self.transport.error = TimeoutError('slow')
        with self.assertRaises(WebhookError) as caught:
            channel.send(self.URL, {}, 'd')
        self.assertEqual(caught.exception.code, 'transport_failed')
        self.assertTrue(caught.exception.outcome_unknown)
        # the native error text never reaches the caller
        self.assertNotIn('slow', str(caught.exception))

    def test_timeout_is_short_and_bounded(self):
        self.assertEqual(self.channel().timeout, 5.0)
        self.assertEqual(self.channel(timeout=10 ** 6).timeout, 15.0)
        self.assertEqual(self.channel(timeout=0).timeout, 0.5)
        channel = self.channel()
        channel.send(self.URL, {}, 'd')
        self.assertEqual(self.transport.posts[0]['timeout'], 5.0)

    def test_oversized_bodies_are_refused(self):
        channel = self.channel()
        self.assertEqual(
            self.refusal_for_body(channel, 'x' * 300_000), 'body_too_large')

    def refusal_for_body(self, channel, text):
        with self.assertRaises(WebhookError) as caught:
            channel.send(self.URL, {'x': text}, 'd')
        return caught.exception.code


# ---------------------------------------------------------------------------
class AlertCase(unittest.TestCase):
    engine = 'sqlite'
    config = None
    external = None

    def setUp(self):
        self.a = AlertStack(self.engine, config=self.config,
                            external=self.external)
        self.s, self.ep, self.svc = self.a.s, self.a.ep, self.a.service

    # builders --------------------------------------------------------------
    def make_question(self, user=OWNER, **kwargs):
        return self.s.q(user, question(**kwargs))

    def alert(self, qid, condition=None, user=OWNER, **kwargs):
        return self.a.create(alert_definition(
            qid, condition or rows_over(3), **kwargs), user)

    def sql(self, statement):
        self.s.connection.execute(statement)

    def grant_id(self, kind, resource_id, principal):
        return self.s.bi.access.grants.find(
            self.ep, kind, resource_id, 'user', principal)['grant_id']

    def revoke(self, kind, resource_id, principal, actor=OWNER):
        self.s.bi.access.remove_grant(
            actor, kind, self.ep, resource_id,
            self.grant_id(kind, resource_id, principal))

    def regrade(self, kind, resource_id, principal, level, actor=OWNER):
        self.s.bi.access.update_grant(
            actor, kind, self.ep, resource_id,
            self.grant_id(kind, resource_id, principal), level)

    def state(self, alert_id):
        return self.svc.get(OWNER, self.ep, alert_id)

    def fired(self, alert_id):
        return [e.fired for e in self.a.events(alert_id)]

    def notes(self, user=OWNER):
        return [n for n in self.a.repo.note_rows if n.user_id == user]


class EvaluationTests(AlertCase):
    def test_create_authorizes_unattended_runs_and_previews_the_schedule(self):
        qid = self.make_question()
        created = self.alert(qid)
        self.assertEqual(created['status'], 'active')
        self.assertEqual(created['next_runs'][0], '2026-03-02T10:00:00+00:00')
        self.assertEqual(created['delegation']['state'], 'active')
        self.assertTrue(created['delegation']['unattended'])
        self.assertEqual(created['breach_state'], 'unknown')
        self.assertEqual(created['resource']['revision'], 1)

    def test_nothing_is_created_without_the_worker_key_authority(self):
        qid = self.make_question()
        self.a.scheduler.available = False
        with self.assertRaisesRegex(AlertError, 'unattended scheduling'):
            self.alert(qid)
        self.assertEqual(self.a.repo.alerts, {})

    def test_a_failed_authorization_leaves_no_alert_behind(self):
        qid = self.make_question()
        with self.assertRaises(ReportSchedulerAccessError):
            self.svc.create(OWNER, self.ep, alert_definition(
                qid, rows_over(1)), SimpleNamespace(user_id=VIEWER))
        self.assertEqual(self.a.repo.alerts, {})

    def test_edge_triggered_by_default(self):
        qid = self.make_question()
        alert_id = self.alert(qid, rows_over(3))['alert_id']
        run = lambda: self.a.run(alert_id)  # noqa: E731
        outcomes = []
        outcomes.append(run())     # 5 rows: breach, fires
        outcomes.append(run())     # still breach: quiet
        self.sql('DELETE FROM sales WHERE amount < 30')   # 2 rows left
        outcomes.append(run())     # recovered: quiet
        self.sql("INSERT INTO sales VALUES ('n','a',1,1,''),('n','b',2,1,''),"
                 "('n','c',3,1,'')")
        outcomes.append(run())     # breach again: fires again
        self.assertEqual(self.fired(alert_id), [True, False, False, True])
        self.assertEqual(len(self.notes()), 2)
        self.assertTrue(all(o['state'] == 'delivered' for o in outcomes))
        labels = [e.outcome for e in self.a.events(alert_id)]
        self.assertEqual(labels, ['breach', 'breach', 'ok', 'breach'])

    def test_level_triggered_fires_on_every_breaching_evaluation(self):
        qid = self.make_question()
        alert_id = self.alert(qid, rows_over(3),
                              fire_on='every_evaluation')['alert_id']
        for _ in range(3):
            self.a.run(alert_id)
        self.assertEqual(self.fired(alert_id), [True, True, True])
        self.assertEqual(len(self.notes()), 3)

    def test_rearm_forgets_the_breach(self):
        qid = self.make_question()
        alert_id = self.alert(qid)['alert_id']
        self.a.run(alert_id)
        self.a.run(alert_id)
        self.assertEqual(self.fired(alert_id), [True, False])
        self.svc.rearm(OWNER, self.ep, alert_id)
        self.assertEqual(self.state(alert_id)['breach_state'], 'ok')
        self.a.run(alert_id)
        self.assertEqual(self.fired(alert_id), [True, False, True])

    def test_snooze_suppresses_then_notifies_once_after_expiry(self):
        qid = self.make_question()
        alert_id = self.alert(qid)['alert_id']
        muted = self.svc.mute(OWNER, self.ep, alert_id, duration_minutes=120)
        self.assertTrue(muted['muted'])
        self.assertEqual(muted['muted_until'], '2026-03-02T11:00:00+00:00')
        self.a.run(alert_id)                 # breach while muted
        self.a.clock.advance(hours=1)
        self.a.run(alert_id)                 # still muted
        events = self.a.events(alert_id)
        self.assertEqual([e.suppressed for e in events], ['muted', 'muted'])
        self.assertEqual(self.notes(), [])
        self.assertTrue(self.state(alert_id)['pending_notify'])
        self.a.clock.advance(hours=2)        # the mute has expired
        self.a.run(alert_id)
        self.a.run(alert_id)
        self.assertEqual(self.fired(alert_id), [False, False, True, False])
        state = self.state(alert_id)
        self.assertFalse(state['muted'])
        self.assertFalse(state['pending_notify'])
        self.assertEqual(len(self.notes()), 1)

    def test_unmute_and_mute_validation(self):
        qid = self.make_question()
        alert_id = self.alert(qid)['alert_id']
        self.svc.mute(OWNER, self.ep, alert_id, duration_minutes=30)
        self.assertFalse(self.svc.unmute(OWNER, self.ep, alert_id)['muted'])
        for kwargs in ({}, {'duration_minutes': 0},
                       {'until': '2026-03-02T09:00:00'}):
            with self.assertRaises(AlertError):
                self.svc.mute(OWNER, self.ep, alert_id, **kwargs)
        until = self.svc.mute(OWNER, self.ep, alert_id,
                              until='2026-03-02T12:30:00+00:00')
        self.assertEqual(until['muted_until'], '2026-03-02T12:30:00+00:00')

    def test_change_since_the_previous_evaluation(self):
        qid = self.make_question()
        condition = column_metric('amount', 'sum', '>=', 20,
                                  against='previous_percent')
        alert_id = self.alert(qid, condition)['alert_id']
        self.a.run(alert_id)            # baseline: sum 105, no verdict
        self.assertEqual(self.state(alert_id)['breach_state'], 'unknown')
        self.assertEqual(self.a.events(alert_id)[0].outcome, 'baseline')
        self.sql("INSERT INTO sales VALUES ('n','a',10,1,'')")
        self.a.run(alert_id)            # 105 -> 115 is +9.5 percent
        self.assertEqual(self.state(alert_id)['breach_state'], 'ok')
        self.sql("INSERT INTO sales VALUES ('n','b',60,1,'')")
        self.a.run(alert_id)            # 115 -> 175 is +52 percent
        self.assertEqual(self.fired(alert_id), [False, False, True])
        value = self.a.events(alert_id)[-1].value
        self.assertAlmostEqual(json.loads(value)['change'], 60 / 115 * 100)
        self.assertIn('Change: ', self.notes()[0].body)

    def test_absolute_change_and_previous_survive_a_quiet_run(self):
        qid = self.make_question()
        condition = column_metric('amount', 'max', '>', 15,
                                  against='previous_change')
        alert_id = self.alert(qid, condition)['alert_id']
        self.a.run(alert_id)                       # max 40, baseline
        self.sql("INSERT INTO sales VALUES ('n','a',70,1,'')")
        self.a.run(alert_id)                       # +30
        self.assertEqual(self.fired(alert_id), [False, True])
        self.a.run(alert_id)                       # +0: recovered
        self.assertEqual(self.state(alert_id)['breach_state'], 'ok')

    def test_results_exist_and_empty(self):
        qid = self.make_question()
        empty = self.alert(qid, {'type': 'results', 'state': 'empty'},
                           name='empty')['alert_id']
        exists = self.alert(qid, {'type': 'results', 'state': 'exist'},
                            name='exists')['alert_id']
        self.a.run(empty)
        self.a.run(exists)
        self.assertEqual((self.fired(empty), self.fired(exists)),
                         ([False], [True]))
        self.sql('DELETE FROM sales')
        self.a.run(empty)
        self.a.run(exists)
        self.assertEqual((self.fired(empty), self.fired(exists)),
                         ([False, True], [True, False]))

    def test_transition_after_pause_and_resume(self):
        qid = self.make_question()
        alert_id = self.alert(qid)['alert_id']
        self.a.run(alert_id)                             # fires
        paused = self.svc.pause(OWNER, self.ep, alert_id)
        self.assertEqual((paused['status'], paused['pause_reason']),
                         ('paused', 'user_paused'))
        self.assertEqual(self.a.run(alert_id)['state'], 'cancelled')
        self.assertEqual(len(self.a.events(alert_id)), 2)  # fire + pause
        # still in breach after the pause: the breach is not announced twice
        self.svc.resume(OWNER, self.ep, alert_id)
        self.a.run(alert_id)
        self.assertEqual(self.fired(alert_id), [True, False, False])
        # recovered during a pause, then breached after it: a new edge
        self.svc.pause(OWNER, self.ep, alert_id)
        self.sql('DELETE FROM sales WHERE amount < 30')
        self.svc.resume(OWNER, self.ep, alert_id)
        self.a.run(alert_id)
        self.sql("INSERT INTO sales VALUES ('n','a',1,1,''),('n','b',2,1,''),"
                 "('n','c',3,1,'')")
        self.a.run(alert_id)
        self.assertTrue(self.a.events(alert_id)[-1].fired)

    def test_resume_with_reset_announces_an_ongoing_breach(self):
        qid = self.make_question()
        alert_id = self.alert(qid)['alert_id']
        self.a.run(alert_id)
        self.svc.pause(OWNER, self.ep, alert_id)
        self.svc.resume(OWNER, self.ep, alert_id, reset=True)
        self.assertEqual(self.state(alert_id)['breach_state'], 'unknown')
        self.a.run(alert_id)
        self.assertTrue(self.a.events(alert_id)[-1].fired)

    def test_parameters_and_pinned_revision_are_used(self):
        qid = self.s.q(OWNER, region_question())
        condition = column_metric('amount', 'sum', '>', 50)
        alert_id = self.a.create(alert_definition(
            qid, condition, parameters={'region': 'west'}))['alert_id']
        self.a.run(alert_id)             # west: 20 + 40 + 5 = 65
        self.assertTrue(self.a.events(alert_id)[0].fired)
        east = self.a.create(alert_definition(
            qid, condition, name='east', parameters={'region': 'east'}))
        self.a.run(east['alert_id'])     # east: 10 + 30 = 40
        self.assertFalse(self.a.events(east['alert_id'])[0].fired)
        # editing the question does not change what the alert watches
        edited = region_question()
        edited['query']['builder']['filters'] = []
        self.s.bi.update_question(OWNER, self.ep, qid, 1, edited)
        self.a.run(east['alert_id'])
        self.assertEqual(self.a.events(east['alert_id'])[-1].resource_revision,
                         1)
        self.assertEqual(json.loads(self.a.events(east['alert_id'])[-1].value)[
            'value'], 40.0)

    def test_update_resets_the_state_when_the_condition_changes(self):
        qid = self.make_question()
        created = self.alert(qid, rows_over(3))
        alert_id = created['alert_id']
        self.a.run(alert_id)
        self.assertEqual(self.state(alert_id)['breach_state'], 'breach')
        definition = alert_definition(qid, rows_over(10), name='Renamed')
        updated = self.svc.update(OWNER, self.ep, alert_id,
                                  created['revision'], definition)
        self.assertEqual((updated['name'], updated['revision'],
                          updated['breach_state']), ('Renamed', 2,
                                                     'unknown'))
        with self.assertRaises(BIError):
            self.svc.update(OWNER, self.ep, alert_id, created['revision'],
                            definition)
        with self.assertRaisesRegex(AlertError, 'cannot change'):
            self.svc.update(OWNER, self.ep, alert_id, 2, alert_definition(
                self.make_question(name='Other'), rows_over(1)))

    def test_delete_revokes_the_delegation(self):
        qid = self.make_question()
        alert_id = self.alert(qid)['alert_id']
        delegation = self.a.scheduler.delegation_for(alert_id)
        self.svc.delete(OWNER, self.ep, alert_id)
        self.assertEqual(delegation.state, 'revoked')
        with self.assertRaisesRegex(AlertError, 'unavailable'):
            self.svc.get(OWNER, self.ep, alert_id)

    def test_limits_and_names(self):
        qid = self.make_question()
        with self.assertRaisesRegex(AlertError, 'more often'):
            self.alert(qid, schedule={'expression': '* * * * *'})
        self.alert(qid)
        with self.assertRaisesRegex(BIError, 'already exists'):
            self.alert(qid)

    def test_a_dry_run_changes_nothing_and_sends_nothing(self):
        qid = self.make_question()
        created = self.alert(qid, channels=[
            {'type': 'in_app', 'recipients': [{'type': 'self'}]},
            {'type': 'webhook', 'url': f'https://{HOOK_HOST}/in'}])
        before = json.dumps(self.state(created['alert_id']), sort_keys=True)
        report = self.svc.test(OWNER, self.ep, runtime=self.a.runtime(),
                               alert_id=created['alert_id'])
        self.assertTrue(report['dry_run'])
        self.assertTrue(report['would_fire'])
        self.assertEqual(report['outcome']['value'], 5.0)
        self.assertEqual({d['state'] for d in report['deliveries']},
                         {'would_send'})
        self.assertEqual(report['message']['preview']['row_count'], 5)
        self.assertEqual(self.a.repo.note_rows, [])
        self.assertEqual(self.a.events(created['alert_id']), [])
        self.assertEqual(self.a.transport.posts, [])
        self.assertEqual(self.a.resolver.calls, [])
        self.assertEqual(before, json.dumps(
            self.state(created['alert_id']), sort_keys=True))
        # a draft can be tested before it is saved
        draft = self.svc.test(OWNER, self.ep, runtime=self.a.runtime(),
                              value=alert_definition(qid, rows_over(99),
                                                     name='draft'))
        self.assertFalse(draft['would_fire'])
        self.assertEqual(len(self.a.repo.alerts), 1)

    def test_run_now_goes_through_the_lease_path_and_is_rate_limited(self):
        qid = self.make_question()
        alert_id = self.alert(qid)['alert_id']
        result = self.svc.run_now(OWNER, self.ep, alert_id)
        self.assertEqual(result['state'], 'delivered')
        self.assertEqual(result['event']['trigger'], 'run_now')
        self.assertTrue(result['event']['fired'])
        with self.assertRaisesRegex(AlertError, 'wait'):
            self.svc.run_now(OWNER, self.ep, alert_id)
        self.a.clock.advance(minutes=1)
        self.assertEqual(self.svc.run_now(
            OWNER, self.ep, alert_id)['state'], 'delivered')
        self.svc.pause(OWNER, self.ep, alert_id)
        self.a.clock.advance(minutes=1)
        with self.assertRaisesRegex(AlertError, 'paused'):
            self.svc.run_now(OWNER, self.ep, alert_id)

    def test_a_manager_cannot_run_another_owners_alert_now(self):
        qid = self.make_question()
        alert_id = self.alert(qid)['alert_id']
        self.s.share(OWNER, 'question', qid, MANAGER, 'manage')
        with self.assertRaisesRegex(AlertError, 'only the owner'):
            self.svc.run_now(MANAGER, self.ep, alert_id)
        self.assertEqual(self.a.events(alert_id), [])

    def test_a_failing_question_pauses_after_repeated_failures(self):
        qid = self.make_question()
        alert_id = self.alert(
            qid, column_metric('nope', 'sum', '>', 1))['alert_id']
        for _ in range(am.MAX_FAILURES - 1):
            self.assertEqual(self.a.run(alert_id)['state'], 'failed')
        self.assertEqual(self.state(alert_id)['status'], 'active')
        self.a.run(alert_id)
        paused = self.state(alert_id)
        self.assertEqual((paused['status'], paused['pause_reason']),
                         ('paused', 'repeated_failures'))
        self.assertEqual(
            {e.error_class for e in self.a.events(alert_id)},
            {'column_missing', 'repeated_failures'})

    def test_a_truncated_result_cannot_give_an_exact_row_count(self):
        self.sql('DELETE FROM sales')
        for start in range(0, 1200, 400):
            values = ','.join(f"('r','p',{i},1,'')"
                              for i in range(start, start + 400))
            self.sql(f'INSERT INTO sales VALUES {values}')
        big = question(name='Big')
        big['query']['builder']['limit'] = 1200
        qid = self.s.q(OWNER, big)
        self.svc.config['max_result_pages'] = 1
        alert_id = self.alert(qid, rows_over(100))['alert_id']
        self.assertEqual(self.a.run(alert_id)['state'], 'failed')
        self.assertEqual(self.a.events(alert_id)[0].error_class,
                         'result_truncated')
        # a first-value metric is still exact on the first page
        first = self.alert(qid, column_metric('amount', 'first', '>=', 0),
                           name='first')['alert_id']
        self.assertEqual(self.a.run(first)['state'], 'delivered')
        self.svc.config['max_result_pages'] = 20
        self.a.run(alert_id)
        self.assertTrue(self.a.events(alert_id)[-1].fired)

    def test_results_are_released_after_every_evaluation(self):
        qid = self.make_question()
        alert_id = self.alert(qid)['alert_id']
        self.a.run(alert_id)
        self.assertEqual(self.s.executor.cache_info(OWNER, self.ep), [])
        self.svc.test(OWNER, self.ep, runtime=self.a.runtime(),
                      alert_id=alert_id)
        self.assertEqual(self.s.executor.cache_info(OWNER, self.ep), [])

    def test_the_query_runs_with_the_owners_endpoint_not_the_workers(self):
        qid = self.make_question()
        shared = self.alert(qid)['alert_id']
        self.a.run(shared)
        who = [s['endpoint']['route']['credential_owner']
               for s in self.s.studio.sessions]
        self.assertEqual(who, [OWNER])


class RevocationTests(AlertCase):
    def shared_alert(self):
        qid = self.make_question()
        self.s.share(OWNER, 'question', qid, VIEWER, 'view')
        alert_id = self.alert(qid, user=VIEWER)['alert_id']
        return qid, alert_id

    def test_losing_view_access_pauses_the_alert_and_destroys_the_delegation(
            self):
        qid, alert_id = self.shared_alert()
        self.a.run(alert_id)
        runs = len(self.s.studio.sessions)
        self.revoke('question', qid, VIEWER)
        outcome = self.a.run(alert_id)
        self.assertEqual(outcome['state'], 'cancelled')
        self.assertEqual(outcome['error_code'], 'resource_unavailable')
        self.assertEqual(len(self.s.studio.sessions), runs)  # nothing ran
        row = self.a.repo.get(alert_id)
        self.assertEqual((row.status, row.pause_reason),
                         ('paused', 'resource_unavailable'))
        self.assertEqual(self.a.scheduler.delegation_for(alert_id).state,
                         'revoked')
        last = self.a.events(alert_id)[-1]
        self.assertEqual((last.outcome, last.error_class),
                         ('paused', 'resource_unavailable'))
        # the pause is visible to the owner with a fixed explanation
        shown = self.svc.get(VIEWER, self.ep, alert_id)
        self.assertEqual(shown['pause_text'],
                         am.FAILURE_TEXT['resource_unavailable'])

    def test_a_resume_needs_access_again_and_a_fresh_authorization(self):
        qid, alert_id = self.shared_alert()
        self.revoke('question', qid, VIEWER)
        self.a.run(alert_id)
        with self.assertRaisesRegex(BIError, 'unavailable'):
            self.svc.resume(VIEWER, self.ep, alert_id,
                            SimpleNamespace(user_id=VIEWER))
        self.s.share(OWNER, 'question', qid, VIEWER, 'view')
        with self.assertRaisesRegex(AlertError, 'owner session'):
            self.svc.resume(VIEWER, self.ep, alert_id)
        resumed = self.svc.resume(VIEWER, self.ep, alert_id,
                                  SimpleNamespace(user_id=VIEWER))
        self.assertEqual(resumed['status'], 'active')
        self.assertTrue(resumed['delegation']['unattended'])
        self.assertEqual(self.a.run(alert_id)['state'], 'delivered')

    def test_archived_content_stops_the_alert(self):
        qid = self.make_question()
        alert_id = self.alert(qid)['alert_id']
        self.s.bi.set_status(OWNER, self.ep, qid, 1, 'archived')
        outcome = self.a.run(alert_id)
        self.assertEqual(outcome['state'], 'failed')
        self.assertEqual(self.a.events(alert_id)[-1].error_class, 'archived')

    def test_credential_and_delegation_failures_pause_with_a_reason(self):
        cases = [
            (ReportSchedulerConflict('changed'), 'endpoint_changed', True),
            (ReportSchedulerError('x'), 'credential_unavailable', True),
        ]
        for error, reason, revoked in cases:
            with self.subTest(reason=reason):
                self.setUp()
                alert_id = self.alert(self.make_question())['alert_id']
                self.a.scheduler.runtime_error = error
                outcome = self.a.run(alert_id)
                self.assertEqual(outcome['error_code'], reason)
                self.assertEqual(self.a.repo.get(alert_id).pause_reason,
                                 reason)
                self.assertEqual(
                    self.a.scheduler.delegation_for(alert_id).state ==
                    'revoked', revoked)

    def test_an_expired_delegation_pauses_the_alert(self):
        alert_id = self.alert(self.make_question(),
                              expires_in_days=1)['alert_id']
        self.a.clock.advance(days=2)
        outcome = self.a.run(alert_id)
        self.assertEqual(outcome['error_code'], 'delegation_expired')
        row = self.a.repo.get(alert_id)
        self.assertEqual((row.status, row.pause_reason),
                         ('paused', 'delegation_expired'))

    def test_a_paused_alert_runs_nothing(self):
        alert_id = self.alert(self.make_question())['alert_id']
        self.svc.pause(OWNER, self.ep, alert_id)
        before = len(self.s.studio.sessions)
        self.assertEqual(self.a.run(alert_id)['phase'], 'alert-paused')
        self.assertEqual(len(self.s.studio.sessions), before)

    def test_only_the_owner_or_a_manager_reaches_an_alert(self):
        qid = self.make_question()
        self.s.share(OWNER, 'question', qid, VIEWER, 'view')
        self.s.share(OWNER, 'question', qid, EDITOR, 'edit')
        self.s.share(OWNER, 'question', qid, MANAGER, 'manage')
        alert_id = self.alert(qid, user=VIEWER)['alert_id']
        for user in (EDITOR, STRANGER, ANALYST):
            with self.subTest(user=user):
                with self.assertRaisesRegex(AlertError, 'unavailable'):
                    self.svc.get(user, self.ep, alert_id)
                with self.assertRaisesRegex(AlertError, 'unavailable'):
                    self.svc.mute(user, self.ep, alert_id,
                                  duration_minutes=10)
        # a manager of the resource can see, mute and delete, not edit
        self.assertEqual(self.svc.get(MANAGER, self.ep, alert_id)['alert_id'],
                         alert_id)
        self.svc.mute(MANAGER, self.ep, alert_id, duration_minutes=10)
        with self.assertRaisesRegex(AlertError, 'only the owner'):
            self.svc.update(MANAGER, self.ep, alert_id, 1, alert_definition(
                qid, rows_over(9)))
        with self.assertRaisesRegex(AlertError, 'only the owner'):
            self.svc.resume(MANAGER, self.ep, alert_id)
        # lists are scoped the same way
        self.assertEqual(self.svc.list(EDITOR, self.ep, 'question', qid), [])
        self.assertEqual(len(self.svc.list(MANAGER, self.ep, 'question',
                                           qid)), 1)
        self.assertEqual(len(self.svc.list(VIEWER, self.ep)), 1)
        self.assertEqual(self.svc.list(OWNER, self.ep), [])

    def test_a_viewer_cannot_alert_on_what_they_cannot_see(self):
        qid = self.make_question()
        with self.assertRaisesRegex(BIError, 'unavailable'):
            self.alert(qid, user=VIEWER)
        with self.assertRaisesRegex(BIError, 'unavailable'):
            self.alert('no-such-question')


class RawSqlAndPolicyTests(AlertCase):
    def test_raw_sql_alerts_follow_the_raw_sql_policy(self):
        qid = self.s.q(OWNER, sql_question(
            'SELECT region, amount FROM sales ORDER BY amount'))
        alert_id = self.alert(qid, rows_over(1))['alert_id']
        self.a.run(alert_id)
        self.assertTrue(self.a.events(alert_id)[0].fired)
        # once the owner declares a row policy, raw SQL bypasses it
        RunAsRunnerTests.tenant_model(None)
        self.s.bi.semantic.create(OWNER, self.ep, RunAsRunnerTests.tenant_model(
            None))
        with self.assertRaisesRegex(BIError, 'raw SQL'):
            self.alert(qid, rows_over(1), name='second')

    def test_a_redacted_column_cannot_be_the_condition(self):
        qid = self.s.q(OWNER, question(
            name='Redacted', redact_columns=['amount']))
        with self.assertRaisesRegex(AlertError, 'redacted'):
            self.alert(qid, column_metric('amount', 'sum', '>', 1))
        self.alert(qid, rows_over(1), name='rows')   # counting is fine

    def test_row_policy_content_goes_to_its_owner_only(self):
        tenant = RunAsRunnerTests.tenant_model(None)
        created = self.s.bi.semantic.create(OWNER, self.ep, tenant)
        qid = self.s.q(OWNER, {
            'name': 'Tenant cube',
            'semantic_model': {'id': created['model_id'], 'revision': 1},
            'query': {'kind': 'semantic', 'builder': {
                'group_by': ['region'],
                'aggregations': [{'measure_id': 'revenue'}],
                'limit': 10}}})
        self.s.share(OWNER, 'question', qid, VIEWER, 'view')
        to_viewer = [{'type': 'in_app', 'recipients': [
            {'type': 'user', 'user_id': VIEWER}]}]
        with self.assertRaisesRegex(AlertError, 'row policy'):
            self.alert(qid, rows_over(0), channels=to_viewer)
        mine = self.alert(qid, rows_over(0), name='mine')['alert_id']
        self.a.run(mine)
        self.assertEqual(len(self.notes(OWNER)), 1)
        # the row policy is applied with the OWNER's claims, never a viewer's
        claims = [c['claims']['user_id'] for c in self.s.security_contexts]
        self.assertEqual(set(claims), {OWNER})


class DeliveryTests(AlertCase):
    external = {'domains': ['partner.example'],
                'addresses': ['auditor@elsewhere.example']}

    def email(self, *recipients, profile='mail'):
        return {'type': 'email', 'profile_id': profile,
                'recipients': list(recipients)}

    def test_recipients_need_view_access_at_creation_and_at_send_time(self):
        qid = self.make_question()
        to_viewer = [{'type': 'in_app', 'recipients': [
            {'type': 'self'}, {'type': 'user', 'user_id': VIEWER}]}]
        with self.assertRaisesRegex(AlertError, 'view access'):
            self.alert(qid, channels=to_viewer)
        self.s.share(OWNER, 'question', qid, VIEWER, 'view')
        alert_id = self.alert(qid, channels=to_viewer)['alert_id']
        self.a.run(alert_id)
        self.assertEqual((len(self.notes(OWNER)), len(self.notes(VIEWER))),
                         (1, 1))
        # access is withdrawn: the next fire skips that recipient only
        self.revoke('question', qid, VIEWER)
        self.svc.rearm(OWNER, self.ep, alert_id)
        self.a.run(alert_id)
        self.assertEqual((len(self.notes(OWNER)), len(self.notes(VIEWER))),
                         (2, 1))
        skipped = [d for d in json.loads(self.a.events(alert_id)[-1]
                                         .deliveries) if d['state'] == 'skipped']
        self.assertEqual([(d['target'], d['code']) for d in skipped],
                         [(f'user:{VIEWER}', 'recipient_not_authorized')])

    def test_recipients_must_be_visible_users(self):
        qid = self.make_question()
        for user in (STRANGER, 999):
            with self.subTest(user=user):
                with self.assertRaisesRegex(AlertError, 'unavailable'):
                    self.alert(qid, channels=[{
                        'type': 'in_app', 'recipients': [
                            {'type': 'user', 'user_id': user}]}])

    def test_pgadmin_user_email_goes_to_their_own_address(self):
        qid = self.make_question()
        self.s.share(OWNER, 'question', qid, VIEWER, 'view')
        alert_id = self.alert(qid, channels=[self.email(
            {'type': 'self'}, {'type': 'user', 'user_id': VIEWER})])[
            'alert_id']
        self.a.run(alert_id)
        sent = [(p[1]['recipients'], p[2]) for p in self.a.smtp.calls]
        self.assertEqual([r for r, _ in sent],
                         [['owner@corp.example'], ['viewer@corp.example']])
        payload = sent[0][1]
        self.assertTrue(payload['subject'].startswith('Alert "Revenue watch"'))
        document = json.loads(payload['content'])
        self.assertEqual(document['event'], 'alert.fired')
        self.assertEqual(document['preview']['row_count'], 5)
        self.assertIn('Condition: row count > 3', payload['body'])

    def test_external_recipients_need_manage_and_the_server_allow_list(self):
        qid = self.make_question()
        outside = {'type': 'email', 'address': 'friend@partner.example'}
        self.s.share(OWNER, 'question', qid, EDITOR, 'edit')
        self.s.share(OWNER, 'question', qid, MANAGER, 'manage')
        with self.assertRaisesRegex(AlertError, 'manage access'):
            self.alert(qid, user=EDITOR, channels=[self.email(outside)])
        with self.assertRaisesRegex(AlertError, 'allow-list'):
            self.alert(qid, channels=[self.email({
                'type': 'email', 'address': 'stranger@evil.example'})])
        # a domain entry and an exact address entry both admit
        alert_id = self.alert(qid, channels=[self.email(
            outside, {'type': 'email', 'address': 'Auditor@Elsewhere.example'}
        )])['alert_id']
        self.assertEqual(self.svc.get(OWNER, self.ep, alert_id)['status'],
                         'active')

    def test_external_delivery_is_rechecked_when_the_owner_loses_manage(self):
        qid = self.make_question()
        self.s.share(OWNER, 'question', qid, MANAGER, 'manage')
        outside = {'type': 'email', 'address': 'friend@partner.example'}
        alert_id = self.alert(qid, user=MANAGER,
                              channels=[self.email(outside)])['alert_id']
        self.regrade('question', qid, MANAGER, 'edit')
        self.a.run(alert_id)
        self.assertEqual(self.a.smtp.calls, [])
        delivery = json.loads(self.a.events(alert_id)[-1].deliveries)[0]
        self.assertEqual((delivery['state'], delivery['code']),
                         ('skipped', 'owner_lacks_manage'))

    def test_external_targets_are_not_stored_in_clear_in_history(self):
        qid = self.make_question()
        outside = {'type': 'email', 'address': 'friend@partner.example'}
        alert_id = self.alert(qid, channels=[self.email(outside)])['alert_id']
        self.a.run(alert_id)
        history = json.dumps(self.svc.history(OWNER, self.ep, alert_id))
        self.assertNotIn('friend@', history)
        self.assertIn('email:partner.example', history)

    def test_object_storage_needs_manage_and_a_matching_profile(self):
        qid = self.make_question()
        self.s.share(OWNER, 'question', qid, EDITOR, 'edit')
        archive = {'type': 's3', 'profile_id': 'archive',
                   'object_name': 'revenue'}
        with self.assertRaisesRegex(AlertError, 'manage access'):
            self.alert(qid, user=EDITOR, channels=[archive])
        with self.assertRaisesRegex(AlertError, 'does not match'):
            self.alert(qid, channels=[{**archive, 'profile_id': 'mail'}])
        with self.assertRaisesRegex(AlertError, 'unavailable'):
            self.alert(qid, channels=[{**archive, 'profile_id': 'ghost'}])
        alert_id = self.alert(qid, channels=[archive])['alert_id']
        self.a.run(alert_id)
        ((profile, target, payload),) = self.a.s3.calls
        self.assertTrue(target['object_name'].startswith('revenue-'))
        self.assertTrue(target['object_name'].endswith('.json'))
        self.assertEqual(json.loads(payload['content'])['alert']['name'],
                         'Revenue watch')

    def test_the_message_never_has_more_rows_than_the_cap(self):
        qid = self.make_question()
        for cap, shown in ((2, 2), (0, 0), (10 ** 6, 5)):
            with self.subTest(cap=cap):
                self.setUp()
                self.svc.config['max_message_rows'] = cap
                self.svc.channels  # the cap is read per message
                qid = self.make_question()
                alert_id = self.alert(qid, channels=[
                    {'type': 'in_app', 'recipients': [{'type': 'self'}]},
                    self.email({'type': 'self'}),
                    {'type': 'webhook', 'url': f'https://{HOOK_HOST}/in'},
                ])['alert_id']
                self.a.run(alert_id)
                note = json.loads(self.notes()[0].data)
                self.assertEqual(len(note['preview']['rows']), shown)
                mail = json.loads(self.a.smtp.calls[0][2]['content'])
                self.assertEqual(len(mail['preview']['rows']), shown)
                hook = json.loads(self.a.transport.posts[0]['body'])
                self.assertEqual(len(hook['preview']['rows']), shown)
                self.assertEqual(hook['preview']['row_count'], 5)
        # the hard ceiling holds even for a very large configured cap
        self.sql('INSERT INTO sales '
                 + ' UNION ALL '.join(
                     f"SELECT 'x','p',{i},1,''" for i in range(60)))
        big = question(name='Many')
        big['query']['builder']['limit'] = 100
        qid = self.s.q(OWNER, big)
        self.svc.config['max_message_rows'] = 10 ** 6
        alert_id = self.alert(qid, rows_over(1), name='many')['alert_id']
        self.a.run(alert_id)
        data = json.loads(self.notes()[-1].data)
        self.assertEqual(len(data['preview']['rows']), am.HARD_MESSAGE_ROWS)

    def test_webhook_needs_manage_and_an_allow_listed_host(self):
        qid = self.make_question()
        self.s.share(OWNER, 'question', qid, EDITOR, 'edit')
        hook = {'type': 'webhook', 'url': f'https://{HOOK_HOST}/in'}
        with self.assertRaisesRegex(AlertError, 'manage access'):
            self.alert(qid, user=EDITOR, channels=[hook])
        for url in ('https://evil.example.net/in', 'http://hooks.example.com/',
                    'https://127.0.0.1/in'):
            with self.subTest(url=url):
                with self.assertRaises(AlertError):
                    self.alert(qid, channels=[{'type': 'webhook',
                                               'url': url}])
        alert_id = self.alert(qid, channels=[hook])['alert_id']
        self.a.run(alert_id)
        (post,) = self.a.transport.posts
        body = json.loads(post['body'])
        self.assertEqual(body['schema'], 'cdeadmin.bi-alert.v1')
        self.assertEqual(body['alert']['name'], 'Revenue watch')
        expected = hmac.new(
            HOOK_SECRET.encode(),
            str(int(self.a.clock.now.timestamp())).encode() + b'.' +
            post['body'], hashlib.sha256).hexdigest()
        self.assertEqual(post['headers']['X-CDEadmin-Signature'],
                         f'v1={expected}')
        # the stored history carries no secret and no signature
        text = json.dumps(self.svc.history(OWNER, self.ep, alert_id))
        self.assertNotIn(HOOK_SECRET, text)
        self.assertNotIn(expected, text)

    def test_ssrf_refusals_at_send_time_are_recorded_not_raised(self):
        qid = self.make_question()
        hook = {'type': 'webhook', 'url': f'https://{HOOK_HOST}/in'}
        alert_id = self.alert(qid, channels=[hook],
                              fire_on='every_evaluation')['alert_id']
        cases = [
            ([ '10.0.0.5'], 'address_refused'),
            ([PUBLIC, '169.254.169.254'], 'address_refused'),
            (['::ffff:7f00:1'], 'address_refused'),
        ]
        for answer, code in cases:
            with self.subTest(answer=answer):
                self.a.resolver.answers[HOOK_HOST] = answer
                outcome = self.a.run(alert_id)
                self.assertEqual(outcome['state'], 'failed')
                last = self.a.events(alert_id)[-1]
                self.assertEqual(last.error_class, 'delivery_failed')
                delivery = json.loads(last.deliveries)[0]
                self.assertEqual((delivery['state'], delivery['code']),
                                 ('failed', code))
        self.assertEqual(self.a.transport.posts, [])

    def test_a_redirecting_receiver_leaves_an_unknown_outcome(self):
        qid = self.make_question()
        alert_id = self.alert(qid, channels=[{
            'type': 'webhook', 'url': f'https://{HOOK_HOST}/in'}])['alert_id']
        self.a.transport.status = 302
        outcome = self.a.run(alert_id)
        self.assertEqual(outcome['state'], 'outcome_unknown')
        self.assertEqual(len(self.a.transport.posts), 1)  # never followed
        delivery = json.loads(self.a.events(alert_id)[-1].deliveries)[0]
        self.assertEqual((delivery['state'], delivery['code']),
                         ('outcome_unknown', 'redirect_refused'))

    def test_delivery_is_at_most_once_per_fire(self):
        qid = self.make_question()
        alert_id = self.alert(qid, channels=[
            {'type': 'webhook', 'url': f'https://{HOOK_HOST}/in'}])[
            'alert_id']
        self.a.transport.status = 503
        self.a.run(alert_id)
        # state was saved before the delivery: a failed send is not retried
        self.a.run(alert_id)
        self.assertEqual(len(self.a.transport.posts), 1)
        self.assertEqual(self.state(alert_id)['breach_state'], 'breach')

    def state(self, alert_id):
        return self.svc.get(OWNER, self.ep, alert_id)

    def test_notifications_list_read_and_prune(self):
        qid = self.make_question()
        alert_id = self.alert(qid, fire_on='every_evaluation')['alert_id']
        for _ in range(3):
            self.a.run(alert_id)
        listing = self.svc.notifications(OWNER, self.ep)
        self.assertEqual(listing['unread'], 3)
        newest = listing['items'][0]
        self.assertEqual((newest['kind'], newest['alert_id']),
                         ('alert', alert_id))
        self.assertEqual(self.svc.mark_read(
            OWNER, self.ep, [newest['notification_id']])['unread'], 2)
        self.assertEqual(len(self.svc.notifications(
            OWNER, self.ep, unread_only=True)['items']), 2)
        # another user's notifications are out of reach
        self.assertEqual(self.svc.notifications(VIEWER, self.ep)['items'], [])
        self.assertEqual(self.svc.mark_read(VIEWER, self.ep)['marked'], 0)
        self.assertEqual(self.svc.mark_read(OWNER, self.ep)['unread'], 0)
        with self.assertRaises(AlertError):
            self.svc.mark_read(OWNER, self.ep, 'all')
        self.svc.channels.notify_keep = 2
        self.a.run(alert_id)
        self.assertEqual(len(self.notes()), 2)


class HistoryTests(AlertCase):
    SECRET_TABLE = 'zzz_secret_table'

    def test_failures_are_recorded_without_sql_or_native_text(self):
        qid = self.s.q(OWNER, sql_question(
            f'SELECT region FROM {self.SECRET_TABLE}'))
        alert_id = self.alert(qid, rows_over(1))['alert_id']
        self.assertEqual(self.a.run(alert_id)['state'], 'failed')
        event = self.a.events(alert_id)[0]
        self.assertEqual(event.error_class, 'execution_failed')
        self.assertEqual(event.error_message,
                         am.FAILURE_TEXT['execution_failed'])
        for viewer in (OWNER,):
            text = json.dumps(self.svc.history(viewer, self.ep, alert_id))
            self.assertNotIn(self.SECRET_TABLE, text)
            self.assertNotIn('SELECT', text)
        state = json.dumps(self.state(alert_id))
        self.assertNotIn('SELECT region FROM', state.replace(
            self.SECRET_TABLE, ''))

    def state(self, alert_id):
        return self.svc.get(OWNER, self.ep, alert_id)

    def test_error_detail_is_for_editors_only(self):
        qid = self.make_question()
        self.s.share(OWNER, 'question', qid, VIEWER, 'view')
        alert_id = self.alert(qid, column_metric('nope', 'sum', '>', 1),
                              user=VIEWER)['alert_id']
        self.a.run(alert_id)
        # the viewer owns the alert but only has view on the question
        (item,) = self.svc.history(VIEWER, self.ep, alert_id)
        self.assertEqual(item['error_class'], 'column_missing')
        self.assertEqual(item['error_text'],
                         am.FAILURE_TEXT['column_missing'])
        self.assertIsNone(item['error_detail'])
        self.regrade('question', qid, VIEWER, 'edit')
        (item,) = self.svc.history(VIEWER, self.ep, alert_id)
        self.assertEqual(item['error_detail'],
                         am.FAILURE_TEXT['column_missing'])

    def test_history_is_bounded_and_newest_first(self):
        qid = self.make_question()
        alert_id = self.alert(qid, fire_on='every_evaluation')['alert_id']
        self.svc.config['events_keep'] = 4
        for _ in range(7):
            self.a.clock.advance(minutes=1)
            self.a.run(alert_id)
        history = self.svc.history(OWNER, self.ep, alert_id, limit=100)
        self.assertEqual(len(history), 4)
        self.assertEqual(len(self.svc.history(OWNER, self.ep, alert_id,
                                              limit=2)), 2)

    def test_the_secret_sql_of_a_shared_raw_question_never_leaks(self):
        qid = self.s.q(OWNER, sql_question(
            "SELECT region, amount FROM sales WHERE product <> "
            "'zzz_hidden_filter'"))
        self.s.share(OWNER, 'question', qid, VIEWER, 'view')
        alert_id = self.alert(qid, rows_over(1), user=VIEWER)['alert_id']
        self.a.run(alert_id)
        every = json.dumps([
            self.svc.get(VIEWER, self.ep, alert_id),
            self.svc.history(VIEWER, self.ep, alert_id),
            self.svc.notifications(VIEWER, self.ep),
            self.svc.test(VIEWER, self.ep, runtime=self.a.runtime(VIEWER),
                          alert_id=alert_id)], default=str)
        self.assertNotIn('zzz_hidden_filter', every)


class SubscriptionTests(AlertCase):
    def test_question_snapshot_in_app(self):
        qid = self.make_question()
        sub = self.a.create(subscription_definition('question', qid))
        self.assertEqual(sub['kind'], 'subscription')
        outcome = self.a.run(sub['alert_id'])
        self.assertEqual(outcome['state'], 'delivered')
        (note,) = self.notes()
        data = json.loads(note.data)
        self.assertEqual(data['schema'], 'cdeadmin.bi-subscription.v1')
        self.assertEqual(data['items'][0]['row_count'], 5)
        # a subscription is not edge-triggered: every run delivers
        self.a.run(sub['alert_id'])
        self.assertEqual(len(self.notes()), 2)

    def test_exports_follow_the_result_policy(self):
        open_q = self.s.q(OWNER, question('Open', **export_policy('csv')))
        closed = self.make_question(name='Closed')
        mail = [{'type': 'email', 'profile_id': 'mail',
                 'recipients': [{'type': 'self'}]}]
        with self.assertRaisesRegex(AlertError, 'result policy'):
            self.a.create(subscription_definition(
                'question', closed, fmt='csv', channels=mail))
        with self.assertRaisesRegex(AlertError, 'result policy'):
            self.a.create(subscription_definition(
                'question', open_q, fmt='json', channels=mail, name='json'))
        both = self.s.q(OWNER, question('Both', **export_policy('csv',
                                                                 'pdf')))
        with self.assertRaisesRegex(AlertError, 'does not admit'):
            self.a.create(subscription_definition(
                'question', both, fmt='pdf', channels=mail, name='pdf'))
        sub = self.a.create(subscription_definition(
            'question', open_q, fmt='csv', channels=mail))
        self.a.run(sub['alert_id'])
        ((profile, target, payload),) = self.a.smtp.calls
        self.assertEqual(target['recipients'], ['owner@corp.example'])
        self.assertEqual(payload['media_type'] if 'media_type' in payload
                         else 'text/csv', 'text/csv')
        self.assertTrue(payload['content'].startswith(b'region,product'))
        self.assertTrue(payload['filename'].endswith('.csv'))

    def test_redacted_columns_stay_redacted_in_the_export(self):
        qid = self.s.q(OWNER, question('Masked', **export_policy(
            'csv', redact_columns=['product'])))
        sub = self.a.create(subscription_definition(
            'question', qid, fmt='csv', channels=[{
                'type': 'email', 'profile_id': 'mail',
                'recipients': [{'type': 'self'}]}]))
        self.a.run(sub['alert_id'])
        content = self.a.smtp.calls[0][2]['content'].decode()
        self.assertNotIn('pear', content)
        self.assertNotIn('apple', content)
        data = json.dumps(self.svc.history(OWNER, self.ep, sub['alert_id']))
        self.assertNotIn('pear', data)

    def test_dashboard_snapshot_exports_each_permitted_card(self):
        exportable = self.s.q(OWNER, question('Exportable',
                                              **export_policy('csv')))
        private = self.make_question(name='No export')
        did = self.s.dashboards.create(OWNER, self.ep, board(
            [exportable, private]))['dashboard_id']
        mail = [{'type': 'email', 'profile_id': 'mail',
                 'recipients': [{'type': 'self'}]}]
        sub = self.a.create(subscription_definition(
            'dashboard', did, fmt='csv', channels=mail))
        self.a.run(sub['alert_id'])
        self.assertEqual(len(self.a.smtp.calls), 1)   # one attachment
        event = self.a.events(sub['alert_id'])[-1]
        self.assertEqual(event.outcome, 'delivered')
        # a dashboard with nothing exportable fails clearly, sends nothing
        none = self.s.dashboards.create(OWNER, self.ep, board(
            [private], name='Plain'))['dashboard_id']
        with self.assertRaisesRegex(AlertError, 'result policy'):
            self.a.create(subscription_definition(
                'dashboard', none, fmt='csv', channels=mail, name='plain'))

    def test_dashboard_cards_the_owner_cannot_see_are_left_out(self):
        mine = self.s.q(OWNER, question('Mine', **export_policy('csv')))
        theirs = self.s.q(EDITOR, question('Theirs', **export_policy('csv')))
        self.s.share(EDITOR, 'question', theirs, OWNER, 'view')
        did = self.s.dashboards.create(OWNER, self.ep, board(
            [mine, theirs]))['dashboard_id']
        sub = self.a.create(subscription_definition('dashboard', did))
        self.revoke('question', theirs, OWNER, actor=EDITOR)
        self.a.run(sub['alert_id'])
        data = json.loads(self.notes()[0].data)
        self.assertEqual([(i['status'], i['code']) for i in data['items']],
                         [('ok', None), ('error', 'no_access')])
        self.assertNotIn('Theirs', json.dumps(data))

    def test_a_dashboard_with_no_usable_card_fails_instead_of_sending(self):
        theirs = self.s.q(EDITOR, question('Theirs'))
        self.s.share(EDITOR, 'question', theirs, OWNER, 'view')
        did = self.s.dashboards.create(OWNER, self.ep, board([theirs]))[
            'dashboard_id']
        sub = self.a.create(subscription_definition('dashboard', did))
        self.revoke('question', theirs, OWNER, actor=EDITOR)
        self.assertEqual(self.a.run(sub['alert_id'])['state'], 'failed')
        self.assertEqual(self.a.events(sub['alert_id'])[0].error_class,
                         'no_card_data')
        self.assertEqual(self.notes(), [])

    def test_dashboard_filters_and_pinned_revision(self):
        qid = self.s.q(OWNER, region_question())
        document = board([qid])
        document['filters'] = [{
            'id': 'region', 'name': 'Region', 'type': 'string',
            'widget': 'select', 'allowed_values': ['east', 'west'],
            'default': 'west',
            'targets': [{'card_id': 'c0', 'parameter_id': 'region'}]}]
        did = self.s.dashboards.create(OWNER, self.ep, document)[
            'dashboard_id']
        sub = self.a.create(subscription_definition(
            'dashboard', did, filters={'region': 'east'}))
        self.a.run(sub['alert_id'])
        item = json.loads(self.notes()[0].data)['items'][0]
        self.assertEqual(item['row_count'], 2)       # east has two rows

    def test_webhook_subscription_carries_signed_attachments(self):
        qid = self.s.q(OWNER, question('Open', **export_policy('csv')))
        sub = self.a.create(subscription_definition(
            'question', qid, fmt='csv', channels=[{
                'type': 'webhook', 'url': f'https://{HOOK_HOST}/digest'}]))
        self.a.run(sub['alert_id'])
        body = json.loads(self.a.transport.posts[0]['body'])
        (attachment,) = body['attachments']
        import base64
        content = base64.b64decode(attachment['content_base64'])
        self.assertEqual(hashlib.sha256(content).hexdigest(),
                         attachment['sha256'])
        self.assertTrue(content.startswith(b'region,product'))

    def test_subscription_recipients_are_authorized_like_alert_recipients(
            self):
        qid = self.make_question()
        mine = [{'type': 'in_app', 'recipients': [
            {'type': 'user', 'user_id': VIEWER}]}]
        with self.assertRaisesRegex(AlertError, 'view access'):
            self.a.create(subscription_definition(
                'question', qid, channels=mine))


class CatalogAndActionTests(AlertCase):
    def test_catalog_lists_channels_without_secrets(self):
        catalog = self.svc.catalog(OWNER)
        self.assertTrue(catalog['scheduling'])
        self.assertEqual([p['profile_id'] for p in catalog['channels'][
            'email']], ['mail'])
        self.assertEqual(catalog['channels']['webhook'],
                         [{'host': HOOK_HOST, 'label': HOOK_HOST}])
        text = json.dumps(catalog)
        for secret in (HOOK_SECRET, 'not-for-the-browser',
                       'private-external-id'):
            self.assertNotIn(secret, text)

    def test_schedule_preview(self):
        out = self.svc.schedule_preview(
            {'expression': '30 8 * * 1-5', 'timezone': 'America/Toronto'}, 3)
        self.assertEqual(out['next_runs'], [
            '2026-03-02T13:30:00+00:00', '2026-03-03T13:30:00+00:00',
            '2026-03-04T13:30:00+00:00'])
        for bad in (0, 21, True, 'x'):
            with self.assertRaises(AlertError):
                self.svc.schedule_preview({'expression': '0 * * * *'}, bad)

    def test_the_action_table_dispatches_every_name(self):
        qid = self.make_question()
        request = {'alert': alert_definition(qid, rows_over(3))}
        created = self.svc.handle(
            'bi_alert_create', request, user_id=OWNER, endpoint_id=self.ep,
            server=SimpleNamespace(user_id=OWNER),
            runtime=lambda: self.a.runtime())
        aid = created['alert_id']
        calls = {
            'bi_alert_catalog': {}, 'bi_alert_get': {'alert_id': aid},
            'bi_alert_list': {'resource_type': 'question',
                              'resource_id': qid},
            'bi_alert_test': {'alert_id': aid},
            'bi_alert_mute': {'alert_id': aid, 'duration_minutes': 5},
            'bi_alert_unmute': {'alert_id': aid},
            'bi_alert_rearm': {'alert_id': aid},
            'bi_alert_history': {'alert_id': aid},
            'bi_alert_run_now': {'alert_id': aid},
            'bi_alert_schedule_preview': {
                'schedule': {'expression': '0 * * * *'}},
            'bi_alert_pause': {'alert_id': aid},
            'bi_alert_resume': {'alert_id': aid},
            'bi_notification_list': {}, 'bi_notification_read': {},
            'bi_alert_update': {'alert_id': aid, 'expected_revision': 1,
                                'alert': alert_definition(
                                    qid, rows_over(4), name='x')},
            'bi_alert_delete': {'alert_id': aid},
        }
        seen = {'bi_alert_create'}
        for action, payload in calls.items():
            with self.subTest(action=action):
                self.svc.handle(
                    action, payload, user_id=OWNER, endpoint_id=self.ep,
                    server=SimpleNamespace(user_id=OWNER),
                    runtime=lambda: self.a.runtime())
                seen.add(action)
        self.assertEqual(seen, set(self.svc.ACTIONS))
        with self.assertRaisesRegex(AlertError, 'unavailable'):
            self.svc.handle('bi_alert_drop', {}, user_id=OWNER,
                            endpoint_id=self.ep)

    def test_malformed_ids_are_unavailable_not_errors(self):
        for value in (None, 5, {'a': 1}, ['x'], 'missing'):
            with self.assertRaisesRegex(AlertError, 'unavailable'):
                self.svc.get(OWNER, self.ep, value)


@unittest.skipIf(duckdb is None, 'duckdb is not installed')
class DuckDBTests(AlertCase):
    engine = 'duckdb'

    def test_threshold_change_and_subscription_on_duckdb(self):
        qid = self.s.q(OWNER, question('Duck', **export_policy('csv')))
        threshold = self.alert(qid, column_metric('amount', 'sum', '>', 100),
                               name='threshold')['alert_id']
        change = self.alert(qid, column_metric(
            'amount', 'sum', '>', 10, against='previous_percent'),
            name='change')['alert_id']
        self.a.run(threshold)
        self.a.run(change)
        self.sql("INSERT INTO sales VALUES ('n','a',50,1,'')")
        self.a.run(threshold)
        self.a.run(change)
        self.assertEqual(self.fired(threshold), [True, False])
        self.assertEqual(self.fired(change), [False, True])
        sub = self.a.create(subscription_definition(
            'question', qid, fmt='csv', channels=[{
                'type': 'email', 'profile_id': 'mail',
                'recipients': [{'type': 'self'}]}]))
        self.a.run(sub['alert_id'])
        self.assertTrue(self.a.smtp.calls[-1][2]['content'].startswith(
            b'region,product'))


# ---------------------------------------------------------------------------
@unittest.skipUnless(MIGRATION_DEPENDENCIES,
                     'SQLAlchemy and Alembic are required')
class MigrationTests(unittest.TestCase):
    @staticmethod
    def load(name):
        path = ROOT / f'web/migrations/versions/{name}_.py'
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_chain_constraints_and_round_trip(self):
        previous = self.load('cde_bi_permissions_v1')
        alerts = self.load('cde_bi_alerts_v1')
        self.assertEqual(alerts.down_revision, previous.revision)
        engine = sa.create_engine('sqlite:///:memory:')
        with engine.connect() as connection:
            metadata = sa.MetaData()
            sa.Table('user', metadata,
                     sa.Column('id', sa.Integer(), primary_key=True))
            sa.Table('cde_endpoint', metadata,
                     sa.Column('id', sa.String(36), primary_key=True))
            metadata.create_all(connection)
            alerts.op = Operations(MigrationContext.configure(connection))
            alerts.upgrade()
            names = set(sa.inspect(connection).get_table_names())
            tables = {'cde_bi_alert', 'cde_bi_alert_delegation',
                      'cde_bi_alert_credential', 'cde_bi_alert_occurrence',
                      'cde_bi_alert_event', 'cde_bi_notification'}
            self.assertTrue(tables <= names)
            connection.commit()
            connection.execute(sa.text('PRAGMA foreign_keys=ON'))
            connection.execute(sa.text('INSERT INTO user (id) VALUES (1)'))
            connection.execute(sa.text(
                "INSERT INTO cde_endpoint (id) VALUES ('ep')"))
            table = sa.Table('cde_bi_alert', sa.MetaData(),
                             autoload_with=connection)
            now = datetime.now(timezone.utc)
            base = dict(
                user_id=1, endpoint_id='ep', kind='alert', name='n',
                resource_type='question', resource_id='q',
                resource_revision=1, status='active',
                breach_state='unknown', pending_notify=False,
                consecutive_failures=0, schedule_anchor=now, revision=1,
                definition='{}', created_at=now, updated_at=now)
            connection.execute(table.insert().values(id='a', **base))
            bad = {
                'duplicate name': dict(id='b', **base),
                'kind': dict(id='c', **{**base, 'kind': 'digest',
                                        'name': 'k'}),
                'status': dict(id='d', **{**base, 'status': 'gone',
                                          'name': 'l'}),
                'breach state': dict(id='e', **{**base, 'breach_state': 'x',
                                                'name': 'm'}),
                'resource': dict(id='f', **{**base, 'resource_type': 'file',
                                            'name': 'o'}),
                'user': dict(id='g', **{**base, 'user_id': 9, 'name': 'p'}),
            }
            for label, values in bad.items():
                with self.subTest(label):
                    with self.assertRaises(sa.exc.IntegrityError):
                        connection.execute(table.insert().values(**values))
            connection.execute(sa.text('DELETE FROM user WHERE id = 1'))
            self.assertEqual(connection.execute(
                sa.select(sa.func.count()).select_from(table)).scalar(), 0)
            alerts.downgrade()
            self.assertFalse(tables & set(
                sa.inspect(connection).get_table_names()))
            alerts.upgrade()
            self.assertTrue(tables <= set(
                sa.inspect(connection).get_table_names()))

    def test_schema_version_is_not_bumped(self):
        source = (ROOT / 'web/pgadmin/model/__init__.py').read_text(
            encoding='utf-8')
        self.assertRegex(source, r'SCHEMA_VERSION\s*=\s*59\b')
        for table in ('cde_bi_alert', 'cde_bi_notification'):
            self.assertIn(f"'{table}'", source)


# ---------------------------------------------------------------------------
try:
    from flask import Flask
    import flask_sqlalchemy  # noqa: F401
    from test_cdeadmin_endpoint_persistence import load_model
    MODEL_DEPENDENCIES = MIGRATION_DEPENDENCIES
except ImportError:  # pragma: no cover
    MODEL_DEPENDENCIES = False

NOW = datetime(2026, 3, 2, 12, 30)


def bound(cls, **attrs):
    instance = cls.__new__(cls)
    instance.__dict__.update(attrs)
    return instance


class DatabaseCase(unittest.TestCase):
    """The real SQLAlchemy models over an on-disk SQLite configuration."""

    foreign_keys = False

    def setUp(self):
        from sqlalchemy import event
        from pgadmin.cdeadmin.bi.alert_store import DatabaseAlertRepository
        from pgadmin.cdeadmin.report_scheduler.service import (
            DatabaseReportSchedulerRepository,
        )
        self.temporary = tempfile.TemporaryDirectory()
        self.model = load_model()
        m = self.model
        self.app = Flask('cdeadmin-bi-alerts-test')
        self.app.config['SQLALCHEMY_DATABASE_URI'] = (
            f'sqlite:///{Path(self.temporary.name) / "config.db"}')
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        m.db.init_app(self.app)
        self.context = self.app.app_context()
        self.context.push()
        if self.foreign_keys:
            @event.listens_for(m.db.engine, 'connect')
            def pragma(connection, _record):
                connection.execute('PRAGMA foreign_keys=ON')
        m.db.create_all()
        for uid, name in ((1, 'owner'), (2, 'viewer')):
            m.db.session.execute(m.User.__table__.insert(), {
                'id': uid, 'username': name, 'active': True,
                'auth_source': f'internal{uid}', 'fs_uniquifier': f'u{uid}',
                'locked': False})
        m.db.session.add_all([m.ServerGroup(id=1, user_id=1, name='G')])
        m.db.session.commit()
        m.db.session.add(m.Server(
            id=10, user_id=1, servergroup_id=1, name='S', host='h', port=1,
            maintenance_db='d', username='u', save_password=0,
            use_ssh_tunnel=0, tunnel_authentication=0,
            tunnel_prompt_password=0, shared=False, kerberos_conn=False,
            cloud_status=0, is_adhoc=0))
        m.db.session.commit()
        self.ep = m.EndpointProfile.query.filter_by(
            legacy_server_id=10).one().id
        self.alerts = bound(DatabaseAlertRepository, db=m.db,
                            alert=m.BIAlert, event=m.BIAlertEvent,
                            notification=m.BINotification)
        self.schedule_repo = bound(
            DatabaseReportSchedulerRepository, db=m.db,
            credential=m.BIAlertCredential, delegation=m.BIAlertDelegation,
            occurrence=m.BIAlertOccurrence)

    def tearDown(self):
        self.model.db.session.remove()
        self.model.db.drop_all()
        for engine in self.model.db.engines.values():
            engine.dispose()
        self.context.pop()
        self.temporary.cleanup()

    def alert_row(self, endpoint_id=None, **values):
        import uuid
        base = dict(
            id=str(uuid.uuid4()), user_id=1,
            endpoint_id=endpoint_id or self.ep, kind='alert', name='A',
            resource_type='question', resource_id='q' * 8,
            resource_revision=1, status='active', breach_state='unknown',
            pending_notify=False, consecutive_failures=0,
            schedule_anchor=datetime(2026, 3, 2, 9, 0), revision=1,
            definition=json.dumps({'schedule': ah.EVERY_HOUR}),
            created_at=NOW, updated_at=NOW)
        base.update(values)
        return self.alerts.new(**base)

    def delegation(self, alert, name='d1', endpoint_id=None):
        row = self.model.BIAlertDelegation(
            id=name, alert_id=alert.id, user_id=alert.user_id,
            endpoint_id=endpoint_id or self.ep, route_id='r',
            endpoint_generation='g', state='active', credential_generation=1,
            created_at=NOW, updated_at=NOW,
            expires_at=NOW + timedelta(days=1))
        return row


@unittest.skipUnless(MODEL_DEPENDENCIES,
                     'Flask-SQLAlchemy and Alembic are required')
class AlertTableTests(DatabaseCase):
    foreign_keys = True

    def test_repository_round_trip(self):
        repo = self.alerts
        row = repo.add(self.alert_row())
        with self.assertRaisesRegex(BIError, 'already exists'):
            repo.add(self.alert_row())
        self.assertIsNone(repo.get(5))
        self.assertIsNone(repo.get('missing'))
        self.assertEqual(repo.count(1, self.ep), 1)
        repo.add(self.alert_row(name='B', resource_id='z' * 8))
        self.assertEqual([r.name for r in repo.list(self.ep)], ['A', 'B'])
        self.assertEqual([r.name for r in repo.list(
            self.ep, resource_type='question', resource_id='z' * 8)], ['B'])
        self.assertEqual(repo.list(self.ep, user_id=2), [])
        repo.update_state(row.id, status='paused',
                          pause_reason='user_paused', muted_until=NOW)
        fresh = repo.get(row.id)
        self.assertEqual((fresh.status, fresh.pause_reason, fresh.muted_until),
                         ('paused', 'user_paused', NOW))

    def test_constraints_reject_bad_states(self):
        for values in ({'status': 'gone'}, {'breach_state': 'x'},
                       {'kind': 'digest'}, {'resource_type': 'file'}):
            with self.subTest(values=values):
                with self.assertRaises(Exception):
                    self.alerts.add(self.alert_row(name=str(values),
                                                   **values))
                self.model.db.session.rollback()

    def test_events_and_notifications(self):
        repo = self.alerts
        row = repo.add(self.alert_row())
        for index in range(5):
            repo.add_event(
                alert_id=row.id, trigger='schedule', outcome='breach',
                fired=index % 2 == 0, resource_revision=1,
                value='{"value":1}', deliveries='[]',
                created_at=NOW + timedelta(minutes=index))
        newest = repo.events(row.id, 3)
        self.assertEqual([e.created_at for e in newest],
                         [NOW + timedelta(minutes=i) for i in (4, 3, 2)])
        self.assertEqual(repo.prune_events(row.id, 2), 3)
        self.assertEqual(len(repo.events(row.id, 50)), 2)
        for user in (1, 1, 2):
            repo.add_notification(
                user_id=user, endpoint_id=self.ep, alert_id=row.id,
                kind='alert', resource_type='question', resource_id='q',
                title='t', body='b', data='{}', created_at=NOW,
                read_at=None)
        self.assertEqual(repo.unread_count(1, self.ep), 2)
        (first, _second) = repo.notifications(1, self.ep)
        self.assertEqual(repo.mark_read(1, self.ep, [first.id], NOW), 1)
        self.assertEqual(repo.unread_count(1, self.ep), 1)
        self.assertEqual(repo.unread_count(2, self.ep), 1)
        self.assertEqual(repo.mark_read(2, self.ep, None, NOW), 1)
        self.assertEqual(repo.prune_notifications(1, self.ep, 1), 1)

    def test_delete_cascades_but_keeps_notifications(self):
        m = self.model
        row = self.alerts.add(self.alert_row())
        self.alerts.add_event(
            alert_id=row.id, trigger='schedule', outcome='ok', fired=False,
            deliveries='[]', created_at=NOW)
        self.schedule_repo.save_grant(self.delegation(row), [{
            'id': 'c1', 'delegation_id': 'd1', 'secret_kind': 'password',
            'key_id': 'k', 'encrypted_value': 'x', 'created_at': NOW}])
        self.schedule_repo.enqueue('d1', NOW)
        self.alerts.add_notification(
            user_id=1, endpoint_id=self.ep, alert_id=row.id, kind='alert',
            resource_type='question', resource_id='q', title='t', body='b',
            data='{}', created_at=NOW, read_at=None)
        self.alerts.delete(self.alerts.get(row.id))
        for model in (m.BIAlertEvent, m.BIAlertDelegation,
                      m.BIAlertCredential, m.BIAlertOccurrence):
            self.assertEqual(model.query.count(), 0, model.__name__)
        (note,) = m.BINotification.query.all()
        self.assertIsNone(note.alert_id)

    def test_deleting_a_user_removes_their_alerts_and_notifications(self):
        m = self.model
        self.alerts.add(self.alert_row(user_id=2, name='theirs'))
        self.alerts.add_notification(
            user_id=2, endpoint_id=self.ep, alert_id=None, kind='alert',
            resource_type='question', resource_id='q', title='t', body='b',
            data='{}', created_at=NOW, read_at=None)
        m.db.session.execute(m.User.__table__.delete().where(
            m.User.id == 2))
        m.db.session.commit()
        self.assertEqual(m.BIAlert.query.count(), 0)
        self.assertEqual(m.BINotification.query.count(), 0)

    def test_one_instant_is_one_occurrence_and_claims_are_exclusive(self):
        row = self.alerts.add(self.alert_row())
        self.schedule_repo.save_grant(self.delegation(row), [])
        first, created = self.schedule_repo.enqueue('d1', NOW)
        again, created_again = self.schedule_repo.enqueue('d1', NOW)
        self.assertEqual((created, created_again, again.id),
                         (True, False, first.id))
        from unittest import mock
        import pgadmin.cdeadmin.report_scheduler.service as service_module
        with mock.patch.object(service_module, '_now', lambda: NOW):
            claimed = self.schedule_repo.claim('w1', 300, first.id)
            self.assertIsNotNone(claimed)
            self.assertIsNone(self.schedule_repo.claim('w2', 300, first.id))
            occurrence, _token = claimed
            self.assertEqual((occurrence.state, occurrence.claimed_by),
                             ('claimed', 'w1'))
            with self.assertRaises(ReportSchedulerConflict):
                self.schedule_repo.transition(
                    first.id, 'wrong-token', 'executing', 'x')


def real_scheduler(stack, repository, model):
    """``BIAlertScheduler`` on the real tables with the stack's runtime."""
    from pgadmin.cdeadmin.bi.alert_scheduler import BIAlertScheduler

    class Scheduler(BIAlertScheduler):
        def __init__(self):
            self.repository = repository
            self.lease_seconds = 300
            self.max_lateness_seconds = 3600
            self.key_ring = SimpleNamespace(available=True)
            self.on_expired = None

        def authorize_alert(self, server, alert, expires_in_days):
            if server.user_id != alert.user_id:
                raise ReportSchedulerAccessError('owner only')
            now = stack.clock.naive()
            row = model.BIAlertDelegation(
                id=f'del-{alert.id[:8]}', alert_id=alert.id,
                user_id=alert.user_id, endpoint_id=alert.endpoint_id,
                route_id='route', endpoint_generation='gen',
                state='active', credential_generation=1, created_at=now,
                updated_at=now,
                expires_at=now + timedelta(days=expires_in_days))
            return repository.save_grant(row, [])

        def runtime(self, delegation):
            if delegation.state != 'active' or (
                    delegation.expires_at <= stack.clock.naive()):
                raise ReportSchedulerAccessError('inactive')
            return (stack.s.provider, stack.s.ctx,
                    stack.s.endpoint_for(delegation.user_id))

    return Scheduler()


@unittest.skipUnless(MODEL_DEPENDENCIES,
                     'Flask-SQLAlchemy and Alembic are required')
class WorkerEndToEndTests(DatabaseCase):
    """The real worker, leases and tables around the live BI stack."""

    def setUp(self):
        super().setUp()
        from unittest import mock
        from pgadmin.cdeadmin.bi.alert_scheduler import BIAlertWorker
        import pgadmin.cdeadmin.bi.alert_scheduler as scheduler_module
        import pgadmin.cdeadmin.report_scheduler.service as service_module
        self.stack = AlertStack('sqlite')
        stack, self.s, self.svc = self.stack, self.stack.s, self.stack.service
        self.endpoint = stack.ep
        self.svc.repository = self.alerts
        self.svc.channels.repository = self.alerts
        self.scheduler = real_scheduler(stack, self.schedule_repo,
                                        self.model)
        self.worker = BIAlertWorker(self.scheduler, self.svc)
        self.svc.scheduler, self.svc.worker = self.scheduler, self.worker
        self.scheduler.on_expired = lambda a: self.svc._pause(
            a, 'delegation_expired', revoke=False)
        for module in (service_module, scheduler_module):
            patch = mock.patch.object(module, '_now', stack.clock.naive)
            patch.start()
            self.addCleanup(patch.stop)
        self.qid = self.s.q(OWNER, question())

    def create(self, **kwargs):
        return self.svc.create(
            OWNER, self.endpoint, alert_definition(
                self.qid, rows_over(3), **kwargs),
            SimpleNamespace(user_id=OWNER))

    def occurrences(self):
        return self.model.BIAlertOccurrence.query.order_by(
            self.model.BIAlertOccurrence.scheduled_for).all()

    def test_schedule_lease_and_delivery_on_real_tables(self):
        alert_id = self.create()['alert_id']
        self.stack.clock.advance(minutes=65)            # 10:05
        summary = self.worker.run_once('w1', 5)
        self.assertEqual((summary['enqueued']['scheduled'],
                          summary['claimed'], summary['delivered']),
                         (1, 1, 1))
        (done,) = self.occurrences()
        self.assertEqual((done.state, done.phase, done.claimed_by),
                         ('delivered', 'complete', 'w1'))
        self.assertEqual(done.scheduled_for, datetime(2026, 3, 2, 10, 0))
        self.assertTrue(json.loads(done.delivery_occurrence_ids))
        (note,) = self.model.BINotification.query.all()
        self.assertEqual((note.user_id, note.alert_id, note.kind),
                         (OWNER, alert_id, 'alert'))
        # nothing new is due: a second cycle is a no-op
        again = self.worker.run_once('w1', 5)
        self.assertEqual((again['claimed'], again['enqueued']['scheduled']),
                         (0, 0))
        # the next hour: still in breach, evaluated, not announced twice
        self.stack.clock.advance(hours=1)
        self.worker.run_once('w1', 5)
        self.assertEqual(len(self.occurrences()), 2)
        self.assertEqual(self.model.BINotification.query.count(), 1)
        events = self.alerts.events(alert_id, 10)
        self.assertEqual([e.fired for e in reversed(events)], [True, False])

    def test_missed_instants_are_recorded_not_replayed(self):
        self.create()
        self.stack.clock.advance(hours=3, minutes=30)   # 12:30
        summary = self.worker.run_once('w1', 10)
        self.assertEqual(summary['enqueued'], {
            'scheduled': 1, 'missed': 2, 'expired': 0})
        states = [(o.scheduled_for.hour, o.state, o.error_type)
                  for o in self.occurrences()]
        self.assertEqual(states, [(10, 'failed', 'SchedulerMisfire'),
                                  (11, 'failed', 'SchedulerMisfire'),
                                  (12, 'delivered', None)])

    def test_paused_alerts_get_no_occurrences_and_delete_cascades(self):
        alert_id = self.create()['alert_id']
        self.svc.pause(OWNER, self.endpoint, alert_id)
        self.stack.clock.advance(hours=2)
        summary = self.worker.run_once('w1', 5)
        self.assertEqual(summary['claimed'], 0)
        self.assertEqual(self.occurrences(), [])
        self.svc.delete(OWNER, self.endpoint, alert_id)
        self.assertEqual(self.model.BIAlertDelegation.query.count(), 0)

    def test_access_loss_during_a_scheduled_run_pauses_for_real(self):
        self.s.share(OWNER, 'question', self.qid, VIEWER, 'view')
        alert_id = self.svc.create(
            VIEWER, self.endpoint, alert_definition(self.qid, rows_over(3)),
            SimpleNamespace(user_id=VIEWER))['alert_id']
        self.s.bi.access.remove_grant(
            OWNER, 'question', self.endpoint, self.qid,
            self.s.bi.access.grants.find(
                self.endpoint, 'question', self.qid, 'user', VIEWER)[
                'grant_id'])
        self.stack.clock.advance(minutes=65)
        summary = self.worker.run_once('w1', 5)
        self.assertEqual(summary.get('cancelled'), 1)
        row = self.alerts.get(alert_id)
        self.assertEqual((row.status, row.pause_reason),
                         ('paused', 'resource_unavailable'))
        delegation = self.model.BIAlertDelegation.query.one()
        self.assertEqual(delegation.state, 'revoked')
        (done,) = self.occurrences()
        self.assertEqual((done.state, done.error_type),
                         ('cancelled', 'resource_unavailable'))
        self.assertEqual(self.model.BINotification.query.count(), 0)

    def test_an_expired_delegation_pauses_the_alert_through_enqueue(self):
        alert_id = self.create(expires_in_days=1)['alert_id']
        self.stack.clock.advance(days=2)
        summary = self.worker.run_once('w1', 5)
        self.assertEqual(summary['enqueued']['expired'], 1)
        row = self.alerts.get(alert_id)
        self.assertEqual((row.status, row.pause_reason),
                         ('paused', 'delegation_expired'))

    def test_a_crashed_worker_is_recovered_without_a_replay(self):
        self.create()
        self.stack.clock.advance(minutes=65)
        self.scheduler.enqueue_due()
        claimed = self.scheduler.claim('crashed')
        self.assertIsNotNone(claimed)
        self.stack.clock.advance(minutes=10)            # past the lease
        summary = self.worker.run_once('w2', 5)
        self.assertEqual(summary['recovered'], 1)
        (row,) = self.occurrences()
        self.assertEqual((row.state, row.phase),
                         ('failed', 'lease-expired'))
        self.assertEqual(self.model.BINotification.query.count(), 0)

    def test_run_now_uses_the_same_claim_and_lease_path(self):
        alert_id = self.create()['alert_id']
        result = self.svc.run_now(OWNER, self.endpoint, alert_id)
        self.assertEqual(result['state'], 'delivered')
        (done,) = self.occurrences()
        self.assertEqual((done.state, done.claimed_by),
                         ('delivered', f'run-now:{OWNER}'))
        self.assertEqual(result['event']['trigger'], 'run_now')

    def test_history_from_the_real_rows_carries_no_secrets(self):
        alert_id = self.create(channels=[{
            'type': 'webhook', 'url': f'https://{HOOK_HOST}/in'}])[
            'alert_id']
        self.stack.clock.advance(minutes=65)
        self.worker.run_once('w1', 5)
        text = json.dumps(self.svc.history(OWNER, self.endpoint, alert_id))
        self.assertNotIn(HOOK_SECRET, text)
        self.assertIn('webhook:hooks.example.com', text)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
