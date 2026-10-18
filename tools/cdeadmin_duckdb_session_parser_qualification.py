"""Original-session DuckDB grammar context and nonexecuting validation evidence."""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output):
    import config  # noqa: F401
    import duckdb
    from pgadmin.cdeadmin.providers.duckdb.provider import DuckDBPilotProvider,_create_client
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    proof={'complete':False,'full_product_complete':False,'history_testing':'not run','native_version':duckdb.__version__,'checks':[],
        'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in [
            'tools/cdeadmin_duckdb_session_parser_qualification.py',
            'web/pgadmin/cdeadmin/providers/duckdb/provider.py','web/pgadmin/cdeadmin/providers/duckdb/language.py']}}
    try:
        for memory in [False,True]:
            directory=output/('memory' if memory else 'file');directory.mkdir()
            route={'database':':memory:' if memory else str(directory/'owned.duckdb'),'filesystem_root':str(directory),'allow_memory':memory}
            client=_create_client();handle=client.open_session({'route':route})
            provider=object.__new__(DuckDBPilotProvider);provider.client=client;provider._sessions={'owned':SimpleNamespace(handle=handle)}
            def validate(source,script=False):return provider.validate_source_without_execution({'session_id':'owned','language_profile':'duckdb-sql','source':source,'script':script})
            try:
                handle.execute('CREATE TABLE pending(id INT)');client.control_transaction(handle,'commit')
                handle.execute('INSERT INTO pending VALUES (42)');handle.execute('CREATE TEMP TABLE private(id INT)')
                transaction=handle.execute('SELECT current_transaction_id()').fetchone()[0]
                nested='SELECT '+'abs('*100+'1'+')'*100
                handle.execute('SET max_expression_depth=40')
                assert duckdb.extract_statements(nested)
                limited=validate(nested);assert limited['grammar_valid'] is False and limited['parser_context']=='retained-native-session'
                handle.execute('SET max_expression_depth=200')
                assert validate(nested)['grammar_valid'] is True
                script="CREATE TABLE never_created(id INT); INSERT INTO pending VALUES (99); DELETE FROM pending; COMMIT; ROLLBACK; INSTALL definitely_uninstalled_extension; LOAD definitely_uninstalled_extension; SET max_expression_depth=1;"
                parsed=validate(script,True);assert parsed['grammar_valid'] and parsed['script_ready'] and len(parsed['statements'])==8
                assert handle.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name='never_created'").fetchone()==(0,)
                assert handle.execute('SELECT * FROM pending').fetchall()==[(42,)]
                assert handle.execute("SELECT count(*) FROM duckdb_tables() WHERE temporary AND table_name='private'").fetchone()==(1,)
                assert handle.execute("SELECT current_setting('max_expression_depth')").fetchone()==(200,)
                assert handle.execute('SELECT current_transaction_id()').fetchone()[0]==transaction
                unknown=validate('PRAGMA deliberately_unknown_pragma');assert unknown['grammar_valid'] is None and unknown['diagnostics'][0]['code']=='DUCKDB_PARSE_CONTEXT'
                secret="SELECT 'do-not-echo-private-source' FROM ;";invalid=validate(secret)
                assert invalid['grammar_valid'] is False and 'do-not-echo-private-source' not in json.dumps(invalid)
                handle.rollback();assert handle.execute('SELECT * FROM pending').fetchall()==[]
                proof['checks'].append({'root':'memory' if memory else 'file','original_parser_limit_observed':True,
                    'changed_native_parser_setting_observed':True,'submitted_mutations_and_transaction_commands_not_executed':True,
                    'pending_rows_temporary_objects_and_transaction_identity_preserved':True,
                    'native_catalog_refusal_not_reported_as_grammar_failure':True,'invalid_source_not_echoed':True})
            finally:client.close()
        proof['complete']=True
    finally:(output/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',required=True,type=Path)
    qualify(parser.parse_args().evidence)
