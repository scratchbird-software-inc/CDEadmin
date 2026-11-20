"""MariaDB physical-chain + binlog dependency-aware retention and uncertain holds.

Prevents deletion of MariaDB binary-log archives required by unretired physical
backup chains, active recovery/PITR holds, or unresolved/uncertain receiver,
backup or replay outcomes. Keeps original native acknowledgements separate from
process or target uncertainty.
"""
from contextlib import contextmanager
from copy import deepcopy
import os
from pathlib import Path
import re
import socket
import stat
import threading
import time
import uuid

from ..operations.fileio import exclusive_file_lock, private_directory, private_file
from ..operations.models import OperationBusError
from ..operations.store import JsonOperationStore
from ..providers.mysql_family.mariadb_binlog_replay import gtids, inventory
from ..providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
from . import mysql_archive_retention as shared_retention
from .mysql_binlog_jobs import digest, identity


def parse_binlog_stem_seq(filename):
    """Split 'sr-owned.000002' -> ('sr-owned', 2) for exact sequence comparison."""
    if not isinstance(filename, str) or '.' not in filename:
        return None
    stem, _, suffix = filename.rpartition('.')
    if not stem or not re.fullmatch(r'[0-9]+', suffix):
        return None
    return stem, int(suffix)


def archive_needed_for_boundary(archive_artifact, boundary_file):
    """Return True when archive_artifact may contain events at or after boundary_file."""
    if not boundary_file:
        return True
    end_file = (archive_artifact.get('end_at') or {}).get('file')
    parsed_end = parse_binlog_stem_seq(end_file)
    parsed_boundary = parse_binlog_stem_seq(boundary_file)
    if parsed_end is None or parsed_boundary is None:
        return True
    if parsed_end[0] != parsed_boundary[0]:
        # Different log basename epoch; conservatively retain until operator retires hold.
        return True
    return parsed_end[1] >= parsed_boundary[1]


class MariaDBBackupProtectionRegistry:
    """Owner-wide atomic registry of physical-chain, recovery-chain and uncertain holds."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.lock = threading.RLock()

    @contextmanager
    def store(self, owner, endpoint):
        if type(owner) is not int or owner <= 0:
            raise BinlogArchiveError('MariaDB archive protection owner is unavailable')
        endpoint = identity(endpoint)
        directory = self.root / str(owner)
        for path in (self.root, directory):
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            private_directory(path)
        path = directory / (endpoint + '.json')
        with self.lock, (directory / '.protection.lock').open('a+b') as lock:
            private_file(Path(lock.name))
            with exclusive_file_lock(lock.fileno()):
                yield JsonOperationStore(path)

    def _scoped_states(self, owner):
        owner_dir = self.root / str(owner)
        if not owner_dir.exists():
            return
        for path in sorted(owner_dir.glob('*.json')):
            scope = identity(path.stem)
            if path.is_symlink() or not path.is_file():
                raise BinlogArchiveError('MariaDB backup protection storage identity changed')
            try:
                state = JsonOperationStore(path).read()
            except OperationBusError:
                raise BinlogArchiveError(
                    'A MariaDB backup protection store is unavailable; archive removal is refused'
                ) from None
            yield scope, state

    def _protections(self, owner, endpoint):
        references = []
        for scope, state in self._scoped_states(owner):
            for row in state.get('mariadb_holds', {}).values():
                if row.get('state') != 'retired':
                    references.append({
                        **deepcopy(row),
                        'same_registration': scope == endpoint,
                        'protection_endpoint_id': scope,
                    })
            for row in state.get('mariadb_recovery_chains', {}).values():
                if row.get('state') == 'active':
                    references.append({
                        **deepcopy(row),
                        'hold_kind': 'recovery_chain',
                        'same_registration': scope == endpoint,
                        'protection_endpoint_id': scope,
                    })
        return references

    def protections(self, owner, endpoint):
        with self.store(owner, endpoint):
            return self._protections(owner, endpoint)

    @staticmethod
    def protection_reasons(record, references):
        """Return all active hold reasons preventing deletion of a MariaDB archive."""
        reasons = []
        source_uid = (record.get('source') or {}).get('server_uid')
        artifact = (record.get('result') or {}).get('artifact') or {}
        job_id = record.get('job_id')
        for row in references:
            kind = row.get('hold_kind')
            if kind == 'recovery_chain':
                if any(
                    item.get('job_id') == job_id and item.get('endpoint_id') == record.get('endpoint_id')
                    for item in row.get('archives', [])
                ):
                    reasons.append({
                        'hold_id': row['chain_id'],
                        'hold_kind': 'recovery_chain',
                        'reason': 'Referenced by active MariaDB PITR recovery chain',
                    })
                continue
            if kind == 'active_recovery_hold':
                if job_id in (row.get('archive_job_ids') or []):
                    reasons.append({
                        'hold_id': row['hold_id'],
                        'hold_kind': 'active_recovery_hold',
                        'reason': 'Referenced by an active MariaDB physical recovery / catch-up workflow',
                    })
                    continue
                if row.get('source_uid') == source_uid and not row.get('archive_job_ids'):
                    reasons.append({
                        'hold_id': row['hold_id'],
                        'hold_kind': 'active_recovery_hold',
                        'reason': 'Active recovery hold protects source archives until retired',
                    })
                continue
            if kind == 'uncertain_hold' or row.get('state') == 'uncertain':
                if row.get('source_uid') == source_uid or (
                    not row.get('source_uid') and row.get('same_registration', True)
                ):
                    reasons.append({
                        'hold_id': row['hold_id'],
                        'hold_kind': 'uncertain_hold',
                        'origin_operation': row.get('origin_operation'),
                        'origin_job_id': row.get('origin_job_id'),
                        'reason': row.get('uncertainty_reason') or 'Unresolved process or target outcome holds source archives',
                    })
                continue
            if kind == 'physical_backup':
                if row.get('source_uid') != source_uid and not (
                    row.get('same_registration', True) and row.get('state') == 'pending_native_reply'
                ):
                    continue
                if row.get('state') in {'pending_native_reply', 'uncertain'} or not row.get('binlog_file'):
                    reasons.append({
                        'hold_id': row['hold_id'],
                        'hold_kind': 'physical_backup',
                        'backup_job_id': row.get('backup_job_id'),
                        'reason': 'Pending or unverified physical backup holds all source archives conservatively',
                    })
                elif archive_needed_for_boundary(artifact, row['binlog_file']):
                    reasons.append({
                        'hold_id': row['hold_id'],
                        'hold_kind': 'physical_backup',
                        'backup_job_id': row.get('backup_job_id'),
                        'chain_root_job_id': row.get('chain_root_job_id'),
                        'binlog_file': row.get('binlog_file'),
                        'gtid_pos': row.get('gtid_pos'),
                        'reason': f"Required for PITR roll-forward from physical backup at {row['binlog_file']}",
                    })
        return reasons

    @classmethod
    def protected(cls, record, references):
        return bool(cls.protection_reasons(record, references))

    @contextmanager
    def guard(self, owner, endpoint, record):
        with self.store(owner, endpoint):
            refs = self._protections(owner, endpoint)
            reasons = self.protection_reasons(record, refs) if not record.get('artifact_removed') else []
            if reasons:
                summary = '; '.join(f"{r['hold_kind']}:{r['hold_id']}" for r in reasons)
                raise BinlogArchiveError(
                    f'MariaDB dependency-aware retention protects this archive ({summary}); '
                    'retire dependent physical backups, recovery holds, or uncertain holds before removal'
                )
            yield

    def register_physical_backup_hold(
        self, owner, endpoint, *, backup_job_id, source_uid, backup_type,
        chain_root_job_id=None, parent_job_id=None, binlog_file=None,
        binlog_position=None, gtid_pos=None, from_lsn=None, to_lsn=None,
        last_lsn=None, state='pending_native_reply', native_acknowledged=False,
    ):
        hold_id = identity(backup_job_id)
        now = time.time()
        with self.store(owner, endpoint) as store:
            def change(doc):
                holds = doc.setdefault('mariadb_holds', {})
                existing = holds.get(hold_id, {})
                if existing.get('state') == 'retired':
                    raise BinlogArchiveError('This MariaDB physical backup hold was already retired')
                holds[hold_id] = {
                    'hold_id': hold_id,
                    'hold_kind': 'physical_backup',
                    'backup_job_id': hold_id,
                    'backup_type': backup_type,
                    'chain_root_job_id': chain_root_job_id or hold_id,
                    'parent_job_id': parent_job_id,
                    'source_uid': source_uid,
                    'binlog_file': binlog_file,
                    'binlog_position': binlog_position,
                    'gtid_pos': gtid_pos,
                    'from_lsn': str(from_lsn) if from_lsn is not None else None,
                    'to_lsn': str(to_lsn) if to_lsn is not None else None,
                    'last_lsn': str(last_lsn) if last_lsn is not None else None,
                    'state': state,
                    'native_acknowledged': bool(native_acknowledged),
                    'execution_host': socket.gethostname(),
                    'created_at': existing.get('created_at', now),
                    'updated_at': now,
                    'automatic_retry': False,
                }
            store.change(change)
            return deepcopy(store.read()['mariadb_holds'][hold_id])

    def register_active_recovery_hold(
        self, owner, endpoint, *, recovery_job_id, source_uid,
        base_backup_job_id, archive_job_ids=(),
    ):
        hold_id = identity(recovery_job_id)
        now = time.time()
        with self.store(owner, endpoint) as store:
            def change(doc):
                holds = doc.setdefault('mariadb_holds', {})
                holds[hold_id] = {
                    'hold_id': hold_id,
                    'hold_kind': 'active_recovery_hold',
                    'recovery_job_id': hold_id,
                    'source_uid': source_uid,
                    'base_backup_job_id': base_backup_job_id,
                    'archive_job_ids': [identity(jid) for jid in archive_job_ids],
                    'state': 'active',
                    'created_at': now,
                    'updated_at': now,
                }
            store.change(change)
            return deepcopy(store.read()['mariadb_holds'][hold_id])

    def record_uncertain_hold(
        self, owner, endpoint, *, origin_operation, origin_job_id, source_uid,
        uncertainty_reason, native_acknowledged=False,
        process_termination_confirmed=False, target_outcome_confirmed=False,
    ):
        hold_id = str(uuid.uuid5(uuid.UUID(identity(origin_job_id)), 'mariadb-uncertain:' + str(origin_operation)))
        now = time.time()
        with self.store(owner, endpoint) as store:
            def change(doc):
                holds = doc.setdefault('mariadb_holds', {})
                existing = holds.get(hold_id, {})
                if existing.get('state') == 'retired':
                    return
                holds[hold_id] = {
                    'hold_id': hold_id,
                    'hold_kind': 'uncertain_hold',
                    'origin_operation': str(origin_operation),
                    'origin_job_id': identity(origin_job_id),
                    'source_uid': source_uid,
                    'uncertainty_reason': str(uncertainty_reason),
                    'state': 'uncertain',
                    'native_acknowledged': bool(native_acknowledged),
                    'process_termination_confirmed': bool(process_termination_confirmed),
                    'target_outcome_confirmed': bool(target_outcome_confirmed),
                    'execution_host': socket.gethostname(),
                    'created_at': existing.get('created_at', now),
                    'updated_at': now,
                    'automatic_retry': False,
                }
            store.change(change)
            return deepcopy(store.read().get('mariadb_holds', {}).get(hold_id))

    def physical_backup_has_dependents(self, owner, endpoint, backup_job_id):
        """Prevent retiring/deleting a physical backup while child incrementals or recovery holds need it."""
        backup_job_id = identity(backup_job_id)
        dependents = []
        for _scope, state in self._scoped_states(owner):
            for row in state.get('mariadb_holds', {}).values():
                if row.get('state') == 'retired' or row.get('hold_id') == backup_job_id:
                    continue
                if row.get('parent_job_id') == backup_job_id or row.get('chain_root_job_id') == backup_job_id:
                    if row.get('backup_job_id') != backup_job_id:
                        dependents.append({'hold_id': row['hold_id'], 'hold_kind': row['hold_kind']})
                elif row.get('base_backup_job_id') == backup_job_id:
                    dependents.append({'hold_id': row['hold_id'], 'hold_kind': row['hold_kind']})
            for chain in state.get('mariadb_recovery_chains', {}).values():
                if chain.get('state') == 'active' and backup_job_id in (
                    chain.get('backup_job_id'),
                    *(chain.get('chain_member_job_ids') or []),
                ):
                    dependents.append({'hold_id': chain['chain_id'], 'hold_kind': 'recovery_chain'})
        return dependents

    def list_holds(self, owner, endpoint, offset=0, limit=25, all_registrations=False):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100 or type(all_registrations) is not bool:
            raise BinlogArchiveError('Select a valid MariaDB protection hold page')
        with self.store(owner, endpoint) as store:
            if all_registrations:
                records = [
                    {**deepcopy(row), 'protection_endpoint_id': scope}
                    for scope, state in self._scoped_states(owner)
                    for row in state.get('mariadb_holds', {}).values()
                ]
            else:
                records = [deepcopy(row) for row in store.read().get('mariadb_holds', {}).values()]
        ordered = sorted(records, key=lambda r: (r.get('created_at', 0), r['hold_id']), reverse=True)
        return {
            'holds': ordered[offset:offset + limit],
            'total': len(ordered),
            'offset': offset,
            'limit': limit,
            'uncertain_hold_count': sum(1 for r in ordered if r.get('state') == 'uncertain'),
            'active_physical_hold_count': sum(
                1 for r in ordered if r.get('hold_kind') == 'physical_backup' and r.get('state') != 'retired'
            ),
        }

    def review_retire_hold(self, owner, endpoint, hold_id):
        hold_id = identity(hold_id)
        with self.store(owner, endpoint) as store:
            record = store.read().get('mariadb_holds', {}).get(hold_id)
            if record is None or record.get('state') == 'retired':
                raise BinlogArchiveError('Select an active or uncertain MariaDB hold to retire')
            if record.get('hold_kind') == 'physical_backup':
                deps = self.physical_backup_has_dependents(owner, endpoint, hold_id)
                if deps:
                    raise BinlogArchiveError(
                        'Retire dependent incremental backups, active recoveries, or recovery chains before retiring this base backup hold'
                    )
            review = {
                'review_id': str(uuid.uuid4()),
                'hold_id': hold_id,
                'snapshot': digest(record),
                'expires_at': time.time() + 300,
                'owner': owner,
                'endpoint_id': endpoint,
            }
            review['review_digest'] = digest(review)
            store.change(lambda doc: doc.setdefault('mariadb_hold_retire_reviews', {}).update({review['review_id']: review}))
        return {
            'review_id': review['review_id'],
            'hold_id': hold_id,
            'snapshot': review['snapshot'],
            'expires_at': review['expires_at'],
            'review_digest': review['review_digest'],
            'hold': deepcopy(record),
            'warning': (
                'Retiring this hold releases its dependency lock on MariaDB binary-log archives. '
                'Original native acknowledgements and uncertain process/target history remain recorded without modification.'
            ),
        }

    def retire_hold(self, owner, endpoint, request):
        if (not isinstance(request, dict) or
                set(request) - {'review_id', 'review_digest', 'confirmed', 'reconciliation_acknowledged'} or
                request.get('confirmed') is not True):
            raise BinlogArchiveError('Confirm the exact MariaDB hold retirement review')
        with self.store(owner, endpoint) as store:
            doc = store.read()
            review = doc.get('mariadb_hold_retire_reviews', {}).get(identity(request.get('review_id')))
            if review is None or review['review_digest'] != request.get('review_digest'):
                raise BinlogArchiveError('MariaDB hold retirement review is unavailable')
            record = doc.get('mariadb_holds', {}).get(review['hold_id'])
            if record is None:
                raise BinlogArchiveError('MariaDB hold record is unavailable')
            if record.get('state') == 'retired' and record.get('retirement_review_id') == review['review_id']:
                return deepcopy(record)
            if review['expires_at'] < time.time() or digest(record) != review['snapshot']:
                raise BinlogArchiveError('MariaDB hold state changed; prepare a new retirement review')
            if record.get('state') == 'uncertain' and request.get('reconciliation_acknowledged') is not True:
                raise BinlogArchiveError(
                    'Retiring an uncertain hold requires explicit reconciliation_acknowledged=True'
                )
            if record.get('hold_kind') == 'physical_backup' and self.physical_backup_has_dependents(owner, endpoint, record['hold_id']):
                raise BinlogArchiveError('Dependent physical chain members or recovery holds still reference this backup')
            def change(state):
                target = state['mariadb_holds'][record['hold_id']]
                target.update(
                    previous_state=target.get('state'),
                    state='retired',
                    retired_at=time.time(),
                    retirement_review_id=review['review_id'],
                    original_native_acknowledgement_preserved=True,
                )
            store.change(change)
            return deepcopy(store.read()['mariadb_holds'][record['hold_id']])


def protection_manager(service):
    from flask import current_app
    store = getattr(service.operation_bus, 'store', None)
    if not isinstance(store, JsonOperationStore):
        raise BinlogArchiveError('MariaDB archive protection requires durable application storage')
    with service._semantic_lock:
        registry = getattr(service, 'mariadb_backup_protection_registry', None)
        if registry is None:
            root = (
                current_app.config.get('CDEADMIN_MARIADB_BACKUP_PROTECTION_ROOT')
                or str(store.path.parent / 'mariadb-backup-protection')
            )
            registry = service.mariadb_backup_protection_registry = MariaDBBackupProtectionRegistry(root)
        return registry


def sync_uncertain_jobs(service, archives, owner, endpoint):
    """Ensure any unresolved/unknown MariaDB archive, receiver or replay job has an explicit uncertain hold."""
    registry = protection_manager(service)
    sources = [('mariadb_binlog_archive', archives)]
    for attr, label in (
        ('mariadb_continuous_binlog_jobs', 'mariadb_continuous_receiver'),
        ('mariadb_binlog_replay_jobs', 'mariadb_binlog_replay'),
    ):
        mgr = getattr(service, attr, None)
        if mgr is not None:
            sources.append((label, mgr))
    for label, mgr in sources:
        index = mgr.scope(owner, endpoint) / 'index'
        if not index.is_dir():
            continue
        with os.scandir(index) as entries:
            for entry in entries:
                if entry.name.startswith('.'):
                    continue
                jid = identity(entry.name.split('_', 1)[-1])
                rec = mgr.load(jid, owner, endpoint)
                if rec.get('state') == 'unknown' or (
                    rec.get('started_at') and rec.get('state') in {'failed', 'cancelled'}
                    and rec.get('native_process_termination_confirmed') is False
                ):
                    reconciled = (rec.get('writer_reconciliation') or {}).get('process_scope_stopped') is True
                    if not reconciled:
                        registry.record_uncertain_hold(
                            owner, endpoint,
                            origin_operation=label,
                            origin_job_id=jid,
                            source_uid=(rec.get('source') or {}).get('server_uid'),
                            uncertainty_reason=f'{label} {jid} has unconfirmed process/outcome finality',
                            native_acknowledged=bool((rec.get('result') or {}).get('native_operation_returned')),
                            process_termination_confirmed=bool(rec.get('native_process_termination_confirmed')),
                            target_outcome_confirmed=False,
                        )


def evaluate_retention(service, archives, owner, endpoint, policy_value):
    """Evaluate every MariaDB archive against age, keep_latest, physical chains, recovery holds & uncertain holds."""
    selected = shared_retention.policy(policy_value)
    sync_uncertain_jobs(service, archives, owner, endpoint)
    registry = protection_manager(service)
    references = registry.protections(owner, endpoint)
    directory = archives.scope(owner, endpoint) / 'index'
    cutoff = time.time() - selected['retention_days'] * 86400
    items = []
    valid_by_source = {}
    if directory.exists():
        shared_retention.directory_identity(directory)
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.name.startswith('.'):
                    continue
                info = entry.stat(follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode) or info.st_size:
                    raise BinlogArchiveError('MariaDB archive retention index identity changed')
                jid = identity(entry.name.split('_', 1)[-1])
                rec = archives.load(jid, owner, endpoint)
                items.append(rec)
                artifact = (rec.get('result') or {}).get('artifact')
                if (not rec.get('artifact_removed') and not rec.get('artifact_removal')
                        and not rec.get('retention_pinned')
                        and rec['state'] in shared_retention.RETAINED
                        and rec.get('native_process_termination_confirmed') is True
                        and artifact is not None
                        and not registry.protected(rec, references)):
                    valid_by_source.setdefault(digest(rec['source']), []).append((rec['created_at'], jid))
    kept_latest = set()
    for rows in valid_by_source.values():
        rows.sort(reverse=True)
        for _created, jid in rows[:selected['keep_latest']]:
            kept_latest.add(jid)

    evaluations = []
    summary = {
        'eligible_for_removal': 0,
        'protected_by_physical_chain': 0,
        'protected_by_recovery_hold': 0,
        'protected_by_uncertain_hold': 0,
        'pinned': 0,
        'minimum_count': 0,
        'within_retention_age': 0,
        'already_removed': 0,
        'unavailable_or_unverified': 0,
    }
    for rec in sorted(items, key=lambda r: (r['created_at'], r['job_id'])):
        jid = rec['job_id']
        artifact = (rec.get('result') or {}).get('artifact') or {}
        reasons = registry.protection_reasons(rec, references) if not rec.get('artifact_removed') else []
        if rec.get('artifact_removed'):
            disposition = 'already_removed'
        elif any(r['hold_kind'] == 'uncertain_hold' for r in reasons):
            disposition = 'protected_by_uncertain_hold'
        elif any(r['hold_kind'] in {'recovery_chain', 'active_recovery_hold'} for r in reasons):
            disposition = 'protected_by_recovery_hold'
        elif any(r['hold_kind'] == 'physical_backup' for r in reasons):
            disposition = 'protected_by_physical_chain'
        elif rec.get('retention_pinned'):
            disposition = 'pinned'
        elif (rec['state'] not in shared_retention.RETAINED or
              rec.get('native_process_termination_confirmed') is not True or not artifact):
            disposition = 'unavailable_or_unverified'
        elif jid in kept_latest:
            disposition = 'minimum_count'
        elif rec['created_at'] >= cutoff:
            disposition = 'within_retention_age'
        else:
            disposition = 'eligible_for_removal'
        summary[disposition] += 1
        evaluations.append({
            'job_id': jid,
            'created_at': rec['created_at'],
            'source_uid': (rec.get('source') or {}).get('server_uid'),
            'start_from': artifact.get('start_from'),
            'end_at': artifact.get('end_at'),
            'disposition': disposition,
            'protected_by': reasons,
            'retention_pinned': bool(rec.get('retention_pinned')),
        })
    return {
        'policy': selected,
        'cutoff_time': cutoff,
        'summary': summary,
        'archives': evaluations,
        'active_holds_evaluated': len(references),
        'remote_database_mutation': False,
    }


def recovery_chain_action(service, archives, owner, endpoint_id, operation, request):
    """Bind an unretired MariaDB physical backup and ordered MariaDB binlog archives into an active recovery chain."""
    registry = protection_manager(service)
    if operation == 'list':
        if set(request) - {'offset', 'limit'}:
            raise BinlogArchiveError('Select a MariaDB recovery chain page')
        offset, limit = request.get('offset', 0), request.get('limit', 25)
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise BinlogArchiveError('Invalid MariaDB recovery chain page bounds')
        with registry.store(owner, endpoint_id) as store:
            chains = list(store.read().get('mariadb_recovery_chains', {}).values())
        ordered = sorted(chains, key=lambda r: (r['created_at'], r['chain_id']), reverse=True)
        return {'chains': ordered[offset:offset + limit], 'total': len(ordered), 'offset': offset, 'limit': limit}

    if operation == 'review_retire':
        if set(request) != {'chain_id'}:
            raise BinlogArchiveError('Select an active MariaDB recovery chain to retire')
        cid = identity(request['chain_id'])
        with registry.store(owner, endpoint_id) as store:
            chain = store.read().get('mariadb_recovery_chains', {}).get(cid)
            if chain is None or chain.get('state') != 'active':
                raise BinlogArchiveError('Select an active MariaDB recovery chain')
            review = {
                'review_id': str(uuid.uuid4()),
                'chain_id': cid,
                'snapshot': digest(chain),
                'expires_at': time.time() + 300,
            }
            review['review_digest'] = digest(review)
            store.change(lambda doc: doc.setdefault('mariadb_chain_retire_reviews', {}).update({review['review_id']: review}))
            return {**review, 'chain': deepcopy(chain)}

    if operation == 'retire':
        if set(request) != {'review_id', 'review_digest', 'confirmed'} or request.get('confirmed') is not True:
            raise BinlogArchiveError('Confirm the exact MariaDB recovery chain retirement review')
        with registry.store(owner, endpoint_id) as store:
            doc = store.read()
            review = doc.get('mariadb_chain_retire_reviews', {}).get(identity(request['review_id']))
            if review is None or review['review_digest'] != request['review_digest']:
                raise BinlogArchiveError('MariaDB recovery chain retirement review is unavailable')
            chain = doc.get('mariadb_recovery_chains', {}).get(review['chain_id'])
            if chain is None:
                raise BinlogArchiveError('MariaDB recovery chain is unavailable')
            if chain.get('state') == 'retired' and chain.get('retirement_review_id') == review['review_id']:
                return deepcopy(chain)
            if time.time() > review['expires_at'] or digest(chain) != review['snapshot']:
                raise BinlogArchiveError('MariaDB recovery chain changed; prepare a new retirement review')
            updated = {**chain, 'state': 'retired', 'retired_at': time.time(), 'retirement_review_id': review['review_id']}
            store.change(lambda s: s['mariadb_recovery_chains'].update({chain['chain_id']: updated}))
            return deepcopy(updated)

    if operation == 'review':
        if set(request) - {'backup_job_id', 'archive_job_ids', 'stop_gtid'} or not {'backup_job_id', 'archive_job_ids'} <= set(request):
            raise BinlogArchiveError('Select a MariaDB physical backup job and ordered binary-log archive jobs')
        backup_id = identity(request['backup_job_id'])
        archive_ids = request['archive_job_ids']
        if not isinstance(archive_ids, list) or not 1 <= len(archive_ids) <= 64:
            raise BinlogArchiveError('Select 1 to 64 distinct ordered MariaDB archive jobs')
        archive_ids = [identity(aid) for aid in archive_ids]
        if len(set(archive_ids)) != len(archive_ids):
            raise BinlogArchiveError('Select distinct ordered MariaDB archive jobs')
        stop_gtid = request.get('stop_gtid')
        if stop_gtid is not None and len(gtids(stop_gtid)) != 1:
            raise BinlogArchiveError('Select a single canonical MariaDB stop GTID or null')
        with registry.store(owner, endpoint_id) as store:
            hold = store.read().get('mariadb_holds', {}).get(backup_id)
            if hold is None or hold.get('hold_kind') != 'physical_backup' or hold.get('state') != 'active':
                raise BinlogArchiveError('Select an active verified MariaDB physical backup hold')
            base_gtids = gtids(hold.get('gtid_pos') or '')
            current_gtids = dict(base_gtids)
            archive_entries = []
            for idx, aid in enumerate(archive_ids):
                rec = archives.load(aid, owner, endpoint_id)
                artifact = (rec.get('result') or {}).get('artifact')
                if (rec['state'] not in shared_retention.RETAINED or rec.get('artifact_removed')
                        or rec.get('artifact_removal') or rec.get('native_process_termination_confirmed') is not True
                        or artifact is None or rec['source']['server_uid'] != hold['source_uid']):
                    raise BinlogArchiveError('Recovery chain archives must be verified, retained, and from the same MariaDB server_uid')
                verified = archives.native_verify(archives.directory(rec) / 'archive', rec['source'])
                if digest(verified) != digest(artifact):
                    raise BinlogArchiveError('MariaDB archive bytes changed since verification')
                inv = inventory(
                    archives.directory(rec) / 'archive', verified,
                    stop=stop_gtid if (stop_gtid and idx == len(archive_ids) - 1) else None,
                )
                start_pos = gtids(inv['start_gtid_pos'])
                end_pos = gtids(inv['end_gtid_pos'])
                for domain, (srv, seq) in start_pos.items():
                    present = current_gtids.get(domain)
                    if present is None or present[1] < seq or (present[1] == seq and present[0] != srv):
                        raise BinlogArchiveError(
                            f'MariaDB recovery chain GTID gap before archive {aid} on domain {domain}'
                        )
                for domain, val in end_pos.items():
                    if current_gtids.get(domain, (0, 0))[1] < val[1]:
                        current_gtids[domain] = val
                archive_entries.append({
                    'job_id': aid,
                    'endpoint_id': endpoint_id,
                    'artifact_digest': digest(verified),
                    'start_gtid_pos': inv['start_gtid_pos'],
                    'end_gtid_pos': inv['end_gtid_pos'],
                })
            chain_members = [backup_id]
            if hold.get('parent_job_id') and hold['parent_job_id'] not in chain_members:
                chain_members.append(hold['parent_job_id'])
            if hold.get('chain_root_job_id') and hold['chain_root_job_id'] not in chain_members:
                chain_members.append(hold['chain_root_job_id'])
            inputs = {
                'backup_job_id': backup_id,
                'chain_member_job_ids': chain_members,
                'source_uid': hold['source_uid'],
                'base_gtid_pos': hold.get('gtid_pos') or '',
                'end_gtid_pos': ','.join(f'{d}-{s}-{q}' for d, (s, q) in sorted(current_gtids.items())),
                'stop_gtid': stop_gtid,
                'archives': archive_entries,
            }
            review = {
                'review_id': str(uuid.uuid4()),
                'created_at': time.time(),
                'expires_at': time.time() + 300,
                'inputs': inputs,
            }
            review['review_digest'] = digest(review)
            store.change(lambda doc: doc.setdefault('mariadb_recovery_chain_reviews', {}).update({review['review_id']: review}))
            return review

    if operation == 'activate':
        if set(request) != {'review_id', 'review_digest', 'confirmed'} or request.get('confirmed') is not True:
            raise BinlogArchiveError('Confirm the exact MariaDB recovery chain review')
        with registry.store(owner, endpoint_id) as store:
            doc = store.read()
            review = doc.get('mariadb_recovery_chain_reviews', {}).get(identity(request['review_id']))
            if review is None or review['review_digest'] != request['review_digest']:
                raise BinlogArchiveError('MariaDB recovery chain review is unavailable')
            existing = doc.get('mariadb_recovery_chains', {}).get(review['review_id'])
            if existing is not None:
                return deepcopy(existing)
            if review['expires_at'] < time.time():
                raise BinlogArchiveError('MariaDB recovery chain review expired')
            chain = {
                **deepcopy(review['inputs']),
                'chain_id': review['review_id'],
                'state': 'active',
                'created_at': time.time(),
            }
            store.change(lambda s: s.setdefault('mariadb_recovery_chains', {}).update({chain['chain_id']: chain}))
            return deepcopy(chain)

    raise BinlogArchiveError('Unknown MariaDB recovery chain action')


def action(service, archives, owner, endpoint_id, operation, request):
    sync_uncertain_jobs(service, archives, owner, endpoint_id)
    registry = protection_manager(service)
    if operation == 'retention_evaluate':
        if set(request) != {'policy'}:
            raise BinlogArchiveError('Select an archive retention policy to evaluate')
        return evaluate_retention(service, archives, owner, endpoint_id, request['policy'])
    if operation == 'hold_list':
        if set(request) - {'offset', 'limit', 'all_registrations'}:
            raise BinlogArchiveError('Invalid MariaDB hold listing request')
        return registry.list_holds(owner, endpoint_id, **request)
    if operation == 'hold_record_uncertain':
        required = {'origin_operation', 'origin_job_id', 'source_uid', 'uncertainty_reason'}
        if not required <= set(request) or set(request) - required - {
            'native_acknowledged', 'process_termination_confirmed', 'target_outcome_confirmed',
        }:
            raise BinlogArchiveError('Supply exact uncertain-hold origin and reason fields')
        return registry.record_uncertain_hold(owner, endpoint_id, **request)
    if operation == 'hold_review_retire':
        if set(request) != {'hold_id'}:
            raise BinlogArchiveError('Select one MariaDB hold to review for retirement')
        return registry.review_retire_hold(owner, endpoint_id, request['hold_id'])
    if operation == 'hold_retire':
        return registry.retire_hold(owner, endpoint_id, request)
    if operation.startswith('recovery_chain_'):
        return recovery_chain_action(
            service, archives, owner, endpoint_id,
            operation.removeprefix('recovery_chain_'), request,
        )
    return shared_retention.action(service, archives, owner, endpoint_id, operation, request)
