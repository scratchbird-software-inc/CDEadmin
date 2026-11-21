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
import {NumberField, TextField} from '../../primitives/Field';
import {Checkbox, Select} from '../../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import CodeEditor from '../../editors/CodeEditor';
import {PostgresqlSectionCard, createPostgresqlServerCaller} from './postgresqlAdminHelpers';

/**
 * PG-UI-03 (SR-F-030452): PostgreSQL High Availability, Standby Bootstrap,
 * Switchover, Production Destination Restore & Archive Retention Workspace.
 */
export default function PostgresqlHaTopologyWorkspace({
  endpointUrl,
  api: injectedApi = null,
}) {
  const api = useMemo(() => injectedApi || getApiInstance(), [injectedApi]);
  const callServer = useMemo(
    () => createPostgresqlServerCaller(api, endpointUrl),
    [api, endpointUrl]
  );

  const [topology, setTopology] = useState(null);
  const [haOp, setHaOp] = useState('standby_bootstrap');
  const [datadir, setDatadir] = useState('');
  const [standbyDsn, setStandbyDsn] = useState('');
  const [slotName, setSlotName] = useState('sr_standby_slot');
  const [standbyPort, setStandbyPort] = useState(5433);
  const [ctlAction, setCtlAction] = useState('status');
  const [reviewedHa, setReviewedHa] = useState(null);
  const [haConfirmed, setHaConfirmed] = useState(false);

  // Archive retention & hold controls
  const [archiveName, setArchiveName] = useState('');
  const [retentionEval, setRetentionEval] = useState(null);
  const [lastReceipt, setLastReceipt] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const refreshTopology = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const topo = await callServer({action: 'postgresql_ha_topology', request: {}});
      setTopology(topo);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  }, [callServer]);

  useEffect(() => {
    refreshTopology();
  }, [refreshTopology]);

  const handleReviewHa = async () => {
    setBusy(true);
    setError('');
    try {
      const options =
        haOp === 'standby_bootstrap'
          ? {
            standby_datadir: datadir.trim(),
            slot_name: slotName.trim(),
            create_slot: true,
            standby_port: Number(standbyPort) || 5433,
            start_standby: true,
          }
          : haOp === 'switchover'
            ? {standby_dsn: standbyDsn.trim(), wait_seconds: 30}
            : haOp === 'promote'
              ? {wait_seconds: 30, ...(standbyDsn.trim() ? {target_dsn: standbyDsn.trim()} : {})}
              : {datadir: datadir.trim(), ctl_action: ctlAction, stop_mode: 'fast'};
      const res = await callServer({
        action: 'postgresql_ha_review',
        request: {operation: haOp, options},
      });
      setReviewedHa(res);
      setHaConfirmed(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleStartHa = async () => {
    if (!reviewedHa || !haConfirmed) return;
    setBusy(true);
    setError('');
    try {
      const done = await callServer({
        action: 'postgresql_ha_start',
        request: {
          job_id: reviewedHa.job_id,
          review_digest: reviewedHa.review_digest,
          confirmed: true,
        },
      });
      setLastReceipt(done);
      setReviewedHa(null);
      await refreshTopology();
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleEvaluateRetention = async () => {
    if (!archiveName.trim()) return;
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'postgresql_continuity_archive_retention_evaluate',
        request: {archive: archiveName.trim()},
      });
      setRetentionEval(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack gap="md">
      <PostgresqlSectionCard
        title={gettext('Streaming Replication Topology, Failover & Host Control')}
        actions={<FormReference reference="SR-F-030452" />}
      >
        <Stack gap="sm">
          <Banner status="info">
            {gettext(
              'Inspects live primary/standby role, WAL lag and replication slots, and orchestrates standby bootstrap, promotion, fenced switchover, and granted host pg_ctl operations.'
            )}
          </Banner>
          {error && <ValidationMessage status="error">{error}</ValidationMessage>}
          {topology && (
            <Box>
              <Badge status={topology.in_recovery ? 'warning' : 'success'} label={topology.role?.toUpperCase()} />{' '}
              <span>
                {gettext('System ID:')} {topology.system_identifier} | {gettext('Timeline:')} {topology.timeline_id} | {gettext('LSN:')} {topology.wal_lsn} | {gettext('Standbys:')} {(topology.standbys || []).length}
              </span>
            </Box>
          )}
          <Grid columns={2} gap="sm">
            <Select
              label={gettext('HA / Host Operation')}
              value={haOp}
              options={[
                {value: 'standby_bootstrap', label: 'Bootstrap streaming standby (pg_basebackup -R)'},
                {value: 'promote', label: 'Promote standby to primary (pg_promote)'},
                {value: 'switchover', label: 'Coordinated switchover (fence primary + catchup + promote)'},
                {value: 'host_pg_ctl', label: 'Authorized host pg_ctl lifecycle'},
              ]}
              onChange={setHaOp}
            />
            {(haOp === 'standby_bootstrap' || haOp === 'host_pg_ctl') && (
              <TextField
                label={gettext('Granted Cluster Data Directory')}
                value={datadir}
                onChange={(e) => setDatadir(e?.target ? e.target.value : e)}
              />
            )}
            {haOp === 'standby_bootstrap' && (
              <>
                <TextField
                  label={gettext('Physical Replication Slot')}
                  value={slotName}
                  onChange={(e) => setSlotName(e?.target ? e.target.value : e)}
                />
                <NumberField
                  label={gettext('Standby Port')}
                  value={standbyPort}
                  min={1024}
                  max={65535}
                  onChange={(v) => setStandbyPort(Number(v) || 5433)}
                />
              </>
            )}
            {(haOp === 'switchover' || haOp === 'promote') && (
              <TextField
                label={gettext('Target Standby Connection DSN')}
                value={standbyDsn}
                onChange={(e) => setStandbyDsn(e?.target ? e.target.value : e)}
              />
            )}
            {haOp === 'host_pg_ctl' && (
              <Select
                label={gettext('pg_ctl Action')}
                value={ctlAction}
                options={[
                  {value: 'status', label: 'status'},
                  {value: 'start', label: 'start'},
                  {value: 'stop', label: 'stop (fast)'},
                  {value: 'restart', label: 'restart'},
                  {value: 'reload', label: 'reload'},
                ]}
                onChange={setCtlAction}
              />
            )}
          </Grid>
          <Stack direction="row" gap="sm">
            <Button variant="primary" disabled={busy} onClick={handleReviewHa}>
              {gettext('Review HA Operation')}
            </Button>
            <Button variant="secondary" disabled={busy} onClick={refreshTopology}>
              {gettext('Refresh Live Topology')}
            </Button>
          </Stack>
        </Stack>
      </PostgresqlSectionCard>

      {reviewedHa && (
        <PostgresqlSectionCard title={gettext('Reviewed HA Operation')}>
          <Stack gap="sm">
            <Checkbox
              label={gettext('Confirm HA operation execution (no automatic replay)')}
              checked={haConfirmed}
              onChange={setHaConfirmed}
            />
            <Button variant="primary" disabled={busy || !haConfirmed} onClick={handleStartHa}>
              {gettext('Execute Reviewed HA Operation')}
            </Button>
          </Stack>
        </PostgresqlSectionCard>
      )}

      <PostgresqlSectionCard title={gettext('WAL Archive Hold & Dependency-Aware Retention')}>
        <Stack gap="sm">
          <Grid columns={2} gap="sm">
            <TextField
              label={gettext('Owned WAL Archive Name')}
              value={archiveName}
              onChange={(e) => setArchiveName(e?.target ? e.target.value : e)}
            />
            <Box>
              <Button variant="secondary" disabled={busy || !archiveName.trim()} onClick={handleEvaluateRetention}>
                {gettext('Evaluate Archive Retention Floor')}
              </Button>
            </Box>
          </Grid>
          {(retentionEval || lastReceipt) && (
            <CodeEditor
              value={JSON.stringify(lastReceipt || retentionEval, null, 2)}
              language="json"
              readOnly
              height="180px"
            />
          )}
        </Stack>
      </PostgresqlSectionCard>
    </Stack>
  );
}

PostgresqlHaTopologyWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  api: PropTypes.object,
};
