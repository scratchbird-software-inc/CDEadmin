"""Owner/database-bound immutable recipe revisions; reading never executes SQL."""
import hashlib
import json
import re
import threading

from .assets import (ProjectAssetError, ProjectAssetForbidden,
                     ProjectAssetNotFound, validate_asset_request)

LOCK = threading.RLock()
ENGINE_NAMES = {'mysql': 'MySQL', 'mariadb': 'MariaDB', 'postgresql': 'PostgreSQL',
                'duckdb': 'DuckDB', 'sqlite': 'SQLite'}


class MySQLRecipeAssets:
    def __init__(self, assets, *, engine='mysql'):
        if engine not in ENGINE_NAMES:
            raise ValueError('Unsupported native recipe engine')
        self.assets = assets
        self.engine = engine

    def apply(self, owner, scope, action, request):
        if not isinstance(request, dict) or set(request) - {
                'database_target_id', 'recipe_id', 'version', 'expected_version', 'recipe'}:
            raise ProjectAssetError('Invalid recipe request')
        name = request.get('recipe_id', 'default')
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', name):
            raise ProjectAssetError('Recipe name requires 1 to 64 letters, digits, dots, underscores or hyphens')
        if action not in {'read', 'save'}:
            raise ProjectAssetError('Invalid recipe action')
        identity = {'engine': self.engine, **scope, 'recipe_id': name}
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        project = f'{self.engine}-recipes-{owner}'
        version = request.get('version')
        if version is not None and (type(version) is not int or version < 1):
            raise ProjectAssetError('Select a positive recipe revision')
        with LOCK:
            row = self.assets.repository.project_by_key(project)
            if row is not None and row.user_id != owner:
                raise ProjectAssetForbidden('Recipe project is not owned')
            current = None
            if row is not None:
                try:
                    current = self.assets.get_asset(owner, (), project, key)
                except ProjectAssetNotFound:
                    pass
            if action == 'read':
                if set(request) - {'database_target_id', 'recipe_id', 'version'}:
                    raise ProjectAssetError('Invalid recipe read')
                if version is not None and current is None:
                    raise ProjectAssetNotFound('Recipe revision unavailable')
                saved = self.assets.get_asset(owner, (), project, key, version) if version is not None else current
            else:
                recipe = request.get('recipe')
                if version is not None or not isinstance(recipe, dict) or recipe.get('scope') != scope or recipe.get('format') != f'scratchrobin.{self.engine}.test-data@1':
                    raise ProjectAssetError('Recipe belongs to another native database')
                body = {'asset_type': f'{self.engine}-test-data-recipe', 'schema_name': f'scratchrobin.{self.engine}.test-data@1',
                        'name': name, 'path': f'recipes/{key}.json', 'expected_version': request.get('expected_version'),
                        'content': recipe, 'metadata': {'scope': identity}, 'source_control_eligible': False}
                validate_asset_request(body, project, key)
                if current is None and body['expected_version'] != 0:
                    raise ProjectAssetError('The recipe has no current revision; refresh before saving')
                if row is None:
                    self.assets.create_project(owner, project, {'name': ENGINE_NAMES[self.engine] + ' test-data recipes', 'source_control_eligible': False})
                saved = self.assets.save_asset(owner, (), project, key, body)
                current = saved
            if saved and (saved['metadata'].get('scope') != identity or saved['content'].get('scope') != scope):
                raise ProjectAssetError('Stored recipe scope differs')
            return {'recipe_id': name, 'scope': scope, 'recipe': saved['content'] if saved else None,
                    'version': saved['version'] if saved else 0, 'current_version': current['version'] if current else 0,
                    'executed': False}
