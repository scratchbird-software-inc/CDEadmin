//////////////////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////////////////

import translations from 'translations';

const BUILTIN_UI_CATALOGS = {
  fr: {
    'Data Navigator': 'Navigateur de données',
    'Navigator': 'Navigateur',
    'Connectors': 'Connecteurs',
    'Connectors (%s)': 'Connecteurs (%s)',
    'Enabled Database Connectors (%s)': 'Connecteurs de bases de données activés (%s)',
    'Database Engines (On / Off)': 'Moteurs de base de données (Marche / Arrêt)',
    'Database Engines (On / Off)…': 'Moteurs de base de données (Marche / Arrêt)…',
    'Local listener detected': 'Écoute locale détectée',
    'Register…': 'Enregistrer…',
    'Register Server…': 'Enregistrer un serveur…',
    'Verify / Connect…': 'Vérifier / Connecter…',
    'Verify Endpoint': 'Vérifier le point de terminaison',
    'Create Database…': 'Créer une base de données…',
    'Register Database…': 'Enregistrer une base…',
    'Open in Separate Tab…': 'Ouvrir dans un onglet séparé…',
    'Remove Server…': 'Supprimer le serveur…',
    'Properties': 'Propriétés',
    'Statistics': 'Statistiques',
    'Dependencies': 'Dépendances',
    'Dependents': 'Dépendants',
    'Apply Changes': 'Appliquer les modifications',
    'Save Settings': 'Enregistrer les paramètres',
    'ScratchRobin Preferences & Workspace Settings': 'Préférences et paramètres ScratchRobin',
    'User or principal': 'Utilisateur ou principal',
    'Save Password': 'Enregistrer le mot de passe',
    'Hide password': 'Masquer le mot de passe',
    'Show password': 'Afficher le mot de passe',
    'Cancel': 'Annuler',
    'Close': 'Fermer',
    'Apply': 'Appliquer',
    'Help': 'Aide',
    'Settings': 'Paramètres',
    'New': 'Nouveau',
    'Save': 'Enregistrer',
    'Undo': 'Annuler',
    'Redo': 'Rétablir',
  },
  de: {
    'Data Navigator': 'Daten-Navigator',
    'Navigator': 'Navigator',
    'Connectors': 'Konnektoren',
    'Connectors (%s)': 'Konnektoren (%s)',
    'Verify Endpoint': 'Endpunkt überprüfen',
    'Properties': 'Eigenschaften',
    'Statistics': 'Statistiken',
    'Apply Changes': 'Änderungen anwenden',
    'Save Settings': 'Einstellungen speichern',
    'User or principal': 'Benutzer oder Prinzipal',
    'Cancel': 'Abbrechen',
    'Close': 'Schließen',
    'Apply': 'Anwenden',
    'Help': 'Hilfe',
    'Settings': 'Einstellungen',
  },
  ja: {
    'Data Navigator': 'データナビゲーター',
    'Navigator': 'ナビゲーター',
    'Connectors': 'コネクター',
    'Connectors (%s)': 'コネクター (%s)',
    'Verify Endpoint': 'エンドポイントの検証',
    'Properties': 'プロパティ',
    'Statistics': '統計情報',
    'Apply Changes': '変更を適用',
    'Save Settings': '設定を保存',
    'Cancel': 'キャンセル',
    'Close': '閉じる',
    'Apply': '適用',
    'Help': 'ヘルプ',
    'Settings': '設定',
  },
};

let currentLocale = 'en';
let catalogRevision = 0;
const reverseLookup = new Map();

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

export default function gettext(text, ...replaceArgs) {
  let rawTranslation = lookupRawTranslation(text);
  if (typeof text === 'string' && typeof rawTranslation === 'string' && rawTranslation !== text) {
    reverseLookup.set(rawTranslation, text);
  }

  if (replaceArgs.length === 0) {
    return rawTranslation;
  }

  try {
    return rawTranslation.split('%s')
      .map(function(w, i) {
        if (i > 0) {
          if (i - 1 < replaceArgs.length) {
            return [replaceArgs[i - 1], w].join('');
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
  const baseLang = normalizedLocale.split(/[-_]/)[0];
  Object.keys(translations).forEach((k) => {
    delete translations[k];
  });
  if (normalizedLocale !== 'en') {
    const builtin = BUILTIN_UI_CATALOGS[normalizedLocale] || BUILTIN_UI_CATALOGS[baseLang] || null;
    if (builtin) {
      Object.keys(builtin).forEach((msgid) => {
        const val = builtin[msgid];
        translations[msgid] = val;
        reverseLookup.set(val, msgid);
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
