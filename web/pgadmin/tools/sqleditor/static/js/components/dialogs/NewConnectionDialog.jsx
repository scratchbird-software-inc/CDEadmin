/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useContext, useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import _ from 'lodash';
import gettext from 'sources/gettext';
import url_for from 'sources/url_for';
import {
  DialogContent as ModalContent,
  DialogFooter as ModalFooter,
} from 'sources/cdeadmin_ui/overlays/DialogLayout';
import {Box, Stack} from '../../../../../../static/js/cdeadmin_ui/primitives/Layout';
import {Button} from '../../../../../../static/js/cdeadmin_ui/primitives/Button';
import {Select} from '../../../../../../static/js/cdeadmin_ui/primitives/Choice';
import {Banner} from '../../../../../../static/js/cdeadmin_ui/feedback/Indicators';
import ConnectServerContent from '../../../../../../static/js/Dialogs/ConnectServerContent';
import {usePgAdmin} from '../../../../../../static/js/PgAdminProvider';
import {QueryToolContext} from '../QueryToolComponent';

export default function NewConnectionDialog({onClose, onSave}) {
  const queryToolCtx = useContext(QueryToolContext);
  const pgAdmin = usePgAdmin();

  const [servers, setServers] = useState([]);
  const [sid, setSid] = useState('');
  const [did, setDid] = useState('');
  const [user, setUser] = useState('');
  const [role, setRole] = useState('');
  const [databases, setDatabases] = useState([]);
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [connecting, setConnecting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [confirmSwitch, setConfirmSwitch] = useState(false);
  const [error, setError] = useState('');

  const connectServer = useCallback(
    async (targetSid, targetUser, formData, connectCallback) => {
      setConnecting(true);
      setError('');
      try {
        const {data: respData} = await queryToolCtx.api({
          method: 'POST',
          url: url_for('sqleditor.connect_server', {
            sid: targetSid,
            ...(targetUser ? {usr: targetUser} : {}),
          }),
          headers: {'Content-Type': 'application/x-www-form-urlencoded'},
          data: formData,
        });
        setConnecting(false);
        connectCallback?.(respData.data);
      } catch (err) {
        if (!err.response) {
          setConnecting(false);
          pgAdmin.Browser.notifier.pgNotifier(
            'error',
            err,
            'Connection error',
            gettext('Connection to ScratchRobin server has been lost.')
          );
        } else {
          queryToolCtx.modal.showModal(
            gettext('Connect to server'),
            (closeModal) => (
              <ConnectServerContent
                closeModal={() => {
                  setConnecting(false);
                  closeModal();
                }}
                data={err.response?.data?.result}
                onOK={(nextFormData) => {
                  connectServer(targetSid, null, nextFormData, connectCallback);
                }}
              />
            )
          );
        }
      }
    },
    [pgAdmin, queryToolCtx]
  );

  const loadDependentOptions = useCallback(
    async (targetSid) => {
      if (!targetSid) return;
      try {
        const [dbResp, userResp, roleResp] = await Promise.all([
          queryToolCtx.api.get(
            url_for('sqleditor.get_new_connection_database', {
              sid: targetSid,
              sgid: 0,
            })
          ),
          queryToolCtx.api.get(
            url_for('sqleditor.get_new_connection_user', {
              sid: targetSid,
              sgid: 0,
            })
          ),
          queryToolCtx.api.get(
            url_for('sqleditor.get_new_connection_role', {
              sid: targetSid,
              sgid: 0,
            })
          ),
        ]);
        const dbList = dbResp.data?.data?.result?.data || [];
        const userList = userResp.data?.data?.result?.data || [];
        const roleList = roleResp.data?.data?.result?.data || [];
        setDatabases(dbList);
        setUsers(userList);
        setRoles(roleList);
        const selDb = dbList.find((d) => d.selected) || dbList[0];
        const selUser = userList.find((u) => u.selected) || userList[0];
        setDid(selDb ? String(selDb.value) : '');
        setUser(selUser ? String(selUser.value) : '');
        setRole('');
      } catch (err) {
        setError(
          err?.response?.data?.errormsg ||
            err?.message ||
            gettext('Something went wrong')
        );
      }
    },
    [queryToolCtx]
  );

  const handleSelectServer = useCallback(
    (nextSidStr, serverListOverride = null) => {
      setSid(nextSidStr);
      setDid('');
      setUser('');
      setRole('');
      setDatabases([]);
      setUsers([]);
      setRoles([]);
      setConfirmSwitch(false);
      const list = serverListOverride || servers;
      const found = list.find((s) => String(s.value) === String(nextSidStr));
      if (!found) return;
      if (found.connected) {
        loadDependentOptions(found.value);
      } else {
        connectServer(found.value, null, null, (connInfo) => {
          setServers((prev) =>
            prev.map((item) =>
              String(item.value) === String(found.value)
                ? {...item, connected: true, image: connInfo?.icon || item.image}
                : item
            )
          );
          loadDependentOptions(found.value);
        });
      }
    },
    [connectServer, loadDependentOptions, servers]
  );

  useEffect(() => {
    let active = true;
    queryToolCtx.api
      .get(url_for('sqleditor.get_new_connection_servers'))
      .then(({data: respData}) => {
        if (!active) return;
        const flat = [];
        _.forIn(respData.data?.result?.server_list || {}, (groupItems, groupName) => {
          (groupItems || []).forEach((item) => {
            flat.push({
              ...item,
              group: groupName,
              displayLabel: groupName ? `${groupName} — ${item.label}` : item.label,
            });
          });
        });
        setServers(flat);
        const defaultServer =
          flat.find((s) => String(s.value) === String(queryToolCtx.params?.sid)) ||
          flat[0];
        if (defaultServer) {
          handleSelectServer(String(defaultServer.value), flat);
        }
      })
      .catch((err) => {
        if (active) {
          setError(err?.message || gettext('Something went wrong'));
        }
      });
    return () => {
      active = false;
    };
  }, [queryToolCtx]);

  const selectedServer = useMemo(
    () => servers.find((s) => String(s.value) === String(sid)),
    [servers, sid]
  );
  const selectedDatabase = useMemo(
    () => databases.find((d) => String(d.value) === String(did)),
    [databases, did]
  );

  const canSave =
    !connecting &&
    !saving &&
    Boolean(selectedServer?.connected) &&
    Boolean(sid) &&
    Boolean(did) &&
    Boolean(user);

  const handleSave = async () => {
    if (!canSave) return;
    if (!confirmSwitch) {
      setConfirmSwitch(true);
      return;
    }
    setSaving(true);
    setError('');
    try {
      await onSave?.(true, {
        sid: selectedServer.value,
        did: selectedDatabase?.value ?? did,
        user,
        role: role || null,
        server_name: selectedServer.label,
        database_name: selectedDatabase?.label ?? '',
        bgcolor: selectedServer.bgcolor,
        fgcolor: selectedServer.fgcolor,
        connected: true,
      });
    } catch (err) {
      setError(err?.message || gettext('Something went wrong'));
      setConfirmSwitch(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalContent>
      <Box style={{flexGrow: 1, padding: 16, overflow: 'auto'}}>
        <Stack spacing={1.5}>
          {connecting && (
            <Banner tone="info">{gettext('Connecting...')}</Banner>
          )}
          <Select
            label={gettext('Server')}
            value={String(sid)}
            disabled={connecting || saving}
            required
            options={servers.map((s) => ({
              value: String(s.value),
              label: s.displayLabel || s.label,
            }))}
            onChange={(val) => handleSelectServer(val)}
          />
          <Select
            label={gettext('Database')}
            value={String(did)}
            disabled={connecting || saving || !selectedServer?.connected}
            required
            options={databases.map((d) => ({
              value: String(d.value),
              label: d.label,
            }))}
            onChange={(val) => {
              setDid(val);
              setConfirmSwitch(false);
            }}
          />
          <Select
            label={gettext('User')}
            value={String(user)}
            disabled={connecting || saving || !selectedServer?.connected}
            required
            options={users.map((u) => ({
              value: String(u.value),
              label: u.label,
            }))}
            onChange={(val) => {
              setUser(val);
              setConfirmSwitch(false);
            }}
          />
          <Select
            label={gettext('Role')}
            value={String(role)}
            disabled={connecting || saving || !selectedServer?.connected}
            options={[
              {value: '', label: ''},
              ...roles.map((r) => ({
                value: String(r.value),
                label: r.label,
              })),
            ]}
            onChange={(val) => {
              setRole(val);
              setConfirmSwitch(false);
            }}
          />
          {confirmSwitch && (
            <Banner tone="warning">
              {gettext(
                'By changing the connection you will lose all your unsaved data for the current connection. Click "Save" again to continue.'
              )}
            </Banner>
          )}
          {error && <Banner tone="error">{error}</Banner>}
        </Stack>
      </Box>
      <ModalFooter>
        <Button
          data-test="Close"
          disabled={saving}
          onClick={() => {
            if (confirmSwitch) {
              setConfirmSwitch(false);
            } else {
              onClose?.();
            }
          }}
        >
          {gettext('Cancel')}
        </Button>
        <Button
          data-test="Save"
          variant="primary"
          disabled={!canSave}
          onClick={handleSave}
        >
          {gettext('Save')}
        </Button>
      </ModalFooter>
    </ModalContent>
  );
}

NewConnectionDialog.propTypes = {
  onClose: PropTypes.func,
  onSave: PropTypes.func,
};
