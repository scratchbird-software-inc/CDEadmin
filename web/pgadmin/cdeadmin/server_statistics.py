##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Provider-neutral connector, server, and database statistics assembly."""

from __future__ import annotations

import ctypes
import json
import os

from pgadmin.cdeadmin.navigator import resource_native

try:
    from flask_babel import gettext
except ImportError:  # pragma: no cover - lightweight test fallback
    def gettext(value, **kwargs):
        return value % kwargs if kwargs else value


AUTH_STATS_MESSAGE = (
    'You will need to authenticate and connect the server or a database on '
    'that server to see the statistics.'
)


def firebird_client_statistics():
    """Return local Firebird client library details without any connection."""
    rows = []
    try:
        import firebird.driver as fb_driver
        from pgadmin.cdeadmin.providers.firebird.provider import (
            _configure_client_library,
        )
        _configure_client_library(fb_driver)
        api = fb_driver.get_api()
        func = api.client_library.isc_get_client_version
        func.argtypes = [ctypes.c_char_p]
        func.restype = None
        buf = ctypes.create_string_buffer(256)
        func(buf)
        client_version = buf.value.decode('utf-8', errors='replace').strip()
        if client_version:
            rows.append({
                'Statistic': gettext('Client version'),
                'Value': client_version,
            })
        lib_name = getattr(api, 'client_library_name', None)
        if lib_name:
            rows.append({
                'Statistic': gettext('Client library'),
                'Value': os.path.basename(str(lib_name)),
            })
        drv_ver = getattr(fb_driver, '__version__', None)
        if drv_ver:
            rows.append({
                'Statistic': gettext('Python driver'),
                'Value': f'firebird-driver {drv_ver}',
            })
    except Exception:
        return rows
    return rows


def build_connector_statistics(engine_id, engine_label, status,
                               client_stats_fn=firebird_client_statistics):
    """Build statistics table payload for an engine connector node."""
    rows = [
        {'Statistic': gettext('Engine'), 'Value': engine_label},
    ]
    ports = status.get('ports') or []
    if ports:
        rows.append({
            'Statistic': gettext('Default port(s)'),
            'Value': ', '.join(str(p) for p in ports),
        })
    listening = status.get('listening_ports') or []
    if status.get('available') and listening:
        local_status = gettext(
            'Listener detected on port(s) %(ports)s',
            ports=', '.join(str(p) for p in listening),
        )
    elif status.get('available'):
        local_status = gettext('Embedded driver available')
    else:
        local_status = gettext('No local listener detected')
    rows.append({
        'Statistic': gettext('Local endpoint status'),
        'Value': local_status,
    })
    if engine_id == 'firebird':
        rows.extend(client_stats_fn())
    rows.append({
        'Statistic': gettext('Server statistics'),
        'Value': gettext(AUTH_STATS_MESSAGE),
    })
    return {
        'columns': [{'name': 'Statistic'}, {'name': 'Value'}],
        'rows': rows,
    }


def build_endpoint_statistics(server, profile, database_target_id=None,
                              snapshot_loader=None,
                              client_stats_fn=firebird_client_statistics):
    """Build `(data, info)` statistics result for a CDE provider endpoint."""
    auth_msg = gettext(AUTH_STATS_MESSAGE)
    rows = []
    seen = set()

    def add_row(label, value):
        if value is None:
            return
        text = str(value).strip()
        if not text or text == 'None':
            return
        key = label.casefold()
        if key in seen:
            return
        seen.add(key)
        rows.append({'Statistic': label, 'Value': text})

    engine_label = (
        profile.get('interface_display_name') or
        profile.get('engine_display_name') or
        profile.get('display_name')
    )
    add_row(gettext('Engine'), engine_label)
    add_row(gettext('Server profile'), getattr(server, 'name', None))

    endpoint = getattr(server, 'endpoint_profile', None)
    routes = getattr(endpoint, 'routes', None) or []
    primary_route = min(
        routes, key=lambda item: (item.priority, item.id), default=None
    )
    route_cfg = {}
    if primary_route is not None:
        try:
            route_cfg = json.loads(primary_route.configuration or '{}')
        except (TypeError, ValueError):
            route_cfg = {}

    if database_target_id is None:
        host = getattr(server, 'host', None) or route_cfg.get('host')
        port = getattr(server, 'port', None) or route_cfg.get('port')
        if host:
            add_row(gettext('Host'), host)
        if port:
            add_row(gettext('Port'), port)
        if route_cfg.get('protocol'):
            add_row(gettext('Network protocol'), route_cfg['protocol'])
        file_path = route_cfg.get('path') or route_cfg.get('database_path')
        if file_path:
            add_row(gettext('Path'), file_path)

    is_firebird = profile.get('engine_id') == 'firebird'
    if is_firebird:
        for item in client_stats_fn():
            add_row(item['Statistic'], item['Value'])

    runtime = getattr(endpoint, 'runtime_identity', None)
    verified = (
        runtime is not None and
        getattr(runtime, 'verification_state', None) == 'verified'
    )
    verified_version = getattr(runtime, 'verified_runtime_version', None)

    if not verified or snapshot_loader is None:
        if is_firebird and database_target_id is None and rows:
            add_row(gettext('Server statistics'), auth_msg)
            return (
                {
                    'columns': [{'name': 'Statistic'}, {'name': 'Value'}],
                    'rows': rows,
                },
                None,
            )
        return None, auth_msg

    try:
        snapshot = snapshot_loader(server, database_target_id)
    except Exception:
        if is_firebird and database_target_id is None and rows:
            if verified_version:
                add_row(gettext('Server version'), verified_version)
            add_row(gettext('Server statistics'), auth_msg)
            return (
                {
                    'columns': [{'name': 'Statistic'}, {'name': 'Value'}],
                    'rows': rows,
                },
                None,
            )
        return None, auth_msg

    resources = (snapshot or {}).get('resources') or []

    server_labels = (
        ('version', gettext('Server version')),
        ('architecture', gettext('Server architecture')),
        ('home_directory', gettext('Server home directory')),
        ('connection_count', gettext('Active attachments')),
        ('edition', gettext('Server edition')),
        ('uptime', gettext('Uptime')),
    )
    for res in resources:
        if res.get('resource_kind') != 'server':
            continue
        native = resource_native(res)
        for key, label in server_labels:
            if key in native:
                add_row(label, native.get(key))
        for key, val in native.items():
            if key in {'scope', 'system_object'} or any(
                key == k for k, _ in server_labels
            ):
                continue
            if isinstance(val, (str, int, float, bool)):
                add_row(key.replace('_', ' ').capitalize(), val)

    if verified_version:
        add_row(gettext('Server version'), verified_version)

    if database_target_id is not None:
        db_labels = (
            ('database_name', gettext('Database')),
            ('sql_dialect', gettext('SQL dialect')),
            ('page_size', gettext('Page size (bytes)')),
            ('allocated_pages', gettext('Allocated pages')),
            ('page_buffers', gettext('Page buffers')),
            ('stored_page_buffers', gettext('Stored page buffers')),
            ('creation_date', gettext('Creation date')),
            ('owner', gettext('Owner')),
            ('read_only', gettext('Read-only')),
            ('forced_writes', gettext('Forced writes')),
            ('reserve_space', gettext('Reserve space')),
            ('sweep_interval', gettext('Sweep interval')),
            ('oldest_transaction', gettext('Oldest transaction')),
            ('oldest_active', gettext('Oldest active transaction')),
            ('oldest_snapshot', gettext('Oldest snapshot')),
            ('next_transaction', gettext('Next transaction')),
            ('next_attachment', gettext('Next attachment ID')),
            ('next_statement', gettext('Next statement ID')),
            ('backup_state', gettext('Backup state')),
            ('encryption_state', gettext('Encryption state')),
            ('shutdown_mode', gettext('Shutdown mode')),
            ('security_database', gettext('Security database')),
        )
        for res in resources:
            if res.get('resource_kind') != 'database':
                continue
            native = resource_native(res)
            ods_major = native.get('ods_major')
            ods_minor = native.get('ods_minor')
            if ods_major is not None and ods_minor is not None:
                add_row(gettext('ODS version'), f'{ods_major}.{ods_minor}')
            for key, label in db_labels:
                if key in native:
                    add_row(label, native.get(key))
            known_db_keys = {k for k, _ in db_labels} | {
                'ods_major', 'ods_minor', 'scope', 'system_object',
                'guid', 'file_id', 'encryption_page',
            }
            for key, val in native.items():
                if key in known_db_keys:
                    continue
                if isinstance(val, (str, int, float, bool)):
                    add_row(key.replace('_', ' ').capitalize(), val)

    metric_labels = {
        'server_version': gettext('Server build string'),
        'security_database': gettext('Security database'),
        'lock_directory': gettext('Lock directory'),
        'message_file': gettext('Message file'),
        'capabilities': gettext('Server capabilities'),
        'num_attachments': gettext('Active attachments'),
        'num_databases': gettext('Databases in use'),
        'implementation': gettext('Implementation'),
    }
    skip_metrics = {'version', 'architecture', 'home_directory'}
    for res in resources:
        if res.get('resource_kind') != 'metric':
            continue
        native = resource_native(res)
        if native.get('observation_error') is not None:
            continue
        native_name = str(
            native.get('native_name') or res.get('display_name') or ''
        ).strip()
        if not native_name or native_name in skip_metrics:
            continue
        val = native.get('value')
        if val in (None, '', 'None', '[]', '{}'):
            continue
        label = metric_labels.get(
            native_name,
            (native.get('description') or native_name.replace('_', ' '))
            .capitalize(),
        )
        add_row(label, val)

    if not rows:
        return None, auth_msg

    return (
        {
            'columns': [{'name': 'Statistic'}, {'name': 'Value'}],
            'rows': rows,
        },
        None,
    )
