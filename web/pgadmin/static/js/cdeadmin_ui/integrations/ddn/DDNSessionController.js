import {loadDDNLibraries} from './library.js';
import {ddnAssetPayload,validateDDNAssetRef,validateDDNSnapshot} from './contracts.js';
import {sourceSet,checkOpen,entriesOf,selectView,captureSVG,envelope} from './runtime.js';
export const DDN_PERSISTENCE_STATES=Object.freeze({CLEAN:'clean',DIRTY:'dirty',SAVING:'saving',
  SAVED_NEWER_EDITS:'saved-newer-edits',SAVE_FAILED:'save-failed',EXTERNAL_CONFLICT:'external-conflict'});
const fingerprint=snapshot=>JSON.stringify({entry:snapshot.entry,view:snapshot.view,files:Object.entries(snapshot.files).sort(([a],[b])=>a.localeCompare(b))});
const failure=result=>new Error(result.failure?.diagnostics?.map(item=>item.message).join('\n') || result.failure?.code || 'DDN command failed.');
export class DDNSessionController {
  static async create(options={}) {
    const libraries=await loadDDNLibraries({designer:true});
    const current=new DDNSessionController(libraries,options);
    try {await current.open(options);return current;} catch(error) {current.destroy();throw error;}
  }
  constructor(libraries,options={}) {
    this.libraries=libraries;this.assetRef=options.assetRef?validateDDNAssetRef(options.assetRef):null;
    this.readOnly=Boolean(options.readOnly);this.validation=options.validation || 'strict';
    this.listeners=new Set();this.persistenceState='clean';this.saving=false;this.destroyed=false;this.lastError=null;
    this.host=options.host || document.createElement('div');
    this.runtime=libraries.viewer.createRuntime(libraries.viewer.createBrowserRuntimeOptions());
    this.viewer=libraries.viewer.createViewer(this.host,{runtime:this.runtime,controls:'standard'});
    // Editing a local design grants model edits only. Review/accept/reopen require
    // an explicit authority supplied by the owning product workflow.
    this.authority=options.authority || {authorize:async action=>({allowed:!this.readOnly && ['model.edit','model.verify'].includes(action),principal:'scratchrobin.design',grants:!this.readOnly?['model.edit','model.verify']:[]})};
  }
  async open(options) {
    const source=options.snapshot?validateDDNSnapshot(options.snapshot):options;
    const opened=checkOpen(await this.viewer.open(sourceSet(source.files,source.entry || Object.keys(source.files)[0],!this.readOnly)));
    const chosen=selectView(entriesOf(this.libraries,opened.snapshot),source.entry,source.view);
    this.entry=chosen.entry;this.view=chosen.view;
    await this.viewer.navigate({kind:'expand-view',target:{file:this.entry,id:this.view}});
    this.designer=this.libraries.designer.createDesigner(this.viewer,{authority:this.authority,controls:'standard'});
    this.savedFingerprint=fingerprint(this.getSnapshot());
    this.inputRevision=0;this.pendingInput=false;
    this.onInput=()=>{if(this.destroyed || this.readOnly)return;this.inputRevision++;this.pendingInput=true;if(!this.saving)this.persistenceState='dirty';this._emit({type:'pending-input'});};
    this.host.addEventListener('input',this.onInput);this.host.addEventListener('change',this.onInput);
    this.unsubscribe=this.runtime.subscribe(event=> {
      if(this.destroyed) return;
      if(!this.saving) this.persistenceState=this.isDirty()?'dirty':'clean';
      this._emit({type:'session',event});
    });
    this.unsubscribeViewer=this.viewer.subscribe(event=> {
      if(['viewport','ready'].includes(event.kind) && event.target && this.libraries.model.listRecords(this.runtime.snapshot().normalized).some(row=>row.kind==='view' && row.ref.file===event.target.file && row.ref.id===event.target.id)) {
        this.entry=event.target.file;this.view=event.target.id;this._emit({type:'view'});
      }
    });
  }
  _alive() {if(this.destroyed) throw new Error('DDN session has been destroyed.');}
  _writable() {this._alive();if(this.readOnly) throw new Error('This DDN workspace is read-only.');}
  _emit(event) {for(const listener of this.listeners) listener(this.state(),event);}
  getFiles() {this._alive();return this.getSnapshot().files;}
  getSnapshot() {this._alive();return envelope(this.runtime,{entry:this.entry,view:this.view});}
  isDirty() {return this.saving || this.pendingInput || fingerprint(this.getSnapshot())!==this.savedFingerprint;}
  state() {return Object.freeze({entry:this.entry,view:this.view,revision:this.runtime.snapshot()?.revision,
    readOnly:this.readOnly,validation:this.validation,persistence:this.persistenceState,lastError:this.lastError});}
  subscribe(listener) {this._alive();if(typeof listener!=='function') throw new TypeError('DDN session listener must be a function.');this.listeners.add(listener);return ()=>this.listeners.delete(listener);}
  async snapshot() {
    this._alive();
    const inputRevision=this.inputRevision;
    const artifacts=await this.designer.save();
    this._alive();
    // Save flushes inspector/dialog drafts and produces one coherent revision.
    if(!artifacts.length || artifacts.some(item=>JSON.stringify(item.revision)!==JSON.stringify(artifacts[0].revision))) throw new Error('DDN returned an incoherent save.');
    const captured={format:'ddn-source-workspace@1',entry:this.entry,view:this.view,
      files:Object.fromEntries(await Promise.all(artifacts.map(async item=>[item.name,new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(await item.blob.arrayBuffer())]))) };
    this.captureRevision=artifacts[0].revision;
    if(this.inputRevision===inputRevision)this.pendingInput=false;
    return validateDDNSnapshot(captured);
  }
  async beforeClose() {await this.snapshot();return this.isDirty();}
  async inspect() {this._alive();return this.viewer.inspect({file:this.entry,id:this.view});}
  async render() {await this.snapshot();return captureSVG(this.viewer,{entry:this.entry,view:this.view});}
  async exportSVG() {return (await this.render()).svg;}
  async review() {await this.snapshot();return this.runtime.verifier.verifyModel(this.runtime.snapshot(),{level:'semantic',scope:{kind:'workarea'},purpose:'view'});}
  async prepare(intent) {this._writable();const result=await this.designer.commands.prepare(intent);if(!result.ok) throw failure(result);return result.command;}
  async commit(plan) {this._writable();const result=await this.designer.commands.commit(plan.id);if(!result.ok) throw failure(result);return result.receipt;}
  async execute(intent) {return this.commit(await this.prepare(intent));}
  async updateSource(file,text) {
    this._writable();const source=this.runtime.sources().files.find(item=>item.id===file);
    if(!source) throw new Error('The selected DDN source does not exist.');
    return this.execute({kind:'edit-source',patches:[{file,base:source.revision,start:0,end:source.text.length,text}]});
  }
  async undo() {this._writable();const result=await this.designer.commands.undo();if(!result.ok) throw failure(result);return result.receipt;}
  async redo() {this._writable();const result=await this.designer.commands.redo();if(!result.ok) throw failure(result);return result.receipt;}
  setReadOnly(value) {this.readOnly=Boolean(value);}
  async save(saveAsset) {
    this._writable();if(this.saving) throw new Error('A DDN save is already in progress.');
    if(!this.assetRef) throw new Error('DDN session is not bound to an AssetRef.');
    if(typeof saveAsset!=='function') throw new TypeError('DDN asset save authority must be a function.');
    this.saving=true;this.persistenceState='saving';this.lastError=null;this._emit({type:'saving'});
    try {
      const captured=await this.snapshot(), saved=fingerprint(captured), revision=this.captureRevision;
      const result=await saveAsset(ddnAssetPayload(this.assetRef,captured),{expectedAssetVersion:this.assetRef.assetVersion,sourceRevision:revision});
      const reference=validateDDNAssetRef(result?.assetRef);
      if(reference.projectId!==this.assetRef.projectId || reference.assetId!==this.assetRef.assetId || reference.assetVersion<=this.assetRef.assetVersion) throw new Error('Save returned an incompatible asset identity or version.');
      this.assetRef=reference;this.savedFingerprint=saved;
      this.persistenceState=!this.pendingInput && fingerprint(this.getSnapshot())===saved?'clean':'saved-newer-edits';
      this._emit({type:'saved',revision,result});return result;
    } catch(error) {
      this.lastError=error;this.persistenceState=error?.code==='asset_conflict'?'external-conflict':'save-failed';
      this._emit({type:'save-error',error});throw error;
    } finally {this.saving=false;}
  }
  destroy() {
    if(this.destroyed) return;
    this.destroyed=true;this.host.removeEventListener('input',this.onInput);this.host.removeEventListener('change',this.onInput);this.unsubscribe?.();this.unsubscribeViewer?.();this.listeners.clear();
    for(const resource of [this.designer,this.viewer,this.runtime]) {
      try {resource?.destroy();} catch(error) {this.lastError ||= error;}
    }
  }
}
