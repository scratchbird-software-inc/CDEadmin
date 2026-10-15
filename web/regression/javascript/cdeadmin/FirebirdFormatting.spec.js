import {firebirdTokens, formatFirebird} from 'sources/cdeadmin_ui/editors/firebirdFormatting';
import {firebirdSQLConfig} from 'sources/cdeadmin_ui/editors/firebirdSyntax';
import {EditorState} from '@codemirror/state';
import {CompletionContext} from '@codemirror/autocomplete';
import {schemaCompletionSource, sql} from '@codemirror/lang-sql';

describe('Firebird source formatting and completion', () => {
  it.each([
    'select q\'{line 1\n\'quoted\'; -- literal}\' from rdb$database',
    'select "END""name", 1e+2, .5, x\'ABCD\' from "TABLE" where x != 1',
    'execute block returns (v varchar(40)) as begin v = \' a  b \'; suspend; end',
    'select 1 -- preserve  comment\nfrom rdb$database /* preserve\ncomment */',
    'set term ^ ; execute block as begin exit; end ^ set term ; ^',
  ])('preserves all native tokens for %s', source => {
    const signature = text => firebirdTokens(text).map(({kind, text: token}) => [kind, token]);
    expect(signature(formatFirebird(source))).toEqual(signature(source));
    expect(formatFirebird(formatFirebird(source))).toBe(formatFirebird(source));
  });
  it.each(['select \'unterminated', 'select "unterminated', 'select /* missing', 'select q\'{unclosed\''])(
    'refuses malformed lexical source %s', source => expect(() => formatFirebird(source)).toThrow());
  it('uses native names and does not invent missing columns', () => {
    const config = firebirdSQLConfig('SELECT FROM', 3, [
      {resource_kind: 'table', display_name: 'Odd"table'},
      {resource_kind: 'column', display_name: 'Odd"column', display_path: ['db', 'Odd"table', 'Odd"column']},
      {resource_kind: 'column', display_name: 'unloaded', display_path: ['db', 'absent', 'unloaded']},
    ]);
    expect(Object.keys(config.schema)).toEqual(['Odd"table']);
    expect(config.schema['Odd"table'].children[0].apply).toBe('"Odd""column"');
    expect(config.schema['Odd"table'].self.apply).toBe('"Odd""table"');
    expect(config.dialect.spec.doubleQuotedStrings).toBe(false);
    expect(firebirdSQLConfig('SELECT', 1, []).dialect.spec.doubleQuotedStrings).toBe(true);
  });
  it('quotes lower-case native names, preserves literal dots and omits names unavailable in dialect 1', () => {
    const resources = ['lower.name', 'UPPER', 'SELECT'].map(display_name => ({resource_kind: 'table', display_name}));
    const modern = firebirdSQLConfig('SELECT', 3, resources, ['SELECT']);
    expect(modern.schema['lower\\.name'].self.apply).toBe('"lower.name"');
    const legacy = firebirdSQLConfig('SELECT', 1, resources, ['SELECT']);
    expect(Object.keys(legacy.schema)).toEqual(['UPPER']);
    expect(legacy.schema.UPPER.self.apply).toBe('UPPER');
  });
  it('resolves actual CodeMirror completion for a quoted native name containing a dot', () => {
    const config = firebirdSQLConfig('SELECT', 3, [
      {resource_kind: 'table', display_name: 'lower.name'},
      {resource_kind: 'column', display_name: 'value', display_path: ['db', 'lower.name', 'value']},
    ]);
    const state = EditorState.create({doc: 'SELECT "lower.name".', extensions: [sql(config)]});
    const result = schemaCompletionSource(config)(new CompletionContext(state, state.doc.length, true));
    expect(result?.options.map(option => option.apply)).toContain('"value"');
  });
});


it('completes public packages/routines and native type/sequence names', () => {
  const config=firebirdSQLConfig('SELECT',3,[{resource_kind:'package',display_name:'P'},
    {resource_kind:'function',display_name:'F',package_name:'P',parameters:[{name:'N'}]},
    {resource_kind:'sequence',display_name:'S'},{resource_kind:'domain',display_name:'D'}]);
  expect(config.schema.P.children[0]).toMatchObject({label:'F',apply:'"F"',type:'function'});
  expect(config.schema.S.self.type).toBe('variable');
  expect(config.schema.D.self.type).toBe('type');
});
