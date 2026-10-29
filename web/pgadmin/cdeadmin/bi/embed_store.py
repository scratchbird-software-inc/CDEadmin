##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Persistence of embeds, signing secrets, one-time ids and view counters.

All timestamps are naive UTC, like the alert and scheduler tables.  The
in-memory twin used by the tests lives in ``tools/tests/bi_embed_harness.py``
and has the same contract.
"""

from __future__ import annotations

import uuid

from .models import BIError


class DatabaseEmbedRepository:
    def __init__(self):
        from pgadmin.model import (
            db, BIEmbed, BIEmbedJti, BIEmbedKey, BIEmbedStat,
        )
        self.db = db
        self.embed, self.key = BIEmbed, BIEmbedKey
        self.jti, self.stat = BIEmbedJti, BIEmbedStat

    # embeds ---------------------------------------------------------------
    def new(self, **values):
        return self.embed(**values)

    def add(self, row):
        from sqlalchemy.exc import IntegrityError
        try:
            self.db.session.add(row)
            self.db.session.commit()
        except IntegrityError as exc:
            self.db.session.rollback()
            raise BIError('an embed with this name already exists') from exc
        return row

    def get(self, embed_id):
        if not isinstance(embed_id, str) or len(embed_id) != 36:
            return None
        return self.embed.query.filter_by(id=embed_id).first()

    def list(self, endpoint_id, *, resource_type=None, resource_id=None,
             user_id=None):
        query = self.embed.query.filter_by(endpoint_id=endpoint_id)
        if resource_type is not None:
            query = query.filter_by(resource_type=resource_type)
        if resource_id is not None:
            query = query.filter_by(resource_id=resource_id)
        if user_id is not None:
            query = query.filter_by(user_id=user_id)
        return query.order_by(self.embed.name).all()

    def count(self, user_id, endpoint_id):
        return self.embed.query.filter_by(
            user_id=user_id, endpoint_id=endpoint_id).count()

    def save(self, row):
        from sqlalchemy.exc import IntegrityError
        try:
            self.db.session.add(row)
            self.db.session.commit()
        except IntegrityError as exc:
            self.db.session.rollback()
            raise BIError('an embed with this name already exists') from exc
        return row

    def _forget(self, embed_id):
        # counters and one-time ids hold no relationship; do not rely on
        # the engine enforcing the foreign key cascade
        self.jti.query.filter_by(embed_id=embed_id).delete()
        self.stat.query.filter_by(embed_id=embed_id).delete()

    def delete(self, row):
        self._forget(row.id)
        self.db.session.delete(row)
        self.db.session.commit()

    def purge_resource(self, resource_type, resource_id):
        """Drop every embed of a deleted resource; return their ids."""
        rows = self.embed.query.filter_by(
            resource_type=resource_type, resource_id=resource_id).all()
        ids = [row.id for row in rows]
        for row in rows:
            self._forget(row.id)
            self.db.session.delete(row)
        self.db.session.commit()
        return ids

    # keys -----------------------------------------------------------------
    def keys(self, embed_id):
        return self.key.query.filter_by(embed_id=embed_id).order_by(
            self.key.created_at).all()

    def install_key(self, embed_id, *, kid, key_id, encrypted_value, now):
        """Make a new key current; the old current becomes previous.

        The old previous key (if any) is dropped in the same transaction, so
        at most two keys ever verify.
        """
        try:
            rows = self.key.query.filter_by(embed_id=embed_id).all()
            for row in rows:
                if row.slot == 'previous':
                    self.db.session.delete(row)
            self.db.session.flush()
            for row in rows:
                if row.slot == 'current':
                    row.slot = 'previous'
            self.db.session.flush()
            self.db.session.add(self.key(
                id=str(uuid.uuid4()), embed_id=embed_id, kid=kid,
                slot='current', key_id=key_id,
                encrypted_value=encrypted_value, created_at=now))
            self.db.session.commit()
        except Exception:
            self.db.session.rollback()
            raise

    def drop_previous(self, embed_id):
        count = self.key.query.filter_by(
            embed_id=embed_id, slot='previous').delete()
        self.db.session.commit()
        return count

    def drop_keys(self, embed_id):
        count = self.key.query.filter_by(embed_id=embed_id).delete()
        self.db.session.commit()
        return count

    def save_keys(self):
        self.db.session.commit()

    def all_keys(self):
        return self.key.query.all()

    # one-time ids -----------------------------------------------------------
    def consume_jti(self, embed_id, jti, expires_at, now):
        """Record a token id; ``False`` when it was already used."""
        from sqlalchemy.exc import IntegrityError
        self.jti.query.filter(self.jti.expires_at < now).delete()
        try:
            self.db.session.add(self.jti(
                embed_id=embed_id, jti=jti, expires_at=expires_at))
            self.db.session.commit()
        except IntegrityError:
            self.db.session.rollback()
            return False
        return True

    def jti_consumed(self, embed_id, jti, now):
        return self.jti.query.filter(
            self.jti.embed_id == embed_id, self.jti.jti == jti,
            self.jti.expires_at >= now).first() is not None

    # counters ---------------------------------------------------------------
    def bump(self, embed_id, day, *, views=0, card_runs=0, errors=0):
        from sqlalchemy.exc import IntegrityError
        for _attempt in range(2):
            changed = self.stat.query.filter_by(
                embed_id=embed_id, day=day).update({
                    'views': self.stat.views + views,
                    'card_runs': self.stat.card_runs + card_runs,
                    'errors': self.stat.errors + errors},
                synchronize_session=False)
            if changed:
                self.db.session.commit()
                return
            try:
                self.db.session.add(self.stat(
                    embed_id=embed_id, day=day, views=views,
                    card_runs=card_runs, errors=errors))
                self.db.session.commit()
                return
            except IntegrityError:
                self.db.session.rollback()

    def stats(self, embed_id, since_day):
        rows = self.stat.query.filter(
            self.stat.embed_id == embed_id, self.stat.day >= since_day
        ).order_by(self.stat.day).all()
        return [{'day': r.day, 'views': r.views, 'card_runs': r.card_runs,
                 'errors': r.errors} for r in rows]


__all__ = ('DatabaseEmbedRepository',)
