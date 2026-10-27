"""Native manifest metadata integrity, streamed decoding and interruption."""
import hashlib
import io
import json
from pathlib import Path
import threading

import pytest

from pgadmin.cdeadmin.providers.postgresql.continuity import ContinuityError,manifest


def document():
    return {'PostgreSQL-Backup-Manifest-Version':2,'System-Identifier':18446744073709551615,
        'Files':[{'Path':'base/quoted ü😀','Size':3,'Checksum-Algorithm':'SHA256','Checksum':'ab'*32},
                 {'Path':'base/empty','Size':0}],
        'WAL-Ranges':[{'Timeline':1,'Start-LSN':'0/1000000','End-LSN':'0/2000000'}],
        'Manifest-Checksum':'cd'*32}


def test_streamed_native_manifest_preserves_uint64_unicode_raw_hash_and_checksum_scope(tmp_path,monkeypatch):
    raw=json.dumps(document(),ensure_ascii=False).encode()
    (tmp_path/'backup_manifest').write_bytes(raw)
    original=Path.open
    class ShortReads:
        def __init__(self,stream):self.stream=stream
        def read(self,size):
            assert size>0
            return self.stream.read(min(size,3))
        def __enter__(self):return self
        def __exit__(self,*_args):self.stream.close()
    monkeypatch.setattr(Path,'open',lambda path,*args,**kwargs:ShortReads(original(path,*args,**kwargs)))
    observed=manifest(tmp_path)
    assert observed['system_identifier']=='18446744073709551615'
    assert observed['manifest_sha256']==hashlib.sha256(raw).hexdigest()
    assert observed['files']==2 and observed['files_with_checksums']==1 and observed['files_without_checksums']==1
    assert observed['checksum_algorithms']==['SHA256']


@pytest.mark.parametrize('raw',[
    b'{"PostgreSQL-Backup-Manifest-Version":2,"System-Identifier":1,"Files":[],"WAL-Ranges":[],}',
    b'{"System-Identifier":1,"System-Identifier":2}', b'{"Files":[{},]}',
    b'{"System-Identifier":NaN}', b'{"Files":[null]}', b'{"Files":[{"Path":"\xff"}]}',
    b'{"System-Identifier":1}trailing', b'{"Files":[{"Path":"unfinished',
])
def test_malformed_manifest_never_becomes_a_native_identity(tmp_path,raw):
    (tmp_path/'backup_manifest').write_bytes(raw)
    with pytest.raises(ContinuityError):manifest(tmp_path)


def test_manifest_inspection_can_be_cancelled_before_and_during_streaming(tmp_path):
    data=document();data['Files']*=2000
    (tmp_path/'backup_manifest').write_text(json.dumps(data))
    signal=threading.Event();signal.set()
    with pytest.raises(ContinuityError,match='cancelled'):manifest(tmp_path,cancel_signal=signal)
    signal.clear();events=[]
    def progress(event):events.append(event);signal.set()
    with pytest.raises(ContinuityError,match='cancelled'):manifest(tmp_path,cancel_signal=signal,progress=progress)
    assert events and events[0]['manifest_bytes_read']<=65536
