"""Native server filenames retain Windows semantics from any application host."""
import pytest
from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION
from pgadmin.cdeadmin.providers.firebird.creation_paths import resolve
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


@pytest.mark.parametrize('root,requested,expected', [
    ('/owned', 'new.fdb', '/owned/new.fdb'),
    ('/owned', '/owned/a/../new.fdb', '/owned/new.fdb'),
    (r'C:\Owned', 'new.fdb', r'C:\Owned\new.fdb'),
    (r'C:\Owned', r'c:\owned\New.fdb', r'c:\owned\New.fdb'),
    ('C:/Owned', 'a/../new.fdb', r'C:\Owned\new.fdb'),
    (r'\\server\share\owned', 'new.fdb', r'\\server\share\owned\new.fdb'),
])
def test_creation_plan_preserves_server_paths(root, requested, expected):
    route = {'host': 'localhost', 'database_create_root': root}
    plan = ADMINISTRATION.plan({'resource_kind': 'database', 'operation_id': 'create',
        '_provider_route': route, 'draft': {'database_path': requested}})
    compiled = plan['provider_payload']['compiled']
    assert compiled['endpoint_database'] == expected
    assert compiled['database'] == 'localhost:' + expected


@pytest.mark.parametrize('root,requested', [
    ('/owned', '../escape.fdb'), ('/owned', '/owned-other/new.fdb'),
    (r'C:\Owned', r'..\escape.fdb'), (r'C:\Owned', r'C:\Owned-other\new.fdb'),
    (r'C:\Owned', r'D:\Owned\new.fdb'), (r'C:\Owned', r'C:new.fdb'),
    (r'C:\Owned', r'\Owned\new.fdb'), (r'C:\Owned', '/Owned/new.fdb'),
    (r'C:Owned', 'new.fdb'), ('relative', 'new.fdb'),
    (r'\\server\share\owned', r'\\other\share\owned\new.fdb'),
])
def test_ambiguous_or_escaping_creation_path_is_refused(root, requested):
    with pytest.raises(RelationalClientError):
        resolve(root, requested)
