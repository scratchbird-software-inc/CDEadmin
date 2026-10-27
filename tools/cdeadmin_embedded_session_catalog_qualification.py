"""Retained catalog qualification shared by portable embedded driver gates."""
import json
from types import SimpleNamespace
import uuid


def qualify(provider, route, receipt):
    from pgadmin.cdeadmin.data_studio.studio import DataStudioService
    from pgadmin.cdeadmin.data_studio.models import StudioSession
    from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
    engine=provider.profile.engine_id
    opened=provider.open_session({'route':route})
    handle=provider._sessions[opened['session_id']].handle
    suffix=uuid.uuid4().hex[:12]
    temporary='sr_temp_'+suffix;pending='sr_pending_'+suffix;attached='sr_attached_'+suffix
    sequence='sr_sequence_'+suffix
    try:
        if engine=='duckdb':handle.execute('COMMIT')  # Only this fresh owned fixture session.
        handle.execute(("ATTACH DATABASE ':memory:' AS " if engine=='sqlite' else "ATTACH ':memory:' AS ")+'"'+attached+'"')
        handle.execute('CREATE TABLE "'+attached+'".'+('main.' if engine=='duckdb' else '')+'"attached table"("attached column" VARCHAR)')
        handle.execute('CREATE TEMP TABLE "'+temporary+'"("exact column" INTEGER, "native column" VARCHAR)')
        handle.execute('BEGIN')
        handle.execute('CREATE TABLE "'+pending+'"(id INTEGER)')
        handle.execute('INSERT INTO "'+pending+'" VALUES (99)')
        if engine=='duckdb':handle.execute('CREATE SEQUENCE "'+sequence+'" START 9007199254740993 MAXVALUE 9223372036854775807')
        if engine=='sqlite':
            handle.execute('CREATE TEMP TRIGGER "'+temporary+'_trigger" AFTER INSERT ON "'+attached+'"."attached table" '
                'BEGIN INSERT INTO "'+pending+'" VALUES(87); END')
        binding=SimpleNamespace(instance=provider,manifest={'identity':provider._identity()})
        studio=DataStudioService(SimpleNamespace(resolve=lambda _context:binding))
        # Portable component gates supply a small provider-context fixture;
        # authenticated workspace qualification separately uses EndpointContext.
        context=SimpleNamespace(**vars(provider.context))
        context.isolation_key=getattr(provider.context,'isolation_key',
            (context.endpoint_id,context.cache_namespace))
        session=StudioSession(context.endpoint_id,provider.profile.language_profile,opened,None,None,None,
            provider_isolation_key=context.isolation_key)
        studio._sessions[session.session_id]=session
        before=handle.execute('SELECT current_transaction_id()').fetchone() if engine=='duckdb' else handle.in_transaction
        observed=studio.session_catalog(context,session.session_id)
        resources=observed['resources']
        if engine=='sqlite':
            trigger=next(row for row in resources if row['resource_kind']=='trigger' and row['display_name']==temporary+'_trigger')
            assert trigger['display_path']==['temp',temporary+'_trigger']
            owner_binding=trigger['native']['owner_binding_observation']
            assert owner_binding['available'] and owner_binding['database']==attached and owner_binding['table']=='attached table'
            assert not owner_binding['existing_trigger_execution_observed']
            receipt['temporary_trigger_owner']={'native_namespace':'temp','native_owner_database':attached,
                'native_declaration_prepare':True,'catalog_did_not_execute_trigger':True}
            raw=handle.execute('PRAGMA temp.table_xinfo("'+temporary+'")').fetchall()
            expected={row[1]:{'ordinal_position':row[0],'data_type':row[2],'nullable':not bool(row[3]),
                             'default':row[4],'primary_key_position':row[5],'hidden':row[6]} for row in raw}
            actual={row['display_name']:row['native']['catalog_metadata'] for row in resources
                    if row['resource_kind']=='column' and row['display_path'][:2]==['temp',temporary]}
            assert actual==expected
            assert handle.in_transaction==before
            import sqlite3
            with sqlite3.connect(route['database']) as other:
                assert not other.execute('SELECT 1 FROM sqlite_schema WHERE name=?',(pending,)).fetchall()
        else:
            raw=handle.execute('SELECT column_name,column_index,data_type FROM duckdb_columns() WHERE database_name=\'temp\' AND table_name=?',[temporary]).fetchall()
            expected={row[0]:(row[1],row[2]) for row in raw}
            actual={row['display_name']:(row['native']['catalog_metadata']['ordinal_position'],row['native']['catalog_metadata']['data_type'])
                    for row in resources if row['resource_kind']=='column' and row['display_path'][:3]==['temp','main',temporary]}
            assert actual==expected
            assert any(row['resource_kind']=='schema' and row['display_path']==['temp','main'] for row in resources)
            assert handle.execute('SELECT current_transaction_id()').fetchone()==before
            native_sequence=next(row for row in resources if row['resource_kind']=='sequence' and row['display_name']==sequence)
            assert native_sequence['native']['catalog_metadata']['start_value']=='9007199254740993'
            import duckdb
            with duckdb.connect(route['database']) as other:
                assert not other.execute('SELECT 1 FROM duckdb_tables() WHERE table_name=?',[pending]).fetchall()
        assert any(row['display_name']=='attached column' and row['native']['session_scope_kind']=='attached-database' for row in resources)
        assert handle.execute('SELECT * FROM "'+pending+'"').fetchall()==[(99,)]
        model=read_catalog(json.dumps(observed['document']['snapshot']),engine=engine)
        assert model['provenance']['observation_scope']=='retained-session'
        if engine=='duckdb':
            from pgadmin.cdeadmin.workspace.duckdb_schema_plan import _root as migration_root
        else:
            from pgadmin.cdeadmin.workspace.sqlite_schema_plan import _scope as migration_root
        try:migration_root(model)
        except ValueError as error:assert 'Retained-session' in str(error)
        else:raise AssertionError('Session observations entered an independent migration')
        handle.execute('ROLLBACK')
        receipt['checks'].extend(['retained-session-temp-attached-and-pending-native-catalog',
            'retained-session-independent-native-column-fact-reconciliation',
            'retained-session-ddn-provenance-and-independent-migration-refusal'])
        receipt['session_catalog']={'engine':engine,'objects':len(resources),'independent_native_columns':len(expected),
            'pending_catalog_preserved':True,'documentary_ddn_roundtrip':True,'independent_migration_refused':True}
    finally:provider.close_session(opened)
