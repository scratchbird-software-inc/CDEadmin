##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Signed BI embedding (docs/en_US/bi_embedding.rst).

Token rules in isolation, then the real unauthenticated blueprint over the
real services and SQLite / DuckDB: the forging matrix, parameter locking,
claim-driven row policies and cache separation, rate limiting, response
headers, raw SQL refusal, the owner losing access, secret hygiene, the
management actions and the real tables / migration.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import bi_embed_harness as eh
from bi_embed_harness import (
    EmbedStack, NOT_FOUND, ORIGINS, OWNER, rows_of,
)
from bi_live_harness import ROOT, duckdb
from bi_permissions_harness import (
    EDITOR, MANAGER, STRANGER, VIEWER, board,
)
from test_cdeadmin_bi_dashboards import card, detail_by_region
from test_cdeadmin_bi_execution import region_question, sql_question

from pgadmin.cdeadmin.bi import BIError
from pgadmin.cdeadmin.bi import embed_tokens as tk
from pgadmin.cdeadmin.bi.embed_tokens import EmbedTokenError
from pgadmin.cdeadmin.bi.embeds import TokenBuckets

try:
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    MIGRATION_DEPENDENCIES = True
except ImportError:  # pragma: no cover
    MIGRATION_DEPENDENCIES = False

ENGINES = ['sqlite'] + (['duckdb'] if duckdb is not None else [])
SECRET = 'S' * 43
EMBED = 'e7f1c2a4-0000-4000-8000-000000000001'
NOW = 1_800_000_000


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
def tenant_model():
    return {
        'name': 'Tenant sales', 'sources': [{
            'id': 'sales', 'resource_id': 'table:sales',
            'relation': ['sales'], 'alias': 'sales'}],
        'dimensions': [{'id': 'region', 'name': 'Region',
                        'field': {'source_id': 'sales', 'field': 'region'}}],
        'measures': [{'id': 'revenue', 'name': 'Revenue',
                      'aggregation': 'sum',
                      'field': {'source_id': 'sales', 'field': 'amount'}}],
        'security': {'tenant_filter': {
            'field': {'source_id': 'sales', 'field': 'qty'},
            'principal_claim': 'tenant_id', 'required': True}},
    }


def tenant_question(stack, user=OWNER):
    created = stack.s.bi.semantic.create(user, stack.ep, tenant_model())
    return stack.s.q(user, {
        'name': 'Tenant cube',
        'semantic_model': {'id': created['model_id'], 'revision': 1},
        'query': {'kind': 'semantic', 'builder': {
            'group_by': ['region'],
            'aggregations': [{'measure_id': 'revenue'}],
            'order_by': [{'id': 'revenue', 'direction': 'desc'}],
            'limit': 10}}})


def sales_board(stack, user=OWNER, **extra):
    """A dashboard with a region filter, two question cards and drills."""
    stack.boards = getattr(stack, 'boards', 0) + 1
    tag = '' if stack.boards == 1 else f' {stack.boards}'
    by_region = stack.s.q(user, dict(region_question(),
                                     name='Sales by region' + tag))
    detail = stack.s.q(user, dict(detail_by_region(), name='Detail' + tag))
    other = stack.s.q(user, dict(detail_by_region(),
                                 name='Elsewhere' + tag))
    document = {
        'name': 'Sales board' + tag,
        'tabs': [{'id': 'main', 'name': 'Main'}],
        'cards': [card('by_region', by_region, x=0),
                  card('detail', detail, x=12)],
        'filters': [{
            'id': 'region', 'name': 'Region', 'type': 'string',
            'widget': 'select', 'allowed_values': ['east', 'west'],
            'targets': [
                {'card_id': 'by_region', 'parameter_id': 'region'},
                {'card_id': 'detail', 'field': {'column': 'region'}}]}],
        'drill_throughs': [
            {'id': 'to_region', 'source_card_id': 'detail',
             'trigger': {'column': 'region'},
             'target': {'kind': 'question', 'question_id': by_region,
                        'revision': 1, 'parameter_mappings': [
                            {'parameter_id': 'region',
                             'from': {'column': 'region'}}]}},
            {'id': 'to_other', 'source_card_id': 'detail',
             'trigger': {'column': 'product'},
             'target': {'kind': 'question', 'question_id': other,
                        'revision': 1, 'parameter_mappings': []}}],
    }
    document.update(extra)
    made = stack.s.dashboards.create(user, stack.ep, document)
    return made['dashboard_id'], SimpleNamespace(
        by_region=by_region, detail=detail, other=other)


def regions(response):
    return sorted({row['region'] for row in rows_of(response)})


def denied(test, response):
    test.assertEqual(response.status_code, 404)
    test.assertEqual(response.data, NOT_FOUND)


def forge(secret, kid, header=None, payload=None, signature=None):
    """A token assembled by hand, signed unless ``signature`` is given."""
    header = {'alg': 'HS256', 'typ': 'JWT', 'kid': kid, **(header or {})}
    head = tk.b64u_encode(json.dumps(header).encode())
    body = tk.b64u_encode(json.dumps(payload or {}).encode())
    signing = f'{head}.{body}'.encode()
    if signature is None:
        signature = tk.b64u_encode(
            hmac.new(secret.encode(), signing, hashlib.sha256).digest())
    return f'{head}.{body}.{signature}'


class Base(unittest.TestCase):
    engine = 'sqlite'
    config = None

    def setUp(self):
        self.st = EmbedStack(self.engine, config=self.config)

    def dashboard(self, **extra):
        did, parts = sales_board(self.st)
        return did, parts

    def make(self, kind, rid, **extra):
        return self.st.create(kind, rid, **extra)

    def board_embed(self, parameters=None, **extra):
        did, parts = self.dashboard()
        embed, secret = self.make(
            'dashboard', did,
            parameters=parameters if parameters is not None else
            [{'id': 'region', 'mode': 'locked'}], **extra)
        self.did, self.parts = did, parts
        return embed, secret

    def token(self, embed, secret, **kwargs):
        return self.st.token(embed['embed_id'], secret, **kwargs)

    def card(self, embed, token, card_id='detail', body=None):
        return self.st.post(embed['embed_id'], f'/cards/{card_id}/run',
                            token, body)


# ---------------------------------------------------------------------------
# tokens in isolation
# ---------------------------------------------------------------------------
class TokenTests(unittest.TestCase):
    def payload(self, **extra):
        return {'aud': EMBED, 'iat': NOW, 'exp': NOW + 300, **extra}

    def check(self, payload, **kwargs):
        options = dict(embed_id=EMBED, now=NOW, max_lifetime=600, leeway=15)
        options.update(kwargs)
        return tk.check_claims(payload, **options)

    def code(self, call):
        with self.assertRaises(EmbedTokenError) as caught:
            call()
        return caught.exception.code

    def test_round_trip(self):
        token = tk.sign(SECRET, 'kid00001', self.payload(params={'a': 1}))
        parsed = tk.parse(token)
        self.assertEqual(parsed.header, {'alg': 'HS256', 'typ': 'JWT',
                                         'kid': 'kid00001'})
        self.assertTrue(tk.verify_signature(parsed, {'kid00001': SECRET}))
        self.assertFalse(tk.verify_signature(parsed, {'kid00001': 'x' * 43}))
        self.assertEqual(parsed.payload['params'], {'a': 1})

    def test_weak_secret_is_refused(self):
        self.assertEqual(self.code(lambda: tk.sign('short', 'kid00001', {})),
                         'weak_secret')

    def test_algorithm_is_pinned(self):
        for alg in ('none', 'None', 'NONE', 'hs256', 'HS384', 'HS512',
                    'RS256', 'ES256', 'EdDSA', '', None, ['HS256']):
            with self.subTest(alg=alg):
                token = forge(SECRET, 'kid00001', {'alg': alg}, self.payload())
                self.assertEqual(self.code(lambda: tk.parse(token)),
                                 'algorithm')
        no_alg = forge(SECRET, 'kid00001', None, self.payload())
        head = json.dumps({'typ': 'JWT', 'kid': 'kid00001'}).encode()
        broken = tk.b64u_encode(head) + '.' + no_alg.split('.', 1)[1]
        self.assertEqual(self.code(lambda: tk.parse(broken)), 'algorithm')

    def test_unexpected_header_members_are_refused(self):
        for extra in ({'jku': 'https://evil.example/keys'},
                      {'jwk': {'kty': 'oct'}}, {'crit': ['exp']},
                      {'x5u': 'https://evil.example'}, {'cty': 'JWT'},
                      {'zip': 'DEF'}):
            with self.subTest(extra=extra):
                token = forge(SECRET, 'kid00001', extra, self.payload())
                self.assertEqual(self.code(lambda: tk.parse(token)),
                                 'algorithm')
        token = forge(SECRET, 'kid00001', {'typ': 'JWE'}, self.payload())
        self.assertEqual(self.code(lambda: tk.parse(token)), 'algorithm')

    def test_kid_syntax(self):
        for kid in ('', 'a', 'a b c d', '../../etc', 'x' * 33, 7, None):
            with self.subTest(kid=kid):
                token = forge(SECRET, kid, {'kid': kid}, self.payload())
                self.assertEqual(self.code(lambda: tk.parse(token)),
                                 'bad_kid')

    def test_strict_encoding(self):
        good = tk.sign(SECRET, 'kid00001', self.payload())
        head, body, sig = good.split('.')
        bad = {
            'two parts': f'{head}.{body}',
            'four parts': good + '.x',
            'padding': f'{head}=.{body}.{sig}',
            'standard alphabet': f'{head}.{body.replace("-", "+")}+.{sig}',
            'empty body': f'{head}..{sig}',
            'short signature': f'{head}.{body}.{sig[:-4]}',
            'whitespace': f' {good}',
            'non ascii': good + 'é',
            'empty': '',
            'oversize': 'a.' * 3000,
        }
        for label, token in bad.items():
            with self.subTest(label):
                self.assertEqual(self.code(lambda: tk.parse(token)),
                                 'malformed')
        for token in (None, 7, b'x', ['a'], {}):
            with self.subTest(type=type(token).__name__):
                self.assertEqual(self.code(lambda: tk.parse(token)),
                                 'malformed')

    def test_non_canonical_base64_is_refused(self):
        # the last character of an unpadded 32 byte signature carries only
        # four significant bits; another character decodes to the same bytes
        good = tk.sign(SECRET, 'kid00001', self.payload())
        head, body, sig = good.split('.')
        alphabet = ('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
                    '0123456789-_')
        index = alphabet.index(sig[-1])
        twin = alphabet[index ^ 1]
        self.assertEqual(base64.urlsafe_b64decode(sig + '='),
                         base64.urlsafe_b64decode(sig[:-1] + twin + '='))
        self.assertEqual(
            self.code(lambda: tk.parse(f'{head}.{body}.{sig[:-1]}{twin}')),
            'malformed')

    def test_strict_json(self):
        def token(raw_payload):
            head = tk.b64u_encode(json.dumps(
                {'alg': 'HS256', 'kid': 'kid00001'}).encode())
            body = tk.b64u_encode(raw_payload)
            mac = hmac.new(SECRET.encode(), f'{head}.{body}'.encode(),
                           hashlib.sha256).digest()
            return f'{head}.{body}.{tk.b64u_encode(mac)}'
        for label, raw in {
                'duplicate member': b'{"exp":1,"exp":2}',
                'nan': b'{"exp":NaN}', 'infinity': b'{"exp":Infinity}',
                'array': b'[1]', 'scalar': b'7', 'not json': b'{',
                'not utf-8': b'{"a":"\xff"}'}.items():
            with self.subTest(label):
                self.assertEqual(self.code(lambda: tk.parse(token(raw))),
                                 'malformed')

    def test_constant_time_compare_is_used_on_every_path(self):
        token = tk.sign(SECRET, 'kid00001', self.payload())
        parsed = tk.parse(token)
        with mock.patch.object(tk.hmac, 'compare_digest',
                               wraps=hmac.compare_digest) as spy:
            tk.verify_signature(parsed, {'kid00001': SECRET})
            tk.verify_signature(parsed, {'kid00001': 'y' * 43})
            tk.verify_signature(parsed, {'other001': SECRET})
            tk.verify_signature(parsed, {})
            tk.verify_signature(parsed, {'kid00001': 'short'})
        self.assertEqual(spy.call_count, 5)

    def test_unknown_key_never_verifies_even_with_the_dummy_key(self):
        dummy = tk.sign('\x00' * 32, 'kid00001', self.payload())
        self.assertFalse(tk.verify_signature(tk.parse(dummy), {}))

    def test_claims_happy_path(self):
        checked = self.check(self.payload(
            nbf=NOW, jti='one-time-0001', params={'region': 'east'},
            claims={'tenant_id': 3, 'groups': ['a', 'b']}))
        self.assertEqual(checked['params'], {'region': 'east'})
        self.assertEqual(checked['claims']['tenant_id'], 3)
        self.assertEqual(checked['jti'], 'one-time-0001')
        self.assertFalse(checked['prv'])

    def test_expiry_rules(self):
        cases = {
            'no_expiry': {'aud': EMBED},
            'expired': self.payload(exp=NOW),
            'bad_expiry': self.payload(exp='9999999999'),
            'bad_expiry ': self.payload(exp=True),
            'lifetime': self.payload(exp=NOW + 601),
        }
        for code, payload in cases.items():
            with self.subTest(code):
                self.assertEqual(self.code(lambda: self.check(payload)),
                                 code.strip())
        # exp has no leeway; the remaining lifetime is what is capped
        self.assertEqual(self.code(lambda: self.check(
            self.payload(exp=NOW - 1))), 'expired')
        self.check(self.payload(iat=NOW - 5000, exp=NOW + 100, nbf=NOW - 100),
                   max_lifetime=6000)
        self.assertEqual(self.code(lambda: self.check(
            self.payload(iat=NOW - 5000, exp=NOW + 100))), 'lifetime')

    def test_not_before_and_issued_at(self):
        self.check(self.payload(nbf=NOW + 15))
        self.assertEqual(self.code(lambda: self.check(
            self.payload(nbf=NOW + 16))), 'not_yet_valid')
        self.assertEqual(self.code(lambda: self.check(
            self.payload(nbf=NOW + 400, exp=NOW + 300))), 'bad_nbf')
        self.assertEqual(self.code(lambda: self.check(
            self.payload(iat=NOW + 16))), 'bad_iat')
        self.assertEqual(self.code(lambda: self.check(
            self.payload(iat=NOW + 300, exp=NOW + 300))), 'bad_iat')

    def test_audience_is_the_embed_id(self):
        for aud in ('someone-else', None, 7, [EMBED], EMBED.upper(), ''):
            with self.subTest(aud=aud):
                payload = self.payload()
                payload['aud'] = aud
                self.assertEqual(self.code(lambda: self.check(payload)),
                                 'audience')
        payload = self.payload()
        del payload['aud']
        self.assertEqual(self.code(lambda: self.check(payload)), 'audience')

    def test_unknown_and_reserved_members(self):
        self.assertEqual(self.code(lambda: self.check(
            self.payload(admin=True))), 'unknown_member')
        for name in sorted(tk.RESERVED_CLAIMS):
            with self.subTest(name):
                self.assertEqual(self.code(lambda: self.check(
                    self.payload(claims={name: 1}))), 'reserved_claim')

    def test_claim_and_parameter_value_types(self):
        bad = {
            'bad_claims': [self.payload(claims={'x': 1.5}),
                           self.payload(claims={'x': None}),
                           self.payload(claims={'x': {'a': 1}}),
                           self.payload(claims={'x': [1.5]}),
                           self.payload(claims={'x': 'a' * 257}),
                           self.payload(claims=[1]),
                           self.payload(claims={'bad name': 1}),
                           self.payload(claims={'x': list(range(101))})],
            'bad_params': [self.payload(params={'x': {'a': 1}}),
                           self.payload(params=[1]),
                           self.payload(params={'x': 'a' * 1025}),
                           self.payload(params={'1 2': 1})],
            'bad_jti': [self.payload(jti='short'),
                        self.payload(jti=7), self.payload(jti='a b c d e f g')],
            'bad_prv': [self.payload(prv='yes')],
            'bad_iss': [self.payload(iss=7)],
        }
        for code, payloads in bad.items():
            for payload in payloads:
                with self.subTest(code, payload=payload):
                    self.assertEqual(self.code(lambda: self.check(payload)),
                                     code)

    def test_policy_denies_undeclared_and_missing(self):
        checked = self.check(self.payload(params={'a': 1}, claims={'t': 1}))
        tk.apply_policy(checked, parameters={'a': 'locked'},
                        claims={'t': True})
        self.assertEqual(self.code(lambda: tk.apply_policy(
            checked, parameters={}, claims={'t': True})), 'undeclared_param')
        self.assertEqual(self.code(lambda: tk.apply_policy(
            checked, parameters={'a': 'locked'}, claims={})),
            'undeclared_claim')
        bare = self.check(self.payload())
        self.assertEqual(self.code(lambda: tk.apply_policy(
            bare, parameters={}, claims={'t': True})), 'missing_claim')
        tk.apply_policy(bare, parameters={}, claims={'t': False})

    def test_claims_digest_is_stable_and_distinguishing(self):
        self.assertEqual(tk.claims_digest({'a': 1, 'b': 2}),
                         tk.claims_digest({'b': 2, 'a': 1}))
        self.assertNotEqual(tk.claims_digest({'a': 1}),
                            tk.claims_digest({'a': '1'}))
        self.assertNotEqual(tk.claims_digest({'a': 1}), tk.claims_digest({}))


class BucketTests(unittest.TestCase):
    def test_burst_refill_and_bound(self):
        now = [0.0]
        buckets = TokenBuckets(2, 1.0, lambda: now[0], keep=3)
        self.assertTrue(buckets.take('a')[0])
        self.assertTrue(buckets.take('a')[0])
        allowed, wait = buckets.take('a')
        self.assertFalse(allowed)
        self.assertGreaterEqual(wait, 1)
        self.assertTrue(buckets.take('b')[0])
        now[0] = 1.0
        self.assertTrue(buckets.take('a')[0])
        for key in 'cdefg':
            buckets.take(key)
        self.assertLessEqual(len(buckets._buckets), 3)


# ---------------------------------------------------------------------------
# the forging matrix over HTTP
# ---------------------------------------------------------------------------
class ForgingTests(Base):
    def setUp(self):
        super().setUp()
        self.embed, self.secret = self.board_embed()
        self.eid = self.embed['embed_id']
        self.good = self.token(self.embed, self.secret,
                               params={'region': 'east'})

    def attempt(self, token, path='/data'):
        return self.st.get(self.eid, path, token)

    def test_good_token_works(self):
        response = self.attempt(self.good)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['data']['kind'], 'dashboard')

    def payload(self, **extra):
        now = self.st.clock.epoch()
        return {'aud': self.eid, 'iat': now, 'exp': now + 300,
                'params': {'region': 'east'}, **extra}

    def kid(self):
        return self.secret['kid']

    def test_every_forgery_is_the_same_404(self):
        secret, kid = self.secret['secret'], self.kid()
        head, body, sig = self.good.split('.')
        other_payload = tk.b64u_encode(json.dumps(
            self.payload(params={'region': 'west'})).encode())
        now = self.st.clock.epoch()
        forged = {
            'no token': '',
            'garbage': 'not-a-token',
            'alg none': forge(secret, kid, {'alg': 'none'}, self.payload(),
                              signature=''),
            'alg none with signature': forge(secret, kid, {'alg': 'none'},
                                             self.payload()),
            'alg HS512': forge(secret, kid, {'alg': 'HS512'}, self.payload()),
            'alg RS256 confusion': forge(secret, kid, {'alg': 'RS256'},
                                         self.payload()),
            'jwk header': forge(secret, kid, {'jwk': {'kty': 'oct'}},
                                self.payload()),
            'wrong kid': forge(secret, 'kzzzzzzz', None, self.payload()),
            'wrong secret': forge('W' * 43, kid, None, self.payload()),
            'tampered claims': f'{head}.{other_payload}.{sig}',
            'tampered signature': f'{head}.{body}.{sig[:-2]}AA',
            'wrong audience': forge(secret, kid, None, self.payload(
                aud='11111111-1111-4111-8111-111111111111')),
            'expired': forge(secret, kid, None, self.payload(
                iat=now - 400, exp=now - 100)),
            'not yet valid': forge(secret, kid, None, self.payload(
                nbf=now + 120, exp=now + 300)),
            'no expiry': forge(secret, kid, None, {
                'aud': self.eid, 'params': {'region': 'east'}}),
            'lifetime too long': forge(secret, kid, None, self.payload(
                exp=now + 5000)),
            'unknown member': forge(secret, kid, None, self.payload(
                admin=True)),
            'reserved claim': forge(secret, kid, None, self.payload(
                claims={'user_id': 1})),
            'undeclared parameter': forge(secret, kid, None, self.payload(
                params={'region': 'east', 'extra': 1})),
            'undeclared claim': forge(secret, kid, None, self.payload(
                claims={'tenant_id': 1})),
        }
        for label, token in forged.items():
            for path in ('/data', '/cards/detail/run', '/run'):
                with self.subTest(label, path=path):
                    if path == '/data':
                        response = self.attempt(token, path)
                    else:
                        response = self.st.post(self.eid, path, token)
                    denied(self, response)

    def test_frame_is_also_a_404_for_forgeries(self):
        for token in ('', 'x.y.z', forge('W' * 43, self.kid(), None,
                                          self.payload())):
            denied(self, self.st.frame(self.eid, token))

    def test_token_for_another_embed_is_refused(self):
        other, other_secret = self.make('dashboard', self.did,
                                        name='Second',
                                        parameters=[{'id': 'region',
                                                     'mode': 'locked'}])
        token = self.token(other, other_secret, params={'region': 'east'})
        self.assertEqual(self.st.get(other['embed_id'], '/data',
                                     token).status_code, 200)
        denied(self, self.st.get(self.eid, '/data', token))
        # and the first embed's secret does not open the second
        denied(self, self.st.get(other['embed_id'], '/data', self.good))

    def test_unknown_embed_and_malformed_ids_are_the_same_404(self):
        for embed_id in (eh.random_id(), 'x', '%00', '..',
                         'a' * 300):
            with self.subTest(embed_id):
                denied(self, self.st.get(embed_id, '/data', self.good))

    def test_wrong_scheme_and_missing_header(self):
        url = f'/cdeadmin/embed/{self.eid}/data'
        for headers in ({}, {'Authorization': self.good},
                        {'Authorization': f'Basic {self.good}'},
                        {'Authorization': 'Bearer'},
                        {'Authorization': f'Bearer  {self.good}x'}):
            with self.subTest(headers=headers):
                denied(self, self.st.client.get(url, headers=headers))

    def test_token_in_query_string_of_the_api_is_ignored(self):
        denied(self, self.st.client.get(
            f'/cdeadmin/embed/{self.eid}/data', query_string={
                'token': self.good}))

    def test_not_yet_valid_becomes_valid_inside_the_leeway(self):
        now = self.st.clock.epoch()
        early = forge(self.secret['secret'], self.kid(), None,
                      self.payload(nbf=now + 10, exp=now + 300))
        self.assertEqual(self.attempt(early).status_code, 200)

    def test_expiry_over_time(self):
        self.assertEqual(self.attempt(self.good).status_code, 200)
        self.st.clock.advance(seconds=299)
        self.assertEqual(self.attempt(self.good).status_code, 200)
        self.st.clock.advance(seconds=1)
        denied(self, self.attempt(self.good))

    def test_disabled_and_revoked_embeds(self):
        self.st.service.disable(OWNER, self.st.ep, self.eid)
        denied(self, self.attempt(self.good))
        self.st.service.enable(OWNER, self.st.ep, self.eid,
                               SimpleNamespace(user_id=OWNER))
        self.assertEqual(self.attempt(self.good).status_code, 200)
        self.st.service.revoke(OWNER, self.st.ep, self.eid)
        denied(self, self.attempt(self.good))
        self.assertEqual(self.st.repo.keys(self.eid), [])
        with self.assertRaises(BIError):
            self.st.service.enable(OWNER, self.st.ep, self.eid,
                                   SimpleNamespace(user_id=OWNER))

    def test_embed_expiry_policy(self):
        embed, secret = self.make(
            'dashboard', self.did, name='Short',
            parameters=[{'id': 'region', 'mode': 'locked'}],
            expires_at=(self.st.clock() + timedelta(hours=1)).isoformat())
        token = self.token(embed, secret, params={'region': 'east'})
        self.assertEqual(self.st.get(embed['embed_id'], '/data',
                                     token).status_code, 200)
        self.st.clock.advance(hours=2)
        fresh = self.token(embed, secret, params={'region': 'east'})
        denied(self, self.st.get(embed['embed_id'], '/data', fresh))

    def test_rotated_out_key(self):
        first = self.secret
        second = self.st.service.rotate(OWNER, self.st.ep, self.eid)['secret']
        old = self.token(self.embed, first, params={'region': 'east'})
        new = self.token(self.embed, second, params={'region': 'east'})
        # two keys are active during the overlap
        self.assertEqual(self.attempt(old).status_code, 200)
        self.assertEqual(self.attempt(new).status_code, 200)
        third = self.st.service.rotate(OWNER, self.st.ep, self.eid)['secret']
        denied(self, self.attempt(old))
        self.assertEqual(self.attempt(new).status_code, 200)
        self.assertEqual(self.attempt(self.token(
            self.embed, third, params={'region': 'east'})).status_code, 200)
        self.assertEqual(len(self.st.repo.keys(self.eid)), 2)

    def test_retired_previous_key(self):
        second = self.st.service.rotate(OWNER, self.st.ep, self.eid)['secret']
        old = self.token(self.embed, self.secret, params={'region': 'east'})
        self.assertEqual(self.attempt(old).status_code, 200)
        self.st.service.retire_previous_key(OWNER, self.st.ep, self.eid)
        denied(self, self.attempt(old))
        self.assertEqual(self.attempt(self.token(
            self.embed, second, params={'region': 'east'})).status_code, 200)

    def test_bad_signature_burns_one_constant_time_compare(self):
        wrong = forge('W' * 43, self.kid(), None, self.payload())
        unknown_kid = forge(self.secret['secret'], 'kzzzzzzz', None,
                            self.payload())
        counts = {}
        for label, call in {
                'good': lambda: self.attempt(self.good),
                'wrong secret': lambda: self.attempt(wrong),
                'unknown kid': lambda: self.attempt(unknown_kid),
                'unknown embed': lambda: self.st.get(
                    eh.random_id(), '/data', self.good),
                'garbage': lambda: self.attempt('garbage')}.items():
            with mock.patch.object(tk.hmac, 'compare_digest',
                                   wraps=hmac.compare_digest) as spy:
                call()
            counts[label] = spy.call_count
        self.assertEqual(set(counts.values()), {1}, counts)


class OneTimeTokenTests(Base):
    def setUp(self):
        super().setUp()
        self.embed, self.secret = self.board_embed(require_jti=True)
        self.eid = self.embed['embed_id']

    def token_with(self, jti='jti-0123456789', **kw):
        return self.token(self.embed, self.secret,
                          params={'region': 'east'}, jti=jti, **kw)

    def test_a_token_without_jti_is_refused(self):
        denied(self, self.st.get(self.eid, '/data', self.token(
            self.embed, self.secret, params={'region': 'east'})))

    def test_replay_is_refused_after_the_first_data_call(self):
        token = self.token_with()
        self.assertEqual(self.st.get(self.eid, '/data', token).status_code,
                         200)
        denied(self, self.st.get(self.eid, '/data', token))
        denied(self, self.st.frame(self.eid, token))

    def test_a_token_never_opened_cannot_run_cards(self):
        token = self.token_with()
        denied(self, self.st.post(self.eid, '/cards/detail/run', token))
        self.assertEqual(self.st.frame(self.eid, token).status_code, 200)
        denied(self, self.st.post(self.eid, '/cards/detail/run', token))
        self.assertEqual(self.st.get(self.eid, '/data', token).status_code,
                         200)
        self.assertEqual(self.st.post(self.eid, '/cards/detail/run',
                                      token).status_code, 200)

    def test_consumed_ids_expire_with_the_token(self):
        token = self.token_with()
        self.st.get(self.eid, '/data', token)
        self.st.clock.advance(seconds=400)
        self.assertEqual(self.st.repo.used, {(self.eid, 'jti-0123456789'):
                                             self.st.repo.used[
                                                 (self.eid,
                                                  'jti-0123456789')]})
        # a new token reusing the id after the old one lapsed is allowed
        again = self.token_with()
        self.assertEqual(self.st.get(self.eid, '/data', again).status_code,
                         200)

    def test_distinct_ids_are_independent(self):
        for index in range(3):
            token = self.token_with(jti=f'jti-abcdefgh{index}')
            self.assertEqual(self.st.get(self.eid, '/data',
                                         token).status_code, 200)


# ---------------------------------------------------------------------------
# parameters
# ---------------------------------------------------------------------------
class ParameterTests(Base):
    def test_locked_value_comes_from_the_token_only(self):
        embed, secret = self.board_embed()
        token = self.token(embed, secret, params={'region': 'east'})
        eid = embed['embed_id']
        for card_id in ('detail', 'by_region'):
            response = self.card(embed, token, card_id)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(regions(response), ['east'])
        for body in ({'filters': {'region': 'west'}},
                     {'filters': {'region': 'east'}},
                     {'filters': {'region': None}}):
            with self.subTest(body):
                response = self.card(embed, token, 'detail', body)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json(),
                                 {'success': 0,
                                  'error': 'parameter_not_editable'})
        # the view shows it as locked with its token value
        view = self.st.get(eid, '/data', token).get_json()['data']
        shown = {p['id']: p for p in view['parameters']}
        self.assertEqual(shown['region']['mode'], 'locked')
        self.assertEqual(shown['region']['value'], 'east')

    def test_missing_locked_value_does_not_widen_the_result(self):
        embed, secret = self.board_embed()
        token = self.token(embed, secret)
        # the card whose parameter is required cannot run without it
        response = self.card(embed, token, 'by_region')
        self.assertNotEqual(response.get_json()['data'].get('status'), 'ok')
        self.assertNotIn('rows', response.get_json()['data'])

    def test_editable_value_may_be_chosen_by_the_viewer(self):
        embed, secret = self.board_embed(
            parameters=[{'id': 'region', 'mode': 'editable'}])
        token = self.token(embed, secret, params={'region': 'east'})
        self.assertEqual(regions(self.card(embed, token)), ['east'])
        west = self.card(embed, token, 'detail',
                         {'filters': {'region': 'west'}})
        self.assertEqual(west.status_code, 200)
        self.assertEqual(regions(west), ['west'])
        # an editable parameter is not forced by the token alone
        bare = self.card(embed, self.token(embed, secret), 'detail')
        self.assertEqual(bare.status_code, 200)
        self.assertEqual(regions(bare), ['east', 'west'])

    def test_hidden_value_is_applied_and_not_shown(self):
        embed, secret = self.board_embed(
            parameters=[{'id': 'region', 'mode': 'hidden'}])
        token = self.token(embed, secret, params={'region': 'west'})
        self.assertEqual(regions(self.card(embed, token)), ['west'])
        view = self.st.get(embed['embed_id'], '/data',
                           token).get_json()['data']
        self.assertEqual(view['parameters'], [])
        self.assertNotIn('west', json.dumps(view['parameters']))
        response = self.card(embed, token, 'detail',
                             {'filters': {'region': 'east'}})
        self.assertEqual(response.status_code, 400)

    def test_undeclared_viewer_parameter_is_refused(self):
        embed, secret = self.board_embed(
            parameters=[{'id': 'region', 'mode': 'editable'}])
        token = self.token(embed, secret, params={'region': 'east'})
        for filters in ({'floor': 5}, {'region': 'east', 'extra': 1},
                        {'__proto__': 1}, {'user_id': 1}):
            with self.subTest(filters):
                response = self.card(embed, token, 'detail',
                                     {'filters': filters})
                self.assertEqual(response.status_code, 400)

    def test_values_are_validated_by_the_typed_binder(self):
        embed, secret = self.board_embed(
            parameters=[{'id': 'region', 'mode': 'editable'}])
        token = self.token(embed, secret, params={'region': 'east'})
        for value in ('north', 7, ['east', 'west'], {'a': 1}, True):
            with self.subTest(value=value):
                response = self.card(embed, token, 'detail',
                                     {'filters': {'region': value}})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json()['error'],
                                 'invalid_filters')
        # a token value outside the allowed values is equally refused
        bad = self.token(embed, secret, params={'region': 'north'})
        response = self.card(embed, bad)
        self.assertEqual(response.status_code, 400)

    def test_non_object_bodies_are_refused(self):
        embed, secret = self.board_embed()
        token = self.token(embed, secret, params={'region': 'east'})
        for body in ([1], 'text', 5):
            response = self.st.client.post(
                f'/cdeadmin/embed/{embed["embed_id"]}/cards/detail/run',
                data=json.dumps(body), content_type='application/json',
                headers={'Authorization': f'Bearer {token}'})
            self.assertEqual(response.status_code, 400)
        response = self.card(embed, token, 'detail', {'filters': [1]})
        self.assertEqual(response.status_code, 400)

    def test_unknown_and_non_question_cards_are_404(self):
        embed, secret = self.board_embed()
        token = self.token(embed, secret, params={'region': 'east'})
        for card_id in ('missing', 'by_region%00', '..'):
            denied(self, self.card(embed, token, card_id))

    def test_required_parameters_must_be_declared(self):
        did, _parts = self.dashboard()
        with self.assertRaises(BIError):
            self.st.create('dashboard', did,
                           parameters=[{'id': 'nope', 'mode': 'locked'}])

    def test_question_embed_parameters(self):
        qid = self.st.s.q(OWNER, dict(region_question(), name='Solo'))
        embed, secret = self.make(
            'question', qid, parameters=[{'id': 'region',
                                          'mode': 'editable'}])
        eid = embed['embed_id']
        token = self.token(embed, secret, params={'region': 'east'})
        response = self.st.post(eid, '/run', token)
        self.assertEqual(regions(response), ['east'])
        response = self.st.post(eid, '/run', token,
                                {'parameters': {'region': 'west'}})
        self.assertEqual(regions(response), ['west'])
        locked, lsecret = self.make(
            'question', qid, name='Locked',
            parameters=[{'id': 'region', 'mode': 'locked'}])
        ltoken = self.token(locked, lsecret, params={'region': 'east'})
        response = self.st.post(locked['embed_id'], '/run', ltoken,
                                {'parameters': {'region': 'west'}})
        self.assertEqual(response.status_code, 400)
        # a question embed has no card endpoint and a dashboard no /run
        denied(self, self.st.post(eid, '/cards/x/run', token))
        board_embed, bsecret = self.board_embed()
        denied(self, self.st.post(
            board_embed['embed_id'], '/run',
            self.token(board_embed, bsecret, params={'region': 'east'})))


# ---------------------------------------------------------------------------
# claim driven row policy and tenant separation
# ---------------------------------------------------------------------------
class TenantTests(unittest.TestCase):
    def make(self, engine):
        st = EmbedStack(engine)
        qid = tenant_question(st)
        did = st.s.dashboards.create(OWNER, st.ep, board([qid]))[
            'dashboard_id']
        embed, secret = st.create(
            'dashboard', did, claims=[{'name': 'tenant_id',
                                       'required': True}])
        return st, embed, secret

    @staticmethod
    def result(response):
        return sorted((r['region'], r['revenue']) for r in rows_of(response))

    def test_a_tenant_claim_changes_the_result(self):
        for engine in ENGINES:
            with self.subTest(engine):
                st, embed, secret = self.make(engine)
                eid = embed['embed_id']
                seen = {}
                for tenant in (1, 2, 3):
                    token = st.token(eid, secret, claims={'tenant_id': tenant})
                    response = st.post(eid, '/cards/c0/run', token)
                    self.assertEqual(response.status_code, 200)
                    seen[tenant] = self.result(response)
                # qty is the tenant column of the sample data
                self.assertEqual(seen[1], [('east', 10), ('west', 5)])
                self.assertEqual(seen[2], [('west', 20)])
                self.assertEqual(seen[3], [('east', 30)])
                contexts = [c['claims'] for c in st.s.security_contexts]
                self.assertEqual([c['tenant_id'] for c in contexts],
                                 [1, 2, 3])
                for context in contexts:
                    self.assertEqual(context['principal'], 'embedding')
                    self.assertEqual(context['embed_id'], eid)
                    self.assertNotIn('user_id', context)

    def test_a_required_claim_is_enforced(self):
        st, embed, secret = self.make('sqlite')
        eid = embed['embed_id']
        denied(self, st.post(eid, '/cards/c0/run', st.token(eid, secret)))
        denied(self, st.post(eid, '/cards/c0/run', st.token(
            eid, secret, claims={'other': 1})))

    def test_no_claim_means_no_data_not_all_data(self):
        st, embed, secret = self.make('sqlite')
        eid = embed['embed_id']
        # the owner can optionalize the claim; the semantic model still
        # requires a tenant identity, so the card must not run unscoped
        st.service.update(
            OWNER, st.ep, eid, 1, st.definition(
                'dashboard', embed['resource']['id'],
                name=embed['name'],
                claims=[{'name': 'tenant_id', 'required': False}]))
        response = st.post(eid, '/cards/c0/run', st.token(eid, secret))
        body = response.get_json()['data']
        self.assertNotEqual(body.get('status'), 'ok')
        self.assertNotIn('rows', body)

    def test_the_run_uses_the_embed_principal_and_the_owner_credentials(self):
        st, embed, secret = self.make('sqlite')
        eid = embed['embed_id']
        st.post(eid, '/cards/c0/run', st.token(eid, secret,
                                               claims={'tenant_id': 1}))
        sessions = st.s.studio.sessions
        self.assertTrue(sessions)
        route = sessions[-1]['endpoint']['route']
        self.assertEqual(route['credential_owner'], OWNER)
        self.assertTrue(route['delegated'])
        self.assertEqual(st.scheduler.runtimes[-1], route['delegated'])

    def test_cache_is_separated_between_tenants_and_from_interactive(self):
        st, embed, secret = self.make('sqlite')
        eid = embed['embed_id']
        tokens_ = {t: st.token(eid, secret, claims={'tenant_id': t})
                   for t in (1, 2)}
        first = st.post(eid, '/cards/c0/run', tokens_[1])
        # the same request again may be served from the cache
        again = st.post(eid, '/cards/c0/run', tokens_[1])
        self.assertEqual(self.result(first), self.result(again))
        other = st.post(eid, '/cards/c0/run', tokens_[2])
        self.assertNotEqual(self.result(first), self.result(other))
        self.assertNotEqual(first.get_json()['data']['result_id'],
                            other.get_json()['data']['result_id'])
        # the owner's own interactive run of the dashboard is not poisoned
        # by, and does not poison, the embedded results
        did = embed['resource']['id']
        interactive = st.s.run_dashboard(OWNER, did)
        self.assertTrue(interactive)
        again = st.post(eid, '/cards/c0/run', tokens_[2])
        self.assertEqual(self.result(again), self.result(other))

    def test_results_of_another_tenant_cannot_be_paged_or_exported(self):
        st, embed, secret = self.make('sqlite')
        eid = embed['embed_id']
        one = st.token(eid, secret, claims={'tenant_id': 1})
        two = st.token(eid, secret, claims={'tenant_id': 2})
        result_id = st.post(eid, '/cards/c0/run', one).get_json()[
            'data']['result_id']
        for path, body in (('/page', {'result_id': result_id,
                                      'cursor': 'x'}),
                           ('/export', {'result_id': result_id,
                                        'format': 'csv'})):
            denied(self, st.post(eid, path, two, body))
        # interactive result ids are invisible to the embed as well
        interactive = st.s.run_as(OWNER, question_id=st.s.q(
            OWNER, detail_by_region()))
        rid = interactive['result']['result_id']
        denied(self, st.post(eid, '/page', one,
                             {'result_id': rid, 'cursor': 'x'}))

    def test_principal_scoping_in_the_executor(self):
        st, embed, secret = self.make('sqlite')
        eid = embed['embed_id']
        st.post(eid, '/cards/c0/run', st.token(eid, secret,
                                               claims={'tenant_id': 1}))
        info = st.s.executor.cache_info(OWNER, st.ep) if hasattr(
            st.s.executor, 'cache_info') else None
        if info is not None:
            self.assertNotIn('embed:', json.dumps(info, default=str))


# ---------------------------------------------------------------------------
# rate limiting
# ---------------------------------------------------------------------------
class RateLimitTests(Base):
    config = {'ip_rate': (4, 0.001), 'embed_rate': (1000, 1000.0)}

    def test_per_ip_budget_is_spent_before_anything_is_looked_up(self):
        embed, secret = self.board_embed()
        eid = embed['embed_id']
        codes = [self.st.get(eid, '/data', 'garbage').status_code
                 for _ in range(7)]
        self.assertEqual(codes[:4], [404] * 4)
        self.assertEqual(set(codes[4:]), {429})
        response = self.st.get(eid, '/data', 'garbage')
        self.assertEqual(response.status_code, 429)
        self.assertTrue(int(response.headers['Retry-After']) >= 1)
        self.assertEqual(response.get_json(),
                         {'success': 0, 'error': 'rate_limited'})
        # even a valid token is refused while the address is limited
        good = self.token(embed, secret, params={'region': 'east'})
        self.assertEqual(self.st.get(eid, '/data', good).status_code, 429)
        # the budget refills
        self.st.mono[0] += 10000
        self.assertEqual(self.st.get(eid, '/data', good).status_code, 200)


class EmbedRateLimitTests(Base):
    config = {'ip_rate': (1000, 1000.0), 'embed_rate': (3, 0.001)}

    def test_per_embed_budget_only_counts_verified_tokens(self):
        embed, secret = self.board_embed()
        eid = embed['embed_id']
        wrong = forge('W' * 43, secret['kid'], None, {
            'aud': eid, 'exp': self.st.clock.epoch() + 100})
        for _ in range(20):
            denied(self, self.st.get(eid, '/data', wrong))
        good = self.token(embed, secret, params={'region': 'east'})
        codes = [self.st.get(eid, '/data', good).status_code
                 for _ in range(5)]
        self.assertEqual(codes, [200, 200, 200, 429, 429])
        # another embed has its own budget
        other, other_secret = self.make(
            'dashboard', self.did, name='Other',
            parameters=[{'id': 'region', 'mode': 'locked'}])
        token = self.token(other, other_secret, params={'region': 'east'})
        self.assertEqual(self.st.get(other['embed_id'], '/data',
                                     token).status_code, 200)

    def test_garbage_cannot_exhaust_the_budget_of_a_real_embed(self):
        embed, secret = self.board_embed()
        eid = embed['embed_id']
        for _ in range(30):
            self.st.get(eid, '/data', 'x.y.z')
            self.st.get(eid, '/data', forge('W' * 43, secret['kid'], None,
                                            {'aud': eid}))
        good = self.token(embed, secret, params={'region': 'east'})
        self.assertEqual(self.st.get(eid, '/data', good).status_code, 200)


# ---------------------------------------------------------------------------
# headers, cookies, CORS
# ---------------------------------------------------------------------------
class HeaderTests(Base):
    def setUp(self):
        super().setUp()
        self.embed, self.secret = self.board_embed()
        self.eid = self.embed['embed_id']
        self.good = self.token(self.embed, self.secret,
                               params={'region': 'east'})

    def ancestors(self, response):
        csp = response.headers['Content-Security-Policy']
        part = [p for p in csp.split(';')
                if p.strip().startswith('frame-ancestors')][0]
        return part.strip()[len('frame-ancestors '):].split()

    def test_frame_ancestors_are_exactly_the_allowed_origins(self):
        response = self.st.frame(self.eid, self.good)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.ancestors(response), ORIGINS)
        csp = response.headers['Content-Security-Policy']
        self.assertIn("default-src 'none'", csp)
        self.assertIn("connect-src 'self'", csp)
        self.assertIn("base-uri 'none'", csp)
        self.assertNotIn('unsafe-inline', csp)
        self.assertNotIn('unsafe-eval', csp)
        self.assertNotIn('*', csp)
        self.assertNotIn('X-Frame-Options', response.headers)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')

    def test_nonce_is_fresh_and_matches_the_markup(self):
        first = self.st.frame(self.eid, self.good)
        second = self.st.frame(self.eid, self.good)
        nonces = []
        for response in (first, second):
            csp = response.headers['Content-Security-Policy']
            nonce = csp.split("script-src 'nonce-")[1].split("'")[0]
            nonces.append(nonce)
            page = response.get_data(as_text=True)
            self.assertIn(f'nonce="{nonce}"', page)
            self.assertEqual(page.count('<script'), 1)
            self.assertNotIn(self.good, page)
        self.assertNotEqual(*nonces)

    def test_an_embed_without_origins_cannot_be_framed(self):
        embed, secret = self.make(
            'dashboard', self.did, name='Nowhere', origins=[],
            parameters=[{'id': 'region', 'mode': 'locked'}])
        token = self.token(embed, secret, params={'region': 'east'})
        response = self.st.frame(embed['embed_id'], token)
        self.assertEqual(self.ancestors(response), ["'none'"])

    def test_origins_are_exact(self):
        did = self.did
        for origin in ('*', 'https://*.example.com', 'http://example.com',
                       'https://example.com/path', 'https://user@example.com',
                       'example.com', 'https://example.com/', 'null',
                       "https://a.example.com; script-src *",
                       'https://exa mple.com', 'javascript:alert(1)',
                       'https://localhost'):
            with self.subTest(origin):
                with self.assertRaises(BIError):
                    self.st.service.create(OWNER, self.st.ep, self.st.definition(
                        'dashboard', did, name='o', origins=[origin],
                        parameters=[{'id': 'region', 'mode': 'locked'}]))
        self.st.service.create(OWNER, self.st.ep, self.st.definition(
            'dashboard', did, name='ok',
            origins=['http://localhost:3000', 'https://a.example.com'],
            parameters=[{'id': 'region', 'mode': 'locked'}]))

    def test_preview_tokens_may_be_framed_by_the_app_itself(self):
        preview = self.st.service.preview(
            OWNER, self.st.ep, self.eid, {'region': 'east'})
        response = self.st.frame(self.eid, preview['token'])
        self.assertEqual(self.ancestors(response), ORIGINS + ["'self'"])
        # an ordinary token cannot ask for 'self'
        self.assertNotIn("'self'", self.ancestors(
            self.st.frame(self.eid, self.good)))
        # claiming to be a preview in an owner-signed token is the owner's
        # own act; an unsigned claim is worthless
        forged = forge('W' * 43, self.secret['kid'], None, {
            'aud': self.eid, 'exp': self.st.clock.epoch() + 100,
            'prv': True, 'jti': 'abcdefghijk'})
        denied(self, self.st.frame(self.eid, forged))

    def test_json_responses_carry_a_locked_down_csp(self):
        response = self.st.get(self.eid, '/data', self.good)
        self.assertEqual(response.headers['Content-Security-Policy'],
                         "default-src 'none'; frame-ancestors 'none'")
        self.assertEqual(response.headers['X-Content-Type-Options'],
                         'nosniff')
        denied_response = self.st.get(self.eid, '/data', 'bad')
        self.assertEqual(
            denied_response.headers['Content-Security-Policy'],
            "default-src 'none'; frame-ancestors 'none'")

    def test_no_cookie_is_read_or_set_anywhere(self):
        calls = [
            self.st.get(self.eid, '/data', self.good),
            self.st.post(self.eid, '/cards/detail/run', self.good),
            self.st.frame(self.eid, self.good),
            self.st.get(self.eid, '/data', 'bad'),
            self.st.post(self.eid, '/cards/missing/run', self.good),
            self.st.get(eh.random_id(), '/data', self.good),
        ]
        for response in calls:
            self.assertEqual(response.headers.getlist('Set-Cookie'), [])
        self.st.seen_cookies.clear()
        self.st.client.get(
            f'/cdeadmin/embed/{self.eid}/data',
            headers={'Authorization': f'Bearer {self.good}',
                     'Cookie': 'session=abc; csrf_token=def'})
        self.assertEqual(self.st.seen_cookies, [{}])
        # the isolation layer is what the harness' paranoid session meets
        probe = self.st.client.get('/not-embed')
        self.assertEqual(probe.status_code, 404)

    def test_no_cors(self):
        url = f'/cdeadmin/embed/{self.eid}/data'
        options = self.st.client.options(url, headers={
            'Origin': ORIGINS[0], 'Access-Control-Request-Method': 'GET'})
        self.assertNotEqual(options.status_code, 200)
        for call in (
                lambda: self.st.client.options(url, headers={
                    'Origin': ORIGINS[0],
                    'Access-Control-Request-Method': 'GET'}),
                lambda: self.st.client.get(url, headers={
                    'Origin': ORIGINS[0],
                    'Authorization': f'Bearer {self.good}'}),
                lambda: self.st.client.get(url, headers={
                    'Origin': 'https://evil.example',
                    'Authorization': 'Bearer bad'})):
            response = call()
            self.assertEqual([h for h in response.headers.keys()
                              if h.lower().startswith('access-control')], [])

    def test_only_the_documented_methods(self):
        for path in ('/data', '/frame', '/cards/detail/run', '/run', '/page'):
            for method in ('put', 'delete', 'patch'):
                response = getattr(self.st.client, method)(
                    f'/cdeadmin/embed/{self.eid}{path}',
                    headers={'Authorization': f'Bearer {self.good}'})
                self.assertEqual(response.status_code, 405)
        response = self.st.client.post(
            f'/cdeadmin/embed/{self.eid}/data',
            headers={'Authorization': f'Bearer {self.good}'})
        self.assertEqual(response.status_code, 405)

    def test_oversized_bodies_are_refused(self):
        response = self.st.client.post(
            f'/cdeadmin/embed/{self.eid}/cards/detail/run',
            data=json.dumps({'filters': {'region': 'x' * 200000}}),
            content_type='application/json',
            headers={'Authorization': f'Bearer {self.good}'})
        self.assertIn(response.status_code, (400, 413))


# ---------------------------------------------------------------------------
# raw SQL
# ---------------------------------------------------------------------------
class RawSqlTests(unittest.TestCase):
    SQL = 'SELECT region, amount FROM sales ORDER BY amount'

    def raw_question(self, st):
        return st.s.q(OWNER, sql_question(self.SQL))

    def test_refused_by_default(self):
        st = EmbedStack()
        qid = self.raw_question(st)
        with self.assertRaisesRegex(BIError, 'ALLOW_RAW_SQL'):
            st.create('question', qid)
        did = st.s.dashboards.create(OWNER, st.ep, board([qid]))[
            'dashboard_id']
        with self.assertRaisesRegex(BIError, 'ALLOW_RAW_SQL'):
            st.create('dashboard', did)

    def test_a_dashboard_with_one_raw_card_is_refused(self):
        st = EmbedStack()
        mixed = st.s.dashboards.create(OWNER, st.ep, board([
            st.s.q(OWNER, detail_by_region()), self.raw_question(st)]))
        with self.assertRaises(BIError):
            st.create('dashboard', mixed['dashboard_id'])

    def test_allowed_only_by_the_server_setting(self):
        st = EmbedStack(config={'allow_raw_sql': True})
        qid = self.raw_question(st)
        embed, secret = st.create('question', qid)
        token = st.token(embed['embed_id'], secret)
        response = st.post(embed['embed_id'], '/run', token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(rows_of(response)), 5)

    def test_not_with_claims(self):
        st = EmbedStack(config={'allow_raw_sql': True})
        qid = self.raw_question(st)
        with self.assertRaisesRegex(BIError, 'claims'):
            st.create('question', qid, claims=[{'name': 'tenant_id'}])

    def test_the_owner_must_pass_the_raw_sql_policy(self):
        st = EmbedStack(config={'allow_raw_sql': True})
        qid = self.raw_question(st)
        embed, secret = st.create('question', qid)
        token = st.token(embed['embed_id'], secret)
        self.assertEqual(st.post(embed['embed_id'], '/run',
                                 token).status_code, 200)
        # a row policy appears at this endpoint: raw SQL could bypass it,
        # so the embedded view stops running it
        st.s.bi.semantic.create(OWNER, st.ep, tenant_model())
        response = st.post(embed['embed_id'], '/run', token)
        self.assertEqual(response.get_json()['data']['status'], 'unavailable')
        self.assertNotIn('rows', response.get_json()['data'])
        with self.assertRaises(BIError):
            st.create('question', qid, name='Another')

    def test_runtime_recheck_when_the_server_setting_is_turned_off(self):
        st = EmbedStack(config={'allow_raw_sql': True})
        qid = self.raw_question(st)
        embed, secret = st.create('question', qid)
        token = st.token(embed['embed_id'], secret)
        st.service.config['allow_raw_sql'] = False
        response = st.post(embed['embed_id'], '/run', token)
        self.assertEqual(response.get_json()['data']['status'], 'unavailable')


# ---------------------------------------------------------------------------
# the owner and the resource
# ---------------------------------------------------------------------------
class OwnerTests(Base):
    def share_all(self, did, parts):
        """MANAGER manages the dashboard and can view its questions."""
        for qid in (parts.by_region, parts.detail, parts.other):
            self.st.s.share(OWNER, 'question', qid, MANAGER, 'view')
        return self.st.s.share(OWNER, 'dashboard', did, MANAGER, 'manage')

    def test_owner_losing_manage_disables_the_embed(self):
        did, parts = sales_board(self.st)
        self.share_all(did, parts)
        embed, secret = self.st.create(
            'dashboard', did, user=MANAGER,
            parameters=[{'id': 'region', 'mode': 'locked'}])
        eid = embed['embed_id']
        token = self.st.token(eid, secret, params={'region': 'east'})
        self.assertEqual(self.st.get(eid, '/data', token).status_code, 200)
        self.assertEqual(self.card(embed, token).status_code, 200)
        for grant in list(self.st.s.grants.rows.values()):
            self.st.s.grants.remove(grant['grant_id'])
        denied(self, self.st.get(eid, '/data', token))
        row = self.st.repo.get(eid)
        self.assertEqual(row.status, 'disabled')
        self.assertEqual(row.disabled_reason, 'owner_access_lost')
        self.assertEqual(self.st.scheduler.delegation_for(eid).state,
                         'revoked')
        # restoring the grant does not silently re-enable it
        self.st.s.share(OWNER, 'dashboard', did, MANAGER, 'manage')
        denied(self, self.st.get(eid, '/data', token))

    def test_downgrade_to_edit_also_disables(self):
        did, parts = sales_board(self.st)
        grant = self.share_all(did, parts)
        embed, secret = self.st.create(
            'dashboard', did, user=MANAGER,
            parameters=[{'id': 'region', 'mode': 'locked'}])
        token = self.st.token(embed['embed_id'], secret,
                              params={'region': 'east'})
        self.st.s.grants.set_level(grant['grant_id'], 'edit')
        denied(self, self.st.get(embed['embed_id'], '/data', token))
        self.assertEqual(self.st.repo.get(embed['embed_id']).disabled_reason,
                         'owner_access_lost')

    def test_archived_resource_stops_serving(self):
        embed, secret = self.board_embed()
        token = self.token(embed, secret, params={'region': 'east'})
        self.assertEqual(self.st.get(embed['embed_id'], '/data',
                                     token).status_code, 200)
        row = self.st.s.dashboards.repository.rows[self.did]
        row.status = 'archived'
        denied(self, self.st.get(embed['embed_id'], '/data', token))

    def test_expired_delegation_disables(self):
        embed, secret = self.board_embed()
        eid = embed['embed_id']
        token = self.token(embed, secret, params={'region': 'east'})
        self.st.scheduler.delegations[eid].expires_at = (
            self.st.clock.naive() - timedelta(seconds=1))
        denied(self, self.card(embed, token))
        self.assertEqual(self.st.repo.get(eid).disabled_reason,
                         'delegation_expired')

    def test_revoked_delegation_is_a_404_not_a_run(self):
        embed, secret = self.board_embed()
        token = self.token(embed, secret, params={'region': 'east'})
        self.st.scheduler.revoke_embed(embed['embed_id'])
        denied(self, self.card(embed, token))

    def test_pinned_revision_is_what_runs(self):
        did, parts = sales_board(self.st)
        embed, secret = self.st.create(
            'dashboard', did, parameters=[{'id': 'region', 'mode': 'locked'}],
            resource={'type': 'dashboard', 'id': did, 'revision': 1})
        eid = embed['embed_id']
        token = self.st.token(eid, secret, params={'region': 'east'})
        current = self.st.s.dashboards.get(OWNER, self.st.ep, did)
        definition = dict(current['definition'])
        definition['cards'] = [c for c in definition['cards']
                               if c['id'] != 'detail']
        definition['drill_throughs'] = []
        definition['filters'] = [dict(
            definition['filters'][0],
            targets=[definition['filters'][0]['targets'][0]])]
        self.st.s.dashboards.update(OWNER, self.st.ep, did,
                                    current['revision'], definition)
        view = self.st.get(eid, '/data', token).get_json()['data']
        self.assertEqual(sorted(c['id'] for c in view['cards']),
                         ['by_region', 'detail'])
        latest, lsecret = self.st.create(
            'dashboard', did, name='Latest',
            parameters=[{'id': 'region', 'mode': 'locked'}])
        view = self.st.get(
            latest['embed_id'], '/data',
            self.st.token(latest['embed_id'], lsecret,
                          params={'region': 'east'})).get_json()['data']
        self.assertEqual([c['id'] for c in view['cards']], ['by_region'])

    def test_deleting_the_resource_removes_its_embeds(self):
        embed, secret = self.board_embed()
        eid = embed['embed_id']
        token = self.token(embed, secret, params={'region': 'east'})
        revision = self.st.s.dashboards.get(OWNER, self.st.ep,
                                            self.did)['revision']
        self.st.s.dashboards.delete(OWNER, self.st.ep, self.did, revision)
        self.assertIsNone(self.st.repo.get(eid))
        self.assertEqual(self.st.repo.keys(eid), [])
        denied(self, self.st.get(eid, '/data', token))


# ---------------------------------------------------------------------------
# nothing sensitive leaves
# ---------------------------------------------------------------------------
class LeakTests(Base):
    FORBIDDEN = ('SELECT', 'select ', 'FROM', ' sales', 'sales"', 'sql',
                 'Traceback', 'sqlite', 'duckdb', 'compiled', 'manifest',
                 'plan', 'credential', 'password', 'user_id', 'endpoint',
                 'fingerprint', 'cache')

    def bodies(self, embed, secret):
        eid = embed['embed_id']
        token = self.token(embed, secret, params={'region': 'east'})
        calls = [
            self.st.get(eid, '/data', token),
            self.st.post(eid, '/cards/detail/run', token),
            self.st.post(eid, '/cards/by_region/run', token),
            self.st.frame(eid, token),
            self.st.get(eid, '/data', 'bad'),
            self.st.post(eid, '/cards/missing/run', token),
            self.st.post(eid, '/cards/detail/run', token,
                         {'filters': {'region': 'west'}}),
        ]
        return [r.get_data(as_text=True) for r in calls]

    def test_no_sql_secret_or_internal_name_is_ever_returned(self):
        embed, secret = self.board_embed()
        for text in self.bodies(embed, secret):
            self.assertNotIn(secret['secret'], text)
            self.assertNotIn('"sql"', text)
            for word in ('SELECT ', 'Traceback', '"manifest"', '"plan"',
                         'credential_owner', 'password', 'sqlite'):
                self.assertNotIn(word, text)

    def test_a_failing_run_is_a_generic_code(self):
        broken = self.st.s.q(OWNER, {
            'name': 'Broken', 'query': {'kind': 'builder', 'builder': {
                'source': {'relation': ['no_such_table_xyz']},
                'columns': ['region'], 'limit': 5}}})
        embed, secret = self.make('question', broken)
        token = self.token(embed, secret)
        response = self.st.post(embed['embed_id'], '/run', token)
        text = response.get_data(as_text=True)
        self.assertNotIn('no_such_table_xyz', text)
        self.assertNotIn('no such table', text.lower())
        self.assertNotIn('Traceback', text)
        data = response.get_json()['data']
        self.assertIn(data['status'], ('error', 'unavailable'))
        self.assertNotIn('rows', data)

    def test_an_unexpected_exception_is_a_generic_500(self):
        embed, secret = self.board_embed()
        token = self.token(embed, secret, params={'region': 'east'})
        with mock.patch.object(self.st.service, 'view',
                               side_effect=RuntimeError('db password=hunter2')):
            response = self.st.get(embed['embed_id'], '/data', token)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json(),
                         {'success': 0, 'error': 'failed'})
        self.assertNotIn('hunter2', response.get_data(as_text=True))

    def test_the_view_whitelist(self):
        embed, secret = self.board_embed()
        token = self.token(embed, secret, params={'region': 'east'})
        data = self.st.get(embed['embed_id'], '/data',
                           token).get_json()['data']
        self.assertEqual(set(data), {
            'kind', 'name', 'description', 'display', 'tabs', 'cards',
            'parameters', 'drills', 'page_size'})
        for item in data['cards']:
            self.assertNotIn('question', item)
        run = self.card(embed, token).get_json()['data']
        self.assertEqual(set(run), {
            'status', 'columns', 'rows', 'row_count', 'next_cursor',
            'result_id', 'visualization', 'download', 'card_id'})

    def test_secrets_are_stored_encrypted(self):
        embed, secret = self.board_embed()
        stored = self.st.repo.keys(embed['embed_id'])
        self.assertEqual(len(stored), 1)
        self.assertNotIn(secret['secret'], stored[0].encrypted_value)
        self.assertNotIn(secret['secret'], json.dumps(
            self.st.service.get(OWNER, self.st.ep, embed['embed_id'])))

    def test_no_key_authority_fails_closed(self):
        st = EmbedStack(ring=False)
        qid = st.s.q(OWNER, detail_by_region())
        with self.assertRaises(BIError):
            st.create('question', qid)


# ---------------------------------------------------------------------------
# dashboards: drills, downloads, paging
# ---------------------------------------------------------------------------
class DrillTests(Base):
    def setUp(self):
        super().setUp()
        self.embed, self.secret = self.board_embed(
            parameters=[{'id': 'region', 'mode': 'locked'}])
        self.eid = self.embed['embed_id']
        self.token_ = self.token(self.embed, self.secret,
                                 params={'region': 'east'})

    def drill(self, drill_id, row, filters=None, token=None):
        return self.st.post(self.eid, '/drill', token or self.token_, {
            'drill_id': drill_id, 'row': row, 'filters': filters})

    def test_only_drills_inside_the_embed_are_offered(self):
        view = self.st.get(self.eid, '/data',
                           self.token_).get_json()['data']
        self.assertEqual([d['id'] for d in view['drills']], ['to_region'])

    def test_drill_to_a_card_of_the_same_dashboard(self):
        response = self.drill('to_region', {'region': 'east',
                                            'product': 'apple'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(regions(response), ['east'])

    def test_a_locked_value_beats_the_clicked_row(self):
        response = self.drill('to_region', {'region': 'west'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(regions(response), ['east'])

    def test_drill_outside_the_embed_is_refused(self):
        denied(self, self.drill('to_other', {'product': 'apple'}))
        for drill_id in ('missing', '../x', ''):
            response = self.drill(drill_id, {'region': 'east'})
            self.assertIn(response.status_code, (400, 404))

    def test_drill_validates_its_input(self):
        for body in ({'drill_id': 7, 'row': {}}, {'drill_id': 'to_region'},
                     {'drill_id': 'to_region', 'row': [1]}):
            response = self.st.post(self.eid, '/drill', self.token_, body)
            self.assertEqual(response.status_code, 400)
        response = self.drill('to_region', {'region': 'east'},
                              {'region': 'west'})
        self.assertEqual(response.status_code, 400)


class DownloadAndPagingTests(Base):
    config = {'allow_downloads': True}

    def test_download_needs_the_setting_and_the_embed_flag(self):
        embed, secret = self.board_embed(
            display={'download': True})
        eid = embed['embed_id']
        token = self.token(embed, secret, params={'region': 'east'})
        run = self.card(embed, token).get_json()['data']
        response = self.st.post(eid, '/export', token, {
            'result_id': run['result_id'], 'format': 'csv'})
        if run['download'] is None:  # the question's export policy forbids
            denied(self, response)
        else:
            self.assertEqual(response.status_code, 200)
            self.assertIn('text/csv', response.headers['Content-Type'])
            self.assertIn('attachment', response.headers['Content-Disposition'])
            self.assertNotIn('Set-Cookie', response.headers)
        plain, psecret = self.make(
            'dashboard', self.did, name='Plain',
            parameters=[{'id': 'region', 'mode': 'locked'}])
        ptoken = self.token(plain, psecret, params={'region': 'east'})
        prun = self.card(plain, ptoken).get_json()['data']
        self.assertIsNone(prun['download'])
        denied(self, self.st.post(plain['embed_id'], '/export', ptoken, {
            'result_id': prun['result_id'], 'format': 'csv'}))

    def test_download_flag_is_refused_when_the_server_forbids_it(self):
        st = EmbedStack(config={'allow_downloads': False})
        qid = st.s.q(OWNER, detail_by_region())
        with self.assertRaisesRegex(BIError, 'ALLOW_DOWNLOADS'):
            st.create('question', qid, display={'download': True})

    def test_disabled_server_setting_wins_at_run_time(self):
        embed, secret = self.board_embed(display={'download': True})
        token = self.token(embed, secret, params={'region': 'east'})
        run = self.card(embed, token).get_json()['data']
        self.st.service.config['allow_downloads'] = False
        denied(self, self.st.post(embed['embed_id'], '/export', token, {
            'result_id': run['result_id'], 'format': 'csv'}))
        again = self.card(embed, token).get_json()['data']
        self.assertIsNone(again['download'])

    def test_page_size_and_row_caps(self):
        embed, secret = self.board_embed(
            parameters=[{'id': 'region', 'mode': 'editable'}],
            page_size=2, max_rows=3)
        eid = embed['embed_id']
        token = self.token(embed, secret)
        first = self.card(embed, token).get_json()['data']
        self.assertEqual(len(first['rows']), 2)
        self.assertIsNotNone(first['next_cursor'])
        big = self.card(embed, token, 'detail',
                        {'page_size': 500}).get_json()['data']
        self.assertLessEqual(len(big['rows']), 2)
        bad = self.card(embed, token, 'detail', {'page_size': 0})
        self.assertEqual(bad.status_code, 400)
        second = self.st.post(eid, '/page', token, {
            'result_id': first['result_id'],
            'cursor': first['next_cursor']})
        self.assertEqual(second.status_code, 200)
        page = second.get_json()['data']
        self.assertEqual(len(page['rows']), 1)
        self.assertIsNone(page['next_cursor'])
        self.assertTrue(page['truncated'])
        again = self.st.post(eid, '/page', token, {
            'result_id': first['result_id'], 'cursor': 'x'})
        self.assertEqual(again.status_code, 400)
        self.assertEqual(again.get_json()['error'], 'row_limit')

    def test_paging_requires_a_result_of_this_principal(self):
        embed, secret = self.board_embed()
        token = self.token(embed, secret, params={'region': 'east'})
        eid = embed['embed_id']
        for body in ({'result_id': 'nope', 'cursor': 'x'},
                     {'result_id': 5, 'cursor': 'x'},
                     {'result_id': 'nope'}, {}):
            response = self.st.post(eid, '/page', token, body)
            self.assertIn(response.status_code, (400, 404))


# ---------------------------------------------------------------------------
# management actions
# ---------------------------------------------------------------------------
class ManagementTests(Base):
    def setUp(self):
        super().setUp()
        self.did, self.parts = sales_board(self.st)
        self.svc = self.st.service

    def act(self, action, user=OWNER, **request):
        return self.svc.handle(action, request, user_id=user,
                               endpoint_id=self.st.ep,
                               server=SimpleNamespace(user_id=user))

    def spec(self, **extra):
        extra.setdefault('parameters', [{'id': 'region', 'mode': 'locked'}])
        return self.st.definition('dashboard', self.did, **extra)

    def created(self, **extra):
        return self.act('bi_embed_create', embed=self.spec(**extra))

    def test_the_catalog(self):
        catalog = self.act('bi_embed_catalog')
        self.assertTrue(catalog['available'])
        self.assertEqual(catalog['algorithm'], 'HS256')
        self.assertFalse(catalog['raw_sql_allowed'])
        self.assertFalse(catalog['downloads_allowed'])
        self.assertIn('user_id', catalog['reserved_claims'])

    def test_creation_is_disabled_and_the_secret_is_shown_once(self):
        made = self.created()
        embed, secret = made['embed'], made['secret']
        self.assertEqual(embed['status'], 'disabled')
        self.assertFalse(embed['enabled'])
        self.assertGreaterEqual(len(secret['secret']), 32)
        self.assertEqual(secret['algorithm'], 'HS256')
        self.assertEqual([k['kid'] for k in embed['keys']], [secret['kid']])
        shown = json.dumps(self.act('bi_embed_get', embed_id=embed['embed_id']))
        self.assertNotIn(secret['secret'], shown)
        listing = json.dumps(self.act(
            'bi_embed_list', resource_type='dashboard', resource_id=self.did))
        self.assertNotIn(secret['secret'], listing)
        self.assertEqual(embed['run_as']['principal'], 'embedding')
        self.assertIsNone(embed['run_as']['delegation'])
        # a disabled embed serves nothing
        token = self.st.token(embed['embed_id'], secret,
                              params={'region': 'east'})
        denied(self, self.st.get(embed['embed_id'], '/data', token))

    def test_enable_authorizes_the_owner_credentials(self):
        embed = self.created()['embed']
        enabled = self.act('bi_embed_enable', embed_id=embed['embed_id'],
                           delegation_days=7)
        self.assertEqual(enabled['status'], 'enabled')
        self.assertEqual(enabled['run_as']['delegation']['state'], 'active')
        with self.assertRaises(BIError):
            self.svc.handle('bi_embed_enable', {'embed_id': embed['embed_id']},
                            user_id=OWNER, endpoint_id=self.st.ep,
                            server=None)

    def test_manage_is_required_for_everything(self):
        embed = self.created()['embed']
        eid = embed['embed_id']
        for user in (VIEWER, EDITOR, STRANGER):
            for action, request in (
                    ('bi_embed_create', {'embed': self.spec(name='x')}),
                    ('bi_embed_list', {'resource_type': 'dashboard',
                                       'resource_id': self.did}),
                    ('bi_embed_get', {'embed_id': eid}),
                    ('bi_embed_update', {'embed_id': eid,
                                         'expected_revision': 1,
                                         'embed': self.spec()}),
                    ('bi_embed_enable', {'embed_id': eid}),
                    ('bi_embed_disable', {'embed_id': eid}),
                    ('bi_embed_rotate', {'embed_id': eid}),
                    ('bi_embed_retire_key', {'embed_id': eid}),
                    ('bi_embed_revoke', {'embed_id': eid}),
                    ('bi_embed_delete', {'embed_id': eid}),
                    ('bi_embed_mint', {'embed_id': eid}),
                    ('bi_embed_preview', {'embed_id': eid}),
                    ('bi_embed_check_token', {'embed_id': eid,
                                              'token': 'x'}),
                    ('bi_embed_stats', {'embed_id': eid})):
                with self.subTest(user=user, action=action):
                    with self.assertRaises(BIError):
                        self.act(action, user=user, **request)

    def test_a_manager_may_disable_and_revoke_but_not_read_secrets(self):
        self.st.s.share(OWNER, 'dashboard', self.did, MANAGER, 'manage')
        made = self.created()
        eid = made['embed']['embed_id']
        self.act('bi_embed_enable', embed_id=eid)
        seen = self.act('bi_embed_get', user=MANAGER, embed_id=eid)
        self.assertFalse(seen['is_owner'])
        self.assertEqual(seen['keys'], [])
        self.assertIsNone(seen['run_as'])
        with self.assertRaises(BIError):
            self.act('bi_embed_rotate', user=MANAGER, embed_id=eid)
        with self.assertRaises(BIError):
            self.act('bi_embed_mint', user=MANAGER, embed_id=eid)
        with self.assertRaises(BIError):
            self.act('bi_embed_enable', user=MANAGER, embed_id=eid)
        self.assertEqual(self.act('bi_embed_disable', user=MANAGER,
                                  embed_id=eid)['status'], 'disabled')
        self.assertEqual(self.act('bi_embed_revoke', user=MANAGER,
                                  embed_id=eid)['status'], 'revoked')

    def test_rotation_keeps_two_keys_and_shows_the_new_secret_once(self):
        made = self.created()
        eid = made['embed']['embed_id']
        first = made['secret']
        second = self.act('bi_embed_rotate', embed_id=eid)
        self.assertNotEqual(first['secret'], second['secret']['secret'])
        self.assertEqual({k['slot'] for k in second['embed']['keys']},
                         {'current', 'previous'})
        third = self.act('bi_embed_rotate', embed_id=eid)
        kids = {k['kid'] for k in third['embed']['keys']}
        self.assertEqual(kids, {second['secret']['kid'],
                                third['secret']['kid']})
        self.assertNotIn(first['kid'], kids)
        retired = self.act('bi_embed_retire_key', embed_id=eid)
        self.assertEqual([k['slot'] for k in retired['keys']], ['current'])

    def test_mint_produces_only_tokens_the_runtime_accepts(self):
        eid = self.created()['embed']['embed_id']
        self.act('bi_embed_enable', embed_id=eid)
        minted = self.act('bi_embed_mint', embed_id=eid,
                          params={'region': 'east'}, ttl_seconds=120)
        self.assertEqual(self.st.get(eid, '/data',
                                     minted['token']).status_code, 200)
        self.assertEqual(self.act('bi_embed_check_token', embed_id=eid,
                                  token=minted['token'])['valid'], True)
        for request in ({'params': {'region': 'east', 'extra': 1}},
                        {'claims': {'tenant_id': 1}},
                        {'ttl_seconds': 100000}, {'ttl_seconds': 0},
                        {'ttl_seconds': True}, {'ttl_seconds': '60'},
                        {'params': {'region': 'east'}, 'claims': {
                            'user_id': 1}}):
            with self.subTest(request):
                with self.assertRaises(BIError):
                    self.act('bi_embed_mint', embed_id=eid, **request)

    def test_check_token_explains_without_consuming(self):
        eid = self.created(require_jti=True)['embed']['embed_id']
        self.act('bi_embed_enable', embed_id=eid)
        minted = self.act('bi_embed_mint', embed_id=eid,
                          params={'region': 'east'})
        for _ in range(3):
            checked = self.act('bi_embed_check_token', embed_id=eid,
                               token=minted['token'])
            self.assertTrue(checked['valid'])
            self.assertTrue(checked['one_time'])
        self.assertEqual(self.st.get(eid, '/data',
                                     minted['token']).status_code, 200)
        bad = self.act('bi_embed_check_token', embed_id=eid, token='x.y.z')
        self.assertEqual(bad, {'valid': False, 'reason': 'malformed'})

    def test_preview_tokens_are_one_time_and_short_lived(self):
        eid = self.created()['embed']['embed_id']
        with self.assertRaises(BIError):  # not enabled yet
            self.act('bi_embed_preview', embed_id=eid,
                     params={'region': 'east'})
        self.act('bi_embed_enable', embed_id=eid)
        preview = self.act('bi_embed_preview', embed_id=eid,
                           params={'region': 'east'})
        self.assertLessEqual(preview['expires_in'], 120)
        self.assertEqual(self.st.frame(eid, preview['token']).status_code, 200)
        self.assertEqual(self.st.get(eid, '/data',
                                     preview['token']).status_code, 200)
        denied(self, self.st.get(eid, '/data', preview['token']))
        self.st.clock.advance(seconds=121)
        denied(self, self.st.post(eid, '/cards/detail/run',
                                  preview['token']))

    def test_update_is_checked_and_versioned(self):
        embed = self.created()['embed']
        eid = embed['embed_id']
        updated = self.act('bi_embed_update', embed_id=eid,
                           expected_revision=1,
                           embed=self.spec(name='Renamed',
                                           origins=[ORIGINS[0]]))
        self.assertEqual(updated['revision'], 2)
        self.assertEqual(updated['definition']['origins'], [ORIGINS[0]])
        from pgadmin.cdeadmin.bi import BIConflict
        with self.assertRaises(BIConflict):
            self.act('bi_embed_update', embed_id=eid, expected_revision=1,
                     embed=self.spec(name='Stale'))
        other_did, _ = sales_board(self.st)
        moved = dict(self.st.definition(
            'dashboard', other_did, name='Moved',
            parameters=[{'id': 'region', 'mode': 'locked'}]))
        with self.assertRaises(BIError):
            self.act('bi_embed_update', embed_id=eid, expected_revision=2,
                     embed=moved)

    def test_definition_validation(self):
        bad = {
            'no name': {'name': ''},
            'bad lifetime': {'max_token_lifetime_seconds': 5},
            'huge lifetime': {'max_token_lifetime_seconds': 10 ** 7},
            'bad mode': {'parameters': [{'id': 'region', 'mode': 'free'}]},
            'duplicate parameter': {'parameters': [
                {'id': 'region', 'mode': 'locked'},
                {'id': 'region', 'mode': 'editable'}]},
            'reserved claim': {'claims': [{'name': 'user_id'}]},
            'bad claim name': {'claims': [{'name': 'a b'}]},
            'bad theme': {'display': {'theme': 'neon'}},
            'page size': {'page_size': 10 ** 6},
            'max rows': {'max_rows': 0},
            'bad expiry': {'expires_at': 'tomorrow'},
            'resource type': {'resource': {'type': 'file', 'id': 'x',
                                           'revision': None}},
        }
        for label, extra in bad.items():
            with self.subTest(label):
                with self.assertRaises(BIError):
                    self.act('bi_embed_create', embed=self.spec(**extra))
        for value in (None, [], 'x', 5):
            with self.assertRaises(BIError):
                self.act('bi_embed_create', embed=value)

    def test_duplicate_names_and_the_per_user_limit(self):
        self.created(name='One')
        with self.assertRaises(BIError):
            self.created(name='One')
        self.svc.config['max_embeds_per_user'] = 2
        self.created(name='Two')
        with self.assertRaises(BIError):
            self.created(name='Three')

    def test_delete_requires_a_disabled_embed(self):
        eid = self.created()['embed']['embed_id']
        self.act('bi_embed_enable', embed_id=eid)
        with self.assertRaises(BIError):
            self.act('bi_embed_delete', embed_id=eid)
        self.act('bi_embed_disable', embed_id=eid)
        self.assertEqual(self.act('bi_embed_delete', embed_id=eid),
                         {'embed_id': eid, 'deleted': True})
        with self.assertRaises(BIError):
            self.act('bi_embed_get', embed_id=eid)

    def test_revoke_is_permanent(self):
        made = self.created()
        eid = made['embed']['embed_id']
        self.act('bi_embed_enable', embed_id=eid)
        revoked = self.act('bi_embed_revoke', embed_id=eid)
        self.assertEqual(revoked['status'], 'revoked')
        self.assertEqual(revoked['keys'], [])
        self.assertEqual(revoked['run_as']['delegation']['state'], 'revoked')
        for action in ('bi_embed_enable', 'bi_embed_rotate', 'bi_embed_mint',
                       'bi_embed_update'):
            with self.subTest(action):
                with self.assertRaises(BIError):
                    self.act(action, embed_id=eid, expected_revision=1,
                             embed=self.spec())

    def test_archived_content_cannot_be_embedded(self):
        self.st.s.dashboards.repository.rows[self.did].status = 'archived'
        with self.assertRaises(BIError):
            self.created()

    def test_stats_count_views_without_personal_data(self):
        made = self.created()
        eid = made['embed']['embed_id']
        self.act('bi_embed_enable', embed_id=eid)
        token = self.st.token(eid, made['secret'], params={'region': 'east'})
        self.st.get(eid, '/data', token)
        self.st.get(eid, '/data', token)
        self.st.post(eid, '/cards/detail/run', token)
        denied(self, self.st.get(eid, '/data', 'bad'))
        stats = self.act('bi_embed_stats', embed_id=eid, days=7)
        self.assertEqual(stats['totals'], {'views': 2, 'card_runs': 1,
                                           'errors': 0})
        self.assertEqual(len(stats['series']), 1)
        self.assertEqual(set(stats['series'][0]),
                         {'day', 'views', 'card_runs', 'errors'})
        for days in (0, 366, True, '7'):
            with self.assertRaises(BIError):
                self.act('bi_embed_stats', embed_id=eid, days=days)

    def test_management_events_are_audited_without_secrets(self):
        made = self.created()
        eid = made['embed']['embed_id']
        self.act('bi_embed_enable', embed_id=eid)
        self.act('bi_embed_rotate', embed_id=eid)
        minted = self.act('bi_embed_mint', embed_id=eid,
                          params={'region': 'east'})
        self.act('bi_embed_disable', embed_id=eid)
        self.act('bi_embed_revoke', embed_id=eid)
        events = self.st.s.grants.audit_list('dashboard', self.did)
        actions = [e['action'] for e in events]
        for action in ('embed.create', 'embed.enable', 'embed.rotate',
                       'embed.mint', 'embed.disable', 'embed.revoke'):
            self.assertIn(action, actions)
        text = json.dumps(events, default=str)
        self.assertNotIn(made['secret']['secret'], text)
        self.assertNotIn(minted['token'], text)
        self.assertNotIn('eyJ', text)

    def test_unknown_actions_and_bad_requests(self):
        for action in ('bi_embed_nope', 'bi_dashboard_get', ''):
            with self.assertRaises(BIError):
                self.svc.handle(action, {}, user_id=OWNER,
                                endpoint_id=self.st.ep)
        with self.assertRaises(BIError):
            self.svc.handle('bi_embed_get', 'x', user_id=OWNER,
                            endpoint_id=self.st.ep)
        for ident in (None, 5, 'x', eh.random_id()):
            with self.assertRaises(BIError):
                self.act('bi_embed_get', embed_id=ident)

    def test_another_endpoint_cannot_reach_an_embed(self):
        eid = self.created()['embed']['embed_id']
        with self.assertRaises(BIError):
            self.svc.get(OWNER, 'other-endpoint', eid)

    def test_disabled_switch_hides_the_feature(self):
        st = EmbedStack(enabled=False)
        qid = st.s.q(OWNER, detail_by_region())
        self.assertFalse(st.service.available)
        with self.assertRaises(BIError):
            st.service.create(OWNER, st.ep, st.definition('question', qid))
        self.assertFalse(st.service.handle(
            'bi_embed_catalog', {}, user_id=OWNER,
            endpoint_id=st.ep)['available'])

    def test_rotating_the_encryption_key_keeps_tokens_valid(self):
        made = self.created()
        eid = made['embed']['embed_id']
        self.act('bi_embed_enable', embed_id=eid)
        token = self.st.token(eid, made['secret'], params={'region': 'east'})
        ring = self.st.ring
        before = self.st.repo.keys(eid)[0].encrypted_value
        summary = self.svc.rotate_encryption()
        self.assertEqual(summary['active_key_id'], ring.active_key_id)
        self.assertEqual(self.st.repo.keys(eid)[0].encrypted_value, before)
        self.assertEqual(self.st.get(eid, '/data', token).status_code, 200)

    def test_a_ciphertext_moved_to_another_embed_does_not_verify(self):
        a = self.created(name='A')
        b = self.created(name='B')
        a_row = self.st.repo.keys(a['embed']['embed_id'])[0]
        b_row = self.st.repo.keys(b['embed']['embed_id'])[0]
        b_row.encrypted_value = a_row.encrypted_value
        token = self.st.token(b['embed']['embed_id'], a['secret'],
                              params={'region': 'east'})
        self.act('bi_embed_enable', embed_id=b['embed']['embed_id'])
        denied(self, self.st.get(b['embed']['embed_id'], '/data', token))


# ---------------------------------------------------------------------------
# the real tables
# ---------------------------------------------------------------------------
class MigrationTests(unittest.TestCase):
    @staticmethod
    def load(name):
        path = ROOT / f'web/migrations/versions/{name}_.py'
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @unittest.skipUnless(MIGRATION_DEPENDENCIES, 'alembic is unavailable')
    def test_chain_constraints_and_round_trip(self):
        previous = self.load('cde_bi_alerts_v1')
        embeds = self.load('cde_bi_embeds_v1')
        self.assertEqual(embeds.down_revision, previous.revision)
        engine = sa.create_engine('sqlite:///:memory:')
        with engine.connect() as connection:
            metadata = sa.MetaData()
            sa.Table('user', metadata,
                     sa.Column('id', sa.Integer(), primary_key=True))
            sa.Table('cde_endpoint', metadata,
                     sa.Column('id', sa.String(36), primary_key=True))
            metadata.create_all(connection)
            embeds.op = Operations(MigrationContext.configure(connection))
            embeds.upgrade()
            tables = {'cde_bi_embed', 'cde_bi_embed_key',
                      'cde_bi_embed_delegation', 'cde_bi_embed_credential',
                      'cde_bi_embed_jti', 'cde_bi_embed_stat'}
            self.assertTrue(tables <= set(
                sa.inspect(connection).get_table_names()))
            connection.commit()
            connection.execute(sa.text('PRAGMA foreign_keys=ON'))
            connection.execute(sa.text('INSERT INTO user (id) VALUES (1)'))
            connection.execute(sa.text(
                "INSERT INTO cde_endpoint (id) VALUES ('ep')"))
            table = sa.Table('cde_bi_embed', sa.MetaData(),
                             autoload_with=connection)
            now = datetime.now(timezone.utc)
            base = dict(
                user_id=1, endpoint_id='ep', name='n',
                resource_type='dashboard', resource_id='d',
                status='disabled', revision=1, definition='{}',
                created_at=now, updated_at=now)
            connection.execute(table.insert().values(id='a', **base))
            bad = {
                'duplicate name': dict(id='b', **base),
                'status': dict(id='c', **{**base, 'status': 'gone',
                                          'name': 'k'}),
                'resource': dict(id='d', **{**base, 'resource_type': 'file',
                                            'name': 'l'}),
                'user': dict(id='e', **{**base, 'user_id': 9, 'name': 'm'}),
                'endpoint': dict(id='f', **{**base, 'endpoint_id': 'zz',
                                            'name': 'o'}),
            }
            for label, values in bad.items():
                with self.subTest(label):
                    with self.assertRaises(sa.exc.IntegrityError):
                        connection.execute(table.insert().values(**values))
            key = sa.Table('cde_bi_embed_key', sa.MetaData(),
                           autoload_with=connection)
            slot = dict(embed_id='a', key_id='r', encrypted_value='x',
                        created_at=now)
            connection.execute(key.insert().values(
                id='1', kid='k1', slot='current', **slot))
            for label, values in {
                    'second current': dict(id='2', kid='k2', slot='current'),
                    'duplicate kid': dict(id='3', kid='k1', slot='previous'),
                    'bad slot': dict(id='4', kid='k4', slot='future'),
                    'no embed': dict(id='5', kid='k5', slot='previous',
                                     embed_id='zz')}.items():
                with self.subTest(label):
                    with self.assertRaises(sa.exc.IntegrityError):
                        connection.execute(key.insert().values(
                            **{**slot, **values}))
            jti = sa.Table('cde_bi_embed_jti', sa.MetaData(),
                           autoload_with=connection)
            connection.execute(jti.insert().values(
                embed_id='a', jti='j', expires_at=now))
            with self.assertRaises(sa.exc.IntegrityError):
                connection.execute(jti.insert().values(
                    embed_id='a', jti='j', expires_at=now))
            connection.execute(sa.text("DELETE FROM cde_bi_embed"))
            for name in ('cde_bi_embed_key', 'cde_bi_embed_jti'):
                count = connection.execute(
                    sa.text(f'SELECT COUNT(*) FROM {name}')).scalar()
                self.assertEqual(count, 0, name)
            embeds.downgrade()
            self.assertFalse(tables & set(
                sa.inspect(connection).get_table_names()))
            embeds.upgrade()
            self.assertTrue(tables <= set(
                sa.inspect(connection).get_table_names()))

    def test_schema_version_is_not_bumped(self):
        source = (ROOT / 'web/pgadmin/model/__init__.py').read_text(
            encoding='utf-8')
        self.assertRegex(source, r'SCHEMA_VERSION\s*=\s*59\b')
        for table in ('cde_bi_embed', 'cde_bi_embed_key',
                      'cde_bi_embed_jti', 'cde_bi_embed_stat',
                      'cde_bi_embed_delegation', 'cde_bi_embed_credential'):
            self.assertIn(f"'{table}'", source)


try:
    from flask import Flask
    import flask_sqlalchemy  # noqa: F401
    from test_cdeadmin_endpoint_persistence import load_model
    MODEL_DEPENDENCIES = MIGRATION_DEPENDENCIES
except ImportError:  # pragma: no cover
    MODEL_DEPENDENCIES = False


def bound(cls, **attrs):
    instance = cls.__new__(cls)
    instance.__dict__.update(attrs)
    return instance


@unittest.skipUnless(MODEL_DEPENDENCIES, 'SQLAlchemy models are unavailable')
class DatabaseRepositoryTests(unittest.TestCase):
    """The real ``DatabaseEmbedRepository`` over an on-disk SQLite file."""

    def setUp(self):
        from pgadmin.cdeadmin.bi.embed_store import DatabaseEmbedRepository
        self.temporary = tempfile.TemporaryDirectory()
        self.model = load_model()
        m = self.model
        self.app = Flask('cdeadmin-bi-embed-test')
        self.app.config['SQLALCHEMY_DATABASE_URI'] = (
            f'sqlite:///{Path(self.temporary.name) / "config.db"}')
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        m.db.init_app(self.app)
        self.context = self.app.app_context()
        self.context.push()
        m.db.create_all()
        m.db.session.execute(m.User.__table__.insert(), {
            'id': 1, 'username': 'owner', 'active': True,
            'auth_source': 'internal1', 'fs_uniquifier': 'u1',
            'locked': False})
        m.db.session.add(m.ServerGroup(id=1, user_id=1, name='G'))
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
        self.repo = bound(DatabaseEmbedRepository, db=m.db, embed=m.BIEmbed,
                          key=m.BIEmbedKey, jti=m.BIEmbedJti,
                          stat=m.BIEmbedStat)
        self.now = datetime(2026, 3, 2, 9, 0)

    def tearDown(self):
        self.model.db.session.remove()
        self.model.db.drop_all()
        for engine in self.model.db.engines.values():
            engine.dispose()
        self.context.pop()
        self.temporary.cleanup()

    def row(self, ident='11111111-1111-4111-8111-111111111111', **values):
        base = dict(
            id=ident, user_id=1, endpoint_id=self.ep, name='n',
            resource_type='dashboard', resource_id='d', status='disabled',
            revision=1, definition='{}', created_at=self.now,
            updated_at=self.now)
        base.update(values)
        return self.repo.add(self.repo.new(**base))

    def test_embed_crud_and_unique_names(self):
        row = self.row()
        self.assertEqual(self.repo.get(row.id).name, 'n')
        self.assertIsNone(self.repo.get('short'))
        self.assertIsNone(self.repo.get(None))
        with self.assertRaises(BIError):
            self.row('22222222-2222-4222-8222-222222222222')
        other = self.row('33333333-3333-4333-8333-333333333333', name='m',
                         resource_id='e')
        self.assertEqual(self.repo.count(1, self.ep), 2)
        self.assertEqual([r.id for r in self.repo.list(
            self.ep, resource_type='dashboard', resource_id='e')],
            [other.id])
        other.name = 'n'
        with self.assertRaises(BIError):
            self.repo.save(other)
        self.model.db.session.rollback()

    def test_two_key_slots(self):
        row = self.row()
        for kid in ('k1', 'k2', 'k3'):
            self.repo.install_key(row.id, kid=kid, key_id='ring',
                                  encrypted_value='v-' + kid, now=self.now)
        keys = {k.kid: k.slot for k in self.repo.keys(row.id)}
        self.assertEqual(keys, {'k2': 'previous', 'k3': 'current'})
        self.assertEqual(self.repo.drop_previous(row.id), 1)
        self.assertEqual(self.repo.drop_keys(row.id), 1)
        self.assertEqual(self.repo.keys(row.id), [])

    def test_one_time_ids(self):
        row = self.row()
        later = self.now + timedelta(minutes=5)
        self.assertFalse(self.repo.jti_consumed(row.id, 'j1', self.now))
        self.assertTrue(self.repo.consume_jti(row.id, 'j1', later, self.now))
        self.assertTrue(self.repo.jti_consumed(row.id, 'j1', self.now))
        self.assertFalse(self.repo.consume_jti(row.id, 'j1', later, self.now))
        after = later + timedelta(seconds=1)
        self.assertFalse(self.repo.jti_consumed(row.id, 'j1', after))
        self.assertTrue(self.repo.consume_jti(
            row.id, 'j1', after + timedelta(minutes=5), after))

    def test_counters(self):
        row = self.row()
        self.repo.bump(row.id, '2026-03-02', views=1)
        self.repo.bump(row.id, '2026-03-02', views=2, card_runs=3)
        self.repo.bump(row.id, '2026-03-03', errors=1)
        self.assertEqual(self.repo.stats(row.id, '2026-03-02'), [
            {'day': '2026-03-02', 'views': 3, 'card_runs': 3, 'errors': 0},
            {'day': '2026-03-03', 'views': 0, 'card_runs': 0, 'errors': 1}])
        self.assertEqual(len(self.repo.stats(row.id, '2026-03-03')), 1)

    def test_purge_and_delete_remove_everything(self):
        first = self.row()
        second = self.row('33333333-3333-4333-8333-333333333333', name='m')
        for row in (first, second):
            self.repo.install_key(row.id, kid='k' + row.id[:3], key_id='r',
                                  encrypted_value='v', now=self.now)
            self.repo.consume_jti(row.id, 'j', self.now + timedelta(days=1),
                                  self.now)
            self.repo.bump(row.id, '2026-03-02', views=1)
        self.assertEqual(sorted(self.repo.purge_resource('dashboard', 'd')),
                         sorted([first.id, second.id]))
        m = self.model
        for table in (m.BIEmbed, m.BIEmbedKey, m.BIEmbedJti, m.BIEmbedStat):
            self.assertEqual(table.query.count(), 0, table.__name__)

    def test_delete_one(self):
        row = self.row()
        self.repo.install_key(row.id, kid='k1', key_id='r',
                              encrypted_value='v', now=self.now)
        self.repo.bump(row.id, '2026-03-02', views=1)
        self.repo.delete(row)
        self.assertIsNone(self.repo.get(row.id))
        self.assertEqual(self.model.BIEmbedKey.query.count(), 0)
        self.assertEqual(self.model.BIEmbedStat.query.count(), 0)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
