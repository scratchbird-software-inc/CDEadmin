import { uiIcon } from '../../viewer/src/ui-icons.js';
export function installWebsiteNavigation(mode) {
    const parameters = new URLSearchParams(location.search);
    const links = document.createElement('nav');
    links.className = 'app-site-nav';
    links.setAttribute('aria-label', 'Website and utilities');
    const siteLinks = document.createElement('div'), modeLinks = document.createElement('div');
    siteLinks.className = 'app-site-links';
    modeLinks.className = 'app-site-links app-mode-links';
    links.append(siteLinks, modeLinks);
    const navigationStyle = document.createElement('style');
    navigationStyle.textContent = `.app-site-nav{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font:12px Inter,system-ui,sans-serif;min-width:0}.app-site-nav .app-mode-links{border:1px solid var(--ddn-ui-border);border-radius:9px;padding:2px;background:color-mix(in srgb,var(--ddn-ui-bg) 70%,transparent)}.app-site-nav .app-mode-links a{padding:4px 8px}@media(max-width:1050px){.app-site-nav .app-site-links:not(.app-mode-links) a span{display:none}}@media(max-width:750px){.app-site-nav{width:100%;justify-content:space-between}}`;
    document.head.append(navigationStyle);
    const navigation = [];
    for (const [title, path, icon] of [['DDN home', '../index.html', 'layers'], ['Gallery', '../gallery/index.html', 'grid'], ['Guide', '../guide/index.html', 'info'], ['Viewer', 'view', 'eye'], ['Designer', 'design', 'pen'], ['Verifier', 'verify', 'check']]) {
        const link = document.createElement('a');
        const text = document.createElement('span');
        text.textContent = title;
        link.append(uiIcon(document, icon), text);
        link.title = path.includes('.html') ? title : `Switch to the ${title.toLowerCase()}`;
        if ((mode === 'designer' && title === 'Designer') || (mode === 'verifier' && title === 'Verifier') || (mode === 'viewer' && title === 'Viewer'))
            link.setAttribute('aria-current', 'page');
        (path.includes('.html') ? siteLinks : modeLinks).append(link);
        navigation.push({ link, path: path });
    }
    const refreshNavigation = () => {
        const theme = document.body.dataset.ddnUiTheme ?? 'dark';
        for (const { link, path } of navigation) {
            if (path.includes('.html'))
                link.href = path + '?theme=' + encodeURIComponent(theme);
            else {
                const query = new URLSearchParams(parameters);
                query.set('mode', path);
                query.set('theme', theme);
                link.href = './index.html?' + query;
            }
        }
    };
    refreshNavigation();
    document.addEventListener('ddn:interface-theme', refreshNavigation);
    const slot = document.querySelector('.app-site-slot');
    if (slot)
        slot.append(links);
    else
        document.body.prepend(links);
    if (parameters.get('embed') === '1') {
        links.style.display = 'none';
        const style = document.createElement('style');
        style.textContent = '.app-source,.app-tools,.app-bar,nav[aria-label="Website and utilities"],.app-status{display:none}.app-main{display:block;flex:none;height:100dvh;min-height:300px;padding:0}.app-surface{height:100%;border:0;border-radius:0;box-shadow:none}';
        document.head.append(style);
    }
}
//# sourceMappingURL=website-navigation.js.map