"""MariaDB native information_schema.ALL_PLUGINS discovery, classification and inspection.

Distinguishes installed ACTIVE plugins from uninstalled-but-available plugin
libraries reported by MariaDB's ALL_PLUGINS catalog view, while keeping MariaDB
Community open-source modules (PAM, GSSAPI, ed25519, parsec, file_key_management,
server_audit, storage engines, compression and data-type plugins) accurately
classified and never mislabeled as MySQL Enterprise.
"""
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
import json
import re

from ...sdk import RelationalClientError
from .mariadb_server_diagnostics import environment, form, target_uid
from .mysql_engine_diagnostics import observer_route, release

KEY = 'mariadb_available_plugins'
KIND = 'available-plugin'
OPERATIONS = {
    'inspect_available_plugins': ('Inspect available plugin modules', 'ALL_PLUGINS'),
}
INSPECTIONS = {'inspect_available_plugins'}
READS = frozenset({'inspect_available_plugins'})

ALL_PLUGINS_COLUMNS = (
    'plugin_name',
    'plugin_version',
    'plugin_status',
    'plugin_type',
    'plugin_type_version',
    'plugin_library',
    'plugin_library_version',
    'plugin_author',
    'plugin_description',
    'plugin_license',
    'load_option',
    'plugin_maturity',
    'plugin_auth_version',
)

ALL_PLUGINS_SELECT = (
    'SELECT PLUGIN_NAME, PLUGIN_VERSION, PLUGIN_STATUS, PLUGIN_TYPE, '
    'PLUGIN_TYPE_VERSION, PLUGIN_LIBRARY, PLUGIN_LIBRARY_VERSION, '
    'PLUGIN_AUTHOR, PLUGIN_DESCRIPTION, PLUGIN_LICENSE, LOAD_OPTION, '
    'PLUGIN_MATURITY, PLUGIN_AUTH_VERSION '
    'FROM information_schema.ALL_PLUGINS '
    'ORDER BY PLUGIN_NAME, PLUGIN_TYPE'
)

SERVER_CATALOG_ALL_PLUGINS_SELECT = (
    'SELECT PLUGIN_NAME, PLUGIN_VERSION, PLUGIN_STATUS, PLUGIN_TYPE, '
    "PLUGIN_LIBRARY, COALESCE(PLUGIN_LIBRARY, 'builtin') AS PLUGIN_LIBRARY_IDENTITY, "
    "COALESCE(PLUGIN_VERSION, '') AS PLUGIN_VERSION_IDENTITY, "
    'PLUGIN_LICENSE, LOAD_OPTION, PLUGIN_MATURITY '
    'FROM information_schema.ALL_PLUGINS '
    'ORDER BY PLUGIN_NAME, PLUGIN_TYPE, PLUGIN_LIBRARY_IDENTITY, PLUGIN_VERSION_IDENTITY'
)

TEST_EXAMPLE_PLUGINS = frozenset({
    'audit_null',
    'auth_0x0100',
    'dialog',
    'dialog_examples',
    'test_plugin',
    'qa_auth_interface',
    'qa_auth_server',
    'qa_auth_client',
    'daemon_example',
    'debug_key_management',
    'example_key_management',
    'ftexample',
    'type_test',
    'func_test',
})

COMMUNITY_PRODUCTION_FAMILIES = {
    'AUTHENTICATION': frozenset({
        'ed25519', 'auth_ed25519', 'pam', 'auth_pam', 'auth_pam_v1',
        'auth_gssapi', 'gssapi', 'auth_parsec', 'parsec', 'unix_socket',
        'auth_socket', 'auth_named_pipe', 'mysql_native_password',
        'mysql_old_password', 'auth_mysql_sha2', 'caching_sha2_password',
    }),
    'ENCRYPTION': frozenset({
        'file_key_management', 'aws_key_management', 'hashicorp_key_management',
    }),
    'AUDIT': frozenset({
        'server_audit', 'server_audit2', 'sql_error_log',
    }),
    'PASSWORD VALIDATION': frozenset({
        'simple_password_check', 'cracklib_password_check', 'password_reuse_check',
    }),
    'STORAGE ENGINE': frozenset({
        'innodb', 'aria', 'myisam', 'memory', 'csv', 'mrg_myisam', 'archive',
        'blackhole', 'federated', 'federatedx', 'sequence', 'connect',
        'spider', 'mroonga', 'oqgraph', 'rocksdb', 's3', 'columnstore',
        'perfschema', 'binlog', 'partition',
    }),
}


def classify_plugin(record):
    """Return MariaDB-native availability and module classification metadata."""
    name = str(record.get('plugin_name') or '')
    lowered = name.lower()
    status = str(record.get('plugin_status') or record.get('status') or '').upper()
    plugin_type = str(record.get('plugin_type') or '').upper()
    library = record.get('plugin_library') if 'plugin_library' in record else record.get('library')
    license_name = record.get('plugin_license') if 'plugin_license' in record else record.get('license')
    load_option = record.get('load_option')
    maturity = record.get('plugin_maturity')

    is_test_example = lowered in TEST_EXAMPLE_PLUGINS or (
        isinstance(library, str) and any(
            marker in library.lower()
            for marker in ('example', 'qa_auth', 'test_plugin', 'debug_key_management', 'audit_null')
        )
    )
    installed = status == 'ACTIVE'
    compiled_in = library is None or library == ''
    available_uninstalled = not installed and not compiled_in

    if is_test_example:
        module_category = 'test_example'
        production_supported = False
    else:
        module_category = 'production'
        production_supported = True

    community_family = None
    for family, names in COMMUNITY_PRODUCTION_FAMILIES.items():
        if lowered in names or plugin_type == family and not is_test_example:
            community_family = family.lower().replace(' ', '_')
            break

    return {
        'plugin_name': name,
        'plugin_type': record.get('plugin_type'),
        'plugin_status': status or None,
        'plugin_version': record.get('plugin_version'),
        'plugin_type_version': record.get('plugin_type_version'),
        'plugin_library': library,
        'plugin_library_version': record.get('plugin_library_version'),
        'plugin_author': record.get('plugin_author'),
        'plugin_description': record.get('plugin_description'),
        'plugin_license': license_name,
        'load_option': load_option,
        'plugin_maturity': maturity,
        'plugin_auth_version': record.get('plugin_auth_version'),
        'installed': installed,
        'compiled_in': compiled_in,
        'available_uninstalled': available_uninstalled,
        'install_eligible': bool(available_uninstalled and production_supported),
        'uninstall_eligible': bool(installed and not compiled_in and str(load_option or '').upper() != 'FORCE_PLUS_PERMANENT'),
        'module_category': module_category,
        'production_supported': production_supported,
        'community_family': community_family,
        'edition_classification': (
            'mariadb-test-example-excluded' if is_test_example
            else 'mariadb-community-open-source'
        ),
        'mysql_enterprise_reclassified': False,
    }


def available_plugin_identity(name, plugin_type, library=None, version=None):
    parts = [str(name), str(plugin_type)]
    if library is not None or version is not None:
        parts.extend([str(library or 'builtin'), str(version or '')])
    return 'mariadb:available-plugin:' + json.dumps(
        parts,
        ensure_ascii=False,
        separators=(',', ':'),
    )


def discover_catalog_plugins(optional_records, add, *, server_uid=None):
    """Populate available-plugin resources from information_schema.ALL_PLUGINS and enrich plugin rows."""
    rows = optional_records(ALL_PLUGINS_SELECT)
    by_pair = {}
    for record in rows:
        classified = classify_plugin(record)
        pair = (str(record.get('plugin_name') or ''), str(record.get('plugin_type') or ''))
        if pair not in by_pair or classified['installed']:
            by_pair[pair] = classified
        native = {
            **record,
            **classified,
            'status': classified['plugin_status'],
            'library': classified['plugin_library'],
            'license': classified['plugin_license'],
            'catalog_source': 'information_schema.ALL_PLUGINS',
            'administration': {'allowed_operations': ['inspect']},
        }
        if server_uid:
            native['server_uid'] = server_uid
        lib = record.get('plugin_library')
        label = (
            f"{pair[0]} ({pair[1]} · {lib})" if pair[1] and lib
            else f"{pair[0]} ({pair[1]})" if pair[1]
            else pair[0]
        )
        add(
            'available-plugin',
            [],
            label,
            native,
            identity=available_plugin_identity(
                pair[0],
                pair[1],
                library=lib,
                version=record.get('plugin_version'),
            ),
        )
    return by_pair


def compile_operation(operation, draft, target):
    uid = target_uid(target)
    if operation != 'inspect_available_plugins' or not isinstance(draft, Mapping):
        raise RelationalClientError('Select the MariaDB available-plugin inspection operation')
    draft = dict(draft)
    allowed = {
        'status_filter',
        'status_scope',
        'plugin_type',
        'include_test_modules',
        'include_test_examples',
        'confirmation',
    }
    if set(draft) - allowed:
        raise RelationalClientError('Unknown MariaDB available-plugin inspection option')
    if draft.get('confirmation') not in (None, '') and draft.get('confirmation') != target.get('display_name'):
        raise RelationalClientError('Confirm the selected MariaDB server name')
    if 'status_filter' in draft and 'status_scope' in draft and draft['status_filter'] != draft['status_scope']:
        raise RelationalClientError('Conflicting MariaDB plugin status filter options')
    raw_status = draft.get('status_filter', draft.get('status_scope', 'ALL'))
    if raw_status not in {'ALL', 'ACTIVE', 'INSTALLED', 'INACTIVE', 'UNINSTALLED_AVAILABLE'}:
        raise RelationalClientError(
            'Select ALL, INSTALLED, ACTIVE, UNINSTALLED_AVAILABLE or INACTIVE plugin status filter'
        )
    status_scope = 'ACTIVE' if raw_status == 'INSTALLED' else raw_status

    plugin_type = draft.get('plugin_type', '')
    if plugin_type is None:
        plugin_type = ''
    if not isinstance(plugin_type, str) or '\x00' in plugin_type or len(plugin_type) > 64:
        raise RelationalClientError('Plugin type filter must be bounded text without NUL')
    plugin_type = plugin_type.strip()
    if plugin_type.upper() == 'ALL':
        plugin_type = ''
    if plugin_type and not re.fullmatch(r'[A-Za-z0-9 _-]+', plugin_type):
        raise RelationalClientError('Plugin type filter contains unsupported characters')

    if (
        'include_test_modules' in draft
        and 'include_test_examples' in draft
        and draft['include_test_modules'] != draft['include_test_examples']
    ):
        raise RelationalClientError('Conflicting MariaDB test/example module filter options')
    include_examples = draft.get('include_test_modules', draft.get('include_test_examples', False))
    if type(include_examples) is not bool:
        raise RelationalClientError('Test/example module inclusion must be boolean')

    conditions = []
    parameters = []
    if status_scope == 'ACTIVE':
        conditions.append("PLUGIN_STATUS = 'ACTIVE'")
    elif status_scope == 'UNINSTALLED_AVAILABLE':
        conditions.append("PLUGIN_STATUS <> 'ACTIVE' AND PLUGIN_LIBRARY IS NOT NULL AND PLUGIN_LIBRARY <> ''")
    elif status_scope == 'INACTIVE':
        conditions.append("PLUGIN_STATUS <> 'ACTIVE'")
    if plugin_type:
        conditions.append('UPPER(PLUGIN_TYPE) = %s')
        parameters.append(plugin_type.upper())
    where = (' WHERE ' + ' AND '.join(conditions)) if conditions else ''
    sql = (
        'SELECT PLUGIN_NAME, PLUGIN_VERSION, PLUGIN_STATUS, PLUGIN_TYPE, '
        'PLUGIN_TYPE_VERSION, PLUGIN_LIBRARY, PLUGIN_LIBRARY_VERSION, '
        'PLUGIN_AUTHOR, PLUGIN_DESCRIPTION, PLUGIN_LICENSE, LOAD_OPTION, '
        'PLUGIN_MATURITY, PLUGIN_AUTH_VERSION '
        'FROM information_schema.ALL_PLUGINS' + where +
        ' ORDER BY PLUGIN_NAME, PLUGIN_TYPE'
    )
    return {
        'statements': [{'source': sql, 'parameters': tuple(parameters)}],
        KEY: {
            'operation': operation,
            'server_uid': uid,
            'target_display_name': target.get('display_name'),
            'status_scope': status_scope,
            'plugin_type': plugin_type,
            'include_test_examples': include_examples,
            'draft': deepcopy(draft),
        },
        'warnings': [
            'Reads information_schema.ALL_PLUGINS on an independent connection without modifying loaded plugins.',
            'Uninstalled plugin libraries remain gated by host plugin_dir binaries, runtime configuration and INSTALL SONAME/PLUGIN review.',
        ],
    }


def _observe_plugins(cursor, intent):
    cursor.execute('SELECT @@GLOBAL.plugin_dir, @@GLOBAL.plugin_maturity')
    plugin_dir, maturity_threshold = cursor.fetchone()
    statement_sql = (
        'SELECT PLUGIN_NAME, PLUGIN_VERSION, PLUGIN_STATUS, PLUGIN_TYPE, '
        'PLUGIN_TYPE_VERSION, PLUGIN_LIBRARY, PLUGIN_LIBRARY_VERSION, '
        'PLUGIN_AUTHOR, PLUGIN_DESCRIPTION, PLUGIN_LICENSE, LOAD_OPTION, '
        'PLUGIN_MATURITY, PLUGIN_AUTH_VERSION '
        'FROM information_schema.ALL_PLUGINS'
    )
    conditions = []
    params = []
    if intent['status_scope'] == 'ACTIVE':
        conditions.append("PLUGIN_STATUS = 'ACTIVE'")
    elif intent['status_scope'] == 'UNINSTALLED_AVAILABLE':
        conditions.append("PLUGIN_STATUS <> 'ACTIVE' AND PLUGIN_LIBRARY IS NOT NULL AND PLUGIN_LIBRARY <> ''")
    elif intent['status_scope'] == 'INACTIVE':
        conditions.append("PLUGIN_STATUS <> 'ACTIVE'")
    if intent['plugin_type']:
        conditions.append('UPPER(PLUGIN_TYPE) = %s')
        params.append(intent['plugin_type'].upper())
    if conditions:
        statement_sql += ' WHERE ' + ' AND '.join(conditions)
    statement_sql += ' ORDER BY PLUGIN_NAME, PLUGIN_TYPE'
    if params:
        cursor.execute(statement_sql, tuple(params))
    else:
        cursor.execute(statement_sql)
    raw_rows = cursor.fetchall()
    if len(raw_rows) > 5000:
        raise RelationalClientError('ALL_PLUGINS inventory exceeds the native observation bound')
    items = []
    excluded_test_count = 0
    for row in raw_rows:
        record = dict(zip(ALL_PLUGINS_COLUMNS, row))
        classified = classify_plugin(record)
        if classified['module_category'] == 'test_example' and not intent['include_test_examples']:
            excluded_test_count += 1
            continue
        items.append(classified)
    return {
        'plugin_dir': plugin_dir,
        'plugin_maturity_policy': maturity_threshold,
        'status_scope': intent['status_scope'],
        'plugin_type_filter': intent['plugin_type'] or None,
        'include_test_examples': intent['include_test_examples'],
        'excluded_test_example_count': excluded_test_count,
        'total_returned': len(items),
        'returned_count': len(items),
        'active_count': sum(1 for item in items if item['installed']),
        'available_uninstalled_count': sum(1 for item in items if item['available_uninstalled']),
        'compiled_in_count': sum(1 for item in items if item['compiled_in']),
        'summary': {
            'total_observed': len(items) + excluded_test_count,
            'active_count': sum(1 for item in items if item['installed']),
            'available_uninstalled_count': sum(1 for item in items if item['available_uninstalled']),
            'excluded_test_example_count': excluded_test_count,
        },
        'rows': items,
        'plugins': items,
    }


def bind_review(client, planned):
    payload = planned['provider_payload']
    intent = payload['compiled'][KEY]
    handle = client._connect({'route': observer_route(payload)})
    cursor = None
    try:
        handle.autocommit = True
        cursor = handle.cursor()
        env = environment(cursor)
        if env['server_uid'] != intent['server_uid']:
            raise RelationalClientError('Native MariaDB server_uid changed before review')
        summary = _observe_plugins(cursor, intent)
        intent['review'] = {
            'environment': env,
            'active_count': summary['active_count'],
            'available_uninstalled_count': summary['available_uninstalled_count'],
        }
        planned['command_preview'].update(
            native_execution_identity=env,
            available_plugins_preview={
                'active_count': summary['active_count'],
                'available_uninstalled_count': summary['available_uninstalled_count'],
                'excluded_test_example_count': summary['excluded_test_example_count'],
            },
        )
        return planned
    finally:
        release(client, handle, cursor)


def apply(client, request, connection=None):
    if connection is not None:
        raise RelationalClientError('Available-plugin inspection requires an independently owned connection')
    payload = request['provider_payload']
    compiled = payload['compiled']
    intent = compiled[KEY]
    review = intent.get('review')
    if not isinstance(review, Mapping):
        raise RelationalClientError('Review the available-plugin inspection before execution')
    expected = compile_operation(
        intent['operation'],
        intent['draft'],
        {
            'resource_kind': 'server',
            'resource_id': 'server:MariaDB',
            'display_path': ['MariaDB'],
            'display_name': intent['target_display_name'],
            'native': {'server_uid': intent['server_uid']},
        },
    )
    candidate = deepcopy(compiled)
    candidate[KEY].pop('review', None)
    if expected != candidate:
        raise RelationalClientError('Reviewed available-plugin inspection changed')

    handle = client._connect({'route': observer_route(payload)})
    cursor = None
    dispatched = acknowledged = False
    try:
        handle.autocommit = True
        cursor = handle.cursor()
        env = environment(cursor)
        if env['server_uid'] != intent['server_uid']:
            raise RelationalClientError('Native MariaDB server_uid changed since review')
        dispatched = True
        observed = _observe_plugins(cursor, intent)
        acknowledged = True
        return {
            'accepted': True,
            'native_acknowledged': True,
            'native_implicit_commit': False,
            'commit_requested': False,
            'rollback_requested': False,
            'staged_in_provider_session': False,
            'automatic_retry': False,
            'driver_observation_only': True,
            'transaction_finality_interpreted_by_common_code': False,
            'observed_at': datetime.now(timezone.utc).isoformat(),
            'execution_identity': env,
            'available_plugins': observed,
            'available_plugins_observation': observed,
        }
    except Exception as error:
        failure = error if isinstance(error, RelationalClientError) else RelationalClientError(
            f'MariaDB ALL_PLUGINS inspection failed ({type(error).__name__})'
        )
        failure.native_dispatched = dispatched
        failure.native_acknowledged = acknowledged
        failure.automatic_retry = False
        failure.errno = getattr(error, 'errno', None)
        failure.sqlstate = getattr(error, 'sqlstate', None)
        raise failure from None
    finally:
        release(client, handle, cursor)
