"""Observe SQLite's compiled keywords and native name roles without execution.

Authority: sqlite3_keyword_name(), Lemon nm/ids/fallback rules in3.53.0
src/parse.y, and contextual WINDOW/OVER/FILTER rules in src/tokenize.c.
Only EXPLAIN of fixed constant SELECTs is prepared; user functions never run.
"""
import ctypes
from functools import lru_cache
import os
import re
import sqlite3


@lru_cache(maxsize=1)
def native_keywords():
    import _sqlite3
    library=ctypes.CDLL('sqlite3.dll' if os.name=='nt' else _sqlite3.__file__)
    library.sqlite3_libversion.argtypes=[];library.sqlite3_libversion.restype=ctypes.c_char_p
    library.sqlite3_sourceid.argtypes=[];library.sqlite3_sourceid.restype=ctypes.c_char_p
    if library.sqlite3_libversion().decode('ascii')!=sqlite3.sqlite_version:
        raise ValueError('The native keyword API belongs to another SQLite runtime')
    library.sqlite3_keyword_count.argtypes=[];library.sqlite3_keyword_count.restype=ctypes.c_int
    library.sqlite3_keyword_name.argtypes=[ctypes.c_int,ctypes.POINTER(ctypes.c_char_p),ctypes.POINTER(ctypes.c_int)]
    library.sqlite3_keyword_name.restype=ctypes.c_int
    count=library.sqlite3_keyword_count()
    if not 1<=count<=2048:raise ValueError('The native SQLite keyword inventory is invalid')
    names=[]
    for index in range(count):
        name=ctypes.c_char_p();length=ctypes.c_int()
        if library.sqlite3_keyword_name(index,ctypes.byref(name),ctypes.byref(length))!=0 or not 1<=length.value<=128:
            raise ValueError('A native SQLite keyword is unavailable')
        word=ctypes.string_at(name,length.value).decode('ascii')
        if not re.fullmatch('[A-Z_]+',word):raise ValueError('A native SQLite keyword identity is invalid')
        names.append(word)
    return tuple(sorted(names)),library.sqlite3_sourceid().decode('ascii')


def observe(connection,fallback_words):
    observations=[]
    try:
        words,source_id=native_keywords()
        observations.append({'section':'native-keyword-api','available':True,'keyword_count':len(words)})
    except (OSError,AttributeError,ValueError,UnicodeError):
        words=tuple(sorted(set(fallback_words)));source_id=None
        observations.append({'section':'native-keyword-api','available':False,'reason':'loaded-runtime-keyword-api-unavailable'})
    roles={name:[] for name in ('nm','ids','bare','qualifier','lookahead')};unavailable=[]
    cursor=connection.cursor()
    def plan(source):
        try:
            cursor.execute('EXPLAIN '+source,(1,));rows=cursor.fetchmany(129)
            if not rows or len(rows)>128:raise ValueError('Native constant-plan observation is incomplete')
            return [tuple(row) for row in rows]
        except sqlite3.Error as error:
            code=getattr(error,'sqlite_errorcode',None)
            if type(code) is int and code&255==sqlite3.SQLITE_ERROR:return None
            raise
    try:
        for word in words:
            quoted='"'+word+'"';base=' FROM (SELECT ? AS '+quoted+') AS "__sr_name"'
            sources={'nm':'SELECT "__sr_name".'+word+base,
                'ids':'SELECT '+quoted+'."value" FROM (SELECT ? AS "value") '+word,
                'qualifier':'SELECT '+word+'."value" FROM (SELECT ? AS "value") AS '+quoted,
                'bare':'SELECT '+word+base}
            if 'WINDOW' in words:sources['lookahead']='SELECT ? FROM (SELECT 1) WINDOW '+word+' AS ()'
            try:
                baseline=plan('SELECT "__sr_name".'+quoted+base)
                if baseline is None:raise ValueError('Native constant-plan baseline is unavailable')
                for role,source in sources.items():
                    result=plan(source)
                    if result is not None and (role!='bare' or result==baseline):roles[role].append(word)
            except (sqlite3.Error,ValueError) as error:
                unavailable.append({'keyword':word,'error_code':getattr(error,'sqlite_errorcode',None),'error_type':type(error).__name__})
    finally:cursor.close()
    observations.append({'section':'identifier-keyword-bindings','available':not unavailable,
        'authority':'native_EXPLAIN_constant_SELECT_binding_without_statement_execution','unavailable':unavailable})
    return {'keywords':' '.join(words),'reserved_words':sorted(set(words)-set(roles['nm'])),
        'identifier_keyword_roles':roles,'sqlite_contextual_keywords':[word for word in ('WINDOW','OVER','FILTER') if word in words],
        'keyword_source_id':source_id,'keyword_observation_complete':all(row['available'] for row in observations)},observations
