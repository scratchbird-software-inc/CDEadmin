"""Document authorized native catalog observations in public DDN data records."""

from datetime import datetime, timezone
import hashlib
import json

MAX_RESOURCES = 20000
MAX_BYTES = 8 * 1024 * 1024
MAX_DDN_UNITS = 2000000
VIEW_LIMIT = 100
MAX_FILES = 64


def _units(text):
    return len(text.encode("utf-16-le")) // 2


def native_metadata(resource, engine="firebird"):
    return resource.get('extensions', {}).get(engine, {}).get(
        'native', resource.get('native', {}))


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)


def build_export(resources, *, endpoint_id, target_id, generation,
                 resource_id=None, include_system=False, refreshed=False,
                 native_model=False, engine="firebird"):
    if engine not in {"firebird", "mysql", "mariadb"}:
        raise ValueError("Unsupported native catalog engine")
    if len(resources) > MAX_RESOURCES:
        raise ValueError('Catalog exceeds the 20,000-resource export limit')
    by_id = {item['resource_id']: item for item in resources}
    if len(by_id) != len(resources):
        raise ValueError('Catalog contains ambiguous native identities')
    if resource_id is not None and resource_id not in by_id:
        raise ValueError('Selected resource is not in the current catalog')
    databases = [item for item in resources if item['resource_kind'] in {'database', 'server'}]
    observations, warnings = [], []
    for database in databases:
        native = native_metadata(database, engine)
        observations.extend(native.get('catalog_observations') or [])
        warnings.extend(native.get('catalog_warnings') or [])
    selected = set(by_id)
    if resource_id is not None and by_id[resource_id]['resource_kind'] != 'database':
        selected = {resource_id}
        children = {}
        for item in resources:
            parent = native_metadata(item, engine).get('navigator_parent_resource_id')
            children.setdefault(parent, []).append(item['resource_id'])
        pending = [resource_id]
        while pending:
            for child in children.get(pending.pop(), []):
                if child not in selected:
                    selected.add(child)
                    pending.append(child)
    items = sorted((item for item in resources if item['resource_id'] in selected
                    and item['resource_kind'] not in {'service-operation', 'metric'}
                    and (include_system or native_metadata(item, engine).get('system_object') is not True)),
                   key=lambda item: (item['resource_kind'], item.get('display_path', []), item['resource_id']))
    coverage = ('unknown' if not observations else 'partial' if
                any(not item.get('available') for item in observations) or
                any(native_metadata(db, engine).get('coverage_complete') is False for db in databases)
                else 'visible-catalog')
    provenance = {
        'mapping': f'scratchrobin.{engine}.catalog@1', 'endpoint_id': endpoint_id,
        'database_target_id': target_id, 'generation': generation,
        'exported_at': datetime.now(timezone.utc).isoformat(),
        'scope_resource_id': resource_id, 'include_system': include_system,
        'observation': 'refreshed-catalog' if refreshed else 'cached-catalog',
        'consistency': 'provider-catalog; storage snapshot not asserted',
        'coverage': coverage, 'catalog_observations': observations,
        'warnings': warnings, 'objects': len(items), 'view_limit': VIEW_LIMIT,
        'deployment': 'documentary-only',
    }
    if engine == 'mariadb' and len(databases) == 1 and databases[0]['resource_kind'] == 'database':
        observed = native_metadata(databases[0], engine)
        provenance['catalog_identity'] = observed.get('catalog_row', {})
        provenance['definition_context'] = observed.get('definition_context', {})
    if native_model:
        # A host capture is already structured metadata, not imported notation.
        # Decode its JSON exactly like imported metadata, without a DDN detour.
        from decimal import Decimal
        rows = {}
        for item in items:
            native = native_metadata(item, engine)
            rows[item['resource_id']] = {
                'resource_id': item['resource_id'], 'kind': item['resource_kind'],
                'name': item['display_name'], 'path': item.get('display_path', []),
                'system': ('true' if native.get('system_object') is True else
                           'false' if native.get('system_object') is False else 'unknown'),
                'native': native,
            }
        capture = _json({'format': f'scratchrobin.{engine}.native-capture@1',
                         'provenance': provenance, 'rows': rows})
        if len(capture.encode('utf-8')) > MAX_BYTES:
            raise ValueError('Native catalog capture exceeds the 8 MiB limit')
        model = json.loads(capture, parse_float=Decimal)
        model['sha256'] = hashlib.sha256(capture.encode('utf-8')).hexdigest()
        return model
    records, ids = [], []
    for item in items:
        key = 'o_' + hashlib.sha256(item['resource_id'].encode()).hexdigest()
        ids.append(key)
        fields = {
            'resource_id': item['resource_id'], 'kind': item['resource_kind'],
            'path_json': _json(item.get('display_path', [])),
            'system': ('true' if native_metadata(item, engine).get('system_object') is True else
                       'false' if native_metadata(item, engine).get('system_object') is False else 'unknown'),
            'native_json': _json(native_metadata(item, engine)),
        }
        records.append('record ' + key + ' ' + _json(item['display_name']) +
                       ' { uid: ' + _json(engine + ':' + endpoint_id + ':' + str(target_id) + ':' + item['resource_id']) +
                       '; x_record: {' + ','.join(name + ':' + _json(value)
                       for name, value in fields.items()) + '}; }')
    if not records:
        records = ['record empty "No objects in the selected visible scope" {}']
        ids = ['empty']
    blocks, views, view_metadata = [], [], []
    pages, current, units = [], [], 0
    for record, identity in zip(records, ids):
        size = _units(record) + len(identity) + 100
        if size > MAX_DDN_UNITS - 20000:
            raise ValueError('Record exceeds the paired DDN per-file limit')
        if current and (len(current) == VIEW_LIMIT or units + size > MAX_DDN_UNITS - 20000):
            pages.append(current)
            current, units = [], 0
        current.append((record, identity))
        units += size
    if current:
        pages.append(current)
    for page, chunk in enumerate(pages, 1):
        block = 'catalog_' + str(page)
        view_id = 'inventory_' + str(page)
        label = f'Native catalog inventory — page {page}; documentary only'
        blocks.append('data ' + block + ' {' + '\n'.join([record for record, _ in chunk]) + '}')
        refs = ['@' + block + '.' + key for key in [identity for _, identity in chunk]]
        views.append('view ' + view_id + ' ' + _json(label) + ' { data: [@' + block + '''];
          projection {kind: table; profile: "table.records@1";
            records: [''' + ','.join(refs) + '''];
            columns: [{key:"name",label:"Name"}, {key:"x_record.kind",label:"Native kind"},
              {key:"x_record.path_json",label:"Exact path"}, {key:"x_record.system",label:"System object"}];
          } publication {size: content; fit: none;}
        }''')
        view_metadata.append({'id': view_id, 'label': label})
    blocks.append('data provenance {record capture "Catalog provenance" { x_record: {'
                  'mapping:' + _json(provenance['mapping']) +
                  ', native_json:' + _json(_json(provenance)) + '}; }}')
    header = f'ddn "0.5"; module "scratchrobin.{engine}.catalog";\n'
    files, parts = {}, [blocks[-1]]
    if _units(header + parts[0]) > MAX_DDN_UNITS:
        raise ValueError('Provenance exceeds the paired DDN per-file limit')
    def flush():
        name = 'catalog.ddn' if not files else f'catalog-{len(files) + 1}.ddn'
        files[name] = header + '\n'.join(parts)
        return name
    pending = []
    for block, view, metadata in zip(blocks[:-1], views, view_metadata):
        part = block + '\n' + view
        if _units(header + '\n'.join(parts + [part])) > MAX_DDN_UNITS:
            name = flush()
            for item in pending:
                item['entry'] = name
            parts, pending = [], []
        parts.append(part)
        pending.append(metadata)
    name = flush()
    for item in pending:
        item['entry'] = name
    if len(files) > MAX_FILES:
        raise ValueError('Catalog exceeds the 64-file workspace limit')
    snapshot = {'format': 'ddn-workspace@1', 'entry': view_metadata[0]['entry'],
                'view': 'inventory_1', 'files': files}
    multi = len(files) > 1
    download = _json(snapshot) if multi else files['catalog.ddn']
    if len(download.encode('utf-8')) > MAX_BYTES:
        raise ValueError('Catalog exceeds the 8 MiB DDN export limit')
    result = {'snapshot': snapshot, 'provenance': provenance, 'views': view_metadata,
              'filename': f'{engine}-catalog.ddn-workspace.json' if multi else f'{engine}-catalog.ddn',
              'sha256': hashlib.sha256(download.encode('utf-8')).hexdigest()}
    if engine == 'mariadb':
        from .mariadb_erd import build_diagram
    elif engine == 'mysql':
        from .mysql_erd import build_diagram
    else:
        from .firebird_erd import build_diagram
    try:
        result['diagram'] = build_diagram(items, provenance)
    except ValueError as error:
        result['diagram'] = {'unavailable': str(error)}
    if multi:
        result['download_text'] = download
    return result
