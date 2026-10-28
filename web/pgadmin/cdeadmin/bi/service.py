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

    def new_collection(self, **values):
        return self.collection(**values)

    def save_collection(self, row):
        self.db.session.add(row)
        self.db.session.commit()

    def delete_collection(self, row):
        self.db.session.delete(row)
        self.db.session.commit()

    def collection_has_questions(self, user_id, collection_id):
        return self.question.query.filter_by(
            user_id=user_id, collection_id=collection_id).first() is not None

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

    def save_question(self, row, snapshot):
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.orm.exc import StaleDataError
        try:
            self.db.session.add(row)
            self.db.session.flush()
            self.db.session.add(self.revision(
                id=str(uuid.uuid4()), question_id=row.id,
                revision=row.revision, status=row.status,
                definition=snapshot, created_at=datetime.now(timezone.utc),
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
    """Own saved questions; the provider owns SQL and execution."""

    def __init__(self, semantic_service, repository=None):
        self.semantic = semantic_service
        self.repository = repository or DatabaseBIRepository()
        self._listeners = []
        self._collection_guards = []
        self._question_guards = []

    def add_collection_guard(self, callback):
        """``callback(user_id, collection_id) -> bool``: still in use."""
        self._collection_guards.append(callback)

    def add_question_guard(self, callback):
        """``callback(user_id, endpoint_id, question_id) -> name|None``."""
        self._question_guards.append(callback)

    def on_question_change(self, callback):
        """Register ``callback(user_id, endpoint_id, question_id)``."""
        self._listeners.append(callback)

    def _changed(self, user_id, endpoint_id, question_id):
        for callback in self._listeners:
            callback(user_id, endpoint_id, question_id)

    # collections ---------------------------------------------------------
    def create_collection(self, user_id, value):
        item = validate_collection(value)
        self._check_parent(user_id, None, item['parent_id'])
        self._unique_collection_name(user_id, item['parent_id'],
                                     item['name'])
        now = _now()
        row = self.repository.new_collection(
            id=str(uuid.uuid4()), user_id=user_id, name=item['name'],
            parent_id=item['parent_id'], description=item['description'],
            created_at=now, updated_at=now)
        self.repository.save_collection(row)
        return self._collection(row)

    def update_collection(self, user_id, collection_id, value):
        row = self._collection_row(user_id, collection_id)
        item = validate_collection(value)
        self._check_parent(user_id, row.id, item['parent_id'])
        self._unique_collection_name(user_id, item['parent_id'],
                                     item['name'], exclude=row.id)
        row.name, row.parent_id = item['name'], item['parent_id']
        row.description = item['description']
        row.updated_at = _now()
        self.repository.save_collection(row)
        return self._collection(row)

    def delete_collection(self, user_id, collection_id):
        row = self._collection_row(user_id, collection_id)
        rows = self.repository.collections(user_id)
        if any(item.parent_id == row.id for item in rows) or (
                self.repository.collection_has_questions(user_id, row.id)
        ) or any(guard(user_id, row.id) for guard in self._collection_guards):
            raise BIError('collection must be empty before deletion')
        self.repository.delete_collection(row)
        return {'collection_id': collection_id, 'deleted': True}

    def list_collections(self, user_id):
        """Return the owner's folders as a nested tree."""
        nodes = {r.id: self._collection(r) | {'children': []}
                 for r in self.repository.collections(user_id)}
        roots = []
        for node in nodes.values():
            parent = nodes.get(node['parent_id'])
            (parent['children'] if parent else roots).append(node)
        return roots

    def _collection_row(self, user_id, collection_id):
        row = self.repository.get_collection(user_id, collection_id)
        if row is None:
            raise BIError('collection is unavailable')
        return row

    def _check_parent(self, user_id, own_id, parent_id):
        if parent_id is None:
            return
        parent = self._collection_row(user_id, parent_id)
        depth, cursor, seen = 1, parent, set()
        while cursor is not None:
            if cursor.id == own_id or cursor.id in seen:
                raise BIError('collection cannot be moved into itself')
            seen.add(cursor.id)
            depth += 1
            cursor = self.repository.get_collection(user_id, cursor.parent_id)
        if depth > 16:
            raise BIError('collections are nested too deeply')

    def _unique_collection_name(self, user_id, parent_id, name,
                                exclude=None):
        for row in self.repository.collections(user_id):
            if row.parent_id == parent_id and row.name == name and (
                    row.id != exclude):
                raise BIError('collection name already exists')

    @staticmethod
    def _collection(row):
        return {'collection_id': row.id, 'parent_id': row.parent_id,
                'name': row.name, 'description': row.description,
                'updated_at': row.updated_at.isoformat()}

    # questions -----------------------------------------------------------
    def list_questions(self, user_id, endpoint_id, **filters):
        scoped = 'collection_id' in filters
        return [self._summary(row) for row in self.repository.questions(
            user_id, endpoint_id, filters.get('collection_id'),
            every_collection=not scoped)]

    def get_question(self, user_id, endpoint_id, question_id):
        return self._present(self._required(user_id, endpoint_id,
                                            question_id))

    def create_question(self, user_id, endpoint_id, value):
        question = validate_question(value)
        self._check_references(user_id, endpoint_id, question)
        now = _now()
        row = self.repository.new_question(
            id=str(uuid.uuid4()), user_id=user_id, endpoint_id=endpoint_id,
            status='active', revision=1, created_at=now, updated_at=now,
            **self._columns(question))
        self.repository.save_question(row, row.definition)
        return self._present(row)

    def update_question(self, user_id, endpoint_id, question_id,
                        expected_revision, value):
        row = self._required(user_id, endpoint_id, question_id)
        self._check_revision(row, expected_revision)
        question = validate_question(value)
        self._check_references(user_id, endpoint_id, question, exclude=row.id)
        for key, item in self._columns(question).items():
            setattr(row, key, item)
        row.revision += 1
        row.updated_at = _now()
        self.repository.save_question(row, row.definition)
        self._changed(user_id, endpoint_id, row.id)
        return self._present(row)

    def set_status(self, user_id, endpoint_id, question_id,
                   expected_revision, status):
        row = self._required(user_id, endpoint_id, question_id)
        self._check_revision(row, expected_revision)
        if status not in QUESTION_STATUSES:
            raise BIError('saved question status is unsupported')
        row.status = status
        row.revision += 1
        row.updated_at = _now()
        self.repository.save_question(row, row.definition)
        self._changed(user_id, endpoint_id, row.id)
        return self._present(row)

    def move_question(self, user_id, endpoint_id, question_id,
                      expected_revision, collection_id):
        value = self.get_question(user_id, endpoint_id, question_id)[
            'definition']
        value['collection_id'] = collection_id
        return self.update_question(user_id, endpoint_id, question_id,
                                    expected_revision, value)

    def clone_question(self, user_id, endpoint_id, question_id, name):
        value = self.get_question(user_id, endpoint_id, question_id)[
            'definition']
        value['name'] = name
        return self.create_question(user_id, endpoint_id, value)

    def delete_question(self, user_id, endpoint_id, question_id,
                        expected_revision):
        row = self._required(user_id, endpoint_id, question_id)
        self._check_revision(row, expected_revision)
        for guard in self._question_guards:
            user = guard(user_id, endpoint_id, question_id)
            if user:
                raise BIError(
                    f'saved question is used by dashboard {user!r}')
        self.repository.delete_question(row)
        self._changed(user_id, endpoint_id, question_id)
        return {'question_id': question_id, 'deleted': True}

    def history(self, user_id, endpoint_id, question_id):
        row = self._required(user_id, endpoint_id, question_id)
        return [{'revision': item.revision, 'status': item.status,
                 'created_at': item.created_at.isoformat()}
                for item in self.repository.revisions(row.id)]

    def revision(self, user_id, endpoint_id, question_id, revision):
        row = self._required(user_id, endpoint_id, question_id)
        for item in self.repository.revisions(row.id):
            if item.revision == revision:
                return {'question_id': row.id, 'revision': revision,
                        'status': item.status,
                        'definition': json.loads(item.definition)}
        raise BIError('requested saved question revision is unavailable')

    # compilation ---------------------------------------------------------
    def compile(self, provider, user_id, endpoint_id, question_id=None,
                definition=None, parameters=None, revision=None,
                security_context=None):
        """Compile a stored (optionally pinned) or ad hoc question."""
        if question_id is not None:
            if revision is None:
                question = self.get_question(
                    user_id, endpoint_id, question_id)['definition']
            else:
                question = self.revision(
                    user_id, endpoint_id, question_id, revision)['definition']
        else:
            question = validate_question(definition)
        return self.compile_definition(
            provider, user_id, endpoint_id, question, parameters,
            security_context)

    def compile_definition(self, provider, user_id, endpoint_id, question,
                           parameters=None, security_context=None,
                           bind=False, extra_filters=()):
        """Compile a validated question.

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
                user_id, endpoint_id, question['semantic_model'])
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
        if style is None:
            return result
        sql = question['query']['sql']
        assert_read_only_select(sql)
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
                          exclude=None):
        if question['collection_id'] is not None:
            self._collection_row(user_id, question['collection_id'])
        reference = question['semantic_model']
        if reference is not None:
            try:
                self._semantic_definition(user_id, endpoint_id, reference)
            except SemanticModelError as exc:
                raise BIError(str(exc)) from exc
        for row in self.repository.questions(user_id, endpoint_id):
            if row.id != exclude and row.name == question['name'] and (
                    row.collection_id == question['collection_id']):
                raise BIError('saved question name already exists')

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

    def _required(self, user_id, endpoint_id, question_id):
        row = self.repository.get_question(user_id, endpoint_id, question_id)
        if row is None:
            raise BIError('saved question is unavailable')
        return row

    @staticmethod
    def _check_revision(row, expected):
        if isinstance(expected, bool) or not isinstance(expected, int):
            raise BIError('expected_revision must be an integer')
        if row.revision != expected:
            raise BIConflict('saved question revision has changed')

    @staticmethod
    def _summary(row):
        return {'question_id': row.id, 'name': row.name,
                'collection_id': row.collection_id, 'status': row.status,
                'revision': row.revision,
                'semantic_model_id': row.semantic_model_id,
                'updated_at': row.updated_at.isoformat()}

    @classmethod
    def _present(cls, row):
        return cls._summary(row) | {
            'definition': copy.deepcopy(json.loads(row.definition))}
