"""Native service installation publication and original outcome boundaries."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_host_installation as installation
from pgadmin.cdeadmin.providers.mysql_family import mysql_host_worker as worker


@pytest.mark.parametrize('race',[False,True])
def test_competing_unit_cannot_be_replaced_between_validation_and_publication(tmp_path,monkeypatch,race):
    units=tmp_path/'units';units.mkdir();directory=tmp_path/'job';directory.mkdir();target=units/'mysql.service'
    info=units.stat();plan={'path':str(target),'parent_identity':[info.st_dev,info.st_ino],
        'selected_service':{'manager':'systemd','name':'mysql.service'},'native_pid_file':'/owned/mysql.pid',
        'unit_text':'[Service]\nExecStart=/native/mysqld\n','unit_sha256':'owned-unit',
        'native_arguments':['/native/mysqld','--no-defaults'],
        'manager':{'path':'/native/systemctl'},'validator':{'path':'/native/systemd-analyze'}}
    process=Mock(return_value={'return_code':0,'outputs':{}})
    host={**worker.__dict__,'process':process,'native_services':Mock()}
    host['native_services'].inspect.side_effect=ValueError('Independent association unavailable')
    monkeypatch.setattr(installation,'inspect',lambda *args:plan)
    original=installation.os.link
    if race:
        def competitor(*args,**kwargs):
            target.write_bytes(b'concurrent native administrator unit')
            return original(*args,**kwargs)
        monkeypatch.setattr(installation.os,'link',competitor)
    observed={'service_installation':plan,'configuration':None,'program':{'path':'/native/mysqld'}}
    if race:
        with pytest.raises(FileExistsError):installation.execute({},observed,directory,30,host)
        assert target.read_bytes()==b'concurrent native administrator unit'
        assert not json.loads((directory/'service-installation.json').read_text())['installed']
        assert not any('daemon-reload' in call.args[1] for call in process.call_args_list)
    else:
        result=installation.execute({},observed,directory,30,host)
        assert result['installed'] and result['daemon_reload']['return_code']==0
        assert not result['restart_issued'] and not result['enable_issued'] and not result['sql_readiness_observed']
        assert target.read_text()==plan['unit_text'] and target.stat().st_mode&0o777==0o644
        assert result['association_error_type']=='ValueError'
    assert not list(units.glob('.scratchrobin-unit-*'))


def test_native_unit_quoting_preserves_systemd_literal_arguments_and_percent_specifiers():
    assert installation.argument('/native/mysql %雪/with "quotes"\\file\n')=='"/native/mysql %%雪/with \\"quotes\\"\\\\file\\n"'
    with pytest.raises(ValueError):installation.argument('native\0argument')


def test_lost_reload_result_preserves_installed_bytes_without_inventing_its_return_code(tmp_path,monkeypatch):
    units=tmp_path/'units';units.mkdir();directory=tmp_path/'job';directory.mkdir();target=units/'mysql.service';info=units.stat()
    plan={'path':str(target),'parent_identity':[info.st_dev,info.st_ino],'unit_text':'[Service]\nExecStart=/native/mysqld\n',
        'unit_sha256':'owned-unit','native_arguments':['/native/mysqld','--no-defaults'],
        'manager':{'path':'/native/systemctl'},'validator':{'path':'/native/systemd-analyze'}}
    def process(_program,arguments,*args,**kwargs):
        if 'daemon-reload' in arguments:raise OSError('Original native manager acknowledgement unavailable')
        return {'return_code':0,'outputs':{}}
    monkeypatch.setattr(installation,'inspect',lambda *args:plan)
    with pytest.raises(OSError):installation.execute({}, {'service_installation':plan,'configuration':None,'program':{'path':'/native/mysqld'}},directory,30,{**worker.__dict__,'process':process})
    phase=json.loads((directory/'service-installation.json').read_text())
    assert target.read_text()==plan['unit_text'] and phase['installed'] and phase['daemon_reload_dispatched']
    assert 'daemon_reload' not in phase and phase['native_result_scope']=='systemd_unit_validation'
    assert not phase['restart_issued'] and not phase['enable_issued']
