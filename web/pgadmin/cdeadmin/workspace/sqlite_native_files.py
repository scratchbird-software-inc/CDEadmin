"""Owned verified input references; callers never supply application-host paths."""
from copy import deepcopy

from ..providers.sqlite.session_api import SessionAPIError


def manager(service,server,target,kind):
    if not isinstance(kind,str) or kind not in {'capture','upload','transform','diff','rebase'}:raise SessionAPIError('Select an owned native artifact kind')
    if kind=='capture':from .sqlite_capture_service import manager as selected
    elif kind=='upload':from .sqlite_upload_service import manager as selected
    elif kind=='transform':from .sqlite_transform_service import manager as selected
    elif kind=='diff':from .sqlite_diff_service import manager as selected
    else:from .sqlite_changeset_service import manager as selected
    return selected(service,server,target)


def resolve(service,server,reference,owner,endpoint):
    if not isinstance(reference,dict) or set(reference)!={'database_target_id','kind','job_id','path'}:
        raise SessionAPIError('Select one exact owned native artifact reference')
    jobs,source_owner,source_endpoint=manager(service,server,reference['database_target_id'],reference['kind'])
    if owner!=source_owner or endpoint.id!=source_endpoint.id:raise SessionAPIError('Native input belongs to another owner or endpoint')
    record=jobs.load(reference['job_id'],owner,endpoint.id);artifact=(record.get('result') or {}).get('artifact') or {}
    if record.get('artifact_removed'):raise SessionAPIError('The selected native artifact files were removed')
    if reference['kind']=='rebase':
        if not record.get('commit_returned') or record['state']!='completed' and not record.get('output_artifact_verified'):
            raise SessionAPIError('Select retained rebase output from an acknowledged native commit')
        expected='native.rebase';native_kind='rebase';factory=jobs.output_download
    else:
        if record['state'] not in {'completed','artifact_verified'} or not artifact.get('native_iterator_complete'):
            raise SessionAPIError('Select a sealed, native-validated changeset or patchset')
        expected='capture.'+record['options']['kind'] if reference['kind']=='capture' else artifact.get('input_name')
        native_kind=record['options']['kind'] if reference['kind']=='capture' else artifact.get('native_kind')
        if native_kind not in {'changeset','patchset'}:raise SessionAPIError('Native input format is unavailable')
        factory=jobs.download
    row=next((row for row in artifact.get('files',[]) if row['path']==expected),None)
    if row is None or reference['path']!=expected:raise SessionAPIError('Select the exact verified native input file')
    observed={'reference':deepcopy(reference),'file':{**deepcopy(row),'size':str(row['size'])},'native_kind':native_kind,
        'origin_program':record['program'],'origin_commit_returned':record.get('commit_returned') is True}
    return observed,lambda:factory(record['job_id'],owner,endpoint.id,expected)
