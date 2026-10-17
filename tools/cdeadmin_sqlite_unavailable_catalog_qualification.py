"""Native catalog retention when an object exists but its module is not loaded."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock
from dataclasses import dataclass

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]
import config  # noqa: E402,F401


def qualify(output,prefix,compiler='cc'):
    output=Path(output).resolve();prefix=Path(prefix).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    source=ROOT/'tools/fixtures/sqlite_catalog_module.c';program=output/'create-fixture';database=output/'native.sqlite'
    proof={'complete':False,'history_testing':'not run','checks':[],'native_sqlite_version':sqlite3.sqlite_version,
        'scope':'Native Linux unavailable-module fixture, catalog/navigator/DDN retention; extension loading remains separate',
        'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),source,
            ROOT/'web/pgadmin/cdeadmin/providers/sqlite/provider.py',ROOT/'web/pgadmin/cdeadmin/workspace/sqlite_catalog_service.py']}}
    provider=None
    try:
        assert sqlite3.sqlite_version=='3.53.0'
        with (output/'compile.log').open('w') as log:
            subprocess.run([compiler,'-I',str(prefix/'include'),'-L',str(prefix/'lib'),'-Wl,-rpath,'+str(prefix/'lib'),
                '-o',str(program),str(source),'-lsqlite3'],stdout=log,stderr=subprocess.STDOUT,check=True)
        made=subprocess.run([str(program),str(database)],capture_output=True,text=True,check=True)
        proof['fixture_engine']=made.stdout.splitlines();assert proof['fixture_engine'][0]=='3.53.0'
        proof['fixture_program_sha256']=hashlib.sha256(program.read_bytes()).hexdigest()
        connection=sqlite3.connect(database)
        try:
            assert connection.execute('SELECT sqlite_source_id()').fetchone()[0]==proof['fixture_engine'][1]
            assert connection.execute("SELECT count(*) FROM sqlite_schema WHERE name IN ('healthy','unavailable')").fetchone()==(2,)
            try:connection.execute('PRAGMA table_xinfo(unavailable)').fetchall()
            except sqlite3.OperationalError as error:assert error.sqlite_errorcode==sqlite3.SQLITE_ERROR
            else:raise AssertionError('Fixture module leaked into the new native connection')
        finally:connection.close()
        from cdeadmin_native_editor_gate import provider as make_provider
        from pgadmin.cdeadmin.providers.sqlite.provider import _resource_id
        from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService
        from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
        from pgadmin.cdeadmin.navigator import resource_children
        provider,route=make_provider('sqlite',{'database':str(database),'filesystem_root':str(output)})
        captured=provider.capture_catalog(route,include_system=False);by_id={r['resource_id']:r for r in captured['resources']}
        identity=_resource_id('virtual-table',['main'],'unavailable');healthy=by_id[_resource_id('table',['main'],'healthy')]
        assert captured['complete'] is False and healthy['native']['column_observation']['available']
        assert [row['name'] for row in healthy['native']['columns']]==['id','body']
        missing=by_id[identity];assert missing['native']['ddl']=='CREATE VIRTUAL TABLE unavailable USING cde_catalog_probe'
        assert missing['native']['column_observation']['available'] is False
        assert missing['native']['module_observation']['registered_in_session'] is False
        assert missing['native']['module_observation']['module']=='cde_catalog_probe'
        proof['checks'].append('actual-unloaded-module-retains-native-object-definition-and-healthy-columns')
        visible=resource_children(captured['resources'],{'scope':'kind','resource_kind':'virtual-table','parent_path':[],'database':'main'},{'engine_id':'sqlite'})
        assert any(row.get('resource_id')==identity for row in visible),visible
        proof['checks'].append('unavailable-native-object-retains-navigator-destination')
        @dataclass(frozen=True)
        class Context:
            endpoint_id:str='endpoint'
            profile_id:str='sqlite-native'
        service=object.__new__(ProviderWorkspaceService);service.endpoint_service=Mock()
        service.endpoint_service.workspace.return_value=(Context(),{'route':route},None)
        service.endpoint_service.provider_registry.resolve.return_value=SimpleNamespace(instance=provider)
        exported=service.sqlite_catalog('owned',{'database_target_id':'file','include_system':False})
        restored=read_catalog(json.dumps(exported['snapshot']),engine='sqlite')
        assert exported['capture_complete'] is False and exported['provenance']['coverage']=='partial'
        assert restored['rows'][identity]['native']['column_observation']['available'] is False
        assert restored['rows'][identity]['native']['module_observation']['module']=='cde_catalog_probe'
        assert any('unavailable' in message for message in exported['provenance']['warnings'])
        proof['checks'].append('production-catalog-service-and-public-ddn-preserve-unavailable-facts-without-empty-catalog')
        proof.update(complete=True,resource_count=len(by_id),extension_loader_bound_in_python=hasattr(sqlite3.Connection,'load_extension'))
    finally:
        if provider is not None:provider.client.close()
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',type=Path,required=True);parser.add_argument('--sqlite-prefix',type=Path,required=True);parser.add_argument('--compiler',default='cc');args=parser.parse_args()
    qualify(args.evidence,args.sqlite_prefix,args.compiler)
