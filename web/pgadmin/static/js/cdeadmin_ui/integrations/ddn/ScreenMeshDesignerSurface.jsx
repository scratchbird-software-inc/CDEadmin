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
import {Box, ScrollArea, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {Checkbox, Select} from '../../primitives/Choice';
import {NumberField, TextField} from '../../primitives/Field';
import {Dialog} from '../../overlays/Dialog';
import {Banner} from '../../feedback/Indicators';
import {EmptyState} from '../../feedback/EmptyState';
import {ProgressOverlay} from '../../feedback/ProgressOverlay';
import {StatusBadge} from '../../status/StatusBadge';
import FormReference from '../../navigation/FormReference';
import CodeEditor from '../../editors/CodeEditor';
import {DDNViewerSurface} from './DDNViewerSurface';
import {
  DesignCheckpointHistoryDrawer,
  DesignerModalTabs,
  DesignerTabbedMenu,
  FormGrid,
  TypedRowsEditor,
  WhereUsedDialog,
} from './DesignerChrome';
import {
  DesignStoreClient,
  SharedDDNTaskController,
} from './sharedDesignLibrary';

export const SCREEN_MESH_CONTROL_ROLE_OPTIONS = Object.freeze([
  {value: 'ui.input', label: 'Text Input (ui.input)'},
  {value: 'ui.button', label: 'Button (ui.button)'},
  {value: 'ui.checkbox', label: 'Checkbox (ui.checkbox)'},
  {value: 'ui.grid', label: 'Data Grid (ui.grid)'},
  {value: 'ui.dropdown', label: 'Dropdown Select (ui.dropdown)'},
  {value: 'ui.radio', label: 'Radio Choice (ui.radio)'},
  {value: 'ui.tabs', label: 'Tab Bar (ui.tabs)'},
  {value: 'ui.list', label: 'List Box (ui.list)'},
  {value: 'ui.label', label: 'Label (ui.label)'},
  {value: 'ui.image', label: 'Image Placeholder (ui.image)'},
]);

export const SCREEN_MESH_REGION_HINT_OPTIONS = Object.freeze([
  {value: '', label: 'Auto-infer from label & binding'},
  {value: 'ui.input', label: 'Input (ui.input)'},
  {value: 'ui.button', label: 'Button (ui.button)'},
  {value: 'ui.checkbox', label: 'Checkbox (ui.checkbox)'},
  {value: 'ui.grid', label: 'Grid (ui.grid)'},
  {value: 'ui.dropdown', label: 'Dropdown (ui.dropdown)'},
  {value: 'ui.radio', label: 'Radio (ui.radio)'},
  {value: 'ui.tabs', label: 'Tabs (ui.tabs)'},
]);

export const SCREEN_MESH_BINDING_KIND_OPTIONS = Object.freeze([
  {value: 'column', label: 'Catalog Column'},
  {value: 'table', label: 'Catalog Table / View'},
  {value: 'question', label: 'BI Question'},
  {value: 'dashboard', label: 'BI Dashboard'},
  {value: 'cube', label: 'Semantic Cube / Measure'},
  {value: 'sql_query', label: 'Named SQL Query'},
  {value: 'diagram', label: 'Diagram Element'},
  {value: 'screen', label: 'Screen Reference'},
]);

export const SCREEN_MESH_ACCESS_OPTIONS = Object.freeze([
  {value: 'read', label: 'Read-only display (read)'},
  {value: 'write', label: 'Input write target (write)'},
  {value: 'read_write', label: 'Read & write (read_write)'},
]);

export const SCREEN_MESH_TRIGGER_OPTIONS = Object.freeze([
  {value: 'click', label: 'Click'},
  {value: 'hover', label: 'Hover'},
  {value: 'delay', label: 'Timed delay'},
]);

export const SCREEN_MESH_ACTION_OPTIONS = Object.freeze([
  {value: 'navigate', label: 'Navigate to screen'},
  {value: 'overlay', label: 'Open modal / overlay screen'},
  {value: 'back', label: 'Navigate back'},
  {value: 'url', label: 'External reference URL'},
]);

// Deterministic valid PNG data URLs for 1-click synthetic sample testing (zero raw Base64 paste)
export const SAMPLE_FORM_PNG_DATA_URL =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAMCAYAAABr5z2BAAAAFElEQVR42mP4//8/AyUYtfBoGAAANBYM8f0t8rAAAAAElFTkSuQmCC';

export const SAMPLE_UPDATED_PNG_DATA_URL =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAMCAYAAABr5z2BAAAAFklEQVR42mNk+M9QzwAEjDAGNzYAAIoaB/H47w6nAAAAAElFTkSuQmCC';

function badgeStatus(status) {
  if (status === 'accepted') return 'success';
  if (status === 'in_review') return 'warning';
  if (status === 'in_progress') return 'information';
  return 'neutral';
}

function bindingBadgeStatus(state) {
  if (state === 'valid') return 'success';
  if (state === 'suspect') return 'warning';
  if (state === 'unbound') return 'neutral';
  return 'information';
}

function resolveMeshView(workspace, requestedView) {
  if (!workspace?.files) return workspace?.view || 'screen_mesh_main';
  const entryText = workspace.files[workspace.entry] || '';
  if (
    requestedView &&
    (entryText.includes(`view "${requestedView}"`) ||
      entryText.includes(`view ${requestedView}`))
  ) {
    return requestedView;
  }
  return workspace.view || 'screen_mesh_main';
}

function applyHanddrawnToDdnText(ddnText, handdrawn) {
  if (!ddnText) return ddnText;
  const cleaned = ddnText.replace(/^\s+look\s+"handdrawn"\s*\n/gm, '');
  if (!handdrawn) return cleaned;
  return cleaned.replace(
    /^(view\s+"[^"]+"\s+as\s+"wireframe\.ui@1"\s*\n\s+with\s*\n(?:\s+id\s+"[^"]+"\s*\n)?(?:\s+title\s+"[^"]+"\s*\n)?)/gm,
    '$1        look "handdrawn"\n'
  );
}

function triggerBrowserDownload(filename, content, mimeType = 'text/plain') {
  if (typeof document === 'undefined') return;
  try {
    const blob = new Blob([String(content || '')], {type: mimeType});
    const url =
      typeof URL !== 'undefined' && typeof URL.createObjectURL === 'function'
        ? URL.createObjectURL(blob)
        : null;
    if (!url) return;
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    if (typeof URL.revokeObjectURL === 'function') {
      URL.revokeObjectURL(url);
    }
  } catch {
    // Safe no-op in headless test environments without Blob URL support.
  }
}

function buildFallbackFieldSpec(designId, title, version, mesh) {
  if (!mesh) {
    return {
      design_id: designId,
      title: title || 'Screen Mesh',
      version: version || 1,
      summary: {
        total_fields: 0,
        bound_fields: 0,
        suspect_fields: 0,
        unbound_fields: 0,
      },
      rows: [],
      markdown: '',
      csv: '',
      html: '',
    };
  }
  const screensById = Object.fromEntries(
    (mesh.screens || []).map((s) => [s.id, s])
  );
  const bindings = mesh.bindings || [];
  const rows = [];

  for (const scr of mesh.screens || []) {
    for (const ctrl of (mesh.controls || []).filter(
      (c) => c.screen_id === scr.id
    )) {
      const ctrlBnds = bindings.filter(
        (b) => b.source_id === ctrl.id && !b.column_id
      );
      if (ctrlBnds.length > 0) {
        for (const b of ctrlBnds) {
          rows.push({
            screen_title: scr.name,
            element_id: ctrl.id,
            element_kind: ctrl.role,
            label: ctrl.name,
            access_mode:
              b.access_mode === 'read' ? 'read_only' : 'read_write',
            target_ref: b.target_ref,
            catalog_type: b.target_kind === 'table' ? 'TABLE' : '—',
            nullable: null,
            default_value: null,
            binding_state: b.state || 'unknown',
            notes: '',
          });
        }
      } else {
        rows.push({
          screen_title: scr.name,
          element_id: ctrl.id,
          element_kind: ctrl.role,
          label: ctrl.name,
          access_mode: ctrl.role === 'ui.button' ? 'trigger' : 'read_write',
          target_ref: '',
          catalog_type: '',
          nullable: null,
          default_value: null,
          binding_state: 'unbound',
          notes: '',
        });
      }

      if (ctrl.role === 'ui.grid') {
        for (const col of ctrl.columns || []) {
          const cb = bindings.find(
            (b) => b.source_id === ctrl.id && b.column_id === col.id
          );
          rows.push({
            screen_title: scr.name,
            element_id: `${ctrl.id}:${col.id}`,
            element_kind: 'ui.grid.column',
            label: `${ctrl.name}.${col.name}`,
            access_mode:
              cb?.access_mode === 'write' || cb?.access_mode === 'read_write'
                ? 'read_write'
                : 'read_only',
            target_ref: cb?.target_ref || '',
            catalog_type: col.datatype || '',
            nullable: null,
            default_value: null,
            binding_state: cb ? cb.state || 'unknown' : 'unbound',
            notes: '',
          });
        }
      }
    }

    for (const reg of (mesh.regions || []).filter(
      (r) => r.screen_id === scr.id
    )) {
      const rb = bindings.find((b) => b.source_id === reg.id);
      rows.push({
        screen_title: scr.name,
        element_id: reg.id,
        element_kind: 'ui.region',
        label: reg.name,
        access_mode: rb?.access_mode === 'read' ? 'read_only' : 'read_write',
        target_ref: rb?.target_ref || '',
        catalog_type: '',
        nullable: null,
        default_value: null,
        binding_state: rb ? rb.state || 'unknown' : 'unbound',
        notes: `bounds=(${reg.bounds?.x ?? 0}, ${reg.bounds?.y ?? 0}, ${reg.bounds?.width ?? 0}x${reg.bounds?.height ?? 0})`,
      });
    }

    for (const nav of mesh.navigations || []) {
      const fromCtrl = (mesh.controls || []).find((c) => c.id === nav.from_id);
      const fromReg = (mesh.regions || []).find((r) => r.id === nav.from_id);
      const ownerSid =
        fromCtrl?.screen_id ||
        fromReg?.screen_id ||
        (nav.from_id === scr.id ? scr.id : '');
      if (ownerSid !== scr.id) continue;
      const destScr = screensById[nav.to_screen_id];
      rows.push({
        screen_title: scr.name,
        element_id: nav.id,
        element_kind: 'navigation',
        label: nav.label,
        access_mode: 'trigger',
        target_ref: destScr ? `screen:${destScr.name}` : nav.to_screen_id,
        catalog_type: `${nav.trigger} -> ${nav.action}`,
        nullable: null,
        default_value: null,
        binding_state: destScr ? 'valid' : 'suspect',
        notes: '',
      });
    }
  }

  const boundCount = rows.filter((r) => r.binding_state !== 'unbound').length;
  const suspectCount = rows.filter((r) => r.binding_state === 'suspect').length;
  const summary = {
    total_fields: rows.length,
    bound_fields: boundCount,
    suspect_fields: suspectCount,
    unbound_fields: rows.length - boundCount,
  };
  const mdLines = [
    `# ${title || mesh.name} (v${version || 1}) — Field Specification`,
    '',
    '| Screen | Control / Column / Region | Kind | Target | Type | Nullable | Validity |',
    '| --- | --- | --- | --- | --- | --- | --- |',
    ...rows.map(
      (r) =>
        `| ${r.screen_title} | ${r.label} | ${r.element_kind} | ${r.target_ref || '—'} | ${r.catalog_type || '—'} | ${r.nullable === null ? '—' : r.nullable ? 'YES' : 'NO'} | ${r.binding_state} |`
    ),
  ];
  const csvLines = [
    'screen_title,label,element_kind,access_mode,target_ref,catalog_type,nullable,binding_state',
    ...rows.map((r) =>
      [
        r.screen_title,
        r.label,
        r.element_kind,
        r.access_mode,
        r.target_ref,
        r.catalog_type,
        r.nullable === null ? '' : r.nullable ? 'YES' : 'NO',
        r.binding_state,
      ]
        .map((cell) => `"${String(cell ?? '').replace(/"/g, '""')}"`)
        .join(',')
    ),
  ];
  const htmlDoc = [
    '<!doctype html><html><body>',
    `<h1>${title || mesh.name} — Field Specification</h1>`,
    '<table><thead><tr><th>Screen</th><th>Label</th><th>Kind</th><th>Target</th><th>Type</th><th>Validity</th></tr></thead><tbody>',
    ...rows.map(
      (r) =>
        `<tr><td>${r.screen_title}</td><td>${r.label}</td><td>${r.element_kind}</td><td>${r.target_ref || '—'}</td><td>${r.catalog_type || '—'}</td><td>${r.binding_state}</td></tr>`
    ),
    '</tbody></table></body></html>',
  ].join('\n');

  return {
    design_id: designId,
    title: title || mesh.name,
    version: version || 1,
    summary,
    rows,
    markdown: mdLines.join('\n'),
    csv: csvLines.join('\n'),
    html: htmlDoc,
  };
}

/**
 * Interactive pointer rubber-band rectangle overlay over a screenshot image.
 * Supports drawing both ui.region hotspots and destructive redaction rectangles
 * while staying bidirectionally synced with TypedRowsEditor.
 */
function ScreenshotRubberBandCanvas({
  label = 'Interactive screenshot region canvas',
  imageSrc = '',
  screenWidth = 960,
  screenHeight = 640,
  boxes = [],
  boxTone = 'region',
  onDrawBox,
}) {
  const surfaceRef = useRef(null);
  const [dragState, setDragState] = useState(null);

  const logicalPoint = (event) => {
    const el = surfaceRef.current;
    const rect = el ? el.getBoundingClientRect() : {left: 0, top: 0, width: 0, height: 0};
    const scaleX = rect.width > 0 ? screenWidth / rect.width : 1;
    const scaleY = rect.height > 0 ? screenHeight / rect.height : 1;
    const rawX = (event.clientX - rect.left) * scaleX;
    const rawY = (event.clientY - rect.top) * scaleY;
    return {
      x: Math.round(Math.max(0, Math.min(screenWidth, rawX))),
      y: Math.round(Math.max(0, Math.min(screenHeight, rawY))),
    };
  };

  const handleMouseDown = (event) => {
    if (event.button !== undefined && event.button !== 0) return;
    const pt = logicalPoint(event);
    setDragState({startX: pt.x, startY: pt.y, curX: pt.x, curY: pt.y});
  };

  const handleMouseMove = (event) => {
    if (!dragState) return;
    const pt = logicalPoint(event);
    setDragState((cur) => (cur ? {...cur, curX: pt.x, curY: pt.y} : null));
  };

  const finishDrag = (event) => {
    if (!dragState) return;
    const pt = event ? logicalPoint(event) : {x: dragState.curX, y: dragState.curY};
    const x = Math.min(dragState.startX, pt.x);
    const y = Math.min(dragState.startY, pt.y);
    const width = Math.max(8, Math.abs(pt.x - dragState.startX));
    const height = Math.max(8, Math.abs(pt.y - dragState.startY));
    setDragState(null);
    onDrawBox?.({x, y, width, height});
  };

  const liveRect = dragState
    ? {
      x: Math.min(dragState.startX, dragState.curX),
      y: Math.min(dragState.startY, dragState.curY),
      width: Math.max(4, Math.abs(dragState.curX - dragState.startX)),
      height: Math.max(4, Math.abs(dragState.curY - dragState.startY)),
    }
    : null;

  const pct = (val, total) => `${Math.max(0, Math.min(100, (val / Math.max(1, total)) * 100))}%`;
  const borderPalette =
    boxTone === 'redact' ? 'error.main' : 'primary.main';

  return (
    <Box sx={{display: 'flex', flexDirection: 'column', gap: 0.5}}>
      <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
        Drag across the screenshot canvas ({screenWidth}×{screenHeight}px) to draw a{' '}
        {boxTone === 'redact' ? 'redaction rectangle' : 'ui.region hotspot'}.
      </Box>
      <Box
        ref={surfaceRef}
        role="application"
        aria-label={label}
        data-testid="screenshot-rubberband-surface"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={finishDrag}
        sx={{
          position: 'relative',
          width: '100%',
          maxWidth: 640,
          aspectRatio: `${Math.max(1, screenWidth)} / ${Math.max(1, screenHeight)}`,
          minHeight: 180,
          border: '1px solid',
          borderColor: 'divider',
          bgcolor: 'background.default',
          cursor: 'crosshair',
          userSelect: 'none',
          overflow: 'hidden',
        }}
      >
        {imageSrc ? (
          <Box
            component="img"
            src={imageSrc}
            alt="Screen Mesh screenshot preview"
            draggable={false}
            sx={{
              width: '100%',
              height: '100%',
              objectFit: 'fill',
              display: 'block',
              pointerEvents: 'none',
            }}
          />
        ) : (
          <Box
            sx={{
              width: '100%',
              height: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '0.8125rem',
              color: 'text.secondary',
              pointerEvents: 'none',
            }}
          >
            Wireframe coordinate frame ({screenWidth}×{screenHeight}px) — drag to place bounds
          </Box>
        )}

        {boxes.map((b, idx) => (
          <Box
            key={b.id || idx}
            sx={{
              position: 'absolute',
              left: pct(Number(b.x) || 0, screenWidth),
              top: pct(Number(b.y) || 0, screenHeight),
              width: pct(Number(b.width) || 40, screenWidth),
              height: pct(Number(b.height) || 24, screenHeight),
              border: '2px solid',
              borderColor: borderPalette,
              bgcolor:
                boxTone === 'redact'
                  ? 'rgba(15, 23, 42, 0.55)'
                  : 'rgba(37, 99, 235, 0.16)',
              pointerEvents: 'none',
              boxSizing: 'border-box',
              px: 0.5,
              fontSize: '0.6875rem',
              fontWeight: 600,
              overflow: 'hidden',
              whiteSpace: 'nowrap',
              textOverflow: 'ellipsis',
            }}
          >
            {b.name || (boxTone === 'redact' ? `Redact #${idx + 1}` : `Region #${idx + 1}`)}
          </Box>
        ))}

        {liveRect && (
          <Box
            data-testid="rubberband-live-rect"
            sx={{
              position: 'absolute',
              left: pct(liveRect.x, screenWidth),
              top: pct(liveRect.y, screenHeight),
              width: pct(liveRect.width, screenWidth),
              height: pct(liveRect.height, screenHeight),
              border: '2px dashed',
              borderColor: borderPalette,
              bgcolor: 'rgba(37, 99, 235, 0.22)',
              pointerEvents: 'none',
              boxSizing: 'border-box',
            }}
          />
        )}
      </Box>
    </Box>
  );
}

ScreenshotRubberBandCanvas.propTypes = {
  label: PropTypes.string,
  imageSrc: PropTypes.string,
  screenWidth: PropTypes.number,
  screenHeight: PropTypes.number,
  boxes: PropTypes.array,
  boxTone: PropTypes.oneOf(['region', 'redact']),
  onDrawBox: PropTypes.func,
};

/**
 * File picker + drag-and-drop image loader with 1-click synthetic PNG sample button.
 * Eliminates raw Base64 paste textareas across upload and comparison modals.
 */
function ScreenshotFileDropzone({
  label = 'Screenshot image file',
  inputLabel = 'Choose screenshot image file',
  sampleLabel = 'Use Sample Form Screenshot',
  sampleDataUrl = SAMPLE_FORM_PNG_DATA_URL,
  fileName = '',
  dataUrl = '',
  onLoaded,
  onError,
}) {
  const fileRef = useRef(null);

  const readSelectedFile = (file) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || '');
      const inferredMime =
        file.type ||
        (result.startsWith('data:image/webp')
          ? 'image/webp'
          : result.startsWith('data:image/jpeg')
            ? 'image/jpeg'
            : 'image/png');
      onLoaded?.({
        dataUrl: result,
        mediaType: inferredMime,
        fileName: file.name || 'capture.png',
      });
    };
    reader.onerror = () => {
      onError?.(new Error('Failed to read selected image file.'));
    };
    reader.readAsDataURL(file);
  };

  return (
    <Box
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        const file = e.dataTransfer?.files?.[0];
        if (file) readSelectedFile(file);
      }}
      data-testid="screenshot-file-dropzone"
      sx={{
        border: '1px dashed',
        borderColor: 'divider',
        p: 1.5,
        display: 'flex',
        flexDirection: 'column',
        gap: 1,
        bgcolor: 'background.paper',
      }}
    >
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 1,
        }}
      >
        <Box sx={{fontSize: '0.8125rem'}}>
          <strong>{label}:</strong>{' '}
          {fileName
            ? `Loaded ${fileName}`
            : dataUrl
              ? 'Image ready for Screen Mesh capture'
              : 'Drag and drop a PNG, JPEG, or WebP screenshot here, or choose a file.'}
        </Box>
        <Stack direction="row" gap="compact">
          <input
            ref={fileRef}
            type="file"
            aria-label={inputLabel}
            accept="image/png,image/jpeg,image/webp"
            style={{display: 'none'}}
            onChange={(e) => readSelectedFile(e.target.files?.[0])}
          />
          <Button size="small" onClick={() => fileRef.current?.click()}>
            Choose Image File…
          </Button>
          <Button
            size="small"
            onClick={() =>
              onLoaded?.({
                dataUrl: sampleDataUrl,
                mediaType: 'image/png',
                fileName: 'sample-form-screenshot.png',
              })
            }
          >
            {sampleLabel}
          </Button>
        </Stack>
      </Box>
      {dataUrl && (
        <Box sx={{maxWidth: 280, maxHeight: 120, overflow: 'hidden', border: '1px solid', borderColor: 'divider'}}>
          <Box
            component="img"
            src={dataUrl}
            alt="Selected screenshot preview"
            sx={{width: '100%', height: 'auto', display: 'block'}}
          />
        </Box>
      )}
    </Box>
  );
}

ScreenshotFileDropzone.propTypes = {
  label: PropTypes.string,
  inputLabel: PropTypes.string,
  sampleLabel: PropTypes.string,
  sampleDataUrl: PropTypes.string,
  fileName: PropTypes.string,
  dataUrl: PropTypes.string,
  onLoaded: PropTypes.func,
  onError: PropTypes.func,
};

export function ScreenMeshDesignerSurface({
  projectId,
  designId,
  client: suppliedClient,
  controller: suppliedController,
  readOnly = false,
  executeCommand,
  onStateChange,
  onExport,
  onError,
}) {
  const client = useMemo(
    () => suppliedClient ?? new DesignStoreClient(),
    [suppliedClient]
  );
  const controller = useMemo(
    () =>
      suppliedController ??
      new SharedDDNTaskController({
        client,
        projectId,
        designId,
        kind: 'screen',
      }),
    [suppliedController, client, projectId, designId]
  );

  const [sessionState, setSessionState] = useState(() => controller.state());
  const [meshPayload, setMeshPayload] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busyMessage, setBusyMessage] = useState('');
  const [error, setError] = useState('');
  const [bannerInfo, setBannerInfo] = useState('');

  // Tabbed menu & top-level workspace view modes
  const [menuTab, setMenuTab] = useState('mesh');
  const [viewMode, setViewMode] = useState('wireframe'); // 'wireframe' | 'flow' | 'field_spec'
  const [selectedWireframeView, setSelectedWireframeView] =
    useState('screen_mesh_main');
  const [activeScreenId, setActiveScreenId] = useState('');

  // Field Specification Table state (SR-F-030022)
  const [fieldSpecData, setFieldSpecData] = useState(null);
  const [fieldSpecFilter, setFieldSpecFilter] = useState('');
  const [specPreviewModal, setSpecPreviewModal] = useState({
    open: false,
    format: 'markdown',
  });

  // Shared chrome dialogs
  const [checkpointDrawerOpen, setCheckpointDrawerOpen] = useState(false);
  const [whereUsedOpen, setWhereUsedOpen] = useState(false);
  const [whereUsedSeed, setWhereUsedSeed] = useState('');
  const [ddnExportModal, setDdnExportModal] = useState({
    open: false,
    ddnText: '',
  });
  const [suspectDialogOpen, setSuspectDialogOpen] = useState(false);

  // Screen & Control dialogs
  const [screenDialogOpen, setScreenDialogOpen] = useState(false);
  const [newScreen, setNewScreen] = useState({
    name: '',
    width: '960',
    height: '640',
    formReference: '',
  });

  const [controlDialogOpen, setControlDialogOpen] = useState(false);
  const [controlModalTab, setControlModalTab] = useState('general');
  const [newControl, setNewControl] = useState({
    screenId: '',
    role: 'ui.input',
    name: '',
    placeholder: '',
    checked: false,
    targetKind: 'column',
    targetRef: '',
    accessMode: 'read_write',
    gridColumns: [
      {col_id: 'id', label: 'ID', target_ref: '', width: 110},
      {col_id: 'name', label: 'Name', target_ref: '', width: 180},
    ],
    choiceRows: [{option: 'Option A'}, {option: 'Option B'}],
  });

  const [bindingDialogOpen, setBindingDialogOpen] = useState(false);
  const [newBinding, setNewBinding] = useState({
    sourceId: '',
    columnId: '',
    targetKind: 'column',
    targetRef: '',
    accessMode: 'read',
  });

  const [navDialogOpen, setNavDialogOpen] = useState(false);
  const [newNav, setNewNav] = useState({
    fromId: '',
    toScreenId: '',
    trigger: 'click',
    action: 'navigate',
    label: '',
  });

  // Screenshot upload, rubber-band regions, redaction, trace & compare (SR-F-030021)
  const [screenshotDialogOpen, setScreenshotDialogOpen] = useState(false);
  const [screenshotForm, setScreenshotForm] = useState({
    screenId: '',
    mediaType: 'image/png',
    dataUrl: '',
    fileName: '',
  });
  const [localScreenPreviews, setLocalScreenPreviews] = useState({});

  const [regionDialogOpen, setRegionDialogOpen] = useState(false);
  const [regionDraftScreenId, setRegionDraftScreenId] = useState('');
  const [regionRows, setRegionRows] = useState([]);

  const [redactDialogOpen, setRedactDialogOpen] = useState(false);
  const [redactScreenId, setRedactScreenId] = useState('');
  const [redactRows, setRedactRows] = useState([
    {x: 16, y: 16, width: 160, height: 40},
  ]);

  const [traceDialogOpen, setTraceDialogOpen] = useState(false);
  const [traceForm, setTraceForm] = useState({
    sourceScreenId: '',
    linkNavigation: true,
    hintRows: [],
  });

  const [compareDialogOpen, setCompareDialogOpen] = useState(false);
  const [compareForm, setCompareForm] = useState({
    screenId: '',
    mediaType: 'image/png',
    dataUrl: '',
    fileName: '',
    replaceScreenshot: false,
  });
  const [compareResult, setCompareResult] = useState(null);

  // SR-F Import modal (SR-F-030023)
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [descriptorForms, setDescriptorForms] = useState([]);
  const [importForm, setImportForm] = useState({
    selectedRef: '',
    customRef: '',
    qaRegions: [],
  });

  // Accept & Git dialogs
  const [acceptDialogOpen, setAcceptDialogOpen] = useState(false);
  const [acceptForm, setAcceptForm] = useState({
    requireGitReview: false,
    gitReviewRef: '',
    comment: '',
  });

  const [gitDialogOpen, setGitDialogOpen] = useState(false);
  const [gitForm, setGitForm] = useState({
    action: 'save',
    repoRoot: '',
    path: '',
    branch: 'main',
    note: '',
  });

  const loadAll = useCallback(
    async (version = null) => {
      setLoading(true);
      setError('');
      try {
        const nextSession = await controller.load({version});
        const hydrated = await controller.getScreenMeshModel({
          version: nextSession.currentVersion,
        });
        setSessionState(nextSession);
        setMeshPayload(hydrated);
        setDirty(false);
        const firstSid = hydrated?.mesh?.screens?.[0]?.id || '';
        setActiveScreenId((cur) =>
          hydrated?.mesh?.screens?.some((s) => s.id === cur) ? cur : firstSid
        );
        onStateChange?.({
          ...nextSession,
          suspectBindingCount: hydrated.suspect_binding_count ?? 0,
        });
      } catch (loadErr) {
        const msg = loadErr?.message || 'Failed to load Screen Mesh.';
        setError(msg);
        onError?.(loadErr);
      } finally {
        setLoading(false);
      }
    },
    [controller, onStateChange, onError]
  );

  useEffect(() => {
    const unsub = controller.subscribe((next) => setSessionState(next));
    loadAll();
    return unsub;
  }, [controller, loadAll]);

  const mesh = meshPayload?.mesh ?? null;
  const screens = mesh?.screens ?? [];
  const controls = mesh?.controls ?? [];
  const regions = mesh?.regions ?? [];
  const bindings = mesh?.bindings ?? [];
  const navigations = mesh?.navigations ?? [];
  const suspectCount = meshPayload?.suspect_binding_count ?? 0;
  const lookHanddrawn = Boolean(mesh?.look_handdrawn);

  const effectiveActiveScreen = useMemo(
    () => screens.find((s) => s.id === activeScreenId) || screens[0] || null,
    [screens, activeScreenId]
  );

  const screenOptions = useMemo(
    () => screens.map((s) => ({value: s.id, label: s.name})),
    [screens]
  );

  const wireframeViewOptions = useMemo(() => {
    const opts = [{value: 'screen_mesh_main', label: 'All Screens Wireframe'}];
    if (screens.length > 1) {
      screens.forEach((scr, idx) => {
        opts.push({
          value: `screen_${idx + 1}`,
          label: `Screen ${idx + 1}: ${scr.name}`,
        });
      });
    }
    return opts;
  }, [screens]);

  const viewerSnapshot = useMemo(() => {
    if (!sessionState.loaded || !sessionState.workspace) return null;
    const requestedView =
      viewMode === 'flow' ? 'screen_flow' : selectedWireframeView;
    const resolvedView = resolveMeshView(sessionState.workspace, requestedView);
    const entry = sessionState.workspace.entry;
    const rawEntryText = sessionState.workspace.files?.[entry] || '';
    const patchedEntryText = applyHanddrawnToDdnText(
      rawEntryText,
      lookHanddrawn
    );
    return {
      ...sessionState.workspace,
      view: resolvedView,
      files: {
        ...sessionState.workspace.files,
        ...(entry ? {[entry]: patchedEntryText} : {}),
      },
    };
  }, [sessionState, viewMode, selectedWireframeView, lookHanddrawn]);

  const bindableSourceOptions = useMemo(() => {
    const list = [];
    screens.forEach((s) =>
      list.push({value: s.id, label: `Screen: ${s.name}`})
    );
    controls.forEach((c) =>
      list.push({value: c.id, label: `${c.role}: ${c.name}`})
    );
    regions.forEach((r) =>
      list.push({value: r.id, label: `ui.region: ${r.name}`})
    );
    return list;
  }, [screens, controls, regions]);

  const screenshotUrlForScreen = useCallback(
    (scr) => {
      if (!scr) return '';
      if (localScreenPreviews[scr.id]) return localScreenPreviews[scr.id];
      if (scr.screenshot_sha256) {
        return controller.screenMeshBlobUrl(scr.screenshot_sha256);
      }
      return '';
    },
    [localScreenPreviews, controller]
  );

  const loadFieldSpec = useCallback(
    async (format = 'markdown') => {
      setBusyMessage('Building Screen Mesh field specification');
      setError('');
      try {
        if (typeof client.getScreenMeshFieldSpec === 'function') {
          const spec = await controller.getScreenMeshFieldSpec({format});
          setFieldSpecData(spec);
          return spec;
        }
        const fallback = buildFallbackFieldSpec(
          designId,
          sessionState.title || mesh?.name,
          sessionState.currentVersion,
          mesh
        );
        setFieldSpecData(fallback);
        return fallback;
      } catch (specErr) {
        setError(specErr.message);
        return null;
      } finally {
        setBusyMessage('');
      }
    },
    [client, controller, designId, sessionState, mesh]
  );

  useEffect(() => {
    if (viewMode === 'field_spec' && mesh) {
      loadFieldSpec('markdown');
    }
  }, [viewMode, mesh, loadFieldSpec]);

  const updateDraftMesh = useCallback((mutator) => {
    setMeshPayload((prev) => {
      if (!prev?.mesh) return prev;
      const nextMesh = mutator({
        ...prev.mesh,
        screens: [...(prev.mesh.screens || [])],
        controls: [...(prev.mesh.controls || [])],
        regions: [...(prev.mesh.regions || [])],
        bindings: [...(prev.mesh.bindings || [])],
        navigations: [...(prev.mesh.navigations || [])],
      });
      return {...prev, mesh: nextMesh};
    });
    setDirty(true);
  }, []);

  const runToolbarCommand = (commandId, invoke) => {
    if (typeof executeCommand === 'function') {
      return executeCommand(commandId, {enabled: !readOnly, invoke});
    }
    return invoke();
  };

  const handleSaveCheckpoint = useCallback(async () => {
    if (!mesh) return;
    setBusyMessage('Saving Screen Mesh checkpoint');
    setError('');
    try {
      const saved = await controller.saveScreenMeshModel({
        mesh,
        status:
          sessionState.status === 'accepted' ? 'draft' : sessionState.status,
        note: 'Saved Screen Mesh checkpoint',
      });
      setMeshPayload(saved);
      setDirty(false);
      setBannerInfo(
        `Saved Screen Mesh checkpoint v${saved.design.version.version}.`
      );
      onStateChange?.({
        ...controller.state(),
        suspectBindingCount: saved.suspect_binding_count ?? 0,
      });
    } catch (saveErr) {
      setError(saveErr.message);
      onError?.(saveErr);
    } finally {
      setBusyMessage('');
    }
  }, [controller, mesh, sessionState.status, onStateChange, onError]);

  const handleAdvanceStatusTo = useCallback(
    async (targetStatus) => {
      setBusyMessage(`Advancing status to ${targetStatus}`);
      setError('');
      try {
        const updated = await controller.advanceStatus(targetStatus);
        setSessionState(updated);
        setBannerInfo(`Advanced save point to ${targetStatus}.`);
      } catch (advErr) {
        setError(advErr.message);
      } finally {
        setBusyMessage('');
      }
    },
    [controller]
  );

  const handleBranchDraft = useCallback(async () => {
    setBusyMessage('Branching new draft from accepted version');
    setError('');
    try {
      const branched = await controller.branchDraft({
        note: 'Branched draft from accepted Screen Mesh',
      });
      await loadAll(branched.currentVersion);
      setBannerInfo(`Branched new draft v${branched.currentVersion}.`);
    } catch (brErr) {
      setError(brErr.message);
    } finally {
      setBusyMessage('');
    }
  }, [controller, loadAll]);

  const handleExportDdn = async () => {
    setBusyMessage('Exporting Screen Mesh DDN');
    setError('');
    try {
      let exportedText = '';
      if (typeof client.exportDDN === 'function') {
        const exp = await client.exportDDN(projectId, designId, {
          version: sessionState.currentVersion,
        });
        exportedText =
          typeof exp === 'string'
            ? exp
            : exp?.ddn_text ||
              exp?.files?.[exp?.entry] ||
              viewerSnapshot?.files?.[viewerSnapshot?.entry] ||
              '';
      } else {
        exportedText = viewerSnapshot?.files?.[viewerSnapshot?.entry] || '';
      }
      triggerBrowserDownload(
        `${sessionState.design?.key || designId}.ddn`,
        exportedText,
        'text/plain'
      );
      setDdnExportModal({open: true, ddnText: exportedText});
    } catch (expErr) {
      setError(expErr.message);
    } finally {
      setBusyMessage('');
    }
  };

  const handleRecomputeLayout = async () => {
    if (typeof client.computeLayout !== 'function') {
      setBannerInfo('Server layout is up to date.');
      return;
    }
    setBusyMessage('Recomputing server-side layered layout');
    setError('');
    try {
      const viewId =
        viewMode === 'flow' ? 'screen_flow' : selectedWireframeView;
      await client.computeLayout(projectId, designId, {
        version: sessionState.currentVersion,
        viewId,
      });
      await loadAll(sessionState.currentVersion);
      setBannerInfo(`Recomputed server layout for view ${viewId}.`);
    } catch (layErr) {
      setError(layErr.message);
    } finally {
      setBusyMessage('');
    }
  };

  const handleToggleSketchLook = () => {
    if (readOnly) return;
    updateDraftMesh((cur) => ({
      ...cur,
      look_handdrawn: !cur.look_handdrawn,
    }));
  };

  const handleAddScreen = () => {
    const trimmed = newScreen.name.trim();
    if (!trimmed) {
      setError('Screen name is required.');
      return;
    }
    const tempId = `019a0000-0000-7000-8000-${String(Date.now())
      .slice(-12)
      .padStart(12, '0')}`;
    updateDraftMesh((cur) => ({
      ...cur,
      screens: [
        ...cur.screens,
        {
          id: tempId,
          name: trimmed,
          width: Math.max(120, Number(newScreen.width) || 960),
          height: Math.max(80, Number(newScreen.height) || 640),
          form_reference: newScreen.formReference.trim(),
          screenshot_path: '',
          screenshot_sha256: '',
          notes: '',
        },
      ],
    }));
    setActiveScreenId(tempId);
    setScreenDialogOpen(false);
  };

  const openAddControlWithRole = (role = 'ui.input') => {
    setControlModalTab('general');
    setNewControl({
      screenId: effectiveActiveScreen?.id || screens[0]?.id || '',
      role,
      name: '',
      placeholder: '',
      checked: false,
      targetKind: role === 'ui.grid' ? 'table' : 'column',
      targetRef: '',
      accessMode: role === 'ui.grid' ? 'read' : 'read_write',
      gridColumns: [
        {col_id: 'id', label: 'ID', target_ref: '', width: 110},
        {col_id: 'name', label: 'Name', target_ref: '', width: 180},
      ],
      choiceRows: [{option: 'Option A'}, {option: 'Option B'}],
    });
    setControlDialogOpen(true);
  };

  const handleAddControl = () => {
    const trimmed = newControl.name.trim();
    if (!trimmed) {
      setError('Control label is required.');
      return;
    }
    const targetScreenId =
      newControl.screenId || effectiveActiveScreen?.id || screens[0]?.id || '';
    const baseNum = Date.now();
    const ctrlId = `019b0000-0000-7000-8000-${String(baseNum)
      .slice(-12)
      .padStart(12, '0')}`;

    const extraBindings = [];
    if (newControl.targetRef.trim()) {
      extraBindings.push({
        id: `019d0000-0000-7000-8001-${String(baseNum)
          .slice(-12)
          .padStart(12, '0')}`,
        source_id: ctrlId,
        column_id: null,
        target_kind: newControl.targetKind,
        target_ref: newControl.targetRef.trim(),
        access_mode: newControl.accessMode,
        state: 'unknown',
      });
    }

    const columns =
      newControl.role === 'ui.grid'
        ? (newControl.gridColumns || [])
          .filter((r) => String(r.col_id || r.label || '').trim())
          .map((r, idx) => {
            const cid =
                String(r.col_id || r.label || `col_${idx + 1}`)
                  .trim()
                  .toLowerCase()
                  .replace(/[^a-z0-9_]+/g, '_')
                  .replace(/^_+|_+$/g, '') || `col_${idx + 1}`;
            if (String(r.target_ref || '').trim()) {
              extraBindings.push({
                id: `019d0000-0000-7000-80${String((idx + 2) % 99).padStart(2, '0')}-${String(
                  baseNum + idx
                )
                  .slice(-12)
                  .padStart(12, '0')}`,
                source_id: ctrlId,
                column_id: cid,
                target_kind: 'column',
                target_ref: String(r.target_ref).trim(),
                access_mode: 'read',
                state: 'unknown',
              });
            }
            return {
              id: cid,
              name: String(r.label || cid).trim(),
              width: Math.max(40, Number(r.width) || 140),
              datatype: 'text',
            };
          })
        : [];

    const options = ['ui.dropdown', 'ui.radio', 'ui.tabs', 'ui.list'].includes(
      newControl.role
    )
      ? (newControl.choiceRows || [])
        .map((r) => String(r.option || '').trim())
        .filter(Boolean)
      : [];

    updateDraftMesh((cur) => ({
      ...cur,
      controls: [
        ...cur.controls,
        {
          id: ctrlId,
          screen_id: targetScreenId,
          role: newControl.role,
          name: trimmed,
          columns,
          options,
          placeholder: newControl.placeholder.trim(),
          checked: Boolean(newControl.checked),
          notes: '',
        },
      ],
      bindings: [...cur.bindings, ...extraBindings],
    }));
    setControlDialogOpen(false);
  };

  const openDrawRegionsModal = (targetSid = null) => {
    const sid = targetSid || effectiveActiveScreen?.id || screens[0]?.id || '';
    setRegionDraftScreenId(sid);
    const existingForScreen = regions
      .filter((r) => r.screen_id === sid)
      .map((r) => {
        const bnd = bindings.find((b) => b.source_id === r.id);
        return {
          id: r.id,
          name: r.name,
          x: Number(r.bounds?.x) || 0,
          y: Number(r.bounds?.y) || 0,
          width: Number(r.bounds?.width) || 160,
          height: Number(r.bounds?.height) || 48,
          kind_hint: r.kind_hint || '',
          target_ref: bnd?.target_ref || '',
        };
      });
    setRegionRows(existingForScreen);
    setRegionDialogOpen(true);
  };

  const handleApplyRegions = () => {
    const sid = regionDraftScreenId || effectiveActiveScreen?.id || screens[0]?.id || '';
    if (!sid) return;
    const stamp = Date.now();
    const validRows = regionRows.filter((r) => String(r.name || '').trim());

    updateDraftMesh((cur) => {
      const otherScreenRegions = cur.regions.filter((r) => r.screen_id !== sid);
      const removedRegionIds = new Set(
        cur.regions.filter((r) => r.screen_id === sid).map((r) => r.id)
      );
      const nextRegionsForScreen = [];
      const nextBindings = cur.bindings.filter(
        (b) => !removedRegionIds.has(b.source_id)
      );

      validRows.forEach((row, idx) => {
        const rid =
          row.id ||
          `019c0000-0000-7000-80${String((idx + 1) % 99).padStart(2, '0')}-${String(
            stamp + idx
          )
            .slice(-12)
            .padStart(12, '0')}`;
        nextRegionsForScreen.push({
          id: rid,
          screen_id: sid,
          role: 'ui.region',
          name: String(row.name).trim(),
          kind_hint: String(row.kind_hint || '').trim(),
          bounds: {
            x: Math.max(0, Number(row.x) || 0),
            y: Math.max(0, Number(row.y) || 0),
            width: Math.max(1, Number(row.width) || 120),
            height: Math.max(1, Number(row.height) || 40),
          },
          notes: '',
        });
        const tref = String(row.target_ref || '').trim();
        if (tref) {
          nextBindings.push({
            id: `019d0000-0000-7000-81${String((idx + 1) % 99).padStart(2, '0')}-${String(
              stamp + idx
            )
              .slice(-12)
              .padStart(12, '0')}`,
            source_id: rid,
            column_id: null,
            target_kind: tref.split('.').length >= 3 ? 'column' : 'table',
            target_ref: tref,
            access_mode: 'read_write',
            state: 'unknown',
          });
        }
      });

      return {
        ...cur,
        regions: [...otherScreenRegions, ...nextRegionsForScreen],
        bindings: nextBindings,
      };
    });
    setRegionDialogOpen(false);
  };

  const handleAddBinding = () => {
    const srcId = newBinding.sourceId || bindableSourceOptions[0]?.value || '';
    const tref = newBinding.targetRef.trim();
    if (!srcId || !tref) {
      setError('Binding source and target reference are required.');
      return;
    }
    const tempId = `019d0000-0000-7000-8000-${String(Date.now())
      .slice(-12)
      .padStart(12, '0')}`;
    updateDraftMesh((cur) => ({
      ...cur,
      bindings: [
        ...cur.bindings,
        {
          id: tempId,
          source_id: srcId,
          column_id: newBinding.columnId.trim() || null,
          target_kind: newBinding.targetKind,
          target_ref: tref,
          access_mode: newBinding.accessMode,
          state: 'unknown',
        },
      ],
    }));
    setBindingDialogOpen(false);
  };

  const handleAddNavigation = () => {
    const fromId = newNav.fromId || bindableSourceOptions[0]?.value || '';
    const toScreenId = newNav.toScreenId || screens[0]?.id || '';
    if (!fromId || !toScreenId) {
      setError('Navigation source and target screen are required.');
      return;
    }
    const tempId = `019e0000-0000-7000-8000-${String(Date.now())
      .slice(-12)
      .padStart(12, '0')}`;
    updateDraftMesh((cur) => ({
      ...cur,
      navigations: [
        ...cur.navigations,
        {
          id: tempId,
          from_id: fromId,
          to_screen_id: toScreenId,
          trigger: newNav.trigger,
          action: newNav.action,
          delay_ms: 0,
          url: '',
          label:
            newNav.label.trim() || `${newNav.trigger} -> ${newNav.action}`,
        },
      ],
    }));
    setNavDialogOpen(false);
  };

  const handleUploadScreenshot = async () => {
    const rawDataUrl = screenshotForm.dataUrl.trim();
    if (!rawDataUrl) {
      setError('Choose or drop a PNG, JPEG, or WebP screenshot image first.');
      return;
    }
    const targetSid =
      screenshotForm.screenId || effectiveActiveScreen?.id || screens[0]?.id || null;
    const strippedB64 = rawDataUrl.includes(',')
      ? rawDataUrl.split(',', 2)[1]
      : rawDataUrl;

    setBusyMessage('Attaching screenshot to Screen Mesh');
    setError('');
    try {
      const updated = await controller.uploadScreenMeshScreenshot({
        imageBase64: strippedB64,
        mediaType: screenshotForm.mediaType,
        screenId: targetSid,
      });
      if (targetSid) {
        setLocalScreenPreviews((cur) => ({...cur, [targetSid]: rawDataUrl}));
      }
      setMeshPayload(updated);
      setDirty(false);
      setScreenshotDialogOpen(false);
      setBannerInfo('Attached screenshot to Screen Mesh.');
    } catch (upErr) {
      setError(upErr.message);
    } finally {
      setBusyMessage('');
    }
  };

  const handleRedactScreenshot = async () => {
    const validBoxes = redactRows
      .map((r) => ({
        x: Math.max(0, Number(r.x) || 0),
        y: Math.max(0, Number(r.y) || 0),
        width: Math.max(1, Number(r.width) || 80),
        height: Math.max(1, Number(r.height) || 30),
      }))
      .filter((r) => r.width > 0 && r.height > 0);
    if (!validBoxes.length) {
      setError('Draw or add at least one redaction rectangle.');
      return;
    }
    const targetSid =
      redactScreenId || effectiveActiveScreen?.id || screens[0]?.id || null;
    setBusyMessage('Destructively redacting screenshot regions');
    setError('');
    try {
      const updated = await controller.redactScreenMeshScreenshot({
        screenId: targetSid,
        regions: validBoxes,
      });
      if (targetSid) {
        setLocalScreenPreviews((cur) => {
          const copy = {...cur};
          delete copy[targetSid];
          return copy;
        });
      }
      setMeshPayload(updated);
      setDirty(false);
      setRedactDialogOpen(false);
      setBannerInfo(
        'Redacted screenshot region(s) and purged original unredacted bytes from designs.db.'
      );
    } catch (redErr) {
      setError(redErr.message);
    } finally {
      setBusyMessage('');
    }
  };

  const openTraceModal = () => {
    const firstWithRegions =
      screens.find((s) => regions.some((r) => r.screen_id === s.id)) ||
      effectiveActiveScreen ||
      screens[0];
    const sid = firstWithRegions?.id || '';
    const hintRows = regions
      .filter((r) => r.screen_id === sid)
      .map((r) => ({
        region_id: r.id,
        region_name: r.name,
        kind_hint: r.kind_hint || '',
      }));
    setTraceForm({
      sourceScreenId: sid,
      linkNavigation: true,
      hintRows,
    });
    setTraceDialogOpen(true);
  };

  const handleTraceScreenshotToMesh = async () => {
    setBusyMessage('Tracing screenshot regions into wireframe controls');
    setError('');
    try {
      const regionHints = {};
      for (const row of traceForm.hintRows) {
        if (row.kind_hint) {
          regionHints[row.region_id || row.region_name] = row.kind_hint;
        }
      }
      const traced = await controller.traceScreenMeshScreenshot({
        source_screen_id: traceForm.sourceScreenId || null,
        link_navigation: Boolean(traceForm.linkNavigation),
        region_hints: regionHints,
      });
      await loadAll(traced?.design?.version?.version ?? null);
      if (traced?.traced_screen_id) {
        setActiveScreenId(traced.traced_screen_id);
      }
      setTraceDialogOpen(false);
      setBannerInfo(
        `Traced ${traced.controls_created ?? 0} controls and preserved ${traced.bindings_preserved ?? 0} bindings on companion wireframe screen.`
      );
    } catch (trErr) {
      setError(trErr.message);
    } finally {
      setBusyMessage('');
    }
  };

  const handleCompareScreenshots = async () => {
    if (!compareForm.dataUrl) {
      setError('Choose, drop, or load a newer screenshot to compare.');
      return;
    }
    setBusyMessage('Comparing newer screenshot against stored baseline');
    setError('');
    try {
      const res = await controller.compareScreenMeshScreenshots({
        screen_id:
          compareForm.screenId || effectiveActiveScreen?.id || screens[0]?.id,
        new_image_base64: compareForm.dataUrl,
        media_type: compareForm.mediaType,
        replace_screenshot: Boolean(compareForm.replaceScreenshot),
      });
      setCompareResult(res);
      if (compareForm.replaceScreenshot && res?.design?.version?.version) {
        await loadAll(res.design.version.version);
        setBannerInfo(
          `Replaced screenshot and saved checkpoint v${res.design.version.version}.`
        );
      }
    } catch (cmpErr) {
      setError(cmpErr.message);
    } finally {
      setBusyMessage('');
    }
  };

  const handleConfirmSuspect = async (storeBindingId, targetRef) => {
    if (!storeBindingId) return;
    setBusyMessage('Confirming suspect binding');
    setError('');
    try {
      await controller.confirmSuspectBinding(storeBindingId, targetRef);
      await loadAll(controller.state().currentVersion);
      setBannerInfo(`Confirmed binding ${targetRef}.`);
    } catch (confErr) {
      setError(confErr.message);
    } finally {
      setBusyMessage('');
    }
  };

  const openImportDescriptorModal = async () => {
    setImportDialogOpen(true);
    if (
      !descriptorForms.length &&
      typeof client.listDescriptorForms === 'function'
    ) {
      try {
        const forms = await client.listDescriptorForms();
        setDescriptorForms(forms || []);
        if (forms?.length) {
          setImportForm((cur) => ({
            ...cur,
            selectedRef: cur.selectedRef || forms[0].form_reference,
          }));
        }
      } catch {
        // Explicit SR-F code input remains available.
      }
    }
  };

  const handleImportDescriptorForm = async () => {
    const refCode = (
      importForm.selectedRef || importForm.customRef
    ).trim();
    if (!refCode) {
      setError('Select or enter an SR-F form reference to import.');
      return;
    }
    setBusyMessage(`Importing ${refCode} into Draft Screen Mesh`);
    setError('');
    try {
      const qaManifest =
        importForm.qaRegions.length > 0
          ? [
            {
              form_reference: refCode,
              regions: importForm.qaRegions
                .filter((r) => String(r.name || '').trim())
                .map((r) => ({
                  name: String(r.name).trim(),
                  bounds: {
                    x: Math.max(0, Number(r.x) || 0),
                    y: Math.max(0, Number(r.y) || 0),
                    width: Math.max(1, Number(r.width) || 160),
                    height: Math.max(1, Number(r.height) || 48),
                  },
                })),
            },
          ]
          : null;
      const imported = await client.importDescriptorMesh(projectId, {
        formReference: refCode,
        qaManifest,
      });
      setImportDialogOpen(false);
      setBannerInfo(
        `Imported ${refCode} as Draft Screen Mesh (${imported?.design?.title || refCode}).`
      );
    } catch (impErr) {
      setError(impErr.message);
    } finally {
      setBusyMessage('');
    }
  };

  const handleAccept = async () => {
    setBusyMessage('Accepting Screen Mesh version');
    setError('');
    try {
      await controller.accept({
        requireGitReview: acceptForm.requireGitReview,
        gitReviewRef: acceptForm.gitReviewRef.trim() || null,
        comment: acceptForm.comment.trim(),
      });
      await loadAll(controller.state().currentVersion);
      setAcceptDialogOpen(false);
      setBannerInfo('Accepted Screen Mesh version.');
    } catch (accErr) {
      setError(accErr.message);
    } finally {
      setBusyMessage('');
    }
  };

  const handleGitSync = async () => {
    setBusyMessage('Running Git operation');
    setError('');
    try {
      await controller.gitOperation({
        action: gitForm.action,
        repoRoot: gitForm.repoRoot.trim(),
        path: gitForm.path.trim() || `${designId}.ddn`,
        branch: gitForm.branch.trim() || 'main',
        note: gitForm.note.trim(),
      });
      await loadAll();
      setGitDialogOpen(false);
      setBannerInfo(`Completed Git ${gitForm.action} operation.`);
    } catch (gitErr) {
      setError(gitErr.message);
    } finally {
      setBusyMessage('');
    }
  };

  const filteredSpecRows = useMemo(() => {
    const all = fieldSpecData?.rows || [];
    const q = fieldSpecFilter.trim().toLowerCase();
    if (!q) return all;
    return all.filter((r) =>
      [
        r.screen_title,
        r.label,
        r.element_kind,
        r.target_ref,
        r.catalog_type,
        r.binding_state,
      ]
        .join(' ')
        .toLowerCase()
        .includes(q)
    );
  }, [fieldSpecData, fieldSpecFilter]);

  if (!loading && error && !mesh) {
    return (
      <Box component="section" aria-label="Screen Mesh Designer">
        <FormReference formKey="screen-mesh-workspace" />
        <EmptyState
          role="alert"
          message={error}
          actionLabel="Retry"
          onAction={() => loadAll()}
        />
      </Box>
    );
  }

  const activeScreenshots = screens.filter(
    (s) => s.screenshot_sha256 || localScreenPreviews[s.id]
  );

  const menuTabs = [
    {
      id: 'mesh',
      label: 'Mesh',
      dirty,
      groups: [
        {
          id: 'mesh-save',
          label: 'Checkpoint',
          items: [
            {
              id: 'screen-mesh-save',
              label: `Save Draft${dirty ? ' *' : ''}`,
              intent: dirty ? 'primary' : 'neutral',
              disabled: readOnly,
              onClick: () =>
                runToolbarCommand(
                  'screen_mesh.designer.save',
                  handleSaveCheckpoint
                ),
            },
          ],
        },
        {
          id: 'mesh-lifecycle',
          label: 'Advance Status',
          items: [
            {
              id: 'screen-mesh-in-progress',
              label: 'In Progress',
              disabled: readOnly || sessionState.status !== 'draft',
              onClick: () => handleAdvanceStatusTo('in_progress'),
            },
            {
              id: 'screen-mesh-in-review',
              label: 'In Review',
              disabled: readOnly || sessionState.status !== 'in_progress',
              onClick: () => handleAdvanceStatusTo('in_review'),
            },
            {
              id: 'screen-mesh-accept',
              label: 'Accept',
              disabled: readOnly,
              onClick: () =>
                runToolbarCommand('screen_mesh.designer.accept', () =>
                  setAcceptDialogOpen(true)
                ),
            },
            {
              id: 'screen-mesh-branch',
              label: 'Branch Draft',
              disabled: readOnly || !sessionState.activeVersion,
              onClick: handleBranchDraft,
            },
          ],
        },
        {
          id: 'mesh-history-git',
          label: 'History & Sync',
          items: [
            {
              id: 'screen-mesh-checkpoints',
              label: 'Checkpoints & Diff…',
              onClick: () => setCheckpointDrawerOpen(true),
            },
            {
              id: 'screen-mesh-git',
              label: 'Git Sync…',
              disabled: readOnly,
              onClick: () => setGitDialogOpen(true),
            },
            {
              id: 'screen-mesh-export-ddn',
              label: 'Export DDN',
              onClick: handleExportDdn,
            },
            {
              id: 'screen-mesh-where-used',
              label: 'Where Used…',
              onClick: () => {
                setWhereUsedSeed('');
                setWhereUsedOpen(true);
              },
            },
          ],
        },
      ],
    },
    {
      id: 'screens_controls',
      label: 'Screens & Controls',
      groups: [
        {
          id: 'active-screen-group',
          label: 'Active Screen',
          items: [
            {
              id: 'active-screen-picker',
              render: () => (
                <Select
                  aria-label="Active Screen"
                  size="small"
                  options={screenOptions}
                  value={effectiveActiveScreen?.id || ''}
                  onChange={(val) => setActiveScreenId(val)}
                />
              ),
            },
            {
              id: 'add-screen-btn',
              label: '+ Add Screen…',
              disabled: readOnly,
              onClick: () => {
                setNewScreen({
                  name: '',
                  width: '960',
                  height: '640',
                  formReference: '',
                });
                setScreenDialogOpen(true);
              },
            },
          ],
        },
        {
          id: 'controls-stencil-group',
          label: 'Wireframe Stencil',
          items: [
            {
              id: 'add-control-btn',
              label: '+ Add Control…',
              disabled: readOnly,
              onClick: () => openAddControlWithRole('ui.input'),
            },
            {
              id: 'add-grid-btn',
              label: '+ Grid',
              disabled: readOnly,
              onClick: () => openAddControlWithRole('ui.grid'),
            },
            {
              id: 'add-dropdown-btn',
              label: '+ Dropdown',
              disabled: readOnly,
              onClick: () => openAddControlWithRole('ui.dropdown'),
            },
            {
              id: 'add-tabs-btn',
              label: '+ Tabs',
              disabled: readOnly,
              onClick: () => openAddControlWithRole('ui.tabs'),
            },
            {
              id: 'add-binding-btn',
              label: '+ Add Binding…',
              disabled: readOnly,
              onClick: () => {
                setNewBinding({
                  sourceId: bindableSourceOptions[0]?.value || '',
                  columnId: '',
                  targetKind: 'column',
                  targetRef: '',
                  accessMode: 'read',
                });
                setBindingDialogOpen(true);
              },
            },
          ],
        },
        {
          id: 'navigation-look-group',
          label: 'Navigation & Look',
          items: [
            {
              id: 'add-nav-btn',
              label: '+ Add Navigation…',
              disabled: readOnly,
              onClick: () => {
                setNewNav({
                  fromId: bindableSourceOptions[0]?.value || '',
                  toScreenId: screens[screens.length - 1]?.id || '',
                  trigger: 'click',
                  action: 'navigate',
                  label: '',
                });
                setNavDialogOpen(true);
              },
            },
            {
              id: 'sketch-look-toggle',
              label: lookHanddrawn ? 'Sketch Look: On' : 'Sketch Look',
              active: lookHanddrawn,
              disabled: readOnly,
              onClick: handleToggleSketchLook,
            },
          ],
        },
      ],
    },
    {
      id: 'screenshots_regions',
      label: 'Screenshots & Regions',
      groups: [
        {
          id: 'capture-regions-group',
          label: 'Screenshot & Hotspots',
          items: [
            {
              id: 'upload-screenshot-btn',
              label: 'Upload Screenshot…',
              disabled: readOnly,
              onClick: () => {
                setScreenshotForm({
                  screenId: effectiveActiveScreen?.id || screens[0]?.id || '',
                  mediaType: 'image/png',
                  dataUrl: '',
                  fileName: '',
                });
                setScreenshotDialogOpen(true);
              },
            },
            {
              id: 'draw-edit-regions-btn',
              label: 'Draw / Edit Regions…',
              disabled: readOnly,
              onClick: () => openDrawRegionsModal(),
            },
          ],
        },
        {
          id: 'redact-trace-compare-group',
          label: 'Redaction, Trace & Drift',
          items: [
            {
              id: 'redact-regions-btn',
              label: 'Redact Sensitive Regions…',
              disabled: readOnly || !activeScreenshots.length,
              onClick: () =>
                runToolbarCommand('screen_mesh.designer.redact', () => {
                  setRedactScreenId(
                    activeScreenshots[0]?.id || effectiveActiveScreen?.id || ''
                  );
                  setRedactRows([{x: 16, y: 16, width: 160, height: 40}]);
                  setRedactDialogOpen(true);
                }),
            },
            {
              id: 'trace-as-mesh-btn',
              label: 'Trace as Mesh…',
              disabled: readOnly || regions.length === 0,
              onClick: openTraceModal,
            },
            {
              id: 'compare-screenshot-btn',
              label: 'Compare Newer Screenshot…',
              disabled: !activeScreenshots.length,
              onClick: () => {
                setCompareResult(null);
                setCompareForm({
                  screenId:
                    activeScreenshots[0]?.id || effectiveActiveScreen?.id || '',
                  mediaType: 'image/png',
                  dataUrl: '',
                  fileName: '',
                  replaceScreenshot: false,
                });
                setCompareDialogOpen(true);
              },
            },
          ],
        },
      ],
    },
    {
      id: 'views_spec',
      label: 'Views & Field Spec',
      groups: [
        {
          id: 'workspace-view-switcher',
          label: 'Workspace View Mode',
          items: [
            {
              id: 'view-mode-wireframe',
              label: 'Screen Wireframe',
              active: viewMode === 'wireframe',
              onClick: () => setViewMode('wireframe'),
            },
            {
              id: 'view-mode-flow',
              label: 'Screen Flow',
              active: viewMode === 'flow',
              onClick: () => setViewMode('flow'),
            },
            {
              id: 'view-mode-field-spec',
              label: 'Field Specification Table',
              active: viewMode === 'field_spec',
              onClick: () => setViewMode('field_spec'),
            },
            ...(viewMode === 'wireframe' && screens.length > 1
              ? [
                {
                  id: 'wireframe-screen-view-select',
                  render: () => (
                    <Select
                      aria-label="Wireframe screen scope"
                      size="small"
                      options={wireframeViewOptions}
                      value={selectedWireframeView}
                      onChange={(val) => setSelectedWireframeView(val)}
                    />
                  ),
                },
              ]
              : []),
          ],
        },
        {
          id: 'layout-commands',
          label: 'Layout',
          items: [
            {
              id: 'recompute-layout-btn',
              label: 'Recompute Layout',
              onClick: handleRecomputeLayout,
            },
          ],
        },
      ],
    },
    {
      id: 'validate_export',
      label: 'Validate & Export',
      attention: suspectCount > 0,
      groups: [
        {
          id: 'validation-group',
          label: 'Binding Validation',
          items: [
            {
              id: 'suspect-bindings-btn',
              label: 'Suspect Bindings',
              badge: suspectCount,
              intent: suspectCount > 0 ? 'warning' : 'neutral',
              onClick: () => setSuspectDialogOpen(true),
            },
          ],
        },
        {
          id: 'spec-export-import-group',
          label: 'Specification & SR-F Import',
          items: [
            {
              id: 'export-spec-btn',
              label: 'Export Spec (Markdown / CSV / HTML)…',
              onClick: async () => {
                await loadFieldSpec('markdown');
                setSpecPreviewModal({open: true, format: 'markdown'});
              },
            },
            {
              id: 'import-srf-btn',
              label: 'Import SR-F Form…',
              disabled: readOnly,
              onClick: openImportDescriptorModal,
            },
          ],
        },
      ],
    },
  ];

  const regionDialogScreen =
    screens.find((s) => s.id === regionDraftScreenId) || effectiveActiveScreen;
  const redactDialogScreen =
    screens.find((s) => s.id === redactScreenId) || effectiveActiveScreen;

  return (
    <Box
      component="section"
      aria-label="Screen Mesh Designer"
      sx={{
        position: 'relative',
        height: '100%',
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <FormReference formKey="screen-mesh-workspace" />

      <DesignerTabbedMenu
        label="Screen Mesh designer menu"
        tabs={menuTabs}
        activeTab={menuTab}
        onTabChange={setMenuTab}
        leading={
          <StatusBadge
            label={
              sessionState.loaded
                ? `v${sessionState.currentVersion} (${sessionState.status})`
                : 'loading'
            }
            status={badgeStatus(sessionState.status)}
          />
        }
        trailing={
          <Stack direction="row" gap="compact">
            {lookHanddrawn && (
              <StatusBadge status="information" label="Sketch Look" />
            )}
            {suspectCount > 0 && (
              <StatusBadge
                status="warning"
                label={`${suspectCount} Suspect`}
              />
            )}
          </Stack>
        }
      />

      <Banner status="info">
        Screen Mesh scope: low-fidelity wireframes, annotated screenshots (
        <code>ui.region</code>), data bindings and screen-to-screen flows (
        <code>wireframe.ui@1</code>). Executable working forms are outside
        ScratchRobin scope.
      </Banner>

      {error && (
        <Banner status="error" onClose={() => setError('')}>
          {error}
        </Banner>
      )}
      {bannerInfo && (
        <Banner status="success" onClose={() => setBannerInfo('')}>
          {bannerInfo}
        </Banner>
      )}
      {suspectCount > 0 && (
        <Banner status="warning">
          {suspectCount} binding(s) are marked suspect after a catalog rename or
          drop. Review and confirm affected bindings below.
        </Banner>
      )}

      <Box
        sx={{
          flex: 1,
          minHeight: 0,
          display: 'grid',
          gridTemplateColumns:
            viewMode === 'field_spec'
              ? '1fr'
              : 'minmax(260px, 320px) 1fr',
          gap: 1,
          p: 1,
          overflow: 'hidden',
        }}
      >
        {viewMode !== 'field_spec' && (
          <ScrollArea
            label="Screen Mesh inspector"
            sx={{
              border: '1px solid',
              borderColor: 'divider',
              p: 1,
            }}
          >
            <Stack gap="standard">
              <Box>
                <strong>
                  {mesh?.name || sessionState.title || 'Screen Mesh'}
                </strong>
                <Box sx={{fontSize: '0.8125rem', color: 'text.secondary'}}>
                  Screens: {screens.length} · Controls: {controls.length} ·
                  Regions: {regions.length} · Bindings: {bindings.length} ·
                  Flows: {navigations.length}
                </Box>
              </Box>

              <Box>
                <strong>Screens (ui.frame)</strong>
                {screens.map((scr) => (
                  <Box key={scr.id} sx={{mt: 0.5, fontSize: '0.8125rem'}}>
                    <Box
                      component="span"
                      sx={{
                        fontWeight:
                          scr.id === effectiveActiveScreen?.id ? 600 : 400,
                      }}
                    >
                      {scr.name} ({scr.width}×{scr.height})
                      {scr.form_reference ? ` [${scr.form_reference}]` : ''}
                    </Box>
                    {scr.screenshot_sha256 ? (
                      <Box sx={{display: 'flex', alignItems: 'center', gap: 1, mt: 0.25}}>
                        <a
                          href={controller.screenMeshBlobUrl(
                            scr.screenshot_sha256
                          )}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Screenshot blob {scr.screenshot_sha256.slice(0, 10)}…
                        </a>
                        {!readOnly && (
                          <Button
                            size="small"
                            onClick={() => openDrawRegionsModal(scr.id)}
                          >
                            Regions…
                          </Button>
                        )}
                      </Box>
                    ) : null}
                  </Box>
                ))}
              </Box>

              {controls.length > 0 && (
                <Box>
                  <strong>Wireframe Controls</strong>
                  {controls.map((ctrl) => (
                    <Box key={ctrl.id} sx={{mt: 0.5, fontSize: '0.8125rem'}}>
                      <code>{ctrl.role}</code>: {ctrl.name}
                      {ctrl.columns?.length
                        ? ` (${ctrl.columns.map((c) => c.name).join(', ')})`
                        : ''}
                    </Box>
                  ))}
                </Box>
              )}

              {regions.length > 0 && (
                <Box>
                  <strong>Screenshot Hotspots (ui.region)</strong>
                  {regions.map((reg) => (
                    <Box key={reg.id} sx={{mt: 0.5, fontSize: '0.8125rem'}}>
                      {reg.name} ({reg.bounds.x}, {reg.bounds.y},{' '}
                      {reg.bounds.width}×{reg.bounds.height})
                    </Box>
                  ))}
                </Box>
              )}

              {bindings.length > 0 && (
                <Box>
                  <strong>Data &amp; Resource Bindings</strong>
                  {bindings.map((bnd) => (
                    <Box key={bnd.id} sx={{mt: 0.5, fontSize: '0.8125rem'}}>
                      <Box component="span">
                        [{bnd.state || 'unknown'}] {bnd.access_mode} →{' '}
                        {bnd.target_kind}:{bnd.target_ref}
                      </Box>
                      {bnd.state === 'suspect' &&
                        bnd.store_binding_id &&
                        !readOnly && (
                        <Box sx={{mt: 0.5}}>
                          <Button
                            size="small"
                            onClick={() =>
                              handleConfirmSuspect(
                                bnd.store_binding_id,
                                bnd.target_ref
                              )
                            }
                          >
                              Confirm Binding
                          </Button>
                        </Box>
                      )}
                    </Box>
                  ))}
                </Box>
              )}

              {navigations.length > 0 && (
                <Box>
                  <strong>Screen Navigation Links</strong>
                  {navigations.map((nav) => (
                    <Box key={nav.id} sx={{mt: 0.5, fontSize: '0.8125rem'}}>
                      {nav.label} ({nav.trigger} → {nav.action})
                    </Box>
                  ))}
                </Box>
              )}
            </Stack>
          </ScrollArea>
        )}

        {viewMode === 'field_spec' ? (
          <Box
            aria-label="Screen Mesh Field Specification Table"
            sx={{
              minHeight: 0,
              border: '1px solid',
              borderColor: 'divider',
              p: 1.5,
              display: 'flex',
              flexDirection: 'column',
              gap: 1,
              overflow: 'hidden',
              bgcolor: 'background.paper',
            }}
          >
            <FormReference formKey="screen-mesh-field-spec" />
            <Box
              sx={{
                display: 'flex',
                alignItems: 'flex-end',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: 1,
              }}
            >
              <Box sx={{minWidth: 240, flex: '1 1 260px', maxWidth: 380}}>
                <TextField
                  label="Filter field specification"
                  placeholder="Filter by screen, control, table.column or type…"
                  value={fieldSpecFilter}
                  onChange={(e) => setFieldSpecFilter(e.target.value)}
                />
              </Box>
              <Stack direction="row" gap="compact">
                <StatusBadge
                  status="information"
                  label={`${fieldSpecData?.summary?.total_fields ?? filteredSpecRows.length} total`}
                />
                <StatusBadge
                  status="success"
                  label={`${fieldSpecData?.summary?.bound_fields ?? 0} bound`}
                />
                {(fieldSpecData?.summary?.suspect_fields ?? 0) > 0 && (
                  <StatusBadge
                    status="warning"
                    label={`${fieldSpecData.summary.suspect_fields} suspect`}
                  />
                )}
                <Button
                  size="small"
                  onClick={async () => {
                    const spec = fieldSpecData || (await loadFieldSpec('markdown'));
                    if (spec) {
                      triggerBrowserDownload(
                        `${designId}-field-spec.md`,
                        spec.markdown,
                        'text/markdown'
                      );
                    }
                  }}
                >
                  Download Markdown
                </Button>
                <Button
                  size="small"
                  onClick={async () => {
                    const spec = fieldSpecData || (await loadFieldSpec('csv'));
                    if (spec) {
                      triggerBrowserDownload(
                        `${designId}-field-spec.csv`,
                        spec.csv,
                        'text/csv'
                      );
                    }
                  }}
                >
                  Download CSV
                </Button>
                <Button
                  size="small"
                  onClick={async () => {
                    const spec = fieldSpecData || (await loadFieldSpec('html'));
                    if (spec) {
                      triggerBrowserDownload(
                        `${designId}-field-spec.html`,
                        spec.html,
                        'text/html'
                      );
                    }
                  }}
                >
                  Download HTML
                </Button>
                <Button
                  size="small"
                  intent="primary"
                  onClick={() =>
                    setSpecPreviewModal({open: true, format: 'markdown'})
                  }
                >
                  Preview Spec…
                </Button>
              </Stack>
            </Box>

            <ScrollArea
              label="Joined field specification rows"
              sx={{flex: 1, minHeight: 0}}
            >
              {filteredSpecRows.length === 0 ? (
                <EmptyState message="No Screen Mesh fields matched the current filter." />
              ) : (
                <Box
                  component="table"
                  aria-label="Field Specification Table"
                  sx={{
                    width: '100%',
                    borderCollapse: 'collapse',
                    fontSize: '0.8125rem',
                  }}
                >
                  <Box component="thead">
                    <Box component="tr">
                      {[
                        'Screen',
                        'Control / Column / Region',
                        'Widget Kind',
                        'Target Table.Column',
                        'Type',
                        'Nullable',
                        'Binding Validity',
                      ].map((hdr) => (
                        <Box
                          key={hdr}
                          component="th"
                          scope="col"
                          sx={{
                            textAlign: 'left',
                            p: 0.75,
                            borderBottom: '1px solid',
                            borderColor: 'divider',
                            fontWeight: 600,
                          }}
                        >
                          {hdr}
                        </Box>
                      ))}
                    </Box>
                  </Box>
                  <Box component="tbody">
                    {filteredSpecRows.map((row, idx) => (
                      <Box key={`${row.element_id}-${idx}`} component="tr">
                        <Box
                          component="td"
                          sx={{
                            p: 0.75,
                            borderBottom: '1px solid',
                            borderColor: 'divider',
                          }}
                        >
                          {row.screen_title}
                        </Box>
                        <Box
                          component="td"
                          sx={{
                            p: 0.75,
                            borderBottom: '1px solid',
                            borderColor: 'divider',
                          }}
                        >
                          <strong>{row.label}</strong>
                        </Box>
                        <Box
                          component="td"
                          sx={{
                            p: 0.75,
                            borderBottom: '1px solid',
                            borderColor: 'divider',
                          }}
                        >
                          <code>{row.element_kind}</code> ({row.access_mode})
                        </Box>
                        <Box
                          component="td"
                          sx={{
                            p: 0.75,
                            borderBottom: '1px solid',
                            borderColor: 'divider',
                          }}
                        >
                          <code>{row.target_ref || '—'}</code>
                        </Box>
                        <Box
                          component="td"
                          sx={{
                            p: 0.75,
                            borderBottom: '1px solid',
                            borderColor: 'divider',
                          }}
                        >
                          {row.catalog_type || '—'}
                        </Box>
                        <Box
                          component="td"
                          sx={{
                            p: 0.75,
                            borderBottom: '1px solid',
                            borderColor: 'divider',
                          }}
                        >
                          {row.nullable === null || row.nullable === undefined
                            ? '—'
                            : row.nullable
                              ? 'YES'
                              : 'NO'}
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
                            status={bindingBadgeStatus(row.binding_state)}
                            label={row.binding_state}
                          />
                        </Box>
                      </Box>
                    ))}
                  </Box>
                </Box>
              )}
            </ScrollArea>
          </Box>
        ) : (
          <Box
            aria-label="Screen Mesh DDN canvas"
            sx={{
              minHeight: 0,
              border: '1px solid',
              borderColor: 'divider',
              overflow: 'hidden',
            }}
          >
            {viewerSnapshot && (
              <DDNViewerSurface
                snapshot={viewerSnapshot}
                showViewSelector={false}
                onExport={onExport}
                onError={onError}
              />
            )}
          </Box>
        )}
      </Box>

      <ProgressOverlay
        message={loading ? 'Loading Screen Mesh' : busyMessage}
      />

      {/* Shared Checkpoints & Diff Drawer */}
      <DesignCheckpointHistoryDrawer
        open={checkpointDrawerOpen}
        onClose={() => setCheckpointDrawerOpen(false)}
        client={client}
        projectId={projectId}
        designId={designId}
        currentVersion={sessionState.currentVersion}
        activeVersion={sessionState.activeVersion}
        onOpenVersion={(ver) => loadAll(ver)}
        onRestored={(newVer) => loadAll(newVer)}
      />

      {/* Shared Where Used Dialog */}
      <WhereUsedDialog
        open={whereUsedOpen}
        onClose={() => setWhereUsedOpen(false)}
        client={client}
        projectId={projectId}
        designId={designId}
        initialTargetRef={whereUsedSeed}
      />

      {/* Add Screen Dialog */}
      <Dialog
        open={screenDialogOpen}
        title="Add Screen (ui.frame)"
        onClose={() => setScreenDialogOpen(false)}
        defaultAction={handleAddScreen}
        actions={
          <>
            <Button onClick={() => setScreenDialogOpen(false)}>Cancel</Button>
            <Button intent="primary" onClick={handleAddScreen}>
              Add Screen
            </Button>
          </>
        }
      >
        <FormGrid columns={2}>
          <TextField
            label="Screen name"
            value={newScreen.name}
            onChange={(e) =>
              setNewScreen((cur) => ({...cur, name: e.target.value}))
            }
          />
          <TextField
            label="Form reference (optional SR-F code)"
            value={newScreen.formReference}
            onChange={(e) =>
              setNewScreen((cur) => ({...cur, formReference: e.target.value}))
            }
          />
          <NumberField
            label="Width (px)"
            value={newScreen.width}
            onChange={(e) =>
              setNewScreen((cur) => ({...cur, width: e.target.value}))
            }
          />
          <NumberField
            label="Height (px)"
            value={newScreen.height}
            onChange={(e) =>
              setNewScreen((cur) => ({...cur, height: e.target.value}))
            }
          />
        </FormGrid>
      </Dialog>

      {/* Add Wireframe Control Dialog (TypedRowsEditor — zero CSV/JSON textareas) */}
      <Dialog
        open={controlDialogOpen}
        size="large"
        title="Add Wireframe Control"
        onClose={() => setControlDialogOpen(false)}
        defaultAction={handleAddControl}
        actions={
          <>
            <Button onClick={() => setControlDialogOpen(false)}>Cancel</Button>
            <Button intent="primary" onClick={handleAddControl}>
              Add Control
            </Button>
          </>
        }
      >
        <DesignerModalTabs
          formKey="screen-mesh-workspace"
          activeTab={controlModalTab}
          onTabChange={setControlModalTab}
          minHeight={240}
          tabs={[
            {
              id: 'general',
              label: 'Control & Data Binding',
              render: () => (
                <Stack gap="standard">
                  <FormGrid columns={2}>
                    <Select
                      label="Target screen"
                      options={screenOptions}
                      value={newControl.screenId}
                      onChange={(val) =>
                        setNewControl((cur) => ({...cur, screenId: val}))
                      }
                    />
                    <Select
                      label="Control role"
                      options={SCREEN_MESH_CONTROL_ROLE_OPTIONS}
                      value={newControl.role}
                      onChange={(val) =>
                        setNewControl((cur) => ({...cur, role: val}))
                      }
                    />
                    <TextField
                      label="Control label"
                      value={newControl.name}
                      onChange={(e) =>
                        setNewControl((cur) => ({...cur, name: e.target.value}))
                      }
                    />
                    {newControl.role === 'ui.input' && (
                      <TextField
                        label="Placeholder"
                        value={newControl.placeholder}
                        onChange={(e) =>
                          setNewControl((cur) => ({
                            ...cur,
                            placeholder: e.target.value,
                          }))
                        }
                      />
                    )}
                    {['ui.checkbox', 'ui.radio'].includes(newControl.role) && (
                      <Box sx={{pt: 2.25}}>
                        <Checkbox
                          label="Checked by default"
                          checked={newControl.checked}
                          onChange={(checked) =>
                            setNewControl((cur) => ({...cur, checked}))
                          }
                        />
                      </Box>
                    )}
                  </FormGrid>
                  <FormGrid columns={3}>
                    <Select
                      label="Bind target kind"
                      options={SCREEN_MESH_BINDING_KIND_OPTIONS}
                      value={newControl.targetKind}
                      onChange={(val) =>
                        setNewControl((cur) => ({...cur, targetKind: val}))
                      }
                    />
                    <TextField
                      label="Optional target reference"
                      placeholder="e.g. sales.orders.customer_id"
                      value={newControl.targetRef}
                      onChange={(e) =>
                        setNewControl((cur) => ({
                          ...cur,
                          targetRef: e.target.value,
                        }))
                      }
                    />
                    <Select
                      label="Access mode"
                      options={SCREEN_MESH_ACCESS_OPTIONS}
                      value={newControl.accessMode}
                      onChange={(val) =>
                        setNewControl((cur) => ({...cur, accessMode: val}))
                      }
                    />
                  </FormGrid>
                </Stack>
              ),
            },
            ...(newControl.role === 'ui.grid'
              ? [
                {
                  id: 'grid_columns',
                  label: 'Grid Columns',
                  render: () => (
                    <TypedRowsEditor
                      label="Grid Columns"
                      addLabel="Add Column"
                      reorderable
                      rows={newControl.gridColumns}
                      onChange={(rows) =>
                        setNewControl((cur) => ({...cur, gridColumns: rows}))
                      }
                      columns={[
                        {
                          key: 'col_id',
                          label: 'Column ID',
                          placeholder: 'order_id',
                          minWidth: 110,
                        },
                        {
                          key: 'label',
                          label: 'Header Label',
                          placeholder: 'Order ID',
                          minWidth: 140,
                        },
                        {
                          key: 'target_ref',
                          label: 'Bound Column Ref',
                          placeholder: 'sales.orders.id',
                          minWidth: 160,
                        },
                        {
                          key: 'width',
                          label: 'Width (px)',
                          type: 'number',
                          default: 140,
                          minWidth: 90,
                        },
                      ]}
                    />
                  ),
                },
              ]
              : []),
            ...(['ui.dropdown', 'ui.radio', 'ui.tabs', 'ui.list'].includes(
              newControl.role
            )
              ? [
                {
                  id: 'choices',
                  label: 'Choices / Tabs',
                  render: () => (
                    <TypedRowsEditor
                      label="Choices / Tab Labels"
                      addLabel="Add Choice"
                      reorderable
                      rows={newControl.choiceRows}
                      onChange={(rows) =>
                        setNewControl((cur) => ({...cur, choiceRows: rows}))
                      }
                      columns={[
                        {
                          key: 'option',
                          label: 'Choice / Tab Label',
                          placeholder: 'Summary',
                          minWidth: 220,
                        },
                      ]}
                    />
                  ),
                },
              ]
              : []),
          ]}
        />
      </Dialog>

      {/* Interactive Draw / Edit Regions Dialog (SR-F-030021) */}
      <Dialog
        open={regionDialogOpen}
        size="large"
        title="Draw & Edit Screenshot Regions (ui.region)"
        onClose={() => setRegionDialogOpen(false)}
        defaultAction={handleApplyRegions}
        actions={
          <>
            <Button onClick={() => setRegionDialogOpen(false)}>Cancel</Button>
            <Button intent="primary" onClick={handleApplyRegions}>
              Apply Regions
            </Button>
          </>
        }
      >
        <Stack gap="standard">
          <FormReference formKey="screen-mesh-screenshot" />
          <FormGrid columns={2}>
            <Select
              label="Target screen"
              options={screenOptions}
              value={regionDraftScreenId}
              onChange={(val) => {
                setRegionDraftScreenId(val);
                const rowsForScr = regions
                  .filter((r) => r.screen_id === val)
                  .map((r) => ({
                    id: r.id,
                    name: r.name,
                    x: r.bounds.x,
                    y: r.bounds.y,
                    width: r.bounds.width,
                    height: r.bounds.height,
                    kind_hint: r.kind_hint || '',
                    target_ref:
                      bindings.find((b) => b.source_id === r.id)?.target_ref ||
                      '',
                  }));
                setRegionRows(rowsForScr);
              }}
            />
          </FormGrid>

          <ScreenshotRubberBandCanvas
            label="Draw screenshot hotspot region"
            imageSrc={screenshotUrlForScreen(regionDialogScreen)}
            screenWidth={regionDialogScreen?.width || 960}
            screenHeight={regionDialogScreen?.height || 640}
            boxes={regionRows}
            boxTone="region"
            onDrawBox={(rect) =>
              setRegionRows((cur) => [
                ...cur,
                {
                  name: `Hotspot ${cur.length + 1}`,
                  x: rect.x,
                  y: rect.y,
                  width: rect.width,
                  height: rect.height,
                  kind_hint: '',
                  target_ref: '',
                },
              ])
            }
          />

          <TypedRowsEditor
            label="Hotspot Regions"
            addLabel="Add Region"
            rows={regionRows}
            onChange={setRegionRows}
            columns={[
              {
                key: 'name',
                label: 'Region Name',
                placeholder: 'Footer Totals Hotspot',
                default: 'New Hotspot',
                minWidth: 140,
              },
              {key: 'x', label: 'X', type: 'number', default: 24, minWidth: 64},
              {key: 'y', label: 'Y', type: 'number', default: 24, minWidth: 64},
              {
                key: 'width',
                label: 'Width',
                type: 'number',
                default: 200,
                minWidth: 74,
              },
              {
                key: 'height',
                label: 'Height',
                type: 'number',
                default: 56,
                minWidth: 74,
              },
              {
                key: 'kind_hint',
                label: 'Trace Widget Hint',
                type: 'select',
                options: SCREEN_MESH_REGION_HINT_OPTIONS,
                default: '',
                minWidth: 130,
              },
              {
                key: 'target_ref',
                label: 'Target Ref',
                placeholder: 'sales.orders.total',
                minWidth: 140,
              },
            ]}
          />
        </Stack>
      </Dialog>

      {/* Add Binding Dialog */}
      <Dialog
        open={bindingDialogOpen}
        title="Bind Control or Region to Data"
        onClose={() => setBindingDialogOpen(false)}
        defaultAction={handleAddBinding}
        actions={
          <>
            <Button onClick={() => setBindingDialogOpen(false)}>Cancel</Button>
            <Button intent="primary" onClick={handleAddBinding}>
              Add Binding
            </Button>
          </>
        }
      >
        <FormGrid columns={2}>
          <Select
            label="Source element"
            options={bindableSourceOptions}
            value={newBinding.sourceId}
            onChange={(val) =>
              setNewBinding((cur) => ({...cur, sourceId: val}))
            }
          />
          <TextField
            label="Grid column ID (optional)"
            value={newBinding.columnId}
            onChange={(e) =>
              setNewBinding((cur) => ({...cur, columnId: e.target.value}))
            }
          />
          <Select
            label="Target kind"
            options={SCREEN_MESH_BINDING_KIND_OPTIONS}
            value={newBinding.targetKind}
            onChange={(val) =>
              setNewBinding((cur) => ({...cur, targetKind: val}))
            }
          />
          <Select
            label="Access mode"
            options={SCREEN_MESH_ACCESS_OPTIONS}
            value={newBinding.accessMode}
            onChange={(val) =>
              setNewBinding((cur) => ({...cur, accessMode: val}))
            }
          />
          <TextField
            label="Target reference (e.g. sales.orders.customer_id)"
            value={newBinding.targetRef}
            onChange={(e) =>
              setNewBinding((cur) => ({...cur, targetRef: e.target.value}))
            }
          />
        </FormGrid>
      </Dialog>

      {/* Add Navigation Dialog */}
      <Dialog
        open={navDialogOpen}
        title="Add Screen-to-Screen Navigation"
        onClose={() => setNavDialogOpen(false)}
        defaultAction={handleAddNavigation}
        actions={
          <>
            <Button onClick={() => setNavDialogOpen(false)}>Cancel</Button>
            <Button intent="primary" onClick={handleAddNavigation}>
              Add Navigation
            </Button>
          </>
        }
      >
        <FormGrid columns={2}>
          <Select
            label="From control or region"
            options={bindableSourceOptions}
            value={newNav.fromId}
            onChange={(val) => setNewNav((cur) => ({...cur, fromId: val}))}
          />
          <Select
            label="Destination screen"
            options={screenOptions}
            value={newNav.toScreenId}
            onChange={(val) => setNewNav((cur) => ({...cur, toScreenId: val}))}
          />
          <Select
            label="Trigger"
            options={SCREEN_MESH_TRIGGER_OPTIONS}
            value={newNav.trigger}
            onChange={(val) => setNewNav((cur) => ({...cur, trigger: val}))}
          />
          <Select
            label="Bounded non-executable action"
            options={SCREEN_MESH_ACTION_OPTIONS}
            value={newNav.action}
            onChange={(val) => setNewNav((cur) => ({...cur, action: val}))}
          />
          <TextField
            label="Flow label"
            value={newNav.label}
            onChange={(e) =>
              setNewNav((cur) => ({...cur, label: e.target.value}))
            }
          />
        </FormGrid>
      </Dialog>

      {/* Upload Screenshot Dialog (File Picker + Drag/Drop + Sample Generator — ZERO Base64 TextArea) */}
      <Dialog
        open={screenshotDialogOpen}
        size="medium"
        title="Upload Screenshot (PNG / JPEG / WebP)"
        onClose={() => setScreenshotDialogOpen(false)}
        actions={
          <>
            <Button onClick={() => setScreenshotDialogOpen(false)}>
              Cancel
            </Button>
            <Button intent="primary" onClick={handleUploadScreenshot}>
              Upload Screenshot
            </Button>
          </>
        }
      >
        <Stack gap="standard">
          <FormReference formKey="screen-mesh-screenshot" />
          <FormGrid columns={2}>
            <Select
              label="Target screen"
              options={screenOptions}
              value={screenshotForm.screenId}
              onChange={(val) =>
                setScreenshotForm((cur) => ({...cur, screenId: val}))
              }
            />
            <Select
              label="Media type"
              options={[
                {value: 'image/png', label: 'PNG (image/png)'},
                {value: 'image/jpeg', label: 'JPEG (image/jpeg)'},
                {value: 'image/webp', label: 'WebP (image/webp)'},
              ]}
              value={screenshotForm.mediaType}
              onChange={(val) =>
                setScreenshotForm((cur) => ({...cur, mediaType: val}))
              }
            />
          </FormGrid>
          <ScreenshotFileDropzone
            label="Screenshot image"
            inputLabel="Choose screenshot image file"
            sampleLabel="Use Sample Form Screenshot"
            sampleDataUrl={SAMPLE_FORM_PNG_DATA_URL}
            fileName={screenshotForm.fileName}
            dataUrl={screenshotForm.dataUrl}
            onLoaded={({dataUrl, mediaType, fileName}) =>
              setScreenshotForm((cur) => ({
                ...cur,
                dataUrl,
                mediaType,
                fileName,
              }))
            }
            onError={(err) => setError(err.message)}
          />
        </Stack>
      </Dialog>

      {/* Destructive Redact Screenshot Regions Dialog (SR-F-030021 / F4) */}
      <Dialog
        open={redactDialogOpen}
        size="large"
        title="Destructively Redact Sensitive Screenshot Regions"
        onClose={() => setRedactDialogOpen(false)}
        actions={
          <>
            <Button onClick={() => setRedactDialogOpen(false)}>Cancel</Button>
            <Button intent="danger" onClick={handleRedactScreenshot}>
              Redact &amp; Purge Original
            </Button>
          </>
        }
      >
        <Stack gap="standard">
          <FormReference formKey="screen-mesh-screenshot" />
          <Banner status="warning">
            Irreversible operation: redacting overwrites pixels in the screenshot
            and purges the unredacted image bytes from <code>asset_blob</code> in{' '}
            <code>designs.db</code>.
          </Banner>
          <FormGrid columns={2}>
            <Select
              label="Target screen"
              options={screenOptions}
              value={redactScreenId}
              onChange={setRedactScreenId}
            />
          </FormGrid>
          <ScreenshotRubberBandCanvas
            label="Draw destructive redaction box"
            imageSrc={screenshotUrlForScreen(redactDialogScreen)}
            screenWidth={redactDialogScreen?.width || 960}
            screenHeight={redactDialogScreen?.height || 640}
            boxes={redactRows}
            boxTone="redact"
            onDrawBox={(rect) =>
              setRedactRows((cur) => [
                ...cur,
                {
                  x: rect.x,
                  y: rect.y,
                  width: rect.width,
                  height: rect.height,
                },
              ])
            }
          />
          <TypedRowsEditor
            label="Redaction Boxes"
            addLabel="Add Redaction Box"
            rows={redactRows}
            onChange={setRedactRows}
            columns={[
              {key: 'x', label: 'X', type: 'number', default: 16, minWidth: 80},
              {key: 'y', label: 'Y', type: 'number', default: 16, minWidth: 80},
              {
                key: 'width',
                label: 'Width',
                type: 'number',
                default: 160,
                minWidth: 96,
              },
              {
                key: 'height',
                label: 'Height',
                type: 'number',
                default: 40,
                minWidth: 96,
              },
            ]}
          />
        </Stack>
      </Dialog>

      {/* Trace Screenshot Regions as Mesh Dialog (SR-F-030021) */}
      <Dialog
        open={traceDialogOpen}
        size="large"
        title="Trace Screenshot Regions as Wireframe Mesh"
        onClose={() => setTraceDialogOpen(false)}
        actions={
          <>
            <Button onClick={() => setTraceDialogOpen(false)}>Cancel</Button>
            <Button intent="primary" onClick={handleTraceScreenshotToMesh}>
              Trace Regions to Mesh
            </Button>
          </>
        }
      >
        <Stack gap="standard">
          <FormReference formKey="screen-mesh-screenshot" />
          <FormGrid columns={2}>
            <Select
              label="Source screenshot screen"
              options={screenOptions}
              value={traceForm.sourceScreenId}
              onChange={(val) =>
                setTraceForm((cur) => ({
                  ...cur,
                  sourceScreenId: val,
                  hintRows: regions
                    .filter((r) => r.screen_id === val)
                    .map((r) => ({
                      region_id: r.id,
                      region_name: r.name,
                      kind_hint: r.kind_hint || '',
                    })),
                }))
              }
            />
            <Box sx={{pt: 2.25}}>
              <Checkbox
                label="Link navigation from source screen to traced mesh"
                checked={Boolean(traceForm.linkNavigation)}
                onChange={(checked) =>
                  setTraceForm((cur) => ({...cur, linkNavigation: checked}))
                }
              />
            </Box>
          </FormGrid>
          <TypedRowsEditor
            label="Region Widget Inference Overrides"
            addLabel="Add Hint"
            rows={traceForm.hintRows}
            onChange={(rows) =>
              setTraceForm((cur) => ({...cur, hintRows: rows}))
            }
            columns={[
              {
                key: 'region_name',
                label: 'Region Hotspot',
                minWidth: 180,
              },
              {
                key: 'kind_hint',
                label: 'Target Control Role',
                type: 'select',
                options: SCREEN_MESH_REGION_HINT_OPTIONS,
                minWidth: 200,
              },
            ]}
          />
        </Stack>
      </Dialog>

      {/* Compare Newer Screenshot Dialog (SR-F-030021) */}
      <Dialog
        open={compareDialogOpen}
        size="large"
        title="Compare With Newer Screenshot"
        onClose={() => setCompareDialogOpen(false)}
        actions={
          <>
            <Button onClick={() => setCompareDialogOpen(false)}>Close</Button>
            <Button intent="primary" onClick={handleCompareScreenshots}>
              Compare Screenshots
            </Button>
          </>
        }
      >
        <Stack gap="standard">
          <FormReference formKey="screen-mesh-screenshot" />
          <FormGrid columns={2}>
            <Select
              label="Screen with baseline screenshot"
              options={screenOptions}
              value={compareForm.screenId}
              onChange={(val) =>
                setCompareForm((cur) => ({...cur, screenId: val}))
              }
            />
            <Box sx={{pt: 2.25}}>
              <Checkbox
                label="Replace stored screenshot in a new checkpoint"
                checked={Boolean(compareForm.replaceScreenshot)}
                onChange={(checked) =>
                  setCompareForm((cur) => ({
                    ...cur,
                    replaceScreenshot: checked,
                  }))
                }
              />
            </Box>
          </FormGrid>
          <ScreenshotFileDropzone
            label="Newer screenshot image"
            inputLabel="Choose newer screenshot image file"
            sampleLabel="Use Sample Updated Screenshot"
            sampleDataUrl={SAMPLE_UPDATED_PNG_DATA_URL}
            fileName={compareForm.fileName}
            dataUrl={compareForm.dataUrl}
            onLoaded={({dataUrl, mediaType, fileName}) =>
              setCompareForm((cur) => ({
                ...cur,
                dataUrl,
                mediaType,
                fileName,
              }))
            }
            onError={(err) => setError(err.message)}
          />
          {compareResult && (
            <Stack gap="compact">
              <Stack direction="row" gap="compact">
                <StatusBadge
                  status={
                    compareResult.dimension_changed ? 'warning' : 'success'
                  }
                  label={`${compareResult.old_dimensions?.width}×${compareResult.old_dimensions?.height} → ${compareResult.new_dimensions?.width}×${compareResult.new_dimensions?.height}`}
                />
                <StatusBadge
                  status="information"
                  label={`Changed pixels: ${(Number(compareResult.changed_pixel_ratio || 0) * 100).toFixed(1)}%`}
                />
                <StatusBadge
                  status="neutral"
                  label={`Diff boxes: ${(compareResult.diff_bounding_boxes || []).length}`}
                />
              </Stack>
              {(compareResult.affected_regions || []).length > 0 && (
                <Box
                  component="table"
                  aria-label="Affected screenshot regions"
                  sx={{
                    width: '100%',
                    borderCollapse: 'collapse',
                    fontSize: '0.8125rem',
                  }}
                >
                  <Box component="thead">
                    <Box component="tr">
                      {['Region', 'Overlap', 'Out of Bounds', 'Recommendation'].map(
                        (h) => (
                          <Box
                            key={h}
                            component="th"
                            sx={{
                              textAlign: 'left',
                              p: 0.5,
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
                    {compareResult.affected_regions.map((ar) => (
                      <Box key={ar.region_id} component="tr">
                        <Box component="td" sx={{p: 0.5}}>
                          {ar.name}
                        </Box>
                        <Box component="td" sx={{p: 0.5}}>
                          {(Number(ar.overlap_ratio || 0) * 100).toFixed(1)}%
                        </Box>
                        <Box component="td" sx={{p: 0.5}}>
                          {ar.out_of_bounds ? 'Yes' : 'No'}
                        </Box>
                        <Box component="td" sx={{p: 0.5}}>
                          <StatusBadge
                            status={
                              ar.recommendation === 'review_bounds'
                                ? 'warning'
                                : 'success'
                            }
                            label={ar.recommendation}
                          />
                        </Box>
                      </Box>
                    ))}
                  </Box>
                </Box>
              )}
            </Stack>
          )}
        </Stack>
      </Dialog>

      {/* Suspect Bindings Dialog */}
      <Dialog
        open={suspectDialogOpen}
        size="medium"
        title="Review Suspect Screen Mesh Bindings"
        onClose={() => setSuspectDialogOpen(false)}
        actions={
          <Button onClick={() => setSuspectDialogOpen(false)}>Close</Button>
        }
      >
        <Stack gap="standard">
          {bindings.filter((b) => b.state === 'suspect').length === 0 ? (
            <EmptyState message="All Screen Mesh data bindings are currently valid or confirmed." />
          ) : (
            bindings
              .filter((b) => b.state === 'suspect')
              .map((b) => (
                <Box
                  key={b.id}
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 1,
                    p: 1,
                    border: '1px solid',
                    borderColor: 'divider',
                  }}
                >
                  <Box sx={{fontSize: '0.8125rem'}}>
                    <strong>{b.target_kind}:</strong> <code>{b.target_ref}</code>
                  </Box>
                  {!readOnly && b.store_binding_id && (
                    <Button
                      size="small"
                      intent="primary"
                      onClick={() =>
                        handleConfirmSuspect(b.store_binding_id, b.target_ref)
                      }
                    >
                      Confirm Binding
                    </Button>
                  )}
                </Box>
              ))
          )}
        </Stack>
      </Dialog>

      {/* Field Specification Export & Preview Modal (SR-F-030022) */}
      <Dialog
        open={specPreviewModal.open}
        size="large"
        title="Export Field Specification (Markdown / CSV / HTML)"
        onClose={() => setSpecPreviewModal((cur) => ({...cur, open: false}))}
        actions={
          <>
            <Button
              onClick={() => {
                const fmt = specPreviewModal.format;
                const ext = fmt === 'markdown' ? 'md' : fmt;
                const content =
                  fmt === 'csv'
                    ? fieldSpecData?.csv
                    : fmt === 'html'
                      ? fieldSpecData?.html
                      : fieldSpecData?.markdown;
                triggerBrowserDownload(
                  `${designId}-field-spec.${ext}`,
                  content || '',
                  fmt === 'html'
                    ? 'text/html'
                    : fmt === 'csv'
                      ? 'text/csv'
                      : 'text/markdown'
                );
              }}
            >
              Download Selected Format
            </Button>
            <Button
              intent="primary"
              onClick={() =>
                setSpecPreviewModal((cur) => ({...cur, open: false}))
              }
            >
              Close
            </Button>
          </>
        }
      >
        <Stack gap="standard">
          <FormReference formKey="screen-mesh-field-spec" />
          <FormGrid columns={2}>
            <Select
              label="Specification export format"
              options={[
                {value: 'markdown', label: 'Markdown (.md)'},
                {value: 'csv', label: 'CSV (.csv)'},
                {value: 'html', label: 'HTML (.html)'},
              ]}
              value={specPreviewModal.format}
              onChange={(val) =>
                setSpecPreviewModal((cur) => ({...cur, format: val}))
              }
            />
          </FormGrid>
          <Box sx={{minHeight: 260}}>
            <CodeEditor
              label="Formatted Field Specification Preview"
              value={
                specPreviewModal.format === 'csv'
                  ? fieldSpecData?.csv || ''
                  : specPreviewModal.format === 'html'
                    ? fieldSpecData?.html || ''
                    : fieldSpecData?.markdown || ''
              }
              readonly
              language="sql"
            />
          </Box>
        </Stack>
      </Dialog>

      {/* Exported DDN Preview Modal */}
      <Dialog
        open={ddnExportModal.open}
        size="large"
        title="Exported Screen Mesh DDN (wireframe.ui@1)"
        onClose={() => setDdnExportModal({open: false, ddnText: ''})}
        actions={
          <Button onClick={() => setDdnExportModal({open: false, ddnText: ''})}>
            Close
          </Button>
        }
      >
        <Box sx={{minHeight: 260}}>
          <CodeEditor
            label="Exported DDN Source"
            value={ddnExportModal.ddnText}
            readonly
            language="sql"
          />
        </Box>
      </Dialog>

      {/* Import SR-F Form Modal (SR-F-030023) */}
      <Dialog
        open={importDialogOpen}
        size="large"
        title="Import ScratchRobin SR-F UI Descriptor Form"
        onClose={() => setImportDialogOpen(false)}
        actions={
          <>
            <Button onClick={() => setImportDialogOpen(false)}>Cancel</Button>
            <Button intent="primary" onClick={handleImportDescriptorForm}>
              Import SR-F Form
            </Button>
          </>
        }
      >
        <Stack gap="standard">
          <FormReference formKey="screen-mesh-import" />
          <FormGrid columns={2}>
            {descriptorForms.length > 0 ? (
              <Select
                label="SR-F UI descriptor form"
                options={descriptorForms.map((item) => ({
                  value: item.form_reference,
                  label: `${item.form_reference} — ${item.engine}/${item.form_key}`,
                }))}
                value={importForm.selectedRef}
                onChange={(val) =>
                  setImportForm((cur) => ({...cur, selectedRef: val}))
                }
              />
            ) : (
              <TextField
                label="SR-F form reference (e.g. SR-F-020073)"
                value={importForm.customRef}
                onChange={(e) =>
                  setImportForm((cur) => ({...cur, customRef: e.target.value}))
                }
              />
            )}
          </FormGrid>
          <TypedRowsEditor
            label="Optional QA Regions"
            addLabel="Add QA Region"
            rows={importForm.qaRegions}
            onChange={(rows) =>
              setImportForm((cur) => ({...cur, qaRegions: rows}))
            }
            columns={[
              {
                key: 'name',
                label: 'Region Name',
                placeholder: 'Header Fields',
                minWidth: 160,
              },
              {key: 'x', label: 'X', type: 'number', default: 20, minWidth: 72},
              {key: 'y', label: 'Y', type: 'number', default: 20, minWidth: 72},
              {
                key: 'width',
                label: 'Width',
                type: 'number',
                default: 260,
                minWidth: 84,
              },
              {
                key: 'height',
                label: 'Height',
                type: 'number',
                default: 80,
                minWidth: 84,
              },
            ]}
          />
        </Stack>
      </Dialog>

      {/* Accept Dialog */}
      <Dialog
        open={acceptDialogOpen}
        title="Accept Screen Mesh Version"
        onClose={() => setAcceptDialogOpen(false)}
        actions={
          <>
            <Button onClick={() => setAcceptDialogOpen(false)}>Cancel</Button>
            <Button intent="primary" onClick={handleAccept}>
              Accept Version
            </Button>
          </>
        }
      >
        <FormGrid columns={2}>
          <Box sx={{pt: 0.5}}>
            <Checkbox
              label="Require Git review reference"
              checked={acceptForm.requireGitReview}
              onChange={(checked) =>
                setAcceptForm((cur) => ({...cur, requireGitReview: checked}))
              }
            />
          </Box>
          <TextField
            label="Approval comment"
            value={acceptForm.comment}
            onChange={(e) =>
              setAcceptForm((cur) => ({...cur, comment: e.target.value}))
            }
          />
          {acceptForm.requireGitReview && (
            <TextField
              label="Git review reference"
              value={acceptForm.gitReviewRef}
              onChange={(e) =>
                setAcceptForm((cur) => ({
                  ...cur,
                  gitReviewRef: e.target.value,
                }))
              }
            />
          )}
        </FormGrid>
      </Dialog>

      {/* Git Sync Dialog */}
      <Dialog
        open={gitDialogOpen}
        title="Screen Mesh Git Sync"
        onClose={() => setGitDialogOpen(false)}
        actions={
          <>
            <Button onClick={() => setGitDialogOpen(false)}>Close</Button>
            <Button intent="primary" onClick={handleGitSync}>
              Run Git Action
            </Button>
          </>
        }
      >
        <FormGrid columns={2}>
          <Select
            label="Git action"
            options={[
              {value: 'save', label: 'Save DDN to Git'},
              {value: 'load', label: 'Load DDN from Git'},
              {value: 'drift', label: 'Check Git Drift'},
            ]}
            value={gitForm.action}
            onChange={(val) => setGitForm((cur) => ({...cur, action: val}))}
          />
          <TextField
            label="Branch"
            value={gitForm.branch}
            onChange={(e) =>
              setGitForm((cur) => ({...cur, branch: e.target.value}))
            }
          />
          <TextField
            label="Repository root"
            value={gitForm.repoRoot}
            onChange={(e) =>
              setGitForm((cur) => ({...cur, repoRoot: e.target.value}))
            }
          />
          <TextField
            label="Relative DDN path"
            value={gitForm.path}
            onChange={(e) =>
              setGitForm((cur) => ({...cur, path: e.target.value}))
            }
          />
        </FormGrid>
      </Dialog>
    </Box>
  );
}

ScreenMeshDesignerSurface.propTypes = {
  projectId: PropTypes.string.isRequired,
  designId: PropTypes.string.isRequired,
  client: PropTypes.object,
  controller: PropTypes.object,
  readOnly: PropTypes.bool,
  executeCommand: PropTypes.func,
  onStateChange: PropTypes.func,
  onExport: PropTypes.func,
  onError: PropTypes.func,
};
