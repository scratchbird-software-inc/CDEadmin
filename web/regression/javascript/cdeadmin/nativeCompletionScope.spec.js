import {EditorState} from '@codemirror/state';
import {CompletionContext} from '@codemirror/autocomplete';
import {sql} from '@codemirror/lang-sql';
import {nativeSQLConfig, nativeCompletionContext, registerNativeCompletion} from '../../../pgadmin/static/js/cdeadmin_ui/editors/nativeCompletion';
import {nativeSchemaCompletion} from '../../../pgadmin/static/js/cdeadmin_ui/editors/nativeScopes';
import {nativeTokens} from '../../../pgadmin/static/js/cdeadmin_ui/editors/nativeLexing';
import fs from 'fs';

const metadata = (engine, extra={}) => ({context:{engine, catalog:'owned', schema:'main', default_schema:'main', keywords:'WITH SELECT FROM WHERE AS JOIN ON', ...extra},
  resources:[['table',['main','one']],['column',['main','one','first']],['table',['main','two']],['column',['main','two','second']]]
    .map(([resource_kind,display_path]) => ({resource_kind,display_path:engine==='duckdb'?['owned',...display_path]:display_path,display_name:display_path.at(-1)}))});
function suggestions(source, data, previous=data, position=source.length) {
  const state=EditorState.create({doc:source, selection:{anchor:position}, extensions:sql(nativeSQLConfig(previous))});
  const observed=nativeCompletionContext(data,new CompletionContext(state,position,true));
  return nativeSchemaCompletion(observed.config,observed.context);
}

(process.env.CDEADMIN_DUCKDB_NATIVE_EDITOR_FIXTURE ? describe : describe.skip)('DuckDB native observed editor fixture',()=> {
  test('inserts exactly the members independently bound and executed by DuckDB',()=> {
    const fixture=JSON.parse(fs.readFileSync(process.env.CDEADMIN_DUCKDB_NATIVE_EDITOR_FIXTURE,'utf8'));
    expect(fixture.metadata.context.engine).toBe('duckdb');
    expect(fixture.cases).toHaveLength(17);
    for(const example of fixture.cases) {
      const source=example.marked.replace('|',''),position=example.marked.indexOf('|');
      const result=suggestions(source,fixture.metadata,fixture.metadata,position);
      if(!result)throw new Error('No completion for native fixture: '+example.marked);
      expect(result.options.map(({label,apply,detail})=>({label,apply,detail}))).toEqual(example.expected);
      expect(source.slice(0,result.from)+result.options[0].apply+source.slice(result.to)).toBe(example.native_sql);
    }
  });
});

(process.env.CDEADMIN_NATIVE_IDENTIFIER_FIXTURES ? describe : describe.skip)('native MySQL-family qualified identifiers',()=> {
  test('inserts every independently bound native result column across client interfaces and modes',()=> {
    const paths=JSON.parse(process.env.CDEADMIN_NATIVE_IDENTIFIER_FIXTURES);
    expect(paths).toHaveLength(2);
    for(const path of paths) {
      const fixture=JSON.parse(fs.readFileSync(path,'utf8'));
      expect(fixture.interfaces).toHaveLength(2);
      for(const observed of fixture.interfaces) {
        expect(observed.cases).toHaveLength(5);
        for(const example of observed.cases) {
          const source=example.marked.replace('|',''),position=example.marked.indexOf('|');
          const result=suggestions(source,observed.metadata,observed.metadata,position);
          if(!result)throw new Error('No '+fixture.engine+' '+observed.label+' completion: '+example.marked);
          expect(result.options.map(({label,apply,type})=>({label,apply,type}))).toEqual(example.expected);
          expect(result.options.map(option=>source.slice(0,result.from)+option.apply+source.slice(result.to))).toEqual(example.native_inserted_sql);
        }
      }
    }
  });
});

(process.env.CDEADMIN_SQLITE_IDENTIFIER_FIXTURE ? describe : describe.skip)('native SQLite identifier roles',()=> {
  test('inserts every independently bound SQLite name without executing metadata functions',()=> {
    const fixture=JSON.parse(fs.readFileSync(process.env.CDEADMIN_SQLITE_IDENTIFIER_FIXTURE,'utf8'));
    expect(fixture.metadata.context.engine).toBe('sqlite');expect(fixture.cases).toHaveLength(20);
    for(const example of fixture.cases) {
      const source=example.marked.replace('|',''),position=example.marked.indexOf('|');
      const result=suggestions(source,fixture.metadata,fixture.metadata,position);
      if(!result)throw new Error('No SQLite completion for '+example.marked);
      expect(result.options.map(({label,apply,type})=>({label,apply,type}))).toEqual(example.expected);
      expect(result.options.map(option=>source.slice(0,result.from)+option.apply+source.slice(result.to))).toEqual(example.native_inserted_sql);
    }
    for(const marked of fixture.negative_cases)
      expect(suggestions(marked.replace('|',''),fixture.metadata,fixture.metadata,marked.indexOf('|'))).toBeNull();
  });
});

const memberShape={kind:'struct',sql:'STRUCT("Field ü" BIGINT)',fields:[{name:'Field ü',type:{kind:'bigint',sql:'BIGINT'}}]};
const containerMetadata=()=> {
  const data=metadata('duckdb');
  for(const [label,shape] of Object.entries({items:{kind:'list',child:memberShape,sql:memberShape.sql+'[]'},
    fixed:{kind:'array',child:memberShape,size:2,sql:memberShape.sql+'[2]'},
    lookup:{kind:'map',key:{kind:'varchar',sql:'VARCHAR'},value:memberShape,sql:'MAP(VARCHAR, '+memberShape.sql+')'},
    matrix:{kind:'list',sql:memberShape.sql+'[][]',child:{kind:'list',sql:memberShape.sql+'[]',child:memberShape}}}))
    data.resources.push({resource_kind:'column',display_path:['owned','main','one',label],detail:shape.sql,native_type:shape});
  return data;
};

test.each([
  'SELECT n.items[1].| FROM one n', 'SELECT n.fixed[1].| FROM one n',
  'SELECT n.lookup[\'key\'].| FROM one n', 'SELECT n.matrix[1][2].| FROM one n',
  'SELECT n.items[1:2][1].| FROM one n', 'SELECT n.fixed[:][1].| FROM one n',
  'SELECT items[1].| FROM one', 'SELECT n.items[index + 1].| FROM one n',
  'WITH q AS (SELECT n.items[1] AS item FROM one n) SELECT q.item.| FROM q',
  'WITH q AS (SELECT n.items AS renamed FROM one n) SELECT q.renamed[1].| FROM q',
  'SELECT q.item.| FROM (SELECT n.fixed[1] AS item FROM one n) q',
  'SELECT n.items[1]."F|" FROM one n',
  'WITH "__proto__" AS (SELECT * FROM one) SELECT "__proto__".items[1].| FROM "__proto__"',
])('DuckDB observed container members resolve %s',marked=> {
  const data=containerMetadata(),result=suggestions(marked.replace('|',''),data,data,marked.indexOf('|'));
  expect(result.options).toEqual([expect.objectContaining({label:marked.includes('"F')?'"Field ü"':'Field ü',apply:'"Field ü"',detail:'BIGINT'})]);
});

test.each(['SELECT n.items.| FROM one n','SELECT n.fixed.| FROM one n','SELECT n.lookup.| FROM one n'])(
  'DuckDB container elements are not fabricated as dot fields in %s',marked=> {
    const data=containerMetadata();
    expect(suggestions(marked.replace('|',''),data,data,marked.indexOf('|')).options).toEqual([]);
  });

test('DuckDB does not guess an ambiguous unqualified indexed column',()=> {
  const data=containerMetadata();
  const item=data.resources.find(row=>row.display_path.at(-1)==='items');
  data.resources.push({...item,display_path:['owned','main','two','items']});
  const marked='SELECT items[1].| FROM one a JOIN two b ON true';
  expect(suggestions(marked.replace('|',''),data,data,marked.indexOf('|'))).toBeNull();
});

test.each([false,true])('DuckDB column resolution respects builtin-name collisions and ambiguity=%s',ambiguous=> {
  const data=containerMetadata(),item=data.resources.find(row=>row.display_path.at(-1)==='items');
  data.resources.push({...item,display_path:['owned','main','one','array_extract']},
    {resource_kind:'function',display_path:['system','main','array_extract'],detail:'native function'});
  if(ambiguous)data.resources.push({...item,display_path:['owned','main','two','array_extract']});
  const marked='SELECT array_extract[1].| FROM one a'+(ambiguous?' JOIN two b ON true':'');
  const result=suggestions(marked.replace('|',''),data,data,marked.indexOf('|'));
  if(ambiguous)expect(result).toBeNull();
  else expect(result.options).toEqual([expect.objectContaining({label:'Field ü',detail:'BIGINT'})]);
});

test.each(['SELECT n.select.| FROM one n',
  'WITH q AS (SELECT n.select AS part FROM one n) SELECT q.part.| FROM q'])(
  'DuckDB native keyword column labels resolve after a dot in %s',marked=> {
    const data=metadata('duckdb');
    data.resources.push({resource_kind:'column',display_path:['owned','main','one','select'],native_type:memberShape});
    expect(suggestions(marked.replace('|',''),data,data,marked.indexOf('|')).options).toEqual([
      expect.objectContaining({label:'Field ü',detail:'BIGINT'})]);
  });

test('DuckDB unknown prototype-named members remain unresolved',()=> {
  const data=containerMetadata(),marked='SELECT n.items[1].__proto__.| FROM one n';
  expect(suggestions(marked.replace('|',''),data,data,marked.indexOf('|'))).toBeNull();
});

const positionalMetadata=()=> {
  const data=metadata('duckdb');
  data.resources.push({resource_kind:'column',display_path:['owned','main','one','positional'],
    native_type:{kind:'struct',sql:'STRUCT(BIGINT, STRUCT("Field ü" BIGINT), STRUCT("Field ü" BIGINT)[])',
      positions:[{kind:'bigint',sql:'BIGINT'},memberShape,{kind:'list',sql:memberShape.sql+'[]',child:memberShape}]}});
  return data;
};
test.each(['SELECT n.positional[2].| FROM one n','SELECT n.positional[3][1].| FROM one n',
  'WITH q AS (SELECT n.positional[2] AS part FROM one n) SELECT q.part.| FROM q'])(
  'DuckDB positional tuple completion retains native ordinal types in %s',marked=> {
    const data=positionalMetadata();
    expect(suggestions(marked.replace('|',''),data,data,marked.indexOf('|')).options).toEqual([
      expect.objectContaining({label:'Field ü',apply:'"Field ü"',detail:'BIGINT'})]);
  });
test.each(['0','-1','4','1:2','ordinal','2.0','2e0'])('DuckDB does not infer a positional tuple member from %s',index=> {
  const data=positionalMetadata(),marked=`SELECT n.positional[${index}].| FROM one n`;
  expect(suggestions(marked.replace('|',''),data,data,marked.indexOf('|'))).toBeNull();
});

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

test.each(['mysql','mariadb'])('%s native qualified keyword table names retain CTE and alias columns',engine=> {
  const data=metadata(engine,{sql_mode:'ANSI_QUOTES'});
  data.resources=data.resources.map(row=>({...row,display_path:row.display_path.map(name=>name==='one'?'select':name)}));
  for(const marked of ['SELECT t.| FROM main.select t',
    'WITH q AS (SELECT t.* FROM main.select t) SELECT q.| FROM q',
    'SELECT q.| FROM (SELECT t.first FROM main.select t) q']) {
    const result=suggestions(marked.replace('|',''),data,data,marked.indexOf('|'));
    expect(result.options).toEqual([expect.objectContaining({label:'first',apply:'"first"'})]);
  }
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
