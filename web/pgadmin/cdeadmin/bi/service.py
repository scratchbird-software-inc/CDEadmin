##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Saved-question and collection lifecycle plus provider compilation."""

from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime, timezone

from pgadmin.cdeadmin.semantic_models.models import (
    SemanticModelError, _validate_parameter_value,
)

from .access import (
    BIAccess, BIPermissionDenied, DatabaseGrantRepository,
    DatabasePrincipalDirectory,
)
from .builder import builder_to_semantic, semantic_to_query
from .models import (
    BIConflict, BIError, QUESTION_STATUSES, validate_collection,
    validate_question,
)
from .sqltext import assert_read_only_select, bind_placeholders

# Bound-parameter style per engine (the driver's marker, never inlined data).
BIND_STYLES = {
    'sqlite': 'qmark', 'duckdb': 'qmark', 'firebird': 'qmark',
    'mysql': 'format', 'mariadb': 'format', 'postgresql': 'format',
}
BIND_MARKERS = {'qmark': '?', 'format': '%s'}


class DatabaseBIRepository:
    """Persist collections, questions and immutable question revisions."""

    def __init__(self):
        from pgadmin.model import (
            db, BICollection, BISavedQuestion, BISavedQuestionRevision,
        )
        self.db = db
        self.collection = BICollection
        self.question = BISavedQuestion
        self.revision = BISavedQuestionRevision

    # collections ---------------------------------------------------------
    def collections(self, user_id):
        return self.collection.query.filter_by(user_id=user_id).order_by(
            self.collection.name).all()

    def get_collection(self, user_id, collection_id):
        if collection_id is None:
            return None
        return self.collection.query.filter_by(
            id=collection_id, user_id=user_id).first()

    # unscoped lookups: callers authorize through ``BIAccess`` -------------
    def all_collections(self):
        return self.collection.query.order_by(self.collection.name).all()

    def find_collection(self, collection_id):
        return self.collection.query.filter_by(id=collection_id).first()

    def find_question(self, endpoint_id, question_id):
        return self.question.query.filter_by(
            id=question_id, endpoint_id=endpoint_id).first()

    def questions_at(self, endpoint_id):
        return self.question.query.filter_by(
            endpoint_id=endpoint_id).order_by(self.question.name).all()

    def save_owner(self, row):
        self.db.session.add(row)
        self.db.session.commit()

    def new_collection(self, **values):
        return self.collection(**values)

    def save_collection(self, row):
        self.db.session.add(row)
        self.db.session.commit()

    def delete_collection(self, row):
        self.db.session.delete(row)
        self.db.session.commit()

    def collection_has_questions(self, user_id, collection_id):
        # any owner's question blocks deletion (sharing)
        return self.question.query.filter_by(
            collection_id=collection_id).first() is not None

    # questions -----------------------------------------------------------
    def questions(self, user_id, endpoint_id, collection_id=None,
                  every_collection=True):
        query = self.question.query.filter_by(
            user_id=user_id, endpoint_id=endpoint_id)
        if not every_collection:
            query = query.filter_by(collection_id=collection_id)
        return query.order_by(self.question.name).all()

    def get_question(self, user_id, endpoint_id, question_id):
        return self.question.query.filter_by(
            id=question_id, user_id=user_id, endpoint_id=endpoint_id).first()

    def new_question(self, **values):
        return self.question(**values)

    def save_question(self, row, snapshot, actor_user_id=None):
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.orm.exc import StaleDataError
        try:
            self.db.session.add(row)
            self.db.session.flush()
            self.db.session.add(self.revision(
                id=str(uuid.uuid4()), question_id=row.id,
                revision=row.revision, status=row.status,
                definition=snapshot, created_at=datetime.now(timezone.utc),
                actor_user_id=actor_user_id,
            ))
            self.db.session.commit()
        except StaleDataError as exc:
            self.db.session.rollback()
            raise BIConflict('saved question revision has changed') from exc
        except IntegrityError as exc:
            self.db.session.rollback()
            raise BIError('saved question revision already exists') from exc

    def revisions(self, question_id):
        return self.revision.query.filter_by(question_id=question_id).order_by(
            self.revision.revision.desc()).all()

    def delete_question(self, row):
        self.db.session.delete(row)
        self.db.session.commit()


def _now():
    return datetime.now(timezone.utc)


class BIService:
    """Own saved questions; the provider owns SQL and execution.

    Every lookup goes through ``self.access`` (``BIAccess``), the single
    authorization point: owner = ``manage``, plus explicit grants and
    inheritance (docs/en_US/bi_permissions.rst).
    """

    def __init__(self, semantic_service, repository=None, grants=None,
                 directory=None):
        self.semantic = semantic_service
        if repository is None:
            repository = DatabaseBIRepository()
            if grants is None:
                grants = DatabaseGrantRepository()
            if directory is None:
                directory = DatabasePrincipalDirectory()
        self.repository = repository
        self.access = BIAccess(grants, directory)
        self.access.register(
            'collection',
            find=lambda _ep, rid: self.repository.find_collection(rid),
            rows=lambda _ep: self.repository.all_collections(),
            set_owner=self._set_collection_owner)
        self.access.register(
            'question',
            find=lambda ep, rid: self.repository.find_question(ep, rid),
            rows=lambda ep: self.repository.questions_at(ep),
            set_owner=self._set_question_owner)
        self._listeners = []
        self._collection_guards = []
        self._question_guards = []
        self._raw_sql_policies = []

    def _set_collection_owner(self, row, new_owner_id):
        row.user_id = new_owner_id
        row.updated_at = _now()
        self.repository.save_collection(row)

    def _set_question_owner(self, row, new_owner_id):
        row.user_id = new_owner_id
        self.repository.save_owner(row)

    def add_collection_guard(self, callback):
        """``callback(user_id, collection_id) -> bool``: still in use."""
        self._collection_guards.append(callback)

    def add_question_guard(self, callback):
        """``callback(user_id, endpoint_id, question_id) -> name|None``."""
        self._question_guards.append(callback)

    def add_raw_sql_policy(self, callback):
        """``callback(user_id, endpoint_id) -> bool``: raw SQL may run here.

        Every registered callback must approve.  Without callbacks the
        built-in rule applies: raw SQL does not pass through semantic row
        policies, so it is refused on an endpoint whose semantic models
        declare row or tenant filters.
        """
        self._raw_sql_policies.append(callback)

    def assert_raw_sql_allowed(self, user_id, endpoint_id, also_users=()):
        """Refuse raw SQL for ``user_id`` (always the RUNNER).

        ``also_users`` adds the stored question's owner to the built-in
        scan: a shared raw question must not run for a viewer who happens to
        own no models when the owner's models declare row policies.
        """
        for callback in self._raw_sql_policies:
            if not callback(user_id, endpoint_id):
                raise BIError('raw SQL questions are not permitted for this '
                              'user on this endpoint')
        if self._raw_sql_policies:
            return
        for scanned in dict.fromkeys((user_id, *also_users)):
            for row in self.semantic.repository.list(scanned, endpoint_id):
                try:
                    security = (json.loads(row.definition).get('security')
                                or {})
                except (TypeError, ValueError):
                    continue
                if security.get('row_filters') or security.get(
                        'tenant_filter'):
                    raise BIError(
                        'raw SQL questions bypass semantic row policies and '
                        'are refused on an endpoint whose models declare '
                        'row or tenant filters; use a builder or semantic '
                        'question, or register a raw-SQL policy that grants '
                        'access')

    def on_question_change(self, callback):
        """Register ``callback(user_id, endpoint_id, question_id)``."""
        self._listeners.append(callback)

    def _changed(self, user_id, endpoint_id, question_id):
        for callback in self._listeners:
            callback(user_id, endpoint_id, question_id)

    # collections ---------------------------------------------------------
    def create_collection(self, user_id, value, endpoint_id=None):
        item = validate_collection(value)
        self._check_parent(user_id, None, item['parent_id'], endpoint_id)
        self._unique_collection_name(user_id, item['parent_id'],
                                     item['name'])
        now = _now()
        row = self.repository.new_collection(
            id=str(uuid.uuid4()), user_id=user_id, name=item['name'],
            parent_id=item['parent_id'], description=item['description'],
            created_at=now, updated_at=now)
        self.repository.save_collection(row)
        return self._collection(row, 'manage', True)

    def update_collection(self, user_id, collection_id, value,
                          endpoint_id=None):
        row, level = self.access.require(
            user_id, 'collection', endpoint_id, collection_id, 'edit',
            'change')
        item = validate_collection(value)
        if item['parent_id'] != row.parent_id:
            # moving re-parents every grant that flows into it
            self.access.require(user_id, 'collection', endpoint_id,
                                collection_id, 'manage', 'move')
            self._check_parent(user_id, row.id, item['parent_id'],
                               endpoint_id)
        self._unique_collection_name(row.user_id, item['parent_id'],
                                     item['name'], exclude=row.id)
        row.name, row.parent_id = item['name'], item['parent_id']
        row.description = item['description']
        row.updated_at = _now()
        self.repository.save_collection(row)
        return self._collection(row, level, row.user_id == user_id)

    def delete_collection(self, user_id, collection_id, endpoint_id=None):
        row, _level = self.access.require(
            user_id, 'collection', endpoint_id, collection_id, 'manage',
            'delete')
        if any(item.parent_id == row.id
               for item in self.repository.all_collections()) or (
                self.repository.collection_has_questions(user_id, row.id)
        ) or any(guard(user_id, row.id) for guard in self._collection_guards):
            raise BIError('collection must be empty before deletion')
        self.repository.delete_collection(row)
        self.access.purge('collection', row.id)
        return {'collection_id': collection_id, 'deleted': True}

    def list_collections(self, user_id, endpoint_id=None):
        """Return the caller's own folders as a nested tree."""
        return self._tree([(r, 'manage', True)
                           for r in self.repository.collections(user_id)])

    def shared_with_me(self, user_id, endpoint_id):
        """Everything shared with the caller at this endpoint.

        ``collections`` is the nested tree of collections the caller does
        not own; ``questions`` and ``dashboards`` are the shared items
        (``access`` is the effective level, ``is_owner`` is always false).
        """
        collections = [item for item in self.access.visible(
            user_id, 'collection', endpoint_id) if not item[2]]
        questions = [item for item in self.access.visible(
            user_id, 'question', endpoint_id) if not item[2]]
        result = {
            'collections': self._tree(collections),
            'questions': [self._summary(r, level, False)
                          for r, level, _ in questions],
            'dashboards': [],
        }
        if 'dashboard' in self.access.kinds:
            result['dashboards'] = [
                self._dashboard_summary(r, level, False)
                for r, level, owned in self.access.visible(
                    user_id, 'dashboard', endpoint_id) if not owned]
        return result

    def _tree(self, entries):
        nodes = {r.id: self._collection(r, level, owned) | {'children': []}
                 for r, level, owned in entries}
        roots = []
        for node in nodes.values():
            parent = nodes.get(node['parent_id'])
            (parent['children'] if parent else roots).append(node)
        return roots

    @staticmethod
    def _dashboard_summary(row, level, owned):
        return {'dashboard_id': row.id, 'name': row.name,
                'collection_id': row.collection_id, 'status': row.status,
                'revision': row.revision, 'access': level,
                'is_owner': owned, 'updated_at': row.updated_at.isoformat()}

    def _collection_row(self, user_id, collection_id, endpoint_id=None,
                        minimum='view', action=None):
        return self.access.require(user_id, 'collection', endpoint_id,
                                   collection_id, minimum, action)[0]

    def _check_parent(self, user_id, own_id, parent_id, endpoint_id=None):
        if parent_id is None:
            return
        parent = self._collection_row(user_id, parent_id, endpoint_id,
                                      'edit', 'add collections to')
        depth, cursor, seen = 1, parent, set()
        while cursor is not None:
            if cursor.id == own_id or cursor.id in seen:
                raise BIError('collection cannot be moved into itself')
            seen.add(cursor.id)
            depth += 1
            cursor = (self.repository.find_collection(cursor.parent_id)
                      if cursor.parent_id is not None else None)
        if depth > 16:
            raise BIError('collections are nested too deeply')

    def _unique_collection_name(self, user_id, parent_id, name,
                                exclude=None):
        for row in self.repository.collections(user_id):
            if row.parent_id == parent_id and row.name == name and (
                    row.id != exclude):
                raise BIError('collection name already exists')

    @staticmethod
    def _collection(row, access='manage', owned=True):
        return {'collection_id': row.id, 'parent_id': row.parent_id,
                'name': row.name, 'description': row.description,
                'updated_at': row.updated_at.isoformat(),
                'access': access, 'is_owner': owned}

    # questions -----------------------------------------------------------
    def list_questions(self, user_id, endpoint_id, **filters):
        """Questions the caller may view (owned and shared)."""
        scoped = 'collection_id' in filters
        return [self._summary(row, level, owned)
                for row, level, owned in self.access.visible(
                    user_id, 'question', endpoint_id)
                if not scoped or row.collection_id == filters[
                    'collection_id']]

    def get_question(self, user_id, endpoint_id, question_id):
        row, level = self.access.require(
            user_id, 'question', endpoint_id, question_id)
        return self._present(row, level, user_id)

    def create_question(self, user_id, endpoint_id, value):
        question = validate_question(value)
        self._check_references(user_id, endpoint_id, question)
        now = _now()
        row = self.repository.new_question(
            id=str(uuid.uuid4()), user_id=user_id, endpoint_id=endpoint_id,
            status='active', revision=1, created_at=now, updated_at=now,
            **self._columns(question))
        self._save(row, row.definition, user_id)
        return self._present(row, 'manage', user_id)

    def update_question(self, user_id, endpoint_id, question_id,
                        expected_revision, value):
        row, level = self.access.require(
            user_id, 'question', endpoint_id, question_id, 'edit', 'change')
        self._check_revision(row, expected_revision)
        question = validate_question(value)
        self._check_references(user_id, endpoint_id, question,
                               exclude=row.id, row=row)
        for key, item in self._columns(question).items():
            setattr(row, key, item)
        row.revision += 1
        row.updated_at = _now()
        self._save(row, row.definition, user_id)
        self._changed(user_id, endpoint_id, row.id)
        return self._present(row, level, user_id)

    def set_status(self, user_id, endpoint_id, question_id,
                   expected_revision, status):
        row, level = self.access.require(
            user_id, 'question', endpoint_id, question_id, 'edit',
            'archive or restore')
        self._check_revision(row, expected_revision)
        if status not in QUESTION_STATUSES:
            raise BIError('saved question status is unsupported')
        row.status = status
        row.revision += 1
        row.updated_at = _now()
        self._save(row, row.definition, user_id)
        self._changed(user_id, endpoint_id, row.id)
        return self._present(row, level, user_id)

    def move_question(self, user_id, endpoint_id, question_id,
                      expected_revision, collection_id):
        row, _level = self.access.require(
            user_id, 'question', endpoint_id, question_id, 'edit', 'move')
        value = json.loads(row.definition)
        value['collection_id'] = collection_id
        return self.update_question(user_id, endpoint_id, question_id,
                                    expected_revision, value)

    def clone_question(self, user_id, endpoint_id, question_id, name):
        row, level = self.access.require(
            user_id, 'question', endpoint_id, question_id)
        value = json.loads(row.definition)
        if self._redacts(value, level):
            # a copy would expose SQL text the caller may not read
            raise BIPermissionDenied(
                'edit access is required to duplicate a raw SQL question')
        value['name'] = name
        target = value.get('collection_id')
        if target is not None and self.access.level(
                user_id, 'collection', endpoint_id, target) not in (
                'edit', 'manage'):
            value['collection_id'] = None  # the copy goes to the root
        return self.create_question(user_id, endpoint_id, value)

    def delete_question(self, user_id, endpoint_id, question_id,
                        expected_revision):
        row, _level = self.access.require(
            user_id, 'question', endpoint_id, question_id, 'manage',
            'delete')
        self._check_revision(row, expected_revision)
        for guard in self._question_guards:
            user = guard(user_id, endpoint_id, question_id)
            if user:
                raise BIError(
                    f'saved question is used by dashboard {user!r}')
        self.repository.delete_question(row)
        self.access.purge('question', question_id)
        self._changed(user_id, endpoint_id, question_id)
        return {'question_id': question_id, 'deleted': True}

    def history(self, user_id, endpoint_id, question_id):
        row, _level = self.access.require(
            user_id, 'question', endpoint_id, question_id)
        return [{'revision': item.revision, 'status': item.status,
                 'created_at': item.created_at.isoformat(),
                 'actor_user_id': getattr(item, 'actor_user_id', None),
                 'actor': self.access.actor_name(
                     user_id, getattr(item, 'actor_user_id', None))}
                for item in self.repository.revisions(row.id)]

    def revision(self, user_id, endpoint_id, question_id, revision):
        row, level = self.access.require(
            user_id, 'question', endpoint_id, question_id)
        for item in self.repository.revisions(row.id):
            if item.revision == revision:
                definition = json.loads(item.definition)
                redacted = self._redacts(definition, level)
                return {'question_id': row.id, 'revision': revision,
                        'status': item.status, 'access': level,
                        'sql_redacted': redacted,
                        'definition': self._redact(definition)
                        if redacted else definition}
        raise BIError('requested saved question revision is unavailable')

    def stored_for_run(self, user_id, endpoint_id, question_id,
                       revision=None):
        """The stored (optionally pinned) definition for the RUNNER.

        Needs ``view``.  The definition is complete (the executor needs the
        SQL to run it); ``redact_sql`` tells the caller to keep raw SQL text
        out of every response.  ``owner_id`` is internal: it selects the
        semantic models that supply row policies, which are still evaluated
        with the runner's claims.
        """
        row, level = self.access.require(
            user_id, 'question', endpoint_id, question_id, 'view', 'run')
        if revision is None:
            definition, resolved = json.loads(row.definition), row.revision
        else:
            for item in self.repository.revisions(row.id):
                if item.revision == revision:
                    definition, resolved = json.loads(item.definition), (
                        revision)
                    break
            else:
                raise BIError(
                    'requested saved question revision is unavailable')
        return {'definition': definition, 'revision': resolved,
                'status': row.status, 'owner_id': row.user_id,
                'access': level,
                'redact_sql': self._redacts(definition, level)}

    def transfer_owner(self, user_id, endpoint_id, kind, resource_id,
                       new_owner_id, confirm=None):
        """Hand a collection, question or dashboard to another user."""
        if kind == 'question':
            row, _ = self.access.require(
                user_id, 'question', endpoint_id, resource_id, 'manage',
                'transfer ownership of')
            if row.semantic_model_id is not None and (
                    self.semantic.repository.get(
                        new_owner_id, endpoint_id, row.semantic_model_id
                    ) is None):
                raise BIError('the new owner does not have the semantic '
                              'model this question uses')
        return self.access.transfer_owner(
            user_id, kind, endpoint_id, resource_id, new_owner_id, confirm)

    # sharing facade ------------------------------------------------------
    def effective_access(self, user_id, endpoint_id, kind, resource_id):
        return self.access.effective_access(user_id, kind, endpoint_id,
                                            resource_id)

    @staticmethod
    def _redacts(definition, level):
        return definition['query']['kind'] == 'sql' and (
            level not in ('edit', 'manage'))

    @staticmethod
    def _redact(definition):
        value = copy.deepcopy(definition)
        value['query']['sql'] = ''
        return value

    # compilation ---------------------------------------------------------
    def compile(self, provider, user_id, endpoint_id, question_id=None,
                definition=None, parameters=None, revision=None,
                security_context=None):
        """Compile a stored (optionally pinned) or ad hoc question."""
        owner_id, redact = None, False
        if question_id is not None:
            stored = self.stored_for_run(user_id, endpoint_id, question_id,
                                         revision)
            question = stored['definition']
            owner_id, redact = stored['owner_id'], stored['redact_sql']
        else:
            question = validate_question(definition)
        compiled = self.compile_definition(
            provider, user_id, endpoint_id, question, parameters,
            security_context, owner_id=owner_id)
        if redact:
            compiled = dict(compiled, source=None, sql_redacted=True)
        return compiled

    def compile_definition(self, provider, user_id, endpoint_id, question,
                           parameters=None, security_context=None,
                           bind=False, extra_filters=(), owner_id=None):
        """Compile a validated question.

        ``user_id`` is always the runner.  ``owner_id`` (a stored question's
        owner) only selects which semantic models supply the definition and
        the raw-SQL policy scan; row policies are evaluated with the
        runner's ``security_context`` and the runner's own connection.

        With ``bind`` the SQL carries only the engine's parameter markers and
        ``parameters`` is the positional array of values, so no caller value
        is ever part of the statement text.  ``extra_filters`` are dashboard
        filters mapped onto a field; they are values too and are bound the
        same way.
        """
        parameters = dict(parameters or {})
        spec = question['query']
        known = {p['id'] for p in question['parameters']}
        if set(parameters) - known:
            raise BIError('compile request contains an unknown parameter')
        descriptor = getattr(provider, 'semantic_model_descriptor', None)
        provider_value = descriptor() if callable(descriptor) else None
        engine_id = (provider_value or {}).get('engine_id')
        style = None
        if bind:
            style = BIND_STYLES.get(engine_id)
            if style is None:
                raise BIError(
                    f'engine {engine_id!r} has no admitted bound-parameter '
                    'style for saved questions')
        if spec['kind'] == 'sql':
            self.assert_raw_sql_allowed(
                user_id, endpoint_id,
                also_users=(owner_id,) if owner_id not in (
                    None, user_id) else ())
            if extra_filters:
                raise BIError(
                    'dashboard field filters cannot be applied to raw SQL; '
                    'map the filter to a question parameter')
            return self._compile_raw(provider, question, parameters, style,
                                     engine_id)
        if spec['kind'] == 'builder':
            family = self.semantic.capabilities(provider)[
                'analytical_profile']['semantic_family']
            builder = copy.deepcopy(spec['builder'])
            builder['filters'] = builder['filters'] + [
                dict(f) for f in extra_filters]
            model, query, columns = builder_to_semantic(
                builder, question['parameters'], family)
        else:
            model = self._semantic_definition(
                owner_id if owner_id is not None else user_id, endpoint_id,
                question['semantic_model'])
            query, columns = semantic_to_query(spec['builder']), None
            query['filters'] = query['filters'] + [
                dict(f) for f in extra_filters]
        query['parameters'] = parameters
        if style is not None:
            query['bind'] = style
        compiled = self.semantic.compile(
            provider, model, query, security_context=security_context)
        compiled['kind'] = spec['kind']
        compiled['output_columns'] = columns if columns is not None else (
            [{'id': i, 'kind': 'dimension', 'label': i}
             for i in query['axes']['rows']] +
            [{'id': i, 'kind': 'measure', 'label': i}
             for i in query['measures']])
        compiled['engine_id'] = engine_id
        compiled['bound'] = style is not None
        return compiled

    @staticmethod
    def _compile_raw(provider, question, parameters, style=None,
                     engine_id=None):
        declared = {p['id']: p for p in question['parameters']}
        for pid, item in declared.items():
            if item['required'] and pid not in parameters and (
                    'default' not in item):
                raise BIError(f'parameter {pid!r} requires a value')
        values = {pid: item['default'] for pid, item in declared.items()
                  if 'default' in item} | parameters
        descriptor = getattr(provider, 'semantic_model_descriptor', None)
        provider_value = descriptor() if callable(descriptor) else {}
        result = {
            'kind': 'sql', 'source': question['query']['sql'],
            'parameters': values,
            'language_profile': (provider_value or {}).get(
                'language_profile'),
            'engine_id': engine_id or (provider_value or {}).get(
                'engine_id'),
            'warnings': ['Raw SQL is passed to the provider unchanged.'],
            'bound': False,
        }
        sql = question['query']['sql']
        assert_read_only_select(sql)  # also for compile-only previews
        if style is None:
            return result
        source, names = bind_placeholders(sql, BIND_MARKERS[style], declared)
        ordered = []
        for pid in names:
            if pid not in values:
                raise BIError(f'parameter {pid!r} requires a value')
            item, value = declared[pid], values[pid]
            if item['type'] == 'array':
                raise BIError(
                    f'array parameter {pid!r} needs a builder filter, not '
                    'a raw SQL marker')
            try:
                _validate_parameter_value(value, item['type'])
            except SemanticModelError as exc:
                raise BIError(f'parameter {pid!r}: {exc}') from exc
            if item['allowed_values'] and value not in item['allowed_values']:
                raise BIError(f'parameter {pid!r} value is not allowed')
            ordered.append(value)
        result.update(
            source=source, parameters=ordered, bound=True,
            warnings=['Raw SQL has read-only lexical checks only; the '
                      'connection privileges remain the authority.'],
            output_columns=None)
        return result

    def _semantic_definition(self, user_id, endpoint_id, reference):
        repository = self.semantic.repository
        row = repository.get(user_id, endpoint_id, reference['id'])
        if row is None:
            raise BIError('semantic model is unavailable')
        revision = reference.get('revision')
        if revision is None or revision == row.revision:
            return json.loads(row.definition)
        for item in repository.revisions(row.id):
            if item.revision == revision:
                return json.loads(item.definition)
        raise BIError('pinned semantic model revision is unavailable')

    # helpers -------------------------------------------------------------
    def _check_references(self, user_id, endpoint_id, question,
                          exclude=None, row=None):
        owner_id = row.user_id if row is not None else user_id
        collection_id = question['collection_id']
        if collection_id is not None and (
                row is None or collection_id != row.collection_id):
            self._collection_row(user_id, collection_id, endpoint_id,
                                 'edit', 'add items to')
        reference = question['semantic_model']
        if reference is not None:
            try:
                self._semantic_definition(owner_id, endpoint_id, reference)
            except SemanticModelError as exc:
                raise BIError(str(exc)) from exc
        for other in self.repository.questions(owner_id, endpoint_id):
            if other.id != exclude and other.name == question['name'] and (
                    other.collection_id == collection_id):
                raise BIError('saved question name already exists')

    def _save(self, row, snapshot, actor_user_id):
        self.repository.save_question(row, snapshot,
                                      actor_user_id=actor_user_id)

    @staticmethod
    def _columns(question):
        reference = question['semantic_model'] or {}
        return {
            'name': question['name'],
            'collection_id': question['collection_id'],
            'semantic_model_id': reference.get('id'),
            'semantic_model_revision': reference.get('revision'),
            'definition': json.dumps(question),
        }

    @staticmethod
    def _check_revision(row, expected):
        if isinstance(expected, bool) or not isinstance(expected, int):
            raise BIError('expected_revision must be an integer')
        if row.revision != expected:
            raise BIConflict('saved question revision has changed')

    @staticmethod
    def _summary(row, access='manage', owned=True):
        return {'question_id': row.id, 'name': row.name,
                'collection_id': row.collection_id, 'status': row.status,
                'revision': row.revision,
                'semantic_model_id': row.semantic_model_id,
                'updated_at': row.updated_at.isoformat(),
                'access': access, 'is_owner': owned}

    @classmethod
    def _present(cls, row, access='manage', viewer_id=None):
        definition = json.loads(row.definition)
        redacted = cls._redacts(definition, access)
        return cls._summary(row, access, row.user_id == viewer_id) | {
            'sql_redacted': redacted,
            'definition': cls._redact(definition) if redacted
            else copy.deepcopy(definition)}
