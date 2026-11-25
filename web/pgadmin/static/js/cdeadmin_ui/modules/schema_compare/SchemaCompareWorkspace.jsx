/////////////////////////////////////////////////////////////
// Schema Comparison module surfaces in the shared CDEadmin shell.
/////////////////////////////////////////////////////////////

import React, {useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {useLocaleRevision} from '../../actions/t_actions';
import {Box} from '../../primitives/Layout';
import {ScratchScrollArea} from '../../base/ScratchScrollArea';
import {Button} from '../../primitives/Button';
import {Checkbox, Select} from '../../primitives/Choice';
import {TextArea} from '../../primitives/Field';
import {SearchField} from '../../primitives/AdvancedControls';
import {ResourcePicker, AssetPicker, TreeRow} from '../../navigation/AdvancedNavigation';
import {Tab} from '../../navigation/TabsAndBreadcrumbs';
import {Toolbar} from '../../layout/WorkbenchChrome';
import {Banner, Badge, ProgressBar, Skeleton} from '../../feedback/Indicators';
import {EmptyState} from '../../feedback/EmptyState';
import {ScratchDiffTable} from '../../data/beautiful';
import FormReference from '../../navigation/FormReference';

export const SCHEMA_COMPARE_SURFACES = Object.freeze([
  {id: 'compare_setup', title: 'Compare Setup'},
  {id: 'diff_tree', title: 'Diff Tree'},
  {id: 'object_diff', title: 'Object Diff'},
  {id: 'mapping_review', title: 'Mapping Review'},
  {id: 'change_plan', title: 'Change Plan'},
  {id: 'apply_export_review', title: 'Apply/Export Review'},
]);

function useSession(service, sessionId) {
  const [session, setSession] = useState(() => service.get(sessionId));
  useEffect(() => service.subscribe((next) => {
    if(next.id === sessionId) setSession(next);
  }), [service, sessionId]);
  return session;
}

function statusColor(state) {
  if(['runtime_failure', 'validation_error', 'permission_denied'].includes(state)) return 'error';
  if(['stale', 'partial', 'disconnected'].includes(state)) return 'warning';
  if(state === 'ready') return 'success';
  return 'info';
}

function StateBoundary({session, children}) {
  return <>
    {session.state === 'background_task_active' && <Box sx={{p: 1}}>
      <ProgressBar label="Schema Comparison task" status="indeterminate" />
    </Box>}
    {session.state === 'loading' && <Box sx={{p: 2}}><Skeleton lines={8} /></Box>}
    {session.error && <Box sx={{p: 1}}><Banner status="error">{session.error}</Banner></Box>}
    {['stale', 'partial', 'disconnected', 'read_only'].includes(session.state) &&
      <Box sx={{p: 1}}><Banner status="warning">
        {session.state === 'stale' ?
          'The displayed result is stale. Run comparison again before planning or applying.' :
          `Schema Comparison is ${session.state.replace('_', ' ')}.`}
      </Banner></Box>}
    {children}
  </>;
}

StateBoundary.propTypes = {session: PropTypes.object.isRequired, children: PropTypes.node};

function SourceCard({side, reference, onChooseResource, onChooseAsset, disabled}) {
  return <Box component="section" aria-label={gettext('%s comparison source', side)}
    sx={{border: '1px solid', borderColor: 'divider', p: 2, minWidth: 280, flex: 1}}>
    <Box component="h3" sx={{m: 0, mb: 1}}>{gettext('%s source', side)}</Box>
    {reference ? <Box component="dl" sx={{m: 0}}>
      <dt>{gettext('Type')}</dt><dd>{reference.schema ?? reference.assetType}</dd>
      <dt>{gettext('Identity')}</dt><dd>{reference.canonical ??
        `${reference.projectId}/${reference.assetId}`}</dd>
    </Box> : <EmptyState message={gettext('Choose the %s source.', side.toLowerCase())} />}
    <Box sx={{display: 'flex', gap: 1, mt: 2}}>
      <Button disabled={disabled} onClick={onChooseResource}>{gettext('Choose live resource')}</Button>
      <Button disabled={disabled} onClick={onChooseAsset}>{gettext('Choose project asset')}</Button>
    </Box>
  </Box>;
}

SourceCard.propTypes = {
  side: PropTypes.string.isRequired,
  reference: PropTypes.object,
  onChooseResource: PropTypes.func,
  onChooseAsset: PropTypes.func,
  disabled: PropTypes.bool,
};

function CompareSetup({session, invoke, resources, assets, requestedPickerSide, onClearRequestedPicker}) {
  const [picker, setPicker] = useState(null);
  useEffect(() => {
    if (requestedPickerSide) {
      setPicker({side: requestedPickerSide, kind: 'resource'});
      onClearRequestedPicker?.();
    }
  }, [requestedPickerSide, onClearRequestedPicker]);
  const choose = (item) => {
    invoke('schema_compare.session.create', {
      configureSessionId: session.id,
      [picker.side === 'Left' ? 'leftRef' : 'rightRef']: item.reference,
    });
    setPicker(null);
  };
  const busy = session.state === 'background_task_active';
  return <ScratchScrollArea orientation="both" style={{height: '100%'}}>
    <Box sx={{p: 2}}>
      <Box component="h2" sx={{mt: 0}}>{gettext('Compare Setup')}</Box>
      <Box sx={{display: 'flex', flexWrap: 'wrap', gap: 2}}>
        {['Left', 'Right'].map((side) => <SourceCard key={side} side={side}
          reference={side === 'Left' ? session.content.leftRef : session.content.rightRef}
          disabled={busy}
          onChooseResource={() => setPicker({side, kind: 'resource'})}
          onChooseAsset={() => setPicker({side, kind: 'asset'})} />)}
      </Box>
      <Box component="fieldset" sx={{mt: 2, border: '1px solid', borderColor: 'divider', p: 1.5}}>
        <legend>{gettext('Comparison scope and normalization options')}</legend>
        <Box sx={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 1}}>
          {[
            ['ignoreWhitespace', gettext('Ignore SQL body whitespace differences')],
            ['ignoreComments', gettext('Ignore SQL comment differences')],
            ['includeGrants', gettext('Include object privileges and grants')],
            ['caseSensitiveIdentifiers', gettext('Case-sensitive unquoted identifier comparison')],
            ['includeSystemObjects', gettext('Include engine system objects')],
          ].map(([optKey, optLabel]) => (
            <Checkbox
              key={optKey}
              label={optLabel}
              disabled={busy}
              checked={Boolean(session.content.options?.[optKey])}
              onChange={(checked) => invoke('schema_compare.session.create', {
                configureSessionId: session.id,
                options: {...(session.content.options || {}), [optKey]: Boolean(checked)},
              })}
            />
          ))}
        </Box>
        <Box component="details" sx={{mt: 1}}>
          <Box component="summary" sx={{cursor: 'pointer', fontSize: '0.75rem'}}>
            {gettext('Options (JSON)')}
          </Box>
          <TextArea rows={4} fullWidth label={gettext('Options (JSON)')} readOnly
            value={JSON.stringify(session.content.options, null, 2)} />
        </Box>
      </Box>
      <Box sx={{mt: 2}}><Button intent="primary" disabled={busy ||
        !session.content.leftRef || !session.content.rightRef}
      onClick={() => invoke('schema_compare.run')}>{gettext('Run comparison')}</Button></Box>
      <ResourcePicker open={picker?.kind === 'resource'} items={resources}
        selected={[]} onClose={() => setPicker(null)} onConfirm={choose} />
      <AssetPicker open={picker?.kind === 'asset'} items={assets}
        selected={[]} onClose={() => setPicker(null)} onConfirm={choose} />
    </Box>
  </ScratchScrollArea>;
}

CompareSetup.propTypes = {
  session: PropTypes.object.isRequired, invoke: PropTypes.func.isRequired,
  resources: PropTypes.array, assets: PropTypes.array,
  requestedPickerSide: PropTypes.string, onClearRequestedPicker: PropTypes.func,
};

function DiffTree({session, selectDiff, openSurface}) {
  const [filter, setFilter] = useState('');
  const [expanded, setExpanded] = useState(() => new Set());
  const groups = useMemo(() => {
    const result = new Map();
    for(const diff of session.result?.differences ?? []) {
      if(filter && !`${diff.qualifiedName} ${diff.classification}`
        .toLowerCase().includes(filter.toLowerCase())) continue;
      const values = result.get(diff.classification) ?? [];
      values.push(diff); result.set(diff.classification, values);
    }
    return [...result.entries()].sort(([left], [right]) => left.localeCompare(right));
  }, [session.result, filter]);
  if(!session.result) return <EmptyState
    message="Run a comparison to browse hierarchical differences." />;
  return <Box sx={{height: '100%', display: 'flex', flexDirection: 'column'}}>
    <Box sx={{p: 1}}><SearchField label="Filter differences" value={filter}
      onChange={setFilter} resultCount={groups.reduce((n, [, values]) => n + values.length, 0)} />
    </Box>
    <ScratchScrollArea orientation="both" style={{flex: 1, minHeight: 0}}>
      <Box role="tree" aria-label="Schema differences" sx={{p: 0.5}}>
        {groups.map(([classification, values], gIdx) => {
          const open = expanded.has(classification);
          return <React.Fragment key={classification}>
            <TreeRow label={`${classification.replaceAll('_', ' ')} (${values.length})`}
              level={1} expandable expanded={open} isLast={gIdx === groups.length - 1}
              onToggle={() => setExpanded((prior) => {
                const next = new Set(prior); open ? next.delete(classification) :
                  next.add(classification); return next;
              })} />
            {open && values.map((diff, dIdx) => <TreeRow key={diff.id}
              label={diff.qualifiedName} level={2} isLast={dIdx === values.length - 1}
              selected={session.selectedDiffId === diff.id}
              trailing={<Badge label={diff.kind} />}
              onSelect={() => selectDiff(diff.id)}
              onOpen={() => { selectDiff(diff.id); openSurface('object_diff'); }} />)}
          </React.Fragment>;
        })}
      </Box>
    </ScratchScrollArea>
  </Box>;
}

DiffTree.propTypes = {
  session: PropTypes.object.isRequired,
  selectDiff: PropTypes.func.isRequired,
  openSurface: PropTypes.func.isRequired,
};

function formatCompareAttributeValue(val) {
  if (val === undefined) return '—';
  if (val === null) return 'NULL';
  if (typeof val === 'boolean') return val ? 'true' : 'false';
  if (typeof val === 'object') return JSON.stringify(val);
  return String(val);
}

function buildAttributeDiffRows(left, right) {
  const rows = [];
  const pushRow = (attribute, hasLeft, leftVal, hasRight, rightVal) => {
    let status = 'Identical';
    let badgeStatus = 'success';
    if (!hasLeft && hasRight) {
      status = 'Target only';
      badgeStatus = 'info';
    } else if (hasLeft && !hasRight) {
      status = 'Source only';
      badgeStatus = 'warning';
    } else if (JSON.stringify(leftVal) !== JSON.stringify(rightVal)) {
      status = 'Modified';
      badgeStatus = 'warning';
    }
    rows.push({
      attribute,
      sourceValue: hasLeft ? formatCompareAttributeValue(leftVal) : '—',
      targetValue: hasRight ? formatCompareAttributeValue(rightVal) : '—',
      status,
      badgeStatus,
    });
  };

  pushRow(
    gettext('Qualified name'),
    Boolean(left),
    left?.qualifiedName,
    Boolean(right),
    right?.qualifiedName
  );
  pushRow(gettext('Kind'), Boolean(left), left?.kind, Boolean(right), right?.kind);
  if (left?.comment || right?.comment) {
    pushRow(gettext('Comment'), Boolean(left), left?.comment ?? '', Boolean(right), right?.comment ?? '');
  }

  const normKeys = new Set([
    ...Object.keys(left?.normalized || {}),
    ...Object.keys(right?.normalized || {}),
  ]);
  for (const key of normKeys) {
    const hasL = Boolean(left?.normalized && Object.hasOwn(left.normalized, key));
    const hasR = Boolean(right?.normalized && Object.hasOwn(right.normalized, key));
    pushRow(key, hasL, left?.normalized?.[key], hasR, right?.normalized?.[key]);
  }

  const nativeKeys = new Set([
    ...Object.keys(left?.native || {}),
    ...Object.keys(right?.native || {}),
  ]);
  for (const key of nativeKeys) {
    const hasL = Boolean(left?.native && Object.hasOwn(left.native, key));
    const hasR = Boolean(right?.native && Object.hasOwn(right.native, key));
    const label = normKeys.has(key) ? `${key} (native)` : key;
    pushRow(label, hasL, left?.native?.[key], hasR, right?.native?.[key]);
  }

  return rows;
}

function buildSqlDiffPreview(diff, left, right, plan) {
  const plannedOps = (plan?.operations || []).filter(
    (op) => op.diffId === diff.id || op.qualifiedName === diff.qualifiedName
  );
  const leftSql =
    left?.native?.ddl || left?.normalized?.ddl || left?.native?.definition || left?.normalized?.definition || '';
  const rightSql =
    right?.native?.ddl || right?.normalized?.ddl || right?.native?.definition || right?.normalized?.definition || '';

  const lines = [];
  if (leftSql || rightSql) {
    lines.push(`-- Source (${left?.qualifiedName || gettext('not present')})`);
    lines.push(leftSql || `-- (${gettext('no DDL source')})`);
    lines.push('');
    lines.push(`-- Target (${right?.qualifiedName || gettext('not present')})`);
    lines.push(rightSql || `-- (${gettext('no DDL source')})`);
  }
  if (plannedOps.length > 0) {
    if (lines.length > 0) lines.push('');
    lines.push(`-- ${gettext('Planned migration statements')}`);
    for (const op of plannedOps) {
      lines.push(op.nativeStatement);
    }
  }
  if (lines.length === 0) {
    lines.push(
      `-- ${diff.kind.toUpperCase()} ${diff.qualifiedName} (${diff.classification.replaceAll('_', ' ')})`
    );
    lines.push(
      `-- Source: ${left ? left.qualifiedName : gettext('absent')} | Target: ${right ? right.qualifiedName : gettext('absent')}`
    );
  }
  return lines.join('\n');
}

function ObjectDiff({session}) {
  const diff = session.result?.differences.find((item) => item.id === session.selectedDiffId);
  if (!diff) return <EmptyState message={gettext('Select an item in Diff Tree to inspect it.')} />;
  const left = session.leftSnapshot?.objects?.find((item) => item.id === diff.leftId);
  const right = session.rightSnapshot?.objects?.find((item) => item.id === diff.rightId);
  const attributeRows = buildAttributeDiffRows(left, right);
  const sqlPreview = buildSqlDiffPreview(diff, left, right, session.plan);

  return (
    <ScratchScrollArea orientation="both" style={{height: '100%'}}>
      <Box sx={{p: 2, display: 'flex', flexDirection: 'column', gap: 2}}>
        <Box sx={{display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center'}}>
          <Box component="h2" sx={{m: 0}}>
            {diff.qualifiedName}
          </Box>
          <Badge label={diff.kind} />
          <Badge status="info" label={diff.classification.replaceAll('_', ' ')} />
          {!left && <Badge status="warning" label={gettext('Missing in source')} />}
          {!right && <Badge status="warning" label={gettext('Missing in target')} />}
        </Box>

        <Box sx={{overflowX: 'auto', border: '1px solid', borderColor: 'divider', borderRadius: 1}}>
          <Box
            component="table"
            aria-label={gettext('Object attribute comparison')}
            sx={{
              width: '100%',
              borderCollapse: 'collapse',
              fontSize: '0.8125rem',
              '& th, & td': {
                p: 1,
                textAlign: 'left',
                borderBottom: '1px solid',
                borderColor: 'divider',
                verticalAlign: 'top',
              },
              '& th': {
                fontWeight: 600,
                bgcolor: 'background.default',
              },
            }}
          >
            <thead>
              <tr>
                <th>{gettext('Attribute')}</th>
                <th>{gettext('Source Value')}</th>
                <th>{gettext('Target Value')}</th>
                <th>{gettext('Status')}</th>
              </tr>
            </thead>
            <tbody>
              {attributeRows.map((row) => (
                <tr key={row.attribute}>
                  <td style={{fontWeight: 600}}>{row.attribute}</td>
                  <td style={{fontFamily: 'monospace', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>
                    {row.sourceValue}
                  </td>
                  <td style={{fontFamily: 'monospace', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>
                    {row.targetValue}
                  </td>
                  <td>
                    <Badge status={row.badgeStatus} label={gettext(row.status)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </Box>
        </Box>

        <Box component="section" aria-label={gettext('SQL diff preview')}>
          <Box component="h3" sx={{mt: 0, mb: 1, fontSize: '0.9rem'}}>
            {gettext('SQL Diff Preview')}
          </Box>
          <Box
            component="pre"
            tabIndex={0}
            sx={{
              m: 0,
              p: 1.5,
              border: '1px solid',
              borderColor: 'divider',
              borderRadius: 1,
              bgcolor: 'background.default',
              fontFamily: 'monospace',
              fontSize: '0.8125rem',
              whiteSpace: 'pre-wrap',
              overflow: 'auto',
            }}
          >
            {sqlPreview}
          </Box>
        </Box>
      </Box>
    </ScratchScrollArea>
  );
}

ObjectDiff.propTypes = {session: PropTypes.object.isRequired};

function MappingReview({session, invoke}) {
  if (!session.result) return <EmptyState message={gettext('Run a comparison to review mappings.')} />;
  const acceptedSet = new Set(
    (session.content?.acceptedMappings || [])
      .filter((m) => m.accepted)
      .map((m) => `${m.leftId}::${m.rightId}`)
  );
  const rows = session.result.renameCandidates.map((candidate) => ({
    ...candidate,
    evidenceText: (candidate.evidence || []).join(', '),
    isAccepted: acceptedSet.has(`${candidate.leftId}::${candidate.rightId}`),
  }));
  const busy = session.state === 'background_task_active';

  return (
    <ScratchScrollArea orientation="both" style={{height: '100%'}}>
      <Box sx={{p: 2, display: 'flex', flexDirection: 'column', gap: 1.5}}>
        <Box component="h2" sx={{m: 0}}>
          {gettext('Rename and equivalence candidates')}
        </Box>
        <Banner status="info">
          {gettext(
            'Candidates are never accepted automatically. Review native semantics before accepting a mapping.'
          )}
        </Banner>
        {rows.length === 0 ? (
          <EmptyState message={gettext('No rename or equivalence candidates were detected.')} />
        ) : (
          <Box sx={{overflowX: 'auto', border: '1px solid', borderColor: 'divider', borderRadius: 1}}>
            <Box
              component="table"
              aria-label={gettext('Mapping candidates')}
              sx={{
                width: '100%',
                borderCollapse: 'collapse',
                fontSize: '0.8125rem',
                '& th, & td': {
                  p: 1,
                  textAlign: 'left',
                  borderBottom: '1px solid',
                  borderColor: 'divider',
                  verticalAlign: 'middle',
                },
                '& th': {
                  fontWeight: 600,
                  bgcolor: 'background.default',
                },
              }}
            >
              <thead>
                <tr>
                  <th>{gettext('Left object')}</th>
                  <th>{gettext('Right object')}</th>
                  <th>{gettext('Kind')}</th>
                  <th>{gettext('Evidence')}</th>
                  <th>{gettext('Status')}</th>
                  <th>{gettext('Actions')}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td style={{fontFamily: 'monospace'}}>{row.leftId}</td>
                    <td style={{fontFamily: 'monospace'}}>{row.rightId}</td>
                    <td>
                      <Badge label={row.kind} />
                    </td>
                    <td>{row.evidenceText}</td>
                    <td>
                      <Badge
                        status={row.isAccepted ? 'success' : 'info'}
                        label={row.isAccepted ? gettext('Accepted') : gettext('Pending review')}
                      />
                    </td>
                    <td>
                      <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap'}}>
                        <Button
                          size="small"
                          intent="primary"
                          disabled={busy}
                          onClick={() =>
                            invoke('schema_compare.rename.accept', {
                              candidateId: row.id,
                              category: 'representational_difference',
                            })
                          }
                        >
                          {gettext('Accept Rename')}
                        </Button>
                        <Button
                          size="small"
                          disabled={busy}
                          onClick={() =>
                            invoke('schema_compare.mapping.set', {
                              mapping: {
                                mappingId: `mapping:${row.leftId}:${row.rightId}`,
                                leftId: row.leftId,
                                rightId: row.rightId,
                                category: 'representational_difference',
                                version: 1,
                                evidence: row.evidence ?? [],
                                accepted: false,
                              },
                            })
                          }
                        >
                          {gettext('Reject / Unmap')}
                        </Button>
                      </Box>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Box>
          </Box>
        )}
      </Box>
    </ScratchScrollArea>
  );
}

MappingReview.propTypes = {
  session: PropTypes.object.isRequired, invoke: PropTypes.func.isRequired,
};

function ChangePlan({session, invoke}) {
  const options = [session.content.leftRef, session.content.rightRef]
    .filter((item) => item?.schema === 'cdeadmin.resource-ref.v1')
    .map((item, index) => ({value: item.canonical, label: `${index ? 'Right' : 'Left'}: `+
      item.canonical}));
  const [target, setTarget] = useState('');
  const targetRef = [session.content.leftRef, session.content.rightRef]
    .find((item) => item?.canonical === target);
  return <Box sx={{height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column'}}>
    <Toolbar label={gettext('Change plan commands')}>
      <Select size="small" label={gettext('Explicit live target')} value={target} options={options}
        onChange={setTarget} sx={{minWidth: 360}} />
      <Button disabled={!session.result || !targetRef}
        onClick={() => invoke('schema_compare.plan.generate', {targetRef})}>
        {gettext('Generate plan')}
      </Button>
      <Button disabled={!session.plan}
        onClick={() => invoke('schema_compare.plan.validate')}>{gettext('Validate exact plan')}</Button>
    </Toolbar>
    {!session.plan ? <EmptyState
      message="Select an explicit live target and generate a provider-native plan." /> :
      <Box sx={{flex: 1, minHeight: 0}}>
        <ScratchDiffTable
          caption="Dependency ordered change plan"
          showIncludeToggle={false}
          searchable
          filterable
          exportable
          items={session.plan.operations.map((op) => ({
            id: op.id,
            name: op.qualifiedName,
            kind: op.kind,
            delta: op.action,
            risk: op.risk,
            destructive:
              op.risk === 'high' ||
              op.risk === 'destructive' ||
              (op.reversible === false && String(op.action).toLowerCase() === 'drop'),
            summary: op.nativeStatement,
          }))}
        />
      </Box>}
  </Box>;
}

ChangePlan.propTypes = {session: PropTypes.object.isRequired, invoke: PropTypes.func.isRequired};

function ApplyExportReview({session, invoke, onExport}) {
  const [confirmation, setConfirmation] = useState('');
  if(!session.plan) return <EmptyState message="Generate a change plan before review." />;
  return <Box sx={{p: 2, height: '100%', overflow: 'auto'}}>
    <Box component="h2" sx={{mt: 0}}>Apply and Export Review</Box>
    <Banner status={session.validation?.applyReady ? 'success' : 'warning'}>
      {session.validation?.applyReady ? 'The exact plan passed target-provider validation.' :
        'Apply is disabled until the exact plan passes target-provider validation.'}
    </Banner>
    <Box component="dl" sx={{display: 'grid', gridTemplateColumns: '180px 1fr', gap: 1}}>
      <dt>Target</dt><dd>{session.plan.targetRef.canonical}</dd>
      <dt>Operations</dt><dd>{session.plan.operations.length}</dd>
      <dt>Destructive</dt><dd>{session.plan.destructive ? 'Yes' : 'No'}</dd>
      <dt>Partial selection</dt><dd>{session.plan.partialSelection ? 'Yes' : 'No'}</dd>
    </Box>
    {session.plan.destructive && <TextArea rows={2} fullWidth
      label="Type the exact plan ID to authorize destructive apply"
      value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />}
    <Box sx={{display: 'flex', gap: 1, my: 2}}>
      <Button onClick={() => invoke('schema_compare.plan.export').then(onExport)}>
        {gettext('Export versioned plan')}
      </Button>
      <Button intent={session.plan.destructive ? 'destructive' : 'primary'}
        disabled={!session.validation?.applyReady || (session.plan.destructive &&
          confirmation !== session.plan.id)}
        onClick={() => invoke('schema_compare.plan.apply', {confirmation})}>
        {gettext('Apply validated plan')}
      </Button>
    </Box>
    <Box component="h3">Generated provider-native operations</Box>
    <Box component="pre" tabIndex={0} sx={{whiteSpace: 'pre-wrap'}}>
      {session.plan.operations.map((item) => item.nativeStatement).join('\n\n')}
    </Box>
  </Box>;
}

ApplyExportReview.propTypes = {
  session: PropTypes.object.isRequired, invoke: PropTypes.func.isRequired,
  onExport: PropTypes.func,
};

const VIEWS = Object.freeze({
  compare_setup: CompareSetup, diff_tree: DiffTree, object_diff: ObjectDiff,
  mapping_review: MappingReview, change_plan: ChangePlan,
  apply_export_review: ApplyExportReview,
});

export function SchemaCompareWorkspace({service, sessionId, surface='compare_setup',
  executeCommand, resources=[], assets=[], onExport=() => {}, onStateChange}) {
  useLocaleRevision();
  const session = useSession(service, sessionId);
  const [active, setActive] = useState(surface);
  const [requestedPickerSide, setRequestedPickerSide] = useState(null);
  useEffect(() => onStateChange?.(session), [session, onStateChange]);
  const invoke = async (commandId, args={}) => {
    try {
      return await executeCommand(commandId, args, {sessionId, service,
        openModuleSurface: setActive});
    } catch(error) {
      service.reportError(sessionId, error,
        String(error.message).split(':')[0].replaceAll(' ', '_'));
      throw error;
    }
  };
  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const onLeft = () => { setActive('compare_setup'); setRequestedPickerSide('Left'); };
    const onRight = () => { setActive('compare_setup'); setRequestedPickerSide('Right'); };
    const onRun = () => {
      if (session.content.leftRef && session.content.rightRef) {
        invoke('schema_compare.run').catch(() => {});
      } else {
        setActive('compare_setup');
      }
    };
    const onReview = () => setActive(session.plan ? 'apply_export_review' : 'change_plan');
    window.addEventListener('scratchrobin:schema-compare-pick-left', onLeft);
    window.addEventListener('scratchrobin:schema-compare-pick-right', onRight);
    window.addEventListener('scratchrobin:schema-compare-run', onRun);
    window.addEventListener('scratchrobin:schema-compare-review', onReview);
    return () => {
      window.removeEventListener('scratchrobin:schema-compare-pick-left', onLeft);
      window.removeEventListener('scratchrobin:schema-compare-pick-right', onRight);
      window.removeEventListener('scratchrobin:schema-compare-run', onRun);
      window.removeEventListener('scratchrobin:schema-compare-review', onReview);
    };
  }, [session.content.leftRef, session.content.rightRef, session.plan]);
  const View = VIEWS[active] ?? CompareSetup;
  return <Box data-module="cdeadmin.schema_compare"
    sx={{height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column'}}>
    <Box role="tablist" aria-label="Schema Comparison surfaces"
      sx={{display: 'flex', overflowX: 'auto', borderBottom: '1px solid',
        borderColor: 'divider'}}>
      {SCHEMA_COMPARE_SURFACES.map((item) => <Tab key={item.id} label={gettext(item.title)}
        active={active === item.id} attention={item.id === 'mapping_review' &&
          Boolean(session.result?.renameCandidates.length)}
        onActivate={() => setActive(item.id)} />)}
    </Box>
    <Box sx={{px: 1, py: 0.5, display: 'flex', gap: 1, alignItems: 'center'}}>
      <FormReference formKey="schema-compare-workspace" />
      <Badge status={statusColor(session.state)} label={session.state.replaceAll('_', ' ')} />
      {session.result && <Box>{session.result.differences.length} differences</Box>}
      {session.dirty && <Badge status="warning" label="Unsaved" />}
    </Box>
    <Box sx={{flex: 1, minHeight: 0, overflow: 'hidden'}}>
      <StateBoundary session={session}>
        <View session={session} invoke={invoke} resources={resources} assets={assets}
          requestedPickerSide={requestedPickerSide}
          onClearRequestedPicker={() => setRequestedPickerSide(null)}
          onExport={onExport} selectDiff={(diffId) => service.selectDiff(sessionId, diffId)}
          openSurface={setActive} />
      </StateBoundary>
    </Box>
  </Box>;
}

SchemaCompareWorkspace.propTypes = {
  service: PropTypes.object.isRequired,
  sessionId: PropTypes.string.isRequired,
  surface: PropTypes.oneOf(SCHEMA_COMPARE_SURFACES.map((item) => item.id)),
  executeCommand: PropTypes.func.isRequired,
  resources: PropTypes.array,
  assets: PropTypes.array,
  onExport: PropTypes.func,
  onStateChange: PropTypes.func,
};

export function schemaCompareInspector(session) {
  const diff = session?.result?.differences.find((item) =>
    item.id === session.selectedDiffId);
  if(!diff) return {Classification: 'No difference selected'};
  const operation = session.plan?.operations.find((item) => item.diffId === diff.id);
  return {
    Classification: diff.classification,
    Mapping: diff.matchReason || 'No accepted mapping',
    Dependencies: operation?.dependencies ?? [],
    Risk: operation?.risk ?? 'Not planned',
    'Proposed operation': operation?.action ?? 'Not planned',
  };
}

export function SchemaCompareNavigator({service, onOpen}) {
  const [sessions, setSessions] = useState(() => service.list());
  const [expanded, setExpanded] = useState(() => new Set());
  useEffect(() => service.subscribe(() => setSessions(service.list())), [service]);
  return <Box role="tree" aria-label="Schema Diff" sx={{height: '100%', overflow: 'auto'}}>
    {!sessions.length && <EmptyState message="No Schema Comparison sessions are open." />}
    {sessions.map((session) => {
      const open = expanded.has(session.id);
      const counts = session.result?.counts ?? {};
      return <React.Fragment key={session.id}>
        <TreeRow label={session.id} level={1} expandable expanded={open}
          trailing={<Badge label={session.state} status={statusColor(session.state)} />}
          onToggle={() => setExpanded((prior) => {
            const next = new Set(prior); open ? next.delete(session.id) : next.add(session.id);
            return next;
          })} onOpen={() => onOpen?.(session.id, 'compare_setup')} />
        {open && Object.entries(counts).filter(([, count]) => count > 0)
          .map(([classification, count]) => <TreeRow key={classification}
            label={`${classification.replaceAll('_', ' ')} (${count})`} level={2}
            onOpen={() => onOpen?.(session.id, 'diff_tree')} />)}
      </React.Fragment>;
    })}
  </Box>;
}

SchemaCompareNavigator.propTypes = {
  service: PropTypes.object.isRequired,
  onOpen: PropTypes.func,
};
