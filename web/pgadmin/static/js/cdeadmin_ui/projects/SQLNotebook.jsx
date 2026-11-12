/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Box, Stack} from '../primitives/Layout';
import {Button} from '../primitives/Button';
import {Checkbox, Select} from '../primitives/Choice';
import {TextArea, TextField} from '../primitives/Field';
import {Banner} from '../feedback/Indicators';
import {ScratchScrollArea} from '../base/ScratchScrollArea';
import {
  useQueryExecutionController,
  QueryExecutionToolbarCluster,
  QueryStepStatusFooter,
} from '../query';
import {ProjectAssetClient} from './ProjectAssetClient';
import {useModalCloseGuard} from '../../helpers/ModalCloseGuard';
import {
  NOTEBOOK_TYPE,
  NOTEBOOK_LIMIT,
  newNotebook,
  notebookRequest,
  portableNotebook,
  rebindNotebook,
  retainedSnapshot,
  sameScope,
  sensitiveColumn,
  validateNotebook,
} from './SQLNotebookModel';

const POLICY_OPTIONS = [
  {value: 'omit', label: 'Omit'},
  {value: 'redact', label: 'Redact'},
  {value: 'retain', label: 'Retain value'},
];

export default function SQLNotebook({
  client: suppliedClient,
  scope = null,
  editorSource = '',
  rendered = null,
  executedSource = null,
  onLoad,
  onRun,
  disabled = false,
  initialProjectId = '',
  initialAssetId = '',
  onDirty,
}) {
  const client = useMemo(() => suppliedClient || new ProjectAssetClient(), [suppliedClient]);
  const [projects, setProjects] = useState([]);
  const [assets, setAssets] = useState([]);
  const [projectId, setProjectId] = useState(initialProjectId);
  const [assetId, setAssetId] = useState(initialAssetId);
  const [name, setName] = useState('SQL investigation');
  const [document, setDocument] = useState(newNotebook());
  const [version, setVersion] = useState(0);
  const [revision, setRevision] = useState('');
  const [revisions, setRevisions] = useState([]);
  const [access, setAccess] = useState('owner');
  const [selected, setSelected] = useState('');
  const [policies, setPolicies] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [reviewed, setReviewed] = useState(false);
  const [saved, setSaved] = useState(
    JSON.stringify({name: 'SQL investigation', document: newNotebook()})
  );
  const [member, setMember] = useState('');
  const fileInputRef = useRef(null);
  const mounted = useRef(true);
  const dirty = saved !== '' && saved !== JSON.stringify({name, document});
  const readonly = access === 'viewer';
  const locked = disabled || busy;
  const cell = document.cells.find((item) => item.id === selected);
  const bound = scope && sameScope(scope, document.scope);
  const canRetain =
    bound && cell?.kind === 'sql' && cell.source === executedSource && rendered;

  const queryController = useQueryExecutionController({
    engine: scope?.engine || document.scope?.engine || 'postgresql',
  });

  useEffect(() => {
    onDirty?.(dirty);
    return () => onDirty?.(false);
  }, [dirty, onDirty]);

  useModalCloseGuard(() => !busy && !dirty);

  useEffect(() => {
    const guard = (event) => {
      if (dirty) {
        event.preventDefault();
        event.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', guard);
    return () => window.removeEventListener('beforeunload', guard);
  }, [dirty]);

  const perform = async (callback) => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await callback();
    } catch (failure) {
      if (mounted.current) setError(failure.message || 'Notebook operation failed.');
    } finally {
      if (mounted.current) setBusy(false);
    }
  };

  const refresh = async () => setProjects(await client.listProjects());

  const load = async (pid, aid, requested = null) => {
    const latest = await client.asset(pid, aid);
    const value = requested ? await client.asset(pid, aid, requested) : latest;
    if (!mounted.current) return;
    if (value.asset_type !== NOTEBOOK_TYPE) throw new Error('Select a SQL notebook asset.');
    const content = validateNotebook(value.content);
    setDocument(content);
    setName(value.name);
    setVersion(latest.version);
    setAccess(value.access);
    setSelected(content.cells[0]?.id || '');
    setReviewed(false);
    setSaved(requested ? '{}' : JSON.stringify({name: value.name, document: content}));
    setRevisions(await client.revisions(pid, aid));
    setNotice(
      requested
        ? `Loaded revision ${requested} as a draft; next save checks current revision ${latest.version}.`
        : `Loaded revision ${latest.version}. No SQL executed.`
    );
  };

  useEffect(() => {
    mounted.current = true;
    perform(async () => {
      await refresh();
      if (initialProjectId && initialAssetId) await load(initialProjectId, initialAssetId);
    });
    return () => {
      mounted.current = false;
    };
  }, [client]);

  useEffect(() => {
    let active = true;
    if (!projectId) {
      setAssets([]);
      return undefined;
    }
    client
      .project(projectId)
      .then((value) => {
        if (active) {
          setAssets(value.assets.filter((item) => item.asset_type === NOTEBOOK_TYPE));
          setAccess(value.access);
        }
      })
      .catch((failure) => {
        if (active) setError(failure.message);
      });
    return () => {
      active = false;
    };
  }, [client, projectId, version]);

  useEffect(() => {
    setPolicies(
      Object.fromEntries(
        (rendered?.view_model?.columns || []).map((column, index) => [
          index,
          sensitiveColumn.test(column.name) ? 'redact' : 'omit',
        ])
      )
    );
  }, [rendered]);

  const change = (value) => {
    setDocument(value);
    setReviewed(false);
  };

  const editCell = (id, update) =>
    change({
      ...document,
      cells: document.cells.map((item) => (item.id === id ? {...item, ...update} : item)),
    });

  const reset = () => {
    const next = newNotebook(scope);
    setDocument(next);
    setName('SQL investigation');
    setAssetId('');
    setVersion(0);
    setRevision('');
    setRevisions([]);
    setSelected('');
    setReviewed(false);
    setSaved(JSON.stringify({name: 'SQL investigation', document: next}));
    setNotice('New notebook. No SQL executed.');
  };

  const add = (kind) => {
    const id = crypto.randomUUID();
    const next = {id, kind, source: '', ...(kind === 'sql' ? {snapshot: null} : {})};
    change({...document, cells: [...document.cells, next]});
    setSelected(id);
  };

  const save = () =>
    perform(async () => {
      const id = assetId || crypto.randomUUID();
      const value = await client.saveAsset(
        projectId,
        id,
        notebookRequest(document, name, version, id)
      );
      setAssetId(id);
      setVersion(value.version);
      setSaved(JSON.stringify({name, document}));
      setRevisions(await client.revisions(projectId, id));
      setNotice(`Saved notebook revision ${value.version}. No SQL executed.`);
    });

  const download = () =>
    perform(async () => {
      if (!reviewed || dirty || !assetId || !version) {
        throw new Error('Save and review the notebook before sharing.');
      }
      const value = await client.asset(projectId, assetId, version);
      const content = portableNotebook(value.content);
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(content, null, 2)], {type: 'application/json'})
      );
      const anchor = window.document.createElement('a');
      anchor.href = url;
      anchor.download = 'investigation.sql-notebook.json';
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice('Shared file contains no local connection binding. No SQL executed.');
    });

  const move = (direction) => {
    const cells = [...document.cells];
    const index = cells.findIndex((item) => item.id === selected);
    const next = index + direction;
    if (next < 0 || next >= cells.length) return;
    [cells[index], cells[next]] = [cells[next], cells[index]];
    change({...document, cells});
  };

  const projectOptions = [
    {value: '', label: 'Select project'},
    ...projects.map((item) => ({value: item.project_id, label: item.name})),
  ];
  const savedNotebookOptions = [
    {value: '', label: 'New notebook'},
    ...assets.map((item) => ({
      value: item.asset_id,
      label: `${item.name} (v${item.version})`,
    })),
  ];
  const revisionOptions = [
    {value: '', label: 'Latest'},
    ...revisions.map((item) => ({
      value: String(item.version),
      label: `v${item.version}`,
    })),
  ];
  const cellOptions = [
    {value: '', label: 'Select cell'},
    ...document.cells.map((item, index) => ({
      value: item.id,
      label: `${index + 1}. ${item.kind}: ${item.source.slice(0, 40)}`,
    })),
  ];

  const runSelectedSqlCell = () => {
    if (!cell || cell.kind !== 'sql' || !onRun) return;
    onRun(cell.source, {
      maxRows: queryController.maxRows,
      rowsPerStep: queryController.rowsPerStep,
    });
  };

  return (
    <ScratchScrollArea orientation="both" style={{height: '100%', minHeight: 150}}>
      <Box component="section" aria-label="SQL notebook" sx={{p: 1.5}}>
        <Stack gap="compact">
          <Banner status="info">
            Notes, SQL and explicitly retained result pages. Opening, importing and sharing never execute SQL.
            {scope
              ? ' Run cell uses this SQL editor session with empty parameter bindings and query attributes. Native transaction controls and cancellation remain in the editor.'
              : 'To execute, open SQL notebook in a native MySQL SQL editor and load this project asset.'}
          </Banner>
          {error && <Banner status="error">{error}</Banner>}
          {notice && <Banner status="info">{notice}</Banner>}

          <Box sx={{display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'flex-end'}}>
            <Select
              size="small"
              label="Notebook project"
              value={projects.some((item) => item.project_id === projectId) ? projectId : ''}
              options={projectOptions}
              disabled={locked || (dirty && Boolean(assetId))}
              sx={{minWidth: 180}}
              onChange={(nextVal) => {
                setProjectId(nextVal);
                setAssetId('');
                setVersion(0);
                setRevision('');
                setRevisions([]);
              }}
            />
            <Button disabled={locked || dirty} onClick={() => perform(refresh)}>
              Refresh projects
            </Button>
            <Button disabled={locked || readonly} onClick={reset}>
              Discard draft / new notebook
            </Button>
            <Select
              size="small"
              label="Saved notebook"
              value={assets.some((item) => item.asset_id === assetId) ? assetId : ''}
              options={savedNotebookOptions}
              sx={{minWidth: 180}}
              disabled={locked || dirty || !projectId}
              onChange={(id) => {
                setAssetId(id);
                setRevision('');
                if (id) perform(() => load(projectId, id));
              }}
            />
            <TextField
              size="small"
              label="Notebook name"
              value={name}
              disabled={locked || readonly}
              onChange={(event) => {
                setName(event.target.value);
                setReviewed(false);
              }}
            />
            <Button disabled={locked || readonly || !projectId} onClick={save}>
              Save notebook revision
            </Button>
            <Select
              size="small"
              label="Notebook revision"
              value={revision}
              options={revisionOptions}
              disabled={locked || dirty || !version}
              sx={{minWidth: 160}}
              onChange={(nextVal) => setRevision(nextVal)}
            />
            <Button
              disabled={locked || dirty || !assetId}
              onClick={() =>
                perform(() => load(projectId, assetId, revision ? Number(revision) : null))
              }
            >
              Reload notebook
            </Button>
            <Button
              disabled={locked || dirty || readonly}
              onClick={() => fileInputRef.current?.click()}
            >
              Import notebook
            </Button>
            <input
              ref={fileInputRef}
              hidden
              type="file"
              aria-label="Import SQL notebook file"
              accept=".json"
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = '';
                if (file) {
                  perform(async () => {
                    if (file.size > NOTEBOOK_LIMIT) throw new Error('Notebook exceeds 2 MiB.');
                    const next = portableNotebook(JSON.parse(await file.text()));
                    setDocument(next);
                    setAssetId('');
                    setVersion(0);
                    setRevisions([]);
                    setRevision('');
                    setReviewed(false);
                    setSelected(next.cells[0]?.id || '');
                    setSaved('{}');
                    setNotice('Imported an unbound draft. Bind explicitly before running.');
                  });
                }
              }}
            />
          </Box>

          <Box role="status" sx={{fontSize: '0.78rem', color: 'text.secondary'}}>
            Saved revision: {version} · {dirty ? 'Unsaved draft' : 'Saved / empty'} · Access: {access}
            <br />
            Connection scope:{' '}
            {document.scope
              ? `${document.scope.engine} / ${document.scope.endpoint_id} / ${document.scope.database_target_id}`
              : 'Unbound portable notebook'}
          </Box>

          {scope && (
            <Box>
              <Button
                disabled={locked || readonly || bound}
                onClick={() => {
                  change(rebindNotebook(document, scope));
                  setNotice('Bound to this editor; previous result snapshots cleared.');
                }}
              >
                Bind to this SQL editor (clear snapshots)
              </Button>
            </Box>
          )}

          <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'flex-end'}}>
            <Button disabled={locked || readonly || document.cells.length >= 200} onClick={() => add('note')}>
              Add note
            </Button>
            <Button disabled={locked || readonly || document.cells.length >= 200} onClick={() => add('sql')}>
              Add SQL cell
            </Button>
            <Select
              size="small"
              label="Notebook cell"
              value={selected}
              options={cellOptions}
              sx={{minWidth: 200}}
              disabled={locked}
              onChange={(nextVal) => setSelected(nextVal)}
            />
            <Button disabled={locked || readonly || !cell} onClick={() => move(-1)}>
              Move cell up
            </Button>
            <Button disabled={locked || readonly || !cell} onClick={() => move(1)}>
              Move cell down
            </Button>
            <Button
              disabled={locked || readonly || !cell}
              onClick={() => {
                change({
                  ...document,
                  cells: document.cells.filter((item) => item.id !== selected),
                });
                setSelected('');
              }}
            >
              Remove cell
            </Button>
          </Box>

          {cell && (
            <>
              <TextArea
                fullWidth
                rows={3}
                label={cell.kind === 'sql' ? 'Notebook SQL cell' : 'Notebook note'}
                value={cell.source}
                disabled={locked || readonly}
                onChange={(event) =>
                  editCell(cell.id, {
                    source: event.target.value,
                    ...(cell.kind === 'sql' ? {snapshot: null} : {}),
                  })
                }
              />
              {cell.kind === 'sql' && (
                <Stack gap="compact">
                  <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center'}}>
                    <Button disabled={locked || !bound || !onLoad} onClick={() => onLoad(cell.source)}>
                      Load cell in SQL editor
                    </Button>
                    <Button
                      disabled={locked || readonly || !onLoad}
                      onClick={() => editCell(cell.id, {source: editorSource, snapshot: null})}
                    >
                      Replace cell from SQL editor
                    </Button>
                    <Button
                      intent="primary"
                      disabled={locked || !bound || !onRun || !cell.source.trim()}
                      onClick={runSelectedSqlCell}
                    >
                      Run selected SQL cell
                    </Button>
                    <QueryExecutionToolbarCluster
                      controller={queryController}
                      qaKeyPrefix="sql-notebook-query"
                    />
                  </Box>
                  <QueryStepStatusFooter
                    controller={queryController}
                    qaKey="sql-notebook-step-footer"
                  />
                  {canRetain && (
                    <Box className="sr-bui-table-card" sx={{p: 1.25}}>
                      <Box sx={{fontSize: '0.78rem', mb: 1}}>
                        Retain at most 100 rows from the displayed page. Columns default to omitted; sensitive names default to redacted.
                      </Box>
                      <Box sx={{display: 'flex', flexWrap: 'wrap', gap: 1, mb: 1}}>
                        {(rendered.view_model?.columns || []).map((column, index) => (
                          <Select
                            key={index}
                            size="small"
                            sx={{minWidth: 160}}
                            label={`Snapshot ${column.name}`}
                            value={policies[index] || 'omit'}
                            options={POLICY_OPTIONS}
                            disabled={locked || readonly}
                            onChange={(nextVal) =>
                              setPolicies({...policies, [index]: nextVal})
                            }
                          />
                        ))}
                      </Box>
                      <Button
                        disabled={locked || readonly}
                        onClick={() =>
                          perform(async () =>
                            editCell(cell.id, {
                              snapshot: retainedSnapshot(
                                rendered,
                                cell.source,
                                scope,
                                policies
                              ),
                            })
                          )
                        }
                      >
                        Retain reviewed page snapshot
                      </Button>
                    </Box>
                  )}
                  {cell.snapshot && (
                    <>
                      <Box
                        component="pre"
                        aria-label="Retained notebook snapshot"
                        className="sr-bui-table-card"
                        sx={{p: 1.25, maxHeight: 220, overflow: 'auto', fontSize: '0.75rem'}}
                      >
                        {JSON.stringify(cell.snapshot, null, 2)}
                      </Box>
                      <Box>
                        <Button
                          disabled={locked || readonly}
                          onClick={() => editCell(cell.id, {snapshot: null})}
                        >
                          Remove retained snapshot
                        </Button>
                      </Box>
                    </>
                  )}
                </Stack>
              )}
            </>
          )}

          <Checkbox
            checked={reviewed}
            disabled={locked || dirty || !version}
            onChange={(nextChecked) => setReviewed(nextChecked)}
            label="I reviewed notes, SQL literals and retained data for secrets before sharing this saved revision."
          />
          <Box>
            <Button
              disabled={locked || dirty || !reviewed || !version}
              onClick={download}
            >
              Export shareable notebook
            </Button>
          </Box>

          {access === 'owner' && (
            <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'flex-end'}}>
              <TextField
                size="small"
                label="Project viewer user ID"
                value={member}
                disabled={locked}
                onChange={(event) => setMember(event.target.value)}
              />
              <Button
                disabled={locked || !projectId || !/^\d+$/.test(member)}
                onClick={() =>
                  perform(async () => {
                    await client.setMember(projectId, {
                      principal_type: 'user',
                      principal_id: Number(member),
                      access_level: 'viewer',
                    });
                    setNotice(
                      'Viewer access granted to the entire project, including saved revisions. Database permissions are separate.'
                    );
                  })
                }
              >
                Grant project viewer access (all assets and revisions)
              </Button>
            </Box>
          )}
        </Stack>
      </Box>
    </ScratchScrollArea>
  );
}

SQLNotebook.propTypes = {
  client: PropTypes.object,
  scope: PropTypes.object,
  editorSource: PropTypes.string,
  rendered: PropTypes.object,
  executedSource: PropTypes.string,
  onLoad: PropTypes.func,
  onRun: PropTypes.func,
  disabled: PropTypes.bool,
  initialProjectId: PropTypes.string,
  initialAssetId: PropTypes.string,
  onDirty: PropTypes.func,
};
