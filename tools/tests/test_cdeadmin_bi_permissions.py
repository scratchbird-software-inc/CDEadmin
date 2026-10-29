##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""BI sharing and permissions (docs/en_US/bi_permissions.rst).

A matrix of owner / viewer / editor / manager / no-grant / role-member
across direct grants, collection inheritance and overrides, dashboards with
unshared cards, run-as-runner behaviour on real SQLite/DuckDB, revision
actors, ownership transfer, existence non-leak, the audit trail and the
cache key.  A final class drives the real SQLAlchemy models and migration.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

import bi_permissions_harness as ph
from bi_permissions_harness import (
    ADMIN, ANALYST, EDITOR, MANAGER, OWNER, STRANGER, VIEWER, SharedStack,
    board,
)
from bi_live_harness import ROOT, duckdb

from pgadmin.cdeadmin.bi import BIError, BIPermissionDenied
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from test_cdeadmin_bi_dashboards import detail_by_region
from test_cdeadmin_bi_execution import region_question, sql_question
from test_cdeadmin_bi_saved_questions import MemoryBI, MemorySemantic

try:
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    MIGRATION_DEPENDENCIES = True
except ImportError:  # pragma: no cover
    MIGRATION_DEPENDENCIES = False

ENGINES = ['sqlite'] + (['duckdb'] if duckdb is not None else [])
SECRET_SQL = ("SELECT region, SUM(amount) AS revenue FROM sales "
              "WHERE product <> 'zzz_hidden_filter' GROUP BY region")
HIDDEN = 'zzz_hidden_filter'


def secret_question(name='Secret revenue'):
    question = sql_question(SECRET_SQL)
    question['name'] = name
    return question


def builder(name, **extra):
    value = detail_by_region()
    value['name'] = name
    value.update(extra)
    return value


def table(result):
    """The rows of a run response."""
    return result['page']['view_model']['rows']


def outcome(call):
    """``ok`` / ``unavailable`` / ``denied`` / other message for a call."""
    try:
        call()
    except BIPermissionDenied:
        return 'denied'
    except BIError as exc:
        return 'unavailable' if 'unavailable' in str(exc) else str(exc)
    return 'ok'


class StackCase(unittest.TestCase):
    def setUp(self):
        self.s = SharedStack('sqlite')
        self.ep = self.s.endpoint_id
        self.bi = self.s.bi
        self.access = self.s.bi.access


# ---------------------------------------------------------------------------
class OwnerOnlyDefaultTests(StackCase):
    """No grants: behaviour is exactly the old owner-only behaviour."""

    def test_other_users_see_nothing_and_errors_are_uniform(self):
        qid = self.s.q(OWNER, builder('Mine'))
        cid = self.bi.create_collection(OWNER, {'name': 'Folder'},
                                        self.ep)['collection_id']
        did = self.s.dashboards.create(
            OWNER, self.ep, board([qid]))['dashboard_id']
        ghost = str(uuid.uuid4())
        for user in (VIEWER, STRANGER, ADMIN):
            self.assertEqual(self.bi.list_questions(user, self.ep), [])
            self.assertEqual(self.s.dashboards.list(user, self.ep), [])
            self.assertEqual(self.bi.list_collections(user, self.ep), [])
            self.assertEqual(self.bi.shared_with_me(user, self.ep)[
                'questions'], [])
            pairs = [
                (lambda i: self.bi.get_question(user, self.ep, i),
                 'question'),
                (lambda i: self.bi.history(user, self.ep, i), 'question'),
                (lambda i: self.bi.revision(user, self.ep, i, 1),
                 'question'),
                (lambda i: self.bi.update_question(
                    user, self.ep, i, 1, builder('x')), 'question'),
                (lambda i: self.bi.set_status(
                    user, self.ep, i, 1, 'archived'), 'question'),
                (lambda i: self.bi.move_question(user, self.ep, i, 1, None),
                 'question'),
                (lambda i: self.bi.clone_question(user, self.ep, i, 'c'),
                 'question'),
                (lambda i: self.bi.delete_question(user, self.ep, i, 1),
                 'question'),
                (lambda i: self.s.run_as(user, question_id=i), 'question'),
                (lambda i: self.bi.compile(
                    self.s.provider, user, self.ep, question_id=i),
                 'question'),
                (lambda i: self.s.dashboards.get(user, self.ep, i),
                 'dashboard'),
                (lambda i: self.s.dashboards.delete(user, self.ep, i, 1),
                 'dashboard'),
                (lambda i: self.s.dashboards.history(user, self.ep, i),
                 'dashboard'),
                (lambda i: self.access.list_grants(
                    user, 'question', self.ep, i), 'question'),
                (lambda i: self.access.effective_access(
                    user, 'question', self.ep, i), 'question'),
            ]
            real = {'question': qid, 'dashboard': did}
            for call, kind in pairs:
                with self.subTest(user=user, kind=kind):
                    with self.assertRaises(BIError) as hidden:
                        call(real[kind])
                    with self.assertRaises(BIError) as missing:
                        call(ghost)
                    # existence is not disclosed: same text, same type
                    self.assertEqual(str(hidden.exception),
                                     str(missing.exception))
                    self.assertIs(type(hidden.exception),
                                  type(missing.exception))
            for call in (
                    lambda: self.bi.update_collection(
                        user, cid, {'name': 'x'}, self.ep),
                    lambda: self.bi.delete_collection(user, cid, self.ep)):
                with self.assertRaisesRegex(BIError, 'unavailable'):
                    call()

    def test_owner_has_manage_everywhere(self):
        qid = self.s.q(OWNER, builder('Mine'))
        self.assertEqual(self.access.level(OWNER, 'question', self.ep, qid),
                         'manage')
        self.assertEqual(self.bi.get_question(OWNER, self.ep, qid)['access'],
                         'manage')
        self.assertTrue(self.bi.get_question(OWNER, self.ep, qid)[
            'is_owner'])

    def test_wrong_endpoint_is_unavailable_even_to_the_owner(self):
        qid = self.s.q(OWNER, builder('Mine'))
        with self.assertRaisesRegex(BIError, 'unavailable'):
            self.bi.get_question(OWNER, 'other-endpoint', qid)


# ---------------------------------------------------------------------------
class DirectGrantMatrixTests(StackCase):
    """Operation x principal matrix on a directly shared builder question."""

    # operation: (needed level, call)
    def operations(self):
        return {
            'get': lambda u, q: self.bi.get_question(u, self.ep, q),
            'run': lambda u, q: self.s.run_as(u, question_id=q),
            'history': lambda u, q: self.bi.history(u, self.ep, q),
            'compile': lambda u, q: self.bi.compile(
                self.s.provider, u, self.ep, question_id=q),
            'clone': lambda u, q: self.bi.clone_question(
                u, self.ep, q, 'copy ' + uuid.uuid4().hex),
            'update': lambda u, q: self.bi.update_question(
                u, self.ep, q, 1, builder(
                    self.bi.repository.qs[q].name, description='v2')),
            'archive': lambda u, q: self.bi.set_status(
                u, self.ep, q, 1, 'archived'),
            'delete': lambda u, q: self.bi.delete_question(
                u, self.ep, q, 1),
            'grants': lambda u, q: self.access.list_grants(
                u, 'question', self.ep, q),
        }

    EXPECTED = {
        #            owner  manager editor viewer stranger
        'get':      ('ok', 'ok', 'ok', 'ok', 'unavailable'),
        'run':      ('ok', 'ok', 'ok', 'ok', 'unavailable'),
        'history':  ('ok', 'ok', 'ok', 'ok', 'unavailable'),
        'compile':  ('ok', 'ok', 'ok', 'ok', 'unavailable'),
        'clone':    ('ok', 'ok', 'ok', 'ok', 'unavailable'),
        'update':   ('ok', 'ok', 'ok', 'denied', 'unavailable'),
        'archive':  ('ok', 'ok', 'ok', 'denied', 'unavailable'),
        'delete':   ('ok', 'ok', 'denied', 'denied', 'unavailable'),
        'grants':   ('ok', 'ok', 'denied', 'denied', 'unavailable'),
    }
    USERS = (OWNER, MANAGER, EDITOR, VIEWER, STRANGER)

    def test_matrix(self):
        for name, call in self.operations().items():
            for index, user in enumerate(self.USERS):
                with self.subTest(operation=name, user=ph.USERS[user]):
                    qid = self.s.q(OWNER, builder(f'Q {name} {user}'))
                    self.s.share(OWNER, 'question', qid, MANAGER, 'manage')
                    self.s.share(OWNER, 'question', qid, EDITOR, 'edit')
                    self.s.share(OWNER, 'question', qid, VIEWER, 'view')
                    self.assertEqual(
                        outcome(lambda: call(user, qid)),
                        self.EXPECTED[name][index])

    def test_levels_report_effective_access(self):
        qid = self.s.q(OWNER, builder('Levels'))
        self.s.share(OWNER, 'question', qid, VIEWER, 'view')
        self.s.share(OWNER, 'question', qid, EDITOR, 'edit')
        self.s.share(OWNER, 'question', qid, MANAGER, 'manage')
        seen = {u: self.access.effective_access(
            u, 'question', self.ep, qid)['level']
            for u in (OWNER, VIEWER, EDITOR, MANAGER)}
        self.assertEqual(seen, {OWNER: 'manage', VIEWER: 'view',
                                EDITOR: 'edit', MANAGER: 'manage'})
        with self.assertRaisesRegex(BIError, 'unavailable'):
            self.access.effective_access(STRANGER, 'question', self.ep, qid)

    def test_grant_for_another_endpoint_does_not_apply(self):
        qid = self.s.q(OWNER, builder('Scoped'))
        # the grant is recorded for a different endpoint id
        self.s.grants.add(endpoint_id='other', kind='question',
                          resource_id=qid, principal_type='user',
                          principal_id=VIEWER, level='manage',
                          actor_id=OWNER)
        with self.assertRaisesRegex(BIError, 'unavailable'):
            self.bi.get_question(VIEWER, self.ep, qid)

    def test_revoking_removes_access_immediately(self):
        qid = self.s.q(OWNER, builder('Revoked'))
        grant = self.s.share(OWNER, 'question', qid, VIEWER, 'view')
        self.bi.get_question(VIEWER, self.ep, qid)
        self.access.remove_grant(OWNER, 'question', self.ep, qid,
                                 grant['grant_id'])
        with self.assertRaisesRegex(BIError, 'unavailable'):
            self.bi.get_question(VIEWER, self.ep, qid)

    def test_delete_removes_grants_and_overrides(self):
        qid = self.s.q(OWNER, builder('Gone'))
        self.s.share(OWNER, 'question', qid, VIEWER, 'view')
        self.access.set_inherit(OWNER, 'question', self.ep, qid, False)
        self.bi.delete_question(OWNER, self.ep, qid, 1)
        self.assertEqual(self.s.grants.rows, {})
        self.assertEqual(self.s.grants.override_rows, set())


# ---------------------------------------------------------------------------
class CollectionInheritanceTests(StackCase):
    def setUp(self):
        super().setUp()
        self.top = self.bi.create_collection(
            OWNER, {'name': 'Top'}, self.ep)['collection_id']
        self.sub = self.bi.create_collection(
            OWNER, {'name': 'Sub', 'parent_id': self.top},
            self.ep)['collection_id']
        self.q = self.s.q(OWNER, builder('Inner', collection_id=self.sub))
        self.d = self.s.dashboards.create(OWNER, self.ep, board(
            [self.q], collection_id=self.sub))['dashboard_id']

    def level(self, user, kind, rid):
        return self.access.level(user, kind, self.ep, rid)

    def test_collection_grant_flows_down_the_tree(self):
        self.s.share(OWNER, 'collection', self.top, VIEWER, 'view')
        self.s.share(OWNER, 'collection', self.top, EDITOR, 'edit')
        for kind, rid in (('collection', self.sub), ('question', self.q),
                          ('dashboard', self.d)):
            self.assertEqual(self.level(VIEWER, kind, rid), 'view')
            self.assertEqual(self.level(EDITOR, kind, rid), 'edit')
            self.assertIsNone(self.level(STRANGER, kind, rid))
        # and the viewer can actually use it
        self.assertEqual(outcome(lambda: self.s.run_as(
            VIEWER, question_id=self.q)), 'ok')
        self.assertEqual(outcome(lambda: self.bi.update_question(
            VIEWER, self.ep, self.q, 1, builder('x'))), 'denied')
        self.assertEqual(outcome(lambda: self.bi.update_question(
            EDITOR, self.ep, self.q, 1, builder(
                'Inner', collection_id=self.sub, description='e'))), 'ok')

    def test_override_stops_inheritance_for_a_child(self):
        self.s.share(OWNER, 'collection', self.top, VIEWER, 'view')
        self.access.set_inherit(OWNER, 'question', self.ep, self.q, False)
        self.assertIsNone(self.level(VIEWER, 'question', self.q))
        # siblings that did not override still inherit
        self.assertEqual(self.level(VIEWER, 'dashboard', self.d), 'view')
        self.assertEqual(self.level(VIEWER, 'collection', self.sub), 'view')
        # a direct grant on the overriding child still works
        self.s.share(OWNER, 'question', self.q, VIEWER, 'view')
        self.assertEqual(self.level(VIEWER, 'question', self.q), 'view')
        self.assertEqual(self.level(OWNER, 'question', self.q), 'manage')
        # lifting the override restores inheritance
        self.access.set_inherit(OWNER, 'question', self.ep, self.q, True)
        self.assertEqual(self.level(VIEWER, 'question', self.q), 'view')

    def test_override_on_a_subcollection_cuts_what_flows_from_above(self):
        self.s.share(OWNER, 'collection', self.top, VIEWER, 'view')
        self.s.share(OWNER, 'collection', self.sub, EDITOR, 'edit')
        self.access.set_inherit(OWNER, 'collection', self.ep, self.sub, False)
        self.assertEqual(self.level(VIEWER, 'collection', self.top), 'view')
        for kind, rid in (('collection', self.sub), ('question', self.q),
                          ('dashboard', self.d)):
            self.assertIsNone(self.level(VIEWER, kind, rid))
            # the sub-collection's own grants still flow into its contents
            self.assertEqual(self.level(EDITOR, kind, rid), 'edit')

    def test_effective_access_is_the_maximum(self):
        self.s.share(OWNER, 'collection', self.top, VIEWER, 'edit')
        self.s.share(OWNER, 'question', self.q, VIEWER, 'view')
        self.assertEqual(self.level(VIEWER, 'question', self.q), 'edit')
        self.s.share(OWNER, 'question', self.q, EDITOR, 'manage')
        self.s.share(OWNER, 'collection', self.top, EDITOR, 'view')
        self.assertEqual(self.level(EDITOR, 'question', self.q), 'manage')
        sources = self.access.effective_access(
            VIEWER, 'question', self.ep, self.q)['sources']
        self.assertEqual((sources['direct'], sources['inherited'],
                          sources['inherited_from']),
                         ('view', 'edit', self.top))

    def test_collection_grant_for_another_endpoint_does_not_flow(self):
        self.s.grants.add(endpoint_id='other', kind='collection',
                          resource_id=self.top, principal_type='user',
                          principal_id=VIEWER, level='manage',
                          actor_id=OWNER)
        self.assertIsNone(self.level(VIEWER, 'question', self.q))
        self.assertIsNone(self.level(VIEWER, 'collection', self.sub))

    def test_owner_of_a_collection_manages_items_filed_in_it(self):
        self.s.share(OWNER, 'collection', self.top, EDITOR, 'edit')
        mine = self.s.q(EDITOR, builder('By editor', collection_id=self.sub))
        self.assertEqual(self.level(OWNER, 'question', mine), 'manage')
        self.assertEqual(self.level(EDITOR, 'question', mine), 'manage')
        # the editor can opt out for their own item
        self.access.set_inherit(EDITOR, 'question', self.ep, mine, False)
        self.assertIsNone(self.level(OWNER, 'question', mine))

    def test_filing_into_a_collection_needs_edit_on_it(self):
        self.s.share(OWNER, 'collection', self.top, VIEWER, 'view')
        self.s.share(OWNER, 'collection', self.top, EDITOR, 'edit')
        self.assertEqual(outcome(lambda: self.s.q(VIEWER, builder(
            'v', collection_id=self.sub))), 'denied')
        self.assertEqual(outcome(lambda: self.s.q(EDITOR, builder(
            'e', collection_id=self.sub))), 'ok')
        self.assertEqual(outcome(lambda: self.s.q(STRANGER, builder(
            's', collection_id=self.sub))), 'unavailable')
        self.assertEqual(outcome(lambda: self.bi.create_collection(
            VIEWER, {'name': 'n', 'parent_id': self.sub}, self.ep)),
            'denied')
        self.assertEqual(outcome(lambda: self.bi.create_collection(
            EDITOR, {'name': 'n', 'parent_id': self.sub}, self.ep)), 'ok')
        self.assertEqual(outcome(lambda: self.s.dashboards.create(
            VIEWER, self.ep, board([], name='dv', collection_id=self.sub))),
            'denied')

    def test_moving_needs_edit_on_both_sides(self):
        self.s.share(OWNER, 'collection', self.sub, EDITOR, 'edit')
        elsewhere = self.bi.create_collection(
            OWNER, {'name': 'Elsewhere'}, self.ep)['collection_id']
        self.assertEqual(outcome(lambda: self.bi.move_question(
            EDITOR, self.ep, self.q, 1, elsewhere)), 'unavailable')
        self.s.share(OWNER, 'collection', elsewhere, EDITOR, 'view')
        self.assertEqual(outcome(lambda: self.bi.move_question(
            EDITOR, self.ep, self.q, 1, elsewhere)), 'denied')
        self.s.share(OWNER, 'collection', elsewhere, MANAGER, 'edit')
        grant = self.s.grants.find(self.ep, 'collection', elsewhere, 'user',
                                   EDITOR)
        self.access.update_grant(OWNER, 'collection', self.ep, elsewhere,
                                 grant['grant_id'], 'edit')
        self.assertEqual(outcome(lambda: self.bi.move_question(
            EDITOR, self.ep, self.q, 1, elsewhere)), 'ok')

    def test_collection_lifecycle_levels(self):
        self.s.share(OWNER, 'collection', self.top, EDITOR, 'edit')
        self.s.share(OWNER, 'collection', self.top, MANAGER, 'manage')
        rename = {'name': 'Renamed', 'parent_id': None}
        self.assertEqual(outcome(lambda: self.bi.update_collection(
            EDITOR, self.top, rename, self.ep)), 'ok')
        # re-parenting is a manage action
        self.assertEqual(outcome(lambda: self.bi.update_collection(
            EDITOR, self.sub, {'name': 'Sub', 'parent_id': None},
            self.ep)), 'denied')
        self.assertEqual(outcome(lambda: self.bi.delete_collection(
            EDITOR, self.top, self.ep)), 'denied')
        # deletion also needs it to be empty, whoever owns the contents
        self.assertIn('empty', outcome(lambda: self.bi.delete_collection(
            MANAGER, self.top, self.ep)))
        self.assertIn('empty', outcome(lambda: self.bi.delete_collection(
            OWNER, self.sub, self.ep)))

    def test_shared_with_me_lists_the_tree_and_items(self):
        self.s.share(OWNER, 'collection', self.top, VIEWER, 'view')
        loose = self.s.q(OWNER, builder('Loose'))
        self.s.share(OWNER, 'question', loose, VIEWER, 'view')
        mine = self.s.q(VIEWER, builder('Mine'))
        shared = self.bi.shared_with_me(VIEWER, self.ep)
        top = shared['collections'][0]
        self.assertEqual((top['name'], top['access'], top['is_owner']),
                         ('Top', 'view', False))
        self.assertEqual([c['name'] for c in top['children']], ['Sub'])
        self.assertEqual({q['name'] for q in shared['questions']},
                         {'Inner', 'Loose'})
        self.assertEqual([d['name'] for d in shared['dashboards']],
                         ['Board'])
        self.assertNotIn(mine, [q['question_id']
                                for q in shared['questions']])
        # list_questions mixes both, flagged
        listed = {q['name']: (q['access'], q['is_owner'])
                  for q in self.bi.list_questions(VIEWER, self.ep)}
        self.assertEqual(listed['Mine'], ('manage', True))
        self.assertEqual(listed['Inner'], ('view', False))
        # the viewer's own folder list never shows the owner's folders
        self.assertEqual(self.bi.list_collections(VIEWER, self.ep), [])


# ---------------------------------------------------------------------------
class RoleMemberTests(StackCase):
    def test_role_grant_reaches_members_only(self):
        qid = self.s.q(OWNER, builder('For analysts'))
        self.s.share(OWNER, 'question', qid, 10, 'view',
                     principal_type='role')
        self.assertEqual(self.access.level(ANALYST, 'question', self.ep,
                                           qid), 'view')
        for outsider in (VIEWER, EDITOR, STRANGER):
            self.assertIsNone(self.access.level(outsider, 'question',
                                                self.ep, qid))

    def test_user_and_role_grants_combine_by_maximum(self):
        qid = self.s.q(OWNER, builder('Both'))
        self.s.share(OWNER, 'question', qid, ANALYST, 'edit')
        self.s.share(OWNER, 'question', qid, 10, 'view',
                     principal_type='role')
        self.s.share(OWNER, 'question', qid, 20, 'manage',
                     principal_type='role')
        self.assertEqual(self.access.level(ANALYST, 'question', self.ep,
                                           qid), 'manage')
        self.assertEqual(self.access.level(VIEWER, 'question', self.ep,
                                           qid), 'manage')  # role 20
        self.assertIsNone(self.access.level(STRANGER, 'question', self.ep,
                                            qid))

    def test_role_grant_through_collection(self):
        top = self.bi.create_collection(OWNER, {'name': 'T'},
                                        self.ep)['collection_id']
        qid = self.s.q(OWNER, builder('In T', collection_id=top))
        self.s.share(OWNER, 'collection', top, 10, 'view',
                     principal_type='role')
        self.assertEqual(self.access.level(ANALYST, 'question', self.ep,
                                           qid), 'view')


# ---------------------------------------------------------------------------
class GrantManagementTests(StackCase):
    def setUp(self):
        super().setUp()
        self.qid = self.s.q(OWNER, builder('Managed'))

    def test_list_add_update_remove_and_audit(self):
        added = self.s.share(OWNER, 'question', self.qid, VIEWER, 'view')
        self.assertEqual((added['principal_type'], added['principal_name'],
                          added['level']), ('user', 'viewer', 'view'))
        updated = self.access.update_grant(
            OWNER, 'question', self.ep, self.qid, added['grant_id'], 'edit')
        self.assertEqual(updated['level'], 'edit')
        listing = self.access.list_grants(OWNER, 'question', self.ep,
                                          self.qid)
        self.assertEqual(listing['owner']['name'], 'owner')
        self.assertTrue(listing['inherit'])
        self.assertEqual([g['level'] for g in listing['direct']], ['edit'])
        self.access.remove_grant(OWNER, 'question', self.ep, self.qid,
                                 added['grant_id'])
        self.assertEqual(self.access.list_grants(
            OWNER, 'question', self.ep, self.qid)['direct'], [])
        trail = self.access.audit_trail(OWNER, 'question', self.ep,
                                        self.qid)
        self.assertEqual([e['action'] for e in trail],
                         ['grant.remove', 'grant.update', 'grant.add'])
        self.assertEqual({e['actor_user_id'] for e in trail}, {OWNER})
        self.assertEqual({(e['target_type'], e['target_id'])
                          for e in trail}, {('user', VIEWER)})
        self.assertEqual(trail[1]['detail'], {'from': 'view', 'to': 'edit'})

    def test_listing_shows_inherited_grants_with_their_source(self):
        top = self.bi.create_collection(OWNER, {'name': 'Folder'},
                                        self.ep)['collection_id']
        q = self.s.q(OWNER, builder('Filed', collection_id=top))
        self.s.share(OWNER, 'collection', top, VIEWER, 'view')
        self.s.share(OWNER, 'question', q, EDITOR, 'edit')
        listing = self.access.list_grants(OWNER, 'question', self.ep, q)
        self.assertEqual([g['principal_name'] for g in listing['direct']],
                         ['editor'])
        inherited = listing['inherited'][0]
        self.assertEqual((inherited['principal_name'], inherited['level'],
                          inherited['collection_name']),
                         ('viewer', 'view', 'Folder'))
        self.access.set_inherit(OWNER, 'question', self.ep, q, False)
        listing = self.access.list_grants(OWNER, 'question', self.ep, q)
        self.assertEqual((listing['inherit'], listing['inherited']),
                         (False, []))

    def test_only_manage_changes_sharing(self):
        grant = self.s.share(OWNER, 'question', self.qid, VIEWER, 'view')
        self.s.share(OWNER, 'question', self.qid, EDITOR, 'edit')
        for user, expected in ((VIEWER, 'denied'), (EDITOR, 'denied'),
                               (STRANGER, 'unavailable')):
            with self.subTest(user=user):
                for call in (
                    lambda: self.s.share(user, 'question', self.qid,
                                         MANAGER, 'view'),
                    lambda: self.access.update_grant(
                        user, 'question', self.ep, self.qid,
                        grant['grant_id'], 'manage'),
                    lambda: self.access.remove_grant(
                        user, 'question', self.ep, self.qid,
                        grant['grant_id']),
                    lambda: self.access.set_inherit(
                        user, 'question', self.ep, self.qid, False),
                    lambda: self.access.audit_trail(
                        user, 'question', self.ep, self.qid),
                ):
                    self.assertEqual(outcome(call), expected)
        # a viewer cannot escalate themselves
        self.assertEqual(self.access.level(VIEWER, 'question', self.ep,
                                           self.qid), 'view')

    def test_a_grant_id_of_another_resource_is_unavailable(self):
        other = self.s.q(OWNER, builder('Other'))
        grant = self.s.share(OWNER, 'question', other, VIEWER, 'view')
        with self.assertRaisesRegex(BIError, 'grant is unavailable'):
            self.access.remove_grant(OWNER, 'question', self.ep, self.qid,
                                     grant['grant_id'])
        with self.assertRaisesRegex(BIError, 'grant is unavailable'):
            self.access.update_grant(OWNER, 'question', self.ep, self.qid,
                                     'nope', 'edit')

    def test_validation(self):
        self.s.share(OWNER, 'question', self.qid, VIEWER, 'view')
        cases = {
            'duplicate': lambda: self.s.share(OWNER, 'question', self.qid,
                                              VIEWER, 'edit'),
            'owner': lambda: self.s.share(OWNER, 'question', self.qid,
                                          OWNER, 'view'),
            'level': lambda: self.s.share(OWNER, 'question', self.qid,
                                          EDITOR, 'root'),
            'principal type': lambda: self.access.add_grant(
                OWNER, 'question', self.ep, self.qid, 'group', 1, 'view'),
            'bool id': lambda: self.access.add_grant(
                OWNER, 'question', self.ep, self.qid, 'user', True, 'view'),
            'unknown user': lambda: self.s.share(OWNER, 'question',
                                                 self.qid, 999, 'view'),
            'invisible user': lambda: self.s.share(OWNER, 'question',
                                                   self.qid, STRANGER,
                                                   'view'),
            'invisible role': lambda: self.s.share(
                OWNER, 'question', self.qid, 30, 'view',
                principal_type='role'),
            'inherit type': lambda: self.access.set_inherit(
                OWNER, 'question', self.ep, self.qid, 'no'),
        }
        for label, call in cases.items():
            with self.subTest(label):
                with self.assertRaises(BIError):
                    call()
        self.assertEqual(len(self.s.grants.rows), 1)

    def test_principal_search_shows_only_visible_principals(self):
        def names(user, **kw):
            return [(i['type'], i['name'])
                    for i in self.access.search_principals(user, **kw)]
        owner_view = names(OWNER)
        self.assertIn(('user', 'viewer'), owner_view)
        self.assertNotIn(('user', 'stranger'), owner_view)
        self.assertNotIn(('role', 'isolated'), owner_view)
        self.assertNotIn(('user', 'owner'), owner_view)  # not oneself
        self.assertIn(('role', 'analysts'), owner_view)
        self.assertNotIn(('role', 'analysts'), names(VIEWER))
        everything = names(ADMIN)
        self.assertIn(('user', 'stranger'), everything)
        self.assertIn(('role', 'isolated'), everything)
        self.assertEqual(names(OWNER, text='ANAL', kinds=['role']),
                         [('role', 'analysts')])
        self.assertEqual(names(STRANGER, kinds=['user']), [])
        with self.assertRaises(BIError):
            self.access.search_principals(OWNER, kinds=['group'])
        for item in self.access.search_principals(OWNER):
            self.assertEqual(set(item), {'type', 'id', 'name'})  # no email


# ---------------------------------------------------------------------------
class RevisionActorTests(StackCase):
    def test_editor_edits_record_the_actor_and_stay_immutable(self):
        qid = self.s.q(OWNER, builder('Edited'))
        self.s.share(OWNER, 'question', qid, EDITOR, 'edit')
        self.bi.update_question(EDITOR, self.ep, qid, 1,
                                builder('Edited', description='by editor'))
        self.bi.set_status(OWNER, self.ep, qid, 2, 'archived')
        self.bi.set_status(EDITOR, self.ep, qid, 3, 'active')
        history = self.bi.history(OWNER, self.ep, qid)
        self.assertEqual([(h['revision'], h['actor_user_id'], h['actor'])
                          for h in history],
                         [(4, EDITOR, 'editor'), (3, OWNER, 'owner'),
                          (2, EDITOR, 'editor'), (1, OWNER, 'owner')])
        before = [(i.revision, i.definition)
                  for i in self.bi.repository.revisions(qid)]
        self.bi.update_question(OWNER, self.ep, qid, 4,
                                builder('Edited', description='again'))
        after = {i.revision: i.definition
                 for i in self.bi.repository.revisions(qid)}
        for revision, definition in before:
            self.assertEqual(after[revision], definition)
        # the question's owner never changes through an edit
        self.assertEqual(self.bi.repository.qs[qid].user_id, OWNER)

    def test_actor_name_is_hidden_from_viewers_who_cannot_see_them(self):
        qid = self.s.q(OWNER, builder('Actors'))
        self.s.share(OWNER, 'question', qid, EDITOR, 'edit')
        # granted out of band (the owner cannot see this user to pick them)
        self.s.grants.add(endpoint_id=self.ep, kind='question',
                          resource_id=qid, principal_type='user',
                          principal_id=STRANGER, level='view',
                          actor_id=ADMIN)
        self.bi.update_question(EDITOR, self.ep, qid, 1,
                                builder('Actors', description='x'))
        history = self.bi.history(STRANGER, self.ep, qid)
        # the stranger shares no role with the editor or the owner
        self.assertEqual([h['actor'] for h in history], [None, None])
        self.assertEqual([h['actor_user_id'] for h in history],
                         [EDITOR, OWNER])

    def test_dashboard_edits_record_the_actor(self):
        qid = self.s.q(OWNER, builder('On board'))
        self.s.share(OWNER, 'question', qid, EDITOR, 'view')
        did = self.s.dashboards.create(OWNER, self.ep, board([qid]))[
            'dashboard_id']
        self.s.share(OWNER, 'dashboard', did, EDITOR, 'edit')
        document = board([qid])
        document['name'] = 'Board v2'
        updated = self.s.dashboards.update(EDITOR, self.ep, did, 1,
                                           document)
        self.assertEqual(updated['access'], 'edit')
        history = self.s.dashboards.history(OWNER, self.ep, did)
        self.assertEqual([(h['revision'], h['actor_user_id'])
                          for h in history], [(2, EDITOR), (1, OWNER)])

    def test_dashboard_editor_must_be_able_to_view_each_pinned_question(self):
        shared = self.s.q(OWNER, builder('Visible'))
        hidden = self.s.q(OWNER, builder('Hidden'))
        self.s.share(OWNER, 'question', shared, EDITOR, 'view')
        self.assertEqual(outcome(lambda: self.s.dashboards.create(
            EDITOR, self.ep, board([shared]))), 'ok')
        with self.assertRaisesRegex(BIError, 'unavailable'):
            self.s.dashboards.create(
                EDITOR, self.ep, board([shared, hidden], name='Two'))


# ---------------------------------------------------------------------------
class OwnershipTransferTests(StackCase):
    def setUp(self):
        super().setUp()
        self.qid = self.s.q(OWNER, builder('Handover'))
        self.s.share(OWNER, 'question', self.qid, MANAGER, 'manage')
        self.s.share(OWNER, 'question', self.qid, EDITOR, 'edit')

    def transfer(self, user, to, confirm='Handover'):
        return self.bi.transfer_owner(user, self.ep, 'question', self.qid,
                                      to, confirm)

    def test_requires_manage_and_typed_confirmation(self):
        self.assertEqual(outcome(lambda: self.transfer(EDITOR, VIEWER)),
                         'denied')
        self.assertEqual(outcome(lambda: self.transfer(STRANGER, VIEWER)),
                         'unavailable')
        self.assertIn('type the exact name', outcome(
            lambda: self.transfer(OWNER, VIEWER, confirm='handover')))
        self.assertIn('type the exact name', outcome(
            lambda: self.transfer(OWNER, VIEWER, confirm=None)))
        self.assertEqual(self.bi.repository.qs[self.qid].user_id, OWNER)

    def test_target_must_be_a_visible_distinct_user(self):
        for target in (STRANGER, 999):
            with self.assertRaisesRegex(BIError, 'principal is unavailable'):
                self.transfer(OWNER, target)
        self.assertEqual(outcome(lambda: self.transfer(OWNER, OWNER)),
                         'that user already owns this resource')
        with self.assertRaisesRegex(BIError, 'principal must be a user or role id'):
            self.bi.transfer_owner(OWNER, self.ep, 'question', self.qid,
                                   'owner', 'Handover')

    def test_manager_transfers_and_the_old_owner_keeps_edit(self):
        outcome_ = self.transfer(MANAGER, VIEWER)
        self.assertEqual(outcome_['owner_user_id'], VIEWER)
        self.assertEqual(outcome_['previous_owner'], OWNER)
        self.assertEqual(self.bi.repository.qs[self.qid].user_id, VIEWER)
        self.assertEqual(self.access.level(VIEWER, 'question', self.ep,
                                           self.qid), 'manage')
        self.assertEqual(self.access.level(OWNER, 'question', self.ep,
                                           self.qid), 'edit')
        self.assertEqual(outcome(lambda: self.bi.delete_question(
            OWNER, self.ep, self.qid, 1)), 'denied')
        self.assertEqual(self.bi.get_question(VIEWER, self.ep, self.qid)[
            'is_owner'], True)
        # the new owner's redundant grant is gone
        self.assertEqual(self.s.share(VIEWER, 'question', self.qid,
                                      ANALYST, 'view')['level'], 'view')

    def test_a_new_owner_with_an_old_grant_loses_the_redundant_row(self):
        self.transfer(OWNER, EDITOR)
        self.assertIsNone(self.s.grants.find(self.ep, 'question', self.qid,
                                             'user', EDITOR))
        self.assertEqual(self.access.level(EDITOR, 'question', self.ep,
                                           self.qid), 'manage')

    def test_transfer_is_audited(self):
        self.transfer(MANAGER, VIEWER)
        trail = self.access.audit_trail(VIEWER, 'question', self.ep,
                                        self.qid)
        event = trail[0]
        self.assertEqual((event['action'], event['actor_user_id'],
                          event['target_type'], event['target_id']),
                         ('owner.transfer', MANAGER, 'user', VIEWER))
        self.assertEqual(event['detail'], {'previous_owner': OWNER})

    def test_dashboards_and_collections_transfer_too(self):
        cid = self.bi.create_collection(OWNER, {'name': 'Folder'},
                                        self.ep)['collection_id']
        self.bi.transfer_owner(OWNER, self.ep, 'collection', cid, EDITOR,
                               'Folder')
        self.assertEqual(self.bi.repository.cols[cid].user_id, EDITOR)
        did = self.s.dashboards.create(OWNER, self.ep, board(
            [self.qid]))['dashboard_id']
        self.s.dashboards.transfer_owner(OWNER, self.ep, did, MANAGER,
                                         'Board')
        self.assertEqual(self.s.dashboards.repository.rows[did].user_id,
                         MANAGER)

    def test_semantic_question_needs_the_model_at_the_new_owner(self):
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
        created = self.bi.semantic.create(OWNER, self.ep, model)
        sid = self.s.q(OWNER, {
            'name': 'Cube',
            'semantic_model': {'id': created['model_id'], 'revision': 1},
            'query': {'kind': 'semantic', 'builder': {
                'group_by': ['region'],
                'aggregations': [{'measure_id': 'revenue'}], 'limit': 5}}})
        self.assertIn('semantic model', outcome(lambda: self.bi.transfer_owner(
            OWNER, self.ep, 'question', sid, VIEWER, 'Cube')))
        self.assertEqual(self.bi.repository.qs[sid].user_id, OWNER)


# ---------------------------------------------------------------------------
class RawSqlRedactionTests(StackCase):
    def setUp(self):
        super().setUp()
        self.raw = self.s.q(OWNER, secret_question())
        self.s.share(OWNER, 'question', self.raw, VIEWER, 'view')
        self.s.share(OWNER, 'question', self.raw, EDITOR, 'edit')
        self.s.share(OWNER, 'question', self.raw, MANAGER, 'manage')

    def test_viewer_cannot_read_the_sql_anywhere(self):
        got = self.bi.get_question(VIEWER, self.ep, self.raw)
        self.assertTrue(got['sql_redacted'])
        self.assertEqual(got['definition']['query']['sql'], '')
        self.assertNotIn(HIDDEN, json.dumps(got))
        pinned = self.bi.revision(VIEWER, self.ep, self.raw, 1)
        self.assertTrue(pinned['sql_redacted'])
        self.assertNotIn(HIDDEN, json.dumps(pinned))
        compiled = self.bi.compile(self.s.provider, VIEWER, self.ep,
                                   question_id=self.raw)
        self.assertIsNone(compiled['source'])
        self.assertTrue(compiled['sql_redacted'])
        self.assertNotIn(HIDDEN, json.dumps(compiled, default=str))
        listed = self.bi.list_questions(VIEWER, self.ep)
        self.assertNotIn(HIDDEN, json.dumps(listed))

    def test_viewer_runs_it_and_gets_rows_but_no_sql(self):
        result = self.s.run_as(VIEWER, question_id=self.raw)
        self.assertIsNone(result['sql'])
        self.assertTrue(result['sql_redacted'])
        self.assertEqual(sorted(r['region'] for r in table(result)),
                         ['east', 'west'])
        self.assertNotIn(HIDDEN, json.dumps(result, default=str))
        cached = self.s.run_as(VIEWER, question_id=self.raw)
        self.assertTrue(cached['cache']['hit'])
        self.assertIsNone(cached['sql'])
        self.assertTrue(cached['sql_redacted'])

    def test_editor_and_above_see_the_sql(self):
        for user in (EDITOR, MANAGER, OWNER):
            with self.subTest(user=user):
                got = self.bi.get_question(user, self.ep, self.raw)
                self.assertFalse(got['sql_redacted'])
                self.assertEqual(got['definition']['query']['sql'],
                                 SECRET_SQL)
                result = self.s.run_as(user, question_id=self.raw)
                self.assertFalse(result['sql_redacted'])
                self.assertEqual(result['sql'], SECRET_SQL)
                self.assertEqual(self.bi.compile(
                    self.s.provider, user, self.ep, question_id=self.raw)[
                        'source'], SECRET_SQL)

    def test_viewer_cannot_duplicate_a_raw_sql_question(self):
        self.assertEqual(outcome(lambda: self.bi.clone_question(
            VIEWER, self.ep, self.raw, 'steal')), 'denied')
        self.assertEqual(outcome(lambda: self.bi.clone_question(
            EDITOR, self.ep, self.raw, 'mine')), 'ok')

    def test_builder_questions_stay_fully_visible_to_viewers(self):
        qid = self.s.q(OWNER, builder('Plain'))
        self.s.share(OWNER, 'question', qid, VIEWER, 'view')
        got = self.bi.get_question(VIEWER, self.ep, qid)
        self.assertFalse(got['sql_redacted'])
        self.assertIn('FROM', self.s.run_as(VIEWER, question_id=qid)['sql'])

    def test_a_failing_run_does_not_echo_the_statement_to_a_viewer(self):
        original = self.s.studio.execute

        def failing(context, session_id, source, **kwargs):
            raise RelationalClientError(f'syntax error in: {source}')
        self.s.studio.execute = failing
        try:
            viewer = outcome(lambda: self.s.run_as(
                VIEWER, question_id=self.raw, bypass_cache=True))
            editor = outcome(lambda: self.s.run_as(
                EDITOR, question_id=self.raw, bypass_cache=True))
        finally:
            self.s.studio.execute = original
        self.assertEqual(viewer, 'question execution failed')
        self.assertIn(HIDDEN, editor)

    def test_raw_sql_is_hidden_across_engines(self):
        if duckdb is None:
            self.skipTest('duckdb is not installed')
        other = SharedStack('duckdb', 'perm-duck')
        qid = other.q(OWNER, secret_question())
        other.share(OWNER, 'question', qid, VIEWER, 'view')
        result = other.run_as(VIEWER, question_id=qid)
        self.assertIsNone(result['sql'])


# ---------------------------------------------------------------------------
class RunAsRunnerTests(StackCase):
    """Sharing never lends out the owner's credentials or row policies."""

    def tenant_model(self):
        return {
            'name': 'Tenant sales', 'sources': [{
                'id': 'sales', 'resource_id': 'table:sales',
                'relation': ['sales'], 'alias': 'sales'}],
            'dimensions': [{'id': 'region', 'name': 'Region',
                            'field': {'source_id': 'sales',
                                      'field': 'region'}}],
            'measures': [{'id': 'revenue', 'name': 'Revenue',
                          'aggregation': 'sum',
                          'field': {'source_id': 'sales',
                                    'field': 'amount'}}],
            'security': {'tenant_filter': {
                'field': {'source_id': 'sales', 'field': 'qty'},
                'principal_claim': 'user_id', 'required': True}},
        }

    def semantic_question(self):
        created = self.bi.semantic.create(OWNER, self.ep, self.tenant_model())
        return self.s.q(OWNER, {
            'name': 'Tenant cube',
            'semantic_model': {'id': created['model_id'], 'revision': 1},
            'query': {'kind': 'semantic', 'builder': {
                'group_by': ['region'],
                'aggregations': [{'measure_id': 'revenue'}],
                'order_by': [{'id': 'revenue', 'direction': 'desc'}],
                'limit': 10}}})

    @staticmethod
    def rows(result):
        return sorted((r['region'], r['revenue']) for r in table(result))

    def test_each_runner_gets_their_own_credentials_context(self):
        qid = self.s.q(OWNER, builder('Creds'))
        self.s.share(OWNER, 'question', qid, VIEWER, 'view')
        self.s.run_as(OWNER, question_id=qid)
        self.s.run_as(VIEWER, question_id=qid)
        who = [s['endpoint']['route']['credential_owner']
               for s in self.s.studio.sessions]
        self.assertEqual(who, [OWNER, VIEWER])
        self.assertTrue(all(s['context'] is self.s.ctx
                            for s in self.s.studio.sessions))

    def test_semantic_row_policy_uses_the_runners_claims(self):
        qid = self.semantic_question()
        self.s.share(OWNER, 'question', qid, VIEWER, 'view')
        self.s.share(OWNER, 'question', qid, EDITOR, 'view')
        by_user = {}
        for user in (OWNER, VIEWER, EDITOR):
            by_user[user] = self.rows(self.s.run_as(user, question_id=qid))
        # qty is the tenant column: rows with qty == the runner's user id
        self.assertEqual(by_user[OWNER], [('east', 10), ('west', 5)])
        self.assertEqual(by_user[VIEWER], [('west', 20)])
        self.assertEqual(by_user[EDITOR], [('east', 30)])
        claims = [c['claims']['user_id'] for c in self.s.security_contexts]
        self.assertEqual(claims, [OWNER, VIEWER, EDITOR])
        # the stored model belongs to the owner; the viewer never owned one
        self.assertEqual(self.bi.semantic.repository.list(VIEWER, self.ep),
                         [])

    def test_a_viewer_gets_no_rows_without_the_claim(self):
        # a runner whose id matches no tenant sees nothing, not the owner's
        qid = self.semantic_question()
        self.s.share(OWNER, 'question', qid, ANALYST, 'view')
        self.assertEqual(self.rows(self.s.run_as(ANALYST, question_id=qid)),
                         [])

    def test_compile_for_a_viewer_binds_the_viewers_tenant(self):
        qid = self.semantic_question()
        self.s.share(OWNER, 'question', qid, VIEWER, 'view')
        owner_sql = self.bi.compile(
            self.s.provider, OWNER, self.ep, question_id=qid,
            security_context={'claims': {'user_id': OWNER}})
        viewer_sql = self.bi.compile(
            self.s.provider, VIEWER, self.ep, question_id=qid,
            security_context={'claims': {'user_id': VIEWER}})
        self.assertNotEqual(owner_sql['source'], viewer_sql['source'])

    def test_raw_sql_for_the_runner_is_refused_when_policies_exist(self):
        # the OWNER declares a tenant policy; a viewer who owns no models
        # must not be able to bypass it through a shared raw question
        self.semantic_question()
        raw = self.s.q(OWNER, sql_question(
            'SELECT region, amount FROM sales ORDER BY amount'))
        self.s.share(OWNER, 'question', raw, VIEWER, 'view')
        for user in (OWNER, VIEWER):
            with self.subTest(user=user):
                with self.assertRaisesRegex(BIError, 'row policies'):
                    self.s.run_as(user, question_id=raw)

    def test_raw_sql_policy_callback_is_evaluated_for_the_runner(self):
        raw = self.s.q(OWNER, sql_question(
            'SELECT region, amount FROM sales ORDER BY amount'))
        self.s.share(OWNER, 'question', raw, VIEWER, 'view')
        self.s.share(OWNER, 'question', raw, EDITOR, 'view')
        seen = []

        def policy(user_id, endpoint_id):
            seen.append(user_id)
            return user_id != VIEWER
        self.bi.add_raw_sql_policy(policy)
        self.assertEqual(outcome(lambda: self.s.run_as(
            OWNER, question_id=raw)), 'ok')
        self.assertEqual(outcome(lambda: self.s.run_as(
            EDITOR, question_id=raw)), 'ok')
        self.assertIn('not permitted', outcome(lambda: self.s.run_as(
            VIEWER, question_id=raw)))
        self.assertEqual(seen, [OWNER, EDITOR, VIEWER])

    def test_read_only_guard_still_applies_to_shared_raw_sql(self):
        raw = self.s.q(OWNER, sql_question('SELECT region FROM sales'))
        self.s.share(OWNER, 'question', raw, EDITOR, 'edit')
        # an editor cannot smuggle a write in through an update
        bad = sql_question('DELETE FROM sales')
        bad['name'] = 'Secret revenue'
        with self.assertRaises(BIError):
            stored = self.bi.update_question(
                EDITOR, self.ep, raw, 1, {**bad, 'name': 'Raw'})
            self.s.run_as(EDITOR, question_id=stored['question_id'])

    def test_cache_key_includes_the_principal(self):
        qid = self.s.q(OWNER, builder('Cached'))
        self.s.share(OWNER, 'question', qid, VIEWER, 'view')
        mine = self.s.run_as(OWNER, question_id=qid)
        theirs = self.s.run_as(VIEWER, question_id=qid)
        again = self.s.run_as(VIEWER, question_id=qid)
        self.assertFalse(mine['cache']['hit'])
        self.assertFalse(theirs['cache']['hit'])   # not served the owner's
        self.assertTrue(again['cache']['hit'])
        self.assertNotEqual(mine['cache']['key'], theirs['cache']['key'])
        self.assertNotEqual(mine['result']['result_id'],
                            theirs['result']['result_id'])
        # and results are private to the runner
        with self.assertRaisesRegex(BIError, 'unavailable'):
            self.s.executor.page(VIEWER, self.ep, mine['result']['result_id'])
        with self.assertRaisesRegex(BIError, 'unavailable'):
            self.s.executor.export(VIEWER, self.ep,
                                   mine['result']['result_id'], 'csv')
        self.assertEqual(
            [e['result_id'] for e in self.s.executor.cache_info(
                VIEWER, self.ep)], [theirs['result']['result_id']])

    def test_revoked_access_ends_runs_cache_hits_and_page_leases(self):
        qid = self.s.q(OWNER, builder('Revocable'))
        grant = self.s.share(OWNER, 'question', qid, VIEWER, 'view')
        result = self.s.run_as(VIEWER, question_id=qid)
        rid = result['result']['result_id']
        self.s.executor.page(VIEWER, self.ep, rid)
        self.access.remove_grant(OWNER, 'question', self.ep, qid,
                                 grant['grant_id'])
        with self.assertRaisesRegex(BIError, 'unavailable'):
            self.s.run_as(VIEWER, question_id=qid)        # no cache hit
        with self.assertRaisesRegex(BIError, 'unavailable'):
            self.s.executor.page(VIEWER, self.ep, rid)

    def test_an_edit_invalidates_every_principals_cache(self):
        qid = self.s.q(OWNER, builder('Fresh'))
        self.s.share(OWNER, 'question', qid, VIEWER, 'view')
        self.s.share(OWNER, 'question', qid, EDITOR, 'edit')
        self.s.run_as(OWNER, question_id=qid)
        self.s.run_as(VIEWER, question_id=qid)
        self.bi.update_question(EDITOR, self.ep, qid, 1,
                                builder('Fresh', description='new'))
        self.assertEqual(self.s.executor.cache_info(OWNER, self.ep), [])
        self.assertEqual(self.s.executor.cache_info(VIEWER, self.ep), [])

    def test_runs_work_on_every_engine(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                stack = SharedStack(engine, 'perm-' + engine)
                qid = stack.q(OWNER, builder('Engine'))
                stack.share(OWNER, 'question', qid, VIEWER, 'view')
                result = stack.run_as(VIEWER, question_id=qid)
                self.assertEqual(len(table(result)), 5)


# ---------------------------------------------------------------------------
class DashboardSharingTests(StackCase):
    def setUp(self):
        super().setUp()
        self.public = self.s.q(OWNER, region_question())
        self.private_q = self.s.q(OWNER, secret_question('Salary details'))
        self.s.share(OWNER, 'question', self.public, VIEWER, 'view')
        self.did = self.s.dashboards.create(OWNER, self.ep, board(
            [self.public, self.private_q], name='Mixed',
            filters=[]))['dashboard_id']
        self.s.share(OWNER, 'dashboard', self.did, VIEWER, 'view')

    def test_viewing_needs_the_dashboard_grant_not_the_questions(self):
        self.s.share(OWNER, 'question', self.private_q, ANALYST, 'view')
        with self.assertRaisesRegex(BIError, 'unavailable'):
            self.s.dashboards.get(ANALYST, self.ep, self.did)

    def test_dashboard_definition_does_not_name_the_unshared_question(self):
        got = self.s.dashboards.get(VIEWER, self.ep, self.did)
        text = json.dumps(got)
        self.assertNotIn('Salary details', text)
        self.assertNotIn(HIDDEN, text)
        self.assertEqual(got['access'], 'view')

    def test_run_marks_unshared_cards_and_never_leaks_them(self):
        # the region question needs a value: give it a default
        question = region_question()
        question['parameters'][0]['default'] = 'east'
        question['name'] = 'East by default'
        public = self.s.q(OWNER, question)
        self.s.share(OWNER, 'question', public, VIEWER, 'view')
        did = self.s.dashboards.create(OWNER, self.ep, board(
            [public, self.private_q], name='Defaults'))['dashboard_id']
        self.s.share(OWNER, 'dashboard', did, VIEWER, 'view')
        outcome_ = self.s.run_dashboard(VIEWER, did)
        cards = outcome_['cards']
        self.assertIn('run', cards['c0'])
        self.assertEqual(cards['c1'], {'type': 'question',
                                       'no_access': True})
        text = json.dumps(outcome_, default=str)
        for secret in ('Salary details', HIDDEN, '<> ',
                       self.private_q):
            self.assertNotIn(secret, text)
        # the owner sees both cards
        owner_cards = self.s.run_dashboard(OWNER, did)['cards']
        self.assertIn('run', owner_cards['c1'])

    def test_single_card_run_reports_no_access_too(self):
        outcome_ = self.s.dashboards.run_card(
            provider=self.s.provider, context=self.s.ctx,
            endpoint=self.s.endpoint_for(VIEWER), user_id=VIEWER,
            dashboard_id=self.did, card_id='c1')
        self.assertEqual(outcome_, {'card_id': 'c1', 'no_access': True})
        self.assertNotIn('Salary', json.dumps(outcome_))

    def test_the_card_question_cannot_be_read_directly(self):
        with self.assertRaisesRegex(BIError, 'unavailable'):
            self.bi.get_question(VIEWER, self.ep, self.private_q)
        with self.assertRaisesRegex(BIError, 'unavailable'):
            self.s.run_as(VIEWER, question_id=self.private_q)

    def test_dashboard_levels(self):
        self.s.share(OWNER, 'dashboard', self.did, EDITOR, 'edit')
        self.s.share(OWNER, 'question', self.public, EDITOR, 'view')
        document = board([self.public], name='Mixed')
        self.assertEqual(outcome(lambda: self.s.dashboards.update(
            VIEWER, self.ep, self.did, 1, document)), 'denied')
        self.assertEqual(outcome(lambda: self.s.dashboards.delete(
            EDITOR, self.ep, self.did, 1)), 'denied')
        self.assertEqual(outcome(lambda: self.s.dashboards.update(
            EDITOR, self.ep, self.did, 1, document)), 'ok')
        self.assertEqual(outcome(lambda: self.s.dashboards.get(
            STRANGER, self.ep, self.did)), 'unavailable')

    def test_cloning_a_dashboard_needs_view_on_each_pinned_question(self):
        self.assertEqual(outcome(lambda: self.s.dashboards.clone(
            VIEWER, self.ep, self.did, 'My copy')), 'unavailable')
        only = self.s.dashboards.create(OWNER, self.ep, board(
            [self.public], name='Only public'))['dashboard_id']
        self.s.share(OWNER, 'dashboard', only, VIEWER, 'view')
        copy = self.s.dashboards.clone(VIEWER, self.ep, only, 'Copy')
        self.assertTrue(copy['is_owner'])

    def test_deleting_a_question_never_names_an_unseen_dashboard(self):
        self.s.share(OWNER, 'question', self.private_q, MANAGER, 'manage')
        with self.assertRaises(BIError) as caught:
            self.bi.delete_question(MANAGER, self.ep, self.private_q, 1)
        self.assertNotIn('Mixed', str(caught.exception))
        # the owner is told which dashboard
        with self.assertRaisesRegex(BIError, 'Mixed'):
            self.bi.delete_question(OWNER, self.ep, self.private_q, 1)

    def test_dashboard_listing_and_shared_with_me(self):
        listed = self.s.dashboards.list(VIEWER, self.ep)
        self.assertEqual([(d['name'], d['access'], d['is_owner'])
                          for d in listed], [('Mixed', 'view', False)])
        self.assertEqual(self.s.dashboards.list(STRANGER, self.ep), [])
        self.assertEqual([d['name'] for d in self.bi.shared_with_me(
            VIEWER, self.ep)['dashboards']], ['Mixed'])

    def test_resolution_helpers_need_view(self):
        for call in (
                lambda u: self.s.dashboards.resolve(u, self.ep, self.did),
                lambda u: self.s.dashboards.history(u, self.ep, self.did)):
            self.assertEqual(outcome(lambda: call(VIEWER)), 'ok')
            self.assertEqual(outcome(lambda: call(STRANGER)), 'unavailable')


# ---------------------------------------------------------------------------
class WorkspaceActionTests(StackCase):
    """The ``bi_*`` sharing actions through ``ProviderWorkspaceService``."""

    def setUp(self):
        super().setUp()
        from pgadmin.cdeadmin.workspace import ProviderWorkspaceService
        service = ProviderWorkspaceService.__new__(ProviderWorkspaceService)
        service.bi_service = self.bi
        self.bi.dashboards = self.s.dashboards
        self.bi.executor = self.s.executor
        context = self.s.ctx
        service.endpoint_service = type('E', (), {
            'workspace': lambda _s, server: (context, {'route': {}}, None),
            'provider_registry': type('R', (), {
                'resolve': lambda _s, _c: type('B', (), {
                    'instance': self.s.provider})()})()})()
        self.service = service

    def act(self, user, action, **request):
        server = type('Server', (), {'user_id': user})()
        return self.service.bi_action(server, action, request)

    def test_sharing_round_trip_through_the_action_surface(self):
        created = self.act(OWNER, 'bi_question_create',
                           question=builder('Via action'))
        qid = created['question_id']
        self.assertEqual(outcome(lambda: self.act(
            VIEWER, 'bi_question_get', question_id=qid)), 'unavailable')
        found = self.act(OWNER, 'bi_principal_search', text='view')['items']
        self.assertEqual([i['name'] for i in found], ['viewer'])
        grant = self.act(OWNER, 'bi_grant_add', resource_type='question',
                         resource_id=qid, principal_type='user',
                         principal_id=VIEWER, level='view')
        got = self.act(VIEWER, 'bi_question_get', question_id=qid)
        self.assertEqual((got['access'], got['is_owner']), ('view', False))
        self.assertEqual(self.act(VIEWER, 'bi_access_get',
                                  resource_type='question',
                                  resource_id=qid)['level'], 'view')
        shared = self.act(VIEWER, 'bi_shared_with_me')
        self.assertEqual([q['question_id'] for q in shared['questions']],
                         [qid])
        self.assertEqual(outcome(lambda: self.act(
            VIEWER, 'bi_grant_list', resource_type='question',
            resource_id=qid)), 'denied')
        listing = self.act(OWNER, 'bi_grant_list', resource_type='question',
                           resource_id=qid)
        self.assertEqual(len(listing['direct']), 1)
        self.act(OWNER, 'bi_grant_update', resource_type='question',
                 resource_id=qid, grant_id=grant['grant_id'], level='edit')
        self.act(OWNER, 'bi_access_inherit', resource_type='question',
                 resource_id=qid, inherit=False)
        self.act(OWNER, 'bi_transfer_owner', resource_type='question',
                 resource_id=qid, new_owner_id=VIEWER, confirm='Via action')
        self.assertTrue(self.act(VIEWER, 'bi_question_get',
                                 question_id=qid)['is_owner'])
        trail = self.act(VIEWER, 'bi_audit_list', resource_type='question',
                         resource_id=qid)['items']
        self.assertEqual([e['action'] for e in trail],
                         ['owner.transfer', 'inherit.set', 'grant.update',
                          'grant.add'])
        self.act(VIEWER, 'bi_grant_remove', resource_type='question',
                 resource_id=qid, grant_id=self.act(
                     VIEWER, 'bi_grant_list', resource_type='question',
                     resource_id=qid)['direct'][0]['grant_id'])

    def test_bad_resource_types_are_rejected(self):
        for kind in ('semantic_model', None, 5):
            with self.assertRaises(Exception):
                self.act(OWNER, 'bi_grant_list', resource_type=kind,
                         resource_id='x')

    def test_collection_actions_carry_the_endpoint(self):
        top = self.act(OWNER, 'bi_collection_create',
                       collection={'name': 'Team'})['collection_id']
        self.act(OWNER, 'bi_grant_add', resource_type='collection',
                 resource_id=top, principal_type='user',
                 principal_id=EDITOR, level='edit')
        made = self.act(EDITOR, 'bi_collection_create',
                        collection={'name': 'Mine', 'parent_id': top})
        self.assertTrue(made['is_owner'])
        self.assertEqual(made['access'], 'manage')
        self.assertEqual(outcome(lambda: self.act(
            VIEWER, 'bi_collection_create',
            collection={'name': 'x', 'parent_id': top})), 'unavailable')


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
        first = self.load('cde_bi_saved_questions_v1')
        second = self.load('cde_bi_dashboards_v1')
        third = self.load('cde_bi_permissions_v1')
        self.assertEqual(third.down_revision, second.revision)
        engine = sa.create_engine('sqlite:///:memory:')
        with engine.connect() as connection:
            metadata = sa.MetaData()
            sa.Table('user', metadata,
                     sa.Column('id', sa.Integer(), primary_key=True))
            sa.Table('role', metadata,
                     sa.Column('id', sa.Integer(), primary_key=True))
            sa.Table('cde_endpoint', metadata,
                     sa.Column('id', sa.String(36), primary_key=True))
            metadata.create_all(connection)
            operations = Operations(MigrationContext.configure(connection))
            for module in (first, second, third):
                module.op = operations
            first.upgrade()
            second.upgrade()
            third.upgrade()
            inspector = sa.inspect(connection)
            for table in ('cde_bi_grant', 'cde_bi_access_override',
                          'cde_bi_audit'):
                self.assertIn(table, inspector.get_table_names())
            for table in ('cde_bi_saved_question_revision',
                          'cde_bi_dashboard_revision'):
                self.assertIn('actor_user_id', [
                    c['name'] for c in inspector.get_columns(table)])
            connection.commit()
            connection.execute(sa.text('PRAGMA foreign_keys=ON'))
            connection.execute(sa.text('INSERT INTO user (id) VALUES (1)'))
            connection.execute(sa.text('INSERT INTO role (id) VALUES (5)'))
            connection.execute(sa.text(
                "INSERT INTO cde_endpoint (id) VALUES ('ep')"))
            grant = sa.Table('cde_bi_grant', sa.MetaData(),
                             autoload_with=connection)
            now = datetime.now(timezone.utc)
            base = dict(endpoint_id='ep', resource_type='question',
                        resource_id='q1', level='view', created_at=now,
                        updated_at=now)
            connection.execute(grant.insert().values(
                id='a', principal_user_id=1, **base))
            connection.execute(grant.insert().values(
                id='b', principal_role_id=5, **base))
            bad = {
                'both principals': dict(id='c', principal_user_id=1,
                                        principal_role_id=5, **base),
                'no principal': dict(id='d', **base),
                'duplicate user': dict(id='e', principal_user_id=1, **base),
                'duplicate role': dict(id='f', principal_role_id=5, **base),
                'level': dict(id='g', principal_user_id=1,
                              **{**base, 'level': 'root',
                                 'resource_id': 'q2'}),
                'resource': dict(id='h', principal_user_id=1,
                                 **{**base, 'resource_type': 'file',
                                    'resource_id': 'q3'}),
            }
            for label, values in bad.items():
                with self.subTest(label):
                    with self.assertRaises(sa.exc.IntegrityError):
                        connection.execute(grant.insert().values(**values))
            # deleting a user or role removes the grants naming it
            connection.execute(sa.text('DELETE FROM role WHERE id = 5'))
            self.assertEqual(connection.execute(
                sa.select(sa.func.count()).select_from(grant)).scalar(), 1)
            third.downgrade()
            names = sa.inspect(connection).get_table_names()
            self.assertNotIn('cde_bi_grant', names)
            self.assertIn('cde_bi_dashboard', names)
            self.assertNotIn('actor_user_id', [
                c['name'] for c in sa.inspect(connection).get_columns(
                    'cde_bi_dashboard_revision')])
            third.upgrade()  # and back again
            self.assertIn('cde_bi_audit',
                          sa.inspect(connection).get_table_names())


# ---------------------------------------------------------------------------
try:
    from flask import Flask
    import flask_sqlalchemy  # noqa: F401
    from test_cdeadmin_endpoint_persistence import load_model
    MODEL_DEPENDENCIES = MIGRATION_DEPENDENCIES
except ImportError:  # pragma: no cover
    MODEL_DEPENDENCIES = False


@unittest.skipUnless(MODEL_DEPENDENCIES,
                     'Flask-SQLAlchemy and Alembic are required')
class DatabaseIntegrationTests(unittest.TestCase):
    """The real SQLAlchemy repositories, models and constraints."""

    def setUp(self):
        from pgadmin.cdeadmin.bi.access import (
            DatabaseGrantRepository, DatabasePrincipalDirectory,
        )
        from pgadmin.cdeadmin.bi.dashboards import (
            DatabaseDashboardRepository, DashboardService,
        )
        from pgadmin.cdeadmin.bi.service import (
            BIService, DatabaseBIRepository,
        )
        from pgadmin.cdeadmin.semantic_models import SemanticModelService
        self.temporary = tempfile.TemporaryDirectory()
        self.model = load_model()
        m = self.model
        self.app = Flask('cdeadmin-bi-permissions-test')
        self.app.config['SQLALCHEMY_DATABASE_URI'] = (
            f'sqlite:///{Path(self.temporary.name) / "config.db"}')
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        m.db.init_app(self.app)
        self.context = self.app.app_context()
        self.context.push()
        m.db.create_all()
        for uid, name in ((1, 'owner'), (2, 'viewer'), (3, 'editor'),
                          (4, 'outsider')):
            m.db.session.execute(m.User.__table__.insert(), {
                'id': uid, 'username': name, 'active': True,
                'auth_source': f'internal{uid}', 'fs_uniquifier': f'u{uid}',
                'locked': False})
        m.db.session.add_all([
            m.Role(id=1, name='Administrator', description='a'),
            m.Role(id=2, name='User', description='u'),
            m.Role(id=3, name='Team', description='t'),
            m.ServerGroup(id=1, user_id=1, name='G')])
        m.db.session.commit()
        for uid, roles in ((1, (2, 3)), (2, (2,)), (3, (2, 3)), (4, ())):
            user = m.db.session.get(m.User, uid)
            user.roles = [m.db.session.get(m.Role, r) for r in roles]
        server = m.Server(
            id=10, user_id=1, servergroup_id=1, name='S', host='h',
            port=1, maintenance_db='d', username='u', save_password=0,
            use_ssh_tunnel=0, tunnel_authentication=0,
            tunnel_prompt_password=0, shared=False, kerberos_conn=False,
            cloud_status=0, is_adhoc=0)
        m.db.session.add(server)
        m.db.session.commit()
        self.ep = m.EndpointProfile.query.filter_by(
            legacy_server_id=10).one().id

        def bound(cls, **attrs):
            instance = cls.__new__(cls)
            instance.__dict__.update(attrs)
            return instance
        repo = bound(DatabaseBIRepository, db=m.db,
                     collection=m.BICollection, question=m.BISavedQuestion,
                     revision=m.BISavedQuestionRevision)
        grants = bound(DatabaseGrantRepository, db=m.db, grant=m.BIGrant,
                       override=m.BIAccessOverride, event=m.BIAuditEvent)
        directory = bound(DatabasePrincipalDirectory, db=m.db,
                          user_model=m.User, role_model=m.Role)
        dashboards = bound(DatabaseDashboardRepository, db=m.db,
                           dashboard=m.BIDashboard,
                           revision=m.BIDashboardRevision)
        self.bi = BIService(SemanticModelService(MemorySemantic()), repo,
                            grants=grants, directory=directory)
        self.dashboards = DashboardService(self.bi, None,
                                           repository=dashboards)

    def tearDown(self):
        self.model.db.session.remove()
        self.model.db.drop_all()
        for engine in self.model.db.engines.values():
            engine.dispose()
        self.context.pop()
        self.temporary.cleanup()

    def test_sharing_flow_on_the_real_tables(self):
        m, bi, ep = self.model, self.bi, self.ep
        folder = bi.create_collection(1, {'name': 'Team'}, ep)[
            'collection_id']
        qid = bi.create_question(1, ep, builder(
            'Stored', collection_id=folder))['question_id']
        with self.assertRaisesRegex(BIError, 'unavailable'):
            bi.get_question(2, ep, qid)
        # users and roles come from the real tables, with the visibility rule
        found = {(i['type'], i['name'])
                 for i in bi.access.search_principals(1)}
        self.assertEqual(found, {('user', 'viewer'), ('user', 'editor'),
                                 ('role', 'User'), ('role', 'Team')})
        bi.access.add_grant(1, 'collection', ep, folder, 'user', 2, 'view')
        bi.access.add_grant(1, 'collection', ep, folder, 'role', 3, 'edit')
        self.assertEqual(bi.get_question(2, ep, qid)['access'], 'view')
        self.assertEqual(bi.get_question(3, ep, qid)['access'], 'edit')
        with self.assertRaisesRegex(BIError, 'unavailable'):
            bi.get_question(4, ep, qid)
        with self.assertRaisesRegex(BIError, 'already has a grant'):
            bi.access.add_grant(1, 'collection', ep, folder, 'user', 2,
                                'edit')
        # an editor edits; the revision records them
        bi.update_question(3, ep, qid, 1, builder(
            'Stored', collection_id=folder, description='by editor'))
        rows = m.BISavedQuestionRevision.query.filter_by(
            question_id=qid).order_by(
            m.BISavedQuestionRevision.revision).all()
        self.assertEqual([(r.revision, r.actor_user_id) for r in rows],
                         [(1, 1), (2, 3)])
        with self.assertRaises(ValueError):
            rows[0].definition = '{}'
            m.db.session.commit()
        m.db.session.rollback()
        # listing, shared-with-me and transfer
        self.assertEqual([q['name'] for q in bi.shared_with_me(2, ep)[
            'questions']], ['Stored'])
        bi.transfer_owner(1, ep, 'question', qid, 3, 'Stored')
        row = m.BISavedQuestion.query.filter_by(id=qid).one()
        self.assertEqual(row.user_id, 3)
        previous = m.BIGrant.query.filter_by(
            resource_id=qid, principal_user_id=1).one()
        self.assertEqual(previous.level, 'edit')
        audit = m.BIAuditEvent.query.filter_by(resource_id=qid).all()
        self.assertEqual([(a.action, a.actor_user_id, a.target_id)
                          for a in audit], [('owner.transfer', 1, 3)])
        # a override and deleting cleans the grant tables
        bi.access.set_inherit(3, 'question', ep, qid, False)
        self.assertEqual(m.BIAccessOverride.query.count(), 1)
        self.assertIsNone(bi.access.level(2, 'question', ep, qid))
        bi.delete_question(3, ep, qid, 2)
        self.assertEqual(m.BIGrant.query.filter_by(resource_id=qid).count(),
                         0)
        self.assertEqual(m.BIAccessOverride.query.count(), 0)

    def test_dashboard_flow_and_user_deletion_cascade(self):
        m, bi, ep = self.model, self.bi, self.ep
        qid = bi.create_question(1, ep, builder('Q'))['question_id']
        bi.access.add_grant(1, 'question', ep, qid, 'user', 3, 'view')
        did = self.dashboards.create(1, ep, board([qid]))['dashboard_id']
        bi.access.add_grant(1, 'dashboard', ep, did, 'user', 3, 'edit')
        self.dashboards.update(3, ep, did, 1, board([qid], name='Board 2'))
        rows = m.BIDashboardRevision.query.filter_by(
            dashboard_id=did).order_by(m.BIDashboardRevision.revision).all()
        self.assertEqual([(r.revision, r.actor_user_id) for r in rows],
                         [(1, 1), (2, 3)])
        self.assertEqual([d['name'] for d in self.dashboards.list(3, ep)],
                         ['Board 2'])
        self.assertEqual(self.dashboards.list(2, ep), [])
        # a deleted principal's grants disappear with them
        m.db.session.execute(m.BIGrant.__table__.delete().where(
            m.BIGrant.resource_id == 'none'))
        m.db.session.commit()
        self.assertEqual(m.BIGrant.query.filter_by(
            principal_user_id=3).count(), 2)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
