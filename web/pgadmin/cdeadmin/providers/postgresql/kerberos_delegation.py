"""Delegated Kerberos credential-cache admission, renewal & expiry enforcement (PG-AUDIT-COLLECTOR-02).

Implements binary MIT Kerberos Credential Cache (`FILE:` v4 `0x0504`) inspection,
private `0600` worker staging, renewable/keytab `kinit` ticket refresh, and strict
fail-closed refusal on expired or missing Kerberos tickets (zero password fallback).
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import threading
import time
import uuid

from ...operations.fileio import private_directory, private_file

_KRB_ENV_LOCK = threading.RLock()
CCACHE_V4_MAGIC = 0x0504


class KerberosDelegationError(ValueError):
    """Raised when a delegated Kerberos credential cache is invalid, expired, or unrenewable."""


class _BufferReader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def read(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise KerberosDelegationError('Truncated MIT Kerberos credential cache file')
        out = self.data[self.pos:self.pos + n]
        self.pos += n
        return out

    def u16(self) -> int:
        return struct.unpack('>H', self.read(2))[0]

    def u32(self) -> int:
        return struct.unpack('>I', self.read(4))[0]

    def i32(self) -> int:
        return struct.unpack('>i', self.read(4))[0]

    def counted_bytes(self) -> bytes:
        length = self.u32()
        if length > 1024 * 1024:
            raise KerberosDelegationError('Kerberos credential cache field exceeds 1 MiB bound')
        return self.read(length)

    def principal(self) -> str:
        _name_type = self.u32()
        num_components = self.u32()
        if num_components > 32:
            raise KerberosDelegationError('Invalid Kerberos principal component count')
        realm = self.counted_bytes().decode('utf8', 'replace')
        components = [self.counted_bytes().decode('utf8', 'replace') for _ in range(num_components)]
        return '/'.join(components) + ('@' + realm if realm else '')


def build_mit_ccache_v4(
    client_principal: str,
    server_principal: str,
    *,
    authtime: int,
    starttime: int,
    endtime: int,
    renew_till: int = 0,
    keyblock_enctype: int = 18,
    session_key: bytes | None = None,
    ticket_bytes: bytes = b'\x61\x03\x02\x01\x05',
    renewable_flag: bool = False,
) -> bytes:
    """Construct a standards-compliant MIT Kerberos v4 (0x0504) credential cache payload."""
    def _pack_counted(raw: bytes) -> bytes:
        return struct.pack('>I', len(raw)) + raw

    def _pack_principal(princ: str) -> bytes:
        if '@' in princ:
            lhs, realm = princ.rsplit('@', 1)
        else:
            lhs, realm = princ, 'EXAMPLE.COM'
        parts = lhs.split('/') if lhs else ['postgres']
        out = bytearray(struct.pack('>II', 1, len(parts)))
        out.extend(_pack_counted(realm.encode('utf8')))
        for p in parts:
            out.extend(_pack_counted(p.encode('utf8')))
        return bytes(out)

    skey = session_key or os.urandom(32)
    flags = 0x00800000 if renewable_flag else 0x40000000  # RENEWABLE vs FORWARDABLE
    buf = bytearray()
    # Header: magic 0x0504 + empty header tags length 0
    buf.extend(struct.pack('>HH', CCACHE_V4_MAGIC, 0))
    # Default client principal
    buf.extend(_pack_principal(client_principal))
    # Credential 1: client, server, keyblock (enctype u16 + counted key), times (4x u32), is_skey (u8), tktflags (u32), addrs (u32 0), authdata (u32 0), ticket, second_ticket
    buf.extend(_pack_principal(client_principal))
    buf.extend(_pack_principal(server_principal))
    buf.extend(struct.pack('>H', keyblock_enctype))
    buf.extend(_pack_counted(skey))
    buf.extend(struct.pack('>IIIIBI', authtime, starttime, endtime, renew_till, 0, flags))
    buf.extend(struct.pack('>II', 0, 0))
    buf.extend(_pack_counted(ticket_bytes))
    buf.extend(_pack_counted(b''))
    return bytes(buf)


def inspect_ccache(ccache_path: str | Path, *, now: float | None = None) -> dict:
    """Validate and inspect a local `FILE:` MIT Kerberos v4 credential cache without exposing key material."""
    raw_str = str(ccache_path)
    if raw_str.startswith('FILE:'):
        raw_str = raw_str[5:]
    path = Path(raw_str)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise KerberosDelegationError('Kerberos credential cache must be an absolute non-symlink regular file')
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_size > 4 * 1024 * 1024:
        raise KerberosDelegationError('Kerberos credential cache exceeds 4 MiB or is non-regular')
    if os.name != 'nt' and (st.st_mode & 0o077) != 0:
        raise KerberosDelegationError('Kerberos credential cache must have owner-only 0600 permissions')

    raw = path.read_bytes()
    sha256 = hashlib.sha256(raw).hexdigest()
    rdr = _BufferReader(raw)
    magic = rdr.u16()
    if magic != CCACHE_V4_MAGIC:
        raise KerberosDelegationError(f'Unsupported Kerberos credential cache format 0x{magic:04x} (expected MIT v4 0x0504)')
    header_len = rdr.u16()
    rdr.read(header_len)
    default_principal = rdr.principal()

    credentials = []
    while rdr.pos < len(raw):
        c_princ = rdr.principal()
        s_princ = rdr.principal()
        enctype = rdr.u16()
        _key = rdr.counted_bytes()
        authtime = rdr.u32()
        starttime = rdr.u32()
        endtime = rdr.u32()
        renew_till = rdr.u32()
        _is_skey = rdr.read(1)
        tkt_flags = rdr.u32()
        num_addrs = rdr.u32()
        for _ in range(num_addrs):
            rdr.u16()
            rdr.counted_bytes()
        num_auth = rdr.u32()
        for _ in range(num_auth):
            rdr.u16()
            rdr.counted_bytes()
        _ticket = rdr.counted_bytes()
        _second_ticket = rdr.counted_bytes()
        if s_princ.startswith('krb5_ccache_conf_data/'):
            continue
        credentials.append({
            'client_principal': c_princ,
            'service_principal': s_princ,
            'enctype': enctype,
            'authtime': authtime,
            'starttime': starttime,
            'endtime': endtime,
            'renew_till': renew_till,
            'renewable': bool(tkt_flags & 0x00800000) and renew_till > endtime,
        })

    if not credentials:
        raise KerberosDelegationError('Kerberos credential cache contains no service or TGT credentials')

    current_ts = float(now if now is not None else time.time())
    valid_creds = [c for c in credentials if c['endtime'] > current_ts]
    expired = len(valid_creds) == 0
    earliest_expiry = min(c['endtime'] for c in valid_creds) if valid_creds else max(c['endtime'] for c in credentials)
    max_renew_till = max((c['renew_till'] for c in credentials), default=0)
    renewable = any(c['renewable'] and c['renew_till'] > current_ts for c in credentials)

    return {
        'ccache_path': str(path),
        'ccache_sha256': sha256,
        'format': 'MIT-ccache-v4',
        'default_principal': default_principal,
        'credential_count': len(credentials),
        'expired': expired,
        'expires_at': earliest_expiry,
        'remaining_seconds': max(0.0, round(earliest_expiry - current_ts, 3)),
        'renewable': renewable,
        'renew_until': max_renew_till if max_renew_till > 0 else None,
    }


def stage_isolated_ccache(source_ccache: str | Path, staging_root: Path, *, now: float | None = None) -> dict:
    """Verify an unexpired ccache and copy it into an isolated 0600 collector file."""
    info = inspect_ccache(source_ccache, now=now)
    if info['expired']:
        raise KerberosDelegationError(
            f"Kerberos delegated credential cache for {info['default_principal']} expired at {info['expires_at']}; "
            'password fallback is forbidden'
        )
    staging_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_directory(staging_root)
    staged_path = staging_root / f'krb5cc_collector_{uuid.uuid4().hex}'
    src = Path(info['ccache_path'])
    shutil.copyfile(src, staged_path)
    private_file(staged_path)
    reverified = inspect_ccache(staged_path, now=now)
    if reverified['ccache_sha256'] != info['ccache_sha256']:
        staged_path.unlink(missing_ok=True)
        raise KerberosDelegationError('Kerberos credential cache changed during isolated staging')
    return {
        **reverified,
        'krb5ccname': f'FILE:{staged_path}',
        'password_fallback_allowed': False,
    }


def renew_ccache(
    staged_ccache: str | Path,
    *,
    keytab_path: str | Path | None = None,
    principal: str | None = None,
    kinit_binary: str | None = None,
) -> dict:
    """Renew an isolated Kerberos credential cache via `kinit -R` or an explicit keytab."""
    raw_str = str(staged_ccache)
    path = Path(raw_str[5:] if raw_str.startswith('FILE:') else raw_str)
    before = inspect_ccache(path)
    kinit = kinit_binary or shutil.which('kinit')
    if not kinit:
        raise KerberosDelegationError('Kerberos kinit utility is unavailable on the application host for ticket renewal')
    if keytab_path is not None:
        kt = Path(keytab_path)
        if not kt.is_absolute() or kt.is_symlink() or not kt.is_file():
            raise KerberosDelegationError('Kerberos keytab must be an absolute non-symlink regular file')
        if os.name != 'nt' and (kt.lstat().st_mode & 0o077) != 0:
            raise KerberosDelegationError('Kerberos keytab must have owner-only 0600 permissions')
        target_princ = principal or before['default_principal']
        cmd = [kinit, '-k', '-t', str(kt), '-c', f'FILE:{path}', target_princ]
    else:
        if not before['renewable']:
            raise KerberosDelegationError('Kerberos ticket is not renewable and no keytab was supplied')
        cmd = [kinit, '-R', '-c', f'FILE:{path}']
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
    if proc.returncode != 0:
        raise KerberosDelegationError(
            f'Kerberos ticket renewal failed (rc={proc.returncode}): {(proc.stderr or proc.stdout).strip()[:256]}'
        )
    private_file(path)
    after = inspect_ccache(path)
    if after['expired']:
        raise KerberosDelegationError('Kerberos ticket remained expired after renewal')
    return {
        **after,
        'renewed': True,
        'previous_expires_at': before['expires_at'],
    }


@contextmanager
def scoped_krb5ccname(ccache_path: str | Path, *, now: float | None = None):
    """Enforce non-expired Kerberos ccache and bind KRB5CCNAME under lock during libpq connect."""
    info = inspect_ccache(ccache_path, now=now)
    if info['expired']:
        raise KerberosDelegationError(
            f"Kerberos delegated ticket for {info['default_principal']} is expired; collector refuses connection without password fallback"
        )
    with _KRB_ENV_LOCK:
        previous = os.environ.get('KRB5CCNAME')
        os.environ['KRB5CCNAME'] = f"FILE:{info['ccache_path']}"
        try:
            yield info
        finally:
            if previous is None:
                os.environ.pop('KRB5CCNAME', None)
            else:
                os.environ['KRB5CCNAME'] = previous
