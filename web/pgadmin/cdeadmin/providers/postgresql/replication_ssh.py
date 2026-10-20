"""Registered, explicitly pinned SSH access without SQL bootstrap."""
import base64
import hashlib
import io
import socket

from .continuity import ContinuityError


def fingerprint(key):
    return 'SHA256:'+base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode('ascii').rstrip('=')


def route(server):
    if not server.use_ssh_tunnel:return None
    mode=server.tunnel_authentication
    if type(mode) is not int or mode not in {0,1}:
        raise ContinuityError('Select a registered SSH authentication method')
    value={'host':server.tunnel_host,'port':22 if server.tunnel_port is None else server.tunnel_port,
        'username':server.tunnel_username,'remote_host':server.host,'remote_port':server.port,
        'authentication':'private_key' if mode==1 else 'password','keep_alive':server.tunnel_keep_alive or 0}
    for name in ('host','username','remote_host'):
        if not isinstance(value[name],str) or not value[name] or '\0' in value[name] or len(value[name])>1024:
            raise ContinuityError('Registered SSH identity is unavailable')
    for name in ('port','remote_port'):
        # The server registration stores tunnel_port as text, while the
        # database port is an integer. Admit only decimal port text here.
        if isinstance(value[name],str) and value[name].isascii() and value[name].isdecimal():
            value[name]=int(value[name])
        if type(value[name]) is not int or not 1<=value[name]<=65535:
            raise ContinuityError('Registered SSH port is unavailable')
    if type(value['keep_alive']) is not int or not 0<=value['keep_alive']<=3600:
        raise ContinuityError('Registered SSH keepalive is unavailable')
    return value


def describe(server,*,probe=False):
    selected=route(server)
    result={'ssh':selected,'ssh_peer':None,'sql_admission_performed':False,'probe_authenticated':False}
    if selected is None or not probe:return result
    import paramiko
    connection=None;transport=None
    try:
        connection=socket.create_connection((selected['host'],selected['port']),timeout=5)
        transport=paramiko.Transport(connection);transport.start_client(timeout=5)
        key=transport.get_remote_server_key()
        result['ssh_peer']={'openssh_key':key.get_name()+' '+key.get_base64(),'fingerprint':fingerprint(key)}
        return result
    except Exception as error:
        raise ContinuityError('Registered SSH peer inspection failed ('+type(error).__name__+')') from None
    finally:
        if transport is not None:transport.close()
        if connection is not None:connection.close()


def material(server,manager,request):
    selected=route(server)
    ssh_fields={'ssh_host_key','ssh_password','ssh_private_key_password'}
    if selected is None:
        if ssh_fields.intersection(request):raise ContinuityError('SSH credentials require a registered SSH transport')
        return None,{},None
    import paramiko
    try:
        text=request.get('ssh_host_key')
        if not isinstance(text,str) or len(text)>32768:raise ValueError()
        parts=text.split(maxsplit=2)
        if len(parts)<2:raise ValueError()
        key=paramiko.PKey.from_type_string(parts[0],base64.b64decode(parts[1],validate=True))
        selected.update(host_key_type=key.get_name(),host_key=key.get_base64())
    except Exception:
        raise ContinuityError('Inspect the registered SSH peer or supply its expected OpenSSH public host key') from None
    from .monitoring_ssh import validate_ssh_route
    validate_ssh_route(selected)
    kind='ssh_private_key_password' if selected['authentication']=='private_key' else 'ssh_password'
    if ({'ssh_password','ssh_private_key_password'}-{kind}).intersection(request):
        raise ContinuityError('SSH credential does not match the registered authentication method')
    password=request.get(kind)
    if password is not None and (not isinstance(password,str) or '\0' in password or len(password)>4096):
        raise ContinuityError('Invalid registered SSH credential')
    if password is None:
        encrypted=getattr(manager,'tunnel_password',None) or server.tunnel_password
        if encrypted:
            from pgadmin.utils.master_password import get_crypt_key
            from pgadmin.utils.crypto import decrypt
            present,crypt_key=get_crypt_key()
            if not present:raise ContinuityError('Registered SSH credential authority is unavailable')
            try:
                password=decrypt(encrypted,crypt_key)
                if isinstance(password,bytes):password=password.decode('utf8')
            except Exception:
                raise ContinuityError('Registered SSH credential could not be unlocked') from None
    secrets={kind:password} if password else {}
    client_key=None
    if selected['authentication']=='private_key':
        from pgadmin.utils import get_complete_file_path
        try:
            with open(get_complete_file_path(server.tunnel_identity_file),'rb') as incoming:data=incoming.read(1024**2+1)
            if not data or len(data)>1024**2:raise ValueError()
            for key_type in (paramiko.Ed25519Key,paramiko.ECDSAKey,paramiko.RSAKey,paramiko.DSSKey):
                try:
                    client_key=key_type.from_private_key(io.StringIO(data.decode('utf8')),password=password);break
                except (paramiko.SSHException,ValueError):continue
            if client_key is None:raise ValueError()
            secrets['ssh_private_key']=data
        except Exception:
            raise ContinuityError('Registered SSH private key could not be admitted') from None
    elif not password:raise ContinuityError('Supply the registered SSH password or unlock its saved credential')
    identity={'host':selected['host'],'port':selected['port'],'username':selected['username'],
        'remote_host':selected['remote_host'],'remote_port':selected['remote_port'],
        'authentication':selected['authentication'],'host_key_fingerprint':fingerprint(key),
        'client_key_fingerprint':fingerprint(client_key) if client_key else None}
    return selected,secrets,identity
