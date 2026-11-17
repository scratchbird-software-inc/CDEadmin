"""Private versioned Firebird recipes; persistence never stages native rows."""
import json
import math
import re

from .assets import ProjectAssetError
from .mysql_recipe_assets import MySQLRecipeAssets

FORMAT = 'scratchrobin.firebird.test-data@1'
FIELDS = {
    'default': set(), 'constant': {'value'},
    'sequential': {'start', 'step'}, 'random-integer': {'min', 'max'},
    'choice': {'values'}, 'file': {'values'},
    'existing': {'table', 'column'}, 'generated': {'table', 'column'},
}


def _name(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 63 or '\x00' in value:
        raise ProjectAssetError('Recipe requires an exact Firebird identifier')
    return value


def _exact(value, depth=0):
    if depth > 32:
        raise ProjectAssetError('Recipe values exceed 32 nesting levels')
    if value is None or type(value) in (str, bool):
        return
    if type(value) is int and abs(value) <= 2**53 - 1:
        return
    if isinstance(value, list):
        for child in value:
            _exact(child, depth + 1)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for child in value.values():
            _exact(child, depth + 1)
        return
    raise ProjectAssetError(
        'Use exact decimal strings or native typed envelopes for numeric values')


def _integer(value):
    if not isinstance(value, str) or not re.fullmatch(r'[+-]?\d{1,39}', value, re.ASCII):
        raise ProjectAssetError('Integer generators require exact decimal strings')
    return int(value)


def validate(recipe, scope, resources=None):
    if (not isinstance(recipe, dict) or set(recipe) != {'format', 'scope', 'seed', 'tables'}
            or recipe['format'] != FORMAT or recipe['scope'] != scope
            or type(recipe['seed']) is not int or not 0 <= recipe['seed'] < 2**32
            or not isinstance(recipe['tables'], list) or not 1 <= len(recipe['tables']) <= 32):
        raise ProjectAssetError('Invalid Firebird recipe format, scope, seed or table count')
    try:
        size = len(json.dumps(recipe, ensure_ascii=False, allow_nan=False).encode('utf-8'))
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise ProjectAssetError('Recipe must contain bounded UTF8 JSON values') from None
    if size > 1024 * 1024:
        raise ProjectAssetError('Recipe exceeds 1 MiB')
    tables, dependencies, total = {}, {}, 0
    for table in recipe['tables']:
        if not isinstance(table, dict) or set(table) != {'table', 'count', 'columns'}:
            raise ProjectAssetError('Invalid recipe table')
        name = _name(table['table'])
        if (name in tables or type(table['count']) is not int or not 1 <= table['count'] <= 1000
                or not isinstance(table['columns'], dict)):
            raise ProjectAssetError('Duplicate table or invalid recipe row/column selection')
        total += table['count']
        if total > 5000:
            raise ProjectAssetError('Recipe exceeds 5000 rows')
        tables[name], dependencies[name] = table, set()
        for column, source in table['columns'].items():
            _name(column)
            if (not isinstance(source, dict) or not isinstance(source.get('kind'), str)
                    or source['kind'] not in FIELDS):
                raise ProjectAssetError('Invalid Firebird generator source')
            kind = source['kind']
            if (set(source) - (FIELDS[kind] | {'kind', 'nullPercent'})
                    or not FIELDS[kind] <= set(source)):
                raise ProjectAssetError('Invalid generator fields')
            rate = source.get('nullPercent', 0)
            if type(rate) not in (int, float) or not 0 <= rate <= 100 or not math.isfinite(rate):
                raise ProjectAssetError('NULL percentage must be 0 through 100')
            if kind == 'constant':
                _exact(source['value'])
            elif kind in {'choice', 'file'}:
                if not isinstance(source['values'], list) or not 1 <= len(source['values']) <= 1000:
                    raise ProjectAssetError('Choice/file sources require 1 through 1000 values')
                _exact(source['values'])
            elif kind == 'sequential':
                _integer(source['start'])
                _integer(source['step'])
            elif kind == 'random-integer':
                if not 1 <= _integer(source['max']) - _integer(source['min']) + 1 <= 2**32:
                    raise ProjectAssetError('Random range must contain 1 through 2^32 integers')
            elif kind in {'existing', 'generated'}:
                _name(source['table'])
                _name(source['column'])
                if kind == 'generated' and rate != 100:
                    dependencies[name].add(source['table'])
    for table in tables.values():
        for source in table['columns'].values():
            if source['kind'] == 'generated' and source.get('nullPercent', 0) != 100:
                parent = tables.get(source['table'], {}).get('columns', {}).get(source['column'])
                if parent is None or parent['kind'] == 'default':
                    raise ProjectAssetError(
                        'Generated references require an explicit generated parent column')
    pending = {name: set(required) for name, required in dependencies.items()}
    while pending:
        ready = {name for name, required in pending.items() if not required}
        if not ready:
            raise ProjectAssetError('Cyclic generated recipe dependencies')
        pending = {name: required - ready for name,
                   required in pending.items() if name not in ready}
    if resources is not None:
        live_tables, live_columns = {}, {}
        for resource in resources:
            native = resource.get('native') or resource.get(
                'extensions', {}).get('firebird', {}).get('native', {})
            if resource.get('resource_kind') == 'table' and native.get('system_object') is not True:
                live_tables[resource['display_name']] = resource
            if resource.get('resource_kind') == 'column' and len(resource.get('display_path', [])) == 2:
                live_columns[(resource['display_path'][0], resource['display_name'])] = native
        for name, table in tables.items():
            if name not in live_tables:
                raise ProjectAssetError('Recipe table is absent from the native user catalog')
            for column, source in table['columns'].items():
                native = live_columns.get((name, column))
                if native is None or native.get('computed_source') or str(native.get('identity_type')) == '0':
                    raise ProjectAssetError('Recipe column is absent, computed or GENERATED ALWAYS')
                if source['kind'] == 'existing' and (source['table'] not in live_tables or
                                                     (source['table'], source['column']) not in live_columns):
                    raise ProjectAssetError(
                        'Existing source is absent from the native user catalog')
    return recipe


class FirebirdRecipeAssets:
    def __init__(self, assets):
        self.storage = MySQLRecipeAssets(assets, engine='firebird')

    def apply(self, owner, scope, action, request, resources=None):
        if action == 'save':
            if not isinstance(request, dict):
                raise ProjectAssetError('Invalid recipe request')
            validate(request.get('recipe'), scope, resources)
        result = self.storage.apply(owner, scope, action, request)
        # Loading a saved draft never establishes current catalog/type/FK
        # validity, nor approval to stage any rows in a native transaction.
        return {**result, 'requires_native_preview': result['recipe'] is not None,
                'contains_user_values': result['recipe'] is not None,
                'source_control_eligible': False}
