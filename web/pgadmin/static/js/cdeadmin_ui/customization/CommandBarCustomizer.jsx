/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// View > Customize Tabbed Bar: the notebook bar's customization form in a
// dialog, saved per account. It arranges only the commands the menus offer.

import {useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import usePreferences from '../../../../preferences/static/js/store';
import {NotebookBarCustomizer} from '../../scratch_notebookbar';
import {Button} from '../primitives/Button';
import {ValidationMessage} from '../feedback/Indicators';
import {buildCommandBarModel} from '../shell/commandBarModel';
import {
  COMMAND_BAR_MESSAGES, COMMAND_BAR_THEME, readCommandBarCustomization,
  saveCommandBarCustomization,
} from '../shell/commandBarSettings';

export default function CommandBarCustomizer({menus, icon, onClose}) {
  const bar = useMemo(() => buildCommandBarModel(menus ?? [], icon), [menus]);
  const [draft, setDraft] = useState(() =>
    readCommandBarCustomization(usePreferences.getState()));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const save = async () => {
    setBusy(true);
    setError('');
    try {
      await saveCommandBarCustomization(usePreferences.getState(), draft);
      onClose?.();
    } catch(failure) {
      setError(failure?.response?.data?.errormsg || failure.message);
    } finally {
      setBusy(false);
    }
  };
  return <div data-cdeadmin-qa-key="command-bar-customizer.dialog"
    style={{...COMMAND_BAR_THEME, height: '100%', minHeight: 0, display: 'grid',
      gridTemplateRows: 'minmax(0, 1fr) auto', gap: 8}}>
    <div style={{overflow: 'auto', padding: 8}}>
      <p style={{marginTop: 0}}>{gettext(
        'Arrange the tabbed command bar. It shows the commands of the menus; a command you cannot run stays unavailable wherever you place it.'
      )}</p>
      <NotebookBarCustomizer model={bar.model} catalog={bar.catalog}
        customization={draft} onChange={setDraft}
        messages={COMMAND_BAR_MESSAGES} />
    </div>
    <div style={{display: 'flex', alignItems: 'center', gap: 8, padding: 8,
      borderTop: '1px solid var(--cde-color-border, currentColor)'}}>
      <div style={{flex: 1}}>{error && <ValidationMessage>{error}</ValidationMessage>}</div>
      <Button onClick={onClose}>{gettext('Cancel')}</Button>
      <Button intent="primary" loading={busy} onClick={save}>{gettext('Save')}</Button>
    </div>
  </div>;
}

CommandBarCustomizer.propTypes = {
  menus: PropTypes.array,
  icon: PropTypes.func,
  onClose: PropTypes.func,
};
