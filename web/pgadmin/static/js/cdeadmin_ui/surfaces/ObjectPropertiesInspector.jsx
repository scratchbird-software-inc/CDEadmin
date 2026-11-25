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
import gettext from 'sources/gettext';
import {Box} from '../primitives/Layout';
import {Button} from '../primitives/Button';
import {Checkbox, Select} from '../primitives/Choice';
import {ScratchScrollArea} from '../base/ScratchScrollArea';
import {Dialog} from '../overlays/Dialog';
import UnifiedDataGrid from '../data/UnifiedDataGrid';
import ObjectPermissionsMatrix from '../security/ObjectGrantsSurface';
import {extractNodeQueryParams} from './ObjectDashboardSurface';

const NON_GRANT_ENGINES = new Set(['sqlite', 'duckdb']);
const GRANTABLE_NODE_TYPES = new Set([
  'cde_database_target',
  'database',
  'schema',
  'table',
  'partition',
  'foreign_table',
  'view',
  'mview',
  'sequence',
  'function',
  'procedure',
  'edbfunc',
  'edbproc',
  'package',
  'type',
  'domain',
  'cde_resource',
]);
const NON_GRANTABLE_RESOURCE_KINDS = new Set([
  'index',
  'partitioned-index',
  'trigger',
  'constraint',
  'rule',
  'row-policy',
  'user',
  'role',
  'storage-file',
  'configuration',
  'service-operation',
  'shadow',
  'exception',
  'blob-filter',
  'collation',
  'character-set',
  'authentication-mapping',
  'global-authentication-mapping',
]);

export function isObjectPermissionsSupported(nodeData) {
  if (!nodeData || !nodeData._type) return false;
  if (!GRANTABLE_NODE_TYPES.has(String(nodeData._type))) return false;
  const rawEngine = String(
    nodeData.cde_engine_id || nodeData.engine_id || nodeData.server_type || 'postgresql'
  ).toLowerCase();
  const engine = rawEngine === 'pg' ? 'postgresql' : rawEngine;
  if (NON_GRANT_ENGINES.has(engine)) return false;
  if (nodeData._type === 'cde_resource' && nodeData.cde_resource_kind) {
    if (NON_GRANTABLE_RESOURCE_KINDS.has(String(nodeData.cde_resource_kind).toLowerCase())) {
      return false;
    }
  }
  return true;
}

function buildJsonHeaders() {
  const win = typeof window !== 'undefined' ? window : {};
  const headerName = win.pgAdmin?.csrf_token_header || 'X-pgA-CSRFToken';
  const token = win.pgAdmin?.csrf_token || '';
  return {
    'Content-Type': 'application/json',
    ...(token ? {[headerName]: token} : {}),
  };
}

export default function ObjectPropertiesInspector({
  boundNodeData,
  instanceId,
  sectionFilter = 'all',
  onSectionFilterChange,
  renderNativeProperties,
}) {
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const [richProps, setRichProps] = useState(null);
  const [customizeOpen, setCustomizeOpen] = useState(false);
  const [customDraft, setCustomDraft] = useState({
    show_empty_attributes: false,
    show_system_attributes: true,
    show_native_registration_panel: true,
    default_section_filter: 'all',
  });

  const queryParams = useMemo(() => extractNodeQueryParams(boundNodeData), [boundNodeData]);
  const querySignature = useMemo(() => JSON.stringify(queryParams), [queryParams]);

  const fetchProperties = useCallback(async () => {
    if (typeof fetch !== 'function' || !boundNodeData) return;
    const search = new URLSearchParams();
    Object.entries(queryParams).forEach(([k, v]) => {
      if (v !== '' && v !== null && v !== undefined) {
        search.set(k, String(v));
      }
    });
    try {
      const resp = await fetch(`/cdeadmin/api/object_dashboard/properties?${search.toString()}`, {
        credentials: 'same-origin',
      });
      if (!resp.ok) return;
      const json = await resp.json();
      if (mountedRef.current && json && json.object_identity) {
        setRichProps(json);
        if (json.customization) {
          setCustomDraft((prev) => ({...prev, ...json.customization}));
        }
      }
    } catch {
      // Fall back cleanly to native properties panel when offline or in unit tests.
    }
  }, [boundNodeData, queryParams]);

  useEffect(() => {
    setRichProps(null);
    void fetchProperties();
  }, [querySignature]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const matchesInstance = (ev) =>
      !ev?.detail?.instanceId || !instanceId || ev.detail.instanceId === instanceId;

    const onRefresh = (ev) => {
      if (matchesInstance(ev)) void fetchProperties();
    };
    const onCustomize = (ev) => {
      if (matchesInstance(ev)) setCustomizeOpen(true);
    };
    const onCopyDdl = (ev) => {
      if (matchesInstance(ev) && richProps?.ddl?.sql && navigator?.clipboard?.writeText) {
        void navigator.clipboard.writeText(richProps.ddl.sql);
      }
    };
    window.addEventListener('scratchrobin:object-properties-refresh', onRefresh);
    window.addEventListener('scratchrobin:object-properties-customize', onCustomize);
    window.addEventListener('scratchrobin:object-properties-copy-ddl', onCopyDdl);
    return () => {
      window.removeEventListener('scratchrobin:object-properties-refresh', onRefresh);
      window.removeEventListener('scratchrobin:object-properties-customize', onCustomize);
      window.removeEventListener('scratchrobin:object-properties-copy-ddl', onCopyDdl);
    };
  }, [fetchProperties, instanceId, richProps]);

  const handleSaveCustomization = async () => {
    setRichProps((prev) =>
      prev ? {...prev, customization: {...customDraft}} : prev
    );
    setCustomizeOpen(false);
    if (customDraft.default_section_filter && onSectionFilterChange) {
      onSectionFilterChange(customDraft.default_section_filter);
    }
    if (typeof fetch === 'function') {
      try {
        await fetch('/cdeadmin/api/object_dashboard/preferences', {
          method: 'POST',
          credentials: 'same-origin',
          headers: buildJsonHeaders(),
          body: JSON.stringify({properties: customDraft}),
        });
      } catch {
        // Ignore offline preference persistence error in test mode.
      }
    }
  };

  const cust = richProps?.customization || customDraft;
  const visibleAttrs = useMemo(() => {
    const raw = richProps?.summary_attributes || [];
    return raw.filter((attr) => {
      if (!cust.show_empty_attributes && attr.is_empty) return false;
      if (!cust.show_system_attributes && attr.is_system) return false;
      return true;
    });
  }, [cust.show_empty_attributes, cust.show_system_attributes, richProps?.summary_attributes]);

  const showOverview = sectionFilter === 'all' || sectionFilter === 'settings';
  const showStructure = sectionFilter === 'all' || sectionFilter === 'structure';
  const showPermissions =
    isObjectPermissionsSupported(boundNodeData) &&
    (sectionFilter === 'all' || sectionFilter === 'permissions');
  const showDdl = sectionFilter === 'all' || sectionFilter === 'ddl';
  const showDeps = sectionFilter === 'all' || sectionFilter === 'dependencies';

  return (
    <ScratchScrollArea orientation="both" style={{flex: 1, minHeight: 0}}>
      <Box
        data-cdeadmin-qa-key="object-properties-inspector"
        sx={{
          display: 'flex',
          flexDirection: 'column',
          gap: 2,
          minWidth: 0,
        }}
      >
        {/* Native Registration / Object Properties Section */}
        {showOverview &&
          cust.show_native_registration_panel !== false &&
          typeof renderNativeProperties === 'function' && (
          <Box data-cdeadmin-qa-key="object-properties-native-section" sx={{minWidth: 0}}>
            {renderNativeProperties()}
          </Box>
        )}

        {/* Per-Object Grants / Permissions Matrix */}
        {showPermissions && (
          <Box
            data-cdeadmin-qa-key="object-properties-permissions-section"
            sx={{px: 2, pt: sectionFilter === 'permissions' ? 2 : 0, minWidth: 0}}
          >
            <ObjectPermissionsMatrix
              boundNodeData={boundNodeData}
              compact={sectionFilter === 'all'}
            />
          </Box>
        )}

        {/* Full Comment & Extended Catalog Attributes */}
        {richProps && (
          <Box sx={{px: 2, pb: 2, display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0}}>
            {showOverview && richProps.comment?.text && (
              <div
                data-cdeadmin-qa-key="object-properties-comment"
                style={{
                  border: '1px solid var(--sr-border-default)',
                  borderLeft: '3px solid var(--sr-accent-primary, #2563eb)',
                  borderRadius: 8,
                  padding: '10px 14px',
                  background: 'var(--sr-surface-subtle)',
                  fontSize: '0.82rem',
                  whiteSpace: 'pre-wrap',
                }}
              >
                <div
                  style={{
                    fontSize: '0.7rem',
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    color: 'var(--sr-text-secondary)',
                    marginBottom: 4,
                  }}
                >
                  {gettext('Object Comment / Description')}
                </div>
                {richProps.comment.text}
              </div>
            )}

            {showOverview && visibleAttrs.length > 0 && (
              <div
                data-cdeadmin-qa-key="object-properties-catalog-attributes"
                style={{
                  border: '1px solid var(--sr-border-default)',
                  borderRadius: 10,
                  padding: '12px 16px',
                  background: 'var(--sr-surface-default, var(--sr-island-bg))',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 10,
                }}
              >
                <div style={{fontWeight: 600, fontSize: '0.86rem'}}>
                  {gettext('Comprehensive Object Attributes')}
                </div>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))',
                    gap: '8px 14px',
                  }}
                >
                  {visibleAttrs.map((attr) => (
                    <div
                      key={attr.key}
                      style={{
                        padding: '6px 10px',
                        borderRadius: 6,
                        background: 'var(--sr-surface-subtle)',
                        border: '1px solid var(--sr-border-subtle, var(--sr-border-default))',
                      }}
                    >
                      <div style={{fontSize: '0.71rem', color: 'var(--sr-text-secondary)'}}>
                        {attr.category} · {attr.label}
                      </div>
                      <div
                        style={{
                          fontSize: '0.82rem',
                          fontWeight: 600,
                          fontFamily: 'var(--sr-font-mono, monospace)',
                          wordBreak: 'break-word',
                        }}
                      >
                        {attr.value}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Structure Sections (Columns, Indexes, Constraints, Triggers, Partitions) */}
            {showStructure &&
              (richProps.sections || []).map((sec) => (
                <div
                  key={sec.id}
                  data-cdeadmin-qa-key={`object-properties-section-${sec.id}`}
                  style={{
                    border: '1px solid var(--sr-border-default)',
                    borderRadius: 10,
                    padding: '12px 14px',
                    background: 'var(--sr-surface-default, var(--sr-island-bg))',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 8,
                  }}
                >
                  <div style={{fontWeight: 600, fontSize: '0.86rem'}}>
                    {sec.title} ({(sec.rows || []).length})
                  </div>
                  <div style={{height: 240, border: '1px solid var(--sr-border-default)', borderRadius: 8}}>
                    <UnifiedDataGrid
                      columns={sec.columns || []}
                      rows={sec.rows || []}
                      editable={false}
                    />
                  </div>
                </div>
              ))}

            {/* DDL / SQL Definition */}
            {showDdl && richProps.ddl?.available && (
              <div
                data-cdeadmin-qa-key="object-properties-ddl"
                style={{
                  border: '1px solid var(--sr-border-default)',
                  borderRadius: 10,
                  padding: '12px 14px',
                  background: 'var(--sr-surface-default, var(--sr-island-bg))',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 8,
                }}
              >
                <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                  <span style={{fontWeight: 600, fontSize: '0.86rem'}}>
                    {gettext('DDL / SQL Definition')}
                  </span>
                  {richProps.ddl.source && (
                    <span style={{fontSize: '0.72rem', color: 'var(--sr-text-secondary)'}}>
                      {richProps.ddl.source}
                    </span>
                  )}
                </div>
                <pre
                  style={{
                    margin: 0,
                    padding: '10px 12px',
                    borderRadius: 8,
                    background: 'var(--sr-surface-subtle)',
                    border: '1px solid var(--sr-border-default)',
                    fontFamily: 'var(--sr-font-mono, monospace)',
                    fontSize: '0.78rem',
                    overflowX: 'auto',
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {richProps.ddl.sql}
                </pre>
              </div>
            )}

            {/* Dependencies & Dependents */}
            {showDeps &&
              (richProps.dependencies?.length > 0 || richProps.dependents?.length > 0) && (
              <div
                data-cdeadmin-qa-key="object-properties-dependencies"
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
                  gap: 12,
                }}
              >
                {richProps.dependencies?.length > 0 && (
                  <div
                    style={{
                      border: '1px solid var(--sr-border-default)',
                      borderRadius: 10,
                      padding: '12px 14px',
                      background: 'var(--sr-surface-default, var(--sr-island-bg))',
                    }}
                  >
                    <div style={{fontWeight: 600, fontSize: '0.84rem', marginBottom: 6}}>
                      {gettext('Dependencies (%s)', richProps.dependencies.length)}
                    </div>
                    <div style={{height: 180}}>
                      <UnifiedDataGrid
                        columns={Object.keys(richProps.dependencies[0] || {name: ''})}
                        rows={richProps.dependencies}
                        editable={false}
                      />
                    </div>
                  </div>
                )}
                {richProps.dependents?.length > 0 && (
                  <div
                    style={{
                      border: '1px solid var(--sr-border-default)',
                      borderRadius: 10,
                      padding: '12px 14px',
                      background: 'var(--sr-surface-default, var(--sr-island-bg))',
                    }}
                  >
                    <div style={{fontWeight: 600, fontSize: '0.84rem', marginBottom: 6}}>
                      {gettext('Dependents (%s)', richProps.dependents.length)}
                    </div>
                    <div style={{height: 180}}>
                      <UnifiedDataGrid
                        columns={Object.keys(richProps.dependents[0] || {name: ''})}
                        rows={richProps.dependents}
                        editable={false}
                      />
                    </div>
                  </div>
                )}
              </div>
            )}
          </Box>
        )}
      </Box>

      {/* Customize Properties Dialog */}
      <Dialog
        open={customizeOpen}
        onClose={() => setCustomizeOpen(false)}
        title={gettext('Customize Object Properties View')}
        size="small"
        actions={
          <div style={{display: 'flex', justifyContent: 'flex-end', gap: 8}}>
            <Button size="small" intent="neutral" onClick={() => setCustomizeOpen(false)}>
              {gettext('Cancel')}
            </Button>
            <Button
              size="small"
              intent="primary"
              data-cdeadmin-qa-key="save-properties-customization"
              onClick={() => void handleSaveCustomization()}
            >
              {gettext('Save Preferences')}
            </Button>
          </div>
        }
      >
        <div style={{display: 'flex', flexDirection: 'column', gap: 12, padding: '4px 0'}}>
          <Checkbox
            label={gettext('Show Empty / Unset Attributes')}
            checked={Boolean(customDraft.show_empty_attributes)}
            onChange={(checked) =>
              setCustomDraft((prev) => ({...prev, show_empty_attributes: Boolean(checked)}))
            }
          />
          <Checkbox
            label={gettext('Show System & Internal Catalog Attributes')}
            checked={customDraft.show_system_attributes !== false}
            onChange={(checked) =>
              setCustomDraft((prev) => ({...prev, show_system_attributes: Boolean(checked)}))
            }
          />
          <Checkbox
            label={gettext('Show Native Registration & Connection Panel')}
            checked={customDraft.show_native_registration_panel !== false}
            onChange={(checked) =>
              setCustomDraft((prev) => ({
                ...prev,
                show_native_registration_panel: Boolean(checked),
              }))
            }
          />
          <Select
            label={gettext('Default Properties Section Filter')}
            value={customDraft.default_section_filter || 'all'}
            options={[
              {value: 'all', label: gettext('All Sections')},
              {value: 'permissions', label: gettext('Permissions & Grants')},
              {value: 'structure', label: gettext('Structure (Columns / Indexes / Constraints)')},
              {value: 'ddl', label: gettext('DDL / SQL Definition')},
              {value: 'dependencies', label: gettext('Dependencies & Dependents')},
              {value: 'settings', label: gettext('Connection & Overview Only')},
            ]}
            onChange={(val) =>
              setCustomDraft((prev) => ({...prev, default_section_filter: val}))
            }
          />
        </div>
      </Dialog>
    </ScratchScrollArea>
  );
}

ObjectPropertiesInspector.propTypes = {
  boundNodeData: PropTypes.object,
  instanceId: PropTypes.string,
  sectionFilter: PropTypes.string,
  onSectionFilterChange: PropTypes.func,
  renderNativeProperties: PropTypes.func,
};
