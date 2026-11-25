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
import gettext from 'sources/gettext';
import {useLocaleRevision} from '../actions/t_actions';
import {Dialog} from '../overlays/Dialog';
import {Box, Stack} from '../primitives/Layout';
import {Button} from '../primitives/Button';
import {TextField} from '../primitives/Field';
import {Select} from '../primitives/Choice';
import {Banner, ValidationMessage} from '../feedback/Indicators';
import {readShowFormReferences} from '../navigation/FormReference';
import CodeEditor from '../editors/CodeEditor';
import {ScratchDiffTable} from '../data/beautiful';
import AdaptiveFieldPlacementGrid from './AdaptiveFieldPlacementGrid';
import FieldControl from './FieldControl';
import {activeFields, fieldVisible, toOperationDraft} from './descriptors';
import {planSqlText} from './ObjectEditor';
import FirebirdServiceObservation from '../../Dialogs/FirebirdServiceObservation';
import FirebirdLimboObservation from '../../Dialogs/FirebirdLimboObservation';

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
    if(field.required && empty) errors[field.field_id] = gettext('%s is required.', field.label);
  }
  return errors;
}

export default function OperationDialog({open, operation, targetName, context={}, executionHosts=[],
  plan, apply, onClose, onApplied}) {
  const localeRev = useLocaleRevision();
  const needsTypedName = operation.confirmation === 'typed_name';
  // A typed-name operation's `confirmation` field is the typed box below; the
  // draft still carries it (see `draft`), so it is not shown twice.
  const fields = useMemo(() => (operation.fields || []).filter((field) =>
    !(needsTypedName && field.field_id === 'confirmation')), [operation.fields, needsTypedName]);
  const [values, setValues] = useState(() => initialValues(fields));
  const [host, setHost] = useState(executionHosts[0]?.value ?? 'local');
  const [confirmText, setConfirmText] = useState('');
  const [planState, setPlanState] = useState({status: 'idle', plan: null, error: null});
  const [applyState, setApplyState] = useState({status: 'idle', result: null, error: null});
  // Errors show on a field once it is edited, and on every field once run is tried.
  const [touched, setTouched] = useState(() => new Set());
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const errors = useMemo(() => validate(fields, values), [fields, values, localeRev]);
  const visible = activeFields(fields, {draft: values});
  const groups = operation.groups?.length ? operation.groups : [...new Set(visible.map((field) => field.group || ''))];
  const confirmed = !needsTypedName || (targetName && confirmText.trim() === targetName);
  // Providers validate a typed confirmation as the draft's `confirmation`
  // field (the route database for database-level tasks, the object name
  // otherwise); the dialog's own match hint never replaces that check.
  // The provider takes its own field shapes: string grids as plain lists,
  // rows without the grid's _id, dotted backend ids nested.
  const draft = toOperationDraft(operation,
    needsTypedName && confirmText.trim() ? {...values, confirmation: confirmText.trim()} : values);

  const setValue = (fieldId, value) => {
    setTouched((current) => current.has(fieldId) ? current : new Set([...current, fieldId]));
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
      return result;
    } catch(error) {
      setPlanState({status: 'error', plan: null, error: error?.message || String(error)});
      return null;
    }
  };
  const doApply = async () => {
    setSubmitAttempted(true);
    if(Object.keys(errors).length > 0 || !confirmed) return;
    let activePlan = planState.plan;
    if(!activePlan) {
      // One click plans and runs, but stops on a plan to read first: blocked,
      // asking for confirmation, or carrying the provider's warnings.
      activePlan = await doPlan();
      if(!activePlan || activePlan.state === 'blocked' || activePlan.execution_available === false ||
        activePlan.confirmation_required || (activePlan.warnings || []).length > 0) return;
    }
    setApplyState({status: 'loading', result: null, error: null});
    try {
      const result = await apply({plan: activePlan, draft});
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

  const resolvedFormRef = operation.form_reference || undefined;
  const resolvedFormKey = !resolvedFormRef
    ? (operation.form?.form_key || (operation.form_id ? `operation:${operation.form_id}` : 'operation:execute'))
    : undefined;

  const opTitle = gettext.retranslate ? gettext.retranslate(operation.title || '') : operation.title;
  return <Dialog open={open} title={targetName ? `${opTitle} — ${targetName}` : opTitle}
    formReference={resolvedFormRef} formKey={resolvedFormKey}
    size={operation.tier === 3 || visible.some((field) => ['grid', 'code'].includes(field.control)) ? 'large' : 'medium'}
    busy={busy} onClose={busy ? undefined : onClose}
    actions={<>
      <Button intent="neutral" onClick={onClose} disabled={busy}>{applyState.status === 'done' ? gettext('Close') : gettext('Cancel')}</Button>
      <Button intent="neutral" disabled={busy || Object.keys(errors).length > 0} onClick={doPlan}>{gettext('Preview')}</Button>
      <Button intent={operation.confirmation === 'typed_name' ? 'destructive' : 'primary'} loading={applyState.status === 'loading'}
        disabled={busy || !confirmed || applyState.status === 'done' || blocked}
        onClick={doApply}>
        {planState.plan ? gettext('Run') : gettext('Preview and run')}
      </Button>
    </>}>
    <Stack gap="comfortable" data-cdeadmin-qa-key={`operation-dialog.${operation.operation_id}`}>
      {operation.status === 'draft' && readShowFormReferences() && <Banner status="info">
        {gettext('This operation is a draft: verification against a live server is pending.')}
      </Banner>}
      {operation.description && <Banner status="info">{gettext(operation.description)}</Banner>}
      {operation.tier === 3 && operation.execution_host && <Select label={gettext('Execution host')} fullWidth size="small"
        options={executionHosts.length ? executionHosts : [{value: 'local', label: gettext('This ScratchRobin server')}]}
        value={host} onChange={(next) => setHost(next)} helperText={gettext('Where the native utility runs.')} />}
      {groups.map((group) => {
        const groupFields = visible.filter((field) => (field.group || '') === group);
        if(!groupFields.length) return null;
        return <Box key={group || '_'} component="section" aria-label={group ? gettext(group) : opTitle}>
          {group && <Box component="h4" sx={{m: 0, mb: 1, fontSize: '0.75rem', fontWeight: 600,
            textTransform: 'uppercase', color: 'text.secondary'}}>{gettext(group)}</Box>}
          <AdaptiveFieldPlacementGrid
            fields={groupFields}
            draft={values}
            context={context}
            resourceKind={operation.resource_kind}
            qaKey={`operation-dialog.grid.${group || 'default'}`}
            renderField={(field) => (
              <FieldControl
                field={field}
                value={values[field.field_id]}
                draft={values}
                context={context}
                resourceKind={operation.resource_kind}
                error={submitAttempted || touched.has(field.field_id) ? errors[field.field_id] : undefined}
                disabled={busy}
                dense
                onChange={(value) => setValue(field.field_id, value)}
              />
            )}
          />
        </Box>;
      })}
      {visible.length === 0 && <Box sx={{fontSize: '0.8125rem', color: 'text.secondary'}}>
        {gettext('This operation takes no options.')}
      </Box>}
      {needsTypedName && <TextField label={gettext('Type %s to confirm', targetName || gettext('the object name'))} size="small" fullWidth
        value={confirmText} onChange={(event) => setConfirm(event.target.value)}
        validationMessage={confirmText && !confirmed ? gettext('Name does not match.') : undefined} />}
      {planState.status === 'error' && <ValidationMessage status="error">{planState.error}</ValidationMessage>}
      {planState.plan && <Box data-cdeadmin-qa-key="operation-dialog.plan">
        {blocked && <Banner status="warning">
          {gettext('The provider will not run this: %s.', (planState.plan.blockers || []).join(', ') || gettext('blocked'))}
        </Banner>}
        {(planState.plan.warnings || []).length > 0 && <Banner status="info">{planState.plan.warnings.join(' ')}</Banner>}
        {Array.isArray(planState.plan.statements) && planState.plan.statements.length > 0 && (
          <Box sx={{mt: 1, mb: 1}}>
            <ScratchDiffTable
              title={gettext('Planned Statement Impact')}
              qaKey="operation-dialog.plan.diff-table"
              items={planState.plan.statements.map((stmt, idx) => ({
                id: `stmt-${idx}`,
                delta: operation.confirmation === 'typed_name' ? 'remove' : 'modify',
                kind: operation.resource_kind || 'operation',
                name: typeof stmt === 'string' ? gettext('Step %s', idx + 1) : (stmt.label || stmt.kind || gettext('Step %s', idx + 1)),
                summary: typeof stmt === 'string' ? stmt : (stmt.sql || stmt.statement || stmt.summary || ''),
                risk: operation.confirmation === 'typed_name' ? 'destructive' : 'safe',
              }))}
            />
          </Box>
        )}
        <Box component="h4" sx={{m: 0, mt: 1, mb: 0.5, fontSize: '0.75rem', fontWeight: 600, color: 'text.secondary'}}>
          {gettext('Provider plan')}
        </Box>
        <CodeEditor label={gettext('Provider plan')} readonly language="sql"
          value={sql || gettext('-- Native operation; the provider reported no SQL text.')} />
      </Box>}
      {applyState.status === 'error' && <ValidationMessage status="error">{applyState.error}</ValidationMessage>}
      {applyState.status === 'done' && (() => {
        const observation = receipt?.driver_observation ??
          (typeof receipt?.schema === 'string' && receipt.schema.startsWith('cdeadmin.firebird-') ? receipt : null);
        const followUpFailures = (applyState.result?.workspace_follow_up || []).filter(
          (item) => item?.state === 'failed' && typeof item.message === 'string'
        );
        return <Box data-cdeadmin-qa-key="operation-dialog.receipt">
          <ValidationMessage status="success">{gettext('Completed.')}</ValidationMessage>
          {observation?.service_release?.service_handle_released === false && (
            <Banner status="warning">
              {gettext('Firebird service handle release is unconfirmed. Do not replay the operation. Review its returned outcome separately from cleanup, then explicitly close the provider connection to retry handle release.')}
            </Banner>
          )}
          {followUpFailures.map((item, idx) => (
            <Banner key={`${item.action || 'followup'}-${idx}`} status="warning">{item.message}</Banner>
          ))}
          {observation?.schema === 'cdeadmin.firebird-limbo-result.v1' ? (
            <FirebirdLimboObservation observation={observation} />
          ) : observation?.schema === 'cdeadmin.firebird-service-result.v1' ? (
            <FirebirdServiceObservation title={opTitle} observation={observation} />
          ) : (
            receipt && (operation.produces_log || typeof receipt === 'string') &&
            <CodeEditor label={gettext('Operation output')} readonly language="text"
              value={typeof receipt === 'string' ? receipt : JSON.stringify(receipt, null, 2)} />
          )}
        </Box>;
      })()}
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
