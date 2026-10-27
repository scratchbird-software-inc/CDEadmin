"""Native closed-file successors for a separately reviewed receiver restart.

This describes a collection boundary. It does not establish transaction finality,
a usable base backup, a complete recovery chain or a binary-log generation ID.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import zlib

from . import mysql_raw_binlog_archives as raw
from .mysql_binlog_archives import BinlogArchiveError
from .mysql_binlog_integrity import decoded

SUCCESSOR_SCOPE = 'native-closed-catalog-successor-after-verified-archive-copy'


def catalog_successor(captured, last_file):
    rows = captured['logs']
    index = next((i for i, row in enumerate(rows) if row['Log_name'] == last_file), None)
    if index is None or not rows[index].get('closed') or index + 1 >= len(rows):
        raise BinlogArchiveError('A native closed-log successor observation is unavailable')
    name = raw.options({'log_names': [rows[index + 1]['Log_name']]})['log_names'][0]
    return {'file': name, 'position': '4', 'scope': SUCCESSOR_SCOPE}


def _regular(stream):
    info = os.fstat(stream.fileno())
    if not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise BinlogArchiveError('Native checkpoint input is not a regular file')
    return tuple(getattr(info, key) for key in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def sealed_metadata(directory, artifact, source):
    directory = Path(directory)
    if directory.resolve() != directory or not directory.is_dir():
        raise BinlogArchiveError('Native checkpoint archive directory changed')
    selected = next((row for row in artifact['files'] if row['path'] == 'archive.json'), None)
    if selected is None or type(selected['size']) is not int or not 1 <= selected['size'] <= 4 * 1024 * 1024:
        raise BinlogArchiveError('Native checkpoint metadata is unavailable or exceeds its byte bound')
    with decoded(directory / 'archive.json', 'none') as stream:
        before = _regular(stream)
        payload = stream.read(selected['size'] + 1)
        if (_regular(stream) != before or len(payload) != selected['size'] or
                hashlib.sha256(payload).hexdigest() != selected['sha256']):
            raise BinlogArchiveError('Native checkpoint metadata changed after sealing')
    try:
        metadata = json.loads(payload)
    except (ValueError, UnicodeError):
        raise BinlogArchiveError('Native checkpoint metadata is invalid') from None
    if metadata.get('format') != 'mysql-raw-binlog@9.7.0' or metadata.get('source') != source:
        raise BinlogArchiveError('Native checkpoint source or archive format differs')
    logs = metadata.get('logs')
    if not isinstance(logs, list) or not logs or any(not isinstance(row,dict) or not isinstance(row.get('name'),str) for row in logs):
        raise BinlogArchiveError('Native checkpoint closed-file inventory is unavailable')
    raw.options({'log_names': [row['name'] for row in logs]})
    return metadata


def rotation_successor(path, file_row, checksum_algorithm):
    """Inspect only the bounded terminal rotation; full verification precedes use."""
    if checksum_algorithm not in {'crc32', 'native_none'}:
        raise BinlogArchiveError('Native checkpoint checksum format is unavailable')
    footer = 4 if checksum_algorithm == 'crc32' else 0
    with decoded(path, 'none') as stream:
        before = _regular(stream)
        size = before[2]
        if size != file_row['size'] or stream.read(4) != b'\xfebin':
            raise BinlogArchiveError('Native checkpoint closed-file length or magic changed')
        # A native rotation has the ordinary 19-byte v4 header, a uint64
        # position, a native basename (at most 255 UTF-8 bytes), and optional CRC.
        stream.seek(max(4, size - (19 + 8 + 255 + footer)))
        tail = stream.read(19 + 8 + 255 + footer)
        if _regular(stream) != before:
            raise BinlogArchiveError('Native checkpoint file changed during inspection')
    candidates = []
    for offset in range(max(0, len(tail) - (19 + 8 + footer))):
        event = tail[offset:]
        if event[4] != 4 or int.from_bytes(event[9:13], 'little') != len(event):
            continue
        if footer and zlib.crc32(event[:-4]) != int.from_bytes(event[-4:], 'little'):
            continue
        if int.from_bytes(event[19:27], 'little') != 4:
            continue
        try:
            name = event[27:len(event)-footer if footer else len(event)].decode('utf8')
            raw.options({'log_names': [name]})
        except (UnicodeError, BinlogArchiveError):
            continue
        candidates.append({'file': name, 'position': '4', 'rotation_sha256': hashlib.sha256(event).hexdigest()})
    if len(candidates) != 1:
        raise BinlogArchiveError('A unique complete native terminal rotation is unavailable')
    return candidates[0]


def successor(directory, artifact, source):
    metadata = sealed_metadata(directory, artifact, source)
    last = metadata['logs'][-1]
    name = last['name']
    if (artifact.get('end_at') or {}).get('file') != name:
        raise BinlogArchiveError('Native checkpoint end-file receipt differs')
    native = metadata.get('source_successor')
    if native is not None:
        if not isinstance(native, dict) or set(native) != {'file', 'position', 'scope'} or native['scope'] != SUCCESSOR_SCOPE or native['position'] != '4':
            raise BinlogArchiveError('Sealed native successor observation is invalid')
        raw.options({'log_names': [native['file']]})
        if native['file']==name:
            raise BinlogArchiveError('A sealed native successor cannot repeat its preceding file')
    if last.get('last_event_type') == 4:
        file_row = next((row for row in artifact['files'] if row['path'] == name), None)
        integrity = next((row for row in artifact['event_integrity'] if row['binlog'] == name), None)
        if file_row is None or integrity is None:
            raise BinlogArchiveError('Native checkpoint file receipt is unavailable')
        observed = rotation_successor(Path(directory) / name, file_row, integrity['checksum_algorithm'])
        if native is not None and observed['file'] != native['file']:
            raise BinlogArchiveError('Native terminal rotation and sealed catalog successor differ')
        authority = 'native-terminal-rotation'
    elif native is not None:
        observed = {key: native[key] for key in ('file', 'position')}
        authority = 'sealed-native-closed-catalog-successor'
    else:
        raise BinlogArchiveError('This archive has neither a terminal rotation nor a sealed native catalog successor')
    return {'last_file': name, 'next_file': observed['file'], 'position': observed['position'],
            'successor_authority': authority, **({'rotation_sha256': observed['rotation_sha256']} if 'rotation_sha256' in observed else {})}
