const states = new WeakMap();
const MAX_FONT_BYTES = 16 * 1024 * 1024;
const MAX_FACES = 128;
const aliases = Object.freeze(Object.assign(Object.create(null), {
    sans: 'system-ui, sans-serif', serif: 'serif', mono: 'monospace', monospace: 'monospace', handwriting: 'cursive',
}));
const generics = new Set(['serif', 'sans-serif', 'monospace', 'cursive', 'fantasy', 'system-ui', 'ui-serif', 'ui-sans-serif', 'ui-monospace', 'ui-rounded', 'math']);
const standard = [
    { key: 'Inter', family: 'Inter', label: 'Inter', category: 'sans', source: 'standard', available: false, weights: ['100 900'], styles: ['normal', 'italic'] },
    { key: 'Source Serif 4', family: 'Source Serif 4', label: 'Source Serif 4', category: 'serif', source: 'standard', available: false, weights: ['200 900'], styles: ['normal', 'italic'] },
    { key: 'JetBrains Mono', family: 'JetBrains Mono', label: 'JetBrains Mono', category: 'monospace', source: 'standard', available: false, weights: ['100 800'], styles: ['normal', 'italic'] },
    { key: 'Caveat', family: 'Caveat', label: 'Caveat', category: 'handwriting', source: 'standard', available: false, weights: ['400 700'], styles: ['normal'] },
];
const system = [
    { key: 'sans', family: 'sans', label: 'System sans', category: 'sans', source: 'system', available: true, weights: ['400', '700'], styles: ['normal', 'italic'] },
    { key: 'serif', family: 'serif', label: 'System serif', category: 'serif', source: 'system', available: true, weights: ['400', '700'], styles: ['normal', 'italic'] },
    { key: 'mono', family: 'mono', label: 'System monospace', category: 'monospace', source: 'system', available: true, weights: ['400', '700'], styles: ['normal', 'italic'] },
    { key: 'handwriting', family: 'handwriting', label: 'System handwriting', category: 'handwriting', source: 'system', available: true, weights: ['400', '700'], styles: ['normal', 'italic'] },
];
function state(document) {
    let value = states.get(document);
    if (!value) {
        value = { installed: new Map(), pending: new Map() };
        states.set(document, value);
    }
    return value;
}
function quote(value) {
    // Quote family names as CSS strings; never interpolate raw names into export styles.
    return '"' + value.replace(/[\\"\x00-\x1f\x7f<>]/g, ch => '\\' + ch.codePointAt(0).toString(16) + ' ') + '"';
}
function names(key) {
    return key.split(',').map(name => name.trim().replace(/^(["'])(.*)\1$/, '$2')).filter(Boolean);
}
/** Existing generic aliases keep their system defaults, whether or not the pack is installed. */
export function fontFamily(key) {
    return aliases[key] ?? (names(key).map(name => generics.has(name) ? name : quote(name)).join(', ') || aliases.sans);
}
function familyName(value) {
    if (typeof value !== 'string' || !value.trim() || value.trim().length > 128 || /[\x00-\x1f\x7f,]/.test(value))
        throw new Error('Font family must contain 1–128 characters without controls or commas.');
    const name = value.trim();
    if (aliases[name.toLowerCase()] || generics.has(name.toLowerCase()))
        throw new Error('A local font cannot replace a generic font alias.');
    return name;
}
function fontWeight(value) {
    if (value === undefined || value === 'normal')
        return '400';
    if (value === 'bold')
        return '700';
    if (typeof value !== 'string' || !/^\d{1,4}(?: \d{1,4})?$/.test(value))
        throw new Error('Font weight must be a number or range from 1 to 1000.');
    const values = value.split(' ').map(Number);
    if (values.some(v => v < 1 || v > 1000) || (values.length === 2 && values[0] > values[1]))
        throw new Error('Font weight must be a number or ascending range from 1 to 1000.');
    return values.join(' ');
}
function format(bytes) {
    if (bytes.byteLength < 12 || bytes.byteLength > MAX_FONT_BYTES)
        throw new Error('Font files must be between 12 bytes and 16 MiB.');
    const magic = String.fromCharCode(...bytes.subarray(0, 4));
    if (magic === 'wOF2')
        return 'woff2';
    if (magic === 'wOFF')
        return 'woff';
    if (magic === 'OTTO')
        return 'otf';
    if (magic === '\x00\x01\x00\x00' || magic === 'true')
        return 'ttf';
    throw new Error('Select a WOFF2, WOFF, TTF or OTF font file.');
}
function decode(resource) {
    if (!resource || typeof resource !== 'object')
        throw new Error('Invalid font resource.');
    const family = familyName(resource.family), weight = fontWeight(resource.weight), style = resource.style ?? 'normal';
    if (!['normal', 'italic', 'oblique'].includes(style))
        throw new Error('Unsupported font style.');
    if (resource.category !== undefined && !['sans', 'serif', 'monospace', 'handwriting', 'custom'].includes(resource.category))
        throw new Error('Unsupported font category.');
    if (resource.source !== undefined && !['standard', 'custom'].includes(resource.source))
        throw new Error('Unsupported font source.');
    if (resource.license !== undefined && (typeof resource.license !== 'string' || resource.license.length > 65536 || /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/.test(resource.license)))
        throw new Error('Invalid font license notice.');
    if (typeof resource.dataURL !== 'string' || resource.dataURL.length > Math.ceil(MAX_FONT_BYTES / 3) * 4 + 40)
        throw new Error('Font resource exceeds 16 MiB.');
    const match = /^data:font\/(woff2|woff|ttf|otf);base64,([A-Za-z0-9+/]+={0,2})$/.exec(resource.dataURL);
    if (!match || match[2].length % 4 !== 0)
        throw new Error('Font resources must use a local base64 font data URL.');
    let binary;
    try {
        binary = atob(match[2]);
    }
    catch {
        throw new Error('Invalid font base64 data.');
    }
    const bytes = Uint8Array.from(binary, ch => ch.charCodeAt(0));
    if (format(bytes) !== match[1])
        throw new Error('Font MIME type does not match its binary format.');
    return { resource: Object.freeze({ family, dataURL: resource.dataURL, weight, style, category: resource.category ?? 'custom', source: resource.source ?? 'custom', ...(resource.license !== undefined ? { license: resource.license } : {}) }), bytes };
}
function slot(resource) { return JSON.stringify([familyName(resource.family).toLowerCase(), fontWeight(resource.weight), resource.style ?? 'normal']); }
function copyOption(value) { return { ...value, weights: [...value.weights], styles: [...value.styles] }; }
/** Standard entries report availability after installation; generic choices always remain usable. */
export function listFonts(document) {
    const options = [...system, ...standard].map(copyOption), byName = new Map(options.map(option => [option.family.toLowerCase(), option]));
    const installed = states.get(document)?.installed.values() ?? [];
    const resources = new Map();
    for (const { resource } of installed) {
        const key = resource.family.toLowerCase();
        resources.set(key, [...(resources.get(key) ?? []), resource]);
    }
    for (const [key, faces] of resources) {
        const first = faces[0], prior = byName.get(key);
        const option = { key: first.family, family: first.family, label: first.family, category: prior?.category ?? first.category ?? 'custom', source: first.source ?? 'custom', available: true,
            weights: [...new Set(faces.map(face => face.weight))], styles: [...new Set(faces.map(face => face.style))] };
        if (prior)
            options[options.indexOf(prior)] = option;
        else
            options.push(option);
    }
    return options;
}
/** Load only the named trusted standard resources; generic/system fonts perform no IO. */
export async function ensureFontResources(document, requests) {
    const host = document.defaultView;
    if (!host)
        return false;
    const selected = requests.flatMap(request => names(request.family).filter(name => !generics.has(name) && !aliases[name]).map(family => ({ family, style: request.style ?? 'normal' })));
    if (!selected.length)
        return false;
    const supplied = host.DDN_FONT_RESOURCES ?? [];
    const resources = host.DDN_LOAD_FONTS ? await host.DDN_LOAD_FONTS(selected) : supplied.filter(resource => selected.some(request => resource.family.toLowerCase() === request.family.toLowerCase() && ((resource.style ?? 'normal') === request.style || !supplied.some(face => face.family === resource.family && face.style === request.style) && (resource.style ?? 'normal') === 'normal'))), current = state(document);
    const missing = resources.some(resource => !current.installed.has(slot(resource)));
    if (missing)
        await installFontResources(document, resources);
    return missing;
}
/** Install an explicit local resource pack (or the page's DDN_FONT_RESOURCES) without fetching. */
export async function installFontResources(document, resources) {
    const loader = document.defaultView?.DDN_LOAD_FONTS;
    if (resources === undefined && loader)
        return installFontResources(document, await loader());
    const supplied = resources ?? document.defaultView?.DDN_FONT_RESOURCES ?? [];
    if (!Array.isArray(supplied) || supplied.length > MAX_FACES)
        throw new Error('A font pack may contain at most 128 faces.');
    if (!supplied.length)
        return listFonts(document);
    const FontFaceClass = document.defaultView?.FontFace;
    if (!FontFaceClass || !document.fonts?.add)
        throw new Error('This browser does not support local font loading.');
    const current = state(document), decoded = supplied.map(decode), unique = new Map();
    // Validate the entire pack before registering any face. Identical repeated installation is harmless.
    for (const entry of decoded) {
        const key = slot(entry.resource), previous = unique.get(key)?.resource ?? current.installed.get(key)?.resource ?? current.pending.get(key);
        if (previous && previous.dataURL !== entry.resource.dataURL)
            throw new Error('A different font is already registered for this family, weight and style.');
        unique.set(key, entry);
    }
    if (new Set([...current.installed.keys(), ...current.pending.keys(), ...unique.keys()]).size > MAX_FACES)
        throw new Error('A document may register at most 128 font faces.');
    await Promise.all([...unique].map(async ([key, entry]) => {
        if (current.installed.has(key))
            return;
        const pending = current.pending.get(key);
        if (pending)
            return pending.promise;
        const face = new FontFaceClass(entry.resource.family, entry.bytes.buffer, { weight: entry.resource.weight, style: entry.resource.style, display: 'swap' });
        const promise = face.load().then(loaded => {
            document.fonts.add(loaded);
            current.installed.set(key, { resource: entry.resource, face: loaded });
        }).finally(() => { current.pending.delete(key); });
        current.pending.set(key, { dataURL: entry.resource.dataURL, promise });
        return promise;
    }));
    document.dispatchEvent(new document.defaultView.Event('ddn:font-resources'));
    return listFonts(document);
}
/** Register a user-selected local binary; no file upload, storage or source-document mutation occurs. */
export async function loadFontFile(document, file, options = {}) {
    if (!file || !Number.isFinite(file.size) || file.size < 12 || file.size > MAX_FONT_BYTES)
        throw new Error('Font files must be between 12 bytes and 16 MiB.');
    const bytes = new Uint8Array(await file.arrayBuffer()), type = format(bytes);
    const family = familyName(options.family ?? file.name.replace(/\.(woff2?|ttf|otf)$/i, '').replace(/[_-]+/g, ' '));
    let binary = '';
    for (let offset = 0; offset < bytes.length; offset += 0x8000)
        binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
    const resource = { family, dataURL: `data:font/${type};base64,${btoa(binary)}`, weight: options.weight ?? '400', style: options.style ?? 'normal', source: 'custom', category: 'custom' };
    await installFontResources(document, [resource]);
    return listFonts(document).find(option => option.family.toLowerCase() === family.toLowerCase());
}
/** Copy loaded local resources for host-managed persistence, optionally limited to used font keys. */
export function getFontResources(document, usedFontKeys) {
    const used = usedFontKeys === undefined ? undefined : new Set([...usedFontKeys].flatMap(key => names(aliases[key] ?? key)).map(name => name.toLowerCase()));
    return [...(states.get(document)?.installed.values() ?? [])].filter(({ resource }) => !used || used.has(resource.family.toLowerCase())).map(({ resource }) => ({ ...resource }));
}
/** Embed only selected, successfully loaded local resources in a standalone SVG style element. */
export function fontCSS(document, usedFontKeys) {
    const notices = new Set();
    return getFontResources(document, usedFontKeys).map(resource => {
        const notice = resource.license && !notices.has(resource.license) ? '/* ' + resource.license.replaceAll('*/', '* /') + ' */\n' : '';
        if (resource.license)
            notices.add(resource.license);
        return notice + `@font-face{font-family:${quote(resource.family)};src:url("${resource.dataURL}");font-weight:${resource.weight};font-style:${resource.style};font-display:block;}`;
    }).join('\n');
}
//# sourceMappingURL=fonts.js.map