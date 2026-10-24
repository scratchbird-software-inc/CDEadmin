"""Private physical-artifact removal; original native outcomes stay unchanged."""
from contextlib import contextmanager
import os
import re
from pathlib import Path
import shutil
import stat
import time

try:
    import _cdeadmin_physical_worker as physical
except ModuleNotFoundError:
    from . import mysql_physical_worker as physical

host=physical.host
Refused=physical.Refused


@contextmanager
def admission(root):
    import fcntl
    root.mkdir(parents=True,exist_ok=True,mode=0o700);host.private_directory(root)
    descriptor=os.open(root/'.physical-admission.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        info=os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid():raise Refused('Physical workspace admission identity differs')
        os.fchmod(descriptor,0o600);fcntl.flock(descriptor,fcntl.LOCK_EX)
        try:yield
        finally:fcntl.flock(descriptor,fcntl.LOCK_UN)
    finally:os.close(descriptor)


def node(path,*,hash_file=True):
    try:info=path.lstat()
    except FileNotFoundError:return None
    value={'device':info.st_dev,'inode':info.st_ino}
    if stat.S_ISDIR(info.st_mode):return {**value,'kind':'directory'}
    if stat.S_ISREG(info.st_mode):
        return {**value,'kind':'file','size':info.st_size,'modified_ns':info.st_mtime_ns,
            **({'sha256':host.file_hash(path)} if hash_file else {'changed_ns':info.st_ctime_ns})}
    raise Refused('Physical retention accepts only regular files and directories')


def tree(path):
    identity=node(path)
    if identity is None:return None
    entries={};pending=[path] if identity['kind']=='directory' else []
    while pending:
        directory=pending.pop()
        for child in directory.iterdir():
            # Native backup files can be terabytes. Inode/size/mtime/ctime
            # admission detects replacement or writes without rereading data.
            # Root replay files retain hashes across their rename ctime change.
            value=node(child,hash_file=False)
            if value is None:raise Refused('Physical retention files changed during inspection')
            if value['device']!=identity['device']:raise Refused('Physical retention cannot cross a filesystem mount')
            entries[child.relative_to(path).as_posix()]=value
            if len(entries)>physical.MAX_FILES:raise Refused('Physical retention manifest exceeds its file bound')
            if value['kind']=='directory':pending.append(child)
    return {'identity':identity,'entries':entries}


def stopped(directory,request):
    original=physical.read_json(directory/'request.json')
    value=physical.read_json(directory/'result.json')
    if original['job_id']!=request['job_id'] or original['input_digest']!=request['input_digest'] or value.get('input_digest')!=request['input_digest']:
        raise Refused('Physical retention original receipt differs')
    if original['phase']=='recover':value=physical.recovery_module().observe(directory,value,'status')
    supervisor_ended=value.get('supervisor_finished') is True or (original['phase']=='recover' and
        value.get('supervisor_process_live') is False and value.get('runtime_process_live') is False)
    if (value.get('process_termination_confirmed') is not True or value.get('credential_cleanup_confirmed') is not True or
            not supervisor_ended or original.get('database_credentials') is not None or
            value.get('supervisor_process_live') is True or value.get('runtime_process_live') is True or
            value.get('process_presence_unknown') is True):
        raise Refused('Independently confirm original native termination and credential cleanup before retention')
    return original,value


def dependencies(root,selected):
    children=[];count=0
    for directory in root.iterdir():
        if not directory.is_dir():continue
        try:physical.job_id(directory.name)
        except ValueError:continue
        count+=1
        if count>10000:raise Refused('Physical dependency inventory exceeds 10000 jobs')
        if directory.is_symlink():raise Refused('Physical dependency inventory contains a symbolic link')
        try:record=physical.read_json(directory/'request.json')
        except (OSError,ValueError):raise Refused('Physical dependency inventory contains an unobserved original job') from None
        if record.get('job_id')!=directory.name:raise Refused('Physical dependency job identity differs')
        intent=directory/'retention-intent.json'
        removed=intent.exists() and physical.read_json(intent).get('state')=='removed'
        if selected in (record.get('input_job_id'),record.get('incremental_job_id')) and not removed:children.append(directory.name)
    return sorted(children)


def unmounted(paths):
    mounts=[]
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        mounts.append(Path(re.sub(r'\\([0-7]{3})',lambda match:chr(int(match[1],8)),line.split()[4])))
    if any(mount.is_relative_to(path) for mount in mounts for path in paths):
        raise Refused('Physical retention cannot traverse a mounted artifact or bind mount')


def snapshot(directory):
    names=['artifact','runtime-data','delta-input',*[f'recovery-{name}.pem' for name in ('ssl_ca','ssl_cert','ssl_key')]]
    names += sorted(p.name for p in directory.glob('recovery-bin.*') if
        p.name=='recovery-bin.index' or re.fullmatch(r'recovery-bin\.\d{6,}',p.name))
    unmounted([directory/name for name in names])
    result={name:value for name in names if (value:=tree(directory/name)) is not None}
    if len(__import__('json').dumps(result).encode())>30*1024*1024:raise Refused('Physical retention manifest exceeds 30 MiB')
    return result


def summary(manifest):
    files=[value for root in manifest.values() for value in [root['identity'],*root['entries'].values()] if value['kind']=='file']
    return {'paths':sorted(manifest),'files':len(files),'bytes':str(sum(value['size'] for value in files)),
        'manifest_sha256':host.digest(manifest)}


def compact(directory,intent):
    value={key:intent[key] for key in ('retention_id','job_id','input_digest','review','state')}
    value.update(state='removed',observed_at=time.time(),original_native_outcome_unchanged=True)
    host.save(directory/'retention-intent.json',value)
    (directory/'retention-review.json').unlink(missing_ok=True)
    return value


def observe(directory,request):
    path=directory/'retention-intent.json'
    if not path.exists():return {'state':'not_claimed','removal_confirmed':False,'automatic_retry':False}
    intent=physical.read_json(path)
    if any(intent.get(key)!=request[key] for key in ('retention_id','job_id','input_digest')):
        raise Refused('Select this artifact\'s original retention intent')
    if intent['state']!='removed':
        if set(snapshot(directory))-set(intent['manifest']):raise Refused('Unreviewed physical retention paths are preserved')
        absent=all(not os.path.lexists(directory/name) and not os.path.lexists(directory/('.removing-'+intent['retention_id']+'-'+name)) for name in intent['manifest'])
        if absent:intent=compact(directory,intent)
    if intent['state']=='removed':(directory/'retention-review.json').unlink(missing_ok=True)
    return {'state':intent['state'],'removal_confirmed':intent['state']=='removed','review':intent['review'],
        'automatic_retry':False,'original_native_outcome_unchanged':True}


def verify_floors(root,request):
    floors=request.get('retained_full_backups',[])
    if not isinstance(floors,list) or not 1<=len(floors)<=1000:raise Refused('Select retained verified full backups')
    seen=set()
    for selected in floors:
        job=physical.job_id(selected['job_id'])
        if job in seen or job==request['job_id'] and request['action']=='retention_remove':raise Refused('Retained full backup identities differ')
        seen.add(job);directory=root/job
        original,value=stopped(directory,{**request,**selected})
        if (original['phase']!='backup' or original.get('source_identity')!=request.get('source_identity') or
                value.get('return_code')!=0 or value.get('error_type') or (directory/'retention-intent.json').exists()):
            raise Refused('Retained full backup is unavailable or belongs to another native source')
        unmounted([directory/'artifact'])
        if physical.public(physical.artifact(directory/'artifact',prepared=False))!=physical.public(value.get('artifact')):
            raise Refused('Retained full backup content changed; preserve the batch')
    return {'verified_full_backup_ids':sorted(seen)}


def dispatch(request,root,directory):
    retention_id=physical.job_id(request['retention_id']);physical.job_id(request['job_id'])
    if not directory.is_dir() or directory.is_symlink():raise Refused('Original physical job directory is unavailable')
    stopped(directory,request)
    action=request['action'];intent_path=directory/'retention-intent.json'
    if action=='retention_verify_floor':return verify_floors(root,request)
    if action=='retention_status':return observe(directory,request)
    if action=='retention_abandon':
        if intent_path.exists():return observe(directory,request)
        preview=directory/'retention-review.json'
        if preview.exists() and physical.read_json(preview)['review']['retention_id']==retention_id:
            host.save(preview,{'review':{'retention_id':retention_id},'expires_at':0,'cancelled':True})
        return {'state':'not_claimed','removal_confirmed':False,'late_dispatch_refused':True,'automatic_retry':False}
    children=dependencies(root,request['job_id'])
    planned=request.get('planned_job_ids',[])
    if not isinstance(planned,list) or len(planned)>100 or any(not isinstance(value,str) for value in planned) or len(set(planned))!=len(planned):raise Refused('Select a bounded physical batch preview')
    for value in planned:physical.job_id(value)
    if children and (action!='retention_inspect' or not set(children)<=set(planned)):
        raise Refused('Retain this physical input until its dependent physical artifacts are explicitly removed')
    if action=='retention_inspect':
        if intent_path.exists():raise Refused('Observe or resume the original physical retention intent')
        manifest=snapshot(directory)
        review={'retention_id':retention_id,'job_id':request['job_id'],'input_digest':request['input_digest'],
            'directory_identity':node(directory),'artifact':summary(manifest)}
        host.save(directory/'retention-review.json',{'review':review,'manifest':manifest,'expires_at':time.time()+600})
        return review
    if action!='retention_remove' or request.get('confirmed') is not True:raise Refused('Confirm the reviewed physical retention intent')
    if request.get('retained_full_backups') is not None:verify_floors(root,request)
    if intent_path.exists():
        current=observe(directory,request)
        if current['removal_confirmed']:return current
        intent=physical.read_json(intent_path)
        if request.get('retention_review')!=intent['review']:raise Refused('Original physical retention review differs')
    else:
        selected=physical.read_json(directory/'retention-review.json')
        if selected['expires_at']<time.time() or selected['review']!=request.get('retention_review') or selected['review']['retention_id']!=retention_id:
            raise Refused('Physical retention review expired or changed')
        if snapshot(directory)!=selected['manifest']:raise Refused('Physical artifact bytes changed after retention review')
        intent={'retention_id':retention_id,'job_id':request['job_id'],'input_digest':request['input_digest'],
            'review':selected['review'],'manifest':selected['manifest'],'state':'removing'}
        host.save(intent_path,intent)
    if node(directory)!=intent['review']['directory_identity']:raise Refused('Original physical job directory identity changed')
    if set(snapshot(directory))-set(intent['manifest']):raise Refused('Unreviewed physical retention paths are preserved')
    if not shutil.rmtree.avoids_symlink_attacks:raise Refused('Physical retention requires descriptor-safe directory removal')
    for name,reviewed in intent['manifest'].items():
        original=directory/name;detached=directory/('.removing-'+retention_id+'-'+name)
        unmounted([original,detached])
        before,after=tree(original),tree(detached)
        if before is not None and after is not None:raise Refused('Both original and detached physical artifacts exist')
        current=before if before is not None else after
        if current is None:continue
        if current['identity']!=reviewed['identity'] or any(reviewed['entries'].get(key)!=value for key,value in current['entries'].items()):
            raise Refused('Unreviewed physical retention files are preserved')
        if before is not None:host.durable_replace(original,detached)
        if current['identity']['kind']=='directory':shutil.rmtree(detached)
        else:detached.unlink()
    return {**compact(directory,intent),'removal_confirmed':True,'automatic_retry':False}
