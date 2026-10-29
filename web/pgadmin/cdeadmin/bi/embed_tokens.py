##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Signed embed tokens (docs/en_US/bi_embedding.rst, "Tokens").

A token is a compact JWT-shaped string ``header.payload.signature`` signed
with HMAC-SHA256 under a per-embed secret that only the embedding site's
server and this server hold.  Everything here is pure and deny-by-default:

* The algorithm is pinned.  The header must be exactly ``alg=HS256`` with an
  optional ``typ=JWT`` and a mandatory ``kid``; there is no negotiation, so
  ``none``, a different case, an asymmetric algorithm used with the HMAC key
  ("algorithm confusion") and any extra header member (``jku``, ``jwk``,
  ``crit``...) are refused.
* Base64url is canonical (no padding, no foreign characters, no alternative
  encodings of the same bytes) and the JSON is strict (one object, no
  duplicate members, no NaN or Infinity), so two different strings never mean
  the same signed content.
* ``exp`` is mandatory and the remaining lifetime is capped by the embed's
  maximum; ``nbf`` and ``iat`` are checked; ``aud`` must be the embed id.
* The signature is compared in constant time, and the comparison is also run
  (against a dummy key) when the key identifier is unknown.

The functions raise ``EmbedTokenError`` with a short internal ``code``.  The
code is for the owner's diagnostic action and the tests; the public endpoints
never show it.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import math
import re

ALGORITHM = 'HS256'
MAX_TOKEN_BYTES = 4096
MIN_SECRET_BYTES = 32

KID = re.compile(r'^[A-Za-z0-9_-]{4,32}$')
JTI = re.compile(r'^[A-Za-z0-9._~-]{8,128}$')
NAME = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$')
_BASE64URL = re.compile(r'^[A-Za-z0-9_-]+$')

HEADER_MEMBERS = frozenset({'alg', 'typ', 'kid'})
PAYLOAD_MEMBERS = frozenset({
    'aud', 'exp', 'nbf', 'iat', 'jti', 'params', 'claims', 'iss', 'sub',
    'prv',
})
# security-context claim names the embedding site may never set: they name
# the server's own principal context
RESERVED_CLAIMS = frozenset({
    'user_id', 'principal', 'embed_id', 'embedding', 'roles_override',
})
MAX_MEMBERS = 32
MAX_LIST = 100
MAX_TEXT = 1024

# a dummy key keeps the verification path (and its timing) the same when the
# key identifier is unknown
_DUMMY_KEY = b'\x00' * MIN_SECRET_BYTES


class EmbedTokenError(Exception):
    """A token or claim set was refused; ``code`` is internal."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


# encoding ---------------------------------------------------------------
def b64u_encode(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


def b64u_decode(text):
    """Canonical unpadded base64url, or ``malformed``."""
    if not isinstance(text, str) or not text or not _BASE64URL.match(text):
        raise EmbedTokenError('malformed')
    if len(text) % 4 == 1:
        raise EmbedTokenError('malformed')
    try:
        raw = base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))
    except (binascii.Error, ValueError):
        raise EmbedTokenError('malformed') from None
    if b64u_encode(raw) != text:  # non-canonical trailing bits
        raise EmbedTokenError('malformed')
    return raw


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate member')
        result[key] = value
    return result


def _reject_constant(_name):
    raise ValueError('non-finite number')


def _load_object(raw):
    try:
        value = json.loads(raw.decode('utf-8'),
                           object_pairs_hook=_no_duplicates,
                           parse_constant=_reject_constant)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise EmbedTokenError('malformed') from None
    if not isinstance(value, dict):
        raise EmbedTokenError('malformed')
    return value


def _dump(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


# secrets ------------------------------------------------------------------
def secret_key(secret):
    """The HMAC key of a secret text (UTF-8, as JWT libraries use it)."""
    key = secret.encode('utf-8') if isinstance(secret, str) else bytes(secret)
    if len(key) < MIN_SECRET_BYTES:
        raise EmbedTokenError('weak_secret')
    return key


def _mac(key, signing_input):
    return hmac.new(key, signing_input, hashlib.sha256).digest()


# minting ------------------------------------------------------------------
def sign(secret, kid, payload):
    """A signed token.  The payload is checked only for being JSON."""
    if not isinstance(kid, str) or not KID.match(kid):
        raise EmbedTokenError('bad_kid')
    header = {'alg': ALGORITHM, 'typ': 'JWT', 'kid': kid}
    signing_input = (b64u_encode(_dump(header)) + '.' +
                     b64u_encode(_dump(payload))).encode('ascii')
    token = signing_input.decode('ascii') + '.' + b64u_encode(
        _mac(secret_key(secret), signing_input))
    if len(token.encode('ascii')) > MAX_TOKEN_BYTES:
        raise EmbedTokenError('too_large')
    return token


# parsing --------------------------------------------------------------------
class ParsedToken:
    """A syntactically valid token whose signature is NOT yet verified."""

    __slots__ = ('header', 'payload', 'signing_input', 'signature', 'kid')

    def __init__(self, header, payload, signing_input, signature):
        self.header, self.payload = header, payload
        self.signing_input, self.signature = signing_input, signature
        self.kid = header['kid']


def parse(token):
    """Split and strictly decode a token without trusting it."""
    if not isinstance(token, str) or not token or (
            len(token) > MAX_TOKEN_BYTES) or not token.isascii():
        raise EmbedTokenError('malformed')
    parts = token.split('.')
    if len(parts) != 3:
        raise EmbedTokenError('malformed')
    header_text, payload_text, signature_text = parts
    header = _load_object(b64u_decode(header_text))
    if set(header) - HEADER_MEMBERS or header.get('alg') != ALGORITHM:
        raise EmbedTokenError('algorithm')
    if 'typ' in header and header['typ'] != 'JWT':
        raise EmbedTokenError('algorithm')
    kid = header.get('kid')
    if not isinstance(kid, str) or not KID.match(kid):
        raise EmbedTokenError('bad_kid')
    payload = _load_object(b64u_decode(payload_text))
    signature = b64u_decode(signature_text)
    if len(signature) != hashlib.sha256().digest_size:
        raise EmbedTokenError('malformed')
    return ParsedToken(
        header, payload, (header_text + '.' + payload_text).encode('ascii'),
        signature)


def verify_signature(parsed, keys):
    """True when ``parsed`` was signed by the key its ``kid`` names.

    ``keys`` maps key identifiers to secret texts.  Exactly one MAC is
    computed and compared in constant time whether or not the identifier is
    known.
    """
    secret = keys.get(parsed.kid)
    try:
        key = secret_key(secret) if secret is not None else _DUMMY_KEY
    except EmbedTokenError:
        key = _DUMMY_KEY
        secret = None
    matches = hmac.compare_digest(_mac(key, parsed.signing_input),
                                  parsed.signature)
    return bool(matches and secret is not None)


# claims -----------------------------------------------------------------------
def _integer(value, code):
    if isinstance(value, bool) or not isinstance(value, int) or (
            value < 0 or value > 4102444800 * 10):
        raise EmbedTokenError(code)
    return value


def _scalar(value, code, *, text=MAX_TEXT):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EmbedTokenError(code)
        return value
    if isinstance(value, str) and len(value) <= text:
        return value
    raise EmbedTokenError(code)


def _value(value, code, *, text=MAX_TEXT):
    if isinstance(value, list):
        if len(value) > MAX_LIST:
            raise EmbedTokenError(code)
        return [_scalar(item, code, text=text) for item in value]
    return _scalar(value, code, text=text)


def _names(value, code):
    if not isinstance(value, dict) or len(value) > MAX_MEMBERS:
        raise EmbedTokenError(code)
    for key in value:
        if not isinstance(key, str) or not NAME.match(key):
            raise EmbedTokenError(code)
    return value


def check_claims(payload, *, embed_id, now, max_lifetime, leeway=15):
    """Validate a decoded payload; return the normalized claim set.

    ``now`` is epoch seconds.  ``max_lifetime`` caps the REMAINING lifetime
    (``exp - now``) and, when ``iat`` is present, ``exp - iat``.
    """
    if set(payload) - PAYLOAD_MEMBERS:
        raise EmbedTokenError('unknown_member')
    if payload.get('aud') != embed_id or not isinstance(embed_id, str):
        raise EmbedTokenError('audience')
    if 'exp' not in payload:
        raise EmbedTokenError('no_expiry')
    exp = _integer(payload['exp'], 'bad_expiry')
    if now >= exp:
        raise EmbedTokenError('expired')
    if exp - now > max_lifetime:
        raise EmbedTokenError('lifetime')
    nbf = payload.get('nbf')
    if nbf is not None:
        nbf = _integer(nbf, 'bad_nbf')
        if nbf > exp:
            raise EmbedTokenError('bad_nbf')
        if now + leeway < nbf:
            raise EmbedTokenError('not_yet_valid')
    iat = payload.get('iat')
    if iat is not None:
        iat = _integer(iat, 'bad_iat')
        if iat > now + leeway:
            raise EmbedTokenError('bad_iat')
        if exp <= iat or exp - iat > max_lifetime:
            raise EmbedTokenError('lifetime')
    jti = payload.get('jti')
    if jti is not None and (not isinstance(jti, str) or not JTI.match(jti)):
        raise EmbedTokenError('bad_jti')
    for member in ('iss', 'sub'):
        if member in payload and (not isinstance(payload[member], str) or
                                  len(payload[member]) > 128):
            raise EmbedTokenError('bad_' + member)
    preview = payload.get('prv', False)
    if not isinstance(preview, bool):
        raise EmbedTokenError('bad_prv')
    params = _names(payload.get('params', {}), 'bad_params')
    claims = _names(payload.get('claims', {}), 'bad_claims')
    if set(claims) & RESERVED_CLAIMS:
        raise EmbedTokenError('reserved_claim')
    return {
        'exp': exp, 'nbf': nbf, 'iat': iat, 'jti': jti, 'prv': preview,
        'params': {k: _value(v, 'bad_params') for k, v in params.items()},
        'claims': {k: _security_claim(v) for k, v in claims.items()},
    }


def _security_claim(value):
    """Claims drive row policy: strings, integers, booleans or lists of them."""
    if isinstance(value, float) or value is None:
        raise EmbedTokenError('bad_claims')
    checked = _value(value, 'bad_claims', text=256)
    if isinstance(checked, list) and any(
            isinstance(item, float) or item is None for item in checked):
        raise EmbedTokenError('bad_claims')
    return checked


def apply_policy(checked, *, parameters, claims):
    """Check a normalized claim set against the embed's declarations.

    ``parameters`` maps declared parameter ids to their modes; ``claims``
    maps declared claim names to ``required``.  Anything undeclared is
    refused, and a missing required claim is refused.
    """
    if set(checked['params']) - set(parameters):
        raise EmbedTokenError('undeclared_param')
    if set(checked['claims']) - set(claims):
        raise EmbedTokenError('undeclared_claim')
    for name, required in claims.items():
        if required and name not in checked['claims']:
            raise EmbedTokenError('missing_claim')
    return checked


def claims_digest(claims):
    """A stable fingerprint of a claim set (cache and principal scoping)."""
    return hashlib.sha256(_dump(claims)).hexdigest()
