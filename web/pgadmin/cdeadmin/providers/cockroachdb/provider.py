"""CockroachDB 26.1.3 distributed SQL provider."""

import json
import os
import re
import subprocess
import time
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

from pgadmin.cdeadmin.sdk import (
    ActualEnginePilotProvider,
    PilotProfile,
    RelationalClientError,
)
from ..distributed_sql import (
    create_sql_client,
    optional_rows,
    postgresql_catalog,
    postgresql_constraint_details,
    resource,
    sql_administration,
)
from . import (
    indexes as index_sql, objects, sequences, tables, types, views,
)
from .driver import CockroachDBClient
from ..distributed_control_plane import DistributedSQLControlPlane
from pgadmin.cdeadmin.visual_admin import (
    ControlPlaneOperation,
    control_plane_field as cp_field,
)


PROFILE = PilotProfile(
    'org.cdeadmin.cockroachdb', 'cockroachdb-native', 'cockroachdb',
    'CockroachDB', '26.1.3', 'postgresql_wire',
    'distributed-relational', 'cockroachdb-sql', 'CockroachDB SQL',
    'cockroachdb-serializable-retry-native', 'tabular',
    (
        'cluster', 'node', 'locality', 'database', 'schema', 'table',
        'column', 'index', 'constraint', 'sequence', 'view',
        'materialized-view', 'type', 'function', 'procedure', 'trigger',
        'partition', 'user', 'role', 'privilege', 'range',
        'zone-config', 'job', 'schedule', 'changefeed',
    ),
    ('cockroach-sql', 'node-status', 'debug-zip', 'backup-restore'),
    parameter_shape='object-or-array',
    parameter_hint='Named or positional bindings; exact type/value envelopes',
    semantic_sql_dialect={
        'contract_complete': True,
        'language_profile': 'cockroachdb-sql', 'quote_open': '"',
        'quote_close': '"', 'supports_rollup': False,
        'limit_style': 'limit',
        'true_literal': 'TRUE', 'false_literal': 'FALSE',
        'time_operations': (
            'as_of', 'range', 'period_to_date', 'period_comparison',
        ),
        'window_operations': (
            'running_sum', 'moving_sum', 'moving_average', 'lag', 'delta',
            'percent_change', 'rank', 'dense_rank',
        ),
    },
    dialect_contract_id='cockroachdb.dialect.26.1.3.v1',
    dialect_evidence=(
        'cockroachdb-26.1.3-source-and-runtime-inventory',
        'cockroachdb-26.1.3-secure-and-five-node-task-live-execution',
    ),
    dialect_contract_file='cockroachdb_dialect_26_1_3.json',
    metrics_contract_file='cockroachdb_metrics_26_1_3.json',
)


_BASE_ADMINISTRATION = sql_administration('cockroachdb', 'postgresql', (
    'node', 'locality', 'range', 'zone-config', 'job', 'schedule',
    'changefeed', 'materialized-view', 'type', 'partition',
))
_COCKROACH_SUPPORTED = dict(_BASE_ADMINISTRATION.dialect.supported)
for _kind in ('function', 'procedure', 'trigger'):
    _COCKROACH_SUPPORTED[_kind] = frozenset({
        'inspect', 'create', 'drop',
    })
# In place: rename, visibility and comment (providers/cockroachdb/indexes).
_COCKROACH_SUPPORTED['index'] = frozenset({
    'inspect', 'create', 'alter', 'drop', 'scatter',
})
# Enums and composites (providers/cockroachdb/types).
_COCKROACH_SUPPORTED['type'] = frozenset({
    'inspect', 'create', 'alter', 'drop',
})
# alter: rename (and a view's query); providers/cockroachdb/views.
_COCKROACH_SUPPORTED['materialized-view'] = frozenset({
    'inspect', 'create', 'alter', 'rename', 'drop',
})
_COCKROACH_DIALECT = replace(
    _BASE_ADMINISTRATION.dialect,
    supported=_COCKROACH_SUPPORTED,
    not_applicable_concepts=frozenset({
        'domains', 'extensions_and_plugins',
    }),
    concept_resource_kinds={
        # CockroachDB exposes cluster, node, and locality as separate native
        # topology resources.  All three belong to the server/topology
        # concept and must carry independent exact live evidence.
        'servers': ('cluster', 'node', 'locality'),
        'tablespaces_and_filespaces': ('zone-config',),
    },
)


def _choice(field_id, label, values, **options):
    return cp_field(
        field_id, label, 'select', options=[
            {'value': value, 'label': title} for value, title in values
        ], **options
    )


_ZONE_FIELDS = (
    cp_field('num_replicas', 'Replica count', 'number', False,
             minimum=1, maximum=15),
    cp_field('num_voters', 'Voting replica count', 'number', False,
             minimum=1, maximum=15),
    cp_field('range_min_bytes', 'Minimum range bytes', 'number', False,
             minimum=0),
    cp_field('range_max_bytes', 'Maximum range bytes', 'number', False,
             minimum=1),
    cp_field('gc_ttl_seconds', 'GC TTL seconds', 'number', False,
             minimum=1),
    cp_field('constraints', 'Replica constraints', 'json', False,
             default=[], json_type='array'),
    cp_field('voter_constraints', 'Voter constraints', 'json', False,
             default=[], json_type='array'),
    cp_field('lease_preferences', 'Lease preferences', 'json', False,
             default=[], json_type='array'),
)

CONTROL_OPERATIONS = (
    ControlPlaneOperation(
        'node', 'decommission', 'Decommission node', 'destructive',
        'topology_admin', (
            _choice('checks', 'Readiness checks', (
                ('enabled', 'Enabled'), ('strict', 'Strict'),
                ('skip', 'Skip'),
            ), required=False, default='enabled'),
            _choice('wait', 'Wait for', (
                ('all', 'All replicas relocated'),
                ('none', 'Request acceptance only'),
            ), required=False, default='all'),
        ), impact_scope='node', long_running=True
    ),
    ControlPlaneOperation(
        'node', 'recommission', 'Recommission node', 'admin',
        'topology_admin', impact_scope='node', long_running=True
    ),
    ControlPlaneOperation(
        'database', 'configure_zone', 'Configure database placement',
        'admin', 'topology_admin', _ZONE_FIELDS, impact_scope='cluster'
    ),
    ControlPlaneOperation(
        'database', 'reset_zone', 'Reset database placement',
        'admin', 'topology_admin', impact_scope='cluster'
    ),
    ControlPlaneOperation(
        'database', 'set_primary_region', 'Set primary region', 'admin',
        'topology_admin', (
            cp_field('region', 'Cluster region', 'text', True,
                     max_length=256, pattern=r'[A-Za-z0-9_.-]+'),
        ), impact_scope='cluster', long_running=True
    ),
    ControlPlaneOperation(
        'database', 'add_region', 'Add database region', 'admin',
        'topology_admin', (
            cp_field('region', 'Cluster region', 'text', True,
                     max_length=256, pattern=r'[A-Za-z0-9_.-]+'),
        ), impact_scope='cluster', long_running=True
    ),
    ControlPlaneOperation(
        'database', 'drop_region', 'Drop database region', 'destructive',
        'topology_admin', (
            cp_field('region', 'Database region', 'text', True,
                     max_length=256, pattern=r'[A-Za-z0-9_.-]+'),
        ), impact_scope='cluster', long_running=True
    ),
    ControlPlaneOperation(
        'database', 'set_secondary_region', 'Set secondary region', 'admin',
        'topology_admin', (
            cp_field('region', 'Database region', 'text', True,
                     max_length=256, pattern=r'[A-Za-z0-9_.-]+'),
        ), impact_scope='cluster', long_running=True
    ),
    ControlPlaneOperation(
        'database', 'drop_secondary_region', 'Drop secondary region',
        'destructive', 'topology_admin', impact_scope='cluster',
        long_running=True
    ),
    ControlPlaneOperation(
        'database', 'set_survival_goal', 'Set survival goal', 'admin',
        'topology_admin', (
            _choice('goal', 'Failure survival goal', (
                ('zone', 'Zone failure'), ('region', 'Region failure'),
            ), required=True, default='zone'),
        ), impact_scope='cluster', long_running=True
    ),
    ControlPlaneOperation(
        'database', 'set_placement', 'Set replica placement policy',
        'admin', 'topology_admin', (
            _choice('policy', 'Placement policy', (
                ('default', 'Default'), ('restricted', 'Restricted'),
            ), required=True, default='default'),
        ), impact_scope='cluster', long_running=True
    ),
    ControlPlaneOperation(
        'table', 'configure_zone', 'Configure table placement',
        'admin', 'topology_admin', _ZONE_FIELDS, impact_scope='cluster'
    ),
    ControlPlaneOperation(
        'table', 'reset_zone', 'Reset table placement',
        'admin', 'topology_admin', impact_scope='cluster'
    ),
    ControlPlaneOperation(
        'table', 'set_locality', 'Set table locality', 'admin',
        'topology_admin', (
            _choice('locality', 'Table locality', (
                ('global', 'Global'),
                ('regional_by_table', 'Regional by table'),
                ('regional_by_row', 'Regional by row'),
            ), required=True),
            cp_field('region', 'Table home region', 'text', False,
                     max_length=256, pattern=r'[A-Za-z0-9_.-]+',
                     visible_when={
                         'field_id': 'locality',
                         'equals': 'regional_by_table',
                     }),
            cp_field('region_column', 'Region column', 'text', False,
                     max_length=256,
                     pattern=r'[A-Za-z_][A-Za-z0-9_$-]*',
                     visible_when={
                         'field_id': 'locality',
                         'equals': 'regional_by_row',
                     }),
        ), impact_scope='cluster', long_running=True
    ),
    ControlPlaneOperation(
        'materialized-view', 'refresh', 'Refresh materialized view', 'admin',
        'maintenance_admin', impact_scope='cluster', long_running=True
    ),
    ControlPlaneOperation(
        'table', 'scatter', 'Scatter table ranges', 'admin',
        'topology_admin', impact_scope='cluster', long_running=True
    ),
    ControlPlaneOperation(
        'index', 'scatter', 'Scatter index ranges', 'admin',
        'topology_admin', impact_scope='cluster', long_running=True
    ),
    ControlPlaneOperation(
        'range', 'relocate_lease', 'Relocate range lease', 'admin',
        'topology_admin', (
            cp_field('destination_store_id', 'Destination store ID',
                     'number', True, minimum=1),
        ), impact_scope='cluster', long_running=True
    ),
    ControlPlaneOperation(
        'range', 'relocate_voter', 'Relocate voting replica', 'admin',
        'topology_admin', (
            cp_field('source_store_id', 'Source store ID', 'number', True,
                     minimum=1),
            cp_field('destination_store_id', 'Destination store ID',
                     'number', True, minimum=1),
        ), impact_scope='cluster', long_running=True
    ),
    ControlPlaneOperation(
        'range', 'relocate_nonvoter', 'Relocate non-voting replica', 'admin',
        'topology_admin', (
            cp_field('source_store_id', 'Source store ID', 'number', True,
                     minimum=1),
            cp_field('destination_store_id', 'Destination store ID',
                     'number', True, minimum=1),
        ), impact_scope='cluster', long_running=True
    ),
    ControlPlaneOperation(
        'job', 'pause', 'Pause job', 'admin', 'maintenance_admin',
        (cp_field('reason', 'Reason', 'text', False, max_length=1024),),
        impact_scope='cluster', long_running=True, cancellable=False
    ),
    ControlPlaneOperation(
        'job', 'resume', 'Resume job', 'admin', 'maintenance_admin',
        impact_scope='cluster', long_running=True, cancellable=True
    ),
    ControlPlaneOperation(
        'job', 'cancel', 'Cancel job', 'destructive', 'maintenance_admin',
        impact_scope='cluster', long_running=True
    ),
    ControlPlaneOperation(
        'schedule', 'pause', 'Pause schedule', 'admin',
        'maintenance_admin', impact_scope='cluster'
    ),
    ControlPlaneOperation(
        'schedule', 'resume', 'Resume schedule', 'admin',
        'maintenance_admin', impact_scope='cluster'
    ),
    ControlPlaneOperation(
        'schedule', 'drop', 'Drop schedule', 'destructive',
        'maintenance_admin', impact_scope='cluster'
    ),
    ControlPlaneOperation(
        'database', 'backup', 'Back up database', 'admin', 'backup_admin',
        (
            cp_field('destination_uri', 'Approved destination URI', 'text',
                     True, max_length=4096, sensitive=True),
            _choice('revision_history', 'Revision history', (
                ('default', 'Default'),
                ('with_revision_history', 'Include revision history'),
            ), required=False, default='default'),
        ),
        impact_scope='cluster', long_running=True, cancellable=True
    ),
    ControlPlaneOperation(
        'cluster', 'restore_database', 'Restore database', 'destructive',
        'restore_admin', (
            cp_field('source_uri', 'Approved backup URI', 'text', True,
                     max_length=4096, sensitive=True),
            cp_field('database_name', 'Database name', 'text', True,
                     max_length=256,
                     pattern=r'[A-Za-z_][A-Za-z0-9_$-]*'),
            cp_field('new_database_name', 'Restore as database', 'text',
                     False, max_length=256,
                     pattern=r'[A-Za-z_][A-Za-z0-9_$-]*'),
        ), impact_scope='cluster', long_running=True, cancellable=True
    ),
    ControlPlaneOperation(
        'table', 'create_changefeed', 'Create table changefeed', 'admin',
        'replication_admin', (
            cp_field('sink_uri', 'Approved sink URI', 'text', True,
                     max_length=8192, sensitive=True),
            _choice('initial_scan', 'Initial scan', (
                ('yes', 'Yes'), ('no', 'No'), ('only', 'Only'),
            ), required=False, default='yes'),
            _choice('format', 'Message format', (
                ('json', 'JSON'), ('csv', 'CSV'),
            ), required=False, default='json'),
            _choice('envelope', 'Envelope', (
                ('wrapped', 'Wrapped'), ('row', 'Row'),
                ('key_only', 'Key only'),
            ), required=False, default='wrapped'),
            cp_field('resolved_interval', 'Resolved timestamp interval',
                     'text', False, max_length=64,
                     pattern=r'[0-9]+(?:ms|s|m|h)'),
        ), impact_scope='cluster', long_running=True, cancellable=True
    ),
    ControlPlaneOperation(
        'changefeed', 'pause', 'Pause changefeed', 'admin',
        'replication_admin', impact_scope='cluster', long_running=True
    ),
    ControlPlaneOperation(
        'changefeed', 'resume', 'Resume changefeed', 'admin',
        'replication_admin', impact_scope='cluster', long_running=True,
        cancellable=True
    ),
    ControlPlaneOperation(
        'changefeed', 'cancel', 'Cancel changefeed', 'destructive',
        'replication_admin', impact_scope='cluster', long_running=True
    ),
    ControlPlaneOperation(
        'changefeed', 'add_table', 'Add table to changefeed', 'admin',
        'replication_admin', (
            cp_field('table_name', 'Qualified table name', 'text', True,
                     max_length=768),
            _choice('initial_scan', 'Initial scan', (
                ('yes', 'Yes'), ('no', 'No'), ('only', 'Only'),
            ), required=False, default='yes'),
        ), impact_scope='cluster', long_running=True
    ),
    ControlPlaneOperation(
        'changefeed', 'drop_table', 'Remove table from changefeed',
        'destructive', 'replication_admin', (
            cp_field('table_name', 'Qualified table name', 'text', True,
                     max_length=768),
        ), impact_scope='cluster', long_running=True
    ),
    ControlPlaneOperation(
        'changefeed', 'set_sink', 'Change changefeed sink', 'admin',
        'replication_admin', (
            cp_field('sink_uri', 'Approved sink URI', 'text', True,
                     max_length=8192, sensitive=True),
        ), impact_scope='cluster', long_running=True
    ),
)


def _path(request):
    target = request.get('target_resource')
    if not isinstance(target, dict):
        raise RelationalClientError('CockroachDB target is required')
    parts = target.get('display_path') or [target.get('display_name')]
    if not isinstance(parts, list) or not parts:
        raise RelationalClientError('CockroachDB target path is invalid')
    return [str(item) for item in parts]


def _quote(value):
    if not isinstance(value, str) or not value or '\x00' in value:
        raise RelationalClientError('CockroachDB identifier is invalid')
    return '"' + value.replace('"', '""') + '"'


def _target_id(request):
    value = _path(request)[-1]
    try:
        result = int(value)
        if result <= 0:
            raise ValueError
        return result
    except (TypeError, ValueError):
        raise RelationalClientError(
            'CockroachDB operation requires a numeric native identifier'
        ) from None


def _positive_integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RelationalClientError(
            f'CockroachDB {label} must be a positive integer')
    return value


def _impact(request, **extra):
    return {
        'scope': 'cluster',
        'target_resource_id': request.get('target_resource', {}).get(
            'resource_id'
        ),
        'availability_risk': extra.pop('availability_risk', 'low'),
        'data_movement_possible': extra.pop(
            'data_movement_possible', False
        ),
        **extra,
    }


def _allowlisted_uri(request, field_id, allowlist_key=None):
    value = request['draft'].get(field_id)
    if not isinstance(value, str) or not value.strip():
        raise RelationalClientError('CockroachDB backup URI is required')
    value = value.strip()
    scheme = urlsplit(value).scheme.lower()
    backup_schemes = {
        'nodelocal', 'userfile', 'external', 's3', 'gs', 'azure', 'http',
        'https',
    }
    changefeed_schemes = {
        'azure', 'azure-kafka', 'confluent-cloud', 'external', 'gcpubsub',
        'gs', 'http', 'https', 'kafka', 'nodelocal', 'null', 'pulsar', 's3',
        'webhook-http', 'webhook-https',
    }
    admitted = changefeed_schemes if field_id == 'sink_uri' else (
        backup_schemes)
    if scheme not in admitted:
        raise RelationalClientError(
            'CockroachDB provider URI scheme is not admitted'
        )
    route = request.get('_provider_route') or {}
    prefixes = route.get(
        allowlist_key or 'backup_destination_allowlist')
    if isinstance(prefixes, str):
        prefixes = [item.strip() for item in prefixes.split(',')]
    if not isinstance(prefixes, list) or not prefixes or not any(
        isinstance(prefix, str) and value.startswith(prefix)
        for prefix in prefixes
    ):
        raise RelationalClientError(
            'CockroachDB backup URI is outside the endpoint allowlist'
        )
    return value


def _qualified_identifier(value, label='qualified identifier'):
    if not isinstance(value, str):
        raise RelationalClientError(f'CockroachDB {label} is invalid')
    parts = value.split('.')
    if not 1 <= len(parts) <= 3 or any(
            not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_$-]{0,255}', part)
            for part in parts):
        raise RelationalClientError(f'CockroachDB {label} is invalid')
    return '.'.join(_quote(part) for part in parts)


def _region(draft):
    value = draft.get('region')
    if not isinstance(value, str) or not re.fullmatch(
            r'[A-Za-z0-9_.-]{1,256}', value):
        raise RelationalClientError('CockroachDB region is invalid')
    return _quote(value)


def _changefeed_options(draft):
    options = []
    parameters = []
    for name, admitted, default in (
        ('initial_scan', {'yes', 'no', 'only'}, 'yes'),
        ('format', {'json', 'csv'}, 'json'),
        ('envelope', {'wrapped', 'row', 'key_only'}, 'wrapped'),
    ):
        value = draft.get(name, default)
        if value not in admitted:
            raise RelationalClientError(
                f'CockroachDB changefeed {name} is invalid')
        options.append(f'{name} = %s')
        parameters.append(value)
    resolved = draft.get('resolved_interval')
    if resolved:
        if not isinstance(resolved, str) or not re.fullmatch(
                r'[0-9]+(?:ms|s|m|h)', resolved):
            raise RelationalClientError(
                'CockroachDB resolved timestamp interval is invalid')
        options.append('resolved = %s')
        parameters.append(resolved)
    return options, parameters


def _node_action(request):
    operation = request['operation_id']
    node_id = str(_target_id(request))
    arguments = ['node', operation]
    if operation == 'decommission':
        draft = request.get('draft') or {}
        checks = draft.get('checks', 'enabled')
        wait = draft.get('wait', 'all')
        if checks not in {'enabled', 'strict', 'skip'} or wait not in {
                'all', 'none'}:
            raise RelationalClientError(
                'CockroachDB decommission options are invalid')
        arguments.extend([f'--checks={checks}', f'--wait={wait}'])
    arguments.append(node_id)
    return {
        'provider_action': {'arguments': arguments},
        'action_preview': {
            'tool': 'cockroach', 'verb': f'node {operation}',
            'argument_count': len(arguments) - 2,
            'provider_constructed': True,
        },
        'impact': _impact(
            request, availability_risk='high',
            data_movement_possible=operation == 'decommission',
        ),
        'provider_operation_observation': {
            'job_backed': False,
            'finality_interpreted_by_common_code': False,
        },
    }


def _compile_control_plane(request):
    kind = request['resource_kind']
    operation = request['operation_id']
    draft = request.get('draft') or {}
    source = None
    parameters = ()
    statements = []
    impact = _impact(request)
    if kind == 'node' and operation in {'decommission', 'recommission'}:
        return _node_action(request)
    if operation in {'configure_zone', 'reset_zone'}:
        target = '.'.join(_quote(part) for part in _path(request))
        prefix = f'ALTER {kind.upper()} {target} CONFIGURE ZONE'
        if operation == 'reset_zone':
            source = prefix + ' DISCARD'
        else:
            assignments = []
            values = []
            names = (
                ('num_replicas', 'num_replicas'),
                ('num_voters', 'num_voters'),
                ('range_min_bytes', 'range_min_bytes'),
                ('range_max_bytes', 'range_max_bytes'),
                ('gc_ttl_seconds', 'gc.ttlseconds'),
                ('constraints', 'constraints'),
                ('voter_constraints', 'voter_constraints'),
                ('lease_preferences', 'lease_preferences'),
            )
            for field_id, sql_name in names:
                value = draft.get(field_id)
                if value in (None, [], ''):
                    continue
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, separators=(',', ':'))
                assignments.append(f'{sql_name} = %s')
                values.append(value)
            if not assignments:
                raise RelationalClientError(
                    'CockroachDB zone configuration has no changes'
                )
            source = prefix + ' USING ' + ', '.join(assignments)
            parameters = tuple(values)
            impact = _impact(
                request, availability_risk='medium',
                data_movement_possible=True
            )
    elif kind == 'database' and operation in {
            'set_primary_region', 'add_region', 'drop_region',
            'set_secondary_region', 'drop_secondary_region',
            'set_survival_goal', 'set_placement'}:
        database = _quote(_path(request)[-1])
        source = f'ALTER DATABASE {database} '
        if operation == 'set_primary_region':
            source += 'SET PRIMARY REGION ' + _region(draft)
        elif operation == 'add_region':
            source += 'ADD REGION ' + _region(draft)
        elif operation == 'drop_region':
            source += 'DROP REGION ' + _region(draft)
        elif operation == 'set_secondary_region':
            source += 'SET SECONDARY REGION ' + _region(draft)
        elif operation == 'drop_secondary_region':
            source += 'DROP SECONDARY REGION'
        elif operation == 'set_survival_goal':
            goal = draft.get('goal')
            if goal not in {'zone', 'region'}:
                raise RelationalClientError(
                    'CockroachDB survival goal is invalid')
            source += f'SURVIVE {goal.upper()} FAILURE'
        else:
            policy = draft.get('policy')
            if policy not in {'default', 'restricted'}:
                raise RelationalClientError(
                    'CockroachDB placement policy is invalid')
            statements.append({
                'source': (
                    'SET enable_multiregion_placement_policy = true'
                ),
                'parameters': (),
            })
            source += f'PLACEMENT {policy.upper()}'
        impact = _impact(
            request, availability_risk='medium',
            data_movement_possible=True,
        )
    elif kind == 'table' and operation == 'set_locality':
        table = '.'.join(_quote(part) for part in _path(request))
        locality = draft.get('locality')
        source = f'ALTER TABLE {table} SET LOCALITY '
        if locality == 'global':
            source += 'GLOBAL'
        elif locality == 'regional_by_table':
            source += 'REGIONAL BY TABLE'
            if draft.get('region'):
                source += ' IN ' + _region(draft)
        elif locality == 'regional_by_row':
            source += 'REGIONAL BY ROW'
            column = draft.get('region_column')
            if column:
                if not re.fullmatch(
                        r'[A-Za-z_][A-Za-z0-9_$-]{0,255}', column):
                    raise RelationalClientError(
                        'CockroachDB region column is invalid')
                source += ' AS ' + _quote(column)
        else:
            raise RelationalClientError(
                'CockroachDB table locality is invalid')
        impact = _impact(
            request, availability_risk='medium',
            data_movement_possible=True,
        )
    elif kind == 'materialized-view' and operation == 'refresh':
        target = '.'.join(_quote(part) for part in _path(request))
        source = f'REFRESH MATERIALIZED VIEW {target}'
        impact = _impact(request, availability_risk='low')
    elif kind in {'table', 'index'} and operation == 'scatter':
        path = _path(request)
        if kind == 'index':
            if len(path) < 2:
                raise RelationalClientError(
                    'CockroachDB index path is invalid')
            target = (
                '.'.join(_quote(part) for part in path[:-1]) + '@' +
                _quote(path[-1])
            )
        else:
            target = '.'.join(_quote(part) for part in path)
        source = f'ALTER {kind.upper()} {target} SCATTER'
        impact = _impact(
            request, availability_risk='low', data_movement_possible=True)
    elif kind == 'range' and operation in {
            'relocate_lease', 'relocate_voter', 'relocate_nonvoter'}:
        range_id = _target_id(request)
        destination = _positive_integer(
            draft.get('destination_store_id'), 'destination store ID')
        if operation == 'relocate_lease':
            source = (
                f'ALTER RANGE {range_id} RELOCATE LEASE TO {destination}'
            )
        else:
            source_store = _positive_integer(
                draft.get('source_store_id'), 'source store ID')
            subject = (
                'VOTERS' if operation == 'relocate_voter'
                else 'NONVOTERS'
            )
            source = (
                f'ALTER RANGE {range_id} RELOCATE {subject} '
                f'FROM {source_store} TO {destination}'
            )
        impact = _impact(
            request, availability_risk='medium',
            data_movement_possible=True)
    elif kind == 'job' and operation in {'pause', 'resume', 'cancel'}:
        source = f'{operation.upper()} JOB %s'
        parameters = (_target_id(request),)
        reason = draft.get('reason')
        if reason and operation == 'pause':
            source += ' WITH REASON = %s'
            parameters += (reason,)
    elif kind == 'schedule' and operation in {'pause', 'resume', 'drop'}:
        source = f'{operation.upper()} SCHEDULE %s'
        parameters = (_target_id(request),)
    elif kind == 'database' and operation == 'backup':
        database = _quote(_path(request)[-1])
        source = f'BACKUP DATABASE {database} INTO %s'
        parameters = (_allowlisted_uri(request, 'destination_uri'),)
        if draft.get('revision_history') == 'with_revision_history':
            source += ' WITH revision_history'
        impact = _impact(request, availability_risk='low')
    elif kind == 'cluster' and operation == 'restore_database':
        database = _quote(draft['database_name'])
        source = f'RESTORE DATABASE {database} FROM LATEST IN %s'
        parameters = (_allowlisted_uri(request, 'source_uri'),)
        if draft.get('new_database_name'):
            source += ' WITH new_db_name = %s'
            parameters += (draft['new_database_name'],)
        impact = _impact(
            request, availability_risk='high',
            data_movement_possible=True
        )
    elif kind == 'table' and operation == 'create_changefeed':
        noun = 'TABLE'
        target = '.'.join(_quote(part) for part in _path(request))
        source = f'CREATE CHANGEFEED FOR {noun} {target} INTO %s'
        parameters = (
            _allowlisted_uri(
                request, 'sink_uri', 'changefeed_sink_allowlist'),
        )
        options, values = _changefeed_options(draft)
        source += ' WITH ' + ', '.join(options)
        parameters += tuple(values)
        impact = _impact(request, availability_risk='medium')
    elif kind == 'changefeed' and operation in {
            'pause', 'resume', 'cancel'}:
        source = f'{operation.upper()} JOB %s'
        parameters = (_target_id(request),)
    elif kind == 'changefeed' and operation in {
            'add_table', 'drop_table'}:
        verb = 'ADD' if operation == 'add_table' else 'DROP'
        table = _qualified_identifier(draft.get('table_name'), 'table name')
        source = f'ALTER CHANGEFEED %s {verb} TABLE {table}'
        parameters = (_target_id(request),)
        if operation == 'add_table':
            initial_scan = draft.get('initial_scan', 'yes')
            if initial_scan not in {'yes', 'no', 'only'}:
                raise RelationalClientError(
                    'CockroachDB changefeed initial scan is invalid')
            # CockroachDB 26.1 cannot infer the placeholder type in this
            # ALTER CHANGEFEED option. The value is drawn from the strict
            # provider allowlist above, so emitting the literal is safe.
            source += f" WITH initial_scan = '{initial_scan}'"
    elif kind == 'changefeed' and operation == 'set_sink':
        source = 'ALTER CHANGEFEED %s SET sink = %s'
        parameters = (
            _target_id(request),
            _allowlisted_uri(
                request, 'sink_uri', 'changefeed_sink_allowlist'),
        )
    if source is None:
        raise RelationalClientError(
            'CockroachDB control-plane operation is unavailable'
        )
    statements.append({'source': source, 'parameters': parameters})
    return {
        'statements': statements,
        'impact': impact,
        'provider_operation_observation': {
            'job_backed': kind in {
                'job', 'schedule', 'changefeed'
            } or operation in {
                'backup', 'restore_database', 'create_changefeed',
            },
            'finality_interpreted_by_common_code': False,
        },
    }


def _private_parts(request):
    plan = request.get('plan')
    payload = request.get('provider_payload')
    if not isinstance(plan, dict) or not isinstance(payload, dict):
        raise RelationalClientError(
            'CockroachDB provider operation handle is invalid'
        )
    route = payload.get('route')
    if not isinstance(route, dict):
        raise RelationalClientError(
            'CockroachDB provider operation route is unavailable'
        )
    return plan, route


def _trusted_file(route, key, label, executable=False):
    value = route.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RelationalClientError(f'CockroachDB {label} is required')
    path = Path(value).expanduser().resolve()
    if not path.is_file() or (executable and not os.access(path, os.X_OK)):
        raise RelationalClientError(f'CockroachDB {label} is unavailable')
    return str(path)


def _cli_address(route):
    host = route.get('host')
    port = route.get('port', 26257)
    if not isinstance(host, str) or not re.fullmatch(
            r'[A-Za-z0-9_.:\-\[\]]{1,512}', host):
        raise RelationalClientError('CockroachDB CLI host is invalid')
    if isinstance(port, bool) or not isinstance(port, int) or not (
            1 <= port <= 65535):
        raise RelationalClientError('CockroachDB CLI port is invalid')
    if ':' in host and not host.startswith('['):
        host = f'[{host}]'
    return f'{host}:{port}'


def _run_node(route, arguments, timeout=None):
    if not isinstance(arguments, list) or len(arguments) < 3 or len(
            arguments) > 32 or any(
                not isinstance(value, str) or not value or '\x00' in value or
                len(value) > 4096 for value in arguments):
        raise RelationalClientError(
            'CockroachDB control arguments are invalid')
    timeout_value = route.get('cockroach_cli_timeout_seconds', 120)
    if timeout is not None:
        timeout_value = timeout
    if isinstance(timeout_value, bool) or not isinstance(
            timeout_value, int) or not 1 <= timeout_value <= 3600:
        raise RelationalClientError('CockroachDB CLI timeout is invalid')
    flags = [f'--host={_cli_address(route)}', '--format=json']
    insecure = route.get('cockroach_insecure', False)
    if not isinstance(insecure, bool):
        raise RelationalClientError(
            'CockroachDB insecure transport option is invalid')
    if insecure:
        flags.append('--insecure')
    else:
        certs = route.get('cockroach_certs_dir')
        if not isinstance(certs, str) or not certs.strip():
            raise RelationalClientError(
                'CockroachDB certificate directory is required')
        cert_path = Path(certs).expanduser().resolve()
        if not cert_path.is_dir():
            raise RelationalClientError(
                'CockroachDB certificate directory is unavailable')
        flags.append(f'--certs-dir={cert_path}')
    cluster_name = route.get('cockroach_cluster_name')
    if cluster_name:
        if not isinstance(cluster_name, str) or not re.fullmatch(
                r'[A-Za-z0-9_.-]{1,256}', cluster_name):
            raise RelationalClientError(
                'CockroachDB cluster name is invalid')
        flags.append(f'--cluster-name={cluster_name}')
    command = [
        _trusted_file(
            route, 'cockroach_path', 'cockroach executable', True),
        *arguments[:-1], *flags, arguments[-1],
    ]
    try:
        result = subprocess.run(
            command, check=False, capture_output=True, text=True,
            timeout=timeout_value,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RelationalClientError(
            'CockroachDB control request failed to return') from exc
    output = (result.stdout or '') + (result.stderr or '')
    if len(output.encode('utf-8')) > 8 * 1024 * 1024:
        raise RelationalClientError(
            'CockroachDB control response exceeds size limit')
    if result.returncode != 0:
        raise RelationalClientError(
            'CockroachDB control request was rejected')
    return {
        'exit_code': 0,
        'stdout': result.stdout or '',
        'stderr': result.stderr or '',
        'provider_response_observed': True,
        'provider_finality_authority': True,
        'automatic_mutation_retry': False,
    }


def _execute_control_action(_client, request):
    payload = request.get('provider_payload') or {}
    action = payload.get('compiled', {}).get('provider_action', {})
    return {
        'accepted': True,
        'provider_response': _run_node(
            payload.get('route') or {}, action.get('arguments')),
        'provider_finality_authority': True,
        'automatic_mutation_retry': False,
    }


def _node_observation(route, node_id):
    response = _run_node(
        route, ['node', 'status', '--decommission', str(node_id)],
        timeout=30,
    )
    document = None
    try:
        document = json.loads(response.get('stdout') or '')
    except (TypeError, ValueError) as exc:
        raise RelationalClientError(
            'CockroachDB node status response is invalid') from exc
    return {
        'provider_observation': response,
        'document': document,
        'provider_observation_only': True,
        'provider_finality_authority': True,
    }


def _node_membership(document, node_id):
    rows = document if isinstance(document, list) else [document]
    for row in rows:
        if not isinstance(row, dict):
            continue
        value = row.get('id')
        try:
            matches = int(value) == int(node_id)
        except (TypeError, ValueError):
            matches = False
        if matches and isinstance(row.get('membership'), str):
            return row['membership'].lower()
    return None


def _result_job_id(request):
    result = request.get('provider_result')
    if isinstance(result, dict):
        for statement in result.get('statement_results') or []:
            for row in statement.get('rows') or []:
                if isinstance(row, (list, tuple)) and row:
                    try:
                        return int(row[0])
                    except (TypeError, ValueError):
                        continue
    plan = request.get('plan') or {}
    target = plan.get('target_resource') or {}
    path = target.get('display_path') or [target.get('display_name')]
    try:
        return int(path[-1])
    except (IndexError, TypeError, ValueError):
        raise RelationalClientError(
            'CockroachDB provider job identifier is unavailable'
        ) from None


def _query_once(client, route, source, parameters=()):
    connection = client._connect({'route': route})
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(source, parameters)
        description = getattr(cursor, 'description', None)
        columns = [item[0] for item in description or []]
        rows = list(cursor.fetchall()) if description else []
        return {
            'columns': columns,
            'rows': rows,
            'provider_observation_only': True,
            'finality_interpreted_by_common_code': False,
        }
    finally:
        if cursor is not None:
            client._safe_close(cursor)
        client._forget_and_close(connection)


def _mutate_once(client, route, source, parameters=()):
    connection = client._connect({'route': route})
    cursor = None
    commit_requested = False
    try:
        cursor = connection.cursor()
        cursor.execute(source, parameters)
        commit = getattr(connection, 'commit', None)
        if callable(commit):
            commit_requested = True
            commit()
        return {
            'request_accepted_by_driver': True,
            'commit_requested': commit_requested,
            'provider_observation_only': True,
            'finality_interpreted_by_common_code': False,
        }
    except Exception as exc:
        rollback = getattr(connection, 'rollback', None)
        if callable(rollback):
            try:
                rollback()
            except Exception:
                pass
        if isinstance(exc, RelationalClientError):
            raise
        raise RelationalClientError(
            'CockroachDB control request failed '
            f'({type(exc).__name__})'
        ) from None
    finally:
        if cursor is not None:
            client._safe_close(cursor)
        client._forget_and_close(connection)


def _inspect_control_plane(client, request):
    plan, route = _private_parts(request)
    kind = plan['resource_kind']
    operation = plan['operation_id']
    if kind == 'node':
        return _node_observation(route, _result_job_id(request))
    if kind == 'changefeed' or operation == 'create_changefeed':
        job_id = _result_job_id(request)
        return _query_once(
            client, route,
            'SELECT job_id, status, error, sink_uri, full_table_names '
            'FROM [SHOW CHANGEFEED JOBS] WHERE job_id = %s',
            (job_id,),
        )
    if kind == 'job' or operation in {'backup', 'restore_database'}:
        job_id = _result_job_id(request)
        return _query_once(
            client, route,
            'SELECT job_id, status, fraction_completed, error, '
            'created, finished FROM [SHOW JOBS] WHERE job_id = %s',
            (job_id,),
        )
    if kind == 'schedule':
        return _query_once(
            client, route,
            'SELECT id, label, schedule_status, next_run '
            'FROM [SHOW SCHEDULES] WHERE id = %s',
            (_result_job_id(request),),
        )
    if operation in {'configure_zone', 'reset_zone'}:
        target = plan.get('target_resource') or {}
        path = target.get('display_path') or [target.get('display_name')]
        if operation == 'reset_zone':
            return _query_once(
                client, route,
                'SELECT target, raw_config_sql FROM '
                '[SHOW ALL ZONE CONFIGURATIONS] WHERE target = %s',
                (kind.upper() + ' ' + '.'.join(str(item) for item in path),),
            )
        name = '.'.join(_quote(str(item)) for item in path)
        return _query_once(
            client, route,
            f'SHOW ZONE CONFIGURATION FOR {kind.upper()} {name}',
        )
    if kind == 'database' and operation in {
            'set_primary_region', 'add_region', 'drop_region',
            'set_secondary_region', 'drop_secondary_region',
            'set_survival_goal', 'set_placement'}:
        name = _quote(_path(plan)[-1])
        observation = _query_once(
            client, route,
            'SELECT database_name, primary_region, secondary_region, '
            'regions, survival_goal FROM [SHOW DATABASES] '
            'WHERE database_name = %s', (_path(plan)[-1],),
        )
        created = _query_once(
            client, route, f'SHOW CREATE DATABASE {name}')
        observation['create_rows'] = created['rows']
        return observation
    if kind in {'table', 'index'} and operation == 'scatter':
        return _query_once(client, route, 'SELECT 1')
    if kind == 'table' and operation == 'set_locality':
        name = '.'.join(_quote(part) for part in _path(plan))
        return _query_once(client, route, f'SHOW CREATE TABLE {name}')
    if kind == 'materialized-view' and operation == 'refresh':
        name = '.'.join(_quote(part) for part in _path(plan))
        return _query_once(
            client, route, f'SHOW CREATE VIEW {name}')
    if kind == 'range':
        database = route.get('database')
        if not isinstance(database, str) or not re.fullmatch(
                r'[A-Za-z_][A-Za-z0-9_$-]{0,255}', database):
            raise RelationalClientError(
                'CockroachDB range observation requires a database')
        return _query_once(
            client, route,
            'SELECT range_id, lease_holder, voting_replicas, '
            'non_voting_replicas FROM [SHOW RANGES FROM DATABASE ' +
            _quote(database) + ' WITH DETAILS] WHERE range_id = %s',
            (_target_id(plan),),
        )
    raise RelationalClientError(
        'CockroachDB operation observation is unavailable'
    )


def _cancel_control_plane(client, request):
    plan, route = _private_parts(request)
    if not plan.get('cancellable'):
        raise RelationalClientError(
            'CockroachDB operation is not declared cancellable'
        )
    return _mutate_once(
        client, route, 'CANCEL JOB %s', (_result_job_id(request),)
    )


def _wait_for_status(client, request, admitted, timeout=90):
    deadline = time.monotonic() + timeout
    observation = None
    while time.monotonic() < deadline:
        observation = _inspect_control_plane(client, request)
        rows = observation.get('rows') or []
        if rows and str(rows[0][1]).lower() in admitted:
            return observation
        time.sleep(0.25)
    return observation or _inspect_control_plane(client, request)


def _post_validate_control_plane(client, request):
    plan, _route = _private_parts(request)
    operation = plan['operation_id']
    kind = plan['resource_kind']
    if kind in {'job', 'changefeed'} or operation in {
            'backup', 'restore_database', 'create_changefeed'}:
        if operation == 'pause':
            statuses = {'paused'}
        elif operation == 'resume' or operation == 'create_changefeed':
            statuses = {'running', 'pending'}
        elif operation == 'cancel':
            statuses = {'canceled'}
        elif operation in {'backup', 'restore_database'}:
            statuses = {'succeeded'}
        else:
            statuses = {'paused'}
        observation = _wait_for_status(client, request, statuses)
    else:
        observation = _inspect_control_plane(client, request)
    rows = observation.get('rows') or []
    draft = plan.get('draft') or {}
    confirmed = False
    if kind == 'node':
        membership = _node_membership(
            observation.get('document'), _result_job_id(request))
        expected = (
            {'decommissioning', 'decommissioned'}
            if operation == 'decommission' else {'active'}
        )
        confirmed = membership in expected
    elif operation == 'pause':
        confirmed = bool(rows) and str(rows[0][2 if (
            kind == 'schedule'
        ) else 1]).lower() == 'paused'
    elif operation == 'resume':
        confirmed = bool(rows) and str(rows[0][2 if (
            kind == 'schedule'
        ) else 1]).lower() in {'active', 'running', 'pending'}
    elif operation in {'cancel', 'backup', 'restore_database'}:
        expected = 'canceled' if operation == 'cancel' else 'succeeded'
        confirmed = bool(rows) and str(rows[0][1]).lower() == expected
    elif operation == 'create_changefeed':
        confirmed = bool(rows) and str(rows[0][1]).lower() in {
            'running', 'pending'
        }
    elif operation == 'drop' and kind == 'schedule':
        confirmed = not rows
    elif operation == 'configure_zone':
        raw = str(rows[0][1]) if rows else ''
        configured = [
            ('num_replicas', 'num_replicas'),
            ('num_voters', 'num_voters'),
            ('range_min_bytes', 'range_min_bytes'),
            ('range_max_bytes', 'range_max_bytes'),
            ('gc_ttl_seconds', 'gc.ttlseconds'),
            ('constraints', 'constraints'),
            ('voter_constraints', 'voter_constraints'),
            ('lease_preferences', 'lease_preferences'),
        ]
        confirmed = bool(rows) and all(
            value in (None, [], '') or re.search(
                rf'(?m)^\s*{re.escape(sql_name)}\s*=', raw)
            for value, sql_name in (
                (draft.get(field_id), sql_name)
                for field_id, sql_name in configured
            )
        )
    elif operation == 'reset_zone':
        confirmed = not rows
    elif kind == 'database' and operation in {
            'set_primary_region', 'add_region', 'drop_region',
            'set_secondary_region', 'drop_secondary_region',
            'set_survival_goal', 'set_placement'}:
        row = rows[0] if rows else None
        regions = set(row[3] or []) if row else set()
        region = draft.get('region')
        if operation == 'set_primary_region':
            confirmed = bool(row) and row[1] == region
        elif operation == 'add_region':
            confirmed = bool(row) and region in regions
        elif operation == 'drop_region':
            confirmed = bool(row) and region not in regions
        elif operation == 'set_secondary_region':
            confirmed = bool(row) and row[2] == region
        elif operation == 'drop_secondary_region':
            confirmed = bool(row) and row[2] in {None, ''}
        elif operation == 'set_survival_goal':
            confirmed = bool(row) and str(row[4]).lower() == draft.get('goal')
        else:
            create_rows = observation.get('create_rows') or []
            statement = str(create_rows[0][1]).upper() if create_rows else ''
            policy = str(draft.get('policy')).upper()
            confirmed = (
                bool(statement) and (
                    f'PLACEMENT {policy}' in statement
                    if policy == 'RESTRICTED'
                    else 'PLACEMENT RESTRICTED' not in statement
                )
            )
    elif kind == 'table' and operation == 'set_locality':
        statement = str(rows[0][1]).upper() if rows else ''
        locality = draft.get('locality')
        expected = {
            'global': 'LOCALITY GLOBAL',
            'regional_by_table': 'LOCALITY REGIONAL BY TABLE',
            'regional_by_row': 'LOCALITY REGIONAL BY ROW',
        }.get(locality, '')
        confirmed = bool(expected) and expected in statement
        if confirmed and locality == 'regional_by_table' and draft.get(
                'region'):
            confirmed = f'IN "{str(draft["region"]).upper()}"' in statement
        if confirmed and locality == 'regional_by_row' and draft.get(
                'region_column'):
            region_column = str(draft['region_column']).upper()
            confirmed = f'AS {region_column}' in statement
    elif kind == 'materialized-view' and operation == 'refresh':
        confirmed = bool(rows) and 'CREATE MATERIALIZED VIEW' in str(
            rows[0][1]).upper()
    elif operation == 'scatter' and kind in {'table', 'index'}:
        confirmed = rows == [(1,)] or rows == [[1]]
    elif kind == 'range' and rows:
        destination = draft.get('destination_store_id')
        if operation == 'relocate_lease':
            confirmed = rows[0][1] == destination
        elif operation == 'relocate_voter':
            confirmed = destination in set(rows[0][2] or [])
        elif operation == 'relocate_nonvoter':
            confirmed = destination in set(rows[0][3] or [])
    elif kind == 'changefeed' and operation in {
            'add_table', 'drop_table', 'set_sink'} and rows:
        if operation == 'set_sink':
            payload = request.get('provider_payload') or {}
            statements = (payload.get('compiled') or {}).get(
                'statements') or []
            parameters = (
                statements[0].get('parameters') or ()
                if statements else ()
            )
            expected_sink = parameters[1] if len(parameters) > 1 else None
            confirmed = str(rows[0][3]) == expected_sink
        else:
            tables = set(rows[0][4] or [])
            table = draft.get('table_name')
            confirmed = (
                table in tables if operation == 'add_table'
                else table not in tables
            )
    return {
        'confirmed': confirmed,
        'operation_id': operation,
        'observation': observation,
        'provider_finality_authority': True,
    }


# Kinds whose create and alter are CockroachDB's own modules.
_EDITED_KINDS = frozenset({'table', 'index', 'type', 'view',
                           'materialized-view', 'sequence'})


class CockroachDBAdministration(DistributedSQLControlPlane):
    """CockroachDB-specific relational forms plus native controls."""

    @staticmethod
    def _native_object(kind, operation):
        return operation in objects.OPERATIONS.get(kind, ()) or (
            operation in {'create', 'alter'} and kind in _EDITED_KINDS)

    def _native_compile(self, request):
        kind, operation = request['resource_kind'], request['operation_id']
        draft = request.get('draft')
        if not isinstance(draft, dict):
            raise RelationalClientError('administration draft is invalid')
        if kind == 'sequence':
            if operation == 'create':
                return {'statements': sequences.create(self, draft)}
            return {'statements': sequences.alter(
                self, draft, request.get('target_resource'))}
        if kind in {'view', 'materialized-view'}:
            if operation == 'create':
                return {'statements': views.create(self, kind, draft)}
            return {'statements': views.alter(
                self, kind, draft, request.get('target_resource'))}
        if kind == 'type':
            if operation == 'create':
                return {'statements': types.create(self, draft)}
            return {'statements': types.alter(
                self, draft, request.get('target_resource'))}
        if kind == 'index':
            if operation == 'create':
                return {'statements': index_sql.create(self, draft)}
            return {'statements': index_sql.alter(
                self, draft, request.get('target_resource'))}
        if kind != 'table':
            return {'statements': objects.compile_operation(
                self, kind, operation, draft,
                request.get('target_resource'))}
        if operation == 'create':
            return {'statements': tables.create(self, draft)}
        statements, warnings = tables.alter(
            self, draft, request.get('target_resource'))
        return {'statements': statements, 'warnings': warnings}

    def validate(self, request):
        kind = request.get('resource_kind')
        operation = request.get('operation_id')
        if not self._native_object(kind, operation) or not self.supports(
                kind, operation):
            return super().validate(request)
        try:
            self._native_compile(request)
        except RelationalClientError as error:
            return {'errors': [{'field_id': None,
                                'code': f'invalid_cockroachdb_{kind}',
                                'message': str(error)}]}
        return {'errors': []}

    def _normalize_draft(self, kind, operation, draft):
        if self._native_object(kind, operation):
            if not isinstance(draft, dict):
                raise RelationalClientError(
                    'administration draft is invalid')
            return dict(draft)
        return super()._normalize_draft(kind, operation, draft)

    def _compile(self, request):
        kind, operation = request['resource_kind'], request['operation_id']
        if self._native_object(kind, operation):
            return self._native_compile(request)
        return super()._compile(request)

    def _form(self, kind, operation):
        if kind == 'sequence' and operation in {'create', 'alter'}:
            return sequences.form(self._field, operation)
        if kind == 'type' and operation in {'create', 'alter'}:
            return types.form(self._field, operation)
        if kind == 'index' and operation in {'create', 'alter'}:
            return index_sql.form(super()._form(kind, 'create'),
                                  self._field, operation)
        if kind == 'table' and operation in {'create', 'alter'}:
            return tables.extend_form(
                super()._form(kind, operation), self._field, operation)
        if kind in {'view', 'materialized-view'} and operation in {
                'create', 'alter'}:
            return views.form(super()._form(kind, 'create')
                              if operation == 'create' else None,
                              self._field, kind, operation)
        if self._native_object(kind, operation):
            return objects.form(kind, operation, self._field)
        return super()._form(kind, operation)


ADMINISTRATION = CockroachDBAdministration(
    _COCKROACH_DIALECT, CONTROL_OPERATIONS,
    _compile_control_plane, inspector=_inspect_control_plane,
    canceller=_cancel_control_plane,
    post_validator=_post_validate_control_plane,
    action_executor=_execute_control_action,
)


def _version(row):
    value = str(row[0] if row else '')
    match = re.search(r'CockroachDB[^\n]*?v?(\d+\.\d+\.\d+)', value, re.I)
    if match is None:
        raise RelationalClientError('CockroachDB version is unavailable')
    return match.group(1)


_CONSTRAINT_TYPES = {'p': 'PRIMARY KEY', 'u': 'UNIQUE', 'f': 'FOREIGN KEY',
                     'c': 'CHECK'}


def _extras(cursor, request, generation):
    values = []
    # From pg_constraint: information_schema.table_constraints also lists
    # each NOT NULL column as a CHECK named <ids>_not_null, which is the
    # column's nullability, not a constraint an editor should re-create.
    details = postgresql_constraint_details(cursor)
    types = {(str(schema), str(table), str(name)): str(kind)
             for schema, table, name, kind in optional_rows(
                 cursor,
                 'SELECT n.nspname, cl.relname, co.conname, co.contype '
                 'FROM pg_catalog.pg_constraint co '
                 'JOIN pg_catalog.pg_class cl ON cl.oid = co.conrelid '
                 'JOIN pg_catalog.pg_namespace n '
                 "ON n.oid = cl.relnamespace WHERE co.contype IN "
                 "('p', 'u', 'f', 'c') ORDER BY 1, 2, 3")}
    for (schema, table, name), kind in types.items():
        values.append(resource(
            'constraint', [schema, table], name, generation, {
                'constraint_type': _CONSTRAINT_TYPES[kind],
                **details.get((schema, table, name), {}),
            }))
    for schema, name in optional_rows(
        cursor,
        'SELECT sequence_schema, sequence_name '
        'FROM information_schema.sequences ORDER BY 1, 2',
    ):
        values.append(resource('sequence', [schema], name, generation))
    for schema, name in optional_rows(
        cursor,
        'SELECT schemaname, matviewname FROM pg_catalog.pg_matviews '
        'ORDER BY 1, 2',
    ):
        values.append(resource(
            'materialized-view', [schema], name, generation
        ))
    # pg_type also lists every table's row type as typtype 'c'; a composite
    # type is the one whose pg_class row is relkind 'c'.
    enum_values = {(str(row[0]), str(row[1])): list(row[2] or [])
                   for row in optional_rows(cursor, 'SHOW ENUMS')}
    fields = {}
    for schema, name, field, field_type in optional_rows(
        cursor,
        'SELECT n.nspname, t.typname, a.attname, '
        'format_type(a.atttypid, a.atttypmod) '
        'FROM pg_catalog.pg_type t '
        'JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace '
        'JOIN pg_catalog.pg_class c ON c.oid = t.typrelid '
        'JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid '
        "WHERE c.relkind = 'c' AND a.attnum > 0 ORDER BY 1, 2, a.attnum",
    ):
        fields.setdefault((str(schema), str(name)), []).append(
            {'name': str(field), 'type': str(field_type)})
    for schema, name, type_kind, comment in optional_rows(
        cursor,
        'SELECT n.nspname, t.typname, t.typtype, d.description '
        'FROM pg_catalog.pg_type t JOIN pg_catalog.pg_namespace n '
        'ON n.oid = t.typnamespace '
        'LEFT JOIN pg_catalog.pg_class c ON c.oid = t.typrelid '
        # Live, 26.1.3: a user type's pg_type oid is its descriptor id plus
        # 100000, but pg_description keeps the bare id.
        'LEFT JOIN pg_catalog.pg_description d '
        'ON d.objoid::INT8 = t.oid::INT8 - 100000 '
        "AND d.classoid = 'pg_catalog.pg_type'::REGCLASS "
        "WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', "
        "'crdb_internal') AND (t.typtype = 'e' OR (t.typtype = 'c' "
        "AND c.relkind = 'c')) ORDER BY 1, 2",
    ):
        key = (str(schema), str(name))
        enum = str(type_kind) == 'e'
        values.append(resource('type', [schema], name, generation, {
            'parent': str(schema),
            'type_kind': 'ENUM' if enum else 'COMPOSITE',
            'values': enum_values.get(key, []) if enum else None,
            'fields': None if enum else fields.get(key, []),
            'comment': None if comment is None else str(comment),
        }))
    for schema, name, routine_kind in optional_rows(
        cursor,
        'SELECT n.nspname, p.proname, p.prokind '
        'FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n '
        'ON n.oid = p.pronamespace '
        "WHERE n.nspname NOT IN ('pg_catalog', 'information_schema') "
        "AND p.prokind IN ('f', 'p') ORDER BY 1, 2",
    ):
        kind = 'procedure' if str(routine_kind) == 'p' else 'function'
        values.append(resource(kind, [schema], name, generation))
    # pg_trigger, not information_schema.triggers: that lists a trigger
    # once per event, so a trigger on two events came back twice.
    for (schema, table, name, tgtype, enabled, function_schema, function,
         arguments, when) in optional_rows(
        cursor,
        'SELECT n.nspname, cl.relname, tg.tgname, tg.tgtype, tg.tgenabled, '
        'pn.nspname, p.proname, tg.tgargs, tg.tgqual '
        'FROM pg_catalog.pg_trigger tg '
        'JOIN pg_catalog.pg_class cl ON cl.oid = tg.tgrelid '
        'JOIN pg_catalog.pg_namespace n ON n.oid = cl.relnamespace '
        'JOIN pg_catalog.pg_proc p ON p.oid = tg.tgfoid '
        'JOIN pg_catalog.pg_namespace pn ON pn.oid = p.pronamespace '
        "WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', "
        "'crdb_internal') ORDER BY 1, 2, 3",
    ):
        values.append(resource(
            'trigger', [schema, table], name, generation,
            objects.trigger_native(
                (str(schema), str(table)), tgtype, enabled,
                (str(function_schema), str(function)), arguments, when),
        ))
    route = request.get('route') or {}
    database = route.get('database')
    partition_rows = []
    if isinstance(database, str) and re.fullmatch(
            r'[A-Za-z_][A-Za-z0-9_$-]{0,255}', database):
        partition_rows = optional_rows(
            cursor,
            f'SHOW PARTITIONS FROM DATABASE {_quote(database)}',
        )
    for database_name, table, name, parent, columns, index, value, *_ in (
            partition_rows):
        values.append(resource(
            'partition', [database_name, table, index], name, generation, {
                'parent_name': None if parent is None else str(parent),
                'column_names': None if columns is None else str(columns),
                'partition_value': None if value is None else str(value),
            },
        ))
    shown = {str(name): (options, member_of) for name, options, member_of,
             *_ in optional_rows(cursor, 'SHOW ROLES')}
    for name, can_login, valid_until in optional_rows(
        cursor,
        'SELECT rolname, rolcanlogin, rolvaliduntil::STRING '
        'FROM pg_catalog.pg_roles ORDER BY rolname',
    ):
        options, member_of = shown.get(str(name), ((), ()))
        native = objects.principal_native(
            options, member_of, can_login, valid_until)
        values.append(resource('role', [], name, generation, {
            'can_login': bool(can_login), **native,
        }))
        if can_login:
            values.append(resource('user', [], name, generation, {
                'can_login': True, **native,
            }))
    for grantee, schema, table, privilege in optional_rows(
        cursor,
        'SELECT grantee, table_schema, table_name, privilege_type '
        'FROM information_schema.table_privileges '
        'WHERE table_schema NOT IN '
        "('pg_catalog', 'information_schema', 'crdb_internal') "
        'ORDER BY 1, 2, 3, 4',
    ):
        display_name = f'{grantee}:{privilege}:{schema}.{table}'
        values.append(resource(
            'privilege', [schema, table, str(grantee)], display_name,
            generation, {'privilege_type': str(privilege),
                         'navigator_relation_path': [schema, table]},
        ))
    route = request.get('route') or {}
    if route.get('cockroach_path'):
        response = _run_node(
            route, ['node', 'status', '--format=json'], timeout=30)
        try:
            node_rows = json.loads(response.get('stdout') or '')
        except (TypeError, ValueError) as exc:
            raise RelationalClientError(
                'CockroachDB node inventory is invalid') from exc
        if not isinstance(node_rows, list):
            raise RelationalClientError(
                'CockroachDB node inventory is invalid')
        for row in node_rows:
            if not isinstance(row, dict) or not str(row.get('id') or ''):
                raise RelationalClientError(
                    'CockroachDB node inventory entry is invalid')
            node_id = str(row['id'])
            values.append(resource(
                'node', [], node_id, generation, dict(row)))
            locality = str(row.get('locality') or '')
            if locality:
                values.append(resource(
                    'locality', [node_id], locality, generation, {
                        'node_id': node_id,
                        'is_live': str(row.get('is_live')).lower() == 'true',
                        'is_available': str(
                            row.get('is_available')).lower() == 'true',
                    }
                ))
    for region, zones in optional_rows(
        cursor, 'SHOW REGIONS FROM CLUSTER',
    ):
        values.append(resource(
            'locality', ['cluster'], region, generation, {
                'region': str(region),
                'zones': list(zones or []),
            }
        ))
    if isinstance(database, str) and re.fullmatch(
            r'[A-Za-z_][A-Za-z0-9_$-]{0,255}', database):
        range_columns = (
            'start_key', 'end_key', 'range_id', 'range_size_mb',
            'lease_holder', 'lease_holder_locality', 'replicas',
            'replica_localities', 'voting_replicas',
            'non_voting_replicas', 'learner_replicas',
            'split_enforced_until', 'range_size', 'span_stats',
        )
        range_rows = optional_rows(
            cursor,
            'SELECT * FROM [SHOW RANGES FROM DATABASE ' +
            _quote(database) + ' WITH DETAILS] ORDER BY range_id LIMIT 2000',
        )
        for row in range_rows:
            native = dict(zip(range_columns, row))
            values.append(resource(
                'range', [database], native['range_id'], generation, native
            ))
    for job_id, status, description in optional_rows(
        cursor,
        'SELECT job_id, status, description FROM [SHOW JOBS] '
        'ORDER BY created DESC LIMIT 200',
    ):
        values.append(resource('job', [], job_id, generation, {
            'status': str(status), 'description': str(description),
        }))
    for row in optional_rows(
        cursor,
        'SELECT id, label, schedule_status, next_run '
        'FROM [SHOW SCHEDULES] ORDER BY id',
    ):
        values.append(resource('schedule', [], row[0], generation, {
            'name': str(row[1]), 'status': str(row[2]),
            'next_run': None if row[3] is None else str(row[3]),
        }))
    for row in optional_rows(
        cursor,
        'SELECT job_id, status, description '
        'FROM [SHOW CHANGEFEED JOBS] ORDER BY job_id',
    ):
        values.append(resource('changefeed', [], row[0], generation, {
            'status': str(row[1]), 'description': str(row[2]),
        }))
    for row in optional_rows(
        cursor,
        'SELECT target, raw_config_sql '
        'FROM [SHOW ALL ZONE CONFIGURATIONS] ORDER BY target',
    ):
        values.append(resource('zone-config', [], row[0], generation, {
            'raw_config_sql': str(row[1]),
        }))
    return values


def _annotate_catalog(connection, values):
    """CockroachDB facts the portable catalog cannot carry.

    Hidden columns (``rowid`` of a table without a primary key, a
    hash-sharded index's ``crdb_internal_..._shard_N``) are marked and the
    constraints on them dropped, so an editor neither re-creates nor drops
    what the engine maintains. Columns carry CockroachDB's own type
    expression and their key membership; indexes their structure.
    """
    cursor = connection.cursor()
    try:
        columns = {(str(row[0]), str(row[1]), str(row[2])): row[3:]
                   for row in optional_rows(
                       cursor,
                       'SELECT table_schema, table_name, column_name, '
                       'is_hidden, crdb_sql_type, column_comment, '
                       'column_default '
                       'FROM information_schema.columns')}
        attributes = {(str(row[0]), str(row[1]), str(row[2])): row[3:]
                      for row in optional_rows(
                          cursor,
                          'SELECT n.nspname, c.relname, a.attname, '
                          'a.attgenerated, a.attidentity '
                          'FROM pg_catalog.pg_attribute a '
                          'JOIN pg_catalog.pg_class c ON c.oid = a.attrelid '
                          'JOIN pg_catalog.pg_namespace n '
                          'ON n.oid = c.relnamespace WHERE a.attnum > 0')}
        relations = {(str(row[0]), str(row[1])): row[2:]
                     for row in optional_rows(
                         cursor,
                         'SELECT n.nspname, c.relname, c.reloptions, '
                         # One argument also matches built-in function
                         # descriptions (live, 26.1.3); name the catalog.
                         "obj_description(c.oid, 'pg_class') "
                         'FROM pg_catalog.pg_class c '
                         'JOIN pg_catalog.pg_namespace n '
                         "ON n.oid = c.relnamespace WHERE c.relkind = 'r'")}
        index_comments = {
            (str(row[0]), str(row[1]), str(row[2])): str(row[3])
            for row in optional_rows(
                cursor,
                'SELECT n.nspname, t.relname, i.relname, '
                "obj_description(i.oid, 'pg_class') "
                'FROM pg_catalog.pg_index x '
                'JOIN pg_catalog.pg_class i ON i.oid = x.indexrelid '
                'JOIN pg_catalog.pg_class t ON t.oid = x.indrelid '
                'JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace')
            if row[3] is not None}
        queries = {('view', str(row[0]), str(row[1])): (str(row[2]), None)
                   for row in optional_rows(
                       cursor, 'SELECT schemaname, viewname, definition '
                       'FROM pg_catalog.pg_views')}
        # Not ispopulated: live, 26.1.3, it stays true after WITH NO DATA.
        queries.update({
            ('materialized-view', str(row[0]), str(row[1])): (
                str(row[2]), None)
            for row in optional_rows(
                cursor, 'SELECT schemaname, matviewname, definition '
                'FROM pg_catalog.pg_matviews')})
        view_columns = {}
        for schema, table, column in optional_rows(
                cursor, 'SELECT c.table_schema, c.table_name, c.column_name '
                'FROM information_schema.columns c '
                'JOIN pg_catalog.pg_class r ON r.relname = c.table_name '
                'JOIN pg_catalog.pg_namespace n ON n.oid = r.relnamespace '
                "AND n.nspname = c.table_schema WHERE r.relkind IN ('v', 'm') "
                # A materialized view has a hidden rowid.
                "AND c.is_hidden = 'NO' "
                'ORDER BY 1, 2, c.ordinal_position'):
            view_columns.setdefault((str(schema), str(table)), []).append(
                str(column))
        created, sequence_facts = {}, {}
        for row in optional_rows(cursor, 'SHOW CREATE ALL TABLES'):
            parsed = tables.parse_create(str(row[0]))
            if parsed:
                created[parsed[0]] = parsed[1:]
            parsed = sequences.parse_create(str(row[0]))
            if parsed:
                sequence_facts[parsed[0]] = parsed[1]
        for schema, name, table_schema, table, column in optional_rows(
                cursor,
                'SELECT n.nspname, s.relname, tn.nspname, t.relname, '
                'a.attname FROM pg_catalog.pg_depend d '
                'JOIN pg_catalog.pg_class s ON s.oid = d.objid '
                'JOIN pg_catalog.pg_namespace n ON n.oid = s.relnamespace '
                'JOIN pg_catalog.pg_class t ON t.oid = d.refobjid '
                'JOIN pg_catalog.pg_namespace tn ON tn.oid = t.relnamespace '
                'JOIN pg_catalog.pg_attribute a ON a.attrelid = t.oid '
                'AND a.attnum = d.refobjsubid '
                "WHERE s.relkind = 'S' AND d.deptype = 'a'"):
            sequence_facts.setdefault((str(schema), str(name)), {})[
                'owned_by'] = f'{table_schema}.{table}.{column}'
        statistics = optional_rows(
            cursor,
            'SELECT table_schema, table_name, index_name, column_name, '
            'direction, storing, implicit, non_unique, visibility '
            'FROM information_schema.statistics '
            'ORDER BY 1, 2, 3, seq_in_index')
    finally:
        cursor.close()
    by_id = {item['resource_id']: item for item in values}
    hidden = set()
    for item in values:
        if item['resource_kind'] != 'column':
            continue
        key = tuple(item['display_path'])
        facts = columns.get(key)
        native = item.setdefault('native', {})
        is_hidden = bool(facts) and str(facts[0]) == 'YES'
        default = None if not facts or facts[3] is None else str(facts[3])
        # The engine's own hidden columns: rowid (a table without a primary
        # key), the TTL expiry column and hash-shard columns. Any other
        # hidden column is the user's NOT VISIBLE column.
        native['hidden'] = is_hidden and (
            key[2].startswith('crdb_internal_') or bool(
                re.fullmatch(r'rowid(_\d+)?', key[2]) and
                default == 'unique_rowid()'))
        if facts and facts[1]:
            native['native_type'] = str(facts[1])
        if native['hidden']:
            hidden.add(key)
        generated, identity = attributes.get(key, ('', ''))
        on_update, families = created.get(key[:2], ({}, []))
        native.update(_column_editor_fields(
            native, key[2], is_hidden, facts, generated, identity,
            on_update, families))
    keys, primaries = {}, set()
    for item in values:
        native = item.get('native') or {}
        if item['resource_kind'] != 'constraint':
            continue
        schema, table = item['display_path'][:2]
        own = native.get('columns') or []
        kind = native.get('constraint_type')
        if kind == 'PRIMARY KEY':
            primaries.add((schema, table, item['display_name']))
        if own and all((schema, table, column) in hidden for column in own):
            # The engine's own: rowid's primary key, a shard column's check.
            item['_drop'] = True
            continue
        if kind == 'PRIMARY KEY':
            for column in own:
                keys[(schema, table, column)] = 'PRI'
        elif kind == 'UNIQUE' and len(own) == 1:
            keys.setdefault((schema, table, own[0]), 'UNI')
    for item in values:
        if item['resource_kind'] == 'column':
            item['native']['column_key'] = keys.get(
                tuple(item['display_path']), '')
    indexes = {}
    for schema, table, name, column, direction, storing, implicit, \
            non_unique, visibility in statistics:
        entry = indexes.setdefault((str(schema), str(table), str(name)), {
            'columns': [], 'directions': [], 'storing': [],
            'unique': str(non_unique) == 'NO',
            'visibility': float(visibility if visibility is not None
                                else 1.0)})
        if str(implicit) == 'YES':
            continue
        if str(storing) == 'YES':
            entry['storing'].append(str(column))
        else:
            entry['columns'].append(str(column))
            entry['directions'].append(str(direction))
    for (schema, table, name), entry in indexes.items():
        item = by_id.get(f'index:{schema}:{table}:{name}')
        if item is None:
            continue
        native = item.setdefault('native', {})
        definition = str(native.get('definition') or '')
        method = re.search(r'\bUSING (\w+) \(', definition)
        bucket = re.search(r'USING HASH WITH \(bucket_count=(\d+)\)',
                           definition)
        # VISIBILITY, when below 1, is rendered after the predicate.
        predicate = re.search(
            r'\) WHERE \((.*)\)(?: VISIBILITY [0-9.]+)?$', definition)
        native.update(
            keys=index_sql.key_list(definition),
            table=[schema, table],
            comment=index_comments.get((schema, table, name)),
            columns=entry['columns'], directions=entry['directions'],
            # The primary index stores every column; that is not a choice.
            storing=[] if (schema, table, name) in primaries else
            entry['storing'],
            unique=entry['unique'],
            method='inverted' if method and method.group(1) == 'gin' else (
                method.group(1) if method else 'btree'),
            hash_sharded=bucket is not None,
            bucket_count=int(bucket.group(1)) if bucket else None,
            predicate=predicate.group(1) if predicate else None,
            visibility=entry['visibility'],
            # rowid's primary index: the engine's, on a hidden column.
            hidden=bool(entry['columns']) and all(
                (schema, table, column) in hidden
                for column in entry['columns']))
    kept = [item for item in values if not item.pop('_drop', False)]
    held = {}
    for item in kept:
        if item['resource_kind'] == 'constraint':
            native = item['native']
            row = _constraint_editor_fields(native)
            native.update(row)
            held.setdefault(tuple(item['display_path'][:2]), []).append(
                {'name': item['display_name'], **row})
    for item in kept:
        if item['resource_kind'] == 'sequence':
            facts = sequence_facts.get(tuple(map(str, item['display_path'])))
            item.setdefault('native', {}).update(
                {'owned_by': None, **(facts or {}),
                 'parent': str(item['display_path'][0])})
        found = queries.get((item['resource_kind'],
                             *map(str, item['display_path'])))
        if found:
            item.setdefault('native', {}).update(
                query=found[0], parent=str(item['display_path'][0]),
                column_names=view_columns.get(
                    tuple(map(str, item['display_path'])), []))
    for item in kept:
        if item['resource_kind'] != 'table':
            continue
        key = tuple(item['display_path'])
        options, comment = relations.get(key, ((), None))
        settings = tables.parse_reloptions(options)
        item.setdefault('native', {}).update({
            'constraints': held.get(key, []),
            'schema_locked': settings.get('schema_locked') == 'true',
            'comment': None if comment is None else str(comment),
            **{name: settings.get(name) for name in tables.TTL_KEYS},
        })
    return kept


def _column_editor_fields(native, name, is_hidden, facts, generated,
                          identity, on_update, families):
    """The column grid's own field ids, from the catalog facts."""
    generated = {'s': 'STORED', 'v': 'VIRTUAL'}.get(str(generated or ''), '')
    identity = {'a': 'ALWAYS', 'd': 'BY DEFAULT'}.get(
        str(identity or ''), '')
    default = native.get('default_expression')
    return {
        'type': native.get('native_type') or native.get('data_type'),
        'nullable': str(native.get('is_nullable')) == 'YES',
        # An identity column's default is its sequence; not a choice.
        'default': None if identity or generated else default,
        'generated_kind': generated,
        'generated_expression': (native.get('generation_expression')
                                 if generated else None),
        'identity': identity,
        'not_visible': is_hidden and not native['hidden'],
        'on_update': on_update.get(name),
        'family': next((family['name'] for family in families
                        if name in family['columns']), None),
        'comment': None if not facts or facts[2] is None else str(facts[2]),
    }


_RULES = {'NO ACTION': 'NO ACTION', 'RESTRICT': 'RESTRICT',
          'CASCADE': 'CASCADE', 'SET NULL': 'SET NULL',
          'SET DEFAULT': 'SET DEFAULT'}


def _constraint_editor_fields(native):
    """The constraint grids' field ids (and the alter baseline row)."""
    kind = native.get('constraint_type')
    row = {'kind': kind, 'columns': list(native.get('columns') or [])}
    if kind == 'FOREIGN KEY':
        row.update(
            references_table=[native.get('referenced_schema'),
                              native.get('referenced_table')],
            references_columns=list(native.get('referenced_columns') or []),
            on_delete=_RULES.get(native.get('delete_rule'), 'NO ACTION'),
            on_update=_RULES.get(native.get('update_rule'), 'NO ACTION'))
    if kind == 'CHECK':
        row = {'kind': kind, 'expression': tables._unwrap(
            str(native.get('check_clause') or ''))}
    return row


def _catalog(connection, request):
    return _annotate_catalog(connection, postgresql_catalog(
        connection, request, 'CockroachDB', _extras))


class CockroachDBProvider(ActualEnginePilotProvider):
    def __init__(self, context, permissions, client):
        super().__init__(context, permissions, client, PROFILE)

    def _discard_unverified_session(self, handle):
        self.client._discard_failed_session(handle)


def create_provider(context, permissions, client=None):
    return CockroachDBProvider(
        context,
        permissions,
        client or create_sql_client(
            PROFILE,
            permissions,
            wire='postgresql',
            version_query='SELECT version()',
            version_parser=_version,
            metadata_reader=_catalog,
            administration=ADMINISTRATION,
            client_class=CockroachDBClient,
            client_options={'pool_namespace': context.pool_namespace},
            pool_namespace=context.pool_namespace,
        ),
    )
