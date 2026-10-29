import { getViewerHandle } from '../../viewer/src/native.js';
import { uiIcon } from '../../viewer/src/ui-icons.js';
import { quoteText } from '../../language/src/index.js';
import { createStandardDialog } from './dialogs.js';
import { viewTypePicker, diagramHeader } from './view-picker.js';
import { viewLayoutDialog, viewLayoutSource } from './view-layout-picker.js';
import { getViewSurfacePreset } from '../../profiles/src/view-surfaces.js';
import { profileLoadingHost } from '../../runtime/src/profile-loading.js';
import { registrations } from '../../runtime/src/registry.js';
const wizardStyle = `
.ddn-document-choices{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:14px 0 6px}
.ddn-ui-dialog .ddn-document-choice{display:flex;flex-direction:column;align-items:center;justify-content:flex-start;gap:9px;min-width:0;padding:18px 12px;border-radius:12px;white-space:normal;text-align:center}
.ddn-document-choice>.ddn-ui-icon{width:36px;height:36px;color:var(--ddn-ui-accent)}
.ddn-document-choice strong{font-size:13px;line-height:1.35;overflow-wrap:anywhere}
.ddn-document-choice small{font-size:11px;line-height:1.4;color:var(--ddn-ui-muted)}
.ddn-workarea-options{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:14px 0 0}
.ddn-workarea-option{display:block;min-width:0;border-radius:10px}
.ddn-ui-dialog .ddn-workarea-option button{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;width:100%;min-height:86px;padding:12px;pointer-events:none}
.ddn-workarea-option .ddn-ui-icon{width:28px;height:28px}
.ddn-workarea-option-hints{min-height:46px;padding-top:6px;font-size:11px;line-height:1.4;color:var(--ddn-ui-muted)}
.ddn-workarea-option-hints p[hidden]{display:none}
@media(max-width:340px){.ddn-document-choices{grid-template-columns:1fr}.ddn-ui-dialog .ddn-document-choice{padding:12px}.ddn-document-choice>.ddn-ui-icon{width:28px;height:28px}}
`;
let nextHint = 0;
/** Document hosts own replacement and persistence; this wizard only chooses new source. */
export function newDiagramDialog(viewer, create) {
    const handle = getViewerHandle(viewer), document = handle.ownerDocument;
    const profiles = profileLoadingHost(handle.runtime)?.profiles ?? registrations(handle.runtime.registry).profiles ?? [];
    let workareaName = 'Untitled', viewName = 'NewView', mode = 'workarea', layout = 'dynamic';
    const field = (body, caption, value) => {
        const label = document.createElement('label'), input = document.createElement('input');
        input.type = 'text';
        input.value = value;
        input.autocomplete = 'off';
        label.append(document.createTextNode(caption), input);
        body.append(label);
        return input;
    };
    const style = (dialog) => {
        const sheet = document.createElement('style');
        sheet.textContent = wizardStyle;
        dialog.body.prepend(sheet);
        dialog.element.style.setProperty('--ddn-ui-dialog-width', '480px');
    };
    const readName = (input) => {
        if (!input.value.trim()) {
            input.focus();
            throw Error('Enter a workarea name.');
        }
        workareaName = input.value.trim();
    };
    const back = (dialog, label, next) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = label;
        button.addEventListener('click', () => { if (dialog.element.getAttribute('aria-busy') === 'true')
            return; dialog.close(); next(); });
        dialog.footer.prepend(button);
    };
    function chooseDocument() {
        const dialog = createStandardDialog(handle.overlays, { title: 'New document', cancelLabel: 'Cancel' });
        style(dialog);
        const name = field(dialog.body, 'Workarea name', workareaName);
        const choices = document.createElement('div');
        choices.className = 'ddn-document-choices';
        for (const [value, caption, icon, description] of [
            ['workarea', 'Create WorkArea', 'layers', 'Arrange multiple views and documents in one workarea.'],
            ['standalone', 'Create Standalone View', 'fit', 'Create a single view with a workarea that fits its size.'],
        ]) {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'ddn-document-choice';
            button.setAttribute('aria-label', caption);
            const title = document.createElement('strong');
            title.textContent = caption;
            const detail = document.createElement('small');
            detail.textContent = description;
            button.append(uiIcon(document, icon), title, detail);
            button.addEventListener('click', () => {
                try {
                    readName(name);
                    mode = value;
                    dialog.close();
                    if (mode === 'workarea')
                        setupWorkarea();
                    else
                        chooseLayout();
                }
                catch (error) {
                    dialog.showError(error);
                }
            });
            choices.append(button);
        }
        dialog.body.append(choices);
    }
    function setupWorkarea() {
        const dialog = createStandardDialog(handle.overlays, { title: 'Create WorkArea', applyLabel: 'Apply', onApply() {
                readName(name);
                dialog.close();
                chooseLayout();
            } });
        style(dialog);
        const name = field(dialog.body, 'Workarea name', workareaName);
        const options = document.createElement('div');
        options.className = 'ddn-workarea-options';
        const hints = document.createElement('div');
        hints.className = 'ddn-workarea-option-hints';
        for (const [caption, icon, text] of [
            ['Settings', 'settings', 'change defaults for the workarea or load a saved template'],
            ['Permissions', 'link', 'setup user permissions for sharing and concurrent editing'],
        ]) {
            // A disabled button cannot receive keyboard focus; its wrapper exposes the same hint.
            const wrapper = document.createElement('span');
            wrapper.className = 'ddn-workarea-option';
            wrapper.tabIndex = 0;
            wrapper.title = text;
            wrapper.setAttribute('role', 'group');
            wrapper.setAttribute('aria-label', `${caption} — unavailable in the open-source designer`);
            const button = document.createElement('button');
            button.type = 'button';
            button.disabled = true;
            button.textContent = caption;
            button.title = text;
            button.prepend(uiIcon(document, icon));
            const hint = document.createElement('p');
            hint.id = 'ddn-workarea-option-hint-' + (++nextHint);
            hint.setAttribute('role', 'tooltip');
            hint.textContent = text;
            hint.hidden = true;
            wrapper.setAttribute('aria-describedby', hint.id);
            button.setAttribute('aria-describedby', hint.id);
            const updateHint = () => { hint.hidden = !wrapper.matches(':hover') && document.activeElement !== wrapper; };
            for (const event of ['mouseenter', 'mouseleave', 'focus', 'blur'])
                wrapper.addEventListener(event, updateHint);
            wrapper.append(button);
            options.append(wrapper);
            hints.append(hint);
        }
        dialog.body.append(options, hints);
        back(dialog, 'Back', () => { workareaName = name.value; chooseDocument(); });
    }
    function chooseLayout() {
        viewLayoutDialog(handle.overlays, { selected: layout,
            onContinue(preset) { layout = preset; chooseView(); },
            onBack(preset) { layout = preset; if (mode === 'workarea')
                setupWorkarea();
            else
                chooseDocument(); },
        });
    }
    function chooseView() {
        let type;
        const dialog = createStandardDialog(handle.overlays, { title: 'Choose diagram type', applyLabel: 'Create view', lockWhileApplying: true, async onApply() {
                viewName = name.value.trim();
                if (!viewName) {
                    name.focus();
                    throw Error('Enter a view name.');
                }
                if (viewName === workareaName) {
                    name.focus();
                    throw Error('The view and workarea must have different names.');
                }
                if (!profiles.some(profile => profile.id === type.value))
                    throw Error('Choose an available diagram type.');
                const header = 'workarea ' + quoteText(workareaName) + '\n' + (mode === 'standalone' ? '    with\n        mode standalone\n' : '');
                await create(header + diagramHeader(viewName, type.value) + '\n' + viewLayoutSource(layout));
                const view = handle.scene()?.entries.find(entry => entry.definition.owner === 'view');
                if (view) {
                    handle.select(view.definition.ref, view.item.occurrence);
                    handle.container.dispatchEvent(new CustomEvent('ddn:action', { detail: { action: 'activate-view-tools' } }));
                }
            } });
        const summary = document.createElement('p');
        summary.className = 'ddn-appearance-message';
        summary.textContent = 'View layout: ' + getViewSurfacePreset(layout).label;
        dialog.body.append(summary);
        type = viewTypePicker(dialog.body, profiles, 'Diagram type');
        const settings = document.createElement('div');
        settings.className = 'ddn-view-type-settings';
        const name = field(settings, 'View name', viewName === workareaName ? viewName + ' View' : viewName);
        dialog.body.append(settings);
        const update = () => {
            settings.hidden = !type.value;
            dialog.applyButton.disabled = !type.value;
            if (type.value) {
                name.focus({ preventScroll: true });
                name.select();
            }
        };
        type.onChange(update);
        update();
        back(dialog, 'Back', () => { viewName = name.value; chooseLayout(); });
    }
    chooseDocument();
}
//# sourceMappingURL=new-diagram.js.map