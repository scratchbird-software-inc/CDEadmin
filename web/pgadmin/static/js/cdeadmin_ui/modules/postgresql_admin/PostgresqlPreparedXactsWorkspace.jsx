/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import getApiInstance from 'sources/api_instance';
import {Box, Grid, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {TextField} from '../../primitives/Field';
import {Checkbox, Select} from '../../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import {PostgresqlSectionCard, createPostgresqlServerCaller} from './postgresqlAdminHelpers';

/**
 * PG-UI-04 (SR-F-030453): PostgreSQL Two-Phase Prepared Transaction Recovery Workspace.
 */
export default function PostgresqlPreparedXactsWorkspace({
  endpointUrl,
  api: injectedApi = null,
}) {
  const api = useMemo(() => injectedApi || getApiInstance(), [injectedApi]);
  const callServer = useMemo(
    () => createPostgresqlServerCaller(api, endpointUrl),
    [api, endpointUrl]
  );

  const [serverResource, setServerResource] = useState(null);
  const [xacts, setXacts] = useState([]);
  const [selectedGid, setSelectedGid] = useState('');
  const [actionMode, setActionMode] = useState('ROLLBACK');
  const [confirmation, setConfirmation] = useState('');
  const [reviewedPlan, setReviewedPlan] = useState(null);
  const [confirmedApply, setConfirmedApply] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const loadPrepared = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const page = await callServer({action: 'resource_page', request: {}});
      const srv = (page?.items || []).find((r) => r.resource_kind === 'server') || null;
      setServerResource(srv);
      if (srv) {
        const plan = await callServer({
          action: 'visual_admin_plan',
          request: {
            resource_kind: 'server',
            operation_id: 'inspect-prepared-transactions',
            target_resource: srv,
            draft: {},
          },
        });
        const applied = await callServer({
          action: 'visual_admin_apply',
          request: {
            plan_id: plan.plan_id,
            plan_digest: plan.plan_digest,
            confirmed: true,
          },
        });
        setXacts(applied?.result?.rows || []);
      }
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  }, [callServer]);

  useEffect(() => {
    loadPrepared();
  }, [loadPrepared]);

  const handleReviewResolve = async () => {
    if (!serverResource || !selectedGid.trim()) return;
    setBusy(true);
    setError('');
    try {
      const matchedTx = xacts.find((t) => t.gid === selectedGid.trim()) || {};
      const plan = await callServer({
        action: 'visual_admin_plan',
        request: {
          resource_kind: 'server',
          operation_id: 'resolve-prepared-transaction',
          target_resource: serverResource,
          draft: {
            gid: selectedGid.trim(),
            expected_database: matchedTx.database || 'postgres',
            expected_owner: matchedTx.owner || 'postgres',
            ...(matchedTx.xid || matchedTx.transaction ? {expected_xid: String(matchedTx.xid || matchedTx.transaction)} : {}),
            coordinator_reference: 'operator-console-review',
            decision: actionMode,
            confirmation: confirmation.trim(),
          },
        },
      });
      setReviewedPlan(plan);
      setConfirmedApply(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleApplyResolve = async () => {
    if (!reviewedPlan || !confirmedApply) return;
    setBusy(true);
    setError('');
    try {
      await callServer({
        action: 'visual_admin_apply',
        request: {
          plan_id: reviewedPlan.plan_id,
          plan_digest: reviewedPlan.plan_digest,
          confirmed: true,
        },
      });
      setReviewedPlan(null);
      setSelectedGid('');
      setConfirmation('');
      await loadPrepared();
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack gap="md">
      <PostgresqlSectionCard
        title={gettext('Two-Phase Prepared Transactions (pg_prepared_xacts)')}
        actions={<FormReference reference="SR-F-030453" />}
      >
        <Stack gap="sm">
          <Banner status="warning">
            {gettext(
              'COMMIT PREPARED and ROLLBACK PREPARED run outside a transaction block after re-verifying exact GID, database, owner, and XID identity.'
            )}
          </Banner>
          {error && <ValidationMessage status="error">{error}</ValidationMessage>}
          <Box>
            <Badge status={xacts.length > 0 ? 'warning' : 'success'} label={`${xacts.length} ${gettext('Prepared Transactions')}`} />
          </Box>
          {xacts.map((tx) => (
            <Stack key={tx.gid} direction="row" gap="sm">
              <Badge status="info" label={tx.gid} />
              <span>{`${tx.database} | ${tx.owner} | XID ${tx.transaction}`}</span>
              <Button
                variant="secondary"
                onClick={() => {
                  setSelectedGid(tx.gid);
                  setConfirmation(tx.gid);
                }}
              >
                {gettext('Select')}
              </Button>
            </Stack>
          ))}
          <Grid columns={3} gap="sm">
            <TextField
              label={gettext('Prepared Transaction GID')}
              value={selectedGid}
              onChange={(e) => setSelectedGid(e?.target ? e.target.value : e)}
            />
            <Select
              label={gettext('Resolution Action')}
              value={actionMode}
              options={[
                {value: 'ROLLBACK', label: 'ROLLBACK PREPARED'},
                {value: 'COMMIT', label: 'COMMIT PREPARED'},
              ]}
              onChange={setActionMode}
            />
            <TextField
              label={gettext('Type Exact GID to Confirm')}
              value={confirmation}
              onChange={(e) => setConfirmation(e?.target ? e.target.value : e)}
            />
          </Grid>
          <Stack direction="row" gap="sm">
            <Button variant="primary" disabled={busy || !selectedGid.trim()} onClick={handleReviewResolve}>
              {gettext('Review Two-Phase Resolution')}
            </Button>
            <Button variant="secondary" disabled={busy} onClick={loadPrepared}>
              {gettext('Refresh Prepared List')}
            </Button>
          </Stack>
        </Stack>
      </PostgresqlSectionCard>

      {reviewedPlan && (
        <PostgresqlSectionCard title={gettext('Prepared Resolution Command Preview')}>
          <Stack gap="sm">
            <Box>{reviewedPlan?.command_preview?.statement}</Box>
            <Checkbox
              label={gettext('Confirm irreversible two-phase transaction settlement')}
              checked={confirmedApply}
              onChange={setConfirmedApply}
            />
            <Button variant="primary" disabled={busy || !confirmedApply} onClick={handleApplyResolve}>
              {gettext('Execute Resolution')}
            </Button>
          </Stack>
        </PostgresqlSectionCard>
      )}
    </Stack>
  );
}

PostgresqlPreparedXactsWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  api: PropTypes.object,
};
