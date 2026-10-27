import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, TextField} from '@mui/material';

export default function RecipeRevisions({post, engine, databaseTargetId, source, onChange, disabled=false}) {
  const serial = useRef(0);
  const [name, setName] = useState('default'), [revision, setRevision] = useState('');
  const [version, setVersion] = useState(0), [busy, setBusy] = useState(false), [error, setError] = useState('');
  useEffect(() => {
    serial.current++; setVersion(0); setRevision(''); setBusy(false); setError('');
    return () => {serial.current++;};
  }, [post, engine, databaseTargetId, name]);
  // A reply must never overwrite edits made while storage I/O was pending.
  useEffect(() => {serial.current++; setBusy(false);}, [source]);
  const persist = async write => {
    const token = ++serial.current; setBusy(true); setError('');
    try {
      const result = await post({action: `${engine}_recipe_${write ? 'save' : 'read'}`,
        request: {database_target_id: databaseTargetId, recipe_id: name,
          ...(write ? {expected_version: version, recipe: JSON.parse(source)} :
            revision ? {version: Number(revision)} : {})}});
      if (token !== serial.current) return;
      setVersion(result.current_version);
      if (!write && result.recipe) onChange(JSON.stringify(result.recipe, null, 2));
      if (!result.recipe) setError('No saved recipe with this name in this database.');
    } catch (failure) {
      if (token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'Recipe storage unavailable');
    } finally {if (token === serial.current) setBusy(false);}
  };
  return <Box sx={{display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap'}}>
    <TextField size="small" label="Saved recipe name" value={name} disabled={disabled || busy}
      onChange={event => setName(event.target.value)} />
    <TextField size="small" type="number" label="Revision (blank for latest)" value={revision} disabled={disabled || busy}
      onChange={event => setRevision(event.target.value)} />
    <Button disabled={disabled || busy || !name} onClick={() => persist(false)}>Load saved recipe</Button>
    <Button disabled={disabled || busy || !name} onClick={() => persist(true)}>Store recipe revision</Button>
    <Box>Current saved revision: {version}</Box>
    {error && <Alert severity="error">{error}</Alert>}
  </Box>;
}
RecipeRevisions.propTypes = {post: PropTypes.func.isRequired, engine: PropTypes.oneOf(['postgresql', 'duckdb', 'sqlite']).isRequired,
  databaseTargetId: PropTypes.string.isRequired, source: PropTypes.string.isRequired, onChange: PropTypes.func.isRequired, disabled: PropTypes.bool};
