"""DuckDB retained-session administration, continuity guards, and write codecs."""
from collections.abc import Mapping
from contextlib import contextmanager
from copy import deepcopy
import os
import re
import time

from ..relational_admin import RelationalAdministration
from ...sdk.relational import RelationalClientError


def _split_top_level_clauses(body):
    clauses, start, depth, quote_ch = [], 0, 0, None
    idx = 0
    while idx < len(body):
        ch = body[idx]
        if quote_ch is not None:
            if ch == quote_ch:
                if idx + 1 < len(body) and body[idx + 1] == quote_ch:
                    idx += 1
                else:
                    quote_ch = None
        elif ch in {'"', "'"}:
            quote_ch = ch
        elif ch in {'(', '['}:
            depth += 1
        elif ch in {')', ']'}:
            depth = max(0, depth - 1)
        elif ch == ',' and depth == 0:
            clauses.append(body[start:idx].strip())
            start = idx + 1
        idx += 1
    tail = body[start:].strip()
    if tail:
        clauses.append(tail)
    return clauses


def _generated_columns_from_ddl(ddl):
    if not isinstance(ddl, str) or '(' not in ddl or ')' not in ddl:
        return set()
    body = ddl[ddl.index('(') + 1:ddl.rindex(')')]
    generated = set()
    for clause in _split_top_level_clauses(body):
        if not re.search(r'\bGENERATED\s+ALWAYS\s+AS\b', clause, re.IGNORECASE):
            continue
        stripped = clause.lstrip()
        if stripped.startswith('"'):
            match = re.match(r'^"((?:[^"]|"")*)"', stripped)
            if match:
                generated.add(match.group(1).replace('""', '"'))
        else:
            match = re.match(r'^([^\s(]+)', stripped)
            if match and match.group(1).upper() != 'CONSTRAINT':
                generated.add(match.group(1))
    return generated


class DuckDBAdministration(RelationalAdministration):
    def _row_cursor(self, client, connection):
        from .grid_values import RowCursor
        return RowCursor(connection)

    def _public_row_values(self, values):
        from .grid_values import public_values
        return public_values(values)

    def _identity_predicate(self, identity):
        from .grid_values import identity_predicate
        return identity_predicate(self._quote, identity)

    def _duckdb_secret(self, name, options):
        from .secret_values import compile_secret
        return compile_secret(self, name, options)

    def _inspect_table_write_schema(self, connection, path):
        schema, table = self._schema_table(path, 'main')
        catalog = (
            path[-3] if len(path) >= 3
            else connection.execute('SELECT current_database()').fetchone()[0]
        )
        qualified = self._qualified((catalog, schema, table))
        relation = connection.sql(f'SELECT * FROM {qualified} LIMIT 0')
        types_by_col = dict(zip(relation.columns, relation.types))
        ddl_row = connection.execute(
            'SELECT sql FROM "system"."main".duckdb_tables() '
            'WHERE database_name = ? AND schema_name = ? AND table_name = ? '
            'AND NOT internal',
            [catalog, schema, table],
        ).fetchone()
        generated = _generated_columns_from_ddl(ddl_row[0] if ddl_row else None)
        return types_by_col, generated

    def _resolve_table_write_schema(self, request):
        target = request.get('target_resource')
        if not isinstance(target, Mapping):
            return None, set()
        path = self._target_path(target)
        handle = request.get('_provider_session_handle') or getattr(
            getattr(self, '_local', None), 'planning_handle', None,
        )
        if handle is not None:
            return self._inspect_table_write_schema(handle, path)
        native = target.get('native') if isinstance(target.get('native'), Mapping) else {}
        ddl = native.get('ddl')
        generated = _generated_columns_from_ddl(ddl)
        route = request.get('_provider_route') or {}
        raw_db = route.get('database')
        if isinstance(raw_db, str) and raw_db.strip() and raw_db.strip() != ':memory:':
            from ..embedded_route import contained_database
            db_path = contained_database(route)
            if os.path.isfile(db_path):
                import duckdb
                from .provider import _initialize_connection, _route_arguments
                conn = duckdb.connect(**_route_arguments(route))
                try:
                    _initialize_connection(conn, route)
                    return self._inspect_table_write_schema(conn, path)
                except duckdb.CatalogException:
                    pass
                finally:
                    conn.close()
        if isinstance(native.get('columns'), list) and native['columns']:
            import duckdb
            parsed = {}
            for col in native['columns']:
                if isinstance(col, Mapping) and col.get('name') and col.get('data_type'):
                    try:
                        parsed[str(col['name'])] = duckdb.sqltype(str(col['data_type']))
                    except Exception:
                        return None, generated
            if parsed:
                return parsed, generated
        return None, generated

    def _compile_insert(self, request):
        if request['target_resource'].get(
            'resource_kind', request['resource_kind'],
        ) != request['resource_kind']:
            raise RelationalClientError('insert target kind does not match')
        if request['resource_kind'] != 'table':
            return super()._compile_insert(request)
        values = request['draft'].get('values')
        if not isinstance(values, Mapping):
            raise RelationalClientError('insert values must be an object')
        target = self._qualified(self._target_path(request['target_resource']))
        if not values:
            return {'source': f'INSERT INTO {target} DEFAULT VALUES', 'parameters': ()}
        types_by_col, generated = self._resolve_table_write_schema(request)
        from .grid_values import compile_write_value
        from .values import parameter as untyped_parameter
        columns = list(values)
        exprs, params = [], []
        for col in columns:
            if col in generated:
                raise RelationalClientError(
                    f'DuckDB generated column {col!r} cannot be inserted directly'
                )
            if types_by_col is not None:
                if col not in types_by_col:
                    raise RelationalClientError(f'Unknown DuckDB table column {col!r}')
                expr, bound = compile_write_value(values[col], types_by_col[col])
                exprs.append(expr)
                params.extend(bound)
            else:
                exprs.append(self.dialect.parameter)
                params.append(untyped_parameter(values[col]))
        source = (
            f'INSERT INTO {target} '
            f'({", ".join(self._quote(item) for item in columns)}) '
            f'VALUES ({", ".join(exprs)})'
        )
        return {'source': source, 'parameters': tuple(params)}

    def _compile_identity_dml(self, request):
        if request['operation_id'] == 'delete':
            return super()._compile_identity_dml(request)
        draft = request['draft']
        selector = draft.get('selector')
        if not isinstance(selector, Mapping):
            raise RelationalClientError('row selector must contain a provider identity token')
        token = selector.get('identity_token')
        if not isinstance(token, str) or not token:
            raise RelationalClientError('provider-issued row identity token is required')
        with self._identity_lock:
            identity = self._row_identities.pop(token, None)
        if identity is None:
            raise RelationalClientError('row identity token is stale or invalid')
        if identity.purpose != 'row':
            raise RelationalClientError('row identity has another purpose')
        if identity.session_id != request.get('session_id'):
            raise RelationalClientError('row identity belongs to another provider session')
        if (identity.resource_kind != request['resource_kind'] or
                identity.resource_kind != request['target_resource'].get('resource_kind', 'table')):
            raise RelationalClientError('row identity belongs to another kind')
        if time.monotonic() - identity.issued_at > 600:
            raise RelationalClientError('row identity token has expired')
        route = request.get('_provider_route')
        if self._route_fingerprint(route) != identity.route_fingerprint:
            raise RelationalClientError('row identity belongs to another route')
        target_path = self._target_path(request['target_resource'])
        if target_path != identity.target_path:
            raise RelationalClientError('row identity belongs to another table')
        where, predicate_params = self._identity_predicate(identity)
        target = self._qualified(target_path)
        changes = draft.get('changes')
        if not isinstance(changes, Mapping) or not changes:
            raise RelationalClientError('row update changes must be an object')
        if identity.writable_columns is not None and any(
            name not in identity.writable_columns for name in changes
        ):
            raise RelationalClientError('row update contains a column not admitted for editing')
        from .grid_values import NativeCell, compile_write_value
        from .values import parameter as untyped_parameter
        types_by_col = {
            col_name: cell.kind
            for col_name, cell in identity.original.items()
            if isinstance(cell, NativeCell)
        }
        target_res = request.get('target_resource')
        target_native = (
            target_res.get('native')
            if isinstance(target_res, Mapping) and isinstance(target_res.get('native'), Mapping)
            else {}
        )
        generated = _generated_columns_from_ddl(target_native.get('ddl'))
        if not types_by_col or getattr(getattr(self, '_local', None), 'planning_handle', None) is not None:
            live_types, live_gen = self._resolve_table_write_schema(request)
            if live_types is not None:
                types_by_col.update(live_types)
            generated |= live_gen
        assignments, write_params = [], []
        for col_name, raw_val in changes.items():
            if col_name in generated:
                raise RelationalClientError(
                    f'DuckDB generated column {col_name!r} cannot be updated directly'
                )
            if types_by_col:
                if col_name not in types_by_col:
                    raise RelationalClientError(f'Unknown DuckDB table column {col_name!r}')
                expr, bound = compile_write_value(raw_val, types_by_col[col_name])
                assignments.append(f'{self._quote(col_name)} = {expr}')
                write_params.extend(bound)
            else:
                assignments.append(f'{self._quote(col_name)} = {self.dialect.parameter}')
                write_params.append(untyped_parameter(raw_val))
        source = f'UPDATE {target} SET {", ".join(assignments)} WHERE {where}'
        return {
            'source': source,
            'parameters': tuple(write_params) + tuple(predicate_params),
            'expected_rowcount': 1,
        }

    def catalog(self, catalog):
        from .object_metadata import KINDS
        from .extension_updates import OPERATIONS
        value = deepcopy(catalog)
        for resource in value.get('objects', []):
            for kind, operation in sorted(OPERATIONS):
                if resource['resource_kind'] == kind:
                    resource['operations'] = [row for row in resource.get('operations', [])
                        if row['operation_id'] != operation] + [{
                            'operation_id': operation,
                            'title': 'Update native extension' if kind == 'extension' else 'Update installed extensions',
                            'mutation_class': 'admin', 'target_required': True,
                            'confirmation_required': True, 'long_running': False,
                            'cancellable': False, 'post_state_required': False}]
            if resource['resource_kind'] in KINDS:
                resource['operations'] = [row for row in resource.get('operations', [])
                    if row['operation_id'] != 'comment'] + [{
                        'operation_id': 'comment', 'title': 'Edit native comment',
                        'mutation_class': 'admin', 'target_required': True,
                        'confirmation_required': True, 'long_running': False,
                        'cancellable': False, 'post_state_required': False}]
        return super().catalog(value)

    def _form(self, kind, operation):
        if kind == 'secret' and operation == 'create':
            from .secrets import form
            return form(self._field)
        from .extension_updates import OPERATIONS, form
        if (kind, operation) in OPERATIONS:
            return form(kind, operation, self._field)
        if operation == 'comment':
            return {'form_id': f'duckdb.{kind}.comment', 'title': 'Edit native DuckDB comment',
                'fields': [{**self._field('comment', 'Comment', 'multiline'),
                    'submit_unchanged': True,
                    'initial_value_path': ['catalog_metadata', 'comment'],
                    'visible_when': {'field_id': 'clear_comment', 'equals': False}},
                    self._field('clear_comment', 'Remove comment', 'boolean', default=False),
                    self._field('confirmation', 'Exact object name', 'text', True)]}
        if operation == 'alter' and kind in {'view', 'macro'}:
            fields = [self._field(
                'query' if kind == 'view' else 'source',
                'Replacement SELECT/WITH query' if kind == 'view' else
                'Complete qualified CREATE OR REPLACE MACRO statement',
                'code', True,
                'DuckDB replaces the entire definition and all macro overloads.'
                if kind == 'macro' else 'Enter one SELECT or WITH query.')]
            fields.extend((
                self._field('complete_definition_confirmed',
                    'I reviewed the complete replacement definition', 'boolean', True),
                self._field('metadata_reset_acknowledged',
                    'I accept that native replacement clears comments and tags',
                    'boolean', True),
            ))
            return {'form_id': f'duckdb.{kind}.alter',
                'title': f'Replace DuckDB {kind}', 'fields': fields}
        if kind == 'database' and operation in {'export_database', 'import_database'}:
            exporting = operation == 'export_database'
            fields = [self._field('directory', 'Export directory' if exporting else 'Import directory',
                'text', True, 'Absolute path under the registered filesystem root.')]
            if exporting:
                fields.append(self._field('format', 'Native format', 'select', False,
                    default='PARQUET', options=('PARQUET', 'CSV')))
            return {'form_id': f'duckdb.database.{operation}',
                'title': 'Export DuckDB logical database' if exporting else 'Import DuckDB logical database',
                'fields': fields}
        return super()._form(kind, operation)

    def _definition_replacement(self, request):
        kind = request['resource_kind']
        draft = request.get('draft') or {}
        expected = ({'query', 'definition'} if kind == 'view' else {'source'}) | {
            'complete_definition_confirmed', 'metadata_reset_acknowledged'}
        if (set(draft) - expected - {'changes'} or draft.get('changes') or
                (kind == 'view' and 'query' in draft and 'definition' in draft) or
                draft.get('complete_definition_confirmed') is not True or
                draft.get('metadata_reset_acknowledged') is not True):
            raise RelationalClientError(
                'DuckDB replacement requires one complete definition and explicit metadata-reset acknowledgement')
        path = self._target_path(request.get('target_resource'))
        if len(path) != 3:
            raise RelationalClientError('DuckDB replacement requires the exact catalog, schema and object')
        if kind == 'view':
            source = ('CREATE OR REPLACE VIEW ' + self._qualified(path) +
                      ' AS ' + self._query_body(draft.get('query', draft.get('definition'))))
        else:
            source = draft.get('source')
        from ...workspace.duckdb_schema_plan import _validated_ddl
        try:
            source = _validated_ddl(source, kind, path, replace=True)
        except ValueError as error:
            raise RelationalClientError(str(error)) from None
        return {'statements': [{'source': source, 'parameters': ()}],
            'warnings': [
                'Native replacement clears existing comments and tags; restore them separately if needed.',
                'The complete macro signature set, including defaults, is operator-authored.'
                if kind == 'macro' else
                'The replacement view query is bound and checked by DuckDB at execution.',
            ]}

    def validate(self, request):
        if request.get('resource_kind') == 'secret' and request.get('operation_id') in {'create', 'drop'}:
            try:
                from .secrets import compile_operation
                compile_operation(self, request)
                return {'errors': []}
            except RelationalClientError as error:
                return {'errors': [{'field_id': None, 'code': 'invalid_duckdb_secret', 'message': str(error)}]}
        from .extension_updates import OPERATIONS, compile_operation
        if (request.get('resource_kind'), request.get('operation_id')) in OPERATIONS:
            try:
                compile_operation(self, request)
                return {'errors': []}
            except RelationalClientError as error:
                return {'errors': [{'field_id': None,
                    'code': 'invalid_duckdb_extension_update', 'message': str(error)}]}
        if request.get('operation_id') == 'comment':
            try:
                from .object_metadata import compile_operation
                compile_operation(self, request)
                return {'errors': []}
            except RelationalClientError as error:
                return {'errors': [{'field_id': None,
                    'code': 'invalid_duckdb_comment', 'message': str(error)}]}
        result = super().validate(request)
        if (not result['errors'] and request.get('operation_id') == 'alter' and
                request.get('resource_kind') in {'view', 'macro'}):
            try:
                self._definition_replacement(request)
            except RelationalClientError as error:
                result['errors'].append({'field_id': None,
                    'code': 'invalid_duckdb_definition_replacement',
                    'message': str(error)})
        elif (not result['errors'] and request.get('resource_kind') in {'table', 'column', 'sequence'} and
                request.get('operation_id') in {'create', 'alter'}):
            try:
                normalized = dict(request)
                normalized['draft'] = self._normalize_draft(
                    request['resource_kind'], request['operation_id'], request.get('draft') or {},
                )
                self._compile(normalized)
            except RelationalClientError as error:
                result['errors'].append({'field_id': None,
                    'code': 'invalid_duckdb_column_spec',
                    'message': str(error)})
        return result

    def _column_definition(self, item):
        if not isinstance(item, Mapping):
            raise RelationalClientError('column definition must be an object')
        name = self._quote(item.get('name'))
        data_type = self._safe_fragment(item.get('type'), 'column type')
        parts = [name, data_type]
        collation = item.get('collation')
        if collation not in {None, ''}:
            if not isinstance(collation, str) or not re.fullmatch(
                r'[A-Za-z_][A-Za-z0-9_.]*', collation.strip(),
            ):
                raise RelationalClientError('DuckDB column collation must be a valid collation identifier')
            parts.extend(('COLLATE', collation.strip()))
        gen_expr = item.get('generated_expression')
        if gen_expr not in {None, ''}:
            if item.get('default') not in {None, ''}:
                raise RelationalClientError(
                    'DuckDB generated column cannot specify both a DEFAULT and GENERATED ALWAYS AS expression'
                )
            if item.get('primary_key'):
                raise RelationalClientError(
                    'DuckDB generated column cannot be a PRIMARY KEY'
                )
            if not item.get('nullable', True):
                raise RelationalClientError(
                    'DuckDB generated column cannot declare NOT NULL'
                )
            expr = self._safe_fragment(gen_expr, 'generated expression')
            parts.append(f'GENERATED ALWAYS AS ({expr})')
            if item.get('unique'):
                parts.append('UNIQUE')
            return ' '.join(parts)
        if not item.get('nullable', True):
            parts.append('NOT NULL')
        if 'default' in item and item['default'] not in {None, ''}:
            parts.extend((
                'DEFAULT', self._safe_fragment(item['default'], 'default'),
            ))
        if item.get('unique'):
            parts.append('UNIQUE')
        if item.get('primary_key'):
            parts.append('PRIMARY KEY')
        parts.extend(self._column_option_clauses(item))
        return ' '.join(parts)

    def _compile(self, request):
        if request.get('resource_kind') == 'secret' and request.get('operation_id') in {'create', 'drop'}:
            from .secrets import compile_operation
            return compile_operation(self, request)
        from .extension_updates import OPERATIONS, compile_operation
        if (request.get('resource_kind'), request.get('operation_id')) in OPERATIONS:
            return compile_operation(self, request)
        if request.get('operation_id') == 'comment':
            from .object_metadata import compile_operation
            return compile_operation(self, request)
        if (request['operation_id'] == 'alter' and
                request['resource_kind'] in {'view', 'macro'}):
            return self._definition_replacement(request)
        if request['operation_id'] == 'alter' and request['resource_kind'] == 'sequence':
            return self._compile_duckdb_sequence_alter(request)
        compiled = super()._compile(request)
        if request.get('resource_kind') == 'table' and request.get('operation_id') == 'alter':
            changes = (request.get('draft') or {}).get('changes') or {}
            add_cols = changes.get('add_columns') or []
            comment_stmts = []
            target = self._qualified(self._target_path(request['target_resource']))
            for item in add_cols:
                if isinstance(item, Mapping) and item.get('comment') not in {None, ''}:
                    if not isinstance(item['comment'], str):
                        raise RelationalClientError('DuckDB column comment must be text')
                    comment_stmts.append({
                        'source': f'COMMENT ON COLUMN {target}.{self._quote(item["name"])} IS {self._literal(item["comment"])}',
                        'parameters': (),
                    })
            if comment_stmts:
                if isinstance(compiled, dict) and 'statements' in compiled:
                    compiled['statements'] = list(compiled['statements']) + comment_stmts
                elif isinstance(compiled, list):
                    compiled = list(compiled) + comment_stmts
        return compiled

    def _compile_duckdb_sequence_create(self, request):
        draft = request['draft']
        options = draft.get('options') or {}
        or_replace = bool(options.get('or_replace'))
        if_not_exists = bool(options.get('if_not_exists'))
        if or_replace and if_not_exists:
            raise RelationalClientError(
                'DuckDB sequence cannot combine OR REPLACE and IF NOT EXISTS'
            )
        temporary = bool(options.get('temporary'))
        no_min = bool(options.get('no_minimum'))
        no_max = bool(options.get('no_maximum'))
        if no_min and options.get('minimum') not in {None, ''}:
            raise RelationalClientError(
                'Choose either a minimum value or NO MINVALUE, not both'
            )
        if no_max and options.get('maximum') not in {None, ''}:
            raise RelationalClientError(
                'Choose either a maximum value or NO MAXVALUE, not both'
            )
        qualified = self._new_object_name(self._identifier(draft['name']), options)
        prefix = 'CREATE '
        if or_replace:
            prefix += 'OR REPLACE '
        if temporary:
            prefix += 'TEMPORARY '
        prefix += 'SEQUENCE '
        if if_not_exists:
            prefix += 'IF NOT EXISTS '
        source = prefix + qualified
        if options.get('start') not in {None, ''}:
            source += f' START WITH {self._integer(options["start"], "start")}'
        if options.get('increment') not in {None, ''}:
            inc = self._integer(options['increment'], 'increment')
            if inc == 0:
                raise RelationalClientError('DuckDB sequence increment cannot be zero')
            source += f' INCREMENT BY {inc}'
        if no_min:
            source += ' NO MINVALUE'
        elif options.get('minimum') not in {None, ''}:
            source += f' MINVALUE {self._integer(options["minimum"], "minimum")}'
        if no_max:
            source += ' NO MAXVALUE'
        elif options.get('maximum') not in {None, ''}:
            source += f' MAXVALUE {self._integer(options["maximum"], "maximum")}'
        if options.get('cycle'):
            source += ' CYCLE'
        statements = [{'source': source, 'parameters': ()}]
        comment = options.get('comment')
        if comment not in {None, ''}:
            if not isinstance(comment, str) or '\x00' in comment:
                raise RelationalClientError('DuckDB sequence comment must be text without NUL')
            statements.append({
                'source': f'COMMENT ON SEQUENCE {qualified} IS {self._literal(comment)}',
                'parameters': (),
            })
        return statements

    def _compile_duckdb_sequence_alter(self, request):
        target_res = request.get('target_resource')
        if not isinstance(target_res, Mapping) or target_res.get('resource_kind') != 'sequence':
            raise RelationalClientError('Select a native DuckDB sequence target')
        path = self._target_path(target_res)
        qualified = self._qualified(path)
        native = target_res.get('native') or {}
        if not isinstance(native, Mapping):
            ext = (target_res.get('extensions') or {}).get('duckdb') or {}
            native = ext.get('native', ext) if isinstance(ext, Mapping) else {}
        meta = native.get('catalog_metadata') if isinstance(native.get('catalog_metadata'), Mapping) else {}
        draft = request.get('draft') or {}
        changes = draft.get('changes') if isinstance(draft.get('changes'), Mapping) else draft

        param_keys = {'start', 'increment', 'minimum', 'maximum', 'no_minimum', 'no_maximum', 'cycle'}
        has_param_change = any(k in changes and changes[k] not in {None, ''} for k in param_keys)
        clear_comment = bool(changes.get('clear_comment'))
        has_comment_change = clear_comment or ('comment' in changes and changes.get('comment') != meta.get('comment'))
        if clear_comment and changes.get('comment') not in {None, ''}:
            raise RelationalClientError('Specify either a sequence comment or Clear comment, not both')
        if not has_param_change and not has_comment_change:
            raise RelationalClientError('DuckDB sequence alteration has no changes to apply')

        statements = []
        warnings = []
        if has_param_change:
            if meta.get('automatic_dependency_observed'):
                raise RelationalClientError(
                    'DuckDB cannot replace a sequence with active automatic table ownership'
                )
            if not bool(changes.get('reset_state_confirmed')):
                raise RelationalClientError(
                    'Confirm generator state reset to replace DuckDB sequence parameters '
                    '(CREATE OR REPLACE SEQUENCE resets last_value)'
                )
            temporary = bool(meta.get('temporary'))
            start_val = (
                self._integer(changes['start'], 'start')
                if changes.get('start') not in {None, ''}
                else meta.get('start_value')
            )
            inc_val = (
                self._integer(changes['increment'], 'increment')
                if changes.get('increment') not in {None, ''}
                else meta.get('increment_by')
            )
            if inc_val == 0:
                raise RelationalClientError('DuckDB sequence increment cannot be zero')
            no_min = bool(changes.get('no_minimum'))
            no_max = bool(changes.get('no_maximum'))
            if no_min and changes.get('minimum') not in {None, ''}:
                raise RelationalClientError('Choose either a minimum value or NO MINVALUE, not both')
            if no_max and changes.get('maximum') not in {None, ''}:
                raise RelationalClientError('Choose either a maximum value or NO MAXVALUE, not both')
            min_val = None if no_min else (
                self._integer(changes['minimum'], 'minimum')
                if changes.get('minimum') not in {None, ''}
                else meta.get('min_value')
            )
            max_val = None if no_max else (
                self._integer(changes['maximum'], 'maximum')
                if changes.get('maximum') not in {None, ''}
                else meta.get('max_value')
            )
            cycle_val = bool(changes['cycle']) if 'cycle' in changes and changes['cycle'] is not None else bool(meta.get('cycle'))

            temp_kw = 'TEMPORARY ' if temporary else ''
            src = f'CREATE OR REPLACE {temp_kw}SEQUENCE {qualified}'
            if start_val is not None:
                src += f' START WITH {int(start_val)}'
            if inc_val is not None:
                src += f' INCREMENT BY {int(inc_val)}'
            if no_min:
                src += ' NO MINVALUE'
            elif min_val is not None:
                src += f' MINVALUE {int(min_val)}'
            if no_max:
                src += ' NO MAXVALUE'
            elif max_val is not None:
                src += f' MAXVALUE {int(max_val)}'
            src += ' CYCLE' if cycle_val else ' NO CYCLE'
            statements.append({'source': src, 'parameters': ()})
            warnings.append(
                'CREATE OR REPLACE SEQUENCE resets the DuckDB generator position to START WITH.'
            )

        effective_comment = (
            None if clear_comment else (
                changes.get('comment')
                if 'comment' in changes
                else meta.get('comment')
            )
        )
        if effective_comment == '':
            effective_comment = None
        if has_comment_change or (has_param_change and effective_comment is not None):
            if effective_comment is not None and (not isinstance(effective_comment, str) or '\x00' in effective_comment):
                raise RelationalClientError('DuckDB sequence comment must be text without NUL')
            statements.append({
                'source': (
                    f'COMMENT ON SEQUENCE {qualified} IS '
                    + ('NULL' if effective_comment is None else self._literal(effective_comment))
                ),
                'parameters': (),
            })
        return {'statements': statements, 'warnings': warnings}

    def _compile_create(self, request):
        if request['resource_kind'] == 'index' and any(
                key in (request['draft'].get('options') or {})
                for key in ('terms', 'method', 'index_options')):
            from .indexes import compile_create
            return compile_create(self, request)
        if request['resource_kind'] == 'sequence':
            return self._compile_duckdb_sequence_create(request)
        statements = super()._compile_create(request)
        kind = request['resource_kind']
        draft = request['draft']
        options = draft.get('options') or {}
        if kind == 'table':
            qualified = self._new_object_name(self._identifier(draft['name']), options)
            extra = []
            for item in options.get('columns') or []:
                if isinstance(item, Mapping) and item.get('comment') not in {None, ''}:
                    if not isinstance(item['comment'], str):
                        raise RelationalClientError('DuckDB column comment must be text')
                    extra.append({
                        'source': f'COMMENT ON COLUMN {qualified}.{self._quote(item["name"])} IS {self._literal(item["comment"])}',
                        'parameters': (),
                    })
            if extra:
                statements = list(statements) + extra
        elif kind == 'column':
            table = self._qualified(self._option_path(options, 'table'))
            comment = options.get('comment')
            if comment not in {None, ''}:
                if not isinstance(comment, str):
                    raise RelationalClientError('DuckDB column comment must be text')
                statements = list(statements) + [{
                    'source': f'COMMENT ON COLUMN {table}.{self._quote(draft["name"])} IS {self._literal(comment)}',
                    'parameters': (),
                }]
        return statements

    def _normalize_draft(self, kind, operation, draft):
        if kind == 'secret' and operation in {'create', 'drop'}:
            return deepcopy(draft)
        if kind == 'sequence' and operation == 'alter':
            return {'changes': deepcopy(dict(draft))}
        result = super()._normalize_draft(kind, operation, draft)
        if kind == 'sequence' and operation == 'create':
            options = result.setdefault('options', {})
            for key in ('if_not_exists', 'no_minimum', 'no_maximum', 'comment', 'or_replace', 'temporary'):
                if key in result:
                    options[key] = result.pop(key)
        if kind == 'column' and operation == 'create':
            options = result.setdefault('options', {})
            for key in ('collation', 'generated_expression', 'comment'):
                if key in result:
                    options[key] = result.pop(key)
        if kind == 'index' and operation == 'create':
            for key in ('terms', 'method', 'index_options'):
                if key in result:
                    value = result.pop(key)
                    options = result.setdefault('options', {})
                    if key in options and options[key] != value:
                        raise RelationalClientError('Conflicting native index controls')
                    options[key] = value
        return result

    def plan(self, request):
        import threading
        if not hasattr(self, '_local'):
            self._local = threading.local()
        handle = request.get('_provider_session_handle')
        clean_request = (
            {k: v for k, v in request.items() if k != '_provider_session_handle'}
            if handle is not None else request
        )
        self._local.planning_handle = handle
        try:
            result = super().plan(clean_request)
        finally:
            self._local.planning_handle = None
        compiled = (result.get('provider_payload') or {}).get('compiled') or {}
        if not any(
            key in compiled
            for key in ('duckdb_secret', 'duckdb_extension_update', 'duckdb_comment')
        ):
            from .destructive_identity import observe_for_plan
            binding = observe_for_plan(request, self)
            if binding is not None:
                result['provider_payload']['duckdb_target_binding'] = binding
                result['command_preview']['native_target_revalidation_required'] = True
        if (request.get('operation_id') == 'alter' and
                request.get('resource_kind') == 'macro'):
            result['command_preview']['provider_constructed'] = False
            result['command_preview']['source_origin'] = 'operator-reviewed-native-statement'
        if request.get('resource_kind') == 'index' and request.get('operation_id') == 'create':
            result['command_preview']['native_index_capabilities'] = {
                'admitted_methods': ['ART'], 'admitted_art_creation_options': [],
                'authority': 'qualified DuckDB 1.5.2 built-in ART registration',
                'extension_method_registry_enumerated': False}
        return result

    @staticmethod
    def _duckdb_operation_directory(route, value, importing=False):
        directory = RelationalAdministration._duckdb_operation_directory(route, value, importing)
        if importing:
            for name in ('schema.sql', 'load.sql'):
                path = os.path.join(directory, name)
                if os.path.islink(path) or os.path.dirname(os.path.realpath(path)) != directory:
                    raise RelationalClientError('DuckDB import control files must reside in the reviewed directory')
        return directory

    def _compile_duckdb_database_operation(self, request):
        compiled = super()._compile_duckdb_database_operation(request)
        if request['operation_id'] == 'export_database':
            compiled.setdefault('warnings', []).extend((
                'EXPORT DATABASE is a logical native export, not a physical backup.',
                'Rollback does not remove files already written by EXPORT DATABASE.',
            ))
        elif request['operation_id'] == 'import_database':
            compiled.setdefault('warnings', []).append(
                'IMPORT DATABASE reads native export files; review their contents before execution.')
        return compiled

    @contextmanager
    def _borrow(self, client, connection):
        if connection is None:
            yield
            return
        with client._lock:
            client._require_idle(connection)
            client._busy.add(id(connection))
        try:
            yield
        finally:
            with client._lock:
                client._busy.discard(id(connection))

    def apply(self, client, request, connection=None):
        with self._borrow(client, connection):
            if 'duckdb_secret' in (request.get('provider_payload') or {}).get('compiled', {}):
                from .secrets import apply
                return apply(client, request, connection)
            if 'duckdb_extension_update' in (request.get('provider_payload') or {}).get('compiled', {}):
                from .extension_updates import apply
                return apply(self, client, request, connection)
            if 'duckdb_comment' in (request.get('provider_payload') or {}).get('compiled', {}):
                from .object_metadata import apply
                return apply(self, client, request, connection)
            return super().apply(client, request, connection=connection)

    def read_rows(self, client, request, connection=None):
        from .grid_values import input_envelope_spec
        with self._borrow(client, connection):
            execution = request.get('_row_read_execution')
            if connection is not None and execution is not None:
                with execution.cancellable_row_read(connection.interrupt):
                    page = super().read_rows(client, request, connection=connection)
            else:
                page = super().read_rows(client, request, connection=connection)
            target = request.get('target_resource')
            if isinstance(target, Mapping) and target.get('resource_kind') in ('table', 'view'):
                path = self._target_path(target)
                owns = connection is None
                obs_conn = connection or client._connect({'route': request.get('_provider_route')})
                col_comments = {}
                table_comment = ''
                types_by_col, generated = {}, set()
                try:
                    if target.get('resource_kind') == 'table':
                        types_by_col, generated = self._inspect_table_write_schema(obs_conn, path)
                    if not request.get('continuation') and hasattr(obs_conn, 'execute'):
                        try:
                            schema_n, table_n = self._schema_table(path, 'main')
                            catalog_n = path[-3] if len(path) >= 3 else obs_conn.execute(
                                'SELECT current_database()'
                            ).fetchone()[0]
                            for cname, cdesc in obs_conn.execute(
                                "SELECT column_name, LEFT(COALESCE(comment, ''), 128) "
                                'FROM duckdb_columns() WHERE database_name=? AND schema_name=? AND table_name=?',
                                (catalog_n, schema_n, table_n),
                            ).fetchall():
                                if cname and cdesc:
                                    col_comments[str(cname)] = str(cdesc)[:128]
                            rel_fn = 'duckdb_views()' if target.get('resource_kind') == 'view' else 'duckdb_tables()'
                            rel_col = 'view_name' if target.get('resource_kind') == 'view' else 'table_name'
                            t_row = obs_conn.execute(
                                f"SELECT LEFT(COALESCE(comment, ''), 128) FROM {rel_fn} "
                                f'WHERE database_name=? AND schema_name=? AND {rel_col}=?',
                                (catalog_n, schema_n, table_n),
                            ).fetchone()
                            if t_row and t_row[0]:
                                table_comment = str(t_row[0])[:128]
                        except Exception:
                            pass
                finally:
                    if owns:
                        client._forget_and_close(obs_conn)
                if table_comment:
                    page['table_comment'] = table_comment
                for col in page.get('columns', []):
                    col_name = col['name']
                    if col_name in col_comments and not col.get('comment'):
                        col['comment'] = col_comments[col_name]
                    kind = types_by_col.get(col_name)
                    if kind is not None:
                        spec = input_envelope_spec(kind)
                        col['input_envelope'] = spec
                        if not spec['admitted'] or col_name in generated:
                            col['editable'] = False
                        if col_name in generated:
                            col['generated'] = True
            return page

    def _primary_key(self, connection, path):
        schema, table = self._schema_table(path, 'main')
        catalog = path[-3] if len(path) >= 3 else connection.execute(
            'SELECT current_database()').fetchone()[0]
        connection.execute(
            'SELECT kcu.column_name FROM information_schema.'
            'table_constraints tc JOIN '
            'information_schema.key_column_usage kcu '
            'ON tc.constraint_catalog=kcu.constraint_catalog AND '
            'tc.constraint_schema=kcu.constraint_schema AND '
            'tc.constraint_name=kcu.constraint_name '
            "WHERE tc.constraint_type='PRIMARY KEY' AND tc.table_catalog=? "
            'AND tc.table_schema=? AND tc.table_name=? '
            'ORDER BY kcu.ordinal_position', (catalog, schema, table))
        return [str(row[0]) for row in connection.fetchall()]
