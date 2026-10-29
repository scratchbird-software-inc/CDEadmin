#!/usr/bin/env python3
"""Regenerate web/regression/javascript/bi/sharingFixtures.js.

The sharing UI tests run against responses produced by the real backend
(``BIAccess``, ``BIService``, ``DashboardService`` and ``BIExecutor`` over
SQLite, with the in-memory grant store and user directory of
``tools/tests/bi_permissions_harness.py``) for the scenario below.  Ids are
replaced by stable names so the file only changes when a contract changes.
Run from the repository root:

    python3 tools/tests/fixtures/cdeadmin_bi/generate_sharing_ui_fixtures.py
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'web'))
sys.path.insert(0, str(ROOT / 'tools' / 'tests'))

import bi_permissions_harness as ph  # noqa: E402
from bi_permissions_harness import (  # noqa: E402
    ADMIN, EDITOR, MANAGER, OWNER, STRANGER, VIEWER, SharedStack, board,
)
from pgadmin.cdeadmin.bi import BIError  # noqa: E402
from test_cdeadmin_bi_dashboards import detail_by_region  # noqa: E402
from test_cdeadmin_bi_execution import region_question, sql_question  # noqa: E402

OUT = ROOT / 'web/regression/javascript/bi/sharingFixtures.js'
UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
STAMP = re.compile(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d')
SECRET = ("SELECT region, SUM(amount) AS revenue FROM sales "
          "WHERE product <> 'zzz_hidden_filter' GROUP BY region")


def message(call):
    try:
        call()
    except BIError as exc:
        return str(exc)
    raise SystemExit('expected a refusal')


def main():
    s = SharedStack('sqlite', 'ui')
    ep, bi, access = s.endpoint_id, s.bi, s.bi.access
    names = {}

    def mark(label, value):
        names[value] = label
        return value

    top = mark('c-team', bi.create_collection(
        OWNER, {'name': 'Team'}, ep)['collection_id'])
    sub = mark('c-reports', bi.create_collection(
        OWNER, {'name': 'Reports', 'parent_id': top}, ep)['collection_id'])
    plain = detail_by_region()
    plain['name'] = 'Detail by region'
    plain['collection_id'] = sub
    q_plain = mark('q-detail', s.q(OWNER, plain))
    raw = sql_question(SECRET)
    raw['name'] = 'Secret revenue'
    raw['collection_id'] = sub
    q_raw = mark('q-secret', s.q(OWNER, raw))
    east = region_question()
    east['parameters'][0]['default'] = 'east'
    east['name'] = 'East revenue'
    q_east = mark('q-east', s.q(OWNER, east))
    private = detail_by_region()
    private['name'] = 'Payroll'
    q_private = mark('q-private', s.q(OWNER, private))

    s.share(OWNER, 'collection', top, VIEWER, 'view')
    s.share(OWNER, 'collection', top, 10, 'edit', principal_type='role')
    s.share(OWNER, 'question', q_plain, EDITOR, 'edit')
    s.share(OWNER, 'question', q_east, VIEWER, 'view')
    s.share(OWNER, 'question', q_raw, EDITOR, 'edit')
    d_mixed = mark('d-mixed', s.dashboards.create(
        OWNER, ep, board([q_east, q_private], name='Mixed'))['dashboard_id'])
    s.share(OWNER, 'dashboard', d_mixed, VIEWER, 'view')

    bi.update_question(EDITOR, ep, q_plain, 1, {
        **plain, 'description': 'tuned by the editor'})
    out = {}
    out['ids'] = dict(top=top, sub=sub, plain=q_plain, raw=q_raw, east=q_east,
                      private=q_private, mixed=d_mixed)
    out['principals'] = {'owner': OWNER, 'viewer': VIEWER, 'editor': EDITOR,
                         'manager': MANAGER, 'stranger': STRANGER,
                         'admin': ADMIN}
    out['grantListing'] = access.list_grants(OWNER, 'question', ep, q_plain)
    out['collectionListing'] = access.list_grants(OWNER, 'collection', ep,
                                                  top)
    out['principalSearch'] = access.search_principals(OWNER)
    out['effective'] = {
        'owner': access.effective_access(OWNER, 'question', ep, q_plain),
        'viewer': access.effective_access(VIEWER, 'question', ep, q_plain),
        'editor': access.effective_access(EDITOR, 'question', ep, q_plain),
    }
    out['sharedWithMe'] = bi.shared_with_me(VIEWER, ep)
    out['viewerQuestions'] = bi.list_questions(VIEWER, ep)
    out['viewerDashboards'] = s.dashboards.list(VIEWER, ep)
    out['ownerCollections'] = bi.list_collections(OWNER, ep)
    out['rawForViewer'] = bi.get_question(VIEWER, ep, q_raw)
    out['rawForEditor'] = bi.get_question(EDITOR, ep, q_raw)
    out['plainForViewer'] = bi.get_question(VIEWER, ep, q_plain)
    run = s.run_as(VIEWER, question_id=q_raw)
    out['rawRunForViewer'] = {
        'sql': run['sql'], 'sql_redacted': run['sql_redacted'],
        'kind': run['kind'], 'redacted_columns': run['redacted_columns']}
    out['dashboardForViewer'] = s.dashboards.get(VIEWER, ep, d_mixed)
    ran = s.run_dashboard(VIEWER, d_mixed)
    out['dashboardRunForViewer'] = {
        'cards': {key: ({'type': card['type'], 'ran': True}
                        if 'run' in card else card)
                  for key, card in ran['cards'].items()}}
    out['history'] = bi.history(OWNER, ep, q_plain)
    out['historyForStranger'] = None
    out['errors'] = {
        'viewerUpdate': message(lambda: bi.update_question(
            VIEWER, ep, q_east, 1, east)),
        'strangerGet': message(lambda: bi.get_question(
            STRANGER, ep, q_private)),
        'missingGet': message(lambda: bi.get_question(
            STRANGER, ep, 'no-such-question')),
        'viewerShare': message(lambda: access.list_grants(
            VIEWER, 'question', ep, q_east)),
        'transferWithoutName': message(lambda: bi.transfer_owner(
            OWNER, ep, 'question', q_private, VIEWER, 'wrong')),
    }
    bi.transfer_owner(OWNER, ep, 'question', q_private, VIEWER, 'Payroll')
    out['transfer'] = {'audit': access.audit_trail(
        VIEWER, 'question', ep, q_private)}
    out['audit'] = access.audit_trail(OWNER, 'question', ep, q_plain)

    counter = {}

    def stable(value):
        if isinstance(value, dict):
            return {k: stable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [stable(v) for v in value]
        if isinstance(value, str):
            if value in names:
                return names[value]
            if STAMP.match(value):
                return '2026-10-28T00:00:00+00:00'
            if UUID.search(value):
                return UUID.sub(lambda m: names.get(m.group(0)) or counter
                                .setdefault(m.group(0),
                                            f'g-{len(counter) + 1}'),
                                value)
        return value
    body = json.dumps(stable(out), indent=2, sort_keys=True, default=str)
    OUT.write_text(f'''/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * GENERATED by tools/tests/fixtures/cdeadmin_bi/generate_sharing_ui_fixtures.py; do not edit.
 * Responses of the real sharing backend (BIAccess / BIService / DashboardService / BIExecutor on
 * SQLite with the in-memory grant store of tools/tests/bi_permissions_harness.py) for one scenario:
 * the owner shares the "Team" collection with a viewer and the analysts role, an editor edits one
 * question, a raw SQL question is run by a viewer, and a dashboard has a card whose question is
 * not shared with the viewer.
 */

/* eslint-disable quotes */

export const sharingFixtures = {body};
''')
    print('wrote', OUT)


if __name__ == '__main__':
    main()
