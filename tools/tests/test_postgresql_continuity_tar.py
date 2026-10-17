"""Native TAR decoding boundaries and independently remapped materialization."""
import gzip
import io
import tarfile
import threading

import pytest

from pgadmin.cdeadmin.providers.postgresql.continuity import ContinuityError
from pgadmin.cdeadmin.providers.postgresql.continuity_tar import materialize


def tar_bytes(entries):
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w') as archive:
        for name,value in entries:
            member=tarfile.TarInfo(name)
            if value is None:member.type=tarfile.DIRTYPE;archive.addfile(member)
            elif isinstance(value,tarfile.TarInfo):archive.addfile(value)
            else:member.size=len(value);archive.addfile(member,io.BytesIO(value))
    return stream.getvalue()


def encode(data,suffix):
    if suffix=='.tar.gz':return gzip.compress(b'')+gzip.compress(data)
    if suffix=='.tar.lz4':
        import lz4.frame
        return lz4.frame.compress(b'')+lz4.frame.compress(data)
    if suffix=='.tar.zst':
        from compression.zstd import compress
        return compress(b'')+compress(data)
    return data


@pytest.mark.parametrize('suffix',['.tar','.tar.gz','.tar.lz4','.tar.zst'])
def test_native_archive_codecs_read_concatenated_frames_and_remap_tablespaces(tmp_path,suffix):
    source=tmp_path/'source';source.mkdir()
    inputs={'base':[('pg_tblspc/',None),('pg_wal/',None),('./pg_wal/archive_status/',None),('./pg_wal/summaries/',None),('global/',None),('global/pg_control',b'control')],
            '42':[('PG_18_native/',None),('PG_18_native/table',b'tablespace')],
            'pg_wal':[('000000010000000000000001',b'wal')]}
    for prefix,entries in inputs.items():(source/(prefix+suffix)).write_bytes(encode(tar_bytes(entries),suffix))
    (source/'backup_manifest').write_bytes(b'native manifest is verified separately')
    before={path.name:path.read_bytes() for path in source.iterdir()}
    job=tmp_path/'job';job.mkdir();target=job/'recovered-clone'
    result=materialize(source,target,[{'oid':42,'location':'/original'}],'stream',progress=lambda _event:None,cancel_signal=threading.Event())
    assert result['independent_byte_copy'] and result['source_format']=='tar'
    if suffix!='.tar':assert result['decoders']
    assert (target/'global/pg_control').read_bytes()==b'control'
    assert (target/'pg_wal/000000010000000000000001').read_bytes()==b'wal'
    assert (target/'pg_tblspc/42').resolve()==job/'tablespaces/42'
    assert (target/'pg_tblspc/42/PG_18_native/table').read_bytes()==b'tablespace'
    assert (target/'backup_manifest').read_bytes()==before['backup_manifest']
    assert {path.name:path.read_bytes() for path in source.iterdir()}==before


@pytest.mark.parametrize('fault',['traversal','absolute','symlink','hardlink','duplicate','trailer','checksum','missing-wal','cancel'])
def test_unsafe_incomplete_or_corrupt_archives_do_not_qualify_materialization(tmp_path,fault):
    source=tmp_path/'source';source.mkdir();suffix='.tar'
    entries=[('safe',b'input')]
    if fault in {'traversal','absolute'}:entries=[('../escape' if fault=='traversal' else '/absolute',b'refused')]
    if fault in {'symlink','hardlink'}:
        link=tarfile.TarInfo('link');link.type=tarfile.SYMTYPE if fault=='symlink' else tarfile.LNKTYPE;link.linkname='../escape'
        entries=[('link',link)]
    if fault=='duplicate':entries*=2
    data=tar_bytes(entries)
    if fault=='trailer':data+=b'unexpected payload'
    if fault=='checksum':suffix='.tar.gz';data=encode(data,suffix);data=data[:-8]+b'\xff'*8
    (source/('base'+suffix)).write_bytes(data)
    (source/'backup_manifest').write_bytes(b'manifest')
    signal=threading.Event()
    def progress(_event):
        if fault=='cancel':signal.set()
    job=tmp_path/'job';job.mkdir()
    with pytest.raises(ContinuityError):
        materialize(source,job/'copy',[],'stream' if fault=='missing-wal' else 'fetch',progress=progress,cancel_signal=signal)
    assert not (tmp_path/'escape').exists()
    assert (source/('base'+suffix)).read_bytes()==data
