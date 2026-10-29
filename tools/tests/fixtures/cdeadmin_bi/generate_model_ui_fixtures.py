#!/usr/bin/env python3
"""Regenerate web/regression/javascript/bi/modelFixtures.js.

The Models view tests run against what the real backend returns for the
semantic_model_* workspace actions: ``validate_model`` / ``public_model``
documents, the lifecycle records, history and compare, the validator and
lineage output, the workspace capability catalog and the migration reports
(dry run, applied, repeated, and a lossy model). Run from the repository
root:

    python3 tools/tests/fixtures/cdeadmin_bi/generate_model_ui_fixtures.py

Identifiers and timestamps are replaced by stable names so the output only
changes when the backend contract does.
"""

import copy
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'web'))
sys.path.insert(0, str(ROOT / 'tools' / 'tests'))

from pgadmin.cdeadmin.workspace import ProviderWorkspaceService  # noqa: E402
from test_cdeadmin_bi_model_migration import (  # noqa: E402
    OWNER, World, legacy_model, windowed,
)

OUT = ROOT / 'web/regression/javascript/bi/modelFixtures.js'
UUID = re.compile(
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
TIME = re.compile(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(\+00:00|Z)?')


class Actions:
    def __init__(self, world):
        service = ProviderWorkspaceService.__new__(ProviderWorkspaceService)
        service.semantic_model_service = world.semantic
        service.bi_service = world.stack.bi
        world.stack.bi.dashboards = world.dashboards
        service.report_delivery_service = None
        service.report_scheduler_service = None
        context = world.stack.ctx
        provider = world.stack.provider
        service.endpoint_service = SimpleNamespace(
            workspace=lambda _server: (context, {'route': {}}, None),
            provider_registry=SimpleNamespace(
                resolve=lambda _c: SimpleNamespace(instance=provider)))
        self.service = service
        self.server = SimpleNamespace(user_id=OWNER)

    def __call__(self, action, **request):
        return self.service.semantic_model_action(
            self.server, action, request)


def stable(text):
    names = {}

    def name(match):
        return names.setdefault(match.group(0), f'id-{len(names) + 1:03d}')

    text = UUID.sub(name, text)
    return TIME.sub('2026-01-01T00:00:00+00:00', text)


def build():
    world = World()
    act = Actions(world)
    model_id = world.model['model_id']
    draft = act('semantic_model_get', model_id=model_id)

    first = copy.deepcopy(draft['definition'])
    edited = copy.deepcopy(first)
    edited['description'] = 'Revenue by region'
    updated = act('semantic_model_update', model_id=model_id,
                  expected_revision=draft['revision'], definition=edited)
    published = act('semantic_model_status', model_id=model_id,
                    expected_revision=updated['revision'],
                    status='published')

    lossy = world.semantic.create(
        OWNER, world.endpoint, {**windowed(legacy_model()),
                                'name': 'Trend cube'})

    migration = {
        'dry': act('semantic_model_migrate', model_id=model_id),
        'applied': act('semantic_model_migrate', model_id=model_id,
                       dry_run=False),
        'again': act('semantic_model_migrate', model_id=model_id,
                     dry_run=False),
        'lossyDry': act('semantic_model_migrate',
                        model_id=lossy['model_id']),
        'lossyAccepted': act('semantic_model_migrate',
                             model_id=lossy['model_id'], dry_run=False,
                             accept_loss=True),
    }
    return {
        'ids': {'model': model_id, 'lossy': lossy['model_id']},
        'catalog': act('semantic_model_capabilities'),
        # the in-memory test repository does not implement list(); summarize its rows the way the service does
        'list': sorted((world.semantic._summary(row) for row in
                        world.semantic.repository.rows.values()),
                       key=lambda item: item['name']),
        'draft': draft,
        'updated': updated,
        'published': published,
        'history': act('semantic_model_history', model_id=model_id),
        'compare': act('semantic_model_compare', model_id=model_id,
                       left_revision=1, right_revision=2),
        'validOutcome': act('semantic_model_validate',
                            definition=draft['definition']),
        'invalidOutcome': act('semantic_model_validate',
                              definition={'name': 'Broken'}),
        'lineage': act('semantic_model_lineage',
                       definition=draft['definition']),
        'lossy': act('semantic_model_get', model_id=lossy['model_id']),
        'migration': migration,
    }


def main():
    header = (
        '/////////////////////////////////////////////////////////////\n'
        '//\n// CDEadmin - Multi-engine Database Administration\n//\n'
        '// Copyright (C) 2013 - 2026, The pgAdmin Development Team\n'
        '// This software is released under the PostgreSQL Licence\n//\n'
        '//////////////////////////////////////////////////////////////\n\n'
        '/*\n * GENERATED by tools/tests/fixtures/cdeadmin_bi/'
        'generate_model_ui_fixtures.py; do not edit.\n'
        ' * Every value is the real backend result of the semantic_model_* '
        'workspace action\n * named by its key (validate_model output, '
        'history, compare, lineage, capabilities,\n * migration reports) for '
        'the model of tools/tests/test_cdeadmin_bi_model_migration.py.\n'
        ' * Identifiers and timestamps are replaced by stable names.\n */\n\n'
        '/* eslint-disable quotes */\n\n')
    body = 'export const modelFixtures = ' + stable(json.dumps(
        build(), indent=2, sort_keys=True, default=str)) + ';\n'
    OUT.write_text(header + body, encoding='utf-8')
    print('wrote', OUT.relative_to(ROOT))


if __name__ == '__main__':
    main()
