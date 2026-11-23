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
import {
  DialogContent as ModalContent,
  DialogFooter as ModalFooter,
} from 'sources/cdeadmin_ui/overlays/DialogLayout';
import {Box, Stack} from '../cdeadmin_ui/primitives/Layout';
import {Button} from '../cdeadmin_ui/primitives/Button';
import {Select} from '../cdeadmin_ui/primitives/Choice';
import {Banner} from '../cdeadmin_ui/feedback/Indicators';
import {isEmptyString} from 'sources/validators';

export default function ChangeOwnershipContent({
  onSave,
  onClose,
  deletedUser,
  userList = [],
  noOfSharedServers = 0,
}) {
  const [newUser, setNewUser] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const options = [
    {value: '', label: gettext('(None — delete shared servers)')},
    ...(userList || []).map((opt) => ({
      value: String(opt.value ?? opt.id ?? ''),
      label: opt.label ?? opt.name ?? String(opt.value ?? ''),
    })),
  ];

  const handleSubmit = async () => {
    if (isEmptyString(newUser) && !confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    setBusy(true);
    setError('');
    try {
      await onSave?.(true, {newUser});
    } catch (err) {
      setError(err?.message || gettext('Something went wrong'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <ModalContent>
      <Box style={{flexGrow: 1, padding: 16, overflow: 'auto'}}>
        <Stack spacing={1.5}>
          <Banner tone="info">
            {gettext(
              `Select the user that will take ownership of the shared servers created by ${deletedUser}. ${noOfSharedServers} shared servers are currently owned by this user. Clicking on the “Change” button will either change ownership if a user is selected or delete any shared servers if no user is selected. There is no way to reverse this action.`
            )}
          </Banner>
          <Select
            label={gettext('User')}
            value={String(newUser)}
            disabled={busy}
            options={options}
            onChange={(val) => {
              setNewUser(val);
              setConfirmDelete(false);
              setError('');
            }}
          />
          {confirmDelete && isEmptyString(newUser) && (
            <Banner tone="warning">
              {gettext(
                `The shared servers owned by ${deletedUser} will be deleted. Click "Confirm Delete" to continue.`
              )}
            </Banner>
          )}
          {error && <Banner tone="error">{error}</Banner>}
        </Stack>
      </Box>
      <ModalFooter>
        <Button
          data-test="Close"
          disabled={busy}
          onClick={() => {
            if (confirmDelete) {
              setConfirmDelete(false);
            } else {
              onClose?.();
            }
          }}
        >
          {gettext('Cancel')}
        </Button>
        <Button
          data-test="Save"
          variant={confirmDelete && isEmptyString(newUser) ? 'danger' : 'primary'}
          disabled={busy}
          onClick={handleSubmit}
        >
          {confirmDelete && isEmptyString(newUser)
            ? gettext('Confirm Delete')
            : gettext('Change')}
        </Button>
      </ModalFooter>
    </ModalContent>
  );
}

ChangeOwnershipContent.propTypes = {
  onSave: PropTypes.func,
  onClose: PropTypes.func,
  userList: PropTypes.array,
  noOfSharedServers: PropTypes.number,
  deletedUser: PropTypes.string,
};
