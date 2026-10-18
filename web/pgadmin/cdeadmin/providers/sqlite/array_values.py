"""Native CARRAY storage widths and nullable TEXT/BLOB element envelopes."""
import base64
import binascii
import struct

from .session_api import SessionAPIError

TYPES={'int32':0,'int64':1,'double':2,'text':3,'blob':4}


def integer(value,bits):
    if isinstance(value,dict) and set(value)=={'encoding','data'} and value['encoding']=='integer':value=value['data']
    if type(value) is int:number=value
    elif isinstance(value,str):
        try:number=int(value)
        except ValueError:raise SessionAPIError('Native array integers require exact decimal text') from None
        if str(number)!=value:raise SessionAPIError('Native array integers require canonical decimal text')
    else:raise SessionAPIError('Native integer arrays require integers or exact decimal text')
    if not -(1<<(bits-1))<=number<(1<<(bits-1)):raise SessionAPIError('Native array integer exceeds its storage width')
    return number


def binary(value,text=False):
    if value is None:return None
    if text and isinstance(value,str):return value.encode('utf8')
    if isinstance(value,bytes):return value
    if isinstance(value,dict) and value.get('encoding')=='base64' and isinstance(value.get('data'),str) and not set(value)-{'encoding','data','byte_length','native_storage_class'}:
        if text and value.get('native_storage_class')!='text':raise SessionAPIError('Raw text bytes require their native TEXT storage class')
        if not text and value.get('native_storage_class') not in (None,'blob'):raise SessionAPIError('Select a native BLOB value')
        try:result=base64.b64decode(value['data'],validate=True)
        except (ValueError,binascii.Error):raise SessionAPIError('Native array bytes require valid base64') from None
        if 'byte_length' in value and (type(value['byte_length']) is not int or value['byte_length']!=len(result)):
            raise SessionAPIError('Native array byte length differs')
        return result
    raise SessionAPIError('Select native nullable TEXT or BLOB elements')


def encode(kind,values):
    if not isinstance(kind,str) or kind not in TYPES or not isinstance(values,(list,tuple)) or len(values)>2147483647:
        raise SessionAPIError('Select a native CARRAY type and element list')
    if kind in {'int32','int64'}:
        bits=32 if kind=='int32' else 64;format='=i' if bits==32 else '=q'
        payload=b''.join(struct.pack(format,integer(value,bits)) for value in values);data_bytes=len(payload)
    elif kind=='double':
        numbers=[]
        for value in values:
            if isinstance(value,dict) and set(value)=={'encoding','data'} and value['encoding']=='float64':value=value['data']
            if type(value) not in (int,float,str):raise SessionAPIError('Native double arrays require numeric values or float64 text')
            try:number=float(value)
            except (ValueError,OverflowError):raise SessionAPIError('Native double array value is invalid') from None
            numbers.append(number)
        payload=b''.join(struct.pack('=d',value) for value in numbers);data_bytes=len(payload)
    else:
        blocks=[];data_bytes=len(values)*struct.calcsize('P')*(1 if kind=='text' else 2)
        for value in values:
            raw=binary(value,kind=='text')
            if raw is None:blocks.append(struct.pack('=q',-1));continue
            if kind=='text' and b'\x00' in raw:raise SessionAPIError('Native CARRAY TEXT uses terminated strings; use BLOB for embedded zero bytes')
            blocks.extend((struct.pack('=q',len(raw)),raw));data_bytes+=len(raw)+1
        payload=b''.join(blocks)
    return {'native_type':TYPES[kind],'type_name':kind,'element_count':len(values),'payload':payload,'native_data_bytes':data_bytes}
