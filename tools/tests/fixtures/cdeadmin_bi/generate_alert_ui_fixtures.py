#!/usr/bin/env python3
"""Regenerate web/regression/javascript/bi/alertFixtures.js.

The alerts UI tests run against responses produced by the real backend
(``BIAlertService`` over ``BIService``, ``DashboardService`` and
``BIExecutor`` on SQLite, with the in-memory repository, fake clock and
stub transports of ``tools/tests/bi_alerts_harness.py``) for the scenario
below.  Ids are replaced by stable names and timestamps by a fixed one, so
the file only changes when a contract changes.  Run from the repository root:

    python3 tools/tests/fixtures/cdeadmin_bi/generate_alert_ui_fixtures.py
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'web'))
sys.path.insert(0, str(ROOT / 'tools' / 'tests'))

from bi_alerts_harness import (  # noqa: E402
    AlertStack, alert_definition, column_metric, rows_over,
    subscription_definition,
)
from bi_permissions_harness import OWNER, VIEWER  # noqa: E402
from pgadmin.cdeadmin.bi import BIError  # noqa: E402
from test_cdeadmin_bi_alerts import export_policy, question  # noqa: E402

OUT = ROOT / 'web/regression/javascript/bi/alertFixtures.js'
UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
STAMP = re.compile(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d')


def refusal(call):
    try:
        call()
    except BIError as exc:
        return str(exc)
    raise SystemExit('expected a refusal')


def main():
    st = AlertStack(external={'domains': ['corp.example']})
    ep, svc = st.ep, st.service
    names = {}

    def mark(label, value):
        names[value] = label
        return value

    base = question('Detail by region', **export_policy('csv', 'xlsx'))
    qid = mark('q-detail', st.s.q(OWNER, base))
    st.s.share(OWNER, 'question', qid, VIEWER, 'view')

    out = {'principals': {'owner': OWNER, 'viewer': VIEWER}}
    out['questionId'] = qid
    out['catalog'] = svc.catalog(OWNER)
    out['schedulePreview'] = svc.schedule_preview(
        {'expression': '0 8 * * 1-5', 'timezone': 'Europe/Berlin'}, 3)

    watch = st.create(alert_definition(
        qid, rows_over(3), name='Many rows'))
    mark('a-watch', watch['alert_id'])
    out['created'] = watch
    out['firstRun'] = st.run(watch['alert_id'])
    st.clock.advance(hours=1)
    st.run(watch['alert_id'])
    out['history'] = svc.history(OWNER, ep, watch['alert_id'])

    # muted before its first breach: the check runs, the notification waits
    snoozed = st.create(alert_definition(qid, rows_over(1), name='Snoozed'))
    mark('a-snoozed', snoozed['alert_id'])
    svc.mute(OWNER, ep, snoozed['alert_id'], None, 120)
    st.run(snoozed['alert_id'])
    out['muted'] = svc.get(OWNER, ep, snoozed['alert_id'])
    out['mutedHistory'] = svc.history(OWNER, ep, snoozed['alert_id'])

    quiet = st.create(alert_definition(
        qid, column_metric('amount', 'sum', '>', 1000000), name='Amount'))
    mark('a-quiet', quiet['alert_id'])
    st.run(quiet['alert_id'])
    out['quiet'] = svc.get(OWNER, ep, quiet['alert_id'])

    digest = st.create(subscription_definition(
        'question', qid, name='Daily digest', fmt='csv',
        channels=[{'type': 'in_app', 'recipients': [{'type': 'self'}]},
                  {'type': 'email', 'profile_id': 'mail',
                   'recipients': [{'type': 'self'}]}]))
    mark('a-digest', digest['alert_id'])
    out['subscription'] = digest

    # an alert owned by the viewer pauses when the viewer loses access
    theirs = st.create(alert_definition(qid, rows_over(0), name='Viewer watch'),
                       user=VIEWER)
    mark('a-theirs', theirs['alert_id'])
    st.run(theirs['alert_id'])
    grant = st.s.bi.access.grants.find(ep, 'question', qid, 'user', VIEWER)
    st.s.bi.access.remove_grant(OWNER, 'question', ep, qid,
                                grant['grant_id'])
    st.run(theirs['alert_id'])
    out['paused'] = svc.get(VIEWER, ep, theirs['alert_id'])
    out['pausedHistory'] = svc.history(VIEWER, ep, theirs['alert_id'])
    st.s.share(OWNER, 'question', qid, VIEWER, 'view')

    out['list'] = {'items': svc.list(OWNER, ep, 'question', qid, None)}
    out['listForViewer'] = {'items': svc.list(VIEWER, ep, 'question', qid,
                                              None)}

    out['testAlert'] = svc.test(OWNER, ep, runtime=st.runtime(),
                                value=alert_definition(
                                    qid, rows_over(3), name='Many rows'))
    out['testStored'] = svc.test(OWNER, ep, runtime=st.runtime(),
                                 alert_id=quiet['alert_id'])
    out['testSubscription'] = svc.test(
        OWNER, ep, runtime=st.runtime(),
        value=subscription_definition('question', qid, name='Digest',
                                      fmt='csv'))
    out['notifications'] = svc.notifications(OWNER, ep)

    out['errors'] = {
        'othersHistory': refusal(lambda: svc.history(
            VIEWER, ep, watch['alert_id'])),
        'badSchedule': refusal(lambda: svc.schedule_preview(
            {'expression': 'not cron', 'timezone': 'UTC'})),
        'tooFrequent': refusal(lambda: st.create(alert_definition(
            qid, rows_over(1), name='Often',
            schedule={'expression': '* * * * *', 'timezone': 'UTC'}))),
        'viewerWebhook': refusal(lambda: st.create(alert_definition(
            qid, rows_over(1), name='Hook',
            channels=[{'type': 'webhook',
                       'url': 'https://hooks.example/x'}]), user=VIEWER)),
    }

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
 * GENERATED by tools/tests/fixtures/cdeadmin_bi/generate_alert_ui_fixtures.py; do not edit.
 * Responses of the real alerts backend (BIAlertService over BIService / DashboardService / BIExecutor
 * on SQLite with the in-memory repository and fake clock of tools/tests/bi_alerts_harness.py) for one
 * scenario: the owner watches a question with a row-count alert (fired, quiet and muted checks), a
 * revenue alert that stays quiet, and a daily digest subscription; a viewer's alert pauses when the
 * viewer loses access; dry runs of an alert and a subscription; and refusals.
 */

/* eslint-disable quotes */

export const alertFixtures = {body};
''')
    print('wrote', OUT)


if __name__ == '__main__':
    main()
