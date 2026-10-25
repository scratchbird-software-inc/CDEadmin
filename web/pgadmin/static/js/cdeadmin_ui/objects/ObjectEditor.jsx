/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * The family object editor: one tabbed dialog for an object on any engine.
 *
 * Tabs come from the resolved descriptor form (family skeleton merged with
 * the engine form). The SQL tab shows the provider plan for the current
 * draft; apply confirms that plan. The host supplies the backend calls
 * (`plan`, `apply`) and optional renderers for shell tabs (Data,
 * Dependencies, Statistics, Indexes, Triggers) so this component holds no
 * engine knowledge and no transport details.
 */

import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Box, Grid, ScrollArea, Stack} from '../primitives/Layout';
import {Button} from '../primitives/Button';
import {Tab} from '../navigation/TabsAndBreadcrumbs';
import {Banner, ValidationMessage} from '../feedback/Indicators';
import {EmptyState} from '../feedback/EmptyState';
import CodeEditor from '../editors/CodeEditor';
import FieldControl from './FieldControl';
import {activeFields, initialDraft, toBackendDraft, validateDraft} from './descriptors';

/** Extract SQL text from a provider plan's command preview, whatever its shape. */
export function planSqlText(plan) {
  const preview = plan?.command_preview;
  if(!preview) return '';
  if(typeof preview === 'string') return preview;
  if(Array.isArray(preview)) return preview.map(planSqlText).filter(Boolean).join('\n\n');
  if(Array.isArray(preview.statements)) {
    return preview.statements.map((statement) => statement?.source ?? statement?.sql ?? '').filter(Boolean).join(';\n\n');
  }
  if(preview.source) return preview.source;
  if(preview.sql) return preview.sql;
  return JSON.stringify(preview, null, 2);
}

function groupFields(fields) {
  const groups = [];
  const index = {};
  for(const field of fields) {
    const name = field.group || '';
    if(!(name in index)) {
      index[name] = groups.length;
      groups.push({name, fields: []});
    }
    groups[index[name]].fields.push(field);
  }
  return groups;
}

function FieldsTab({tab, form, draft, errors, mode, context, resourceKind, disabled, onFieldChange}) {
  const fields = activeFields(tab.fields, {mode, draft});
  if(!fields.length) {
    return <EmptyState message={`Nothing to set on ${tab.title} for this ${form.family_title.toLowerCase()}.`} />;
  }
  const groups = groupFields(fields);
  return <Stack gap="comfortable">
    {groups.map((group) => <Box key={group.name || '_'} component="section"
      aria-label={group.name || tab.title}>
      {group.name && <Box component="h4" sx={{m: 0, mb: 1, fontSize: '0.75rem', fontWeight: 600,
        textTransform: 'uppercase', color: 'text.secondary'}}>{group.name}</Box>}
      <Grid columns={group.fields.some((field) => ['grid', 'code', 'privileges', 'keyvalue'].includes(field.control)) ?
        1 : 'repeat(auto-fit, minmax(260px, 1fr))'} gap="standard">
        {group.fields.map((field) => <FieldControl key={field.field_id} field={field}
          value={draft[field.field_id]} draft={draft} context={context} resourceKind={resourceKind}
          error={errors[field.field_id]} disabled={disabled}
          onChange={(value) => onFieldChange(field.field_id, value)} />)}
      </Grid>
    </Box>)}
  </Stack>;
}

FieldsTab.propTypes = {
  tab: PropTypes.object.isRequired, form: PropTypes.object.isRequired, draft: PropTypes.object.isRequired,
  errors: PropTypes.object.isRequired, mode: PropTypes.string.isRequired, context: PropTypes.object,
  resourceKind: PropTypes.string, disabled: PropTypes.bool, onFieldChange: PropTypes.func.isRequired,
};

export default function ObjectEditor({form, mode='create', resourceKind, record={}, context={},
  plan, apply, tabRenderers={}, onClose, onApplied, title, readOnly=false, autoPlan=true}) {
  const [draft, setDraft] = useState(() => initialDraft(form, {mode, record}));
  const [baseline] = useState(() => initialDraft(form, {mode, record}));
  const [activeTab, setActiveTab] = useState(form.tabs[0]?.tab);
  const [touched, setTouched] = useState(false);
  const [planState, setPlanState] = useState({status: 'idle', plan: null, error: null});
  const [applyState, setApplyState] = useState({status: 'idle', result: null, error: null});
  const planRequest = useRef(0);
  const errors = useMemo(() => validateDraft(form, draft, {mode, baseline}), [form, draft, mode, baseline]);
  const dirty = useMemo(() => JSON.stringify(draft) !== JSON.stringify(baseline), [draft, baseline]);
  const backendDraft = useMemo(() => toBackendDraft(form, draft, {mode}), [form, draft, mode]);
  const canPlan = Object.keys(errors).length === 0 && (mode === 'create' || dirty) && !readOnly;

  const refreshPlan = useCallback(async () => {
    if(!plan || !canPlan) return;
    const request = ++planRequest.current;
    setPlanState({status: 'loading', plan: null, error: null});
    try {
      const result = await plan({draft: backendDraft, mode});
      if(request !== planRequest.current) return;
      setPlanState({status: 'ready', plan: result, error: null});
    } catch(error) {
      if(request !== planRequest.current) return;
      setPlanState({status: 'error', plan: null, error: error?.message || String(error)});
    }
  }, [plan, canPlan, backendDraft, mode]);

  useEffect(() => {
    // The plan belongs to the draft it was made from; any edit retires it.
    setPlanState({status: 'idle', plan: null, error: null});
    setApplyState({status: 'idle', result: null, error: null});
  }, [backendDraft]);

  useEffect(() => {
    if(activeTab === 'SQL' && autoPlan && planState.status === 'idle') refreshPlan();
  }, [activeTab, autoPlan, planState.status, refreshPlan]);

  const onFieldChange = (fieldId, value) => {
    setTouched(true);
    setDraft((current) => ({...current, [fieldId]: value}));
  };

  const doApply = async () => {
    if(!apply) return;
    let current = planState.plan;
    if(!current) {
      await refreshPlan();
      return;
    }
    setApplyState({status: 'loading', result: null, error: null});
    try {
      const result = await apply({plan: current, draft: backendDraft, mode});
      setApplyState({status: 'done', result, error: null});
      onApplied?.(result);
    } catch(error) {
      setApplyState({status: 'error', result: null, error: error?.message || String(error)});
    }
  };

  const tabErrors = useMemo(() => {
    const byTab = {};
    for(const tab of form.tabs) {
      byTab[tab.tab] = activeFields(tab.fields, {mode, draft}).some((field) =>
        Object.keys(errors).some((key) => key === field.field_id || key.startsWith(`${field.field_id}[`)));
    }
    return byTab;
  }, [form.tabs, errors, mode, draft]);

  const current = form.tabs.find((tab) => tab.tab === activeTab) || form.tabs[0];
  const heading = title || `${mode === 'create' ? 'Create' : 'Edit'} ${form.family_title.toLowerCase()}` +
    (record?.name || record?.display_name ? ` — ${record.name || record.display_name}` : '');
  const planBlocked = planState.plan && planState.plan.state === 'blocked';
  const confirmLabel = planState.plan?.confirmation_required ? 'Confirm and apply' : 'Apply';

  return <Box role="dialog" aria-label={heading} data-cdeadmin-qa-key={`object-editor.${form.family}`}
    sx={{display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0}}>
    <Box component="h2" sx={{m: 0, px: 2, py: 1.5, fontSize: '1rem', borderBottom: '1px solid', borderColor: 'divider'}}>
      {heading}
    </Box>
    {form.status !== 'complete' && <Banner status="info">
      {form.status === 'draft' ? `This ${form.family_title.toLowerCase()} form is a draft: fields are listed, round-trip verification is pending.` :
        'This form is a skeleton; the engine descriptor has no fields yet.'}
    </Banner>}
    <Box role="tablist" aria-label={`${form.family_title} tabs`}
      sx={{display: 'flex', flexWrap: 'wrap', borderBottom: '1px solid', borderColor: 'divider', px: 1}}>
      {form.tabs.map((tab) => <Tab key={tab.tab} label={tab.title} active={tab.tab === current?.tab}
        attention={Boolean(tabErrors[tab.tab]) && touched}
        dirty={tab.tab === 'SQL' && planState.status === 'ready'}
        onActivate={() => setActiveTab(tab.tab)} />)}
    </Box>
    <ScrollArea label={`${current?.title || ''} tab content`} sx={{flex: 1, minHeight: 0, p: 2}}>
      {current && <Box role="tabpanel" aria-label={current.title} data-cdeadmin-qa-key={`object-editor.tab.${current.tab}`}>
        {current.primitive === 'sql_preview' && <SqlTab planState={planState} canPlan={canPlan} errors={errors}
          onRefresh={refreshPlan} mode={mode} dirty={dirty} />}
        {current.primitive !== 'sql_preview' && (tabRenderers[current.tab] ?
          tabRenderers[current.tab]({tab: current, draft, record, context, mode}) :
          (current.fields.length ?
            <FieldsTab tab={current} form={form} draft={draft} errors={errors} mode={mode} context={context}
              resourceKind={resourceKind} disabled={readOnly || applyState.status === 'loading'}
              onFieldChange={onFieldChange} /> :
            <EmptyState message={`${current.title} is shown once the object exists.`} />))}
      </Box>}
    </ScrollArea>
    <Box sx={{display: 'flex', gap: 1, alignItems: 'center', px: 2, py: 1.5, borderTop: '1px solid',
      borderColor: 'divider'}}>
      <Box sx={{flex: 1, fontSize: '0.75rem', color: 'text.secondary'}}>
        {applyState.status === 'done' && <ValidationMessage status="success">Applied.</ValidationMessage>}
        {applyState.status === 'error' && <ValidationMessage status="error">{applyState.error}</ValidationMessage>}
        {applyState.status === 'idle' && Object.keys(errors).length > 0 && touched &&
          <ValidationMessage status="error">{Object.keys(errors).length} field(s) need attention.</ValidationMessage>}
        {applyState.status === 'idle' && planBlocked &&
          <ValidationMessage status="warning">Plan blocked: {(planState.plan.blockers || []).join(', ') || 'see SQL tab'}.</ValidationMessage>}
      </Box>
      <Button intent="neutral" onClick={onClose}>{applyState.status === 'done' ? 'Close' : 'Cancel'}</Button>
      {!readOnly && <Button intent="neutral" disabled={!canPlan || planState.status === 'loading'}
        onClick={() => { setActiveTab('SQL'); refreshPlan(); }}>Preview SQL</Button>}
      {!readOnly && <Button intent="primary" loading={applyState.status === 'loading'}
        disabled={!canPlan || applyState.status === 'done' || planState.status === 'loading' ||
          (planState.plan && (planBlocked || planState.plan.execution_available === false))}
        onClick={doApply}>
        {planState.plan ? confirmLabel : 'Preview and apply'}
      </Button>}
    </Box>
  </Box>;
}

function SqlTab({planState, canPlan, errors, onRefresh, mode, dirty}) {
  if(!canPlan) {
    const reason = Object.keys(errors).length ? 'Complete the required fields to preview the SQL.' :
      (mode === 'alter' && !dirty ? 'No changes yet; the SQL tab shows the ALTER set once you edit a field.' :
        'Nothing to preview.');
    return <EmptyState message={reason} />;
  }
  if(planState.status === 'loading') return <EmptyState message="Asking the provider for its plan..." />;
  if(planState.status === 'error') return <Stack>
    <ValidationMessage status="error">{planState.error}</ValidationMessage>
    <Box><Button intent="neutral" onClick={onRefresh}>Retry</Button></Box>
  </Stack>;
  if(planState.status === 'idle') return <Box><Button intent="neutral" onClick={onRefresh}>Preview SQL</Button></Box>;
  const plan = planState.plan;
  const sql = planSqlText(plan);
  return <Stack gap="standard">
    {plan.state === 'blocked' && <Banner status="warning">
      The provider will not run this plan: {(plan.blockers || []).join(', ') || 'blocked'}.
    </Banner>}
    {(plan.warnings || []).length > 0 && <Banner status="info">{plan.warnings.join(' ')}</Banner>}
    <Box data-cdeadmin-qa-key="object-editor.sql-preview" aria-label="Provider plan SQL">
      <CodeEditor label="Provider plan SQL" value={sql || '-- The provider produced no SQL text for this plan.'}
        readonly language="sql" />
    </Box>
    {plan.command_preview && typeof plan.command_preview === 'object' && plan.command_preview.driver_operation &&
      <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
        Driver operation: {String(plan.command_preview.driver_operation)}
      </Box>}
  </Stack>;
}

SqlTab.propTypes = {
  planState: PropTypes.object.isRequired, canPlan: PropTypes.bool, errors: PropTypes.object,
  onRefresh: PropTypes.func, mode: PropTypes.string, dirty: PropTypes.bool,
};

ObjectEditor.propTypes = {
  form: PropTypes.object.isRequired,
  mode: PropTypes.oneOf(['create', 'alter']),
  resourceKind: PropTypes.string,
  record: PropTypes.object,
  context: PropTypes.object,
  plan: PropTypes.func,
  apply: PropTypes.func,
  tabRenderers: PropTypes.object,
  onClose: PropTypes.func,
  onApplied: PropTypes.func,
  title: PropTypes.string,
  readOnly: PropTypes.bool,
  autoPlan: PropTypes.bool,
};
