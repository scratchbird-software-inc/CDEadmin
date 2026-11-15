"""Native parent-namespace continuity, including older PostgreSQL minors.

A relation lock does not prevent every supported server from renaming its
namespace. Hold the actual pg_namespace tuple through the DROP transaction.
Ordinary owners use a narrowly scoped, superuser-installed native SQL helper.
"""
from psycopg import Cursor
from psycopg.rows import tuple_row

NAME = 'pg_catalog.scratchrobin_lock_drop_namespace_v1'
SIGNATURE = NAME + '(oid,oid,text)'
BODY = '''SELECT n.oid FROM pg_catalog.pg_namespace n
JOIN pg_catalog.pg_class c ON c.relnamespace=n.oid
WHERE c.oid=$1 AND n.oid=$2 AND n.nspname=$3 AND c.relkind IN ('r','p')
AND (pg_catalog.pg_has_role(CASE WHEN pg_catalog.current_setting('role')='none'
THEN SESSION_USER::text ELSE pg_catalog.current_setting('role') END,c.relowner,'USAGE')
OR pg_catalog.pg_has_role(CASE WHEN pg_catalog.current_setting('role')='none'
THEN SESSION_USER::text ELSE pg_catalog.current_setting('role') END,n.nspowner,'USAGE'))
FOR SHARE OF n,c NOWAIT'''
INSTALL = f'''CREATE FUNCTION {SIGNATURE.replace('(oid,oid,text)', '(oid, oid, text)')}
RETURNS oid LANGUAGE sql VOLATILE STRICT SECURITY DEFINER
SET search_path = pg_catalog AS $sr_namespace_guard${BODY}$sr_namespace_guard$;
GRANT EXECUTE ON FUNCTION {SIGNATURE} TO PUBLIC'''


def lock(connection, relation_oid, namespace_oid, schema):
    from .destructive_identity import IdentityConflict
    with Cursor(connection, row_factory=tuple_row) as cursor:
        cursor.execute('SELECT rolsuper FROM pg_catalog.pg_roles WHERE rolname=CURRENT_USER')
        if cursor.fetchone() == (True,):
            cursor.execute('''SELECT n.oid FROM pg_catalog.pg_namespace n
JOIN pg_catalog.pg_class c ON c.relnamespace=n.oid
WHERE c.oid=%s AND n.oid=%s AND n.nspname=%s FOR SHARE OF n,c NOWAIT''',
                           (relation_oid, namespace_oid, schema))
        else:
            cursor.execute('''SELECT p.prosrc,p.prosecdef,p.proisstrict,p.provolatile,
p.proconfig,p.prorettype=\'oid\'::pg_catalog.regtype,p.prokind,l.lanname,r.rolsuper,
n.nspname,pg_catalog.has_function_privilege(p.oid,'EXECUTE')
FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_language l ON l.oid=p.prolang
JOIN pg_catalog.pg_roles r ON r.oid=p.proowner
JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
WHERE p.oid=pg_catalog.to_regprocedure(%s)''', (SIGNATURE,))
            if cursor.fetchone() != (BODY, True, True, 'v', ['search_path=pg_catalog'], True,
                                      'f', 'sql', True, 'pg_catalog', True):
                raise IdentityConflict('The database needs its superuser-installed native namespace DROP guard; use Install DROP namespace guard and review again')
            cursor.execute(f'SELECT {NAME}(%s::oid,%s::oid,%s::text)', (relation_oid, namespace_oid, schema))
        if cursor.fetchone() != (namespace_oid,):
            raise IdentityConflict('The reviewed native namespace changed or its ownership is unavailable; refresh and review again')
