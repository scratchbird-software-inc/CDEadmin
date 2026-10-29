##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Shared harness: real ``ResultService`` over real SQLite / DuckDB.

The production SQLite and DuckDB providers refuse a runtime whose version
differs from the admitted profile, so tests cannot open them in every
environment.  This harness keeps everything above the driver real (semantic
compiler, dialect contract, bound parameters, ``ResultService`` admission,
paging, redaction, export) and replaces only the Data Studio session with one
that runs the statement on an in-memory ``sqlite3`` / ``duckdb`` connection.
"""

from __future__ import annotations

import copy
import sqlite3
import sys
import uuid
from pathlib import Path
from types import ModuleType, SimpleNamespace

try:
    import duckdb
except ImportError:  # pragma: no cover
    duckdb = None

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WEB = ROOT / 'web'
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(WEB / 'pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.bi import BIService  # noqa: E402
from pgadmin.cdeadmin.bi.execution import BIExecutor  # noqa: E402
from pgadmin.cdeadmin.results import (  # noqa: E402
    InlineRendererExecutor, ResultAdapterContribution, ResultService,
)
from pgadmin.cdeadmin.semantic_models import (  # noqa: E402
    SemanticModelService,
)

from test_cdeadmin_bi_saved_questions import (  # noqa: E402
    MemoryBI, MemorySemantic, PROVIDERS, ROWS,
)
from test_cdeadmin_result_renderers import (  # noqa: E402
    CAPABILITY, context as result_context, identity as result_identity,
    result as result_template,
)


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def seed_sql():
    return [
        'CREATE TABLE sales (region VARCHAR, product VARCHAR, '
        'amount INTEGER, qty INTEGER, notes VARCHAR)',
    ]


def connect(engine):
    if engine == 'sqlite':
        connection = sqlite3.connect(':memory:')
    else:
        connection = duckdb.connect(':memory:')
    connection.execute(seed_sql()[0])
    for region, product, amount, qty in ROWS:
        connection.execute(
            'INSERT INTO sales VALUES (?, ?, ?, ?, ?)',
            [region, product, amount, qty, f'private-{product}'])
    return connection


class LiveProvider:
    """Semantic dialect of the real pilot plus a tabular result adapter."""

    def __init__(self, ctx, pilot):
        self.context = ctx
        self.pilot = pilot
        self.records = {}

    def __getattr__(self, name):
        return getattr(self.pilot, name)

    @staticmethod
    def _describe(binding, result):
        records = copy.deepcopy(binding.instance.records[result['result_id']])
        return {
            'descriptor_version': '1.0.0',
            'capability_id': CAPABILITY,
            'records': records,
            'limits': {'max_records': 10000, 'max_page_size': 500,
                       'max_record_bytes': 65536,
                       'max_descriptor_bytes': 4 * 1024 * 1024},
            'sampling': {'mode': 'head', 'limit': max(len(records), 1)},
            'export_policy': {'enabled': True,
                              'formats': ['csv', 'json', 'jsonl'],
                              'max_records': 10000,
                              'max_bytes': 1024 * 1024, 'redact_keys': []},
            'worker_policy': {'required': False, 'timeout_seconds': 2.0},
            'renderer_id': 'cdeadmin.result.tabular.legacy-grid',
            'component_reference': 'SchemaView/DataGridView',
        }

    @classmethod
    def result_contributions(cls):
        return {'adapters': (ResultAdapterContribution(
            'live.tabular.adapter', frozenset({'tabular'}), CAPABILITY,
            cls._describe),)}

    def select_renderer(self, _result):
        return {
            'identity': result_identity(),
            'endpoint_id': self.context.endpoint_id,
            'resource_id': 'live:renderer:tabular',
            'identity_kind': 'provider-renderer-id',
            'resource_kind': 'result-renderer',
            'model_family': 'relational',
            'display_name': 'Live tabular renderer',
            'parent_resource_id': None,
            'display_path': ['Live', 'Tabular'],
            'authority_path': ['live', 'renderer', 'tabular'],
            'is_virtual': True,
            'generation': self.context.cache_namespace,
            'capability_ids': [CAPABILITY],
            'extensions': {},
        }


class LiveStudio:
    """The slice of ``DataStudioService`` the BI executor calls."""

    def __init__(self, connection, results, provider):
        self.connection = connection
        self.results = results
        self.provider = provider
        self.calls = []
        self.closed = []
        self._occurrences = {}

    def open_session(self, context, endpoint, language):
        self.language = language
        return {'provider_session': {'session_id': str(uuid.uuid4())}}

    def execute(self, context, session_id, source, parameters=None,
                output_policy=None):
        self.calls.append({'source': source,
                           'parameters': copy.deepcopy(parameters),
                           'output_policy': copy.deepcopy(output_policy)})
        cursor = self.connection.cursor() if hasattr(
            self.connection, 'cursor') else self.connection
        if isinstance(self.connection, sqlite3.Connection):
            cursor.execute(source, parameters or [])
            rows = cursor.fetchall()
            names = [c[0] for c in cursor.description]
        else:
            self.connection.execute(source, parameters or [])
            rows = self.connection.fetchall()
            names = [c[0] for c in self.connection.description]
        occurrence_id = str(uuid.uuid4())
        result = result_template(str(uuid.uuid4()))
        result.update(execution_id=occurrence_id, complete=True,
                      continuation=None)
        result['schema'] = {'columns': [{'name': n} for n in names]}
        self.provider.records[result['result_id']] = [
            dict(zip(names, row)) for row in rows]
        self._occurrences[occurrence_id] = result
        return {'occurrence_id': occurrence_id}

    def poll(self, context, occurrence_id):
        return {'operation': {'terminal': True},
                'result': copy.deepcopy(self._occurrences[occurrence_id])}

    def request_cancel(self, context, occurrence_id):  # pragma: no cover
        return {}

    def admit_result(self, context, occurrence_id, capabilities):
        return self.results.admit_provider_result(
            context, copy.deepcopy(self._occurrences[occurrence_id]),
            frozenset(capabilities))

    def close_session(self, context, session_id):
        self.closed.append(session_id)
        return {}


class Stack:
    """One engine's complete BI stack."""

    def __init__(self, engine, label='stack'):
        self.engine = engine
        self.clock = FakeClock()
        self.ctx = result_context(f'{label}-{engine}')
        self.pilot = PROVIDERS[engine]
        self.provider = LiveProvider(self.ctx, self.pilot)
        binding = SimpleNamespace(
            context=self.ctx, instance=self.provider,
            manifest={'identity': result_identity(),
                      'contracts': ['ResultRenderer']})
        registry = SimpleNamespace(resolve=lambda _ctx: binding)
        self.results = ResultService(registry,
                                     executor=InlineRendererExecutor())
        self.connection = connect(engine)
        self.studio = LiveStudio(self.connection, self.results,
                                 self.provider)
        self.bi = BIService(SemanticModelService(MemorySemantic()),
                            MemoryBI())
        self.executor = BIExecutor(
            self.bi, self.studio, self.results, clock=self.clock,
            sleeper=lambda _s: None)
        self.endpoint = {'route': {}}

    def run(self, user_id=1, **request):
        return self.executor.run(
            provider=self.provider, context=self.ctx,
            endpoint=self.endpoint, user_id=user_id, **request)

    def create(self, question, user_id=1):
        return self.bi.create_question(user_id, self.ctx.endpoint_id,
                                       question)
