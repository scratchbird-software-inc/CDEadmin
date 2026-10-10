"""Explicit participant recovery with persisted dispatch and no replay.

The store records operator workflow, never database transaction authority.
Each participant is authorized independently by the workspace resolver.
Native decisions use the existing single-participant recovery owner.
"""

import copy
from dataclasses import asdict
import hashlib
import json
import time
import uuid

from pgadmin.cdeadmin.operations.store import JsonOperationStore
from . import limbo


class RecoveryGroupError(ValueError):
    """A recovery review or dispatch cannot be admitted."""


def digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(',', ':'),
        default=lambda item: sorted(item) if isinstance(
            item, (set, frozenset)) else str(item)).encode()).hexdigest()


def participant_binding(context, route):
    return digest({'context': asdict(context), 'route': route})


def inspect_participant(provider, route, identifier):
    """Read one selected native identity using a fresh owned attachment."""
    provider._admit_transport({'route': route})
    provider.permissions.require('administer', 'resource')
    provider.permissions.require('maintenance_admin', 'endpoint')
    client = provider.client
    with client._temporary_operation():
        connection = client._connect({'route': route})
        try:
            records = limbo.inspect_attachment(connection, client.module)
            record = next((item for item in records
                           if item['transaction_id'] == identifier), None)
            if record is None:
                raise RecoveryGroupError(
                    'The selected transaction is not currently in limbo; '
                    'its outcome has not been inferred')
            with limbo._metadata_transaction(
                    connection, client.module) as transaction:
                with transaction.cursor() as cursor:
                    cursor.execute(
                        "SELECT RDB$GET_CONTEXT('SYSTEM','DB_GUID'), "
                        "RDB$GET_CONTEXT('SYSTEM','DB_FILE_ID') "
                        'FROM RDB$DATABASE')
                    guid, file_id = cursor.fetchone()
            identity = {'guid': str(uuid.UUID(guid)), 'file_id': file_id}
            if (not isinstance(file_id, str) or not file_id or
                    len(file_id) > 1024):
                raise RecoveryGroupError(
                    'Native database identity unavailable')
            return identity, record
        finally:
            client._release_attachment(connection)


class RecoveryGroups:
    """One application-process coordinator over the existing durable store."""

    def __init__(self, store, clock=time.time):
        self.store = store
        self.clock = clock
        self.instance_id = str(uuid.uuid4())

    def _require_store(self):
        if not isinstance(self.store, JsonOperationStore):
            raise RecoveryGroupError(
                'Recovery requires persistent operation storage')

    @staticmethod
    def _record(state, group_id, owner, coordinator):
        record = state.get('firebird_recovery_groups', {}).get(group_id)
        if record is None or record['owner'] != owner or (
                record['coordinator_server_id'] != coordinator):
            raise RecoveryGroupError('Recovery group unavailable')
        return record

    def _public(self, record):
        result = copy.deepcopy(record)
        result.pop('owner', None)
        for item in result['participants']:
            item.pop('binding', None)
        if result['state'] == 'executing' and result['instance_id'] != (
                self.instance_id):
            result['state'] = 'unknown_outcome'
        result.pop('instance_id', None)
        result.update(automatic_mutation_retry=False,
                      global_outcome_inferred=False,
                      atomicity='not-claimed',
                      dispatch_may_be_interrupted=(
                          result['state'] in {'executing', 'unknown_outcome'}))
        return result

    def get(self, group_id, owner, coordinator):
        self._require_store()
        return self._public(self._record(
            self.store.read(), group_id, owner, coordinator))

    def preview(self, request, owner, coordinator, resolve):
        self._require_store()
        if not isinstance(request, dict) or set(request) != {
                'decision', 'participants'} or request['decision'] not in (
                    'commit', 'rollback'):
            raise RecoveryGroupError(
                'Choose a recovery decision and participants')
        selections = request['participants']
        if not isinstance(selections, list) or not 1 <= len(selections) <= 64:
            raise RecoveryGroupError('Select between 1 and 64 participants')
        participants = []
        identities = set()
        for selection in selections:
            if not isinstance(selection, dict) or set(selection) != {
                    'server_id', 'database_target_id', 'transaction_id'}:
                raise RecoveryGroupError('Participant selection is invalid')
            if type(selection['server_id']) is not int or (
                    selection['server_id'] <= 0) or not isinstance(
                        selection['database_target_id'], str) or not (
                            0 < len(selection['database_target_id']) <= 128):
                raise RecoveryGroupError(
                    'Select a registered endpoint and database')
            identifier = limbo.transaction_id(selection['transaction_id'])
            selected = {**selection, 'transaction_id': identifier}
            resolved = resolve(selected)
            key = digest([resolved['database_identity'], identifier])
            if key in identities:
                raise RecoveryGroupError(
                    'Duplicate native database participant')
            identities.add(key)
            observed = {key: copy.deepcopy(resolved[key]) for key in (
                'database', 'server_name', 'binding',
                'database_identity', 'observation')}
            participants.append({**selected, **observed,
                                 'observed_at': self.clock(),
                                 'state': 'not_dispatched'})
        record = {'schema': 'cdeadmin.firebird-recovery-group.v1',
                  'group_id': str(uuid.uuid4()), 'owner': owner,
                  'coordinator_server_id': coordinator,
                  'decision': request['decision'], 'state': 'reviewed',
                  'participants': participants, 'created_at': self.clock(),
                  'expires_at': self.clock() + 300,
                  'instance_id': self.instance_id}
        record['review_digest'] = digest(record)
        if len(json.dumps(record).encode()) > 1024 * 1024:
            raise RecoveryGroupError(
                'Recovery review exceeds the supported size')

        def save(state):
            state.setdefault('firebird_recovery_groups', {})[
                record['group_id']] = record
            return record

        return self._public(self.store.change(save))

    def apply(self, request, owner, coordinator, resolve):
        self._require_store()
        if not isinstance(request, dict) or set(request) != {
                'group_id', 'review_digest', 'decision',
                'coordinator_reviewed', 'confirmations'}:
            raise RecoveryGroupError('Recovery confirmation is invalid')
        record = self._record(self.store.read(), request['group_id'],
                              owner, coordinator)
        if record['state'] != 'reviewed':
            return self._public(record)
        expected = [{'database': item['database'],
                     'transaction_id': item['transaction_id']}
                    for item in record['participants']]
        if (request['review_digest'] != record['review_digest'] or
                request['decision'] != record['decision'] or
                request['coordinator_reviewed'] is not True or
                request['confirmations'] != expected or
                self.clock() > record['expires_at']):
            raise RecoveryGroupError(
                'Review expired or confirmations do not match')
        # Reauthorize and inspect every participant before the first decision.
        resolved = []
        for item in record['participants']:
            current = resolve(item)
            if any(current[key] != item[key] for key in (
                    'binding', 'database_identity', 'observation')):
                raise RecoveryGroupError(
                    'Participant changed; create a new review')
            resolved.append(current)

        def claim(state):
            current = self._record(
                state, record['group_id'], owner, coordinator)
            if current['state'] != 'reviewed':
                return False
            if self.clock() > current['expires_at']:
                raise RecoveryGroupError('Review expired during inspection')
            current.update(state='executing', instance_id=self.instance_id)
            return True

        if not self.store.change(claim):
            return self.get(record['group_id'], owner, coordinator)
        for index, current in enumerate(resolved):
            def mark_dispatch(state):
                item = self._record(state, record['group_id'], owner,
                                    coordinator)['participants'][index]
                item.update(state='unknown_outcome',
                            dispatched_at=self.clock())

            # Persistence failure here prevents this native call. An already
            # dispatched earlier participant is never compensated or replayed.
            self.store.change(mark_dispatch)
            outcome = {'state': 'unknown_outcome'}
            try:
                receipt = current['dispatch'](record['decision'])
                outcome['receipt'] = receipt
                if receipt.get('native_decision_returned') is True and (
                        receipt.get('native_decision_requested') ==
                        record['decision']):
                    outcome['state'] = 'native_decision_returned'
            except Exception as error:
                outcome['error_type'] = type(error).__name__
                released = getattr(error, 'attachment_released', None)
                if isinstance(released, bool):
                    outcome['attachment_released'] = released
            needs_review = (outcome['state'] == 'unknown_outcome' or
                            outcome.get('receipt', {}).get(
                                'attachment_released') is not True)

            def save_result(state):
                saved = self._record(state, record['group_id'], owner,
                                     coordinator)
                saved['participants'][index].update(outcome)
                if needs_review:
                    saved['state'] = 'needs_review'

            self.store.change(save_result)
            if needs_review:
                break
        else:
            def finish(state):
                self._record(state, record['group_id'], owner,
                             coordinator)['state'] = 'native_calls_returned'

            self.store.change(finish)
        return self.get(record['group_id'], owner, coordinator)
