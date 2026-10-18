"""Receiver admission, native-family publication and bounded live receipts."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket
import threading
import time
from types import SimpleNamespace
import uuid

import psutil
import pytest

from pgadmin.cdeadmin.providers.mysql_family import continuous_binlog as receiver
from pgadmin.cdeadmin.providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
from pgadmin.cdeadmin.security import SecretLease
from pgadmin.cdeadmin.workspace.mysql_binlog_jobs import MySQLBinlogJobs


@pytest.mark.parametrize('family', ['mysql', 'mariadb'])
@pytest.mark.parametrize('options', [
    {'start_file': '../outside', 'receiver_server_id': 2},
    {'start_file': 'native.000001', 'receiver_server_id': 0},
    {'start_file': 'native.000001', 'receiver_server_id': True},
    {'start_file': 'native.000001', 'receiver_server_id': 4294967296},
    {'start_file': 'native.000001', 'receiver_server_id': '2'},
    {'start_file': 'native.000001', 'receiver_server_id': 2, 'timeout_seconds': 0},
    {'start_file': 'native.000001', 'receiver_server_id': 2, 'unsafe_sql': 'SELECT 1'},
])
def test_invalid_receiver_options_never_become_native_arguments(family, options):
    with pytest.raises(BinlogArchiveError): receiver.options(family, options)


def test_source_identity_source_id_and_purged_start_are_refused():
    captured={'status': 'available', 'identity': {'server_id': 42, 'server_uuid': 'owned'}, 'logs': [{'Log_name': 'native.000001'}]}
    with pytest.raises(BinlogArchiveError, match='different'): receiver.admit(captured, {'start_file': 'native.000001', 'receiver_server_id': 42})
    with pytest.raises(BinlogArchiveError, match='purged'): receiver.admit(captured, {'start_file': 'purged.000001', 'receiver_server_id': 43})
    with pytest.raises(BinlogArchiveError, match='identity'): receiver.admit({**captured, 'identity': {'server_id': 42, 'server_uid': 'unknown'}}, {'start_file': 'native.000001', 'receiver_server_id': 43})


def test_completed_copy_preserves_bytes_and_refuses_size_changes_or_links(tmp_path):
    cancel=threading.Event(); source=tmp_path/'source'; source.write_bytes(b'\x00\x80\xffnative')
    target=tmp_path/'copied'; receiver.copy_completed(source, target, source.stat().st_size, cancel)
    assert target.read_bytes()==source.read_bytes()
    with pytest.raises(BinlogArchiveError, match='changed'): receiver.copy_completed(source, tmp_path/'wrong-size', source.stat().st_size+1, cancel)
    linked=tmp_path/'linked'; linked.symlink_to(source)
    with pytest.raises(BinlogArchiveError, match='regular'): receiver.copy_completed(linked, tmp_path/'escaped', source.stat().st_size, cancel)


@pytest.mark.parametrize('family', ['mysql', 'mariadb'])
def test_only_closed_files_with_a_later_native_file_are_sealed_through_the_family_verifier(tmp_path, monkeypatch, family):
    real=receiver.adapter(family); first="native 'ü'.000001"; second="native 'ü'.000002"
    data=b'\xfebin\x00\x80\xffcomplete'; endpoint=str(uuid.uuid4()); source_key='server_uuid' if family=='mysql' else 'server_uid'
    identity={'server_id': 42, source_key: 'owned-source', 'version': '9.7.0' if family=='mysql' else '12.2.2-MariaDB'}
    program={'executable_sha256': 'a'*64, 'tool_version': '9.7.0' if family=='mysql' else '12.2.2-MariaDB',
             'execution_host': {'kind': 'application-host', 'platform': 'posix'}}
    captured={'identity': identity, 'status': 'available', 'state': {'native-state': family},
              'logs': [{'Log_name': first, 'File_size': str(len(data)), 'closed': False, **({'Encrypted': 'No'} if family=='mysql' else {})}]}
    metadata_seen=[]; calls=[]
    def verify(directory, expected, **_kwargs):
        metadata=json.loads((directory/'archive.json').read_text()); metadata_seen.append(metadata)
        assert metadata['source']==expected==identity
        assert metadata['format']==('mysql-raw-binlog@9.7.0' if family=='mysql' else 'mariadb-binlog@12.2.2')
        assert metadata['logs'][0]['server_file_bytes']==str(len(data))
        assert (directory/first).read_bytes()==data
        files=[{'path': p.name, 'size': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(directory.iterdir())]
        return {'format': metadata['format'], 'files': files, 'total_bytes': sum(row['size'] for row in files), 'event_integrity': []}
    fake=SimpleNamespace(options=real.options, selected_logs=real.selected_logs, capture=lambda _connection: deepcopy(captured), program_identity=lambda *_a, **_k: deepcopy(program),
        decoded_length=real.decoded_length if family=='mysql' else None, framing=lambda p, **_k: (p.stat().st_size, 2, 4),
        verify_frames=lambda *_a, **_k: {'native-checks': family}, verify=verify,
        connection_arguments=lambda *_a: ['--host=127.0.0.1', '--port=3306'])
    monkeypatch.setattr(receiver, 'adapter', lambda selected: fake if selected==family else None)
    class Runner:
        def run(self, grant, arguments, **kwargs):
            calls.append((grant.executable_id, arguments))
            if '--raw' in arguments:
                receiving=Path(grant.workspace)/'receiving'; (receiving/first).write_bytes(data)
                event={'pid': 999999999, 'process_create_time': 0, 'elapsed_seconds': 0}
                kwargs['progress'](event)
                assert not metadata_seen  # An active file is not a complete archive.
                captured['logs'][0]['closed']=True
                captured['logs'].append({'Log_name': second, 'File_size': '4', 'closed': False, **({'Encrypted': 'No'} if family=='mysql' else {})})
                time.sleep(1.02)
                kwargs['progress'](event)
                assert not metadata_seen  # Catalog rotation alone does not close the local handle.
                (receiving/second).write_bytes(b'\xfebin')
                time.sleep(1.02); kwargs['progress'](event)
                assert metadata_seen and not (receiving/first).exists() and (receiving/second).exists()
                kwargs['cancel_signal'].signal.set()
                return {'return_code': -15, 'executable_sha256': 'a'*64, 'process_observation': {'cleanup_confirmed': True, 'cancel_requested': True}}
            assert '--verify-binlog-checksum' in arguments and '--short-form' in arguments
            return {'return_code': 0, 'executable_sha256': 'a'*64, 'process_observation': {'cleanup_confirmed': True}}
    client=SimpleNamespace(_tool_runner=Runner(), _connection_arguments=lambda *_a: ['--host=127.0.0.1', '--port=3306'], _discard_failed_session=lambda _c: None)
    archives=MySQLBinlogJobs(tmp_path/'archives.json', tmp_path/'archives')
    directory=tmp_path/'receiver'; directory.mkdir()
    record={'job_id': str(uuid.uuid4()), 'owner': 1, 'endpoint_id': endpoint, 'configuration': 'owned',
            'source': identity, 'program': {**program, 'execution_host': {**program['execution_host'], 'hostname': socket.gethostname()}},
            'worker_identity': [psutil.Process().pid, psutil.Process().create_time()],
            'options': {'start_file': first, 'receiver_server_id': 99, 'timeout_seconds': None}}
    class Cancellation:
        signal=threading.Event()
        def is_set(self): return self.signal.is_set()
    cancellation=Cancellation(); events=[]
    transport=receiver.ReceiverTransport(family, client, {'host': '127.0.0.1', 'port': 3306}, SecretLease(b'[client]\npassword="private"\n'), object(), archives)
    try: result=transport.execute(record, directory, cancellation, events.append)
    finally: transport.close(); archives.close()
    assert result['published_batches']==1 and len(result['last_archive_job_ids'])==1 and result['next_file']==second
    child=archives.load(result['last_archive_job_ids'][0], 1, endpoint)
    assert child['state']=='completed' and child['continuation']['continuous_receiver_job_id']==record['job_id']
    assert child['parent_receiver_job_id']==record['job_id'] and metadata_seen[-1]['native_parser_verification']['tool_version']==program['tool_version']
    raw_calls=[args for _name, args in calls if '--raw' in args]
    assert len(raw_calls)==1
    expected='--connection-server-id=99' if family=='mysql' else '--stop-never-slave-server-id=99'
    assert expected in raw_calls[0] and '--stop-never' in raw_calls[0]
    assert len(events[-1]['last_archive_job_ids'])<=10


def test_failed_receipt_callback_stops_the_native_receiver_before_it_can_become_unobserved(tmp_path, monkeypatch):
    identity={'server_id': 42, 'server_uuid': 'owned'}
    program={'executable_sha256': 'a'*64, 'tool_version': '9.7.0', 'execution_host': {'kind': 'application-host', 'platform': 'posix'}}
    fake=SimpleNamespace(capture=lambda _observer: {'status': 'available', 'identity': identity, 'logs': [{'Log_name': 'native.000001'}]},
        program_identity=lambda *_a, **_k: deepcopy(program), connection_arguments=lambda *_a: [])
    monkeypatch.setattr(receiver, 'adapter', lambda _family: fake)
    class Cancellation:
        signal=threading.Event()
        def is_set(self): return self.signal.is_set()
    cancel=Cancellation()
    class Runner:
        def run(self,_grant,_arguments,**kwargs):
            kwargs['progress']({'pid': 999999999})
            assert cancel.is_set()
            return {'return_code': -15, 'process_observation': {'cleanup_confirmed': True, 'cancel_requested': True}}
    client=SimpleNamespace(_tool_runner=Runner(), _discard_failed_session=lambda _c: None)
    transport=receiver.ReceiverTransport('mysql',client,{},SecretLease(b'[client]\npassword="private"\n'),object(),None)
    record={'source': identity, 'program': {**program, 'execution_host': {**program['execution_host'], 'hostname': socket.gethostname()}},
            'options': {'start_file': 'native.000001', 'receiver_server_id': 99, 'timeout_seconds': None}}
    def broken_receipt(_event): raise OSError('private storage diagnostic')
    try:
        with pytest.raises(BinlogArchiveError, match='publication failed') as failure:
            transport.execute(record,tmp_path,cancel,broken_receipt)
        assert failure.value.publication_failed and failure.value.observation['process_observation']['cleanup_confirmed']
        assert 'private storage diagnostic' not in str(failure.value)
    finally:transport.close()
