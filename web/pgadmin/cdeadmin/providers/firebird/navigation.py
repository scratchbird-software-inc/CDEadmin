"""Firebird-only virtual folders; native identities remain unchanged."""

ROOTS = ('monitoring', 'programming', 'security', 'system')
SYSTEM = {'configuration': 'configuration', 'publication': 'replication',
          'trigger': 'database-triggers', 'service-operation': 'service',
          'shadow': 'shadows', 'storage-file': 'storage',
          'character-set': 'character sets', 'collation': 'collations'}
PROGRAMMING = {'procedure': 'procedures', 'domain': 'domains',
               'blob-filter': 'filters', 'exception': 'exceptions',
               'external-function': 'external functions', 'function': 'functions',
               'package': 'packages', 'sequence': 'sequences'}
SECURITY = {'user': 'users', 'role': 'roles', 'privilege': 'grants',
            'authentication-mapping': 'authentication mappings',
            'global-authentication-mapping': 'global authentication mappings'}


def children(resources, prepared, state):
    from pgadmin.cdeadmin.navigator import resource_native, ProviderNavigatorError, kind_label

    def ordered(nodes):
        return sorted(nodes, key=lambda n: (
            n['node_type'] != 'group' and not n.get('section'),
            n['label'].casefold(), n.get('resource_id', '')))

    def group(label, kind, branch=None):
        return {'node_type': 'group', 'label': label, 'resource_kind': kind,
                'parent_path': state.get('parent_path', []), 'has_children': True,
                'virtual_branch': branch or state.get('virtual_branch')}

    def resource(item, section=None):
        return {'node_type': 'resource', 'label': section or item['display_name'],
                'resource_kind': item['resource_kind'], 'resource_id': item['resource_id'],
                'display_path': item['_navigator_path'], 'resource': item['_source'],
                'has_children': False if section else item['resource_kind'] in
                {'table', 'view', 'column', 'package'} or any(
                    p['_navigator_path'][:-1] == item['_navigator_path'] for p in prepared),
                **({'section': section} if section else {})}

    def category(item):
        kind, name = item['resource_kind'], item['display_name'].upper()
        if kind in {'table', 'view', 'metric'} and name.startswith('MON$'):
            return 'monitoring'
        if kind in {'table', 'view'} and name.startswith('SEC$'):
            return 'security'
        if kind in {'table', 'view'}:
            if name.startswith('RDB$'):
                return 'system'
            if name.startswith('MON$'):
                return 'monitoring'
            if name.startswith('SEC$'):
                return 'security'
            if resource_native(item['_source']).get('system_object'):
                return 'system'
            return 'root'
        if kind in SYSTEM:
            return 'system'
        if kind in PROGRAMMING:
            return 'programming'
        if kind in SECURITY:
            return 'security'
        return 'system'

    top = [p for p in prepared if len(p['_navigator_path']) == 1 and
           not resource_native(p['_source']).get('navigator_parent_resource_id')]
    scope, branch = state['scope'], state.get('virtual_branch')
    if scope == 'database':
        return ordered([group(name, 'firebird-folder', name) for name in ROOTS] +
                       [resource(p) for p in top if category(p) == 'root'])
    if scope == 'resource':
        owner = next((p for p in prepared if p['resource_id'] == state.get('resource_id') and
                      p['_navigator_path'] == state.get('parent_path')), None)
        if owner is None:
            raise ProviderNavigatorError('navigator resource is unavailable')
        kind = owner['resource_kind']
        if kind in {'table', 'view', 'column'}:
            kinds = ('column', 'index', 'trigger',
                     'constraint') if kind != 'column' else ()
            groups = [group({'column': 'columns', 'index': 'indexes',
                            'trigger': 'triggers', 'constraint': 'constraints'}[k], k) for k in kinds]
            sections = ('dependencies', 'comments', 'grants') if kind != 'column' else (
                'constraints', 'calculations', 'comments', 'grants')
            return ordered(groups + [resource(owner, s) for s in sections])
        return None  # Preserve native package and other child discovery.
    if scope == 'kind' and state.get('resource_kind') == 'firebird-folder':
        if branch not in ROOTS:
            raise ProviderNavigatorError('Unknown Firebird virtual branch')
        mapping = SYSTEM if branch == 'system' else PROGRAMMING if branch == 'programming' else SECURITY if branch == 'security' else {}
        groups = [group(label, kind, branch)
                  for kind, label in mapping.items()]
        selected = [p for p in top if category(p) == branch]
        extra_kinds = {p['resource_kind'] for p in selected} - set(mapping) - {'table', 'view'}
        if branch == 'monitoring':
            extra_kinds.discard('metric')
        groups += [group(kind_label(kind), kind, branch) for kind in extra_kinds]
        direct = [resource(p) for p in selected if p['resource_kind'] in {
            'table', 'view'} or (branch == 'monitoring' and p['resource_kind'] == 'metric')]
        return ordered(groups + direct)
    if scope == 'kind':
        parent_id = state.get('resource_id')
        parent_path = state.get('parent_path', [])
        selected = []
        for p in prepared:
            if p['resource_kind'] != state.get('resource_kind'):
                continue
            native_parent = resource_native(p['_source']).get(
                'navigator_parent_resource_id')
            if parent_id:
                if native_parent and native_parent != parent_id:
                    continue
                if p['_navigator_path'][:-1] != parent_path:
                    continue
            elif category(p) != branch or p not in top:
                continue
            selected.append(resource(p))
        return sorted(selected, key=lambda p: (p['label'].casefold(), p['resource_id']))
    return None
