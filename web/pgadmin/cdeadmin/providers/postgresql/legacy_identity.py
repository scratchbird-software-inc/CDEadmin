"""Legacy identity chain for PostgreSQL provider resources.

The inherited PostgreSQL tools and dialogs (backup, restore, maintenance,
the debugger, the object dialogs, Browse data) address an object by the
route chain ``gid/sid/did/scid/tid/<oid>``: server group, server,
database OID, schema OID, owning relation OID and the object's own OID,
with the legacy node type choosing the route. Captured provider resources
carry the server, database and object OID but not the schema OID, the
owning relation or the node type (parity matrix, blocker 5, 2026-11-08).

This module derives the rest from what capture already holds, so a
provider node can open the legacy tool for the same object. Nothing here
talks to the server: the schema OIDs come from the captured namespaces
and the owning relation from the capture's native ownership links.
"""

# Fixed pg_type OIDs (src/include/catalog/pg_type.dat): a function whose
# return type is one of these is a trigger function to the legacy tree.
TRIGGER_RETURN_TYPE_OIDS = frozenset({2279, 3838})

# Constraints are one capture kind but five legacy node types, chosen by
# pg_constraint.contype; a constraint on a domain is a sixth.
CONSTRAINT_NODE_TYPES = {
    'p': 'primary_key', 'u': 'unique_constraint', 'f': 'foreign_key',
    'c': 'check_constraint', 'x': 'exclusion_constraint',
}

# Capture resource kind -> legacy node type. ``None`` records a kind the
# legacy tree has no node for, so callers can tell "no legacy route" from
# "kind not mapped yet" (a KeyError).
LEGACY_NODE_TYPES = {
    'database': 'database',
    'schema': 'schema',
    'column': 'column',
    'table': 'table',
    'partitioned-table': 'table',
    'view': 'view',
    'materialized-view': 'mview',
    'foreign-table': 'foreign_table',
    'sequence': 'sequence',
    'index': 'index',
    'partitioned-index': 'index',
    'composite-relation': None,
    'toast-table': None,
    'relation': None,
    'type': 'type',
    'domain': 'domain',
    'function': 'function',
    'procedure': 'procedure',
    'aggregate': 'aggregate',
    'window-function': 'function',
    'routine': None,
    'trigger': 'trigger',
    'rule': 'rule',
    'policy': 'row_security_policy',
    'extension': 'extension',
    'collation': 'collation',
    'conversion': None,
    'operator': 'operator',
    'operator-class': None,
    'operator-family': None,
    'text-search-configuration': 'fts_configuration',
    'text-search-dictionary': 'fts_dictionary',
    'text-search-parser': 'fts_parser',
    'text-search-template': 'fts_template',
    'extended-statistics': None,
    'cast': 'cast',
    'transform': None,
    'default-privileges': None,
    'user-mapping': 'user_mapping',
    'large-object': None,
    'language': 'language',
    'event-trigger': 'event_trigger',
    'publication': 'publication',
    'foreign-data-wrapper': 'foreign_data_wrapper',
    'foreign-server': 'foreign_server',
    'access-method': None,
    'subscription': 'subscription',
}

# Legacy node types whose route carries the owning relation as ``tid``.
RELATION_OWNED = frozenset({
    'index', 'trigger', 'rule', 'row_security_policy',
    *CONSTRAINT_NODE_TYPES.values(),
})


def _parent_oid(native, catalog):
    """Return the OID of the native owner when it is in ``catalog``."""
    owner = native.get('navigator_parent_resource_id') or ''
    prefix = f'postgresql:{catalog}:'
    if not owner.startswith(prefix):
        return None
    try:
        return int(owner[len(prefix):])
    except ValueError:
        return None


def schema_oids(resources):
    """Map schema name -> OID from the captured namespaces."""
    result = {}
    for item in resources:
        native = item.get('native') or {}
        if native.get('catalog') == 'pg_namespace':
            result[item.get('display_name')] = native.get('oid')
    return result


def _oid(value):
    """An OID from the capture (int, or text in ``to_jsonb`` rows)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def foreign_server_wrappers(resources):
    """Map foreign server OID -> its foreign-data-wrapper OID."""
    result = {}
    for item in resources:
        native = item.get('native') or {}
        if native.get('catalog') == 'pg_foreign_server':
            wrapper = _oid((native.get('catalog_row') or {}).get('srvfdw'))
            if wrapper:
                result[_oid(native.get('oid'))] = wrapper
    return result


def constraint_indexes(resources):
    """Map an index OID -> (contype, constraint OID) for indexes that back
    a primary key, unique or exclusion constraint. The inherited tree shows
    those as constraint nodes, never as indexes."""
    result = {}
    for item in resources:
        native = item.get('native') or {}
        if native.get('catalog') != 'pg_constraint':
            continue
        row = native.get('catalog_row') or {}
        if row.get('contype') in ('p', 'u', 'x') and row.get('conindid'):
            result[int(row['conindid'])] = (row['contype'], native.get('oid'))
    return result


def legacy_node_type(resource_kind, native):
    """Return the legacy node type for a captured resource, or ``None``."""
    row = native.get('catalog_row') or {}
    if resource_kind == 'constraint':
        if row.get('contypid'):
            return 'domain_constraints'
        return CONSTRAINT_NODE_TYPES.get(row.get('contype'))
    if resource_kind in {'function', 'window-function'}:
        if row.get('prorettype') in TRIGGER_RETURN_TYPE_OIDS:
            return 'trigger_function'
    if resource_kind in {'table', 'partitioned-table'}:
        if row.get('relispartition'):
            return 'partition'
    return LEGACY_NODE_TYPES.get(resource_kind)


def legacy_route(server_id, database_id, resource_kind, native,
                 schemas, backed=None, wrappers=None):
    """Return the legacy route chain for one captured resource.

    ``schemas`` maps schema name to OID (see :func:`schema_oids`) and
    ``backed`` maps index OID to its constraint (see
    :func:`constraint_indexes`). The result always carries ``sid``,
    ``did`` and ``oid``; ``scid`` and ``tid`` are ``None`` when the object
    has no schema or no owning relation, and ``node_type`` is ``None``
    when the legacy tree has no node for the kind. ``gid`` is added by the
    tree layer, which knows the server group. An index that backs a
    constraint routes to the constraint node; its OID stays the index OID.
    ``wrappers`` maps foreign server OID to wrapper OID (see
    :func:`foreign_server_wrappers`): foreign servers and user mappings
    carry the wrapper as ``fid``, which their inherited views take.
    """
    node_type = legacy_node_type(resource_kind, native)
    object_id = native.get('oid')
    backing = (backed or {}).get(object_id) if node_type == 'index' else None
    if backing:
        # The inherited constraint nodes are keyed by the index OID.
        node_type = CONSTRAINT_NODE_TYPES.get(backing[0])
    schema = native.get('schema')
    scid = schemas.get(schema) if schema else None
    if resource_kind == 'schema':
        scid = native.get('oid')
    tid = None
    if node_type in RELATION_OWNED:
        tid = _parent_oid(native, 'pg_class')
    elif node_type == 'domain_constraints':
        tid = (native.get('catalog_row') or {}).get('contypid')
    elif node_type == 'partition':
        # Capture attaches the pg_inherits row to the child relation.
        inherits = (native.get('children') or {}).get('pg_inherits') or []
        tid = inherits[0].get('inhparent') if inherits else None
    elif node_type == 'user_mapping':
        tid = _parent_oid(native, 'pg_foreign_server')
    chain = {
        'sid': server_id,
        'did': database_id,
        'scid': scid,
        'tid': tid,
        'oid': object_id,
        'node_type': node_type,
    }
    if node_type == 'foreign_server':
        chain['fid'] = _oid((native.get('catalog_row') or {}).get('srvfdw'))
    elif node_type == 'user_mapping':
        chain['fid'] = (wrappers or {}).get(tid)
    return chain


def implicit_type_ids(resources, include_system=False):
    """Resource ids of captured types the inherited Types node hides.

    The inherited node (``types/.../nodes.sql``) lists neither array types
    (names starting with an underscore) nor, unless system objects are
    shown, the row types of relations other than free-standing composite
    types. The provider tree follows it (M3 follow-up, 2026-11-11).
    """
    relkinds = {}
    for item in resources:
        native = item.get('native') or {}
        if native.get('catalog') == 'pg_class':
            relkinds[_oid(native.get('oid'))] = (
                native.get('catalog_row') or {}).get('relkind')
    hidden = set()
    for item in resources:
        native = item.get('native') or {}
        if native.get('catalog') != 'pg_type' or \
                item.get('resource_kind') != 'type':
            continue
        row = native.get('catalog_row') or {}
        name = row.get('typname') or item.get('display_name') or ''
        if name.startswith('_'):
            hidden.add(item['resource_id'])
            continue
        # The captured row carries OIDs as text.
        relation = _oid(row.get('typrelid'))
        if (not include_system and relation and
                relkinds.get(relation, 'c') != 'c'):
            hidden.add(item['resource_id'])
    return hidden
