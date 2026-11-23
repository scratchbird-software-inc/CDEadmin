/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useLayoutEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {
  DialogContent as ModalContent,
  DialogFooter as ModalFooter,
} from 'sources/cdeadmin_ui/overlays/DialogLayout';
import {Box, Stack} from '../cdeadmin_ui/primitives/Layout';
import {Button} from '../cdeadmin_ui/primitives/Button';
import {TextField} from '../cdeadmin_ui/primitives/Field';
import {Checkbox} from '../cdeadmin_ui/primitives/Choice';
import {Banner} from '../cdeadmin_ui/feedback/Indicators';

export default function ConnectServerContent({
  closeModal,
  data,
  onOK,
  setHeight,
  hideSavePassword = false,
}) {
  const containerRef = useRef();
  const firstEleRef = useRef();
  const okBtnRef = useRef();
  const requiresUserInput = Boolean(data?.require_username_input);
  const [formData, setFormData] = useState(() => ({
    tunnel_password: '',
    save_tunnel_password: false,
    password: '',
    save_password: false,
    connect_as: data?.require_username_input ? (data?.suggested_username || '') : '',
    use_alternate_user: false,
  }));
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [tunnelPasswordVisible, setTunnelPasswordVisible] = useState(false);

  const onTextChange = (e, id) => {
    const val = e?.target ? e.target.value : e;
    setFormData((prev) => ({...prev, [id]: val}));
  };

  const onKeyDown = (e) => {
    if (e.key === 'Enter') {
      okBtnRef.current?.click();
    }
  };

  useLayoutEffect(() => {
    firstEleRef.current?.focus();
  }, []);

  useEffect(() => {
    setHeight?.(containerRef.current?.offsetHeight);
  }, [setHeight]);

  if (!data) {
    return <>No data</>;
  }

  const isSubmitDisabled =
    (requiresUserInput || formData.use_alternate_user) &&
    (!formData.connect_as.trim() || !formData.password);

  return (
    <ModalContent ref={containerRef}>
      <Box style={{flexGrow: 1, padding: 16}}>
        <Stack spacing={1.5}>
          {data.prompt_tunnel_password && (
            <>
              <div style={{fontWeight: 600}}>
                {data.tunnel_identity_file
                  ? gettext(
                    'Please enter the SSH Tunnel password for the identity file \'%s\' to connect the server "%s"',
                    data.tunnel_identity_file,
                    data.tunnel_host
                  )
                  : gettext(
                    'Please enter the SSH Tunnel password for the user \'%s\' to connect the server "%s"',
                    data.tunnel_username,
                    data.tunnel_host
                  )}
              </div>
              <Box style={{display: 'flex', alignItems: 'center', gap: 8}}>
                <TextField
                  ref={firstEleRef}
                  style={{flex: 1}}
                  type={tunnelPasswordVisible ? 'text' : 'password'}
                  value={formData.tunnel_password}
                  inputProps={{
                    'data-testid': 'input-text',
                    autoComplete: 'new-password',
                  }}
                  onChange={(e) => onTextChange(e, 'tunnel_password')}
                  onKeyDown={onKeyDown}
                />
                <Button
                  data-test="toggle-tunnel-password-visibility"
                  onClick={() => setTunnelPasswordVisible(!tunnelPasswordVisible)}
                >
                  {tunnelPasswordVisible ? gettext('Hide password') : gettext('Show password')}
                </Button>
              </Box>
              {!hideSavePassword && (
                <Checkbox
                  label={gettext('Save Password')}
                  checked={Boolean(formData.save_tunnel_password)}
                  disabled={!data.allow_save_tunnel_password}
                  onChange={(checked) => onTextChange(Boolean(checked), 'save_tunnel_password')}
                />
              )}
            </>
          )}

          {data.prompt_password && (
            <>
              {requiresUserInput && (
                <TextField
                  label={gettext('User or principal')}
                  value={formData.connect_as}
                  inputProps={{
                    'data-testid': 'input-text',
                    maxLength: 255,
                    autoComplete: 'username',
                    placeholder: data.suggested_username || 'e.g. SYSDBA',
                    'aria-label': gettext('User or principal'),
                  }}
                  onChange={(event) => onTextChange(event, 'connect_as')}
                  onKeyDown={onKeyDown}
                />
              )}
              {data.allow_user_override && !requiresUserInput && (
                <Stack spacing={1}>
                  <Checkbox
                    label={gettext('Connect as a different user')}
                    checked={Boolean(formData.use_alternate_user)}
                    onChange={(checked) => {
                      const nextChecked = Boolean(checked);
                      setFormData((previous) => ({
                        ...previous,
                        use_alternate_user: nextChecked,
                        connect_as: nextChecked ? previous.connect_as : '',
                        save_password: nextChecked ? false : previous.save_password,
                      }));
                    }}
                  />
                  {formData.use_alternate_user && (
                    <TextField
                      label={gettext('Alternate user or principal')}
                      value={formData.connect_as}
                      inputProps={{
                        'data-testid': 'input-text',
                        maxLength: 255,
                        autoComplete: 'username',
                        'aria-label': gettext('Alternate user or principal'),
                      }}
                      onChange={(event) => onTextChange(event, 'connect_as')}
                      onKeyDown={onKeyDown}
                    />
                  )}
                </Stack>
              )}
              <div style={{fontWeight: 600}}>
                {((requiresUserInput || formData.use_alternate_user)
                  ? formData.connect_as.trim()
                  : data.username)
                  ? gettext(
                    'Please enter the password for the user \'%s\' to connect the server - "%s"',
                    (requiresUserInput || formData.use_alternate_user)
                      ? formData.connect_as.trim()
                      : data.username,
                    data.server_label
                  )
                  : gettext(
                    'Please enter the password for the user to connect the server - "%s"',
                    data.server_label
                  )}
              </div>
              <Box style={{display: 'flex', alignItems: 'center', gap: 8}}>
                <TextField
                  ref={(ele) => {
                    if (!data.prompt_tunnel_password) {
                      firstEleRef.current = ele;
                    }
                  }}
                  style={{flex: 1}}
                  type={passwordVisible ? 'text' : 'password'}
                  value={formData.password}
                  inputProps={{
                    'data-testid': 'input-text',
                    autoComplete: 'current-password',
                    'aria-label': gettext('Password'),
                  }}
                  onChange={(e) => onTextChange(e, 'password')}
                  onKeyDown={onKeyDown}
                />
                <Button
                  data-test="toggle-password-visibility"
                  onClick={() => setPasswordVisible(!passwordVisible)}
                >
                  {passwordVisible ? gettext('Hide password') : gettext('Show password')}
                </Button>
              </Box>
              {!hideSavePassword && (
                <Checkbox
                  label={gettext('Save Password')}
                  checked={Boolean(formData.save_password)}
                  disabled={
                    !data.allow_save_password ||
                    (formData.use_alternate_user && !requiresUserInput)
                  }
                  onChange={(checked) => onTextChange(Boolean(checked), 'save_password')}
                />
              )}
            </>
          )}

          {data.errmsg && <Banner tone="error">{data.errmsg}</Banner>}
        </Stack>
      </Box>
      <ModalFooter>
        <Button
          data-test="close"
          onClick={() => {
            closeModal();
          }}
        >
          {gettext('Cancel')}
        </Button>
        {(data.prompt_password || data.prompt_tunnel_password) && (
          <Button
            ref={okBtnRef}
            data-test="save"
            variant="primary"
            disabled={isSubmitDisabled}
            onClick={() => {
              const postFormData = new FormData();
              if (data.prompt_tunnel_password) {
                postFormData.append('tunnel_password', formData.tunnel_password);
                if (formData.save_tunnel_password) {
                  postFormData.append('save_tunnel_password', formData.save_tunnel_password);
                }
              }
              if (data.prompt_password) {
                postFormData.append('password', formData.password);
                if ((requiresUserInput || formData.use_alternate_user) && formData.connect_as.trim()) {
                  postFormData.append('connect_as', formData.connect_as.trim());
                }
                if (formData.save_password && (!formData.use_alternate_user || requiresUserInput)) {
                  postFormData.append('save_password', formData.save_password);
                }
              }
              onOK?.(postFormData);
              closeModal();
            }}
          >
            {gettext('OK')}
          </Button>
        )}
      </ModalFooter>
    </ModalContent>
  );
}

ConnectServerContent.propTypes = {
  closeModal: PropTypes.func,
  data: PropTypes.object,
  onOK: PropTypes.func,
  setHeight: PropTypes.func,
  hideSavePassword: PropTypes.bool,
};
