/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {Select} from '../../primitives/Choice';
import {Radio, SearchField} from '../../primitives/AdvancedControls';
import {Banner} from '../../feedback/Indicators';
import {EmptyState} from '../../feedback/EmptyState';
import {Dialog} from '../../overlays/Dialog';

/**
 * Choose a saved question for a new card. A card pins one revision of the
 * question, so "latest" pins the question's newest revision at this moment;
 * a later edit of the question never changes the dashboard.
 */
export default function CardPicker({client, questions, collections, onPick, onClose}) {
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState(null);
  const [mode, setMode] = useState('latest');
  const [history, setHistory] = useState(null);
  const [revision, setRevision] = useState('');
  const [error, setError] = useState('');

  const pathOf = (id) => collections.find((row) => row.id === id)?.path.join(' / ') || '';
  const needle = search.trim().toLowerCase();
  const list = questions.filter((question) => question.status !== 'archived' &&
    (!needle || question.name.toLowerCase().includes(needle)));

  useEffect(() => {
    if(!selected || mode !== 'pinned') return undefined;
    let cancelled = false;
    setHistory(null);
    client.history(selected.question_id).then(
      (items) => {
        if(cancelled) return;
        setHistory(items);
        setRevision((current) => current || String(items[0]?.revision ?? selected.revision));
      },
      (caught) => { if(!cancelled) setError(caught?.message || String(caught)); });
    return () => { cancelled = true; };
  }, [client, selected, mode]);

  const choose = (question) => {
    setSelected(question);
    setMode('latest');
    setRevision('');
    setError('');
  };
  const pinned = mode === 'latest' ? selected?.revision : Number(revision);
  const confirm = () => onPick({question_id: selected.question_id, revision: pinned, name: selected.name});

  return <Dialog open title={gettext('Add a question card')} size="medium" onClose={onClose}
    actions={<Stack direction="row" gap="compact">
      <Button onClick={onClose}>{gettext('Cancel')}</Button>
      <Button intent="primary" disabled={!selected || !pinned} onClick={confirm}>{gettext('Add card')}</Button>
    </Stack>}>
    <Stack>
      {error && <Banner status="error">{error}</Banner>}
      <SearchField size="small" label={gettext('Search saved questions')} value={search} onChange={setSearch}
        resultCount={needle ? list.length : undefined} />
      <Box role="listbox" aria-label={gettext('Saved questions')} sx={{maxHeight: 220, overflow: 'auto', m: 0, p: 0}}>
        {list.map((question) => <Box key={question.question_id} role="option" component="button" type="button"
          aria-selected={selected?.question_id === question.question_id}
          onClick={() => choose(question)}
          sx={{display: 'flex', width: '100%', textAlign: 'left', gap: 1, cursor: 'pointer', border: 0, font: 'inherit',
            py: 0.5, px: 1, color: 'text.primary',
            bgcolor: selected?.question_id === question.question_id ? 'action.selected' : 'transparent',
            '&:hover': {bgcolor: 'action.hover'}}}>
          <Box component="span" sx={{flex: 1}}>{question.name}</Box>
          <Box component="span" sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
            {pathOf(question.collection_id)}
          </Box>
        </Box>)}
        {list.length === 0 && <EmptyState message={needle ?
          gettext('No saved question matches the search.') : gettext('There are no saved questions yet.')} />}
      </Box>
      {selected && <Stack>
        <Radio label={gettext('Revision to show')} value={mode} onChange={setMode} options={[
          {value: 'latest', label: gettext('Latest revision (%s)', selected.revision)},
          {value: 'pinned', label: gettext('An earlier revision')}]} />
        {mode === 'pinned' && (history ?
          <Select size="small" label={gettext('Pinned revision')} value={revision} onChange={setRevision}
            options={history.map((item) => ({value: String(item.revision), label: gettext('Revision %s', item.revision)}))} /> :
          <Box role="status" sx={{fontSize: '0.75rem'}}>{gettext('Loading revisions...')}</Box>)}
      </Stack>}
    </Stack>
  </Dialog>;
}

CardPicker.propTypes = {
  client: PropTypes.shape({history: PropTypes.func.isRequired}).isRequired,
  questions: PropTypes.array.isRequired,
  collections: PropTypes.array.isRequired,
  onPick: PropTypes.func.isRequired,
  onClose: PropTypes.func.isRequired,
};
