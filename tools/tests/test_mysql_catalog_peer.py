"""Retained resource inspection cannot overwrite native editor diagnostics."""
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
from threading import Event
import pytest
from pgadmin.cdeadmin.providers.mysql_family.provider import _create_client, MYSQL_PROFILE
from pgadmin.cdeadmin.providers.mysql_family import mysql_completion as completion
from pgadmin.cdeadmin.providers.mysql_family.mysql_session_variables import SourceIdentityUnavailable
from pgadmin.cdeadmin.sdk import RelationalClientError


def setup(monkeypatch):
    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace())
    source=SimpleNamespace(cursor=Mock(side_effect=AssertionError('Original SQL')));peer=object()
    rows=[{'resource_kind':'server','native':{}},{'resource_kind':'table','native':{'columns':['id']}}]
    reader=Mock(return_value=rows);client.config=replace(client.config,metadata_reader=reader)
    client._connections.append(source);monkeypatch.setattr(client,'_require_usable_session',lambda *_:None)
    @contextmanager
    def observed():yield peer,{'default_schema':'source_database'}
    observer=SimpleNamespace(parser_session=observed)
    monkeypatch.setattr(completion,'editor_observer',lambda *_:observer)
    monkeypatch.setattr(completion,'prepare',lambda *_:None)
    return client,source,peer,reader,rows,observer


def test_retained_catalog_uses_private_peer_keeps_requested_target_and_copies_reader_facts(monkeypatch):
    client,source,peer,reader,rows,_=setup(monkeypatch)
    try:
        request={'route':{'database':'selected_database'},'_provider_session_handle':source}
        result=client.list_resources(request)
        assert reader.call_args.args==(peer,{'route':{'database':'selected_database'}})
        assert result[0]['native']['metadata_observation']['original_session_commands_sent']==0
        assert not result[0]['native']['original_session_catalog_binding_validated']
        assert result[0]['native']['metadata_observation']['source_default_schema']=='source_database'
        result[1]['native']['columns'].append('caller_mutation')
        assert rows[1]['native']['columns']==['id'] and rows[0]['native']=={}
        source.cursor.assert_not_called()
    finally:client._connections.clear();client.close()


@pytest.mark.parametrize('condition',['unregistered','busy','identity','denied','malformed'])
def test_no_original_metadata_fallback_on_unadmitted_or_failed_observation(monkeypatch,condition):
    client,source,peer,reader,rows,observer=setup(monkeypatch)
    try:
        if condition=='unregistered':client._connections.clear()
        elif condition=='busy':client._executions.tokens.append(SimpleNamespace(connection=source,finished=Event()))
        elif condition in {'identity','denied'}:
            def failed(*_):raise (SourceIdentityUnavailable if condition=='identity' else RelationalClientError)('Unavailable')
            monkeypatch.setattr(completion,'prepare',failed)
        else:reader.return_value=None
        with pytest.raises(RelationalClientError):client.list_resources({'route':{},'_provider_session_handle':source})
        if condition!='malformed':reader.assert_not_called()
        assert (id(source) in client._uncertain_sessions)==(condition=='identity')
        source.cursor.assert_not_called()
    finally:client._executions.tokens.clear();client._connections.clear();client.close()
