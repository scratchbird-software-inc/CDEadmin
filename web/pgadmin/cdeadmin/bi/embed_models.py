##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""The embed definition: validation and pure helpers.

An embed is the owner's declaration of what a signed token may do
(docs/en_US/bi_embedding.rst).  Everything not declared here is refused:
a parameter that is not listed cannot be set by the token or the viewer, a
claim that is not listed cannot be carried by a token, an origin that is not
listed cannot frame the page, and a download is off unless switched on.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from .embed_tokens import NAME, RESERVED_CLAIMS
from .models import BIError, _list, _map, _text

RESOURCE_TYPES = ('question', 'dashboard')
STATUSES = ('enabled', 'disabled', 'revoked')
MODES = ('locked', 'editable', 'hidden')
THEMES = ('light', 'dark', 'auto')
MIN_LIFETIME = 30
DEFAULT_LIFETIME = 600
MAX_ORIGINS = 20
MAX_PARAMETERS = 64
MAX_CLAIMS = 16

# An origin is a scheme, a lower-case host and an optional port: no path, no
# wildcard, no user information and no character that could end a CSP source.
_HOST = r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}'
_ORIGIN = re.compile(r'^https://' + _HOST + r'(?::[0-9]{1,5})?$')
_LOCAL = re.compile(r'^http://(?:localhost|127\.0\.0\.1)(?::[0-9]{1,5})?$')


def valid_origin(value):
    if not isinstance(value, str) or len(value) > 255 or not (
            _ORIGIN.match(value) or _LOCAL.match(value)):
        return False
    port = value.rsplit(':', 1)[-1]
    return not port.isdigit() or 1 <= int(port) <= 65535


def _int(value, label, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not (
            low <= value <= high):
        raise BIError(f'{label} must be an integer from {low} to {high}')
    return value


def _expiry(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise BIError('expires_at must be an ISO 8601 timestamp or null')
    try:
        moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise BIError('expires_at must be an ISO 8601 timestamp') from None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat()


def validate_embed(value, *, caps):
    """Validate and normalize an embed definition.

    ``caps`` carries the server limits: ``max_token_lifetime``,
    ``max_page_size``, ``max_rows``.  Whether the embed is allowed to enable
    downloads is decided by the service (server setting), not here.
    """
    item = _map(value, 'embed')
    resource = _map(item.get('resource'), 'embed.resource')
    kind = resource.get('type')
    if kind not in RESOURCE_TYPES:
        raise BIError('embed.resource.type must be question or dashboard')
    rid = _text(resource.get('id'), 'embed.resource.id', 36)
    revision = resource.get('revision')
    if revision is not None:
        revision = _int(revision, 'embed.resource.revision', 1, 10 ** 9)

    parameters, seen = [], set()
    for raw in _list(item.get('parameters', []), 'embed.parameters',
                     MAX_PARAMETERS):
        entry = _map(raw, 'embed.parameter')
        pid = entry.get('id')
        if not isinstance(pid, str) or not NAME.match(pid):
            raise BIError('embed.parameter.id is invalid')
        if pid in seen:
            raise BIError('embed parameters must be unique')
        if entry.get('mode') not in MODES:
            raise BIError('embed.parameter.mode must be locked, editable '
                          'or hidden')
        seen.add(pid)
        parameters.append({'id': pid, 'mode': entry['mode']})

    claims, seen = [], set()
    for raw in _list(item.get('claims', []), 'embed.claims', MAX_CLAIMS):
        entry = _map(raw, 'embed.claim')
        name = entry.get('name')
        if not isinstance(name, str) or not NAME.match(name):
            raise BIError('embed.claim.name is invalid')
        if name in RESERVED_CLAIMS:
            raise BIError(f'embed claim {name!r} is reserved for the '
                          'server')
        if name in seen:
            raise BIError('embed claims must be unique')
        seen.add(name)
        claims.append({'name': name,
                       'required': bool(entry.get('required', False))})

    origins = []
    for origin in _list(item.get('origins', []), 'embed.origins',
                        MAX_ORIGINS):
        if not valid_origin(origin):
            raise BIError(
                'embed origins must be exact origins such as '
                'https://app.example.com (no wildcard, path or credentials)')
        if origin not in origins:
            origins.append(origin)

    lifetime = _int(item.get('max_token_lifetime_seconds',
                             min(DEFAULT_LIFETIME, caps['max_token_lifetime'])),
                    'embed.max_token_lifetime_seconds', MIN_LIFETIME,
                    caps['max_token_lifetime'])
    display = _map(item.get('display', {}), 'embed.display')
    theme = display.get('theme', 'auto')
    if theme not in THEMES:
        raise BIError('embed.display.theme must be light, dark or auto')
    return {
        'name': _text(item.get('name'), 'embed.name', 256),
        'resource': {'type': kind, 'id': rid, 'revision': revision},
        'parameters': parameters,
        'claims': claims,
        'origins': origins,
        'max_token_lifetime_seconds': lifetime,
        'require_jti': bool(item.get('require_jti', False)),
        'expires_at': _expiry(item.get('expires_at')),
        'page_size': _int(item.get('page_size', min(50, caps['max_page_size'])),
                          'embed.page_size', 1, caps['max_page_size']),
        'max_rows': _int(item.get('max_rows', min(1000, caps['max_rows'])),
                         'embed.max_rows', 1, caps['max_rows']),
        'display': {
            'title': bool(display.get('title', True)),
            'theme': theme,
            'border': bool(display.get('border', True)),
            'download': bool(display.get('download', False)),
        },
    }


def parameter_modes(definition):
    return {p['id']: p['mode'] for p in definition['parameters']}


def claim_requirements(definition):
    return {c['name']: c['required'] for c in definition['claims']}


def frame_ancestors(definition):
    """The ``frame-ancestors`` source list: the declared origins or none."""
    origins = [o for o in definition.get('origins', []) if valid_origin(o)]
    return ' '.join(origins) if origins else "'none'"


def resource_parameters(kind, resource_definition):
    """``{id: descriptor}`` of what an embed may declare for a resource."""
    if kind == 'dashboard':
        return {f['id']: f for f in resource_definition['filters']}
    return {p['id']: p for p in resource_definition['parameters']}
