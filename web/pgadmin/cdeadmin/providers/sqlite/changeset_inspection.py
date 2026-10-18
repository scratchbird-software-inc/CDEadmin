"""Typed native file pages and byte ranges; no database data is inspected."""
import base64
import codecs
import os
import stat

from .session_api import SessionAPIError


def decimal(value,label):
    if not isinstance(value,str) or not value.isascii() or not value.isdecimal() or len(value)>19 or str(int(value))!=value or int(value)>9223372036854775807:
        raise SessionAPIError(label+' requires exact nonnegative bounded decimal text')
    return int(value)


def options(value):
    if not isinstance(value,dict):raise SessionAPIError('Select native inspection options')
    mode=value.get('mode','page');timeout=value.get('timeout_seconds',3600)
    if not isinstance(mode,str) or mode not in {'page','cell','extract'} or timeout is not None and (type(timeout) is not int or not 1<=timeout<=2147483647):raise SessionAPIError('Select a native inspection mode and positive duration or no deadline')
    common={'mode','timeout_seconds'}
    if mode=='page':
        if set(value)-common-{'offset','limit','preview_bytes','max_json_bytes'}:raise SessionAPIError('Select one bounded native record page')
        offset=value.get('offset','0');decimal(offset,'Native record offset');limit=value.get('limit',25);preview=value.get('preview_bytes',256);budget=value.get('max_json_bytes',1048576)
        if type(limit) is not int or not 1<=limit<=100 or type(preview) is not int or not 0<=preview<=65536 or type(budget) is not int or not 1<=budget<=16777216:
            raise SessionAPIError('Select native page, byte-preview and JSON limits')
        return {'mode':mode,'offset':offset,'limit':limit,'preview_bytes':preview,'max_json_bytes':budget,'timeout_seconds':timeout}
    allowed={'record_number','column_index','side'} | ({'byte_offset','byte_limit'} if mode=='cell' else set())
    if set(value)-common-allowed:raise SessionAPIError('Select one native cell range or complete byte value')
    number=value.get('record_number');offset=value.get('byte_offset','0');column=value.get('column_index');side=value.get('side');limit=value.get('byte_limit',65536)
    if decimal(number,'Native record number')<1 or type(column) is not int or not 0<=column<=2147483647 or not isinstance(side,str) or side not in {'old','new'} or type(limit) is not int or not 1<=limit<=65536:
        raise SessionAPIError('Select an exact native record, column, side and byte range')
    decimal(offset,'Native cell byte offset')
    result={'mode':mode,'record_number':number,'column_index':column,'side':side,'timeout_seconds':timeout}
    return {**result,'byte_offset':offset,'byte_limit':limit} if mode=='cell' else result


def decode_cell(value):
    if 'hex' not in value:return value
    raw=bytes.fromhex(value['hex']);value['data']={'encoding':'base64','data':base64.b64encode(raw).decode('ascii'),'byte_length':len(raw)}
    if value['native_type']=='text':
        value['data']['native_storage_class']='text'
        try:value['preview_text']=codecs.getincrementaldecoder('utf8')('strict').decode(raw,final=not value['truncated'])
        except UnicodeDecodeError:pass
    return value


def decode_page(value):
    for row in value['rows']:
        raw=bytes.fromhex(row['table_hex'])
        try:row['table']=raw.decode('utf8')
        except UnicodeDecodeError:row['table']={'encoding':'base64','data':base64.b64encode(raw).decode('ascii'),'native_storage_class':'text'}
        for side in ('old_values','new_values'):
            if row[side] is not None:row[side]=[decode_cell(cell) for cell in row[side]]
    value['column_name_scope']='Native files contain column positions and primary-key masks, not original column names or declared SQL types'
    value['validation_scope']='This bounded iterator result does not validate any unvisited suffix; input eligibility has its own full native validation receipt'
    return value


def inspect(api,descriptor,selected,cancel_descriptor=-1,output_descriptor=None):
    selected=options(selected)
    if api.program.get('native_session_revision',0)<6:raise SessionAPIError('The native session helper lacks typed file inspection')
    if type(descriptor) is not int or descriptor<0 or not stat.S_ISREG(os.fstat(descriptor).st_mode) or type(cancel_descriptor) is not int or cancel_descriptor<-1:
        raise SessionAPIError('Select owned regular input and cancellation descriptors')
    os.lseek(descriptor,0,os.SEEK_SET)
    if selected['mode']=='page':
        return decode_page(api.call('inspect_page',descriptor,cancel_descriptor,int(selected['offset']),selected['limit'],selected['preview_bytes'],selected['max_json_bytes']))
    if selected['mode']=='extract':
        if type(output_descriptor) is not int or output_descriptor<0:raise SessionAPIError('Select an owned native byte-value output descriptor')
        source=os.fstat(descriptor);target=os.fstat(output_descriptor)
        if not stat.S_ISREG(target.st_mode) or (source.st_dev,source.st_ino)==(target.st_dev,target.st_ino):raise SessionAPIError('Native byte extraction requires a separate regular output file')
        return api.call('extract_cell',descriptor,cancel_descriptor,int(selected['record_number']),selected['column_index'],int(selected['side']=='new'),output_descriptor)
    return decode_cell(api.call('inspect_cell',descriptor,cancel_descriptor,int(selected['record_number']),selected['column_index'],int(selected['side']=='new'),int(selected['byte_offset']),selected['byte_limit']))
