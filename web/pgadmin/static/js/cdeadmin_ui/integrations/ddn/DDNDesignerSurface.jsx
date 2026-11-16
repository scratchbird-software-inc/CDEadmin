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
import {Box} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {TextArea} from '../../primitives/Field';
import {Banner} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import {
  ddnAssetPayload,
  validateDDNAssetRef,
  validateDDNFiles,
  validateDDNSnapshot,
} from './contracts';
import {DDNViewerSurface} from './DDNViewerSurface';
import {
  buildLocalFallbackScene,
  serializeRobinSceneToSvg,
} from './RobinTiledCanvas';

const LABELS = Object.freeze({
  clean: 'Saved',
  dirty: 'Unsaved changes',
  saving: 'Saving',
  'saved-newer-edits': 'Saved; newer changes remain',
  'save-failed': 'Save failed',
  'external-conflict': 'External conflict',
});

function applyPinnedPositionToDdn(ddnText, nodeId, x, y) {
  const safeId = String(nodeId || '').replace(/"/g, '\\"');
  const rx = Math.round(Number(x) * 100) / 100;
  const ry = Math.round(Number(y) * 100) / 100;
  const lines = String(ddnText || '').split(/\r?\n/);

  // Remove any previous layout x_record for this subject id if inside a scratchrobin.layout block
  const recordBlock = [
    '',
    'data "scratchrobin_pins" from "inline"',
    '    with',
    '        id "scratchrobin_pins"',
    '    x_record',
    '        with',
    `            subject_id "${safeId}"`,
    `            layout_x "${rx}"`,
    `            layout_y "${ry}"`,
    '            layout_pinned "true"',
  ].join('\n');

  if (ddnText.includes(`subject_id "${safeId}"`)) {
    const subIdx = lines.findIndex((ln) =>
      ln.includes(`subject_id "${safeId}"`)
    );
    if (subIdx >= 0) {
      for (let i = subIdx + 1; i < Math.min(lines.length, subIdx + 6); i += 1) {
        if (lines[i].trim().startsWith('layout_x ')) {
          lines[i] = `            layout_x "${rx}"`;
        } else if (lines[i].trim().startsWith('layout_y ')) {
          lines[i] = `            layout_y "${ry}"`;
        } else if (lines[i].trim().startsWith('layout_pinned ')) {
          lines[i] = '            layout_pinned "true"';
        }
      }
      return lines.join('\n');
    }
  }
  return `${String(ddnText || '').trimEnd()}\n${recordBlock}\n`;
}

/**
 * ScratchRobin Native DDN Designer Surface.
 * Replaces the proof-of-concept `@ddn/standalone` designer with ScratchRobin's
 * own host-tiled interactive canvas, node drag-to-pin, optional split DDN source
 * editor, and coherent `cdeadmin.ddn-asset.v1` persistence.
 */
export function DDNDesignerSurface(props) {
  const {
    files,
    snapshot,
    assetRef,
    readOnly = false,
    saveAsset,
    executeCommand,
    onExport,
  } = props;

  const callbacks = useRef(props);
  callbacks.current = props;

  const initialSeed = useMemo(() => {
    if (snapshot) {
      const validated = validateDDNSnapshot(snapshot);
      return {
        files: {...validated.files},
        entry: validated.entry,
        view: validated.view,
      };
    }
    const validatedFiles = validateDDNFiles(files || {'model.ddn': 'version ddn-next-1\n'});
    const entryName = Object.keys(validatedFiles)[0];
    const parsed = buildLocalFallbackScene(validatedFiles[entryName] || '');
    return {
      files: {...validatedFiles},
      entry: entryName,
      view: parsed.view_id || 'main',
    };
  }, [files, snapshot]);

  const [draftFiles, setDraftFiles] = useState(initialSeed.files);
  const [activeEntry, setActiveEntry] = useState(initialSeed.entry);
  const [activeView, setActiveView] = useState(initialSeed.view);
  const [persistence, setPersistence] = useState('clean');
  const [error, setError] = useState(null);
  const [ready, setReady] = useState(false);
  const [showSource, setShowSource] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState('');

  const assetRefState = useRef(
    assetRef ? validateDDNAssetRef(assetRef) : null
  );
  const latestRef = useRef({
    files: initialSeed.files,
    entry: initialSeed.entry,
    view: initialSeed.view,
    persistence: 'clean',
    lastSvg: '',
    revision: 1,
  });

  useEffect(() => {
    assetRefState.current = assetRef ? validateDDNAssetRef(assetRef) : null;
  }, [assetRef]);

  useEffect(() => {
    setDraftFiles(initialSeed.files);
    setActiveEntry(initialSeed.entry);
    setActiveView(initialSeed.view);
    setPersistence('clean');
    setError(null);
    latestRef.current = {
      files: initialSeed.files,
      entry: initialSeed.entry,
      view: initialSeed.view,
      persistence: 'clean',
      lastSvg: '',
      revision: 1,
    };
  }, [initialSeed]);

  const controller = useMemo(() => {
    const subscribers = new Set();
    const buildSnap = () =>
      validateDDNSnapshot({
        format: 'ddn-source-workspace@1',
        entry: latestRef.current.entry,
        view: latestRef.current.view,
        files: {...latestRef.current.files},
      });
    const buildState = () =>
      Object.freeze({
        entry: latestRef.current.entry,
        view: latestRef.current.view,
        revision: latestRef.current.revision,
        readOnly: Boolean(readOnly),
        persistence: latestRef.current.persistence,
      });
    const notify = (evt) => {
      const st = buildState();
      for (const fn of subscribers) fn(st, evt);
      callbacks.current.onStateChange?.(st);
    };

    return {
      subscribe(fn) {
        if (typeof fn !== 'function') {
          throw new TypeError('Designer listener must be a function.');
        }
        subscribers.add(fn);
        return () => subscribers.delete(fn);
      },
      state: buildState,
      getFiles: () => ({...latestRef.current.files}),
      getSnapshot: buildSnap,
      isDirty: () => latestRef.current.persistence === 'dirty',
      async snapshot() {
        return buildSnap();
      },
      async beforeClose() {
        return latestRef.current.persistence === 'dirty';
      },
      async exportSVG() {
        if (latestRef.current.lastSvg) return latestRef.current.lastSvg;
        const text =
          latestRef.current.files[latestRef.current.entry] || '';
        const local = buildLocalFallbackScene(text, latestRef.current.view);
        return serializeRobinSceneToSvg(local, local.loaded_tiles);
      },
      async save(authorityFn) {
        const fn = authorityFn || callbacks.current.saveAsset;
        if (typeof fn !== 'function') {
          throw new TypeError('Asset save authority must be a function.');
        }
        const currentAsset = assetRefState.current;
        if (!currentAsset) {
          throw new Error('Designer session is not bound to an AssetRef.');
        }
        latestRef.current.persistence = 'saving';
        setPersistence('saving');
        setError(null);
        notify({type: 'saving'});
        try {
          const captured = buildSnap();
          const rev = latestRef.current.revision;
          const res = await fn(ddnAssetPayload(currentAsset, captured), {
            expectedAssetVersion: currentAsset.assetVersion,
            sourceRevision: rev,
          });
          if (res?.assetRef) {
            assetRefState.current = validateDDNAssetRef(res.assetRef);
          }
          const newerEdits = latestRef.current.revision !== rev;
          const nextState = newerEdits ? 'saved-newer-edits' : 'clean';
          latestRef.current.persistence = nextState;
          setPersistence(nextState);
          notify({type: 'saved', revision: rev, result: res});
          return res;
        } catch (saveErr) {
          const failState =
            saveErr?.code === 'asset_conflict'
              ? 'external-conflict'
              : 'save-failed';
          latestRef.current.persistence = failState;
          setPersistence(failState);
          setError(saveErr);
          notify({type: 'save-error', error: saveErr});
          throw saveErr;
        }
      },
      destroy() {
        subscribers.clear();
      },
      _notifySessionEdit(nextFiles, nextEntry, nextView) {
        latestRef.current.files = nextFiles;
        latestRef.current.entry = nextEntry;
        latestRef.current.view = nextView;
        latestRef.current.revision += 1;
        latestRef.current.persistence = 'dirty';
        setPersistence('dirty');
        const snap = buildSnap();
        notify({type: 'session'});
        callbacks.current.onChange?.(snap, {type: 'session'});
      },
    };
  }, [readOnly]);

  useEffect(() => {
    if (readOnly) return undefined;
    setReady(true);
    callbacks.current.onReady?.(controller);
    return () => controller.destroy();
  }, [controller, readOnly]);

  const handlePinNode = useCallback(
    (nodeId, x, y) => {
      if (readOnly) return;
      const curText = latestRef.current.files[activeEntry] || '';
      const updatedText = applyPinnedPositionToDdn(curText, nodeId, x, y);
      const nextFiles = {...latestRef.current.files, [activeEntry]: updatedText};
      setDraftFiles(nextFiles);
      controller._notifySessionEdit(nextFiles, activeEntry, activeView);
    },
    [activeEntry, activeView, controller, readOnly]
  );

  const handleSourceEdit = (evt) => {
    const nextText = evt?.target ? evt.target.value : String(evt ?? '');
    const nextFiles = {...latestRef.current.files, [activeEntry]: nextText};
    setDraftFiles(nextFiles);
    controller._notifySessionEdit(nextFiles, activeEntry, activeView);
  };

  if (readOnly) {
    return (
      <DDNViewerSurface
        files={files}
        snapshot={snapshot}
        onExport={onExport}
        onError={props.onError}
        executeCommand={executeCommand}
      />
    );
  }

  const run = async (id, invoke) => {
    try {
      await (executeCommand
        ? executeCommand(id, {invoke, enabled: ready})
        : invoke());
    } catch (failure) {
      setError(failure);
      callbacks.current.onError?.(failure);
    }
  };

  return (
    <Box
      data-cde-surface="diagram.ddn.designer"
      sx={{
        height: '100%',
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <Box
        component="header"
        sx={{display: 'flex', gap: 1, p: 0.5, alignItems: 'center'}}
      >
        <FormReference formKey="ddn-designer" />
        <Button
          disabled={!ready || !saveAsset || !assetRef || persistence === 'saving'}
          onClick={() =>
            run('ddn.designer.save', () => controller.save(saveAsset))
          }
        >
          Save
        </Button>
        <Button
          disabled={!ready}
          onClick={() =>
            run('ddn.designer.export', async () => {
              const captured = await controller.snapshot();
              const svg = await controller.exportSVG();
              onExport?.(svg, captured);
            })
          }
        >
          Export SVG
        </Button>
        <Button onClick={() => setShowSource((cur) => !cur)}>
          {showSource ? 'Hide DDN Source' : 'DDN Source'}
        </Button>
        <Box role="status" sx={{ml: 'auto', fontSize: '0.8rem'}}>
          {ready ? LABELS[persistence] || 'Saved' : 'Opening Designer'}
        </Box>
      </Box>

      {error && <Banner status="error">{error.message}</Banner>}

      <Box
        aria-label="DDN Designer"
        sx={{
          flex: 1,
          minHeight: 400,
          display: 'grid',
          gridTemplateColumns: showSource ? '1fr 380px' : '1fr',
          overflow: 'hidden',
        }}
      >
        <DDNViewerSurface
          files={draftFiles}
          entry={activeEntry}
          view={activeView}
          editable
          selectedNodeId={selectedNodeId}
          onSelectNode={(n) => setSelectedNodeId(n?.id || '')}
          onPinNode={handlePinNode}
          onSelectionChange={(sel) => {
            if (sel?.entry) setActiveEntry(sel.entry);
            if (sel?.view) {
              setActiveView(sel.view);
              latestRef.current.view = sel.view;
            }
          }}
          onReady={(captured) => {
            if (captured?.svg) latestRef.current.lastSvg = captured.svg;
          }}
          onExport={(svg) => {
            controller.snapshot().then((cap) => onExport?.(svg, cap));
          }}
          onError={props.onError}
        />

        {showSource && (
          <Box
            sx={{
              borderLeft: '1px solid',
              borderColor: 'divider',
              p: 1,
              display: 'flex',
              flexDirection: 'column',
              minHeight: 0,
            }}
          >
            <TextArea
              label={`DDN Source (${activeEntry})`}
              rows={22}
              value={draftFiles[activeEntry] || ''}
              onChange={handleSourceEdit}
            />
          </Box>
        )}
      </Box>
    </Box>
  );
}

DDNDesignerSurface.propTypes = {
  files: PropTypes.object,
  snapshot: PropTypes.object,
  assetRef: PropTypes.object,
  readOnly: PropTypes.bool,
  saveAsset: PropTypes.func,
  executeCommand: PropTypes.func,
  onChange: PropTypes.func,
  onExport: PropTypes.func,
  onReady: PropTypes.func,
  onError: PropTypes.func,
  onStateChange: PropTypes.func,
};
