"""Versioned DDN designs over the shared project asset repository."""
import hashlib
import json
import threading

from .assets import (ProjectAssetError, ProjectAssetForbidden,
                     ProjectAssetNotFound, validate_asset_request)

_LOCK = threading.RLock()


class NativeDesignAssets:
    def __init__(self, assets, *, engine='firebird'):
        if engine not in {'firebird', 'mysql'}:
            raise ProjectAssetError('Unsupported native design engine')
        self.assets = assets
        self.engine = engine
        self.title = {'firebird': 'Firebird', 'mysql': 'MySQL'}[engine]
        self.baseline_key = engine + 'Design'

    def apply(self, owner, scope, action, request):
        if not isinstance(request, dict) or set(request) - {
                'kind', 'database_target_id', 'version', 'assetRef', 'snapshot', 'baseline'}:
            raise ProjectAssetError('Invalid design request')
        kind = request.get('kind')
        if kind not in {'catalog', 'relations'} or action not in {'read', 'save'}:
            raise ProjectAssetError('Invalid native design family or action')
        identity = {**scope, 'kind': kind}
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        project = f'{self.engine}-designs-{owner}'
        reference = {'schemaVersion': 1, 'projectId': project, 'assetId': key,
                     'assetVersion': 0, 'assetType': 'ddn-workspace',
                     'path': f'designs/{key}.ddn', 'displayName': f'{self.title} {kind} design'}
        version = request.get('version')
        if version is not None and (type(version) is not int or version < 1):
            raise ProjectAssetError('Select a positive design revision')
        with _LOCK:
            row = self.assets.repository.project_by_key(project)
            if row is not None and row.user_id != owner:
                raise ProjectAssetForbidden('Design project is not owned by this user')
            current = None
            if row is not None:
                try:
                    current = self.assets.get_asset(owner, (), project, key)
                except ProjectAssetNotFound:
                    pass
            if action == 'read':
                if set(request) - {'kind', 'database_target_id', 'version'}:
                    raise ProjectAssetError('Invalid design read request')
                if version is not None and current is None:
                    raise ProjectAssetNotFound('Design revision is unavailable')
                result = (self.assets.get_asset(owner, (), project, key, version)
                          if version is not None else current)
            else:
                supplied = request.get('assetRef')
                if (version is not None or not isinstance(supplied, dict) or
                        set(supplied) != set(reference) or any(
                            supplied[k] != v for k, v in reference.items() if k != 'assetVersion')):
                    raise ProjectAssetError('Design reference does not match database scope')
                baseline = request.get('baseline')
                # Validate both workspaces before any repository mutation.
                body = {'schema': 'cdeadmin.ddn-asset.v1', 'assetRef': supplied,
                        'snapshot': baseline}
                validate_asset_request(body, project, key)
                body['snapshot'] = request.get('snapshot')
                validate_asset_request(body, project, key)
                body['snapshot'] = {**body['snapshot'], self.baseline_key: {'baseline': baseline}}
                body['metadata'] = {'scope': identity}
                validate_asset_request(body, project, key)
                from .assets import ProjectAssetConflict
                if supplied['assetVersion'] != (current['version'] if current else 0):
                    raise ProjectAssetConflict('Design version has changed; reload before saving')
                if row is None:
                    self.assets.create_project(owner, project, {
                        'name': self.title + ' database designs', 'source_control_eligible': False})
                result = self.assets.save_asset(owner, (), project, key, body)
                current = result
            if result and result['metadata'].get('scope') != identity:
                raise ProjectAssetError('Stored design scope differs from the selected database')
            if result:
                baseline = result['content'].get(self.baseline_key, {}).get('baseline')
                validate_asset_request({'schema': 'cdeadmin.ddn-asset.v1',
                    'assetRef': reference, 'snapshot': baseline}, project, key)
            return {'scope': identity, 'assetRef': current['assetRef'] if current else reference,
                    'version': result['version'] if result else 0,
                    'snapshot': {k: v for k, v in result['content'].items()
                                 if k != self.baseline_key} if result else None,
                    'baseline': result['content'][self.baseline_key]['baseline'] if result else None}


# Preserve the established Firebird constructor and asset namespace.
FirebirdDesignAssets = NativeDesignAssets
