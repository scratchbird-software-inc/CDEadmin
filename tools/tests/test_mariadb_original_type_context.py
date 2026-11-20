"""Explicit source mode/role refresh preserves native pending work."""
from types import SimpleNamespace
from unittest.mock import Mock
from contextlib import closing
import uuid
import pytest
from test_mariadb_session_flagsets import native,SETTINGS  # noqa: F401
from pgadmin.cdeadmin.providers.mysql_family.provider import MariaDBPilotProvider,_create_client,MARIADB_PROFILE
from pgadmin.cdeadmin.sdk import RelationalClientError
from ui_descriptor_roundtrip import engine_operations,operation_draft


def test_no_source_context_command_without_explicit_acknowledgement():
    handle=Mock();client=Mock();provider=SimpleNamespace(client=client,_require=Mock(),_editor_session=lambda _:handle)
    with pytest.raises(RelationalClientError,match='acknowledgement'):
        MariaDBPilotProvider.native_editor_context_action(provider,{'session_id':'owned','language_profile':'mariadb-sql','operation':'refresh_completion'})
    handle.cursor.assert_not_called()


def test_native_original_oracle_role_context_and_peer_types_do_not_finalize_pending_work(native):
    from tools.mysql_driver_gate_support import provider_access
    native.autocommit=True
    cur=native.cursor();role='sr_types_'+uuid.uuid4().hex
    cur.execute('CREATE ROLE `'+role+'`');cur.execute('GRANT `'+role+"` TO 'root'@'%'")
    route,permissions=provider_access({**SETTINGS,'ssl':False,'ssl_verify_cert':False})
    client=_create_client(MARIADB_PROFILE,permissions,SimpleNamespace(pool_namespace='owned-original-types'))
    handle=client.open_session({'route':route})
    provider=SimpleNamespace(client=client,_require=Mock(),_editor_session=lambda _:handle)
    try:
        source=handle.cursor();source.execute('CREATE TABLE IF NOT EXISTS original_type_pending(value INTEGER) ENGINE=InnoDB')
        source.execute('SET ROLE `'+role+'`');source.execute('SELECT @@sql_mode');before=source.fetchone()[0]
        source.execute('START TRANSACTION');source.execute('INSERT INTO original_type_pending VALUES(1)')
        source.execute('SAVEPOINT caller');source.execute('INSERT INTO original_type_pending VALUES(2)')
        source.execute("SET SESSION sql_mode='ORACLE'")
        fields=operation_draft(engine_operations('mariadb')['refresh_editor_context@database'],{'diagnostics_change_confirmed':True})
        result=MariaDBPilotProvider.native_editor_context_action(provider,{'session_id':'owned','language_profile':'mariadb-sql','operation':'refresh_completion',**fields})
        assert 'editor_context' in result,result
        metadata=result['editor_context'];context=metadata['context']
        assert context['original_session_context_observed'] and 'ORACLE' in context['sql_mode'].split(',')
        assert context['active_role']==role and metadata['original_active_roles_observed']
        assert metadata['original_session_commands_sent']==1 and not metadata['original_diagnostics_preserved']
        assert metadata['original_temporary_objects_observed'] and not metadata['complete']
        names={row['display_name'] for row in metadata['resources'] if row['resource_kind']=='type'}
        assert {'NUMBER','VARCHAR2','RAW','CLOB'}<=names
        assert any(row['name']=='associative-array-declaration' and row['available'] for row in context['routine_type_candidates'])
        source.execute('SET SESSION sql_mode=?',(before,))
        source.execute('SELECT value FROM original_type_pending ORDER BY value');assert source.fetchall()==[(1,),(2,)]
        cur.execute('SELECT count(*) FROM original_type_pending');assert cur.fetchone()==(0,)
        source.execute('ROLLBACK TO SAVEPOINT caller')
        source.execute('SELECT value FROM original_type_pending');assert source.fetchall()==[(1,)]
        handle.rollback();source.close()
    finally:
        client.close();cur.execute('DROP ROLE `'+role+'`');cur.close()
