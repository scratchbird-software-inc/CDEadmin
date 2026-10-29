import { drawerFor } from '../../viewer/src/drawer.js';
import { ddnLogoDataURL, ddnLogoDarkDataURL } from './brand.js';
import { uiIcon } from '../../viewer/src/ui-icons.js';
import { normalizeLocation, listRecords } from '../../model/src/index.js';
import { installUITheme, setUITheme, UI_THEME_NAMES } from '../../viewer/src/ui-theme.js';
import { createStandardDialog, colourField, syncColourField, numberField } from '../../viewer/src/dialogs.js';
import { choiceField } from '../../viewer/src/choice-field.js';
import { DRAFT_KEY, encodeDraftAsset, readDocumentDraft, restoreDraftAssets } from './document-draft.js';
import { decodeSources } from '../../language/src/index.js';
import { findUICommand, commandEnabled, UI_COMMANDS_CHANGED } from '../../viewer/src/ui-commands.js';
import { popOut, floatPanel, syncDetachedThemes } from '../../viewer/src/popout.js';
import { createMenuBar, openPopupMenu } from './menus.js';
import { zipFiles } from './zip.js';
const BLANK_DOCUMENT = '';
const examples = {
    'ERD whiteboard': 'erd Sales : Sales design\n    Customer\n    Order\n    connect Customer to Order\n',
    'Mind map': 'mindmap Product\n    Research\n        Interviews\n        Prototypes\n    Delivery\n        Design\n        Build\n',
    'Concept map': 'view Knowledge as "concept.map@1"\n    element Concept as object\n    element Evidence as object\n    connect Concept to Evidence as assoc : supports\n',
    'Table': 'data Tasks\n    task:lt:60.owner:lt.status:ct\n    Design.Alex.Draft\n    Build.Sam.In-progress\nview Records as table.records@1\n    with\n        projection.options\n            records Tasks\n            columns 3\n            missing gap\n',
};
export function mountShell(factories) {
    const doc = document;
    const host = doc.defaultView;
    installUITheme(doc.body);
    let interfaceTheme = 'dark', interfaceTokens = {};
    setUITheme(doc.body, interfaceTheme);
    try {
        const saved = JSON.parse(localStorage.getItem('ddn.interface.v1') ?? 'null');
        if (saved) {
            setUITheme(doc.body, saved.name, saved.overrides);
            interfaceTheme = saved.name;
            interfaceTokens = saved.overrides ?? {};
        }
    }
    catch { }
    const query = new URLSearchParams(doc.defaultView?.location.search);
    const requestedTheme = query.get('theme');
    if (UI_THEME_NAMES.includes(requestedTheme)) {
        interfaceTheme = requestedTheme;
        interfaceTokens = {};
        setUITheme(doc.body, interfaceTheme);
    }
    const isDesigner = factories.mode === 'designer', isVerifier = factories.mode === 'verifier';
    doc.title = 'DDN ' + (isDesigner ? 'Designer' : isVerifier ? 'Verifier' : 'Viewer');
    const style = doc.createElement('style');
    style.textContent = `
:root{font-family:Inter,system-ui,sans-serif;color:var(--ddn-ui-text);background:var(--ddn-ui-bg)}
*{box-sizing:border-box}body{margin:0;min-height:100vh;height:100dvh;display:flex;flex-direction:column;background:var(--ddn-ui-bg);color:var(--ddn-ui-text);font-size:var(--ddn-ui-font-size)}
button,select,input,textarea{font:inherit}button{display:inline-flex;align-items:center;justify-content:center;gap:7px;cursor:pointer;border:1px solid var(--ddn-ui-border);background:var(--ddn-ui-surface);border-radius:9px;padding:6px 10px;color:var(--ddn-ui-text);transition:background .15s,border-color .15s,box-shadow .15s}
button:hover{background:color-mix(in srgb,var(--ddn-ui-accent) 9%,var(--ddn-ui-surface));border-color:color-mix(in srgb,var(--ddn-ui-accent) 55%,var(--ddn-ui-border))}button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible,a:focus-visible{outline:2px solid var(--ddn-ui-accent);outline-offset:3px}
button>svg,.app-source-heading>svg{width:16px;height:16px;flex:none}select,input{color:var(--ddn-ui-text);background:var(--ddn-ui-input);border:1px solid var(--ddn-ui-border);border-radius:8px;padding:5px 8px;min-height:30px}select{max-width:100%;text-overflow:ellipsis}button:disabled{cursor:default;opacity:.55}
.app-bar{display:flex;align-items:center;gap:14px;flex-wrap:wrap;padding:6px 14px;min-height:48px;background:color-mix(in srgb,var(--ddn-ui-surface) 88%,transparent);border-bottom:1px solid var(--ddn-ui-border);backdrop-filter:blur(16px);flex:none}
.app-brand{display:flex;align-items:center;gap:10px;min-width:0}.app-brand-mark{display:grid;place-items:center;width:32px;height:32px;flex:none;border:1px solid color-mix(in srgb,var(--ddn-ui-accent) 25%,var(--ddn-ui-border));border-radius:9px;background:color-mix(in srgb,var(--ddn-ui-accent) 7%,var(--ddn-ui-bg))}.app-brand-mark img{width:22px;height:22px;object-fit:contain}.app-brand-mark .app-logo-dark{display:none}[data-ddn-ui-theme=dark] .app-brand-mark .app-logo-light,[data-ddn-ui-theme=midnight] .app-brand-mark .app-logo-light{display:none}[data-ddn-ui-theme=dark] .app-brand-mark .app-logo-dark,[data-ddn-ui-theme=midnight] .app-brand-mark .app-logo-dark{display:block}
.app-brand-copy{display:flex;flex-direction:column;gap:1px;min-width:0}.app-bar strong{font-size:14px;letter-spacing:-.03em;font-weight:700;line-height:1.2;white-space:nowrap}.app-bar small{font-size:10px;color:var(--ddn-ui-muted);letter-spacing:.02em;white-space:nowrap}.app-interface{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-left:auto}.app-interface label{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--ddn-ui-muted)}.app-interface select{min-width:90px;min-height:30px;padding:4px 8px}.app-interface button{min-height:30px;padding:4px 9px;font-size:12px}
.app-site-links{display:flex;align-items:center;gap:2px;flex-wrap:wrap}.app-site-links a{display:inline-flex;align-items:center;gap:5px;padding:5px 8px;border-radius:7px;color:var(--ddn-ui-muted);text-decoration:none;font-size:12px}.app-site-links a:hover{background:color-mix(in srgb,var(--ddn-ui-accent) 10%,transparent);color:var(--ddn-ui-text)}.app-site-links a svg{width:14px;height:14px}.app-site-links a[aria-current=page]{color:var(--ddn-ui-accent);background:color-mix(in srgb,var(--ddn-ui-accent) 12%,transparent);font-weight:650}
.app-document-toggle{display:none}.app-tools{display:flex;gap:6px;align-items:center;flex-wrap:wrap;padding:5px 14px;border-bottom:1px solid var(--ddn-ui-border);background:color-mix(in srgb,var(--ddn-ui-surface) 65%,var(--ddn-ui-bg));flex:none}.app-tools button{min-height:30px;padding:5px 9px;font-size:12px;white-space:nowrap}.app-tools label{display:flex;align-items:center;gap:6px;min-width:0;max-width:100%;font-size:11px;color:var(--ddn-ui-muted)}.app-tools label[hidden],.app-tools button[hidden],.app-source-toolbar button[hidden]{display:none}.app-tools select{min-width:0;max-width:240px;font-size:12px;min-height:30px}.app-tools input:not([type=file]){max-width:120px}.app-tools .app-primary,.app-source-toolbar .app-primary{background:var(--ddn-ui-accent);color:var(--ddn-ui-accent-text);border-color:transparent;font-weight:650}.app-tools .app-primary:hover,.app-source-toolbar .app-primary:hover{filter:brightness(1.08)}.app-tools .app-spacer{flex:1 1 auto}
.app-menu-host{position:relative}.app-menu{position:absolute;top:calc(100% + 4px);left:0;z-index:60;min-width:230px;display:grid;gap:2px;padding:6px;background:var(--ddn-ui-surface);border:1px solid var(--ddn-ui-border);border-radius:10px;box-shadow:0 14px 40px color-mix(in srgb,var(--ddn-ui-shadow) 70%,transparent)}.app-menu[hidden]{display:none}.app-menu button{justify-content:flex-start;gap:9px;border:0;background:transparent;border-radius:7px;padding:7px 9px;font-size:12px;width:100%;text-align:left}.app-menu button:hover,.app-menu button:focus-visible{background:color-mix(in srgb,var(--ddn-ui-accent) 12%,var(--ddn-ui-surface));color:var(--ddn-ui-text)}.app-menu button kbd{margin-left:auto;font:11px ui-monospace,monospace;color:var(--ddn-ui-muted)}.app-menu hr{width:100%;border:0;border-top:1px solid var(--ddn-ui-border);margin:3px 0}.app-menu .app-menu-head{padding:4px 9px 2px;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--ddn-ui-muted)}
.app-main{display:grid;grid-template-columns:minmax(230px,24%) minmax(0,1fr);flex:1;min-height:360px;gap:10px;padding:10px 12px;isolation:isolate;position:relative}.app-source{display:flex;flex-direction:column;min-height:0;min-width:0;border:1px solid var(--ddn-ui-border);border-radius:12px;background:var(--ddn-ui-surface);overflow:hidden;box-shadow:0 6px 24px color-mix(in srgb,var(--ddn-ui-shadow) 45%,transparent)}.app-source-heading{display:flex;align-items:center;gap:8px;padding:8px 10px;border-bottom:1px solid var(--ddn-ui-border);font-size:12px;font-weight:650}.app-source-heading>svg{color:var(--ddn-ui-accent)}.app-source-kind{margin-left:auto;font-size:10px;font-weight:500;color:var(--ddn-ui-muted);text-transform:uppercase;letter-spacing:.07em}
.app-source-toolbar{display:flex;align-items:center;gap:5px;flex-wrap:wrap;padding:6px 8px;border-bottom:1px solid var(--ddn-ui-border);background:color-mix(in srgb,var(--ddn-ui-surface) 65%,var(--ddn-ui-bg))}.app-source-toolbar button{min-height:28px;padding:3px 9px;font-size:12px}.app-source-toolbar .app-dirty{margin-left:auto;font-size:11px;color:var(--ddn-ui-muted)}.app-source-toolbar .app-dirty[data-state=dirty]{color:var(--ddn-ui-accent);font-weight:600}
.app-source textarea{width:100%;resize:none;flex:1;min-height:140px;border:0;outline-offset:-3px;padding:12px 14px;background:var(--ddn-ui-input);color:var(--ddn-ui-text);font:12px/1.6 'JetBrains Mono',ui-monospace,monospace;tab-size:4;border-radius:0;scrollbar-color:var(--ddn-ui-border) transparent;white-space:pre;overflow:auto}.app-source textarea[aria-invalid=true]{box-shadow:inset 3px 0 0 var(--ddn-ui-danger)}
.app-diagnostics{max-height:112px;overflow:auto;border-top:1px solid var(--ddn-ui-border);font-size:11px;line-height:1.45;background:color-mix(in srgb,var(--ddn-ui-danger) 7%,var(--ddn-ui-surface))}.app-diagnostics:empty{display:none}.app-diagnostics button{display:flex;gap:8px;width:100%;text-align:left;border:0;border-radius:0;background:transparent;padding:6px 10px;color:var(--ddn-ui-text);font-size:11px;line-height:1.45;justify-content:flex-start}.app-diagnostics button:hover{background:color-mix(in srgb,var(--ddn-ui-danger) 14%,var(--ddn-ui-surface))}.app-diagnostics b{flex:none;color:var(--ddn-ui-danger);font-weight:650}
.app-note{padding:7px 12px;font-size:11px;line-height:1.5;color:var(--ddn-ui-muted);border-top:1px solid var(--ddn-ui-border)}.app-note kbd{font:10px ui-monospace,monospace;padding:1px 4px;border:1px solid var(--ddn-ui-border);border-radius:4px}
.app-surface{min-width:0;min-height:0;background:var(--ddn-ui-surface);border:1px solid var(--ddn-ui-border);border-radius:12px;overflow:hidden;box-shadow:0 6px 24px color-mix(in srgb,var(--ddn-ui-shadow) 45%,transparent)}.app-surface>.ddn-viewer{height:100%;min-height:0;border:0}.app-main[data-source-hidden=true]{grid-template-columns:minmax(0,1fr)}.app-main[data-source-hidden=true]>.app-source{display:none}
.app-banner{grid-column:1/-1;display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:8px 12px;border:1px solid color-mix(in srgb,var(--ddn-ui-accent) 40%,var(--ddn-ui-border));border-radius:10px;background:color-mix(in srgb,var(--ddn-ui-accent) 9%,var(--ddn-ui-surface));font-size:12px}.app-banner button{min-height:28px;padding:3px 9px;font-size:12px}.app-banner .app-primary{background:var(--ddn-ui-accent);color:var(--ddn-ui-accent-text);border-color:transparent;font-weight:650}.app-banner .app-spacer{flex:1 1 auto}
.app-status{padding:6px 14px;font-size:11px;line-height:1.5;color:var(--ddn-ui-muted);border-top:1px solid var(--ddn-ui-border);background:var(--ddn-ui-surface);flex:none;display:flex;gap:16px;align-items:center}.app-status:empty{display:none}.app-status .app-status-text{flex:1 1 auto;min-width:0}.app-status .app-saved{flex:none;color:var(--ddn-ui-muted)}.app-error .app-status-text{color:var(--ddn-ui-danger)}.app-report{padding:24px;overflow:auto;height:100%}.app-report h2{font-size:20px;letter-spacing:-.03em;margin:0 0 10px}.app-report>p{color:var(--ddn-ui-muted);font-size:12px}.app-report>input{width:min(100%,420px);margin:8px 0 18px}.app-report table{width:100%;border-collapse:collapse;text-align:left;font-size:12px}.app-report th,.app-report td{padding:12px 10px;border-bottom:1px solid var(--ddn-ui-border);vertical-align:top;overflow-wrap:anywhere}.app-report th{background:var(--ddn-ui-bg)}.app-report code{white-space:pre-wrap}.app-pending{font-weight:600;color:var(--ddn-ui-accent)}
.app-toasts{position:fixed;right:16px;bottom:48px;z-index:80;display:grid;gap:6px;pointer-events:none}.app-toast{pointer-events:auto;display:flex;align-items:center;gap:8px;padding:8px 12px;border-radius:10px;background:var(--ddn-ui-text);color:var(--ddn-ui-bg);font-size:12px;box-shadow:0 10px 30px color-mix(in srgb,var(--ddn-ui-shadow) 60%,transparent);animation:app-toast-in .18s ease-out}.app-toast[data-kind=error]{background:var(--ddn-ui-danger);color:#fff}.app-toast svg{width:14px;height:14px;flex:none}@keyframes app-toast-in{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.app-samples{display:grid;gap:4px;max-height:360px;overflow:auto;border:1px solid var(--ddn-ui-border);border-radius:8px;padding:4px}.app-samples button{justify-content:flex-start;text-align:left;border:0;background:transparent;border-radius:6px;padding:6px 8px;gap:8px;width:100%}.app-samples button[aria-pressed=true]{background:color-mix(in srgb,var(--ddn-ui-accent) 15%,var(--ddn-ui-surface));color:var(--ddn-ui-accent)}.app-samples small{color:var(--ddn-ui-muted);margin-left:auto;font-size:10px;white-space:nowrap}.app-samples .app-menu-head{padding:6px 8px 2px;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--ddn-ui-muted)}
.app-shortcuts{display:grid;grid-template-columns:auto 1fr;gap:4px 14px;font-size:12px;margin:0}.app-shortcuts dt{font:11px ui-monospace,monospace;color:var(--ddn-ui-accent);white-space:nowrap}.app-shortcuts dd{margin:0}
@media(max-width:1050px){.app-bar{gap:10px;padding:6px 12px}.app-tools{padding:5px 12px}.app-main{padding:8px;gap:8px;grid-template-columns:minmax(210px,25%) minmax(0,1fr)}.app-tools select{max-width:200px}.app-bar small{display:none}}
@media(max-width:750px){.app-document-toggle{display:inline-flex}.app-tools:not([data-expanded=true]){display:none}body{height:auto;min-height:100dvh}.app-bar{padding:8px 10px;gap:8px}.app-brand{flex:1 1 auto}.app-interface{margin-left:0;gap:6px}.app-bar strong{font-size:13px}.app-interface label{font-size:11px}.app-tools{padding:8px 10px;gap:6px}.app-tools label{flex-wrap:wrap}.app-tools select{max-width:calc(100vw - 70px)}.app-main{grid-template-columns:minmax(0,1fr);flex:none;min-height:0;padding:8px;gap:8px}.app-source{height:280px}.app-surface{height:660px}.app-main[data-source-hidden=true] .app-surface{height:max(500px,calc(100dvh - 170px))}.app-status{padding:6px 10px}.app-report{padding:16px}.app-report td{padding:8px 5px}.app-toasts{right:8px;left:8px;bottom:40px}}
@media(max-width:760px){.app-surface:has(.ddn-viewer[data-ddn-dock-left]),.app-surface:has(.ddn-viewer[data-ddn-dock-right]){height:max(880px,calc(100dvh - 170px))}.app-surface:has(.ddn-viewer[data-ddn-dock-left][data-ddn-dock-right]){height:max(1100px,calc(100dvh - 170px))}}
@media(prefers-reduced-motion:reduce){button{transition:none}.app-toast{animation:none}}
.app-menubar{display:flex;align-items:center;gap:1px;min-width:0;flex:0 1 auto}.app-menubar>.app-menu-host>button{border:0;background:transparent;border-radius:7px;padding:5px 9px;min-height:30px;font-size:12.5px;font-weight:550;color:var(--ddn-ui-text)}.app-menubar>.app-menu-host>button:hover,.app-menubar>.app-menu-host>button[aria-expanded=true]{background:color-mix(in srgb,var(--ddn-ui-accent) 13%,transparent)}
.app-menu{max-height:calc(100dvh - 90px);overflow:auto;min-width:260px}.app-menu button{gap:6px}.app-menu button[aria-disabled=true]{opacity:.5;cursor:default}.app-menu button[aria-disabled=true]:hover{background:transparent}.app-menu .app-menu-check{width:14px;flex:none;text-align:center;color:var(--ddn-ui-accent);font-weight:700}.app-menu .app-menu-label{flex:1 1 auto;white-space:nowrap}.app-menu .app-menu-arrow{margin-left:auto;color:var(--ddn-ui-muted)}.app-menu .app-menu-badge{font-size:9.5px;letter-spacing:.04em;padding:1px 6px;border-radius:999px;border:1px solid var(--ddn-ui-border);color:var(--ddn-ui-muted);white-space:nowrap}.app-menu .app-menu-head{padding-left:29px}
.app-submenu-host{position:relative}.app-submenu{position:absolute;top:-6px;left:calc(100% + 2px);z-index:61}.app-submenu[data-flip]{left:auto;right:calc(100% + 2px)}
.app-bar .app-site-links:not(.app-mode-links) a span{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}.app-bar .app-site-links:not(.app-mode-links) a{padding:5px 6px}
.app-interface>label>.app-theme-word{display:none}
.app-main{grid-template-columns:var(--ddn-source-width,340px) 6px minmax(0,1fr);gap:0 4px}.app-main>.app-source{grid-column:1}.app-main>.app-splitter{grid-column:2}.app-main>.app-surface{grid-column:3}.app-main>.app-rail{display:none}
.app-splitter{cursor:col-resize;border-radius:4px;align-self:stretch;position:relative;outline-offset:-2px;touch-action:none}.app-splitter::after{content:'';position:absolute;inset:30% 2px;border-radius:2px;background:var(--ddn-ui-border);opacity:0;transition:opacity .15s}.app-splitter:hover::after,.app-splitter:focus-visible::after,.app-splitter[data-dragging]::after{opacity:1}
.app-rail{display:flex;flex-direction:column;align-items:center;gap:6px;padding:6px 0;border:1px solid var(--ddn-ui-border);border-radius:10px;background:var(--ddn-ui-surface)}.app-rail button{writing-mode:vertical-rl;transform:rotate(180deg);padding:10px 4px;min-height:0;font-size:11.5px;border:0;background:transparent;gap:6px}.app-rail button svg{transform:rotate(90deg)}
.app-source-heading .ddn-drawer-controls{display:flex;gap:2px;margin-left:auto}.app-source-heading .ddn-drawer-controls button{padding:4px;min-width:24px;width:24px;border:0;background:transparent;color:var(--ddn-ui-muted)}.app-source-heading .ddn-drawer-controls button[hidden]{display:none}.app-source-heading .app-source-collapse{margin-left:2px}
.app-main[data-source-hidden=true],.app-main[data-source-detached=true]{grid-template-columns:30px minmax(0,1fr)}.app-main[data-source-hidden=true]>.app-rail,.app-main[data-source-detached=true]>.app-rail{display:flex;grid-column:1}.app-main[data-source-hidden=true]>.app-surface,.app-main[data-source-detached=true]>.app-surface{grid-column:2}.app-main[data-source-hidden=true]>.app-splitter,.app-main[data-source-detached=true]>.app-splitter{display:none}.app-main[data-source-detached=true]>.app-source{display:none}
.app-source-heading .app-source-collapse{margin-left:4px;min-height:24px;padding:2px 6px;font-size:11px;border-color:transparent;background:transparent}.app-source-heading .app-source-collapse svg{width:13px;height:13px}
.app-zoom{display:flex;align-items:center;gap:2px;flex:none}.app-zoom[hidden]{display:none}.app-zoom button{min-height:22px;padding:1px 7px;font-size:11px;border-color:transparent;background:transparent}.app-zoom .app-zoom-value{min-width:62px;font-variant-numeric:tabular-nums;border-color:var(--ddn-ui-border)}
.app-bar{position:relative}.app-bar:has(.app-menubar[data-open]){z-index:55}.app-surface[data-ddn-menus] .ddn-viewer>.ddn-viewer-toolbar:not(.ddn-designer-toolbar),.app-surface[data-ddn-quick=hidden] .ddn-designer-toolbar{height:0;min-height:0;padding:0;margin:0;border:0;overflow:hidden;visibility:hidden}
.app-surface[data-ddn-outline=hidden] .ddn-viewer-outline{display:none}.app-surface[data-ddn-outline=hidden] .ddn-viewer:not([data-ddn-dock-left]){grid-template-columns:minmax(0,1fr)}.app-surface[data-ddn-outline=hidden] .ddn-viewer:not([data-ddn-dock-left]) .ddn-viewer-stage{grid-column:1}.app-surface[data-ddn-outline=hidden] .ddn-viewer:not([data-ddn-dock-left])[data-ddn-dock-right]{grid-template-columns:minmax(0,1fr) 320px}.app-surface[data-ddn-outline=hidden] .ddn-viewer:not([data-ddn-dock-left])[data-ddn-dock-right] .ddn-designer-dock-right{grid-column:2}
body[data-ddn-status=hidden] .app-status{display:none}
body[data-ddn-motion=reduced] *,body[data-ddn-motion=reduced] *::before,body[data-ddn-motion=reduced] *::after{transition:none!important;animation:none!important;scroll-behavior:auto!important}
body[data-ddn-contrast=high]{--ddn-ui-border:var(--ddn-ui-text);--ddn-ui-muted:var(--ddn-ui-text)}body[data-ddn-contrast=high] :focus-visible{outline-width:3px!important}
.app-command-list{display:grid;gap:2px;max-height:360px;overflow:auto;margin-top:8px}.app-command-list button{justify-content:flex-start;text-align:left;border:0;background:transparent;padding:6px 8px;gap:8px;width:100%}.app-command-list button[aria-selected=true]{background:color-mix(in srgb,var(--ddn-ui-accent) 15%,var(--ddn-ui-surface))}.app-command-list small{color:var(--ddn-ui-muted)}.app-command-list kbd{margin-left:auto;font:11px ui-monospace,monospace;color:var(--ddn-ui-muted)}
.app-tools[data-empty=true]{display:none}
@media(max-width:1050px){.app-bar .app-mode-links a span{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}}
@media(max-width:750px){.app-menubar{order:3;flex:1 1 100%;flex-wrap:wrap}.app-menubar>.app-menu-host>button{padding:4px 7px}.app-main,.app-main[data-source-hidden=true],.app-main[data-source-detached=true]{grid-template-columns:minmax(0,1fr)}.app-main>.app-source,.app-main>.app-surface,.app-main>.app-rail{grid-column:1!important}.app-main>.app-splitter{display:none}.app-rail{flex-direction:row;padding:0 6px}.app-rail button{writing-mode:horizontal-tb;transform:none}.app-rail button svg{transform:none}.app-tools[data-empty=true]{display:none!important}}`;
    doc.head.append(style);
    const bar = doc.createElement('header');
    bar.className = 'app-bar';
    const brandGroup = doc.createElement('div');
    brandGroup.className = 'app-brand';
    const mark = doc.createElement('span');
    mark.className = 'app-brand-mark';
    for (const [className, src] of [['app-logo-light', ddnLogoDataURL], ['app-logo-dark', ddnLogoDarkDataURL]]) {
        const logo = doc.createElement('img');
        logo.className = className;
        logo.src = src;
        logo.alt = 'DDN';
        logo.width = 22;
        logo.height = 22;
        mark.append(logo);
    }
    const brandCopy = doc.createElement('div');
    brandCopy.className = 'app-brand-copy';
    const brand = doc.createElement('strong');
    brand.textContent = doc.title;
    const sub = doc.createElement('small');
    sub.textContent = (factories.edition === 'complete' ? 'Complete profile edition' : 'Native edition') + ' · ddn-next-1 · everything runs locally';
    brandGroup.title = sub.textContent;
    brandCopy.append(brand, sub);
    brandGroup.append(mark, brandCopy);
    bar.append(brandGroup);
    // The website navigation (if any) mounts its links into this slot so the tool needs one bar, not two.
    const siteSlot = doc.createElement('div');
    siteSlot.className = 'app-site-slot';
    bar.append(siteSlot);
    const interfaceControls = doc.createElement('div');
    interfaceControls.className = 'app-interface';
    bar.append(interfaceControls);
    const tools = doc.createElement('nav');
    tools.className = 'app-tools';
    tools.setAttribute('aria-label', 'Document controls');
    const main = doc.createElement('main');
    main.className = 'app-main';
    const panel = doc.createElement('section');
    panel.className = 'app-source';
    panel.setAttribute('aria-label', 'DDN source');
    const sourceLabel = doc.createElement('label');
    sourceLabel.textContent = 'DDN source';
    const sourceHeading = doc.createElement('div');
    sourceHeading.className = 'app-source-heading';
    const sourceKind = doc.createElement('small');
    sourceKind.className = 'app-source-kind';
    sourceKind.textContent = factories.mode === 'viewer' ? 'Read only' : 'Source';
    sourceHeading.append(uiIcon(doc, 'code'), sourceLabel, sourceKind);
    const sourceToolbar = doc.createElement('div');
    sourceToolbar.className = 'app-source-toolbar';
    sourceToolbar.setAttribute('role', 'toolbar');
    sourceToolbar.setAttribute('aria-label', 'Source actions');
    const editor = doc.createElement('textarea');
    editor.id = 'ddn-source';
    editor.setAttribute('aria-label', 'DDN source');
    editor.spellcheck = false;
    editor.readOnly = factories.mode === 'viewer';
    editor.wrap = 'off';
    sourceLabel.htmlFor = editor.id;
    const diagnosticsList = doc.createElement('div');
    diagnosticsList.className = 'app-diagnostics';
    diagnosticsList.setAttribute('role', 'list');
    diagnosticsList.setAttribute('aria-label', 'Source problems');
    const sourceNote = doc.createElement('div');
    sourceNote.className = 'app-note';
    sourceNote.append(doc.createTextNode(isDesigner ? 'Indent with spaces · ' : 'Indent with spaces. '));
    if (isDesigner) {
        const k1 = doc.createElement('kbd');
        k1.textContent = 'Ctrl+Enter';
        const k2 = doc.createElement('kbd');
        k2.textContent = 'Esc';
        const k3 = doc.createElement('kbd');
        k3.textContent = 'Tab';
        sourceNote.append(k1, doc.createTextNode(' applies · '), k2, doc.createTextNode(' then '), k3, doc.createTextNode(' leaves the editor. Nothing is uploaded; work is kept in this browser.'));
    }
    else
        sourceNote.append(doc.createTextNode('Nothing is uploaded; processing is local to this page.'));
    panel.append(sourceHeading, sourceToolbar, editor, diagnosticsList, sourceNote);
    const surface = doc.createElement('section');
    surface.className = 'app-surface';
    surface.setAttribute('aria-label', isVerifier ? 'Verification results' : 'Diagram workspace');
    main.append(panel, surface);
    const status = doc.createElement('footer');
    status.className = 'app-status';
    const statusText = doc.createElement('span');
    statusText.className = 'app-status-text';
    statusText.setAttribute('role', 'status');
    statusText.setAttribute('aria-live', 'polite');
    const savedIndicator = doc.createElement('span');
    savedIndicator.className = 'app-saved';
    status.append(statusText, savedIndicator);
    const toasts = doc.createElement('div');
    toasts.className = 'app-toasts';
    toasts.setAttribute('aria-live', 'polite');
    doc.body.replaceChildren(bar, tools, main, status, toasts);
    const files = new Map(), assets = new Map();
    let entry = 'main.ddn', sequence = 0, lastReport, viewer, designer, editorDirty = false, sourceConflict = false, editGeneration = 0, openGeneration = 0, pendingDocument = false;
    let cleanState = '', dirty = false, documentEntry = entry, replacing = false;
    let draftAssets = [], recoveryBanner;
    /** What File › Revert returns to: the sources and assets as last opened. */
    let lastOpened;
    let pendingRecovery = isDesigner && !factories.initial ? readDocumentDraft(localStorageValue(DRAFT_KEY)) : undefined;
    function localStorageValue(key) { try {
        return localStorage.getItem(key);
    }
    catch {
        return null;
    } }
    function workingSources() { return { entry: documentEntry, files: [...files.values()].map(file => file.id === entry && file.text !== editor.value ? { ...file, text: editor.value, originalBytes: new TextEncoder().encode(editor.value) } : file) }; }
    function contentState() { const source = workingSources(); return JSON.stringify([source.entry, source.files.map(file => [file.id, file.text]).sort((a, b) => String(a[0]).localeCompare(String(b[0])))]); }
    function markClean() { cleanState = contentState(); setDirty(false); }
    function clearRecovery() { pendingRecovery = undefined; recoveryBanner?.remove(); recoveryBanner = undefined; clearTimeout(draftTimer); try {
        localStorage.removeItem(DRAFT_KEY);
    }
    catch { } savedIndicator.textContent = ''; }
    const setDirty = (value) => { dirty = isDesigner && value; doc.documentElement.dataset.ddnDirty = String(value); dirtyLabel.dataset.state = value ? 'dirty' : 'clean'; dirtyLabel.textContent = value ? 'Unsaved changes' : ''; };
    let cancellation;
    const verifier = isVerifier ? factories.verifier(factories.options()) : undefined;
    const toast = (text, kind = 'info') => {
        const item = doc.createElement('div');
        item.className = 'app-toast';
        item.dataset.kind = kind;
        item.append(uiIcon(doc, kind === 'error' ? 'info' : 'check'), doc.createTextNode(text));
        toasts.append(item);
        while (toasts.children.length > 4)
            toasts.firstElementChild?.remove();
        setTimeout(() => { item.remove(); }, kind === 'error' ? 7000 : 3800);
    };
    const showError = (error) => { status.classList.add('app-error'); statusText.textContent = error instanceof Error ? error.message : String(error); toast(statusText.textContent, 'error'); };
    const notify = (text) => { status.classList.remove('app-error'); statusText.textContent = text; };
    const iconFor = { 'Open files…': 'folder', 'Open a sample…': 'layers', 'New diagram…': 'plus', 'Verify': 'check', 'Open': 'eye', 'Apply source': 'pen', 'Reload source': 'code', 'Download report': 'download', 'Download .ddn': 'download', 'Export SVG': 'download', 'Export PNG': 'download', 'Export JSON': 'download', 'Export Markdown': 'download', 'Export CSV': 'download', 'Download assets': 'download', 'Keyboard shortcuts': 'info' };
    const makeButton = (text, action, host = tools) => {
        const result = doc.createElement('button');
        result.type = 'button';
        result.textContent = text;
        if (iconFor[text])
            result.prepend(uiIcon(doc, iconFor[text]));
        if (['Verify', 'Open', 'Apply source'].includes(text))
            result.classList.add('app-primary');
        result.addEventListener('click', () => { Promise.resolve().then(action).catch(showError); });
        host.append(result);
        return result;
    };
    const labelled = (label, control, host = tools) => { const tag = doc.createElement('label'); tag.append(doc.createTextNode(label), control); host.append(tag); return tag; };
    const themeChoice = doc.createElement('select');
    themeChoice.setAttribute('aria-label', 'Interface theme');
    themeChoice.title = 'Interface theme — colours of the tools, not the diagram';
    for (const name of UI_THEME_NAMES)
        themeChoice.add(new Option(name.charAt(0).toUpperCase() + name.slice(1), name));
    themeChoice.value = interfaceTheme;
    const saveInterface = () => {
        setUITheme(doc.body, interfaceTheme, interfaceTokens);
        doc.dispatchEvent(new CustomEvent('ddn:interface-theme', { detail: { name: interfaceTheme } }));
        try {
            localStorage.setItem('ddn.interface.v1', JSON.stringify({ name: interfaceTheme, overrides: interfaceTokens }));
        }
        catch {
            notify('Interface style changed for this session. Browser preference storage is unavailable.');
        }
    };
    themeChoice.addEventListener('change', () => { interfaceTheme = themeChoice.value; interfaceTokens = {}; saveInterface(); });
    const themeLabel = doc.createElement('label');
    const themeWord = doc.createElement('span');
    themeWord.className = 'app-theme-word';
    themeWord.textContent = 'Theme ';
    themeLabel.append(themeWord, themeChoice);
    interfaceControls.append(themeLabel);
    const customise = doc.createElement('button');
    customise.type = 'button';
    customise.textContent = 'UI colours';
    customise.title = 'Customise the page, panel, text and accent colours of the tools';
    customise.prepend(uiIcon(doc, 'palette'));
    interfaceControls.append(customise);
    customise.addEventListener('click', () => {
        const original = { ...interfaceTokens }, dialog = createStandardDialog(doc.body, { title: 'Interface colours', modal: false });
        const note = doc.createElement('p');
        note.textContent = 'These colours change the tools, not the diagram or its exported appearance.';
        dialog.body.append(note);
        const fields = [];
        for (const [label, token] of [['Page', '--ddn-ui-bg'], ['Panels', '--ddn-ui-surface'], ['Text', '--ddn-ui-text'], ['Accent', '--ddn-ui-accent']]) {
            const input = colourField(dialog.body, label, String(interfaceTokens[token] ?? getComputedStyle(doc.body).getPropertyValue(token).trim()));
            fields.push({ input, token });
            input.addEventListener('input', () => {
                try {
                    const next = { ...interfaceTokens, [token]: input.value };
                    setUITheme(doc.body, interfaceTheme, next);
                    interfaceTokens = next;
                    saveInterface();
                    dialog.showError('');
                }
                catch (error) {
                    dialog.showError(error);
                }
            });
        }
        const reset = doc.createElement('button');
        reset.type = 'button';
        reset.textContent = 'Revert colours';
        reset.addEventListener('click', () => { interfaceTokens = { ...original }; saveInterface(); for (const { input, token } of fields) {
            input.value = String(interfaceTokens[token] ?? getComputedStyle(doc.body).getPropertyValue(token).trim());
            syncColourField(input);
        } dialog.showError(''); });
        dialog.footer.prepend(reset);
    });
    // ----- Source drawer: docked at the left, collapses to a rail, resizes, floats or pops out -----
    panel.id = 'ddn-source-panel';
    const collapseSource = doc.createElement('button');
    collapseSource.type = 'button';
    collapseSource.className = 'app-source-collapse';
    collapseSource.setAttribute('aria-label', 'Hide source');
    collapseSource.title = 'Collapse the source drawer to a rail, widening the diagram (Ctrl+\\)';
    collapseSource.append(uiIcon(doc, 'arrow-left'));
    collapseSource.setAttribute('aria-expanded', 'true');
    collapseSource.setAttribute('aria-controls', panel.id);
    sourceHeading.append(collapseSource);
    const rail = doc.createElement('div');
    rail.className = 'app-rail';
    const expandSource = doc.createElement('button');
    expandSource.type = 'button';
    expandSource.append(uiIcon(doc, 'code'), doc.createTextNode('Source'));
    expandSource.setAttribute('aria-label', 'Show source');
    expandSource.title = 'Open the source drawer (Ctrl+\\)';
    expandSource.setAttribute('aria-expanded', 'false');
    expandSource.setAttribute('aria-controls', panel.id);
    rail.append(expandSource);
    const splitter = doc.createElement('div');
    splitter.className = 'app-splitter';
    splitter.tabIndex = 0;
    splitter.setAttribute('role', 'separator');
    splitter.setAttribute('aria-orientation', 'vertical');
    splitter.setAttribute('aria-label', 'Source drawer width');
    splitter.setAttribute('aria-controls', panel.id);
    splitter.title = 'Drag to resize the source drawer, or focus and use the arrow keys';
    main.prepend(rail);
    panel.after(splitter);
    const VIEW_KEY = 'ddn.view.v1';
    const viewPrefs = (() => { try {
        return JSON.parse(localStorage.getItem(VIEW_KEY) ?? '{}') ?? {};
    }
    catch {
        return {};
    } })();
    const saveViewPrefs = () => { try {
        localStorage.setItem(VIEW_KEY, JSON.stringify(viewPrefs));
    }
    catch { /* Preferences are optional. */ } };
    const setSourceWidth = (width, persist = true) => {
        const limit = Math.max(260, Math.min(900, (doc.defaultView?.innerWidth ?? 1200) * .6));
        const value = Math.round(Math.max(220, Math.min(limit, width)));
        main.style.setProperty('--ddn-source-width', value + 'px');
        splitter.setAttribute('aria-valuenow', String(value));
        splitter.setAttribute('aria-valuemin', '220');
        splitter.setAttribute('aria-valuemax', String(Math.round(limit)));
        if (persist) {
            viewPrefs.sourceWidth = value;
            saveViewPrefs();
        }
    };
    setSourceWidth(viewPrefs.sourceWidth ?? 340, false);
    let splitDrag;
    splitter.addEventListener('pointerdown', event => { if (event.button !== 0)
        return; splitDrag = { id: event.pointerId, x: event.clientX, width: panel.getBoundingClientRect().width }; splitter.setPointerCapture(event.pointerId); splitter.dataset.dragging = ''; event.preventDefault(); });
    splitter.addEventListener('pointermove', event => { if (splitDrag?.id === event.pointerId)
        setSourceWidth(splitDrag.width + event.clientX - splitDrag.x, false); });
    const endSplit = () => { if (!splitDrag)
        return; splitDrag = undefined; delete splitter.dataset.dragging; setSourceWidth(panel.getBoundingClientRect().width); };
    splitter.addEventListener('pointerup', endSplit);
    splitter.addEventListener('pointercancel', endSplit);
    splitter.addEventListener('keydown', event => {
        const step = event.shiftKey ? 64 : 16, current = panel.getBoundingClientRect().width;
        if (event.key === 'ArrowLeft') {
            event.preventDefault();
            setSourceWidth(current - step);
        }
        else if (event.key === 'ArrowRight') {
            event.preventDefault();
            setSourceWidth(current + step);
        }
        else if (event.key === 'Home') {
            event.preventDefault();
            setSourceWidth(220);
        }
        else if (event.key === 'End') {
            event.preventDefault();
            setSourceWidth(900);
        }
    });
    const showSource = (hidden, persist = false) => {
        if (detachedPanels.has('source')) {
            if (!hidden)
                detachedPanels.get('source').focus();
            return;
        }
        main.dataset.sourceHidden = String(hidden);
        collapseSource.setAttribute('aria-expanded', String(!hidden));
        expandSource.setAttribute('aria-expanded', String(!hidden));
        if (persist) {
            viewPrefs.sourceHidden = hidden;
            saveViewPrefs();
        }
        refreshMenus();
    };
    const detachedPanels = new Map();
    let refreshMenus = () => { };
    const narrow = !!doc.defaultView?.matchMedia('(max-width:750px)').matches;
    showSource(!isVerifier && (narrow || viewPrefs.sourceHidden === true));
    collapseSource.addEventListener('click', () => { if (detachedPanels.has('source')) {
        setPanelMode(panelOf('source'), 'hidden');
        return;
    } showSource(true, true); surface.querySelector('.ddn-viewer-stage>svg')?.focus({ preventScroll: true }); });
    expandSource.addEventListener('click', () => { showSource(false, true); editor.focus({ preventScroll: true }); });
    tools.id = 'ddn-document-tools';
    tools.dataset.expanded = 'false';
    const documentToggle = doc.createElement('button');
    documentToggle.className = 'app-document-toggle';
    documentToggle.type = 'button';
    documentToggle.append(uiIcon(doc, 'folder'), doc.createTextNode('Document tools'));
    documentToggle.setAttribute('aria-controls', tools.id);
    documentToggle.setAttribute('aria-expanded', 'false');
    interfaceControls.append(documentToggle);
    documentToggle.addEventListener('click', () => { const expanded = tools.dataset.expanded !== 'true'; tools.dataset.expanded = String(expanded); documentToggle.setAttribute('aria-expanded', String(expanded)); });
    const fileSelect = doc.createElement('select');
    fileSelect.setAttribute('aria-label', 'Source file');
    fileSelect.title = 'Which file of the document the source panel shows';
    function refreshFiles() {
        fileSelect.replaceChildren();
        for (const name of files.keys()) {
            const option = doc.createElement('option');
            option.value = name;
            option.textContent = name;
            fileSelect.append(option);
        }
        fileSelect.value = entry;
        fileSelect.parentElement.hidden = files.size < 2;
        refreshSourceState();
    }
    function refreshSourceState() {
        editor.readOnly = factories.mode === 'viewer' || files.get(entry)?.writable === false;
        sourceKind.textContent = editor.readOnly ? 'Read only' : 'Source';
        applyButton.disabled = isDesigner && editor.readOnly;
    }
    const input = doc.createElement('input');
    input.type = 'file';
    input.multiple = true;
    input.hidden = true;
    input.accept = '.ddn,.txt,.css,.svg,.png,.jpg,.jpeg,.webp,.json,.geojson';
    tools.append(input);
    async function loadSources(sources, incomingAssets, stillWanted = () => true, approvedContent = contentState()) {
        const operation = ++openGeneration;
        let encoded;
        try {
            encoded = await Promise.all([...(incomingAssets ?? [])].filter(([id]) => !sources.files.some(file => file.id === id)).map(async ([id, file]) => encodeDraftAsset(id, file.type, new Uint8Array(await file.arrayBuffer()))));
        }
        catch (error) {
            if (operation === openGeneration)
                showError(error);
            return false;
        }
        if (operation !== openGeneration || !stillWanted())
            return false;
        if (contentState() !== approvedContent) {
            if (!await confirmReplace())
                return false;
            if (operation !== openGeneration || !stillWanted())
                return false;
        }
        clearRecovery();
        resetSession();
        replacing = true;
        files.clear();
        assets.clear();
        draftAssets = encoded;
        for (const [id, file] of incomingAssets ?? [])
            assets.set(id, file);
        for (const file of sources.files)
            files.set(file.id, { ...file, revision: String(++sequence) });
        lastOpened = { sources, assets: new Map(incomingAssets ?? []) };
        entry = documentEntry = sources.entry;
        refreshFiles();
        editor.value = files.get(entry)?.text ?? '';
        editorDirty = false;
        sourceConflict = false;
        pendingDocument = true;
        editGeneration++;
        renderDiagnostics([]);
        markClean();
        return true;
    }
    async function readFiles(selected) {
        let operation = ++openGeneration;
        const approvedContent = contentState();
        try {
            const loaded = [], selectedAssets = new Map();
            for (const file of Array.from(selected)) {
                const id = normalizeLocation(file.webkitRelativePath || file.name);
                if (selectedAssets.has(id))
                    throw Error('Duplicate selected file: ' + id);
                selectedAssets.set(id, file);
                if (!/\.(ddn|txt|css)$/i.test(id))
                    continue;
                if (file.size > 16 * 1024 * 1024)
                    throw Error('Source exceeds the 16 MiB per-file budget');
                const bytes = new Uint8Array(await file.arrayBuffer());
                if (operation !== openGeneration)
                    return;
                const text = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes);
                loaded.push({ id, text, revision: '0', encoding: 'utf-8', writable: true, originalBytes: bytes });
            }
            const root = loaded.find(file => !/\.css$/i.test(file.id));
            if (!root)
                throw Error('Select at least one DDN source file (.ddn)');
            if (operation !== openGeneration)
                return;
            if (!await loadSources({ entry: root.id, files: loaded }, selectedAssets, () => true, approvedContent))
                return;
            const opening = operation = openGeneration + 1;
            const loadedContent = contentState();
            await open(true);
            if (opening !== openGeneration)
                return;
            if (contentState() === loadedContent)
                markClean();
            rememberRecent(entry.split('/').at(-1) ?? entry, workingSources());
            toast('Opened ' + entry);
        }
        catch (error) {
            if (operation === openGeneration)
                throw error;
        }
    }
    // Confirm before replacing unsaved work (Load sample, Open files, New). Returns true when the caller may proceed.
    const confirmReplace = (includeRecovery = true) => new Promise(resolve => {
        if ((!dirty && (!includeRecovery || !pendingRecovery)) || !isDesigner) {
            resolve(true);
            return;
        }
        let decided = false;
        const dialog = createStandardDialog(doc.body, { title: 'Replace your unsaved changes?', applyLabel: 'Replace', cancelLabel: 'Keep editing', onApply() { decided = true; }, onClose() { setTimeout(() => resolve(decided), 0); } });
        const text = doc.createElement('p');
        text.textContent = 'Replacing this document also replaces its recovery draft in this browser. Download any changes you want to keep first.';
        dialog.body.append(text);
        const downloadFirst = doc.createElement('button');
        downloadFirst.type = 'button';
        downloadFirst.textContent = 'Download .ddn first';
        downloadFirst.addEventListener('click', () => { Promise.resolve().then(downloadSource).catch(showError); });
        dialog.footer.prepend(downloadFirst);
    });
    const openFiles = async () => { if (await confirmReplace())
        input.click(); };
    input.addEventListener('change', () => {
        if (input.files)
            void readFiles(input.files).catch(showError);
    });
    const newDocument = async () => {
        if (!await confirmReplace())
            return;
        if (!await loadSources({ entry: 'main.ddn', files: [{ id: 'main.ddn', text: '', revision: '0', encoding: 'utf-8', writable: true }] }))
            return;
        input.value = '';
        viewSelect.replaceChildren();
        const currentViewer = viewer, operation = openGeneration + 1, emptyContent = contentState();
        await open(true);
        if (!currentViewer || viewer !== currentViewer || operation !== openGeneration)
            return;
        if (contentState() !== emptyContent)
            return;
        markClean();
        factories.newDiagram?.(currentViewer, async (text) => {
            if (viewer !== currentViewer || operation !== openGeneration || contentState() !== emptyContent)
                throw Error('This document has changed. Start a new document again.');
            editor.value = text;
            editGeneration++;
            editorDirty = true;
            const creating = openGeneration + 1;
            await open(true);
            if (viewer !== currentViewer || creating !== openGeneration)
                throw Error('This document is no longer open.');
            setDirty(true);
            scheduleDraft();
        });
        notify('Create a workarea or a standalone view.');
    };
    const catalogue = () => { const site = host?.DDN_WEBSITE_CATALOGUE; return site && Array.isArray(site.corpus) ? site.corpus : []; };
    const loadSampleScript = (sampleEntry) => new Promise((resolve, reject) => {
        if (!host || !catalogue().some(sample => sample.entry === sampleEntry)) {
            reject(Error('Unknown sample'));
            return;
        }
        const script = doc.createElement('script');
        const previous = host.DDN_SITE_INITIAL;
        script.src = new URL('../' + sampleEntry + '.js', host.location.href).href;
        script.onload = () => { const initial = host.DDN_SITE_INITIAL; script.remove(); if (previous !== undefined)
            host.DDN_SITE_INITIAL = previous;
        else
            delete host.DDN_SITE_INITIAL; if (!initial?.sources)
            reject(Error('The sample did not supply sources'));
        else
            resolve(initial); };
        script.onerror = () => { script.remove(); reject(Error('Unable to load the sample ' + sampleEntry)); };
        doc.body.append(script);
    });
    const openSampleDialog = async () => {
        if (!await confirmReplace())
            return;
        let chosen = { kind: 'starter', name: 'ERD whiteboard' };
        let sampleOpen = true;
        const dialog = createStandardDialog(doc.body, { title: 'Open a sample', applyLabel: 'Open', onClose() { sampleOpen = false; }, async onApply() {
                const approvedContent = contentState();
                if (chosen.kind === 'starter') {
                    if (!await loadSources({ entry: 'main.ddn', files: [{ id: 'main.ddn', text: examples[chosen.name], revision: '0', encoding: 'utf-8', writable: true }] }, undefined, () => sampleOpen))
                        return;
                }
                else {
                    const operation = ++openGeneration;
                    const initial = await loadSampleScript(chosen.entry);
                    if (operation !== openGeneration || !sampleOpen)
                        return;
                    if (!await loadSources(initial.sources, new Map(Object.entries(initial.assets ?? {}).map(([id, asset]) => [id, new File([asset.text], id, { type: asset.mime })])), () => sampleOpen, approvedContent))
                        return;
                }
                const operation = openGeneration + 1;
                const loadedContent = contentState();
                await open(true);
                if (operation !== openGeneration || !sampleOpen)
                    return;
                if (contentState() === loadedContent)
                    markClean();
                rememberRecent(chosen.kind === 'starter' ? chosen.name : chosen.title, workingSources());
                toast('Opened sample: ' + (chosen.kind === 'starter' ? chosen.name : chosen.title));
            } });
        const search = doc.createElement('input');
        search.type = 'search';
        search.placeholder = 'Filter samples';
        search.setAttribute('aria-label', 'Filter samples');
        dialog.body.append(search);
        const list = doc.createElement('div');
        list.className = 'app-samples';
        list.setAttribute('role', 'listbox');
        dialog.body.append(list);
        const hint = doc.createElement('p');
        hint.textContent = 'Starters are small documents to edit; field-guide samples show finished diagrams of each type. Opening a sample replaces the current document.';
        dialog.body.append(hint);
        const render = () => {
            const q = search.value.trim().toLowerCase();
            list.replaceChildren();
            const section = (title) => { const head = doc.createElement('div'); head.className = 'app-menu-head'; head.textContent = title; list.append(head); };
            const option = (label, detail, value, pressed) => {
                const item = doc.createElement('button');
                item.type = 'button';
                item.setAttribute('role', 'option');
                item.setAttribute('aria-pressed', String(pressed));
                item.setAttribute('aria-selected', String(pressed));
                item.append(doc.createTextNode(label));
                if (detail) {
                    const small = doc.createElement('small');
                    small.textContent = detail;
                    item.append(small);
                }
                item.addEventListener('click', () => { chosen = value; render(); });
                item.addEventListener('dblclick', () => { chosen = value; dialog.applyButton?.click(); });
                list.append(item);
            };
            const starters = Object.keys(examples).filter(name => !q || name.toLowerCase().includes(q));
            if (starters.length) {
                section('Starters');
                for (const name of starters)
                    option(name, 'starter', { kind: 'starter', name }, chosen.kind === 'starter' && chosen.name === name);
            }
            const corpus = catalogue().filter(item => !q || `${item.title} ${item.entry} ${(item.views ?? []).map(v => v.profile).join(' ')}`.toLowerCase().includes(q));
            if (corpus.length) {
                section('Field guide samples');
                for (const item of corpus.slice(0, 200))
                    option(item.title ?? item.entry, `${(item.views ?? []).length} view${(item.views ?? []).length === 1 ? '' : 's'} · ${(item.views ?? [])[0]?.profile ?? ''}`, { kind: 'catalogue', entry: item.entry, title: item.title ?? item.entry }, chosen.kind === 'catalogue' && chosen.entry === item.entry);
            }
            if (!starters.length && !corpus.length) {
                const empty = doc.createElement('p');
                empty.textContent = 'No sample matches.';
                list.append(empty);
            }
        };
        search.addEventListener('input', render);
        render();
    };
    doc.addEventListener('ddn:open-sample', () => { void openSampleDialog().catch(showError); });
    doc.addEventListener('ddn:open-files', () => { void openFiles().catch(showError); });
    doc.addEventListener('ddn:new-document', () => { void newDocument().catch(showError); });
    labelled('File', fileSelect);
    const viewSelect = doc.createElement('select');
    viewSelect.setAttribute('aria-label', 'Current view');
    viewSelect.title = 'Which view of the document the diagram shows';
    if (!isVerifier)
        labelled('View', viewSelect);
    viewSelect.addEventListener('change', () => {
        if (viewer && viewSelect.value)
            void viewer.navigate({ kind: 'fit-view', target: JSON.parse(viewSelect.value) }).catch(showError);
    });
    fileSelect.addEventListener('change', () => {
        if (editorDirty) {
            fileSelect.value = entry;
            showError('Apply the source edit before switching files.');
            return;
        }
        entry = fileSelect.value;
        editor.value = files.get(entry)?.text ?? '';
        refreshSourceState();
        validateSoon();
    });
    const level = doc.createElement('select');
    level.setAttribute('aria-label', 'Verification level');
    for (const value of ['decode', 'structural', 'semantic', 'review', 'publication']) {
        const option = doc.createElement('option');
        option.value = value;
        option.textContent = value;
        level.append(option);
    }
    level.value = 'semantic';
    const purpose = doc.createElement('input');
    purpose.value = 'design';
    purpose.setAttribute('aria-label', 'Verification purpose');
    purpose.size = 12;
    if (isVerifier) {
        labelled('Level', level);
        labelled('Purpose', purpose);
    }
    const spacer = doc.createElement('span');
    spacer.className = 'app-spacer';
    tools.append(spacer);
    const dirtyLabel = doc.createElement('span');
    dirtyLabel.className = 'app-dirty';
    dirtyLabel.setAttribute('aria-live', 'polite');
    // Primary action: in the designer it lives beside the source it applies to; viewer/verifier keep it in the tools row.
    const applyHost = isDesigner ? sourceToolbar : tools;
    const applyButton = makeButton(isVerifier ? 'Verify' : factories.mode === 'viewer' ? 'Open' : 'Apply source', () => open(), applyHost);
    applyButton.title = isDesigner ? 'Apply the source text to the diagram (Ctrl+Enter)' : isVerifier ? 'Verify the source text' : 'Open the source text in the viewer';
    if (isDesigner) {
        const reload = makeButton('Reload source', () => {
            const current = viewer && factories.getRuntime?.(viewer).sources();
            if (current) {
                syncSources(current);
                notify('Source reloaded from the current diagram.');
            }
        }, sourceToolbar);
        reload.title = 'Rewrite the source text from the current diagram (keeps your diagram, discards unapplied text edits)';
        sourceToolbar.append(dirtyLabel);
    }
    const cancelButton = makeButton('Cancel', () => {
        if (cancellation) {
            cancellation.aborted = true;
            for (const listener of cancellation.listeners)
                listener();
            notify('Cancellation requested');
        }
    }, isDesigner ? sourceToolbar : tools);
    cancelButton.title = 'Stop a long-running open or verification';
    cancelButton.hidden = true;
    const download = (name, blob) => { const url = URL.createObjectURL(blob), a = doc.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); toast('Download requested: ' + name); notify('Download requested: ' + name + '.'); };
    const downloadSource = async () => {
        if (isVerifier) {
            if (!lastReport)
                throw Error('Verify a document first');
            download('ddn-verification.json', new Blob([JSON.stringify(lastReport, null, 2)], { type: 'application/json' }));
            return;
        }
        const source = workingSources(), saved = contentState(), generation = editGeneration, currentViewer = viewer;
        if (designer && !editorDirty && !sourceConflict && !pendingDocument) {
            const artifacts = await designer.save();
            if (viewer !== currentViewer)
                return;
            for (const artifact of artifacts)
                download(artifact.name, artifact.blob);
        }
        else {
            for (const file of source.files)
                download(file.id, new Blob([file.originalBytes ? new Uint8Array(file.originalBytes) : file.text], { type: 'text/plain;charset=utf-8' }));
        }
        if (generation === editGeneration && saved === contentState()) {
            cleanState = saved;
            setDirty(false);
        }
        rememberRecent(documentEntry.split('/').at(-1) ?? documentEntry, source);
        // Retain a recovery copy: the browser cannot confirm the download reached disk.
        persistDraft();
    };
    /** Export uses the capture scope chosen in Document › Capture scope (the current view by default). */
    let captureScope = 'view';
    const captureTarget = () => {
        if (captureScope === 'selection') {
            const selected = findUICommand(surface, 'view.selection')?.value?.();
            if (selected)
                return { kind: 'item', target: JSON.parse(selected) };
        }
        if (captureScope === 'workarea' && !standaloneDocument() || !viewSelect.value)
            return { kind: 'workarea' };
        return { kind: 'view', target: JSON.parse(viewSelect.value) };
    };
    const exportAs = (format) => async () => {
        if (!viewer)
            throw Error('Open a document first');
        const result = await viewer.capture({ scope: captureTarget(), format, extent: 'content', includePreview: false, partial: format === 'svg' ? 'label' : 'reject', stale: 'reject' });
        if (!result.ok)
            throw Error(result.diagnostics.map(d => d.message).join('; ') || result.reason);
        for (const artifact of result.artifacts)
            download(artifact.name, artifact.blob);
    };
    const downloadAssets = () => {
        const supplied = [...assets].filter(([id]) => !files.has(id));
        if (!supplied.length) {
            toast('This document has no separately supplied assets (images, CSS, GeoJSON).');
            return;
        }
        for (const [id, file] of supplied)
            download(id.split('/').at(-1) ?? id, file);
    };
    /** One .zip with every source file and supplied asset, for keeping or sending the whole document. */
    const saveBundle = async () => {
        if (isVerifier)
            throw Error('Bundles are for documents; use Download report.');
        const currentViewer = viewer, entries = [];
        if (designer && !editorDirty && !sourceConflict && !pendingDocument) {
            for (const artifact of await designer.save())
                entries.push({ name: artifact.name, bytes: new Uint8Array(await artifact.blob.arrayBuffer()) });
        }
        else
            for (const file of workingSources().files)
                entries.push({ name: file.id, bytes: file.originalBytes ? new Uint8Array(file.originalBytes) : new TextEncoder().encode(file.text) });
        if (viewer !== currentViewer)
            return;
        for (const [id, file] of assets)
            if (!files.has(id) && !entries.some(entry => entry.name === id))
                entries.push({ name: id, bytes: new Uint8Array(await file.arrayBuffer()) });
        const base = documentEntry.split('/').at(-1)?.replace(/\.ddn$/i, '') || 'document';
        download(base + '.zip', zipFiles(entries));
        persistDraft();
    };
    function showShortcuts() {
        const dialog = createStandardDialog(doc.body, { title: 'Keyboard shortcuts' });
        const dl = doc.createElement('dl');
        dl.className = 'app-shortcuts';
        const rows = [['Ctrl+K', 'Command search: find any menu command'], ['Ctrl+Z / Ctrl+Shift+Z or Ctrl+Y', 'Undo / redo'], ['Ctrl+X / Ctrl+C / Ctrl+V', 'Cut / copy / paste the selected element'], ['Ctrl+Shift+V / Ctrl+Alt+V', 'Paste in place / paste as reference'], ['Ctrl+D', 'Duplicate the selected element'], ['Delete', 'Delete the selected element'], ['Arrow keys', 'Move the selected element 16 px (Shift: 1 px; snaps to the grid when snapping is on)'], ['Enter', 'Select the focused element'], ['Escape', 'Cancel a drag, close a menu or dialog, clear the selection'], ['Ctrl+= / Ctrl+− / Ctrl+0', 'Zoom in / out / actual size'], ['Shift+1 / Shift+2 / Shift+3', 'Fit workarea / fit selection / fit current view'], ['Alt+← / Alt+→', 'Previous / next position'], ['+ / − / 0', 'Zoom in / out / fit the workarea (diagram focused)'], ['Mouse wheel', 'Designer: scroll the workarea (Ctrl+wheel or pinch zooms) · Viewer: zoom at the pointer'], ['A', 'Add element (opens the palette)'], ['C', 'Connect: click the first element, then the second'], ['P', 'Properties of the selected element (inspector)'], ['F2', 'Rename the selected element'], ['Double-click', 'Rename an element'], ['Right-click / long-press', 'Context menu for the element'], ['Ctrl+Enter', 'Apply the source text'], ['Ctrl+S / Ctrl+Shift+S', 'Download the .ddn source / the whole document as a .zip'], ['Ctrl+O', 'Open files'], ['Ctrl+Alt+N', 'New diagram'], ['Ctrl+F', 'Find a view or element'], ['Ctrl+\\', 'Collapse or open the source drawer'], ['Ctrl+I', 'Show or hide the inspector'], ['Ctrl+Shift+E', 'Show or hide the navigator'], ['Ctrl+E / Ctrl+P', 'Export / print the current document view'], ['F1', 'Open the guide'], ['Esc then Tab', 'Leave the source editor'], ['?', 'This list']];
        for (const [keys = '', text = ''] of rows) {
            const dt = doc.createElement('dt'), dd = doc.createElement('dd');
            dt.textContent = keys;
            dd.textContent = text;
            dl.append(dt, dd);
        }
        dialog.body.append(dl);
    }
    doc.addEventListener('ddn:shortcuts', showShortcuts);
    // ----- Source diagnostics (inline) -----
    const lineOf = (text, offset) => text.slice(0, Math.max(0, offset)).split('\n').length;
    const renderDiagnostics = (items) => {
        diagnosticsList.replaceChildren();
        const problems = items.filter(d => d.severity === 'error' || d.severity === 'warning').slice(0, 20);
        editor.setAttribute('aria-invalid', String(problems.some(d => d.severity === 'error')));
        for (const d of problems) {
            const row = doc.createElement('button');
            row.type = 'button';
            row.setAttribute('role', 'listitem');
            const offset = d.source && (d.source.file === entry || !d.source.file) ? Number(d.source.start) : undefined;
            const line = offset !== undefined && Number.isFinite(offset) ? lineOf(editor.value, offset) : undefined;
            const where = doc.createElement('b');
            where.textContent = line ? `Line ${line}` : d.severity === 'error' ? 'Error' : 'Warning';
            row.append(where, doc.createTextNode(d.message));
            row.title = offset !== undefined && Number.isFinite(offset) ? 'Go to this line in the source' : d.code ?? '';
            row.addEventListener('click', () => { if (offset !== undefined && Number.isFinite(offset)) {
                editor.focus();
                editor.setSelectionRange(offset, offset);
                const before = editor.value.slice(0, offset).split('\n').length;
                editor.scrollTop = Math.max(0, (before - 4) * 19.2);
            } });
            diagnosticsList.append(row);
        }
    };
    let validateTimer;
    const validateNow = () => {
        if (isVerifier)
            return;
        try {
            const decoded = decodeSources(workingSources());
            renderDiagnostics(decoded.diagnostics);
        }
        catch {
            /* validation is advisory */
        }
    };
    const validateSoon = () => { clearTimeout(validateTimer); validateTimer = setTimeout(validateNow, 600); };
    editor.addEventListener('input', () => { editorDirty = true; editGeneration++; setDirty(contentState() !== cleanState); validateSoon(); scheduleDraft(); });
    // ----- Autosave (designer): the working document is kept in this browser and offered back on the next visit -----
    let draftTimer;
    function persistDraft() {
        if (!isDesigner || pendingRecovery || replacing)
            return;
        try {
            const source = workingSources();
            const snapshot = { ...source, files: source.files.map(({ id, text, writable }) => ({ id, text, writable, revision: 'recovered', encoding: 'utf-8' })), version: 1, savedAt: new Date().toISOString(), assets: draftAssets };
            localStorage.setItem(DRAFT_KEY, JSON.stringify(snapshot));
            savedIndicator.textContent = 'Kept in this browser · ' + new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }
        catch {
            savedIndicator.textContent = 'Browser storage unavailable — download to keep your work';
        }
    }
    function scheduleDraft() {
        if (!isDesigner || pendingRecovery || replacing)
            return;
        clearTimeout(draftTimer);
        draftTimer = setTimeout(persistDraft, 800);
    }
    const assetProvider = { async read(id) {
            let location = id;
            try {
                const parts = JSON.parse(id);
                if (Array.isArray(parts)) {
                    const recordId = String(parts[1]);
                    const snapshot = viewer && factories.getRuntime?.(viewer).snapshot();
                    const bundle = snapshot?.normalized;
                    const record = bundle?.files?.find(f => f.location === parts[0])?.document.assets?.find(a => a.id === recordId || a.name === recordId);
                    location = record && typeof record.path === 'string' ? record.path : normalizeLocation(recordId, String(parts[0]));
                }
            }
            catch { }
            const file = assets.get(location);
            if (!file)
                throw Error('Local asset was not supplied: ' + location);
            const bytes = new Uint8Array(await file.arrayBuffer());
            const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
            return { bytes, mime: file.type || (/\.svg$/i.test(location) ? 'image/svg+xml' : /\.css$/i.test(location) ? 'text/css' : /\.(geojson|json)$/i.test(location) ? 'application/geo+json' : 'application/octet-stream'), hash: Array.from(digest, b => b.toString(16).padStart(2, '0')).join('') };
        } };
    let unsubscribe;
    function attachViewer() {
        if (!factories.viewer)
            return;
        const attached = factories.viewer(surface, { runtimeOptions: factories.options(), assets: assetProvider });
        viewer = attached;
        if (factories.designer)
            designer = factories.designer(attached);
        attached.subscribe(event => {
            if (attached === viewer && event.kind === 'diagnostics' && event.diagnostics?.length)
                notify(event.diagnostics.map(d => d.message).join(' · '));
        });
        const runtime = factories.getRuntime?.(attached);
        unsubscribe = runtime?.subscribe(event => {
            if (attached !== viewer || event.kind !== 'revision')
                return;
            const source = runtime.sources();
            if (!source)
                return;
            if (editorDirty) {
                sourceConflict = true;
                notify('The diagram changed while you were editing the source text. Reload source to see the change, then reapply your edit.');
            }
            else
                syncSources(source);
            const views = refreshViews(true);
            if (views?.newView) {
                viewSelect.value = views.newView;
                void attached.navigate({ kind: 'fit-view', target: JSON.parse(views.newView) }).catch(showError);
            }
            else if (views && [...viewSelect.options].some(option => option.value === views.previousView))
                viewSelect.value = views.previousView;
            if (!replacing) {
                setDirty(contentState() !== cleanState);
                if (dirty)
                    scheduleDraft();
            }
        });
    }
    function resetSession() {
        openGeneration++;
        clearTimeout(validateTimer);
        clearTimeout(draftTimer);
        if (cancellation) {
            cancellation.aborted = true;
            for (const listener of cancellation.listeners)
                listener();
        }
        unsubscribe?.();
        unsubscribe = undefined;
        // Detached viewer panels belong to the old session: bring them home before it closes.
        for (const id of ['inspector', 'palette', 'navigator'])
            detachedPanels.get(id)?.dock();
        designer?.destroy();
        viewer?.destroy();
        designer = undefined;
        viewer = undefined;
        lastReport = undefined;
        knownViewKeys = new Set();
        viewSelect.replaceChildren();
        attachViewer();
    }
    function syncSources(source) {
        files.clear();
        for (const file of source.files)
            files.set(file.id, file);
        documentEntry = source.entry;
        if (!files.has(entry))
            entry = source.entry;
        refreshFiles();
        editor.value = files.get(entry)?.text ?? '';
        editorDirty = false;
        sourceConflict = false;
        renderDiagnostics([]);
    }
    let knownViewKeys = new Set();
    function refreshViews(selectNew = true) {
        if (!viewer)
            return;
        const runtime = factories.getRuntime?.(viewer);
        const previousView = viewSelect.value;
        viewSelect.replaceChildren();
        const bundle = runtime?.snapshot()?.normalized;
        const keys = new Set();
        let added;
        for (const file of bundle?.files ?? [])
            for (const view of file.document.views ?? []) {
                if (standaloneDocument() && viewSelect.options.length)
                    continue;
                const option = doc.createElement('option');
                option.value = JSON.stringify({ file: file.location, id: view.id });
                option.textContent = view.title ?? view.name ?? view.id;
                viewSelect.append(option);
                keys.add(option.value);
                if (!knownViewKeys.has(option.value))
                    added = option.value;
            }
        const newView = selectNew && knownViewKeys.size && added && !knownViewKeys.has(added) ? added : undefined;
        knownViewKeys = keys;
        viewSelect.parentElement.hidden = standaloneDocument() || viewSelect.options.length < 2;
        return { previousView, newView };
    }
    attachViewer();
    window.addEventListener('pagehide', () => { clearTimeout(draftTimer); clearTimeout(validateTimer); if (dirty)
        persistDraft(); unsubscribe?.(); designer?.destroy(); viewer?.destroy(); verifier?.destroy(); }, { once: true });
    window.addEventListener('beforeunload', event => { if (isDesigner && dirty) {
        event.preventDefault();
        event.returnValue = '';
    } });
    function renderReport(report) {
        surface.replaceChildren();
        const body = doc.createElement('div');
        body.className = 'app-report';
        const heading = doc.createElement('h2');
        heading.textContent = report.outcome + ' — ' + (report.reviewEligible ? 'review eligible' : 'review not established');
        body.append(heading);
        const detail = doc.createElement('p');
        detail.textContent = `${report.level} · ${report.coverage.checked.length} checked records · ${Math.round(report.stats.elapsedMs)} ms`;
        body.append(detail);
        const search = doc.createElement('input');
        search.placeholder = 'Filter diagnostics';
        search.setAttribute('aria-label', 'Filter diagnostics');
        body.append(search);
        const table = doc.createElement('table');
        body.append(table);
        const fill = () => {
            table.replaceChildren();
            for (const diagnostic of report.diagnostics.filter(d => (d.code + ' ' + d.message).toLowerCase().includes(search.value.toLowerCase()))) {
                const row = doc.createElement('tr');
                for (const text of [diagnostic.severity, diagnostic.code, diagnostic.message, diagnostic.source ? diagnostic.source.file + ':' + diagnostic.source.start : '']) {
                    const cell = doc.createElement('td');
                    cell.textContent = text;
                    row.append(cell);
                }
                table.append(row);
            }
        };
        search.addEventListener('input', fill);
        fill();
        surface.append(body);
    }
    async function open(replace = false) {
        const operation = ++openGeneration, bufferGeneration = editGeneration;
        const currentViewer = viewer, currentDesigner = designer;
        try {
            replace = replace || pendingDocument;
            if (sourceConflict && !replace)
                throw Error('The diagram changed since this source edit began. Copy your text, then Reload source and reconcile your edit.');
            const old = files.get(entry);
            if (old?.text !== editor.value)
                files.set(entry, { id: entry, text: editor.value, revision: String(++sequence), encoding: 'utf-8', writable: old?.writable ?? true });
            const source = workingSources();
            if (cancellation) {
                cancellation.aborted = true;
                for (const listener of cancellation.listeners)
                    listener();
            }
            cancellation = { aborted: false, listeners: new Set() };
            const current = cancellation;
            const cancel = { get aborted() { return current.aborted; }, onAbort(handler) { current.listeners.add(handler); return () => { current.listeners.delete(handler); }; } };
            notify('Working…');
            cancelButton.hidden = false;
            await new Promise(resolve => setTimeout(resolve, 0));
            if (operation !== openGeneration)
                return;
            if (factories.mode === 'verifier') {
                const report = await verifier.verifySources(source, { scope: { kind: 'workarea' }, purpose: purpose.value, level: level.value, cancel });
                if (operation !== openGeneration)
                    return;
                lastReport = report;
                renderDiagnostics(report.diagnostics.filter(d => d.source));
                renderReport(lastReport);
                notify('Verification ' + lastReport.outcome + (bufferGeneration !== editGeneration ? ' for the previous source buffer; verify the current edit again.' : ''));
            }
            else if (currentViewer) {
                const runtime = factories.getRuntime?.(currentViewer), currentSources = runtime?.sources();
                if (!replace && currentDesigner && currentSources && currentSources.entry === documentEntry && currentSources.files.length === source.files.length && currentSources.files.every(f => source.files.some(next => next.id === f.id))) {
                    const patches = source.files.flatMap(file => { const previous = currentSources.files.find(f => f.id === file.id); return previous.text === file.text ? [] : [{ file: file.id, base: previous.revision, start: 0, end: previous.text.length, text: file.text }]; });
                    if (patches.length) {
                        const prepared = await currentDesigner.commands.prepare({ kind: 'edit-source', patches }, { cancel });
                        if (operation !== openGeneration)
                            return;
                        if (bufferGeneration !== editGeneration) {
                            if (prepared.ok)
                                currentDesigner.commands.discard(prepared.command.id);
                            notify('Your newer source text is retained. Apply again to use the current edit.');
                            return;
                        }
                        if (!prepared.ok) {
                            renderDiagnostics(prepared.failure.diagnostics);
                            throw Error(prepared.failure.diagnostics.map(d => d.message).join('; '));
                        }
                        editorDirty = false;
                        const committed = await currentDesigner.commands.commit(prepared.command.id, { cancel });
                        if (operation !== openGeneration)
                            return;
                        if (!committed.ok) {
                            editorDirty = true;
                            renderDiagnostics(committed.failure.diagnostics);
                            throw Error(committed.failure.diagnostics.map(d => d.message).join('; '));
                        }
                    }
                }
                else {
                    editorDirty = false;
                    const result = await currentViewer.open(source, { cancel });
                    if (operation !== openGeneration)
                        return;
                    renderDiagnostics(result.diagnostics);
                    if (result.diagnostics.some(d => d.severity === 'error'))
                        throw Error(result.diagnostics.map(d => d.message).join(' · '));
                }
                if (operation !== openGeneration)
                    return;
                if (bufferGeneration !== editGeneration) {
                    sourceConflict = true;
                    notify('Your newer source text is retained. The completed operation used an earlier buffer; reconcile before applying.');
                    return;
                }
                const openedSources = runtime?.sources();
                if (openedSources)
                    syncSources(openedSources);
                pendingDocument = false;
                const views = refreshViews(false);
                const previousView = views?.previousView;
                const requested = factories.initial?.view;
                const chosen = [...viewSelect.options].find(o => o.value === previousView) ?? [...viewSelect.options].find(o => JSON.parse(o.value).id === requested) ?? viewSelect.options[0];
                if (chosen) {
                    viewSelect.value = chosen.value;
                    await currentViewer.navigate({ kind: 'fit-view', target: JSON.parse(chosen.value) });
                }
                if (operation !== openGeneration)
                    return;
                replacing = false;
                if (replace)
                    factories.ready?.({ viewer: currentViewer, ...(currentDesigner ? { designer: currentDesigner } : {}) });
                notify((factories.edition === 'complete' ? 'Complete' : 'Native') + ' DDN ' + factories.mode + ' ready');
            }
        }
        catch (error) {
            // A New/open action invalidates results and errors from the old session.
            if (operation === openGeneration) {
                if (bufferGeneration === editGeneration)
                    editorDirty = true;
                throw error;
            }
        }
        finally {
            if (operation === openGeneration) {
                cancelButton.hidden = true;
                replacing = false;
            }
        }
    }
    // Source editor keys: Tab indents; Escape then Tab leaves; Ctrl+Enter applies.
    let escapeArmed = 0;
    editor.addEventListener('keydown', event => {
        if (event.key === 'Escape') {
            escapeArmed = Date.now();
            notify('Press Tab to leave the source editor.');
            return;
        }
        if (event.key === 'Tab' && !editor.readOnly) {
            if (Date.now() - escapeArmed < 3000) {
                escapeArmed = 0;
                return; // let the browser move focus
            }
            event.preventDefault();
            const start = editor.selectionStart;
            editor.setRangeText('    ', start, editor.selectionEnd, 'end');
            editorDirty = true;
            editGeneration++;
            setDirty(true);
            validateSoon();
            scheduleDraft();
        }
        if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && !editor.readOnly) {
            event.preventDefault();
            void open().catch(showError);
        }
    });
    // ===== Menu bar, panels, view settings and shortcuts =====
    // Every edition shows the same menus in the same places; what this edition or mode
    // cannot do stays visible but disabled, with the reason, so nothing needs relearning.
    const WEAVER = 'Available in ScratchWeaver, the commercial edition';
    const LATER = 'Planned for a later iteration of the designer';
    const command = (id) => findUICommand(surface, id);
    const runCommand = (id, argument) => {
        const found = command(id);
        if (!found || !commandEnabled(found))
            return false;
        Promise.resolve().then(() => found.run(argument)).catch(showError);
        return true;
    };
    const bus = (label, id, extra = {}) => ({
        label, ...(extra.shortcut ? { shortcut: extra.shortcut } : {}), hint: extra.hint ?? command(id)?.hint ?? (viewer ? 'Not available for the current selection or view' : 'Open a document first'),
        enabled: () => commandEnabled(command(id)), run: () => { runCommand(id, extra.argument); },
        ...(extra.checked ? { checked: extra.checked, radio: !!extra.radio } : {}),
    });
    const weaver = (label) => ({ label, badge: 'ScratchWeaver', hint: WEAVER, enabled: () => false });
    const later = (label, shortcut) => ({ label, hint: LATER, enabled: () => false, ...(shortcut ? { shortcut } : {}) });
    const separator = { kind: 'separator' };
    const heading = (label) => ({ kind: 'heading', label });
    const needsDesigner = (item) => isDesigner || item.kind === 'separator' || item.kind === 'heading' ? item : { ...item, enabled: () => false, hint: 'Editing happens in the designer' };
    function standaloneDocument() {
        const snapshot = viewer && factories.getRuntime?.(viewer)?.snapshot();
        return !!snapshot && listRecords(snapshot.normalized).some(record => record.kind === 'workarea' && record.file === snapshot.rootFile && record.record.mode === 'standalone');
    }
    const workareaOnly = new Set(['Workarea settings…', 'Add view…', 'Add document view…', 'New document view…', 'Place an existing view', 'Layers', 'Regions', 'Bookmarks', 'Workarea defaults…', 'Fit workarea', 'Expand view', 'Mini-views when small']);
    const documentItems = (items) => standaloneDocument() ? items.filter(item => item.kind === 'separator' || !workareaOnly.has(item.label)) : items;
    // ----- Recent documents (kept only in this browser) -----
    const RECENT_KEY = 'ddn.recent.v1';
    function readRecent() { try {
        const list = JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]');
        return Array.isArray(list) ? list.filter(item => item && typeof item.title === 'string' && item.sources && Array.isArray(item.sources.files)) : [];
    }
    catch {
        return [];
    } }
    function rememberRecent(title, sources) {
        if (!isDesigner)
            return;
        try {
            const compact = { entry: sources.entry, files: sources.files.map(({ id, text, writable }) => ({ id, text, writable, revision: 'recent', encoding: 'utf-8' })) };
            if (compact.files.reduce((sum, file) => sum + file.text.length, 0) > 512 * 1024 || !compact.files.some(file => file.text.trim()))
                return;
            localStorage.setItem(RECENT_KEY, JSON.stringify([{ title, savedAt: new Date().toISOString(), sources: compact }, ...readRecent().filter(item => item.title !== title)].slice(0, 6)));
        }
        catch { /* Recent documents are optional. */ }
    }
    const openRecent = async (item) => {
        if (!await confirmReplace())
            return;
        if (!await loadSources(item.sources))
            return;
        const operation = openGeneration + 1, loaded = contentState();
        await open(true);
        if (operation === openGeneration && contentState() === loaded)
            markClean();
        toast('Opened ' + item.title);
    };
    const revert = async () => {
        const previous = lastOpened;
        if (!previous)
            throw Error('There is no opened version to return to yet.');
        if (!await confirmReplace(false))
            return;
        if (!await loadSources(previous.sources, previous.assets))
            return;
        const operation = openGeneration + 1, loaded = contentState();
        await open(true);
        if (operation === openGeneration && contentState() === loaded)
            markClean();
        toast('Reverted to the version you opened');
    };
    // ----- Import a stylesheet: adds the CSS file and a file-level style declaration -----
    const importStylesheet = () => {
        const picker = doc.createElement('input');
        picker.type = 'file';
        picker.accept = '.css,text/css';
        picker.addEventListener('change', () => void (async () => {
            const file = picker.files?.[0];
            if (!file)
                return;
            if (editorDirty)
                throw Error('Apply or reload the source text before importing a stylesheet.');
            const name = normalizeLocation(file.name), text = await file.text();
            const root = files.get(documentEntry);
            if (!root)
                throw Error('The document has no root file.');
            files.set(name, { id: name, text, revision: String(++sequence), encoding: 'utf-8', writable: true });
            assets.set(name, file);
            const declaration = `style ${JSON.stringify(name)}\n`;
            if (!root.text.split('\n').some(line => line.trim() === declaration.trim())) {
                const updated = declaration + root.text;
                files.set(documentEntry, { ...root, text: updated, revision: String(++sequence) });
                if (entry === documentEntry)
                    editor.value = updated;
            }
            editGeneration++;
            editorDirty = false;
            pendingDocument = true;
            refreshFiles();
            await open(true);
            setDirty(true);
            scheduleDraft();
            toast('Stylesheet imported: ' + name);
        })().catch(showError));
        picker.click();
    };
    // ----- Print the current view (or the chosen capture scope) through the browser -----
    const printCurrent = async () => {
        if (!viewer)
            throw Error('Open a document first');
        const result = await viewer.capture({ scope: captureTarget(), format: 'svg', extent: 'content', includePreview: false, partial: 'label', stale: 'label' });
        if (!result.ok)
            throw Error(result.diagnostics.map(d => d.message).join('; ') || result.reason);
        const svgText = await result.artifacts[0].blob.text();
        const frame = doc.createElement('iframe');
        frame.setAttribute('aria-hidden', 'true');
        frame.tabIndex = -1;
        frame.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden';
        doc.body.append(frame);
        const printDoc = frame.contentDocument;
        printDoc.open();
        printDoc.write('<!doctype html><html lang="en"><head><meta charset="utf-8"><title></title><style>@page{margin:12mm}html,body{margin:0}svg{display:block;width:100%;height:auto;max-height:calc(100vh - 2px)}</style></head><body></body></html>');
        printDoc.close();
        printDoc.title = doc.title;
        const parsed = new DOMParser().parseFromString(svgText, 'image/svg+xml').documentElement;
        printDoc.body.append(printDoc.importNode(parsed, true));
        const win = frame.contentWindow;
        win.addEventListener('afterprint', () => setTimeout(() => frame.remove(), 0));
        setTimeout(() => frame.remove(), 120000);
        win.focus();
        win.print();
    };
    // ----- Capture scope: what File › Export and Print include -----
    const chooseCaptureScope = () => {
        const chosen = standaloneDocument() && captureScope === 'workarea' ? 'view' : captureScope;
        const dialog = createStandardDialog(doc.body, { title: 'Capture scope', modal: false });
        const note = doc.createElement('p');
        note.textContent = 'Exports and prints use an explicit scope, never "whatever is on screen". The choice lasts for this session.';
        dialog.body.append(note);
        const choice = choiceField(dialog.body, 'Capture scope', [
            { value: 'view', label: 'Current view', preview: () => uiIcon(doc, 'fit-view') },
            ...(!standaloneDocument() ? [{ value: 'workarea', label: 'Whole workarea', description: 'Every view', preview: () => uiIcon(doc, 'fit') }] : []),
            { value: 'selection', label: 'Selected element', description: 'Falls back to the current view', preview: () => uiIcon(doc, 'select') },
        ], chosen);
        choice.addEventListener('change', () => { captureScope = choice.value; toast('Export scope updated.'); });
    };
    // ----- Help -----
    const siteLink = (path) => doc.querySelector('.app-site-nav') ? new URL('../' + path, doc.defaultView.location.href).href : undefined;
    const help = (label, path, shortcut) => ({ label, ...(shortcut ? { shortcut } : {}), hint: 'Part of the DDN website; open the designer from the website to use this link', enabled: () => !!siteLink(path), run: () => { const url = siteLink(path); if (url)
            doc.defaultView.open(url, '_blank', 'noopener'); } });
    const openHelp = () => { const url = siteLink('guide/index.html'); if (url)
        doc.defaultView.open(url, '_blank', 'noopener');
    else
        showShortcuts(); };
    const showAbout = () => {
        const dialog = createStandardDialog(doc.body, { title: 'About DDN' });
        const lines = [
            `DDN ${isDesigner ? 'Designer' : isVerifier ? 'Verifier' : 'Viewer'} · dialect ddn-next-1 · ${factories.edition === 'complete' ? 'complete profile edition' : 'native edition'}.`,
            'Everything runs in this browser. Nothing is uploaded; documents are kept only when you download them (a recovery copy stays in this browser).',
            'DDN is free and open-source software under GPL-2.0-or-later, sponsored by ScratchBird Software Inc. ScratchWeaver, the commercial edition, adds collaboration, live layout sharing, managed connectors, templates and more output formats with the same menus.',
        ];
        for (const text of lines) {
            const p = doc.createElement('p');
            p.textContent = text;
            dialog.body.append(p);
        }
        const link = doc.createElement('a');
        link.href = 'https://scratchbird.ca';
        link.target = '_blank';
        link.rel = 'noopener';
        link.textContent = 'scratchbird.ca';
        dialog.body.append(link);
    };
    const showWhatsNew = () => {
        const dialog = createStandardDialog(doc.body, { title: "What's new" });
        const list = doc.createElement('ul');
        for (const text of ['A menu bar: File, Edit, WorkArea, View, Document, Window and Help, the same in every edition.', 'The source panel is a drawer: collapse it to a rail, drag its edge to resize it, float it or pop it out.', 'Pop-out windows for the source, inspector, palette, navigator and the appearance editors, for a second monitor.', 'Cut, copy, paste, paste in place, paste as reference and duplicate.', 'Zoom presets, actual size, fit selection, and a zoom control in the status bar.', 'View settings: grid, snap to grid, mini-views, mouse wheel behaviour, toolbar and status bar.', 'Documents: new document views, page setup, header and footer, export, capture scope and print.', 'Command search (Ctrl+K) finds any menu command.']) {
            const item = doc.createElement('li');
            item.textContent = text;
            list.append(item);
        }
        dialog.body.append(list);
    };
    const commandSearch = () => {
        const entries = [];
        const walk = (items, path) => {
            for (const item of items) {
                if (item.kind === 'separator' || item.kind === 'heading')
                    continue;
                if (item.kind === 'submenu') {
                    walk(item.items(), path + ' › ' + item.label);
                    continue;
                }
                entries.push({ path, item });
            }
        };
        for (const spec of menuSpecs)
            walk(spec.items(), spec.label);
        const dialog = createStandardDialog(doc.body, { title: 'Command search' });
        const search = doc.createElement('input');
        search.type = 'search';
        search.placeholder = 'Type a command, e.g. "zoom" or "paste"';
        search.setAttribute('aria-label', 'Search commands');
        const list = doc.createElement('div');
        list.className = 'app-command-list';
        list.setAttribute('role', 'listbox');
        list.setAttribute('aria-label', 'Commands');
        dialog.body.append(search, list);
        let matches = [], active = 0;
        const usable = (item) => { try {
            return item.kind !== 'separator' && item.kind !== 'heading' && (!('enabled' in item) || !item.enabled || item.enabled());
        }
        catch {
            return false;
        } };
        const choose = (match) => { if (!match || !usable(match.item))
            return; dialog.close(); Promise.resolve().then(() => match.item.run?.()).catch(showError); };
        const render = () => {
            const words = search.value.toLowerCase().split(/\s+/).filter(Boolean);
            matches = entries.filter(entry => usable(entry.item) && words.every(word => (entry.path + ' ' + entry.item.label).toLowerCase().includes(word))).slice(0, 60);
            active = Math.min(active, Math.max(0, matches.length - 1));
            list.replaceChildren();
            matches.forEach((match, index) => {
                const option = doc.createElement('button');
                option.type = 'button';
                option.setAttribute('role', 'option');
                option.setAttribute('aria-selected', String(index === active));
                const label = doc.createElement('span');
                label.textContent = match.item.label;
                const where = doc.createElement('small');
                where.textContent = match.path;
                option.append(label, where);
                if (match.item.shortcut) {
                    const kbd = doc.createElement('kbd');
                    kbd.textContent = match.item.shortcut;
                    option.append(kbd);
                }
                option.addEventListener('click', () => choose(match));
                list.append(option);
            });
            if (!matches.length) {
                const empty = doc.createElement('p');
                empty.textContent = 'No available command matches.';
                list.append(empty);
            }
        };
        search.addEventListener('input', () => { active = 0; render(); });
        search.addEventListener('keydown', event => {
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault();
                active = (active + (event.key === 'ArrowDown' ? 1 : -1) + matches.length) % Math.max(1, matches.length);
                render();
                list.children[active]?.scrollIntoView({ block: 'nearest' });
            }
            else if (event.key === 'Enter') {
                event.preventDefault();
                choose(matches[active]);
            }
        });
        render();
        queueMicrotask(() => search.focus());
    };
    // ----- View settings: session display preferences, remembered in this browser -----
    const applyViewSettings = (redraw = true) => {
        if (isDesigner)
            surface.dataset.ddnMenus = '';
        surface.dataset.ddnGrid = viewPrefs.grid ? 'on' : 'off';
        surface.dataset.ddnSnap = viewPrefs.snap ? 'on' : 'off';
        surface.dataset.ddnLod = viewPrefs.lod ?? 'auto';
        surface.dataset.ddnWheel = viewPrefs.wheel ?? (isDesigner ? 'pan' : 'zoom');
        if (viewPrefs.quick === false)
            surface.dataset.ddnQuick = 'hidden';
        else
            delete surface.dataset.ddnQuick;
        const navigator = drawerFor(surface.querySelector('.ddn-viewer'), 'navigator');
        if (navigator) {
            if (viewPrefs.outline === false && navigator.mode !== 'hidden')
                navigator.setMode('hidden');
            else if (viewPrefs.outline !== false && navigator.mode === 'hidden')
                navigator.setMode('docked');
        }
        if (viewPrefs.outline === false && !detachedPanels.has('navigator'))
            surface.dataset.ddnOutline = 'hidden';
        else if (!detachedPanels.has('navigator'))
            delete surface.dataset.ddnOutline;
        doc.body.dataset.ddnStatus = viewPrefs.status === false ? 'hidden' : 'shown';
        if (viewPrefs.motion)
            doc.body.dataset.ddnMotion = 'reduced';
        else
            delete doc.body.dataset.ddnMotion;
        if (viewPrefs.contrast)
            doc.body.dataset.ddnContrast = 'high';
        else
            delete doc.body.dataset.ddnContrast;
        if (redraw)
            runCommand('view.redraw');
    };
    const toggleSetting = (key) => { viewPrefs[key] = !viewPrefs[key]; saveViewPrefs(); applyViewSettings(); };
    const showSetting = (key) => { viewPrefs[key] = viewPrefs[key] === false; saveViewPrefs(); applyViewSettings(false); };
    const setting = (label, checked, change, shortcut) => ({ label, checked, run: change, ...(shortcut ? { shortcut } : {}) });
    const choice = (label, current, value, change) => ({ label, radio: true, checked: () => current() === value, run: () => change(value) });
    const setTheme = (name) => { themeChoice.value = name; themeChoice.dispatchEvent(new Event('change')); };
    doc.addEventListener('ddn:interface-theme', () => syncDetachedThemes(doc));
    const toggleFullScreen = () => { if (doc.fullscreenElement)
        void doc.exitFullscreen();
    else
        void doc.documentElement.requestFullscreen?.().catch(() => toast('Full screen is not available here.', 'error')); };
    const viewerContainer = () => surface.querySelector('.ddn-viewer');
    const dockedIn = (selector, attribute) => ({
        element: () => surface.querySelector(selector),
        detaching: () => viewerContainer()?.removeAttribute(attribute),
        returned: () => { const container = viewerContainer(); if (container?.querySelector(selector))
            container.setAttribute(attribute, ''); },
    });
    const windowPanels = [
        { id: 'source', title: 'DDN source', element: () => panel, shown: () => main.dataset.sourceHidden !== 'true', show: () => showSource(false, true), hide: () => showSource(true, true),
            detaching: () => { main.dataset.sourceHidden = 'false'; main.dataset.sourceDetached = 'true'; }, returned: () => { delete main.dataset.sourceDetached; } },
        { id: 'inspector', title: 'Inspector', hostClass: 'ddn-viewer', ...dockedIn('.ddn-designer-dock-right', 'data-ddn-dock-right'), shown: () => !!surface.querySelector('.ddn-designer-dock-right'), show: () => { const found = command('window.inspector'); if (commandEnabled(found))
                void found.run(true); }, hide: () => { command('window.inspector')?.run(false); }, available: () => commandEnabled(command('window.inspector')), hint: 'Select an element first' },
        { id: 'palette', title: 'Element palette', hostClass: 'ddn-viewer', ...dockedIn('.ddn-designer-dock-left', 'data-ddn-dock-left'), shown: () => !!surface.querySelector('.ddn-designer-dock-left'), show: () => { const found = command('window.palette'); if (commandEnabled(found))
                void found.run(true); }, hide: () => { command('window.palette')?.run(false); }, available: () => commandEnabled(command('window.palette')), hint: 'This view type has no element palette' },
        { id: 'navigator', title: 'Navigator', hostClass: 'ddn-viewer', element: () => surface.querySelector('.ddn-viewer-outline'), shown: () => surface.dataset.ddnOutline !== 'hidden',
            show: () => { viewPrefs.outline = true; saveViewPrefs(); delete surface.dataset.ddnOutline; }, hide: () => { viewPrefs.outline = false; saveViewPrefs(); surface.dataset.ddnOutline = 'hidden'; },
            detaching: () => { surface.dataset.ddnOutline = 'hidden'; }, returned: () => { if (viewPrefs.outline !== false)
                delete surface.dataset.ddnOutline; }, available: () => !!viewer },
    ];
    const panelOf = (id) => windowPanels.find(item => item.id === id);
    const panelMode = (definition) => { const drawer = drawerFor(viewerContainer(), definition.id); if (drawer)
        return drawer.mode; const detached = detachedPanels.get(definition.id); return detached ? (detached.kind === 'window' ? 'popout' : 'floating') : definition.shown() ? 'docked' : 'hidden'; };
    function setPanelMode(definition, mode) {
        if (definition.id !== 'source') {
            if (!drawerFor(viewerContainer(), definition.id) && mode !== 'hidden')
                definition.show();
            const drawer = drawerFor(viewerContainer(), definition.id);
            if (drawer) {
                drawer.setMode(mode);
                refreshMenus();
                return;
            }
        }
        detachedPanels.get(definition.id)?.dock();
        if (mode === 'hidden') {
            definition.hide();
            refreshMenus();
            return;
        }
        if (!definition.shown())
            definition.show();
        const element = definition.element();
        if (mode === 'docked' || !element) {
            refreshMenus();
            return;
        }
        definition.detaching?.();
        const options = { title: definition.title, name: definition.id, hostClass: definition.hostClass ?? '', onKeydown: globalKeydown, onReturn: () => { detachedPanels.delete(definition.id); definition.returned?.(); refreshSourcePanelControls(); refreshMenus(); } };
        let result = mode === 'popout' ? popOut(element, options) : undefined;
        if (mode === 'popout' && !result)
            toast('The browser blocked the new window, so the panel floats in the page instead. Allow pop-ups for this page to use a second monitor.', 'error');
        result ??= floatPanel(element, { ...options, actions: [{ label: 'Dock', title: 'Return the panel to its place', run: () => setPanelMode(definition, 'docked') }, { label: 'Pop out', title: 'Open in its own window, for example on a second monitor', run: () => setPanelMode(definition, 'popout') }] });
        detachedPanels.set(definition.id, result);
        refreshSourcePanelControls();
        refreshMenus();
    }
    const sourceModes = doc.createElement('div');
    sourceModes.className = 'ddn-drawer-controls';
    sourceModes.setAttribute('role', 'group');
    sourceModes.setAttribute('aria-label', 'Source panel controls');
    sourceHeading.insertBefore(sourceModes, collapseSource);
    const sourceModeButtons = new Map();
    for (const [mode, label, icon, hint] of [['floating', 'Float source', 'layers', 'Float the source panel over the page.'], ['popout', 'Pop out source', 'expand', 'Open the source in its own window; move that window to another monitor.'], ['docked', 'Dock source', 'fit', 'Return the source to its drawer.']]) {
        const button = doc.createElement('button');
        button.type = 'button';
        button.setAttribute('aria-label', label);
        button.title = hint;
        button.append(uiIcon(doc, icon));
        button.addEventListener('click', () => setPanelMode(panelOf('source'), mode));
        sourceModes.append(button);
        sourceModeButtons.set(mode, button);
    }
    function refreshSourcePanelControls() { for (const [mode, button] of sourceModeButtons)
        button.hidden = mode === panelMode(panelOf('source')); }
    refreshSourcePanelControls();
    surface.addEventListener('ddn:drawer-change', event => {
        const detail = event.detail;
        if (!detail?.drawer || event.target !== viewerContainer())
            return;
        const { id, drawer } = detail;
        if (drawer.detached)
            detachedPanels.set(id, drawer.detached);
        else
            detachedPanels.delete(id);
        if (id === 'navigator') {
            viewPrefs.outline = drawer.mode !== 'hidden';
            saveViewPrefs();
            if (drawer.mode === 'docked')
                delete surface.dataset.ddnOutline;
            else
                surface.dataset.ddnOutline = 'hidden';
        }
        refreshMenus();
    });
    const togglePanel = (id) => { const definition = panelOf(id); if (panelMode(definition) === 'hidden') {
        if (!definition.available || definition.available())
            setPanelMode(definition, 'docked');
    }
    else
        setPanelMode(definition, 'hidden'); };
    const panelMenu = (id, shortcut) => {
        const definition = panelOf(id), usable = () => panelMode(definition) !== 'hidden' || !definition.available || definition.available();
        const mode = (label, value) => ({ label, radio: true, checked: () => panelMode(definition) === value, enabled: usable, ...(definition.hint ? { hint: definition.hint } : {}), run: () => setPanelMode(definition, value) });
        return { kind: 'submenu', label: definition.title, items: () => [mode('Docked', 'docked'), mode('Floating', 'floating'), mode('Pop out to a window', 'popout'), { ...mode('Hidden', 'hidden'), ...(shortcut ? { shortcut } : {}) }] };
    };
    const toggleSource = () => { const definition = panelOf('source'), current = panelMode(definition); setPanelMode(definition, current === 'hidden' ? 'docked' : current === 'docked' ? 'hidden' : 'docked'); };
    const runFind = () => { if (panelMode(panelOf('navigator')) === 'hidden')
        setPanelMode(panelOf('navigator'), 'docked'); return runCommand('edit.find'); };
    // ----- The menus -----
    const zoomPresets = [25, 50, 75, 100, 150, 200, 400];
    const recentItems = () => { const list = readRecent(); return list.length ? list.map(item => ({ label: item.title, run: () => openRecent(item) })) : [{ label: 'No recent documents in this browser', enabled: () => false }]; };
    const menuSpecs = [
        { label: 'File', items: () => isVerifier ? [
                { label: 'Open files…', shortcut: 'Ctrl+O', run: openFiles }, { label: 'Open a sample…', run: openSampleDialog }, separator,
                heading('Report'), { label: 'Download report', run: downloadSource }, separator, { label: 'Keyboard shortcuts', shortcut: '?', run: showShortcuts },
            ] : [
                ...(isDesigner ? [{ label: 'New diagram…', shortcut: 'Ctrl+Alt+N', run: newDocument }, weaver('New from template…')] : []),
                { label: 'Open files…', shortcut: 'Ctrl+O', run: openFiles }, { label: 'Open a sample…', run: openSampleDialog },
                ...(isDesigner ? [{ kind: 'submenu', label: 'Open recent', items: recentItems }] : []),
                separator, heading('Save'),
                { label: 'Download .ddn', shortcut: 'Ctrl+S', run: downloadSource },
                { label: 'Save as bundle (.zip)', shortcut: 'Ctrl+Shift+S', run: saveBundle },
                { label: 'Download assets', run: downloadAssets },
                ...(isDesigner ? [weaver('Save as template…'), { label: 'Revert to last opened', enabled: () => !!lastOpened, hint: 'Nothing has been opened yet', run: revert }] : []),
                separator, heading('Import'),
                needsDesigner(bus('CSV as dataset…', 'workarea.import-csv')), needsDesigner({ label: 'CSS stylesheet…', run: importStylesheet, enabled: () => !!viewer }),
                separator, heading('Export'),
                { label: 'Export SVG', run: exportAs('svg') }, { label: 'Export PNG', run: exportAs('png') }, { label: 'Export JSON', run: exportAs('json') }, { label: 'Export Markdown', run: exportAs('markdown') }, { label: 'Export CSV', run: exportAs('csv') },
                { label: 'Print…', shortcut: 'Ctrl+P', run: printCurrent, enabled: () => !!viewer },
            ] },
        { label: 'Edit', items: () => [
                bus('Undo', 'edit.undo', { shortcut: 'Ctrl+Z' }), bus('Redo', 'edit.redo', { shortcut: 'Ctrl+Shift+Z' }), separator,
                bus('Cut', 'edit.cut', { shortcut: 'Ctrl+X', hint: 'Select an element first' }), bus('Copy', 'edit.copy', { shortcut: 'Ctrl+C', hint: 'Select an element first' }),
                bus('Paste', 'edit.paste', { shortcut: 'Ctrl+V' }), bus('Paste in place', 'edit.paste-in-place', { shortcut: 'Ctrl+Shift+V' }), bus('Paste as reference', 'edit.paste-reference', { shortcut: 'Ctrl+Alt+V' }),
                bus('Duplicate', 'edit.duplicate', { shortcut: 'Ctrl+D', hint: 'Select an element first' }), bus('Delete', 'edit.delete', { shortcut: 'Delete', hint: 'Select an element first' }), separator,
                later('Select all in view', 'Ctrl+A'), later('Select connected'), bus('Deselect', 'edit.deselect', { shortcut: 'Esc' }), separator,
                { label: 'Find…', shortcut: 'Ctrl+F', enabled: () => commandEnabled(command('edit.find')), run: () => { runFind(); } },
                bus('Rename', 'edit.rename', { shortcut: 'F2', hint: 'Select an element first' }), bus('Properties', 'edit.properties', { shortcut: 'P', hint: 'Select an element first' }),
                bus('Appearance & presets…', 'edit.appearance', { hint: 'Select an element first' }), bus('Review status…', 'edit.status', { hint: 'Select an element first' }),
            ] },
        { label: 'WorkArea', items: () => documentItems([
                bus('Workarea settings…', 'workarea.settings', { hint: 'Open a document in the designer first' }), separator, heading('Views and elements'),
                bus('Add view…', 'workarea.add-view'), { label: 'Add document view…', enabled: () => commandEnabled(command('document.new')), hint: 'Open a document in the designer first', run: () => { runCommand('document.new'); } },
                later('Place an existing view'), bus('Add element…', 'workarea.add-element', { shortcut: 'A' }), bus('Add existing element…', 'workarea.add-existing'), bus('Connect', 'workarea.connect', { shortcut: 'C' }), bus('Add entity', 'workarea.add-entity', { hint: 'ERD views only' }),
                bus('Reflow view', 'workarea.reflow', { hint: 'Release fixed positions and arrange the active diagram' }),
                { label: 'Navigator', shortcut: 'Ctrl+Shift+E', checked: () => panelMode(panelOf('navigator')) !== 'hidden', run: () => togglePanel('navigator') },
                later('Layers'), later('Regions'), later('Bookmarks'), separator, heading('Data'),
                bus('Data sources and datasets…', 'workarea.datasets'), bus('Import CSV as dataset…', 'workarea.import-csv'), bus('Projection settings…', 'workarea.projection', { hint: 'Data-bound views only' }),
                separator, heading('Styles'), later('Workarea defaults…'), needsDesigner({ label: 'Import stylesheet…', run: importStylesheet, enabled: () => !!viewer }),
                separator, weaver('Managed connectors…'), weaver('Collaborators and presence'),
            ]).map(needsDesigner) },
        { label: 'View', items: () => documentItems([
                bus('Zoom in', 'view.zoom-in', { shortcut: 'Ctrl+=' }), bus('Zoom out', 'view.zoom-out', { shortcut: 'Ctrl+−' }),
                { kind: 'submenu', label: 'Zoom to', enabled: () => commandEnabled(command('view.zoom')), items: () => zoomPresets.map(percent => bus(percent + ' %', 'view.zoom', { argument: percent, checked: () => command('view.zoom')?.value?.() === percent + '%', radio: true })) },
                bus('Actual size (100 %)', 'view.actual-size', { shortcut: 'Ctrl+0' }), separator,
                bus('Fit workarea', 'view.fit-workarea', { shortcut: 'Shift+1' }), bus('Fit selection', 'view.fit-selection', { shortcut: 'Shift+2' }), bus('Fit current view', 'view.fit-view', { shortcut: 'Shift+3' }),
                bus('Expand view', 'view.expand', { checked: () => !!command('view.expand')?.checked?.() }), bus('Back', 'view.back', { shortcut: 'Alt+←' }), bus('Forward', 'view.forward', { shortcut: 'Alt+→' }),
                bus('Item details…', 'view.details'), separator,
                setting('Show grid', () => !!viewPrefs.grid, () => toggleSetting('grid')), setting('Snap to grid', () => !!viewPrefs.snap, () => toggleSetting('snap')),
                later('Rulers'), later('Guides'),
                { kind: 'submenu', label: 'Mini-views when small', items: () => [choice('Automatic', () => viewPrefs.lod ?? 'auto', 'auto', value => { viewPrefs.lod = value; saveViewPrefs(); applyViewSettings(); }), choice('Always frames', () => viewPrefs.lod ?? 'auto', 'frames', value => { viewPrefs.lod = value; saveViewPrefs(); applyViewSettings(); }), choice('Never', () => viewPrefs.lod ?? 'auto', 'full', value => { viewPrefs.lod = value; saveViewPrefs(); applyViewSettings(); })] },
                { kind: 'submenu', label: 'Mouse wheel', items: () => [choice('Scrolls (Ctrl+wheel zooms)', () => surface.dataset.ddnWheel ?? 'zoom', 'pan', value => { viewPrefs.wheel = value; saveViewPrefs(); applyViewSettings(false); }), choice('Zooms', () => surface.dataset.ddnWheel ?? 'zoom', 'zoom', value => { viewPrefs.wheel = value; saveViewPrefs(); applyViewSettings(false); })] },
                later('Show documents at print size'), separator,
                ...(isDesigner ? [setting('Quick-access toolbar', () => viewPrefs.quick !== false, () => showSetting('quick'))] : []),
                setting('Status bar', () => viewPrefs.status !== false, () => showSetting('status')),
                { kind: 'submenu', label: 'Interface theme', items: () => [...UI_THEME_NAMES.map(name => choice(name.charAt(0).toUpperCase() + name.slice(1), () => interfaceTheme, name, value => setTheme(value))), separator, { label: 'Interface colours…', run: () => customise.click() }] },
                setting('Reduced motion', () => !!viewPrefs.motion, () => toggleSetting('motion')), setting('High contrast', () => !!viewPrefs.contrast, () => toggleSetting('contrast')),
                { label: 'Full screen', shortcut: 'F11', run: toggleFullScreen, checked: () => !!doc.fullscreenElement },
            ]) },
        { label: 'Document', items: () => documentItems([
                bus('New document view…', 'document.new', { hint: 'Open a document in the designer first' }),
                weaver('PPTX output'), weaver('Send by email…'), separator,
                bus('Page setup…', 'document.page-setup'), bus('Header…', 'document.header'), bus('Footer…', 'document.footer'),
                { label: 'Capture scope…', run: chooseCaptureScope, enabled: () => !!viewer }, later('Page preview'), later('Document defaults and stylesheet…'), separator,
                bus('Export document…', 'document.export', { shortcut: 'Ctrl+E' }), { label: 'Print…', shortcut: 'Ctrl+P', run: printCurrent, enabled: () => !!viewer },
            ]).map(needsDesigner) },
        { label: 'Window', items: () => [
                panelMenu('source', 'Ctrl+\\'), panelMenu('inspector', 'Ctrl+I'), panelMenu('palette'), panelMenu('navigator', 'Ctrl+Shift+E'), separator,
                heading('Open windows'),
                ...(detachedPanels.size ? [...detachedPanels].map(([id, detached]) => ({ label: panelOf(id).title + (detached.kind === 'window' ? ' (window)' : ' (floating)'), run: () => detached.focus() })) : [{ label: 'No detached panels', enabled: () => false }]),
                separator, { label: 'Dock all', enabled: () => detachedPanels.size > 0, run: () => { for (const detached of [...detachedPanels.values()])
                        detached.dock(); } },
                { label: 'Reset layout', run: () => { for (const detached of [...detachedPanels.values()])
                        detached.dock(); try {
                        for (const key of Object.keys(localStorage))
                            if (key.startsWith('ddn.detached.'))
                                localStorage.removeItem(key);
                    }
                    catch { /* optional */ } delete viewPrefs.sourceWidth; viewPrefs.sourceHidden = false; viewPrefs.outline = true; saveViewPrefs(); setSourceWidth(340, false); showSource(false); applyViewSettings(); toast('Layout reset'); } },
            ] },
        { label: 'Help', items: () => [
                { label: 'Command search…', shortcut: 'Ctrl+K', run: commandSearch }, { label: 'Keyboard shortcuts', shortcut: '?', run: showShortcuts }, separator,
                help('Guide', 'guide/index.html', 'F1'), help('Language reference', 'reference/index.html'), help('Field guide', 'field-guide/index.html'), help('Gallery', 'gallery/index.html'), separator,
                { label: "What's new", run: showWhatsNew }, { label: 'About DDN', run: showAbout },
            ] },
    ];
    const menuBar = createMenuBar(doc, menuSpecs, { label: isDesigner ? 'Designer menu' : isVerifier ? 'Verifier menu' : 'Viewer menu', onError: showError });
    bar.insertBefore(menuBar.element, siteSlot);
    let menuFrame = 0;
    refreshMenus = () => { if (menuFrame || !menuBar.isOpen())
        return; menuFrame = requestAnimationFrame(() => { menuFrame = 0; menuBar.refresh(); }); };
    // ----- Status bar zoom control -----
    const zoomGroup = doc.createElement('div');
    zoomGroup.className = 'app-zoom';
    zoomGroup.setAttribute('role', 'group');
    zoomGroup.setAttribute('aria-label', 'Zoom');
    zoomGroup.hidden = true;
    const zoomButton = (text, label, title, run) => { const button = doc.createElement('button'); button.type = 'button'; button.textContent = text; button.setAttribute('aria-label', label); button.title = title; button.addEventListener('click', run); zoomGroup.append(button); return button; };
    const zoomOutButton = zoomButton('−', 'Zoom out', 'Zoom out (Ctrl+−)', () => { runCommand('view.zoom-out'); });
    const zoomValue = zoomButton('100%', 'Zoom level', 'Choose a zoom level', () => openPopupMenu(zoomValue, documentItems([
        ...zoomPresets.map(percent => ({ label: percent + ' %', radio: true, checked: () => command('view.zoom')?.value?.() === percent + '%', run: () => { runCommand('view.zoom', percent); } })),
        separator, { label: 'Fit workarea', shortcut: 'Shift+1', run: () => { runCommand('view.fit-workarea'); } }, { label: 'Fit selection', shortcut: 'Shift+2', enabled: () => commandEnabled(command('view.fit-selection')), run: () => { runCommand('view.fit-selection'); } }, { label: 'Fit current view', shortcut: 'Shift+3', enabled: () => commandEnabled(command('view.fit-view')), run: () => { runCommand('view.fit-view'); } },
        separator, { label: 'Custom…', run: customZoom },
    ]), 'Zoom level', showError));
    zoomValue.className = 'app-zoom-value';
    zoomValue.setAttribute('aria-haspopup', 'menu');
    zoomValue.setAttribute('aria-expanded', 'false');
    const zoomInButton = zoomButton('+', 'Zoom in', 'Zoom in (Ctrl+=)', () => { runCommand('view.zoom-in'); });
    function customZoom() {
        const original = parseInt(command('view.zoom')?.value?.() ?? '100', 10);
        const dialog = createStandardDialog(doc.body, { title: 'Zoom level', modal: false });
        const field = numberField(dialog.body, 'Zoom (%)', original, { min: 5, max: 3200 });
        field.addEventListener('input', () => { if (!field.checkValidity() || !Number.isFinite(field.valueAsNumber)) {
            dialog.showError('Enter a zoom from 5 % to 3200 %.');
            return;
        } dialog.showError(''); runCommand('view.zoom', field.valueAsNumber); });
    }
    status.append(zoomGroup);
    const updateStatusZoom = () => {
        const zoom = command('view.zoom');
        zoomGroup.hidden = !zoom;
        if (!zoom)
            return;
        zoomValue.textContent = zoom.value?.() ?? '—';
        const enabled = commandEnabled(zoom);
        zoomOutButton.disabled = zoomInButton.disabled = zoomValue.disabled = !enabled;
    };
    surface.addEventListener(UI_COMMANDS_CHANGED, () => { updateStatusZoom(); refreshMenus(); });
    // The tools row only holds file/view pickers now; hide it when it would be empty.
    const updateToolsRow = () => { tools.dataset.empty = String(![...tools.children].some(child => child instanceof HTMLElement && !child.hidden && child.tagName !== 'INPUT' && !child.classList.contains('app-spacer') && getComputedStyle(child).display !== 'none')); };
    new MutationObserver(updateToolsRow).observe(tools, { subtree: true, attributes: true, attributeFilter: ['hidden'], childList: true });
    updateToolsRow();
    // ----- Keyboard shortcuts (also forwarded from detached panels) -----
    function globalKeydown(event) {
        if (event.defaultPrevented)
            return;
        const target = event.target;
        const within = (selector) => !!target && typeof target.closest === 'function' && !!target.closest(selector);
        const typing = !!target?.isContentEditable || within('input, textarea, select, [contenteditable=true]');
        const inDiagram = within('.ddn-viewer') && target.ownerDocument === doc, inDialog = within('.ddn-ui-dialog');
        const mod = event.ctrlKey || event.metaKey, letter = event.code.startsWith('Key') ? event.code.slice(3).toLowerCase() : event.key.toLowerCase();
        const take = (done) => { if (done)
            event.preventDefault(); };
        if (mod && !event.altKey && letter === 's') {
            event.preventDefault();
            void (event.shiftKey ? saveBundle() : downloadSource()).catch(showError);
            return;
        }
        if (mod && !event.altKey && !event.shiftKey && letter === 'o') {
            event.preventDefault();
            void openFiles().catch(showError);
            return;
        }
        if (mod && event.key === '\\') {
            event.preventDefault();
            toggleSource();
            return;
        }
        if (mod && !event.altKey && !event.shiftKey && letter === 'k') {
            event.preventDefault();
            if (!doc.querySelector('.ddn-ui-dialog[aria-modal=true]'))
                commandSearch();
            return;
        }
        if (event.key === 'F1') {
            event.preventDefault();
            openHelp();
            return;
        }
        if (mod && event.altKey && letter === 'n' && isDesigner) {
            event.preventDefault();
            void newDocument().catch(showError);
            return;
        }
        if (typing || inDialog || menuBar.isOpen())
            return;
        if (event.key === '?' && !mod && !doc.querySelector('.ddn-ui-dialog')) {
            event.preventDefault();
            showShortcuts();
            return;
        }
        if (mod && event.shiftKey && !event.altKey && letter === 'e') {
            event.preventDefault();
            togglePanel('navigator');
            return;
        }
        if (mod && !event.shiftKey && !event.altKey && letter === 'i') {
            if (isDesigner) {
                event.preventDefault();
                togglePanel('inspector');
            }
            return;
        }
        if (mod && !event.shiftKey && !event.altKey && letter === 'e') {
            take(runCommand('document.export'));
            return;
        }
        if (mod && !event.shiftKey && !event.altKey && letter === 'p') {
            event.preventDefault();
            void printCurrent().catch(showError);
            return;
        }
        if (mod && !event.shiftKey && !event.altKey && letter === 'f') {
            take(runFind());
            return;
        }
        if (mod && !event.altKey && (event.key === '=' || event.key === '+')) {
            take(runCommand('view.zoom-in'));
            return;
        }
        if (mod && !event.altKey && (event.key === '-' || event.key === '_')) {
            take(runCommand('view.zoom-out'));
            return;
        }
        if (mod && !event.altKey && event.key === '0') {
            take(runCommand('view.actual-size'));
            return;
        }
        if (event.altKey && !mod && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
            take(runCommand(event.key === 'ArrowLeft' ? 'view.back' : 'view.forward'));
            return;
        }
        if (event.shiftKey && !mod && !event.altKey && ['Digit1', 'Digit2', 'Digit3'].includes(event.code)) {
            take(runCommand(event.code === 'Digit1' ? 'view.fit-workarea' : event.code === 'Digit2' ? 'view.fit-selection' : 'view.fit-view'));
            return;
        }
        if (!isDesigner)
            return;
        if (mod && !event.altKey && !event.shiftKey && letter === 'x') {
            take(runCommand('edit.cut'));
            return;
        }
        if (mod && !event.altKey && !event.shiftKey && letter === 'c') {
            take(runCommand('edit.copy'));
            return;
        }
        if (mod && event.altKey && letter === 'v') {
            take(runCommand('edit.paste-reference'));
            return;
        }
        if (mod && event.shiftKey && letter === 'v') {
            take(runCommand('edit.paste-in-place'));
            return;
        }
        if (mod && !event.altKey && letter === 'v') {
            take(runCommand('edit.paste'));
            return;
        }
        if (mod && !event.shiftKey && !event.altKey && letter === 'd') {
            take(runCommand('edit.duplicate'));
            return;
        }
        if (mod && !event.shiftKey && !event.altKey && letter === 'y') {
            take(runCommand('edit.redo'));
            return;
        }
        // Inside the diagram the designer handles undo and Delete itself.
        if (!inDiagram && mod && !event.altKey && letter === 'z') {
            take(runCommand(event.shiftKey ? 'edit.redo' : 'edit.undo'));
            return;
        }
    }
    doc.addEventListener('keydown', globalKeydown);
    applyViewSettings(false);
    surface.addEventListener('dragover', event => event.preventDefault());
    surface.addEventListener('drop', event => {
        event.preventDefault();
        if (event.dataTransfer?.files)
            void (async () => { const selected = Array.from(event.dataTransfer.files); if (await confirmReplace())
                await readFiles(selected); })().catch(showError);
    });
    // ----- Initial document: the website's example, a kept draft, or a blank document -----
    const draft = pendingRecovery;
    if (factories.initial) {
        entry = documentEntry = factories.initial.sources.entry;
        for (const file of factories.initial.sources.files)
            files.set(file.id, file);
        for (const [id, asset] of Object.entries(factories.initial.assets ?? {})) {
            assets.set(id, new File([asset.text], id, { type: asset.mime }));
            draftAssets.push(encodeDraftAsset(id, asset.mime, new TextEncoder().encode(asset.text)));
        }
        editor.value = files.get(entry)?.text ?? '';
    }
    else {
        editor.value = isDesigner ? BLANK_DOCUMENT : examples['ERD whiteboard'];
        files.set(entry, { id: entry, text: editor.value, revision: String(++sequence), encoding: 'utf-8', writable: true });
    }
    refreshFiles();
    markClean();
    void open().then(() => {
        factories.ready?.({ ...(viewer ? { viewer } : {}), ...(designer ? { designer } : {}), ...(verifier ? { verifier } : {}) });
        if (draft) {
            const banner = doc.createElement('div');
            recoveryBanner = banner;
            banner.className = 'app-banner';
            banner.setAttribute('role', 'region');
            banner.setAttribute('aria-label', 'Unsaved work found');
            const when = new Date(draft.savedAt);
            const text = doc.createElement('span');
            text.textContent = `You have unsaved work from ${Number.isNaN(when.getTime()) ? 'an earlier visit' : when.toLocaleString()} (${draft.files.length} file${draft.files.length === 1 ? '' : 's'}).`;
            const sp = doc.createElement('span');
            sp.className = 'app-spacer';
            const restore = doc.createElement('button');
            restore.type = 'button';
            restore.textContent = 'Restore';
            restore.classList.add('app-primary');
            const discard = doc.createElement('button');
            discard.type = 'button';
            discard.textContent = 'Discard';
            banner.append(text, sp, restore, discard);
            main.prepend(banner);
            restore.addEventListener('click', () => {
                void (async () => {
                    if (!await confirmReplace(false))
                        return;
                    if (!await loadSources(draft, restoreDraftAssets(draft)))
                        return;
                    const operation = openGeneration + 1;
                    try {
                        await open(true);
                    }
                    finally {
                        if (operation === openGeneration) {
                            setDirty(true);
                            persistDraft();
                        }
                    }
                    if (operation !== openGeneration)
                        return;
                    toast('Restored your unsaved work');
                })().catch(showError);
            });
            discard.addEventListener('click', () => clearRecovery());
        }
    }).catch(showError);
}
//# sourceMappingURL=shell.js.map