import {SQLDialect, MySQL, PostgreSQL, SQLite, StandardSQL} from '@codemirror/lang-sql';
import {useEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, TextField} from '@mui/material';
import FormReference from '../navigation/FormReference';
import CodeEditor from './CodeEditor';
import {formatFirebird} from './firebirdFormatting';
import {firebirdSQLConfig} from './firebirdSyntax';
import {duckdbSQLConfig} from './duckdbSyntax';
import {firebirdExecution} from './firebirdExecution';
import {duckdbExecution} from './duckdbExecution';
import {readSourceFile, saveSourceFile} from './scriptFiles';

export default function LanguageSourceEditor({language, source, onChange, post, ensureSession, databaseTargetId, disabled=false, onScriptLock, historySensitive=false, clientSqlDialect=3, resources, onExecute, parameterSource='{}'}) {
  const [syntax, setSyntax] = useState(true);
  const [completion, setCompletion] = useState(null);
  const [prepared, setPrepared] = useState(null);
  const plainEditor = useRef(null);
  const syntaxEditor = useRef(null);
  const firebird = language?.language_profile === 'firebird-sql';
  const sqlConfig = useMemo(() => firebirdSQLConfig(language?.editor?.keywords || '', clientSqlDialect, completion?.resources || resources, language?.editor?.reserved_words),
    [language?.editor, clientSqlDialect, resources, completion]);
  const nativeProfile = language?.language_profile || '';
  const scriptParameters = useMemo(() => {
    try {const value = JSON.parse(parameterSource || '{}');
      return value && typeof value === 'object' && Object.keys(value).length === 0 ? value : null;
    } catch {return null;}
  }, [parameterSource]);
  const jsonLanguage = /json|keyvalue|query-api|query-search-api|query-dsl|resp3/.test(nativeProfile);
  const nativeDialect = /mysql|maria|tidb|vitess|dolt/.test(nativeProfile) ? MySQL :
    /postgres|cockroach|ysql|xtdb/.test(nativeProfile) ? PostgreSQL : /sqlite/.test(nativeProfile) ? SQLite : StandardSQL;
  const nativeConfig = useMemo(() => ({dialect: language?.editor?.keywords ?
    SQLDialect.define({keywords: language.editor.keywords}) : nativeDialect}), [language?.editor, nativeDialect]);
  const duckdbConfig = useMemo(() => duckdbSQLConfig(language?.editor, resources), [language?.editor, resources]);
  const [validation, setValidation] = useState(null);
  const [plan, setPlan] = useState(null);
  const [preparedSource, setPreparedSource] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [checking, setChecking] = useState(false);
  const generation = useRef(0);
  const mounted = useRef(true);
  const inFlight = useRef(false);
  const fileGeneration = useRef(0);
  useEffect(() => {fileGeneration.current++;}, [source, nativeProfile, databaseTargetId, disabled, running, plan]);
  const loadFile = async event => {
    const file = event.target.files?.[0]; event.target.value = '';
    if (!file || disabled || running || plan?.occurrence_id || plan?.unresolved) return;
    const token = ++fileGeneration.current;
    try {
      const text = await readSourceFile(file);
      if (mounted.current && token === fileGeneration.current) {onChange(text); setError('');}
    } catch (failure) {if (mounted.current && token === fileGeneration.current) setError(failure.message);}
  };
  const completionGeneration = useRef(0);
  useEffect(() => {
    completionGeneration.current++; setCompletion(null);
    return () => {completionGeneration.current++;};
  }, [post, databaseTargetId]);
  const loadCompletion = async () => {
    const current = ++completionGeneration.current;
    setChecking(true); setError('');
    try {
      const value = await post({action: 'firebird_editor_metadata', database_target_id: databaseTargetId});
      if(current === completionGeneration.current) setCompletion(value);
    } catch(failure) {if(current === completionGeneration.current) setError(failure.message);}
    finally {if(current === completionGeneration.current) setChecking(false);}
  };
  const format = () => {
    if(disabled || running || plan?.occurrence_id) return;
    try {onChange(formatFirebird(source)); setError('');}
    catch(failure) {setError(failure.message);}
  };
  const prepareExecution = async (mode) => {
    const current = ++generation.current;
    setChecking(true);
    try {
      const selection = syntax ? syntaxEditor.current?.state.selection.main : null;
      const cursor = selection?.head ?? (plainEditor.current?.selectionDirection === 'backward' ?
        plainEditor.current.selectionStart : (plainEditor.current?.selectionEnd ?? 0));
      const from = mode === 'selection' ? (selection?.from ?? plainEditor.current?.selectionStart ?? 0) : cursor;
      const to = mode === 'selection' ? (selection?.to ?? plainEditor.current?.selectionEnd ?? from) : cursor;
      const value = firebird ? firebirdExecution(source, mode, from, to) :
        await duckdbExecution(source, mode, from, to, async input => send({
          action: 'source_validate', session_id: await ensureSession(), source: input,
        }));
      if (!mounted.current || current !== generation.current) return;
      setPrepared({...value, original: source});
      setError('');
    } catch(failure) {
      if (mounted.current && current === generation.current) {setPrepared(null); setError(failure.message);}
    } finally {if (mounted.current) setChecking(false);}
  };
  useEffect(() => {generation.current++;setValidation(null);setPrepared(null);}, [source, language?.language_profile, databaseTargetId]);
  useEffect(() => {mounted.current=true;return () => {mounted.current=false;generation.current++;};}, []);
  const send = (payload) => post({...payload, database_target_id: databaseTargetId});
  const inspect = async (script, executionSource=source) => {
    const current=++generation.current;setChecking(true);setError('');
    try {
      if (script && !scriptParameters) throw new Error('Retained scripts require empty parameter bindings.');
      if (script && plan?.plan_id) {
        await send({action:'native_script_discard',plan_id:plan.plan_id});
      }
      const result=await send({action:script ? 'native_script_prepare' : 'source_validate',
        session_id:await ensureSession(), source:executionSource,
        ...(script ? {parameters: scriptParameters} : {}),
        ...(script && language?.language_profile === 'firebird-sql' ?
          {history_sensitive: historySensitive, client_sql_dialect: clientSqlDialect} : {}),
        ...(script && ['mysql-sql', 'mariadb-sql', 'duckdb-sql'].includes(language?.language_profile) ? {history_sensitive: historySensitive} : {})});
      if (!mounted.current || current!==generation.current) return;
      if(result.sql_history?.warning) setError(result.sql_history.warning);
      if(script){setPlan(result);setPreparedSource(source);setValidation(result.validation || null);}
      else setValidation(result);
    } catch(e){if(mounted.current && current===generation.current)setError(e.message);}
    finally {if(mounted.current)setChecking(false);}
  };
  useEffect(() => {
    if(!running || !plan || inFlight.current) return undefined;
    if(['complete','stopped','invalid'].includes(plan.state)) {
      setRunning(false);onScriptLock(Boolean(plan.unresolved));return undefined;
    }
    const timer=setTimeout(async () => {
      inFlight.current=true;
      try {
        const result=await send({action:'native_script_advance',plan_id:plan.plan_id,revision:plan.revision});
        if(mounted.current) {
          setPlan(result);
          if(result.observation_unavailable){setRunning(false);setError('Observation unavailable. Resume checks this execution; it does not replay it.');}
        }
      } catch(e){if(mounted.current){setRunning(false);setError(e.message+' — do not rerun; resume the retained plan.');}}
      finally{inFlight.current=false;}
    }, plan.state==='waiting' ? 400 : 0);
    return () => clearTimeout(timer);
  }, [running, plan]);
  const stop = async () => {
    try {
      const result=await send({action:'native_script_stop',plan_id:plan.plan_id});
      if(mounted.current){setPlan(result);setRunning(result.state==='waiting');onScriptLock(result.state==='waiting' || Boolean(result.unresolved));}
    } catch(e){if(mounted.current)setError(e.message);}
  };
  return <FormReference formKey="query-editor" sx={{display: 'flex', flexDirection: 'column', height: '50%',
    flex: '0 0 auto', minHeight: 160, maxHeight: '60%', resize: 'vertical', overflow: 'auto'}}>
    <Box component="details" sx={{flexShrink: 0, maxHeight: '45%', overflow: 'auto'}}><summary>Source tools</summary>
      <Button component="label" disabled={disabled || running || Boolean(plan?.occurrence_id) || Boolean(plan?.unresolved)}>
        Load source file<input hidden type="file" accept={jsonLanguage ? '.json,.txt,application/json,text/plain' : '.sql,.txt,text/plain,application/sql'}
          aria-label="Load source file" disabled={disabled || running || Boolean(plan?.occurrence_id) || Boolean(plan?.unresolved)} onChange={loadFile} />
      </Button>
      <Button disabled={!source} onClick={() => {
        try {saveSourceFile(source, (nativeProfile.replace(/[^a-z0-9_-]/gi, '_') || 'query') + (jsonLanguage ? '.json' : '.sql')); setError('');}
        catch (failure) {setError(failure.message);}
      }}>Save source file</Button>
      {(firebird || nativeProfile === 'duckdb-sql') && <Box>
        {firebird && <><Button disabled={disabled || running} onClick={() => setSyntax(!syntax)}>{syntax ? 'Plain text editor' : 'Syntax editor'}</Button>
          <Button disabled={disabled || running || Boolean(plan?.occurrence_id)} onClick={format}>Format Firebird source</Button></>}
        {['selection', 'current', 'from-cursor'].map(mode => <Button key={mode}
          disabled={disabled || checking || running || !onExecute || Boolean(plan?.occurrence_id) || Boolean(plan?.unresolved)}
          onClick={() => prepareExecution(mode)}>{({'selection': 'Prepare selection', 'current': 'Prepare current statement', 'from-cursor': 'Prepare from cursor'})[mode]}</Button>)}
      </Box>}
      {(firebird || nativeProfile === 'duckdb-sql') && prepared?.original === source && <Box sx={{my: 1}}>
        <Alert severity="info">Review the prepared {prepared.scriptMode ? 'script, including inherited client settings and any transaction commands' : 'native statement'}.
          {prepared.scriptMode ? ' Scripts require empty parameter bindings.' : ' Existing ordered parameters apply.'}
        No SQL has been executed by preparing this source.</Alert>
        <TextField multiline fullWidth minRows={3} maxRows={10} label="Prepared execution source"
          value={prepared.source} InputProps={{readOnly: true}} />
        <Button disabled={disabled || checking || running || !onExecute} onClick={() => {
          const value = prepared; setPrepared(null);
          if (!firebird && value.scriptMode) inspect(true, value.source);
          else onExecute(value.source, value.scriptMode);
        }}>{!firebird && prepared.scriptMode ? 'Preview prepared script' : 'Run prepared source'}</Button>
      </Box>}
      <Button disabled={disabled || checking || running || Boolean(plan?.occurrence_id)} onClick={() => inspect(false)}>Check source</Button>
      {language?.tooling?.script_framing && <FormReference formKey="script">
        {!scriptParameters && <Alert severity="info">Clear query bindings to prepare or run a retained script.</Alert>}
        <Button disabled={disabled || checking || running || Boolean(plan?.occurrence_id)} onClick={() => inspect(true)}>Preview script</Button>
        <Button disabled={!plan?.plan_id || !['ready','waiting'].includes(plan.state) || preparedSource!==source || running || disabled || !scriptParameters}
          onClick={() => {setRunning(true);onScriptLock(true);}}>Run / resume retained script</Button>
        <Button disabled={!plan?.plan_id || ['stopped','complete'].includes(plan.state)} onClick={stop}>Stop after current statement</Button>
        {plan && <Box component="pre" aria-label="Script progress" sx={{whiteSpace:'pre-wrap'}}>{JSON.stringify({plan_id:plan.plan_id,state:plan.state,next_statement:plan.next_statement,statements:plan.statements?.map(s=>({ordinal:s.ordinal,source:s.source})),history:plan.history,stop_reason:plan.stop_reason},null,2)}</Box>}
      </FormReference>}
      {error && <Alert severity="error">{error}</Alert>}
      {validation && <Box role="status">
        <Alert severity={validation.diagnostics?.length ? 'warning' : 'info'}>{validation.scope || validation.authority} SQL grammar: {validation.grammar_valid===true ? 'accepted by the reported parser' : validation.grammar_valid===false ? 'rejected' : 'not checked'}.</Alert>
        {(validation.diagnostics || []).map((d,i)=><Alert key={i} severity="error">{d.line}:{d.column} — {d.message}</Alert>)}
      </Box>}
    </Box>
    {syntax ? <>
      <Box sx={{flex: '1 1 auto', minHeight: 100, overflow: 'auto'}}><CodeEditor label="Query source" value={source} onChange={onChange}
        language={jsonLanguage ? 'json' : firebird ? 'firebird' : 'sql'} sqlConfig={firebird ? sqlConfig : nativeProfile === 'duckdb-sql' ? duckdbConfig : nativeConfig} autocomplete autocompleteOnKeyPress
        currEditor={editor => {syntaxEditor.current = editor;}}
        formatOverride={firebird ? format : undefined} disabled={disabled || running || Boolean(plan?.occurrence_id)} /></Box>
      {firebird && <Button disabled={disabled || checking || running} onClick={loadCompletion}>Refresh metadata completion</Button>}

      {completion && <Alert severity={completion.truncated ? 'warning' : 'info'}>{completion.coverage}.
        {completion.resources.length} of {completion.visible_resource_count} visible resources loaded.
        {completion.truncated ? ' Completion is truncated.' : ''}</Alert>}
    </> : <TextField multiline fullWidth minRows={7} maxRows={14} value={source} inputRef={plainEditor}
      disabled={disabled || running || Boolean(plan?.occurrence_id)}
      onChange={event => onChange(event.target.value)} inputProps={{'aria-label':'Query source'}}
      label="Query source"
      helperText={'Validation: '+(language?.tooling?.validation_authority || 'unavailable')+'. Native execution remains the grammar/semantic authority.'} />}
  </FormReference>;
}
LanguageSourceEditor.propTypes={parameterSource:PropTypes.string,onExecute:PropTypes.func,resources:PropTypes.array,historySensitive:PropTypes.bool,clientSqlDialect:PropTypes.number,language:PropTypes.object,source:PropTypes.string.isRequired,onChange:PropTypes.func.isRequired,post:PropTypes.func.isRequired,ensureSession:PropTypes.func.isRequired,databaseTargetId:PropTypes.string,disabled:PropTypes.bool,onScriptLock:PropTypes.func.isRequired};
