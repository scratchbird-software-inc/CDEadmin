"""Ask native MySQL to encode complete DDL; never execute imported definitions."""
import base64
import hashlib
import re


def encode_metadata(connection,metadata):
    if connection.in_transaction:raise ValueError('Native encoding requires its own idle connection')
    if metadata.get('blockers') or not metadata.get('statements') or not metadata.get('native_encoding_required'):
        raise ValueError('A complete encoding-required native metadata export is required')
    connection.autocommit=True
    connection.set_charset_collation(charset='utf8mb4',collation='utf8mb4_0900_ai_ci')
    cursor=connection.cursor();encoded=[];size=0
    try:
        cursor.execute('SELECT VERSION(),@@server_uuid,DATABASE()');identity=cursor.fetchone()
        if str(identity[0]).split('-')[0]!='9.7.0' or identity[1]!=metadata['server_uuid'] or identity[2]!=metadata['database']:
            raise ValueError('Native encoding connection identity changed')
        for block in metadata['statements']:
            context=block['context'];charset=context['character_set_client'];collation=context['collation_connection']
            if not all(isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_]+',value) for value in (charset,collation)):
                raise ValueError('Invalid native charset/collation identity')
            try:
                # These commands and their values are ASCII. Restore the owned
                # UTF-8 connection before sending any non-ASCII definition.
                cursor.execute('SET SESSION character_set_client=%s',(charset,))
                cursor.execute('SET SESSION collation_connection=%s',(collation,))
            finally:
                connection.set_charset_collation(charset='utf8mb4',collation='utf8mb4_0900_ai_ci')
            statement=block['statement']
            cursor.execute('SELECT CAST(CONVERT(%s USING '+charset+') AS BINARY), CONVERT(CONVERT(%s USING '+charset+') USING utf8mb4)',(statement,statement))
            data,roundtrip=cursor.fetchone()
            if not isinstance(data,(bytes,bytearray)) or roundtrip!=statement:
                raise ValueError('Native character conversion would lose definition text for '+block['name'])
            size+=len(data)
            if size>8*1024*1024:raise ValueError('Native encoded statements exceed 8 MiB')
            encoded.append((block,bytes(data)))
    finally:cursor.close()
    from ..workspace.mysql_encoded_script import render
    data,encodings=render(encoded,metadata['database'])
    return {**metadata,'script_available':True,'native_encoding_required':False,
        'script_preview':'\n\n'.join(block['statement']+';' for block,_data in encoded),
        'encoded_script':{'consumer':'mysql-cli-fresh-session','encoding':'mysql-client-mixed-charsets',
            'data_base64':base64.b64encode(data).decode('ascii'),'sha256':hashlib.sha256(data).hexdigest(),
            'byte_size':len(data),'required_client_options':['--binary-mode','--default-character-set=utf8mb4'],'statement_encodings':encodings}}
