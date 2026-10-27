/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Tier 2/3 operation dialog (ANALYZE, backup, sweep, grant...): grouped
 * fields from an operations.json entry, provider plan, confirmation and
 * receipt. Tier 3 adds the execution-host selector and an output pane.
 */

import {useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import {Dialog} from '../overlays/Dialog';
import {Box, Grid, Stack} from '../primitives/Layout';
import {Button} from '../primitives/Button';
import {TextField} from '../primitives/Field';
import {Select} from '../primitives/Choice';
import {Banner, ValidationMessage} from '../feedback/Indicators';
import CodeEditor from '../editors/CodeEditor';
import FieldControl from './FieldControl';
import {activeFields, fieldVisible} from './descriptors';
import {planSqlText} from './ObjectEditor';

function initialValues(fields) {
  const values = {};
  for(const field of fields) {
    if(field.default !== undefined) values[field.field_id] = field.default;
    else if(field.control === 'boolean') values[field.field_id] = false;
    else if(field.control === 'grid') values[field.field_id] = [];
  }
  return values;
}

function validate(fields, values) {
  const errors = {};
  for(const field of fields) {
    if(!fieldVisible(field, values) || field.available === false || field.readonly) continue;
    const value = values[field.field_id];
    const empty = value === undefined || value === null || value === '' || (Array.isArray(value) && !value.length);
    if(field.required && empty) errors[field.field_id] = `${field.label} is required.`;
  }
  return errors;
}

export default function OperationDialog({open, operation, targetName, context={}, executionHosts=[],
  plan, apply, onClose, onApplied}) {
  const fields = operation.fields || [];
  const [values, setValues] = useState(() => initialValues(fields));
  const [host, setHost] = useState(executionHosts[0]?.value ?? 'local');
  const [confirmText, setConfirmText] = useState('');
  const [planState, setPlanState] = useState({status: 'idle', plan: null, error: null});
  const [applyState, setApplyState] = useState({status: 'idle', result: null, error: null});
  const errors = useMemo(() => validate(fields, values), [fields, values]);
  const visible = activeFields(fields, {draft: values});
  const groups = operation.groups?.length ? operation.groups : [...new Set(visible.map((field) => field.group || ''))];
  const needsTypedName = operation.confirmation === 'typed_name';
  const confirmed = !needsTypedName || (targetName && confirmText.trim() === targetName);
  // Providers validate a typed confirmation as the draft's `confirmation`
  // field (the route database for database-level tasks, the object name
  // otherwise); the dialog's own match hint never replaces that check.
  const draft = needsTypedName && confirmText.trim() ? {...values, confirmation: confirmText.trim()} : values;

  const setValue = (fieldId, value) => {
    setValues((current) => ({...current, [fieldId]: value}));
    setPlanState({status: 'idle', plan: null, error: null});
  };
  const setConfirm = (text) => {
    setConfirmText(text);
    if(needsTypedName) setPlanState({status: 'idle', plan: null, error: null});
  };
  const doPlan = async () => {
    setPlanState({status: 'loading', plan: null, error: null});
    try {
      const result = await plan({draft, execution_host: operation.execution_host ? host : undefined});
      setPlanState({status: 'ready', plan: result, error: null});
    } catch(error) {
      setPlanState({status: 'error', plan: null, error: error?.message || String(error)});
    }
  };
  const doApply = async () => {
    if(!planState.plan) { await doPlan(); return; }
    setApplyState({status: 'loading', result: null, error: null});
    try {
      const result = await apply({plan: planState.plan, draft});
      setApplyState({status: 'done', result, error: null});
      onApplied?.(result);
    } catch(error) {
      setApplyState({status: 'error', result: null, error: error?.message || String(error)});
    }
  };
  const blocked = planState.plan?.state === 'blocked' || planState.plan?.execution_available === false;
  const busy = planState.status === 'loading' || applyState.status === 'loading';
  const receipt = applyState.result?.provider_result ?? applyState.result;
  const sql = planSqlText(planState.plan);

  return <Dialog open={open} title={targetName ? `${operation.title} — ${targetName}` : operation.title}
    size={operation.tier === 3 || visible.some((field) => ['grid', 'code'].includes(field.control)) ? 'large' : 'medium'}
    busy={busy} onClose={busy ? undefined : onClose}
    actions={<>
      <Button intent="neutral" onClick={onClose} disabled={busy}>{applyState.status === 'done' ? 'Close' : 'Cancel'}</Button>
      <Button intent="neutral" disabled={busy || Object.keys(errors).length > 0} onClick={doPlan}>Preview</Button>
      <Button intent={operation.confirmation === 'typed_name' ? 'destructive' : 'primary'} loading={applyState.status === 'loading'}
        disabled={busy || Object.keys(errors).length > 0 || !confirmed || applyState.status === 'done' || blocked}
        onClick={doApply}>
        {planState.plan ? 'Run' : 'Preview and run'}
      </Button>
    </>}>
    <Stack gap="comfortable" data-cdeadmin-qa-key={`operation-dialog.${operation.operation_id}`}>
      {operation.notes && <Banner status="info">{operation.notes}</Banner>}
      {operation.tier === 3 && operation.execution_host && <Select label="Execution host" fullWidth size="small"
        options={executionHosts.length ? executionHosts : [{value: 'local', label: 'This CDEadmin server'}]}
        value={host} onChange={(next) => setHost(next)} helperText="Where the native utility runs." />}
      {groups.map((group) => {
        const groupFields = visible.filter((field) => (field.group || '') === group);
        if(!groupFields.length) return null;
        return <Box key={group || '_'} component="section" aria-label={group || operation.title}>
          {group && <Box component="h4" sx={{m: 0, mb: 1, fontSize: '0.75rem', fontWeight: 600,
            textTransform: 'uppercase', color: 'text.secondary'}}>{group}</Box>}
          <Grid columns={groupFields.some((field) => ['grid', 'code', 'keyvalue'].includes(field.control)) ?
            1 : 'repeat(auto-fit, minmax(240px, 1fr))'}>
            {groupFields.map((field) => <FieldControl key={field.field_id} field={field} value={values[field.field_id]}
              draft={values} context={context} resourceKind={operation.resource_kind} error={errors[field.field_id]}
              disabled={busy} dense onChange={(value) => setValue(field.field_id, value)} />)}
          </Grid>
        </Box>;
      })}
      {visible.length === 0 && <Box sx={{fontSize: '0.8125rem', color: 'text.secondary'}}>
        This operation takes no options.
      </Box>}
      {needsTypedName && <TextField label={`Type ${targetName || 'the object name'} to confirm`} size="small" fullWidth
        value={confirmText} onChange={(event) => setConfirm(event.target.value)}
        validationMessage={confirmText && !confirmed ? 'Name does not match.' : undefined} />}
      {planState.status === 'error' && <ValidationMessage status="error">{planState.error}</ValidationMessage>}
      {planState.plan && <Box data-cdeadmin-qa-key="operation-dialog.plan">
        {blocked && <Banner status="warning">
          The provider will not run this: {(planState.plan.blockers || []).join(', ') || 'blocked'}.
        </Banner>}
        {(planState.plan.warnings || []).length > 0 && <Banner status="info">{planState.plan.warnings.join(' ')}</Banner>}
        <Box component="h4" sx={{m: 0, mt: 1, mb: 0.5, fontSize: '0.75rem', fontWeight: 600, color: 'text.secondary'}}>
          Provider plan
        </Box>
        <CodeEditor label="Provider plan" readonly language="sql"
          value={sql || '-- Native operation; the provider reported no SQL text.'} />
      </Box>}
      {applyState.status === 'error' && <ValidationMessage status="error">{applyState.error}</ValidationMessage>}
      {applyState.status === 'done' && <Box data-cdeadmin-qa-key="operation-dialog.receipt">
        <ValidationMessage status="success">Completed.</ValidationMessage>
        {receipt && (operation.produces_log || typeof receipt === 'string') &&
          <CodeEditor label="Operation output" readonly language="text"
            value={typeof receipt === 'string' ? receipt : JSON.stringify(receipt, null, 2)} />}
      </Box>}
    </Stack>
  </Dialog>;
}

OperationDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  operation: PropTypes.object.isRequired,
  targetName: PropTypes.string,
  context: PropTypes.object,
  executionHosts: PropTypes.array,
  plan: PropTypes.func.isRequired,
  apply: PropTypes.func.isRequired,
  onClose: PropTypes.func.isRequired,
  onApplied: PropTypes.func,
};
