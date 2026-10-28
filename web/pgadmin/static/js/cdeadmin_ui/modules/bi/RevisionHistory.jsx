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
import {Badge, Banner} from '../../feedback/Indicators';
import {EmptyState} from '../../feedback/EmptyState';
import {Dialog} from '../../overlays/Dialog';
import CodeEditor from '../../editors/CodeEditor';

function when(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

/**
 * Immutable revisions of a saved question (bi_question_history /
 * bi_question_revision). Restoring loads the revision into the editor as an
 * unsaved draft, so the next save appends a new revision and nothing is lost.
 */
export default function RevisionHistory({client, questionId, currentRevision, onRestore, onClose}) {
  const [items, setItems] = useState(null);
  const [error, setError] = useState('');
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState('');

  useEffect(() => {
    let cancelled = false;
    client.history(questionId).then(
      (history) => { if(!cancelled) setItems(history); },
      (caught) => { if(!cancelled) setError(caught?.message || String(caught)); });
    return () => { cancelled = true; };
  }, [client, questionId]);

  const attempt = async (key, work) => {
    setBusy(key);
    setError('');
    try { await work(); } catch(caught) { setError(caught?.message || String(caught)); } finally { setBusy(''); }
  };
  const showSql = (revision) => attempt(`sql-${revision}`, async () => {
    const compiled = await client.compileRevision(questionId, revision);
    setPreview({revision, source: String(compiled.source ?? '')});
  });
  const restore = (revision) => attempt(`restore-${revision}`, async () => {
    const record = await client.revision(questionId, revision);
    onRestore(record.definition, revision);
    onClose();
  });

  return <Dialog open title={gettext('Revision history')} size="large" onClose={onClose}
    actions={<Button onClick={onClose}>{gettext('Close')}</Button>}>
    <Stack>
      {error && <Banner status="error">{error}</Banner>}
      {!items && !error && <Box role="status" sx={{fontSize: '0.75rem'}}>{gettext('Loading revisions...')}</Box>}
      {items && items.length === 0 && <EmptyState message={gettext('This question has no revisions.')} />}
      {items && items.length > 0 && <Box component="ul" aria-label={gettext('Revisions')} sx={{m: 0, p: 0, listStyle: 'none'}}>
        {items.map((item) => <Box component="li" key={item.revision}
          sx={{display: 'flex', alignItems: 'center', gap: 1, py: 0.5, borderBottom: '1px solid', borderColor: 'divider', flexWrap: 'wrap'}}>
          <Box sx={{flex: 1, minWidth: 160}}>
            <strong>{gettext('Revision %s', item.revision)}</strong>{' '}
            <Box component="span" sx={{fontSize: '0.75rem', color: 'text.secondary'}}>{when(item.created_at)}</Box>
          </Box>
          {item.revision === currentRevision && <Badge status="success" label={gettext('Current')} />}
          {item.status === 'archived' && <Badge status="warning" label={gettext('Archived')} />}
          <Button size="small" loading={busy === `sql-${item.revision}`}
            aria-label={gettext('Preview SQL of revision %s', item.revision)}
            onClick={() => showSql(item.revision)}>{gettext('Preview SQL')}</Button>
          <Button size="small" loading={busy === `restore-${item.revision}`}
            aria-label={gettext('Restore revision %s', item.revision)}
            onClick={() => restore(item.revision)}>{gettext('Restore as draft')}</Button>
        </Box>)}
      </Box>}
      {preview && <Box>
        <Box component="h4" sx={{m: 0, mb: 0.5, fontSize: '0.8125rem'}}>
          {gettext('SQL of revision %s', preview.revision)}
        </Box>
        <Box sx={{height: 180}}>
          <CodeEditor label={gettext('Revision SQL')} language="sql" readonly value={preview.source} />
        </Box>
      </Box>}
    </Stack>
  </Dialog>;
}

RevisionHistory.propTypes = {
  client: PropTypes.shape({history: PropTypes.func.isRequired, revision: PropTypes.func.isRequired,
    compileRevision: PropTypes.func.isRequired}).isRequired,
  questionId: PropTypes.string.isRequired,
  currentRevision: PropTypes.number,
  onRestore: PropTypes.func.isRequired,
  onClose: PropTypes.func.isRequired,
};
