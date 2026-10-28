#!/usr/bin/env python3
"""Regenerate web/regression/javascript/bi/dashboardFixtures.js.

The dashboard UI tests run against documents produced by the real backend
validators (``validate_dashboard``, ``validate_question``), the real
resolution functions and the real DDN converter, for the board that
``tools/tests/test_cdeadmin_bi_dashboards.py`` (``World.document``) builds.
Run from the repository root:

    python3 tools/tests/fixtures/cdeadmin_bi/generate_dashboard_ui_fixtures.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'web'))
sys.path.insert(0, str(ROOT / 'tools' / 'tests'))

from pgadmin.cdeadmin.bi import dashboard_ddn  # noqa: E402
from pgadmin.cdeadmin.bi.dashboard_models import (  # noqa: E402
    check_mappings, resolve_cross_filter, resolve_drill, resolve_filters,
    validate_dashboard,
)
from pgadmin.cdeadmin.bi.models import validate_question  # noqa: E402
from test_cdeadmin_bi_execution import region_question  # noqa: E402
from test_cdeadmin_bi_dashboards import (  # noqa: E402
    FIXTURES, card, detail_by_region, floor_sql_question,
)

OUT = ROOT / 'web/regression/javascript/bi/dashboardFixtures.js'
IDS = {'region': 'q-by-region', 'detail': 'q-detail', 'floor': 'q-floor'}


def board():
    return {
        'name': 'Sales board',
        'tabs': [{'id': 'main', 'name': 'Main'}],
        'cards': [
            card('by_region', IDS['region'], x=0),
            card('detail', IDS['detail'], x=12),
            card('floor', IDS['floor'], x=0, y=6),
            {'id': 'note', 'tab_id': 'main', 'type': 'text',
             'layout': {'x': 12, 'y': 6, 'w': 12, 'h': 2},
             'text': {'markdown': '# Sales'}},
        ],
        'filters': [
            {'id': 'region', 'name': 'Region', 'type': 'string',
             'widget': 'select', 'allowed_values': ['east', 'west'],
             'targets': [
                 {'card_id': 'by_region', 'parameter_id': 'region'},
                 {'card_id': 'detail', 'field': {'column': 'region'}}]},
            {'id': 'floor', 'name': 'Minimum', 'type': 'integer',
             'widget': 'number', 'default': 0,
             'targets': [{'card_id': 'floor', 'parameter_id': 'floor'}]},
            {'id': 'window', 'name': 'Window', 'type': 'date',
             'widget': 'date_range', 'targets': []},
            {'id': 'products', 'name': 'Products', 'type': 'string',
             'widget': 'multi_select', 'allowed_values': ['a', 'b'],
             'targets': [{'card_id': 'detail',
                          'field': {'column': 'product'}}]},
        ],
        'cross_filters': [
            {'id': 'click_region', 'source_card_id': 'detail',
             'source_column': 'region', 'filter_id': 'region'}],
        'drill_throughs': [
            {'id': 'to_floor', 'source_card_id': 'detail',
             'trigger': {'column': 'amount'}, 'label': 'Floor view',
             'target': {'kind': 'question', 'question_id': IDS['floor'],
                        'revision': 1, 'parameter_mappings': [
                            {'parameter_id': 'floor',
                             'from': {'column': 'amount'}}]}},
            {'id': 'to_board', 'source_card_id': 'by_region',
             'trigger': {'row': True},
             'target': {'kind': 'dashboard', 'dashboard_id': 'd-other',
                        'filter_mappings': [
                            {'filter_id': 'region',
                             'from': {'filter_id': 'region'}}]}},
        ],
        'settings': {'auto_refresh_seconds': 60},
    }


def main():
    document = validate_dashboard(board())
    questions = {
        IDS['region']: validate_question(region_question()),
        IDS['detail']: validate_question(detail_by_region()),
        IDS['floor']: validate_question(floor_sql_question()),
    }
    check_mappings(document, {
        (IDS['region'], 1): questions[IDS['region']],
        (IDS['detail'], 1): questions[IDS['detail']],
        (IDS['floor'], 1): questions[IDS['floor']]})
    monitoring = json.loads(FIXTURES.read_text(encoding='utf-8'))
    converted = dashboard_ddn.ddn_to_dashboard(
        monitoring['sqlite_database']['snapshot'])
    fleet = dashboard_ddn.ddn_to_dashboard(
        monitoring['sqlite_engine_fleet']['snapshot'])
    cross = resolve_cross_filter(document, 'click_region', {'region': 'west'},
                                 {'floor': 5})
    resolved = resolve_filters(document, {'region': 'east'})
    cross_resolved = resolve_filters(document, cross['filters'],
                                     cross['exclude'])
    drill = resolve_drill(document, 'to_floor', {'amount': 10})
    drill_board = resolve_drill(document, 'to_board', {'region': 'east'},
                                {'region': 'east'})
    payload = {
        'ids': IDS,
        'board': document,
        'questions': questions,
        'resolved': resolved,
        'cross': {'outcome': cross, 'resolved': cross_resolved},
        'drill': drill,
        'drillBoard': drill_board,
        'monitoring': {'dashboard': converted['dashboard'],
                       'loss': converted['loss']},
        'fleet': {'dashboard': fleet['dashboard'], 'loss': fleet['loss']},
    }
    header = (
        '/////////////////////////////////////////////////////////////\n'
        '//\n// CDEadmin - Multi-engine Database Administration\n//\n'
        '// Copyright (C) 2013 - 2026, The pgAdmin Development Team\n'
        '// This software is released under the PostgreSQL Licence\n//\n'
        '//////////////////////////////////////////////////////////////\n\n'
        '/*\n * GENERATED by tools/tests/fixtures/cdeadmin_bi/'
        'generate_dashboard_ui_fixtures.py; do not edit.\n'
        ' * The board is World.document() of '
        'tools/tests/test_cdeadmin_bi_dashboards.py (plus a date-range and a\n'
        ' * multi-select filter and a dashboard drill-through) normalized by '
        'validate_dashboard;\n * the questions are validate_question output; '
        'resolved/cross/drill are the real\n * resolve_filters, '
        'resolve_cross_filter and resolve_drill results; monitoring and\n'
        ' * fleet are ddn_to_dashboard of the encoder fixtures.\n */\n\n'
        '/* eslint-disable quotes */\n\n')
    body = 'export const dashboardFixtures = ' + json.dumps(
        payload, indent=2, sort_keys=True) + ';\n'
    OUT.write_text(header + body, encoding='utf-8')
    print('wrote', OUT.relative_to(ROOT))


if __name__ == '__main__':
    main()
