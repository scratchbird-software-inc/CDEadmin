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
import {Box, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {Checkbox} from '../../primitives/Choice';
import {SearchField} from '../../primitives/AdvancedControls';
import {Badge} from '../../feedback/Indicators';
import {EmptyState} from '../../feedback/EmptyState';
import {
  findCollection, flattenCollections, matchingCollectionIds, moveTargets, questionCounts, visibleQuestions,
} from './collectionTree';
import {MoveDialog, NameDialog} from './Dialogs';
import DashboardList from './DashboardList';

const itemSx = (active, depth) => ({
  display: 'block', width: '100%', textAlign: 'left', cursor: 'pointer', border: 0, font: 'inherit',
  py: 0.5, pr: 1, pl: 1 + depth * 1.5, color: 'text.primary',
  bgcolor: active ? 'action.selected' : 'transparent',
  borderLeft: '3px solid', borderColor: active ? 'primary.main' : 'transparent',
  '&:hover': {bgcolor: 'action.hover'},
});

function CollectionItem({label, count, depth, active, onSelect}) {
  return <li>
    <Box component="button" type="button" aria-current={active ? 'true' : undefined} onClick={onSelect}
      sx={itemSx(active, depth)}>
      {label}{' '}<Box component="span" sx={{color: 'text.secondary', fontSize: '0.75rem'}}>({count})</Box>
    </Box>
  </li>;
}

CollectionItem.propTypes = {
  label: PropTypes.string.isRequired, count: PropTypes.number.isRequired, depth: PropTypes.number.isRequired,
  active: PropTypes.bool, onSelect: PropTypes.func.isRequired,
};

/**
 * Collections and the question list: search by name, create / rename / move
 * collections, and rename / move / archive / duplicate questions. Every
 * change goes through the bi_* actions and then asks the host to refresh.
 */
export default function CollectionBrowser({
  client, tree, questions, dashboards = [], selected, onSelect, search, onSearch, showArchived, onShowArchived,
  activeQuestionId, dirtyQuestionId, activeDashboardId, dirtyDashboardId,
  onOpen, onNew, onOpenDashboard, onNewDashboard, onImportDashboard, onChanged, onChangedDashboard, onError,
}) {
  const [dialog, setDialog] = useState(null);
  const rows = useMemo(() => flattenCollections(tree), [tree]);
  const counts = useMemo(() => {
    const items = [...questions, ...dashboards];
    return questionCounts(showArchived ? items : items.filter((item) => item.status !== 'archived'));
  }, [questions, dashboards, showArchived]);
  const matching = useMemo(() => matchingCollectionIds(tree, search), [tree, search]);
  const searching = search.trim() !== '';
  const list = visibleQuestions(questions, {
    collectionId: searching ? undefined : selected, text: search, includeArchived: showArchived,
  });
  const dashboardList = visibleQuestions(dashboards, {
    collectionId: searching ? undefined : selected, text: search, includeArchived: showArchived,
  });
  const selectedCollection = typeof selected === 'string' ? findCollection(tree, selected) : null;
  const total = [...counts.values()].reduce((sum, value) => sum + value, 0);

  // Dialogs show a failure themselves; direct buttons report it through onError.
  const attempt = (work, changedQuestionId) => async (...args) => {
    await work(...args);
    await onChanged(changedQuestionId);
  };
  const direct = (work, changedQuestionId) => () => attempt(work, changedQuestionId)().catch(
    (error) => onError(error?.message || String(error)));
  const blocked = (question) => question.question_id === dirtyQuestionId;
  const blockedHint = gettext('Save or discard the open changes first.');
  const pathOf = (id) => rows.find((row) => row.id === id)?.path.join(' / ') || '';

  return <Box data-cdeadmin-qa-key="bi.browser" sx={{display: 'grid', gap: 1, alignContent: 'start', minWidth: 0}}>
    <Stack direction="row" gap="compact" sx={{flexWrap: 'wrap'}}>
      <Button intent="primary" onClick={() => onNew(typeof selected === 'string' ? selected : null)}>
        {gettext('New question')}
      </Button>
      <Button onClick={() => onNewDashboard(typeof selected === 'string' ? selected : null)}>
        {gettext('New dashboard')}
      </Button>
      <Button onClick={() => setDialog({kind: 'newCollection'})}>{gettext('New collection')}</Button>
      <Button onClick={onImportDashboard}>{gettext('Import monitoring dashboard')}</Button>
    </Stack>
    <SearchField size="small" label={gettext('Search questions, dashboards and collections')} value={search}
      onChange={onSearch} resultCount={searching ? list.length + dashboardList.length : undefined} />
    <Checkbox size="small" label={gettext('Show archived')} checked={showArchived} onChange={onShowArchived} />

    <Box component="nav" aria-label={gettext('Collections')}>
      <Box component="ul" sx={{m: 0, p: 0, listStyle: 'none'}}>
        <CollectionItem label={gettext('All items')} count={total} depth={0}
          active={!searching && selected === undefined} onSelect={() => onSelect(undefined)} />
        <CollectionItem label={gettext('No collection')} count={counts.get(null) || 0} depth={0}
          active={!searching && selected === null} onSelect={() => onSelect(null)} />
        {rows.filter((row) => !matching || matching.has(row.id)).map((row) =>
          <CollectionItem key={row.id} label={row.name} count={counts.get(row.id) || 0} depth={row.depth + 1}
            active={!searching && selected === row.id} onSelect={() => onSelect(row.id)} />)}
      </Box>
    </Box>
    {selectedCollection && !searching && <Stack direction="row" gap="compact" role="group"
      aria-label={gettext('Collection %s', selectedCollection.name)} sx={{flexWrap: 'wrap'}}>
      <Button size="small" onClick={() => setDialog({kind: 'renameCollection', collection: selectedCollection})}>
        {gettext('Rename collection')}
      </Button>
      <Button size="small" onClick={() => setDialog({kind: 'moveCollection', collection: selectedCollection})}>
        {gettext('Move collection')}
      </Button>
      <Button size="small" intent="destructive" onClick={direct(async () => {
        await client.deleteCollection(selectedCollection.collection_id);
        onSelect(undefined);
      })}>{gettext('Delete collection')}</Button>
    </Stack>}

    <Box component="h3" sx={{m: 0, fontSize: '0.8125rem'}}>{gettext('Questions')}</Box>
    <Box component="ul" aria-label={gettext('Questions')} sx={{m: 0, p: 0, listStyle: 'none'}}>
      {list.map((question) => {
        const archived = question.status === 'archived';
        const stop = blocked(question);
        return <Box component="li" key={question.question_id} aria-current={question.question_id === activeQuestionId ? 'true' : undefined}
          sx={{borderBottom: '1px solid', borderColor: 'divider', py: 0.5,
            bgcolor: question.question_id === activeQuestionId ? 'action.selected' : 'transparent'}}>
          <Stack direction="row" gap="compact" sx={{alignItems: 'center', flexWrap: 'wrap'}}>
            <Button size="small" onClick={() => onOpen(question)}
              aria-label={gettext('Open %s', question.name)}>{question.name}</Button>
            {archived && <Badge status="warning" label={gettext('Archived')} />}
            {searching && question.collection_id && <Box component="span" sx={{fontSize: '0.7rem', color: 'text.secondary'}}>
              {pathOf(question.collection_id)}</Box>}
          </Stack>
          <Stack direction="row" gap="compact" role="group" aria-label={gettext('Actions for %s', question.name)}
            sx={{flexWrap: 'wrap', mt: 0.5}}>
            <Button size="small" disabled={stop} title={stop ? blockedHint : undefined}
              aria-label={gettext('Rename %s', question.name)}
              onClick={() => setDialog({kind: 'renameQuestion', question})}>{gettext('Rename')}</Button>
            <Button size="small" disabled={stop} title={stop ? blockedHint : undefined}
              aria-label={gettext('Move %s', question.name)}
              onClick={() => setDialog({kind: 'moveQuestion', question})}>{gettext('Move')}</Button>
            <Button size="small" disabled={stop} title={stop ? blockedHint : undefined}
              aria-label={archived ? gettext('Restore %s', question.name) : gettext('Archive %s', question.name)}
              onClick={direct(() => client.setQuestionStatus(
                question.question_id, question.revision, archived ? 'active' : 'archived'), question.question_id)}>{archived ? gettext('Restore') : gettext('Archive')}</Button>
            <Button size="small" aria-label={gettext('Duplicate %s', question.name)}
              onClick={() => setDialog({kind: 'cloneQuestion', question})}>{gettext('Duplicate')}</Button>
          </Stack>
        </Box>;
      })}
      {list.length === 0 && <li><EmptyState message={searching ?
        gettext('No question or collection matches the search.') : gettext('No questions here yet.')} /></li>}
    </Box>

    <Box component="h3" sx={{m: 0, fontSize: '0.8125rem'}}>{gettext('Dashboards')}</Box>
    <DashboardList client={client} dashboards={dashboardList} collections={rows} searching={searching}
      activeDashboardId={activeDashboardId} dirtyDashboardId={dirtyDashboardId}
      onOpen={onOpenDashboard} onChanged={onChangedDashboard} onError={onError} />

    {dialog?.kind === 'newCollection' && <NameDialog open title={gettext('New collection')}
      label={gettext('Collection name')} confirmLabel={gettext('Create')} onClose={() => setDialog(null)}
      onConfirm={attempt((name) => client.createCollection({
        name, description: '', parent_id: typeof selected === 'string' ? selected : null}))} />}
    {dialog?.kind === 'renameCollection' && <NameDialog open title={gettext('Rename collection')}
      label={gettext('Collection name')} initial={dialog.collection.name} confirmLabel={gettext('Rename')}
      onClose={() => setDialog(null)}
      onConfirm={attempt((name) => client.updateCollection(dialog.collection.collection_id, {
        name, description: dialog.collection.description || '', parent_id: dialog.collection.parent_id ?? null}))} />}
    {dialog?.kind === 'moveCollection' && <MoveDialog open title={gettext('Move collection')}
      targets={moveTargets(tree, dialog.collection.collection_id)} current={dialog.collection.parent_id ?? null}
      onClose={() => setDialog(null)}
      onConfirm={attempt((parentId) => client.updateCollection(dialog.collection.collection_id, {
        name: dialog.collection.name, description: dialog.collection.description || '', parent_id: parentId}))} />}
    {dialog?.kind === 'renameQuestion' && <NameDialog open title={gettext('Rename question')}
      label={gettext('Question name')} initial={dialog.question.name} confirmLabel={gettext('Rename')}
      onClose={() => setDialog(null)}
      onConfirm={attempt(async (name) => {
        const record = await client.getQuestion(dialog.question.question_id);
        await client.updateQuestion(record.question_id, record.revision, {...record.definition, name});
      }, dialog.question.question_id)} />}
    {dialog?.kind === 'moveQuestion' && <MoveDialog open title={gettext('Move question')}
      targets={rows} current={dialog.question.collection_id ?? null} onClose={() => setDialog(null)}
      onConfirm={attempt((collectionId) => client.moveQuestion(
        dialog.question.question_id, dialog.question.revision, collectionId), dialog.question.question_id)} />}
    {dialog?.kind === 'cloneQuestion' && <NameDialog open title={gettext('Duplicate question')}
      label={gettext('Name of the copy')} initial={gettext('Copy of %s', dialog.question.name)}
      confirmLabel={gettext('Duplicate')} onClose={() => setDialog(null)}
      onConfirm={attempt((name) => client.cloneQuestion(dialog.question.question_id, name))} />}
  </Box>;
}

CollectionBrowser.propTypes = {
  client: PropTypes.object.isRequired,
  tree: PropTypes.array.isRequired,
  questions: PropTypes.array.isRequired,
  dashboards: PropTypes.array,
  selected: PropTypes.oneOfType([PropTypes.string, PropTypes.oneOf([null])]),
  onSelect: PropTypes.func.isRequired,
  search: PropTypes.string.isRequired,
  onSearch: PropTypes.func.isRequired,
  showArchived: PropTypes.bool.isRequired,
  onShowArchived: PropTypes.func.isRequired,
  activeQuestionId: PropTypes.string,
  dirtyQuestionId: PropTypes.string,
  activeDashboardId: PropTypes.string,
  dirtyDashboardId: PropTypes.string,
  onOpen: PropTypes.func.isRequired,
  onNew: PropTypes.func.isRequired,
  onOpenDashboard: PropTypes.func.isRequired,
  onNewDashboard: PropTypes.func.isRequired,
  onImportDashboard: PropTypes.func.isRequired,
  onChanged: PropTypes.func.isRequired,
  onChangedDashboard: PropTypes.func.isRequired,
  onError: PropTypes.func.isRequired,
};
