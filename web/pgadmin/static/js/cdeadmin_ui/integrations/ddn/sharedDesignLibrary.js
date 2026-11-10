/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import getApiInstance from 'sources/api_instance';
import {validateDDNSnapshot} from './contracts.js';

const ROOT = '/cdeadmin/api/projects';

export const DESIGN_SAVE_POINTS = Object.freeze([
  'draft',
  'in_progress',
  'in_review',
  'accepted',
]);

export const DESIGN_KINDS = Object.freeze([
  'erd',
  'cube',
  'question',
  'dashboard',
  'screen_mesh',
  'monitoring',
]);

export const ERD_MODELLING_LEVELS = Object.freeze([
  'conceptual',
  'logical',
  'physical',
  'deployment',
]);

function segment(value) {
  return encodeURIComponent(String(value));
}

function unwrap(response) {
  return response?.data?.data;
}

export class DesignStoreClientError extends Error {
  constructor(error) {
    const response = error?.response?.data;
    super(
      response?.errormsg || error?.message || 'Design store request failed.'
    );
    this.name = 'DesignStoreClientError';
    this.code = response?.code || 'design_store_request_failed';
    this.status = error?.response?.status ?? 0;
    this.cause = error;
  }
}

async function callApi(fn) {
  try {
    return unwrap(await fn());
  } catch (error) {
    throw new DesignStoreClientError(error);
  }
}

/**
 * Shared client-side transport for the server-side DesignStore and
 * StoreDDNProcess (owner direction 2026-11-09 & 2026-11-10).
 */
export class DesignStoreClient {
  constructor(api = getApiInstance()) {
    this.api = api;
  }

  listDesigns(projectId, {kind = null, query = null} = {}) {
    const params = new URLSearchParams();
    if (kind) params.set('kind', kind);
    if (query) params.set('q', query);
    const suffix = params.toString() ? `?${params.toString()}` : '';
    return callApi(() =>
      this.api.get(`${ROOT}/${segment(projectId)}/designs${suffix}`)
    );
  }

  createDesign(projectId, payload) {
    return callApi(() =>
      this.api.post(`${ROOT}/${segment(projectId)}/designs`, payload)
    );
  }

  importPhysicalErd(projectId, {key, title, workspace, note = ''}) {
    return callApi(() =>
      this.api.post(`${ROOT}/${segment(projectId)}/designs`, {
        mode: 'import_physical_erd',
        key,
        title,
        workspace,
        note,
      })
    );
  }

  openSession(
    projectId,
    designId,
    {version = null, activeOnly = false, view = null, tileSize = 1024} = {}
  ) {
    const params = new URLSearchParams();
    if (version !== null && version !== undefined) {
      params.set('version', String(version));
    }
    if (activeOnly) params.set('active_only', '1');
    if (view) params.set('view', view);
    if (tileSize) params.set('tile_size', String(tileSize));
    const suffix = params.toString() ? `?${params.toString()}` : '';
    return callApi(() =>
      this.api.get(
        `${ROOT}/${segment(projectId)}/designs/${segment(designId)}${suffix}`
      )
    );
  }

  saveVersion(projectId, designId, payload) {
    return callApi(() =>
      this.api.put(
        `${ROOT}/${segment(projectId)}/designs/${segment(designId)}`,
        payload
      )
    );
  }

  deleteDesign(projectId, designId, expectedHeadVersion = null) {
    return callApi(() =>
      this.api.delete(
        `${ROOT}/${segment(projectId)}/designs/${segment(designId)}`,
        {data: {expected_head_version: expectedHeadVersion}}
      )
    );
  }

  listVersions(projectId, designId) {
    return callApi(() =>
      this.api.get(
        `${ROOT}/${segment(projectId)}/designs/${segment(designId)}/versions`
      )
    );
  }

  advanceStatus(projectId, designId, version, status) {
    return callApi(() =>
      this.api.post(
        `${ROOT}/${segment(projectId)}/designs/${segment(designId)}` +
          `/versions/${segment(version)}/status`,
        {status}
      )
    );
  }

  acceptVersion(
    projectId,
    designId,
    version,
    {
      requireGitReview = false,
      gitReviewRef = null,
      comment = '',
    } = {}
  ) {
    return callApi(() =>
      this.api.post(
        `${ROOT}/${segment(projectId)}/designs/${segment(designId)}` +
          `/versions/${segment(version)}/accept`,
        {
          require_git_review: Boolean(requireGitReview),
          git_review_ref: gitReviewRef,
          comment,
        }
      )
    );
  }

  rollbackVersion(projectId, designId, version, {comment = ''} = {}) {
    return callApi(() =>
      this.api.post(
        `${ROOT}/${segment(projectId)}/designs/${segment(designId)}` +
          `/versions/${segment(version)}/rollback`,
        {comment}
      )
    );
  }

  branchDraftFromAccepted(projectId, designId, {note = ''} = {}) {
    return callApi(() =>
      this.api.post(
        `${ROOT}/${segment(projectId)}/designs/${segment(designId)}/branch`,
        {note}
      )
    );
  }

  confirmBinding(projectId, designId, bindingId, {newTargetRef = null} = {}) {
    return callApi(() =>
      this.api.post(
        `${ROOT}/${segment(projectId)}/designs/${segment(designId)}` +
          `/bindings/${segment(bindingId)}/confirm`,
        {new_target_ref: newTargetRef}
      )
    );
  }

  includeDesign(
    projectId,
    designId,
    {
      version = 1,
      dependsOnDesignId,
      pinVersion = true,
      explicitVersion = null,
    }
  ) {
    return callApi(() =>
      this.api.post(
        `${ROOT}/${segment(projectId)}/designs/${segment(designId)}/includes`,
        {
          version,
          depends_on_design_id: dependsOnDesignId,
          pin_version: Boolean(pinVersion),
          explicit_version: explicitVersion,
        }
      )
    );
  }

  computeLayout(
    projectId,
    designId,
    {
      ddnText = null,
      version = null,
      viewId = null,
      pinnedPositions = null,
      tileSize = 1024,
    } = {}
  ) {
    return callApi(() =>
      this.api.post(
        `${ROOT}/${segment(projectId)}/designs/${segment(designId)}/layout`,
        {
          ddn_text: ddnText,
          version,
          view_id: viewId,
          pinned_positions: pinnedPositions,
          tile_size: tileSize,
        }
      )
    );
  }

  exportDDN(projectId, designId, {version = null, entry = null, view = null} = {}) {
    const params = new URLSearchParams();
    if (version !== null && version !== undefined) {
      params.set('version', String(version));
    }
    if (entry) params.set('entry', entry);
    if (view) params.set('view', view);
    const suffix = params.toString() ? `?${params.toString()}` : '';
    return callApi(() =>
      this.api.get(
        `${ROOT}/${segment(projectId)}/designs/${segment(designId)}/export${suffix}`
      )
    );
  }

  convertErdEngine(
    projectId,
    designId,
    {
      version = null,
      sourceEngine,
      targetEngine,
      customTypeMap = null,
      lossChoices = null,
      strict = true,
      saveVersion = false,
      note = '',
    }
  ) {
    return callApi(() =>
      this.api.post(
        `${ROOT}/${segment(projectId)}/designs/${segment(designId)}/erd/convert`,
        {
          version,
          source_engine: sourceEngine,
          target_engine: targetEngine,
          custom_type_map: customTypeMap,
          loss_choices: lossChoices,
          strict,
          save_version: saveVersion,
          note,
        }
      )
    );
  }

  computeErdDrift(projectId, designId, {version = null, liveNodes = []} = {}) {
    return callApi(() =>
      this.api.post(
        `${ROOT}/${segment(projectId)}/designs/${segment(designId)}/erd/drift`,
        {
          version,
          live_nodes: liveNodes,
        }
      )
    );
  }

  createErdDesign(
    projectId,
    {
      key,
      title,
      conceptualEntities = [],
      logicalEntities = [],
      physicalTables = [],
      deploymentNodes = [],
      levelLinks = [],
      extensions = null,
      note = '',
    }
  ) {
    return callApi(() =>
      this.api.post(`${ROOT}/${segment(projectId)}/designs`, {
        mode: 'create_erd',
        key,
        title,
        conceptual_entities: conceptualEntities,
        logical_entities: logicalEntities,
        physical_tables: physicalTables,
        deployment_nodes: deploymentNodes,
        level_links: levelLinks,
        extensions,
        note,
      })
    );
  }

  saveErdModel(
    projectId,
    designId,
    {
      title = null,
      expectedHeadVersion = null,
      conceptualEntities = [],
      logicalEntities = [],
      physicalTables = [],
      deploymentNodes = [],
      levelLinks = [],
      extensions = null,
      pinnedPositions = null,
      status = 'draft',
      note = '',
    }
  ) {
    return callApi(() =>
      this.api.post(
        `${ROOT}/${segment(projectId)}/designs/${segment(designId)}/erd/model`,
        {
          title,
          expected_head_version: expectedHeadVersion,
          conceptual_entities: conceptualEntities,
          logical_entities: logicalEntities,
          physical_tables: physicalTables,
          deployment_nodes: deploymentNodes,
          level_links: levelLinks,
          extensions,
          pinned_positions: pinnedPositions,
          status,
          note,
        }
      )
    );
  }

  previewErdAlterPlan(
    projectId,
    designId,
    {
      baseVersion = null,
      desiredVersion = null,
      selectedDifferenceIds = null,
      targetEngine = 'sqlite',
      catalogSnapshot = null,
      handoffOptions = null,
    } = {}
  ) {
    return callApi(() =>
      this.api.post(
        `${ROOT}/${segment(projectId)}/designs/${segment(designId)}` +
          `/erd/alter-plan`,
        {
          base_version: baseVersion,
          desired_version: desiredVersion,
          selected_difference_ids: selectedDifferenceIds,
          target_engine: targetEngine,
          catalog_snapshot: catalogSnapshot,
          handoff_options: handoffOptions,
        }
      )
    );
  }

  proposeErdDiagramChange(
    projectId,
    designId,
    {version = null, elementId, action, parameters = {}}
  ) {
    return callApi(() =>
      this.api.post(
        `${ROOT}/${segment(projectId)}/designs/${segment(designId)}/erd/drift`,
        {
          version,
          propose_change: true,
          element_id: elementId,
          action,
          parameters,
        }
      )
    );
  }
}

/**
 * Shared task-designer session controller used by the ERD, cube, BI and
 * screen-mesh designers. Delegates calculation, layered layout and tiling
 * to the server while exposing validated DDN snapshots for the single
 * shared DDNViewerSurface.
 */
export class SharedDDNTaskController {
  constructor({
    client = new DesignStoreClient(),
    projectId,
    designId,
    kind = 'erd',
    tileSize = 1024,
  }) {
    if (!projectId || !designId) {
      throw new Error('projectId and designId are required.');
    }
    this.client = client;
    this.projectId = projectId;
    this.designId = designId;
    this.kind = kind;
    this.tileSize = tileSize;
    this.session = null;
    this.pinnedPositions = {};
    this.listeners = new Set();
  }

  subscribe(listener) {
    if (typeof listener !== 'function') {
      throw new TypeError('Listener must be a function.');
    }
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  _emit(event) {
    for (const listener of this.listeners) {
      listener(this.state(), event);
    }
  }

  state() {
    if (!this.session) {
      return Object.freeze({
        loaded: false,
        projectId: this.projectId,
        designId: this.designId,
        kind: this.kind,
      });
    }
    const {design, workspace, layout, resolved_includes, binding_summary} =
      this.session;
    return Object.freeze({
      loaded: true,
      projectId: this.projectId,
      designId: this.designId,
      kind: design.kind,
      title: design.title,
      headVersion: design.head_version,
      activeVersion: design.active_version,
      currentVersion: design.version.version,
      status: design.version.status,
      workspace: validateDDNSnapshot(workspace),
      layout,
      tiles: layout?.tiles || [],
      resolvedIncludes: resolved_includes || [],
      bindings: design.bindings || [],
      bindingSummary: binding_summary || {
        total: 0,
        valid: 0,
        suspect: 0,
        unknown: 0,
      },
      pinnedPositions: {...this.pinnedPositions},
    });
  }

  async load({version = null, activeOnly = false, view = null} = {}) {
    this.session = await this.client.openSession(this.projectId, this.designId, {
      version,
      activeOnly,
      view,
      tileSize: this.tileSize,
    });
    this._emit({type: 'loaded'});
    return this.state();
  }

  pinNode(nodeId, x, y, pinned = true) {
    this.pinnedPositions[nodeId] = {
      x: Number(x),
      y: Number(y),
      pinned: Boolean(pinned),
    };
    this._emit({type: 'pin-changed', nodeId});
  }

  visibleTiles(viewportBounds) {
    const tiles = this.session?.layout?.tiles || [];
    if (!viewportBounds) return tiles;
    const {min_x, min_y, max_x, max_y} = viewportBounds;
    return tiles.filter(
      (t) =>
        !(
          t.bounds.max_x < min_x ||
          t.bounds.min_x > max_x ||
          t.bounds.max_y < min_y ||
          t.bounds.min_y > max_y
        )
    );
  }

  async save({
    ddnOrWorkspace = null,
    status = 'draft',
    note = '',
    allowConflictNote = false,
  } = {}) {
    if (!this.session) {
      throw new Error('Load the design session before saving.');
    }
    const source = ddnOrWorkspace || this.session.workspace;
    const res = await this.client.saveVersion(this.projectId, this.designId, {
      expected_head_version: this.session.design.head_version,
      workspace: typeof source === 'object' ? source : undefined,
      ddn_text: typeof source === 'string' ? source : undefined,
      pinned_positions: this.pinnedPositions,
      status,
      note,
      allow_conflict_note: allowConflictNote,
    });
    await this.load({version: res.design.version.version});
    this._emit({type: 'saved', version: res.design.version.version});
    return this.state();
  }

  async advanceStatus(targetStatus) {
    if (!this.session) throw new Error('Design session is not loaded.');
    await this.client.advanceStatus(
      this.projectId,
      this.designId,
      this.session.design.version.version,
      targetStatus
    );
    return this.load({version: this.session.design.version.version});
  }

  async accept({
    requireGitReview = false,
    gitReviewRef = null,
    comment = '',
  } = {}) {
    if (!this.session) throw new Error('Design session is not loaded.');
    await this.client.acceptVersion(
      this.projectId,
      this.designId,
      this.session.design.version.version,
      {requireGitReview, gitReviewRef, comment}
    );
    return this.load({version: this.session.design.version.version});
  }

  async confirmSuspectBinding(bindingId, newTargetRef = null) {
    await this.client.confirmBinding(this.projectId, this.designId, bindingId, {
      newTargetRef,
    });
    return this.load({version: this.session?.design?.version?.version});
  }

  async branchDraft({note = ''} = {}) {
    const branched = await this.client.branchDraftFromAccepted(
      this.projectId,
      this.designId,
      {note}
    );
    return this.load({version: branched.head_version});
  }

  async rollback(version, {comment = ''} = {}) {
    await this.client.rollbackVersion(
      this.projectId,
      this.designId,
      version,
      {comment}
    );
    return this.load({version});
  }

  async convertErdEngine(options) {
    const result = await this.client.convertErdEngine(
      this.projectId,
      this.designId,
      {
        version: this.session?.design?.version?.version ?? null,
        ...options,
      }
    );
    if (options?.saveVersion && result?.saved?.design?.version?.version) {
      await this.load({version: result.saved.design.version.version});
    }
    return result;
  }

  previewErdAlterPlan(options = {}) {
    return this.client.previewErdAlterPlan(this.projectId, this.designId, {
      desiredVersion: this.session?.design?.version?.version ?? null,
      ...options,
    });
  }

  computeErdDrift({liveNodes = []} = {}) {
    return this.client.computeErdDrift(this.projectId, this.designId, {
      version: this.session?.design?.version?.version ?? null,
      liveNodes,
    });
  }

  proposeErdDiagramChange({elementId, action, parameters = {}}) {
    return this.client.proposeErdDiagramChange(this.projectId, this.designId, {
      version: this.session?.design?.version?.version ?? null,
      elementId,
      action,
      parameters,
    });
  }
}
