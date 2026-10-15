"""Execute generated previews only in the gate-owned disposable database."""
import json
from pathlib import Path
import subprocess


def qualify(connection):
    from pgadmin.cdeadmin.providers.firebird.grid_values import bind_value
    module = Path(__file__).resolve().parents[1] / 'web/pgadmin/static/js/Dialogs/firebirdRowSqlHelpers.js'
    runner = """
import {readFileSync} from 'node:fs';
const m = await import('data:text/javascript;base64,' + readFileSync(process.argv[1]).toString('base64'));
const columns = [{name:'ID',input_kind:'integer'}, {name:'T"X',input_kind:'text'},
 {name:'N',input_kind:'decimal'}, {name:'B',input_kind:'binary'}, {name:'D',input_kind:'date'}, {name:'V',input_kind:'boolean'}];
const values = {ID:'9007199254740993', 'T"X':"O'Brien 世界", N:'12345678901234567890.1234',
 B:{encoding:'base64',data:'AP9B',byte_length:3},D:'2026-10-10',V:true};
const args = {table:'ROW_SQL_TEST',columns,rows:[{values}],keys:['ID']};
process.stdout.write(JSON.stringify({
 inserts:[false,true].map(inline=>m.generateRowSql({...args,operation:'insert',inline})[0]),
 update:m.generateRowSql({...args,rows:[{values:{...values,'T"X':'Updated'}}],operation:'update'})[0],
 upsert:m.generateRowSql({...args,rows:[{values:{...values,'T"X':'Upserted'}}],operation:'upsert',inline:true})[0],
 predicate:m.generateRowSql({...args,operation:'in',inColumn:'ID'})[0]}));
"""
    plans = json.loads(subprocess.run(['node', '--input-type=module', '-e', runner, str(module)],
                                     capture_output=True, text=True, check=True, timeout=15).stdout)
    with connection.cursor() as cursor:
        cursor.execute('CREATE TABLE ROW_SQL_TEST (ID BIGINT PRIMARY KEY, "T""X" VARCHAR(60) CHARACTER SET UTF8, N NUMERIC(30,4), B BLOB SUB_TYPE BINARY, D DATE, V BOOLEAN)')
    connection.commit()

    def execute(plan):
        with connection.cursor() as cursor:
            cursor.execute(plan['source'], [bind_value(value) for value in plan['parameters']])
            return cursor.fetchall() if cursor.description else []

    for insert in plans['inserts']:
        execute(insert)
        row = execute(plans['predicate'])[0]
        assert row[0] == 9007199254740993 and row[1] == "O'Brien 世界"
        assert str(row[2]) == '12345678901234567890.1234' and row[3] == b'\0\xffA'
        assert str(row[4]) == '2026-10-10' and row[5] is True
        execute(plans['update'])
        assert execute(plans['predicate'])[0][1] == 'Updated'
        execute(plans['upsert'])
        rows = execute(plans['predicate'])
        assert len(rows) == 1 and rows[0][1] == 'Upserted'
        connection.rollback()
        assert execute(plans['predicate']) == []
        connection.rollback()
    return {'passed': True, 'bound_and_inline_inserts': True,
            'native_update_upsert_and_in_predicate': True, 'exact_numeric_and_binary_values': True,
            'rollback_preserved': True}
