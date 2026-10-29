#!/usr/bin/env python3
"""Regenerate web/regression/javascript/bi/embedFixtures.js.

The embed UI tests run against responses produced by the real backend
(``BIEmbedService`` and the unauthenticated blueprint over ``BIService``,
``DashboardService`` and ``BIExecutor`` on SQLite, with the in-memory
repository, fake clock and fake scheduler of ``tools/tests/bi_embed_harness.py``)
for the scenario below.  Ids are replaced by stable names, timestamps by a
fixed one, and signing secrets and tokens by placeholders, so the file only
changes when a contract changes.  Run from the repository root:

    python3 tools/tests/fixtures/cdeadmin_bi/generate_embed_ui_fixtures.py
"""

import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'web'))
sys.path.insert(0, str(ROOT / 'tools' / 'tests'))

from bi_embed_harness import EmbedStack, ORIGINS  # noqa: E402
from bi_permissions_harness import MANAGER, OWNER, VIEWER  # noqa: E402
from pgadmin.cdeadmin.bi import BIError  # noqa: E402
from test_cdeadmin_bi_embedding import sales_board  # noqa: E402
from test_cdeadmin_bi_execution import sql_question  # noqa: E402

OUT = ROOT / 'web/regression/javascript/bi/embedFixtures.js'
UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
STAMP = re.compile(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d')
DAY = re.compile(r'^\d{4}-\d\d-\d\d$')
JWT = re.compile(r'[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}')


def refusal(label, call):
    try:
        call()
    except BIError as exc:
        return str(exc)
    raise SystemExit('expected a refusal: ' + label)


def main():
    st = EmbedStack(config={'allow_downloads': True})
    ep, svc = st.ep, st.service
    names, texts = {}, {}

    def mark(label, value):
        names[value] = label
        return value

    def secret_text(label, secret):
        texts[secret['secret']] = label
        texts[secret['kid']] = label.replace('SECRET', 'kid')
        return secret

    did, parts = sales_board(st)
    mark('d-sales', did)
    mark('q-region', parts.by_region)
    mark('q-detail', parts.detail)
    mark('q-other', parts.other)
    for qid in (parts.by_region, parts.detail, parts.other):
        st.s.share(OWNER, 'question', qid, MANAGER, 'view')
    st.s.share(OWNER, 'dashboard', did, MANAGER, 'manage')
    st.s.share(OWNER, 'dashboard', did, VIEWER, 'view')

    out = {'principals': {'owner': OWNER, 'manager': MANAGER, 'viewer': VIEWER},
           'dashboardId': did, 'origins': ORIGINS}
    out['dashboardFilters'] = st.s.dashboards.get(
        OWNER, ep, did)['definition']['filters']
    out['catalog'] = svc.catalog()

    server = SimpleNamespace(user_id=OWNER)
    partner = svc.create(OWNER, ep, st.definition(
        'dashboard', did, name='Partner portal',
        parameters=[{'id': 'region', 'mode': 'editable'}],
        claims=[{'name': 'tenant_id', 'required': True}],
        max_token_lifetime_seconds=900))
    mark('e-partner', partner['embed']['embed_id'])
    secret_text('SECRET-1', partner['secret'])
    out['created'] = partner
    eid = partner['embed']['embed_id']
    out['enabled'] = svc.enable(OWNER, ep, eid, server)

    token = st.token(eid, partner['secret'], params={'region': 'east'},
                     claims={'tenant_id': 7})
    texts[token] = 'TOKEN-1'
    for _ in range(3):
        st.get(eid, '/data', token)
    st.post(eid, '/cards/detail/run', token)
    st.post(eid, '/cards/by_region/run', token)
    st.get(eid, '/data', 'garbage')  # refusals are not counted
    out['stats'] = svc.stats(OWNER, ep, eid, 7)

    minted = svc.mint(OWNER, ep, eid, {'region': 'west'}, {'tenant_id': 9},
                      120)
    texts[minted['token']] = 'TOKEN-2'
    out['minted'] = minted
    out['checkValid'] = svc.check_token(OWNER, ep, eid, minted['token'])
    out['checkInvalid'] = svc.check_token(OWNER, ep, eid, 'not.a.token')
    out['checkNoClaim'] = svc.check_token(OWNER, ep, eid, st.token(
        eid, partner['secret'], params={'region': 'east'}))
    preview = svc.preview(OWNER, ep, eid, {'region': 'east'},
                          {'tenant_id': 7})
    texts[preview['token']] = 'TOKEN-3'
    out['preview'] = preview

    # a second embed that is created but not enabled, and one that is revoked
    draft = svc.create(OWNER, ep, st.definition(
        'dashboard', did, name='Draft embed',
        parameters=[{'id': 'region', 'mode': 'locked'}], origins=[]))
    mark('e-draft', draft['embed']['embed_id'])
    secret_text('SECRET-2', draft['secret'])
    out['draft'] = draft
    gone = svc.create(OWNER, ep, st.definition(
        'dashboard', did, name='Old embed',
        parameters=[{'id': 'region', 'mode': 'hidden'}]))
    mark('e-old', gone['embed']['embed_id'])
    secret_text('SECRET-3', gone['secret'])
    svc.enable(OWNER, ep, gone['embed']['embed_id'], server)
    out['revoked'] = svc.revoke(OWNER, ep, gone['embed']['embed_id'])

    rotated = svc.rotate(OWNER, ep, eid)
    secret_text('SECRET-4', rotated['secret'])
    out['rotated'] = rotated
    out['retired'] = svc.retire_previous_key(OWNER, ep, eid)

    out['list'] = svc.list(OWNER, ep, 'dashboard', did)
    out['listForManager'] = svc.list(MANAGER, ep, 'dashboard', did)
    out['getForManager'] = svc.get(MANAGER, ep, eid)
    out['disabledByManager'] = svc.disable(MANAGER, ep, eid)
    out['reenabled'] = svc.enable(OWNER, ep, eid, server)

    raw = st.s.q(OWNER, sql_question('SELECT region FROM sales'))
    mark('q-raw', raw)
    out['errors'] = {
        'rawSql': refusal('rawSql', lambda: svc.create(OWNER, ep, st.definition(
            'question', raw, name='Raw'))),
        'badOrigin': refusal('badOrigin', lambda: svc.create(OWNER, ep, st.definition(
            'dashboard', did, name='Bad', origins=['https://*.example.com'],
            parameters=[{'id': 'region', 'mode': 'locked'}]))),
        'reservedClaim': refusal('reservedClaim', lambda: svc.create(OWNER, ep, st.definition(
            'dashboard', did, name='Bad', claims=[{'name': 'user_id'}],
            parameters=[{'id': 'region', 'mode': 'locked'}]))),
        'unknownParameter': refusal('unknownParameter', lambda: svc.create(OWNER, ep,
            st.definition('dashboard', did, name='Bad', parameters=[
                {'id': 'nope', 'mode': 'locked'}]))),
        'staleRevision': refusal('staleRevision', lambda: svc.update(
            OWNER, ep, eid, 99, st.definition('dashboard', did,
                parameters=[{'id': 'region', 'mode': 'locked'}]))),
        'viewerList': refusal('viewerList', lambda: svc.list(VIEWER, ep, 'dashboard', did)),
        'managerRotate': refusal('managerRotate', lambda: svc.rotate(MANAGER, ep, eid)),
        'mintTooLong': refusal('mintTooLong', lambda: svc.mint(
            OWNER, ep, eid, {'region': 'east'}, {'tenant_id': 1}, 100000)),
        'previewDisabled': refusal('previewDisabled', lambda: svc.preview(
            OWNER, ep, draft['embed']['embed_id'])),
    }

    # an embed made by a manager is disabled when that manager loses manage
    theirs = svc.create(MANAGER, ep, st.definition(
        'dashboard', did, name='Manager embed',
        parameters=[{'id': 'region', 'mode': 'locked'}]))
    mark('e-theirs', theirs['embed']['embed_id'])
    secret_text('SECRET-5', theirs['secret'])
    tid = theirs['embed']['embed_id']
    svc.enable(MANAGER, ep, tid, SimpleNamespace(user_id=MANAGER))
    grant = st.s.grants.find(ep, 'dashboard', did, 'user', MANAGER)
    st.s.grants.set_level(grant['grant_id'], 'edit')
    lost_token = st.token(tid, theirs['secret'], params={'region': 'east'})
    texts[lost_token] = 'TOKEN-4'
    st.get(tid, '/data', lost_token)
    out['ownerLost'] = svc.get(OWNER, ep, tid)

    counter = {}

    def stable(value):
        if isinstance(value, dict):
            return {k: stable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [stable(v) for v in value]
        if isinstance(value, str):
            if value in texts:
                return texts[value]
            if value in names:
                return names[value]
            if STAMP.match(value):
                return '2026-10-28T00:00:00+00:00'
            if DAY.match(value):
                return '2026-03-02'
            if UUID.search(value):
                return UUID.sub(lambda m: names.get(m.group(0)) or counter
                                .setdefault(m.group(0),
                                            f'g-{len(counter) + 1}'),
                                value)
        return value

    text = json.dumps(stable(out), indent=2, sort_keys=True, default=str)
    for secret in texts:  # nothing real may reach the file
        assert secret not in text, 'a secret leaked into the fixture'
    assert not JWT.search(text.replace('TOKEN', 'x')), 'a token leaked'
    OUT.write_text(f'''/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * GENERATED by tools/tests/fixtures/cdeadmin_bi/generate_embed_ui_fixtures.py; do not edit.
 * Responses of the real embedding backend (BIEmbedService and the public blueprint over BIService /
 * DashboardService / BIExecutor on SQLite with the in-memory repository, fake clock and fake scheduler of
 * tools/tests/bi_embed_harness.py) for one scenario: the owner embeds a sales dashboard for a partner
 * (editable region, required tenant claim), enables it, mints and previews tokens, the embed is viewed a
 * few times, a key is rotated and retired; a second embed is only created and a third revoked; a manager
 * sees the list without keys and disables the embed; and refusals. Signing secrets and tokens are
 * placeholders.
 */

/* eslint-disable quotes */

export const embedFixtures = {text};
''')
    print('wrote', OUT)


if __name__ == '__main__':
    main()
