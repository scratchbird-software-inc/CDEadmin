"""Shared MySQL wire, distinct MySQL and MariaDB semantic profiles."""

import copy
import hashlib
import json
import os
import re
from contextlib import contextmanager, nullcontext
from pathlib import Path
from importlib import resources as package_resources

from ..catalog_presentation import annotate_relation_ownership
from ..native_editor import NativeEditorProvider

from pgadmin.cdeadmin.sdk import (
    ActualEnginePilotProvider,
    PilotProfile,
    RelationalClientConfig,
    RelationalDBAPIClient,
    RelationalClientError,
    RelationalCredentialError,
    ProviderToolError,
    ProviderToolGrant,
    ProviderToolRunner,
)
from ..relational_admin import (
    RelationalAdministration,
    RelationalAdminDialect,
)
from ..distributed_sql import mysql_route
from ..form_contracts import provider_form_contract
from .mariadb_connections import Connector as _MariaDBConnectorFacade
from .administration import MySQLAdministration


MYSQL_PROFILE = PilotProfile(
    'org.cdeadmin.mysql', 'mysql-native', 'mysql', 'MySQL', '9.7.0',
    'mysql_wire', 'relational', 'mysql-sql', 'MySQL SQL',
    'mysql-session-autocommit', 'tabular',
    ('server', 'database', 'table', 'column', 'view', 'materialized-view',
     'index', 'constraint', 'trigger', 'event', 'procedure', 'function',
     'partition', 'tablespace', 'user', 'role', 'privilege', 'plugin', 'component', 'library', 'loadable-function',
     'replication-channel', 'group-replication', 'group-replication-member', 'resource-group', 'system-variable', 'session', 'metric',
     'character-set', 'collation', 'storage-engine', 'spatial-reference-system', 'server-link'),
    ('mysql-shell', 'backup', 'replication', 'account-administration'),
    semantic_sql_dialect={
        'contract_complete': True,
        'language_profile': 'mysql-sql', 'quote_open': '`',
        'quote_close': '`', 'supports_rollup': True,
        'rollup_style': 'with_rollup', 'rollup_allows_order_by': False,
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
    dialect_contract_id='mysql.dialect.9.7.0.v1',
    dialect_evidence=(
        'mysql-9.7.0-source-and-runtime-inventory',
        'mysql-9.7.0-task-live-execution',
    ),
    dialect_contract_file='mysql_dialect_9_7_0.json',
    metrics_contract_file='mysql_metrics_9_7_0.json',
    parameter_shape='object-or-array',
    parameter_hint=(
        'Use a JSON object for %(name)s placeholders or an ordered array '
        'for %s placeholders. Exact numeric values use '
        '{"encoding":"integer","data":"9007199254740993"} or '
        '{"encoding":"decimal","data":"1.2300"}; binary values use '
        '{"encoding":"base64","data":"/wA="}.'
        ' Native temporal envelopes use encoding date (YYYY-MM-DD), '
        'datetime (YYYY-MM-DD HH:MM:SS.ffffff), or time (signed HHH:MM:SS.ffffff).'
    ),
    query_plan_templates=(
        ('MySQL JSON query plan', 'EXPLAIN FORMAT=JSON {source}'),
        ('MySQL TREE query plan', 'EXPLAIN FORMAT=TREE {source}'),
        ('MySQL execution plan (executes query)', 'EXPLAIN ANALYZE FORMAT=TREE {source}'),
        ('MySQL JSON execution plan (executes query)', 'EXPLAIN ANALYZE FORMAT=JSON {source}'),
    ),
)
MARIADB_PROFILE = PilotProfile(
    'org.cdeadmin.mariadb', 'mariadb-native', 'mariadb', 'MariaDB', '12.2.2',
    'mysql_wire', 'relational', 'mariadb-sql', 'MariaDB SQL',
    'mariadb-session-transaction', 'tabular',
    ('server', 'database', 'table', 'column', 'view', 'index', 'constraint',
     'sequence', 'trigger', 'event', 'procedure', 'function', 'package',
     'partition', 'tablespace', 'user', 'role', 'privilege',
     'plugin', 'replication-channel', 'server-link', 'loadable-function', 'metric', 'session',
     'system-variable', 'lock', 'lock-wait', 'table-storage', 'binary-log',
     'binary-log-event', 'binary-log-status', 'log-configuration',
     'general-log-entry', 'slow-query', 'tls-configuration',
     'character-set', 'collation', 'storage-engine'),
    ('mariadb-client', 'mariadb-dump', 'mariadb-upgrade', 'replication',
     'user-administration'),
    semantic_sql_dialect={
        'contract_complete': True,
        'language_profile': 'mariadb-sql', 'quote_open': '`',
        'quote_close': '`', 'supports_rollup': True,
        'rollup_style': 'with_rollup', 'rollup_allows_order_by': False,
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
    dialect_contract_id='mariadb.dialect.12.2.2.v1',
    dialect_evidence=(
        'mariadb-12.2.2-source-and-runtime-inventory',
        'mariadb-12.2.2-task-live-execution',
    ),
    dialect_contract_file='mariadb_dialect_12_2_2.json',
    metrics_contract_file='mariadb_metrics_12_2_2.json',
    parameter_shape='object-or-array',
    parameter_hint=(
        'Use an ordered JSON array for ? or %s parameters, or a JSON object '
        'for %(name)s parameters. Exact numbers use integer/decimal encoding '
        'envelopes; binary parameters use base64 encoding and data.'
    ),
    starter_source=(
        'SELECT id, value, event_date\n'
        'FROM qualification\n'
        'ORDER BY id\n'
        'LIMIT 100'
    ),
    source_presets=(
        ('Server identity',
         'SELECT VERSION() AS version, @@hostname AS hostname, '
         'CURRENT_USER() AS current_user'),
        ('Current database',
         'SELECT DATABASE() AS current_database, '
         '@@transaction_isolation AS transaction_isolation'),
        ('Qualification rows',
         'SELECT id, value, event_date FROM qualification '
         'ORDER BY id LIMIT 100'),
    ),
    query_plan_templates=(
        ('MariaDB JSON query plan', 'EXPLAIN FORMAT=JSON {source}'),
        ('MariaDB JSON execution analysis',
         'ANALYZE FORMAT=JSON {source}'),
    ),
)


def _administration(profile):
    common = {
        'server': frozenset({'inspect'}),
        'partition': frozenset({'inspect'}),
        'tablespace': frozenset({'inspect'}),
        'replication-channel': frozenset({'inspect'}),
        'resource-group': frozenset({'inspect'}),
        'server-link': frozenset({'inspect'}),
        'database': frozenset({
            'inspect', 'create', 'alter', 'drop',
        }),
        'table': frozenset({
            'inspect', 'create', 'alter', 'rename', 'drop',
            'insert', 'update', 'delete',
        }),
        'view': frozenset({'inspect', 'create', 'drop'}),
        'materialized-view': frozenset({
            'inspect', 'create', 'alter', 'drop',
        }),
        'column': frozenset({'inspect', 'create', 'rename', 'drop'}),
        'constraint': frozenset({'inspect', 'create', 'drop'}),
        'index': frozenset({'inspect', 'create', 'drop'}),
        'trigger': frozenset({'inspect', 'create', 'drop'}),
        'procedure': frozenset({'inspect', 'create', 'drop'}),
        'function': frozenset({'inspect', 'create', 'drop'}),
        'event': frozenset({'inspect', 'create', 'alter', 'drop'}),
        'sequence': frozenset({
            'inspect', 'create', 'alter', 'rename', 'drop',
        }),
        'role': frozenset({
            'inspect', 'create', 'drop',
        }),
        'user': frozenset({
            'inspect', 'create', 'alter', 'rename', 'drop',
        }),
        'privilege': frozenset({'inspect', 'grant', 'revoke'}),
        'plugin': frozenset({'inspect', 'create', 'drop'}),
        'metric': frozenset({'inspect'}),
    }
    if profile is MYSQL_PROFILE:
        from .column_masking import OPERATIONS as column_masking_operations
        common['column'] = common['column'] | column_masking_operations
        from .mysql_key_cache import OPERATIONS as key_cache_operations
        common['table'] = common['table'] | key_cache_operations
        from .mysql_server_control import OPERATIONS as server_control_operations
        common['server'] = common['server'] | frozenset(server_control_operations)
        from .mysql_xa import OPERATIONS as xa_operations
        common['server'] = common['server'] | frozenset(xa_operations)
        common['prepared-transaction'] = frozenset({'inspect'})
        from .mysql_instance import OPERATIONS as instance_operations
        from .mysql_user_keys import OPERATIONS as user_key_operations
        common['server'] = common['server'] | user_key_operations
        common['server'] = common['server'] | frozenset(instance_operations)
        from .mysql_page_tracking import OPERATIONS as page_tracking_operations
        common['server'] = common['server'] | frozenset(page_tracking_operations)
        from .mysql_rewriter import OPERATIONS as rewriter_operations
        common['server'] = common['server'] | frozenset(rewriter_operations)
        from .mysql_key_cache_lifecycle import OPERATIONS as cache_lifecycle_operations
        common['server'] = common['server'] | frozenset(cache_lifecycle_operations)
        common['spatial-reference-system'] = frozenset({'inspect', 'create', 'alter', 'drop'})
        common['server-link'] = frozenset({'inspect', 'create', 'alter', 'drop'})
        for kind in ('character-set', 'collation', 'storage-engine'):
            common[kind] = frozenset({'inspect'})
        from ..mysql_events import OPERATIONS as event_operations
        common['event']=event_operations | frozenset({'inspect'})
        from ..mysql_program_objects import OPERATIONS as program_operations
        for kind,operations in program_operations.items():common[kind]=operations | frozenset({'inspect'})
        from ..mysql_group_replication import OPERATIONS as group_operations
        common['group-replication']=group_operations | frozenset({'inspect'})
        common['group-replication-member']=frozenset({'inspect'})
        common['component'] = frozenset({'inspect','create','drop'})
        common['constraint'] = common['constraint'] | frozenset({'enforcement'})
        common['view'] = common['view'] | frozenset({'alter'})
        from ..mysql_object_changes import OPERATIONS as object_changes
        for kind, operations in object_changes.items():
            common[kind] = common[kind] | operations
        from ..mysql_replication import OPERATIONS as replication_operations
        common['replication-channel'] = common['replication-channel'] | replication_operations
        from ..mysql_partitions import OPERATIONS as partition_operations
        for kind, operations in partition_operations.items():
            common[kind] = common[kind] | operations
        common['tablespace'] = frozenset({'inspect', 'create', 'alter', 'rename', 'drop'})
        common['system-variable'] = frozenset({'inspect', 'set_global', 'set_persist', 'set_persist_only', 'reset_persist'})
        common['session'] = frozenset({'inspect', 'terminate_query', 'terminate_connection'})
        common['resource-group'] = frozenset({'inspect', 'create', 'alter', 'assign', 'drop'})
        common['role'] = common['role'] | frozenset({'grant', 'revoke', 'set_default'})
        common.pop('sequence')
        common['database'] = common['database'] | frozenset({
            'analyze_tables', 'check_tables', 'optimize_tables',
            'repair_tables', 'checksum_tables', 'backup_logical',
            'restore_logical', 'verify_logical',
        })
    else:
        common.pop('materialized-view')
        for kind in ('character-set', 'collation', 'storage-engine'):
            common[kind] = frozenset({'inspect'})
        common['server'] = frozenset({'inspect', 'check_upgrade_required'})
        for resource_kind in (
                'session', 'system-variable', 'lock', 'lock-wait',
                'table-storage', 'binary-log', 'binary-log-status',
                'binary-log-event', 'log-configuration',
                'general-log-entry', 'slow-query', 'tls-configuration'):
            common[resource_kind] = frozenset({'inspect'})
        common['system-variable'] = frozenset({'inspect', 'set_global'})
        common['session'] = frozenset({
            'inspect', 'terminate_query', 'terminate_connection',
        })
        common['binary-log'] = frozenset({'inspect', 'purge_before'})
        common['binary-log-status'] = frozenset({'inspect', 'rotate'})
        common['role'] = frozenset({
            'inspect', 'create', 'grant', 'revoke', 'set_default', 'drop',
        })
        common['replication-channel'] = frozenset({
            'inspect', 'create', 'alter', 'start', 'stop', 'reset',
        })
        common['database'] = common['database'] | frozenset({
            'analyze_tables', 'check_objects', 'optimize_tables',
            'repair_objects', 'checksum_tables', 'backup_logical',
            'restore_logical',
        })
        from ..mariadb_server_objects import OPERATIONS as server_operations
        for kind, operations in server_operations.items():
            common[kind] = frozenset({'inspect'}) | operations
        from ..mariadb_packages import OPERATIONS as package_operations
        common['package'] = frozenset({'inspect', 'create', 'alter', 'drop'}) | package_operations
        from ..mariadb_partitions import OPERATIONS as partition_operations
        for kind, operations in partition_operations.items():
            common[kind] = common[kind] | operations
    adapter = MySQLAdministration if profile is MYSQL_PROFILE else RelationalAdministration
    return adapter(RelationalAdminDialect(
        engine_id=profile.engine_id,
        quote_open='`',
        quote_close='`',
        parameter='%s',
        supported=common,
        supports_cascade=profile is not MARIADB_PROFILE,
        not_applicable_concepts=frozenset({
            'domains', 'types',
            *(
                {'sequences'} if profile is MYSQL_PROFILE
                else {'materialized_views'}
            ),
        }),
        concept_resource_kinds={'schemas': ('database',)},
        database_forms=provider_form_contract({
            'profile_id': profile.profile_id,
            'engine_id': profile.engine_id,
            'display_name': profile.engine_name,
            'route_kind': 'network',
            'connection_fields': [],
            'secret_fields': [],
        })['database']['forms'],
    ))


MYSQL_ADMINISTRATION = _administration(MYSQL_PROFILE)
MARIADB_ADMINISTRATION = _administration(MARIADB_PROFILE)


def _metric_records(profile):
    """Load only the metrics admitted by the exact provider contract."""
    artifact = package_resources.files(__package__).joinpath(
        profile.metrics_contract_file
    )
    document = json.loads(artifact.read_text(encoding='utf-8'))
    observations = {
        item['observation_id']: item
        for item in document['native_observations']
    }
    return [{
        **observations[item['observation_id']], **item,
    } for item in document['metrics']]


class MariaDBDBAPIClient(RelationalDBAPIClient):
    """Native MariaDB sessions with private pools and ordered result streams."""

    transaction_actions = ('commit', 'rollback', 'autocommit_on',
                           'autocommit_off')

    def __init__(self, config, pool_namespace, module=None, tool_runner=None):
        super().__init__(config, module)
        self._mariadb_connector = _MariaDBConnectorFacade(
            self.module, pool_namespace
        )
        self._connector = self._mariadb_connector
        self._uncertain_sessions = set()
        from .mariadb_execution import Executions
        self._executions = Executions(self)
        self._session_requests = {}
        self._backup_stage_reviews = {}
        self._backup_stage_handles = set()
        self._tool_runner = tool_runner or ProviderToolRunner({
            'mariadb-binlog': os.environ.get('CDEADMIN_MARIADB_BINLOG_BINARY', 'mariadb-binlog'),
            'mariadb-dump': os.environ.get(
                'CDEADMIN_MARIADB_DUMP_BINARY', 'mariadb-dump'
            ),
            'mariadb-client': os.environ.get(
                'CDEADMIN_MARIADB_CLIENT_BINARY', 'mariadb'
            ),
            'mariadb-upgrade': os.environ.get(
                'CDEADMIN_MARIADB_UPGRADE_BINARY', 'mariadb-upgrade'
            ),
        })

    def open_session(self, request):
        with self._executions.lock:
            if self._executions.closing:
                raise RelationalClientError('MariaDB client is closing')
            connection = super().open_session(request)
            try:
                self._executions.sessions.register(connection)
            except BaseException:
                self._discard_failed_session(connection)
                raise
            self._session_requests[id(connection)] = copy.deepcopy(dict(request))
            return connection

    def execute(self, handle, request):
        session_request = self._session_requests.get(id(handle))
        if session_request is None:
            raise RelationalClientError('MariaDB session route is unavailable')
        return self._executions.execute(handle, request, session_request)

    def describe_result(self, token):
        return self._executions.describe(token)

    def cancel(self, token):
        return self._executions.cancel(token)

    def _discard_failed_session(self, connection):
        from .mariadb_connections import discard
        self._backup_stage_handles.discard(id(connection))
        self._forget_connection(connection)
        discard(connection)

    def _require_usable_session(self, handle):
        if id(handle) in self._uncertain_sessions:
            raise RelationalClientError(
                'MariaDB session outcome is unknown; close it before '
                'opening a separate session. Do not replay the operation.')

    def describe_transaction(self, handle):
        with self._executions.lock:
            if self._executions.active(handle):
                return {'state': 'executing', 'connection_usable': False,
                        'driver_observation_only': True,
                        'finality_interpreted_by_common_code': False}
            return self._describe_idle_transaction(handle)

    def _describe_idle_transaction(self, handle):
        from .session_state import transaction_observation
        return transaction_observation(handle, 'MariaDB',
            self._executions.sessions, self._uncertain_sessions)

    def control_transaction(self, handle, action):
        with self._executions.lock:
            self._executions.require_idle(handle)
            return self._control_idle_transaction(handle, action)

    def _control_idle_transaction(self, handle, action):
        self._require_usable_session(handle)
        if action not in self.transaction_actions:
            return super().control_transaction(handle, action)
        if action in {'autocommit_on', 'autocommit_off'}:
            observation = self._describe_idle_transaction(handle)
            if not observation.get('connection_usable') or not observation.get('status_current'):
                raise RelationalClientError('MariaDB session outcome is unknown')
            enabled = action == 'autocommit_on'
            if observation['autocommit'] == enabled:
                return observation
            if observation['in_transaction']:
                raise RelationalClientError(
                    'Commit or roll back the MariaDB transaction before '
                    'changing autocommit')
            try:
                handle.autocommit = enabled
                self._executions.sessions.status_unknown.discard(id(handle))
                observed = self._describe_idle_transaction(handle)
                if (not observed.get('connection_usable') or
                        observed.get('autocommit') != enabled):
                    raise RelationalClientError(
                        'MariaDB autocommit acknowledgement is unknown')
                return observed
            except BaseException:
                self._uncertain_sessions.add(id(handle))
                raise
        try:
            result = super().control_transaction(handle, action)
            self._executions.sessions.status_unknown.discard(id(handle))
            return result
        except BaseException:
            self._uncertain_sessions.add(id(handle))
            raise

    def close_session(self, handle):
        with self._executions.lock:
            self._executions.require_idle(handle)
            self._session_requests.pop(id(handle), None)
            self._executions.sessions.forget(handle)
            return self._close_idle_session(handle)

    def _close_idle_session(self, handle):
        from .mariadb_connections import discard
        if id(handle) in getattr(self, '_backup_stage_handles', set()):
            # BACKUP locks are connection-scoped and do not belong to a pool's
            # next borrower, even when pool_reset_connection was disabled.
            self._backup_stage_handles.discard(id(handle))
            self._forget_connection(handle)
            discard(handle)
            self._uncertain_sessions.discard(id(handle))
            return {'rollback_requested': False, 'connection_released': True,
                'native_disconnect_requested': True, 'backup_session_discarded': True,
                'lock_state_independently_observed': False, 'state': 'unknown',
                'driver_observation_only': True, 'finality_interpreted_by_common_code': False}
        if id(handle) in self._uncertain_sessions:
            self._forget_connection(handle)
            discard(handle)
            self._uncertain_sessions.discard(id(handle))
            return {'rollback_requested': False, 'connection_released': True,
                    'state': 'unknown', 'driver_observation_only': True,
                    'finality_interpreted_by_common_code': False}
        try:
            return super().close_session(handle)
        except BaseException:
            self._forget_connection(handle)
            discard(handle)
            raise

    def close(self):
        self._executions.close()
        try:
            for handle in tuple(self._connections):
                if id(handle) in self._uncertain_sessions or id(handle) in self._backup_stage_handles:
                    self.close_session(handle)
            super().close()
        finally:
            self._mariadb_connector.close()
            self._uncertain_sessions.clear()
            self._session_requests.clear()
            self._executions.sessions.entries.clear()
            self._executions.sessions.status_unknown.clear()
            self._backup_stage_handles.clear()

    @staticmethod
    def _workspace_path(workspace, value):
        if not isinstance(workspace, str) or not workspace:
            raise RelationalClientError('MariaDB tool workspace is required')
        root = Path(workspace).resolve(strict=False)
        if not root.is_absolute() or root in {Path('/'), Path.home()}:
            raise RelationalClientError('MariaDB tool workspace is unsafe')
        if not isinstance(value, str) or not value.strip() or '\x00' in value:
            raise RelationalClientError('MariaDB dump path is invalid')
        candidate = Path(value.strip())
        if not candidate.is_absolute():
            candidate = root / candidate
        candidate = candidate.resolve(strict=False)
        try:
            candidate.relative_to(root)
        except ValueError:
            raise RelationalClientError(
                'MariaDB dump path escapes the tool workspace'
            ) from None
        if candidate == root:
            raise RelationalClientError(
                'MariaDB dump path must be a child path'
            )
        return root, candidate

    @staticmethod
    def _metadata_path(path):
        return path.with_name(path.name + '.cdeadmin.json')

    @staticmethod
    def _file_sha256(path):
        digest = hashlib.sha256()
        size = 0
        with path.open('rb') as stream:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
        return digest.hexdigest(), size

    @staticmethod
    def _defaults_file(password):
        if not isinstance(password, str) or '\x00' in password:
            raise RelationalCredentialError(
                'MariaDB tool credential is invalid'
            )
        escaped = (
            password.replace('\\', '\\\\').replace('"', '\\"')
            .replace('\n', '\\n').replace('\r', '\\r')
        )
        return f'[client]\npassword="{escaped}"\n'.encode('utf-8')

    def _tool_grant(self, route, executable_id):
        timeout = route.get('tool_timeout', 3600)
        if isinstance(timeout, bool) or not isinstance(timeout, int):
            raise RelationalClientError('MariaDB tool timeout is invalid')
        try:
            return ProviderToolGrant(
                executable_id, route.get('tool_workspace'),
                route.get('host'), int(route.get('port', 3306)),
                timeout_seconds=timeout,
            )
        except (ProviderToolError, TypeError, ValueError) as exc:
            raise RelationalClientError(str(exc)) from None

    def _tool_secret(self, route, callback):
        references = dict(route.get('credential_references') or {})
        primary = route.get('credential_reference_id')
        if primary is not None:
            references.setdefault('database_password', primary)
        reference = references.get('database_password')
        if reference is None:
            return callback('')
        principal = route.get('principal_reference')
        if not isinstance(principal, str) or not principal.strip() or not (
                callable(self.config.secret_acquirer)):
            raise RelationalCredentialError(
                'MariaDB tool credential binding is unavailable'
            )
        try:
            lease = self.config.secret_acquirer(
                str(reference), principal.strip(), 'provider_tool',
                'database_password',
            )
        except Exception:
            raise RelationalCredentialError(
                'MariaDB tool credential is unavailable'
            ) from None
        with lease:
            return lease.use(
                lambda view: callback(bytes(view).decode('utf-8'))
            )

    @staticmethod
    def _connection_arguments(route, options):
        arguments = [
            '--user=' + str(route.get('user') or route.get('username') or ''),
            '--default-character-set=' + str(
                options.get('default_character_set', 'utf8mb4')
            ),
            '--max-allowed-packet=' + str(
                int(options.get('max_allowed_packet', 1073741824))
            ),
        ]
        if route.get('unix_socket'):
            arguments.extend([
                '--protocol=socket', '--socket=' + str(route['unix_socket']),
            ])
        else:
            arguments.extend([
                '--protocol=tcp', '--host=' + str(route['host']),
                '--port=' + str(route.get('port', 3306)),
            ])
        ssl_requested = route.get('ssl') is True or any(
            route.get(key) for key in (
                'ssl_key', 'ssl_cert', 'ssl_ca', 'ssl_capath', 'ssl_cipher',
                'ssl_crlpath', 'tls_version',
            )
        )
        arguments.append('--ssl' if ssl_requested else '--skip-ssl')
        for key, native in (
            ('ssl_key', 'ssl-key'), ('ssl_cert', 'ssl-cert'),
            ('ssl_ca', 'ssl-ca'), ('ssl_capath', 'ssl-capath'),
            ('ssl_cipher', 'ssl-cipher'), ('ssl_crlpath', 'ssl-crlpath'),
            ('tls_version', 'tls-version'),
        ):
            value = route.get(key)
            if value:
                arguments.append(f'--{native}={value}')
        if ssl_requested:
            arguments.append(
                '--ssl-verify-server-cert'
                if route.get('ssl_verify_cert') is True else
                '--skip-ssl-verify-server-cert'
            )
        if options.get('compress_connection') is True:
            arguments.append('--compress')
        return arguments

    @staticmethod
    def _inventory(connection, database):
        cursor = connection.cursor()
        try:
            cursor.execute('SELECT VERSION()')
            version = _version(cursor.fetchone())
            cursor.execute(
                'SELECT TABLE_NAME, TABLE_TYPE FROM '
                'information_schema.TABLES WHERE TABLE_SCHEMA = ? '
                'ORDER BY TABLE_NAME',
                (database,),
            )
            objects = [
                {'name': str(name), 'type': str(object_type)}
                for name, object_type in cursor.fetchall()
            ]
            return {'runtime_version': version, 'objects': objects}
        finally:
            cursor.close()

    def _invoke_tool(
            self, route, executable_id, arguments, password, *,
            input_path=None, accepted_return_codes=frozenset({0})):
        grant = self._tool_grant(route, executable_id)
        try:
            version_observation = self._tool_runner.run(grant, ['--version'])
            version_text = (
                str(version_observation.get('stdout') or '') + ' ' +
                str(version_observation.get('stderr') or '')
            )
            version_return_codes = (
                {0, 1} if executable_id == 'mariadb-upgrade' else {0}
            )
            if version_observation.get(
                    'return_code') not in version_return_codes or (
                    '12.2.2-MariaDB' not in version_text):
                raise RelationalClientError(
                    'MariaDB tool must be from the exact 12.2.2 release'
                )
            result = self._tool_runner.run(
                grant, arguments, input_path=input_path,
                secret_config=self._defaults_file(password),
                secret_argument='--defaults-file={path}',
                secret_suffix='.cnf', secret_argument_position=0,
                redact_values=(password,),
            )
        except ProviderToolError as exc:
            raise RelationalClientError(str(exc)) from None
        if result['return_code'] not in accepted_return_codes:
            raise RelationalClientError(
                f'{executable_id} failed; inspect the redacted provider '
                'observation'
            )
        return {
            **result, 'stdout': '', 'stderr': '',
            'tool_version_identity': '12.2.2-MariaDB',
        }

    @staticmethod
    def _upgrade_check_arguments(route):
        arguments = [
            '--check-if-upgrade-is-needed',
            '--user=' + str(route.get('user') or route.get('username') or ''),
        ]
        if route.get('unix_socket'):
            arguments.extend([
                '--protocol=socket', '--socket=' + str(route['unix_socket']),
            ])
        else:
            arguments.extend([
                '--protocol=tcp', '--host=' + str(route['host']),
                '--port=' + str(route.get('port', 3306)),
            ])
        ssl_requested = route.get('ssl') is True or any(
            route.get(key) for key in (
                'ssl_key', 'ssl_cert', 'ssl_ca', 'ssl_capath', 'ssl_cipher',
                'ssl_crlpath', 'tls_version',
            )
        )
        arguments.append('--ssl' if ssl_requested else '--skip-ssl')
        for key, native in (
            ('ssl_key', 'ssl-key'), ('ssl_cert', 'ssl-cert'),
            ('ssl_ca', 'ssl-ca'), ('ssl_capath', 'ssl-capath'),
            ('ssl_cipher', 'ssl-cipher'), ('ssl_crlpath', 'ssl-crlpath'),
            ('tls_version', 'tls-version'),
        ):
            value = route.get(key)
            if value:
                arguments.append(f'--{native}={value}')
        if ssl_requested:
            arguments.append(
                '--ssl-verify-server-cert'
                if route.get('ssl_verify_cert') is True else
                '--skip-ssl-verify-server-cert'
            )
        return arguments

    def _backup_arguments(self, route, options, path):
        arguments = self._connection_arguments(route, options)
        arguments.extend([
            '--quick', '--result-file=' + str(path),
        ])
        if options.get('include_schema', True) is False:
            arguments.append('--no-create-info')
        if options.get('include_data', True) is False:
            arguments.append('--no-data')
        if options.get('single_transaction', True):
            arguments.append('--single-transaction')
        elif options.get('lock_all_tables', False):
            arguments.append('--lock-all-tables')
        else:
            arguments.append('--skip-lock-tables')
        switches = (
            ('add_drop_database', '--add-drop-database', None),
            ('add_drop_table', '--add-drop-table', '--skip-add-drop-table'),
            ('routines', '--routines', None),
            ('events', '--events', None),
            ('triggers', '--triggers', '--skip-triggers'),
            ('dump_history', '--dump-history', None),
            ('hex_blob', '--hex-blob', None),
            ('order_by_primary', '--order-by-primary', None),
            ('extended_insert', '--extended-insert',
             '--skip-extended-insert'),
            ('complete_insert', '--complete-insert', None),
            ('comments', '--comments', '--skip-comments'),
            ('dump_date', '--dump-date', '--skip-dump-date'),
            ('tz_utc', '--tz-utc', '--skip-tz-utc'),
            ('flush_logs', '--flush-logs', None),
        )
        defaults = {
            'add_drop_database': True, 'add_drop_table': True,
            'routines': True, 'events': True, 'triggers': True,
            'dump_history': False, 'hex_blob': True,
            'order_by_primary': False, 'extended_insert': True,
            'complete_insert': False, 'comments': True, 'dump_date': True,
            'tz_utc': True, 'flush_logs': False,
        }
        for field_id, enabled, disabled in switches:
            if options.get(field_id, defaults[field_id]):
                arguments.append(enabled)
            elif disabled:
                arguments.append(disabled)
        if options.get('as_of'):
            arguments.append('--as-of=' + str(options['as_of']))
        position = options.get('replication_position', 'NONE')
        if position != 'NONE':
            arguments.append(
                '--master-data=1' if position == 'EXECUTABLE'
                else '--master-data=2'
            )
        if options.get('gtid'):
            arguments.append('--gtid')
        arguments.extend(['--databases', str(route['database'])])
        return arguments

    def _restore_arguments(self, route, options):
        arguments = self._connection_arguments(route, options)
        arguments.extend(['--batch', '--skip-auto-rehash'])
        arguments.append(
            '--abort-source-on-error'
            if options.get('abort_on_error', True) else '--force'
        )
        if options.get('binary_mode', True):
            arguments.append('--binary-mode')
        if options.get('show_warnings', True):
            arguments.append('--show-warnings')
        return arguments

    def run_database_operation(
            self, connection, route, operation_id, options):
        if operation_id == 'check_upgrade_required':
            if not isinstance(options, dict) or options:
                raise RelationalClientError(
                    'MariaDB upgrade check does not accept options'
                )

            def check_upgrade(password):
                observation = self._invoke_tool(
                    route, 'mariadb-upgrade',
                    self._upgrade_check_arguments(route), password,
                    accepted_return_codes=frozenset({0, 1}),
                )
                return {
                    **observation,
                    'operation_id': operation_id,
                    'upgrade_required': observation['return_code'] == 0,
                    'upgrade_check_completed': True,
                    'check_is_read_only': True,
                    'driver_observation_only': True,
                    'transaction_finality_interpreted_by_common_code': False,
                }

            return self._tool_secret(route, check_upgrade)
        if operation_id not in {'backup_logical', 'restore_logical'}:
            return super().run_database_operation(
                connection, route, operation_id, options
            )
        if not isinstance(options, dict):
            raise RelationalClientError('MariaDB tool options are invalid')
        _root, path = self._workspace_path(
            route.get('tool_workspace'), options['path']
        )
        metadata_path = self._metadata_path(path)
        database = str(route.get('database') or '')
        if operation_id == 'backup_logical':
            if path.exists() or metadata_path.exists():
                raise RelationalClientError(
                    'MariaDB backup artifact already exists'
                )
            owns_connection = connection is None
            inventory_connection = connection or self._connect({
                'route': route
            })
            try:
                before = self._inventory(inventory_connection, database)
            finally:
                if owns_connection:
                    self._forget_and_close(inventory_connection)

            def backup(password):
                try:
                    observation = self._invoke_tool(
                        route, 'mariadb-dump',
                        self._backup_arguments(route, options, path),
                        password,
                    )
                    if not path.is_file():
                        raise RelationalClientError(
                            'MariaDB backup produced no dump file'
                        )
                    digest, size = self._file_sha256(path)
                    if size == 0:
                        raise RelationalClientError(
                            'MariaDB backup produced an empty dump file'
                        )
                    metadata = {
                        'schema': 'cdeadmin.mariadb-logical-backup.v1',
                        'engine_id': 'mariadb',
                        'reference_version': MARIADB_PROFILE.exact_version,
                        'database': database,
                        'dump_file': path.name,
                        'dump_sha256': digest,
                        'dump_size': size,
                        'source_inventory': before,
                        'backup_options': {
                            key: value for key, value in options.items()
                            if key != 'path'
                        },
                    }
                    with metadata_path.open('x', encoding='utf-8') as stream:
                        json.dump(metadata, stream, indent=2, sort_keys=True)
                        stream.write('\n')
                    return {
                        **observation, 'operation_id': operation_id,
                        'artifact_path': str(path),
                        'metadata_path': str(metadata_path),
                        'artifact_sha256': digest,
                        'artifact_total_bytes': size,
                        'mariadb_dump_completed': True,
                        'driver_observation_only': True,
                        'transaction_finality_interpreted_by_common_code':
                            False,
                    }
                except Exception:
                    path.unlink(missing_ok=True)
                    metadata_path.unlink(missing_ok=True)
                    raise

            return self._tool_secret(route, backup)
        if not path.is_file() or not metadata_path.is_file():
            raise RelationalClientError(
                'MariaDB restore source lacks its CDEadmin metadata'
            )
        try:
            metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise RelationalClientError(
                'MariaDB restore metadata is invalid'
            ) from None
        metadata_mismatch = any((
            metadata.get('schema') != 'cdeadmin.mariadb-logical-backup.v1',
            metadata.get('engine_id') != 'mariadb',
            metadata.get('reference_version') != MARIADB_PROFILE.exact_version,
            metadata.get('database') != database,
            metadata.get('dump_file') != path.name,
        ))
        if metadata_mismatch:
            raise RelationalClientError(
                'MariaDB restore metadata does not match the target'
            )
        digest, size = self._file_sha256(path)
        if digest != metadata.get('dump_sha256') or size != metadata.get(
                'dump_size'):
            raise RelationalClientError(
                'MariaDB restore dump checksum does not match metadata'
            )
        if options.get('dry_run'):
            return {
                'operation_id': operation_id, 'dry_run': True,
                'artifact_path': str(path), 'artifact_sha256': digest,
                'artifact_total_bytes': size,
                'metadata_validated': True,
                'driver_observation_only': True,
                'transaction_finality_interpreted_by_common_code': False,
            }

        def restore(password):
            observation = self._invoke_tool(
                route, 'mariadb-client',
                self._restore_arguments(route, options), password,
                input_path=path,
            )
            verification = self._connect({'route': route})
            try:
                after = self._inventory(verification, database)
            finally:
                self._forget_and_close(verification)
            expected = metadata.get('source_inventory', {}).get('objects')
            if not isinstance(expected, list) or after['objects'] != expected:
                raise RelationalClientError(
                    'MariaDB restore object postcondition failed'
                )
            return {
                **observation, 'operation_id': operation_id,
                'artifact_path': str(path), 'artifact_sha256': digest,
                'artifact_total_bytes': size,
                'restore_postcondition': {
                    'runtime_version': after['runtime_version'],
                    'expected_objects': expected,
                    'observed_objects': after['objects'],
                    'object_postcondition_passed': True,
                },
                'mariadb_restore_completed': True,
                'driver_observation_only': True,
                'transaction_finality_interpreted_by_common_code': False,
            }

        return self._tool_secret(route, restore)


class MySQLDBAPIClient(RelationalDBAPIClient):
    """MySQL DB-API plus a constrained MySQL Shell administration port."""

    transaction_actions = ('commit', 'rollback', 'autocommit_on',
                           'autocommit_off')

    def plan_admin_operation(self, request):
        planned = super().plan_admin_operation(request)
        compiled = planned.get('provider_payload', {}).get('compiled', {})
        if 'mysql_server_control' in compiled:
            from .mysql_server_control import bind_review
            return bind_review(self,planned)
        if 'mysql_xa' in compiled:
            from .mysql_xa import bind_review
            return bind_review(self,planned)
        if 'mysql_page_tracking' in compiled:
            from .mysql_page_tracking import bind_review
            return bind_review(self, planned)
        if 'mysql_rewriter' in compiled:
            from .mysql_rewriter import bind_review
            return bind_review(self, planned)
        if 'mysql_key_cache_lifecycle' in compiled:
            from .mysql_key_cache_lifecycle import bind_review
            return bind_review(self,planned)
        if 'mysql_instance' in compiled:
            from .mysql_instance import bind_review
            return bind_review(self,planned)
        if 'mysql_user_keys' in compiled:
            from .mysql_user_keys import bind_review
            return bind_review(self,planned)
        if 'mysql_key_cache' in compiled:
            from .mysql_key_cache import bind_review
            return bind_review(self,planned)
        if compiled.get('driver_operation') == 'mysql-shell' and compiled.get('operation_id') == 'verify_logical':
            from .mysql_dump_verification import bind_review
            return bind_review(self, planned)
        if 'mysql_column_masking' in planned.get('provider_payload', {}).get('compiled', {}):
            from .column_masking import bind_review
            return bind_review(self, planned)
        if 'mysql_foreign_server' in planned.get('provider_payload', {}).get('compiled', {}):
            from .foreign_servers import bind_review
            return bind_review(self, planned)
        if 'mysql_spatial_reference' in planned.get('provider_payload', {}).get('compiled', {}):
            from .spatial_reference_systems import bind_review
            return bind_review(self, planned)
        return planned

    _OPTION_NAMES = {
        'backup_logical': {
            'consistent': 'consistent',
            'skip_consistency_checks': 'skipConsistencyChecks',
            'ddl_only': 'ddlOnly', 'data_only': 'dataOnly',
            'checksum': 'checksum', 'chunking': 'chunking',
            'bytes_per_chunk': 'bytesPerChunk', 'threads': 'threads',
            'max_rate': 'maxRate', 'show_progress': 'showProgress',
            'default_character_set': 'defaultCharacterSet',
            'compression': 'compression', 'tz_utc': 'tzUtc',
            'events': 'events', 'routines': 'routines',
            'libraries': 'libraries', 'triggers': 'triggers',
            'include_tables': 'includeTables',
            'exclude_tables': 'excludeTables',
            'include_events': 'includeEvents',
            'exclude_events': 'excludeEvents',
            'include_routines': 'includeRoutines',
            'exclude_routines': 'excludeRoutines',
            'include_libraries': 'includeLibraries',
            'exclude_libraries': 'excludeLibraries',
            'include_triggers': 'includeTriggers',
            'exclude_triggers': 'excludeTriggers',
            'partitions': 'partitions', 'where': 'where',
            'compatibility': 'compatibility',
            'target_version': 'targetVersion',
            'skip_upgrade_checks': 'skipUpgradeChecks',
            'dry_run': 'dryRun',
        },
        'restore_logical': {
            'analyze_tables': 'analyzeTables',
            'background_threads': 'backgroundThreads',
            'character_set': 'characterSet', 'checksum': 'checksum',
            'create_invisible_pks': 'createInvisiblePKs',
            'defer_table_indexes': 'deferTableIndexes',
            'disable_bulk_load': 'disableBulkLoad',
            'drop_existing_objects': 'dropExistingObjects',
            'dry_run': 'dryRun', 'exclude_events': 'excludeEvents',
            'exclude_libraries': 'excludeLibraries',
            'exclude_routines': 'excludeRoutines',
            'exclude_schemas': 'excludeSchemas',
            'exclude_tables': 'excludeTables',
            'exclude_triggers': 'excludeTriggers',
            'exclude_users': 'excludeUsers',
            'handle_grant_errors': 'handleGrantErrors',
            'ignore_existing_objects': 'ignoreExistingObjects',
            'ignore_version': 'ignoreVersion',
            'include_events': 'includeEvents',
            'include_libraries': 'includeLibraries',
            'include_routines': 'includeRoutines',
            'include_schemas': 'includeSchemas',
            'include_tables': 'includeTables',
            'include_triggers': 'includeTriggers',
            'include_users': 'includeUsers',
            'load_data': 'loadData', 'load_ddl': 'loadDdl',
            'load_indexes': 'loadIndexes', 'load_users': 'loadUsers',
            'max_bytes_per_transaction': 'maxBytesPerTransaction',
            'progress_file': 'progressFile',
            'reset_progress': 'resetProgress', 'schema': 'schema',
            'session_init_sql': 'sessionInitSql',
            'show_metadata': 'showMetadata',
            'show_progress': 'showProgress', 'skip_binlog': 'skipBinlog',
            'threads': 'threads', 'update_gtid_set': 'updateGtidSet',
            'wait_dump_timeout': 'waitDumpTimeout',
        },
    }

    def __init__(self, config, module=None, tool_runner=None):
        super().__init__(config, module)
        from .mysql_connections import Connector
        self._mysql_connector = Connector(self.module)
        self._connector = self._mysql_connector
        self._uncertain_sessions = set()
        from .mysql_execution import Executions
        self._executions = Executions(self)
        self._session_requests = {}
        self._native_operations = 0
        self._tool_runner = tool_runner or ProviderToolRunner({
            'mysql-shell': os.environ.get(
                'CDEADMIN_MYSQLSH_BINARY', 'mysqlsh'
            ),
            'mysql-binlog': os.environ.get('CDEADMIN_MYSQL_BINLOG_BINARY','mysqlbinlog'),
            'mysql-client': os.environ.get('CDEADMIN_MYSQL_CLIENT_BINARY','mysql'),
            'mysql-server': os.environ.get('CDEADMIN_MYSQL_SERVER_BINARY','mysqld'),
        })

    def _connect(self, request):
        # Keep admission through native initialization and handle publication.
        # This includes dedicated catalog/collector connections, not just the
        # interactive sessions published by the provider facade.
        with self._executions.lock:
            if self._executions.closing:
                raise RelationalClientError('MySQL client is closing')
            return super()._connect(request)

    def open_session(self, request):
        with self._executions.lock:
            if self._executions.closing:
                raise RelationalClientError('MySQL client is closing')
            handle = super().open_session(request)
            try:
                self._executions.sessions.register(handle)
                from .mysql_session_variables import install
                install(self, handle, request)
            except BaseException:
                self._discard_failed_session(handle)
                raise
            self._session_requests[id(handle)] = copy.deepcopy(dict(request))
            return handle

    def execute(self, handle, request):
        session_request = self._session_requests.get(id(handle))
        if session_request is None:
            raise RelationalClientError('MySQL session route is unavailable')
        return self._executions.execute(handle, request, session_request)

    def describe_result(self, token):
        return self._executions.describe(token)

    def cancel(self, token):
        return self._executions.cancel(token)

    def _discard_failed_session(self, connection):
        from .mysql_connections import discard
        self._forget_connection(connection)
        discard(connection)

    def _require_usable_session(self, handle):
        if id(handle) in self._uncertain_sessions:
            raise RelationalClientError(
                'MySQL session outcome is unknown; close it before '
                'opening a separate session. Do not replay the operation.')

    def describe_transaction(self, handle):
        with self._executions.lock:
            if self._executions.active(handle):
                return {'state': 'executing', 'connection_usable': False,
                        'driver_observation_only': True,
                        'finality_interpreted_by_common_code': False}
            return self._describe_idle_transaction(handle)

    def _describe_idle_transaction(self, handle):
        from .session_state import transaction_observation
        return transaction_observation(handle, 'MySQL',
            self._executions.sessions, self._uncertain_sessions)

    def control_transaction(self, handle, action):
        with self._executions.lock:
            self._executions.require_idle(handle)
            return self._control_idle_transaction(handle, action)

    def _control_idle_transaction(self, handle, action):
        self._require_usable_session(handle)
        if action not in self.transaction_actions:
            return super().control_transaction(handle, action)
        if action in {'autocommit_on', 'autocommit_off'}:
            observation = self._describe_idle_transaction(handle)
            if not observation.get('connection_usable') or not observation.get('status_current'):
                raise RelationalClientError('MySQL session outcome is unknown')
            enabled = action == 'autocommit_on'
            if observation['autocommit'] == enabled:
                return observation
            if observation['in_transaction']:
                raise RelationalClientError(
                    'Commit or roll back the MySQL transaction before '
                    'changing autocommit')
            try:
                handle.autocommit = enabled
                self._executions.sessions.status_unknown.discard(id(handle))
                observed = self._describe_idle_transaction(handle)
                if (not observed.get('connection_usable') or
                        observed.get('autocommit') != enabled):
                    raise RelationalClientError(
                        'MySQL autocommit acknowledgement is unknown')
                return observed
            except BaseException:
                self._uncertain_sessions.add(id(handle))
                raise
        try:
            result = super().control_transaction(handle, action)
            self._executions.sessions.status_unknown.discard(id(handle))
            return result
        except BaseException:
            self._uncertain_sessions.add(id(handle))
            raise

    def close_session(self, handle):
        with self._executions.lock:
            self._executions.require_idle(handle)
            from .mysql_session_variables import uninstall
            uninstall(handle)
            self._session_requests.pop(id(handle), None)
            self._executions.sessions.forget(handle)
            return self._close_idle_session(handle)

    def _close_idle_session(self, handle):
        from .mysql_connections import discard
        if id(handle) in self._uncertain_sessions:
            self._forget_connection(handle)
            discard(handle)
            self._uncertain_sessions.discard(id(handle))
            return {'rollback_requested': False, 'connection_released': True,
                    'state': 'unknown', 'driver_observation_only': True,
                    'finality_interpreted_by_common_code': False}
        try:
            return super().close_session(handle)
        except BaseException:
            self._forget_connection(handle)
            discard(handle)
            raise

    def close(self):
        with self._executions.lock:
            if self._native_operations:
                raise RelationalClientError('MySQL native utility work is active')
            self._executions.closing = True
        self._executions.close()
        try:
            from .mysql_session_variables import uninstall
            for handle in tuple(self._connections):
                uninstall(handle)
                if id(handle) in self._uncertain_sessions:
                    self.close_session(handle)
            super().close()
        finally:
            self._mysql_connector.close()
            self._uncertain_sessions.clear()
            self._session_requests.clear()
            self._executions.sessions.entries.clear()
            self._executions.sessions.status_unknown.clear()

    @staticmethod
    def _workspace_path(workspace, value, label):
        if not isinstance(workspace, str) or not workspace:
            raise RelationalClientError('MySQL Shell workspace is required')
        root = Path(workspace).resolve(strict=False)
        if not root.is_absolute() or root in {Path('/'), Path.home()}:
            raise RelationalClientError('MySQL Shell workspace is unsafe')
        if not isinstance(value, str) or not value or '\x00' in value:
            raise RelationalClientError(f'{label} is invalid')
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = root / candidate
        candidate = candidate.resolve(strict=False)
        try:
            candidate.relative_to(root)
        except ValueError:
            raise RelationalClientError(
                f'{label} escapes the MySQL Shell workspace'
            ) from None
        if candidate == root:
            raise RelationalClientError(f'{label} must be a child path')
        return root, candidate

    def _tool_grant(self, route):
        timeout = route.get('tool_timeout', 3600)
        if isinstance(timeout, bool) or not isinstance(timeout, int):
            raise RelationalClientError('MySQL Shell timeout is invalid')
        try:
            return ProviderToolGrant(
                'mysql-shell', route.get('tool_workspace'),
                route.get('host'), int(route.get('port', 3306)),
                timeout_seconds=timeout,
            )
        except (ProviderToolError, TypeError, ValueError) as exc:
            raise RelationalClientError(str(exc)) from None

    @contextmanager
    def _native_operation(self):
        with self._executions.lock:
            if self._executions.closing:
                raise RelationalClientError('MySQL client is closing')
            self._native_operations += 1
        try:
            yield
        finally:
            with self._executions.lock:
                self._native_operations -= 1

    def _tool_secrets(self, route, callback, *, allow_recovery_credentials=False):
        with self._native_operation():
            return self._acquire_tool_secrets(route, callback,
                allow_recovery_credentials=allow_recovery_credentials)

    def _acquire_tool_secrets(self, route, callback, *, allow_recovery_credentials=False):
        if route.get('mysql_recovery_binding') and not allow_recovery_credentials:
            from .mysql_recovery_bridge import require_replay_utility
            require_replay_utility(route)
        references = dict(route.get('credential_references') or {})
        primary = route.get('credential_reference_id')
        if primary is not None:
            references.setdefault('database_password', primary)
        bindings = [
            (kind, references[kind]) for kind in (
                'database_password', 'database_password_2',
                'database_password_3',
            ) if kind in references
        ]
        if not bindings:
            return callback([])
        principal = route.get('principal_reference')
        if not isinstance(principal, str) or not principal.strip() or not (
                callable(self.config.secret_acquirer)):
            raise RelationalCredentialError(
                'MySQL Shell credential binding is unavailable'
            )

        def acquire(index, values):
            if index == len(bindings):
                return callback(values)
            kind, reference = bindings[index]
            try:
                lease = self.config.secret_acquirer(
                    str(reference), principal.strip(), 'provider_tool', kind
                )
            except Exception:
                raise RelationalCredentialError(
                    'MySQL Shell credentials are unavailable'
                ) from None
            with lease:
                return lease.use(lambda view: acquire(
                    index + 1,
                    [*values, bytes(view).decode('utf-8')],
                ))

        return acquire(0, [])

    @staticmethod
    def _shell_connection_arguments(route):
        arguments = [
            '--no-defaults', '--mysql', '--js',
            '--host=' + str(route['host']),
            '--port=' + str(route.get('port', 3306)),
            '--user=' + str(route.get('user') or route.get('username') or ''),
            '--passwords-from-stdin',
        ]
        if route.get('ssl_disabled'):
            arguments.append('--ssl-mode=DISABLED')
        elif route.get('ssl_verify_identity'):
            arguments.append('--ssl-mode=VERIFY_IDENTITY')
        elif route.get('ssl_verify_cert'):
            arguments.append('--ssl-mode=VERIFY_CA')
        else:
            arguments.append('--ssl-mode=REQUIRED')
        mappings = (
            ('ssl_ca', '--ssl-ca='), ('ssl_cert', '--ssl-cert='),
            ('ssl_key', '--ssl-key='), ('ssl_cipher', '--ssl-cipher='),
        )
        for key, prefix in mappings:
            if route.get(key):
                arguments.append(prefix + str(route[key]))
        versions = route.get('tls_versions')
        if isinstance(versions, list) and versions:
            arguments.append('--tls-version=' + ','.join(versions))
        suites = route.get('tls_ciphersuites')
        if isinstance(suites, list) and suites:
            arguments.append('--tls-ciphersuites=' + ':'.join(suites))
        arguments.append(
            '--compress=REQUIRED' if route.get('compress')
            else '--compress=DISABLED'
        )
        return arguments

    @classmethod
    def _shell_options(cls, operation, options):
        mapping = cls._OPTION_NAMES[operation]
        return {
            native: options[field]
            for field, native in mapping.items()
            if field in options and options[field] is not None and
            options[field] != ''
        }

    @staticmethod
    def _artifact_manifest(path):
        files = []
        total = 0
        for item in sorted(path.rglob('*')):
            if not item.is_file():
                continue
            digest = hashlib.sha256()
            size = 0
            with item.open('rb') as stream:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    size += len(chunk)
            total += size
            files.append({
                'path': str(item.relative_to(path)),
                'size': size, 'sha256': digest.hexdigest(),
            })
        return files, total

    @staticmethod
    def _selected_restore_schemas(path, options):
        try:
            metadata = json.loads((path / '@.json').read_text(
                encoding='utf-8'
            ))
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise RelationalClientError(
                'MySQL Shell dump metadata is invalid'
            ) from None
        schemas = metadata.get('schemas')
        if not isinstance(schemas, list) or not schemas or not all(
                isinstance(item, str) and item for item in schemas):
            raise RelationalClientError(
                'MySQL Shell dump has no verifiable schema inventory'
            )
        includes = options.get('include_schemas')
        excludes = set(options.get('exclude_schemas') or [])
        if includes:
            schemas = [item for item in schemas if item in set(includes)]
        schemas = [item for item in schemas if item not in excludes]
        if options.get('schema'):
            if len(schemas) != 1:
                raise RelationalClientError(
                    'MySQL Shell target schema requires one selected schema'
                )
            schemas = [options['schema']]
        if not schemas:
            raise RelationalClientError(
                'MySQL Shell restore selected no schemas to verify'
            )
        return schemas

    def _verify_restore(self, route, path, options):
        schemas = self._selected_restore_schemas(path, options)
        verification = self._connect({'route': route})
        cursor = None
        try:
            cursor = verification.cursor()
            cursor.execute('SELECT VERSION()')
            version = _version(cursor.fetchone())
            cursor.execute(
                'SELECT SCHEMA_NAME FROM information_schema.SCHEMATA '
                'WHERE SCHEMA_NAME IN (' +
                ','.join(['%s'] * len(schemas)) + ')', tuple(schemas),
            )
            observed = sorted(str(row[0]) for row in cursor.fetchall())
            if observed != sorted(schemas):
                raise RelationalClientError(
                    'MySQL Shell restore schema postcondition failed'
                )
            return {
                'runtime_version': version,
                'expected_schemas': sorted(schemas),
                'observed_schemas': observed,
                'schema_postcondition_passed': True,
            }
        finally:
            if cursor is not None:
                cursor.close()
            self._forget_and_close(verification)

    def run_database_operation(
            self, connection, route, operation_id, options):
        with self._native_operation():
            return self._run_database_operation(connection, route, operation_id, options)

    def _run_database_operation(
            self, connection, route, operation_id, options):
        if operation_id == 'verify_logical':
            from .mysql_dump_verification import verify
            return verify(self, route, options)
        if operation_id not in {'backup_logical', 'restore_logical'}:
            return super().run_database_operation(
                connection, route, operation_id, options
            )
        if not isinstance(options, dict):
            raise RelationalClientError('MySQL Shell options are invalid')
        _root, path = self._workspace_path(
            route.get('tool_workspace'), options['path'],
            'MySQL Shell dump path',
        )
        if operation_id == 'backup_logical':
            if path.exists():
                raise RelationalClientError(
                    'MySQL Shell backup path already exists'
                )
            database = str(route.get('database') or '')
            method = 'dumpSchemas'
            operands = [[database], str(path)]
        else:
            if not path.is_dir() or not (path / '@.json').is_file() or not (
                    path / '@.done.json').is_file():
                raise RelationalClientError(
                    'MySQL Shell restore source is not a completed dump'
                )
            method = 'loadDump'
            operands = [str(path)]
        effective_options = dict(options)
        progress_file = effective_options.get('progress_file')
        if progress_file:
            _progress_root, progress_path = self._workspace_path(
                route.get('tool_workspace'), progress_file,
                'MySQL Shell progress file',
            )
            effective_options['progress_file'] = str(progress_path)
        if operation_id == 'restore_logical':
            self._selected_restore_schemas(path, effective_options)
        shell_options = self._shell_options(operation_id, effective_options)
        source = 'util.%s(%s)' % (
            method,
            ', '.join(json.dumps(value, separators=(',', ':')) for value in (
                *operands, shell_options,
            )),
        )
        def invoke_native(passwords):
            try:
                from .mysql_shell_tools import run
                observation = run(self, route, source, passwords)
            except ProviderToolError as exc:
                raise RelationalClientError(str(exc)) from None
            if observation['return_code'] != 0:
                raise RelationalClientError(
                    'MySQL Shell operation failed; inspect the redacted '
                    'provider observation'
                )
            if effective_options.get('dry_run'):
                return {
                    **observation,
                    'stdout': '', 'stderr': '',
                    'operation_id': operation_id,
                    'artifact_path': str(path),
                    'mysql_shell_completed': True,
                    'dry_run': True,
                    'driver_observation_only': True,
                    'transaction_finality_interpreted_by_common_code': False,
                }
            files, total = self._artifact_manifest(path)
            if not files or not (path / '@.json').is_file() or not (
                    path / '@.done.json').is_file():
                raise RelationalClientError(
                    'MySQL Shell operation has no verifiable dump metadata'
                )
            return {
                **observation,
                'stdout': '', 'stderr': '',
                'operation_id': operation_id,
                'artifact_path': str(path),
                'artifact_file_count': len(files),
                'artifact_total_bytes': total,
                'artifact_manifest': files,
                'mysql_shell_completed': True,
                'driver_observation_only': True,
                'transaction_finality_interpreted_by_common_code': False,
            }

        if operation_id == 'backup_logical':
            def invoke(passwords):
                from .mysql_backup_events import track, completed
                with track(self, route, path, effective_options) as ticket:
                    return completed(ticket, invoke_native(passwords))
        else:
            invoke = invoke_native

        enable_local_infile = (
            operation_id == 'restore_logical' and
            effective_options.get('enable_local_infile') is True
        )
        if not enable_local_infile:
            result = self._tool_secrets(route, invoke)
        else:
            owns_connection = connection is None
            settings_connection = connection or self._connect({
                'route': route
            })
            settings_cursor = None
            changed = False
            try:
                settings_cursor = settings_connection.cursor()
                settings_cursor.execute('SELECT @@GLOBAL.local_infile')
                prior = bool(settings_cursor.fetchone()[0])
                if not prior:
                    settings_cursor.execute('SET GLOBAL local_infile = ON')
                    changed = True
                result = self._tool_secrets(route, invoke)
                result['local_infile_temporarily_enabled'] = changed
                result['local_infile_prior_state'] = prior
            finally:
                try:
                    if changed:
                        if settings_cursor is None:
                            settings_cursor = settings_connection.cursor()
                        settings_cursor.execute(
                            'SET GLOBAL local_infile = OFF'
                        )
                finally:
                    if settings_cursor is not None:
                        settings_cursor.close()
                    if owns_connection:
                        self._forget_and_close(settings_connection)
        if operation_id == 'restore_logical' and not effective_options.get(
                'dry_run'):
            result['restore_postcondition'] = self._verify_restore(
                route, path, effective_options
            )
        return result


class MySQLPilotProvider(NativeEditorProvider, ActualEnginePilotProvider):
    def __init__(self, context, permissions, client):
        super().__init__(context, permissions, client, MYSQL_PROFILE)

    @contextmanager
    def profile_change_guard(self):
        """Preserve native sessions, including idle temporary/prepared state."""
        native = isinstance(self.client, MySQLDBAPIClient)
        with self.client._executions.lock if native else nullcontext():
            if self._sessions or (native and (
                    self.client._connections or self.client._session_requests or
                    self.client._native_operations or
                    self.client._uncertain_sessions or any(
                        not token.finished.is_set()
                        for token in self.client._executions.tokens))):
                raise RelationalClientError(
                    'Close MySQL SQL sessions and dedicated native work before '
                    'changing this connection; explicitly finish pending work')
            yield

    def release_for_profile_change(self):
        with self.profile_change_guard():
            self.close()

    def apply_server_operation(self, route, record, operation):
        from ..mysql_server_application import apply_operation
        self._require('administer', 'resource')
        self._require('execute')
        if not isinstance(self.client, MySQLDBAPIClient):
            raise RelationalClientError('Native MySQL server application client is unavailable')
        connection = self.client._connect({'route': {**route, 'database': None}})
        try:
            return apply_operation(connection, record, operation)
        finally:
            self.client._discard_failed_session(connection)

    def apply_data_import(self, route, record):
        from ..mysql_data_application import apply_import, verify
        self._require('data_write', 'resource')
        self._require('data_read', 'resource')
        self._require('execute')
        if not isinstance(self.client, MySQLDBAPIClient):
            raise RelationalClientError('Native MySQL data client is unavailable')
        connection = self.client._connect({'route': route})
        try:
            result = apply_import(connection, record)
        finally:
            self.client._discard_failed_session(connection)
        if result['state'] == 'committed':
            check = None
            try:
                check = self.client._connect({'route': {**route, 'autocommit': True}})
                observed = verify(check, record['plan'])
                result.update(independent_verification=observed, rediscovery_verified=observed['verified'])
            except Exception as error:
                result.update(rediscovery_verified=False, verification_error_type=type(error).__name__)
            finally:
                if check is not None:
                    self.client._discard_failed_session(check)
        return result

    def apply_schema_review(self, route, record):
        from ..mysql_schema_application import apply_review
        self._require('administer', 'resource')
        self._require('execute')
        if not isinstance(self.client, MySQLDBAPIClient):
            raise RelationalClientError('Native MySQL application client is unavailable')
        connection = self.client._connect({'route': route})
        try:
            return apply_review(connection, record)
        finally:
            self.client._discard_failed_session(connection)

    def encode_native_metadata(self, route, metadata):
        from ..mysql_native_encoding import encode_metadata
        self._require('data_read', 'resource')
        self._require('execute')
        if not isinstance(self.client, MySQLDBAPIClient):
            raise RelationalClientError('Native MySQL encoding client is unavailable')
        connection = self.client._connect({'route': route})
        try:
            return encode_metadata(connection, metadata)
        finally:
            self.client._discard_failed_session(connection)

    def validate_schema_plan(self, route, plan):
        from ..mysql_schema_validation import validate
        self._require('data_read', 'resource')
        self._require('execute')
        if not isinstance(self.client, MySQLDBAPIClient):
            raise RelationalClientError('Native MySQL validation client is unavailable')
        connection = self.client._connect({'route': route})
        try:
            return validate(connection, plan)
        finally:
            self.client._discard_failed_session(connection)

    def capture_server_catalog(self, route, *, spatial_reference_ids=None):
        from .mysql_server_catalog import capture
        self._require('data_read', 'resource')
        if not isinstance(self.client, MySQLDBAPIClient):
            raise RelationalClientError('Native MySQL catalog client is unavailable')
        connection = self.client._connect({'route': {**route, 'database': None}})
        try:
            return capture(connection, spatial_reference_ids=spatial_reference_ids)
        finally:
            self.client._discard_failed_session(connection)

    def capture_data(self, route, resource_id, *, endpoint_id, target_id, mode='sample', row_limit=100):
        from .mysql_data_capture import capture
        self._require('data_read', 'resource')
        self._require('execute')
        if not isinstance(self.client, MySQLDBAPIClient):
            raise RelationalClientError('Native MySQL data client is unavailable')
        connection = self.client._connect({'route': route})
        try:
            return capture(connection, route.get('database'), resource_id, endpoint_id=endpoint_id,
                target_id=target_id, mode=mode, row_limit=row_limit)
        finally:
            self.client._discard_failed_session(connection)

    def capture_catalog(self, route, *, include_system=False):
        """Capture on a dedicated lease, never an interactive session handle."""
        from .mysql_catalog import capture
        self._require('data_read', 'resource')
        if not isinstance(self.client, MySQLDBAPIClient):
            raise RelationalClientError('Native MySQL catalog client is unavailable')
        connection = self.client._connect({'route': route})
        try:
            return capture(connection, route.get('database'), include_system=include_system)
        finally:
            # Even a bounded-read interruption may leave an unread result.
            # Retire this attachment rather than lending it to user work.
            self.client._discard_failed_session(connection)


class MariaDBPilotProvider(NativeEditorProvider, ActualEnginePilotProvider):
    def __init__(self, context, permissions, client):
        super().__init__(context, permissions, client, MARIADB_PROFILE)

    def backup_stage_action(self, request):
        from .mariadb_backup_stages import action
        self._require('execute')
        self._require('backup_admin')
        if request.get('language_profile') != 'mariadb-sql':
            raise RelationalClientError('Native MariaDB query session required')
        if not isinstance(self.client, MariaDBDBAPIClient):
            raise RelationalClientError('Native MariaDB backup-stage client is unavailable')
        handle = self._editor_session(request)
        try:
            return action(self.client, handle, {key: value for key, value in request.items()
                if key not in {'session_id', 'language_profile'}})
        except (ValueError, RelationalClientError):
            raise
        except Exception as error:
            self.client._uncertain_sessions.add(id(handle))
            raise RelationalClientError('Native MariaDB backup-stage workflow failed (' +
                type(error).__name__ + ')') from None

    def apply_server_operation(self, route, record, operation):
        from ..mariadb_server_application import apply_operation
        self._require('administer', 'resource')
        self._require('execute')
        if not isinstance(self.client, MariaDBDBAPIClient):
            raise RelationalClientError('Native MariaDB server application client is unavailable')
        connection = self.client._connect({'route': {**route, 'database': None}})
        try:
            return apply_operation(connection, record, operation)
        finally:
            self.client._discard_failed_session(connection)

    def apply_data_import(self, route, record):
        from ..mariadb_data_application import apply_import, verify
        self._require('data_write', 'resource')
        self._require('data_read', 'resource')
        self._require('execute')
        if not isinstance(self.client, MariaDBDBAPIClient):
            raise RelationalClientError('Native MariaDB data client is unavailable')
        connection = self.client._connect({'route': route})
        try:
            result = apply_import(connection, record)
        finally:
            self.client._discard_failed_session(connection)
        if result['state'] == 'committed':
            check = None
            try:
                check = self.client._connect({'route': {**route, 'autocommit': True}})
                observed = verify(check, record['plan'])
                result.update(independent_verification=observed, rediscovery_verified=observed['verified'])
            except Exception as error:
                result.update(rediscovery_verified=False, verification_error_type=type(error).__name__)
            finally:
                if check is not None:
                    self.client._discard_failed_session(check)
        return result

    def validate_schema_plan(self, route, plan):
        from ..mariadb_schema_validation import validate
        self._require('administer', 'resource')
        if not isinstance(self.client, MariaDBDBAPIClient):
            raise RelationalClientError('Native MariaDB validation client is unavailable')
        connection = self.client._connect({'route': {**route, 'autocommit': True, 'reconnect': False}})
        try:
            return validate(connection, plan)
        finally:
            self.client._discard_failed_session(connection)

    def apply_schema_review(self, route, record):
        from ..mariadb_schema_application import apply_review
        self._require('administer', 'resource')
        if not isinstance(self.client, MariaDBDBAPIClient):
            raise RelationalClientError('Native MariaDB application client is unavailable')
        connection = self.client._connect({'route': {**route, 'autocommit': True, 'reconnect': False}})
        try:
            return apply_review(connection, record)
        finally:
            self.client._discard_failed_session(connection)

    def encode_native_metadata(self, route, metadata):
        from .mariadb_native_encoding import encode_metadata
        self._require('data_read', 'resource')
        if not isinstance(self.client, MariaDBDBAPIClient):
            raise RelationalClientError('Native MariaDB encoding client is unavailable')
        connection = self.client._connect({'route': {**route, 'autocommit': True, 'reconnect': False}})
        try:
            return encode_metadata(connection, metadata)
        finally:
            self.client._discard_failed_session(connection)

    def capture_server_catalog(self, route):
        from .mariadb_server_catalog import capture
        self._require('data_read', 'resource')
        if not isinstance(self.client, MariaDBDBAPIClient):
            raise RelationalClientError('Native MariaDB server catalog client is unavailable')
        connection = self.client._connect({'route': {**route, 'database': None, 'autocommit': True}})
        try:
            return capture(connection)
        finally:
            self.client._discard_failed_session(connection)

    def capture_data(self, route, resource_id, *, endpoint_id, target_id, expected_server_uid, mode='sample', row_limit=100):
        from .mariadb_data_capture import capture
        self._require('data_read', 'resource')
        self._require('execute')
        if not isinstance(self.client, MariaDBDBAPIClient):
            raise RelationalClientError('Native MariaDB data client is unavailable')
        connection = self.client._connect({'route': {**route, 'autocommit': True, 'reconnect': False}})
        try:
            return capture(connection, route.get('database'), resource_id, endpoint_id=endpoint_id,
                target_id=target_id, expected_server_uid=expected_server_uid, mode=mode, row_limit=row_limit)
        finally:
            self.client._discard_failed_session(connection)

    def capture_catalog(self, route, *, include_system=False):
        """Observe native MariaDB metadata on an independently owned lease."""
        from .mariadb_catalog import capture
        self._require('data_read', 'resource')
        if not isinstance(self.client, MariaDBDBAPIClient):
            raise RelationalClientError('Native MariaDB catalog client is unavailable')
        connection = self.client._connect({'route': {**route, 'autocommit': True}})
        try:
            return capture(connection, route.get('database'), include_system=include_system)
        finally:
            self.client._discard_failed_session(connection)


def _route_arguments(route, profile):
    if profile is MYSQL_PROFILE:
        if route.get('auth_plugin') == 'mysql_native_password':
            raise RelationalClientError(
                'MySQL 9.7 does not support mysql_native_password')
        options = mysql_route(route)
        if 'mysql_recovery_binding' in route:
            options['mysql_recovery_binding'] = copy.deepcopy(route['mysql_recovery_binding'])
        if 'use_pure' in route:
            if type(route['use_pure']) is not bool:
                raise RelationalClientError(
                    'MySQL driver mode must be boolean')
            options['use_pure'] = route['use_pure']
        for name in ('allow_local_infile', 'allow_local_infile_in_path'):
            if name in route:
                options[name] = route[name]
        return options
    allowed = {
        'host', 'port', 'user', 'database', 'unix_socket',
        'connection_timeout', 'connect_timeout', 'read_timeout',
        'write_timeout', 'local_infile', 'compress', 'init_command',
        'default_file', 'default_group', 'plugin_dir', 'reconnect',
        'ssl_key', 'ssl_cert', 'ssl_ca', 'ssl_capath', 'ssl_cipher',
        'ssl_crlpath', 'ssl_verify_cert', 'ssl', 'tls_version',
        'autocommit', 'pool_name', 'pool_size', 'pool_reset_connection',
        'pool_validation_interval',
    }
    result = {key: value for key, value in route.items() if key in allowed}
    if profile is MARIADB_PROFILE and 'connection_timeout' in result:
        result['connect_timeout'] = result.pop('connection_timeout')
    if result.get('pool_size') and not result.get('pool_name'):
        route_id = str(route.get('route_id') or 'unscoped')
        result['pool_name'] = 'cde_' + hashlib.sha256(
            route_id.encode('utf-8')
        ).hexdigest()[:24]
    return result


def _initialize_connection(connection, route):
    isolation = route.get('transaction_isolation')
    if isolation is None:
        return
    allowed = {
        'READ UNCOMMITTED', 'READ COMMITTED', 'REPEATABLE READ',
        'SERIALIZABLE',
    }
    if isolation not in allowed:
        raise RelationalClientError(
            'MySQL-family transaction isolation is invalid'
        )
    cursor = connection.cursor()
    try:
        cursor.execute(
            f'SET SESSION TRANSACTION ISOLATION LEVEL {isolation}'
        )
    finally:
        cursor.close()


def _initialize_mysql_connection(connection, route):
    _initialize_connection(connection, route)
    # Connector/Python's post-connection initialization ignores empty strings.
    # Clearing sql_mode explicitly differs from preserving server defaults.
    if route.get('sql_mode') == '':
        connection.sql_mode = ''


def _version(row):
    value = str(row[0]).strip() if row else ''
    match = re.match(r'^(\d+\.\d+\.\d+)', value)
    if match is None:
        raise RelationalClientError(
            'MySQL-family profile version is unavailable'
        )
    return match.group(1)


def _resources(connection, request, profile=MYSQL_PROFILE):
    cursor = connection.cursor()
    try:
        generation = str(request.get('capability_generation') or 'current')
        route = request.get('route') if isinstance(request, dict) else None
        selected_database = route.get('database') if isinstance(
            route, dict
        ) else None
        selected_database = selected_database if isinstance(selected_database, str) and selected_database else None
        resources = {}
        catalog_failures = []
        catalog_unavailable = []
        system_databases = {'information_schema', 'mysql',
                            'performance_schema', 'sys'}

        def catalog_source(source):
            if selected_database not in system_databases:
                return source
            # Keep endpoint scans bounded, but never exclude the system
            # database the user explicitly selected in the navigator.
            return re.sub(
                r"(?:WHERE|AND) (?:TABLE|TRIGGER|ROUTINE|EVENT|LIBRARY)_SCHEMA "
                r"NOT IN \('information_schema', 'mysql', "
                r"'performance_schema', 'sys'\) ", '', source)

        def record_failure(source, error):
            code = getattr(error, 'errno', None)
            server_native = resources.get('server:' + profile.engine_name, {}).get('native', {})
            if (profile is MARIADB_PROFILE and source == 'SHOW BINARY LOGS' and
                    code == 1381 and server_native.get('log_bin') in (0, False, '0', 'OFF')):
                catalog_unavailable.append({'feature': 'binary-log',
                    'state': 'disabled', 'native_error_code': 1381,
                    'sqlstate': getattr(error, 'sqlstate', None)})
                return
            catalog_failures.append({
                'query_sha256': hashlib.sha256(source.encode()).hexdigest(),
                'error_code': None if code is None else str(code),
                'sqlstate': getattr(error, 'sqlstate', None),
                'category': ('permission_denied' if code in {1142, 1227}
                             else 'query_failed'),
            })

        def resource_key(kind, path, name):
            parts = [kind, *map(str, path), str(name)]
            # Retain established uncomplicated IDs and avoid delimiter collisions.
            return (profile.engine_id + '-resource:' + json.dumps(parts, ensure_ascii=False, separators=(',', ':'))
                    if any(':' in part for part in parts)
                    else ':'.join(parts))

        def add(kind, path, name, native=None, *, identity=None):
            path = [str(item) for item in path]
            name = str(name)
            resource_id = identity or resource_key(kind, path, name)
            resource = resources.setdefault(resource_id, {
                'resource_id': resource_id,
                'resource_kind': kind,
                'display_name': name,
                'display_path': [*path, name],
                'authority_path': [*path, kind, name],
                'generation': generation,
            })
            if native:
                resource.setdefault('native', {}).update(native)
            if kind in {'user', 'role', 'tablespace', 'plugin', 'component',
                    'loadable-function', 'resource-group', 'system-variable', 'session', 'metric',
                    'character-set', 'collation', 'storage-engine', 'replication-channel',
                    'group-replication', 'group-replication-member', 'server-link', 'spatial-reference-system', 'lock', 'lock-wait',
                    'binary-log', 'binary-log-status', 'binary-log-event', 'general-log-entry',
                    'slow-query', 'log-configuration', 'tls-configuration'}:
                resource.setdefault('native', {})['navigator_scope'] = 'server'
            if (path and path[0] in system_databases) or (
                    kind == 'database' and name in system_databases):
                resource.setdefault('native', {})['system_object'] = True

        def optional(source, parameters=()):
            try:
                if parameters:
                    cursor.execute(catalog_source(source), parameters)
                else:
                    cursor.execute(catalog_source(source))
                return cursor.fetchall()
            except Exception as error:
                record_failure(source, error)
                return []

        def normalized(value):
            if value is None or isinstance(value, (str, int, float, bool)):
                return value
            if isinstance(value, (bytes, bytearray, memoryview)):
                return bytes(value).hex()
            return str(value)

        def optional_records(source, parameters=None):
            try:
                if parameters is None:
                    cursor.execute(catalog_source(source))
                else:
                    cursor.execute(catalog_source(source), parameters)
                names = tuple(str(item[0]).lower() for item in (
                    cursor.description or ()
                ))
                return [
                    {
                        name: normalized(row[index])
                        for index, name in enumerate(names)
                    }
                    for row in cursor.fetchall()
                ]
            except Exception as error:
                record_failure(source, error)
                return []

        if profile is MYSQL_PROFILE:
            server_observation = optional(
                'SELECT VERSION(), @@hostname, @@port, @@server_uuid, '
                '@@version_comment, @@version_compile_machine, '
                '@@version_compile_os, @@lower_case_table_names, '
                '@@default_storage_engine, @@transaction_isolation, '
                'CURRENT_USER(), USER(), @@sql_mode'
            )
            server_names = (
                'version', 'hostname', 'port', 'server_uuid',
                'version_comment', 'version_compile_machine',
                'version_compile_os', 'lower_case_table_names',
                'default_storage_engine', 'transaction_isolation',
                'current_user', 'session_user', 'sql_mode',
            )
        else:
            server_observation = optional(
                'SELECT VERSION(), @@hostname, @@port, @@server_id, '
                '@@version_comment, '
                '@@version_compile_machine, @@version_compile_os, '
                '@@lower_case_table_names, @@default_storage_engine, '
                '@@tx_isolation, CURRENT_USER(), USER(), @@sql_mode, '
                '@@character_set_server, @@collation_server, @@log_bin, '
                '@@binlog_format, @@gtid_strict_mode, '
                '(SELECT VARIABLE_VALUE FROM information_schema.GLOBAL_VARIABLES '
                "WHERE VARIABLE_NAME='WSREP_ON'), "
                '@@max_connections'
            )
            server_names = (
                'version', 'hostname', 'port', 'server_id', 'version_comment',
                'version_compile_machine', 'version_compile_os',
                'lower_case_table_names', 'default_storage_engine',
                'tx_isolation', 'current_user', 'session_user', 'sql_mode',
                'character_set_server', 'collation_server', 'log_bin',
                'binlog_format', 'gtid_strict_mode', 'wsrep_on',
                'max_connections',
            )
        add('server', [], profile.engine_name, (
            dict(zip(server_names, server_observation[0]))
            if server_observation else {
                'observation_error': 'server_properties_unavailable',
            }
        ))
        schema_source = (
            'SELECT SCHEMA_NAME, DEFAULT_CHARACTER_SET_NAME, '
            'DEFAULT_COLLATION_NAME, DEFAULT_ENCRYPTION '
            'FROM information_schema.SCHEMATA ORDER BY SCHEMA_NAME'
            if profile is MYSQL_PROFILE else
            'SELECT SCHEMA_NAME, DEFAULT_CHARACTER_SET_NAME, '
            'DEFAULT_COLLATION_NAME, SCHEMA_COMMENT '
            'FROM information_schema.SCHEMATA '
            'ORDER BY SCHEMA_NAME'
        )
        for row in optional(schema_source):
            native = {
                'default_character_set': row[1],
                'default_collation': row[2],
            }
            if profile is MYSQL_PROFILE:
                native['default_encryption'] = row[3]
            else:
                native['schema_comment'] = row[3]
            add('database', [], row[0], native)
        cursor.execute(catalog_source(
            'SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE '
            'FROM information_schema.TABLES '
            "WHERE TABLE_SCHEMA NOT IN ('information_schema', 'mysql', "
            "'performance_schema', 'sys') "
            'ORDER BY TABLE_SCHEMA, TABLE_NAME'
        ))
        for schema_name, object_name, object_type in cursor.fetchall():
            schema_name = str(schema_name)
            add('database', [], schema_name)
            object_type = str(object_type).upper()
            escaped_schema = schema_name.replace('`', '``')
            escaped_name = str(object_name).replace('`', '``')
            create_source = ''
            if object_type == 'SEQUENCE' and profile is MARIADB_PROFILE:
                kind = 'sequence'
                definition = optional(
                    f'SHOW CREATE SEQUENCE `{escaped_schema}`.'
                    f'`{escaped_name}`'
                )
                create_source = (
                    str(definition[0][1]) if definition else ''
                )
            elif object_type == 'VIEW' and profile is MYSQL_PROFILE:
                definition = optional(
                    f'SHOW CREATE VIEW `{escaped_schema}`.`{escaped_name}`'
                )
                create_source = (
                    str(definition[0][1]) if definition else ''
                )
                from ..mysql_view_identity import HEADER as view_header
                matched = view_header.match(create_source)
                kind = 'materialized-view' if matched and matched['materialized'] else 'view'
            else:
                kind = 'view' if 'VIEW' in object_type else 'table'
                show_kind = 'VIEW' if kind == 'view' else 'TABLE'
                if object_type == 'SYSTEM VIEW':
                    # SYSTEM VIEWs include dictionary views and temporary
                    # native tables. SHOW CREATE TABLE supports both;
                    # SHOW CREATE VIEW fails with 1347 on the native tables.
                    show_kind = 'TABLE'
                definition = optional(
                    f'SHOW CREATE {show_kind} `{escaped_schema}`.'
                    f'`{escaped_name}`'
                )
                create_source = (
                    str(definition[0][1]) if definition else ''
                )
            native = {'table_type': object_type}
            if create_source:
                native['ddl'] = create_source
            if kind == 'view' and profile is MYSQL_PROFILE:
                facts = optional('SELECT VIEW_DEFINITION,CHECK_OPTION,DEFINER,SECURITY_TYPE,IS_UPDATABLE '
                                 'FROM information_schema.VIEWS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s',
                                 (schema_name, object_name))
                if facts:
                    row = facts[0]
                    native.update(view_definition=row[0], check_option=row[1],
                                  definer=row[2], sql_security=row[3], is_updatable=row[4])
                    user, separator, host = str(row[2]).rpartition('@')
                    if separator:
                        native.update(definer_user=user, definer_host=host)
                algorithm = re.match(r'CREATE\s+ALGORITHM\s*=\s*(UNDEFINED|MERGE|TEMPTABLE)\b', create_source, re.I)
                if algorithm:
                    native['algorithm'] = algorithm.group(1).upper()
                output_columns = optional('SELECT COLUMN_NAME FROM information_schema.COLUMNS '
                                          'WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION',
                                          (schema_name, object_name))
                if output_columns:
                    native['view_columns'] = [str(row[0]) for row in output_columns]
            add(kind, [schema_name], object_name, native)
        queries = (
            ('column', 'SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, '
             'COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT '
             "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA NOT IN "
             "('information_schema', 'mysql', 'performance_schema', 'sys') "
             'ORDER BY 1, 2, '
             'ORDINAL_POSITION'),
            ('index', 'SELECT DISTINCT TABLE_SCHEMA, TABLE_NAME, INDEX_NAME, '
             'NON_UNIQUE, INDEX_TYPE FROM information_schema.STATISTICS '
             "WHERE TABLE_SCHEMA NOT IN ('information_schema', 'mysql', "
             "'performance_schema', 'sys') "
             'ORDER BY 1, 2, 3'),
            ('constraint', 'SELECT TABLE_SCHEMA, TABLE_NAME, '
             'CONSTRAINT_NAME, CONSTRAINT_TYPE FROM information_schema.'
             "TABLE_CONSTRAINTS WHERE TABLE_SCHEMA NOT IN "
             "('information_schema', 'mysql', 'performance_schema', 'sys') "
             'ORDER BY 1, 2, 3'),
            ('trigger', 'SELECT TRIGGER_SCHEMA, EVENT_OBJECT_TABLE, '
             'TRIGGER_NAME, ACTION_TIMING, EVENT_MANIPULATION '
             "FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA NOT IN "
             "('information_schema', 'mysql', 'performance_schema', 'sys') "
             'ORDER BY 1, 2, 3'),
            ('partition', 'SELECT TABLE_SCHEMA, TABLE_NAME, PARTITION_NAME, '
             'PARTITION_METHOD, PARTITION_EXPRESSION FROM information_schema.'
             "PARTITIONS WHERE PARTITION_NAME IS NOT NULL AND TABLE_SCHEMA "
             "NOT IN ('information_schema', 'mysql', 'performance_schema', "
             "'sys') ORDER BY 1, 2, 3"),
        )
        for kind, source in queries:
            for row in optional(source):
                schema_name, parent, name, *detail = row
                add(kind, [schema_name, parent], name, {
                    'details': [
                        None if item is None else str(item)
                        for item in detail
                    ],
                })
        if profile is MYSQL_PROFILE:
            from .column_masking import policy_clauses
            from .mysql_catalog import _value as column_value
            mode = resources.get('server:MySQL', {}).get('native', {}).get('sql_mode')
            column_policy_cache = {}
            for record in optional_records('SELECT * FROM information_schema.COLUMNS WHERE TABLE_SCHEMA NOT IN '
                    "('information_schema', 'mysql', 'performance_schema', 'sys') ORDER BY TABLE_SCHEMA,TABLE_NAME,ORDINAL_POSITION"):
                schema, table, column = (record.get(key) for key in ('table_schema', 'table_name', 'column_name'))
                if not all(isinstance(value, str) for value in (schema, table, column)):
                    continue
                key = resource_key('column', [schema, table], column)
                if key not in resources:
                    continue
                facts = {key: column_value(value) for key, value in record.items()}
                value = resources[key].setdefault('native', {})
                value['catalog_metadata'] = facts
                value['extra'] = facts.get('extra')
                table_resource = resources.get(resource_key('table', [schema], table), {})
                ddl = table_resource.get('native', {}).get('ddl')
                try:
                    if not isinstance(mode, str) or not isinstance(ddl, str):
                        raise ValueError('Native table definition context unavailable')
                    if (schema, table) not in column_policy_cache:
                        column_policy_cache[schema, table] = policy_clauses(ddl, mode)
                    policy = column_policy_cache[schema, table][column]
                    if bool(policy['name']) != ('MASKING POLICY' in str(facts.get('extra', '')).upper()):
                        raise ValueError('Native column declaration and facts disagree')
                    value['masking_policy'] = {'name': policy['name'], 'available': True}
                except (ValueError, KeyError):
                    value['masking_policy'] = {'name': None, 'available': False,
                        'reason': 'Exact native column declaration unavailable'}
            for record in optional_records(
                'SELECT DISTINCT TABLE_SCHEMA, TABLE_NAME, INDEX_NAME, NON_UNIQUE, INDEX_TYPE, IS_VISIBLE, INDEX_COMMENT '
                'FROM information_schema.STATISTICS WHERE TABLE_SCHEMA NOT IN '
                "('information_schema','mysql','performance_schema','sys') ORDER BY 1,2,3"
            ):
                native = {key: value for key, value in record.items() if key not in {'table_schema', 'table_name', 'index_name'}}
                native['administration'] = {'allowed_operations': ['inspect', 'drop'] if record['index_name'].upper() == 'PRIMARY' else ['inspect', 'drop', 'rename', 'visibility']}
                add('index', [record['table_schema'], record['table_name']], record['index_name'], native)
            for record in optional_records(
                'SELECT ROUTINE_SCHEMA, ROUTINE_NAME, ROUTINE_TYPE, SECURITY_TYPE, SQL_DATA_ACCESS, ROUTINE_COMMENT, IS_DETERMINISTIC '
                'FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA NOT IN '
                "('information_schema','mysql','performance_schema','sys') ORDER BY 1,2"
            ):
                add(record['routine_type'].lower(), [record['routine_schema']], record['routine_name'], {
                    key: value for key, value in record.items() if key not in {'routine_schema', 'routine_name', 'routine_type'}})
            for record in optional_records(
                'SELECT TABLE_SCHEMA,TABLE_NAME,CONSTRAINT_NAME,CONSTRAINT_TYPE,ENFORCED '
                'FROM information_schema.TABLE_CONSTRAINTS '
                "WHERE TABLE_SCHEMA NOT IN ('information_schema','mysql','performance_schema','sys') "
                'ORDER BY TABLE_SCHEMA,TABLE_NAME,CONSTRAINT_NAME'
            ):
                native = {**record, 'enforcement': 'ENFORCED' if record['enforced'] == 'YES' else 'NOT ENFORCED', 'administration': {'allowed_operations':
                    ['inspect', 'create', 'drop'] + (['enforcement'] if record['constraint_type'] == 'CHECK' else [])}}
                add('constraint', [record['table_schema'], record['table_name']], record['constraint_name'], native)
            for record in optional_records(
                'SELECT p.TABLE_SCHEMA, p.TABLE_NAME, p.PARTITION_NAME, p.PARTITION_METHOD, p.PARTITION_EXPRESSION, '
                'p.PARTITION_ORDINAL_POSITION, p.PARTITION_DESCRIPTION, p.TABLE_ROWS, p.DATA_LENGTH, p.INDEX_LENGTH, '
                't.ENGINE, p.TABLESPACE_NAME, p.SUBPARTITION_NAME, p.SUBPARTITION_METHOD, p.SUBPARTITION_EXPRESSION '
                'FROM information_schema.PARTITIONS p JOIN information_schema.TABLES t '
                'ON t.TABLE_SCHEMA=p.TABLE_SCHEMA AND t.TABLE_NAME=p.TABLE_NAME WHERE p.PARTITION_NAME IS NOT NULL '
                "AND p.TABLE_SCHEMA NOT IN ('information_schema','mysql','performance_schema','sys') "
                'ORDER BY p.TABLE_SCHEMA,p.TABLE_NAME,p.PARTITION_ORDINAL_POSITION,p.SUBPARTITION_ORDINAL_POSITION'
            ):
                add('partition', [record['table_schema'], record['table_name']], record['partition_name'], {
                    key: value for key, value in record.items() if not key.startswith('subpartition_')})
                if record.get('subpartition_name'):
                    partition = resources[resource_key('partition',[record['table_schema'],record['table_name']],record['partition_name'])]
                    partition['native'].setdefault('subpartitions', []).append({key:value for key,value in record.items() if key.startswith('subpartition_')})
            for resource in resources.values():
                if resource['resource_kind'] != 'partition':
                    continue
                native = resource['native']
                allowed = ['inspect']
                if native.get('engine') == 'InnoDB':
                    allowed += ['analyze', 'check', 'optimize', 'rebuild', 'truncate']
                    if native.get('partition_method') in {'RANGE', 'RANGE COLUMNS', 'LIST', 'LIST COLUMNS'}:
                        allowed += ['drop', 'reorganize']
                    if not native.get('subpartitions'):
                        allowed += ['exchange']
                native['administration'] = {'allowed_operations': allowed}
        for schema_name, name, routine_type, data_type in optional(
            'SELECT ROUTINE_SCHEMA, ROUTINE_NAME, ROUTINE_TYPE, DATA_TYPE '
            "FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA NOT IN "
            "('information_schema', 'mysql', 'performance_schema', 'sys') "
            'ORDER BY 1, 2'
        ):
            kind = str(routine_type).lower()
            if kind in {'package', 'package body'} and (
                profile is MARIADB_PROFILE
            ):
                from .mariadb_catalog import identifier as quote_package
                part = 'package_body' if kind == 'package body' else 'package_specification'
                native = {'routine_type': 'PACKAGE', part: {
                    'routine_type': str(routine_type).upper(), 'data_type': data_type,
                    'show_create': optional_records('SHOW CREATE ' + str(routine_type).upper() + ' ' +
                        quote_package(schema_name) + '.' + quote_package(name))}}
                add('package', [schema_name], name, native)
                continue
            if kind not in {'procedure', 'function'}:
                continue
            add(kind, [schema_name], name, {'data_type': data_type})
        for schema_name, name, status, event_type in optional(
            'SELECT EVENT_SCHEMA, EVENT_NAME, STATUS, EVENT_TYPE '
            "FROM information_schema.EVENTS WHERE EVENT_SCHEMA NOT IN "
            "('information_schema', 'mysql', 'performance_schema', 'sys') "
            'ORDER BY 1, 2'
        ):
            add('event', [schema_name], name, {
                'status': status, 'event_type': event_type,
            })
        if profile is MYSQL_PROFILE:
            from .mysql_catalog import identifier as quote_event_identifier
            for record in optional_records("SELECT * FROM information_schema.EVENTS WHERE EVENT_SCHEMA NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys') ORDER BY EVENT_SCHEMA,EVENT_NAME"):
                record['show_create']=optional_records('SHOW CREATE EVENT '+quote_event_identifier(record['event_schema'])+'.'+quote_event_identifier(record['event_name']))
                add('event',[record['event_schema']],record['event_name'],record)
        roles = set()
        if profile is MYSQL_PROFILE:
            # MySQL stores role membership with the role on the FROM side.
            # The TO side is the user (or role) receiving that role.
            for user, host in optional(
                'SELECT DISTINCT FROM_USER, FROM_HOST FROM mysql.role_edges '
                'ORDER BY 1, 2'
            ):
                roles.add((str(user), str(host)))
                add('role', [], f'{user}@{host}', {
                    'user': str(user), 'host': str(host),
                }, identity=('mysql-role:' + json.dumps([str(user), str(host)], ensure_ascii=False, separators=(',', ':'))
                    if '@' in str(user) or '@' in str(host) else None))
            accounts = optional(
                'SELECT User, Host, account_locked FROM mysql.user '
                'ORDER BY 1, 2'
            )
        else:
            accounts = optional(
                'SELECT User, Host, is_role, plugin, password_expired, '
                'default_role, max_questions, max_updates, max_connections, '
                'max_user_connections, max_statement_time, ssl_type, '
                'ssl_cipher, x509_issuer, x509_subject FROM mysql.user '
                'ORDER BY 1, 2'
            )
            locked_accounts = {}
            for user, host, locked in optional(
                    "SELECT User, Host, COALESCE(JSON_VALUE(Priv,'$.account_locked'),'false') IN ('true','1') FROM mysql.global_priv"):
                locked_accounts[(str(user), str(host))] = bool(locked)
            for row in accounts:
                user, host, is_role = row[:3]
                if str(is_role).upper() == 'Y':
                    roles.add((str(user), str(host)))
                    add('role', [], str(user), {
                        'user': str(user), 'host': str(host),
                        'default_role': row[5],
                    })
        for row in accounts:
            user, host, account_state = row[:3]
            if (str(user), str(host)) not in roles:
                if profile is MYSQL_PROFILE:
                    native = {'account_locked': str(account_state), 'user': str(user), 'host': str(host)}
                else:
                    native = {
                        'user': str(user), 'host': str(host),
                        'is_role': str(account_state),
                        'authentication_plugin': row[3],
                        'password_expired': row[4],
                        'default_role': row[5],
                        'max_queries_per_hour': int(row[6] or 0),
                        'max_updates_per_hour': int(row[7] or 0),
                        'max_connections_per_hour': int(row[8] or 0),
                        'max_user_connections': int(row[9] or 0),
                        'max_statement_time': str(row[10] or 0),
                        'tls_requirement': row[11],
                        'tls_cipher': row[12],
                        'x509_issuer': row[13],
                        'x509_subject': row[14],
                        'account_locked': locked_accounts.get(
                            (str(user), str(host))
                        ),
                        'authentication_secrets_returned': False,
                    }
                add('user', [], f'{user}@{host}', native, identity=(
                    profile.engine_id + '-account:' + json.dumps([str(user), str(host)], ensure_ascii=False, separators=(',', ':'))
                    if '@' in str(user) or '@' in str(host) else None))
        for grantee, privilege in optional(
            'SELECT GRANTEE, PRIVILEGE_TYPE FROM information_schema.'
            'USER_PRIVILEGES ORDER BY 1, 2'
        ):
            add('privilege', [grantee], privilege, {
                'grantee': str(grantee), 'privilege': str(privilege),
                'scope': 'global', 'navigator_scope': 'server',
            })
        if profile in (MYSQL_PROFILE, MARIADB_PROFILE):
            from ..mysql_grants import QUERIES as scoped_grants, routine_grants
            for _section, scope, source, keys in scoped_grants:
                if scope == 'routine' and profile is MYSQL_PROFILE:
                    accounts = optional_records("SELECT User,Host,CONCAT(QUOTE(User),'@',QUOTE(Host)) AS grantee_identity FROM mysql.user ORDER BY User,Host")
                    records = routine_grants(accounts, optional_records)
                elif scope == 'routine':
                    from ..mariadb_grants import routine_grants as maria_routine_grants
                    principals = optional_records("SELECT User,Host,is_role,CONCAT(QUOTE(User),'@',QUOTE(Host)) AS grantee_identity FROM mysql.user ORDER BY User,Host")
                    records = maria_routine_grants(principals, optional_records)
                else:
                    records = optional_records(source)
                for record in records:
                    database = record['table_schema']
                    if selected_database and database != selected_database:
                        continue
                    if scope == 'routine':
                        path = [database, record['routine_name']]
                        owner_kind = record['routine_type'].lower()
                    elif scope in {'table', 'column'}:
                        path = [database, record['table_name']]
                        owner_kind = 'column' if scope == 'column' else 'table'
                        if scope == 'column':
                            path.append(record['column_name'])
                    else:
                        path = [database]
                        owner_kind = 'database'
                    name = record['grantee'] + ' / ' + record['privilege_type']
                    owner_id = resource_key(owner_kind, path[:-1], path[-1])
                    add('privilege', path, name, {**record, 'grantee': record['grantee'],
                        'privilege': record['privilege_type'], 'scope': scope, 'database': database,
                        'navigator_parent_resource_id': owner_id,
                        'administration': {'allowed_operations': ['inspect']}},
                        identity=profile.engine_id + '-grant:' + json.dumps([scope, *[record[key] for key in keys]], ensure_ascii=False, separators=(',', ':')))
        tablespace_source = (
            'SELECT DISTINCT TABLESPACE_NAME, ENGINE FROM '
            'information_schema.FILES WHERE TABLESPACE_NAME IS NOT NULL '
            'ORDER BY 1'
            if profile is MYSQL_PROFILE else
            "SELECT NAME, 'InnoDB' FROM information_schema."
            'INNODB_SYS_TABLESPACES ORDER BY NAME'
        )
        for name, engine in optional(tablespace_source):
            add('tablespace', [], name, {'engine': engine})
        plugin_rows = optional('SHOW PLUGINS')
        if profile is MYSQL_PROFILE:
            from .spatial_reference_systems import SELECT as srs_select, normalized as srs_normalized
            for row in optional(srs_select + ' ORDER BY SRS_ID'):
                add('spatial-reference-system', [], str(row[1]), {
                    **srs_normalized(row),
                    'has_organization': row[2] is not None,
                    'has_description': row[5] is not None,
                    'server_uuid': resources.get('server:MySQL', {}).get('native', {}).get('server_uuid'),
                })
            keyring_status = optional_records('SELECT STATUS_KEY, STATUS_VALUE FROM performance_schema.keyring_component_status')
            keyring_active = any(row.get('status_key') == 'Component_status' and row.get('status_value') == 'Active' for row in keyring_status) or any(
                str(row[0]).startswith('keyring_') and str(row[1]).upper() == 'ACTIVE' for row in plugin_rows)
            for record in optional_records(
                'SELECT s.NAME, s.SPACE_TYPE, s.STATE, s.ENCRYPTION, s.AUTOEXTEND_SIZE, '
                's.FILE_SIZE, s.ALLOCATED_SIZE, s.PAGE_SIZE, s.ZIP_PAGE_SIZE, '
                'e.ENGINE_ATTRIBUTE FROM information_schema.INNODB_TABLESPACES s '
                'LEFT JOIN information_schema.TABLESPACES_EXTENSIONS e ON e.TABLESPACE_NAME=s.NAME '
                'ORDER BY s.NAME'
            ):
                space_type = record['space_type']
                allowed = ['inspect']
                changes = []
                if space_type == 'General':
                    allowed += ['alter', 'rename', 'drop']
                    changes = ['AUTOEXTEND_SIZE', 'ENGINE_ATTRIBUTE'] + (['ENCRYPTION'] if keyring_active else [])
                elif space_type == 'Undo' and str(record['name']).lower() not in {'innodb_undo_001', 'innodb_undo_002'}:
                    allowed += ['alter', 'drop']
                    changes = ['ACTIVE', 'INACTIVE']
                add('tablespace', [], record['name'], {**record, 'engine': 'InnoDB',
                    'available_tablespace_changes': changes, 'keyring_observed_active': keyring_active,
                    'administration': {'allowed_operations': allowed}})
        if profile is MYSQL_PROFILE:
            for record in optional_records('SELECT component_id,component_group_id,component_urn FROM mysql.component ORDER BY component_id'):
                add('component',[],record['component_urn'],record)
        for name, status, plugin_type, library, license_name in plugin_rows:
            # MariaDB's uuid is both a DATA TYPE and a FUNCTION plugin.
            # Preserve native names for operations and distinct catalog IDs.
            identity = ('mariadb:plugin:' + json.dumps([name, plugin_type],
                ensure_ascii=False, separators=(',', ':'))) if profile is MARIADB_PROFILE else None
            add('plugin', [], name, {
                **({'plugin_name': name} if profile is MARIADB_PROFILE else {}),
                'status': status,
                'plugin_type': plugin_type,
                'library': library,
                'license': license_name,
            }, identity=identity)
        if profile is MYSQL_PROFILE:
            for record in optional_records("SELECT * FROM information_schema.LIBRARIES WHERE LIBRARY_SCHEMA NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys') ORDER BY LIBRARY_SCHEMA,LIBRARY_NAME"):
                from .mysql_catalog import identifier as quote_library_identifier
                record['show_create']=optional_records('SHOW CREATE LIBRARY '+quote_library_identifier(record['library_schema'])+'.'+quote_library_identifier(record['library_name']))
                add('library',[record['library_schema']],record['library_name'],record)
            functions={}
            for record in optional_records('SELECT name,ret,dl,type FROM mysql.func ORDER BY name'):
                name=record['name'];functions[name]={**record,'registration_origin':'mysql.func'}
            for record in optional_records('SELECT * FROM performance_schema.user_defined_functions ORDER BY UDF_NAME'):
                name=record['udf_name'];functions.setdefault(name,{'registration_origin':'runtime-service'}).update(record)
            for name,record in functions.items():
                record['administration']={'allowed_operations':['inspect','drop'] if record['registration_origin']=='mysql.func' else ['inspect']}
                add('loadable-function',[],name,record)
        if profile is MARIADB_PROFILE:
            for record in optional_records('SELECT name,ret,dl,type FROM mysql.func ORDER BY name'):
                record.update(registration_origin='mysql.func',
                              administration={'allowed_operations': ['inspect', 'drop']})
                add('loadable-function', [], record['name'], record)
        if profile is MYSQL_PROFILE and any(str(row[0]).lower()=='group_replication' and str(row[1]).upper()=='ACTIVE' for row in plugin_rows):
            members=optional_records('SELECT * FROM performance_schema.replication_group_members')
            stats=optional_records('SELECT * FROM performance_schema.replication_group_member_stats')
            group={'group_replication_plugin_status':'ACTIVE','members':members,'member_statistics':stats}
            for field,source in [('configuration','SELECT @@GLOBAL.group_replication_group_name AS group_name, @@GLOBAL.group_replication_single_primary_mode AS single_primary_mode'),
                *([('communication_protocol','SELECT group_replication_get_communication_protocol() AS value'),
                   ('write_concurrency','SELECT group_replication_get_write_concurrency() AS value')] if any(str(row.get('member_state')).upper()=='ONLINE' for row in members) else [])]:
                group[field]=optional_records(source)
            add('group-replication',[],'Group Replication',group)
            for member in members:
                if member.get('member_id'):add('group-replication-member',['Group Replication'],str(member['member_id']),member)
        replication_source = (
            'SELECT CHANNEL_NAME, HOST, PORT FROM performance_schema.'
            'replication_connection_configuration ORDER BY CHANNEL_NAME'
            if profile is MYSQL_PROFILE else
            'SELECT Connection_name, Master_host, Master_user, Master_port, '
            'Connect_retry, Master_log_file, Read_master_log_pos, '
            'Relay_log_file, Relay_log_pos, Slave_IO_running, '
            'Slave_SQL_running, Last_errno, Last_error, '
            'Seconds_behind_master, Master_SSL_allowed, '
            'Master_SSL_verify_server_cert, Using_Gtid, Gtid_IO_Pos, '
            'SQL_Delay, SQL_Remaining_Delay, Slave_heartbeat_period '
            'FROM information_schema.SLAVE_STATUS ORDER BY Connection_name'
        )
        for row in optional(replication_source):
            if profile is MYSQL_PROFILE:
                name, host, port = row
                native = {'channel_name': name, 'host': host, 'port': port,
                          'replication_password_returned': False,
                          **({'administration': {'allowed_operations': ['inspect']}}
                             if str(name).lower().startswith('group_replication_') else {})}
            else:
                name, host, user, port, *detail = row
                native = {
                    'host': host, 'user': user, 'port': port,
                    **dict(zip((
                        'connect_retry', 'master_log_file',
                        'read_master_log_position', 'relay_log_file',
                        'relay_log_position', 'io_running', 'sql_running',
                        'last_error_number', 'last_error',
                        'seconds_behind_master', 'ssl_allowed',
                        'verify_server_certificate', 'using_gtid',
                        'gtid_io_position', 'sql_delay',
                        'sql_remaining_delay', 'heartbeat_period',
                    ), detail)),
                    'replication_password_returned': False,
                }
                native = {
                    key: (str(value) if value is not None and not isinstance(
                        value, (str, int, float, bool)) else value)
                    for key, value in native.items()
                }
            if profile is MYSQL_PROFILE:
                from ..mysql_replication import channel_label
                name = channel_label(name)
            add('replication-channel', [], name, native)
        if profile is MYSQL_PROFILE:
            for query, observation in [
                ('SELECT CHANNEL_NAME, SERVICE_STATE, SOURCE_UUID, RECEIVED_TRANSACTION_SET, LAST_ERROR_NUMBER, LAST_ERROR_TIMESTAMP FROM performance_schema.replication_connection_status', 'receiver'),
                ('SELECT CHANNEL_NAME, SERVICE_STATE, REMAINING_DELAY, COUNT_TRANSACTIONS_RETRIES FROM performance_schema.replication_applier_status', 'applier'),
            ]:
                for record in optional_records(query):
                    name = record['channel_name']
                    key = resource_key('replication-channel', [], channel_label(name))
                    if key in resources:
                        resources[key]['native'][observation] = record
        if profile is MYSQL_PROFILE:
            from .foreign_servers import SELECT as foreign_select, normalized as foreign_normalized
            for record in optional_records(foreign_select + ' ORDER BY Server_name'):
                record = foreign_normalized(record)
                record['server_uuid'] = resources.get('server:MySQL', {}).get('native', {}).get('server_uuid')
                add('server-link', [], record['server_name'], record)
            for record in optional_records(
                'SELECT t.THREAD_ID, t.PROCESSLIST_ID, t.PROCESSLIST_USER, t.PROCESSLIST_HOST, '
                't.PROCESSLIST_DB, t.PROCESSLIST_COMMAND, t.PROCESSLIST_TIME, t.PROCESSLIST_STATE, '
                't.RESOURCE_GROUP FROM performance_schema.threads t '
                'WHERE t.PROCESSLIST_ID IS NOT NULL ORDER BY t.PROCESSLIST_ID'
            ):
                record['processlist_id'] = str(record['processlist_id'])
                record['thread_id'] = str(record['thread_id'])
                add('session', ['Sessions'], record['processlist_id'], record)
            from .system_variables import SELECT as variables_select, administration as variable_administration
            for record in optional_records(variables_select):
                allowed = variable_administration(record)
                add('system-variable', ['Configuration'], record['variable_name'],
                    {**record, **({'administration': allowed} if allowed is not None else {})})
        if profile is MYSQL_PROFILE:
            for name, resource_type, enabled in optional(
                'SELECT RESOURCE_GROUP_NAME, RESOURCE_GROUP_TYPE, '
                'RESOURCE_GROUP_ENABLED '
                'FROM information_schema.RESOURCE_GROUPS '
                'ORDER BY RESOURCE_GROUP_NAME'
            ):
                add('resource-group', [], name, {
                    'resource_type': resource_type, 'enabled': enabled,
                })
        else:
            for record in optional_records(
                'SELECT Server_name, Host, Db, Username, Port, Socket, Wrapper, Owner '
                'FROM mysql.servers ORDER BY Server_name'
            ):
                add('server-link', [], record['server_name'],
                    {**record, 'database': record['db']})
            for record in optional_records(
                'SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE, INFO, '
                'TIME_MS, STAGE, MAX_STAGE, PROGRESS, MEMORY_USED, '
                'MAX_MEMORY_USED, EXAMINED_ROWS, SENT_ROWS, QUERY_ID, TID, '
                'TMP_SPACE_USED FROM information_schema.PROCESSLIST '
                'ORDER BY ID'
            ):
                add('session', ['Sessions'], record['id'], record)
            for record in optional_records(
                'SELECT VARIABLE_NAME, SESSION_VALUE, GLOBAL_VALUE, '
                'GLOBAL_VALUE_ORIGIN, DEFAULT_VALUE, VARIABLE_SCOPE, '
                'VARIABLE_TYPE, VARIABLE_COMMENT, NUMERIC_MIN_VALUE, '
                'NUMERIC_MAX_VALUE, NUMERIC_BLOCK_SIZE, ENUM_VALUE_LIST, '
                'READ_ONLY, COMMAND_LINE_ARGUMENT, GLOBAL_VALUE_PATH '
                'FROM information_schema.SYSTEM_VARIABLES '
                'ORDER BY VARIABLE_NAME'
            ):
                add(
                    'system-variable', ['Configuration'],
                    record['variable_name'], record,
                )
            for record in optional_records(
                'SELECT lock_id, lock_trx_id, lock_mode, lock_type, '
                'lock_table, lock_index, lock_space, lock_page, lock_rec, '
                'lock_data FROM information_schema.INNODB_LOCKS '
                'ORDER BY lock_id'
            ):
                add('lock', ['Locks'], record['lock_id'], record)
            for record in optional_records(
                'SELECT requesting_trx_id, requested_lock_id, '
                'blocking_trx_id, blocking_lock_id FROM '
                'information_schema.INNODB_LOCK_WAITS '
                'ORDER BY requesting_trx_id, blocking_trx_id'
            ):
                name = (
                    f"{record['requesting_trx_id']} -> "
                    f"{record['blocking_trx_id']}"
                )
                add('lock-wait', ['Lock waits'], name, record)
            for record in optional_records(
                'SELECT TABLE_SCHEMA, TABLE_NAME, ENGINE, TABLE_ROWS, '
                'DATA_LENGTH, INDEX_LENGTH, DATA_FREE, AUTO_INCREMENT, '
                'CREATE_TIME, UPDATE_TIME, CHECK_TIME, TABLE_COLLATION, '
                'CHECKSUM, CREATE_OPTIONS, TABLE_COMMENT, MAX_INDEX_LENGTH, '
                'TEMPORARY FROM information_schema.TABLES WHERE '
                "TABLE_SCHEMA NOT IN ('information_schema', 'mysql', "
                "'performance_schema', 'sys') ORDER BY TABLE_SCHEMA, "
                'TABLE_NAME'
            ):
                add(
                    'table-storage', [record['table_schema']],
                    record['table_name'], record,
                )
            binary_logs = optional_records('SHOW BINARY LOGS')
            for record in binary_logs:
                name = record.get('log_name') or record.get('file')
                if name:
                    add('binary-log', [], name, record)
                    escaped_name = str(name).replace("'", "''")
                    for event in optional_records(
                        "SHOW BINLOG EVENTS IN '" + escaped_name +
                        "' LIMIT 200"
                    ):
                        event_name = (
                            f"{event.get('pos')} / "
                            f"{event.get('event_type')}"
                        )
                        add(
                            'binary-log-event',
                            [name], event_name, {
                                **event,
                                'navigator_parent_resource_id':
                                    f'binary-log:{name}',
                            },
                        )
            for record in optional_records('SHOW BINLOG STATUS'):
                name = record.get('file') or 'Current binary log position'
                add('binary-log-status', [], name, record)
            log_values = {
                record['variable_name']: record['global_value']
                for record in optional_records(
                    'SELECT VARIABLE_NAME, GLOBAL_VALUE FROM '
                    'information_schema.SYSTEM_VARIABLES WHERE '
                    "VARIABLE_NAME IN ('GENERAL_LOG', 'GENERAL_LOG_FILE', "
                    "'SLOW_QUERY_LOG', 'SLOW_QUERY_LOG_FILE', "
                    "'LOG_OUTPUT') ORDER BY VARIABLE_NAME"
                )
            }
            add(
                'log-configuration', ['Logs'], 'Server log configuration',
                log_values,
            )
            for record in optional_records(
                'SELECT event_time, user_host, thread_id, server_id, '
                'command_type, argument FROM mysql.general_log '
                'ORDER BY event_time DESC LIMIT 200'
            ):
                name = f"{record['event_time']} / {record['thread_id']}"
                add('general-log-entry', ['Logs', 'General log'], name, record)
            for record in optional_records(
                'SELECT start_time, user_host, query_time, lock_time, '
                'rows_sent, rows_examined, db, last_insert_id, insert_id, '
                'server_id, sql_text, thread_id, rows_affected FROM '
                'mysql.slow_log ORDER BY start_time DESC LIMIT 200'
            ):
                name = f"{record['start_time']} / {record['thread_id']}"
                add('slow-query', ['Logs', 'Slow query log'], name, record)
            tls_values = {
                record['variable_name']: record['global_value']
                for record in optional_records(
                    'SELECT VARIABLE_NAME, GLOBAL_VALUE FROM '
                    'information_schema.SYSTEM_VARIABLES WHERE '
                    "VARIABLE_NAME IN ('HAVE_SSL', 'HAVE_OPENSSL', "
                    "'SSL_CA', 'SSL_CERT', 'SSL_KEY', 'TLS_VERSION') "
                    'ORDER BY VARIABLE_NAME'
                )
            }
            add(
                'tls-configuration', ['Security'],
                'TLS configuration', tls_values,
            )
        if profile in (MYSQL_PROFILE, MARIADB_PROFILE):
            for kind, source, name_field in (
                ('character-set', 'SELECT CHARACTER_SET_NAME, DEFAULT_COLLATE_NAME, DESCRIPTION, MAXLEN FROM information_schema.CHARACTER_SETS', 'character_set_name'),
                ('collation', 'SELECT COLLATION_NAME, CHARACTER_SET_NAME, ID, IS_DEFAULT, IS_COMPILED, SORTLEN' + (', PAD_ATTRIBUTE' if profile is MYSQL_PROFILE else '') + ' FROM information_schema.COLLATIONS', 'collation_name'),
                ('storage-engine', 'SELECT ENGINE, SUPPORT, COMMENT, TRANSACTIONS, XA, SAVEPOINTS FROM information_schema.ENGINES', 'engine'),
            ):
                for record in optional_records(source):
                    add(kind, [], record[name_field], {**record, 'system_object': True,
                        'administration': {'allowed_operations': ['inspect']}})
        status_source = (
            'SELECT VARIABLE_NAME, VARIABLE_VALUE FROM '
            'performance_schema.global_status'
            if profile is MYSQL_PROFILE else
            'SELECT VARIABLE_NAME, VARIABLE_VALUE FROM '
            'information_schema.GLOBAL_STATUS'
        )
        values = {
            str(name).upper(): value
            for name, value in optional(status_source)
        }
        for metric in _metric_records(profile):
            native_name = metric['native_name']
            add('metric', ['Metrics'], native_name, {
                **metric,
                'value': (
                    None if native_name.upper() not in values else
                    str(values[native_name.upper()])
                ),
                'observation_error': (
                    None if native_name.upper() in values else
                    'metric_absent_from_exact_runtime'
                ),
            })
        definition_kinds = {
            'database', 'table', 'view', 'materialized-view', 'column',
            'index', 'constraint', 'trigger', 'partition', 'procedure',
            'function', 'event', 'sequence', 'package', 'tablespace',
            'plugin', 'component', 'library', 'loadable-function', 'resource-group', 'server-link', 'spatial-reference-system', 'system-variable',
            'log-configuration', 'tls-configuration',
        }
        state_kinds = {
            'server', 'replication-channel', 'group-replication', 'group-replication-member', 'session', 'lock', 'lock-wait',
            'binary-log-status',
        }
        data_kinds = {
            'binary-log', 'binary-log-event', 'general-log-entry',
            'slow-query',
        }
        security_kinds = {'user', 'role', 'privilege'}
        for resource in resources.values():
            native = resource.setdefault('native', {})
            owner = native.get('navigator_parent_resource_id')
            if (resource['resource_kind'] == 'privilege' and
                    native.get('scope') != 'global' and owner not in resources):
                # Grants may survive DROP or refer to an object not visible to
                # this account. Keep their exact facts reachable at database scope.
                database = native['database']
                native.update(object_visible=False,
                    navigator_parent_resource_id=resource_key('database', [], database))
                address = native.get('routine_name') or native.get('table_name') or database
                resource['display_name'] = native['scope'] + ': ' + address + ' / ' + resource['display_name']
                resource['display_path'] = [database, resource['display_name']]
            snapshot = copy.deepcopy(native)
            kind = resource['resource_kind']
            if kind in definition_kinds:
                native['definition'] = snapshot
            elif kind in state_kinds:
                native['state'] = snapshot
            elif kind in data_kinds:
                native['data'] = snapshot
            elif kind == 'table-storage':
                native['statistics'] = snapshot
            elif kind == 'metric':
                native['statistics'] = snapshot
            elif kind in security_kinds:
                native['security'] = snapshot
                if kind == 'privilege':
                    native['privileges'] = [snapshot]
        annotate_relation_ownership(list(resources.values()))
        coverage = {
            'state': 'partial' if catalog_failures else 'queried',
            'complete_native_inventory': False,
            'failed_query_count': len(catalog_failures),
            'failures': catalog_failures,
            **({'unavailable': catalog_unavailable} if catalog_unavailable else {}),
        }
        for resource in resources.values():
            if resource['resource_kind'] in {'server', 'database'}:
                resource.setdefault('native', {})['catalog_coverage'] = (
                    copy.deepcopy(coverage))
            elif catalog_failures:
                # An object selection must not hide the endpoint's limited
                # visibility. Avoid copying the full failure list per column.
                resource.setdefault('native', {})['catalog_coverage'] = {
                    'state': 'partial', 'scope': 'endpoint-catalog',
                    'failed_query_count': len(catalog_failures),
                    'complete_native_inventory': False,
                    'details_resource_id': f'server:{profile.engine_name}',
                }
        if selected_database is None:
            return list(resources.values())
        database_scoped = {
            'database', 'table', 'view', 'materialized-view', 'column',
            'index', 'constraint', 'trigger', 'partition', 'procedure',
            'function', 'event', 'sequence', 'package', 'library',
            'table-storage',
        }
        return [
            resource for resource in resources.values()
            if resource['resource_kind'] not in database_scoped or (
                resource['display_name'] == selected_database
                if resource['resource_kind'] == 'database' else
                bool(resource['display_path']) and
                resource['display_path'][0] == selected_database
            )
        ]
    finally:
        cursor.close()


def _security(connection, request):
    cursor = connection.cursor()
    try:
        cursor.execute('SELECT CURRENT_USER(), USER()')
        current_user, session_user = cursor.fetchone()
        generation = str(request.get('capability_generation') or 'current')
        return {
            'resource_id': f'authorization:{current_user}',
            'display_name': str(current_user),
            'authority_path': ['authorization', str(current_user)],
            'generation': generation,
            'native': {
                'current_user': str(current_user),
                'session_user': str(session_user),
            },
        }
    finally:
        cursor.close()


def _create_client(profile, permissions, context):
    mysql_values = None
    if profile is MYSQL_PROFILE:
        from pgadmin.cdeadmin.sdk import load_optional_module
        load_optional_module('mysql.connector')
        from . import mysql_values
    module_name = (
        'mysql.connector' if profile is MYSQL_PROFILE else 'mariadb'
    )
    config = RelationalClientConfig(
        profile=profile,
        module_name=module_name,
        version_query='SELECT VERSION()',
        version_parser=_version,
        connect_arguments=lambda route: _route_arguments(route, profile),
        metadata_reader=lambda connection, request: _resources(
            connection, request, profile
        ),
        security_reader=_security,
        credential_arguments=(
            {
                'database_password': 'password',
                'database_password_2': 'password2',
                'database_password_3': 'password3',
            }
            if profile is MYSQL_PROFILE else
            {'database_password': 'password'}
        ),
        secret_acquirer=permissions.acquire_secret,
        connection_initializer=(
            _initialize_mysql_connection if profile is MYSQL_PROFILE
            else _initialize_connection),
        query_parameter_normalizer=(
            mysql_values.parameters if profile is MYSQL_PROFILE else None),
        query_columns_reader=(
            mysql_values.columns if profile is MYSQL_PROFILE else None),
        administration=(
            MYSQL_ADMINISTRATION if profile is MYSQL_PROFILE
            else MARIADB_ADMINISTRATION
        ),
    )
    if profile is MARIADB_PROFILE:
        return MariaDBDBAPIClient(
            config, context.pool_namespace
        )
    return MySQLDBAPIClient(config)


def create_provider(context, permissions, client=None):
    providers = {
        MYSQL_PROFILE.profile_id: MySQLPilotProvider,
        MARIADB_PROFILE.profile_id: MariaDBPilotProvider,
    }
    provider_type = providers[context.profile_id]
    return provider_type(
        context, permissions, client or _create_client(
            MYSQL_PROFILE if provider_type is MySQLPilotProvider
            else MARIADB_PROFILE,
            permissions,
            context,
        )
    )
