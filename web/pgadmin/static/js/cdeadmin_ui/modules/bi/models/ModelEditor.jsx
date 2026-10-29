/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Stack} from '../../../primitives/Layout';
import {Button} from '../../../primitives/Button';
import {Select} from '../../../primitives/Choice';
import {Banner} from '../../../feedback/Indicators';
import {Dialog} from '../../../overlays/Dialog';
import PanelTabs from '../PanelTabs';
import {NameDialog} from '../Dialogs';
import ModelFields from './ModelFields';
import EmbeddedPanel from './EmbeddedPanel';
import QueryPanel from './QueryPanel';
import {AdvancedPanel, LineagePanel, MaterializationPlans, RevisionsPanel, StatusBadge} from './InsightPanels';
import {modelForm, modelOptionContext} from './modelForm';

const EXTRA_TABS = ['try', 'embedded', 'lineage', 'revisions', 'advanced'];
const EXTRA_TITLES = () => ({
  try: gettext('Try it'), embedded: gettext('Charts and reports'), lineage: gettext('Lineage'),
  revisions: gettext('Revisions'), advanced: gettext('Advanced JSON'),
});

/** Status changes the lifecycle allows from each status: [target status, button label, confirm?] */
export const TRANSITIONS = {
  draft: [['published', () => gettext('Publish'), true], ['archived', () => gettext('Archive'), false]],
  published: [['draft', () => gettext('Return to draft'), true], ['archived', () => gettext('Archive'), false]],
  archived: [['draft', () => gettext('Restore'), false]],
};

function Confirm({open, title, children, confirmLabel, busy, onConfirm, onClose}) {
  return <Dialog open={open} title={title} onClose={onClose} busy={busy}
    actions={<Stack direction="row" gap="compact">
      <Button onClick={onClose}>{gettext('Cancel')}</Button>
      <Button intent="primary" loading={busy} onClick={onConfirm}>{confirmLabel}</Button>
    </Stack>}>{children}</Dialog>;
}

Confirm.propTypes = {
  open: PropTypes.bool.isRequired, title: PropTypes.string.isRequired, children: PropTypes.node,
  confirmLabel: PropTypes.string.isRequired, busy: PropTypes.bool, onConfirm: PropTypes.func.isRequired,
  onClose: PropTypes.func.isRequired,
};

function SourcePicker({resources, profile, onAdd, disabled}) {
  const kinds = profile.source_kinds || null;
  const usable = resources.filter((item) => !kinds || kinds.includes(item.resource_kind));
  const [chosen, setChosen] = useState('');
  if(!usable.length) return null;
  const options = usable.map((item) => ({value: item.resource_id,
    label: (item.display_path || [item.display_name]).join('.')}));
  return <Stack direction="row" gap="compact" sx={{alignItems: 'flex-end'}}>
    <Select size="small" label={gettext('Discovered resource')} value={chosen} disabled={disabled}
      options={[{value: '', label: gettext('Choose a table')}, ...options]} onChange={setChosen} sx={{minWidth: 280}} />
    <Button disabled={disabled || !chosen} onClick={() => {
      onAdd(usable.find((item) => item.resource_id === chosen));
      setChosen('');
    }}>{gettext('Add as source')}</Button>
  </Stack>;
}

SourcePicker.propTypes = {
  resources: PropTypes.array.isRequired, profile: PropTypes.object.isRequired, onAdd: PropTypes.func.isRequired,
  disabled: PropTypes.bool,
};

/**
 * One model: the toolbar (save, validate, status, clone, delete), the typed form tabs and the
 * panels around them. A published model is read-only until it is returned to draft.
 */
export default function ModelEditor({client, session}) {
  const {state, catalog, profile, resources, busy, error, issues, built, readOnly} = session;
  const {draft, record, dirty, validation, lineage} = state;
  const [tab, setTab] = useState('model');
  const [dialog, setDialog] = useState(null);

  const form = useMemo(() => modelForm(profile), [profile]);
  const context = useMemo(() => modelOptionContext(draft, built.definition), [draft, built.definition]);
  const formIds = form.tabs.map((item) => item.tab);
  const ids = [...formIds, ...EXTRA_TABS];
  const titles = EXTRA_TITLES();
  const labelOf = (id) => titles[id] || form.tabs.find((item) => item.tab === id)?.title || id;
  const active = ids.includes(tab) ? tab : 'model';
  const formTab = form.tabs.find((item) => item.tab === active);
  const transitions = record ? TRANSITIONS[record.status] || [] : [];

  const transition = async (status) => {
    setDialog(null);
    await session.setStatus(status);
  };
  const problems = [...built.problems, ...Object.values(issues)];

  return <Stack gap="standard" data-cdeadmin-qa-key="bi.models.editor" sx={{p: 1.5, minWidth: 0}}>
    <Stack direction="row" gap="compact" sx={{alignItems: 'center', flexWrap: 'wrap'}}>
      <Box component="h2" sx={{m: 0, mr: 1, fontSize: '1rem'}}>{draft.name || gettext('Untitled model')}</Box>
      {record && <><StatusBadge status={record.status} /><span>r{record.revision}</span></>}
      {dirty && <span aria-label={gettext('Unsaved changes')}>•</span>}
      <Box sx={{flex: 1}} />
      <Button intent="primary" disabled={busy !== '' || readOnly || !dirty && Boolean(record)}
        loading={busy === 'save'} onClick={session.save}>{gettext('Save')}</Button>
      <Button loading={busy === 'validate'} disabled={busy !== ''} onClick={session.validate}>
        {gettext('Validate')}</Button>
      {transitions.map(([status, label, confirm]) => <Button key={status} disabled={busy !== '' || dirty}
        loading={busy === 'status'} onClick={() => confirm ? setDialog({kind: 'status', status, label: label()}) :
          transition(status)}>{label()}</Button>)}
      <Button disabled={!record || busy !== ''} onClick={() => setDialog({kind: 'clone'})}>{gettext('Clone')}</Button>
      <Button intent="destructive" disabled={!record || busy !== '' || readOnly}
        onClick={() => setDialog({kind: 'delete'})}>{gettext('Delete')}</Button>
    </Stack>
    {readOnly && <Banner status="info">
      {gettext('This model is published and read-only. Return it to draft to edit it.')}</Banner>}
    {record && record.status === 'archived' && <Banner status="info">
      {gettext('This model is archived. Restore it to continue editing.')}</Banner>}
    {error && <Banner status="error">{error}</Banner>}
    {validation && (validation.valid ?
      <Banner status="success">{gettext('The model is valid.')}</Banner> :
      <Banner status="error">
        <Box component="ul" aria-label={gettext('Validation errors')} sx={{m: 0, pl: 2}}>
          {(validation.errors || []).map((item, index) => <li key={index}>{item.message}</li>)}
        </Box>
      </Banner>)}
    {dirty && problems.length > 0 && <Banner status="warning">{problems.join(' ')}</Banner>}

    <PanelTabs label={gettext('Model sections')} ids={ids} labelOf={labelOf} active={active} onChange={setTab} />

    <Box role="tabpanel" aria-label={labelOf(active)}>
      {formTab && <ModelFields tab={formTab} draft={draft} context={context} errors={issues}
        disabled={readOnly || record?.status === 'archived'} onChange={session.edit}>
        {active === 'model' && <SourcePicker resources={resources} profile={profile} onAdd={session.addSource}
          disabled={readOnly || record?.status === 'archived'} />}
        {active === 'materializations' && <MaterializationPlans client={client} record={record}
          definition={built.definition} catalog={catalog} dirty={dirty} />}
      </ModelFields>}
      {active === 'try' && <QueryPanel client={client} record={record} dirty={dirty} built={built} draft={draft}
        catalog={catalog} />}
      {active === 'embedded' && <EmbeddedPanel client={client} record={record} dirty={dirty}
        definition={built.definition} catalog={catalog} />}
      {active === 'lineage' && <LineagePanel lineage={lineage} busy={busy === 'lineage'}
        onRefresh={session.refreshLineage} />}
      {active === 'revisions' && <RevisionsPanel client={client} record={record} />}
      {active === 'advanced' && <AdvancedPanel definition={built.definition} readOnly={readOnly}
        onApply={session.replaceDefinition} />}
    </Box>

    <Confirm open={dialog?.kind === 'status'} title={dialog?.label || ''} confirmLabel={dialog?.label || ''}
      busy={busy === 'status'} onClose={() => setDialog(null)} onConfirm={() => transition(dialog.status)}>
      {dialog?.status === 'published' ?
        gettext('Publishing freezes this revision. Scheduled reports can be authorized only for a published model.') :
        gettext('The model becomes editable again and its scheduled reports lose authorization.')}
    </Confirm>
    <Confirm open={dialog?.kind === 'delete'} title={gettext('Delete model')} confirmLabel={gettext('Delete')}
      busy={busy === 'remove'} onClose={() => setDialog(null)} onConfirm={async () => {
        setDialog(null);
        await session.remove();
      }}>
      {gettext('This deletes the model and all of its revisions. Questions and dashboards already migrated to BI are kept.')}
    </Confirm>
    {dialog?.kind === 'clone' && <NameDialog open title={gettext('Clone model')} label={gettext('Name of the copy')}
      initial={gettext('%s (copy)', draft.name || '')} confirmLabel={gettext('Clone')}
      onConfirm={(name) => session.clone(name)} onClose={() => setDialog(null)} />}
  </Stack>;
}

ModelEditor.propTypes = {
  client: PropTypes.object.isRequired,
  session: PropTypes.object.isRequired,
};
