/** Interface preferences only: these tokens never enter a DDN document. */
export const UI_THEME_NAMES = ['light', 'dark', 'midnight', 'warm'];
const colourTokens = ['bg', 'surface', 'input', 'text', 'muted', 'border', 'accent', 'accent-text', 'danger', 'shadow'];
const metrics = {
    'font-size': [13, 11, 16], 'control-height': [32, 28, 40],
    radius: [12, 0, 16], 'dialog-width': [480, 280, 560],
};
export const UI_THEME_TOKEN_NAMES = [...colourTokens, ...Object.keys(metrics)].map(name => `--ddn-ui-${name}`);
const themes = {
    light: ['#f3f6fc', '#ffffff', '#f8faff', '#18263d', '#55677f', '#d6dfed', '#3468db', '#ffffff', '#a71d3a', '#14243620'],
    dark: ['#0f172a', '#1b263b', '#111c30', '#f1f5fc', '#abbad0', '#35445e', '#80b3ff', '#10233d', '#ff9dad', '#02081780'],
    midnight: ['#070b16', '#11182b', '#0b1020', '#f1efff', '#b3b0cf', '#34344f', '#b4a2ff', '#1b1237', '#ff9dad', '#00000090'],
    warm: ['#f7f2e8', '#fffaf2', '#fdf8ef', '#44382d', '#79634c', '#dfd0ba', '#955023', '#ffffff', '#aa3140', '#49372120'],
};
const themeProperties = (name) => colourTokens.map((token, index) => `--ddn-ui-${token}:${themes[name][index]}`).join(';');
const css = `
:root{${themeProperties('light')};${Object.entries(metrics).map(([key, values]) => `--ddn-ui-${key}:${values[0]}px`).join(';')}}
${UI_THEME_NAMES.map(name => `[data-ddn-ui-theme="${name}"]{${themeProperties(name)};color-scheme:${name === 'dark' || name === 'midnight' ? 'dark' : 'light'}}`).join('\n')}
.ddn-ui-layer{position:fixed;inset:0;display:grid;align-items:center;justify-items:center;padding:12px;box-sizing:border-box;pointer-events:auto;background:var(--ddn-ui-shadow);isolation:isolate}
.ddn-ui-layer[data-modal=false]{pointer-events:none;background:transparent}
.ddn-ui-layer[data-positioned]>.ddn-ui-dialog{position:absolute;width:min(var(--ddn-ui-dialog-width),calc(100% - 24px))}
.ddn-ui-dialog{position:relative;box-sizing:border-box;display:grid;grid-template-rows:auto minmax(0,1fr) auto auto;width:min(var(--ddn-ui-dialog-width),100%);max-height:min(640px,calc(100vh - 24px));max-height:min(640px,calc(100dvh - 24px));min-height:0;overflow:hidden;background:var(--ddn-ui-surface);color:var(--ddn-ui-text);border:1px solid var(--ddn-ui-border);border-radius:var(--ddn-ui-radius);box-shadow:0 22px 64px var(--ddn-ui-shadow),0 2px 10px var(--ddn-ui-shadow);font:var(--ddn-ui-font-size)/1.4 Inter,system-ui,sans-serif;pointer-events:auto}
.ddn-ui-dialog[data-ddn-resized]{max-width:calc(100vw - 24px);max-height:calc(100dvh - 24px)}
.ddn-ui-dialog *,.ddn-ui-colour-field *{box-sizing:border-box}
.ddn-ui-icon{display:inline-block;width:16px;height:16px;min-height:0;flex:none;pointer-events:none;vertical-align:middle}
.ddn-ui-dialog-header{display:flex;align-items:center;gap:8px;padding:6px 10px;border-bottom:1px solid var(--ddn-ui-border)}
.ddn-ui-dialog-header h3{flex:1;min-width:0;margin:0;font-size:14px;line-height:1.4;font-weight:650;letter-spacing:-.015em;overflow-wrap:anywhere}
.ddn-ui-dialog-body{min-height:0;overflow:auto;overscroll-behavior:contain;padding:10px 12px}
.ddn-ui-dialog-footer{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:6px;margin:0;padding:8px 34px 8px 12px;border-top:1px solid var(--ddn-ui-border);background:var(--ddn-ui-bg)}
.ddn-ui-dialog-error{color:var(--ddn-ui-danger);margin:0;padding:6px 12px;max-height:80px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere}
.ddn-ui-dialog [hidden]{display:none!important}
.ddn-ui-dialog-error[hidden]{display:none}
.ddn-ui-dialog label{display:block;margin:6px 0}
.ddn-ui-dialog label>input,.ddn-ui-dialog label>select,.ddn-ui-dialog label>textarea{display:block;margin-top:3px}
.ddn-ui-dialog input:not([type=checkbox]):not([type=radio]),.ddn-ui-dialog select,.ddn-ui-dialog textarea,.ddn-ui-colour-field input{width:100%;min-width:0;min-height:var(--ddn-ui-control-height);padding:4px 7px;border:1px solid var(--ddn-ui-border);border-radius:8px;background:var(--ddn-ui-input);color:var(--ddn-ui-text);font:inherit}
.ddn-ui-dialog input[type=checkbox],.ddn-ui-dialog input[type=radio]{display:inline-block;width:auto;margin:0 6px 0 0;accent-color:var(--ddn-ui-accent)}
.ddn-ui-dialog textarea{min-height:88px;resize:vertical;white-space:pre-wrap}
.ddn-ui-dialog button,.ddn-ui-colour-field button{min-height:var(--ddn-ui-control-height);padding:4px 10px;border:1px solid var(--ddn-ui-border);border-radius:8px;background:var(--ddn-ui-input);color:var(--ddn-ui-text);font:inherit;cursor:pointer}
.ddn-ui-dialog button[data-ddn-apply]{background:var(--ddn-ui-accent);color:var(--ddn-ui-accent-text);border-color:var(--ddn-ui-accent)}
.ddn-ui-dialog button:not(:disabled):hover{border-color:var(--ddn-ui-accent)}
.ddn-ui-dialog button:disabled{opacity:.55;cursor:default}
.ddn-ui-dialog .ddn-ui-dialog-move{width:100%;text-align:left;padding:3px 2px;border:0;background:transparent;font:inherit;cursor:grab;touch-action:none;user-select:none}
.ddn-ui-dialog .ddn-ui-dialog-move.ddn-ui-dragging{cursor:grabbing}
.ddn-ui-dialog .ddn-ui-dialog-dismiss{flex:0 0 28px;min-height:28px;padding:0;border:0;background:transparent;font-size:20px;line-height:1}
.ddn-ui-dialog .ddn-ui-dialog-popout{flex:0 0 28px;min-height:28px;padding:0;border:0;background:transparent;font-size:15px;line-height:1;color:var(--ddn-ui-muted)}
.ddn-ui-dialog .ddn-ui-dialog-popout:hover{color:var(--ddn-ui-accent)}
.ddn-ui-dialog :focus-visible,.ddn-ui-colour-field :focus-visible{outline:2px solid var(--ddn-ui-accent);outline-offset:2px}
.ddn-ui-dialog input[aria-invalid=true]{border-color:var(--ddn-ui-danger)}
.ddn-ui-dialog fieldset{min-width:0;margin:8px 0;padding:10px;border:1px solid var(--ddn-ui-border);border-radius:10px}
.ddn-ui-dialog legend{padding:0 4px;color:var(--ddn-ui-muted)}
.ddn-ui-dialog p{margin:6px 0}
.ddn-ui-dialog pre{max-width:100%;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere}
.ddn-ui-dialog table{border-collapse:collapse;width:100%}
.ddn-ui-dialog th,.ddn-ui-dialog td{padding:4px;border:1px solid var(--ddn-ui-border)}
.ddn-ui-colour-field{display:flex;align-items:flex-end;gap:6px;margin:6px 0;font:var(--ddn-ui-font-size)/1.4 Inter,system-ui,sans-serif;color:var(--ddn-ui-text)}
.ddn-ui-colour-field>label{flex:1;min-width:0;margin:0}
.ddn-ui-colour-field>label>input{display:block;margin-top:3px}
.ddn-ui-colour-field input[type=color]{width:36px;height:var(--ddn-ui-control-height);flex:0 0 36px;padding:2px}
.ddn-ui-colour-field>button{flex:0 0 auto;padding:4px 7px}
.ddn-ui-colour-channels{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px}
.ddn-ui-colour-swatches{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:5px;margin:8px 0}
.ddn-ui-dialog .ddn-ui-colour-swatches button{padding:3px;min-width:0}
.ddn-ui-colour-swatches span{display:block;min-height:20px;border:1px solid var(--ddn-ui-border);border-radius:2px}
.ddn-ui-colour-previews{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:8px 0}
.ddn-ui-colour-preview{background:repeating-conic-gradient(#ddd 0% 25%,#fff 0% 50%) 0/12px 12px;border:1px solid var(--ddn-ui-border);border-radius:4px;overflow:hidden}
.ddn-ui-colour-preview>span{display:block;height:48px}
.ddn-ui-colour-preview-label{display:block;margin-bottom:3px;color:var(--ddn-ui-muted)}
.ddn-ui-number-field{min-width:0;margin:6px 0}
.ddn-ui-number-field>label{margin:0 0 3px}
.ddn-ui-number-controls{display:grid;grid-template-columns:minmax(0,1fr) 80px;gap:10px;align-items:center}
.ddn-ui-dialog .ddn-ui-number-controls input[type=range]{padding:0;min-width:0;width:100%;border:0;box-shadow:none;background:transparent;accent-color:var(--ddn-ui-accent);cursor:pointer}
@media(max-width:380px){.ddn-ui-layer{padding:6px}.ddn-ui-dialog{max-height:calc(100dvh - 12px)}.ddn-ui-layer[data-positioned]>.ddn-ui-dialog{width:min(var(--ddn-ui-dialog-width),calc(100% - 12px))}.ddn-ui-dialog-header,.ddn-ui-dialog-body{padding:8px}.ddn-ui-dialog-footer{padding:6px 32px 6px 8px}.ddn-ui-colour-channels{grid-template-columns:repeat(2,minmax(0,1fr))}}
`;
/** Install once per document without overriding any inherited theme. */
export function installUITheme(host) {
    const document = host.ownerDocument;
    if (!document.querySelector('style[data-ddn-ui-theme-styles]')) {
        const style = document.createElement('style');
        style.dataset.ddnUiThemeStyles = '';
        style.textContent = css;
        (document.head ?? document.documentElement).append(style);
    }
    host.classList.add('ddn-ui-theme');
}
/** Reject unknown/unbounded values atomically; switching theme clears old overrides. */
export function setUITheme(host, name, overrides = {}) {
    if (!UI_THEME_NAMES.includes(name))
        throw new Error('Unknown DDN interface theme');
    const validated = [];
    for (const [key, value] of Object.entries(overrides)) {
        if (!UI_THEME_TOKEN_NAMES.includes(key))
            throw new Error(`Unknown interface token: ${key}`);
        const token = key.slice('--ddn-ui-'.length);
        if (Object.hasOwn(metrics, token)) {
            const [, min, max] = metrics[token];
            if (typeof value !== 'number' || !Number.isFinite(value) || value < min || value > max)
                throw new Error(`${key} must be a number from ${min} to ${max}`);
            validated.push([key, `${value}px`]);
        }
        else {
            if (typeof value !== 'string' || !/^(?:#[\da-f]{3,4}|#[\da-f]{6}(?:[\da-f]{2})?|transparent)$/i.test(value))
                throw new Error(`${key} must be a hex colour or transparent`);
            validated.push([key, value]);
        }
    }
    installUITheme(host);
    host.dataset.ddnUiTheme = name;
    for (const key of UI_THEME_TOKEN_NAMES)
        host.style.removeProperty(key);
    for (const [key, value] of validated)
        host.style.setProperty(key, value);
}
//# sourceMappingURL=ui-theme.js.map