"""Visible catalog coverage, distinct from server-wide visibility or live audit."""
from collections import Counter

CATALOG_KINDS = frozenset({
    'table', 'view', 'column', 'index', 'constraint', 'domain', 'sequence',
    'trigger', 'procedure', 'function', 'external-function', 'blob-filter',
    'package', 'exception', 'role', 'character-set', 'collation', 'user',
    'publication', 'configuration', 'authentication-mapping',
    'global-authentication-mapping', 'privilege', 'shadow', 'storage-file',
})


def coverage(resources, observations, mappings, creation_authority):
    unavailable = [item['section'] for item in observations if not item['available']]
    unavailable.extend(kind for kind, value in mappings.items() if not value['available'])
    if not creation_authority.get('available'):
        unavailable.append('database creation authority')
    counts = Counter(item['resource_kind'] for item in resources)
    return {
        'schema': 'firebird-visible-catalog-coverage@1',
        'state': 'partial' if unavailable else 'observed',
        'visibility': 'current_attachment',
        'server_wide_completeness_asserted': False,
        'independent_inventory_verified': False,
        'unavailable_sections': unavailable,
        'resource_counts': {kind: counts[kind] for kind in sorted(CATALOG_KINDS)},
        'implicit_domains': 'Engine-generated RDB$FIELDS rows are represented through column and routine type metadata, not standalone user domains.',
        'notes': [
            'Successful empty queries establish only that no rows were visible to this attachment.',
            'A native inventory audit is required to qualify completeness for the supported object kinds.',
            'Service operations and metric definitions are capabilities, not native catalog objects.',
        ],
    }
