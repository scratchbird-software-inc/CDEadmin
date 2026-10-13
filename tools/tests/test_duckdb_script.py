"""Native DuckDB scripts submit each statement once on the retained session."""

import time
from types import SimpleNamespace

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.data_studio.scripts import ScriptCoordinator
from pgadmin.cdeadmin.providers.duckdb.provider import (
    DuckDBPilotProvider, _create_client,
)


def test_native_script_sequences_and_stops_at_first_error(tmp_path):
    pytest.importorskip('duckdb')
    pytest.importorskip('pyarrow')
    client = _create_client()
    path = tmp_path / 'script.duckdb'
    handle = client.open_session({'route': {
        'database': str(path), 'filesystem_root': str(tmp_path)}})
    provider = object.__new__(DuckDBPilotProvider)
    provider.client = client
    provider._sessions = {'native': SimpleNamespace(handle=handle)}
    context = SimpleNamespace(endpoint_id='owned')

    class Studio:
        def __init__(self):
            self.scripts = ScriptCoordinator(self)
            self.tokens = {}
            self.calls = []
            self._occurrences = {}

        def _operational_session(self, _context, session_id):
            assert session_id == 'owned-session'
            return (SimpleNamespace(language_profile='duckdb-sql',
                provider_session={'session_id': 'native'}),
                SimpleNamespace(instance=provider))

        def execute(self, _context, session_id, source, *, _script_plan_id):
            assert session_id == 'owned-session' and _script_plan_id
            token = client.execute(handle, {'source': source, 'parameters': {}})
            occurrence_id = str(len(self.calls))
            self.calls.append(source)
            self.tokens[occurrence_id] = token
            return {'occurrence_id': occurrence_id}

        def poll(self, _context, occurrence_id):
            page = client.describe_result(self.tokens[occurrence_id])
            return {'operation': {'terminal': page['complete']},
                'result': {'complete': page['complete'],
                    'extensions': {'duckdb': {'payload': page['payload']}}}}

    def run(studio, source):
        plan = studio.scripts.prepare(context, 'owned-session', source)
        assert plan['state'] == 'ready'
        deadline = time.monotonic() + 10
        while plan['state'] not in {'stopped', 'complete'}:
            assert time.monotonic() < deadline
            updated = studio.scripts.advance(context, plan['plan_id'], plan['revision'])
            if updated['revision'] == plan['revision']:
                time.sleep(.01)
            plan = updated
        return plan

    try:
        studio = Studio()
        result = run(studio, 'CREATE TABLE facts(i INTEGER); '
            'INSERT INTO facts VALUES (1); SELECT count(*) FROM facts;')
        assert result['state'] == 'complete'
        assert len(studio.calls) == 3
        assert handle.execute('SELECT count(*) FROM facts').fetchone() == (1,)
        failed = run(studio, 'SELECT 1; SELECT absent_column; '
            'CREATE TABLE never_submitted(i INTEGER);')
        assert failed['state'] == 'stopped' and failed['stop_reason'] == 'error'
        assert len(studio.calls) == 5
        assert not any('never_submitted' in call for call in studio.calls)
    finally:
        client.close()
