"""Literal metadata search over a scoped, provider-observed Firebird catalog."""
from .firebird_catalog_export import native_metadata

FIELDS = {'name', 'kind', 'description', 'source', 'fields'}
SOURCE_KEYS = {'definition', 'ddl', 'metadata_source', 'header_source', 'body_source',
               'expression_source', 'condition_source', 'default_source',
               'validation_source', 'computed_source', 'source'}
FIELD_KEYS = {'columns', 'view_columns', 'parameters', 'field_name', 'field_source',
              'relation_name', 'type', 'type_sql', 'datatype', 'native_type'}


def validate(request):
    if not isinstance(request, dict) or set(request) - {'target_id', 'query', 'fields', 'kind'}:
        raise ValueError('Invalid metadata search request')
    target, query, fields = request.get('target_id'), request.get('query'), request.get('fields')
    if not isinstance(target, str) or not target or len(target) > 1024:
        raise ValueError('Select a registered database')
    if not isinstance(query, str) or not query.strip() or len(query) > 256 or '\0' in query:
        raise ValueError('Search text must contain 1–256 characters')
    if not isinstance(fields, list) or not fields or any(not isinstance(item, str) or item not in FIELDS for item in fields):
        raise ValueError('Select known metadata search fields')
    kind = request.get('kind', '')
    if not isinstance(kind, str) or len(kind) > 80:
        raise ValueError('Invalid resource kind filter')
    return target, query.casefold(), set(fields), kind


def strings(value, depth=0):
    if depth > 8:
        return
    if isinstance(value, str):
        yield value
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from strings(item, depth + 1)
    elif isinstance(value, dict):
        # Only the caller's allowlisted metadata subtree is visited.
        for item in value.values():
            yield from strings(item, depth + 1)


def search(snapshot, query, fields, kind='', limit=500):
    matches, total, missing_ddl, observations, warnings, coverage = [], 0, 0, [], [], []
    for resource in snapshot['resources']:
        native = native_metadata(resource) or {}
        if resource.get('resource_kind') == 'database':
            observations.extend(native.get('catalog_observations') or [])
            warnings.extend(native.get('catalog_warnings') or [])
            if native.get('catalog_coverage'):
                coverage.append(native['catalog_coverage'])
        missing_ddl += bool(native.get('ddl_unavailable_reason'))
        if kind and resource.get('resource_kind') != kind:
            continue
        candidates = []
        if 'name' in fields:
            candidates.append(('name', resource.get('display_name', '')))
        if 'kind' in fields:
            candidates.append(('kind', resource.get('resource_kind', '')))
        if 'description' in fields:
            candidates.extend(('description', text) for text in strings(native.get('description')))
        for category, keys in (('source', SOURCE_KEYS), ('fields', FIELD_KEYS)):
            if category in fields:
                for key in sorted(keys):
                    candidates.extend((category + ':' + key, text) for text in strings(native.get(key)))
        found = [(category, text) for category, text in candidates if query in text.casefold()]
        if not found:
            continue
        total += 1
        if len(matches) >= limit:
            continue
        category, text = found[0]
        # Unicode casefold changes length; the snippet is contextual, not an
        # authoritative character offset into native source.
        offset = max(0, text.casefold().find(query) - 60)
        matches.append({**{key: resource.get(key) for key in (
            'resource_id', 'resource_kind', 'display_name', 'display_path')},
            'matched_fields': sorted({item[0] for item in found}),
            'snippet': text[offset:offset + 240], 'snippet_truncated': len(text) > 240})
    return {'matches': matches, 'match_count': total, 'truncated': total > len(matches),
            'generation': snapshot['generation'], 'missing_ddl_count': missing_ddl,
            'catalog_observations': observations, 'catalog_coverage': coverage,
            'catalog_warnings': warnings,
            'coverage': 'Current attachment-visible catalog only; unavailable metadata is not searched'}
