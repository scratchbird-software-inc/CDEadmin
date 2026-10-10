import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, TextField} from '@mui/material';
import FormReference from '../navigation/FormReference';

export default function LanguageSourceEditor({language, source, onChange, post, ensureSession, databaseTargetId, disabled=false, onScriptLock}) {
  const [validation, setValidation] = useState(null);
  const [plan, setPlan] = useState(null);
  const [preparedSource, setPreparedSource] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [checking, setChecking] = useState(false);
  const generation = useRef(0);
  const mounted = useRef(true);
  const inFlight = useRef(false);
  useEffect(() => {generation.current++;setValidation(null);}, [source, language?.language_profile]);
  useEffect(() => {mounted.current=true;return () => {mounted.current=false;generation.current++;};}, []);
  const send = (payload) => post({...payload, database_target_id: databaseTargetId});
  const inspect = async (script) => {
    const current=++generation.current;setChecking(true);setError('');
    try {
      if (script && plan?.plan_id) {
        await send({action:'native_script_discard',plan_id:plan.plan_id});
      }
      const result=await send({action:script ? 'native_script_prepare' : 'source_validate',
        session_id:await ensureSession(), source});
      if (!mounted.current || current!==generation.current) return;
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
  return <FormReference formKey="query-editor">
    <TextField multiline fullWidth minRows={7} maxRows={14} value={source}
      disabled={disabled || running || Boolean(plan?.occurrence_id)}
      onChange={event => onChange(event.target.value)} inputProps={{'aria-label':'Query source'}}
      label="Query source"
      helperText={'Validation: '+(language?.tooling?.validation_authority || 'unavailable')+'. Native execution remains the grammar/semantic authority.'} />
    <Button disabled={disabled || checking || running || Boolean(plan?.occurrence_id)} onClick={() => inspect(false)}>Check source</Button>
    {language?.tooling?.script_framing && <FormReference formKey="script">
      <Button disabled={disabled || checking || running || Boolean(plan?.occurrence_id)} onClick={() => inspect(true)}>Preview script</Button>
      <Button disabled={!plan?.plan_id || !['ready','waiting'].includes(plan.state) || preparedSource!==source || running || disabled}
        onClick={() => {setRunning(true);onScriptLock(true);}}>Run / resume retained script</Button>
      <Button disabled={!plan?.plan_id || ['stopped','complete'].includes(plan.state)} onClick={stop}>Stop after current statement</Button>
      {plan && <Box component="pre" aria-label="Script progress" sx={{whiteSpace:'pre-wrap'}}>{JSON.stringify({plan_id:plan.plan_id,state:plan.state,next_statement:plan.next_statement,statements:plan.statements?.map(s=>({ordinal:s.ordinal,source:s.source})),history:plan.history,stop_reason:plan.stop_reason},null,2)}</Box>}
    </FormReference>}
    {error && <Alert severity="error">{error}</Alert>}
    {validation && <Box role="status">
      <Alert severity={validation.diagnostics?.length ? 'warning' : 'info'}>{validation.scope || validation.authority} Full grammar validation: {validation.grammar_valid===true ? 'confirmed by native validator' : 'not certified'}.</Alert>
      {(validation.diagnostics || []).map((d,i)=><Alert key={i} severity="error">{d.line}:{d.column} — {d.message}</Alert>)}
    </Box>}
  </FormReference>;
}
LanguageSourceEditor.propTypes={language:PropTypes.object,source:PropTypes.string.isRequired,onChange:PropTypes.func.isRequired,post:PropTypes.func.isRequired,ensureSession:PropTypes.func.isRequired,databaseTargetId:PropTypes.string,disabled:PropTypes.bool,onScriptLock:PropTypes.func.isRequired};
