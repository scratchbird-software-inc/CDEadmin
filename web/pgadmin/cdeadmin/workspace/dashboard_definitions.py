"""Owner-scoped DDN drafts; saving is not dashboard publication."""

import hashlib
import json
import threading

from .assets import ProjectAssetError, ProjectAssetForbidden, ProjectAssetNotFound

# Serialize this adapter's read/check/save operations. The underlying asset store
# remains authoritative and carries immutable revisions and expected versions.
_LOCK = threading.RLock()


class DashboardDefinitions:
    def __init__(self, assets, authorize, validator=None):
        self.assets = assets
        self.authorize = authorize
        from .dashboard_validation import validate_dashboard
        self.validate = validator or validate_dashboard

    def _identity(self, owner, sid, target):
        scope = self.authorize(owner, sid, target)
        project = f'firebird-dashboard-drafts-{owner}'
        key = hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()
        reference = {'schemaVersion': 1, 'projectId': project, 'assetId': key,
                     'assetVersion': 0, 'assetType': 'ddn-workspace',
                     'path': f'dashboards/{key}.ddn',
                     'displayName': f"Firebird {scope['kind']} dashboard draft"}
        return scope, reference

    def _project(self, owner, key):
        row = self.assets.repository.project_by_key(key)
        if row is not None and row.user_id != owner:
            raise ProjectAssetForbidden('Dashboard project is not owned by this user')
        return row

    def read(self, owner, sid=None, target=None):
        scope, reference = self._identity(owner, sid, target)
        with _LOCK:
            project = self._project(owner, reference['projectId'])
            result = None
            if project is not None:
                try:
                    result = self.assets.get_asset(owner, (), reference['projectId'],
                                                   reference['assetId'])
                except ProjectAssetNotFound:
                    pass
            publication = self._publication(owner, reference)
            return {'state': 'draft', 'scope': scope,
                    'publication_version': publication['version'] if publication else 0,
                    'assetRef': result['assetRef'] if result else reference,
                    'snapshot': result['content'] if result else None}

    def save(self, owner, sid, target, body):
        scope, reference = self._identity(owner, sid, target)
        if not isinstance(body, dict) or set(body) != {'schema', 'assetRef', 'snapshot'}:
            raise ProjectAssetError('Expected a DDN draft asset envelope')
        supplied = body.get('assetRef')
        if (body.get('schema') != 'cdeadmin.ddn-asset.v1' or
                not isinstance(supplied, dict) or
                any(supplied.get(key) != value for key, value in reference.items()
                    if key != 'assetVersion')):
            raise ProjectAssetError('Dashboard draft reference does not match scope')
        # Validate before creating any project; no empty project on bad input.
        from .assets import validate_asset_request
        validate_asset_request(body, reference['projectId'], reference['assetId'])
        with _LOCK:
            if self._project(owner, reference['projectId']) is None:
                if supplied.get('assetVersion') != 0:
                    from .assets import ProjectAssetConflict
                    raise ProjectAssetConflict('Dashboard draft version has changed')
                self.assets.create_project(owner, reference['projectId'], {
                    'name': 'Firebird dashboard drafts',
                    'source_control_eligible': False})
            result = self.assets.save_asset(owner, (), reference['projectId'],
                                            reference['assetId'], body)
            return {'state': 'draft', 'scope': scope,
                    'publication_version': (self._publication(owner, reference) or {}).get('version', 0),
                    'assetRef': result['assetRef'], 'snapshot': result['content']}


    def _publication(self, owner, reference):
        if self._project(owner, reference['projectId']) is None:
            return None
        try:
            return self.assets.get_asset(owner, (), reference['projectId'],
                                         reference['assetId'] + '-published')
        except ProjectAssetNotFound:
            return None

    def published(self, owner, sid=None, target=None):
        scope, reference = self._identity(owner, sid, target)
        publication = self._publication(owner, reference)
        if publication is None:
            return {'state': 'standard', 'scope': scope, 'version': 0, 'snapshot': None}
        # Recheck even content changed through the generic asset API.
        snapshot = self.validate(publication['content'], scope['kind'])
        return {'state': 'published', 'scope': scope, 'version': publication['version'],
                'snapshot': snapshot, 'source_version': publication['metadata'].get('source_version')}

    def publish(self, owner, sid, target, body):
        from .assets import ProjectAssetConflict
        scope, reference = self._identity(owner, sid, target)
        if (not isinstance(body, dict) or set(body) != {'source_version', 'expected_version'} or
                type(body['source_version']) is not int or body['source_version'] < 1 or
                type(body['expected_version']) is not int or body['expected_version'] < 0):
            raise ProjectAssetError('Publication requires exact saved versions')
        with _LOCK:
            if self._project(owner, reference['projectId']) is None:
                raise ProjectAssetNotFound('Save the dashboard draft before publishing')
            source = self.assets.get_asset(owner, (), reference['projectId'],
                                            reference['assetId'], body['source_version'])
            snapshot = self.validate(source['content'], scope['kind'])
            previous = self._publication(owner, reference)
            if (previous['version'] if previous else 0) != body['expected_version']:
                raise ProjectAssetConflict('Dashboard publication has changed')
            published_ref = {**reference, 'assetId': reference['assetId'] + '-published',
                             'path': f"dashboards/{reference['assetId']}.published.ddn",
                             'assetVersion': body['expected_version'],
                             'displayName': f"Firebird {scope['kind']} published dashboard"}
            from sqlalchemy.exc import IntegrityError
            try:
                result = self.assets.save_asset(owner, (), reference['projectId'], published_ref['assetId'], {
                    'schema': 'cdeadmin.ddn-asset.v1', 'assetRef': published_ref,
                    'snapshot': snapshot, 'metadata': {'source_version': body['source_version'],
                        'binding_contract': 'firebird-observations-v1'},
                })
            except IntegrityError:
                # Two workers may both see no first publication. Unique asset
                # identity selects one winner; report the loser as a conflict.
                self.assets.repository.rollback()
                current = self._publication(owner, reference)
                if current and current['version'] != body['expected_version']:
                    raise ProjectAssetConflict('Dashboard publication has changed') from None
                raise
            return {'state': 'published', 'scope': scope, 'version': result['version'],
                    'source_version': body['source_version'], 'snapshot': snapshot}
