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
import {Select} from '../../primitives/Choice';
import {EmptyState} from '../../feedback/EmptyState';
import {ProgressOverlay} from '../../feedback/ProgressOverlay';
import {StatusBadge} from '../../status/StatusBadge';
import FormReference from '../../navigation/FormReference';
import {validateDDNFiles, validateDDNSnapshot} from './contracts';
import {DesignStoreClient} from './sharedDesignLibrary';
import {
  RobinTiledCanvas,
  buildLocalFallbackScene,
  serializeRobinSceneToSvg,
} from './RobinTiledCanvas';

function discoverFileEntries(sourceFiles, primaryEntry, compiledScene) {
  const names = Object.keys(sourceFiles || {});
  if (!names.length) {
    const fallbackViews = compiledScene?.views?.length
      ? compiledScene.views
      : [{id: 'main', name: 'main'}];
    return [{file: primaryEntry || 'model.ddn', views: fallbackViews}];
  }
  return names.map((fileName) => {
    if (fileName === primaryEntry && compiledScene?.views?.length) {
      return {
        file: fileName,
        views: compiledScene.views.map((v) => ({
          id: v.id,
          name: v.name || v.id,
        })),
      };
    }
    const local = buildLocalFallbackScene(sourceFiles[fileName] || '');
    return {
      file: fileName,
      views: local.views.map((v) => ({id: v.id, name: v.name || v.id})),
    };
  });
}

function chooseEntryAndView(entries, requestedEntry, requestedView) {
  const firstFile = entries[0] || {
    file: 'model.ddn',
    views: [{id: 'main', name: 'main'}],
  };
  const fileObj =
    entries.find((f) => f.file === requestedEntry) || firstFile;
  const viewObj =
    fileObj.views.find((v) => v.id === requestedView) ||
    fileObj.views[0] || {id: 'main', name: 'main'};
  return {entry: fileObj.file, view: viewObj.id};
}

/**
 * ScratchRobin Native Shared Diagram, Dashboard, Cube & Wireframe Viewer.
 * Delegates layout, orthogonal routing and spatial `(tx, ty)` tiling to the
 * ScratchRobin Python host (`robin_scene_engine.py`) with zero `@ddn/standalone`
 * runtime usage.
 */
export function DDNViewerSurface(props) {
  const {
    files,
    snapshot,
    entry,
    view,
    projectId = '',
    designId = '',
    version = null,
    initialScene = null,
    client: suppliedClient = null,
    presentation = false,
    viewSelection = false,
    showViewSelector = true,
    liveData,
    selectedNodeId = '',
    onSelectNode,
    editable = false,
    onPinNode,
  } = props;

  const callbacks = useRef(props);
  callbacks.current = props;

  const canvasApiRef = useRef(null);
  const retained = useRef(null);
  const prevRequested = useRef({entry: '', view: ''});

  const canUseHostHttp =
    Boolean(suppliedClient) || process.env.NODE_ENV !== 'test';
  const activeClient = useMemo(
    () =>
      suppliedClient || (canUseHostHttp ? new DesignStoreClient() : null),
    [canUseHostHttp, suppliedClient]
  );

  const sourceFiles = useMemo(() => {
    try {
      if (snapshot) return validateDDNSnapshot(snapshot).files;
      if (files) return validateDDNFiles(files);
      return null;
    } catch (err) {
      return {__validationError: err};
    }
  }, [files, snapshot]);

  const sourceSignature = useMemo(() => {
    if (sourceFiles?.__validationError) return 'invalid';
    if (!sourceFiles) return `${projectId}:${designId}:${version ?? 'head'}`;
    const keys = Object.keys(sourceFiles);
    // Avoid stringifying megabytes repeatedly when sha/version is already known
    if (initialScene?.ddn_sha256 && projectId && designId) {
      return `${projectId}:${designId}:${version ?? 'head'}:${initialScene.ddn_sha256}`;
    }
    return JSON.stringify(
      keys.map((k) => [k, (sourceFiles[k] || '').length, sourceFiles[k]])
    );
  }, [sourceFiles, projectId, designId, version, initialScene?.ddn_sha256]);

  const requestedEntry = entry || snapshot?.entry || '';
  const requestedView = view || snapshot?.view || '';

  const [entries, setEntries] = useState([]);
  const [selection, setSelection] = useState({entry: '', view: ''});
  const [scene, setScene] = useState(null);
  const [loadedTiles, setLoadedTiles] = useState({});
  const [svgDataUri, setSvgDataUri] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const compileAndLoad = useCallback(
    async (targetEntry, targetView, allowInitialScene = false) => {
      if (sourceFiles?.__validationError) {
        throw sourceFiles.__validationError;
      }

      const fileNames = sourceFiles ? Object.keys(sourceFiles) : [];
      const activeEntry =
        (targetEntry && fileNames.includes(targetEntry) && targetEntry) ||
        fileNames[0] ||
        targetEntry ||
        'model.ddn';

      // Fast Path 1: Pre-compiled host scene arrived with openSession()
      if (
        allowInitialScene &&
        initialScene &&
        (!targetView || initialScene.view_id === targetView)
      ) {
        const discovered = discoverFileEntries(
          sourceFiles,
          activeEntry,
          initialScene
        );
        const chosen = chooseEntryAndView(
          discovered,
          activeEntry,
          initialScene.view_id
        );
        const svgText = presentation
          ? serializeRobinSceneToSvg(initialScene, initialScene.loaded_tiles)
          : '';
        return {
          scene: initialScene,
          tiles: initialScene.loaded_tiles || {},
          entries: discovered,
          chosen,
          svgText,
        };
      }

      // Fast Path 2: Saved design on host — stream view manifest + initial viewport tiles
      if (
        projectId &&
        designId &&
        typeof activeClient?.fetchDesignTiles === 'function'
      ) {
        try {
          const hostScene = await activeClient.fetchDesignTiles(
            projectId,
            designId,
            {
              version,
              view: targetView || undefined,
              tileSize: 1024,
            }
          );
          if (hostScene && hostScene.canvas_bounds) {
            const discovered = discoverFileEntries(
              sourceFiles,
              activeEntry,
              hostScene
            );
            const chosen = chooseEntryAndView(
              discovered,
              activeEntry,
              hostScene.view_id
            );
            let svgText = '';
            if (presentation) {
              if (typeof activeClient.fetchDesignSvg === 'function') {
                const svgRes = await activeClient.fetchDesignSvg(
                  projectId,
                  designId,
                  {version, view: chosen.view}
                );
                svgText = svgRes?.svg || '';
              }
              if (!svgText) {
                svgText = serializeRobinSceneToSvg(
                  hostScene,
                  hostScene.loaded_tiles
                );
              }
            }
            return {
              scene: hostScene,
              tiles: hostScene.loaded_tiles || {},
              entries: discovered,
              chosen,
              svgText,
            };
          }
        } catch {
          // Fall through to workspace compilation or local fallback
        }
      }

      // Fast Path 3: Standalone/unsaved DDN workspace compiled on host
      const ddnText = sourceFiles ? sourceFiles[activeEntry] || '' : '';
      if (
        sourceFiles &&
        typeof activeClient?.compileDdnScene === 'function'
      ) {
        try {
          const hostScene = await activeClient.compileDdnScene({
            files: sourceFiles,
            entry: activeEntry,
            view: targetView || undefined,
            tileSize: 1024,
            includeSvg: Boolean(presentation),
          });
          if (hostScene && hostScene.canvas_bounds) {
            const discovered = discoverFileEntries(
              sourceFiles,
              activeEntry,
              hostScene
            );
            const chosen = chooseEntryAndView(
              discovered,
              activeEntry,
              hostScene.view_id
            );
            const svgText = presentation
              ? hostScene.svg ||
                serializeRobinSceneToSvg(hostScene, hostScene.loaded_tiles)
              : '';
            return {
              scene: hostScene,
              tiles: hostScene.loaded_tiles || {},
              entries: discovered,
              chosen,
              svgText,
            };
          }
        } catch {
          // Offline / unit-test environment without live Flask endpoint: use local compiler
        }
      }

      // Path 4: Deterministic offline local fallback (unit tests)
      const localEntries = discoverFileEntries(sourceFiles, activeEntry, null);
      const chosen = chooseEntryAndView(localEntries, activeEntry, targetView);
      const chosenText = sourceFiles ? sourceFiles[chosen.entry] || ddnText : ddnText;
      const fallbackScene = buildLocalFallbackScene(chosenText, chosen.view);
      const svgText = presentation
        ? serializeRobinSceneToSvg(fallbackScene, fallbackScene.loaded_tiles)
        : '';
      return {
        scene: fallbackScene,
        tiles: fallbackScene.loaded_tiles || {},
        entries: localEntries,
        chosen,
        svgText,
      };
    },
    [
      activeClient,
      designId,
      initialScene,
      presentation,
      projectId,
      sourceFiles,
      version,
    ]
  );

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    const propChanged =
      prevRequested.current.entry !== requestedEntry ||
      prevRequested.current.view !== requestedView;
    prevRequested.current = {entry: requestedEntry, view: requestedView};
    if (propChanged && (requestedEntry || requestedView)) {
      retained.current = null;
    }

    const desiredEntry =
      viewSelection && retained.current?.entry
        ? retained.current.entry
        : requestedEntry;
    const desiredView =
      viewSelection && retained.current?.view
        ? retained.current.view
        : requestedView;

    compileAndLoad(desiredEntry, desiredView, true)
      .then((res) => {
        if (!active) return;
        retained.current = res.chosen;
        setEntries(res.entries);
        setSelection(res.chosen);
        setScene(res.scene);
        setLoadedTiles(res.tiles);
        if (presentation && res.svgText) {
          setSvgDataUri(
            `data:image/svg+xml;charset=utf-8,${encodeURIComponent(res.svgText)}`
          );
        } else {
          setSvgDataUri('');
        }
        setLoading(false);
        callbacks.current.onSelectionChange?.(res.chosen);
        callbacks.current.onReady?.({
          entry: res.chosen.entry,
          view: res.chosen.view,
          svg:
            res.svgText ||
            serializeRobinSceneToSvg(res.scene, res.tiles),
          diagnostics: res.scene.diagnostics || [],
          scene: res.scene,
        });
      })
      .catch((failure) => {
        if (!active) return;
        setScene(null);
        setLoadedTiles({});
        setSvgDataUri('');
        setError(failure);
        setLoading(false);
        callbacks.current.onError?.(failure);
      });

    return () => {
      active = false;
    };
  }, [
    compileAndLoad,
    liveData,
    presentation,
    requestedEntry,
    requestedView,
    sourceSignature,
    viewSelection,
  ]);

  const handleRequestTiles = useCallback(
    async (missingCoords) => {
      if (!missingCoords?.length || !scene) return;
      try {
        if (
          projectId &&
          designId &&
          typeof activeClient?.fetchDesignTiles === 'function'
        ) {
          const tileBatch = await activeClient.fetchDesignTiles(
            projectId,
            designId,
            {
              version,
              view: selection.view || scene.view_id,
              tileSize: scene.tile_size || 1024,
              coords: missingCoords,
            }
          );
          if (tileBatch?.loaded_tiles) {
            setLoadedTiles((prev) => ({...prev, ...tileBatch.loaded_tiles}));
          }
          return;
        }
        if (
          sourceFiles &&
          !sourceFiles.__validationError &&
          typeof activeClient?.compileDdnScene === 'function'
        ) {
          const tileBatch = await activeClient.compileDdnScene({
            files: sourceFiles,
            entry: selection.entry,
            view: selection.view || scene.view_id,
            tileSize: scene.tile_size || 1024,
            coords: missingCoords,
          });
          if (tileBatch?.loaded_tiles) {
            setLoadedTiles((prev) => ({...prev, ...tileBatch.loaded_tiles}));
          }
        }
      } catch {
        // Keep already loaded tiles visible if background tile fetch is interrupted
      }
    },
    [
      activeClient,
      designId,
      projectId,
      scene,
      selection.entry,
      selection.view,
      sourceFiles,
      version,
    ]
  );

  const chooseView = async (value) => {
    const [nextEntry, nextView] = String(value || '').split('\0');
    setLoading(true);
    setError(null);
    try {
      const res = await compileAndLoad(nextEntry, nextView, false);
      retained.current = res.chosen;
      setEntries(res.entries);
      setSelection(res.chosen);
      setScene(res.scene);
      setLoadedTiles(res.tiles);
      if (presentation && res.svgText) {
        setSvgDataUri(
          `data:image/svg+xml;charset=utf-8,${encodeURIComponent(res.svgText)}`
        );
      }
      setLoading(false);
      callbacks.current.onSelectionChange?.(res.chosen);
      callbacks.current.onReady?.({
        entry: res.chosen.entry,
        view: res.chosen.view,
        svg: res.svgText || serializeRobinSceneToSvg(res.scene, res.tiles),
        diagnostics: res.scene.diagnostics || [],
        scene: res.scene,
      });
    } catch (failure) {
      setError(failure);
      setLoading(false);
      callbacks.current.onError?.(failure);
    }
  };

  const run = async (id, invoke) => {
    try {
      await (callbacks.current.executeCommand
        ? callbacks.current.executeCommand(id, {invoke, enabled: Boolean(scene)})
        : invoke());
    } catch (failure) {
      setError(failure);
      callbacks.current.onError?.(failure);
    }
  };

  const handleExportSvg = async () => {
    let svgOut = '';
    if (
      projectId &&
      designId &&
      typeof activeClient?.fetchDesignSvg === 'function'
    ) {
      try {
        const res = await activeClient.fetchDesignSvg(projectId, designId, {
          version,
          view: selection.view || scene?.view_id,
        });
        svgOut = res?.svg || '';
      } catch {
        svgOut = '';
      }
    }
    if (!svgOut && sourceFiles && typeof activeClient?.compileDdnScene === 'function') {
      try {
        const res = await activeClient.compileDdnScene({
          files: sourceFiles,
          entry: selection.entry,
          view: selection.view || scene?.view_id,
          includeSvg: true,
        });
        svgOut = res?.svg || '';
      } catch {
        svgOut = '';
      }
    }
    if (!svgOut) {
      svgOut =
        canvasApiRef.current?.exportSvg?.() ||
        serializeRobinSceneToSvg(scene, loadedTiles);
    }
    callbacks.current.onExport?.(svgOut, selection);
  };

  const options = entries.flatMap((file) =>
    file.views.map((item) => ({
      value: `${file.file}\0${item.id}`,
      label: `${file.file} / ${item.name || item.id}`,
    }))
  );

  const diagnosticsCount = scene?.diagnostics?.length || 0;

  return (
    <Box
      data-cde-surface="diagram.ddn.viewer"
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: presentation ? 'auto' : '100%',
        minHeight: 0,
      }}
    >
      <FormReference formKey="ddn-viewer" />
      {((presentation && viewSelection && options.length > 1) ||
        !presentation) && (
        <Box
          component="header"
          sx={{display: 'flex', gap: 1, alignItems: 'center', p: 0.5}}
        >
          {(presentation || showViewSelector) && (
            <Select
              label={presentation ? 'Dashboard view' : 'DDN view'}
              size="small"
              value={
                selection.entry ? `${selection.entry}\0${selection.view}` : ''
              }
              options={options}
              onChange={chooseView}
            />
          )}
          {!presentation && (
            <>
              <Button
                disabled={!scene}
                onClick={() =>
                  run('ddn.viewer.fit', () =>
                    canvasApiRef.current?.fitWorkarea?.()
                  )
                }
              >
                Fit
              </Button>
              <Button
                disabled={!scene}
                onClick={() => canvasApiRef.current?.zoomOut?.()}
              >
                −
              </Button>
              <Button
                disabled={!scene}
                onClick={() => canvasApiRef.current?.zoomIn?.()}
              >
                +
              </Button>
              <Button
                disabled={!scene}
                onClick={() => run('ddn.viewer.export', handleExportSvg)}
              >
                Export SVG
              </Button>
              <StatusBadge
                live
                status={
                  error ? 'error' : diagnosticsCount ? 'warning' : 'success'
                }
                label={
                  error ? 'Render failed' : `${diagnosticsCount} diagnostics`
                }
              />
            </>
          )}
        </Box>
      )}
      <Box
        sx={{
          position: 'relative',
          flex: 1,
          minHeight: presentation ? 120 : 0,
          overflow: presentation ? 'auto' : 'hidden',
        }}
      >
        {error && <EmptyState role="alert" message={error.message} />}
        {!error && !presentation && (
          <RobinTiledCanvas
            scene={scene}
            loadedTiles={loadedTiles}
            onRequestTiles={handleRequestTiles}
            selectedNodeId={selectedNodeId}
            onSelectNode={onSelectNode}
            editable={editable}
            onPinNode={onPinNode}
            canvasApiRef={canvasApiRef}
            ariaLabel="DDN diagram"
          />
        )}
        {presentation && (
          <img
            alt="DDN diagram"
            src={svgDataUri || undefined}
            style={{
              maxWidth: '100%',
              display: error || !svgDataUri ? 'none' : 'block',
            }}
          />
        )}
        <ProgressOverlay message={loading ? 'Rendering DDN view' : ''} />
      </Box>
    </Box>
  );
}

DDNViewerSurface.propTypes = {
  files: PropTypes.object,
  snapshot: PropTypes.object,
  entry: PropTypes.string,
  view: PropTypes.string,
  projectId: PropTypes.string,
  designId: PropTypes.string,
  version: PropTypes.number,
  initialScene: PropTypes.object,
  client: PropTypes.object,
  presentation: PropTypes.bool,
  viewSelection: PropTypes.bool,
  showViewSelector: PropTypes.bool,
  liveData: PropTypes.array,
  selectedNodeId: PropTypes.string,
  onSelectNode: PropTypes.func,
  editable: PropTypes.bool,
  onPinNode: PropTypes.func,
  executeCommand: PropTypes.func,
  onExport: PropTypes.func,
  onReady: PropTypes.func,
  onError: PropTypes.func,
  onSelectionChange: PropTypes.func,
};
