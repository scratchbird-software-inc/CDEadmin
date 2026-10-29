##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Pure model of BI alerts and subscriptions (docs/en_US/bi_alerts.rst).

Validation of an alert definition, the condition metrics and comparisons,
the edge / level firing state machine and the bounded message preview.
Nothing here touches a database, a clock or the network, so every rule can
be tested with plain values.
"""

from __future__ import annotations

import copy
import math
import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import CroniterBadCronError, croniter

from pgadmin.cdeadmin.semantic_models.models import EXPORT_FORMATS

from .models import BIError

KINDS = ('alert', 'subscription')
RESOURCE_TYPES = ('question', 'dashboard')
OPERATORS = ('>', '>=', '<', '<=', '==', '!=', 'between')
AGGREGATES = ('first', 'sum', 'avg', 'min', 'max')
AGAINST = ('constant', 'previous_change', 'previous_percent')
FIRE_ON = ('transition', 'every_evaluation')
CHANNEL_TYPES = ('in_app', 'email', 's3', 'webhook')
BREACH_STATES = ('unknown', 'ok', 'breach')

MAX_CHANNELS = 8
MAX_RECIPIENTS = 20
MAX_PARAMETERS = 64
MAX_FAILURES = 5
MAX_MUTE = timedelta(days=90)
MIN_MUTE = timedelta(minutes=1)
DEFAULT_EXPIRY_DAYS = 30
HARD_MESSAGE_ROWS = 25
MAX_CELL_CHARS = 200
MAX_PREVIEW_COLUMNS = 12

_OBJECT_BASE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$')
_PROFILE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$')
_EMAIL = re.compile(r'^[^@\s,;<>()\[\]\\"]{1,64}@[A-Za-z0-9.-]{1,253}$')

# What an evaluation or delivery failure is allowed to say.  The history
# keeps these fixed texts and a code, never a database or transport message,
# because those can quote SQL, paths or credentials.
FAILURE_TEXT = {
    'resource_unavailable': 'The owner can no longer view the resource.',
    'archived': 'The question is archived.',
    'execution_failed': 'The question could not be executed.',
    'column_missing': 'The condition column is not in the result.',
    'column_redacted': 'The condition column is redacted by the result '
                       'policy.',
    'column_not_numeric': 'The condition column is not numeric.',
    'result_truncated': 'The result was truncated, so the row count is not '
                        'exact.',
    'credential_unavailable': 'The delegated credentials are unavailable.',
    'delegation_expired': 'The delegation expired.',
    'delegation_revoked': 'The delegation was revoked.',
    'endpoint_changed': 'The endpoint changed after authorization.',
    'repeated_failures': 'Paused after repeated failures.',
    'export_not_permitted': 'The result policy does not allow this export.',
    'no_exportable_card': 'No card of the dashboard can be exported.',
    'card_failed': 'A card could not be run.',
    'no_access': 'The owner cannot view a card\'s question.',
    'no_card_data': 'No card of the dashboard produced data.',
    'delivery_failed': 'A delivery failed.',
    'worker_error': 'The evaluation stopped unexpectedly.',
    'user_paused': 'Paused by a user.',
    'scheduler_unavailable': 'Unattended scheduling is not configured.',
}


class AlertError(BIError):
    """An alert or subscription request cannot be admitted."""


class AlertEvaluationError(BIError):
    """An evaluation failed for a reason with a stable code."""

    def __init__(self, code, message=None):
        super().__init__(message or FAILURE_TEXT.get(code, code))
        self.code = code


def failure_text(code):
    return FAILURE_TEXT.get(code, 'The evaluation failed.')


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
def _map(value, label):
    if not isinstance(value, Mapping):
        raise AlertError(f'{label} must be an object')
    return copy.deepcopy(dict(value))


def _text(value, label, maximum=256):
    if not isinstance(value, str) or not value.strip():
        raise AlertError(f'{label} must not be empty')
    value = value.strip()
    if len(value) > maximum:
        raise AlertError(f'{label} exceeds its length limit')
    return value


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AlertError(f'{label} must be a number')
    if isinstance(value, float) and not math.isfinite(value):
        raise AlertError(f'{label} must be finite')
    return value


def validate_schedule(value):
    """A five-field cron expression in an IANA time zone."""
    item = _map(value, 'schedule')
    expression = _text(item.get('expression'), 'schedule.expression', 120)
    zone_name = _text(item.get('timezone', 'UTC'), 'schedule.timezone', 64)
    if len(expression.split()) != 5:
        raise AlertError('schedule needs a five-field cron expression')
    try:
        zone = ZoneInfo(zone_name)
        croniter(expression, datetime.now(zone)).get_next(datetime)
    except (CroniterBadCronError, ValueError, ZoneInfoNotFoundError,
            KeyError) as exc:
        raise AlertError(
            'schedule expression or time zone is invalid') from exc
    return {'expression': ' '.join(expression.split()), 'timezone': zone_name}


def schedule_interval_seconds(schedule, samples=6):
    """The shortest gap between the next few instants (for rate limits)."""
    zone = ZoneInfo(schedule['timezone'])
    iterator = croniter(schedule['expression'],
                        datetime(2026, 1, 1, tzinfo=zone))
    previous, shortest = None, None
    for _index in range(samples):
        current = iterator.get_next(datetime)
        if previous is not None:
            gap = (current - previous).total_seconds()
            shortest = gap if shortest is None else min(shortest, gap)
        previous = current
    return shortest if shortest is not None else 0


def _operator_value(item, label):
    operator = item.get('operator')
    if operator not in OPERATORS:
        raise AlertError(f'{label}.operator is unsupported')
    value = item.get('value')
    if operator == 'between':
        if not isinstance(value, list) or len(value) != 2:
            raise AlertError(f'{label}.value must be [low, high]')
        low = _number(value[0], f'{label}.value')
        high = _number(value[1], f'{label}.value')
        if low > high:
            raise AlertError(f'{label}.value low must not exceed high')
        value = [low, high]
    else:
        value = _number(value, f'{label}.value')
    return operator, value


def validate_condition(value):
    item = _map(value, 'condition')
    kind = item.get('type')
    if kind == 'results':
        if item.get('state') not in ('exist', 'empty'):
            raise AlertError('condition.state must be exist or empty')
        return {'type': 'results', 'state': item['state']}
    if kind != 'metric':
        raise AlertError('condition.type must be metric or results')
    metric = _map(item.get('metric'), 'condition.metric')
    if metric.get('kind') == 'row_count':
        metric = {'kind': 'row_count'}
    elif metric.get('kind') == 'column':
        aggregate = metric.get('aggregate', 'first')
        if aggregate not in AGGREGATES:
            raise AlertError('condition.metric.aggregate is unsupported')
        metric = {'kind': 'column', 'aggregate': aggregate,
                  'column': _text(metric.get('column'),
                                  'condition.metric.column', 128)}
    else:
        raise AlertError('condition.metric.kind must be row_count or column')
    against = item.get('against', 'constant')
    if against not in AGAINST:
        raise AlertError('condition.against is unsupported')
    operator, bound = _operator_value(item, 'condition')
    return {'type': 'metric', 'metric': metric, 'against': against,
            'operator': operator, 'value': bound}


def validate_recipients(value, owner_id, label):
    if not isinstance(value, list) or len(value) > MAX_RECIPIENTS:
        raise AlertError(
            f'{label} must be an array of at most {MAX_RECIPIENTS}')
    result, seen = [], set()
    for raw in value:
        item = _map(raw, f'{label} entry')
        kind = item.get('type')
        if kind == 'self':
            entry = {'type': 'user', 'user_id': owner_id}
        elif kind == 'user':
            user_id = item.get('user_id')
            if isinstance(user_id, bool) or not isinstance(user_id, int):
                raise AlertError(f'{label} user_id must be an integer')
            entry = {'type': 'user', 'user_id': user_id}
        elif kind == 'email':
            address = _text(item.get('address'), f'{label} address', 320)
            if not _EMAIL.fullmatch(address) or address.count('@') != 1:
                raise AlertError(f'{label} address is invalid')
            entry = {'type': 'email', 'address': address.casefold()}
        else:
            raise AlertError(f'{label} type must be user, self or email')
        key = tuple(sorted(entry.items()))
        if key in seen:
            raise AlertError(f'{label} contains a duplicate')
        seen.add(key)
        result.append(entry)
    return result


def validate_channel(value, owner_id, kind):
    item = _map(value, 'channel')
    channel = item.get('type')
    if channel not in CHANNEL_TYPES:
        raise AlertError('channel type must be in_app, email, s3 or webhook')
    if channel == 'in_app':
        recipients = validate_recipients(
            item.get('recipients', [{'type': 'self'}]), owner_id,
            'channel recipients')
        if not recipients or any(r['type'] != 'user' for r in recipients):
            raise AlertError('in-app notifications go to pgAdmin users')
        return {'type': 'in_app', 'recipients': recipients}
    if channel == 'email':
        recipients = validate_recipients(
            item.get('recipients'), owner_id, 'channel recipients')
        if not recipients:
            raise AlertError('an email channel needs a recipient')
        return {'type': 'email',
                'profile_id': _profile(item.get('profile_id')),
                'recipients': recipients}
    if channel == 's3':
        base = item.get('object_name')
        if not isinstance(base, str) or not _OBJECT_BASE.fullmatch(base):
            raise AlertError(
                'an object-storage channel needs an object name made of '
                'letters, digits, dot, dash and underscore')
        return {'type': 's3', 'profile_id': _profile(item.get('profile_id')),
                'object_name': base}
    return {'type': 'webhook', 'url': _text(item.get('url'), 'webhook url',
                                            1024)}


def _profile(value):
    value = _text(value, 'channel profile_id', 128)
    if not _PROFILE.fullmatch(value):
        raise AlertError('channel profile_id is invalid')
    return value


def validate_alert(value, owner_id):
    """Normalize one alert or subscription definition."""
    item = _map(value, 'alert')
    kind = item.get('kind', 'alert')
    if kind not in KINDS:
        raise AlertError('kind must be alert or subscription')
    resource = _map(item.get('resource'), 'resource')
    rtype = resource.get('type')
    if rtype not in RESOURCE_TYPES:
        raise AlertError('resource.type must be question or dashboard')
    if kind == 'alert' and rtype != 'question':
        raise AlertError('alerts are defined on saved questions')
    rid = resource.get('id')
    if not isinstance(rid, str) or not rid or len(rid) > 36:
        raise AlertError('resource.id must be a string')
    revision = item.get('revision')
    if revision is not None and (isinstance(revision, bool) or not isinstance(
            revision, int) or revision < 1):
        raise AlertError('revision must be a positive integer or null')
    expiry = item.get('expires_in_days', DEFAULT_EXPIRY_DAYS)
    if isinstance(expiry, bool) or not isinstance(expiry, int) or not (
            1 <= expiry <= 365):
        raise AlertError('expires_in_days must be 1 to 365')
    parameters = _map(item.get('parameters', {}), 'parameters')
    filters = _map(item.get('filters', {}), 'filters')
    if len(parameters) > MAX_PARAMETERS or len(filters) > MAX_PARAMETERS:
        raise AlertError('too many parameter or filter values')
    for label, mapping in (('parameters', parameters),
                           ('filters', filters)):
        for key, entry in mapping.items():
            if not isinstance(key, str) or not key or len(key) > 128:
                raise AlertError(f'{label} keys must be short strings')
            if isinstance(entry, float) and not math.isfinite(entry):
                raise AlertError(f'{label} values must be finite')
    if rtype == 'dashboard' and parameters:
        raise AlertError('a dashboard takes filters, not parameters')
    if rtype == 'question' and filters:
        raise AlertError('a question takes parameters, not filters')
    channels_raw = item.get('channels', [])
    if not isinstance(channels_raw, list) or len(channels_raw) > MAX_CHANNELS:
        raise AlertError(f'channels must be an array of at most '
                         f'{MAX_CHANNELS}')
    channels = [validate_channel(c, owner_id, kind) for c in channels_raw]
    if not channels:
        raise AlertError('at least one channel is required')
    result = {
        'kind': kind, 'name': _text(item.get('name'), 'name', 256),
        'resource': {'type': rtype, 'id': rid},
        'revision': revision,
        'schedule': validate_schedule(item.get('schedule')),
        'parameters': parameters, 'filters': filters,
        'channels': channels, 'expires_in_days': expiry,
    }
    if kind == 'alert':
        result['condition'] = validate_condition(item.get('condition'))
        fire_on = item.get('fire_on', 'transition')
        if fire_on not in FIRE_ON:
            raise AlertError('fire_on must be transition or every_evaluation')
        result['fire_on'] = fire_on
        result['format'] = None
    else:
        export = item.get('format')
        needs = any(c['type'] != 'in_app' for c in channels)
        if export is None and needs:
            raise AlertError('a subscription needs an export format')
        if export is not None and export not in EXPORT_FORMATS:
            raise AlertError('format is not a supported export format')
        result['format'] = export
        result['condition'] = None
        result['fire_on'] = None
    return result


def mute_until(now, until=None, duration_minutes=None):
    """The expiry of a mute: an absolute instant or minutes from ``now``.

    A mute always has an expiry (one minute to ninety days).
    """
    if (until is None) == (duration_minutes is None):
        raise AlertError('give either until or duration_minutes')
    if duration_minutes is not None:
        if isinstance(duration_minutes, bool) or not isinstance(
                duration_minutes, int):
            raise AlertError('duration_minutes must be an integer')
        end = now + timedelta(minutes=duration_minutes)
    else:
        try:
            end = datetime.fromisoformat(str(until))
        except ValueError as exc:
            raise AlertError('until must be an ISO 8601 instant') from exc
        if end.tzinfo is not None:
            end = end.astimezone(now.tzinfo or end.tzinfo).replace(
                tzinfo=now.tzinfo)
    if end - now < MIN_MUTE:
        raise AlertError('a mute lasts at least one minute')
    if end - now > MAX_MUTE:
        raise AlertError('a mute lasts at most 90 days')
    return end


# ---------------------------------------------------------------------------
# metrics, conditions and the firing state machine
# ---------------------------------------------------------------------------
def to_number(value):
    """A finite float, or ``None`` for null / non-numeric values."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        number = float(value)
        return number if math.isfinite(number) else None
    return None


def compute_metric(metric, *, columns, rows, row_count):
    """The metric value of one result.  ``None`` means "no value"."""
    if metric['kind'] == 'row_count':
        return float(row_count)
    column = metric['column']
    if column not in columns:
        raise AlertEvaluationError('column_missing')
    values = [row.get(column) for row in rows]
    if metric['aggregate'] == 'first':
        if not values:
            return None
        first = values[0]
        if first is None:
            return None
        number = to_number(first)
        if number is None:
            raise AlertEvaluationError('column_not_numeric')
        return number
    numbers = []
    for entry in values:
        if entry is None:
            continue
        number = to_number(entry)
        if number is None:
            raise AlertEvaluationError('column_not_numeric')
        numbers.append(number)
    if not numbers:
        return None
    aggregate = metric['aggregate']
    if aggregate == 'sum':
        return math.fsum(numbers)
    if aggregate == 'avg':
        return math.fsum(numbers) / len(numbers)
    return min(numbers) if aggregate == 'min' else max(numbers)


def compare(operator, left, bound):
    if operator == 'between':
        return bound[0] <= left <= bound[1]
    if operator == '==':
        return math.isclose(left, bound, rel_tol=1e-9, abs_tol=1e-9)
    if operator == '!=':
        return not math.isclose(left, bound, rel_tol=1e-9, abs_tol=1e-9)
    return {'>': left > bound, '>=': left >= bound, '<': left < bound,
            '<=': left <= bound}[operator]


def evaluate_condition(condition, *, columns, rows, row_count, previous):
    """Evaluate one condition on one result.

    Returns ``{'breached', 'value', 'previous', 'change', 'detail'}``.
    ``breached`` is ``None`` when the condition cannot be decided
    (``detail`` is ``baseline`` for the first evaluation of a change
    condition, ``indeterminate`` for a percent change from zero or a missing
    value); those evaluations never change the breach state.
    """
    if condition['type'] == 'results':
        exists = row_count > 0
        return {'breached': exists if condition['state'] == 'exist'
                else not exists, 'value': float(row_count), 'previous': None,
                'change': None, 'detail': None}
    value = compute_metric(condition['metric'], columns=columns, rows=rows,
                           row_count=row_count)
    outcome = {'breached': None, 'value': value, 'previous': previous,
               'change': None, 'detail': None}
    if condition['against'] == 'constant':
        if value is None:
            outcome['breached'] = False
            outcome['detail'] = 'no_value'
            return outcome
        outcome['breached'] = compare(condition['operator'], value,
                                      condition['value'])
        return outcome
    if previous is None:
        outcome['detail'] = 'baseline'
        return outcome
    if value is None:
        outcome['detail'] = 'indeterminate'
        return outcome
    if condition['against'] == 'previous_change':
        change = value - previous
    elif previous == 0:
        if value != 0:  # a percentage of zero is undefined
            outcome['detail'] = 'indeterminate'
            return outcome
        change = 0.0
    else:
        change = (value - previous) / abs(previous) * 100.0
    outcome['change'] = change
    outcome['breached'] = compare(condition['operator'], change,
                                  condition['value'])
    return outcome


def advance(*, breach_state, pending_notify, breached, fire_on, muted):
    """The edge / level state machine.

    ``breach_state`` is ``unknown`` (never evaluated, or reset), ``ok`` or
    ``breach``.  ``breached`` is ``None`` for an undecided evaluation, which
    leaves the state alone.  In ``transition`` mode a notification is due on
    the way into breach (from ``ok`` or ``unknown``); in ``every_evaluation``
    mode on every breaching evaluation.  A muted alert keeps tracking but
    suppresses the notification; in ``transition`` mode it remembers that one
    is owed (``pending_notify``) and sends it at the first breaching
    evaluation after the mute ends.  A recovery cancels an owed
    notification.
    """
    if breached is None:
        return {'breach_state': breach_state,
                'pending_notify': pending_notify, 'fire': False,
                'suppressed': None, 'reason': None}
    if not breached:
        return {'breach_state': 'ok', 'pending_notify': False,
                'fire': False, 'suppressed': None, 'reason': None}
    if fire_on == 'every_evaluation':
        due, reason = True, 'level'
    elif breach_state != 'breach':
        due, reason = True, 'transition'
    elif pending_notify:
        due, reason = True, 'unmuted'
    else:
        due, reason = False, None
    if due and muted:
        return {'breach_state': 'breach',
                'pending_notify': fire_on == 'transition', 'fire': False,
                'suppressed': 'muted', 'reason': reason}
    return {'breach_state': 'breach', 'pending_notify': False, 'fire': due,
            'suppressed': None, 'reason': reason}


def describe_condition(condition):
    """A short human-readable form of a condition."""
    if condition['type'] == 'results':
        return ('the question returns rows' if condition['state'] == 'exist'
                else 'the question returns no rows')
    metric = condition['metric']
    name = ('row count' if metric['kind'] == 'row_count'
            else f"{metric['aggregate']} of {metric['column']}")
    bound = condition['value']
    shown = (f'{bound[0]} and {bound[1]}' if condition['operator'] ==
             'between' else bound)
    if condition['against'] == 'previous_change':
        name += ' (change since the previous evaluation)'
    elif condition['against'] == 'previous_percent':
        name += ' (percent change since the previous evaluation)'
    return f"{name} {condition['operator']} {shown}"


# ---------------------------------------------------------------------------
# bounded message preview
# ---------------------------------------------------------------------------
def clamp_rows(value, default=5):
    """The configured preview row cap, never above the hard ceiling."""
    if isinstance(value, bool) or not isinstance(value, int):
        value = default
    return max(0, min(value, HARD_MESSAGE_ROWS))


def _cell(value):
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    text = str(value)
    return text if len(text) <= MAX_CELL_CHARS else (
        text[:MAX_CELL_CHARS - 1] + '…')


def build_preview(columns, rows, cap):
    """At most ``cap`` rows (and a bounded number of columns/characters)."""
    cap = clamp_rows(cap)
    shown = list(columns)[:MAX_PREVIEW_COLUMNS]
    return {
        'columns': shown,
        'rows': [{name: _cell(row.get(name)) for name in shown}
                 for row in list(rows)[:cap]],
        'row_count': len(rows), 'shown': min(len(rows), cap),
        'truncated': len(rows) > cap,
    }


def number_text(value):
    if value is None:
        return 'no value'
    if float(value).is_integer() and abs(value) < 1e15:
        return str(int(value))
    return f'{value:.6g}'
