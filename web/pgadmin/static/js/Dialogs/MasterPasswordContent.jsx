/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import url_for from 'sources/url_for';
import {
  DialogContent as ModalContent,
  DialogFooter as ModalFooter,
} from 'sources/cdeadmin_ui/overlays/DialogLayout';
import {Box, Stack} from '../cdeadmin_ui/primitives/Layout';
import {Button, IconButton} from '../cdeadmin_ui/primitives/Button';
import {SecretField} from '../cdeadmin_ui/primitives/Field';
import {Banner} from '../cdeadmin_ui/feedback/Indicators';

export default function MasterPasswordContent({
  closeModal,
  onResetPassowrd,
  onOK,
  onCancel,
  setHeight,
  isPWDPresent,
  data,
  keyringName = '',
}) {
  const containerRef = useRef();
  const firstEleRef = useRef();
  const isKeyring = keyringName.length > 0;
  const [password, setPassword] = useState('');

  const submit = () => {
    if (!password.length) return;
    const postFormData = new FormData();
    postFormData.append('password', password);
    postFormData.append('submit_password', true);
    onOK?.(postFormData);
    closeModal();
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      firstEleRef.current?.focus();
    }, 350);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    setHeight?.(containerRef.current?.offsetHeight);
  }, [setHeight]);

  return (
    <ModalContent ref={containerRef}>
      <Box style={{flexGrow: 1, padding: 16}}>
        <Stack spacing={1.5}>
          {isKeyring ? (
            <>
              <div style={{fontWeight: 600}}>
                {gettext('Please enter your master password.')}
              </div>
              <Banner tone="info">
                {gettext(
                  `Saved passwords are encrypted using an encryption key stored in ${keyringName}. Enter the master password for your existing ScratchRobin saved passwords; they will be re-encrypted when you click OK.`
                )}
              </Banner>
            </>
          ) : (
            <>
              <div style={{fontWeight: 600}}>
                {isPWDPresent
                  ? gettext('Please enter your master password.')
                  : gettext('Please set a master password for ScratchRobin.')}
              </div>
              <div style={{fontSize: '0.8125rem', color: 'var(--sr-text-muted)'}}>
                {isPWDPresent
                  ? gettext('This is required to unlock saved passwords and reconnect to the database server(s).')
                  : gettext('This will be used to secure and later unlock saved passwords and other credentials.')}
              </div>
            </>
          )}
          <SecretField
            ref={firstEleRef}
            label={gettext('Master password')}
            allowReveal
            autoComplete={isKeyring ? 'current-password' : 'new-password'}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && password.length > 0) {
                e.preventDefault();
                submit();
              }
            }}
          />
          {data?.errmsg && <Banner tone="error">{data.errmsg}</Banner>}
        </Stack>
      </Box>
      <ModalFooter>
        <Box style={{marginRight: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6}}>
          <IconButton
            data-test="help-masterpassword"
            label={gettext('Help')}
            onClick={() => {
              const _url = url_for('help.static', {filename: 'master_password.html'});
              window.open(_url, 'pgadmin_help');
            }}
          >
            ?
          </IconButton>
          {isPWDPresent && (
            <Button
              data-test="reset-masterpassword"
              variant="danger"
              onClick={() => {
                onResetPassowrd?.(isKeyring);
              }}
            >
              {gettext('Reset Master Password')}
            </Button>
          )}
        </Box>
        {!isKeyring && (
          <Button
            data-test="close"
            onClick={() => {
              onCancel?.();
              closeModal();
            }}
          >
            {gettext('Cancel')}
          </Button>
        )}
        <Button
          data-test="save"
          variant="primary"
          disabled={password.length === 0}
          onClick={submit}
        >
          {gettext('OK')}
        </Button>
      </ModalFooter>
    </ModalContent>
  );
}

MasterPasswordContent.propTypes = {
  closeModal: PropTypes.func,
  onResetPassowrd: PropTypes.func,
  onOK: PropTypes.func,
  onCancel: PropTypes.func,
  setHeight: PropTypes.func,
  isPWDPresent: PropTypes.bool,
  data: PropTypes.object,
  keyringName: PropTypes.string,
};
