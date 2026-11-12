/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Box, Stack} from '../../primitives/Layout';
import {Badge, Banner} from '../../feedback/Indicators';
import {Icon} from '../../icons';
import {ProjectAssetClient} from '../../projects/ProjectAssetClient';
import {Toolbar} from '../../layout/WorkbenchChrome';
import {Button} from '../../primitives/Button';
import {TextField} from '../../primitives/Field';
import {Select} from '../../primitives/Choice';
import {TreeRow} from '../../navigation/AdvancedNavigation';
import {Dialog} from '../../overlays/Dialog';
import {EmptyState} from '../../feedback/EmptyState';
import {ProgressOverlay} from '../../feedback/ProgressOverlay';
import CodeEditor from '../../editors/CodeEditor';
import FormReference from '../../navigation/FormReference';
import {DesignStoreClient} from './sharedDesignLibrary';

export const BI_DESIGN_CREATE_EVENT = 'cdeadmin:bi-design-create';
export const BI_DESIGN_OPEN_EVENT = 'cdeadmin:bi-design-open';
export const DESIGN_SHORTCUT_EVENT = 'cdeadmin:design-shortcut';
const NEW_PROJECT = '\u0000new-project';
const WRITABLE = new Set(['owner', 'manager', 'editor']);
let pendingCreate = false;

export function requestBIDesignCreate() {
  pendingCreate = true;
  window.dispatchEvent(new CustomEvent(BI_DESIGN_CREATE_EVENT));
}

function takePendingCreate() {
  const pending = pendingCreate;
  pendingCreate = false;
  return pending;
}

function takeWindowPendingShortcut() {
  if (typeof window === 'undefined') return null;
  const pending = window.__cdeadminPendingDesignShortcut || null;
  if (
    pending &&
    (pending.design_shortcut === 'bi_question_from_sql' ||
      pending.design_shortcut === 'bi_question_from_table')
  ) {
    window.__cdeadminPendingDesignShortcut = null;
    return pending;
  }
  return null;
}

export function openBIDesign(projectId, design) {
  window.dispatchEvent(
    new CustomEvent(BI_DESIGN_OPEN_EVENT, {
      detail: {
        projectId,
        designId: design.id,
        kind: design.kind,
        title: design.title,
      },
    })
  );
}

function slugKey(name, fallback = 'bi') {
  return (
    String(name || '')
      .toLowerCase()
      .normalize('NFKD')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 64) || fallback
  );
}

function bytesToBase64(bytes) {
  let binary = '';
  for (let i = 0; i < bytes.length; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

async function readUploadedFileBytes(file) {
  if (typeof file.arrayBuffer === 'function') {
    const buf = await file.arrayBuffer();
    return new Uint8Array(buf);
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(new Uint8Array(reader.result));
    reader.onerror = () => reject(new Error('Failed to read selected file.'));
    reader.readAsArrayBuffer(file);
  });
}

function parseTableShortcut(detail) {
  if (Array.isArray(detail?.relation) && detail.relation.length > 0) {
    return detail.relation.map(String);
  }
  if (detail?.table) {
    return detail.schema
      ? [String(detail.schema), String(detail.table)]
      : ['main', String(detail.table)];
  }
  const resId = String(detail?.resource_id || detail?.resourceId || '');
  if (resId.startsWith('table:')) {
    const parts = resId.slice(6).split(':').filter(Boolean);
    if (parts.length >= 2) return parts.slice(-2);
    if (parts.length === 1) return ['main', parts[0]];
  }
  return ['main', 'orders'];
}

export function BIDesignsNavigator({
  designClient: suppliedDesignClient,
  projectClient: suppliedProjectClient,
  onOpenDesign = openBIDesign,
}) {
  const designClient = useMemo(
    () => suppliedDesignClient ?? new DesignStoreClient(),
    [suppliedDesignClient]
  );
  const projectClient = useMemo(
    () => suppliedProjectClient ?? new ProjectAssetClient(),
    [suppliedProjectClient]
  );

  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(false);
  const [importSummary, setImportSummary] = useState(null);
  const [draft, setDraft] = useState({
    mode: 'new_question',
    title: '',
    project: '',
    projectId: 'analytics',
    projectName: 'Analytics BI',
    endpointId: 'default-endpoint',
    fileName: '',
    parsedBundle: null,
    archiveBase64: '',
    sqlText: '',
    prefillRelation: null,
  });
  const [createError, setCreateError] = useState('');
  const [saving, setSaving] = useState(false);
  const sqlTextRef = useRef('');
  sqlTextRef.current = draft.sqlText;

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const projects = await projectClient.listProjects();
      const loaded = await Promise.all(
        projects.map(async (project) => {
          try {
            const all = await designClient.listDesigns(project.project_id);
            const items = (all || []).filter(
              (d) => d.kind === 'question' || d.kind === 'dashboard'
            );
            return {project, items, error: ''};
          } catch (loadErr) {
            return {project, items: [], error: loadErr.message};
          }
        })
      );
      setGroups(loaded);
      return loaded;
    } catch (loadErr) {
      setError(loadErr.message);
      return [];
    } finally {
      setLoading(false);
    }
  }, [designClient, projectClient]);

  const writable = useMemo(
    () => groups.filter(({project}) => WRITABLE.has(project.access)),
    [groups]
  );
  const firstWritableProjectId = writable[0]?.project.project_id || '';

  const applyShortcut = useCallback(
    (detail, fallbackProject) => {
      if (!detail) return false;
      const shortcut = detail.design_shortcut;
      if (shortcut === 'bi_question_from_sql') {
        setCreateError('');
        setDraft((cur) => ({
          ...cur,
          mode: 'from_sql',
          title: String(detail.title || 'SQL Question'),
          sqlText: String(detail.sql || 'SELECT 1 AS value'),
          endpointId: String(detail.endpointId || cur.endpointId || 'default-endpoint'),
          prefillRelation: null,
          fileName: '',
          parsedBundle: null,
          archiveBase64: '',
          project:
            cur.project ||
            fallbackProject ||
            firstWritableProjectId ||
            NEW_PROJECT,
        }));
        setOpen(true);
        return true;
      }
      if (shortcut === 'bi_question_from_table') {
        const rel = parseTableShortcut(detail);
        const tblName = rel[rel.length - 1] || 'table';
        setCreateError('');
        setDraft((cur) => ({
          ...cur,
          mode: 'new_question',
          title: String(detail.title || `${tblName} Summary`),
          prefillRelation: rel,
          sqlText: '',
          endpointId: String(detail.endpointId || cur.endpointId || 'default-endpoint'),
          fileName: '',
          parsedBundle: null,
          archiveBase64: '',
          project:
            cur.project ||
            fallbackProject ||
            firstWritableProjectId ||
            NEW_PROJECT,
        }));
        setOpen(true);
        return true;
      }
      return false;
    },
    [firstWritableProjectId]
  );

  const applyShortcutRef = useRef(applyShortcut);
  applyShortcutRef.current = applyShortcut;

  const beginCreate = useCallback(() => {
    setCreateError('');
    setDraft((cur) => ({
      ...cur,
      mode: 'new_question',
      title: '',
      fileName: '',
      parsedBundle: null,
      archiveBase64: '',
      sqlText: '',
      prefillRelation: null,
      project: cur.project || firstWritableProjectId || NEW_PROJECT,
    }));
    setOpen(true);
  }, [firstWritableProjectId]);

  useEffect(() => {
    refresh().then((loaded) => {
      const first = loaded.find(({project}) => WRITABLE.has(project.access));
      const defaultProj = first?.project.project_id || NEW_PROJECT;
      const pendingShortcut = takeWindowPendingShortcut();
      if (pendingShortcut) {
        applyShortcutRef.current(pendingShortcut, defaultProj);
        return;
      }
      if (takePendingCreate()) {
        setDraft((cur) => ({
          ...cur,
          mode: 'new_question',
          title: '',
          project: defaultProj,
        }));
        setOpen(true);
      }
    });
  }, [refresh]);

  useEffect(() => {
    const listener = () => {
      takePendingCreate();
      beginCreate();
    };
    window.addEventListener(BI_DESIGN_CREATE_EVENT, listener);
    return () => window.removeEventListener(BI_DESIGN_CREATE_EVENT, listener);
  }, [beginCreate]);

  useEffect(() => {
    const onShortcut = (event) => {
      const detail = event?.detail;
      if (applyShortcut(detail)) {
        takeWindowPendingShortcut();
      }
    };
    window.addEventListener(DESIGN_SHORTCUT_EVENT, onShortcut);
    return () => window.removeEventListener(DESIGN_SHORTCUT_EVENT, onShortcut);
  }, [applyShortcut]);

  const handleBundleFileSelect = async (event) => {
    const file = event.target.files?.[0];
    setCreateError('');
    if (!file) {
      setDraft((cur) => ({
        ...cur,
        fileName: '',
        parsedBundle: null,
        archiveBase64: '',
      }));
      return;
    }
    try {
      const bytes = await readUploadedFileBytes(file);
      const lowerName = String(file.name || '').toLowerCase();
      if (lowerName.endsWith('.json')) {
        const text = new TextDecoder('utf-8').decode(bytes);
        const parsed = JSON.parse(text);
        setDraft((cur) => ({
          ...cur,
          fileName: file.name,
          parsedBundle: parsed,
          archiveBase64: '',
        }));
      } else {
        const encoded = bytesToBase64(bytes);
        setDraft((cur) => ({
          ...cur,
          fileName: file.name,
          parsedBundle: null,
          archiveBase64: encoded,
        }));
      }
    } catch (fileErr) {
      setCreateError(fileErr.message || 'Unable to parse selected bundle file.');
    }
  };

  const create = async () => {
    setSaving(true);
    setCreateError('');
    try {
      let projectId = draft.project;
      if (projectId === NEW_PROJECT) {
        projectId = draft.projectId.trim();
        if (!/^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,255}$/.test(projectId)) {
          throw new Error(
            'Project ID must be a stable identifier without spaces.'
          );
        }
        await projectClient.createProject(projectId, {
          name: draft.projectName.trim() || projectId,
        });
      }

      if (draft.mode === 'import_legacy_bi') {
        const imported = await designClient.importBiLegacy(projectId, {
          bundle: draft.parsedBundle || null,
          endpointId: draft.endpointId.trim() || 'default-endpoint',
        });
        setImportSummary(imported.loss_report || null);
        await refresh();
        setOpen(false);
        const firstTarget =
          imported.dashboards?.[0] || imported.questions?.[0] || null;
        if (firstTarget) {
          onOpenDesign(projectId, firstTarget);
        }
        return;
      }

      if (draft.mode === 'import_superset' || draft.mode === 'import_metabase') {
        if (!draft.parsedBundle && !draft.archiveBase64) {
          throw new Error(
            'Select a .zip or .json export bundle file to import.'
          );
        }
        const imported =
          draft.mode === 'import_superset'
            ? await designClient.importBiSuperset(projectId, {
              bundle: draft.parsedBundle,
              zipBase64: draft.archiveBase64 || null,
              endpointId: draft.endpointId.trim() || 'default-endpoint',
            })
            : await designClient.importBiMetabase(projectId, {
              bundle: draft.parsedBundle,
              bundleBase64: draft.archiveBase64 || null,
              endpointId: draft.endpointId.trim() || 'default-endpoint',
            });
        setImportSummary(imported.loss_report || null);
        await refresh();
        setOpen(false);
        const firstTarget =
          imported.dashboards?.[0] || imported.questions?.[0] || null;
        if (firstTarget) {
          onOpenDesign(projectId, firstTarget);
        }
        return;
      }

      const trimmedTitle = draft.title.trim();
      if (!trimmedTitle) {
        throw new Error('A BI question or dashboard needs a title.');
      }
      const key = `${slugKey(trimmedTitle)}-${Date.now().toString(36)}`;

      if (draft.mode === 'from_sql') {
        const sqlClean = String(draft.sqlText || '').trim();
        if (!sqlClean) {
          throw new Error('Provide a read-only SELECT statement to import.');
        }
        const endpoint = draft.endpointId.trim() || 'default-endpoint';
        let questionPayload = {
          name: trimmedTitle,
          endpoint_id: endpoint,
          query: {kind: 'sql', sql: sqlClean},
          visualization: {type: 'bar'},
        };
        if (typeof designClient.biSqlBridge === 'function') {
          const converted = await designClient.biSqlBridge(projectId, {
            action: 'from_sql',
            sql: sqlClean,
            name: trimmedTitle,
            endpoint_id: endpoint,
          });
          if (converted?.question) {
            questionPayload = converted.question;
          }
          setImportSummary({
            source_format: `SQL (${converted?.fidelity || 'exact'})`,
            loss_count: (converted?.loss || []).length,
          });
        }
        const created = await designClient.createBiQuestion(projectId, {
          key,
          title: trimmedTitle,
          endpointId: endpoint,
          question: questionPayload,
        });
        await refresh();
        setOpen(false);
        onOpenDesign(projectId, created);
        return;
      }

      let prefilledQuestion = undefined;
      if (draft.mode === 'new_question' && Array.isArray(draft.prefillRelation)) {
        const alias = String(
          draft.prefillRelation[draft.prefillRelation.length - 1] || 'tbl'
        ).replace(/[^A-Za-z0-9_]+/g, '_') || 'tbl';
        prefilledQuestion = {
          name: trimmedTitle,
          endpoint_id: draft.endpointId.trim() || 'default-endpoint',
          query: {
            kind: 'sbsql',
            sbsql: {
              from: {relation: draft.prefillRelation, alias},
              columns: [],
              measures: [{function: 'count', column: null, alias: 'row_count'}],
              limit: 100,
            },
          },
          visualization: {type: 'bar'},
        };
      }

      const created =
        draft.mode === 'new_dashboard'
          ? await designClient.createBiDashboard(projectId, {
            key,
            title: trimmedTitle,
          })
          : await designClient.createBiQuestion(projectId, {
            key,
            title: trimmedTitle,
            endpointId: draft.endpointId.trim() || 'default-endpoint',
            question: prefilledQuestion,
          });

      await refresh();
      setOpen(false);
      onOpenDesign(projectId, created);
    } catch (saveErr) {
      setCreateError(saveErr.message);
    } finally {
      setSaving(false);
    }
  };

  const total = groups.reduce((count, g) => count + g.items.length, 0);
  const isImportMode =
    draft.mode === 'import_superset' ||
    draft.mode === 'import_metabase' ||
    draft.mode === 'import_legacy_bi' ||
    draft.mode === 'from_sql';

  return (
    <Box
      component="section"
      aria-label="BI Questions and Dashboards"
      sx={{
        height: '100%',
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <FormReference formKey="bi-designs-navigator" />
      <Toolbar label="BI design commands">
        <Button onClick={beginCreate}>New BI design…</Button>
        <Button onClick={refresh}>Refresh</Button>
      </Toolbar>
      {importSummary && (
        <Box sx={{p: 1}}>
          <Banner status="info" onClose={() => setImportSummary(null)}>
            Imported {importSummary.source_format} into Draft DDN (loss items:{' '}
            {importSummary.loss_count || 0}).
          </Banner>
        </Box>
      )}
      <Box
        role="tree"
        aria-label="BI designs by project"
        sx={{position: 'relative', flex: 1, minHeight: 0, overflow: 'auto'}}
      >
        {error && (
          <EmptyState
            role="alert"
            message={error}
            actionLabel="Retry"
            onAction={refresh}
          />
        )}
        {!error && !loading && !total && (
          <EmptyState
            message="No BI questions or dashboards yet. Create a question, compose a dashboard or import Superset / Metabase exports."
            actionLabel="New BI design"
            onAction={beginCreate}
          />
        )}
        {!error &&
          groups
            .filter((g) => g.items.length || g.error)
            .map(({project, items, error: projErr}) => (
              <Box key={project.project_id} role="group">
                <TreeRow
                  level={1}
                  label={project.name}
                  expandable
                  expanded
                  warning={projErr}
                  icon={<Icon iconKey="object.schema" decorative />}
                />
                {items.map((item) => (
                  <TreeRow
                    level={2}
                    key={item.id}
                    label={`${item.title} (${item.kind})`}
                    icon={<Icon iconKey="tool.data-explorer" decorative />}
                    trailing={`v${item.head_version}`}
                    onOpen={() => onOpenDesign(project.project_id, item)}
                  />
                ))}
              </Box>
            ))}
        <ProgressOverlay message={loading ? 'Loading BI designs' : ''} />
      </Box>

      <Dialog
        open={open}
        title="New or imported BI question or dashboard"
        size="medium"
        onClose={() => !saving && setOpen(false)}
        busy={saving}
        validationError={createError}
        defaultAction={create}
        actions={
          <>
            <Button disabled={saving} onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button intent="primary" loading={saving} onClick={create}>
              Continue
            </Button>
          </>
        }
      >
        <FormReference formKey="bi-design-create" />
        {isImportMode && <FormReference formKey="bi-designer-import" />}
        <Stack gap="standard">
          <Select
            label="Mode"
            value={draft.mode}
            options={[
              {value: 'new_question', label: 'New BI question'},
              {value: 'from_sql', label: 'New BI question from SQL'},
              {value: 'new_dashboard', label: 'New BI dashboard'},
              {
                value: 'import_superset',
                label: 'Import Apache Superset YAML ZIP / JSON (Draft)',
              },
              {
                value: 'import_metabase',
                label: 'Import Metabase serialization bundle (Draft)',
              },
              {
                value: 'import_legacy_bi',
                label:
                  'Migrate Legacy ScratchRobin BI (JSON / Store -> Draft DDN)',
              },
            ]}
            onChange={(val) =>
              setDraft((cur) => ({
                ...cur,
                mode: val,
                fileName: '',
                parsedBundle: null,
                archiveBase64: '',
              }))
            }
          />
          {(draft.mode === 'new_question' ||
            draft.mode === 'new_dashboard' ||
            draft.mode === 'from_sql') && (
            <TextField
              autoFocus
              required
              label="Design title"
              value={draft.title}
              onChange={(e) =>
                setDraft((cur) => ({...cur, title: e.target.value}))
              }
            />
          )}
          {draft.mode === 'new_question' && draft.prefillRelation && (
            <Badge
              status="info"
              label={`Source table: ${draft.prefillRelation.join('.')}`}
            />
          )}
          {draft.mode === 'from_sql' && (
            <Box sx={{height: 160}}>
              <CodeEditor
                label="Source SQL"
                language="sql"
                value={draft.sqlText}
                onChange={(val) => {
                  const next =
                    typeof val === 'string' ? val : val?.target?.value ?? '';
                  if (next === sqlTextRef.current) return;
                  sqlTextRef.current = next;
                  setDraft((cur) => ({...cur, sqlText: next}));
                }}
              />
            </Box>
          )}
          {(draft.mode === 'import_superset' ||
            draft.mode === 'import_metabase' ||
            draft.mode === 'import_legacy_bi') && (
            <Stack gap="compact">
              <Box
                component="label"
                sx={{fontSize: '0.8125rem', fontWeight: 600}}
              >
                {draft.mode === 'import_legacy_bi'
                  ? 'Optional Legacy BI JSON File (leave empty to read live store)'
                  : 'Select Export Bundle (.zip or .json)'}
                <Box sx={{mt: 0.5}}>
                  <input
                    type="file"
                    aria-label="Import bundle file"
                    accept=".zip,.json,.yaml,.yml,.tar.gz,.tgz"
                    onChange={handleBundleFileSelect}
                  />
                </Box>
              </Box>
              {draft.fileName && (
                <Badge status="success" label={`Selected: ${draft.fileName}`} />
              )}
            </Stack>
          )}
          {draft.mode !== 'new_dashboard' && (
            <TextField
              label="Target Endpoint ID"
              value={draft.endpointId}
              onChange={(e) =>
                setDraft((cur) => ({...cur, endpointId: e.target.value}))
              }
            />
          )}
          <Select
            label="Project"
            value={draft.project}
            options={[
              ...writable.map(({project}) => ({
                value: project.project_id,
                label: project.name,
              })),
              {value: NEW_PROJECT, label: 'New project…'},
            ]}
            onChange={(val) => setDraft((cur) => ({...cur, project: val}))}
          />
          {draft.project === NEW_PROJECT && (
            <>
              <TextField
                label="New project ID"
                required
                value={draft.projectId}
                onChange={(e) =>
                  setDraft((cur) => ({...cur, projectId: e.target.value}))
                }
              />
              <TextField
                label="New project name"
                value={draft.projectName}
                onChange={(e) =>
                  setDraft((cur) => ({...cur, projectName: e.target.value}))
                }
              />
            </>
          )}
        </Stack>
      </Dialog>
    </Box>
  );
}

BIDesignsNavigator.propTypes = {
  designClient: PropTypes.object,
  projectClient: PropTypes.object,
  onOpenDesign: PropTypes.func,
};
