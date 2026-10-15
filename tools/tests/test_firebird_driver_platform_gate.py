"""Reject existing targets and unsafe fixture roots before native work."""
from unittest.mock import patch

import pytest
from tools.cdeadmin_firebird_driver_platform_gate import run


@pytest.mark.parametrize('route,directory,style', [
    ({'host': 'localhost', 'database': '/existing.fdb'}, '/tests', 'posix'),
    ({'host': 'localhost', 'password': 'not-a-real-secret'},
     '/tests', 'posix'),
    ({'host': 'localhost', 'credential_reference_id': 'saved'},
     '/tests', 'posix'),
    ({}, '/tests', 'posix'),
    ({'host': 'localhost'}, '/', 'posix'),
    ({'host': 'localhost'}, 'relative', 'posix'),
    ({'host': 'localhost'}, 'C:\\', 'windows'),
    ({'host': 'localhost'}, 'C:relative', 'windows'),
    ({'host': 'localhost'}, '/tests', 'unknown'),
])
def test_rejected_fixture_no_client(tmp_path, route, directory, style):
    with patch('tools.cdeadmin_firebird_driver_platform_gate._create_client') \
            as factory:
        with pytest.raises(ValueError):
            run(route, directory, tmp_path / 'evidence', path_style=style)
        factory.assert_not_called()
    assert not (tmp_path / 'evidence').exists()


def test_embedded_rejects_password_before_native_creation(tmp_path):
    with patch('tools.cdeadmin_firebird_driver_platform_gate._create_client') \
            as factory:
        with pytest.raises(ValueError, match='password'):
            run({'attachment_mode': 'embedded'}, str(tmp_path),
                tmp_path / 'evidence', password='not-a-real-secret',
                path_style='windows' if __import__('os').name == 'nt' else 'posix')
        factory.assert_not_called()
