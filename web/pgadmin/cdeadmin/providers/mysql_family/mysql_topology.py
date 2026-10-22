"""Native MySQL Shell AdminAPI calls; instance and topology interfaces differ."""
import json
import math
from pathlib import Path
import uuid
from urllib.parse import quote as url_quote, quote_plus

from ...operations.fileio import private_file
from ...sdk.tooling import ProviderToolGrant
from .mysql_binlog_archives import BinlogArchiveError, connection_options, rows, program_identity

CREDENTIAL_FILE = 'CDEADMIN_MYSQL_TOPOLOGY_CREDENTIAL_FILE'


def call(context, method, arguments, *, read=False, seed=False):
    return {'context': context, 'method': method, 'arguments': arguments,
            'read_only': read, 'seed_argument': seed,
            'instance_format': 'uri' if context in {'replica_set', 'cluster_set'} or method == 'add_replica_instance' else 'connection'}


CALLS = {
    'instance.check_configuration': call('instance', 'check_instance_configuration', ['options?'], read=True, seed=True),
    'instance.configure_cluster': call('instance', 'configure_instance', ['options?'], seed=True),
    'instance.configure_replica_set': call('instance', 'configure_replica_set_instance', ['options?'], seed=True),
    'instance.create_cluster': call('instance', 'create_cluster', ['name', 'options?']),
    'instance.create_replica_set': call('instance', 'create_replica_set', ['name', 'options?']),
    'instance.reboot_cluster': call('instance', 'reboot_cluster_from_complete_outage', ['name?', 'options?']),
    'instance.upgrade_metadata': call('instance', 'upgrade_metadata', ['options?']),
    'instance.drop_metadata': call('instance', 'drop_metadata_schema', ['options?']),
    'cluster.describe': call('cluster', 'describe', [], read=True),
    'cluster.status': call('cluster', 'status', ['options?'], read=True),
    'cluster.options': call('cluster', 'options', ['options?'], read=True),
    'cluster.add_instance': call('cluster', 'add_instance', ['instance', 'options?']),
    'cluster.add_replica_instance': call('cluster', 'add_replica_instance', ['instance', 'options?']),
    'cluster.rejoin_instance': call('cluster', 'rejoin_instance', ['instance', 'options?']),
    'cluster.remove_instance': call('cluster', 'remove_instance', ['instance', 'options?']),
    'cluster.rescan': call('cluster', 'rescan', ['options?']),
    'cluster.set_primary': call('cluster', 'set_primary_instance', ['instance', 'options?']),
    'cluster.single_primary': call('cluster', 'switch_to_single_primary_mode', ['instance?']),
    'cluster.multi_primary': call('cluster', 'switch_to_multi_primary_mode', []),
    'cluster.force_quorum': call('cluster', 'force_quorum_using_partition_of', ['instance']),
    'cluster.dissolve': call('cluster', 'dissolve', ['options?']),
    'cluster.set_option': call('cluster', 'set_option', ['option', 'value']),
    'cluster.set_instance_option': call('cluster', 'set_instance_option', ['instance', 'option', 'value']),
    'cluster.fence_writes': call('cluster', 'fence_writes', []),
    'cluster.unfence_writes': call('cluster', 'unfence_writes', []),
    'cluster.fence_all_traffic': call('cluster', 'fence_all_traffic', []),
    'cluster.reset_recovery_passwords': call('cluster', 'reset_recovery_accounts_password', ['options?']),
    'cluster.reset_replication_passwords': call('cluster', 'reset_replication_accounts_password', ['options?']),
    'cluster.create_cluster_set': call('cluster', 'create_cluster_set', ['name', 'options?']),
    'replica_set.describe': call('replica_set', 'describe', [], read=True),
    'replica_set.status': call('replica_set', 'status', ['options?'], read=True),
    'replica_set.options': call('replica_set', 'options', ['options?'], read=True),
    'replica_set.add_instance': call('replica_set', 'add_instance', ['instance', 'options?']),
    'replica_set.rejoin_instance': call('replica_set', 'rejoin_instance', ['instance', 'options?']),
    'replica_set.remove_instance': call('replica_set', 'remove_instance', ['instance', 'options?']),
    'replica_set.rescan': call('replica_set', 'rescan', ['options?']),
    'replica_set.set_primary': call('replica_set', 'set_primary_instance', ['instance', 'options?']),
    'replica_set.force_primary': call('replica_set', 'force_primary_instance', ['instance?', 'options?']),
    'replica_set.dissolve': call('replica_set', 'dissolve', ['options?']),
    'replica_set.set_option': call('replica_set', 'set_option', ['option', 'value']),
    'replica_set.set_instance_option': call('replica_set', 'set_instance_option', ['instance', 'option', 'value']),
    'replica_set.reset_replication_passwords': call('replica_set', 'reset_replication_accounts_password', ['options?']),
    'cluster_set.describe': call('cluster_set', 'describe', [], read=True),
    'cluster_set.status': call('cluster_set', 'status', ['options?'], read=True),
    'cluster_set.options': call('cluster_set', 'options', ['options?'], read=True),
    'cluster_set.create_replica_cluster': call('cluster_set', 'create_replica_cluster', ['instance', 'name', 'options?']),
    'cluster_set.remove_cluster': call('cluster_set', 'remove_cluster', ['name', 'options?']),
    'cluster_set.rejoin_cluster': call('cluster_set', 'rejoin_cluster', ['name', 'options?']),
    'cluster_set.set_primary': call('cluster_set', 'set_primary_cluster', ['name', 'options?']),
    'cluster_set.force_primary': call('cluster_set', 'force_primary_cluster', ['name', 'options?']),
    'cluster_set.dissolve': call('cluster_set', 'dissolve', ['options?']),
    'cluster_set.set_option': call('cluster_set', 'set_option', ['option', 'value']),
    'cluster_set.reset_replication_passwords': call('cluster_set', 'reset_replication_accounts_password', ['options?']),
}

RECOVERY_CALLS = frozenset({'instance.reboot_cluster', 'cluster.add_instance',
    'cluster.add_replica_instance', 'cluster.rejoin_instance',
    'replica_set.add_instance', 'replica_set.rejoin_instance', 'cluster_set.create_replica_cluster'})


def parse(value):
    if not isinstance(value, str) or len(value.encode('utf8')) > 1024 * 1024:
        raise BinlogArchiveError('Select bounded native JSON argument text')
    def constant(_value): raise ValueError('Native JSON does not accept nonfinite numbers')
    def number(value):
        result = float(value)
        if not math.isfinite(result): raise ValueError('Native JSON numeric overflow')
        return result
    def native_values(value):
        if type(value) is int and not -(2**63) <= value <= 2**64-1:
            raise ValueError('Integer exceeds the native Shell value range')
        if isinstance(value, dict):
            for item in value.values(): native_values(item)
        elif isinstance(value, list):
            for item in value: native_values(item)
    try:
        result = json.loads(value, parse_constant=constant, parse_float=number)
        native_values(result)
        return result
    except (ValueError, RecursionError): raise BinlogArchiveError('Native argument JSON is invalid') from None


def canonical(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':'))


def options(value):
    allowed = {'operation', 'arguments_json', 'context_name', 'context_options_json',
               'target_confirmation', 'use_advertised_endpoint', 'timeout_seconds'}
    if (not isinstance(value, dict) or set(value) - allowed or
            not isinstance(value.get('operation'), str) or value['operation'] not in CALLS):
        raise BinlogArchiveError('Select a native topology operation')
    specification = CALLS[value['operation']]
    target = value.get('target_confirmation')
    try:
        if not isinstance(target, str) or str(uuid.UUID(target)) != target: raise ValueError()
    except (ValueError, AttributeError): raise BinlogArchiveError('Confirm the native topology seed UUID') from None
    arguments = parse(value.get('arguments_json', '[]'))
    definitions = specification['arguments']
    if (not isinstance(arguments, list) or len(arguments) > len(definitions) or
            len(arguments) < sum(not name.endswith('?') for name in definitions)):
        raise BinlogArchiveError('Supply the selected native method arguments in their declared order')
    for definition, argument in zip(definitions, arguments):
        kind = definition.rstrip('?')
        if argument is None and definition.endswith('?'): continue
        if kind in {'name', 'option'} and not isinstance(argument, str):
            raise BinlogArchiveError('Native names and option names require strings')
        if kind == 'options':
            if not isinstance(argument, dict): raise BinlogArchiveError('Native options require a JSON object')
            # Account creation and host-file deployment keep separate authority;
            # their credentials/paths must never enter a retained argument JSON.
            if {key.casefold() for key in argument} & {'password', 'password1', 'password2', 'password3', 'clusteradminpassword', 'mycnfpath', 'outputmycnfpath'}:
                raise BinlogArchiveError('Account credentials and host option-file deployment require their dedicated workflows')
        if kind == 'instance':
            if (not isinstance(argument, dict) or set(argument) != {'server_id'} or
                    type(argument['server_id']) is not int or argument['server_id'] <= 0):
                raise BinlogArchiveError('Select an owned registered instance for each native instance argument')
    context_name = value.get('context_name', '')
    context_options = parse(value.get('context_options_json', '{}'))
    if not isinstance(context_name, str) or not isinstance(context_options, dict):
        raise BinlogArchiveError('Select a native context name and context option object')
    if {key.casefold() for key in context_options} & {'password', 'password1', 'password2', 'password3', 'clusteradminpassword'}:
        raise BinlogArchiveError('Native context credentials come from the registered endpoint')
    if specification['context'] != 'cluster' and context_options:
        raise BinlogArchiveError('Only the native Cluster getter accepts context options')
    advertised, timeout = value.get('use_advertised_endpoint', False), value.get('timeout_seconds', 3600)
    if type(advertised) is not bool or timeout is not None and (type(timeout) is not int or not 1 <= timeout <= 2147483647):
        raise BinlogArchiveError('Select the native execution address and positive client runtime or null')
    return {'operation': value['operation'], 'arguments_json': canonical(arguments), 'context_name': context_name,
            'context_options_json': canonical(context_options), 'target_confirmation': target,
            'use_advertised_endpoint': advertised, 'timeout_seconds': timeout}


def member_ids(selected):
    return sorted({argument['server_id'] for definition, argument in zip(
        CALLS[selected['operation']]['arguments'], parse(selected['arguments_json']))
        if definition.rstrip('?') == 'instance' and argument is not None})


def metadata(connection):
    inventory = ("SELECT TABLE_NAME,COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA='mysql_innodb_cluster_metadata' AND TABLE_NAME IN "
        "('schema_version','clusters','instances','clustersets') ORDER BY TABLE_NAME,COLUMN_NAME")
    columns = rows(connection, inventory)
    queries = [inventory]
    results = [[list(row.values()) for row in columns]]
    identities = {
        'schema_version': ('major','minor','patch'),
        'clusters': ('cluster_id','cluster_name','cluster_type','clusterset_id'),
        'instances': ('instance_id','cluster_id','mysql_server_uuid','address','instance_name'),
        'clustersets': ('clusterset_id','domain_name'),
    }
    native_instances = []; native_tags = []
    for table, names in identities.items():
        available = {row['COLUMN_NAME'] for row in columns if row['TABLE_NAME'] == table}
        selected = [name for name in names if name in available]
        if not selected: continue
        source = 'SELECT ' + ','.join('CAST(`' + name + '` AS CHAR) AS `' + name + '`' for name in selected)
        source += ' FROM `mysql_innodb_cluster_metadata`.`' + table + '` ORDER BY ' + ','.join('`' + name + '`' for name in selected)
        queries.append(source)
        values = [list(row.values()) for row in rows(connection, source)]
        results.append(values)
        if table == 'instances' and 'mysql_server_uuid' in selected:
            index = selected.index('mysql_server_uuid')
            native_instances.extend(row[index] for row in values if row[index] is not None)
        if table != 'schema_version' and 'attributes' in available:
            source = 'SELECT CAST(`'+selected[0]+'` AS CHAR) AS identity_value,'
            source += "CAST(JSON_EXTRACT(attributes,'$.tags') AS CHAR) AS tags_json FROM `mysql_innodb_cluster_metadata`.`"
            source += table+'` ORDER BY `'+selected[0]+'`'
            queries.append(source)
            values = [list(row.values()) for row in rows(connection, source)]
            results.append(values)
            native_tags.extend({'table': table, 'identity': row[0], 'tags_json': row[1]} for row in values)
    return {'queries': queries, 'results': results, 'instance_uuids': sorted(set(native_instances)),
            'native_tag_json': native_tags,
            'visibility': 'Current native principal; no metadata absence or topology-health inference'}


def tag_observation(metadata):
    def unsigned(value):
        if type(value) is int: return value > 2**63-1
        if isinstance(value, dict): return any(unsigned(item) for item in value.values())
        if isinstance(value, list): return any(unsigned(item) for item in value)
        return False
    values = metadata['native_tag_json']
    return {'tags': values, 'native_shell_json_signed_limit': any(
        unsigned(json.loads(row['tags_json'])) for row in values if row['tags_json'] is not None),
        'scope': 'Independent SQL text of native stored tags; the original Shell result is unchanged'}


def capture(connection):
    facts = rows(connection, 'SELECT @@server_uuid AS server_uuid,VERSION() AS version,'
        'CURRENT_USER() AS authenticated_principal,CURRENT_ROLE() AS active_role,'
        '@@report_host AS reported_host,@@report_port AS reported_port,@@hostname AS hostname')[0]
    if facts['version'].split('-')[0] != '9.7.0':
        raise BinlogArchiveError('Native topology workflows require the selected MySQL 9.7.0 profile')
    return {'identity': {key: facts[key] for key in ('server_uuid', 'version', 'authenticated_principal', 'active_role')},
            'reported_endpoint': {'host': facts['reported_host'] or facts['hostname'], 'port': int(facts['reported_port'])},
            'metadata': metadata(connection)}


def connection(client, route, observed, selected):
    value = connection_options(client, route)
    if selected['use_advertised_endpoint']:
        value.pop('socket', None)
        value.update(observed['reported_endpoint'])
    return value


def script(selected, seed, members, marker):
    specification = CALLS[selected['operation']]
    settings = {'call': specification, 'selected': selected, 'seed': seed, 'members': members, 'marker': marker}
    # JSON travels as text, preserving native integer arguments outside the
    # JavaScript Number range throughout review, execution and result display.
    return '''import json,os
settings=json.loads(''' + repr(canonical(settings)) + ''')
with open(os.environ[''' + repr(CREDENTIAL_FILE) + '''],encoding="utf8") as stream: authentication=json.load(stream)
def authenticated(key,definition):
    return dict(definition,**authentication[key])
def identity(session,expected):
    observed=list(session.run_sql("SELECT @@server_uuid,VERSION(),CURRENT_USER(),CURRENT_ROLE()").fetch_one())
    if observed!=[expected[name] for name in ("server_uuid","version","authenticated_principal","active_role")]:
        raise RuntimeError("Native topology instance or principal changed")
def native_error(error):
    args=getattr(error,"args",())
    code=getattr(error,"code",None)
    if type(code) is not int and args and type(args[0]) is int:code=args[0]
    state=getattr(error,"sqlstate",None)
    return {"code":code if type(code) is int else None,"sqlstate":state,"type":type(error).__name__,"message":str(error)}
shell.options["useWizards"]=False
invoked=False;returned=False;stage="connecting";failure=None;result_json=None;observation_error=None
try:
    shell.connect(authenticated("seed",settings["seed"]["connection"]))
    identity(shell.get_session(),settings["seed"]["identity"])
    metadata=settings["seed"]["metadata"]
    observed_metadata=[[list(row) for row in shell.get_session().run_sql(query).fetch_all()] for query in metadata["queries"]]
    if observed_metadata!=metadata["results"]:raise RuntimeError("Native topology metadata identities changed after review")
    prepared={}
    for key,member in settings["members"].items():
        definition=authenticated(key,member["connection"])
        peer=mysql.get_classic_session(definition)
        try:identity(peer,member["identity"])
        finally:peer.close()
        prepared[int(key)]=definition
    selected=settings["selected"];specification=settings["call"];context=specification["context"]
    stage="context"
    if context=="instance":target=dba
    elif context=="cluster":
        name=selected["context_name"] or None;options=json.loads(selected["context_options_json"])
        target=dba.get_cluster(name,options) if name or options else dba.get_cluster()
    elif context=="replica_set":target=dba.get_replica_set()
    else:target=dba.get_cluster_set()
    arguments=json.loads(selected["arguments_json"])
    for index,(kind,value) in enumerate(zip(specification["arguments"],arguments)):
        if kind.rstrip("?")!="instance" or value is None:continue
        definition=prepared[value["server_id"]]
        # Preserve each method's declared native connection argument type.
        # The URI is constructed only in private native memory, never argv or a
        # retained review/script. The native formatter preserves its encoding.
        arguments[index]=shell.unparse_uri(definition) if specification["instance_format"]=="uri" else definition
    if specification["seed_argument"]:arguments.insert(0,authenticated("seed",settings["seed"]["connection"]))
    stage="native_operation";invoked=True
    result=getattr(target,specification["method"])(*arguments)
    returned=True;stage="returned"
    try:
        if hasattr(result,"status"):result=result.status({"extended":1})
        result_json=json.dumps(result,ensure_ascii=True,allow_nan=False,separators=(",",":"))
    except Exception as error:observation_error=native_error(error)
except Exception as error:
    failure=native_error(error)
finally:
    print(settings["marker"]+json.dumps({"native_load_invoked":invoked,"native_load_returned":returned,
        "stage":stage,"native_error":failure,"result_json":result_json,"observation_error":observation_error},ensure_ascii=True))
'''


def run(client, route, credentials, selected, seed, members, workspace, program, *, cancel=None, progress=None, boundary=None):
    workspace = Path(workspace)
    if program_identity(client, route, workspace, cancel=cancel, progress=progress) != program:
        raise BinlogArchiveError('Native topology utility or execution host changed')
    marker = 'CDEADMIN_MYSQL_TOPOLOGY_' + uuid.uuid4().hex + ':'
    path = workspace / 'native-topology.py'
    with path.open('x', encoding='utf8') as stream:
        private_file(path); stream.write(script(selected, seed, members, marker))
    grant = ProviderToolGrant('mysql-shell', str(workspace), seed['connection'].get('host') or 'localhost',
        int(seed['connection'].get('port', 3306)), timeout_seconds=selected['timeout_seconds'],
        allow_unbounded_runtime=selected['timeout_seconds'] is None, secret_environment_names=(CREDENTIAL_FILE,),
        durable_name='mysql-topology')
    def invoke(view):
        if boundary is not None: boundary()
        observed = client._tool_runner.run(grant,
            ['--no-defaults', '--py', '--log-level=none', '--quiet-start=2', '--file=' + str(path)],
            secret_config=bytes(view), secret_argument=None, secret_environment_name=CREDENTIAL_FILE,
            secret_suffix='.json', cancel_signal=cancel, progress=progress)
        controls = []
        for line in observed['stdout'].splitlines():
            if line.startswith(marker):
                try: controls.append(json.loads(line[len(marker):]))
                except ValueError: pass
        control = controls[0] if len(controls) == 1 and isinstance(controls[0], dict) else None
        sensitive = {variant for values in json.loads(bytes(view)).values() for value in values.values()
                     if isinstance(value, str) and value for variant in
                     (value, url_quote(value, safe=''), quote_plus(value, safe=''))}
        def redact(value):
            if isinstance(value, dict): return {key: redact(item) for key, item in value.items()}
            if isinstance(value, list): return [redact(item) for item in value]
            if isinstance(value, str):
                for secret in sorted(sensitive, key=len, reverse=True): value = value.replace(secret, '[redacted]')
            return value
        if control:
            allowed = {'native_load_invoked', 'native_load_returned', 'stage', 'native_error', 'result_json', 'observation_error'}
            if set(control) != allowed or any(type(control.get(key)) is not bool for key in ('native_load_invoked', 'native_load_returned')):
                control = None
            else:
                result_text = control.pop('result_json')
                control = redact(control)
                control['result_json'] = None
                if result_text is not None:
                    try: control['result_json'] = canonical(redact(json.loads(result_text)))
                    except (ValueError, TypeError): control['result_json'] = None
        output = '\n'.join(line for line in (observed['stdout'] + '\n' + observed['stderr']).splitlines() if not line.startswith(marker))
        return {'tool': {key: value for key, value in observed.items() if key not in {'stdout', 'stderr'}},
                'control': control, 'output_text': redact(output)}
    result = credentials.use(invoke)
    if result['tool']['executable_sha256'] != program['executable_sha256']:
        error = BinlogArchiveError('Native topology executable identity changed')
        error.observation = result['tool']; error.control = result['control']; raise error
    return result
