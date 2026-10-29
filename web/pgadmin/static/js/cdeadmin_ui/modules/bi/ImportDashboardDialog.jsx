/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {TextField} from '../../primitives/Field';
import {FilePickerButton} from '../../primitives/AdvancedControls';
import {Banner} from '../../feedback/Indicators';
import {Dialog} from '../../overlays/Dialog';
import {lossLines, readFileText, snapshotFromText} from './dashboardImport';

/**
 * Import a monitoring dashboard: choose the saved DDN source, convert it with
 * bi_dashboard_from_ddn, read what the conversion drops, and open the result
 * as an unsaved dashboard in the editor. Nothing is stored until it is saved.
 */
export default function ImportDashboardDialog({client, onImported, onClose}) {
  const [file, setFile] = useState(null);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [converted, setConverted] = useState(null);

  const convert = async () => {
    setBusy(true);
    setError('');
    setConverted(null);
    try {
      const snapshot = snapshotFromText(file.name, await readFileText(file));
      const result = await client.dashboardFromDdn(snapshot, name.trim() || undefined);
      setConverted(result);
    } catch(caught) {
      setError(caught?.message || String(caught));
    } finally {
      setBusy(false);
    }
  };
  const lines = converted ? lossLines(converted.loss) : [];
  return <Dialog open title={gettext('Import monitoring dashboard')} size="medium" onClose={onClose} busy={busy}
    actions={<Stack direction="row" gap="compact">
      <Button onClick={onClose}>{gettext('Cancel')}</Button>
      {converted ?
        <Button intent="primary" onClick={() => onImported(converted.dashboard, converted.loss)}>
          {gettext('Open in the editor')}</Button> :
        <Button intent="primary" loading={busy} disabled={!file} onClick={convert}>{gettext('Convert')}</Button>}
    </Stack>}>
    <Stack>
      {error && <Banner status="error">{error}</Banner>}
      <Box sx={{fontSize: '0.8125rem'}}>
        {gettext('Choose the dashboard source of a monitoring dashboard (dashboard.ddn), or a saved DDN snapshot (.json).')}
      </Box>
      <Stack direction="row" gap="compact" sx={{alignItems: 'center', flexWrap: 'wrap'}}>
        <FilePickerButton label={gettext('Choose file')} accept=".ddn,.json,text/plain,application/json"
          onFiles={(files) => { setFile(files[0] || null); setConverted(null); setError(''); }} />
        <Box component="span" role="status" sx={{fontSize: '0.8125rem'}}>
          {file ? file.name : gettext('No file chosen')}</Box>
      </Stack>
      <TextField size="small" label={gettext('Dashboard name (optional)')} value={name}
        onChange={(event) => setName(event.target.value)} />
      {converted && <>
        <Banner status={lines.length ? 'warning' : 'success'}>
          {lines.length ?
            gettext('Converted with %s differences.', lines.length) :
            gettext('Converted without loss: %s cards on %s tabs.',
              converted.dashboard.cards.length, converted.dashboard.tabs.length)}
        </Banner>
        {lines.length > 0 && <Box component="ul" aria-label={gettext('Conversion report')} sx={{m: 0, pl: 2, fontSize: '0.8125rem'}}>
          {lines.map((line, index) => <li key={index}>{line.text}</li>)}
        </Box>}
      </>}
    </Stack>
  </Dialog>;
}

ImportDashboardDialog.propTypes = {
  client: PropTypes.shape({dashboardFromDdn: PropTypes.func.isRequired}).isRequired,
  onImported: PropTypes.func.isRequired,
  onClose: PropTypes.func.isRequired,
};
