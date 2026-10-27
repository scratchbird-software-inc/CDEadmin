"""Native TAR decoding boundaries and independently remapped materialization."""
import gzip
import io
import tarfile
import threading

import pytest

from pgadmin.cdeadmin.providers.postgresql.continuity import ContinuityError
from pgadmin.cdeadmin.providers.postgresql.continuity_tar import materialize,parse_tablespace_map,tablespace_observation


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


def test_native_map_preserves_escaped_newlines_backslashes_leading_spaces_and_exact_oids():
    data=b'42  /source \\\n\\\r\\\\ Unicode \xc3\xa9\n4294967295 C:\\\\source path\r\n'
    values=parse_tablespace_map(data)
    assert values==[{'oid':42,'location':' /source \n\r\\ Unicode é','name_observed':False},
        {'oid':4294967295,'location':'C:\\source path','name_observed':False}]


@pytest.mark.parametrize('data',[b'42 /unterminated',b'42 /trailing\\',b'0 /zero\n',b'01 /zero\n',
    b'4294967296 /overflow\n',b'42 /first\n42 /duplicate\n',b'42 \n',b'42 /nul\0byte\n',b'42 /invalid\xff\n'])
def test_invalid_or_lossy_native_map_is_not_inferred(data):
    with pytest.raises(ContinuityError):parse_tablespace_map(data)


@pytest.mark.parametrize('suffix',['.tar','.tar.gz','.tar.lz4','.tar.zst'])
def test_tablespace_observation_uses_verified_artifact_metadata_without_opening_source_paths(tmp_path,suffix):
    source=tmp_path/'source';source.mkdir()
    path='/never-open-source/space \n\\ é'
    encoded=path.replace('\\','\\\\').replace('\n','\\\n').encode()
    data=b'42 '+encoded+b'\n'
    (source/('base'+suffix)).write_bytes(encode(tar_bytes([('backup_label',b'label'),('tablespace_map',data),('file',b'body')]),suffix))
    (source/('42'+suffix)).write_bytes(encode(tar_bytes([('file',b'tablespace')]),suffix))
    (source/'backup_manifest').write_bytes(b'verification is a separate native receipt')
    result=tablespace_observation(source,progress=lambda _event:None,cancel_signal=threading.Event())
    assert result['tablespaces']==[{'oid':42,'location':path,'name_observed':False}]
    assert result['source_host_paths_opened'] is False and result['native_names_observed'] is False
    assert result['tablespace_catalog_observed'] is False


@pytest.mark.parametrize('fault',['missing-map','missing-archive','duplicate-archive','cancel','linked-map'])
def test_tablespace_observation_refuses_missing_or_unsafe_native_facts(tmp_path,fault):
    source=tmp_path/'source';source.mkdir();data=b'42 /source\n'
    entries=[('backup_label',b'label')]
    if fault=='linked-map':
        link=tarfile.TarInfo('tablespace_map');link.type=tarfile.SYMTYPE;link.linkname='/source'
        entries.append(('tablespace_map',link))
    elif fault!='missing-map':entries.append(('tablespace_map',data))
    (source/'base.tar').write_bytes(tar_bytes(entries))
    if fault!='missing-archive':(source/'42.tar').write_bytes(tar_bytes([]))
    if fault=='duplicate-archive':(source/'42.tar.gz').write_bytes(encode(tar_bytes([]),'.tar.gz'))
    signal=threading.Event()
    if fault=='cancel':signal.set()
    with pytest.raises(ContinuityError):tablespace_observation(source,progress=lambda _event:None,cancel_signal=signal)


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
