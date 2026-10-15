"""Render native-encoded statements for a fresh mysql-client batch session."""
import hashlib
from .mysql_sql_export import _literal
from ..providers.mysql_family.mysql_catalog import identifier


def render(encoded,database,*,engine="mysql"):
    if engine not in {"mysql","mariadb"}:raise ValueError("Unsupported native metadata engine")
    if not encoded:raise ValueError('Native encoded statements are required')
    combined=b'\n'.join(data for _block,data in encoded);nonce=0
    while True:
        delimiter=('__sr_'+hashlib.sha256(str(nonce).encode()+combined).hexdigest()[:10]).encode('ascii')
        if delimiter not in combined:break
        nonce+=1
    output=bytearray(('-- Native '+('MariaDB' if engine=='mariadb' else 'MySQL')+' metadata; fresh '+engine+' --binary-mode --default-character-set=utf8mb4 client only.\n').encode('ascii'))
    output.extend(b'-- Imported DDL is unvalidated; this file does not authorize execution.\n')
    output.extend(b'\\C utf8mb4\nDELIMITER '+delimiter+b'\n')
    selected=False;encodings=[]
    def append(data):output.extend(data+b'\n'+delimiter+b'\n')
    for block,data in encoded:
        # Select the database with UTF-8 protocol bytes before switching to a
        # stored object charset which may not represent the database's name.
        if block['kind']!='database' and not selected:
            output.extend(b'\\C utf8mb4\n');append(('USE '+identifier(database)).encode('utf8'));selected=True
        context=block['context'];charset=context['character_set_client']
        output.extend(('\\C '+charset+'\n').encode('ascii'))
        for key in ('sql_mode','collation_connection','time_zone'):
            if key not in context:continue
            append(('SET SESSION '+key+'='+_literal(context[key])).encode('ascii'))
        append(data)
        encodings.append({'resource_id':block['resource_id'],'character_set_client':charset,'byte_size':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        if len(output)>8*1024*1024:raise ValueError('Native mixed-encoding script exceeds 8 MiB')
    output.extend(b'\\C utf8mb4\nDELIMITER ;\n')
    if len(output)>8*1024*1024:raise ValueError('Native mixed-encoding script exceeds 8 MiB')
    return bytes(output),encodings
