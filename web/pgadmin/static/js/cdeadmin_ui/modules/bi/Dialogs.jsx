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
import {Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {TextArea, TextField} from '../../primitives/Field';
import {Select} from '../../primitives/Choice';
import {Dialog} from '../../overlays/Dialog';
import {Banner} from '../../feedback/Indicators';

const ROOT = '__root__';

/** Collection choices for a Select: the root plus every collection by path. */
export function collectionOptions(rows) {
  return [{value: ROOT, label: gettext('No collection')},
    ...rows.map((row) => ({value: row.id, label: row.path.join(' / ')}))];
}

const fromOption = (value) => value === ROOT ? null : value;
const toOption = (value) => value ?? ROOT;

function useAttempt(action, onClose) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const run = async (...args) => {
    setBusy(true);
    setError('');
    try {
      await action(...args);
      onClose();
    } catch(caught) {
      setError(caught?.message || String(caught));
    } finally {
      setBusy(false);
    }
  };
  return {busy, error, run};
}

/** Ask for a name (new collection, rename, duplicate). */
export function NameDialog({open, title, label, initial = '', confirmLabel, onConfirm, onClose}) {
  const [name, setName] = useState(initial);
  const {busy, error, run} = useAttempt(onConfirm, onClose);
  const submit = () => name.trim() && run(name.trim());
  return <Dialog open={open} title={title} onClose={onClose} busy={busy} defaultAction={submit}
    actions={<Stack direction="row" gap="compact">
      <Button onClick={onClose}>{gettext('Cancel')}</Button>
      <Button intent="primary" loading={busy} disabled={!name.trim()} onClick={submit}>{confirmLabel}</Button>
    </Stack>}>
    {error && <Banner status="error">{error}</Banner>}
    <TextField autoFocus fullWidth size="small" label={label} value={name}
      onChange={(event) => setName(event.target.value)} />
  </Dialog>;
}

NameDialog.propTypes = {
  open: PropTypes.bool.isRequired, title: PropTypes.string.isRequired, label: PropTypes.string.isRequired,
  initial: PropTypes.string, confirmLabel: PropTypes.string.isRequired,
  onConfirm: PropTypes.func.isRequired, onClose: PropTypes.func.isRequired,
};

/** Choose the collection something moves to. `targets` come from moveTargets()/flattenCollections(). */
export function MoveDialog({open, title, targets, current = null, onConfirm, onClose}) {
  const [target, setTarget] = useState(toOption(current));
  const {busy, error, run} = useAttempt(onConfirm, onClose);
  return <Dialog open={open} title={title} onClose={onClose} busy={busy}
    actions={<Stack direction="row" gap="compact">
      <Button onClick={onClose}>{gettext('Cancel')}</Button>
      <Button intent="primary" loading={busy} onClick={() => run(fromOption(target))}>{gettext('Move')}</Button>
    </Stack>}>
    {error && <Banner status="error">{error}</Banner>}
    <Select fullWidth size="small" label={gettext('Move to')} value={target}
      options={collectionOptions(targets)} onChange={setTarget} />
  </Dialog>;
}

MoveDialog.propTypes = {
  open: PropTypes.bool.isRequired, title: PropTypes.string.isRequired, targets: PropTypes.array.isRequired,
  current: PropTypes.string, onConfirm: PropTypes.func.isRequired, onClose: PropTypes.func.isRequired,
};

/** Save a new question or dashboard, or a copy: name, description and collection. */
export function SaveDialog({open, title, initial, collections, confirmLabel, nameLabel, onConfirm, onClose}) {
  const [name, setName] = useState(initial.name);
  const [description, setDescription] = useState(initial.description);
  const [collection, setCollection] = useState(toOption(initial.collectionId));
  const {busy, error, run} = useAttempt(onConfirm, onClose);
  const submit = () => name.trim() && run({name: name.trim(), description, collectionId: fromOption(collection)});
  return <Dialog open={open} title={title} onClose={onClose} busy={busy} defaultAction={submit}
    actions={<Stack direction="row" gap="compact">
      <Button onClick={onClose}>{gettext('Cancel')}</Button>
      <Button intent="primary" loading={busy} disabled={!name.trim()} onClick={submit}>{confirmLabel}</Button>
    </Stack>}>
    <Stack>
      {error && <Banner status="error">{error}</Banner>}
      <TextField autoFocus fullWidth size="small" label={nameLabel || gettext('Question name')} value={name}
        onChange={(event) => setName(event.target.value)} />
      <TextArea fullWidth size="small" rows={2} label={gettext('Description')} value={description}
        onChange={(event) => setDescription(event.target.value)} />
      <Select fullWidth size="small" label={gettext('Collection')} value={collection}
        options={collectionOptions(collections)} onChange={setCollection} />
    </Stack>
  </Dialog>;
}

SaveDialog.propTypes = {
  open: PropTypes.bool.isRequired, title: PropTypes.string.isRequired,
  initial: PropTypes.shape({name: PropTypes.string, description: PropTypes.string, collectionId: PropTypes.string}).isRequired,
  collections: PropTypes.array.isRequired, confirmLabel: PropTypes.string.isRequired,
  nameLabel: PropTypes.string,
  onConfirm: PropTypes.func.isRequired, onClose: PropTypes.func.isRequired,
};
