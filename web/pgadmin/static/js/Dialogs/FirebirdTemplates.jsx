import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, MenuItem, TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';

export default function FirebirdTemplates({post, resource, generation, databaseTargetId, onLoad, disabled}) {
  const [context, setContext] = useState(null), [family, setFamily] = useState('');
  const [template, setTemplate] = useState(''), [newName, setNewName] = useState('');
  const [rendered, setRendered] = useState(null), [error, setError] = useState(null), [busy, setBusy] = useState(false);
  const token = useRef(0);
  const call = (values={}) => post({action: 'firebird_object_templates', request: {
    resource_id: resource.resource_id, generation, database_target_id: databaseTargetId, ...values}});
  useEffect(() => {
    const serial = ++token.current;
    setContext(null); setRendered(null); setError(null); setBusy(true);
    call().then(value => {
      if (serial !== token.current) return;
      const first = value.templates.select ? 'select' : value.templates.definition ? 'definition' : 'execute-block';
      setContext(value); setFamily(first); setTemplate(value.templates[first]);
    }).catch(() => {if (serial === token.current) setError('Native template context is unavailable. Refresh the object catalog.');})
      .finally(() => {if (serial === token.current) setBusy(false);});
    return () => {token.current++;};
  }, [post, resource.resource_id, generation, databaseTargetId]);
  const preview = async () => {
    const serial = token.current; setBusy(true); setError(null); setRendered(null);
    try {const value = await call({template, new_name: newName}); if (serial === token.current) setRendered(value);}
    catch (failure) {if (serial === token.current) setError(failure.response?.data?.errormsg || 'Template rendering failed. Check substitutions and catalog freshness.');}
    finally {if (serial === token.current) setBusy(false);}
  };
  const save = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify({schema: 'scratchrobin.firebird.template@1', template}, null, 2)], {type: 'application/json'}));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'firebird-template.json'; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <Box sx={{p: 2, overflow: 'auto'}}>
    <FormReference formKey="firebird-code-templates" />
    <Alert severity="info">Native context: {resource.display_name}. Templates do not execute SQL. Review names, native permissions and parameters. PSQL and multi-statement definitions use native script controls. UPDATE/DELETE default to FALSE until you supply a row-key predicate.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    {context && <>
      <TextField select label="Native template" value={family} disabled={busy} onChange={event => {setFamily(event.target.value); setTemplate(context.templates[event.target.value]); setRendered(null);}}>
        {Object.keys(context.templates).map(key => <MenuItem key={key} value={key}>{key}</MenuItem>)}
      </TextField>
      <TextField label="New object name" value={newName} disabled={busy} onChange={event => {setNewName(event.target.value); setRendered(null);}} />
      <TextField fullWidth multiline minRows={6} maxRows={18} label="Reusable SQL template" value={template} disabled={busy} onChange={event => {setTemplate(event.target.value); setRendered(null);}} />
      <Box>Substitutions: object, columns, insert_columns, values, assignments, key_predicate, definition, new_object. Enclose a name in double braces.</Box>
      <Button disabled={busy || !template} onClick={save}>Save template file</Button>
      <Button component="label" disabled={busy}>Load template file
        <input type="file" hidden aria-label="Reusable template file" disabled={busy} onChange={async event => {
          const file = event.target.files?.[0]; event.target.value = ''; if (!file) return;
          const serial = token.current;
          try {
            if (file.size > 128 * 1024) throw new Error();
            const value = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(await file.arrayBuffer()));
            if (value.schema !== 'scratchrobin.firebird.template@1' || typeof value.template !== 'string' || Object.keys(value).sort().join(',') !== 'schema,template') throw new Error();
            if (serial === token.current) {setTemplate(value.template); setRendered(null); setError(null);}
          } catch {if (serial === token.current) setError('Load a UTF-8 ScratchRobin template JSON file, maximum 128 KiB.');}
        }} />
      </Button>
      <Button disabled={busy || !template} onClick={preview}>Render template preview</Button>
      {context.definition_unavailable && <Alert severity="warning">Native definition unavailable: {context.definition_unavailable}</Alert>}
    </>}
    {rendered && <>
      <TextField fullWidth multiline minRows={4} maxRows={20} label="Rendered native SQL" value={rendered.source} InputProps={{readOnly: true}} />
      <Alert severity="info">{rendered.parameter_policy}</Alert>
      <Button disabled={busy || disabled || !onLoad} onClick={() => onLoad(rendered)}>Load rendered SQL into editor</Button>
    </>}
  </Box>;
}
FirebirdTemplates.propTypes = {post: PropTypes.func.isRequired, resource: PropTypes.object.isRequired,
  generation: PropTypes.string, databaseTargetId: PropTypes.string, onLoad: PropTypes.func, disabled: PropTypes.bool};
