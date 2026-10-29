##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Delivery of BI alert messages and subscription snapshots.

Channels: an in-app notification record, SMTP and object storage through
the existing ``report_delivery`` adapters, and a signed webhook.  Every
recipient is authorized again at send time:

* a pgAdmin user needs ``view`` on the resource (and an active account);
* an external email address needs the server's external-recipient
  allow-list, and the alert owner needs ``manage`` on the resource;
* object storage and webhooks leave the application, so the owner needs
  ``manage`` as well.

A resource whose semantic model declares row or tenant filters delivers to
its owner only: the data was computed with the owner's row policy.
"""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from dataclasses import dataclass, field

from .alert_store import dumps
from .webhook import WebhookError

EVENT_NAMESPACE = uuid.UUID('6c1b1b6e-2d1f-4a52-9a4e-5f0b2c7b8a11')
DELIVERED, FAILED, UNKNOWN = 'delivered', 'failed', 'outcome_unknown'
SKIPPED = 'skipped'
MAX_WEBHOOK_ATTACHMENT_BYTES = 1024 * 1024


@dataclass
class Attachment:
    name: str          # card id or question name, for file names
    filename: str
    media_type: str
    format: str
    content: bytes
    result_id: str = ''


@dataclass
class Dispatch:
    alert: object
    definition: dict
    run_id: str
    title: str
    text: str
    message: dict
    attachments: list = field(default_factory=list)
    stamp: str = ''


def state_of(delivery_state):
    return {'delivered': DELIVERED, 'failed': FAILED,
            'outcome_unknown': UNKNOWN}.get(delivery_state, FAILED)


class AlertDelivery:
    def __init__(self, bi, repository, *, delivery=None, webhook=None,
                 external=None, policy_bound=None, clock=None,
                 notify_keep=200):
        self.bi = bi
        self.repository = repository
        self.delivery = delivery
        self.webhook = webhook
        external = external or {}
        self.external_addresses = frozenset(
            str(item).casefold() for item in external.get('addresses', ()))
        self.external_domains = frozenset(
            str(item).casefold().lstrip('@')
            for item in external.get('domains', ()))
        self.policy_bound = policy_bound or (lambda alert: False)
        self.clock = clock
        self.notify_keep = notify_keep

    # authorization -----------------------------------------------------------
    @property
    def external_configured(self):
        return bool(self.external_addresses or self.external_domains)

    def external_allowed(self, address):
        address = address.casefold()
        return address in self.external_addresses or (
            address.rsplit('@', 1)[-1] in self.external_domains)

    def user_code(self, alert, user_id):
        """``None`` when the user may receive this alert, else a code."""
        directory = self.bi.access.directory
        if directory.user(user_id) is None:
            return 'recipient_unavailable'
        if user_id != alert.user_id:
            if self.policy_bound(alert):
                return 'row_policy_bound'
        if self.bi.access.level(user_id, alert.resource_type,
                                alert.endpoint_id,
                                alert.resource_id) is None:
            return 'recipient_not_authorized'
        return None

    def owner_manages(self, alert):
        return self.bi.access.level(
            alert.user_id, alert.resource_type, alert.endpoint_id,
            alert.resource_id) == 'manage'

    def external_code(self, alert, address):
        if not self.owner_manages(alert):
            return 'owner_lacks_manage'
        if not self.external_allowed(address):
            return 'external_not_allowed'
        return None

    # planning and sending ---------------------------------------------------
    def run(self, dispatch, *, send):
        """Plan (``send=False``) or perform every delivery of a dispatch."""
        results = []
        for channel in dispatch.definition['channels']:
            handler = getattr(self, f"_{channel['type']}")
            results.extend(handler(dispatch, channel, send))
        return results

    def _key(self, dispatch, *parts):
        return str(uuid.uuid5(EVENT_NAMESPACE,
                              ':'.join((dispatch.run_id,) + parts)))

    # in-app ---------------------------------------------------------------
    def _in_app(self, dispatch, channel, send):
        out = []
        for recipient in channel['recipients']:
            uid = recipient['user_id']
            entry = {'channel': 'in_app', 'target': f'user:{uid}'}
            code = self.user_code(dispatch.alert, uid)
            if code:
                out.append({**entry, 'state': SKIPPED, 'code': code})
                continue
            if not send:
                out.append({**entry, 'state': 'would_send', 'code': None})
                continue
            alert = dispatch.alert
            row = self.repository.add_notification(
                user_id=uid, endpoint_id=alert.endpoint_id,
                alert_id=alert.id, kind=alert.kind,
                resource_type=alert.resource_type,
                resource_id=alert.resource_id, title=dispatch.title[:256],
                body=dispatch.text, data=dumps(dispatch.message),
                created_at=self._now(), read_at=None)
            self.repository.prune_notifications(
                uid, alert.endpoint_id, self.notify_keep)
            out.append({**entry, 'state': DELIVERED, 'code': None,
                        'delivery_id': row.id})
        return out

    # email ------------------------------------------------------------------
    def _email(self, dispatch, channel, send):
        out = []
        profile = self._profile(channel['profile_id'], 'smtp')
        for recipient in channel['recipients']:
            if recipient['type'] == 'user':
                uid = recipient['user_id']
                label = f'user:{uid}'
                code = self.user_code(dispatch.alert, uid)
                address = None if code else self.bi.access.directory.email(
                    uid)
                if not code and not address:
                    code = 'no_address'
            else:
                address = recipient['address']
                label = 'email:' + address.rsplit('@', 1)[1]
                code = self.external_code(dispatch.alert, address)
            entry = {'channel': 'email', 'target': label}
            if code:
                out.append({**entry, 'state': SKIPPED, 'code': code})
                continue
            if profile is None or self.delivery is None:
                out.append({**entry, 'state': SKIPPED,
                            'code': 'profile_unavailable'})
                continue
            if not send:
                out.append({**entry, 'state': 'would_send', 'code': None})
                continue
            out.extend(self._mail_one(dispatch, channel, address, entry))
        return out

    def _documents(self, dispatch):
        """``(filename, media_type, format, bytes, name)`` per attachment."""
        if dispatch.attachments:
            return [(a.filename, a.media_type, a.format, a.content,
                     a.result_id, a.name) for a in dispatch.attachments]
        body = json.dumps(dispatch.message, sort_keys=True, indent=2,
                          default=str).encode('utf-8')
        return [(f'cdeadmin-alert-{dispatch.alert.id[:8]}-{dispatch.stamp}'
                 '.json', 'application/json', 'json', body,
                 dispatch.run_id, 'alert')]

    def _mail_one(self, dispatch, channel, address, entry):
        out = []
        for filename, media_type, fmt, content, result_id, name in (
                self._documents(dispatch)):
            result = {**entry}
            try:
                delivered = self.delivery.deliver(
                    dispatch.alert.user_id, dispatch.alert.endpoint_id, {
                        'request_key': self._key(dispatch, 'email', address,
                                                 name),
                        'result_id': result_id or dispatch.run_id,
                        'format': fmt, 'profile_id': channel['profile_id'],
                        'target': {'recipients': [address]},
                        'content': content, 'filename': filename,
                        'media_type': media_type,
                        'subject': dispatch.title[:200].replace('\n', ' '),
                        'body': dispatch.text,
                    })
                result.update(state=state_of(delivered['state']),
                              code=None if delivered['state'] == 'delivered'
                              else (delivered.get('error_type') or
                                    'delivery_failed'),
                              delivery_id=delivered['occurrence_id'])
            except Exception as exc:
                result.update(state=FAILED, code=type(exc).__name__)
            out.append(result)
        return out

    # object storage ------------------------------------------------------------
    def _s3(self, dispatch, channel, send):
        entry = {'channel': 's3', 'target': 's3:' + channel['profile_id']}
        profile = self._profile(channel['profile_id'], 's3')
        if not self.owner_manages(dispatch.alert):
            return [{**entry, 'state': SKIPPED,
                     'code': 'owner_lacks_manage'}]
        if profile is None or self.delivery is None:
            return [{**entry, 'state': SKIPPED,
                     'code': 'profile_unavailable'}]
        if not send:
            return [{**entry, 'state': 'would_send', 'code': None}]
        out = []
        for filename, media_type, fmt, content, result_id, name in (
                self._documents(dispatch)):
            base = channel['object_name']
            suffix = '' if name in ('alert',) else f'-{name}'
            object_name = (f'{base}{suffix}-{dispatch.stamp}-'
                           f'{dispatch.run_id[:8]}.{fmt}')[:255]
            result = {**entry}
            try:
                delivered = self.delivery.deliver(
                    dispatch.alert.user_id, dispatch.alert.endpoint_id, {
                        'request_key': self._key(dispatch, 's3', name),
                        'result_id': result_id or dispatch.run_id,
                        'format': fmt, 'profile_id': channel['profile_id'],
                        'target': {'object_name': object_name},
                        'content': content, 'filename': filename,
                        'media_type': media_type,
                    })
                result.update(state=state_of(delivered['state']),
                              code=None if delivered['state'] == 'delivered'
                              else (delivered.get('error_type') or
                                    'delivery_failed'),
                              delivery_id=delivered['occurrence_id'])
            except Exception as exc:
                result.update(state=FAILED, code=type(exc).__name__)
            out.append(result)
        return out

    # webhook ------------------------------------------------------------------
    def _webhook(self, dispatch, channel, send):
        entry = {'channel': 'webhook', 'target': 'webhook'}
        if not self.owner_manages(dispatch.alert):
            return [{**entry, 'state': SKIPPED,
                     'code': 'owner_lacks_manage'}]
        if self.webhook is None:
            return [{**entry, 'state': SKIPPED,
                     'code': 'webhook_unavailable'}]
        try:
            host, _port, _target = self.webhook.check_url(channel['url'])
        except WebhookError as exc:
            return [{**entry, 'state': SKIPPED, 'code': exc.code}]
        entry['target'] = 'webhook:' + host
        if not send:
            return [{**entry, 'state': 'would_send', 'code': None}]
        payload = dict(dispatch.message)
        if dispatch.attachments:
            budget, items = MAX_WEBHOOK_ATTACHMENT_BYTES, []
            for item in dispatch.attachments:
                meta = {'name': item.name, 'filename': item.filename,
                        'media_type': item.media_type, 'format': item.format,
                        'bytes': len(item.content),
                        'sha256': hashlib.sha256(item.content).hexdigest()}
                if len(item.content) <= budget:
                    budget -= len(item.content)
                    meta['content_base64'] = base64.b64encode(
                        item.content).decode('ascii')
                else:
                    meta['content_omitted'] = 'over the webhook size limit'
                items.append(meta)
            payload['attachments'] = items
        delivery_id = self._key(dispatch, 'webhook')
        try:
            receipt = self.webhook.send(channel['url'], payload, delivery_id)
        except WebhookError as exc:
            return [{**entry, 'state': UNKNOWN if exc.outcome_unknown
                     else FAILED, 'code': exc.code}]
        return [{**entry, 'state': DELIVERED, 'code': None,
                 'delivery_id': delivery_id, 'status': receipt['status']}]

    # helpers --------------------------------------------------------------------
    def _profile(self, profile_id, kind):
        if self.delivery is None:
            return None
        try:
            profile = self.delivery.profiles.get(profile_id)
        except Exception:
            return None
        return profile if profile['kind'] == kind else None

    def _now(self):
        return self.clock().replace(tzinfo=None)
