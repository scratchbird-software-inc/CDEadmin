/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {loadDDNLibraries} from './library';
import {
  ddnAssetPayload,
  validateDDNAssetRef,
  validateDDNFiles,
  validateDDNSnapshot,
} from './contracts';

export const DDN_PERSISTENCE_STATES = Object.freeze({
  CLEAN: 'clean',
  DIRTY: 'dirty',
  SAVING: 'saving',
  SAVED_NEWER_EDITS: 'saved-newer-edits',
  SAVE_FAILED: 'save-failed',
  EXTERNAL_CONFLICT: 'external-conflict',
});

export class DDNSessionController {
  static async create(options={}) {
    const libraries = await loadDDNLibraries();
    return new DDNSessionController(libraries, options);
  }

  constructor(libraries, options={}) {
    this.libraries = libraries;
    this.assetRef = options.assetRef ?
      validateDDNAssetRef(options.assetRef) : null;
    this.tool = options.tool || null;
    this.readOnly = Boolean(options.readOnly);
    this.validation = options.validation || 'strict';
    const source = options.snapshot ? validateDDNSnapshot(options.snapshot) : options;
    this._workspace = this.tool ? null : libraries.viewer.createWorkspace(validateDDNFiles(source.files));
    this.editor = this.workspace.editor({canWrite: () => !this.readOnly});
    const entries = this.workspace.entries().filter((item) => item.views.length);
    const entry = entries.find((item) => item.file === source.entry) || entries[0];
    if(!entry) {
      if(!this.tool) this.workspace.destroy();
      throw new Error('The DDN workspace has no displayable views.');
    }
    this.entry = entry.file;
    this.view = entry.views.find((item) => item.id === source.view)?.id || entry.views[0].id;
    this.overrides = source.overrides;
    this.layoutState = source.layoutState;
    this.persistenceState = DDN_PERSISTENCE_STATES.CLEAN;
    this.lastError = null;
    this.listeners = new Set();
    this.destroyed = false;
    this.saving = false;
    this.savedFingerprint = JSON.stringify(this.snapshot().files);
    const changed = (event) => {
      this.persistenceState = DDN_PERSISTENCE_STATES.DIRTY;
      try {
        if(!this.isDirty()) this.persistenceState = DDN_PERSISTENCE_STATES.CLEAN;
      } catch(error) { this.lastError = error; }
      this._emit({type: 'session', event});
    };
    this.unsubscribe = this.tool ? this.tool.onSourceChange(changed) : this.workspace.subscribe(changed);
  }

  _alive() {
    if(this.destroyed) throw new Error('DDN session has been destroyed.');
  }

  get workspace() { return this.tool?.workspace || this._workspace; }
  isDirty() { return this.saving || JSON.stringify(this.snapshot().files) !== this.savedFingerprint; }

  _emit(event) {
    for(const listener of this.listeners) listener(this.state(), event);
  }

  state() {
    return Object.freeze({
      entry: this.entry,
      view: this.view,
      revision: this.workspace.revision,
      readOnly: this.readOnly,
      validation: this.validation,
      persistence: this.persistenceState,
      history: Object.freeze({...this.workspace.history()}),
      lastError: this.lastError,
    });
  }

  subscribe(listener) {
    this._alive();
    if(typeof listener !== 'function') {
      throw new TypeError('DDN session listener must be a function.');
    }
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  _writable() {
    this._alive();
    if(this.readOnly) throw new Error('This DDN workspace is read-only.');
  }
  request() { return {entry: this.entry, view: this.view, overrides: this.overrides, layoutState: this.layoutState}; }
  inspect() { this._alive(); return this.workspace.inspect(this.entry, this.view); }
  getFiles() { this._alive(); return this.tool ? validateDDNFiles(this.tool.getSource({includeAppearance: true}).files) : this.workspace.getFiles(); }
  render() { this._alive(); return this.workspace.renderSync(this.request()); }
  review() { this._alive(); return this.workspace.validateDraft(this.entry, this.view); }
  exportSVG() { this._alive(); return this.tool ? this.tool.exportSvgString() : this.render().svg; }
  snapshot() {
    this._alive();
    if(this.tool) {
      // A source bridge alone does not detect pending structured-editor drafts.
      // The documented snapshot API rejects unapplied drafts before any save.
      const snapshot = this.tool.snapshot();
      const source = this.tool.getSource({includeAppearance: true});
      return validateDDNSnapshot({...snapshot, format: 'ddn-workspace@1', ...source});
    }
    return validateDDNSnapshot(this.workspace.snapshot(this.entry, this.view, this.overrides, this.layoutState));
  }
  prepare(operation) {
    this._writable();
    return this.editor.preview({entry: this.entry, view: this.view,
      expectedRevision: this.workspace.revision, mode: this.validation === 'strict' ? 'review' : 'design',
      operations: [operation]});
  }
  commit(plan) { this._writable(); return this.editor.apply(plan); }
  execute(operation) { return this.commit(this.prepare(operation)); }
  updateSource(file, source) { return this.execute({type: 'files', changes: {[file]: source}}); }
  undo() { this._writable(); return this.workspace.undo(); }
  redo() { this._writable(); return this.workspace.redo(); }
  setReadOnly(value) { this.readOnly = Boolean(value); }

  async save(saveAsset) {
    this._writable();
    if(this.saving) throw new Error('A DDN save is already in progress.');
    if(!this.assetRef) throw new Error('DDN session is not bound to an AssetRef.');
    if(typeof saveAsset !== 'function') {
      throw new TypeError('DDN asset save authority must be a function.');
    }
    const captured = this.snapshot();
    const fingerprint = JSON.stringify(captured.files);
    const revision = this.workspace.revision;
    const payload = ddnAssetPayload(this.assetRef, captured);
    this.saving = true;
    this.persistenceState = DDN_PERSISTENCE_STATES.SAVING;
    this.lastError = null;
    this._emit({type: 'saving', revision});
    try {
      const result = await saveAsset(payload, {
        expectedAssetVersion: this.assetRef.assetVersion,
        sourceRevision: revision,
      });
      if(!result?.assetRef) throw new Error('Save did not return a versioned AssetRef.');
      const reference = validateDDNAssetRef(result.assetRef);
      if(reference.projectId !== this.assetRef.projectId || reference.assetId !== this.assetRef.assetId ||
          reference.assetVersion <= this.assetRef.assetVersion) {
        throw new Error('Save returned an incompatible asset identity or version.');
      }
      this.assetRef = reference;
      this.savedFingerprint = fingerprint;
      this.persistenceState = JSON.stringify(this.snapshot().files) === fingerprint ?
        DDN_PERSISTENCE_STATES.CLEAN :
        DDN_PERSISTENCE_STATES.SAVED_NEWER_EDITS;
      this._emit({type: 'saved', revision, result});
      return result;
    } catch(error) {
      this.lastError = error;
      this.persistenceState = error?.code === 'asset_conflict' ?
        DDN_PERSISTENCE_STATES.EXTERNAL_CONFLICT :
        DDN_PERSISTENCE_STATES.SAVE_FAILED;
      this._emit({type: 'save-error', revision, error});
      throw error;
    } finally {
      this.saving = false;
    }
  }

  destroy() {
    if(this.destroyed) return;
    this.unsubscribe?.();
    this.listeners.clear();
    if(!this.tool) this.workspace.destroy();
    this.destroyed = true;
  }
}
