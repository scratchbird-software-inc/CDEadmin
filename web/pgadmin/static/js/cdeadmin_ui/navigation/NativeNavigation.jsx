import {useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Menu, MenuItem, Typography} from '@mui/material';
import FormReference, {formReference} from './FormReference';
import MissingForm from './MissingForm';

function native(resource) {
  return resource?.native || Object.values(resource?.extensions || {}).find(v => v?.native)?.native || {};
}
function operationAllowed(resource, id) {
  const administration = native(resource).administration;
  if (administration == null) return true;
  if (typeof administration !== 'object' || Array.isArray(administration)) return false;
  const allowed = administration.allowed_operations;
  return allowed == null || (Array.isArray(allowed) && allowed.includes(id));
}
function childrenFor(node, resources, owner) {
  return resources.filter(r => {
    if (r.resource_kind !== node.kind) return false;
    if (!owner) return true;
    const parent = native(r).navigator_parent_resource_id;
    if (parent) return parent === owner.resource_id;
    const path = r.display_path || [];
    const prefix = owner.display_path || [];
    return prefix.length > 0 && path.length > prefix.length && prefix.every((part, i) => path[i] === part);
  });
}
export default function NativeNavigation({design, endpoint, catalog, resources, onOpen, onOperation, onRefresh}) {
  const [missing, setMissing] = useState(null);
  const [menu, setMenu] = useState(null);
  const descriptors = useMemo(() => Object.fromEntries((catalog?.objects || []).map(o => [o.resource_kind, o])), [catalog]);
  if (!design) return <Alert severity="info">No native navigation design is registered for this provider.</Alert>;
  const context = (node, resource, owner) => ({engine_id: design.engine_id, profile_id: design.profile_id,
    endpoint_id: endpoint?.endpoint_id, resource_id: resource?.resource_id || null,
    owner_resource_id: owner?.resource_id || null, native_kind: node.kind,
    definition_member: node.label, section: node.section,
    form_reference: node.form_reference, template_id: node.id});
  const open = (node, resource, owner) => {
    const target = resource || (node.section ? owner : null);
    if (target && descriptors[target.resource_kind]) {
      setMissing(null);onOpen(target, resource ? 'properties' : node.section || 'properties', resource?.display_name || node.label);return;
    }
    setMissing({reference: node.form_reference, title: node.label, context: context(node, resource, owner)});
  };
  const render = (node, owner=null, depth=0, scope=null) => {
    const objectScope = /User objects/i.test(node.label) ? 'user' : node.kind === 'system-catalog' ? 'system' : scope;
    // Conditional branches require observed objects; a condition string is not a capability grant.
    const matches = childrenFor(node, resources, owner).filter(r => objectScope === 'system' ? native(r).system_object === true : objectScope === 'user' ? native(r).system_object !== true : true);
    if (node.condition && !matches.length) return null;
    const instances = node.label.startsWith('<') && matches.length ? matches : [null];
    return instances.map(resource => {
      const actual = resource;
      const key = node.id + ':' + (actual?.resource_id || owner?.resource_id || 'template');
      const label = node.kind === 'endpoint' ? endpoint?.display_name || node.label : actual?.display_name || node.label;
      return <li key={key}>
        <Button size="small" sx={{textTransform: 'none', textAlign: 'left'}}
          data-navigation-template={node.id} data-form-reference={node.form_reference}
          onClick={() => open(node, actual, owner)}
          onContextMenu={event => {event.preventDefault();setMenu({node, resource: actual, owner, x: event.clientX, y: event.clientY});}}>
          {label}{!actual && node.label.startsWith('<') ? ' — no discovered instance' : ''}
        </Button>
        {node.children.length > 0 && <ul style={{paddingLeft: 20}}>{node.children.map(c => render(c, actual || owner, depth + 1, objectScope))}</ul>}
      </li>;
    });
  };
  const action = (callback) => {callback();setMenu(null);};
  return <FormReference formKey="navigation">
    <Typography variant="h6">Native navigation</Typography>
    <Alert severity="info">Unbound entries open numbered form placeholders, never fabricated database objects. Conditional branches require provider observations. Refresh or load more resources to discover additional objects.</Alert>
    <Button onClick={onRefresh}>Refresh native objects</Button>
    <Box sx={{display: 'grid', gridTemplateColumns: 'minmax(240px, 1fr) minmax(240px, 1fr)', gap: 2}}>
      <Box component="ul" sx={{listStyle: 'none', pl: 0, maxHeight: '65vh', overflow: 'auto'}}>{render(design.root)}</Box>
      {missing && <MissingForm {...missing} />}
    </Box>
    <Menu open={Boolean(menu)} onClose={() => setMenu(null)} anchorReference="anchorPosition"
      anchorPosition={menu ? {left: menu.x, top: menu.y} : undefined}>
      <MenuItem onClick={() => action(() => open(menu.node, menu.resource, menu.owner))}>Information / form</MenuItem>
      {menu?.resource && (descriptors[menu.resource.resource_kind]?.operations || []).filter(op => op.native_supported !== false && operationAllowed(menu.resource, op.operation_id) && op.operation_id !== 'inspect' && op.operation_id !== 'create').map(op =>
        <MenuItem key={op.operation_id} disabled={op.execution_available !== true}
          onClick={() => action(() => onOperation(menu.resource, op.operation_id))}>{op.title}</MenuItem>)}
      {menu?.owner && menu.node.section && <MenuItem onClick={() => action(() => onOpen(menu.owner, menu.node.section, menu.node.label))}>Open owner → {menu.node.section}</MenuItem>}
      {menu && ['schema', 'database', 'endpoint', 'folder'].includes(menu.node.kind) && <MenuItem onClick={() => action(() => setMissing({reference: formReference('scoped-creation'), title: 'Scoped creation', context: {...context(menu.node, menu.resource, menu.owner), required: 'Select an admitted native child form and bind its parent before creation.'}}))}>Create native child…</MenuItem>}
      <MenuItem onClick={() => action(() => setMissing({reference: formReference('metadata-extraction'), title: 'Metadata extraction', context: {...context(menu.node, menu.resource, menu.owner), scope: 'selected-object', implementation: 'pending'}}))}>Extract metadata — selected object…</MenuItem>
      {menu?.node.children.length > 0 && <MenuItem onClick={() => action(() => setMissing({reference: formReference('metadata-extraction'), title: 'Metadata extraction', context: {...context(menu.node, menu.resource, menu.owner), scope: 'branch', implementation: 'pending'}}))}>Extract metadata — full branch…</MenuItem>}
    </Menu>
  </FormReference>;
}
NativeNavigation.propTypes = {design: PropTypes.object, endpoint: PropTypes.object, catalog: PropTypes.object,
  resources: PropTypes.array.isRequired, onOpen: PropTypes.func.isRequired, onOperation: PropTypes.func.isRequired, onRefresh: PropTypes.func.isRequired};
