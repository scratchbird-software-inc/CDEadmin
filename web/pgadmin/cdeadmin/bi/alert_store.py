##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Persistence of BI alerts, their history and in-app notifications.

Times are naive UTC, like the report scheduler's.  State columns are
updated in place (``update_state``) so an evaluation never overwrites a
definition edit or a mute made while it ran.
"""

from __future__ import annotations

import json
import uuid

from .models import BIError


class DatabaseAlertRepository:
    """SQLAlchemy store used in production."""

    def __init__(self):
        from pgadmin.model import (
            db, BIAlert, BIAlertEvent, BINotification,
        )
        self.db = db
        self.alert = BIAlert
        self.event = BIAlertEvent
        self.notification = BINotification

    # alerts ---------------------------------------------------------------
    def new(self, **values):
        return self.alert(**values)

    def add(self, row):
        from sqlalchemy.exc import IntegrityError
        try:
            self.db.session.add(row)
            self.db.session.commit()
        except IntegrityError as exc:
            self.db.session.rollback()
            raise BIError('an alert or subscription with this name already '
                          'exists') from exc
        return row

    def get(self, alert_id):
        if not isinstance(alert_id, str):
            return None
        return self.alert.query.filter_by(id=alert_id).first()

    def list(self, endpoint_id, *, resource_type=None, resource_id=None,
             user_id=None, kind=None):
        query = self.alert.query.filter_by(endpoint_id=endpoint_id)
        if resource_type is not None:
            query = query.filter_by(resource_type=resource_type)
        if resource_id is not None:
            query = query.filter_by(resource_id=resource_id)
        if user_id is not None:
            query = query.filter_by(user_id=user_id)
        if kind is not None:
            query = query.filter_by(kind=kind)
        return query.order_by(self.alert.name).all()

    def count(self, user_id, endpoint_id):
        return self.alert.query.filter_by(
            user_id=user_id, endpoint_id=endpoint_id).count()

    def save(self, row):
        from sqlalchemy.exc import IntegrityError
        try:
            self.db.session.add(row)
            self.db.session.commit()
        except IntegrityError as exc:
            self.db.session.rollback()
            raise BIError('an alert or subscription with this name already '
                          'exists') from exc
        return row

    def update_state(self, alert_id, **values):
        self.alert.query.filter_by(id=alert_id).update(
            values, synchronize_session='fetch')
        self.db.session.commit()

    def delete(self, row):
        self.db.session.delete(row)
        self.db.session.commit()

    def delegation(self, alert_id):
        from pgadmin.model import BIAlertDelegation
        return BIAlertDelegation.query.filter_by(alert_id=alert_id).first()

    # events ---------------------------------------------------------------
    def add_event(self, **values):
        row = self.event(id=str(uuid.uuid4()), **values)
        self.db.session.add(row)
        self.db.session.commit()
        return row

    def events(self, alert_id, limit=50):
        return self.event.query.filter_by(alert_id=alert_id).order_by(
            self.event.created_at.desc()).limit(limit).all()

    def prune_events(self, alert_id, keep):
        rows = self.event.query.filter_by(alert_id=alert_id).order_by(
            self.event.created_at.desc()).offset(keep).all()
        for row in rows:
            self.db.session.delete(row)
        if rows:
            self.db.session.commit()
        return len(rows)

    # notifications --------------------------------------------------------
    def add_notification(self, **values):
        row = self.notification(id=str(uuid.uuid4()), **values)
        self.db.session.add(row)
        self.db.session.commit()
        return row

    def notifications(self, user_id, endpoint_id, *, unread_only=False,
                      limit=50):
        query = self.notification.query.filter_by(
            user_id=user_id, endpoint_id=endpoint_id)
        if unread_only:
            query = query.filter(self.notification.read_at.is_(None))
        return query.order_by(self.notification.created_at.desc()).limit(
            limit).all()

    def unread_count(self, user_id, endpoint_id):
        return self.notification.query.filter_by(
            user_id=user_id, endpoint_id=endpoint_id).filter(
            self.notification.read_at.is_(None)).count()

    def mark_read(self, user_id, endpoint_id, ids, now):
        query = self.notification.query.filter_by(
            user_id=user_id, endpoint_id=endpoint_id).filter(
            self.notification.read_at.is_(None))
        if ids is not None:
            query = query.filter(self.notification.id.in_(list(ids)))
        count = query.update({'read_at': now}, synchronize_session=False)
        self.db.session.commit()
        return count

    def prune_notifications(self, user_id, endpoint_id, keep):
        rows = self.notification.query.filter_by(
            user_id=user_id, endpoint_id=endpoint_id).order_by(
            self.notification.created_at.desc()).offset(keep).all()
        for row in rows:
            self.db.session.delete(row)
        if rows:
            self.db.session.commit()
        return len(rows)


def dumps(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      default=str)
