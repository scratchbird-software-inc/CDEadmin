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
import {Box, ScrollArea, Stack} from '../../primitives/Layout';
import {Icon} from '../../icons';
import {ProjectAssetClient} from '../../projects/ProjectAssetClient';
import {Toolbar} from '../../layout/WorkbenchChrome';
import {Button} from '../../primitives/Button';
import {TextArea, TextField} from '../../primitives/Field';
import {Select} from '../../primitives/Choice';
import {TreeRow} from '../../navigation/AdvancedNavigation';
import {Dialog} from '../../overlays/Dialog';
import {Banner} from '../../feedback/Indicators';
import {EmptyState} from '../../feedback/EmptyState';
import {ProgressOverlay} from '../../feedback/ProgressOverlay';
import {StatusBadge} from '../../status/StatusBadge';
import FormReference from '../../navigation/FormReference';
import {
  DesignerModalTabs,
  FormGrid,
  TypedRowsEditor,
  WhereUsedDialog,
} from './DesignerChrome';
import {DesignStoreClient} from './sharedDesignLibrary';

export const ERD_MODEL_CREATE_EVENT = 'cdeadmin:erd-model-create';
export const ERD_MODEL_OPEN_EVENT = 'cdeadmin:erd-model-open';
const NEW_PROJECT = '\u0000new-project';
const WRITABLE = new Set(['owner', 'manager', 'editor']);
let pendingCreate = false;

const IMPORT_ENGINE_OPTIONS = Object.freeze([
  {value: 'postgresql', label: 'PostgreSQL'},
  {value: 'sqlite', label: 'SQLite'},
  {value: 'duckdb', label: 'DuckDB'},
  {value: 'firebird', label: 'Firebird 5'},
  {value: 'mysql', label: 'MySQL'},
  {value: 'mariadb', label: 'MariaDB'},
]);

export function requestERDModelCreate() {
  pendingCreate = true;
  window.dispatchEvent(new CustomEvent(ERD_MODEL_CREATE_EVENT));
}

function takePendingCreate() {
  const pending = pendingCreate;
  pendingCreate = false;
  return pending;
}

export function openERDModel(projectId, design) {
  window.dispatchEvent(
    new CustomEvent(ERD_MODEL_OPEN_EVENT, {
      detail: {
        projectId,
        designId: design.id,
        title: design.title,
      },
    })
  );
}

function slugKey(name) {
  return (
    String(name || '')
      .toLowerCase()
      .normalize('NFKD')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 64) || 'data-model'
  );
}

function buildSampleOperationsTemplate() {
  return {
    conceptualEntities: [
      {name: 'Customer'},
      {name: 'Work Order'},
    ],
    logicalEntities: [
      {
        name: 'Customer',
        fields: [
          {name: 'customer_id', datatype: 'bigint', nullable: false},
          {name: 'email', datatype: 'string', nullable: false},
        ],
      },
      {
        name: 'WorkOrder',
        fields: [
          {name: 'work_order_id', datatype: 'bigint', nullable: false},
          {name: 'customer_id', datatype: 'bigint', nullable: false},
          {name: 'status', datatype: 'string', nullable: false},
        ],
      },
    ],
    physicalTables: [
      {
        name: 'customers',
        engine: 'postgresql',
        fields: [
          {name: 'customer_id', datatype: 'BIGINT', nullable: false},
          {name: 'email', datatype: 'VARCHAR(255)', nullable: false},
        ],
      },
      {
        name: 'work_orders',
        engine: 'postgresql',
        fields: [
          {name: 'work_order_id', datatype: 'BIGINT', nullable: false},
          {name: 'customer_id', datatype: 'BIGINT', nullable: false},
          {name: 'status', datatype: 'VARCHAR(32)', nullable: false},
        ],
      },
    ],
    deploymentNodes: [
      {
        name: 'ops-pg-primary',
        engine: 'postgresql',
        host: 'pg-ops-01.internal',
        cloud_region: 'us-east-1',
      },
    ],
  };
}

export function ERDModelsNavigator({
  designClient: suppliedDesignClient,
  projectClient: suppliedProjectClient,
  onOpenModel = openERDModel,
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

  // Create New Data Model state
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState({
    title: '',
    project: '',
    projectId: 'models',
    projectName: 'Data Models',
    starterTemplate: 'blank',
    initialRole: 'conceptual',
    firstEntityName: '',
  });
  const [createError, setCreateError] = useState('');
  const [saving, setSaving] = useState(false);

  // Import SQL / DBML / Catalog modal state (SR-F-030015)
  const [importOpen, setImportOpen] = useState(false);
  const [importTab, setImportTab] = useState('source');
  const [importDraft, setImportDraft] = useState({
    title: '',
    project: '',
    projectId: 'models',
    projectName: 'Data Models',
    format: 'sql',
    targetEngine: 'postgresql',
    sourceText: '',
    endpointId: '',
    sqlitePath: '',
    catalogRows: [],
  });
  const [importError, setImportError] = useState('');
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);

  // Cross-design Where Used dialog state (SR-F-030041)
  const [whereUsedOpen, setWhereUsedOpen] = useState(false);
  const [whereUsedTarget, setWhereUsedTarget] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const projects = await projectClient.listProjects();
      const loaded = await Promise.all(
        projects.map(async (project) => {
          try {
            const models = await designClient.listDesigns(project.project_id, {
              kind: 'erd',
            });
            return {project, models: models || [], error: ''};
          } catch (loadErr) {
            return {project, models: [], error: loadErr.message};
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
  const defaultProjectId =
    writable[0]?.project.project_id || groups[0]?.project.project_id || NEW_PROJECT;

  const beginCreate = useCallback(() => {
    setCreateError('');
    setDraft((cur) => ({
      ...cur,
      title: '',
      firstEntityName: '',
      starterTemplate: 'blank',
      project: cur.project || writable[0]?.project.project_id || NEW_PROJECT,
    }));
    setOpen(true);
  }, [writable]);

  const beginImport = useCallback(
    (preset = {}) => {
      setImportError('');
      setImportResult(null);
      setImportTab('source');
      setImportDraft((cur) => ({
        ...cur,
        title: preset.title ?? '',
        format: preset.format || 'sql',
        targetEngine: preset.targetEngine || 'postgresql',
        endpointId: preset.endpointId ?? '',
        sqlitePath: preset.sqlitePath ?? '',
        sourceText: preset.sourceText ?? '',
        project: cur.project || writable[0]?.project.project_id || NEW_PROJECT,
      }));
      setImportOpen(true);
    },
    [writable]
  );

  useEffect(() => {
    refresh().then((loaded) => {
      if (takePendingCreate()) {
        const first = loaded.find(({project}) => WRITABLE.has(project.access));
        setDraft((cur) => ({
          ...cur,
          title: '',
          firstEntityName: '',
          starterTemplate: 'blank',
          project: first?.project.project_id || NEW_PROJECT,
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
    window.addEventListener(ERD_MODEL_CREATE_EVENT, listener);
    return () => window.removeEventListener(ERD_MODEL_CREATE_EVENT, listener);
  }, [beginCreate]);

  // Listen for provider context-menu shortcuts ('erd_from_database' & 'where_used')
  useEffect(() => {
    const onDesignShortcut = (evt) => {
      const detail = evt?.detail || {};
      const shortcut = detail.design_shortcut;
      if (shortcut === 'erd_from_database') {
        const engineGuess = String(detail.providerId || 'postgresql')
          .toLowerCase()
          .replace(/^org\.cdeadmin\./, '');
        const validEngine = IMPORT_ENGINE_OPTIONS.some(
          (o) => o.value === engineGuess
        )
          ? engineGuess
          : 'postgresql';
        beginImport({
          format: 'catalog',
          endpointId: detail.endpointId || '',
          targetEngine: validEngine,
          title: detail.endpointLabel
            ? `${detail.endpointLabel} ERD`
            : 'Imported Catalog ERD',
        });
      } else if (shortcut === 'where_used') {
        setWhereUsedTarget(detail.targetRef || detail.endpointLabel || '');
        setWhereUsedOpen(true);
      }
    };
    window.addEventListener('cdeadmin:design-shortcut', onDesignShortcut);
    return () =>
      window.removeEventListener('cdeadmin:design-shortcut', onDesignShortcut);
  }, [beginImport]);

  const resolveOrCreateProject = async (selectedProject, projIdRaw, projNameRaw) => {
    if (selectedProject !== NEW_PROJECT) return selectedProject;
    const projectId = projIdRaw.trim();
    if (!/^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,255}$/.test(projectId)) {
      throw new Error('Project ID must be a stable identifier without spaces.');
    }
    await projectClient.createProject(projectId, {
      name: projNameRaw.trim() || projectId,
    });
    return projectId;
  };

  const create = async () => {
    const trimmedTitle = draft.title.trim();
    if (!trimmedTitle) {
      setCreateError('A data model needs a title.');
      return;
    }
    setSaving(true);
    setCreateError('');
    try {
      const projectId = await resolveOrCreateProject(
        draft.project,
        draft.projectId,
        draft.projectName
      );

      let payload;
      if (draft.starterTemplate === 'sample_ops') {
        payload = {
          key: `${slugKey(trimmedTitle)}-${Date.now().toString(36)}`,
          title: trimmedTitle,
          ...buildSampleOperationsTemplate(),
        };
      } else {
        const entityName = draft.firstEntityName.trim();
        payload = {
          key: `${slugKey(trimmedTitle)}-${Date.now().toString(36)}`,
          title: trimmedTitle,
          conceptualEntities:
            entityName && draft.initialRole === 'conceptual'
              ? [{name: entityName}]
              : [],
          logicalEntities:
            entityName && draft.initialRole === 'logical'
              ? [{name: entityName, fields: [{name: 'id', datatype: 'uuid'}]}]
              : [],
          physicalTables:
            entityName && draft.initialRole === 'physical'
              ? [
                {
                  name: entityName,
                  engine: 'sqlite',
                  fields: [{name: 'id', datatype: 'INTEGER', nullable: false}],
                },
              ]
              : [],
        };
      }

      const created = await designClient.createErdDesign(projectId, payload);
      await refresh();
      setOpen(false);
      onOpenModel(projectId, created);
    } catch (saveErr) {
      setCreateError(saveErr.message);
    } finally {
      setSaving(false);
    }
  };

  const handleImportFile = (evt) => {
    const file = evt.target.files?.[0];
    if (!file) return;
    const lower = file.name.toLowerCase();
    const detectedFmt = lower.endsWith('.dbml') ? 'dbml' : 'sql';
    const reader = new FileReader();
    reader.onload = () => {
      const text = typeof reader.result === 'string' ? reader.result : '';
      setImportDraft((cur) => ({
        ...cur,
        format: detectedFmt,
        title: cur.title || file.name.replace(/\.[^.]+$/, ''),
        sourceText: text,
      }));
    };
    reader.readAsText(file);
  };

  const submitImport = async () => {
    if (
      (importDraft.format === 'sql' || importDraft.format === 'dbml') &&
      !importDraft.sourceText.trim()
    ) {
      setImportError(
        `Paste or upload ${importDraft.format.toUpperCase()} schema source before importing.`
      );
      return;
    }
    setImporting(true);
    setImportError('');
    try {
      const projectId = await resolveOrCreateProject(
        importDraft.project || defaultProjectId,
        importDraft.projectId,
        importDraft.projectName
      );
      const catalogTables =
        importDraft.format === 'catalog'
          ? importDraft.catalogRows
            .filter((r) => String(r.name || '').trim())
            .map((r) => ({
              name: String(r.name).trim(),
              columns: [
                {
                  name: String(r.pk_column || 'id').trim(),
                  type: String(r.pk_type || 'BIGINT').trim(),
                  pk: true,
                  nullable: false,
                },
              ],
            }))
          : undefined;

      const res = await designClient.importErdExternal(projectId, {
        format: importDraft.format,
        title:
          importDraft.title.trim() ||
          `Imported ${importDraft.format.toUpperCase()} Model`,
        target_engine: importDraft.targetEngine,
        source: importDraft.sourceText,
        endpoint_id: importDraft.endpointId.trim() || undefined,
        sqlite_path: importDraft.sqlitePath.trim() || undefined,
        tables: catalogTables?.length ? catalogTables : undefined,
      });
      await refresh();
      setImportResult({projectId, ...res});
      setImportTab('report');
      if ((res?.loss_report?.loss_count ?? 0) === 0 && res?.design) {
        onOpenModel(projectId, res.design);
      }
    } catch (impErr) {
      setImportError(impErr.message);
    } finally {
      setImporting(false);
    }
  };

  const total = groups.reduce((count, g) => count + g.models.length, 0);
  const activeWhereUsedProject =
    writable[0]?.project.project_id || groups[0]?.project.project_id || 'models';

  return (
    <Box
      component="section"
      aria-label="Data Models (ERD)"
      sx={{
        height: '100%',
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <FormReference formKey="erd-models" />
      <Toolbar label="Data model commands">
        <Button intent="primary" onClick={beginCreate}>
          New data model…
        </Button>
        <Button onClick={() => beginImport()}>
          Import SQL / DBML / Catalog…
        </Button>
        <Button
          onClick={() => {
            setWhereUsedTarget('');
            setWhereUsedOpen(true);
          }}
        >
          Where Used…
        </Button>
        <Button onClick={refresh}>Refresh</Button>
      </Toolbar>

      <Box
        role="tree"
        aria-label="Data models by project"
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
            message="No data models yet. Start a conceptual whiteboard sketch, sample 4-level schema, or import SQL / DBML / live catalog."
            actionLabel="New data model"
            onAction={beginCreate}
          />
        )}
        {!error &&
          groups
            .filter((g) => g.models.length || g.error)
            .map(({project, models, error: projErr}) => (
              <Box key={project.project_id} role="group">
                <TreeRow
                  level={1}
                  label={project.name}
                  expandable
                  expanded
                  warning={projErr}
                  icon={<Icon iconKey="object.schema" decorative />}
                />
                {models.map((model) => (
                  <TreeRow
                    level={2}
                    key={model.id}
                    label={model.title}
                    icon={<Icon iconKey="tool.erd" decorative />}
                    trailing={`v${model.head_version}`}
                    onOpen={() => onOpenModel(project.project_id, model)}
                  />
                ))}
              </Box>
            ))}
        <ProgressOverlay message={loading ? 'Loading data models' : ''} />
      </Box>

      {/* New Data Model Dialog with Starter Templates */}
      <Dialog
        open={open}
        title="New data model (ERD)"
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
              Create data model
            </Button>
          </>
        }
      >
        <FormReference formKey="erd-model-create" />
        <Stack gap="standard">
          <FormGrid columns={2}>
            <TextField
              autoFocus
              required
              label="Model title"
              value={draft.title}
              onChange={(e) =>
                setDraft((cur) => ({...cur, title: e.target.value}))
              }
            />
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
          </FormGrid>

          {draft.project === NEW_PROJECT && (
            <FormGrid columns={2}>
              <TextField
                required
                label="Project ID"
                value={draft.projectId}
                onChange={(e) =>
                  setDraft((cur) => ({...cur, projectId: e.target.value}))
                }
              />
              <TextField
                label="Project name"
                value={draft.projectName}
                onChange={(e) =>
                  setDraft((cur) => ({...cur, projectName: e.target.value}))
                }
              />
            </FormGrid>
          )}

          <Select
            label="Starter template"
            value={draft.starterTemplate}
            options={[
              {
                value: 'blank',
                label: 'Blank Conceptual Whiteboard / Role',
              },
              {
                value: 'sample_ops',
                label: 'Sample Four-Level Operations Schema',
              },
            ]}
            onChange={(val) =>
              setDraft((cur) => ({...cur, starterTemplate: val}))
            }
          />

          {draft.starterTemplate === 'blank' && (
            <FormGrid columns={2}>
              <Select
                label="Starting role"
                value={draft.initialRole}
                options={[
                  {
                    value: 'conceptual',
                    label: 'Conceptual whiteboard (free-form drafting)',
                  },
                  {value: 'logical', label: 'Logical data model'},
                  {value: 'physical', label: 'Physical ERD'},
                ]}
                onChange={(val) =>
                  setDraft((cur) => ({...cur, initialRole: val}))
                }
              />
              <TextField
                label="Initial entity or table name (optional)"
                value={draft.firstEntityName}
                onChange={(e) =>
                  setDraft((cur) => ({...cur, firstEntityName: e.target.value}))
                }
              />
            </FormGrid>
          )}
        </Stack>
      </Dialog>

      {/* Import SQL / DBML / Catalog Modal (SR-F-030015) */}
      <Dialog
        open={importOpen}
        title="Import SQL DDL, DBML or Live Catalog into Draft ERD"
        size="large"
        busy={importing}
        onClose={() => !importing && setImportOpen(false)}
        actions={
          <>
            <Button disabled={importing} onClick={() => setImportOpen(false)}>
              Close
            </Button>
            {importResult?.design && (
              <Button
                onClick={() => {
                  setImportOpen(false);
                  onOpenModel(importResult.projectId, importResult.design);
                }}
              >
                Open Imported Model
              </Button>
            )}
            <Button intent="primary" loading={importing} onClick={submitImport}>
              Import as Draft ERD
            </Button>
          </>
        }
      >
        <DesignerModalTabs
          formKey="erd-designer-import"
          activeTab={importTab}
          onTabChange={setImportTab}
          banner={
            importError ? <Banner status="error">{importError}</Banner> : null
          }
          tabs={[
            {
              id: 'source',
              label: 'Import Source & Dialect',
              render: () => (
                <Stack gap="standard">
                  <FormGrid columns={2}>
                    <TextField
                      label="Model title"
                      placeholder="e.g. Commerce Core ERD"
                      value={importDraft.title}
                      onChange={(e) =>
                        setImportDraft((cur) => ({
                          ...cur,
                          title: e.target.value,
                        }))
                      }
                    />
                    <Select
                      label="Project"
                      value={importDraft.project || defaultProjectId}
                      options={[
                        ...writable.map(({project}) => ({
                          value: project.project_id,
                          label: project.name,
                        })),
                        {value: NEW_PROJECT, label: 'New project…'},
                      ]}
                      onChange={(val) =>
                        setImportDraft((cur) => ({...cur, project: val}))
                      }
                    />
                    <Select
                      label="Import Format"
                      value={importDraft.format}
                      options={[
                        {value: 'sql', label: 'SQL DDL Script (.sql)'},
                        {value: 'dbml', label: 'DBML Schema (.dbml)'},
                        {value: 'catalog', label: 'Live Database Catalog'},
                      ]}
                      onChange={(val) =>
                        setImportDraft((cur) => ({...cur, format: val}))
                      }
                    />
                    <Select
                      label="Target Physical Engine"
                      value={importDraft.targetEngine}
                      options={IMPORT_ENGINE_OPTIONS}
                      onChange={(val) =>
                        setImportDraft((cur) => ({
                          ...cur,
                          targetEngine: val,
                        }))
                      }
                    />
                  </FormGrid>

                  {(importDraft.format === 'sql' ||
                    importDraft.format === 'dbml') && (
                    <Stack gap="compact">
                      <Box>
                        <Box
                          component="label"
                          sx={{
                            display: 'block',
                            fontSize: '0.75rem',
                            fontWeight: 600,
                            mb: 0.5,
                          }}
                        >
                          Upload .sql or .dbml file
                          <input
                            type="file"
                            aria-label="Upload SQL or DBML file"
                            accept=".sql,.ddl,.dbml,.txt"
                            style={{display: 'block', marginTop: 4}}
                            onChange={handleImportFile}
                          />
                        </Box>
                      </Box>
                      <TextArea
                        rows={7}
                        label="Schema source text"
                        placeholder={
                          importDraft.format === 'dbml'
                            ? 'Table customers {\n  id bigint [pk]\n}'
                            : 'CREATE TABLE customers (id BIGINT PRIMARY KEY);'
                        }
                        value={importDraft.sourceText}
                        onChange={(e) =>
                          setImportDraft((cur) => ({
                            ...cur,
                            sourceText: e.target.value,
                          }))
                        }
                      />
                    </Stack>
                  )}

                  {importDraft.format === 'catalog' && (
                    <Stack gap="standard">
                      <FormGrid columns={2}>
                        <TextField
                          label="Registered Endpoint ID"
                          placeholder="e.g. ep-prod-pg"
                          value={importDraft.endpointId}
                          onChange={(e) =>
                            setImportDraft((cur) => ({
                              ...cur,
                              endpointId: e.target.value,
                            }))
                          }
                        />
                        <TextField
                          label="SQLite / Local Database File Path (optional)"
                          placeholder="/path/to/database.sqlite"
                          value={importDraft.sqlitePath}
                          onChange={(e) =>
                            setImportDraft((cur) => ({
                              ...cur,
                              sqlitePath: e.target.value,
                            }))
                          }
                        />
                      </FormGrid>
                      <TypedRowsEditor
                        label="Optional Catalog Table Snapshot"
                        addLabel="Catalog Table"
                        rows={importDraft.catalogRows}
                        columns={[
                          {key: 'name', label: 'Table Name', minWidth: 150},
                          {
                            key: 'pk_column',
                            label: 'PK Column',
                            default: 'id',
                            minWidth: 110,
                          },
                          {
                            key: 'pk_type',
                            label: 'PK SQL Type',
                            default: 'BIGINT',
                            minWidth: 110,
                          },
                        ]}
                        onChange={(rows) =>
                          setImportDraft((cur) => ({...cur, catalogRows: rows}))
                        }
                      />
                    </Stack>
                  )}
                </Stack>
              ),
            },
            {
              id: 'report',
              label: `Loss Report${
                importResult?.loss_report
                  ? ` (${importResult.loss_report.loss_count || 0})`
                  : ''
              }`,
              attention: (importResult?.loss_report?.loss_count || 0) > 0,
              render: () =>
                !importResult ? (
                  <EmptyState message="Run an import to inspect imported table counts, foreign key relationships and explicit conversion loss items." />
                ) : (
                  <Stack gap="standard">
                    <Stack direction="row" gap="compact">
                      <StatusBadge
                        status="success"
                        label={`${importResult.summary?.tables_imported ?? 0} Tables`}
                      />
                      <StatusBadge
                        status="info"
                        label={`${importResult.summary?.relationships_imported ?? 0} Foreign Keys`}
                      />
                      <StatusBadge
                        status={
                          (importResult.loss_report?.loss_count || 0) > 0
                            ? 'warning'
                            : 'success'
                        }
                        label={`${importResult.loss_report?.loss_count ?? 0} Loss Items`}
                      />
                    </Stack>

                    {(importResult.loss_report?.items || []).length === 0 ? (
                      <Banner status="success">
                        Imported cleanly with zero unsupported clauses or losses.
                      </Banner>
                    ) : (
                      <ScrollArea
                        label="Import loss report items"
                        sx={{maxHeight: 260}}
                      >
                        <Box
                          data-testid="erd-import-loss-report"
                          component="table"
                          aria-label="ERD import loss report"
                          sx={{
                            width: '100%',
                            borderCollapse: 'collapse',
                            fontSize: '0.8125rem',
                          }}
                        >
                          <Box component="thead">
                            <Box component="tr">
                              {['Code', 'Severity', 'Object', 'Detail'].map(
                                (h) => (
                                  <Box
                                    key={h}
                                    component="th"
                                    sx={{
                                      textAlign: 'left',
                                      p: 0.75,
                                      borderBottom: '1px solid',
                                      borderColor: 'divider',
                                    }}
                                  >
                                    {h}
                                  </Box>
                                )
                              )}
                            </Box>
                          </Box>
                          <Box component="tbody">
                            {importResult.loss_report.items.map((item, idx) => (
                              <Box key={idx} component="tr">
                                <Box
                                  component="td"
                                  sx={{
                                    p: 0.75,
                                    borderBottom: '1px solid',
                                    borderColor: 'divider',
                                  }}
                                >
                                  <code>{item.code}</code>
                                </Box>
                                <Box
                                  component="td"
                                  sx={{
                                    p: 0.75,
                                    borderBottom: '1px solid',
                                    borderColor: 'divider',
                                  }}
                                >
                                  <StatusBadge
                                    status={
                                      item.severity === 'warning'
                                        ? 'warning'
                                        : 'info'
                                    }
                                    label={item.severity || 'info'}
                                  />
                                </Box>
                                <Box
                                  component="td"
                                  sx={{
                                    p: 0.75,
                                    borderBottom: '1px solid',
                                    borderColor: 'divider',
                                  }}
                                >
                                  {item.object}
                                </Box>
                                <Box
                                  component="td"
                                  sx={{
                                    p: 0.75,
                                    borderBottom: '1px solid',
                                    borderColor: 'divider',
                                  }}
                                >
                                  {item.detail}
                                </Box>
                              </Box>
                            ))}
                          </Box>
                        </Box>
                      </ScrollArea>
                    )}
                  </Stack>
                ),
            },
          ]}
        />
      </Dialog>

      {/* Cross-Design Where Used Explorer (SR-F-030041) */}
      <WhereUsedDialog
        open={whereUsedOpen}
        onClose={() => setWhereUsedOpen(false)}
        client={designClient}
        projectId={activeWhereUsedProject}
        initialTargetRef={whereUsedTarget}
      />
    </Box>
  );
}

ERDModelsNavigator.propTypes = {
  designClient: PropTypes.object,
  projectClient: PropTypes.object,
  onOpenModel: PropTypes.func,
};
