import {useEffect, useRef, useState} from 'react';
import {Alert, Dialog, DialogContent, DialogTitle} from '@mui/material';
import FactCheckOutlinedIcon from '@mui/icons-material/FactCheckOutlined';
import PropTypes from 'prop-types';
import {PgIconButton} from '../../../../../../static/js/components/Buttons';
import {QUERY_TOOL_EVENTS} from '../QueryToolConstants';
import url_for from 'sources/url_for';
import FormReference from 'sources/cdeadmin_ui/navigation/FormReference';

export default function SourceValidation({api, eventBus, transId, disabled}) {
  const generation = useRef(0);
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const invalidate = () => {generation.current++; setResult(null); setError(''); setPending(false);};
    invalidate();
    eventBus.registerListener(QUERY_TOOL_EVENTS.QUERY_CHANGED, invalidate);
    return () => {generation.current++; eventBus.deregisterListener(QUERY_TOOL_EVENTS.QUERY_CHANGED, invalidate);};
  }, [eventBus, transId]);
  const check = () => {
    if (pending || disabled) return;
    const current = ++generation.current;
    setPending(true); setResult(null); setError('');
    eventBus.fireEvent(QUERY_TOOL_EVENTS.TRIGGER_GET_QUERY_CONTENT, async source => {
      try {
        const response = await api.post(url_for('sqleditor.validate_source', {trans_id: transId}), {source});
        if (current === generation.current) {
          if (!response.data?.data?.authority) throw new Error('Source validation was unavailable.');
          setResult(response.data.data);
        }
      } catch (failure) {
        if (current === generation.current) setError(failure.response?.data?.errormsg || failure.message);
      } finally {if (current === generation.current) setPending(false);}
    });
  };
  return <>
    <PgIconButton title="Check SQL source without executing" aria-label="Check SQL source without executing"
      icon={<FactCheckOutlinedIcon />} disabled={disabled || pending} onClick={check} />
    <Dialog open={Boolean(error || result)} maxWidth="sm" fullWidth onClose={() => {setResult(null); setError('');}}>
      <DialogTitle>{result?.grammar_valid ? 'SQL grammar accepted' : 'SQL source diagnostics'}</DialogTitle>
      <DialogContent>
        <FormReference formKey="sql-source-validation" />
        {error && <Alert severity="error" onClose={() => setError('')}>{error}</Alert>}
        {result && <Alert severity={result.diagnostics?.length ? 'warning' : 'info'} onClose={() => setResult(null)}>
          {result.scope} Checked selection, or the full editor when no text was selected.
          {(result.diagnostics || []).map((item, index) => <div key={index}>
            {item.line}:{item.column}{item.position_exact === false ? ' (approximate)' : ''} — {item.message}
          </div>)}
        </Alert>}
      </DialogContent>
    </Dialog>
  </>;
}
SourceValidation.propTypes = {
  api: PropTypes.object.isRequired, eventBus: PropTypes.object.isRequired,
  transId: PropTypes.oneOfType([PropTypes.string, PropTypes.number]).isRequired,
  disabled: PropTypes.bool,
};
