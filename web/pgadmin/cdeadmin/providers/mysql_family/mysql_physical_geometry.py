"""Retained native system/undo geometry for private physical recovery.

Native SQL supplies original paths; native backup metadata supplies the system
file specifications. Only private utility inputs and destinations are remapped.
Opaque InnoDB pages and dictionary contents are never rewritten.
"""
import configparser
from pathlib import Path, PurePosixPath
import posixpath
import re

try:
    import _cdeadmin_physical_worker as physical
except ModuleNotFoundError:
    from . import mysql_physical_worker as physical

Refused=physical.Refused
FILE='.scratchrobin-storage.json'
STAGED='prepare-storage.json'
VARIABLES={'innodb_data_home_dir','innodb_data_file_path','innodb_undo_directory','innodb_directories'}
UNDO_NAMING='native-number-v1'
SYSTEM_NAMING='native-ordinal-v1'


def undo_number(space_id):
    """MySQL9.7 undo::id2num; the number survives native ID rotation."""
    if type(space_id) is not int or not 0xFFFFFFF0-127*400000<=space_id<=0xFFFFFFEF:
        raise Refused('Native undo space ID is unavailable or outside its reserved range')
    return (0xFFFFFFEF-space_id)%127+1


class ResolutionRequired(Refused):
    """Only the authenticated source filesystem can resolve this path."""


class UndoNamingRequired(ResolutionRequired):
    """Qualified native backup names must resolve duplicate source basenames."""


class SystemNamingRequired(ResolutionRequired):
    """Qualified native ordinals must resolve flattened system-file collisions."""


def absolute(value,base=None,*,resolve=None):
    value=physical.host.text(value);path=PurePosixPath(value)
    raw=path if path.is_absolute() else PurePosixPath(base)/path if base is not None else None
    descended=False
    for part in path.parts:
        if part=='..' and (path.is_absolute() or descended):
            if resolve is None:raise ResolutionRequired('Circular native storage paths require separately observed filesystem resolution')
            return resolve(str(raw))
        if part not in {'/','.', '..'}:descended=True
    if not path.is_absolute():
        if base is None:raise Refused('Native storage requires an observed absolute directory')
        path=PurePosixPath(base)/path
    return posixpath.normpath(str(path))


def home(value,datadir,*,resolve=None):
    if value in {None,'','.', './'}:return datadir
    return absolute(value,datadir,resolve=resolve)


def observed_resolution(raw,paths):
    effective=paths.get(raw)
    if not isinstance(effective,str) or not PurePosixPath(effective).is_absolute() or absolute(effective)!=effective:
        raise Refused('Retained native filesystem resolution is missing or incompatible')
    return effective


def configuration_matches(native,value):
    return (native.get('innodb_data_file_path')==value['variables']['innodb_data_file_path'] and
        home(native.get('innodb_undo_directory','./'),value['original_datadir'],
            resolve=lambda raw:observed_resolution(raw,value.get('resolved_paths',{})))==value['undo_home'])


def configuration(directory):
    parser=configparser.ConfigParser(interpolation=None,strict=False)
    parser.read_string(physical.metadata(directory/'backup-my.cnf'))
    if parser.sections()!=['mysqld'] or parser.defaults():raise Refused('Native storage backup configuration is unavailable')
    return dict(parser['mysqld'])


def system_spec(value,*,allow_duplicate_names=False):
    if not isinstance(value,str) or not value or len(value)>65536:raise Refused('Native system-file specification is unavailable')
    result=[]
    for item in value.split(';'):
        match=re.fullmatch(r'([^:;\x00\r\n]+):([0-9]+[KkMmGg]?(?::autoextend(?::max:[0-9]+[KkMmGg]?)?)?)((?:new)?raw)?',item)
        if not match:raise Refused('Native system-file geometry needs additional admission')
        name,suffix,raw=match.groups();path=PurePosixPath(name)
        if path.name in {'','.', '..'}:raise Refused('Native system-file identity is ambiguous')
        result.append({'native_name':name,'backup_name':path.name,'suffix':suffix+(raw or ''),
            **({'raw_mode':raw,'regular_suffix':suffix} if raw else {})})
    if len(result)>256 or not allow_duplicate_names and len({row['backup_name'] for row in result})!=len(result):
        raise Refused('Native flattened system-file identities are ambiguous')
    return result


def from_source(request,*,filesystem=False,observed_paths=None,undo_naming=None,system_naming=None):
    source=request.get('source_storage')
    if source is None:return None
    if system_naming not in {None,SYSTEM_NAMING}:raise Refused('Native system backup naming is incompatible')
    if undo_naming not in {None,UNDO_NAMING}:raise Refused('Native undo backup naming is incompatible')
    if not isinstance(source,dict) or set(source)!={'variables','files'}:
        raise Refused('Select exact native storage variables and file identities')
    values=source['variables'];files=source['files'];datadir=absolute(request['binding']['datadir'])
    if not isinstance(values,dict) or set(values)!=VARIABLES or any(
            v is None and key=='innodb_data_file_path' or v is not None and (not isinstance(v,str) or len(v)>65536)
            for key,v in values.items()):
        raise Refused('Native storage variables are unavailable')
    if not isinstance(files,list) or len(files)>4096:raise Refused('Native storage file inventory exceeds its bound')
    resolved={}
    if observed_paths is not None and (not isinstance(observed_paths,dict) or len(observed_paths)>8192):
        raise Refused('Retained filesystem resolution exceeds its bound')
    def resolve(raw):
        if filesystem:
            try:effective=str(Path(raw).resolve(strict=True))
            except (OSError,RuntimeError):raise Refused('Native storage filesystem resolution is unavailable') from None
        elif observed_paths is not None:
            effective=observed_resolution(raw,observed_paths)
        else:raise ResolutionRequired('Circular native storage paths require separately observed filesystem resolution')
        resolved[raw]=effective
        return effective
    data_home=home(values['innodb_data_home_dir'],datadir,resolve=resolve);undo_home=home(values['innodb_undo_directory'],datadir,resolve=resolve)
    system=[];undo=[];seen=set()
    for row in files:
        if not isinstance(row,dict) or not {'file_name','tablespace_name','file_type'}<=set(row) or set(row)-{'file_name','tablespace_name','file_type','undo_number'}:
            raise Refused('Native storage file identity is unavailable')
        # System FILES names use data-home. Relative undo FILES names already
        # contain their configured undo-directory prefix and use datadir.
        name=absolute(row['file_name'],datadir if row['file_type']=='UNDO LOG' else data_home,resolve=resolve)
        if name in seen:raise Refused('Native storage file identity is duplicated')
        seen.add(name)
        if row['file_type']=='UNDO LOG':
            number=row.get('undo_number')
            if 'undo_number' in row and (type(number) is not int or not 1<=number<=127):
                raise Refused('Native undo number is unavailable or outside its engine range')
            if undo_naming is not None and number is None:raise Refused('Observe native undo space IDs before using numbered backup names')
            undo.append({'source_file':name,'backup_name':PurePosixPath(name).name,
                'tablespace_name':physical.host.text(row['tablespace_name']),**({'undo_number':number} if number is not None else {})})
            if undo_naming is not None and number>2:undo[-1]['backup_name']='sr-undo-'+str(number)+'.ibu'
        elif row['file_type']=='TABLESPACE' and row['tablespace_name']=='innodb_system' and 'undo_number' not in row:system.append(name)
        else:raise Refused('Select only native system and undo file identities')
    specifications=system_spec(values['innodb_data_file_path'],allow_duplicate_names=True)
    for row in specifications:row['source_file']=absolute(row['native_name'],data_home,resolve=resolve)
    if {row['source_file'] for row in specifications}!=set(system):
        raise Refused('Native system-file specification differs from its observed catalog')
    numbers=[row['undo_number'] for row in undo if 'undo_number' in row]
    if len(numbers)!=len(set(numbers)):raise Refused('Native undo number is duplicated')
    if len({row['backup_name'] for row in undo})!=len(undo):
        if len(numbers)==len(undo):raise UndoNamingRequired('Duplicate native undo filenames require a qualified numbered backup layout')
        raise Refused('Native flattened undo-file identities are ambiguous')
    names=[row['backup_name'] for row in [*specifications,*undo]]
    numbered_system=len(names)!=len(set(names))
    if numbered_system:
        if system_naming is None:raise SystemNamingRequired('Native flattened system files require a qualified ordinal backup layout')
        for index,row in enumerate(specifications):row['backup_name']='sr-system-'+str(index)+'.ibdata'
        names=[row['backup_name'] for row in [*specifications,*undo]]
        if len(names)!=len(set(names)):raise Refused('Native system/undo backup namespaces overlap')
    directories=[]
    for value in (values['innodb_directories'] or '').split(';'):
        if not value:continue
        directory=absolute(value,datadir,resolve=resolve)
        if directory not in directories:directories.append(directory)
    if len(directories)>256:raise Refused('Native storage directory inventory exceeds its bound')
    result={'format':'mysql-9.7-storage-v1','original_datadir':datadir,'variables':values,
        'data_home':data_home,'undo_home':undo_home,'system_files':specifications,'undo_files':undo,'scan_directories':directories}
    numbered=undo_naming is not None and any(row['undo_number']>2 for row in undo)
    if numbered:result['undo_naming']=undo_naming
    if numbered_system:result['system_naming']=system_naming
    if observed_paths is not None and resolved!=observed_paths:
        raise Refused('Retained filesystem resolution contains unobserved native paths')
    if resolved:result.update(resolved_paths=resolved,catalog_files=files)
    external=any(not PurePosixPath(row['source_file']).is_relative_to(PurePosixPath(datadir)) for row in [*specifications,*undo])
    needed=numbered_system or numbered or external or bool(directories) or data_home!=datadir or undo_home!=datadir or any('/' in row['native_name'] or row.get('raw_mode') for row in specifications)
    if needed and request.get('isolate_external_paths') is not True:
        raise Refused('Review native storage-path isolation before using external system/undo files or retained scan roots')
    return result if needed else None


def capture(request,directory,*,reviewed=None):
    value=from_source(request,filesystem=True,undo_naming=reviewed.get('undo_naming') if reviewed else None,system_naming=reviewed.get('system_naming') if reviewed else None)
    if reviewed is not None and value!=reviewed:
        raise Refused('Native filesystem storage paths changed after their reviewed capture')
    if value is None:return None
    native=configuration(directory)
    if not configuration_matches(native,value):
        raise Refused('Native checkpoint storage geometry changed after its reviewed source capture')
    physical.host.save(directory/FILE,value)
    return audit(directory)


def audit(directory):
    path=directory/FILE
    if path.is_symlink():raise Refused('Retained native storage metadata cannot be a symbolic link')
    if not path.exists():return None
    value=physical.read_json(path)
    required={'format','original_datadir','variables','data_home','undo_home','system_files','undo_files','scan_directories'}
    if not isinstance(value,dict) or not required<=set(value) or set(value)-required-{'resolved_paths','catalog_files','undo_naming','system_naming'} or value['format']!='mysql-9.7-storage-v1':
        raise Refused('Retained native storage geometry is incompatible')
    if ('resolved_paths' in value)!=('catalog_files' in value):raise Refused('Retain original native catalog paths with their filesystem resolution')
    files=[{'file_name':row['source_file'],'tablespace_name':'innodb_system','file_type':'TABLESPACE'} for row in value['system_files']]
    files.extend({'file_name':row['source_file'],'tablespace_name':row['tablespace_name'],'file_type':'UNDO LOG',
        **({'undo_number':row['undo_number']} if 'undo_number' in row else {})} for row in value['undo_files'])
    # Preserve all original spellings; several aliases can name the same file.
    if 'catalog_files' in value:files=value['catalog_files']
    expected=from_source({'binding':{'datadir':value['original_datadir']},'source_storage':{'variables':value['variables'],'files':files},'isolate_external_paths':True},observed_paths=value.get('resolved_paths'),undo_naming=value.get('undo_naming'),system_naming=value.get('system_naming'))
    if expected!=value:raise Refused('Retained native storage paths differ from their original catalog/specification')
    native=configuration(directory)
    if not configuration_matches(native,value):
        raise Refused('Retained native storage differs from its backup configuration')
    expected={row['backup_name'] for row in value['undo_files']}
    observed=set()
    for path in directory.iterdir():
        if not path.is_file():continue
        name=path.name
        if name.endswith(('.delta','.meta')):name=name.rsplit('.',1)[0]
        if name.endswith('.ibu') or re.fullmatch(r'undo_[0-9]+',name):observed.add(name)
    if observed-expected:raise Refused('Native undo output contains unobserved source file identities; verified publication withheld')
    return value


def retained(directory,artifact,copied):
    """Bind runtime geometry to both original and verified copy-back bytes."""
    value=audit(directory)
    if value!=artifact.get('storage_geometry'):
        raise Refused('Retained native storage differs from its original artifact receipt')
    if value is not None:
        checksum=physical.host.file_hash(directory/FILE)
        if not any(row['path']==FILE and row['sha256']==checksum for row in artifact['files']):
            raise Refused('Retained native storage bytes changed after native preparation')
        try:copied_value=physical.read_json(copied/FILE)
        except (OSError,ValueError):raise Refused('Verified copy-back storage metadata is unavailable') from None
        if copied_value!=value:raise Refused('Verified copy-back storage differs from its prepared input')
    return value


def external_entries(value):
    if value is None:return [],[]
    datadir=PurePosixPath(value['original_datadir']);entries=[]
    for kind,rows in [('SYSTEM',value['system_files']),('UNDO_LOG',value['undo_files'])]:
        for row in rows:
            if not PurePosixPath(row['source_file']).is_relative_to(datadir):
                entries.append({'file_name':row['source_file'],'tablespace_name':row.get('tablespace_name',row['backup_name']),
                    'tablespace_type':'RAW_SYSTEM' if row.get('raw_mode') else kind})
    directories=sorted(set(value['scan_directories'])|{value['data_home'],value['undo_home']})
    return entries,[root for root in directories if not PurePosixPath(root).is_relative_to(datadir)]


def backup_arguments(value):
    return ['--scratchrobin-system-file-numbers'] if value and value.get('system_naming')==SYSTEM_NAMING else []


def prepare_arguments(directory,value):
    if value is None:return []
    return ['--innodb-data-file-path='+';'.join(row['backup_name']+':'+row.get('regular_suffix',row['suffix']) for row in value['system_files']),
        '--innodb-data-home-dir='+str(directory),'--innodb-undo-directory='+str(directory)]


def stage_prepare(directory,target,incremental=None):
    value=audit(target)
    newest=audit(incremental) if incremental is not None else None
    if newest is not None:
        if value is not None and any(newest[key]!=value[key] for key in ('original_datadir','system_files','data_home','undo_home')):
            raise Refused('Review a new full checkpoint after native system storage geometry changes')
        value=newest
    if value is not None:
        physical.host.save(directory/STAGED,value)
        (target/FILE).unlink(missing_ok=True)
    return value


def restore_prepare(directory,target):
    staged=directory/STAGED
    if staged.exists():
        if (target/FILE).exists():raise Refused('Native preparation unexpectedly replaced its retained storage geometry')
        staged.rename(target/FILE)
        audit(target)


def destination(source,target,context):
    source=PurePosixPath(source);datadir=PurePosixPath(context['original_datadir'])
    if source.is_relative_to(datadir):return target/str(source.relative_to(datadir))
    for row in context['plan']:
        root=PurePosixPath(row['source_root'])
        if source.is_relative_to(root):return target/row['relative_root']/str(source.relative_to(root))
    raise Refused('Native storage destination is absent from its reviewed private map')


def copy_back_arguments(directory,target,value,context):
    if value is None:return []
    return ['--innodb-data-file-path='+';'.join(str(destination(row['source_file'],target,context))+':'+row.get('regular_suffix',row['suffix']) for row in value['system_files']),
        '--innodb-undo-directory='+str(directory/'undo-copy-back')]+backup_arguments(value)


def copied_metadata(original,target):
    value=audit(original)
    if value is not None:
        if (target/FILE).exists():
            if physical.read_json(target/FILE)!=value:raise Refused('Native copy-back replaced its retained storage metadata')
        else:physical.host.save(target/FILE,value)
    return value


def finish_copy_back(directory,original,target,value,context):
    if value is None:return
    pool=directory/'undo-copy-back'
    expected={row['backup_name'] for row in value['undo_files']}
    if not pool.is_dir() or {p.name for p in pool.iterdir()}!=expected:
        raise Refused('Native copied undo files differ from the retained source inventory')
    for row in value['undo_files']:
        source=pool/row['backup_name'];output=destination(row['source_file'],target,context)
        if source.is_symlink() or not source.is_file() or output.exists():raise Refused('Native copied undo destination is ambiguous')
        output.parent.mkdir(mode=0o700,parents=True,exist_ok=True);source.rename(output)
    pool.rmdir()
    for row in context['plan']:
        path=target/row['relative_root']
        (path.parent if row.get('kind')=='file' else path).mkdir(mode=0o700,parents=True,exist_ok=True)
    (target/'external-data').mkdir(mode=0o700,exist_ok=True)
    for root in sorted(set(value['scan_directories'])|{value['data_home'],value['undo_home']}):
        path=destination(root,target,context);path.mkdir(mode=0o700,parents=True,exist_ok=True)
    copied_metadata(original,target)
