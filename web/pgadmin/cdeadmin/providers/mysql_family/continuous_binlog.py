"""Native long-lived raw receivers with independently sealed closed-log batches."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import threading
import time

from .mysql_binlog_archives import BinlogArchiveError, seal
from ...operations.fileio import private_directory, private_file
from ...sdk.tooling import ProviderToolGrant


def adapter(family):
    if family == 'mysql':
        from . import mysql_raw_binlog_archives as native
    elif family == 'mariadb':
        from . import mariadb_binlog_archives as native
    else: raise BinlogArchiveError('Select a native binary-log receiver family')
    return native


def options(family, value):
    native = adapter(family)
    if not isinstance(value, dict) or set(value) - {'start_file', 'receiver_server_id', 'timeout_seconds'}:
        raise BinlogArchiveError('Select exact native receiver options')
    selected = native.options({'log_names': [value.get('start_file')], 'timeout_seconds': value.get('timeout_seconds')})
    identity = value.get('receiver_server_id')
    if type(identity) is not int or not 1 <= identity <= 4294967295:
        raise BinlogArchiveError('Select an explicit nonzero uint32 replication receiver server ID')
    return {'start_file': selected['log_names'][0], 'receiver_server_id': identity,
            'timeout_seconds': selected['timeout_seconds']}


def admit(captured, selected):
    if captured['status'] != 'available': raise BinlogArchiveError('Native binary logging is unavailable')
    identity = captured['identity'].get('server_uuid', captured['identity'].get('server_uid'))
    if not identity or identity == 'unknown': raise BinlogArchiveError('Native binary-log source identity is unavailable')
    if int(captured['identity']['server_id']) == selected['receiver_server_id']:
        raise BinlogArchiveError('Select a receiver server ID different from this source server ID')
    if selected['start_file'] not in [row['Log_name'] for row in captured['logs']]:
        raise BinlogArchiveError('The selected native starting binary log is unavailable or purged')


def copy_completed(source, destination, expected_bytes, cancel):
    """The receiver keeps its source; readers consume only this fsynced copy."""
    initial = source.lstat()
    if not stat.S_ISREG(initial.st_mode) or getattr(initial, 'st_file_attributes', 0) & 0x400 or source.resolve() != source:
        raise BinlogArchiveError('Native receiver files must be owned regular files')
    descriptor = os.open(source, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
    with os.fdopen(descriptor, 'rb') as incoming, destination.open('xb') as output:
        private_file(destination)
        before = os.fstat(incoming.fileno()); copied = 0
        if (initial.st_dev, initial.st_ino, initial.st_size, initial.st_mtime_ns, initial.st_ctime_ns) != (
                before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns):
            raise BinlogArchiveError('Native receiver files cannot be links')
        while data := incoming.read(1048576):
            if cancel.is_set(): raise InterruptedError('Native receiver publication cancelled')
            output.write(data); copied += len(data)
        after = os.fstat(incoming.fileno())
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) or copied != expected_bytes:
            raise BinlogArchiveError('The native closed log changed during receiver publication')
        output.flush(); os.fsync(output.fileno())


class ReceiverTransport:
    def __init__(self, family, client, route, credentials, observer, archive_jobs):
        self.family, self.native = family, adapter(family)
        self.client, self.route, self.credentials, self.observer = client, route, credentials, observer
        self.archive_jobs = archive_jobs

    def close(self):
        if self.credentials is not None: self.credentials.close(); self.credentials = None
        if self.observer is not None:
            owned = self.observer; self.observer = None; self.client._discard_failed_session(owned)

    def publish(self, parent, directory, captured, selected, grant, cancel, progress):
        """Publish through the existing engine-specific sealed archive contract."""
        native = self.native
        chosen = [deepcopy(row) for row in selected]
        native.options({'log_names': [row['Log_name'] for row in chosen]})
        state = {**deepcopy(captured['state']), 'selected_logs': chosen}
        review = self.archive_jobs.review(parent['owner'], parent['endpoint_id'],
            {'log_names': [row['Log_name'] for row in chosen], 'timeout_seconds': parent['options']['timeout_seconds']},
            {'identity': parent['source'], 'state': state}, parent['configuration'], parent['program'],
            continuation={'continuous_receiver_job_id': parent['job_id']})
        child = self.archive_jobs.load(review['job_id'], parent['owner'], parent['endpoint_id'])
        workspace = self.archive_jobs.directory(child); incoming = workspace/'archive.incoming'
        incoming.mkdir(mode=0o700); private_directory(incoming)
        self.archive_jobs.update(child, state='active', worker_identity=parent['worker_identity'],
                                 parent_receiver_job_id=parent['job_id'])
        with self.archive_jobs._maps_lock:
            self.archive_jobs.workers[child['job_id']] = (threading.current_thread(), cancel.signal)
        native_rows = []
        try:
            for row in chosen:
                name = row['Log_name']; expected = native.decoded_length(row) if self.family == 'mysql' else int(row['File_size'])
                copy_completed(directory/'receiving'/name, incoming/name, expected, cancel)
                size, count, last = native.framing(incoming/name, cancel=cancel)
                integrity = native.verify_frames(incoming/name, 'none', size, count, cancel=cancel)
                native_rows.append({'name': name, 'decoded_bytes': str(size), 'event_count': str(count),
                    'last_event_type': last, 'native_integrity': integrity,
                    'server_file_bytes': row['File_size'],
                    **({'server_file_encrypted': row['Encrypted']} if self.family == 'mysql' else {})})
            temporary = workspace/'verification-load'; temporary.mkdir(mode=0o700); private_directory(temporary)
            tool = 'mysql-binlog' if self.family == 'mysql' else 'mariadb-binlog'
            parser_grant = ProviderToolGrant(tool, str(workspace), grant.endpoint_host, grant.endpoint_port,
                timeout_seconds=parent['options']['timeout_seconds'], allow_unbounded_runtime=parent['options']['timeout_seconds'] is None)
            arguments = ['--no-defaults', *(['--no-login-paths'] if self.family == 'mysql' else []),
                '--verify-binlog-checksum', '--short-form', '--local-load='+str(temporary), '--',
                *[str(Path('archive.incoming')/row['name']) for row in native_rows]]
            checked = self.client._tool_runner.run(parser_grant, arguments, cancel_signal=cancel, progress=progress)
            if cancel.is_set(): raise InterruptedError('Native receiver snapshot verification cancelled')
            if checked['return_code'] != 0 or checked['executable_sha256'] != parent['program']['executable_sha256']:
                raise BinlogArchiveError('The reviewed native parser refused the receiver snapshot')
            shutil.rmtree(temporary)
            after = native.capture(self.observer)
            verify_selection = native.selected_logs(after, {'log_names': [row['Log_name'] for row in chosen]})
            if after['identity'] != parent['source'] or verify_selection != chosen:
                raise BinlogArchiveError('Native source or closed-log postimage changed during receiver publication')
            metadata = {'format': 'mysql-raw-binlog@9.7.0' if self.family == 'mysql' else 'mariadb-binlog@12.2.2',
                'source': parent['source'], 'logs': native_rows,
                'source_observation_scope': 'native_sql_identity_and_closed_catalog_before_after_receiver_copy_with_registered_transport_policy',
                'native_parser_verification': {'tool_version': parent['program']['tool_version'],
                    'executable_sha256': parent['program']['executable_sha256'],
                    'scope': 'original_native_parser_postimages_bound_to_sealed_archive_bytes'}}
            with (incoming/'archive.json').open('x', encoding='utf8') as output:
                private_file(incoming/'archive.json'); json.dump(metadata, output, sort_keys=True, ensure_ascii=True)
                output.flush(); os.fsync(output.fileno())
            artifact = native.verify(incoming, parent['source'], cancel=cancel)
            seal(incoming, workspace/'archive', cancel=cancel)
            if native.verify(workspace/'archive', parent['source'], cancel=cancel) != artifact:
                raise BinlogArchiveError('Native receiver snapshot changed during durable publication')
            self.archive_jobs.update(child, state='completed', result={'artifact': artifact,
                'program': parent['program'], 'native_operation_returned': True, 'remote_database_mutation': False,
                'producer_receiver_job_id': parent['job_id']}, native_process_termination_confirmed=True,
                finished_at=time.time(), parent_receiver_still_independent=True)
            return child['job_id']
        except BaseException as error:
            observed = getattr(error, 'observation', None) or getattr(error, 'process_observation', None) or {}
            stopped = observed.get('process_observation', observed).get('cleanup_confirmed')
            self.archive_jobs.update(child, state='unknown' if stopped is False else 'cancelled' if isinstance(error, InterruptedError) else 'failed',
                error_type=type(error).__name__, automatic_retry=False)
            raise
        finally:
            with self.archive_jobs._maps_lock:
                known = self.archive_jobs.workers.get(child['job_id'])
                if known and known[0] is threading.current_thread(): self.archive_jobs.workers.pop(child['job_id'], None)

    def execute(self, record, directory, cancel, progress):
        native = self.native
        before = native.capture(self.observer)
        if before['identity'] != record['source']: raise BinlogArchiveError('Native receiver source changed')
        admit(before, record['options'])
        program = native.program_identity(self.client, self.route, directory, cancel=cancel, progress=progress)
        program = {**program, 'execution_host': {**program['execution_host'], 'hostname': socket.gethostname()}}
        if program != record['program']:
            raise BinlogArchiveError('Native receiver program changed after review')
        receiving = directory/'receiving'; receiving.mkdir(mode=0o700); private_directory(receiving)
        tool = 'mysql-binlog' if self.family == 'mysql' else 'mariadb-binlog'
        grant = ProviderToolGrant(tool, str(directory), str(self.route.get('host') or 'localhost'),
            int(self.route.get('port', 3306)), timeout_seconds=record['options']['timeout_seconds'],
            allow_unbounded_runtime=record['options']['timeout_seconds'] is None)
        next_file = record['options']['start_file']; published = []; total = 0; failure = []; next_check = 0
        def collect_step(event):
            nonlocal next_file, total, next_check
            progress({**event, 'published_batches': total, 'last_archive_job_ids': published,
                      'next_file': next_file, 'execution_hostname': socket.gethostname()})
            if time.monotonic() < next_check or cancel.is_set(): return
            next_check = time.monotonic() + 1
            try:
                captured = native.capture(self.observer)
                if captured['identity'] != record['source']: raise BinlogArchiveError('Native receiver source identity changed')
                names = [row['Log_name'] for row in captured['logs']]
                if next_file not in names: raise BinlogArchiveError('Native receiver continuity has a purged or missing next log')
                selected = []
                for index in range(names.index(next_file), len(names)):
                    row = captured['logs'][index]
                    native.options({'log_names': [row['Log_name']]})
                    if not row['closed'] or not (receiving/row['Log_name']).is_file(): break
                    # A later FDE opens the next file only after the utility
                    # closes the previous handle, including on Windows.
                    following = names[index + 1]
                    native.options({'log_names': [following]})
                    if not (receiving/following).is_file(): break
                    expected = native.decoded_length(row) if self.family == 'mysql' else int(row['File_size'])
                    if (receiving/row['Log_name']).stat().st_size != expected: break
                    selected.append(row)
                    if len(selected) >= 512: break
                if selected:
                    child_id = self.publish(record, directory, captured, selected, grant, cancel, progress)
                    next_file = names[names.index(selected[-1]['Log_name']) + 1]
                    published.append(child_id); del published[:-10]; total += 1
                    for row in selected: (receiving/row['Log_name']).unlink()
                    progress({**event, 'published_batches': total, 'last_archive_job_ids': published,
                              'next_file': next_file, 'execution_hostname': socket.gethostname()})
            except InterruptedError:
                if cancel.is_set(): return
                raise
            except Exception as error:
                failure.append(error)
                # The generic tool observer disables a failing callback. Stop
                # this receiver before propagating its publication failure.
                cancel.signal.set()
        def collect(event):
            try: collect_step(event)
            except Exception as error:
                # Receipt/progress persistence can fail before a catalog pass.
                # The native process must not outlive a disabled callback.
                failure.append(error); cancel.signal.set()
        connection_arguments = (native.connection_arguments(self.client, self.route) if self.family == 'mysql' else
            [item for item in self.client._connection_arguments({**self.route, 'host': self.route.get('host') or 'localhost'},
                {'compress_connection': bool(self.route.get('compress'))}) if not item.startswith(('--default-character-set=', '--max-allowed-packet='))])
        arguments = [*connection_arguments, '--read-from-remote-server', '--raw',
            '--stop-never', '--verify-binlog-checksum',
            ('--connection-server-id=' if self.family == 'mysql' else '--stop-never-slave-server-id=')+str(record['options']['receiver_server_id']),
            '--result-file='+str(receiving)+os.sep, '--', record['options']['start_file']]
        result = self.credentials.use(lambda view: self.client._tool_runner.run(grant, arguments,
            secret_config=bytes(view), secret_argument='--defaults-file={path}', secret_argument_position=0,
            cancel_signal=cancel, progress=collect))
        receipt = {key: value for key, value in result.items() if key not in {'stdout', 'stderr'}}
        if failure:
            error = BinlogArchiveError('Native receiver publication failed ('+type(failure[0]).__name__+'); retained archives remain independent and this receiver is not repeated')
            error.observation = receipt; error.publication_failed = True; raise error
        if result['process_observation'].get('cleanup_confirmed') is not True:
            error = BinlogArchiveError('Native receiver process termination is unconfirmed'); error.observation = receipt; raise error
        return {'receiver_observation': receipt, 'published_batches': total, 'last_archive_job_ids': published,
                'next_file': next_file, 'native_operation_returned': result['return_code'] == 0,
                'remote_database_mutation': False, 'automatic_restart': False}
