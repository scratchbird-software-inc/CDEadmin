/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

define(['translations', 'sources/cdeadmin_ui/i18n/ui_catalogs'], function (translations, uiCatalogs) {
  const catalogRoot = (uiCatalogs && uiCatalogs.default) || uiCatalogs || {};
  const BUILTIN_UI_CATALOGS = catalogRoot.gettext || {};

  let currentLocale = 'en';
  let catalogRevision = 0;
  const reverseLookup = new Map();

  // Pre-seed reverseLookup across all 15 built-in languages so strings cached
  // in an earlier locale can always be retranslated immediately on switch.
  Object.keys(BUILTIN_UI_CATALOGS).forEach((loc) => {
    const cat = BUILTIN_UI_CATALOGS[loc];
    if (!cat || typeof cat !== 'object') return;
    Object.keys(cat).forEach((msgid) => {
      const val = cat[msgid];
      if (typeof val === 'string' && val && val !== msgid) {
        reverseLookup.set(val, msgid);
      }
    });
  });

  // Seed reverse lookup from any initial server-rendered translations.
  if (translations && typeof translations === 'object') {
    Object.keys(translations).forEach((msgid) => {
      const val = translations[msgid];
      if (typeof val === 'string' && val && val !== msgid) {
        reverseLookup.set(val, msgid);
      }
    });
  }

  function resolveBuiltinCatalog(normalizedLocale) {
    if (!normalizedLocale || normalizedLocale === 'en') return null;
    const underscored = normalizedLocale.replace(/-/g, '_');
    if (BUILTIN_UI_CATALOGS[underscored]) return BUILTIN_UI_CATALOGS[underscored];
    const lower = underscored.toLowerCase();
    if (lower.startsWith('zh_hans') || lower === 'zh_cn' || lower === 'zh') {
      return BUILTIN_UI_CATALOGS.zh_Hans_CN || null;
    }
    if (lower.startsWith('zh_hant') || lower === 'zh_tw' || lower === 'zh_hk') {
      return BUILTIN_UI_CATALOGS.zh_Hant_TW || null;
    }
    if (lower.startsWith('pt')) {
      return BUILTIN_UI_CATALOGS.pt_BR || null;
    }
    const baseLang = underscored.split('_')[0].toLowerCase();
    return BUILTIN_UI_CATALOGS[baseLang] || null;
  }

  function lookupRawTranslation(text) {
    if (typeof text !== 'string' || !text) return text;
    if (translations[text]) return translations[text];
    if (text.includes('…')) {
      const asciiKey = text.replace(/…/g, '...');
      if (translations[asciiKey]) return translations[asciiKey];
    } else if (text.includes('...')) {
      const ellipsisKey = text.replace(/\.\.\./g, '…');
      if (translations[ellipsisKey]) return translations[ellipsisKey];
    }
    return text;
  }

  function gettext(text) {
    let rawTranslation = lookupRawTranslation(text);
    if (typeof text === 'string' && typeof rawTranslation === 'string' && rawTranslation !== text) {
      reverseLookup.set(rawTranslation, text);
    }

    if (arguments.length <= 1) {
      return rawTranslation;
    }

    try {
      let replaceArgs = arguments;
      return rawTranslation.split('%s')
        .map(function(w, i) {
          if (i > 0) {
            if (i < replaceArgs.length) {
              return [replaceArgs[i], w].join('');
            } else {
              return ['%s', w].join('');
            }
          } else {
            return w;
          }
        })
        .join('');
    } catch (e) {
      console.error(e);
      return rawTranslation;
    }
  }

  gettext.setCatalog = function(nextCatalog, localeCode) {
    const normalizedLocale = String(localeCode || 'en').trim() || 'en';
    Object.keys(translations).forEach((k) => {
      delete translations[k];
    });
    if (normalizedLocale !== 'en') {
      const builtin = resolveBuiltinCatalog(normalizedLocale);
      if (builtin) {
        Object.keys(builtin).forEach((msgid) => {
          const val = builtin[msgid];
          translations[msgid] = val;
          if (val !== msgid) {
            reverseLookup.set(val, msgid);
          }
        });
      }
      if (nextCatalog && typeof nextCatalog === 'object') {
        Object.keys(nextCatalog).forEach((msgid) => {
          const val = nextCatalog[msgid];
          if (typeof val === 'string' && val) {
            translations[msgid] = val;
            if (val !== msgid) {
              reverseLookup.set(val, msgid);
            }
          }
        });
      }
    }
    const changed = currentLocale !== normalizedLocale || Boolean(nextCatalog);
    currentLocale = normalizedLocale;
    catalogRevision += 1;
    if (typeof document !== 'undefined' && document.documentElement) {
      document.documentElement.lang = normalizedLocale;
    }
    if (changed && typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
      window.dispatchEvent(
        new CustomEvent('scratchrobin:language-changed', {
          detail: {locale: currentLocale, revision: catalogRevision},
        })
      );
    }
    return catalogRevision;
  };

  gettext.getLocale = function() {
    return currentLocale;
  };

  gettext.getRevision = function() {
    return catalogRevision;
  };

  gettext.retranslate = function(value) {
    if (typeof value !== 'string' || !value) return value;
    const msgid = reverseLookup.get(value) || value;
    return gettext(msgid);
  };

  return gettext;
});
