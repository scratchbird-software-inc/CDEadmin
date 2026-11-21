/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Grid, Panel, Stack} from '../primitives/Layout';
import {Button} from '../primitives/Button';
import {TextField} from '../primitives/Field';
import {Checkbox, Select} from '../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../feedback/Indicators';
import {Dialog} from '../overlays/Dialog';
import FormReference from '../navigation/FormReference';
import {mysqlQueryAttributes} from '../editors/mysqlQueryAttributes';
import {parseMySQLPlan} from '../../Dialogs/mysqlPlanPresentation';

/**
 * MYSQL-UI-04 (SR-F-030201): MySQL Per-Statement QUERY_ATTRIBUTES &
 * Session Autocommit / Implicit-DDL Observation Dialog.
 */
export function SqlMySQLQueryAttributesDialog({
  open,
  attributesObject = {},
  transaction = null,
  onSaveAttributes,
  onClose,
}) {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    const initialEntries = Object.entries(attributesObject || {}).map(([name, val]) => ({
      name,
      type: typeof val === 'number' ? 'number' : typeof val === 'boolean' ? 'boolean' : 'string',
      value: val === null ? '' : String(val),
    }));
    setRows(initialEntries);
    setError('');
  }, [attributesObject, open]);

  if (!open) return null;

  const nativeTx = transaction?.provider_payload || {};
  const observedBool = (v) => (typeof v === 'boolean' ? (v ? gettext('On') : gettext('Off')) : gettext('Not observed'));

  const addRow = () => {
    setRows((cur) => [...cur, {name: '', type: 'string', value: ''}]);
  };

  const updateRow = (idx, patch) => {
    setRows((cur) => cur.map((r, i) => (i === idx ? {...r, ...patch} : r)));
  };

  const removeRow = (idx) => {
    setRows((cur) => cur.filter((_r, i) => i !== idx));
  };

  const handleSave = () => {
    setError('');
    try {
      const nextObj = {};
      for (const r of rows) {
        const key = r.name.trim();
        if (!key) continue;
        if (Object.prototype.hasOwnProperty.call(nextObj, key)) {
          throw new Error(gettext('Duplicate MySQL query attribute name: %s', key));
        }
        if (r.type === 'number') {
          const n = Number(r.value);
          if (!Number.isFinite(n)) throw new Error(gettext('Numeric query attribute "%s" must be finite.', key));
          nextObj[key] = n;
        } else if (r.type === 'boolean') {
          nextObj[key] = ['true', '1', 'yes', 'on'].includes(String(r.value).trim().toLowerCase());
        } else {
          nextObj[key] = r.value;
        }
      }
      const validated = mysqlQueryAttributes(JSON.stringify(nextObj));
      onSaveAttributes(validated);
      onClose();
    } catch (err) {
      setError(err?.message || String(err));
    }
  };

  return (
    <Dialog
      open={open}
      title={gettext('MySQL Per-Statement Query Attributes & Session Observation')}
      formReference="SR-F-030201"
      size="large"
      onClose={onClose}
      actions={
        <>
          <Button intent="neutral" onClick={onClose}>
            {gettext('Cancel')}
          </Button>
          <Button intent="neutral" onClick={() => setRows([])}>
            {gettext('Clear All')}
          </Button>
          <Button intent="primary" onClick={handleSave}>
            {gettext('Save Query Attributes')}
          </Button>
        </>
      }
    >
      <Stack gap="comfortable" data-cdeadmin-qa-key="sql-surface.mysql-query-attributes">
        <Banner status="info">
          {gettext(
            'MySQL DDL statements can implicitly commit active transactions, and rollback does not undo changes to non-transactional tables. Query attributes are sent via wire protocol and read via mysql_query_attribute_string() when query_attributes is installed.'
          )}
        </Banner>

        {error && <ValidationMessage status="error">{error}</ValidationMessage>}

        <Panel variant="outlined" style={{padding: 12}}>
          <Stack gap="standard">
            <strong>{gettext('Observed Native Session Transaction State')}</strong>
            <table style={{width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem'}} aria-label={gettext('MySQL session observation')}>
              <tbody>
                <tr style={{borderBottom: '1px solid var(--sr-border-subtle)'}}>
                  <th style={{textAlign: 'left', padding: 6}}>{gettext('Session state')}</th>
                  <td style={{padding: 6}}>{nativeTx.state || gettext('Not observed')}</td>
                </tr>
                <tr style={{borderBottom: '1px solid var(--sr-border-subtle)'}}>
                  <th style={{textAlign: 'left', padding: 6}}>{gettext('Autocommit (observed)')}</th>
                  <td style={{padding: 6}}>{observedBool(nativeTx.autocommit)}</td>
                </tr>
                <tr>
                  <th style={{textAlign: 'left', padding: 6}}>{gettext('In transaction (observed)')}</th>
                  <td style={{padding: 6}}>{observedBool(nativeTx.in_transaction)}</td>
                </tr>
              </tbody>
            </table>
          </Stack>
        </Panel>

        <Panel variant="outlined" style={{padding: 12}}>
          <Stack gap="standard">
            <Stack direction="row" gap="standard" style={{alignItems: 'center', justifyContent: 'space-between'}}>
              <strong>{gettext('Per-Statement Wire Query Attributes (%s)', rows.length)}</strong>
              <Button size="small" intent="neutral" onClick={addRow}>
                {gettext('Add Attribute')}
              </Button>
            </Stack>
            {rows.length === 0 ? (
              <Box sx={{fontSize: '0.8rem'}}>{gettext('No per-statement query attributes configured.')}</Box>
            ) : (
              rows.map((row, idx) => (
                <Grid key={idx} columns="minmax(160px, 2fr) minmax(110px, 1fr) minmax(180px, 2fr) auto">
                  <TextField
                    label={gettext('Attribute name')}
                    size="small"
                    value={row.name}
                    onChange={(e) => updateRow(idx, {name: e.target.value})}
                  />
                  <Select
                    label={gettext('Type')}
                    size="small"
                    options={[
                      {value: 'string', label: gettext('String')},
                      {value: 'number', label: gettext('Number')},
                      {value: 'boolean', label: gettext('Boolean')},
                    ]}
                    value={row.type}
                    onChange={(v) => updateRow(idx, {type: v})}
                  />
                  <TextField
                    label={gettext('Attribute value')}
                    size="small"
                    value={row.value}
                    onChange={(e) => updateRow(idx, {value: e.target.value})}
                  />
                  <Box style={{display: 'flex', alignItems: 'flex-end'}}>
                    <Button size="small" intent="destructive" onClick={() => removeRow(idx)}>
                      {gettext('Remove')}
                    </Button>
                  </Box>
                </Grid>
              ))
            )}
          </Stack>
        </Panel>
      </Stack>
    </Dialog>
  );
}

SqlMySQLQueryAttributesDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  attributesObject: PropTypes.object,
  transaction: PropTypes.object,
  onSaveAttributes: PropTypes.func.isRequired,
  onClose: PropTypes.func.isRequired,
};

/**
 * MYSQL-UI-05: Explicit confirmation before running MySQL EXPLAIN ANALYZE
 * (which executes the statement on the live session).
 */
export function SqlMySQLAnalyzeConsentDialog({open, busy = false, onConfirm, onClose}) {
  const [confirmed, setConfirmed] = useState(false);

  useEffect(() => {
    if (open) setConfirmed(false);
  }, [open]);

  if (!open) return null;

  return (
    <Dialog
      open={open}
      title={gettext('Run MySQL EXPLAIN ANALYZE (Executes Statement)')}
      size="medium"
      onClose={onClose}
      actions={
        <>
          <Button intent="neutral" disabled={busy} onClick={onClose}>
            {gettext('Cancel')}
          </Button>
          <Button intent="primary" disabled={busy || !confirmed} onClick={onConfirm}>
            {gettext('Execute EXPLAIN ANALYZE')}
          </Button>
        </>
      }
    >
      <Stack gap="standard">
        <Banner status="warning">
          {gettext(
            'Unlike EXPLAIN FORMAT=JSON, MySQL EXPLAIN ANALYZE actually executes the statement on the active session to measure real iterator timings and row counts. A displayed plan does not commit or roll back changes.'
          )}
        </Banner>
        <Checkbox
          label={gettext('I understand EXPLAIN ANALYZE executes this statement on the active MySQL session')}
          checked={confirmed}
          onChange={setConfirmed}
        />
      </Stack>
    </Dialog>
  );
}

SqlMySQLAnalyzeConsentDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  busy: PropTypes.bool,
  onConfirm: PropTypes.func.isRequired,
  onClose: PropTypes.func.isRequired,
};

function MySQLPlanTreeItem({id, graph, selectedId, onSelect}) {
  const node = graph.nodes[id];
  const [expanded, setExpanded] = useState(true);
  return (
    <li role="treeitem" aria-label={node.label} aria-selected={selectedId === id} style={{listStyle: 'none', marginTop: 6}}>
      <Stack direction="row" gap="compact" style={{alignItems: 'flex-start'}}>
        {node.children.length > 0 && (
          <Button size="small" intent="neutral" onClick={() => setExpanded((v) => !v)}>
            {expanded ? '−' : '+'}
          </Button>
        )}
        <button
          type="button"
          onClick={() => onSelect(id)}
          style={{
            textAlign: 'left',
            padding: '6px 10px',
            border: selectedId === id ? '2px solid var(--sr-accent-primary, #2563eb)' : '1px solid var(--sr-border-default, #ccc)',
            background: 'var(--sr-surface-elevated, transparent)',
            color: 'inherit',
            borderRadius: 4,
            cursor: 'pointer',
            width: '100%',
          }}
        >
          <div style={{fontWeight: 600, fontSize: '0.82rem'}}>{node.label}</div>
          <div style={{fontSize: '0.74rem', opacity: 0.8}}>
            {node.actual ? gettext('Native actual measurements') : gettext('Native optimizer estimates')}
          </div>
          {node.facts
            .filter((fact) => /cost|rows|time|loops|access_type|table_name|key$|native estimates|native actuals/.test(fact.name))
            .slice(0, 6)
            .map((fact) => (
              <div key={fact.name} style={{fontSize: '0.75rem', fontFamily: 'monospace'}}>
                {fact.name}: {fact.value}
              </div>
            ))}
        </button>
      </Stack>
      {node.children.length > 0 && expanded && (
        <ul role="group" style={{paddingLeft: 18, margin: '4px 0 0 8px', borderLeft: '1px solid var(--sr-border-subtle, #ddd)'}}>
          {node.children.map((childId) => (
            <MySQLPlanTreeItem key={childId} id={childId} graph={graph} selectedId={selectedId} onSelect={onSelect} />
          ))}
        </ul>
      )}
    </li>
  );
}

MySQLPlanTreeItem.propTypes = {
  id: PropTypes.number.isRequired,
  graph: PropTypes.object.isRequired,
  selectedId: PropTypes.number,
  onSelect: PropTypes.func.isRequired,
};

/**
 * MYSQL-UI-05 (SR-F-001370): Interactive Native MySQL Operator Graph & Diagnostics
 * in SqlEditorSurface's Metrics & Plan view.
 */
export function SqlMySQLPlanGraphView({planText = '', mysqlDiagnostics = null}) {
  const graph = useMemo(() => (planText ? parseMySQLPlan(planText) : {available: false}), [planText]);
  const [selectedId, setSelectedId] = useState(0);

  if (!graph.available && !mysqlDiagnostics) return null;
  const selectedNode = graph.nodes?.[selectedId] || graph.nodes?.[0] || null;

  return (
    <Stack gap="comfortable" data-cdeadmin-qa-key="sql-surface.mysql-plan-graph">
      {mysqlDiagnostics?.session_reuse_blocked && (
        <Banner status="warning">
          {gettext('MySQL session outcome is uncertain; close and reconnect before replaying mutating statements.')}
        </Banner>
      )}
      {mysqlDiagnostics?.error?.query_dispatch === 'partially_started' && (
        <Banner status="warning">
          {gettext('MySQL multi-statement or streamed dispatch was partially started before failure; inspect session transaction state.')}
        </Banner>
      )}

      {graph.available && (
        <Panel variant="outlined" style={{padding: 12}}>
          <Stack gap="standard">
            <Stack direction="row" gap="standard" style={{alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap'}}>
              <Stack direction="row" gap="standard" style={{alignItems: 'center'}}>
                <strong>{gettext('Interactive MySQL Operator Plan (%s)', graph.format)}</strong>
                <Badge label={`${graph.nodes.length} ${gettext('nodes')}`} status={graph.hasActual ? 'success' : 'info'} />
              </Stack>
              <FormReference formKey="mysql-query-plan" />
            </Stack>

            <Grid columns="minmax(260px, 3fr) minmax(220px, 2fr)">
              <Box style={{maxHeight: 420, overflow: 'auto', paddingRight: 6}}>
                <ul role="tree" aria-label={gettext('Native MySQL operator graph')} style={{margin: 0, paddingLeft: 4}}>
                  {graph.roots.map((rootId) => (
                    <MySQLPlanTreeItem
                      key={rootId}
                      id={rootId}
                      graph={graph}
                      selectedId={selectedNode?.id}
                      onSelect={setSelectedId}
                    />
                  ))}
                </ul>
              </Box>

              {selectedNode && (
                <Panel variant="outlined" style={{padding: 10, maxHeight: 420, overflow: 'auto'}} aria-label={gettext('Selected native operator')}>
                  <Stack gap="compact">
                    <strong>{selectedNode.label}</strong>
                    <code style={{fontSize: '0.75rem'}}>{selectedNode.path}</code>
                    <dl style={{margin: 0, fontSize: '0.78rem'}}>
                      {selectedNode.facts.map((fact, idx) => (
                        <div key={idx} style={{marginTop: 6}}>
                          <dt style={{fontWeight: 600}}>{fact.name}</dt>
                          <dd style={{margin: 0, fontFamily: 'monospace', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>
                            {fact.value}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </Stack>
                </Panel>
              )}
            </Grid>
          </Stack>
        </Panel>
      )}
    </Stack>
  );
}

SqlMySQLPlanGraphView.propTypes = {
  planText: PropTypes.string,
  mysqlDiagnostics: PropTypes.object,
};
