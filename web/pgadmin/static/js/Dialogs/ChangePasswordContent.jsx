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
import {
  DialogContent as ModalContent,
  DialogFooter as ModalFooter,
} from 'sources/cdeadmin_ui/overlays/DialogLayout';
import {Box, Stack} from '../cdeadmin_ui/primitives/Layout';
import {Button} from '../cdeadmin_ui/primitives/Button';
import {SecretField, TextField} from '../cdeadmin_ui/primitives/Field';
import {Banner} from '../cdeadmin_ui/feedback/Indicators';

export default function ChangePasswordContent({
  getInitData,
  onSave,
  onClose,
  hasCsrfToken = false,
  showUser = true,
  userName = '',
  isPgpassFileUsed = false,
}) {
  const [user, setUser] = useState(userName || '');
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [csrfToken, setCsrfToken] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (userName) setUser(userName);
  }, [userName]);

  useEffect(() => {
    let active = true;
    const maybePromise = getInitData?.();
    if (maybePromise && typeof maybePromise.then === 'function') {
      setBusy(true);
      maybePromise
        .then((init) => {
          if (!active || !init) return;
          if (init.user) setUser(init.user);
          if (init.csrf_token) setCsrfToken(init.csrf_token);
        })
        .catch((err) => {
          if (active) setError(err?.message || gettext('Something went wrong'));
        })
        .finally(() => {
          if (active) setBusy(false);
        });
    }
    return () => {
      active = false;
    };
  }, [getInitData]);

  const mismatchError =
    confirmPassword && newPassword !== confirmPassword
      ? gettext('Passwords do not match.')
      : '';
  const canSubmit =
    !busy &&
    (isPgpassFileUsed || Boolean(password)) &&
    Boolean(newPassword) &&
    Boolean(confirmPassword) &&
    newPassword === confirmPassword;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    setError('');
    try {
      const payload = {
        user,
        password,
        newPassword,
        confirmPassword,
        ...(hasCsrfToken ? {csrf_token: csrfToken} : {}),
      };
      await onSave?.(true, payload);
    } catch (err) {
      setError(
        err?.response?.data?.errormsg ||
          err?.message ||
          gettext('Something went wrong')
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <ModalContent>
      <Box style={{flexGrow: 1, padding: 16, overflow: 'auto'}}>
        <Stack spacing={1.5}>
          {showUser && (
            <TextField
              label={gettext('User')}
              value={user}
              disabled
            />
          )}
          <SecretField
            label={gettext('Current Password')}
            allowReveal
            autoComplete="current-password"
            value={password}
            disabled={busy || isPgpassFileUsed}
            required={!isPgpassFileUsed}
            onChange={(e) => setPassword(e.target.value)}
          />
          <SecretField
            label={gettext('New Password')}
            allowReveal
            autoComplete="new-password"
            value={newPassword}
            disabled={busy}
            required
            onChange={(e) => setNewPassword(e.target.value)}
          />
          <SecretField
            label={gettext('Confirm Password')}
            allowReveal
            autoComplete="new-password"
            value={confirmPassword}
            disabled={busy}
            required
            validationMessage={mismatchError}
            onChange={(e) => setConfirmPassword(e.target.value)}
          />
          {error && <Banner tone="error">{error}</Banner>}
        </Stack>
      </Box>
      <ModalFooter>
        <Button
          data-test="Close"
          disabled={busy}
          onClick={() => onClose?.()}
        >
          {gettext('Cancel')}
        </Button>
        <Button
          data-test="Save"
          variant="primary"
          disabled={!canSubmit}
          onClick={handleSubmit}
        >
          {gettext('Change')}
        </Button>
      </ModalFooter>
    </ModalContent>
  );
}

ChangePasswordContent.propTypes = {
  onSave: PropTypes.func,
  onClose: PropTypes.func,
  getInitData: PropTypes.func,
  hasCsrfToken: PropTypes.bool,
  showUser: PropTypes.bool,
  userName: PropTypes.string,
  isPgpassFileUsed: PropTypes.bool,
};
