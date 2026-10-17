"""Native parser ABI/string-context proof; no database or history execution."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys


def run(output):
    import pglast
    from pglast import parser, parse_sql
    receipt = {'component':'postgresql-parser-runtime', 'complete':False,
        'python':sys.version, 'platform':platform.platform(), 'checks':[], 'failures':[],
        'history_runtime_tests':'not run', 'scope':'offline native parser ABI and SQL/PLpgSQL string settings'}
    try:
        assert parser.CDEADMIN_PARSE_OPTIONS_REVISION == 2
        library = Path(parser.__file__)
        receipt.update(pglast_version=pglast.__version__, postgresql_parser_version=parser.get_postgresql_version(),
            extension_sha256=hashlib.sha256(library.read_bytes()).hexdigest())
        if sys.platform != 'linux': assert library.read_bytes()[:4] != b'\x7fELF'
        # Exercise direct AST traversal too: JSON-only success cannot prove
        # the Cython and libpg_query structure layouts agree.
        statement = parse_sql("SELECT 'é😀' AS exact_value FROM owned_relation WHERE id=1")[0].stmt
        assert statement.targetList[0].val.val.sval == 'é😀'
        assert statement.targetList[0].name == 'exact_value'
        assert statement.fromClause[0].relname == 'owned_relation'
        assert statement.whereClause.rexpr.val.ival == 1
        receipt['checks'].append('native-cython-ast-layout-and-unicode')
        sql = r"SELECT 'it\'s'"
        body = r"CREATE FUNCTION f() RETURNS text LANGUAGE plpgsql AS $$BEGIN RETURN 'it\'s'; END$$"
        cases = [(parser.parse_sql_json,(sql,32),True), (parser.parse_sql_json,(sql,0),False),
                 (parser.parse_sql_json,(sql,48),False),
                 (parser.parse_plpgsql_json,(body,0,32),True),
                 (parser.parse_plpgsql_json,(body,32,0),False),
                 (parser.parse_plpgsql_json,(body,0,48),False)]
        for cycle in range(3):
            for number,(operation,arguments,expected) in enumerate(cases):
                try: operation(*arguments); actual = True
                except parser.ParseError: actual = False
                assert actual is expected
                receipt['checks'].append({'cycle':cycle,'case':number,'grammar_valid':actual})
        assert json.loads(parser.parse_sql_json('SELECT 1'))['stmts']
        receipt['complete'] = True
    except Exception as error:
        receipt['failures'].append({'type':type(error).__name__})
    output.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    return 0 if receipt['complete'] else 1


if __name__ == '__main__':
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument('--output',type=Path,required=True)
    raise SystemExit(run(arguments.parse_args().output))
