import {EditorState} from '@codemirror/state';
import {CompletionContext} from '@codemirror/autocomplete';
import {sql} from '@codemirror/lang-sql';
import {nativeSQLConfig, nativeCompletionContext, registerNativeCompletion} from '../../../pgadmin/static/js/cdeadmin_ui/editors/nativeCompletion';
import {nativeSchemaCompletion} from '../../../pgadmin/static/js/cdeadmin_ui/editors/nativeScopes';
import {nativeTokens} from '../../../pgadmin/static/js/cdeadmin_ui/editors/nativeLexing';

const metadata = (engine, extra={}) => ({context:{engine, catalog:'owned', schema:'main', default_schema:'main', keywords:'WITH SELECT FROM WHERE AS JOIN ON', ...extra},
  resources:[['table',['main','one']],['column',['main','one','first']],['table',['main','two']],['column',['main','two','second']]]
    .map(([resource_kind,display_path]) => ({resource_kind,display_path:engine==='duckdb'?['owned',...display_path]:display_path,display_name:display_path.at(-1)}))});
function suggestions(source, data, previous=data, position=source.length) {
  const state=EditorState.create({doc:source, selection:{anchor:position}, extensions:sql(nativeSQLConfig(previous))});
  const observed=nativeCompletionContext(data,new CompletionContext(state,position,true));
  return nativeSchemaCompletion(observed.config,observed.context);
}

test.each(['SELECT a.info. FROM one a','SELECT a.info."outer ü". FROM one a'])('DuckDB native nested members resolve alias paths in %s', source => {
  const data=metadata('duckdb');
  data.resources.push({resource_kind:'column',display_path:['owned','main','one','info'],detail:'STRUCT'},
    {resource_kind:'field',display_path:['owned','main','one','info','outer ü'],detail:'STRUCT'},
    {resource_kind:'field',display_path:['owned','main','one','info','outer ü','inner.dot'],detail:'BIGINT'});
  const position=source.indexOf(' FROM');
  const result=suggestions(source,data,data,position);
  const label=source.includes('outer ü') ? 'inner.dot' : 'outer ü';
  expect(result.options).toEqual([expect.objectContaining({label,apply:'"'+label+'"',type:'property'})]);
});

test.each([
  'WITH q AS (SELECT * FROM one) SELECT q.info.| FROM q',
  'WITH q AS (SELECT o.info AS renamed FROM one o) SELECT q.renamed.| FROM q',
  'WITH q(renamed) AS (SELECT info FROM one) SELECT q.renamed.| FROM q',
  'SELECT q.renamed.| FROM (SELECT o.info AS renamed FROM one o) q',
])('DuckDB nested native fields survive direct CTE/derived projection in %s', marked => {
  const data=metadata('duckdb');
  data.resources.push({resource_kind:'column',display_path:['owned','main','one','info'],detail:'STRUCT'},
    {resource_kind:'field',display_path:['owned','main','one','info','Field ü'],detail:'BIGINT'});
  const result=suggestions(marked.replace('|',''),data,data,marked.indexOf('|'));
  expect(result.options).toEqual([expect.objectContaining({label:'Field ü',apply:'"Field ü"',type:'property',detail:'BIGINT'})]);
});

test('DuckDB native STRUCT star retains nested member types in a CTE', () => {
  const data=metadata('duckdb');
  data.resources.push({resource_kind:'column',display_path:['owned','main','one','info'],detail:'STRUCT("outer ü" STRUCT("inner.dot" BIGINT))'},
    {resource_kind:'field',display_path:['owned','main','one','info','outer ü'],detail:'STRUCT("inner.dot" BIGINT)'},
    {resource_kind:'field',display_path:['owned','main','one','info','outer ü','inner.dot'],detail:'BIGINT'});
  const marked='WITH q AS (SELECT info.* FROM one) SELECT q."outer ü".| FROM q';
  const result=suggestions(marked.replace('|',''),data,data,marked.indexOf('|'));
  expect(result.options).toEqual([expect.objectContaining({label:'inner.dot',apply:'"inner.dot"',detail:'BIGINT'})]);
});

test.each(['mysql','mariadb'])('%s completion reparses newly observed ANSI_QUOTES before CTE/alias resolution', engine => {
  const source='WITH c AS (SELECT t.* FROM "one" t) SELECT * FROM c WHERE c.';
  const result=suggestions(source,metadata(engine,{sql_mode:'ANSI_QUOTES,NO_BACKSLASH_ESCAPES'}),metadata(engine));
  expect(result.options).toEqual(expect.arrayContaining([expect.objectContaining({label:'first',apply:'"first"'})]));
  expect(result.options.some(item => item.label==='second')).toBe(false);
});

test('native callback uses the returned mode without waiting for React to reconfigure the editor', async () => {
  const source='WITH c AS (SELECT t.* FROM "one" t) SELECT * FROM c WHERE c.';
  const state=EditorState.create({doc:source,selection:{anchor:source.length},extensions:sql(nativeSQLConfig(metadata('mysql')))});
  let callback;
  const settings={active:true,blocked:false,scope:'mysql:owned',nativeProfile:'mysql-sql',databaseTargetId:'owned',
    ensureSession:async ()=>'retained',post:jest.fn().mockResolvedValue({editor_context:metadata('mysql',{sql_mode:'ANSI_QUOTES'})}),onMetadata:jest.fn(),onError:jest.fn()};
  registerNativeCompletion({state,registerAutocomplete:fn=>{callback=fn;}},()=>settings);
  const available=jest.fn(), result=await callback(new CompletionContext(state,source.length,true),available);
  expect(result.options.some(item=>item.label==='first')).toBe(true);
  expect(settings.onError).not.toHaveBeenCalled();
  expect(available).toHaveBeenCalledTimes(1);
});

test.each([['"T"','first'],['"t"','second']])('PostgreSQL CTE star projection preserves distinct quoted alias %s', (alias,column) => {
  const source=`WITH c AS (SELECT ${alias}.* FROM one AS "T" JOIN two AS "t" ON true) SELECT * FROM c WHERE c.`;
  expect(suggestions(source,metadata('postgresql')).options.map(item=>item.label)).toEqual([column]);
});

test('PostgreSQL unquoted names fold lower and do not resolve a differently cased quoted relation', () => {
  const data=metadata('postgresql');
  data.resources=data.resources.slice(0,2).map(item=>({...item,display_path:item.display_path.map(part=>part==='one'?'Mixed':part)}));
  expect(suggestions('WITH C AS (SELECT t.* FROM mixed t) SELECT * FROM C WHERE C.',data).options).toEqual([]);
  expect(suggestions('WITH C AS (SELECT t.* FROM "Mixed" t) SELECT * FROM C WHERE C.',data).options[0].label).toBe('first');
});

test.each(['duckdb','sqlite'])('%s quoted paths remain insensitive to identifier case', engine => {
  expect(suggestions('SELECT * FROM "ONE" AS t WHERE t.',metadata(engine)).options[0].label).toBe('first');
});

test.each(['mysql','mariadb','duckdb','sqlite','postgresql'])('%s hidden columns stay queryable but are omitted from CTE star expansion', engine => {
  const data=metadata(engine);
  const owner=data.resources[1].display_path.slice(0,-1);
  data.resources.push({resource_kind:'column',display_path:[...owner,'hidden'],display_name:'hidden',hidden_from_star:true});
  expect(suggestions('SELECT * FROM one t WHERE t.',data).options.map(item=>item.label)).toEqual(['first','hidden']);
  for (const projection of ['*', 't.*']) {
    expect(suggestions(`WITH c AS (SELECT ${projection} FROM one t) SELECT c.`,data).options.map(item=>item.label)).toEqual(['first']);
  }
  expect(suggestions('WITH c AS (SELECT t.hidden FROM one t) SELECT c.',data).options.map(item=>item.label)).toEqual(['hidden']);
});

test.each([1,3])('Firebird dialect %s DB_KEY suggestions do not leak into star projection', sql_dialect => {
  const data={context:{engine:'firebird',sql_dialect,keywords:'WITH SELECT FROM WHERE AS',reserved_words:[]},resources:[
    {resource_kind:'table',display_name:'WIDGETS',display_path:['WIDGETS']},
    {resource_kind:'column',display_name:'ID',display_path:['WIDGETS','ID']},
    {resource_kind:'column',display_name:'RDB$DB_KEY',display_path:['WIDGETS','RDB$DB_KEY'],hidden_from_star:true,native_identifier_token:true}]};
  expect(suggestions('SELECT * FROM WIDGETS t WHERE t.',data).options.map(item=>item.label)).toEqual(['ID','RDB$DB_KEY']);
  expect(suggestions('SELECT * FROM WIDGETS t WHERE t.',data).options.find(item=>item.label==='RDB$DB_KEY').apply).toBe('RDB$DB_KEY');
  expect(suggestions('WITH c AS (SELECT t.* FROM WIDGETS t) SELECT c.',data).options.map(item=>item.label)).toEqual(['ID']);
  expect(suggestions('WITH c AS (SELECT t.RDB$DB_KEY FROM WIDGETS t) SELECT c.',data).options.map(item=>item.label)).toEqual(['RDB$DB_KEY']);
});

test.each(['postgresql','duckdb','sqlite'])('%s identifier folding preserves distinct non-ASCII names', engine => {
  const data=metadata(engine);
  data.resources=data.resources.slice(0,2).map(item=>({...item,display_path:item.display_path.map(part=>part==='one'?'Ä':part)}));
  expect(suggestions('SELECT * FROM Ä t WHERE t.',data).options[0].label).toBe('first');
  expect(suggestions('SELECT * FROM ä t WHERE t.',data)).toBeNull();
  data.resources=data.resources.map(item=>({...item,display_path:item.display_path.map(part=>part==='Ä'?'🚀':part)}));
  expect(suggestions('SELECT * FROM 🚀 t WHERE t.',data).options[0].label).toBe('first');
});

test.each(['postgresql','duckdb'])('%s non-ASCII dollar tags protect exact literal content from formatting', engine => {
  expect(nativeTokens('SELECT $é$ exact literal\n  spaces ; $é$',{engine})).toEqual(['SELECT','$é$ exact literal\n  spaces ; $é$']);
});

test.each(['mysql','mariadb'])('%s relation and alias case follows native lower_case_table_names', engine => {
  expect(suggestions('SELECT * FROM ONE t WHERE t.',metadata(engine,{lower_case_table_names:0}))).toBeNull();
  expect(suggestions('SELECT * FROM one T WHERE t.',metadata(engine,{lower_case_table_names:0}))).toBeNull();
  for (const mode of [1,2]) expect(suggestions('SELECT * FROM ONE T WHERE t.',metadata(engine,{lower_case_table_names:mode})).options[0].label).toBe('first');
});

test('qualified escaped names resolve through the exact catalog and schema', () => {
  const data=metadata('mysql');
  data.resources=data.resources.slice(0,2).map(item=>({...item,display_path:item.display_path.map(part=>part==='one'?'odd`table':part)}));
  expect(suggestions('SELECT main.`odd``table`.',data).options[0].label).toBe('first');
});

test('quoted paths decode doubled identifier delimiters and preserve exact insertion', () => {
  const data=metadata('mysql');
  data.resources=data.resources.slice(0,2).map(item=>({...item,display_path:item.display_path.map(part=>part==='one'?'odd`table':part==='first'?'odd`column':part)}));
  const result=suggestions('SELECT * FROM `odd``table` AS t WHERE t.',data);
  expect(result.options).toEqual([expect.objectContaining({label:'odd`column',apply:'`odd``column`'})]);
});

test('Firebird dialect 1 folds unquoted CTEs/aliases upper and inserts valid unquoted columns', () => {
  const data={context:{engine:'firebird',sql_dialect:1,keywords:'WITH SELECT FROM WHERE AS',reserved_words:[]},resources:[
    {resource_kind:'table',display_name:'WIDGETS',display_path:['WIDGETS']},
    {resource_kind:'column',display_name:'EXACT_VALUE',display_path:['WIDGETS','EXACT_VALUE']} ]};
  const result=suggestions('WITH c AS (SELECT t.* FROM widgets t) SELECT * FROM c WHERE c.',data);
  expect(result.options).toEqual([expect.objectContaining({label:'EXACT_VALUE',apply:'EXACT_VALUE'})]);
});

test('CTEs and aliases in sibling statements and subqueries do not leak', () => {
  const data=metadata('sqlite');
  expect(suggestions('WITH private_cte(x) AS (SELECT 1) SELECT x FROM private_cte; SELECT ',data).options.some(item=>item.label==='private_cte')).toBe(false);
  expect(suggestions('SELECT (SELECT first FROM one private_alias) FROM two WHERE private_alias.',data)).toBeNull();
});

test('inner query aliases shadow the enclosing query without leaking into its sibling', () => {
  const data=metadata('sqlite'), source='SELECT (SELECT t. FROM two t) FROM one t WHERE t.';
  expect(suggestions(source,data,data,source.indexOf('t.')+2).options[0].label).toBe('second');
  expect(suggestions(source,data).options[0].label).toBe('first');
});

test('projection completion requires a named column or an actual explicit/implicit alias', () => {
  const data=metadata('postgresql');
  expect(suggestions('WITH c AS (SELECT first + first FROM one) SELECT c.',data).options).toEqual([]);
  expect(suggestions('WITH c AS (SELECT first + first AS calculated FROM one) SELECT c.',data).options[0].label).toBe('calculated');
  expect(suggestions('WITH c AS (SELECT first + first calculated FROM one) SELECT c.',data).options[0].label).toBe('calculated');
});

test('qualification continues across whitespace and comments after the dot', () => {
  expect(suggestions('SELECT * FROM one t WHERE t. /* comment */ ',metadata('sqlite')).options[0].label).toBe('first');
});

test.each(['-- comment', 'SELECT \'literal'])('completion stays out of native string/comment tokens: %s', source => {
  expect(suggestions(source,metadata('mysql'))).toBeNull();
});
