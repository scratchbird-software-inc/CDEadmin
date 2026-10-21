"""The native utility must receive exact secrets, without line framing."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_shell_tools as native
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.sdk.tooling import ProviderToolGrant


@pytest.mark.parametrize('kinds', [[], ['database_password_2'], ['database_password', 'database_password_3']])
def test_exact_factor_positions_and_every_password_character_use_private_json(tmp_path, kinds):
    passwords = ['LF\nCR\rquote"slash\\雪-' + str(index) for index in range(len(kinds))]
    route = {'host': 'registered', 'port': 3306, 'credential_references': {key: 'ref' for key in kinds}}
    paths = []
    def run(grant, args, **kwargs):
        assert kwargs.get('input_bytes', b'') == b'' and '--passwords-from-stdin' not in args
        assert grant.secret_environment_names == (native.CREDENTIAL_FILE,)
        assert kwargs['secret_environment_name'] == native.CREDENTIAL_FILE and kwargs['secret_argument'] is None
        expected = {'password': ''}
        expected.update(dict(zip([{'database_password': 'password', 'database_password_2': 'password2', 'database_password_3': 'password3'}[key] for key in kinds], passwords)))
        assert json.loads(kwargs['secret_config']) == expected
        assert kwargs['redact_values'] == tuple(passwords)
        path = Path(next(item.split('=', 1)[1] for item in args if item.startswith('--file=')))
        source = path.read_text(); paths.append(path)
        assert all(password not in source and password not in ' '.join(args) for password in passwords)
        assert 'shell.connect(target)' in source and 'util.loadDump' in source
        return {'return_code': 0}
    client = SimpleNamespace(_tool_grant=lambda _route: ProviderToolGrant('mysql-shell', str(tmp_path), 'registered', 3306),
        _shell_connection_arguments=lambda _route: ['--host=registered', '--port=3306', '--ssl-mode=REQUIRED'],
        _tool_runner=SimpleNamespace(run=run))
    assert native.run(client, route, 'util.loadDump("owned dump",{})', passwords)['return_code'] == 0
    assert len(paths) == 1 and not paths[0].exists()


def test_lost_native_dispatch_reply_does_not_reissue_tool_and_releases_script(tmp_path):
    runner = Mock(side_effect=OSError('Owned missing local tool acknowledgement'))
    client = SimpleNamespace(_tool_grant=lambda _route: ProviderToolGrant('mysql-shell', str(tmp_path), 'registered', 3306),
        _shell_connection_arguments=lambda _route: [], _tool_runner=SimpleNamespace(run=runner))
    with pytest.raises(OSError): native.run(client, {}, 'util.loadDump("owned",{})', [])
    assert runner.call_count == 1 and list(tmp_path.iterdir()) == []


def test_missing_factor_binding_refuses_before_any_script_or_tool(tmp_path):
    client = Mock()
    with pytest.raises(RelationalClientError): native.run(client, {'credential_references': {'database_password_2': 'ref'}}, 'util.dumpSchemas([],"owned")', [])
    client._tool_grant.assert_not_called(); client._tool_runner.run.assert_not_called()
