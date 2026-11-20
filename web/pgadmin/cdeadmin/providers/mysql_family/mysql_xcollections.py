"""Native MySQL 9.7 X Plugin collection discovery, administration, and CRUD."""
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
import json
import re
import uuid

from ...sdk import RelationalClientError
from .mysql_xprotocol import ALLOWED_FILTER_OPS, XProtocolError, XProtocolSession

KIND = 'x-collection'
KEY = 'mysql_xcollection'

OPERATIONS = {
    'create': 'Create X collection',
    'ensure': 'Ensure X collection',
    'modify_options': 'Modify X collection validation',
    'drop': 'Drop X collection',
    'create_index': 'Create X collection index',
    'drop_index': 'Drop X collection index',
    'insert_documents': 'Insert X collection documents',
    'find_documents': 'Find X collection documents',
    'modify_documents': 'Modify X collection documents',
    'remove_documents': 'Remove X collection documents',
}
READ_OPERATIONS = frozenset({'find_documents'})
DESTRUCTIVE_OPERATIONS = frozenset({'drop', 'drop_index', 'remove_documents'})
VALIDATION_LEVELS = ('OFF', 'STRICT')
INDEX_TYPES = ('INDEX', 'SPATIAL', 'FULLTEXT')


def _ident_name(value, label):
    if not isinstance(value, str) or not value or len(value) > 64 or '\x00' in value:
        raise RelationalClientError(f'{label} requires 1 to 64 characters without NUL')
    return value


def _parse_schema_json(raw):
    if raw in (None, ''):
        return None
    if isinstance(raw, Mapping):
        parsed = dict(raw)
    elif isinstance(raw, str):
        if len(raw.encode('utf-8')) > 65536 or '\x00' in raw:
            raise RelationalClientError('Validation JSON schema must be bounded UTF-8 text without NUL')
        try:
            parsed = json.loads(raw)
        except ValueError:
            raise RelationalClientError('Validation JSON schema must be a valid JSON object') from None
    else:
        raise RelationalClientError('Validation JSON schema must be a JSON object')
    if not isinstance(parsed, dict) or not parsed:
        raise RelationalClientError('Validation JSON schema must be a non-empty JSON object')
    return parsed


def _coerce_typed_scalar(value_type, raw_value):
    vtype = (value_type or 'STRING').upper()
    if vtype == 'NULL':
        return None
    if vtype == 'STRING':
        if not isinstance(raw_value, str):
            raw_value = '' if raw_value is None else str(raw_value)
        return raw_value
    if vtype == 'INTEGER':
        if isinstance(raw_value, bool):
            raise RelationalClientError('Integer filter/update value cannot be boolean')
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            raise RelationalClientError('Invalid integer filter/update value') from None
    if vtype == 'FLOAT':
        if isinstance(raw_value, bool):
            raise RelationalClientError('Float filter/update value cannot be boolean')
        try:
            return float(raw_value)
        except (TypeError, ValueError):
            raise RelationalClientError('Invalid numeric filter/update value') from None
    if vtype == 'BOOLEAN':
        if isinstance(raw_value, bool):
            return raw_value
        if str(raw_value).lower() in {'true', '1'}:
            return True
        if str(raw_value).lower() in {'false', '0'}:
            return False
        raise RelationalClientError('Boolean value must be true or false')
    if vtype == 'JSON':
        if isinstance(raw_value, (dict, list)):
            return deepcopy(raw_value)
        try:
            return json.loads(str(raw_value))
        except ValueError:
            raise RelationalClientError('Invalid JSON value in document operation') from None
    raise RelationalClientError(f'Unsupported typed scalar kind: {value_type}')


def _normalize_predicates(raw_predicates):
    if raw_predicates in (None, ''):
        return []
    if not isinstance(raw_predicates, list) or len(raw_predicates) > 32:
        raise RelationalClientError('Supply at most 32 typed filter predicates')
    normalized = []
    for item in raw_predicates:
        if not isinstance(item, Mapping):
            raise RelationalClientError('Each filter predicate must be a structured row')
        path = item.get('path')
        if not isinstance(path, str) or not path or len(path) > 256 or '\x00' in path:
            raise RelationalClientError('Each filter predicate requires a document path')
        op = item.get('operator', '==')
        if op not in ALLOWED_FILTER_OPS:
            raise RelationalClientError(f'Unsupported filter operator: {op}')
        vtype = item.get('value_type', 'STRING')
        val = _coerce_typed_scalar(vtype, item.get('value'))
        normalized.append({'path': path, 'operator': op, 'value_type': vtype, 'value': val})
    return normalized


def _target_collection(target):
    if not isinstance(target, Mapping) or target.get('resource_kind') != KIND:
        raise RelationalClientError('Select a native MySQL X collection resource')
    path = target.get('display_path')
    if not isinstance(path, (list, tuple)) or len(path) != 2:
        raise RelationalClientError('Select a database-qualified MySQL X collection')
    schema = _ident_name(path[0], 'Collection schema')
    name = _ident_name(path[1], 'Collection name')
    native = target.get('native') or {}
    return schema, name, native.get('server_uuid')


def compile_operation(operation, draft, target):
    if operation not in OPERATIONS or not isinstance(draft, Mapping):
        raise RelationalClientError('Select a typed native MySQL X collection operation')
    if operation in {'create', 'ensure'} and (target is None or target.get('resource_kind') in {None, 'database', KIND}):
        if isinstance(target, Mapping) and target.get('resource_kind') == KIND:
            schema, default_name, server_uuid = _target_collection(target)
            schema = _ident_name(draft.get('database', schema), 'Collection schema')
            name = _ident_name(draft.get('name', default_name), 'Collection name')
            expected_confirm = target.get('display_name')
        elif isinstance(target, Mapping) and target.get('resource_kind') == 'database':
            schema = _ident_name(draft.get('database') or target.get('display_name'), 'Collection schema')
            name = _ident_name(draft.get('name'), 'Collection name')
            server_uuid = (target.get('native') or {}).get('server_uuid')
            expected_confirm = None
        else:
            schema = _ident_name(draft.get('database'), 'Collection schema')
            name = _ident_name(draft.get('name'), 'Collection name')
            server_uuid = None
            expected_confirm = None
    else:
        schema, name, server_uuid = _target_collection(target)
        expected_confirm = target.get('display_name')

    if expected_confirm is not None and draft.get('confirmation') != expected_confirm:
        raise RelationalClientError('Confirm the exact X collection name')

    x_port_override = draft.get('mysqlx_port')
    if x_port_override in ('', None):
        x_port_override = None
    elif type(x_port_override) is not int or isinstance(x_port_override, bool) or not (1 <= x_port_override <= 65535):
        raise RelationalClientError('X Protocol port must be an integer 1..65535')

    if operation in {'create', 'ensure'}:
        allowed = {'database', 'name', 'reuse_existing', 'validation_level', 'validation_schema', 'mysqlx_port', 'confirmation'}
        if set(draft) - allowed:
            raise RelationalClientError(f'Unknown X collection {operation} option')
        level = str(draft.get('validation_level', 'OFF') or 'OFF').upper()
        if level not in VALIDATION_LEVELS:
            raise RelationalClientError('Validation level must be OFF or STRICT')
        schema_obj = _parse_schema_json(draft.get('validation_schema')) or {'type': 'object'}
        reuse = bool(draft.get('reuse_existing', False))
        validation = {'level': level.lower(), 'schema': schema_obj}
        options = {'validation': validation}
        if operation == 'create' and reuse:
            options['reuse_existing'] = True
        admin_cmd = 'create_collection' if operation == 'create' else 'ensure_collection'
        x_args = {'schema': schema, 'name': name, 'options': options}
        preview = f'mysqlx.{admin_cmd}({json.dumps(x_args, sort_keys=True)})'
        intent_body = {'protocol_kind': 'admin', 'admin_command': admin_cmd, 'admin_args': x_args}

    elif operation == 'modify_options':
        allowed = {'validation_level', 'validation_schema', 'mysqlx_port', 'confirmation'}
        if set(draft) - allowed:
            raise RelationalClientError('Unknown modify_collection_options field')
        level = draft.get('validation_level')
        schema_obj = _parse_schema_json(draft.get('validation_schema'))
        validation = {}
        if level not in (None, ''):
            level_up = str(level).upper()
            if level_up not in VALIDATION_LEVELS:
                raise RelationalClientError('Validation level must be OFF or STRICT')
            validation['level'] = level_up.lower()
        if schema_obj is not None:
            validation['schema'] = schema_obj
        if not validation:
            raise RelationalClientError('Specify validation_level and/or validation_schema to modify')
        x_args = {'schema': schema, 'name': name, 'options': {'validation': validation}}
        preview = f'mysqlx.modify_collection_options({json.dumps(x_args, sort_keys=True)})'
        intent_body = {'protocol_kind': 'admin', 'admin_command': 'modify_collection_options', 'admin_args': x_args}

    elif operation == 'drop':
        if set(draft) - {'mysqlx_port', 'confirmation'}:
            raise RelationalClientError('Unknown drop_collection field')
        x_args = {'schema': schema, 'name': name}
        preview = f'mysqlx.drop_collection({json.dumps(x_args, sort_keys=True)})'
        intent_body = {'protocol_kind': 'admin', 'admin_command': 'drop_collection', 'admin_args': x_args}

    elif operation == 'create_index':
        allowed = {'index_name', 'index_type', 'unique', 'with_parser', 'fields', 'mysqlx_port', 'confirmation'}
        if set(draft) - allowed:
            raise RelationalClientError('Unknown create_collection_index field')
        idx_name = _ident_name(draft.get('index_name'), 'Collection index name')
        idx_type = str(draft.get('index_type', 'INDEX') or 'INDEX').upper()
        if idx_type not in INDEX_TYPES:
            raise RelationalClientError('Collection index type must be INDEX, SPATIAL, or FULLTEXT')
        unique = bool(draft.get('unique', False))
        if unique and idx_type in {'SPATIAL', 'FULLTEXT'}:
            raise RelationalClientError(f'Unique {idx_type} collection index is not supported by MySQL X Plugin')
        parser_name = draft.get('with_parser')
        if parser_name not in (None, '') and idx_type != 'FULLTEXT':
            raise RelationalClientError('with_parser applies only to FULLTEXT collection indexes')
        raw_fields = draft.get('fields')
        if not isinstance(raw_fields, list) or not (1 <= len(raw_fields) <= 16):
            raise RelationalClientError('Specify 1 to 16 indexed document fields')
        constraints = []
        for f in raw_fields:
            if not isinstance(f, Mapping):
                raise RelationalClientError('Each indexed document field must be an object')
            member = f.get('field') or f.get('member')
            if not isinstance(member, str) or not member.startswith('$.') or len(member) > 256 or '\x00' in member:
                raise RelationalClientError('Indexed document field path must start with "$."')
            entry = {'member': member, 'required': bool(f.get('required', False))}
            if f.get('type') not in (None, ''):
                entry['type'] = str(f['type'])
            if f.get('array') is True:
                entry['array'] = True
            constraints.append(entry)
        x_args = {
            'schema': schema,
            'collection': name,
            'name': idx_name,
            'unique': unique,
            'type': idx_type,
            'constraint': constraints,
        }
        if parser_name not in (None, ''):
            x_args['with_parser'] = _ident_name(str(parser_name), 'FULLTEXT parser')
        preview = f'mysqlx.create_collection_index({json.dumps(x_args, sort_keys=True)})'
        intent_body = {'protocol_kind': 'admin', 'admin_command': 'create_collection_index', 'admin_args': x_args}

    elif operation == 'drop_index':
        allowed = {'index_name', 'mysqlx_port', 'confirmation'}
        if set(draft) - allowed:
            raise RelationalClientError('Unknown drop_collection_index field')
        idx_name = _ident_name(draft.get('index_name'), 'Collection index name')
        x_args = {'schema': schema, 'collection': name, 'name': idx_name}
        preview = f'mysqlx.drop_collection_index({json.dumps(x_args, sort_keys=True)})'
        intent_body = {'protocol_kind': 'admin', 'admin_command': 'drop_collection_index', 'admin_args': x_args}

    elif operation == 'insert_documents':
        allowed = {'documents', 'upsert', 'mysqlx_port', 'confirmation'}
        if set(draft) - allowed:
            raise RelationalClientError('Unknown insert_documents field')
        raw_docs = draft.get('documents')
        if not isinstance(raw_docs, list) or not (1 <= len(raw_docs) <= 100):
            raise RelationalClientError('Supply 1 to 100 JSON documents to insert')
        docs = []
        for item in raw_docs:
            doc_str = item.get('document') if isinstance(item, Mapping) and 'document' in item else item
            parsed = _parse_schema_json(doc_str)
            docs.append(parsed)
        upsert = bool(draft.get('upsert', False))
        preview = f'Mysqlx.Crud.Insert(schema={schema!r}, collection={name!r}, count={len(docs)}, upsert={upsert})'
        intent_body = {'protocol_kind': 'crud_insert', 'documents': docs, 'upsert': upsert}

    elif operation == 'find_documents':
        allowed = {'predicates', 'combinator', 'limit', 'offset', 'sort_path', 'sort_direction', 'mysqlx_port', 'confirmation'}
        if set(draft) - allowed:
            raise RelationalClientError('Unknown find_documents field')
        predicates = _normalize_predicates(draft.get('predicates'))
        combinator = str(draft.get('combinator', 'AND') or 'AND').upper()
        if combinator not in {'AND', 'OR'}:
            raise RelationalClientError('Filter combinator must be AND or OR')
        limit = draft.get('limit', 50)
        offset = draft.get('offset', 0)
        if type(limit) is not int or not (1 <= limit <= 500) or type(offset) is not int or offset < 0:
            raise RelationalClientError('Find limit must be 1..500 and offset >= 0')
        sort_path = draft.get('sort_path') or None
        sort_dir = str(draft.get('sort_direction', 'ASC') or 'ASC').upper()
        if sort_dir not in {'ASC', 'DESC'}:
            raise RelationalClientError('Sort direction must be ASC or DESC')
        preview = f'Mysqlx.Crud.Find(schema={schema!r}, collection={name!r}, limit={limit}, offset={offset})'
        intent_body = {
            'protocol_kind': 'crud_find',
            'predicates': predicates,
            'combinator': combinator,
            'limit': limit,
            'offset': offset,
            'sort_path': sort_path,
            'sort_direction': sort_dir,
        }

    elif operation == 'modify_documents':
        allowed = {'predicates', 'combinator', 'updates', 'limit', 'mysqlx_port', 'confirmation'}
        if set(draft) - allowed:
            raise RelationalClientError('Unknown modify_documents field')
        predicates = _normalize_predicates(draft.get('predicates'))
        if not predicates:
            raise RelationalClientError('Document modify requires at least one filter predicate')
        combinator = str(draft.get('combinator', 'AND') or 'AND').upper()
        raw_updates = draft.get('updates')
        if not isinstance(raw_updates, list) or not (1 <= len(raw_updates) <= 32):
            raise RelationalClientError('Specify 1 to 32 document update operations')
        updates = []
        for u in raw_updates:
            if not isinstance(u, Mapping):
                raise RelationalClientError('Each document update entry must be structured')
            op_type = str(u.get('operation', 'ITEM_SET')).upper()
            if op_type not in {'ITEM_SET', 'ITEM_REMOVE', 'ITEM_REPLACE', 'ARRAY_APPEND', 'MERGE_PATCH'}:
                raise RelationalClientError(f'Unsupported X document update operation: {op_type}')
            path = '$' if op_type == 'MERGE_PATCH' and not u.get('path') else u.get('path')
            if not isinstance(path, str) or not path:
                raise RelationalClientError('Update operation requires a document path')
            val = None if op_type == 'ITEM_REMOVE' else _coerce_typed_scalar(
                'JSON' if op_type == 'MERGE_PATCH' else u.get('value_type', 'STRING'),
                u.get('value'),
            )
            updates.append({'operation': op_type, 'path': path, 'value': val})
        limit = draft.get('limit')
        if limit in ('', None):
            limit = None
        elif type(limit) is not int or limit < 1:
            raise RelationalClientError('Document modify limit must be a positive integer')
        preview = f'Mysqlx.Crud.Update(schema={schema!r}, collection={name!r}, operations={len(updates)})'
        intent_body = {
            'protocol_kind': 'crud_modify',
            'predicates': predicates,
            'combinator': combinator,
            'updates': updates,
            'limit': limit,
        }

    else:  # remove_documents
        allowed = {'predicates', 'combinator', 'limit', 'mysqlx_port', 'confirmation'}
        if set(draft) - allowed:
            raise RelationalClientError('Unknown remove_documents field')
        predicates = _normalize_predicates(draft.get('predicates'))
        if not predicates:
            raise RelationalClientError('Document remove requires at least one filter predicate')
        combinator = str(draft.get('combinator', 'AND') or 'AND').upper()
        limit = draft.get('limit')
        if limit in ('', None):
            limit = None
        elif type(limit) is not int or limit < 1:
            raise RelationalClientError('Document remove limit must be a positive integer')
        preview = f'Mysqlx.Crud.Delete(schema={schema!r}, collection={name!r})'
        intent_body = {
            'protocol_kind': 'crud_remove',
            'predicates': predicates,
            'combinator': combinator,
            'limit': limit,
        }

    return {
        'statements': [{'source': preview, 'preview_source': preview, 'parameters': ()}],
        KEY: {
            'operation': operation,
            'schema': schema,
            'collection': name,
            'server_uuid': server_uuid,
            'mysqlx_port': x_port_override,
            'draft': deepcopy(dict(draft)),
            'target': deepcopy(dict(target)) if isinstance(target, Mapping) else None,
            **intent_body,
        },
        'warnings': [
            'Executes natively over MySQL X Protocol (Mysqlx protobuf messages on X Plugin), never fabricated SQL.',
        ],
    }


def discover_collections_from_rows(column_records, constraint_records):
    """Identify genuine MySQL X collections from pre-observed COLUMNS and TABLE_CONSTRAINTS rows."""
    by_table = {}
    for row in column_records:
        t_schema = row.get('table_schema')
        t_name = row.get('table_name')
        if isinstance(t_schema, str) and isinstance(t_name, str):
            by_table.setdefault((t_schema, t_name), []).append(row)
    constraints = {}
    for row in constraint_records:
        ctype = str(row.get('constraint_type', 'CHECK')).upper()
        if ctype == 'CHECK' and str(row.get('constraint_name', '')).startswith('$val_strict_'):
            constraints[(row.get('table_schema'), row.get('table_name'))] = str(row.get('enforced', '')).upper() == 'YES'
    found = []
    for (schema, tname), tcols in sorted(by_table.items()):
        has_doc = False
        has_id = False
        schema_expr = None
        other_non_gen = False
        for c in tcols:
            cname = c.get('column_name')
            dtype = str(c.get('data_type', '')).lower()
            ctype = str(c.get('column_type', '')).lower()
            extra = str(c.get('extra', '')).upper()
            ckey = str(c.get('column_key', '')).upper()
            if cname == 'doc' and dtype == 'json' and 'GENERATED' not in extra:
                has_doc = True
            elif cname == '_id' and ctype == 'varbinary(32)' and 'STORED GENERATED' in extra and ckey == 'PRI':
                has_id = True
            elif cname == '_json_schema' and dtype == 'json' and 'GENERATED' in extra:
                schema_expr = c.get('generation_expression', '')
            elif 'GENERATED' not in extra:
                other_non_gen = True
        if has_doc and has_id and schema_expr is not None and not other_non_gen:
            enforced = constraints.get((schema, tname), False)
            found.append({
                'schema': schema,
                'name': tname,
                'validation_level': 'STRICT' if enforced else 'OFF',
                'validation_schema_expression': schema_expr,
            })
    return found


def discover_collections_from_catalog(optional_records, selected_database=None):
    """Identify genuine MySQL X collections without misclassifying ordinary JSON SQL tables.

    Mirrors Admin_command_collection_handler::is_collection in
    plugin/x/src/admin_cmd_collection_handler.cc:
    - doc JSON
    - _id VARBINARY(32) STORED GENERATED PRIMARY KEY
    - _json_schema JSON VIRTUAL GENERATED
    - all other columns (if any) are GENERATED ($ix_* collection index columns)
    """
    where = (
        'WHERE TABLE_SCHEMA = %s'
        if selected_database
        else "WHERE TABLE_SCHEMA NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')"
    )
    params = (selected_database,) if selected_database else None
    cols = optional_records(
        'SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE, COLUMN_TYPE, EXTRA, '
        'COLUMN_KEY, GENERATION_EXPRESSION '
        f'FROM information_schema.COLUMNS {where} ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION',
        params,
    )
    chk_rows = optional_records(
        'SELECT TABLE_SCHEMA, TABLE_NAME, CONSTRAINT_NAME, CONSTRAINT_TYPE, ENFORCED '
        f"FROM information_schema.TABLE_CONSTRAINTS {where} AND CONSTRAINT_TYPE = 'CHECK'",
        params,
    )
    return discover_collections_from_rows(cols, chk_rows)


def _with_x_session(client, route, schema, callback, *, port_override=None):
    x_port = port_override or route.get('mysqlx_port', 33060)
    x_socket = route.get('mysqlx_socket')
    x_host = route.get('mysqlx_host') or route.get('host', '127.0.0.1')
    user = route.get('user') or route.get('username') or 'root'
    use_tls = route.get('mysqlx_tls', True)
    ssl_ca = route.get('ssl_ca')
    ssl_verify = bool(route.get('ssl_verify_cert', False))

    def connect_and_run(password):
        sess = XProtocolSession.connect(
            host=x_host,
            port=int(x_port),
            unix_socket=x_socket,
            user=user,
            password=password,
            schema='',
            timeout=10.0,
            use_tls=bool(use_tls),
            ssl_ca=ssl_ca,
            ssl_verify_cert=ssl_verify,
        )
        try:
            return callback(sess)
        finally:
            sess.close()

    if 'password' in route and route['password'] is not None:
        return connect_and_run(route['password'])
    if hasattr(client, '_tool_secrets'):
        return client._tool_secrets(
            route,
            lambda secrets_list: connect_and_run(secrets_list[0] if secrets_list else ''),
        )
    return connect_and_run('')


def _observe_x_state(sess, schema, collection):
    id_res = sess.execute_sql('SELECT VERSION(), @@server_uuid, CURRENT_USER(), USER()')
    if len(id_res['rows']) != 1:
        raise RelationalClientError('MySQL X Protocol server identity is unavailable')
    version, server_uuid, effective_user, session_user = id_res['rows'][0]
    if str(version).split('-')[0] != '9.7.0':
        raise RelationalClientError('MySQL X collection administration requires MySQL 9.7.0')
    identity = {
        'version': str(version),
        'server_uuid': str(server_uuid),
        'effective_principal': str(effective_user),
        'authenticated_principal': str(session_user),
    }
    objs = sess.execute_admin('list_objects', {'schema': schema, 'pattern': collection})
    obj_map = {str(r[0]): str(r[1]) for r in objs['rows'] if len(r) >= 2}
    object_type = obj_map.get(collection)
    validation = None
    if object_type == 'COLLECTION':
        opt_res = sess.execute_admin(
            'get_collection_options',
            {'schema': schema, 'name': collection, 'options': ['validation']},
        )
        if opt_res['rows'] and opt_res['rows'][0]:
            try:
                validation = json.loads(opt_res['rows'][0][0]).get('validation')
            except ValueError:
                validation = opt_res['rows'][0][0]
    return identity, {'exists': object_type is not None, 'object_type': object_type, 'validation': validation}


def bind_review(client, planned):
    payload = planned['provider_payload']
    intent = payload['compiled'][KEY]
    try:
        def review_cb(sess):
            identity, obj_state = _observe_x_state(sess, intent['schema'], intent['collection'])
            if intent.get('server_uuid') and identity['server_uuid'] != intent['server_uuid']:
                raise RelationalClientError('Live MySQL X server_uuid differs from the selected server')
            intent['server_uuid'] = identity['server_uuid']
            op = intent['operation']
            if op not in {'create', 'ensure'}:
                if obj_state['object_type'] != 'COLLECTION':
                    err = RelationalClientError(
                        f"Object `{intent['schema']}`.`{intent['collection']}` is "
                        f"{obj_state['object_type'] or 'missing'}, not a native MySQL X COLLECTION"
                    )
                    err.errno = 5157
                    raise err
            elif obj_state['exists'] and obj_state['object_type'] != 'COLLECTION':
                err = RelationalClientError(
                    f"Object `{intent['schema']}`.`{intent['collection']}` already exists as {obj_state['object_type']}, not a COLLECTION"
                )
                err.errno = 5157
                raise err
            intent['review'] = {
                'execution_identity': identity,
                'collection_state': obj_state,
                'review_nonce': uuid.uuid4().hex,
            }
            planned['command_preview'].update(
                native_execution_identity=identity,
                native_x_collection_state=obj_state,
            )
            return planned

        return _with_x_session(
            client, payload['route'], intent['schema'], review_cb, port_override=intent.get('mysqlx_port')
        )
    except RelationalClientError:
        raise
    except XProtocolError as exc:
        err = RelationalClientError(f'MySQL X Protocol review failed: {exc}')
        err.errno = exc.errno
        err.sqlstate = exc.sqlstate
        err.native_status_codes = (exc.errno,) if type(exc.errno) is int else ()
        err.automatic_retry = False
        raise err from None
    except Exception as exc:
        raise RelationalClientError(f'MySQL X Protocol connection failed ({type(exc).__name__}): {exc}') from None


def apply(client, request, connection=None):
    if connection is not None:
        raise RelationalClientError('MySQL X collection operations require a dedicated X Protocol session')
    payload = request['provider_payload']
    compiled = payload['compiled']
    intent = compiled[KEY]
    checked = deepcopy(compiled)
    review = checked[KEY].pop('review', None)
    orig_uuid = ((intent.get('target') or {}).get('native') or {}).get('server_uuid')
    if orig_uuid is None:
        checked[KEY]['server_uuid'] = None
    if not isinstance(review, Mapping) or compile_operation(
        intent['operation'], intent['draft'], intent['target']
    ) != checked:
        raise RelationalClientError('Review the exact MySQL X collection operation before dispatch')
    consumed = getattr(client, '_consumed_xcollection_reviews', None)
    if consumed is None:
        consumed = set()
        client._consumed_xcollection_reviews = consumed
    nonce = review.get('review_nonce')
    if not isinstance(nonce, str) or nonce in consumed:
        raise RelationalClientError('This reviewed MySQL X collection plan was already consumed; replay is refused')

    dispatched = False
    acknowledged = False
    try:
        def apply_cb(sess):
            nonlocal dispatched, acknowledged
            identity, obj_state = _observe_x_state(sess, intent['schema'], intent['collection'])
            if identity != review.get('execution_identity'):
                raise RelationalClientError('MySQL X server or principal identity changed since review')
            op = intent['operation']
            if op not in {'create', 'ensure'} and obj_state['object_type'] != 'COLLECTION':
                err = RelationalClientError(
                    f"Target `{intent['schema']}`.`{intent['collection']}` is no longer an X COLLECTION"
                )
                err.errno = 5157
                raise err
            consumed.add(nonce)
            dispatched = True
            kind = intent['protocol_kind']
            if kind == 'admin':
                res = sess.execute_admin(intent['admin_command'], intent['admin_args'])
            elif kind == 'crud_insert':
                res = sess.crud_insert_documents(
                    intent['schema'], intent['collection'], intent['documents'], upsert=intent['upsert']
                )
            elif kind == 'crud_find':
                res = sess.crud_find_documents(
                    intent['schema'],
                    intent['collection'],
                    predicates=intent['predicates'],
                    combinator=intent['combinator'],
                    limit=intent['limit'],
                    offset=intent['offset'],
                    sort_path=intent['sort_path'],
                    sort_direction=intent['sort_direction'],
                )
            elif kind == 'crud_modify':
                res = sess.crud_modify_documents(
                    intent['schema'],
                    intent['collection'],
                    predicates=intent['predicates'],
                    combinator=intent['combinator'],
                    operations=intent['updates'],
                    limit=intent['limit'],
                )
            elif kind == 'crud_remove':
                res = sess.crud_remove_documents(
                    intent['schema'],
                    intent['collection'],
                    predicates=intent['predicates'],
                    combinator=intent['combinator'],
                    limit=intent['limit'],
                )
            else:
                raise RelationalClientError(f'Unknown X collection protocol kind: {kind}')
            acknowledged = True
            _, after_state = _observe_x_state(sess, intent['schema'], intent['collection'])
            return {
                'accepted': True,
                'commit_requested': False,
                'rollback_requested': False,
                'native_implicit_commit': kind == 'admin',
                'staged_in_provider_session': False,
                'automatic_retry': False,
                'transaction_finality_interpreted_by_common_code': False,
                'xcollection_result': {
                    'operation': op,
                    'schema': intent['schema'],
                    'collection': intent['collection'],
                    'protocol': 'mysqlx-protobuf',
                    'execution_identity': identity,
                    'before': obj_state,
                    'after': after_state,
                    'rows_affected': res['rows_affected'],
                    'generated_document_ids': res['generated_document_ids'],
                    'documents': res.get('documents', []),
                    'warnings': res['warnings'],
                    'truncated': res['truncated'],
                    'native_dispatched': True,
                    'native_acknowledged': True,
                    'observed_at': datetime.now(timezone.utc).isoformat(),
                },
            }

        return _with_x_session(
            client, payload['route'], intent['schema'], apply_cb, port_override=intent.get('mysqlx_port')
        )
    except RelationalClientError as exc:
        exc.native_dispatched = dispatched
        exc.native_acknowledged = acknowledged
        exc.automatic_retry = False
        raise
    except XProtocolError as exc:
        err = RelationalClientError(
            f'MySQL X Plugin rejected {intent["operation"]} (error {exc.errno}, SQLSTATE {exc.sqlstate}): {exc}'
        )
        err.errno = exc.errno
        err.sqlstate = exc.sqlstate
        err.native_status_codes = (exc.errno,) if type(exc.errno) is int else ()
        err.native_dispatched = dispatched
        err.native_acknowledged = acknowledged
        err.automatic_retry = False
        raise err from None
    except Exception as exc:
        err = RelationalClientError(f'MySQL X collection operation failed ({type(exc).__name__}): {exc}')
        err.native_dispatched = dispatched
        err.native_acknowledged = acknowledged
        err.automatic_retry = False
        raise err from None
