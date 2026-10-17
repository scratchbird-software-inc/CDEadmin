#!/usr/bin/env python3
"""Portable native DuckDB qualification through the production provider."""
import argparse
import hashlib
import json
import platform
from pathlib import Path
import shutil
import sys
import time
import traceback
import uuid
from types import ModuleType, SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'web'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.providers.duckdb.provider import (  # noqa: E402
    PROFILE, create_provider,
)


def run(evidence):
    evidence = Path(evidence).resolve()
    if evidence == ROOT or ROOT in evidence.parents:
        raise ValueError('Evidence must be outside the repository')
    evidence.mkdir(parents=True, exist_ok=False)
    fixture = evidence / 'owned-fixture'
    fixture.mkdir()
    receipt = dict(complete=False, checks=[], failures=[],
                   platform=platform.platform(),
                   python=platform.python_version(),
                   cleanup_complete=False,
                   scope='DuckDB native driver; UX acceptance separate')
    files = list((ROOT / 'web/pgadmin/cdeadmin/providers/duckdb').glob('*.py'))
    files += [Path(__file__),
              ROOT / 'web/pgadmin/cdeadmin/providers/embedded_route.py']
    files += [ROOT / path for path in (
        'tools/cdeadmin_embedded_session_catalog_qualification.py',
        'web/pgadmin/cdeadmin/providers/embedded_session_catalog.py',
        'web/pgadmin/cdeadmin/providers/native_editor.py',
        'web/pgadmin/cdeadmin/data_studio/studio.py',
        'web/pgadmin/cdeadmin/data_studio/catalog_values.py',
        'web/pgadmin/cdeadmin/workspace/firebird_catalog_export.py',
        'web/pgadmin/cdeadmin/workspace/firebird_catalog_import.py',
        'web/pgadmin/cdeadmin/workspace/duckdb_schema_plan.py',
        'web/pgadmin/cdeadmin/workspace/sqlite_schema_plan.py',
        'web/pgadmin/static/vendor/ddn/current/resource-manifest.json')]
    receipt['source_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(
        p.read_bytes()).hexdigest() for p in files}
    context = SimpleNamespace(
        endpoint_id=str(uuid.uuid4()), session_namespace='owned-duckdb-proof',
        pool_namespace='owned-duckdb-proof',
        cache_namespace='owned-duckdb-proof',
        provider_id=PROFILE.provider_id, profile_id=PROFILE.profile_id,
        profile_version=PROFILE.exact_version, provider_version='0.1.0')
    provider = None
    route = dict(database=str(fixture / 'active.duckdb'),
                 filesystem_root=str(fixture))
    try:
        import duckdb
        import pyarrow
        receipt.update(duckdb=duckdb.__version__, pyarrow=pyarrow.__version__)
        assert duckdb.__version__ == PROFILE.exact_version
        assert pyarrow.__version__ == '25.0.1'
        provider = create_provider(
            context, SimpleNamespace(require=lambda *_: None))
        session = provider.open_session({'route': route})
        handle = provider._sessions[session['session_id']].handle
        receipt['native_version'] = handle.execute('PRAGMA version').fetchall()
        receipt['checks'].append('exact-provider-runtime-admission')

        def observe(operation):
            pages = []
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                page = provider.describe_result(operation)
                pages.append(page)
                if page['complete']:
                    return pages
            raise AssertionError('DuckDB execution did not terminate')

        def query(source, parameters=None, target=None):
            request = dict(target or session, source=source,
                           parameters=parameters)
            pages = observe(provider.execute(request))
            payloads = [p['extensions']['duckdb']['payload'] for p in pages]
            assert not payloads[-1].get('error'), payloads[-1]
            return [row for p in payloads for row in p['rows']]

        values = query(
            'SELECT $i AS same, $u AS same, $d, $b, $s, NULL, '
            "timestamp_ns '2026-01-01 00:00:00.123456789', "
            "interval '1 month 2 days 3 microseconds', "
            "'12:00:00+05:30'::TIMETZ, union_value(x:=42), "
            "map([1,2],['a','b']), {'nested':[1,2]}", {
                'i': {'encoding': 'integer', 'data': str(2**127 - 1)},
                'u': {'encoding': 'integer', 'data': str(2**128 - 1)},
                'd': {'encoding': 'decimal', 'data': '1234567890.12345678'},
                'b': {'encoding': 'base64', 'data': 'AP8='},
                's': 'Grüße 🌲'})[0]
        assert values[:3] == [
            str(2**127 - 1), str(2**128 - 1), '1234567890.12345678']
        assert values[3]['data'] == 'AP8='
        assert values[4:6] == ['Grüße 🌲', None]
        assert values[6]['ticks'].endswith('123456789')
        assert values[7] == dict(months=1, days=2, nanoseconds='3000')
        assert values[8]['native_type'] == 'time_tz'
        assert values[9]['value'] == 42
        assert values[10]['entries'] == [[1, 'a'], [2, 'b']]
        assert values[11] == {'nested': [1, 2]}
        assert query('SELECT ?', [42]) == [[42]]
        receipt['checks'].append('exact-arrow-values-and-native-bindings')
        query('CREATE SEQUENCE owned_sequence')
        union_rows = query("SELECT union_value(x:=NULL::INT), "
                           "NULL::UNION(x INT,y VARCHAR), "
                           "union_value(x:=nextval('owned_sequence'))")
        assert union_rows[0][0] == dict(tag='x', type_code=0, value=None)
        assert union_rows[0][1] is None
        assert union_rows[0][2]['value'] == 1
        assert query("SELECT currval('owned_sequence')") == [[1]]
        query('CREATE TABLE returned(i INT, u UNION(x INT,y VARCHAR))')
        assert query("INSERT INTO returned VALUES(1, "
                     "union_value(y:=NULL::VARCHAR)) RETURNING u") == [[
                         dict(tag='y', type_code=1, value=None)]]
        assert query('SELECT count(*) FROM returned') == [[1]]
        query('DROP TABLE returned')
        receipt['checks'].append('union-null-validity-and-single-execution')
        pages = observe(provider.execute(dict(
            session, source='SELECT i FROM range(777) t(i)')))
        payloads = [p['extensions']['duckdb']['payload'] for p in pages]
        assert sum(len(p['rows']) for p in payloads) == 777
        assert max(len(p['rows']) for p in payloads) <= 256
        assert {p['result_set_index']
                for p in payloads if p.get('has_page')} == {0}
        rejected = observe(provider.execute(dict(session,
            source='CREATE TABLE forbidden(i INT); SELECT 1')))
        assert rejected[-1]['extensions']['duckdb']['payload']['error'][
            'type'] == 'StatementCountError'
        assert query("SELECT count(*) FROM duckdb_tables() "
                     "WHERE table_name='forbidden'") == [[0]]
        receipt['checks'].append('bounded-single-statement-results-and-no-prefix-dispatch')
        query('CREATE TABLE owned(id INTEGER PRIMARY KEY, value VARCHAR)')
        resources = provider.client.list_resources(dict(
            route=route, _provider_session_handle=handle))
        assert any(r['display_name'] == 'owned' for r in resources)
        provider.control_transaction(dict(session, action='commit'))
        query("INSERT INTO owned VALUES(1,'committed')")
        provider.control_transaction(dict(session, action='commit'))
        query("UPDATE owned SET value='rolled back'")
        provider.control_transaction(dict(session, action='rollback'))
        assert query('SELECT value FROM owned') == [['committed']]
        query("INSERT INTO owned VALUES(2,'discarded')")
        failed = observe(provider.execute(dict(
            session, source="INSERT INTO owned VALUES(2,'duplicate')")))
        assert failed[-1]['extensions']['duckdb']['payload']['error'][
            'type'] == 'ConstraintException'
        decision = provider.control_transaction(dict(session, action='commit'))
        assert decision['provider_payload']['last_decision'] == 'rollback'
        assert query('SELECT count(*) FROM owned') == [[1]]
        receipt['checks'].append(
            'retained-decisions-aborted-commit-and-metadata')
        operation = provider.execute(dict(
            session, source='SELECT sum(i*j) FROM '
            'range(1000000) a(i), range(1000000) b(j)'))
        time.sleep(.1)
        provider.cancel(operation)
        cancelled = observe(operation)[-1]['extensions']['duckdb']['payload']
        assert cancelled['error']['type'] == 'InterruptException'
        provider.control_transaction(dict(session, action='rollback'))
        assert query('SELECT 7') == [[7]]
        receipt['checks'].append('native-interruption-and-reuse')
        parquet = str(fixture / 'copy #% 漢字.parquet').replace("'", "''")
        query(f"COPY owned TO '{parquet}' (FORMAT PARQUET)")
        assert query(f"SELECT value FROM read_parquet('{parquet}')") == [
            ['committed']]
        export = str(fixture / 'export').replace("'", "''")
        query(f"EXPORT DATABASE '{export}' (FORMAT PARQUET)")
        imported_route = dict(route,
                              database=str(fixture / 'imported.duckdb'))
        imported = provider.open_session({'route': imported_route})
        query(f"IMPORT DATABASE '{export}'", target=imported)
        provider.control_transaction(dict(imported, action='commit'))
        assert query('SELECT value FROM owned',
                     target=imported) == [['committed']]
        provider.close_session(imported)
        receipt['checks'].append('native-copy-parquet-export-import')
        provider.close_session(session)
        read_only = provider.open_session(
            {'route': dict(route, read_only=True)})
        failed = observe(provider.execute(dict(
            read_only, source='INSERT INTO owned VALUES(3,NULL)')))
        assert failed[-1]['extensions']['duckdb']['payload']['error']
        provider.close_session(read_only)
        assert not provider.client._connections
        receipt['checks'].append('read-only-and-native-release')
        with duckdb.connect(route['database'], read_only=True) as observer:
            assert observer.execute(
                'SELECT * FROM owned').fetchall() == [(1, 'committed')]
        receipt['checks'].append('independent-final-effect')
        if __package__:
            from .cdeadmin_embedded_session_catalog_qualification import qualify as qualify_session_catalog
        else:
            from cdeadmin_embedded_session_catalog_qualification import qualify as qualify_session_catalog
        qualify_session_catalog(provider,route,receipt)
        assert not provider.client._connections
        receipt['complete'] = True
    except Exception as exc:
        receipt['failures'].append(dict(type=type(exc).__name__,
                                        detail=str(exc)))
        (evidence / 'failure.txt').write_text(traceback.format_exc())
    finally:
        try:
            if provider is not None:
                provider.client.close()
            shutil.rmtree(fixture)
            receipt['cleanup_complete'] = True
        except Exception as exc:
            receipt['complete'] = False
            receipt['failures'].append(dict(phase='cleanup',
                                            type=type(exc).__name__))
        (evidence / 'summary.json').write_text(
            json.dumps(receipt, indent=2) + '\n')
    return 0 if receipt['complete'] and receipt['cleanup_complete'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True)
    sys.exit(run(parser.parse_args().evidence))
