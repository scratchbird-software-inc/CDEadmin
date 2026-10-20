"""Retained, revision-checked script sequencing over provider executions.

A completed statement is not a transaction commit. Providers own outcome
interpretation. Lost replies never cause implicit resubmission.
"""
import copy
from functools import wraps
import threading
import uuid
from .language_tools import analyze
from .models import DataStudioAccessError


def serialized_execution(method):
    @wraps(method)
    def call(self, context, session_id, *args, **kwargs):
        plan_id = kwargs.pop('_script_plan_id', None)
        with self.scripts.lock:
            self.scripts.check_execution(session_id, plan_id)
            try:
                return method(self, context, session_id, *args, **kwargs)
            finally:
                session=getattr(self,'_sessions',{}).get(session_id)
                request=args[0] if args and isinstance(args[0],dict) else kwargs.get('request',{})
                operation=request.get('operation') if isinstance(request,dict) else None
                mutating=(method.__name__ in {'execute','control_transaction','sqlite_transform_binding','sqlite_capture_binding'} or
                    method.__name__ in {'sqlite_extension_action','sqlite_native_session_action','sqlite_native_array_action','sqlite_native_preupdate_action'} and
                    operation not in {'inventory','status','receipt','events'})
                if (mutating and session is not None and session.language_profile=='sqlite-sql' and
                        session.provider_isolation_key is not None and session.provider_isolation_key==context.isolation_key):
                    session.native_work_revision+=1
    return call


def serialized_close(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self.scripts.lock:
            return method(self, *args, **kwargs)
    return call


class ScriptCoordinator:
    def __init__(self, studio):
        self.studio = studio
        self.plans = {}
        self.lock = threading.RLock()

    def check_execution(self, session_id, plan_id=None):
        for plan in self.plans.values():
            if plan['session_id'] == session_id and plan.get('started') and (
                    plan['state'] not in {'complete', 'stopped'} or
                    plan.get('unresolved')) and plan['plan_id'] != plan_id:
                raise DataStudioAccessError(
                    'Session is reserved by a retained script')

    def forget_closed_session(self, session_id):
        with self.lock:
            self.plans = {key: plan for key, plan in self.plans.items()
                          if plan['session_id'] != session_id}

    def prepare(self, context, session_id, source):
        session, binding = self.studio._operational_session(
            context, session_id)
        if session.language_profile == 'firebird-sql':
            raise DataStudioAccessError('Use the Firebird native script workflow for its dialect and client settings')
        if not callable(
                getattr(binding.instance, 'script_statement_outcome', None)):
            raise DataStudioAccessError(
                'Provider has no script outcome adapter')
        validator = getattr(binding.instance, 'validate_source_without_execution', None)
        checked = validator({
            'session_id': session.provider_session['session_id'],
            'language_profile': session.language_profile,
            'source': source, 'script': True,
        }) if callable(validator) else analyze(source, session.language_profile, script=True)
        if not checked['script_ready']:
            return {'state': 'invalid', 'validation': checked}
        with self.lock:
            if len(self.plans) >= 32:
                raise DataStudioAccessError(
                    'Script plan limit reached; discard a completed plan')
            plan = {'plan_id': str(uuid.uuid4()), 'session_id': session_id,
                    'endpoint_id': context.endpoint_id, 'language_profile': session.language_profile,
                    'source_sha256': checked['source_sha256'], 'statements': checked['statements'],
                    'syntax_context': {key: checked[key] for key in ('syntax_settings', 'sql_mode', 'client_sql_dialect') if key in checked},
                    'state': 'ready', 'revision': 0, 'next_statement': 0, 'occurrence_id': None, 'history': []}
            self.plans[plan['plan_id']] = plan
            return copy.deepcopy(plan)

    def _owned(self, context, plan_id):
        plan = self.plans.get(plan_id)
        if not plan or plan['endpoint_id'] != context.endpoint_id:
            raise DataStudioAccessError(
                'Script plan unavailable for this endpoint')
        session, binding = self.studio._operational_session(
            context, plan['session_id'])
        if session.language_profile != plan['language_profile']:
            raise DataStudioAccessError('Script language binding changed')
        return plan, binding

    def advance(self, context, plan_id, revision):
        with self.lock:
            plan, binding = self._owned(context, plan_id)
            if type(revision) is not int or revision != plan['revision']:
                return copy.deepcopy(plan)
            if plan['state'] == 'waiting':
                try:
                    observed = self.studio.poll(context, plan['occurrence_id'])
                    outcome = binding.instance.script_statement_outcome(
                        observed)
                except Exception:
                    # Polling may be retried; the submitted statement must not
                    # be.
                    plan['observation_unavailable'] = True
                    return copy.deepcopy(plan)
                plan.pop('observation_unavailable', None)
                if outcome == 'pending':
                    return copy.deepcopy(plan)
                plan['history'].append({'ordinal': plan['next_statement'] + 1,
                                        'occurrence_id': plan['occurrence_id'], 'outcome': outcome})
                plan['revision'] += 1
                plan['unresolved'] = outcome not in {
                    'success', 'error', 'cancelled'}
                if not plan['unresolved']:
                    plan['occurrence_id'] = None
                if outcome != 'success':
                    plan['state'] = 'stopped'
                    plan['stop_reason'] = outcome
                else:
                    plan['next_statement'] += 1
                    plan['occurrence_id'] = None
                    plan['state'] = 'stopped' if plan.get(
                        'stop_requested') else 'complete' if plan['next_statement'] == len(plan['statements']) else 'ready'
                return copy.deepcopy(plan)
            if plan['state'] != 'ready':
                return copy.deepcopy(plan)
            self.check_execution(plan['session_id'], plan_id)
            for occurrence in getattr(
                    self.studio, '_occurrences', {}).values():
                if occurrence.session_id == plan['session_id'] and not (
                        occurrence.operation or {}).get('terminal'):
                    raise DataStudioAccessError(
                        'Session has an unresolved execution')
            validator = getattr(binding.instance, 'validate_source_without_execution', None)
            if callable(validator):
                session, _ = self.studio._operational_session(context, plan['session_id'])
                checked = validator({
                    'session_id': session.provider_session['session_id'],
                    'language_profile': session.language_profile, 'script': True,
                    'source': plan['statements'][plan['next_statement']]['source'],
                })
                context_changed = any(
                    any(observed is not None and observed != value.get(name)
                        for name, observed in checked.get(key, {}).items())
                    if key == 'syntax_settings' else checked.get(key) != value
                    for key, value in plan.get('syntax_context', {}).items())
                if not checked['script_ready'] or context_changed:
                    plan.update(state='stopped', stop_reason='source-validation-changed',
                                validation=checked, revision=plan['revision'] + 1)
                    return copy.deepcopy(plan)
            plan['started'] = True
            plan['state'] = 'submitting'
            plan['revision'] += 1
            try:
                occurrence = self.studio.execute(context, plan['session_id'],
                                                 plan['statements'][plan['next_statement']
                                                                    ]['source'],
                                                 _script_plan_id=plan_id)
            except Exception:
                plan['unresolved'] = True
                plan['state'] = 'stopped'
                plan['stop_reason'] = 'submission-outcome-unavailable; do not replay'
                return copy.deepcopy(plan)
            plan['occurrence_id'] = occurrence['occurrence_id']
            plan['state'] = 'waiting'
            return copy.deepcopy(plan)

    def stop(self, context, plan_id):
        with self.lock:
            plan, _ = self._owned(context, plan_id)
            if plan['state'] in {'complete', 'stopped'}:
                return copy.deepcopy(plan)
            plan['stop_requested'] = True
            plan['state'] = 'waiting' if plan['occurrence_id'] else 'stopped'
            plan['stop_reason'] = 'user-stopped; any active statement remains provider-owned'
            plan['revision'] += 1
            # Stopping sequencing does not claim cancellation, rollback or
            # commit.
            return copy.deepcopy(plan)

    def discard(self, context, plan_id):
        with self.lock:
            plan, _ = self._owned(context, plan_id)
            if plan['state'] not in {
                    'complete', 'stopped', 'ready'} or plan['occurrence_id'] or plan.get('unresolved'):
                raise DataStudioAccessError(
                    'Retain the plan while a statement outcome is unresolved')
            del self.plans[plan_id]
            return {'discarded': True}


def retained_outcome(occurrence, engine_id):
    """Interpret the exact retained-driver result contract, not transaction state."""
    if not occurrence.get('operation', {}).get('terminal'):
        return 'pending'
    result = occurrence.get('result') or {}
    payload = (result.get('extensions', {}).get(
        engine_id) or {}).get('payload')
    if not result.get('complete') or not isinstance(payload, dict):
        return 'unknown'
    if payload.get('error'):
        return 'error'
    if payload.get('cancelled') or payload.get('canceled'):
        return 'cancelled'
    if payload.get('outcome_unknown') or payload.get('session_reuse_blocked'):
        return 'unknown'
    # Positive usability observation is required; absence of an error is
    # insufficient.
    if payload.get('session_reuse_blocked') is not False:
        return 'unknown'
    return 'success'
