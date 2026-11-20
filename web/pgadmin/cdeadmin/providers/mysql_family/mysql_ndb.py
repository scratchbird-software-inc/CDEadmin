"""Optional source-available MySQL 9.7 NDB Cluster storage, catalog, and MGM adapters."""
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
import re
import socket
import uuid

from ...sdk import RelationalClientError
from .mysql_engine_diagnostics import observer_route, release
from .mysql_instance import environment, target_uuid

LOGFILE_GROUP_KIND = 'logfile-group'
NDB_NODE_KIND = 'ndb-node'
KEY = 'mysql_ndb'

SERVER_OPERATIONS = {
    'inspect_ndb_cluster': 'Inspect NDB Cluster status and ndbinfo',
    'start_ndb_backup': 'Start NDB Cluster online backup',
    'abort_ndb_backup': 'Abort NDB Cluster backup',
}
SERVER_READS = frozenset({'inspect_ndb_cluster'})
SERVER_DESTRUCTIVE = frozenset({'abort_ndb_backup'})

LOGFILE_GROUP_OPERATIONS = ('create', 'alter', 'drop')
NODE_OPERATIONS = {
    'restart_ndb_node': 'Restart NDB Cluster node',
    'stop_ndb_node': 'Stop NDB Cluster node',
}


def _quote_ident(name):
    if not isinstance(name, str) or not name or len(name) > 64 or '\x00' in name:
        raise RelationalClientError('Native NDB identifier requires 1 to 64 characters without NUL')
    return '`' + name.replace('`', '``') + '`'


def _bounded_path(path, label='undofile'):
    if not isinstance(path, str) or not path or '\x00' in path or len(path.encode('utf-8')) > 4096:
        raise RelationalClientError(f'Native NDB {label} path requires bounded text without NUL')
    return path


def _positive_int(val, label):
    if type(val) is not int or isinstance(val, bool) or val <= 0 or val > 2**53 - 1:
        raise RelationalClientError(f'{label} requires a positive integer')
    return val


def _valid_mgm_endpoint(draft):
    host = draft.get('mgm_host')
    port = draft.get('mgm_port', 1186)
    if not isinstance(host, str) or not host.strip() or '\x00' in host or '\n' in host or len(host) > 255:
        raise RelationalClientError('Specify an explicit NDB management server host (mgm_host)')
    if type(port) is not int or isinstance(port, bool) or not (1 <= port <= 65535):
        raise RelationalClientError('NDB management server port must be 1..65535')
    return host.strip(), port


class NdbMgmProtocolError(Exception):
    pass


class NdbMgmClient:
    """Pure-Python NDB Management Server (ndb_mgmd) protocol client over TCP 1186."""

    def __init__(self, sock):
        self._sock = sock
        self._buf = b''

    @classmethod
    def connect(cls, host, port=1186, timeout=10.0):
        sock = socket.create_connection((host, int(port)), timeout=timeout)
        sock.settimeout(timeout)
        client = cls(sock)
        try:
            ver = client.command('get version')
            client.command(
                'set clientversion',
                {
                    'major': int(ver['properties'].get('major', 9)),
                    'minor': int(ver['properties'].get('minor', 7)),
                    'build': int(ver['properties'].get('build', 0)),
                },
            )
            return client
        except BaseException:
            client.close()
            raise

    def _read_line(self):
        while b'\n' not in self._buf:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise NdbMgmProtocolError('NDB management server closed connection unexpectedly')
            self._buf += chunk
        line, self._buf = self._buf.split(b'\n', 1)
        return line.rstrip(b'\r').decode('utf-8', errors='replace')

    def command(self, cmd_name, args=None):
        if '\n' in cmd_name or '\r' in cmd_name:
            raise NdbMgmProtocolError('Invalid MGM command name')
        lines = [cmd_name]
        for k, v in (args or {}).items():
            if v is None:
                continue
            sval = str(v)
            if '\n' in sval or '\r' in sval:
                raise NdbMgmProtocolError(f'Invalid newline in MGM argument {k}')
            lines.append(f'{k}: {sval}')
        payload = ('\n'.join(lines) + '\n\n').encode('utf-8')
        self._sock.sendall(payload)
        header = self._read_line()
        while header == '':
            header = self._read_line()
        props = {}
        while True:
            line = self._read_line()
            if line == '':
                break
            if ':' in line:
                k, v = line.split(':', 1)
                props[k.strip()] = v.strip()
        return {'header': header, 'properties': props}

    def get_status(self):
        reply = self.command('get status')
        props = reply['properties']
        node_count = int(props.get('nodes', '0') or '0')
        by_node = {}
        for key, val in props.items():
            m = re.match(r'^node\.([0-9]+)\.(.+)$', key)
            if m:
                nid = int(m.group(1))
                by_node.setdefault(nid, {'node_id': nid})[m.group(2)] = val
        nodes = [by_node[nid] for nid in sorted(by_node)]
        return {'node_count': node_count, 'nodes': nodes, 'raw_header': reply['header']}

    def start_backup(self, *, wait_mode='WAIT_COMPLETED', backup_id=None, snapshot_point='COMPLETE_TIME'):
        completed_map = {'NO_WAIT': 0, 'WAIT_STARTED': 1, 'WAIT_COMPLETED': 2}
        if wait_mode not in completed_map:
            raise NdbMgmProtocolError(f'Invalid NDB backup wait_mode: {wait_mode}')
        args = {
            'completed': completed_map[wait_mode],
            'backuppoint': 0 if snapshot_point == 'COMPLETE_TIME' else 1,
        }
        if backup_id is not None:
            args['backupid'] = int(backup_id)
        reply = self.command('start backup', args)
        res = reply['properties'].get('result', '')
        if res != 'Ok':
            raise NdbMgmProtocolError(f'ndb_mgmd start backup failed: {res or reply}')
        bid = reply['properties'].get('id')
        return {'result': res, 'backup_id': int(bid) if bid and bid.isdigit() else backup_id, 'properties': reply['properties']}

    def abort_backup(self, backup_id):
        reply = self.command('abort backup', {'id': int(backup_id)})
        res = reply['properties'].get('result', '')
        if res != 'Ok':
            raise NdbMgmProtocolError(f'ndb_mgmd abort backup failed: {res or reply}')
        return {'result': res, 'backup_id': int(backup_id), 'properties': reply['properties']}

    def restart_node(self, node_id, *, initial_start=False, nostart=False, abort=False, force=False):
        reply = self.command(
            'restart node v2',
            {
                'node': str(int(node_id)),
                'initialstart': 1 if initial_start else 0,
                'nostart': 1 if nostart else 0,
                'abort': 1 if abort else 0,
                'force': 1 if force else 0,
            },
        )
        res = reply['properties'].get('result', '')
        if res != 'Ok':
            raise NdbMgmProtocolError(f'ndb_mgmd restart node {node_id} failed: {res or reply}')
        return {'result': res, 'node_id': int(node_id), 'properties': reply['properties']}

    def stop_node(self, node_id, *, abort=False, force=False):
        reply = self.command(
            'stop v2',
            {
                'node': str(int(node_id)),
                'abort': 1 if abort else 0,
                'force': 1 if force else 0,
            },
        )
        res = reply['properties'].get('result', '')
        if res != 'Ok':
            raise NdbMgmProtocolError(f'ndb_mgmd stop node {node_id} failed: {res or reply}')
        return {'result': res, 'node_id': int(node_id), 'properties': reply['properties']}

    def close(self):
        try:
            self._sock.sendall(b'bye\n\n')
        except Exception:
            pass
        try:
            self._sock.close()
        except Exception:
            pass


def observe_ndb_engines(cursor):
    cursor.execute(
        "SELECT LOWER(ENGINE), UPPER(SUPPORT) FROM information_schema.ENGINES "
        "WHERE LOWER(ENGINE) IN ('ndbcluster', 'ndbinfo')"
    )
    found = {str(k): str(v) for k, v in cursor.fetchall()}
    ndb_support = found.get('ndbcluster', 'MISSING')
    ndbinfo_support = found.get('ndbinfo', 'MISSING')
    return {
        'ndbcluster_support': ndb_support,
        'ndbcluster_active': ndb_support in {'YES', 'DEFAULT'},
        'ndbinfo_support': ndbinfo_support,
        'ndbinfo_active': ndbinfo_support in {'YES', 'DEFAULT'},
    }


def require_ndbcluster_engine(cursor):
    state = observe_ndb_engines(cursor)
    if not state['ndbcluster_active']:
        err = RelationalClientError(
            f"MySQL NDB Cluster storage engine (ndbcluster) is unavailable on this server "
            f"(SUPPORT={state['ndbcluster_support']}); connect an NDB Cluster SQL node"
        )
        err.error_code = 'ndbcluster_unavailable'
        err.ndb_engine_state = state
        err.native_dispatched = False
        err.native_acknowledged = False
        err.automatic_retry = False
        raise err
    return state


def query_ndbinfo_summary(cursor):
    state = require_ndbcluster_engine(cursor)
    if not state['ndbinfo_active']:
        return {'engine_state': state, 'ndbinfo_available': False, 'nodes': [], 'memoryusage': [], 'logbuffers': [], 'transporters': []}
    out = {'engine_state': state, 'ndbinfo_available': True}
    queries = (
        ('nodes', 'SELECT CAST(node_id AS CHAR), CAST(uptime AS CHAR), status, CAST(start_phase AS CHAR), CAST(config_generation AS CHAR) FROM ndbinfo.nodes ORDER BY node_id LIMIT 128'),
        ('memoryusage', 'SELECT CAST(node_id AS CHAR), memory_type, CAST(used AS CHAR), CAST(total AS CHAR), CAST(used_pages AS CHAR), CAST(total_pages AS CHAR) FROM ndbinfo.memoryusage ORDER BY node_id, memory_type LIMIT 256'),
        ('logbuffers', 'SELECT CAST(node_id AS CHAR), log_type, CAST(log_id AS CHAR), CAST(log_part AS CHAR), CAST(total AS CHAR), CAST(used AS CHAR) FROM ndbinfo.logbuffers ORDER BY node_id, log_type, log_id, log_part LIMIT 256'),
        ('transporters', 'SELECT CAST(node_id AS CHAR), CAST(remote_node_id AS CHAR), status FROM ndbinfo.transporters ORDER BY node_id, remote_node_id LIMIT 256'),
    )
    for section_name, sql in queries:
        cursor.execute(sql)
        cols = [c[0].lower() for c in (cursor.description or ())]
        out[section_name] = [dict(zip(cols, row)) for row in cursor.fetchall()]
    return out


def discover_ndb_resources(optional_records, add, server_uuid=None):
    """Discover logfile-group and ndb-node resources without failing on non-NDB servers."""
    engines = {
        str(r.get('engine', '')).lower(): str(r.get('support', '')).upper()
        for r in optional_records(
            "SELECT ENGINE, SUPPORT FROM information_schema.ENGINES WHERE LOWER(ENGINE) IN ('ndbcluster', 'ndbinfo')"
        )
    }
    if engines.get('ndbcluster') not in {'YES', 'DEFAULT'}:
        return
    lg_files = {}
    for row in optional_records(
        'SELECT LOGFILE_GROUP_NAME, FILE_NAME, INITIAL_SIZE, TOTAL_EXTENTS, FREE_EXTENTS, EXTRA '
        "FROM information_schema.FILES WHERE FILE_TYPE = 'UNDO LOG' AND LOWER(ENGINE) = 'ndbcluster' "
        'AND LOGFILE_GROUP_NAME IS NOT NULL ORDER BY LOGFILE_GROUP_NAME, FILE_NAME'
    ):
        lg = row['logfile_group_name']
        entry = lg_files.setdefault(lg, {'logfile_group_name': lg, 'engine': 'ndbcluster', 'undofiles': [], 'server_uuid': server_uuid})
        entry['undofiles'].append(row)
    for lg_name, lg_native in lg_files.items():
        add(LOGFILE_GROUP_KIND, [], lg_name, lg_native)

    for ts_row in optional_records(
        'SELECT TABLESPACE_NAME, LOGFILE_GROUP_NAME, FILE_NAME, INITIAL_SIZE, TOTAL_EXTENTS, FREE_EXTENTS '
        "FROM information_schema.FILES WHERE FILE_TYPE = 'DATAFILE' AND LOWER(ENGINE) = 'ndbcluster' "
        'AND TABLESPACE_NAME IS NOT NULL ORDER BY TABLESPACE_NAME, FILE_NAME'
    ):
        add(
            'tablespace',
            [],
            ts_row['tablespace_name'],
            {
                'name': ts_row['tablespace_name'],
                'space_type': 'NDB',
                'engine': 'ndbcluster',
                'logfile_group_name': ts_row['logfile_group_name'],
                'available_tablespace_changes': ['ADD_DATAFILE', 'DROP_DATAFILE'],
                'server_uuid': server_uuid,
                'administration': {'allowed_operations': ['inspect', 'alter', 'drop']},
            },
        )

    if engines.get('ndbinfo') in {'YES', 'DEFAULT'}:
        mem_by_node = {}
        for mrow in optional_records(
            'SELECT node_id, memory_type, used, total, used_pages, total_pages '
            'FROM ndbinfo.memoryusage ORDER BY node_id, memory_type'
        ):
            mem_by_node.setdefault(str(mrow['node_id']), []).append(mrow)
        for nrow in optional_records(
            'SELECT node_id, uptime, status, start_phase, config_generation '
            'FROM ndbinfo.nodes ORDER BY node_id'
        ):
            nid_str = str(nrow['node_id'])
            add(
                NDB_NODE_KIND,
                [],
                nid_str,
                {
                    **nrow,
                    'node_id': nid_str,
                    'memoryusage': mem_by_node.get(nid_str, []),
                    'server_uuid': server_uuid,
                },
            )


def compile_logfile_group_operation(operation, draft, target):
    if operation not in LOGFILE_GROUP_OPERATIONS or not isinstance(draft, Mapping):
        raise RelationalClientError('Select a typed NDB logfile-group operation')
    if operation == 'create':
        allowed = {'name', 'undofile', 'initial_size', 'undo_buffer_size', 'nodegroup', 'comment'}
        if set(draft) - allowed:
            raise RelationalClientError('Unknown NDB logfile-group create option')
        name = draft.get('name')
        quoted = _quote_ident(name)
        undofile = _bounded_path(draft.get('undofile'), 'undofile')
        source = f'CREATE LOGFILE GROUP {quoted} ADD UNDOFILE %s'
        preview = f'CREATE LOGFILE GROUP {quoted} ADD UNDOFILE <bound-path>'
        params = [undofile]
        for key, clause in (('initial_size', 'INITIAL_SIZE'), ('undo_buffer_size', 'UNDO_BUFFER_SIZE')):
            if draft.get(key) not in (None, ''):
                sz = _positive_int(draft[key], clause)
                source += f' {clause}={sz}'
                preview += f' {clause}={sz}'
        if draft.get('nodegroup') not in (None, ''):
            ng = draft['nodegroup']
            if type(ng) is not int or isinstance(ng, bool) or not (0 <= ng <= 65535):
                raise RelationalClientError('NODEGROUP requires an integer 0..65535')
            source += f' NODEGROUP={ng}'
            preview += f' NODEGROUP={ng}'
        if draft.get('comment') not in (None, ''):
            comment = draft['comment']
            if not isinstance(comment, str) or '\x00' in comment or len(comment) > 2048:
                raise RelationalClientError('COMMENT requires bounded text without NUL')
            source += ' COMMENT=%s'
            preview += ' COMMENT=<bound-value>'
            params.append(comment)
        source += ' ENGINE=NDBCLUSTER'
        preview += ' ENGINE=NDBCLUSTER'
        server_uuid = None
    elif operation == 'alter':
        if not isinstance(target, Mapping) or target.get('resource_kind') != LOGFILE_GROUP_KIND:
            raise RelationalClientError('Select an NDB logfile-group resource')
        allowed = {'undofile', 'initial_size', 'confirmation'}
        if set(draft) - allowed or draft.get('confirmation') != target.get('display_name'):
            raise RelationalClientError('Confirm the exact NDB logfile-group name and undofile options')
        name = target['display_name']
        quoted = _quote_ident(name)
        undofile = _bounded_path(draft.get('undofile'), 'undofile')
        source = f'ALTER LOGFILE GROUP {quoted} ADD UNDOFILE %s'
        preview = f'ALTER LOGFILE GROUP {quoted} ADD UNDOFILE <bound-path>'
        params = [undofile]
        if draft.get('initial_size') not in (None, ''):
            sz = _positive_int(draft['initial_size'], 'INITIAL_SIZE')
            source += f' INITIAL_SIZE={sz}'
            preview += f' INITIAL_SIZE={sz}'
        source += ' ENGINE=NDBCLUSTER'
        preview += ' ENGINE=NDBCLUSTER'
        server_uuid = (target.get('native') or {}).get('server_uuid')
    else:  # drop
        if not isinstance(target, Mapping) or target.get('resource_kind') != LOGFILE_GROUP_KIND:
            raise RelationalClientError('Select an NDB logfile-group resource')
        if set(draft) - {'confirmation'} or draft.get('confirmation') != target.get('display_name'):
            raise RelationalClientError('Confirm the exact NDB logfile-group name')
        name = target['display_name']
        quoted = _quote_ident(name)
        source = f'DROP LOGFILE GROUP {quoted} ENGINE=NDBCLUSTER'
        preview = source
        params = []
        server_uuid = (target.get('native') or {}).get('server_uuid')

    return {
        'statements': [{'source': source, 'preview_source': preview, 'parameters': tuple(params), 'ndb_required': True}],
        KEY: {
            'kind': LOGFILE_GROUP_KIND,
            'operation': operation,
            'name': name,
            'draft': deepcopy(dict(draft)),
            'target': deepcopy(dict(target)) if isinstance(target, Mapping) else None,
            'server_uuid': server_uuid,
        },
        'warnings': [
            'NDB logfile-group DDL applies cluster-wide across NDB data nodes and requires active ndbcluster storage support.',
        ],
    }


def compile_server_operation(operation, draft, target):
    if operation not in SERVER_OPERATIONS or not isinstance(draft, Mapping):
        raise RelationalClientError('Select a typed NDB Cluster server operation')
    server_uuid = target_uuid(target)
    if operation == 'inspect_ndb_cluster':
        allowed = {'mgm_host', 'mgm_port', 'confirmation'}
        if set(draft) - allowed or draft.get('confirmation') != target.get('display_name'):
            raise RelationalClientError('Confirm the exact server display name for NDB cluster inspection')
        mgm = _valid_mgm_endpoint(draft) if draft.get('mgm_host') not in (None, '') else None
        preview = 'SELECT * FROM ndbinfo.nodes, ndbinfo.memoryusage, ndbinfo.logbuffers, ndbinfo.transporters' + (
            f' /* + ndb_mgmd {mgm[0]}:{mgm[1]} get status */' if mgm else ''
        )
    elif operation == 'start_ndb_backup':
        allowed = {'mgm_host', 'mgm_port', 'wait_mode', 'backup_id', 'snapshot_point', 'confirmation'}
        if set(draft) - allowed or draft.get('confirmation') != target.get('display_name'):
            raise RelationalClientError('Confirm the exact server display name and NDB backup options')
        mgm = _valid_mgm_endpoint(draft)
        wait_mode = str(draft.get('wait_mode', 'WAIT_COMPLETED') or 'WAIT_COMPLETED').upper()
        if wait_mode not in {'NO_WAIT', 'WAIT_STARTED', 'WAIT_COMPLETED'}:
            raise RelationalClientError('wait_mode must be NO_WAIT, WAIT_STARTED, or WAIT_COMPLETED')
        snap = str(draft.get('snapshot_point', 'COMPLETE_TIME') or 'COMPLETE_TIME').upper()
        if snap not in {'COMPLETE_TIME', 'START_TIME'}:
            raise RelationalClientError('snapshot_point must be COMPLETE_TIME or START_TIME')
        bid = draft.get('backup_id')
        if bid not in (None, ''):
            _positive_int(bid, 'backup_id')
        preview = f'ndb_mgmd({mgm[0]}:{mgm[1]}) start backup wait={wait_mode} snapshot={snap}'
    else:  # abort_ndb_backup
        allowed = {'mgm_host', 'mgm_port', 'backup_id', 'confirmation'}
        if set(draft) - allowed or draft.get('confirmation') != target.get('display_name'):
            raise RelationalClientError('Confirm the exact server display name and NDB backup ID to abort')
        mgm = _valid_mgm_endpoint(draft)
        bid = _positive_int(draft.get('backup_id'), 'backup_id')
        preview = f'ndb_mgmd({mgm[0]}:{mgm[1]}) abort backup id={bid}'

    return {
        'statements': [{'source': preview, 'preview_source': preview, 'parameters': (), 'ndb_required': True}],
        KEY: {
            'kind': 'server',
            'operation': operation,
            'mgm_endpoint': list(mgm) if mgm else None,
            'draft': deepcopy(dict(draft)),
            'target': deepcopy(dict(target)),
            'server_uuid': server_uuid,
        },
        'warnings': [
            'NDB Cluster operations verify active ndbcluster support on the SQL node and communicate directly with the selected ndb_mgmd management endpoint.',
        ],
    }


def compile_node_operation(operation, draft, target):
    if operation not in NODE_OPERATIONS or not isinstance(draft, Mapping):
        raise RelationalClientError('Select a typed NDB Cluster node operation')
    if not isinstance(target, Mapping) or target.get('resource_kind') != NDB_NODE_KIND:
        raise RelationalClientError('Select an NDB Cluster node resource')
    node_str = str(target.get('display_name') or (target.get('native') or {}).get('node_id') or '')
    if not re.fullmatch(r'[1-9][0-9]{0,2}', node_str) or not (1 <= int(node_str) <= 255):
        raise RelationalClientError('NDB node ID must be 1..255')
    node_id = int(node_str)
    if draft.get('confirmation') != target.get('display_name'):
        raise RelationalClientError('Confirm the exact NDB node ID')
    mgm = _valid_mgm_endpoint(draft)
    if operation == 'restart_ndb_node':
        allowed = {'mgm_host', 'mgm_port', 'initial_start', 'nostart', 'abort', 'force', 'confirmation'}
        if set(draft) - allowed:
            raise RelationalClientError('Unknown restart_ndb_node option')
        for bkey in ('initial_start', 'nostart', 'abort', 'force'):
            if bkey in draft and not isinstance(draft[bkey], bool):
                raise RelationalClientError(f'{bkey} must be boolean')
        preview = f'ndb_mgmd({mgm[0]}:{mgm[1]}) restart node v2 node={node_id}'
    else:  # stop_ndb_node
        allowed = {'mgm_host', 'mgm_port', 'abort', 'force', 'confirmation'}
        if set(draft) - allowed:
            raise RelationalClientError('Unknown stop_ndb_node option')
        for bkey in ('abort', 'force'):
            if bkey in draft and not isinstance(draft[bkey], bool):
                raise RelationalClientError(f'{bkey} must be boolean')
        preview = f'ndb_mgmd({mgm[0]}:{mgm[1]}) stop v2 node={node_id}'

    server_uuid = (target.get('native') or {}).get('server_uuid')
    return {
        'statements': [{'source': preview, 'preview_source': preview, 'parameters': (), 'ndb_required': True}],
        KEY: {
            'kind': NDB_NODE_KIND,
            'operation': operation,
            'node_id': node_id,
            'mgm_endpoint': list(mgm),
            'draft': deepcopy(dict(draft)),
            'target': deepcopy(dict(target)),
            'server_uuid': server_uuid,
        },
        'warnings': [
            'Stopping or restarting an NDB data node affects cluster redundancy and availability; cluster quorum checks are enforced by ndb_mgmd.',
        ],
    }


def compile_operation(operation, draft, target):
    kind = target.get('resource_kind') if isinstance(target, Mapping) else None
    if kind == LOGFILE_GROUP_KIND or (kind is None and operation in LOGFILE_GROUP_OPERATIONS):
        return compile_logfile_group_operation(operation, draft, target)
    if kind == NDB_NODE_KIND or operation in NODE_OPERATIONS:
        return compile_node_operation(operation, draft, target)
    return compile_server_operation(operation, draft, target)


def bind_review(client, planned):
    payload = planned['provider_payload']
    compiled = payload['compiled']
    intent = compiled.get(KEY)
    handle = client._connect({'route': observer_route(payload)})
    cursor = None
    ready = False
    try:
        handle.autocommit = True
        cursor = handle.cursor()
        identity = environment(cursor)
        if intent and intent.get('server_uuid') and identity['server_uuid'] != intent['server_uuid']:
            raise RelationalClientError('Live MySQL server_uuid differs from the selected NDB target')
        engine_state = require_ndbcluster_engine(cursor)
        mgm_status = None
        if intent and intent.get('mgm_endpoint'):
            mhost, mport = intent['mgm_endpoint']
            try:
                mgm = NdbMgmClient.connect(mhost, mport)
                try:
                    mgm_status = mgm.get_status()
                finally:
                    mgm.close()
            except Exception as exc:
                err = RelationalClientError(f'NDB management server {mhost}:{mport} is unreachable: {exc}')
                err.error_code = 'ndb_mgmd_unavailable'
                raise err from None
        review_record = {
            'execution_identity': identity,
            'ndb_engine_state': engine_state,
            'mgm_status': mgm_status,
            'review_nonce': uuid.uuid4().hex,
        }
        if intent is not None:
            intent['review'] = review_record
        else:
            compiled['mysql_ndb_tablespace_review'] = review_record
        planned['command_preview'].update(
            native_execution_identity=identity,
            native_ndb_engine=engine_state,
            **({'native_ndb_mgm_status': mgm_status} if mgm_status is not None else {}),
        )
        ready = True
        return planned
    finally:
        cleanup = release(client, handle, cursor)
        if ready and not cleanup['connection_released']:
            raise RelationalClientError('NDB review connection release is unconfirmed')


def apply(client, request, connection=None):
    if connection is not None:
        raise RelationalClientError('NDB Cluster administration requires a dedicated administrative connection')
    payload = request['provider_payload']
    compiled = payload['compiled']
    intent = compiled.get(KEY)
    ts_review = compiled.get('mysql_ndb_tablespace_review')
    review = intent.get('review') if isinstance(intent, Mapping) else ts_review
    if not isinstance(review, Mapping):
        # Even if called without bind_review, connect to report exact ndbcluster_unavailable
        # on non-NDB servers, otherwise demand explicit review.
        handle = client._connect({'route': observer_route(payload)})
        cur = None
        try:
            handle.autocommit = True
            cur = handle.cursor()
            require_ndbcluster_engine(cur)
        finally:
            release(client, handle, cur)
        raise RelationalClientError('Review the exact NDB Cluster operation before dispatch')

    consumed = getattr(client, '_consumed_ndb_reviews', None)
    if consumed is None:
        consumed = set()
        client._consumed_ndb_reviews = consumed
    nonce = review.get('review_nonce')
    if not isinstance(nonce, str) or nonce in consumed:
        raise RelationalClientError('This reviewed NDB Cluster plan was already consumed; replay is refused')

    handle = client._connect({'route': observer_route(payload)})
    cursor = None
    dispatched = acknowledged = False
    response = failure = None
    try:
        handle.autocommit = True
        cursor = handle.cursor()
        identity = environment(cursor)
        if identity != review.get('execution_identity'):
            raise RelationalClientError('MySQL server or principal identity changed since NDB review')
        engine_state = require_ndbcluster_engine(cursor)
        consumed.add(nonce)

        if intent is None or intent['kind'] == LOGFILE_GROUP_KIND:
            # NDB tablespace or logfile-group SQL DDL
            stmt = compiled['statements'][0]
            cursor.execute('SET SESSION lock_wait_timeout = 30')
            dispatched = True
            if stmt.get('parameters'):
                cursor.execute(stmt['source'], stmt['parameters'])
            else:
                cursor.execute(stmt['source'])
            acknowledged = True
            response = {
                'accepted': True,
                'statement_results': [{
                    'source': stmt.get('preview_source', stmt['source']),
                    'rowcount': getattr(cursor, 'rowcount', 0),
                    'columns': [],
                    'rows': [],
                }],
                'commit_requested': False,
                'rollback_requested': False,
                'native_implicit_commit': True,
                'staged_in_provider_session': False,
                'automatic_retry': False,
                'transaction_finality_interpreted_by_common_code': False,
                'ndb_result': {
                    'kind': intent['kind'] if intent else 'tablespace',
                    'operation': intent['operation'] if intent else 'tablespace_ddl',
                    'execution_identity': identity,
                    'ndb_engine_state': engine_state,
                    'native_dispatched': True,
                    'native_acknowledged': True,
                },
            }
            return response

        op = intent['operation']
        if op == 'inspect_ndb_cluster':
            dispatched = True
            summary = query_ndbinfo_summary(cursor)
            mgm_status = None
            if intent.get('mgm_endpoint'):
                mhost, mport = intent['mgm_endpoint']
                mgm = NdbMgmClient.connect(mhost, mport)
                try:
                    mgm_status = mgm.get_status()
                finally:
                    mgm.close()
            acknowledged = True
            response = {
                'accepted': True,
                'commit_requested': False,
                'rollback_requested': False,
                'native_implicit_commit': False,
                'staged_in_provider_session': False,
                'automatic_retry': False,
                'transaction_finality_interpreted_by_common_code': False,
                'ndb_result': {
                    'operation': op,
                    'execution_identity': identity,
                    'ndbinfo': summary,
                    'mgm_status': mgm_status,
                    'native_dispatched': True,
                    'native_acknowledged': True,
                    'observed_at': datetime.now(timezone.utc).isoformat(),
                },
            }
            return response

        mhost, mport = intent['mgm_endpoint']
        draft = intent['draft']
        mgm = NdbMgmClient.connect(mhost, mport)
        try:
            dispatched = True
            if op == 'start_ndb_backup':
                mgm_res = mgm.start_backup(
                    wait_mode=str(draft.get('wait_mode', 'WAIT_COMPLETED') or 'WAIT_COMPLETED').upper(),
                    backup_id=draft.get('backup_id') if draft.get('backup_id') not in (None, '') else None,
                    snapshot_point=str(draft.get('snapshot_point', 'COMPLETE_TIME') or 'COMPLETE_TIME').upper(),
                )
            elif op == 'abort_ndb_backup':
                mgm_res = mgm.abort_backup(draft['backup_id'])
            elif op == 'restart_ndb_node':
                mgm_res = mgm.restart_node(
                    intent['node_id'],
                    initial_start=bool(draft.get('initial_start', False)),
                    nostart=bool(draft.get('nostart', False)),
                    abort=bool(draft.get('abort', False)),
                    force=bool(draft.get('force', False)),
                )
            elif op == 'stop_ndb_node':
                mgm_res = mgm.stop_node(
                    intent['node_id'],
                    abort=bool(draft.get('abort', False)),
                    force=bool(draft.get('force', False)),
                )
            else:
                raise RelationalClientError(f'Unknown NDB management operation: {op}')
            acknowledged = True
            post_status = mgm.get_status()
        finally:
            mgm.close()

        response = {
            'accepted': True,
            'commit_requested': False,
            'rollback_requested': False,
            'native_implicit_commit': False,
            'staged_in_provider_session': False,
            'automatic_retry': False,
            'transaction_finality_interpreted_by_common_code': False,
            'ndb_result': {
                'operation': op,
                'execution_identity': identity,
                'ndb_engine_state': engine_state,
                'mgm_endpoint': {'host': mhost, 'port': mport},
                'mgm_response': mgm_res,
                'mgm_status_after': post_status,
                'native_dispatched': True,
                'native_acknowledged': True,
                'observed_at': datetime.now(timezone.utc).isoformat(),
            },
        }
        return response
    except Exception as exc:
        if isinstance(exc, RelationalClientError):
            failure = exc
        elif isinstance(exc, NdbMgmProtocolError):
            failure = RelationalClientError(str(exc))
            failure.error_code = 'ndb_mgm_rejected'
        else:
            failure = RelationalClientError(f'Native NDB Cluster operation failed ({type(exc).__name__}): {exc}')
            failure.errno = getattr(exc, 'errno', None)
            failure.sqlstate = getattr(exc, 'sqlstate', None)
            failure.native_status_codes = (failure.errno,) if type(failure.errno) is int else ()
        failure.native_dispatched = dispatched
        failure.native_acknowledged = acknowledged
        failure.automatic_retry = False
        raise failure from None
    finally:
        cleanup = release(client, handle, cursor)
        if response is not None:
            response['connection_release'] = cleanup
        elif failure is not None:
            failure.connection_release = cleanup
