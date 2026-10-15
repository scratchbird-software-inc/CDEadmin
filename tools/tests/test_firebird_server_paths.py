import pytest
from tools.firebird_server_paths import server_path


@pytest.mark.parametrize('filename,root,name', [
    ('/var/lib/firebird/data/owned.fdb', '/var/lib/firebird/data', 'owned.fdb'),
    ('C:\\Firebird Data\\owned.fdb', 'C:\\Firebird Data', 'owned.fdb'),
    ('C:/Firebird Data/owned.fdb', 'C:/Firebird Data', 'owned.fdb'),
    ('\\\\server\\share\\owned.fdb', '\\\\server\\share\\', 'owned.fdb'),
])
def test_server_path_flavor_is_independent_of_host(filename, root, name):
    path = server_path(filename)
    assert path.name == name
    assert path.parent == server_path(root)


@pytest.mark.parametrize('filename', ['relative.fdb', 'C:relative.fdb', '\\rooted.fdb'])
def test_ambiguous_server_filename_is_rejected(filename):
    with pytest.raises(ValueError, match='absolute'):
        server_path(filename)
