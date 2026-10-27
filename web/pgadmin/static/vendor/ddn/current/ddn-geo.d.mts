/** DDN 0.8.0 public API. Source access is not a security boundary. */
export type SourceFiles = Record<string, string>;
export type Placement = 'source'|'auto'|'grid'|'manual'|'fit_grid'|'circular'|'radial'|'layered'|'tree'|'spanning_tree'|'mindmap'|'grouped'|'organic';
export type ProjectionKind = 'graph'|'chen'|'matrix'|'table'|'panels'|'chart'|'timeline'|'fishbone'|'decision';
export interface ProjectionMark {id:string;sourceIds:string[];property?:string;[key:string]:unknown}
export interface Options {
  endpointOrdering?: 'source'|'optimize'|'preserve';
  mark?:'source'|'bar'|'line'|'area'|'point'|'pie'|'donut';
  placement?: Placement; autoPlace?: boolean|null; center?: 'source'|'pins'|'content'; gridStep?: number|null;
  theme?: 'source'|'default'|'base'|'neutral'|'forest'|'dark'|'night'; look?: 'classic'|'handDrawn'|'neo'|null;
  routing?: 'source'|'orthogonal'|'straight'|'curved'|'rounded'; crossings?: 'source'|'gap'|'bridge'|'square_bridge';
  fields?: 'source'|'names'|'none'; domains?: 'source'|'show'|'hide'; datatypes?: 'source'|'show'|'hide'; depth?: number|null;
  labels?: 'source'|'numbers'|'text'|'tokens'; kind?: 'source'|'icon_token'|'icon'|'text'|'none';
  page?: 'source'|'content'|'web'|'a4-landscape'|'a4-portrait'|'letter-landscape'|'letter-portrait'|'custom';
  width?: number; height?: number; font?: 'source'|'sans'|'serif'|'mono'|'handwriting'; fontSize?: number|null;
  roughness?: number|null; hachure?: boolean|null;
  /** Per-verb / per-relation routing overlay (B1-011). Keys are verb ids or relation ids of the current view;
   *  relation-id keys win over verb keys, verb keys win over the view-level `routing`. Values map onto the
   *  per-relation routing hints (`rounded` → curved route with rounded bends). Unknown keys reject LIVE022,
   *  unsupported values reject LIVE023; rejected with LIVE021 on data-bound/chen views and LIVE020 on sequence views. */
  relationRouting?: Record<string,'orthogonal'|'straight'|'curved'|'rounded'>|null;
  /** View-level curve tension 0..1 (LIVE003 out of range); inert unless the effective routing is curved. */
  curveTension?: number|null;
  /** View-level rounded-corner radius in px, 0..512 (LIVE003 out of range); inert unless the effective routing is curved. */
  curveRadius?: number|null;
}
export interface LayoutState { format:'ddn-layout-state@1'; view:string; positions:Record<string,[number,number]> }
export interface Diagnostic {code:string;severity?:'info'|'warning'|'error'|'incomplete';message:string;source?:string;offset?:number}
export interface Scene {occurrences?:Array<{occurrence:string;source:string;number:number;owner?:string}>;marks?:ProjectionMark[];projection?:{kind:ProjectionKind;profile:string;sourceIds?:string[];quantitative?:boolean;[key:string]:unknown};nodes:Array<{id:string;x:number;y:number;w:number;h:number;[key:string]:unknown}>; routes:Array<Record<string,unknown>>;layoutState?:LayoutState;[key:string]:unknown}
export interface RenderRequest {entry:string;view:string;overrides?:Options;layoutState?:LayoutState|null;noMotion?:boolean;isoFrom?:{depths?:Record<string,number>}|null}
export interface RenderResult {svg:string;scene:Scene;layoutState:LayoutState|null;diagnostics:Diagnostic[];entry:string;view:string;revision:number;milliseconds:number;modelFingerprint:string;sourceMap:Record<string,Record<string,unknown>>;dependencies:string[];profiles:Record<string,unknown>;capabilities:Record<string,unknown>;keys:Record<string,number>;overrides:Options}
export interface Snapshot extends RenderRequest {format:'ddn-workspace@1';runtime:Record<string,string>;files:SourceFiles}
export interface TextEdit {file:string;start:number;end:number;text:string}
export interface DraftResult {status:'valid'|'incomplete'|'invalid';ir:Record<string,unknown>|null;diagnostics:Diagnostic[]}
export interface DraftPreview extends DraftResult {svg:string|null;scene:Scene|null}
export type EditorOperation = {type:'files';changes:SourceFiles}|{type:'edits';edits:TextEdit[]}|{type:'authoring';method:string;args:unknown[]};
export interface EditorRequest {entry:string;view:string;operations:EditorOperation[];mode?:'design'|'review';label?:string;expectedRevision?:number}
export interface EditPlan {readonly format:'ddn-edit-plan@1';readonly baseRevision:number;readonly label:string;readonly entry:string;readonly view:string;readonly mode:'design'|'review';readonly status:'valid'|'incomplete';readonly changes:ReadonlyArray<{readonly file:string;readonly before:string|null;readonly after:string|null;readonly beforeHash:string|null;readonly afterHash:string|null}>;readonly results:ReadonlyArray<unknown>;readonly diagnostics:ReadonlyArray<Diagnostic>;readonly views:ReadonlyArray<{file:string;view:string;status:'valid'|'incomplete'|'invalid'}>}
export interface EditorAdapter {readonly methods:ReadonlyArray<string>;preview(request:EditorRequest):EditPlan;capture(request:Omit<EditorRequest,'operations'>,edit:(draft:Workspace)=>unknown):EditPlan;apply(plan:EditPlan):number;cancel(plan:EditPlan):boolean;validate(entry:string,view:string):DraftResult;previewLayout(entry:string,view:string):DraftPreview;previewLayout(plan:EditPlan):DraftPreview}
export interface Workspace {
 editor(options?:{canWrite?:(file:string)=>boolean}):EditorAdapter;
 validateDraft(entry:string,view:string):DraftResult;
 previewDraft(entry:string,view:string):DraftPreview;
 documents(entry:string,view:string):ResolvedDocument[];
 commitFiles(changes:Record<string,string>,options:{expectedRevision?:number;entry:string;view:string}):number;
 checkpoint():object;restoreCheckpoint(token:object,options?:{expectedRevision?:number}):number;
 readonly revision:number;getFiles():SourceFiles;entries():Array<{file:string;views:Array<{id:string;name:string}>}>;views(entry:string):Array<{id:string;name:string}>;
 analyze(file:string):Record<string,unknown>;resolve(entry:string,view:string):Record<string,unknown>;inspect(entry:string,view:string):Record<string,unknown>;
 updateFiles(changes:SourceFiles):number;replaceFiles(files:SourceFiles):number;removeFile(file:string,options?:{force?:boolean}):number;dependents(file:string):string[];renameFile(oldName:string,newName:string):number;
 applyEdits(edits:TextEdit[],options?:{expectedRevision?:number;entry?:string;view?:string}):number;history():{canUndo:boolean;canRedo:boolean;undoLabel:string;redoLabel:string};undo():boolean;redo():boolean;
 /** Replace the records of a named `data` block, leaving every other byte of the source untouched. Records must carry the same keys as the block's existing first record. */
 replaceData(name:string,records:Array<Record<string,unknown>>):{revision:number;diagnostics:Diagnostic[]};
 subscribe(fn:(event:{revision:number;changedFiles:string[]})=>void):()=>void;
 renderSync(request:RenderRequest):RenderResult;render(request:RenderRequest):Promise<RenderResult>;exportModel(request:RenderRequest):string;exportVegaLite(request:RenderRequest):Record<string,unknown>;projectionPlan(entry:string,view:string):Record<string,unknown>; evaluateDecision(entry:string,view:string,input:Record<string,unknown>):Record<string,unknown>; simulateLifecycle(entry:string,view:string,events:Array<{event:string;data?:Record<string,unknown>}>,expected?:string):Record<string,unknown>;
 snapshot(entry:string,view:string,overrides?:Options,layoutState?:LayoutState|null):Snapshot;destroy():void;
}
export interface MountOptions extends RenderRequest {workspace:Workspace}
export interface DiagramElement extends HTMLElement {
 ready:Promise<RenderResult|{superseded:true}>;setOptions(options:Options):Promise<RenderResult|{superseded:true}>;
 exportSVG():string;getState():Record<string,unknown>;destroy():void;
}
export interface MatrixEdit {row:string;column:string;value?:unknown;remove?:boolean;id?:string}
export interface Occurrence {id:string;source:string;number:number;from?:string;to?:string}
export interface OccurrenceLayer {version:1;elements:Occurrence[];relations:Occurrence[]}
export interface AddedOccurrence {revision:number;occurrenceId:string;sourceId:string;number:number}
export interface Authoring {
 setComposition(ws:Workspace,entry:string,view:string,id:string,props:ElementComposition|null,options?:{scope?:'appearance'|'element'}):number;
 setDocument(ws:Workspace,entry:string,view:string,id:string,input:TextDocument|null,storage?:{file?:string|null;documentId?:string}):number;
 occurrences(ws:Workspace,entry:string,view:string):OccurrenceLayer;
 addOccurrence(ws:Workspace,entry:string,view:string,id:string,options?:{number?:number;x?:number;y?:number}):AddedOccurrence;
 addRelationOccurrence(ws:Workspace,entry:string,view:string,id:string,options:{from:string;to:string;number?:number}):AddedOccurrence;
 occurrencePresentation(ws:Workspace,entry:string,view:string,id:string):Record<string,unknown>;
 setOccurrencePresentation(ws:Workspace,entry:string,view:string,id:string,props:Record<string,unknown>):number;
 setMatrixCell(ws:Workspace,entry:string,view:string,row:string,column:string,value:unknown,options?:{remove?:boolean;id?:string}):number;
 setMatrixCells(ws:Workspace,entry:string,view:string,changes:MatrixEdit[]):number;
 setRecordValue(ws:Workspace,entry:string,view:string,id:string,key:string,value:unknown):number;
 /** Workspace-level record replacement backing `ws.replaceData`. */
 replaceData(ws:Workspace,name:string,records:Array<Record<string,unknown>>):{revision:number;diagnostics:Diagnostic[]};
 setAssignment(ws:Workspace,entry:string,view:string,id:string,code:string):number;
 value(value:unknown):string;
 setLabel(ws:Workspace,entry:string,view:string,id:string,label:string):number;
 setProperty(ws:Workspace,entry:string,view:string,id:string,key:string,value:unknown):number;
 /** B1-050: write presentation state into the view's source (profile groups,
  * route members, x_tool_presentation extension record) as one validated
  * transaction; the canonical value serializer is reused. */
 setViewProfile(ws:Workspace,entry:string,view:string,groups:Record<string,Record<string,unknown>>,options?:{routes?:Record<string,Record<string,unknown>>;presentation?:Record<string,unknown>|null}):number;
 /** Designer phase 1: flat view-level metadata (title, description, source, generator); undefined removes. */
 setViewProperties(ws:Workspace,entry:string,view:string,props:Record<string,unknown>):number;
 /** Designer phase 1: publication chrome child groups (header/footer run bands, page border, page background); null removes a concern. */
 setViewChrome(ws:Workspace,entry:string,view:string,concerns:Record<string,unknown>):number;
 /** Designer phase 3: batch property write on a RELATION definition (kind, description, cardinality source_/target_ min/max, enforcement, scope, source_mark/target_mark); undefined removes a property. Core validation re-runs at commit. */
 setRelationProps(ws:Workspace,entry:string,view:string,id:string,props:Record<string,unknown>):number;
 /** Designer phase 3: merge-write an x_* extension record on a relation (e.g. x_endlabels.source/target); a sub-record of null removes that key, undefined removes the extension. DDN-PJ149 is judged at commit. */
 setRelationExtension(ws:Workspace,entry:string,view:string,id:string,key:string,rec:Record<string,unknown>|undefined):number;
 pin(ws:Workspace,entry:string,view:string,id:string,x:number,y:number):number;unpin(ws:Workspace,entry:string,view:string,id:string):number|false;hide(ws:Workspace,entry:string,view:string,id:string):number|false;
 renameDefinition(ws:Workspace,entry:string,view:string,id:string,newId:string):number;
 columnLayout(ws:Workspace,entry:string,view:string,id:string):Array<Record<string,unknown>>|null;
 setColumnLayout(ws:Workspace,entry:string,view:string,id:string,columns:Array<Record<string,unknown>>|null):number;
 creationDestinations(ws:Workspace):Array<{file:string;module:string;block:string}>;
 addElement(ws:Workspace,entry:string,view:string,data:{id:string;name?:string;kind?:string;destination?:{file:string;module:string;block:string}}):number;
 addField(ws:Workspace,entry:string,view:string,parent:string,data:{id:string;name?:string}):number;
 addRelation(ws:Workspace,entry:string,view:string,data:{id:string;name?:string;kind?:string;from:string;to:string}):number;
 deleteDefinition(ws:Workspace,entry:string,view:string,id:string):number;
 sourceOf(ws:Workspace,entry:string,view:string,id:string):{file:string;start:number;end:number;type:string;id:string;name:string;properties:Record<string,unknown>};
}
export interface IO {
 open(files:FileList|File[],options?:{directory?:boolean}):Promise<{files:SourceFiles;snapshot:Snapshot;ignored:string[]}>;
 toJSON(snapshot:Snapshot):string;toZIP(snapshot:Snapshot):Uint8Array;unzip(bytes:Uint8Array):Promise<{files:Record<string,string>;ignored:string[]}>;zipStore(files:Record<string,string>):Uint8Array;
 crc32(bytes:Uint8Array):number;download(name:string,data:BlobPart,type?:string):void;
 bundle(files:SourceFiles,entry:string):{text:string;diagnostics:Array<{code:string;severity:string;message:string;source?:string}>};
}
export const profileCatalogue:{version:string;profiles:Array<Record<string,unknown>>;kinds:Array<Record<string,unknown>>;relationships:Array<Record<string,unknown>>;[key:string]:unknown};
export const VERSION:string;
export const runtime:Record<string,string>;
export function createWorkspace(files:SourceFiles):Workspace;
export function registerWorkspace(name:string,files:SourceFiles|Workspace):Workspace;
export function mount(element:Element,options:MountOptions):DiagramElement;
export function fromSnapshot(snapshot:Snapshot):MountOptions;
export function parse(source:string,file?:string):Record<string,unknown>;
export const authoring:Authoring;
export const io:IO;
export interface Defaults extends Record<string,unknown> {
 /** Deep copy of the registry default property set for an element kind; `{}` when absent (B1-002). */
 forKind(kind:string):Record<string,unknown>;
}
export const defaults:Defaults;
export interface Glyphs {
 /** Miniature profile contour from the diagram renderer; falls back to the registered glyph without the graph module. */
 previewForKind(kind:string,profile?:string):{kind:string;glyph:string;viewBox:string;svg:string;meaning:string}|null;
 /** Registered plate glyph for a kind keyword (or registry id): symbol body + viewBox; null when absent (B1-012). */
 forKind(kind:string):{kind:string;glyph:string;viewBox:string;svg:string;meaning:string}|null;
}
export const glyphs:Glyphs;
/** Designer phase 2: palette kind choice with capability metadata. */
export interface KindChoice{id:string;label:string;code:string;group:string|null;allowed_in:string[];composition?:ElementComposition}
export interface VerbChoice{id:string;label:string;code:string;allowed_in:string[]}
export const kinds:KindChoice[];
export const relations:VerbChoice[];
/** Legal verbs for an endpoint kind pair, from the merged registry's endpoint contracts (same data as the CLI verbs query). */
export function legalVerbs(from:string,to:string):string[];
export const capabilities:{viewCapabilities(projection:{kind?:string;profile?:string}|null|undefined):string[];allowedInView(allowed:string[],projection:{kind?:string;profile?:string}|null|undefined):boolean;paletteGroups:string[]};
declare const DDNLive:{occurrenceId:typeof occurrenceId;expandOccurrences:typeof expandOccurrences;profileCatalogue:typeof profileCatalogue;VERSION:typeof VERSION;runtime:typeof runtime;createWorkspace:typeof createWorkspace;registerWorkspace:typeof registerWorkspace;mount:typeof mount;fromSnapshot:typeof fromSnapshot;authoring:Authoring;io:IO;parse:typeof parse;defaults:Defaults;glyphs:Glyphs;kinds:typeof kinds;relations:typeof relations;legalVerbs:typeof legalVerbs;capabilities:typeof capabilities;setTextProvider(fn:((text:string,size:number,font:string,weight:number)=>{width:number;ascent?:number;descent?:number})|null,name?:string):void;setTextMetrics(metrics:Record<string,unknown>):void};
export default DDNLive;

/** Stable, opaque visual id. Ordinal 1 keeps the historical model id. */
export function occurrenceId(view:string,source:string,number?:number):string;
/** Rendering/UI projection only; workspace.resolve remains semantic. */
export function expandOccurrences(ir:any):any;

export interface ElementComposition {sections?:Array<'name'|'type'|'table'|'notes'>;order?:Array<'table'|'notes'>;note_height?:number;note_wrap?:'auto'|'on'|'off'}
export interface TextDocument {format?:'plain'|'markdown_text'|'code';role?:'note'|'procedure_source'|'function_source'|'source';language?:string;text:string;digest?:string}
export interface ResolvedDocument extends TextDocument {elementId:string;storage?:{file:string;id:string}}
