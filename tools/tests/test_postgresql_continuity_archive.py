"""Native-file publication boundaries; synthetic headers are not recovery proof."""
import gzip
from pathlib import Path
import struct
import threading

import pytest

from pgadmin.cdeadmin.providers.postgresql.continuity import ContinuityError
from pgadmin.cdeadmin.providers.postgresql.continuity_archive import publish_file, publish_completed

NAME='000000020000000000000003'
SOURCE={'system_identifier':'18446744073709551615','wal_segment_bytes':1024**2,'wal_block_bytes':8192}


def native_shaped(*,endian='<',timeline=2,**changes):
    values={**SOURCE,**changes}
    header=bytearray(40)
    struct.pack_into(endian+'HHIQI',header,0,0xD118,2,timeline,3*1024**2,0)
    struct.pack_into(endian+'QII',header,24,int(values['system_identifier']),values['wal_segment_bytes'],values['wal_block_bytes'])
    return bytes(header)+b'\x00'*(1024**2-40)


@pytest.mark.parametrize('compression',['none','gzip','lz4'])
@pytest.mark.parametrize('endian',['<','>'])
@pytest.mark.parametrize('timeline',[1,2])
def test_publication_retains_exact_raw_identity_and_ancestor_page_timeline(tmp_path,compression,endian,timeline):
    archive=tmp_path/'archive';archive.mkdir()
    content=native_shaped(endian=endian,timeline=timeline)
    suffix={'none':'','gzip':'.gz','lz4':'.lz4'}[compression]
    path=tmp_path/(NAME+suffix)
    if compression=='none':encoded=content
    elif compression=='gzip':encoded=gzip.compress(content)
    else:
        import lz4.frame
        encoded=lz4.frame.compress(content)
    path.write_bytes(encoded)
    result=publish_file(path,archive,SOURCE)
    assert (archive/NAME).read_bytes()==content
    assert result['published'] and result['completed_native_file_observed']
    assert result['native_record_verification'] is False and result['page_timeline']==timeline
    assert path.read_bytes()==encoded
    repeated=publish_file(path,archive,SOURCE)
    assert repeated['published'] is False and repeated['sha256']==result['sha256']
    assert not list(tmp_path.glob('.scratchrobin-wal-*'))


@pytest.mark.parametrize('fault',['cluster','segment_size','block_size','magic','short','oversized','address','future_page_timeline','symlink','existing_different','cancelled'])
def test_publication_never_overwrites_or_admits_mismatched_native_identity(tmp_path,fault):
    archive=tmp_path/'archive';archive.mkdir()
    path=tmp_path/NAME;content=native_shaped()
    if fault=='cluster':content=native_shaped(system_identifier='1')
    if fault=='segment_size':content=native_shaped(wal_segment_bytes=2*1024**2)
    if fault=='block_size':content=native_shaped(wal_block_bytes=16384)
    if fault=='magic':content=b'xx'+content[2:]
    if fault=='short':content=content[:-1]
    if fault=='oversized':content+=b'x'
    if fault=='address':content=content[:8]+struct.pack('<Q',0)+content[16:]
    if fault=='future_page_timeline':content=native_shaped(timeline=3)
    path.write_bytes(content)
    if fault=='symlink':
        original=tmp_path/'original';path.rename(original);path.symlink_to(original)
    target=archive/NAME
    if fault=='existing_different':target.write_bytes(b'original archive bytes')
    signal=threading.Event()
    if fault=='cancelled':signal.set()
    with pytest.raises(ContinuityError):publish_file(path,archive,SOURCE,cancel_signal=signal)
    if fault=='existing_different':assert target.read_bytes()==b'original archive bytes'
    else:assert not target.exists()
    assert not list(tmp_path.glob('.scratchrobin-wal-*'))


def test_partial_native_files_are_never_published_and_completed_observations_are_reusable(tmp_path):
    archive=tmp_path/'archive';archive.mkdir();staging=tmp_path/'native';staging.mkdir()
    (staging/(NAME+'.partial')).write_bytes(b'in progress')
    (staging/(NAME+'.gz.partial')).write_bytes(b'in progress')
    (staging/'00000002.history.tmp').write_bytes(b'in progress')
    observed=set()
    assert publish_completed(staging,archive,SOURCE,observed=observed)==[]
    (staging/NAME).write_bytes(native_shaped())
    (staging/'00000002.history').write_bytes(b'1\t0/300000\towned timeline switch\n')
    results=publish_completed(staging,archive,SOURCE,observed=observed)
    assert {r['name'] for r in results}=={NAME,'00000002.history'}
    assert publish_completed(staging,archive,SOURCE,observed=observed)==[]
    assert {p.name for p in archive.iterdir()}=={NAME,'00000002.history'}


def test_non_native_files_and_linked_archives_are_refused(tmp_path):
    staging=tmp_path/'native';staging.mkdir();archive=tmp_path/'archive';archive.mkdir()
    (staging/'unexpected.conf').write_text('not native WAL')
    with pytest.raises(ContinuityError):publish_completed(staging,archive,SOURCE)
    path=tmp_path/NAME;path.write_bytes(native_shaped())
    link=tmp_path/'link';link.symlink_to(archive,target_is_directory=True)
    with pytest.raises(ContinuityError):publish_file(path,link,SOURCE)


def test_windows_publication_requests_exclusive_write_through_without_cross_volume_copy(monkeypatch,tmp_path):
    import ctypes
    from types import SimpleNamespace
    from pgadmin.cdeadmin.providers.postgresql import continuity_archive as module
    actual_os=module.os;calls=[]
    class Move:
        def __call__(self,*args):calls.append(args);return True
    move=Move()
    monkeypatch.setattr(ctypes,'WinDLL',lambda *_args,**_kwargs:SimpleNamespace(MoveFileExW=move),raising=False)
    monkeypatch.setattr(module,'os',SimpleNamespace(name='nt',fspath=actual_os.fspath))
    module._publish_exclusive(tmp_path/'source',tmp_path/'target')
    assert calls==[(str(tmp_path/'source'),str(tmp_path/'target'),8)]


def test_publication_polls_cancellation_between_large_file_chunks_and_removes_the_partial_output(tmp_path):
    archive=tmp_path/'archive';archive.mkdir();path=tmp_path/NAME
    source={**SOURCE,'wal_segment_bytes':2*1024**2}
    content=native_shaped(wal_segment_bytes=2*1024**2)
    content=content[:8]+struct.pack('<Q',3*2*1024**2)+content[16:]+b'\0'*1024**2
    path.write_bytes(content);signal=threading.Event();checks=[]
    def check():
        checks.append(True)
        if len(checks)==3:signal.set()
    with pytest.raises(ContinuityError,match='publication was cancelled'):
        publish_file(path,archive,source,cancel_signal=signal,check_cancel=check)
    assert len(checks)==3 and not list(archive.iterdir())
    assert path.read_bytes()==content and not list(tmp_path.glob('.scratchrobin-wal-*'))
