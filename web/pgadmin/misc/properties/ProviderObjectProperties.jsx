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
import pgAdmin from 'sources/pgadmin';
import {Alert, Box, Button, CircularProgress, Tab, Tabs} from '@mui/material';
import getApiInstance from '../../static/js/api_instance';
import FormReference from '../../static/js/cdeadmin_ui/navigation/FormReference';
import {resolveSectionIconKey} from '../../static/js/cdeadmin_ui/icons/registry';
import {useProjectInstanceScope} from '../../static/js/cdeadmin_ui/shell/ProjectShell';
import ObjectPermissionsMatrix from '../../static/js/cdeadmin_ui/security/ObjectGrantsSurface';
import {isObjectPermissionsSupported} from '../../static/js/cdeadmin_ui/surfaces/ObjectPropertiesInspector';
import {promptEndpointVerification} from '../../browser/static/js/ProviderObjectEditor';

const PRIVILEGE_SECTION_ALIASES = new Set(['privileges', 'grants', 'security', 'permissions']);

function resolveRequestedSection(requested, sections) {
  if (!requested) return sections[0] || 'properties';
  if (sections.includes(requested)) return requested;
  if (PRIVILEGE_SECTION_ALIASES.has(requested)) {
    const match = sections.find((sec) => PRIVILEGE_SECTION_ALIASES.has(sec));
    if (match) return match;
  }
  return sections[0] || 'properties';
}

const SECTION_EXCLUDED_NATIVE_KEYS = new Set([
  'property_sections', 'definition', 'metadata_source', 'ddl',
  'dependencies', 'dependents', 'privileges', 'package_privileges',
  'security', 'grants', 'acls', 'constraints', 'indexes', 'triggers',
  'columns', 'parameters', 'files', 'statistics', 'stats', 'metrics',
  'state', 'data', 'catalog_coverage', 'catalog_warnings',
]);

const SECTION_TITLE_MSGIDS = {
  properties: 'Properties',
  columns: 'Columns',
  constraints: 'Constraints',
  indexes: 'Indexes',
  triggers: 'Triggers',
  parameters: 'Parameters',
  definition: 'Definition',
  ddl: 'SQL / DDL',
  privileges: 'Privileges',
  permissions: 'Permissions',
  security: 'Security',
  grants: 'Grants',
  dependencies: 'Dependencies',
  dependents: 'Dependents',
  files: 'Storage files',
  statistics: 'Statistics',
  state: 'State',
  comments: 'Comments',
  calculations: 'Calculations',
  operations: 'Operations',
};

const INFERRED_SECTION_KEYS = [
  ['columns', ['columns']],
  ['constraints', ['constraints']],
  ['indexes', ['indexes']],
  ['triggers', ['triggers']],
  ['parameters', ['parameters']],
  ['definition', ['definition', 'metadata_source']],
  ['ddl', ['ddl']],
  ['privileges', ['privileges', 'package_privileges']],
  ['security', ['security', 'grants', 'acls']],
  ['dependencies', ['dependencies']],
  ['dependents', ['dependents']],
  ['files', ['files']],
  ['statistics', ['statistics', 'stats', 'metrics']],
  ['state', ['state']],
  ['comments', ['description', 'comments']],
  ['calculations', ['computed_source', 'computed_expression']],
];

function providerNative(resource) {
  return resource?.native && typeof resource.native === 'object' ? resource.native : {};
}

function humanizeFieldLabel(rawKey) {
  const cleaned = String(rawKey || '')
    .replace(/[_-]+/g, ' ')
    .trim();
  if (!cleaned) return '';
  const titled = cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
  return gettext(titled);
}

function getSectionTitle(section) {
  const msgid = SECTION_TITLE_MSGIDS[section];
  return msgid ? gettext(msgid) : humanizeFieldLabel(section);
}

function isScalarValue(val) {
  return val === null || val === undefined || typeof val !== 'object';
}

function isScalarList(val) {
  return Array.isArray(val) && val.every(isScalarValue);
}

function isObjectRowList(val) {
  return (
    Array.isArray(val) &&
    val.length > 0 &&
    val.every((row) => row && typeof row === 'object' && !Array.isArray(row))
  );
}

function formatScalarValue(value) {
  if (value === null || value === undefined || value === '') {
    return {text: gettext('Not set'), muted: true};
  }
  if (typeof value === 'boolean') {
    return {text: value ? gettext('Yes') : gettext('No'), muted: false};
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return {text: gettext('None'), muted: true};
    }
    return {
      text: value
        .map((item) =>
          item === null || item === undefined
            ? gettext('Not set')
            : typeof item === 'boolean'
              ? item
                ? gettext('Yes')
                : gettext('No')
              : String(item)
        )
        .join(' / '),
      muted: false,
    };
  }
  return {text: String(value), muted: false};
}

function computeSections(resource, descriptor, nodeData = null) {
  const native = providerNative(resource);
  const sections = ['properties'];
  if (Array.isArray(native.property_sections) && native.property_sections.length > 0) {
    native.property_sections.forEach((sec) => {
      if (sec && sec !== 'properties' && Object.hasOwn(SECTION_TITLE_MSGIDS, sec) && !sections.includes(sec)) {
        sections.push(sec);
      }
    });
  } else {
    INFERRED_SECTION_KEYS.forEach(([sec, keys]) => {
      if (keys.some((k) => Object.hasOwn(native, k) && native[k] !== null && native[k] !== undefined)) {
        if (!sections.includes(sec)) sections.push(sec);
      }
    });
  }
  if (
    isObjectPermissionsSupported(nodeData) &&
    !sections.some((sec) => PRIVILEGE_SECTION_ALIASES.has(sec))
  ) {
    sections.push('privileges');
  }
  if (Array.isArray(descriptor?.operations) && descriptor.operations.length > 0 && !sections.includes('operations')) {
    sections.push('operations');
  }
  return sections;
}

function resolveSectionContent(section, resource, descriptor) {
  const native = providerNative(resource);
  switch (section) {
  case 'columns':
    return native.columns ?? [];
  case 'constraints':
    return native.constraints ?? [];
  case 'indexes':
    return native.indexes ?? [];
  case 'triggers':
    return native.triggers ?? [];
  case 'parameters':
    return native.parameters ?? [];
  case 'definition':
    return native.definition ?? native.metadata_source ?? null;
  case 'ddl':
    return native.ddl ?? null;
  case 'privileges':
    return native.package_privileges
      ? {object_privileges: native.privileges ?? [], package_privileges: native.package_privileges}
      : native.privileges ?? [];
  case 'security':
  case 'grants':
    return native.security ?? native.privileges ?? native.grants ?? native.acls ?? [];
  case 'dependencies':
    return native.dependencies ?? [];
  case 'dependents':
    return native.dependents ?? [];
  case 'files':
    return native.files ?? [];
  case 'statistics':
    return native.statistics ?? native.stats ?? native.metrics ?? {};
  case 'state':
    return native.state ?? native.status ?? native.health ?? {};
  case 'comments':
    return native.description ?? native.comments ?? null;
  case 'calculations':
    return native.computed_source ?? native.computed_expression ?? null;
  case 'operations':
    return (descriptor?.operations || []).map((item) => ({
      operation_id: item.operation_id,
      title: item.title,
      available: Boolean(item.execution_available),
      blockers: (item.blockers || []).join(', '),
    }));
  default:
    return {};
  }
}

function AutoPlacingFieldGrid({fields, qaKey = 'auto-placing-properties-grid'}) {
  if (!fields.length) {
    return (
      <Box sx={{color: 'text.secondary', fontSize: '0.8125rem'}}>
        {gettext('None')}
      </Box>
    );
  }
  return (
    <Box
      role="group"
      data-cdeadmin-qa-key={qaKey}
      aria-label={gettext('Object properties')}
      sx={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
        columnGap: 2,
        rowGap: 1.5,
        alignItems: 'start',
        minWidth: 0,
      }}
    >
      {fields.map(({key, label, value}) => {
        const {text, muted} = formatScalarValue(value);
        const isWide = typeof text === 'string' && (text.length > 72 || text.includes('\n'));
        const isCodeBlock = typeof value === 'string' && value.includes('\n');
        return (
          <Box
            key={key}
            data-cdeadmin-qa-key={`property-field-${key}`}
            sx={{
              display: 'flex',
              flexDirection: 'column',
              gap: 0.4,
              minWidth: 0,
              gridColumn: isWide ? '1 / -1' : undefined,
            }}
          >
            <Box
              sx={{
                fontSize: '0.75rem',
                fontWeight: 600,
                color: 'text.secondary',
                lineHeight: 1.25,
              }}
            >
              {label}
            </Box>
            <Box
              component={isCodeBlock ? 'pre' : 'div'}
              sx={{
                m: 0,
                px: 1.25,
                py: 0.65,
                borderRadius: 1,
                border: '1px solid',
                borderColor: 'divider',
                bgcolor: 'background.paper',
                color: muted ? 'text.secondary' : 'text.primary',
                fontSize: '0.8125rem',
                fontFamily: isCodeBlock ? 'monospace' : 'inherit',
                minHeight: '2rem',
                display: isCodeBlock ? 'block' : 'flex',
                alignItems: isCodeBlock ? undefined : 'center',
                whiteSpace: isCodeBlock ? 'pre-wrap' : 'normal',
                overflowWrap: 'anywhere',
              }}
            >
              {text}
            </Box>
          </Box>
        );
      })}
    </Box>
  );
}

AutoPlacingFieldGrid.propTypes = {
  fields: PropTypes.arrayOf(
    PropTypes.shape({
      key: PropTypes.string.isRequired,
      label: PropTypes.string.isRequired,
      value: PropTypes.any,
    })
  ).isRequired,
  qaKey: PropTypes.string,
};

function StructuredRowsTable({rows, label}) {
  const columns = [];
  rows.forEach((row) =>
    Object.keys(row).forEach((k) => {
      if (!columns.includes(k)) columns.push(k);
    })
  );
  if (!columns.length) {
    return (
      <Box sx={{color: 'text.secondary', fontSize: '0.8125rem'}}>
        {gettext('None')}
      </Box>
    );
  }
  const cellSx = {
    px: 1.25,
    py: 0.65,
    fontSize: '0.8125rem',
    overflowWrap: 'anywhere',
    borderRight: '1px solid',
    borderBottom: '1px solid',
    borderColor: 'divider',
  };
  return (
    <Box sx={{overflowX: 'auto'}}>
      <Box
        role="table"
        aria-label={label}
        sx={{
          display: 'grid',
          minWidth: 'max-content',
          gridTemplateColumns: `repeat(${columns.length}, minmax(110px, 1fr))`,
          borderTop: '1px solid',
          borderLeft: '1px solid',
          borderColor: 'divider',
          borderRadius: 1,
          bgcolor: 'background.paper',
        }}
      >
        {columns.map((col) => (
          <Box
            key={col}
            role="columnheader"
            sx={{
              ...cellSx,
              fontSize: '0.75rem',
              fontWeight: 700,
              color: 'text.secondary',
              bgcolor: 'action.hover',
            }}
          >
            {humanizeFieldLabel(col)}
          </Box>
        ))}
        {rows.map((row, rowIdx) =>
          columns.map((col) => {
            const raw = row[col];
            const rendered =
              isScalarValue(raw) || isScalarList(raw)
                ? formatScalarValue(raw)
                : {text: JSON.stringify(raw), muted: false};
            return (
              <Box
                key={`${rowIdx}:${col}`}
                role="cell"
                sx={{
                  ...cellSx,
                  color: rendered.muted ? 'text.secondary' : 'text.primary',
                }}
              >
                {rendered.text}
              </Box>
            );
          })
        )}
      </Box>
    </Box>
  );
}

StructuredRowsTable.propTypes = {
  rows: PropTypes.arrayOf(PropTypes.object).isRequired,
  label: PropTypes.string,
};

function SectionPayloadRenderer({payload, label}) {
  if (payload === null || payload === undefined || payload === '') {
    return (
      <Box sx={{color: 'text.secondary', fontSize: '0.8125rem'}}>
        {gettext('None')}
      </Box>
    );
  }
  if (typeof payload === 'string' || typeof payload === 'number' || typeof payload === 'boolean') {
    return (
      <AutoPlacingFieldGrid
        fields={[{key: 'value', label, value: payload}]}
        qaKey="auto-placing-section-grid"
      />
    );
  }
  if (Array.isArray(payload)) {
    if (payload.length === 0) {
      return (
        <Box sx={{color: 'text.secondary', fontSize: '0.8125rem'}}>
          {gettext('None')}
        </Box>
      );
    }
    if (isObjectRowList(payload)) {
      return <StructuredRowsTable rows={payload} label={label} />;
    }
    return (
      <AutoPlacingFieldGrid
        fields={[{key: 'items', label, value: payload}]}
        qaKey="auto-placing-section-grid"
      />
    );
  }
  if (typeof payload === 'object') {
    const entries = Object.entries(payload);
    const scalarFields = entries
      .filter(([, val]) => isScalarValue(val) || isScalarList(val))
      .map(([k, val]) => ({key: k, label: humanizeFieldLabel(k), value: val}));
    const nestedEntries = entries.filter(([, val]) => !(isScalarValue(val) || isScalarList(val)));
    return (
      <Box sx={{display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0}}>
        {scalarFields.length > 0 && (
          <AutoPlacingFieldGrid fields={scalarFields} qaKey="auto-placing-section-grid" />
        )}
        {nestedEntries.map(([k, val]) => (
          <Box key={k} component="section" aria-label={humanizeFieldLabel(k)} sx={{minWidth: 0}}>
            <Box
              component="h4"
              sx={{
                m: 0,
                mb: 1,
                pb: 0.5,
                fontSize: '0.73rem',
                fontWeight: 700,
                letterSpacing: '0.03em',
                textTransform: 'uppercase',
                color: 'text.secondary',
                borderBottom: '1px solid',
                borderColor: 'divider',
              }}
            >
              {humanizeFieldLabel(k)}
            </Box>
            <SectionPayloadRenderer payload={val} label={humanizeFieldLabel(k)} />
          </Box>
        ))}
      </Box>
    );
  }
  return null;
}

SectionPayloadRenderer.propTypes = {
  payload: PropTypes.any,
  label: PropTypes.string,
};

function isCredentialRequiredError(error) {
  const status = error?.response?.status ?? error?.status;
  const data = error?.response?.data;
  const code =
    error?.code ||
    data?.code ||
    data?.data?.code ||
    data?.result?.code ||
    data?.error?.code;
  if (code === 'CREDENTIAL_REQUIRED') return true;
  if (
    status === 401 &&
    /credential|verify|password/i.test(String(data?.errormsg || error?.message || ''))
  ) {
    return true;
  }
  return false;
}

function findSelectedServerItem() {
  const tree = pgAdmin?.Browser?.tree;
  let current = tree?.selected?.();
  while (current) {
    const data = tree?.itemData?.(current);
    if (data?._type === 'server') return current;
    current = tree?.hasParent?.(current) ? tree.parent(current) : null;
  }
  return null;
}

/** Resolve by endpoint/target/resource identity; render an auto-placing responsive field grid. */
export default function ProviderObjectProperties({nodeData}) {
  const instanceScope = useProjectInstanceScope();
  const [state, setState] = useState({loading: true});
  const [reloadNonce, setReloadNonce] = useState(0);
  const [localeRev, setLocaleRev] = useState(0);
  const url = nodeData.cde_workspace_url;
  const identity = nodeData.cde_resource_id;
  const targetId = nodeData.cde_database_target_id;
  const resourceKind = nodeData.cde_resource_kind;

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const onLanguageChanged = () => setLocaleRev((n) => n + 1);
    window.addEventListener('scratchrobin:language-changed', onLanguageChanged);
    return () => window.removeEventListener('scratchrobin:language-changed', onLanguageChanged);
  }, []);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const api = getApiInstance();
    setState({loading: true});

    const loadProperties = async (allowPrompt = true) => {
      try {
        const {data} = await api.get(url, {signal: controller.signal});
        const workspace = data?.data || {};
        const response = await api.post(
          url,
          {
            action: 'resource_inspect',
            request: {
              resource_id: identity,
              generation: workspace.resource_page?.generation,
              ...(targetId ? {database_target_id: targetId} : {}),
            },
          },
          {signal: controller.signal}
        );
        if (active) {
          setState({
            resource: response.data?.data,
            descriptor: workspace.visual_admin?.objects?.find(
              (item) => item.resource_kind === resourceKind
            ),
          });
        }
      } catch (error) {
        if (!active || controller.signal.aborted) return;
        if (allowPrompt && isCredentialRequiredError(error)) {
          const serverItem = findSelectedServerItem();
          if (serverItem) {
            const verified = await promptEndpointVerification(serverItem, targetId);
            if (active && verified) {
              return loadProperties(false);
            }
          }
        }
        if (active) {
          setState({
            error: error?.response?.data?.errormsg || error?.message || gettext('Failed to load object properties.'),
          });
        }
      }
    };

    void loadProperties(true);
    return () => {
      active = false;
      controller.abort();
    };
  }, [url, identity, resourceKind, targetId, reloadNonce]);

  const sections = useMemo(
    () => (state.resource ? computeSections(state.resource, state.descriptor, nodeData) : ['properties']),
    [nodeData, state.resource, state.descriptor]
  );
  const [section, setSection] = useState(() => resolveRequestedSection(nodeData.cde_section, ['properties']));

  useEffect(() => {
    setSection(resolveRequestedSection(nodeData.cde_section, sections));
  }, [nodeData.cde_section, identity, sections]);

  useEffect(() => {
    if (!sections.includes(section)) {
      setSection(resolveRequestedSection(section, sections));
    }
  }, [section, sections]);

  const hostedOnTabbedIconBar = Boolean(instanceScope);

  useEffect(() => {
    if (!hostedOnTabbedIconBar || !instanceScope || !state.resource) return undefined;
    const items = sections.map((sec) => {
      const label = getSectionTitle(sec);
      return {
        id: sec,
        label,
        hint: label,
        icon: resolveSectionIconKey(sec, label),
        checked: sec === section,
      };
    });
    instanceScope.setSubsections({
      items,
      onSelect: (nextSec) => setSection(nextSec),
    });
  }, [hostedOnTabbedIconBar, instanceScope, localeRev, section, sections, state.resource]);

  useEffect(() => {
    if (!hostedOnTabbedIconBar || !instanceScope) return undefined;
    return () => instanceScope.setSubsections(null);
  }, [hostedOnTabbedIconBar, instanceScope]);

  const handleRefresh = useCallback(() => {
    setReloadNonce((n) => n + 1);
  }, []);

  if (state.loading) {
    return <CircularProgress aria-label={gettext('Loading object properties')} />;
  }
  if (state.error) {
    return <Alert severity="error">{state.error}</Alert>;
  }

  const resource = state.resource;
  if (!resource) return null;

  const native = providerNative(resource);
  const summaryFields = [];
  const complexNativeEntries = [];

  if (resource.display_name !== undefined) {
    summaryFields.push({key: 'name', label: gettext('Name'), value: resource.display_name});
  }
  const kindValue = resource.resource_kind ?? resourceKind;
  if (kindValue !== undefined) {
    summaryFields.push({key: 'kind', label: gettext('Kind'), value: kindValue});
  }
  if (resource.display_path !== undefined) {
    summaryFields.push({key: 'display_path', label: gettext('Display path'), value: resource.display_path});
  }

  Object.entries(native).forEach(([k, val]) => {
    if (SECTION_EXCLUDED_NATIVE_KEYS.has(k)) return;
    if (isScalarValue(val) || isScalarList(val)) {
      if (summaryFields.some((f) => f.key === k)) return;
      summaryFields.push({key: k, label: humanizeFieldLabel(k), value: val});
    } else {
      complexNativeEntries.push([k, val]);
    }
  });

  const kindTitle = state.descriptor?.title
    ? gettext(state.descriptor.title)
    : humanizeFieldLabel(kindValue || '');

  return (
    <Box
      data-contained-scroll="false"
      data-cdeadmin-qa-key={`provider-object-properties-${identity}`}
      sx={{height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column'}}
    >
      <Box
        sx={{
          px: 3,
          py: 0.75,
          borderBottom: '1px solid',
          borderColor: 'divider',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 1.5,
          flexWrap: 'wrap',
        }}
      >
        <Box sx={{fontSize: '0.85rem', color: 'text.secondary', display: 'flex', alignItems: 'center', gap: 1}}>
          <Box component="strong" sx={{color: 'text.primary'}}>
            {resource.display_name || identity}
          </Box>
          {kindTitle ? ` · ${kindTitle}` : ''}
          <Button size="small" onClick={handleRefresh}>
            {gettext('Refresh')}
          </Button>
        </Box>
        <FormReference formKey="inspector" />
      </Box>

      {Array.isArray(native.catalog_warnings) &&
        native.catalog_warnings
          .filter((msg) => typeof msg === 'string' && msg.trim())
          .map((msg, idx) => (
            <Alert key={idx} severity="warning" sx={{mx: 2.5, mt: 1}}>
              {msg}
            </Alert>
          ))}

      {native.catalog_coverage?.state === 'partial' && (
        <Alert severity="warning" sx={{mx: 2.5, mt: 1}}>
          {gettext(
            'Catalog visibility is incomplete. Missing objects may reflect denied access or failed catalog queries, not an empty database.'
          )}
        </Alert>
      )}

      {!hostedOnTabbedIconBar && sections.length > 1 && (
        <Tabs
          value={section}
          variant="scrollable"
          scrollButtons="auto"
          aria-label={gettext('Object properties sections')}
          onChange={(_e, nextSec) => setSection(nextSec)}
          sx={{px: 2, borderBottom: '1px solid', borderColor: 'divider', minHeight: 36}}
        >
          {sections.map((sec) => (
            <Tab key={sec} value={sec} label={getSectionTitle(sec)} sx={{minHeight: 36, py: 0.5}} />
          ))}
        </Tabs>
      )}

      <Box
        role="tabpanel"
        aria-label={`${getSectionTitle(section)} ${gettext('section')}`}
        sx={{p: 2.5, overflowY: 'auto', flex: 1, minHeight: 0}}
      >
        {section === 'properties' ? (
          <Box sx={{display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0}}>
            <AutoPlacingFieldGrid fields={summaryFields} qaKey="auto-placing-properties-grid" />
            {complexNativeEntries.map(([k, val]) => (
              <Box key={k} component="section" aria-label={humanizeFieldLabel(k)} sx={{minWidth: 0}}>
                <Box
                  component="h4"
                  sx={{
                    m: 0,
                    mb: 1,
                    pb: 0.5,
                    fontSize: '0.73rem',
                    fontWeight: 700,
                    letterSpacing: '0.03em',
                    textTransform: 'uppercase',
                    color: 'text.secondary',
                    borderBottom: '1px solid',
                    borderColor: 'divider',
                  }}
                >
                  {humanizeFieldLabel(k)}
                </Box>
                <SectionPayloadRenderer payload={val} label={humanizeFieldLabel(k)} />
              </Box>
            ))}
          </Box>
        ) : PRIVILEGE_SECTION_ALIASES.has(section) && isObjectPermissionsSupported(nodeData) ? (
          <ObjectPermissionsMatrix boundNodeData={nodeData} resource={resource} />
        ) : (
          <SectionPayloadRenderer
            payload={resolveSectionContent(section, resource, state.descriptor)}
            label={getSectionTitle(section)}
          />
        )}
      </Box>
    </Box>
  );
}

ProviderObjectProperties.propTypes = {nodeData: PropTypes.object.isRequired};
