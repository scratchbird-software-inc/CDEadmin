"""Once-only, owner/file-bound native recovery with separate publication facts."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import time
import uuid

import psutil

from ..operations.fileio import exclusive_file_lock, private_directory
from ..operations.store import JsonOperationStore
from ..providers.sqlite.recovery import RecoveryError as Error, digest_file, recover


ACTIVE = {'dispatching', 'active', 'cancel_requested', 'publishing'}
REVIEW = ('job_id', 'owner', 'endpoint_id', 'database_target_id', 'configuration',
          'route', 'source', 'program', 'options', 'created_at', 'expires_at')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True, allow_nan=False).encode('ascii')).hexdigest()


def identifier(value):
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value: raise ValueError()
    except (TypeError, ValueError, AttributeError): raise Error('Invalid SQLite recovery identity') from None
    return value


class Cancellation:
    def __init__(self, jobs, record, signal):
        self.jobs, self.record, self.signal = jobs, record, signal
        self.next_check = 0

    def is_set(self):
        if not self.signal.is_set() and time.monotonic() >= self.next_check:
            self.next_check = time.monotonic() + .25
            current = self.jobs.load(self.record['job_id'], self.record['owner'],
                self.record['endpoint_id'], self.record['database_target_id'])
            if current.get('cancel_requested'): self.signal.set()
        return self.signal.is_set()

    def wait(self, seconds):
        self.signal.wait(min(seconds, .25))
        return self.is_set()


class SQLiteRecoveryJobs:
    _maps, _maps_lock = {}, threading.RLock()

    def __init__(self, path, root):
        self.path, self.root = Path(path), Path(root).resolve()
        self.lock = threading.RLock()
        with self._maps_lock: self.workers = self._maps.setdefault(str(self.path.resolve()), {})
        self.worker_identity = [os.getpid(), psutil.Process().create_time()]

    def scope(self, owner, endpoint, target):
        if type(owner) is not int or owner <= 0 or not isinstance(target, str) or not 1 <= len(target) <= 256:
            raise Error('Invalid SQLite recovery owner or file scope')
        return self.root / str(owner) / identifier(endpoint) / hashlib.sha256(target.encode('utf8')).hexdigest()

    def directory(self, record):
        return self.scope(record['owner'], record['endpoint_id'], record['database_target_id']) / identifier(record['job_id'])

    def prepare(self, owner, endpoint, target):
        scope = self.scope(owner, endpoint, target)
        for path in (self.root, self.root / str(owner), self.root / str(owner) / endpoint, scope):
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            private_directory(path)
        return scope

    @contextmanager
    def store(self, job_id):
        root = Path(str(self.path) + '.jobs')
        root.mkdir(parents=True, exist_ok=True, mode=0o700); private_directory(root)
        path = root / (identifier(job_id) + '.json')
        with self.lock:
            descriptor = os.open(str(path) + '.lock', os.O_CREAT | os.O_RDWR, 0o600)
            try:
                with exclusive_file_lock(descriptor): yield JsonOperationStore(path)
            finally: os.close(descriptor)

    @staticmethod
    def record(state, job_id, owner, endpoint, target):
        record = state.get('sqlite_recovery_jobs', {}).get(job_id)
        if (record is None or type(owner) is not int or record['owner'] != owner or
                record['endpoint_id'] != endpoint or record['database_target_id'] != target):
            raise Error('Recovery receipt is unavailable for this owner, endpoint and file')
        return record

    def load(self, job_id, owner, endpoint, target):
        self.scope(owner, endpoint, target)
        with self.store(job_id) as store:
            return self.record(store.read(), job_id, owner, endpoint, target)

    def public(self, record):
        result = deepcopy({key: value for key, value in record.items()
            if key not in {'owner', 'route', 'configuration', 'worker_identity'}})
        result['automatic_retry'] = False
        source = result.get('source', {})
        if 'output_parent_identity' in source:
            source['output_parent_identity'] = [str(value) for value in source['output_parent_identity']]
        for observations in (source.get('files', {}), (result.get('result') or {}).get('source_images', {})):
            for item in observations.values():
                for field in ('device', 'inode'):
                    if field in item: item[field] = str(item[field])
        if record['state'] in ACTIVE:
            with self.lock: worker = self.workers.get(record['job_id'])
            pid, created = record.get('worker_identity', (None, None))
            try: alive = pid is not None and psutil.Process(pid).create_time() == created
            except psutil.Error: alive = False
            if not alive or record.get('worker_identity') == self.worker_identity and not (worker and worker[0].is_alive()):
                result.update(state='unknown_outcome', publication_acknowledgement_unknown=True)
        return result

    def get(self, *scope): return self.public(self.load(*scope))

    def update(self, record, **values):
        with self.store(record['job_id']) as store:
            def change(state):
                current = self.record(state, record['job_id'], record['owner'], record['endpoint_id'], record['database_target_id'])
                current.update(deepcopy(values), updated_at=time.time())
            store.change(change)

    def list(self, owner, endpoint, target, offset=0, limit=25):
        scope = self.scope(owner, endpoint, target)
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise Error('Invalid recovery receipt page')
        entries = sorted((path for path in scope.iterdir() if path.is_dir()),
            key=lambda path: path.stat().st_mtime_ns, reverse=True) if scope.is_dir() else []
        records, unavailable = [], []
        for path in entries[offset:offset + limit]:
            try: records.append(self.get(path.name, owner, endpoint, target))
            except Error: unavailable.append(path.name)
        return {'jobs': records, 'offset': offset, 'limit': limit, 'total': len(entries),
                'more': offset + limit < len(entries), 'unavailable_job_ids': unavailable}

    def review(self, owner, endpoint, target, route, source, program, selected, configuration):
        self.prepare(owner, endpoint, target)
        record = {'job_id': str(uuid.uuid4()), 'owner': owner, 'endpoint_id': endpoint,
            'database_target_id': target, 'route': deepcopy(route), 'source': deepcopy(source),
            'program': deepcopy(program), 'options': deepcopy(selected), 'configuration': configuration,
            'state': 'reviewed', 'created_at': time.time(), 'expires_at': time.time() + 300,
            'warnings': ['The source must be isolated from writers while its main, WAL and journal images are captured. This is salvage, not an online backup.',
                'A new recovered file is published without replacing the original. Native integrity does not establish complete application-data recovery.',
                *(['Freelist recovery can recover deleted records.'] if selected['include_freelist'] else [])]}
        record['review_digest'] = digest({key: record[key] for key in REVIEW})
        directory = self.directory(record); directory.mkdir(mode=0o700); private_directory(directory)
        with self.store(record['job_id']) as store:
            store.change(lambda state: state.setdefault('sqlite_recovery_jobs', {}).__setitem__(record['job_id'], record))
        return self.public(record)

    def start(self, request, owner, endpoint, target, configuration):
        if not isinstance(request, dict) or set(request) != {'job_id', 'review_digest', 'confirmed'} or request['confirmed'] is not True:
            raise Error('Explicit confirmation of a prepared recovery review is required')
        claimed = False; signal = threading.Event(); worker = None
        with self.store(request['job_id']) as store:
            def claim(state):
                nonlocal claimed
                record = self.record(state, request['job_id'], owner, endpoint, target)
                if request['review_digest'] != record['review_digest']:
                    raise Error('Recovery review fingerprint changed')
                if record['state'] != 'reviewed': return deepcopy(record)
                if (record['expires_at'] < time.time() or record['configuration'] != configuration or
                        digest({key: record[key] for key in REVIEW}) != record['review_digest']):
                    raise Error('Recovery source, registration or review changed; prepare a new review')
                record.update(state='dispatching', worker_identity=self.worker_identity, started_at=time.time())
                claimed = True
                return deepcopy(record)
            record = store.change(claim)
        if not claimed: return self.get(record['job_id'], owner, endpoint, target)
        try:
            worker = threading.Thread(target=self.run, args=(record, signal), daemon=True,
                name='sqlite-recovery-' + record['job_id'])
            with self.lock: self.workers[record['job_id']] = (worker, signal)
            worker.start()
        except BaseException:
            if worker is None or worker.ident is None:
                self.update(record, state='not_dispatched', error_type='worker_start_failed')
            raise
        return self.get(record['job_id'], owner, endpoint, target)

    def cancel(self, job_id, owner, endpoint, target):
        accepted = False
        with self.store(job_id) as store:
            def change(state):
                nonlocal accepted
                record = self.record(state, job_id, owner, endpoint, target)
                if record['state'] in {'dispatching', 'active', 'cancel_requested'}:
                    record.update(state='cancel_requested', cancel_requested=True); accepted = True
                elif record['state'] == 'reviewed':
                    record.update(state='cancelled', cancel_requested=True); accepted = True
            store.change(change)
        with self.lock:
            if accepted and job_id in self.workers: self.workers[job_id][1].set()
        return {**self.get(job_id, owner, endpoint, target), 'cancellation_accepted': accepted}

    def run(self, record, signal):
        work = self.directory(record) / 'work'; published = False; publication_dispatched = False; result = None; last = 0
        cancellation = Cancellation(self, record, signal)
        def progress(values):
            nonlocal last
            now = time.monotonic()
            if now - last >= .25:
                self.update(record, progress=values); last = now
        try:
            work.mkdir(mode=0o700); private_directory(work)
            self.update(record, state='active')
            result = recover(record, work, cancel=cancellation, progress=progress)
            execution = result.get('process_observation', {})
            if result.get('completed') is not True:
                state = ('unknown_outcome' if execution.get('cleanup_confirmed') is False else
                    'cancelled' if execution.get('cancel_requested') else 'timed_out' if execution.get('timed_out') else 'failed')
                self.update(record, state=state, result=result, finished_at=time.time(), output_published=False)
                return
            with self.store(record['job_id']) as store:
                def publication(state):
                    current = self.record(state, record['job_id'], record['owner'], record['endpoint_id'], record['database_target_id'])
                    if current.get('cancel_requested') or signal.is_set(): return False
                    current.update(state='publishing', result=deepcopy(result), publication_started_at=time.time())
                    return True
                admitted = store.change(publication)
            if not admitted:
                self.update(record, state='cancelled', result=result, finished_at=time.time(), output_published=False)
                return
            output = Path(record['source']['output_path']); parent = output.parent.stat()
            if ([parent.st_dev, parent.st_ino] != record['source']['output_parent_identity'] or
                    output.parent.resolve(strict=True) != output.parent or
                    any(os.path.lexists(str(output) + suffix) for suffix in ('', '-wal', '-shm', '-journal'))):
                raise Error('The reviewed recovery output directory or filename changed')
            artifact = work / 'recovered.sqlite'
            if digest_file(artifact) != result['artifact_sha256']:
                raise Error('The recovered artifact changed before publication')
            publication_dispatched = True
            if os.name == 'nt':
                os.rename(artifact, output); published = True
            else:
                os.link(artifact, output)
                published = True
                descriptor = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
                try: os.fsync(descriptor)
                finally: os.close(descriptor)
            if digest_file(output) != result['artifact_sha256']:
                raise Error('The published recovered file changed before acknowledgement')
            self.update(record, state='completed', result=result, output_published=True,
                publication_acknowledged=True, finished_at=time.time())
        except Exception as error:
            observation = getattr(error, 'observation', {})
            uncertain = (published or observation.get('cleanup_confirmed') is False or
                publication_dispatched and not isinstance(error, (FileExistsError, PermissionError, FileNotFoundError)))
            if result is None and observation: result = {'completed': False, 'process_observation': observation}
            self.update(record, state='unknown_outcome' if uncertain else 'cancelled' if signal.is_set() else
                'timed_out' if isinstance(error, TimeoutError) else 'failed',
                error_type=type(error).__name__, result=result,
                error_message=str(error) if isinstance(error, (Error, TimeoutError)) else None,
                output_published=True if published else None if uncertain else False,
                publication_acknowledgement_unknown=uncertain, finished_at=time.time())

    def reconcile(self, job_id, owner, endpoint, target):
        record = self.load(job_id, owner, endpoint, target)
        public = self.public(record)
        if public['state'] in ACTIVE: return public
        output = Path(record['source']['output_path']); expected = (record.get('result') or {}).get('artifact_sha256')
        matched = bool(expected and output.is_file() and not output.is_symlink() and digest_file(output) == expected)
        values = {'current_artifact': {'checked_at': time.time(), 'matches_expected': matched}}
        if public['state'] == 'unknown_outcome' and matched:
            values.update(state='artifact_verified', publication_acknowledgement_unknown=True)
        self.update(record, **values)
        return self.get(job_id, owner, endpoint, target)

    def remove_images(self, job_id, owner, endpoint, target, confirmation):
        record = self.load(job_id, owner, endpoint, target)
        public = self.public(record)
        if confirmation != job_id or public['state'] not in {
                'completed', 'failed', 'cancelled', 'timed_out', 'not_dispatched', 'artifact_verified'}:
            raise Error('Confirm a terminal recovery job before removing its staged images')
        work = self.directory(record) / 'work'
        if work.exists(): shutil.rmtree(work, ignore_errors=False)
        self.update(record, staged_images_removed=True, staged_images_removed_at=time.time())
        return self.get(job_id, owner, endpoint, target)

    def close(self):
        with self.lock: workers = list(self.workers.values())
        for _worker, signal in workers: signal.set()
        for worker, _signal in workers:
            if worker.is_alive(): worker.join(timeout=5)
