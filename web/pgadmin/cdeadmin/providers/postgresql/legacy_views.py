"""Read-only inspection of PostgreSQL provider nodes through the inherited
node views (M3, owner direction 2026-11-08: carry the inherited tree's
strengths onto the provider tree, reusing pgAdmin's tested SQL templates).

Given a node's inherited identity chain (``legacy_route``: gid, sid, did,
scid, tid, oid, node_type), this module calls the inherited view for that
node type to obtain the reverse-engineered SQL, the dependencies and the
dependents, exactly as the inherited tree's panels did. The views need a
Flask request and the server's default connection; both exist inside the
workspace ``resource_inspect`` request, which is the only caller. Nothing
here raises for a missing or failing view: every section reports its own
state so the inspector shows what is available and why the rest is not.

Reverse-engineered SQL for user mappings and subscriptions can carry
passwords; the text is redacted before it leaves this module.
"""
import importlib
import json
import re

# node_type -> inherited view and how its route ids are named.
#   module: the view's module under pgadmin.browser.server_groups.servers
#   view:   the view class
#   object: the keyword for the object's own OID
#   owner:  the keyword the owning relation/domain OID (chain ``tid``) takes,
#           or None when the view has no owner id
#   scid:   whether the view takes the schema OID
#   did:    whether the view takes the database OID
#   text:   True when ``sql(json_resp=False)`` returns plain text
_SERVERS = 'pgadmin.browser.server_groups.servers.'
_SCHEMA = _SERVERS + 'databases.schemas.'
_TABLE = _SCHEMA + 'tables.'
_CONSTRAINT = _TABLE + 'constraints.'
_FDW = _SERVERS + 'databases.foreign_data_wrappers.'


def _spec(module, view, obj, owner=None, scid=True, did=True, text=False):
    return {'module': module, 'view': view, 'object': obj, 'owner': owner,
            'scid': scid, 'did': did, 'text': text}


VIEW_SPECS = {
    'database': _spec(_SERVERS + 'databases', 'DatabaseView', 'did',
                      scid=False, did=False),
    'schema': _spec(_SCHEMA[:-1], 'SchemaView', 'scid', scid=False),
    'table': _spec(_TABLE[:-1], 'TableView', 'tid'),
    'partition': _spec(_TABLE + 'partitions', 'PartitionsView', 'ptid',
                       owner='tid'),
    'view': _spec(_SCHEMA + 'views', 'ViewNode', 'vid', text=True),
    'mview': _spec(_SCHEMA + 'views', 'MViewNode', 'vid', text=True),
    'foreign_table': _spec(_SCHEMA + 'foreign_tables', 'ForeignTableView',
                           'foid', text=True),
    'sequence': _spec(_SCHEMA + 'sequences', 'SequenceView', 'seid',
                      text=True),
    'type': _spec(_SCHEMA + 'types', 'TypeView', 'tid', text=True),
    'domain': _spec(_SCHEMA + 'domains', 'DomainView', 'doid', text=True),
    'domain_constraints': _spec(_SCHEMA + 'domains.domain_constraints',
                                'DomainConstraintView', 'coid',
                                owner='doid'),
    'collation': _spec(_SCHEMA + 'collations', 'CollationView', 'coid',
                       text=True),
    'function': _spec(_SCHEMA + 'functions', 'FunctionView', 'fnid',
                      text=True),
    'procedure': _spec(_SCHEMA + 'functions', 'ProcedureView', 'fnid',
                       text=True),
    'trigger_function': _spec(_SCHEMA + 'functions', 'TriggerFunctionView',
                              'fnid', text=True),
    'aggregate': _spec(_SCHEMA + 'aggregates', 'AggregateView', 'agid',
                       text=True),
    'operator': _spec(_SCHEMA + 'operators', 'OperatorView', 'opid'),
    'fts_configuration': _spec(_SCHEMA + 'fts_configurations',
                               'FtsConfigurationView', 'cfgid', text=True),
    'fts_dictionary': _spec(_SCHEMA + 'fts_dictionaries',
                            'FtsDictionaryView', 'dcid', text=True),
    'fts_parser': _spec(_SCHEMA + 'fts_parsers', 'FtsParserView', 'pid',
                        text=True),
    'fts_template': _spec(_SCHEMA + 'fts_templates', 'FtsTemplateView',
                          'tid', text=True),
    'index': _spec(_TABLE + 'indexes', 'IndexesView', 'idx', owner='tid'),
    'trigger': _spec(_TABLE + 'triggers', 'TriggerView', 'trid',
                     owner='tid'),
    'rule': _spec(_TABLE + 'rules', 'RuleView', 'rid', owner='tid'),
    'row_security_policy': _spec(_TABLE + 'row_security_policies',
                                 'RowSecurityView', 'plid', owner='tid'),
    # The registered subclasses carry constraint_type; the base view does not.
    'primary_key': _spec(_CONSTRAINT + 'index_constraint',
                         'PrimaryKeyConstraintView', 'cid', owner='tid'),
    'unique_constraint': _spec(_CONSTRAINT + 'index_constraint',
                               'UniqueConstraintView', 'cid', owner='tid'),
    'check_constraint': _spec(_CONSTRAINT + 'check_constraint',
                              'CheckConstraintView', 'cid', owner='tid'),
    'exclusion_constraint': _spec(_CONSTRAINT + 'exclusion_constraint',
                                  'ExclusionConstraintView', 'exid',
                                  owner='tid'),
    'foreign_key': _spec(_CONSTRAINT + 'foreign_key',
                         'ForeignKeyConstraintView', 'fkid', owner='tid'),
    'extension': _spec(_SERVERS + 'databases.extensions', 'ExtensionView',
                       'eid', scid=False, text=True),
    'event_trigger': _spec(_SERVERS + 'databases.event_triggers',
                           'EventTriggerView', 'etid', scid=False,
                           text=True),
    'cast': _spec(_SERVERS + 'databases.casts', 'CastView', 'cid',
                  scid=False, text=True),
    'language': _spec(_SERVERS + 'databases.languages', 'LanguageView',
                      'lid', scid=False, text=True),
    'publication': _spec(_SERVERS + 'databases.publications',
                         'PublicationView', 'pbid', scid=False, text=True),
    'subscription': _spec(_SERVERS + 'databases.subscriptions',
                          'SubscriptionView', 'subid', scid=False,
                          text=True),
    'foreign_data_wrapper': _spec(_FDW[:-1], 'ForeignDataWrapperView',
                                  'fid', scid=False, text=True),
    'role': _spec(_SERVERS + 'roles', 'RoleView', 'rid', scid=False,
                  did=False),
    'tablespace': _spec(_SERVERS + 'tablespaces', 'TablespaceView', 'tsid',
                        scid=False, did=False),
}

# Node types whose inherited view has a statistics method.
STATISTICS_NODE_TYPES = frozenset({
    'database', 'table', 'mview', 'sequence', 'index', 'function',
    'procedure', 'trigger_function', 'subscription', 'primary_key',
    'unique_constraint',
})

# Node types whose inherited view needs an id the chain does not carry yet
# (the foreign-data-wrapper OID): reported as unavailable, not attempted.
NEEDS_WRAPPER_ID = frozenset({'foreign_server', 'user_mapping'})

_PASSWORD_LITERAL = re.compile(r"(?i)(password\s*)'(?:[^']|'')*'")
_PASSWORD_ASSIGNMENT = re.compile(r"(?i)(password\s*=\s*)[^\s,;)']+")


def redact_sql(text):
    """Hide password literals the inherited templates may print."""
    if not isinstance(text, str):
        return text
    text = _PASSWORD_LITERAL.sub(r"\1'[redacted]'", text)
    return _PASSWORD_ASSIGNMENT.sub(r'\1[redacted]', text)


def view_kwargs(chain):
    """Return the keyword arguments the node's inherited ``sql`` takes.

    Raises ``KeyError`` for a node type without a view and ``ValueError``
    when the chain lacks an id the view needs.
    """
    spec = VIEW_SPECS[chain['node_type']]
    # The provider's chain carries no server group; the tree adds it for
    # its nodes. The inherited views take gid but their SQL never uses it.
    kwargs = {'gid': chain.get('gid', 1), 'sid': chain['sid']}
    if spec['did']:
        if chain.get('did') is None:
            raise ValueError('database id missing')
        kwargs['did'] = chain['did']
    if spec['scid']:
        if chain.get('scid') is None:
            raise ValueError('schema id missing')
        kwargs['scid'] = chain['scid']
    if spec['owner']:
        if chain.get('tid') is None:
            raise ValueError('owning object id missing')
        kwargs[spec['owner']] = chain['tid']
    if chain.get('oid') is None:
        raise ValueError('object id missing')
    kwargs[spec['object']] = chain['oid']
    return kwargs


def _view(spec):
    module = importlib.import_module(spec['module'])
    return getattr(module, spec['view'])(cmd='nodes, compare, ddl_compare')


def _unwrap(result):
    """Return (ok, value) from a view's text, tuple or Flask Response."""
    if isinstance(result, tuple):
        result = result[0]
    if isinstance(result, str):
        return True, result
    status = getattr(result, 'status_code', None)
    if status is None:
        return False, 'inherited view returned no text'
    try:
        body = json.loads(result.get_data(as_text=True))
    except ValueError:
        return False, f'inherited view answered {status}'
    if status != 200:
        message = body.get('errormsg') if isinstance(body, dict) else body
        return False, f'inherited view answered {status}: {message}'
    if isinstance(body, dict):
        body = body.get('data', body)
    return (True, body) if isinstance(body, str) else (
        False, 'inherited view returned no text')


def _unwrap_json(result):
    """Return (ok, data) from a view's JSON Response."""
    status = getattr(result, 'status_code', None)
    if status is None:
        return False, 'inherited view returned no data'
    try:
        body = json.loads(result.get_data(as_text=True))
    except ValueError:
        return False, f'inherited view answered {status}'
    if status != 200:
        message = body.get('errormsg') if isinstance(body, dict) else body
        return False, f'inherited view answered {status}: {message}'
    return True, body.get('data', body) if isinstance(body, dict) else body


def statistics_rows(data):
    """Shape the inherited statistics for the inspector: one object's
    statistics become a name -> value mapping; several rows stay a list."""
    rows = data.get('rows') if isinstance(data, dict) else None
    if rows is None:
        return data
    if len(rows) == 1 and isinstance(rows[0], dict):
        return dict(rows[0])
    return [dict(row) if isinstance(row, dict) else row for row in rows]


def inherited_statistics(chain):
    """The node's statistics from its inherited view, or a reason."""
    node_type = chain['node_type']
    if node_type not in STATISTICS_NODE_TYPES:
        return False, 'the inherited node has no statistics'
    spec = VIEW_SPECS[node_type]
    ok, value = _unwrap_json(_view(spec).statistics(**view_kwargs(chain)))
    return (True, statistics_rows(value)) if ok else (False, value)


def inherited_sql(chain):
    """The node's reverse-engineered SQL from its inherited view."""
    spec = VIEW_SPECS[chain['node_type']]
    kwargs = view_kwargs(chain)
    if spec['text']:
        kwargs['json_resp'] = False
    ok, value = _unwrap(_view(spec).sql(**kwargs))
    return ok, (redact_sql(value) if ok else value)


def inherited_dependencies(chain, connection):
    """(dependencies, dependents) as the inherited panels listed them."""
    spec = VIEW_SPECS[chain['node_type']]
    view = _view(spec)
    if chain['node_type'] == 'role':
        # RoleView overrides get_dependents(conn, sid, rid).
        return (view.get_dependencies(connection, chain['oid']),
                view.get_dependents(connection, chain['sid'], chain['oid']))
    return (view.get_dependencies(connection, chain['oid']),
            view.get_dependents(connection, chain['oid']))


def inherited_inspection(chain, connection_for=None):
    """Inspect a provider node through its inherited view.

    ``connection_for(did)`` returns the server's default connection for a
    database (``None`` for cluster-level objects). Returns a dict with
    ``ddl``, ``statistics``, ``dependencies``, ``dependents`` when
    available and a ``states`` entry naming each section's state and
    reason; never raises.
    """
    result = {'states': {}}
    node_type = (chain or {}).get('node_type')
    if not node_type:
        result['states']['all'] = 'unavailable: no inherited node for kind'
        return result
    if node_type in NEEDS_WRAPPER_ID:
        result['states']['all'] = (
            'unavailable: the inherited view needs the foreign-data-wrapper '
            'id, which the identity chain does not carry yet')
        return result
    if node_type not in VIEW_SPECS:
        result['states']['all'] = f'unavailable: no view map for {node_type}'
        return result
    try:
        ok, value = inherited_sql(chain)
        if ok:
            result['ddl'] = value
            result['states']['ddl'] = 'inherited'
        else:
            result['states']['ddl'] = 'unavailable: ' + str(value)
    except Exception as exc:  # the inspector must still answer
        result['states']['ddl'] = (
            f'unavailable: {type(exc).__name__}: {exc}')
    try:
        ok, value = inherited_statistics(chain)
        if ok:
            result['statistics'] = value
            result['states']['statistics'] = 'inherited'
        else:
            result['states']['statistics'] = 'unavailable: ' + str(value)
    except Exception as exc:
        result['states']['statistics'] = (
            f'unavailable: {type(exc).__name__}: {exc}')
    if connection_for is None:
        result['states']['dependencies'] = 'unavailable: no connection'
        return result
    try:
        connection = connection_for(chain.get('did'))
        dependencies, dependents = inherited_dependencies(chain, connection)
        result['dependencies'] = dependencies
        result['dependents'] = dependents
        result['states']['dependencies'] = 'inherited'
    except Exception as exc:
        result['states']['dependencies'] = (
            f'unavailable: {type(exc).__name__}: {exc}')
    return result
